"""INFO-AUDIT-001: how much does the engine add to the closing price, historically?

    python research/info_audit/blend_gain.py

Reads out_real/oos_predictions.csv (the engine's walk-forward output; the blend
is a logistic stack of logit(engine) and logit(market) fit on earlier folds
only - cfl_engine/train.py::rolling_blend). Reports the log-loss gain of the
blend over the market alone, an event-clustered bootstrap interval, the gain by
year, and how many fights a prospective test would need to confirm a given gain.

This is a historical walk-forward, not a prospective result. The market is the
BestFightOdds consensus closer, whose capture time is not recorded.
"""
import pathlib
import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parents[2]
d = pd.read_csv(REPO / "out_real" / "oos_predictions.csv")
b = d[d.blended & d.q_mkt.notna()].copy()


def ll(p, y):
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


b["gain_blend"] = ll(b.q_mkt, b.y) - ll(b.p_blend, b.y)   # positive = blend better
b["gain_engine"] = ll(b.q_mkt, b.y) - ll(b.p_cal, b.y)    # positive = engine better
print(f"fights {len(b)}  events {b.event_date.nunique()}  {b.event_date.min()}..{b.event_date.max()}")
rng = np.random.default_rng(0)
for c in ["gain_blend", "gain_engine"]:
    g = b.groupby("event_date")[c].agg(["sum", "count"])
    idx = np.arange(len(g))
    bs = []
    for _ in range(4000):
        s = rng.choice(idx, len(idx))
        bs.append(g["sum"].values[s].sum() / g["count"].values[s].sum())
    lo, hi = np.percentile(bs, [2.5, 97.5])
    print(f"{c:12s} mean {b[c].mean():+.4f}  sd {b[c].std():.4f}  event-clustered 95% CI [{lo:+.4f}, {hi:+.4f}]")
print(f"accuracy  market {((b.q_mkt > .5) == b.y).mean():.4f}  blend {((b.p_blend > .5) == b.y).mean():.4f}")
print(b.assign(yr=b.event_date.str[:4]).groupby("yr").gain_blend.agg(["mean", "count"]).round(4))
sd = b.gain_blend.std()
for eff in (0.003, 0.005, 0.010, 0.020):
    n = ((1.96 + 0.84) * sd / eff) ** 2
    print(f"fights needed to detect a {eff:.3f} gain (80% power, iid, sd of the blend): {n:,.0f}")
