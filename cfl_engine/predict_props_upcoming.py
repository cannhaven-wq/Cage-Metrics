"""Live serving for the PROPS output layer: per-fighter significant-strike and
takedown predictions (and a fight-duration read) for an UPCOMING card, straight
from the audited count models + Monte-Carlo simulator.

This is the "predict tonight's props" companion to predict_upcoming.py (which
serves the win model). It does NOT touch the DB — read-only, prints a plain-
English report and writes a preview CSV.

PIPELINE
  1. Pull the card's still-pending fights (winner_id is null) from Supabase.
     A fighter who also appears in a GRADED fight on the same event is a stale
     scraper double-booking; their pending row is dropped (dead-booking guard).
  2. career_state() folds every completed fight into each fighter's covariate
     accumulators (features/build_count_features.py — the exact same fold the
     training panel uses, verified zero train/serve skew).
  3. Fit the significant-strike NB2 and takedown hurdle models on the full count
     panel, and the duration hazard model on the full duration panel.
  4. Simulate each fight (Monte-Carlo) and report, per fighter: expected /
     median significant strikes with an 80% range, expected takedowns, P(1+ TD),
     P(2+ TD); and per fight: P(goes the distance) and the round-end split.

DURATION CAVEAT (v1): the duration hazard model is fed a LEAGUE-BASELINE
covariate row, so the round-end split / P(distance) is the league-average
3-round curve, identical across fights — NOT yet fighter-adjusted. Significant
strikes and takedowns ARE fully fighter-specific. Personalising duration needs
the ~50-covariate duration serve features (features/build_features.py) built for
upcoming fights; that is the clean next step. Strike/TD totals still vary per
fight because they are driven by each fighter's own rates within the fought
rounds.

Credentials: env SUPABASE_URL + a service key (SUPABASE_SECRET_KEY /
SUPABASE_SERVICE_ROLE_KEY / SUPABASE_SERVICE_KEY). Read-only.

Usage (from repo root):
  python cfl_engine/predict_props_upcoming.py                 # today's card
  python cfl_engine/predict_props_upcoming.py --event-id 4221
  python cfl_engine/predict_props_upcoming.py --date 2026-08-08 --within-days 2
  python cfl_engine/predict_props_upcoming.py --sims 40000
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "models"))
sys.path.insert(0, os.path.join(HERE, "features"))

import build_count_features as bcf          # noqa: E402  (career_state / serve_feats)
from counts import SigStrikeModel, TakedownModel  # noqa: E402
from duration import DurationHazardModel     # noqa: E402
from simulate import FightSimulator, build_context  # noqa: E402
from export_data import fetch_all            # noqa: E402  (paginating PostgREST reader)

DATA_DIR = os.path.join(HERE, "data")
FEAT_DIR = os.path.join(HERE, "features")
PREVIEW = os.path.join(HERE, os.pardir, "out_real")

# Sig-strike over/under lines to quote P(over) at (illustrative — no posted prop
# board is captured yet; these are round half-points near typical UFC totals).
SIG_LINES = (25.5, 35.5, 45.5, 55.5, 65.5, 75.5)


def _env_key() -> str:
    for name in ("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY"):
        if os.environ.get(name):
            return os.environ[name]
    sys.exit("No Supabase service key in env (SUPABASE_SECRET_KEY / "
             "SUPABASE_SERVICE_ROLE_KEY / SUPABASE_SERVICE_KEY).")


# --------------------------------------------------------------------- card pull
def pull_card(base_url, key, event_id, date, within_days, log=print):
    """Return (pending_df, dropped_dead) for the target card.

    Target events: an explicit --event-id, else every event on [date, date+within].
    Pending fights = winner_id is null. A fighter appearing in a GRADED fight on
    the same event has already fought → their pending row is a dead booking.
    """
    if event_id is not None:
        ev = fetch_all(base_url, key, "events",
                       f"select=id,event_date,name&id=eq.{event_id}")
    else:
        lo = date.isoformat()
        hi = (date + dt.timedelta(days=within_days)).isoformat()
        ev = fetch_all(base_url, key, "events",
                       "select=id,event_date,name"
                       f"&event_date=gte.{lo}&event_date=lte.{hi}&order=event_date")
    ev = {e["id"]: e for e in ev if e.get("event_date")}
    if not ev:
        return pd.DataFrame(), []
    idlist = ",".join(str(i) for i in ev)
    fights = fetch_all(base_url, key, "fights",
                       "select=id,event_id,fighter_a_id,fighter_b_id,winner_id,"
                       "weight_class,scheduled_rounds"
                       f"&event_id=in.({idlist})&order=event_id,id")

    # fighters who already have a result on the same event (dead-booking guard)
    graded_by_event = {}
    for f in fights:
        if f["winner_id"] is not None:
            s = graded_by_event.setdefault(f["event_id"], set())
            s.update([f["fighter_a_id"], f["fighter_b_id"]])

    rows, dropped = [], []
    for f in fights:
        if f["winner_id"] is not None:
            continue
        if f["fighter_a_id"] is None or f["fighter_b_id"] is None:
            continue
        e = ev[f["event_id"]]
        gone = graded_by_event.get(f["event_id"], set())
        if f["fighter_a_id"] in gone or f["fighter_b_id"] in gone:
            dropped.append(f["id"])
            log(f"      dead-booking: dropping fight {f['id']} "
                f"(a fighter already has a result on {e['name']})")
            continue
        rows.append({
            "fight_id": f["id"], "event_id": f["event_id"],
            "event_name": e["name"], "event_date": e["event_date"],
            "fighter_a_id": f["fighter_a_id"], "fighter_b_id": f["fighter_b_id"],
            "weight_class": f["weight_class"],
            "rounds_sched": f["scheduled_rounds"] or 3,
        })
    return pd.DataFrame(rows), dropped


def name_map(base_url, key, ids):
    if not ids:
        return {}
    out = {}
    ids = list(ids)
    for i in range(0, len(ids), 200):
        chunk = ",".join(str(x) for x in ids[i:i + 200])
        for x in fetch_all(base_url, key, "fighters", f"select=id,name&id=in.({chunk})"):
            out[x["id"]] = x["name"]
    return out


# --------------------------------------------------------------------- modeling
def league_round_probs(log=print):
    """League-baseline [P(R1), P(R2), P(R3), P(decision)] from the duration hazard
    model at covariate means. v1 duration read — same for every 3-round fight."""
    dur = pd.read_parquet(os.path.join(FEAT_DIR, "duration_features.parquet"))
    dur["event_date"] = pd.to_datetime(dur["event_date"])
    cov = json.load(open(os.path.join(FEAT_DIR, "feature_manifest.json")))["covariate_columns"]
    dm = DurationHazardModel().fit(dur, cov)
    base = dur.drop_duplicates("fight_id").iloc[:1].copy()
    for c in cov:
        base[c] = dur[c].mean()
    d = dm.fight_distribution(base, calibrated=False).iloc[0]
    probs = [float(d.p_ends_r1), float(d.p_ends_r2), float(d.p_ends_r3), float(d.p_decision)]
    log(f"  duration (league baseline): R1 {probs[0]:.0%}  R2 {probs[1]:.0%}  "
        f"R3 {probs[2]:.0%}  decision {probs[3]:.0%}  (E[min] {float(d.exp_minutes):.1f})")
    return probs, float(d.exp_minutes)


def fit_count_models(log=print):
    panel = pd.read_parquet(os.path.join(FEAT_DIR, "count_features.parquet"))
    panel["event_date"] = pd.to_datetime(panel["event_date"])
    log(f"  count panel: {len(panel):,} fighter-rounds "
        f"({panel.event_date.min().date()} → {panel.event_date.max().date()})")
    sig = SigStrikeModel().fit(panel)
    td = TakedownModel().fit(panel)
    return sig, td


# --------------------------------------------------------------------- main
def run(base_url, key, event_id, date, within_days, sims, seed, log=print):
    log("[1/4] pulling card ...")
    card, dropped = pull_card(base_url, key, event_id, date, within_days, log=log)
    if card.empty:
        log("      no pending fights found for the target card.")
        return pd.DataFrame()
    log(f"      {len(card)} pending fight(s) on "
        f"{card['event_name'].iloc[0]} ({card['event_date'].iloc[0]})"
        + (f"; dropped {len(dropped)} dead booking(s)" if dropped else ""))

    log("[2/4] building career-to-date covariates (all completed fights) ...")
    acc, g, priors = bcf.career_state()
    names = name_map(base_url, key,
                     set(card.fighter_a_id) | set(card.fighter_b_id))

    log("[3/4] fitting models ...")
    sig, td = fit_count_models(log=log)
    round_probs, exp_min = league_round_probs(log=log)
    simr = FightSimulator(sig, td)

    log(f"[4/4] simulating {sims:,} draws/fight ...")
    out_rows = []
    for i, r in enumerate(card.itertuples(index=False)):
        a_id, b_id = int(r.fighter_a_id), int(r.fighter_b_id)
        a_feats = bcf.serve_feats(acc[a_id], acc[b_id], priors)
        b_feats = bcf.serve_feats(acc[b_id], acc[a_id], priors)
        ctx = build_context(r.fight_id, round_probs, a_feats, b_feats,
                            rounds_sched=int(r.rounds_sched))
        res = simr.simulate(ctx, n=sims, seed=seed + i)

        went_distance = res.draws["finished"] == 0     # reached the scorecards
        for side, fid_self, fid_opp, sig_key, td_key, feats in (
                ("a", a_id, b_id, "a_sig", "a_td", a_feats),
                ("b", b_id, a_id, "b_sig", "b_td", b_feats)):
            s = res.summary(sig_key)
            sig_draws = res.draws[sig_key]
            td_draws = res.draws[td_key]
            # Distance-conditional = the "if it goes the full N rounds" projection.
            # This is the clean prop number: it is driven ONLY by the fighter's own
            # per-minute rates over full rounds, independent of the duration baseline.
            sig_d = sig_draws[went_distance]
            td_d = td_draws[went_distance]
            out_rows.append({
                "fight_id": r.fight_id, "event": r.event_name,
                "weight_class": r.weight_class, "side": side,
                "fighter": names.get(fid_self, str(fid_self)),
                "opponent": names.get(fid_opp, str(fid_opp)),
                "exp_min_tape": round(float(feats["own_exp_min"]), 1),
                "debut": acc[fid_self]["nf"] == 0,
                # ---- distance-conditional (recommended prop projection) ----
                "sig_dist_mean": round(float(sig_d.mean()), 1),
                "sig_dist_median": round(float(np.median(sig_d)), 0),
                "sig_dist_p20": round(float(np.percentile(sig_d, 20)), 0),
                "sig_dist_p80": round(float(np.percentile(sig_d, 80)), 0),
                "td_dist_exp": round(float(td_d.mean()), 2),
                # ---- full marginal (integrates finish risk) ----
                "sig_mean": round(s["mean"], 1), "sig_median": round(float(s["p50"]), 0),
                "sig_p10": round(float(np.percentile(sig_draws, 10)), 0),
                "sig_p90": round(float(np.percentile(sig_draws, 90)), 0),
                "td_exp": round(float(td_draws.mean()), 2),
                "p_td_1plus": round(float((td_draws >= 1).mean()), 3),
                "p_td_2plus": round(float((td_draws >= 2).mean()), 3),
                **{f"sig_p_over_{int(L)}": round(res.line(sig_key, L)["over"], 3)
                   for L in SIG_LINES},
                "p_distance": round(res.p_gtd(), 3),
                "p_finish": round(res.finish_rate(), 3),
            })
    return pd.DataFrame(out_rows)


def print_report(df, exp_min=None):
    if df.empty:
        print("\nNo predictions produced.")
        return
    ev = df["event"].iloc[0]
    print("\n" + "=" * 82)
    print(f"PROP PREDICTIONS — {ev}")
    print("=" * 82)
    print("Numbers are per fighter, whole fight. 'sig' = significant strikes landed,")
    print("shown as the projection IF THE FIGHT GOES ITS FULL ROUNDS (the clean prop")
    print("number). 'TD' = takedowns landed. P(1+/2+) integrate finish risk.")
    print("Fight length / P(distance) is a league-average baseline (v1 — see header).\n")
    for fid, g in df.groupby("fight_id", sort=False):
        a, b = g.iloc[0], g.iloc[1]
        print(f"— {a['fighter']} vs {b['fighter']}  ({a['weight_class']})")
        print(f"    P(goes the distance) {a['p_distance']:.0%}   P(finish) {a['p_finish']:.0%}")
        for row in (a, b):
            flag = "  [DEBUT — league-avg profile]" if row["debut"] else (
                "  [thin tape]" if row["exp_min_tape"] < 30 else "")
            print(f"    {row['fighter']:<22s} "
                  f"sig ~{row['sig_dist_mean']:.0f} "
                  f"(likely {row['sig_dist_p20']:.0f}–{row['sig_dist_p80']:.0f})   "
                  f"TD ~{row['td_dist_exp']:.2f}  "
                  f"P(1+) {row['p_td_1plus']:.0%}  P(2+) {row['p_td_2plus']:.0%}{flag}")
        print()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--event-id", type=int, default=None,
                    help="explicit event id to price (overrides --date)")
    ap.add_argument("--date", default=None,
                    help="target date YYYY-MM-DD (default: today)")
    ap.add_argument("--within-days", type=int, default=1,
                    help="with --date, also include events up to N days later (default 1)")
    ap.add_argument("--sims", type=int, default=20000, help="Monte-Carlo draws per fight")
    ap.add_argument("--seed", type=int, default=20260808)
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")   # Windows console is cp1252
    except Exception:
        pass

    base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not base_url:
        sys.exit("SUPABASE_URL not set in env.")
    key = _env_key()
    date = (dt.date.fromisoformat(args.date) if args.date else dt.date.today())

    df = run(base_url, key, args.event_id, date, args.within_days, args.sims, args.seed)
    if df.empty:
        return
    print_report(df)

    os.makedirs(PREVIEW, exist_ok=True)
    outp = os.path.join(PREVIEW, "props_preview.csv")
    df.to_csv(outp, index=False)
    print(f"preview CSV → {os.path.abspath(outp)}")


if __name__ == "__main__":
    main()
