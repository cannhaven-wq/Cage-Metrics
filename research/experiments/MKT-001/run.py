"""MKT-001 — which de-vig best describes the historical BFO closing consensus?

    python3 -I research/experiments/MKT-001/run.py      # writes results.json beside this file

Implements PREREGISTRATION.md (frozen in commit 1082cdc7 before this file
existed). DEV only: the input is the Discovery Engine's DEV export, checked by
sha256, every row passed through pred_protocol.dev_only (raises on a sealed
date), and the scored set checked against PRED-001's frozen DEV fingerprints.
Aggregates only are written; no per-fight row leaves this script.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import pathlib
import sys

sys.dont_write_bytecode = True        # no __pycache__ inside an experiment folder
HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path[:0] = [str(REPO / "research" / "protocol"), str(REPO / "cfl_engine")]

import numpy as np  # noqa: E402

import pred_protocol as pp  # noqa: E402
from clv import devig as clv_devig  # noqa: E402  frozen CLV-001 helpers, used only as a cross-check

DATA = REPO / "research" / "discovery" / "data" / "dev" / "fights.csv"
DATA_SHA256 = "5a5f1838d7585e68bb9041f93314a1caad7ec367e1408db866d93fe62924c2ee"
ERAS = {"2007-2012": (2007, 2012), "2013-2016": (2013, 2016), "2017-2020": (2017, 2020), "2021-2024": (2021, 2024)}
WF_YEARS = range(2010, 2025)
BOOT_B, BOOT_SEED = 10_000, 20261012
ALPHA = 0.05
METHODS = ("proportional", "power", "shin")
PAIRS = (("power", "proportional"), ("shin", "proportional"), ("power", "shin"))


# ----------------------------------------------------------------------------- de-vig
def implied(american: float) -> float:
    return pp.american_to_implied(american)


def power(qa: float, qb: float) -> float:
    """Same equation as clv.devig.power_devig (q**(1/k) summing to 1), no market band."""
    lo, hi = 0.5, 5.0
    f = lambda k: qa ** (1.0 / k) + qb ** (1.0 / k) - 1.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if f(lo) * f(mid) <= 0:
            hi = mid
        else:
            lo = mid
    k = (lo + hi) / 2.0
    a, b = qa ** (1.0 / k), qb ** (1.0 / k)
    return a / (a + b)


def shin(qa: float, qb: float) -> float:
    """Same two-outcome Shin inversion as clv.devig.shin_devig, no market band."""
    s = qa + qb
    fair = lambda q, z: ((z * z + 4.0 * (1.0 - z) * q * q / s) ** 0.5 - z) / (2.0 * (1.0 - z))
    lo, hi = 0.0, 0.9999
    for _ in range(200):
        z = (lo + hi) / 2.0
        if fair(qa, z) + fair(qb, z) > 1.0:
            lo = z
        else:
            hi = z
    a, b = fair(qa, z), fair(qb, z)
    return a / (a + b)


def devig(method: str, a: float, b: float) -> float:
    if method == "proportional":
        return pp.devig_proportional(a, b)
    qa, qb = implied(a), implied(b)
    return power(qa, qb) if method == "power" else shin(qa, qb)


# ----------------------------------------------------------------------------- data
def load():
    raw = DATA.read_bytes()
    if hashlib.sha256(raw).hexdigest() != DATA_SHA256:
        raise SystemExit(f"{DATA} is not the pinned DEV export (see research/discovery/WITHHELD.json)")
    rows = pp.dev_only(list(csv.DictReader(raw.decode().splitlines())), date_key="event_date")
    out = []
    for r in rows:
        if r["winner"] not in ("a", "b") or not r["bfo_close_a"] or not r["bfo_close_b"] or r["is_active"] == "0":
            continue
        out.append({"id": int(r["fight_id"]), "event": r["event_id"], "year": int(r["event_date"][:4]),
                    "y": 1.0 if r["winner"] == "a" else 0.0,
                    "ca": float(r["bfo_close_a"]), "cb": float(r["bfo_close_b"]),
                    "oa": float(r["bfo_open_a"]) if r["bfo_open_a"] else None,
                    "ob": float(r["bfo_open_b"]) if r["bfo_open_b"] else None})
    ids = sorted(f["id"] for f in out)
    y = {f["id"]: int(f["y"]) for f in out}
    dev = pp.MANIFEST["partitions"]["DEV"]
    got = {"decided_priced": len(ids),
           "priced_ids_sha256": hashlib.sha256(",".join(map(str, ids)).encode()).hexdigest(),
           "priced_outcomes_sha256": hashlib.sha256(",".join(f"{i}:{y[i]}" for i in ids).encode()).hexdigest()}
    if any(got[k] != dev[k] for k in got):
        raise SystemExit(f"scored set does not reproduce PRED-001's DEV fingerprints: {got}")
    return out, got


def cross_check(fights):
    """Band-free power/Shin must equal the frozen CLV-001 helpers wherever those accept the pair."""
    checked, worst = 0, 0.0
    for f in fights:
        qa, qb = implied(f["ca"]), implied(f["cb"])
        try:
            pw, sh = clv_devig.power_devig(qa, qb)[0], clv_devig.shin_devig(qa, qb)[0]
        except ValueError:
            continue
        worst = max(worst, abs(pw - power(qa, qb)), abs(sh - shin(qa, qb)))
        checked += 1
    if worst > 1e-9:
        raise SystemExit(f"band-free de-vig disagrees with clv.devig by {worst}")
    return {"fights_checked": checked, "fights_outside_band": len(fights) - checked, "max_abs_diff": worst}


# ----------------------------------------------------------------------------- measures
def r6(x):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), 6)


def ci(boot):
    return [r6(np.percentile(boot, 2.5)), r6(np.percentile(boot, 97.5))]


def describe(y, q, ev):
    a, b = pp.calibration_fit(y, q)
    bins = np.minimum((q * 10).astype(int), 9)
    rel = [{"bin": f"{i / 10:.1f}-{(i + 1) / 10:.1f}", "n": int((bins == i).sum()),
            "mean_forecast": r6(q[bins == i].mean()) if (bins == i).any() else None,
            "observed_rate": r6(y[bins == i].mean()) if (bins == i).any() else None} for i in range(10)]
    return {"n": int(len(y)), "events": int(len(set(ev))), "log_loss": r6(pp.log_loss_each(y, q).mean()),
            "brier": r6(pp.brier_each(y, q).mean()), "calibration_intercept": r6(a),
            "calibration_slope": r6(b), "reliability": rel}


def fit_slope(L, y):
    a = 1.0
    for _ in range(100):
        mu = 1.0 / (1.0 + np.exp(-a * L))
        step = float((L * (y - mu)).sum() / (L * L * mu * (1 - mu)).sum())
        a += step
        if abs(step) < 1e-12:
            break
    return a


def reweighting(y, q, yr, ev):
    L = np.log(np.clip(q, 1e-4, 1 - 1e-4) / (1 - np.clip(q, 1e-4, 1 - 1e-4)))
    p = np.full(len(y), np.nan)
    slopes = {}
    for Y in WF_YEARS:
        tr, te = yr < Y, yr == Y
        a = fit_slope(L[tr], y[tr])
        slopes[str(Y)] = r6(a)
        p[te] = 1.0 / (1.0 + np.exp(-a * L[te]))
    out = {"fitted_slope_by_test_year": slopes}
    for name, (lo, hi) in {"2010-2024": (2010, 2024), **ERAS}.items():
        m = ~np.isnan(p) & (yr >= lo) & (yr <= hi)
        if not m.any():
            continue
        g = pp.log_loss_each(y[m], q[m]) - pp.log_loss_each(y[m], p[m])
        boot = pp.cluster_bootstrap(g, ev[m], BOOT_B, BOOT_SEED)
        out[name] = {"n": int(m.sum()), "gain": r6(g.mean()), "ci95": ci(boot)}
    return out


def paired(y, qa, qb, ev):
    """Per-fight LL(b) - LL(a): positive means method a forecast better."""
    d = pp.log_loss_each(y, qb) - pp.log_loss_each(y, qa)
    boot = pp.cluster_bootstrap(d, ev, BOOT_B, BOOT_SEED)
    p_two = 2 * min((np.sum(boot <= 0) + 1) / (BOOT_B + 1), (np.sum(boot >= 0) + 1) / (BOOT_B + 1))
    return {"n": int(len(d)), "mean_ll_advantage": r6(d.mean()), "ci95": ci(boot), "p_two_sided": r6(min(1.0, p_two))}


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    out = [False] * len(ps)
    for rank, i in enumerate(order):
        if ps[i] <= ALPHA / (len(ps) - rank):
            out[i] = True
        else:
            break
    return out


def main():
    fights, fingerprints = load()
    check = cross_check(fights)
    y = np.array([f["y"] for f in fights])
    yr = np.array([f["year"] for f in fights])
    ev = np.array([f["event"] for f in fights])
    q = {m: np.array([devig(m, f["ca"], f["cb"]) for f in fights]) for m in METHODS}

    res = {"experiment": "MKT-001", "preregistration_commit": "1082cdc7",
           "data": {"sha256": DATA_SHA256, **fingerprints,
                    "events": int(len(set(ev))), "years": [int(yr.min()), int(yr.max())]},
           "band_free_cross_check": check, "methods": {}, "paired": {}, "by_era": {}}

    for m in METHODS:
        res["methods"][m] = {"all": describe(y, q[m], ev), "reweighting": reweighting(y, q[m], yr, ev)}
        for era, (lo, hi) in ERAS.items():
            k = (yr >= lo) & (yr <= hi)
            res["by_era"].setdefault(era, {})[m] = describe(y[k], q[m][k], ev[k])

    # Primary: paired comparisons over all fights, Holm over the three
    for a, b in PAIRS:
        res["paired"][f"{a}_vs_{b}"] = paired(y, q[a], q[b], ev)
    keys = list(res["paired"])
    surv = holm([res["paired"][k]["p_two_sided"] for k in keys])
    for k, s in zip(keys, surv):
        res["paired"][k]["holm_survives"] = bool(s)

    # Decision rule (PREREGISTRATION.md)
    ll = {m: res["methods"][m]["all"]["log_loss"] for m in METHODS}
    best = min(ll, key=ll.get)
    others = [m for m in METHODS if m != best]

    def beats(w, l):
        k = f"{w}_vs_{l}" if f"{w}_vs_{l}" in res["paired"] else f"{l}_vs_{w}"
        r = res["paired"][k]
        better = r["mean_ll_advantage"] > 0 if k.startswith(w) else r["mean_ll_advantage"] < 0
        return better and r["holm_survives"]

    recommended = best if all(beats(best, o) for o in others) else None
    res["decision"] = {"lowest_log_loss": best, "recommended_reporting_baseline": recommended,
                       "rule": "lowest log loss AND both its paired comparisons survive Holm at 0.05; otherwise none"}

    # Era agreement on the ordering, and per-era paired comparisons (descriptive)
    order = {}
    for era, (lo, hi) in ERAS.items():
        k = (yr >= lo) & (yr <= hi)
        order[era] = sorted(METHODS, key=lambda m: res["by_era"][era][m]["log_loss"])
        res["by_era"][era]["paired"] = {f"{a}_vs_{b}": paired(y[k], q[a][k], q[b][k], ev[k]) for a, b in PAIRS}
    res["era_ordering"] = order
    res["eras_agree_on_best"] = len({o[0] for o in order.values()}) == 1

    # Margins, descriptive
    def margin(a, b):
        return implied(a) + implied(b) - 1.0
    marg = {}
    for era, (lo, hi) in {"all": (0, 9999), **ERAS}.items():
        sel = [f for f in fights if lo <= f["year"] <= hi]
        cl = [margin(f["ca"], f["cb"]) for f in sel]
        op = [margin(f["oa"], f["ob"]) for f in sel if f["oa"] is not None and f["ob"] is not None]
        marg[era] = {"closer_median": r6(np.median(cl)), "opener_median": r6(np.median(op)) if op else None,
                     "n_closer": len(cl), "n_opener": len(op)}
    res["overround"] = marg

    # Opener, secondary and descriptive (ordered before the close, not timed)
    with_open = [i for i, f in enumerate(fights) if f["oa"] is not None and f["ob"] is not None]
    oi = np.array(with_open)
    res["opener"] = {}
    for m in METHODS:
        qo = np.array([devig(m, fights[i]["oa"], fights[i]["ob"]) for i in with_open])
        res["opener"][m] = {"opener": describe(y[oi], qo, ev[oi]), "closer_same_fights": describe(y[oi], q[m][oi], ev[oi])}

    (HERE / "results.json").write_text(json.dumps(res, indent=1) + "\n")
    return res


if __name__ == "__main__":
    r = main()
    print(json.dumps({"decision": r["decision"], "paired": r["paired"],
                      "log_loss": {m: r["methods"][m]["all"]["log_loss"] for m in METHODS},
                      "slope": {m: r["methods"][m]["all"]["calibration_slope"] for m in METHODS},
                      "reweighting_2010_2024": {m: r["methods"][m]["reweighting"]["2010-2024"] for m in METHODS},
                      "era_ordering": r["era_ordering"], "overround": r["overround"]["all"],
                      "cross_check": r["band_free_cross_check"]}, indent=1))
