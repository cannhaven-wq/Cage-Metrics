"""WIN-001 development harness. DEV data only, walk-forward by year.

    cd research/experiments/WIN-001 && python3 dev_walkforward.py

For each test year 2019..2024 the model is fitted on priced, decided DEV
fights dated before 1 January of that year and scored on that year. Per-fight
gain is LL_market - LL_model (positive = model better). The event-clustered
bootstrap, log loss and calibration come from the protocol's own code so the
numbers here are the numbers the auditor's look would produce.

Every row is passed through pred_protocol.dev_only(): a sealed date raises.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "protocol"))
import features as F  # noqa: E402
import model as M  # noqa: E402
import pred_protocol as pp  # noqa: E402

TEST_YEARS = list(range(2019, 2025))
REBOOKED = {43, 46, 8780}


def load():
    fights = pd.read_csv(HERE / "data/fights_dev.csv")
    fighters = pd.read_csv(HERE / "data/fighters_dev.csv")
    closing = pd.read_csv(HERE / "data/closing_dev.csv")
    pp.dev_only(fights.to_dict("records"))
    rows = F.build_rows(fights, fighters)
    rows = rows.merge(closing, on="fight_id", how="left")
    rows["p_market"] = [F.devig_proportional(a, b) if a == a else np.nan
                        for a, b in zip(rows.american_a, rows.american_b)]
    rows["y"] = (rows["result"] == "a").astype(int)
    elig = rows["result"].isin(["a", "b"]) & rows["p_market"].notna() & ~rows["fight_id"].isin(REBOOKED)
    return rows, rows[elig].reset_index(drop=True)


def score(y, p_model, p_market, clusters) -> dict:
    d = pp.log_loss_each(y, p_market) - pp.log_loss_each(y, p_model)
    lo, hi = _ci(d, clusters)
    im, sm = pp.calibration_fit(y, p_model)
    return {"n": int(len(y)), "delta": float(d.mean()), "sd": float(d.std(ddof=1)),
            "ci95": [lo, hi], "acc_model": float(((p_model > 0.5) == y).mean()),
            "acc_market": float(((p_market > 0.5) == y).mean()),
            "ll_model": float(pp.log_loss_each(y, p_model).mean()),
            "ll_market": float(pp.log_loss_each(y, p_market).mean()),
            "cal_intercept": float(im), "cal_slope": float(sm)}


def _ci(d, clusters):
    rng = np.random.default_rng(20261012)
    cl = np.asarray(clusters)
    uniq = np.unique(cl)
    idx = {c: np.flatnonzero(cl == c) for c in uniq}
    means = []
    for _ in range(2000):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        sel = np.concatenate([idx[c] for c in pick])
        means.append(d[sel].mean())
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main():
    rows, elig = load()
    print(f"DEV rows {len(rows)}, eligible priced decided {len(elig)}, events {elig.event_id.nunique()}")
    results = {}
    for name, (feats, C) in M.VARIANTS.items():
        for standalone in ([False] if feats else [False]):
            pm, pk, ys, cls = [], [], [], []
            for yr in TEST_YEARS:
                tr = elig[elig.event_date < f"{yr}-01-01"]
                te = elig[(elig.event_date >= f"{yr}-01-01") & (elig.event_date < f"{yr + 1}-01-01")]
                art = M.fit(tr, tr.p_market.to_numpy(), tr.y.to_numpy(), feats, C, standalone)
                pm.append(M.predict(art, te, te.p_market.to_numpy()))
                pk.append(te.p_market.to_numpy()); ys.append(te.y.to_numpy()); cls.append(te.event_id.to_numpy())
            y, p, k, c = map(np.concatenate, (ys, pm, pk, cls))
            r = score(y, p, k, c)
            r["years"] = {yr: float((pp.log_loss_each(ys[i], pk[i]) - pp.log_loss_each(ys[i], pm[i])).mean())
                          for i, yr in enumerate(TEST_YEARS)}
            results[name] = r
            print(f"{name:16s} n={r['n']} delta={r['delta']:+.5f} sd={r['sd']:.4f} "
                  f"ci=[{r['ci95'][0]:+.4f},{r['ci95'][1]:+.4f}] acc {r['acc_model']:.3f} vs mkt {r['acc_market']:.3f} "
                  f"cal int {r['cal_intercept']:+.3f} slope {r['cal_slope']:.3f}")
    # standalone reading of the full feature set, reported never decisive
    pm, pk, ys, cls = [], [], [], []
    for yr in TEST_YEARS:
        tr = elig[elig.event_date < f"{yr}-01-01"]
        te = elig[(elig.event_date >= f"{yr}-01-01") & (elig.event_date < f"{yr + 1}-01-01")]
        art = M.fit(tr, tr.p_market.to_numpy(), tr.y.to_numpy(), F.DIFF_FEATURES, 0.1, standalone=True)
        pm.append(M.predict(art, te, te.p_market.to_numpy()))
        pk.append(te.p_market.to_numpy()); ys.append(te.y.to_numpy()); cls.append(te.event_id.to_numpy())
    y, p, k, c = map(np.concatenate, (ys, pm, pk, cls))
    results["standalone_full_c01"] = score(y, p, k, c)
    r = results["standalone_full_c01"]
    print(f"{'standalone':16s} n={r['n']} delta={r['delta']:+.5f} sd={r['sd']:.4f} acc {r['acc_model']:.3f}")
    (HERE / "DEV_RESULTS.json").write_text(json.dumps(results, indent=1) + "\n")


if __name__ == "__main__":
    main()
