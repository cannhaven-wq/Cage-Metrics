"""Export the engine's point-in-time Elo per fighter to the fighter_ratings table.

Usage:
    PYTHONPATH=cfl_engine python cfl_engine/export_ratings.py            # dry run, prints a preview
    PYTHONPATH=cfl_engine python cfl_engine/export_ratings.py --execute  # full-table replace

Reads cfl_engine/data/fights.csv (the same export the engine trains on) and
applies engine.compute_elo, so the number on the site is the number the
model sees. Strength of schedule is the average opponent rating going into
each fight, which is honest: it never uses a result that hadn't happened yet.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import ELO_K, ELO_START, compute_elo  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FIGHTS = os.path.join(HERE, "data", "fights.csv")
BATCH = 500


def build(fights_path: str = FIGHTS) -> pd.DataFrame:
    f = pd.read_csv(fights_path, parse_dates=["event_date"])
    f = f[f["result"].isin(["a", "b", "draw", "nc"])].copy()
    f = f.sort_values(["event_date", "fight_id"]).reset_index(drop=True)
    pre_a, pre_b = compute_elo(f)
    f["a_pre"], f["b_pre"] = pre_a, pre_b

    # Replay once more to get post-fight ratings (compute_elo only returns pre).
    rating: dict = defaultdict(lambda: ELO_START)
    rows: dict = defaultdict(lambda: {"n": 0, "peak": ELO_START, "opp": [], "wins_vs_rated": 0, "last": None})
    pending: list = []
    prev = None
    for r in f.itertuples(index=False):
        if prev is not None and r.event_date != prev:
            for fid, d in pending:
                rating[fid] += d
                rows[fid]["peak"] = max(rows[fid]["peak"], rating[fid])
            pending = []
        prev = r.event_date
        ra, rb = rating[r.fighter_a_id], rating[r.fighter_b_id]
        for me, opp_r, won in ((r.fighter_a_id, rb, r.result == "a"), (r.fighter_b_id, ra, r.result == "b")):
            s = rows[me]
            s["n"] += 1
            s["opp"].append(opp_r)
            s["last"] = r.event_date
            if won and opp_r > ELO_START:
                s["wins_vs_rated"] += 1
        if r.result == "nc":
            continue
        score_a = {"a": 1.0, "b": 0.0, "draw": 0.5}[r.result]
        exp_a = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
        pending.append((r.fighter_a_id, ELO_K * (score_a - exp_a)))
        pending.append((r.fighter_b_id, ELO_K * ((1.0 - score_a) - (1.0 - exp_a))))
    for fid, d in pending:
        rating[fid] += d
        rows[fid]["peak"] = max(rows[fid]["peak"], rating[fid])

    out = []
    for fid, s in rows.items():
        opp = s["opp"]
        out.append({
            "fighter_id": int(fid),
            "elo": round(float(rating[fid]), 1),
            "elo_peak": round(float(s["peak"]), 1),
            "n_fights": int(s["n"]),
            "opp_elo_avg": round(float(np.mean(opp)), 1) if opp else None,
            "opp_elo_last5": round(float(np.mean(opp[-5:])), 1) if opp else None,
            "wins_vs_rated": int(s["wins_vs_rated"]),
            "last_fight_date": s["last"].strftime("%Y-%m-%d") if s["last"] is not None else None,
        })
    return pd.DataFrame(out).sort_values("elo", ascending=False).reset_index(drop=True)


def _key() -> str:
    for n in ("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY"):
        if os.environ.get(n):
            return os.environ[n]
    sys.exit("No Supabase service key in env -- required for --execute.")


def execute(df: pd.DataFrame) -> None:
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not base:
        sys.exit("SUPABASE_URL not set.")
    key = _key()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Prefer": "return=minimal"}
    # Derived data: wipe and reload so retired fighters don't linger with stale numbers.
    req = urllib.request.Request(f"{base}/rest/v1/fighter_ratings?fighter_id=gte.0", method="DELETE", headers=h)
    with urllib.request.urlopen(req, timeout=120):
        pass
    now = datetime.now(timezone.utc).isoformat()
    recs = df.to_dict("records")
    for r in recs:
        r["computed_at"] = now
        for k, v in list(r.items()):
            if isinstance(v, float) and np.isnan(v):
                r[k] = None
    for i in range(0, len(recs), BATCH):
        body = json.dumps(recs[i:i + BATCH]).encode()
        req = urllib.request.Request(f"{base}/rest/v1/fighter_ratings", data=body, method="POST", headers=h)
        with urllib.request.urlopen(req, timeout=120):
            pass
        print(f"  inserted {min(i + BATCH, len(recs))}/{len(recs)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--fights", default=FIGHTS)
    a = ap.parse_args()
    df = build(a.fights)
    print(f"{len(df)} fighters rated; top 10:")
    print(df.head(10).to_string(index=False))
    if a.execute:
        execute(df)
        print("fighter_ratings replaced.")


if __name__ == "__main__":
    main()
