"""PRED-002 development-years export. The ONLY code in PRED-002 that reads the
database; the experiment itself (research/experiments/PRED-002/) reads files.

PRED-001 §2: development code may read fights dated before 2025-01-01 and
nothing after. This export asks the database for development-years events only,
then passes every fight through pred_protocol.dev_only(), which RAISES on a
sealed date rather than dropping it. A fight dated 2025+ cannot reach the
experiment through this file.

Writes, to --outdir:
  fights.csv       engine contract + event_id, priced flag, BFO closing prices
  fight_stats.csv  engine contract (per fight, per fighter totals)
  fighters.csv     fighter_id, name, dob, height_in, reach_in, stance
  rounds.csv       per fight, per fighter: distance / clinch / ground landed,
                   takedowns landed, control seconds, fight seconds
  manifest.json    counts and the sha256 of every file

Read-only: GET requests through PostgREST with the service key.

  python research/pred002_data/export_dev.py --outdir pred002_dev
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from statistics import median

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir))
sys.path.insert(0, os.path.join(REPO, "cfl_engine"))
sys.path.insert(0, os.path.join(REPO, "research", "protocol"))

from export_data import (STAT_KEYS, _env_key, fetch_all, fight_seconds,  # noqa: E402
                         map_result, prob_to_american)
from pred_protocol import DEV_END, dev_only  # noqa: E402

SPLITS = {  # rounds.csv column -> fight_rounds stem
    "distance_landed": "distance_landed",
    "clinch_landed": "clinch_landed",
    "ground_landed": "ground_landed",
    "td_landed": "td_landed",
    "ctrl_seconds": "ctrl_seconds",
}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def chunked(xs, n):
    xs = list(xs)
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="pred002_dev")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = _env_key()
    dev_end = str(DEV_END)

    events = fetch_all(base, key, "events",
                       f"select=id,event_date,is_upcoming&event_date=lt.{dev_end}&order=id")
    events = [e for e in events if e["event_date"] and not e["is_upcoming"]]
    ev = {e["id"]: e for e in events}

    fight_cols = ",".join(
        ["id", "event_id", "fighter_a_id", "fighter_b_id", "winner_id", "method",
         "weight_class", "scheduled_rounds", "end_round", "end_time"]
        + [f"{s}_{stem}" for stem in STAT_KEYS.values() for s in ("a", "b")])
    fights = []
    for ids in chunked(sorted(ev), 150):
        fights += fetch_all(base, key, "fights",
                            f"select={fight_cols}&event_id=in.({','.join(map(str, ids))})&order=id")
    # the gate: every fight carries its event date and must be development data
    rows = dev_only([{**f, "event_date": ev[f["event_id"]]["event_date"]} for f in fights])
    fids = [f["id"] for f in rows]

    split_cols = ",".join(["fight_id", "fighter_a_id", "fighter_b_id"]
                          + [f"{s}_{stem}" for stem in SPLITS.values() for s in ("a", "b")])
    rounds = []
    for ids in chunked(fids, 200):
        rounds += fetch_all(base, key, "fight_rounds",
                            f"select={split_cols}&fight_id=in.({','.join(map(str, ids))})&order=id")
    books = {b["id"]: b["name"] for b in fetch_all(base, key, "odds_books", "select=id,name&order=id")}
    bfo = {i for i, n in books.items() if n and n.upper().startswith("BFO")}
    odds = []
    for ids in chunked(fids, 200):
        odds += fetch_all(base, key, "fight_odds",
                          "select=fight_id,fighter_id,book_id,implied_prob,american_odds,is_closer"
                          f"&is_closer=eq.true&fight_id=in.({','.join(map(str, ids))})&order=id")
    fighters = fetch_all(base, key, "fighters",
                         "select=id,name,dob,height_in,reach_in,stance&order=id")

    # ---- dead-booking dedupe, the export_data rule: a stats-less duplicate of
    # the same pair on the same card is a ghost; two rows that both carry stats
    # are a real same-night rematch and both stay
    has_round = {r["fight_id"] for r in rounds}

    def evidence(f):
        return f["id"] in has_round or any(
            f.get(f"{s}_{stem}") is not None for stem in STAT_KEYS.values() for s in ("a", "b"))

    groups = {}
    for f in rows:
        groups.setdefault((f["event_id"], tuple(sorted((f["fighter_a_id"], f["fighter_b_id"])))), []).append(f)
    skip = set()
    for g in groups.values():
        if len(g) < 2:
            continue
        ev_rows = [f for f in g if evidence(f)]
        if len(ev_rows) >= 2:
            continue
        keep = ev_rows[0] if ev_rows else max(g, key=lambda f: f["id"])
        skip |= {f["id"] for f in g if f["id"] != keep["id"]}

    # ---- BFO closing consensus per fighter: median implied probability across
    # BFO closer rows, as PRED-001's manifest defines "priced"
    by = {}
    for o in odds:
        if o["book_id"] not in bfo:
            continue
        p = o["implied_prob"]
        if p is None and o["american_odds"] is not None and abs(o["american_odds"]) >= 100:
            a = float(o["american_odds"])
            p = 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)
        if p is None or not (0.0 < float(p) < 1.0):
            continue
        by.setdefault((o["fight_id"], o["fighter_id"]), []).append(float(p))

    fight_rows, stat_rows, round_rows = [], [], []
    excluded = {"duplicate_booking": 0, "no_result": 0, "winner_not_in_corners": 0,
                "winnerless_finish": 0, "no_corners": 0}
    agg = {}
    for r in rounds:
        for side, col in (("a", "fighter_a_id"), ("b", "fighter_b_id")):
            acc = agg.setdefault((r["fight_id"], r[col]), {k: 0 for k in SPLITS})
            for k, stem in SPLITS.items():
                acc[k] += r.get(f"{side}_{stem}") or 0
    for f in rows:
        if f["id"] in skip:
            excluded["duplicate_booking"] += 1
            continue
        if f["fighter_a_id"] is None or f["fighter_b_id"] is None:
            excluded["no_corners"] += 1
            continue
        res = map_result(f["winner_id"], f["fighter_a_id"], f["fighter_b_id"], f["method"])
        if isinstance(res, tuple):
            excluded[res[1]] += 1
            continue
        pa = by.get((f["id"], f["fighter_a_id"]))
        pb = by.get((f["id"], f["fighter_b_id"]))
        secs = fight_seconds(f["end_round"], f["end_time"], f["scheduled_rounds"], f["method"])
        fight_rows.append({
            "fight_id": f["id"], "event_id": f["event_id"], "event_date": f["event_date"],
            "fighter_a_id": f["fighter_a_id"], "fighter_b_id": f["fighter_b_id"],
            "result": res, "weight_class": f["weight_class"],
            "n_rounds_sched": f["scheduled_rounds"], "method": f["method"],
            "odds_a": prob_to_american(median(pa)) if pa else None,
            "odds_b": prob_to_american(median(pb)) if pb else None,
            "imp_a": median(pa) if pa else None, "imp_b": median(pb) if pb else None,
            "priced": bool(pa and pb),
        })
        corner = {}
        for side, col in (("a", "fighter_a_id"), ("b", "fighter_b_id")):
            vals = {k: f.get(f"{side}_{stem}") for k, stem in STAT_KEYS.items()}
            if all(v is None for v in vals.values()):
                corner[f[col]] = None
            else:
                corner[f[col]] = {k: (v if v is not None else 0) for k, v in vals.items()}
        if any(v is not None for v in corner.values()):
            for fid, vals in corner.items():
                stat_rows.append({"fight_id": f["id"], "fighter_id": fid,
                                  **(vals or {k: 0 for k in STAT_KEYS}), "fight_seconds": secs})
        for col in ("fighter_a_id", "fighter_b_id"):
            a = agg.get((f["id"], f[col]))
            if a is not None:
                round_rows.append({"fight_id": f["id"], "fighter_id": f[col], **a,
                                   "fight_seconds": secs})

    fights_df = pd.DataFrame(fight_rows).sort_values(["event_date", "fight_id"])
    assert fights_df["event_date"].max() < dev_end, "sealed fight in the export"
    out = {
        "fights.csv": fights_df,
        "fight_stats.csv": pd.DataFrame(stat_rows),
        "fighters.csv": pd.DataFrame([{"fighter_id": x["id"], "name": x["name"], "dob": x["dob"],
                                       "height_in": x.get("height_in"), "reach_in": x.get("reach_in"),
                                       "stance": x.get("stance")} for x in fighters]),
        "rounds.csv": pd.DataFrame(round_rows),
    }
    manifest = {"dev_end_exclusive": dev_end, "counts": {}, "excluded": excluded, "sha256": {}}
    for name, df in out.items():
        path = os.path.join(args.outdir, name)
        df.to_csv(path, index=False)
        manifest["counts"][name] = int(len(df))
        manifest["sha256"][name] = sha256_file(path)
    manifest["last_event_date"] = str(fights_df["event_date"].max())
    manifest["priced_fights"] = int(fights_df["priced"].sum())
    with open(os.path.join(args.outdir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    print(json.dumps(manifest, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
