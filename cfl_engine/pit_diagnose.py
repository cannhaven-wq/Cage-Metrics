"""Diagnose PIT structural-check mismatches exhaustively (audit gate follow-up).

Recomputes the feature matrix from the exported CSVs and compares a_n_fights /
b_n_fights against strictly-prior fight counts for EVERY row, then inspects
each mismatch: is the fighter a same-day multi-fight case (tournament era)?
"""
import pandas as pd

from engine import build_features, load_data

fights, stats, fighters = load_data(
    "cfl_engine/data/fights.csv", "cfl_engine/data/fight_stats.csv",
    "cfl_engine/data/fighters.csv")
feat = build_features(fights, stats, fighters)

# strictly-prior counts per fighter, exact audit semantics, vectorized
long_ = pd.concat([
    fights[["fight_id", "event_date", "fighter_a_id"]].rename(columns={"fighter_a_id": "fid"}),
    fights[["fight_id", "event_date", "fighter_b_id"]].rename(columns={"fighter_b_id": "fid"}),
])
mismatches = []
by_fighter = {fid: g["event_date"].to_numpy() for fid, g in long_.groupby("fid")}
for r in feat.itertuples(index=False):
    for side, fid in (("a", r.fighter_a_id), ("b", r.fighter_b_id)):
        strict_prior = int((by_fighter[fid] < r.event_date).sum())
        feat_n = int(getattr(r, f"{side}_n_fights"))
        if strict_prior != feat_n:
            same_day = int((by_fighter[fid] == r.event_date).sum())
            mismatches.append({
                "fight_id": r.fight_id, "event_date": r.event_date, "fighter": fid,
                "feature_n": feat_n, "strict_prior": strict_prior,
                "fighter_fights_that_day": same_day,
            })

m = pd.DataFrame(mismatches)
print(f"total corner-checks: {2 * len(feat)}, mismatches: {len(m)}")
if not m.empty:
    print(f"date range of mismatches: {m['event_date'].min().date()} .. "
          f"{m['event_date'].max().date()}")
    explained = (m["fighter_fights_that_day"] > 1).all()
    print(f"ALL mismatches involve a same-day multi-fight fighter: {explained}")
    print(m.head(40).to_string(index=False))
    # how many distinct fights / what share of dataset
    print(f"\ndistinct fights affected: {m['fight_id'].nunique()} of {len(feat)}")
    # any mismatch NOT explained by same-day duplicates?
    bad = m[m["fighter_fights_that_day"] <= 1]
    if len(bad):
        print("\nUNEXPLAINED MISMATCHES (not same-day):")
        print(bad.to_string(index=False))
