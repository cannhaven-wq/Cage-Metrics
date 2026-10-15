"""SYM-003 outcome-free audit: truncation test, swap test, representation R^2.
Writes private/results/sym003_audit.json. Uses no fight result."""
from __future__ import annotations

import json
import os
import shutil
import tempfile

import numpy as np
import pandas as pd

import features as FE
import matchup_features as MF
from features import DATA, FEATS, HERE

NEW = [f"W{i}" for i in (1, 2, 3)] + [f"S{i}" for i in (1, 2, 3)] + [f"O{i}" for i in range(1, 7)]
OUT = os.path.join(HERE, "private", "results")


def truncation(cutoff="2019-01-01"):
    full = pd.read_parquet(os.path.join(DATA, "matchup.parquet")).set_index("fight_id")
    tmp = tempfile.mkdtemp()
    try:
        for fn in os.listdir(DATA):
            if fn.endswith(".csv"):
                shutil.copy(os.path.join(DATA, fn), tmp)
        f = pd.read_csv(os.path.join(tmp, "fights.csv"), parse_dates=["event_date"])
        f[f.event_date < cutoff].to_csv(os.path.join(tmp, "fights.csv"), index=False)
        FE.DATA = MF.DATA = tmp
        FE.build().to_parquet(os.path.join(tmp, "features.parquet"), index=False)
        tr, _ = MF.build()
    finally:
        FE.DATA = MF.DATA = DATA
        shutil.rmtree(tmp)
    tr = tr.set_index("fight_id")
    common = full.index.intersection(tr.index)
    d = (full.loc[common, NEW] - tr.loc[common, NEW]).abs().to_numpy().max()
    return {"cutoff": cutoff, "fights_compared": int(len(common)), "max_abs_difference": float(d),
            "rule": "deleting every fight on/after the cutoff (including opponents' later careers) must not change any earlier feature"}


def swap_test():
    """Rebuild W/S formulas with the corners exchanged: every feature must negate."""
    F = pd.read_parquet(os.path.join(DATA, "features.parquet"))
    M = pd.read_parquet(os.path.join(DATA, "matchup.parquet"))
    # O and the W/S definitions are differences of per-side quantities by construction; check numerically on O
    err_O = max(float(np.abs(M[f"O{k+1}"] - (M[f"a_O_{r}"] - M[f"b_O_{r}"])).max()) for k, r in enumerate(MF.RESID))
    sw = F.rename(columns={c: ("b_" + c[2:] if c.startswith("a_") else "a_" + c[2:]) for c in F.columns if c[:2] in ("a_", "b_")})
    w3 = sw.a_td_acc * (1 - sw.b_td_def) - sw.b_td_acc * (1 - sw.a_td_def)
    return {"W3_swap_max_abs(f(A,B)+f(B,A))": float(np.abs(M.W3 + w3).max()), "O_definition_max_err": err_O}


def representation():
    F = pd.read_parquet(os.path.join(DATA, "features.parquet"))
    M = pd.read_parquet(os.path.join(DATA, "matchup.parquet"))
    d = F.merge(M, on="fight_id")
    d = d[d.eligible_fighters & (d.event_date >= "2008-01-01") & (d.event_date < "2021-01-01")]
    from run_experiment import Prep
    p = Prep(d); A, B = p.AB(d); X = A - B
    out = {}
    for c in NEW:
        y = d[c].to_numpy()
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)          # no intercept: both sides antisymmetric
        out[c] = round(float(1 - np.sum((y - X @ beta) ** 2) / np.sum(y ** 2)), 4)
    groups = {"W": NEW[:3], "S": NEW[3:6], "O": NEW[6:]}
    return {"n_rows": int(len(d)), "per_feature_r2_on_23_baseline_diffs": out,
            "largely_represented_(r2>=0.9)": [c for c, v in out.items() if v >= 0.9],
            "group_mean_r2": {g: round(float(np.mean([out[c] for c in cs])), 4) for g, cs in groups.items()},
            "pairwise_corr_new_features": d[NEW].corr().round(3).to_dict()}


if __name__ == "__main__":
    rep = {"truncation_test": truncation(), "swap_test": swap_test(), "representation": representation()}
    json.dump(rep, open(os.path.join(OUT, "sym003_audit.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in rep.items() if k != "representation"}, indent=1))
    r = rep["representation"]
    print(json.dumps({k: r[k] for k in ("n_rows", "per_feature_r2_on_23_baseline_diffs", "largely_represented_(r2>=0.9)", "group_mean_r2")}, indent=1))
