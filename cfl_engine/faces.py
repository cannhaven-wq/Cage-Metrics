"""Two faces, one brain.

Face 1 (Picks): calibrated probability -> pick + confidence tier. Sold on accuracy.
Face 2 (Edges): blend vs vig-free close -> flagged bets, fractional Kelly. Sold on ROI/CLV.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import american_to_decimal

TIERS = [(0.65, "Lock"), (0.57, "Pick"), (0.0, "Lean")]


def tier_of(p: float) -> str:
    conf = max(p, 1 - p)
    for cut, name in TIERS:
        if conf >= cut:
            return name
    return "Lean"


def face1_table(oos: pd.DataFrame) -> pd.DataFrame:
    """Accuracy by confidence tier, calibrated folds only."""
    d = oos[oos["calibrated"]].copy()
    d["tier"] = d["p_cal"].map(tier_of)
    d["pick_correct"] = ((d["p_cal"] >= 0.5).astype(int) == d["y"]).astype(int)
    g = d.groupby("tier")["pick_correct"].agg(["count", "mean"]).rename(
        columns={"count": "n", "mean": "accuracy"})
    g["avg_conf"] = d.groupby("tier")["p_cal"].apply(lambda s: np.maximum(s, 1 - s).mean())
    order = ["Lock", "Pick", "Lean"]
    return g.reindex([t for t in order if t in g.index])


def face2_edges(oos: pd.DataFrame, edge_min: float = 0.04,
                kelly_frac: float = 0.25, cap: float = 0.02) -> tuple[pd.DataFrame, dict]:
    """Flag +EV bets vs the vig-free close; backtest flat and fractional-Kelly ROI.

    Note: with only closing odds on file, 'edge' here is model-vs-close. True CLV
    (bet-time line vs close) requires capturing the line when the bet is placed --
    that instrumentation is part of the product, not the backtest.
    """
    d = oos[(oos["blended"]) & oos["q_mkt"].notna()].copy()
    if d.empty:
        return pd.DataFrame(), {}

    take_a = d["p_blend"] >= d["q_mkt"]
    d["side"] = np.where(take_a, "a", "b")
    d["p_side"] = np.where(take_a, d["p_blend"], 1 - d["p_blend"])
    d["q_side"] = np.where(take_a, d["q_mkt"], 1 - d["q_mkt"])
    d["edge"] = d["p_side"] - d["q_side"]
    d["dec_odds"] = np.where(
        take_a,
        d["odds_a"].map(american_to_decimal),
        d["odds_b"].map(american_to_decimal),
    )
    d["won"] = np.where(take_a, d["y"] == 1, d["y"] == 0).astype(int)

    bets = d[(d["edge"] >= edge_min) & d["dec_odds"].notna()].copy()
    if bets.empty:
        return bets, {"n_bets": 0}

    b = bets["dec_odds"] - 1.0
    kelly = (bets["p_side"] * b - (1 - bets["p_side"])) / b
    bets["stake"] = np.minimum(cap, kelly_frac * np.maximum(kelly, 0.0))

    flat_pnl = np.where(bets["won"] == 1, b, -1.0)
    kelly_pnl = np.where(bets["won"] == 1, bets["stake"] * b, -bets["stake"])
    summary = {
        "n_bets": int(len(bets)),
        "bet_rate": float(len(bets) / len(d)),
        "avg_edge": float(bets["edge"].mean()),
        "flat_roi": float(flat_pnl.sum() / len(bets)),
        "kelly_roi": float(kelly_pnl.sum() / bets["stake"].sum()),
        "win_rate": float(bets["won"].mean()),
        "avg_price_taken": float(bets["dec_odds"].mean()),
    }
    return bets, summary
