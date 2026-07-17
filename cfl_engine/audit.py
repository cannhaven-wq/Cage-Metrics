"""Leak-audit suite. Run this before trusting any backtest number.

Checks, in order of how often they kill ufcstats-based models:
1. Corner symmetry     -- residual orientation sensitivity of the trained model
2. Too-good detectors  -- OOS accuracy / logloss-vs-market thresholds that imply leakage
3. PIT structural check-- recompute n_prior_fights from raw fights table, must match features
4. Calibration         -- decile reliability table + ECE
5. Segment Brier       -- model vs market by weight class and debut status
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss

ACC_RED_FLAG = 0.70
LL_BEAT_RED_FLAG = 0.015


def metric_block(y, p, label: str) -> dict:
    return {
        "set": label,
        "n": int(len(y)),
        "accuracy": float(((p >= 0.5).astype(int) == y).mean()),
        "log_loss": float(log_loss(y, np.clip(p, 1e-4, 1 - 1e-4), labels=[0, 1])),
        "brier": float(brier_score_loss(y, p)),
    }


def too_good_flags(oos: pd.DataFrame) -> list[str]:
    flags = []
    d = oos[oos["calibrated"]]
    acc = ((d["p_cal"] >= 0.5).astype(int) == d["y"]).mean()
    if acc > ACC_RED_FLAG:
        flags.append(
            f"RED FLAG: OOS accuracy {acc:.1%} > {ACC_RED_FLAG:.0%}. Clean MMA models live "
            f"~62-67%. This smells like leakage (corner ordering or future career stats)."
        )
    m = d[d["q_mkt"].notna()]
    if len(m) > 300:
        ll_model = log_loss(m["y"], np.clip(m["p_cal"], 1e-4, 1 - 1e-4), labels=[0, 1])
        ll_mkt = log_loss(m["y"], np.clip(m["q_mkt"], 1e-4, 1 - 1e-4), labels=[0, 1])
        if ll_model < ll_mkt - LL_BEAT_RED_FLAG:
            flags.append(
                f"RED FLAG: model logloss beats the vig-free close by "
                f"{ll_mkt - ll_model:.4f} (> {LL_BEAT_RED_FLAG}). Nobody honest does that "
                f"standalone. Audit for leakage before celebrating."
            )
    return flags


def pit_structural_check(feat_df: pd.DataFrame, fights: pd.DataFrame,
                         n_sample: int = 200, seed: int = 5) -> dict:
    """a_n_fights must equal the count of the fighter's strictly-prior fights."""
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(feat_df), size=min(n_sample, len(feat_df)), replace=False)
    mismatches = 0
    for i in idx:
        r = feat_df.iloc[i]
        fid, date = r["fighter_a_id"], r["event_date"]
        prior = ((fights["event_date"] < date) &
                 ((fights["fighter_a_id"] == fid) | (fights["fighter_b_id"] == fid))).sum()
        if prior != int(r["a_n_fights"]):
            mismatches += 1
    return {"checked": int(len(idx)), "mismatches": int(mismatches)}


def calibration_table(oos: pd.DataFrame, bins: int = 10) -> tuple[pd.DataFrame, float]:
    d = oos[oos["calibrated"]].copy()
    d["bin"] = pd.cut(d["p_cal"], np.linspace(0, 1, bins + 1), include_lowest=True)
    g = d.groupby("bin", observed=True).agg(
        n=("y", "size"), predicted=("p_cal", "mean"), actual=("y", "mean"))
    ece = float((g["n"] / g["n"].sum() * (g["predicted"] - g["actual"]).abs()).sum())
    return g.reset_index(), ece


def segment_brier(oos_meta: pd.DataFrame, min_n: int = 30) -> pd.DataFrame:
    """Brier of model vs market per segment. oos_meta needs p_cal, q_mkt, y,
    weight_class, a_n_fights, b_n_fights."""
    d = oos_meta[oos_meta["calibrated"] & oos_meta["q_mkt"].notna()].copy()
    d["segment"] = d["weight_class"].astype(str)
    d.loc[(d["a_n_fights"] == 0) | (d["b_n_fights"] == 0), "segment"] = "debut_involved"
    rows = []
    for seg, g in d.groupby("segment"):
        if len(g) < min_n:
            continue
        rows.append({
            "segment": seg, "n": len(g),
            "brier_model": brier_score_loss(g["y"], g["p_cal"]),
            "brier_market": brier_score_loss(g["y"], g["q_mkt"]),
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out["model_minus_market"] = out["brier_model"] - out["brier_market"]
        out = out.sort_values("model_minus_market", ascending=False)
    return out


def feature_importance(model, cols: list[str], top: int = 15) -> pd.DataFrame:
    imp = model.get_booster().get_score(importance_type="gain")
    rows = [{"feature": c, "gain": imp.get(c, 0.0)} for c in cols]
    return (pd.DataFrame(rows).sort_values("gain", ascending=False)
            .head(top).reset_index(drop=True))
