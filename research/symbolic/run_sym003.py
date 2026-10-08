"""SYM-003: baseline LR vs baseline + matchup feature groups (rules: config_sym003.json).

Writes private/results/sym003_metrics.json, sym003_oos_predictions.csv and
private/models/sym003_final_*.json (+ SYM003_FROZEN.json).
"""
from __future__ import annotations

import hashlib
import json
import os
import time

import numpy as np
import pandas as pd

import symreg as S
from features import CFG, DATA, FEATS, HERE
from report import boot_diff, metrics
from run_experiment import LAMBDA_GRID, Prep, split

PRIV = os.path.join(HERE, "private")
CFG3 = json.load(open(os.path.join(HERE, "config_sym003.json")))
GROUPS = {"W": ["W1", "W2", "W3"], "S": ["S1", "S2", "S3"], "O": [f"O{i}" for i in range(1, 7)]}
MODELS = {"baseline": [], "baseline+W": GROUPS["W"], "baseline+S": GROUPS["S"], "baseline+O": GROUPS["O"],
          "baseline+all": GROUPS["W"] + GROUPS["S"] + GROUPS["O"]}
NEW_CLIP = 5.0
YEARS = CFG["validation"]["outer_test_years"]
HEAD = [y for y in YEARS if y != 2026]


class Design:
    """Fold-local design matrix: 23 standardised per-fighter differences + new features.
    Everything learned from `fit_rows` only. All columns antisymmetric; no intercept."""

    def __init__(self, fit_rows, extra):
        self.prep, self.extra = Prep(fit_rows), extra
        A, B = self.prep.AB(fit_rows)
        self.base_sd = np.std(A - B, axis=0)
        self.new_sd = fit_rows[extra].std(ddof=0).to_numpy() if extra else np.zeros(0)

    def X(self, rows, swap=False):
        A, B = self.prep.AB(rows)
        if swap:
            A, B = B, A
        cols = [(A - B) / self.base_sd]
        if self.extra:
            N = rows[self.extra].to_numpy(float) * (-1 if swap else 1)
            cols.append(np.clip(N / self.new_sd, -NEW_CLIP, NEW_CLIP))
        return np.column_stack(cols)

    def to_dict(self):
        return {"preprocessing": self.prep.to_dict(), "base_features": FEATS, "base_diff_train_std": self.base_sd.tolist(),
                "new_features": self.extra, "new_feature_train_std": self.new_sd.tolist(), "new_feature_clip": NEW_CLIP}


def fit_model(train, itr, iva, extra):
    best = None
    di = Design(itr, extra)
    Xi, Xv = di.X(itr), di.X(iva)
    for lam in LAMBDA_GRID:
        w = S.fit_logistic(Xi, itr.y.to_numpy(), lam=lam)
        ll = S.logloss(S.sigmoid(Xv @ w), iva.y.to_numpy())
        if best is None or ll < best[0]:
            best = (ll, lam)
    d = Design(train, extra)
    w = S.fit_logistic(d.X(train), train.y.to_numpy(), lam=best[1])
    return d, w, best


def main():
    t0 = time.time()
    F = pd.read_parquet(os.path.join(DATA, "features.parquet"))
    M = pd.read_parquet(os.path.join(DATA, "matchup.parquet"))
    df = F.merge(M, on="fight_id", how="left")
    allp, sel, swap_err = [], {}, {}
    for fold in YEARS + ["final"]:
        train, itr, iva, test = split(df, fold)
        preds = {}
        for name, extra in MODELS.items():
            d, w, best = fit_model(train, itr, iva, extra)
            sel[f"{fold}|{name}"] = {"lambda": best[1], "inner_val_ll": best[0], "n_train": len(train),
                                     "n_inner_train": len(itr), "n_inner_val": len(iva)}
            if fold == "final":
                save(name, d, w, best)
                continue
            p = S.sigmoid(d.X(test) @ w)
            q = S.sigmoid(d.X(test, swap=True) @ w)
            swap_err[f"{fold}|{name}"] = float(np.abs(p + q - 1).max())
            preds[name] = p
        if fold != "final":
            out = test[["fight_id", "event_id", "event_date", "y", "p_a_archived"]].reset_index(drop=True)
            out = pd.concat([out, pd.DataFrame(preds)], axis=1)
            out["market_archived"] = out.p_a_archived
            out["fold"] = fold
            allp.append(out)
    P = pd.concat(allp, ignore_index=True)
    P.to_csv(os.path.join(PRIV, "results", "sym003_oos_predictions.csv"), index=False)
    names = list(MODELS) + ["market_archived"]
    R = {"per_fold": {}, "pooled_2021_2025": {}, "historical_2026": {}, "vs_baseline_2021_2025": {},
         "vs_baseline_2026": {}, "fold_diffs_vs_baseline": {}, "selection": sel, "swap_max_error": max(swap_err.values())}
    for y in YEARS:
        d = P[P.fold == y]
        R["per_fold"][y] = {m: metrics(d[m].to_numpy(), d.y.to_numpy()) for m in names}
        R["per_fold"][y]["_n_events"] = int(d.event_id.nunique())
    head, h26 = P[P.fold.isin(HEAD)], P[P.fold == 2026]
    for m in names:
        R["pooled_2021_2025"][m] = metrics(head[m].to_numpy(), head.y.to_numpy())
        R["historical_2026"][m] = metrics(h26[m].to_numpy(), h26.y.to_numpy())
    for m in names[1:]:
        b = boot_diff(head, m, "baseline")
        fd = {y: R["per_fold"][y][m]["logloss"] - R["per_fold"][y]["baseline"]["logloss"] for y in YEARS}
        b["folds_better_of_5"] = int(sum(fd[y] < 0 for y in HEAD))
        b["meets_preregistered_rule"] = bool(b["ci95"][1] < 0 and b["folds_better_of_5"] >= 4) if m != "market_archived" else None
        R["vs_baseline_2021_2025"][m] = b
        R["vs_baseline_2026"][m] = boot_diff(h26, m, "baseline")
        R["fold_diffs_vs_baseline"][m] = fd
    R["any_group_meets_rule"] = any(R["vs_baseline_2021_2025"][m]["meets_preregistered_rule"] for m in list(MODELS)[1:])
    R["seconds"] = round(time.time() - t0, 1)
    json.dump(R, open(os.path.join(PRIV, "results", "sym003_metrics.json"), "w"), indent=1, default=float)
    print(json.dumps({"swap_max_error": R["swap_max_error"], "vs_baseline_2021_2025": R["vs_baseline_2021_2025"],
                      "any_group_meets_rule": R["any_group_meets_rule"]}, indent=1, default=float))


HASHES = {}


def save(name, d, w, best):
    body = json.dumps({"experiment": "SYM-003", "model": name, **d.to_dict(), "lambda": best[1],
                       "weights": dict(zip(FEATS + d.extra, map(float, w))),
                       "formula": "P(A wins) = sigmoid(sum_j weight_j * column_j); base column = (zA - zB)/base_diff_train_std; "
                                  "new column = clip(feature / new_feature_train_std, -5, 5); no intercept"},
                      indent=1, sort_keys=True, default=float)
    path = os.path.join(PRIV, "models", f"sym003_final_{name.replace('+', '_plus_')}.json")
    open(path, "w").write(body)
    HASHES[name] = hashlib.sha256(body.encode()).hexdigest()
    if len(HASHES) == len(MODELS):
        json.dump({"frozen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "trained_through": "2026-10-03",
                   "prospective_from": "events after 2026-10-07", "sha256": HASHES},
                  open(os.path.join(PRIV, "models", "SYM003_FROZEN.json"), "w"), indent=2)


if __name__ == "__main__":
    main()
