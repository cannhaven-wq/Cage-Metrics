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
import urllib.request

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

MODEL_VERSION = "props_v1"
PROJ_TABLE = "prop_projections"

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
    df = pd.DataFrame(rows)
    if not df.empty:
        df, dup_dropped = _dedupe_duplicate_fighters(df, log)
        dropped += dup_dropped
    return df, dropped


def _dedupe_duplicate_fighters(df, log=print):
    """On a fully-upcoming card there is no result to catch a scraper
    double-booking, so a fighter appearing in >1 pending fight on the same event
    is a phantom. Keep the newest scrape (highest fight_id) — matching
    export_data's canonical choice. Returns (kept_df, dropped_ids)."""
    keep = set(df["fight_id"])
    for _eid, grp in df.groupby("event_id"):
        booked = {}
        for r in grp.itertuples(index=False):
            for fid in (r.fighter_a_id, r.fighter_b_id):
                booked.setdefault(fid, []).append(r.fight_id)
        for fighter, fids in booked.items():
            if len(set(fids)) > 1:
                for drop in sorted(set(fids))[:-1]:   # keep the highest fight_id
                    if drop in keep:
                        keep.discard(drop)
                        log(f"      duplicate booking: dropping fight {drop} "
                            f"(fighter {fighter} also booked in {max(fids)})")
    dropped = sorted(set(df["fight_id"]) - keep)
    return df[df["fight_id"].isin(keep)].reset_index(drop=True), dropped


def detect_main_fight(card, names, log=print):
    """Best-effort main-event id from the event headline (e.g.
    'UFC 330: Makhachev vs. Machado Garry'): the fight whose BOTH fighters'
    surnames appear after the colon. None if no confident match."""
    ev = str(card["event_name"].iloc[0] or "")
    headline = (ev.split(":", 1)[1] if ":" in ev else ev).lower()
    if not headline.strip():
        return None
    for r in card.itertuples(index=False):
        an = names.get(int(r.fighter_a_id), "") or ""
        bn = names.get(int(r.fighter_b_id), "") or ""
        a_sur = an.split()[-1].lower() if an.split() else ""
        b_sur = bn.split()[-1].lower() if bn.split() else ""
        if a_sur and b_sur and a_sur in headline and b_sur in headline:
            log(f"      main event: fight {int(r.fight_id)} ({an} vs {bn})")
            return int(r.fight_id)
    return None


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
def run(base_url, key, event_id, date, within_days, sims, seed,
        main_fight_id=None, log=print):
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
    if main_fight_id is None:
        main_fight_id = detect_main_fight(card, names, log=log)

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
                "fight_id": r.fight_id, "event_id": int(r.event_id),
                "event": r.event_name, "event_date": str(r.event_date),
                "weight_class": r.weight_class, "side": side,
                "fighter_id": int(fid_self),
                "fighter": names.get(fid_self, str(fid_self)),
                "opponent": names.get(fid_opp, str(fid_opp)),
                "main_event": bool(main_fight_id and int(r.fight_id) == int(main_fight_id)),
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


# --------------------------------------------------------------------- publish
def _to_db_rows(df):
    """Map the per-fighter output frame to prop_projections rows (one per corner)."""
    rows = []
    for r in df.itertuples(index=False):
        rows.append({
            "event_id": int(r.event_id),
            "event_name": r.event,
            "event_date": r.event_date,
            "fight_id": int(r.fight_id),
            "weight_class": r.weight_class,
            "main_event": bool(r.main_event),
            "side": r.side,
            "fighter_id": int(r.fighter_id),
            "fighter_name": r.fighter,
            "opponent_name": r.opponent,
            "p_distance": float(r.p_distance),
            "sig_proj": float(r.sig_dist_mean),
            "sig_lo": float(r.sig_dist_p20),
            "sig_hi": float(r.sig_dist_p80),
            "sig_med": float(r.sig_dist_median),
            "td_proj": float(r.td_dist_exp),
            "p_td_1plus": float(r.p_td_1plus),
            "p_td_2plus": float(r.p_td_2plus),
            "thin_tape": bool(r.exp_min_tape < 30 or r.debut),
            "model_version": MODEL_VERSION,
        })
    return rows


def _rest(base_url, key, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{base_url}/rest/v1/{path}", data=data, method=method,
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Content-Type": "application/json",
                 "Prefer": "return=representation"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        txt = resp.read().decode()
        return json.loads(txt) if txt else []


def publish(base_url, key, df, log=print):
    """Full-table replace: the board only ever shows ONE card, so wipe
    prop_projections and insert the current card's rows. Keeps the table from
    accumulating finished cards; the view hides it once the card's date passes."""
    rows = _to_db_rows(df)
    _rest(base_url, key, "DELETE", f"{PROJ_TABLE}?id=gt.0")   # clear all
    inserted = _rest(base_url, key, "POST", PROJ_TABLE, rows)
    events = sorted({row["event_id"] for row in rows})
    log(f"  published {len(inserted)} row(s) for event(s) {events} to {PROJ_TABLE} "
        f"(table replaced).")
    return len(inserted)


def find_next_event(base_url, key, within_days, log=print):
    """Soonest UPCOMING event (today .. today+within_days) that still has at least
    one pending fight. Returns event_id or None. Used by --auto so a scheduled run
    always targets the next card and skips one that has already finished."""
    today = dt.date.today()
    horizon = (today + dt.timedelta(days=within_days)).isoformat()
    events = fetch_all(base_url, key, "events",
                       "select=id,event_date,name"
                       f"&event_date=gte.{today.isoformat()}&event_date=lte.{horizon}"
                       "&order=event_date")
    for e in events:                       # soonest first
        pend = fetch_all(base_url, key, "fights",
                         f"select=id&event_id=eq.{e['id']}&winner_id=is.null&limit=1")
        if pend:
            log(f"      next card: {e['name']} ({e['event_date']}, id {e['id']})")
            return e["id"]
    log(f"      no upcoming card with pending fights within {within_days} days.")
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--event-id", type=int, default=None,
                    help="explicit event id to price (overrides --date)")
    ap.add_argument("--date", default=None,
                    help="target date YYYY-MM-DD (default: today)")
    ap.add_argument("--within-days", type=int, default=1,
                    help="with --date, also include events up to N days later (default 1)")
    ap.add_argument("--auto", action="store_true",
                    help="target the soonest upcoming card with pending fights within "
                         "--within-days (for scheduled runs); overrides --date")
    ap.add_argument("--main-fight-id", type=int, default=None,
                    help="fight id to flag as the main event (highlighted on the page)")
    ap.add_argument("--sims", type=int, default=20000, help="Monte-Carlo draws per fight")
    ap.add_argument("--seed", type=int, default=20260808)
    ap.add_argument("--execute", action="store_true",
                    help="publish to the prop_projections table (default: dry-run)")
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

    event_id = args.event_id
    if args.auto and event_id is None:
        wd = max(args.within_days, 8)   # look a card-week ahead by default
        print(f"[auto] finding the next card within {wd} days ...")
        event_id = find_next_event(base_url, key, wd)
        if event_id is None:
            print("[auto] nothing to publish — no upcoming card in the window. "
                  "(The board keeps showing the last card until its date passes.)")
            return

    df = run(base_url, key, event_id, date, args.within_days, args.sims,
             args.seed, main_fight_id=args.main_fight_id)
    if df.empty:
        return
    print_report(df)

    os.makedirs(PREVIEW, exist_ok=True)
    outp = os.path.join(PREVIEW, "props_preview.csv")
    df.to_csv(outp, index=False)
    print(f"preview CSV → {os.path.abspath(outp)}")

    if args.execute:
        print("\nPublishing to prop_projections ...")
        publish(base_url, key, df)
        print("Done. props.html (reading v_prop_projections_current) will show it.")
    else:
        print("\nDRY-RUN — nothing published. Re-run with --execute to publish "
              "to the site table.")


if __name__ == "__main__":
    main()
