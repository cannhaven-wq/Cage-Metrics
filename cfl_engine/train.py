"""Walk-forward training with leak-free tuning, rolling calibration, market blend.

Chronology is sacred:
- Hyperparameters are tuned only on data preceding ALL evaluation slices.
- Each fold trains on everything strictly before its test slice.
- The isotonic calibrator for fold k is fit only on out-of-sample predictions
  from folds < k. Same for the market-blend logistic regression.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier

from engine import predict_symmetric

EPS = 1e-4

PARAM_GRID = {
    "max_depth": [3, 4, 6],
    "learning_rate": [0.05, 0.1],
    "min_child_weight": [1, 10],
}
FIXED = dict(
    n_estimators=2000,
    subsample=0.9,
    colsample_bytree=0.9,
    objective="binary:logistic",
    eval_metric="logloss",
    tree_method="hist",
    n_jobs=4,
    random_state=13,
)


def _logit(p):
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def chronological_folds(n: int, base_frac: float = 0.55, n_slices: int = 6):
    """Expanding-window folds over row indices already sorted by date."""
    base = int(n * base_frac)
    cuts = np.linspace(base, n, n_slices + 1).astype(int)
    return [(np.arange(0, cuts[i]), np.arange(cuts[i], cuts[i + 1])) for i in range(n_slices)]


def tune(X: pd.DataFrame, y: np.ndarray, base_end: int, log=print) -> dict:
    """Tune on the base window only: train on first 80%, validate on last 20%.
    Everything used here precedes every evaluation slice -> no tuning leak."""
    split = int(base_end * 0.8)
    Xtr, ytr = X.iloc[:split], y[:split]
    Xv, yv = X.iloc[split:base_end], y[split:base_end]
    best, best_ll = None, np.inf
    for md, lr, mcw in itertools.product(*PARAM_GRID.values()):
        m = XGBClassifier(max_depth=md, learning_rate=lr, min_child_weight=mcw,
                          early_stopping_rounds=75, **FIXED)
        m.fit(Xtr, ytr, eval_set=[(Xv, yv)], verbose=False)
        ll = m.best_score
        if ll < best_ll:
            best_ll = ll
            best = dict(max_depth=md, learning_rate=lr, min_child_weight=mcw)
    log(f"  tuned params: {best}  (base-window val logloss {best_ll:.4f})")
    return best


def walk_forward(X: pd.DataFrame, y: np.ndarray, diff_cols: list[str],
                 params: dict, folds, log=print):
    """Returns (oos DataFrame indexed like X rows in test slices, last_model)."""
    records = []
    last_model = None
    for k, (tr, te) in enumerate(folds):
        es = int(len(tr) * 0.9)  # last 10% of the training window (still pre-test) for early stopping
        m = XGBClassifier(early_stopping_rounds=75, **{**FIXED, **params})
        m.fit(X.iloc[tr[:es]], y[tr[:es]], eval_set=[(X.iloc[tr[es:]], y[tr[es:]])], verbose=False)
        p_sym, asym = predict_symmetric(m, X.iloc[te], diff_cols)
        records.append(pd.DataFrame({
            "row": te, "fold": k, "p_raw": p_sym.astype("float64"),
            "raw_asymmetry": asym.astype("float64"), "y": y[te],
        }))
        last_model = m
        log(f"  fold {k}: train n={len(tr)}  test n={len(te)}  best_iter={m.best_iteration}")
    return pd.concat(records, ignore_index=True), last_model


ISO_MIN_POOL = 1500  # below this, isotonic's step function overfits; use Platt


def rolling_calibrate(oos: pd.DataFrame) -> pd.DataFrame:
    """Calibrator for fold k is fit only on OOS preds of folds < k. Fold 0 stays raw.
    Small prior pools get Platt scaling (strictly monotone, low variance);
    large pools graduate to isotonic."""
    oos = oos.copy()
    oos["p_cal"] = oos["p_raw"].astype("float64")
    oos["calibrated"] = False
    for k in sorted(oos["fold"].unique()):
        if k == 0:
            continue
        prior = oos[oos["fold"] < k]
        mask = oos["fold"] == k
        pk = oos.loc[mask, "p_raw"].to_numpy()
        if len(prior) >= ISO_MIN_POOL:
            iso = IsotonicRegression(y_min=EPS, y_max=1 - EPS, out_of_bounds="clip")
            iso.fit(prior["p_raw"].to_numpy(), prior["y"].to_numpy())
            oos.loc[mask, "p_cal"] = iso.predict(pk)
        else:
            platt = LogisticRegression(C=1e6, max_iter=1000)
            platt.fit(_logit(prior["p_raw"].to_numpy()).reshape(-1, 1),
                      prior["y"].to_numpy())
            oos.loc[mask, "p_cal"] = platt.predict_proba(_logit(pk).reshape(-1, 1))[:, 1]
        oos.loc[mask, "calibrated"] = True
    oos["p_cal"] = oos["p_cal"].clip(EPS, 1 - EPS)
    return oos


def rolling_blend(oos: pd.DataFrame) -> pd.DataFrame:
    """Logistic stack of [logit(model), logit(market)] fit on prior folds only.
    Rows without odds get p_blend = p_cal."""
    oos = oos.copy()
    oos["p_blend"] = oos["p_cal"].astype("float64")
    oos["blended"] = False
    has_q = oos["q_mkt"].notna()
    for k in sorted(oos["fold"].unique()):
        if k == 0:
            continue
        prior = oos[(oos["fold"] < k) & has_q]
        mask = (oos["fold"] == k) & has_q
        if len(prior) < 200 or mask.sum() == 0:
            continue
        Z = np.column_stack([_logit(prior["p_cal"]), _logit(prior["q_mkt"])])
        lr = LogisticRegression(C=100.0, max_iter=1000)
        lr.fit(Z, prior["y"].to_numpy())
        Zk = np.column_stack([_logit(oos.loc[mask, "p_cal"]), _logit(oos.loc[mask, "q_mkt"])])
        oos.loc[mask, "p_blend"] = lr.predict_proba(Zk)[:, 1]
        oos.loc[mask, "blended"] = True
    oos["p_blend"] = oos["p_blend"].clip(EPS, 1 - EPS)
    return oos
