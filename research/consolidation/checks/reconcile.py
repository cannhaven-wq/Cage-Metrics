"""Consolidation checks, 2026-10-21: where DISC-001 and the Discovery Engine overlap.

    python3 -I research/consolidation/checks/reconcile.py      # writes reconcile.json beside this file

Two questions, both on DEV data only (fights before 2025-01-01; every row passes
pred_protocol.dev_only, which raises on a sealed date):

1. The "market re-weighting" gain. DISC-001 says it is an artefact of the
   proportional de-vig and vanishes under power. The engine reports it as the
   closing price being under-confident in 2019-24. Both are recomputed here,
   for each de-vig method, on each project's own window.
2. DISC-001's overlapping factors, scored separately on 2012-18 and 2019-24,
   so they line up with the engine's screen (2010-18) and confirm (2019-24)
   periods.

Reads only the two committed DEV exports. Imports DISC-001's discover.py and
devig_check.py unchanged (its power and Shin have no market band; the frozen
CLV-001 helpers refuse 7 DEV fights priced beyond 97%). Writes nothing else.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.dont_write_bytecode = True    # no __pycache__ inside an experiment folder
HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path[:0] = [str(REPO / "research" / "protocol"), str(REPO / "cfl_engine"),
                str(REPO / "research" / "experiments" / "DISC-001")]

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import pred_protocol as pp  # noqa: E402
import discover as d  # noqa: E402  DISC-001, unchanged
import devig_check as dc  # noqa: E402  DISC-001, unchanged
from clv.devig import power_devig  # noqa: E402  frozen CLV-001 helper, for the band count only

BOOT_B, BOOT_SEED = 10_000, 20261012


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def fit_slope(L, y, ridge):
    """Market-slope-only logistic, penalty ridge*(a-1)^2/2 (the engine's ridge 1 shrinks
    toward the market; DISC-001 uses none)."""
    a = 1.0
    for _ in range(100):
        mu = 1 / (1 + np.exp(-a * L))
        step = ((L * (y - mu)).sum() - ridge * (a - 1)) / ((L * L * mu * (1 - mu)).sum() + ridge)
        a += step
        if abs(step) < 1e-12:
            break
    return a


def recalibration():
    f = pd.read_csv(REPO / "research/discovery/data/dev/fights.csv", keep_default_na=False,
                    na_values={"bfo_close_a": [""], "bfo_close_b": [""], "is_active": [""]})
    pp.dev_only(f.to_dict("records"), date_key="event_date")
    f = f[f.winner.isin(["a", "b"]) & f.bfo_close_a.notna() & f.bfo_close_b.notna()
          & (f.is_active.fillna(1) != 0)].copy()
    out = {"fights": int(len(f)), "events": int(f.event_id.nunique())}
    band = 0
    for a, b in zip(f.bfo_close_a, f.bfo_close_b):
        try:
            power_devig(pp.american_to_implied(float(a)), pp.american_to_implied(float(b)))
        except ValueError:
            band += 1
    out["fights_outside_clv001_market_band"] = band
    y = (f.winner == "a").to_numpy(float)
    yr = pd.to_datetime(f.event_date).dt.year.to_numpy()
    ev = f.event_id.to_numpy()
    q = {"proportional": [pp.devig_proportional(float(a), float(b)) for a, b in zip(f.bfo_close_a, f.bfo_close_b)],
         "power": [dc.power(float(a), float(b)) for a, b in zip(f.bfo_close_a, f.bfo_close_b)],
         "shin": [dc.shin(float(a), float(b)) for a, b in zip(f.bfo_close_a, f.bfo_close_b)]}
    windows = {"DISC-001 2012-24 (train all earlier years, no penalty)": (range(2012, 2025), 0, 0.0),
               "Engine screen 2010-18 (train from 2007, ridge 1)": (range(2010, 2019), 2007, 1.0),
               "Engine confirm 2019-24 (train from 2007, ridge 1)": (range(2019, 2025), 2007, 1.0)}
    out["windows"] = {}
    for wname, (years, start, ridge) in windows.items():
        res = {}
        for method, qs in q.items():
            qs = np.asarray(qs)
            L = logit(qs)
            p = np.full(len(y), np.nan)
            for Y in years:
                tr, te = (yr < Y) & (yr >= start), yr == Y
                p[te] = 1 / (1 + np.exp(-fit_slope(L[tr], y[tr], ridge) * L[te]))
            m = ~np.isnan(p)
            g = pp.log_loss_each(y[m], qs[m]) - pp.log_loss_each(y[m], p[m])
            boot = pp.cluster_bootstrap(g, ev[m], BOOT_B, BOOT_SEED)
            _, slope = pp.calibration_fit(y[m], qs[m])
            res[method] = {"n": int(m.sum()), "market_log_loss": round(float(pp.log_loss_each(y[m], qs[m]).mean()), 5),
                           "recalibration_gain": round(float(g.mean()), 5),
                           "ci95": [round(float(np.percentile(boot, 2.5)), 5), round(float(np.percentile(boot, 97.5)), 5)],
                           "calibration_slope_in_window": round(float(slope), 3)}
        out["windows"][wname] = res
    return out


def disc001_by_window():
    fights, dob = d.load()
    feats = d.build(fights, dob)
    rows = []
    for f in fights:
        priced = (f["bfo_a"] is not None and f["bfo_b"] is not None
                  and 100 <= abs(f["bfo_a"]) <= d.MAX_AMERICAN and 100 <= abs(f["bfo_b"]) <= d.MAX_AMERICAN)
        if f["res"] not in ("A", "B") or not priced or f["id"] in d.EXCLUDED_FIGHTS:
            continue
        r = dict(f)
        r["m"] = d.pp.devig_proportional(f["bfo_a"], f["bfo_b"])
        r["scored"] = f["date"].year in d.TEST_YEARS
        rows.append(r)
    D = d.Design(rows, feats)
    base, _ = d.walk_forward(D, [])
    out = {}
    for fid in ("F13", "F14", "F03", "F16", "F07", "F01", "F11", "F10", "F15", "F12", "F19", "F20"):
        p, _ = d.walk_forward(D, [fid])
        out[fid] = {}
        for lab, (lo, hi) in {"2012-18": (2012, 2018), "2019-24": (2019, 2024)}.items():
            s = d.score(D, p, base, D.scored & (D.year >= lo) & (D.year <= hi))
            out[fid][lab] = {"gain": round(s["gain"], 5), "ci95": [round(x, 5) for x in s["ci95"]],
                             "p_one_sided": round(s["p_one_sided"], 3)}
    return out


if __name__ == "__main__":
    result = {"recalibration_by_devig": recalibration(), "disc001_factors_by_window": disc001_by_window()}
    (HERE / "reconcile.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result["recalibration_by_devig"], indent=1))
