"""PROP-0001 prediction locks for the DUR-001 experiment.

PROP-0001 is the FROZEN fight-duration research model (2026-08-06 gate,
cfl_engine/harness/walkforward_report.json): the discrete-time logistic hazard
in models/duration.py on the point-in-time covariate set in
features/build_features.py (49 columns), isotonic-recalibrated. It is NOT the
league-baseline `props_v1.p_distance` published on the Prop Board.

This script writes one immutable row per (fight, threshold) into
`prop_model_locks` BEFORE the fight, using only information available at lock
time:

  * training data = every completed 3-round UFC fight with event_date strictly
    before `training_cutoff` (= the lock date, UTC);
  * fighter histories = only rounds/fights strictly before that cutoff;
  * the model is refit from scratch on that data (the spec is frozen, the data
    grows), then applied to the upcoming fight's point-in-time feature row.

Threshold mapping (frozen). The hazard model gives per-round finish
probabilities h1..h3. A sportsbook total of X.5 rounds settles at 2:30 of round
X+1, so we need the share of round-(X+1) finishes that land at or before 2:30,
phi_{X+1}, estimated point-in-time from the same training data (~0.45):

    P(over X.5) = S_X * (1 - phi_{X+1} * h_{X+1}),   S_0 = 1, S_1 = 1-h1, S_2 = (1-h1)(1-h2)
    P(goes the distance) = S_2 * (1 - h3)

Side symmetry: the training panel randomises corner order, so the fitted signed
diffs are not exactly antisymmetric. A served fight is scored under both
orderings and the hazards averaged, so the lock does not depend on which corner
ufcstats listed first. The a/b-ordered feature row is stored on the lock.

Scope: 3-round fights only (the model was never fit on 5-rounders). Upcoming
fights are scraped with scheduled_rounds=3 by default, so main events and title
fights are excluded on their flags, not on scheduled_rounds.

Immutability: prop_model_locks rejects UPDATE/DELETE/TRUNCATE by trigger, and an
insert trigger rejects any lock whose training_cutoff is after actual_lock_at,
whose fight already has a result, or whose best-known start time is not after
the lock. Re-runs skip fights already locked under this model_version (first
lock wins). A changed spec is a new MODEL_VERSION and new rows.

Usage (repo root; needs SUPABASE_URL + a service key in env):
  python cfl_engine/dur001/lock_prop0001.py                 # dry-run, next 8 days
  python cfl_engine/dur001/lock_prop0001.py --execute       # write locks
  python cfl_engine/dur001/lock_prop0001.py --event-id 4433 --execute
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from collections import defaultdict

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ENGINE, "features"))
sys.path.insert(0, os.path.join(ENGINE, "models"))

import build_features as bf                    # noqa: E402  (frozen feature code)
from duration import DurationHazardModel       # noqa: E402  (frozen model code)

MODEL_NAME = "PROP-0001"
# Freeze tag. Bump ONLY if the spec (features, model, calibration recipe,
# threshold mapping) changes. Training data growing over time is not a change.
MODEL_VERSION = "PROP-0001@v1"
THRESHOLDS = (0.5, 1.5, 2.5)          # every 3-round total a book can post
CAL_WINDOW_DAYS = 365                 # isotonic fit on the trailing year, OOS to the base fit
K, K_SLOPE, K_FIGHTS = 25.0, 8.0, 5.0 # build_features.py defaults (frozen)
SEED = 42                             # build_features.py corner-randomisation seed
MIDPOINT_SECONDS = 150                # 2:30 — where an X.5 total settles
LOCK_TABLE = "prop_model_locks"
EPS = 1e-6


# ----------------------------------------------------------------------------- io
def env_key() -> str:
    for name in ("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY"):
        if os.environ.get(name):
            return os.environ[name]
    sys.exit("No Supabase service key in env (SUPABASE_SECRET_KEY / "
             "SUPABASE_SERVICE_ROLE_KEY / SUPABASE_SERVICE_KEY).")


def git_commit() -> str:
    try:
        sha = subprocess.check_output(["git", "rev-parse", "--short=12", "HEAD"],
                                      cwd=ENGINE, text=True).strip()
        dirty = subprocess.run(["git", "diff", "--quiet"], cwd=ENGINE).returncode != 0
        return sha + ("-dirty" if dirty else "")
    except Exception:
        return "unknown"


def rest_post(base_url, key, path, body):
    req = urllib.request.Request(
        f"{base_url}/rest/v1/{path}", data=json.dumps(body, default=str).encode(),
        method="POST",
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Content-Type": "application/json", "Prefer": "return=representation"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        txt = resp.read().decode()
        return json.loads(txt) if txt else []


def load_all(base_url, key, log=print):
    log("pulling events, fighters, fights, fight_rounds ...")
    events = bf.fetch_all(base_url, key, "events", "select=id,name,event_date,is_upcoming&order=id")
    fighters = bf.fetch_all(base_url, key, "fighters",
                            "select=id,name,dob,height_in,reach_in,stance&order=id")
    fights = bf.fetch_all(base_url, key, "fights",
                          "select=id,event_id,fighter_a_id,fighter_b_id,winner_id,method,"
                          "weight_class,scheduled_rounds,end_round,end_time,is_main_event,"
                          "is_title_fight&order=id")
    round_cols = ("fight_id,fighter_a_id,fighter_b_id,round_number,"
                  + ",".join(f"{s}_{stem}" for stem in bf.ROUND_STATS for s in ("a", "b")))
    rounds = bf.fetch_all(base_url, key, "fight_rounds", f"select={round_cols}&order=id")
    log(f"  events={len(events)} fighters={len(fighters)} fights={len(fights)} rounds={len(rounds)}")
    return events, fighters, fights, rounds


# ------------------------------------------------------------ point-in-time data
def end_seconds(end_time):
    try:
        m, s = str(end_time).split(":")
        return int(m) * 60 + int(s)
    except Exception:
        return None


class PITWorld:
    """Everything the model may know at `cutoff` (a UTC date): completed fights
    with event_date < cutoff, and nothing else. Built once per lock run."""

    def __init__(self, events, fighters, fights, rounds, cutoff: dt.date, log=print):
        self.cutoff = cutoff
        ev = {e["id"]: e for e in events}
        self.fight_date = {}
        for f in fights:
            e = ev.get(f["event_id"])
            if not e or not e.get("event_date") or e.get("is_upcoming"):
                continue
            d = dt.date.fromisoformat(e["event_date"])
            if d >= cutoff:
                continue                                  # the future does not exist
            if f.get("winner_id") is None and not f.get("method"):
                continue                                  # unresolved: not evidence
            self.fight_date[f["id"]] = pd.Timestamp(d)
        known = set(self.fight_date)
        self.fights = [f for f in fights if f["id"] in known]
        self.rounds = [r for r in rounds if r["fight_id"] in known]
        self.corners = {f["id"]: (f["fighter_a_id"], f["fighter_b_id"]) for f in self.fights}
        self.round_recs = bf.build_round_records(self.rounds, self.fight_date, self.corners)
        self.fight_hist = bf.build_fight_history(self.fights, self.fight_date)
        self.pri = bf.league_priors(self.round_recs, K, K_SLOPE)
        self.lr = bf.league_fight_rates(self.fight_hist)
        self.fight_pos = {fid: {x["fight_id"]: i for i, x in enumerate(recs)}
                          for fid, recs in self.fight_hist.items()}
        self.round_start = {}
        for fid, recs in self.round_recs.items():
            d = {}
            for i, x in enumerate(recs):
                d.setdefault(x["fight_id"], i)
            self.round_start[fid] = d
        self.fmeta = {f["id"]: f for f in fighters}
        log(f"  PIT world @ {cutoff}: {len(self.fights)} completed fights, "
            f"{len(self.rounds)} round rows, {len(self.round_recs)} fighters with tape")

    def feats_asof(self, fighter_id, fight_id, when: pd.Timestamp) -> dict:
        """Identical to build_features.main's feats_asof: strictly-prior rounds and
        fights. For a fight not in the histories (an upcoming one) the prefix is
        the whole (already cutoff-filtered) history."""
        prior_r = []
        rr = self.round_recs.get(fighter_id)
        if rr:
            cut = self.round_start.get(fighter_id, {}).get(fight_id, len(rr))
            prior_r = rr[:cut]
        prior_f = []
        fh = self.fight_hist.get(fighter_id)
        if fh:
            pos = self.fight_pos[fighter_id].get(fight_id, len(fh))
            prior_f = fh[:pos]
        d = {}
        d.update(bf.round_profile_asof(prior_r, self.pri, K, K_SLOPE))
        d.update(bf.fight_history_asof(prior_f, self.lr, K_FIGHTS))
        d["style"] = bf.style_asof(prior_r)
        meta = self.fmeta.get(fighter_id, {})
        dob = meta.get("dob")
        d["age"] = ((when - pd.Timestamp(dob)).days / 365.25) if dob else np.nan
        d["reach_in"] = pd.to_numeric(meta.get("reach_in"), errors="coerce")
        d["height_in"] = pd.to_numeric(meta.get("height_in"), errors="coerce")
        d["stance"] = bf.stance_flag(meta.get("stance"))
        return d

    # ---- training panel (mirrors build_features.main, with the cutoff applied)
    def training_panel(self, seed=SEED):
        rng = np.random.default_rng(seed)
        rows = []
        for f in self.fights:
            if f["scheduled_rounds"] != 3:
                continue
            when = self.fight_date[f["id"]]
            if when.year < bf.MIN_YEAR:
                continue
            kind, fr = bf.classify_outcome(f["method"], f["end_round"], f["scheduled_rounds"])
            if kind in ("nc", "bad"):
                continue
            a_id, b_id = f["fighter_a_id"], f["fighter_b_id"]
            if a_id is None or b_id is None:
                continue
            if rng.random() < 0.5:
                a_id, b_id = b_id, a_id
            fa = self.feats_asof(a_id, f["id"], when)
            fb = self.feats_asof(b_id, f["id"], when)
            row = {"fight_id": f["id"], "event_date": when, "outcome_kind": kind,
                   "finish_round": fr, "reached": (fr if kind == "finish" else 3),
                   "end_seconds": end_seconds(f.get("end_time")) if kind == "finish" else None}
            row.update(bf.matchup_features(fa, fb))
            rows.append(row)
        fdf = pd.DataFrame(rows).sort_values(["event_date", "fight_id"]).reset_index(drop=True)
        cov = bf.covariate_columns()
        pp_rows = []
        for r in fdf.itertuples(index=False):
            rd = r._asdict()
            for rnum in range(1, rd["reached"] + 1):
                pr = {"fight_id": rd["fight_id"], "event_date": rd["event_date"], "round": rnum,
                      "event": 1 if (rd["outcome_kind"] == "finish" and rnum == rd["finish_round"]) else 0,
                      "r1": float(rnum == 1), "r2": float(rnum == 2), "r3": float(rnum == 3)}
                for c in cov:
                    pr[c] = rd[c]
                pp_rows.append(pr)
        pp = pd.DataFrame(pp_rows)
        med = pp[cov].median(numeric_only=True)
        pp[cov] = pp[cov].fillna(med)
        # phi_r: share of round-r finishes at or before 2:30 (point-in-time)
        phi = {}
        fin = fdf[fdf.outcome_kind == "finish"]
        for r in (1, 2, 3):
            s = fin[fin.finish_round == r]["end_seconds"].dropna()
            phi[r] = float((s <= MIDPOINT_SECONDS).mean()) if len(s) else 0.5
        return pp, fdf, cov, med, phi


# ------------------------------------------------------------------- the model
def fit_prop0001(pp: pd.DataFrame, cov, cutoff: dt.date, log=print):
    """Frozen recipe: hazard fit on everything before (cutoff - 365d), isotonic
    fit on the trailing year's raw hazards (out-of-sample to that fit), then the
    hazard is refit on all training rows and carries that isotonic map."""
    cal_start = pd.Timestamp(cutoff - dt.timedelta(days=CAL_WINDOW_DAYS))
    pre, cal = pp[pp.event_date < cal_start], pp[pp.event_date >= cal_start]
    base = DurationHazardModel().fit(pre, cov)
    base.fit_calibration(cal)
    full = DurationHazardModel().fit(pp, cov)
    full.iso_ = base.iso_
    log(f"  PROP-0001 fit: {pp.fight_id.nunique()} fights / {len(pp)} person-period rows; "
        f"calibration rows={len(cal)} (from {cal_start.date()}); "
        f"regularized={full.regularized_}")
    return full, {"n_train_rows": int(len(pp)), "n_train_fights": int(pp.fight_id.nunique()),
                  "n_cal_rows": int(len(cal)), "cal_start": str(cal_start.date()),
                  "regularized_fallback": bool(full.regularized_)}


def threshold_probs(h1, h2, h3, phi):
    S = {0: 1.0, 1: 1.0 - h1, 2: (1.0 - h1) * (1.0 - h2)}
    h = {1: h1, 2: h2, 3: h3}
    out = {}
    for X in (0, 1, 2):
        out[X + 0.5] = S[X] * (1.0 - phi[X + 1] * h[X + 1])
    out["distance"] = S[2] * (1.0 - h3)
    out["p_ends"] = {1: h1, 2: S[1] * h2, 3: S[2] * h3}
    return out


def serve_fight(model, world, cov, med, phi, fight, when: pd.Timestamp):
    """Hazards for one upcoming fight, averaged over both corner orderings."""
    a, b = fight["fighter_a_id"], fight["fighter_b_id"]
    fa = world.feats_asof(a, fight["id"], when)
    fb = world.feats_asof(b, fight["id"], when)
    rows = []
    for x, y in ((fa, fb), (fb, fa)):
        r = bf.matchup_features(x, y)
        rows.append(r)
    df = pd.DataFrame(rows)[cov].astype(float)
    df = df.fillna(med)
    dist = model.fight_distribution(df, calibrated=True)
    h1 = float(dist.haz_r1.mean()); h2 = float(dist.haz_r2.mean()); h3 = float(dist.haz_r3.mean())
    feats_ab = {k: (None if (isinstance(v, float) and np.isnan(v)) else float(v)) for k, v in rows[0].items()}
    return (h1, h2, h3), threshold_probs(h1, h2, h3, phi), feats_ab


# --------------------------------------------------------------------- the card
def upcoming_card(events, fights, lock_date: dt.date, within_days: int, event_id=None, log=print):
    ev = {e["id"]: e for e in events if e.get("event_date")}
    if event_id is not None:
        ids = {event_id}
    else:
        hi = lock_date + dt.timedelta(days=within_days)
        ids = {i for i, e in ev.items()
               if lock_date <= dt.date.fromisoformat(e["event_date"]) <= hi}
    card, skipped = [], defaultdict(int)
    graded_by_event = defaultdict(set)
    for f in fights:
        if f["event_id"] in ids and f.get("winner_id") is not None:
            graded_by_event[f["event_id"]].update([f["fighter_a_id"], f["fighter_b_id"]])
    for f in fights:
        if f["event_id"] not in ids:
            continue
        if f.get("winner_id") is not None or f.get("method"):
            skipped["already_settled"] += 1; continue
        if f["fighter_a_id"] is None or f["fighter_b_id"] is None:
            skipped["missing_corner"] += 1; continue
        if f["fighter_a_id"] in graded_by_event[f["event_id"]] or f["fighter_b_id"] in graded_by_event[f["event_id"]]:
            skipped["dead_booking"] += 1; continue
        if f.get("is_main_event") or f.get("is_title_fight") or (f.get("scheduled_rounds") or 3) != 3:
            skipped["not_3_rounds"] += 1; continue           # PROP-0001 scope
        e = ev[f["event_id"]]
        card.append({**f, "event_date": e["event_date"], "event_name": e["name"]})
    # duplicate pending bookings on one card: keep the newest scrape (highest id)
    seen = {}
    for f in sorted(card, key=lambda x: x["id"]):
        for fid in (f["fighter_a_id"], f["fighter_b_id"]):
            seen[(f["event_id"], fid)] = f["id"]
    keep = {f["id"] for f in card
            if seen[(f["event_id"], f["fighter_a_id"])] == f["id"] and seen[(f["event_id"], f["fighter_b_id"])] == f["id"]}
    dropped = [f["id"] for f in card if f["id"] not in keep]
    if dropped:
        skipped["duplicate_booking"] += len(dropped)
    card = [f for f in card if f["id"] in keep]
    if skipped:
        log(f"  card filter skipped: {dict(skipped)}")
    return card


def existing_locks(base_url, key, fight_ids):
    if not fight_ids:
        return set()
    out = set()
    ids = ",".join(str(i) for i in fight_ids)
    for r in bf.fetch_all(base_url, key, LOCK_TABLE,
                          f"select=fight_id,market_type,threshold,side&model_version=eq.{MODEL_VERSION}"
                          f"&fight_id=in.({ids})"):
        out.add((r["fight_id"], r["market_type"], float(r["threshold"]) if r["threshold"] is not None else None, r["side"]))
    return out


# ------------------------------------------------------------------------ main
def build_lock_rows(card, model, world, cov, med, phi, fit_info, lock_time: dt.datetime,
                    cutoff: dt.date, code_version, names, log=print):
    rows, generated_at = [], dt.datetime.now(dt.timezone.utc)
    for f in card:
        when = pd.Timestamp(dt.date.fromisoformat(f["event_date"]))
        (h1, h2, h3), tp, feats = serve_fight(model, world, cov, med, phi, f, when)
        fh = hashlib.sha256(json.dumps(feats, sort_keys=True).encode()).hexdigest()[:16]
        base = {
            "fight_id": f["id"], "event_id": f["event_id"], "event_date": f["event_date"],
            "model_name": MODEL_NAME, "model_version": MODEL_VERSION,
            # actual_lock_at is NOT sent: the ledger stamps it with now() at insert,
            # so it can never be earlier than generated_at or claimed after the fact.
            "generated_at": generated_at.isoformat(),
            "training_cutoff": dt.datetime.combine(cutoff, dt.time(0, 0), tzinfo=dt.timezone.utc).isoformat(),
            "training_n_fights": fit_info["n_train_fights"],
            "haz_r1": round(h1, 6), "haz_r2": round(h2, 6), "haz_r3": round(h3, 6),
            "phi_r1": round(phi[1], 6), "phi_r2": round(phi[2], 6), "phi_r3": round(phi[3], 6),
            "p_ends_r1": round(tp["p_ends"][1], 6), "p_ends_r2": round(tp["p_ends"][2], 6),
            "p_ends_r3": round(tp["p_ends"][3], 6), "p_decision": round(tp["distance"], 6),
            "features": feats, "code_version": code_version, "feature_hash": fh,
            "notes": f"{names.get(f['fighter_a_id'], f['fighter_a_id'])} vs "
                     f"{names.get(f['fighter_b_id'], f['fighter_b_id'])} | {f['event_name']} | "
                     f"hazards averaged over both corner orderings; calibration rows={fit_info['n_cal_rows']}",
        }
        for X in THRESHOLDS:
            p = float(np.clip(tp[X], EPS, 1 - EPS))
            rows.append({**base, "market_type": "total_rounds", "threshold": X, "side": "over",
                         "predicted_probability": round(p, 6)})
        rows.append({**base, "market_type": "goes_distance", "threshold": None, "side": "yes",
                     "predicted_probability": round(float(np.clip(tp["distance"], EPS, 1 - EPS)), 6)})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--event-id", type=int, default=None)
    ap.add_argument("--within-days", type=int, default=8)
    ap.add_argument("--execute", action="store_true", help="write locks (default: dry-run)")
    ap.add_argument("--out", default=os.path.join(ENGINE, os.pardir, "out_real", "prop0001_locks_preview.csv"))
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not base_url:
        sys.exit("SUPABASE_URL not set.")
    key = env_key()

    lock_time = dt.datetime.now(dt.timezone.utc)
    cutoff = lock_time.date()                       # strictly-before-today evidence only
    code_version = git_commit()
    print(f"[lock] {MODEL_NAME} {MODEL_VERSION} | lock_time={lock_time.isoformat()} "
          f"| training_cutoff={cutoff} | code={code_version}")

    events, fighters, fights, rounds = load_all(base_url, key)
    card = upcoming_card(events, fights, cutoff, args.within_days, args.event_id)
    if not card:
        print("[lock] no eligible 3-round pending fights in the window — nothing to lock.")
        return
    print(f"[lock] {len(card)} eligible fight(s) on: "
          + ", ".join(sorted({f['event_name'] for f in card})))

    world = PITWorld(events, fighters, fights, rounds, cutoff)
    pp, fdf, cov, med, phi = world.training_panel()
    print(f"  training panel: {len(fdf)} fights / {len(pp)} rows, {len(cov)} covariates; "
          f"phi(<=2:30 by round)={ {k: round(v, 3) for k, v in phi.items()} }")
    model, fit_info = fit_prop0001(pp, cov, cutoff)

    names = {x["id"]: x["name"] for x in fighters}
    rows = build_lock_rows(card, model, world, cov, med, phi, fit_info, lock_time, cutoff, code_version, names)

    have = existing_locks(base_url, key, [f["id"] for f in card])
    fresh = [r for r in rows if (r["fight_id"], r["market_type"], r["threshold"], r["side"]) not in have]
    print(f"[lock] {len(rows)} lock row(s) computed; {len(rows) - len(fresh)} already on the ledger "
          f"for {MODEL_VERSION} (skipped, first lock wins); {len(fresh)} new.")

    prev = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    prev.drop(columns=["features"]).to_csv(args.out, index=False)
    for f in card:
        r = {x["threshold"]: x["predicted_probability"] for x in rows
             if x["fight_id"] == f["id"] and x["market_type"] == "total_rounds"}
        d = next(x["predicted_probability"] for x in rows if x["fight_id"] == f["id"] and x["market_type"] == "goes_distance")
        print(f"  fight {f['id']:>6} {names.get(f['fighter_a_id'], '?'):<22} vs {names.get(f['fighter_b_id'], '?'):<22} "
              f"O0.5 {r[0.5]:.3f}  O1.5 {r[1.5]:.3f}  O2.5 {r[2.5]:.3f}  distance {d:.3f}")
    print(f"preview CSV -> {os.path.abspath(args.out)}")

    if not args.execute:
        print("\nDRY-RUN — nothing written. Re-run with --execute to lock.")
        return
    if not fresh:
        print("nothing new to write.")
        return
    written = rest_post(base_url, key, LOCK_TABLE, fresh)
    print(f"[lock] wrote {len(written)} immutable lock row(s) to {LOCK_TABLE}.")


if __name__ == "__main__":
    main()
