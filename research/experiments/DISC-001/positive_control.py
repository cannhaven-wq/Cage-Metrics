"""DISC-001 positive control — can the engine find an effect that is really there?

Not part of the preregistered analysis; a check on the instrument. It keeps the
real fights, odds and factor values, throws away the real results, and draws
simulated results in which a chosen factor DOES carry information beyond the
market, at a chosen strength. Then it runs the same walk-forward and bootstrap
as discover.py and reports how often the planted effect is found.

    python3 research/experiments/DISC-001/positive_control.py

If a planted effect of a size worth caring about were usually missed, a
"NOTHING" in the real run would mean little.
"""
from __future__ import annotations

import json
import math
import sys

import numpy as np

sys.dont_write_bytecode = True   # no __pycache__ in an experiment folder
import discover as d  # noqa: E402

SIM_SEED = 20261022
REPS = 40
# planted effect, stated as: at even odds, the fighter ahead by one unit of the
# factor (1 for a yes/no factor, one typical difference otherwise) wins this often
PLANTED = [53.0, 55.0, 57.0, 60.0]
FACTORS = ["F03", "F08", "F13"]
HOLM_FIRST = d.ALPHA / len(d.PRIMARY)    # the bar the best factor must clear


def main():
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
    S = D.scored
    rng = np.random.default_rng(SIM_SEED)
    out = {}
    for fid in FACTORS:
        j = D.col[fid]
        x = D.X[:, j]
        nz = x[S & D.ok[:, j] & (x != 0)]
        unit = 1.0 if set(np.unique(np.abs(nz))) <= {1.0} else float(np.std(nz))
        out[fid] = {}
        for pct in PLANTED:
            beta = math.log(pct / (100 - pct)) / unit
            found, found05, gains = 0, 0, []
            for _ in range(REPS):
                D.y = (rng.random(len(D.m)) < d.sigmoid(D.L + beta * x)).astype(float)
                p0, _ = d.walk_forward(D, [])
                p1, _ = d.walk_forward(D, [fid])
                g = d.pp.log_loss_each(D.y[S], p0[S]) - d.pp.log_loss_each(D.y[S], p1[S])
                boot = d.pp.cluster_bootstrap(g, D.event[S], 2000, SIM_SEED)
                p = (np.sum(boot <= 0) + 1) / 2001
                gains.append(float(g.mean()))
                found += int(p <= HOLM_FIRST)
                found05 += int(p < d.ALPHA)
            out[fid][f"{pct:.0f}%"] = {"found_share": found / REPS,
                                         "found_share_uncorrected": found05 / REPS, "mean_gain": float(np.mean(gains))}
            print(fid, pct, out[fid][f"{pct:.0f}%"])
    (d.HERE / "positive_control.json").write_text(json.dumps(
        {"reps": REPS, "bar_one_sided_p": HOLM_FIRST, "results": out}, indent=1) + "\n")


if __name__ == "__main__":
    main()
