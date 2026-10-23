"""DISC-001 diagnostic — is the market-slope gain real, or an artefact of de-vig?

The baseline (a refitted slope on the market's log-odds) beat the raw vig-free
close out of sample. Proportional de-vig is known to leave longshots slightly
too likely, which a slope above 1 would "fix" without the market being wrong
about anything. PRED-001 §4 names power and Shin as the sensitivities; this
repeats the baseline-versus-raw comparison under each.

    python3 research/experiments/DISC-001/devig_check.py
"""
from __future__ import annotations

import json
import math
import sys

import numpy as np

sys.dont_write_bytecode = True   # no __pycache__ in an experiment folder
import discover as d  # noqa: E402


def implied(a):
    return d.pp.american_to_implied(a)


def power(a, b):
    ia, ib = implied(a), implied(b)
    lo, hi = 1.0, 5.0
    for _ in range(100):
        k = (lo + hi) / 2
        if ia ** k + ib ** k > 1:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2
    return ia ** k / (ia ** k + ib ** k)


def shin(a, b):
    ia, ib = implied(a), implied(b)
    s = ia + ib
    lo, hi = 0.0, 0.5
    for _ in range(100):
        z = (lo + hi) / 2
        ps = [(math.sqrt(z * z + 4 * (1 - z) * q * q / s) - z) / (2 * (1 - z)) for q in (ia, ib)]
        if sum(ps) > 1:
            lo = z
        else:
            hi = z
    z = (lo + hi) / 2
    pa, pb = [(math.sqrt(z * z + 4 * (1 - z) * q * q / s) - z) / (2 * (1 - z)) for q in (ia, ib)]
    return pa / (pa + pb)


def main():
    fights, dob = d.load()
    feats = d.build(fights, dob)
    out = {}
    for name, fn in (("proportional", d.pp.devig_proportional), ("power", power), ("shin", shin)):
        rows = []
        for f in fights:
            priced = (f["bfo_a"] is not None and f["bfo_b"] is not None
                      and 100 <= abs(f["bfo_a"]) <= d.MAX_AMERICAN and 100 <= abs(f["bfo_b"]) <= d.MAX_AMERICAN)
            if f["res"] not in ("A", "B") or not priced or f["id"] in d.EXCLUDED_FIGHTS:
                continue
            r = dict(f)
            r["m"] = fn(f["bfo_a"], f["bfo_b"])
            r["scored"] = f["date"].year in d.TEST_YEARS
            rows.append(r)
        D = d.Design(rows, feats)
        p0, coefs = d.walk_forward(D, [])
        res = d.score(D, p0, D.m, D.scored)
        res["market_slope_final_year"] = coefs[d.TEST_YEARS[-1]][0]
        out[name] = res
        print(name, json.dumps(res))
    (d.HERE / "devig_check.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
