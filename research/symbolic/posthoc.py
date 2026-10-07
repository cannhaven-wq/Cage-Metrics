"""SYM-002 POST-HOC diagnostics. Decided AFTER the preregistered results were
seen, so nothing here may be read as a confirmatory result.

1. v1-style market correction vs the archived market, and vs a market-only
   recalibration sigmoid(b * logit(p_market)) refitted per fold. If the
   recalibration explains the gain, the "correction" is mostly the archived
   price being under-confident, not fighter information.
2. How linear is the selected final Experiment-A formula? R^2 of its logit
   regressed on the 23 standardised linear differences (training rows).
"""
from __future__ import annotations

import json
import os
import pickle

import numpy as np
import pandas as pd

import symreg as S
from features import DATA, FEATS, HERE
from report import boot_diff, metrics
from run_experiment import Prep, logit, predict, split

PRIV = os.path.join(HERE, "private")


def main():
    df = pd.read_parquet(os.path.join(DATA, "features.parquet"))
    P = pd.read_csv(os.path.join(PRIV, "results", "oos_predictions.csv"))
    recal = []
    for y in sorted(P.fold.unique()):
        train, *_ = split(df, int(y))
        tr = train[train.p_a_archived.between(0.01, 0.99)]
        b = S.fit_logistic(logit(tr.p_a_archived.to_numpy())[:, None], tr.y.to_numpy(), lam=1e-6)[0]
        d = P[P.fold == y]
        recal.append(pd.Series(S.sigmoid(b * logit(d.market_archived.to_numpy())), index=d.index))
        print(f"fold {y}: market recalibration slope b = {b:.4f}")
    P["market_recalibrated"] = pd.concat(recal)
    head = P[P.fold <= 2025]
    out = {"market_recalibrated_pooled_2021_2025": metrics(head.market_recalibrated.to_numpy(), head.y.to_numpy())}
    for m1, m2 in (("v1_market_refit", "market_archived"), ("market_recalibrated", "market_archived"),
                   ("v1_market_refit", "market_recalibrated"), ("B_symbolic", "market_recalibrated")):
        r = boot_diff(head, m1, m2)
        r["fold_wins_of_5"] = int(sum(
            S.logloss(head[head.fold == y][m1].to_numpy(), head[head.fold == y].y.to_numpy())
            < S.logloss(head[head.fold == y][m2].to_numpy(), head[head.fold == y].y.to_numpy())
            for y in range(2021, 2026)))
        r26 = boot_diff(P[P.fold == 2026], m1, m2)
        out[f"{m1} vs {m2}"] = {"2021_2025": r, "2026": r26}

    # 2. linearity of the final A formula
    fin = pickle.load(open(os.path.join(PRIV, "results", "fold_final.pkl"), "rb"))
    train, *_ = split(df, "final")
    po = Prep(train); A, B = po.AB(train)
    m = fin["models"]["A"]
    z = logit(predict(m["trees"], m["sds"], m["w"], A, B))
    X = A - B
    coef, *_ = np.linalg.lstsq(X, z, rcond=None)
    r2 = 1 - np.var(z - X @ coef) / np.var(z)
    per_term = {}
    for t, s in zip(m["trees"], m["sds"]):
        v = S.term(t, A, B) / s
        c, *_ = np.linalg.lstsq(X, v, rcond=None)
        per_term[S.to_str(t, FEATS)] = round(float(1 - np.var(v - X @ c) / np.var(v)), 4)
    out["final_A_linearity"] = {"r2_of_logit_on_23_linear_diffs": round(float(r2), 4), "per_term_r2": per_term,
                                "best_linear_approximation_on_z_diffs": dict(zip(FEATS, np.round(coef, 4).tolist()))}
    json.dump(out, open(os.path.join(PRIV, "results", "posthoc.json"), "w"), indent=1, default=float)
    print(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
