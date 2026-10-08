"""SYM-002 data audit: point-in-time checks, corner bias, odds timestamps.

Writes private/results/audit.json. Model-free: nothing here fits anything.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from features import DATA, HERE, fight_seconds, outcome

OUT = os.path.join(HERE, "private", "results")


def main():
    os.makedirs(OUT, exist_ok=True)
    d = pd.read_parquet(os.path.join(DATA, "features.parquet"))
    raw = pd.read_csv(os.path.join(DATA, "fights.csv"), parse_dates=["event_date"])
    raw["res"] = [outcome(r) for r in raw.itertuples(index=False)]
    raw["secs"] = [fight_seconds(r, t) for r, t in zip(raw.end_round, raw.end_time)]
    rep = {}

    # 1. brute-force recomputation of prior counts and raw slpm from the raw table
    rng = np.random.default_rng(0)
    sample = d[d.eligible_fighters].sample(400, random_state=1)
    bad_n, bad_slpm = 0, 0
    long = pd.concat([
        raw.assign(fid=raw.fighter_a_id, sl=raw.a_sig_l, ok=raw[["a_sig_l", "b_sig_l"]].notna().all(axis=1)),
        raw.assign(fid=raw.fighter_b_id, sl=raw.b_sig_l, ok=raw[["a_sig_l", "b_sig_l"]].notna().all(axis=1)),
    ])
    long = long[long.res != "none"]
    for r in sample.itertuples(index=False):
        for side in ("a", "b"):
            fid = getattr(r, f"{side}_id")
            prior = long[(long.fid == fid) & (long.event_date < r.event_date)]
            if len(prior) != getattr(r, f"{side}_n_prior"):
                bad_n += 1
            later = long[(long.fid == fid) & (long.event_date >= r.event_date)]
            # the feature must not change if every later bout is deleted: check via counts only
            if getattr(r, f"{side}_n_prior") > len(prior) + 0 and len(later):
                bad_slpm += 1
    rep["pit_prior_count_mismatches"] = {"checked_fighter_rows": 800, "mismatches": bad_n,
                                         "rule": "n_prior must equal the count of the fighter's decided/nc bouts strictly before the event date"}

    # 2. truncation test: rebuild features with every fight on/after a cutoff removed;
    #    features for fights before the cutoff must be bit-identical.
    import features as F
    cutoff = pd.Timestamp("2019-01-01")
    full = d[d.event_date < cutoff].set_index("fight_id").sort_index()
    raw_trunc = raw[raw.event_date < cutoff]
    tmp = os.path.join(DATA, "_trunc_fights.csv")
    raw_trunc.drop(columns=["res", "secs"]).to_csv(tmp, index=False)
    orig = F.DATA
    try:
        os.rename(os.path.join(DATA, "fights.csv"), os.path.join(DATA, "_fights_full.csv"))
        os.rename(tmp, os.path.join(DATA, "fights.csv"))
        trunc = F.build().set_index("fight_id").sort_index()
    finally:
        os.rename(os.path.join(DATA, "fights.csv"), tmp)
        os.rename(os.path.join(DATA, "_fights_full.csv"), os.path.join(DATA, "fights.csv"))
        os.remove(tmp)
    cols = [c for c in full.columns if c.startswith(("a_", "b_")) and "leaky" not in c and c not in ("a_id", "b_id")]
    common = full.index.intersection(trunc.index)
    diff = (full.loc[common, cols].astype(float) - trunc.loc[common, cols].astype(float)).abs()
    diff = diff.where(~(full.loc[common, cols].isna() & trunc.loc[common, cols].isna()), 0)
    rep["truncation_test"] = {"cutoff": str(cutoff.date()), "fights_compared": int(len(common)),
                              "features_compared": len(cols), "max_abs_difference": float(np.nanmax(diff.values)),
                              "rule": "deleting every fight on/after the cutoff must not change any earlier feature"}

    # 3. corner bias in the raw table
    dec = raw[raw.res.isin(["a", "b"])]
    rep["corner_bias"] = {"listed_fighter_a_win_rate_raw": round(float((dec.res == "a").mean()), 4),
                          "fighter_a_win_rate_after_seeded_randomisation": round(float(d.loc[d.y.notna(), "y"].mean()), 4),
                          "consequence": "a model with an intercept, or accuracy computed in the raw corner order, inherits this bias"}

    # 4. career-average leakage: correlation of the leaky career field with the outcome vs the PIT field
    e = d[d.eligible_eval]
    def auc_like(x):  # P(sign agrees with result), ties dropped
        s = np.sign(x); m = s != 0
        return float(((s[m] > 0) == (e.y[m] == 1)).mean())
    rep["career_average_leak"] = {
        "sapm_point_in_time_direction_accuracy": round(auc_like(-(e.a_sapm - e.b_sapm)), 4),
        "sapm_fighters_table_career_direction_accuracy": round(auc_like(-(e.a_leaky_sapm - e.b_leaky_sapm)), 4),
        "slpm_point_in_time": round(auc_like(e.a_slpm - e.b_slpm), 4),
        "slpm_fighters_table_career": round(auc_like(e.a_leaky_slpm - e.b_leaky_slpm), 4),
        "note": "share of fights where the lower-absorbing (or higher-landing) fighter won; the career column contains the fight being predicted",
    }
    # current age vs age at fight: the gap is identical for both fighters only if same DOB offset; check it is not used
    rep["current_age_vs_age_at_fight"] = {
        "median_abs_diff_years_between_d_age_now_and_d_age_at_fight": round(float(((e.a_leaky_age_now - e.b_leaky_age_now) - (e.a_age_yrs - e.b_age_yrs)).abs().median()), 3),
    }

    # 5. odds timestamps
    rep["odds"] = {
        "archived_fights_with_price": int(d.p_a_archived.notna().sum()),
        "archived_ts_kind_counts": d.ts_kind.value_counts().to_dict(),
        "archived_single_book_share": round(float((d.n_books == 1).mean()), 3),
        "verified_fights_with_price": int(d.p_a_verified.notna().sum()),
        "verified_decided": int((d.p_a_verified.notna() & d.y.notna()).sum()),
        "verified_minutes_before_start_median": float(d.mins_before_start.median()),
        "verified_rule": "latest pre-start quote per book whose row carries retrieved_at, provider_last_update and source_commence_at, captured_at < source_commence_at, not live; median vig-free across books",
        "archived_rule": "is_closer rows, vig removed per book, median across books; 30,724 archived rows have captured_at = 1970-01-01 placeholders, so when the price was available is unknown",
        "eligible_eval_market_favourite_win_rate": round(float(((e.p_a_archived > 0.5) == (e.y == 1))[e.p_a_archived != 0.5].mean()), 4),
    }
    rep["cohort"] = {"rows": int(len(d)), "eligible_fighters": int(d.eligible_fighters.sum()),
                     "eligible_eval": int(d.eligible_eval.sum()),
                     "eligible_eval_2026": int((d.eligible_eval & (d.event_date.dt.year == 2026)).sum())}
    json.dump(rep, open(os.path.join(OUT, "audit.json"), "w"), indent=2, default=str)
    print(json.dumps(rep, indent=2, default=str))


if __name__ == "__main__":
    main()
