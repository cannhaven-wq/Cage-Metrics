"""WIN-001 model: market-plus-stats logistic blend, weights frozen on DEV.

Incremental form (the one PRED-001 §4 scores):

    logit p_model = w_m * logit(p_market) + sum_i w_i * d_i / s_i

where d_i are the antisymmetric A-B features from features.py, s_i their DEV
standard deviations, and p_market the proportionally de-vigged BFO closing
consensus. There is no intercept, so corner symmetry is exact.

The frozen artifact is artifact.json: feature list, scales, weights, the DEV
data fingerprint and the fit configuration. predict() reads only that file
plus the feature rows, so a third party can reproduce every probability.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

import features as F

HERE = pathlib.Path(__file__).resolve().parent
ARTIFACT = HERE / "artifact.json"

VARIANTS = {
    # name: (feature list, L2 C). The honest set compared on DEV; see DEV_RESULTS.md.
    "market_only": ([], 1.0),
    "elo": (["elo"], 1.0),
    "elo_age_record": (["elo", "age", "ufc_gap"], 1.0),
    "full_c1": (F.DIFF_FEATURES, 1.0),
    "full_c01": (F.DIFF_FEATURES, 0.1),
    "full_c001": (F.DIFF_FEATURES, 0.01),
}


def design(rows: pd.DataFrame, p_market: np.ndarray, feats: list[str], scale: dict | None):
    X = F.matchup_matrix(rows, feats)
    if scale is None:
        scale = {c: float(X[c].std(ddof=0)) or 1.0 for c in X.columns}
    for c in X.columns:
        X[c] = X[c] / scale[c]
    X.insert(0, "logit_market", F.logit(p_market))
    return X, scale


def fit(rows: pd.DataFrame, p_market: np.ndarray, y: np.ndarray, feats: list[str], C: float,
        standalone: bool = False) -> dict:
    X, scale = design(rows, p_market, feats, None)
    if standalone:
        X = X.drop(columns=["logit_market"])
    clf = LogisticRegression(fit_intercept=False, C=C, max_iter=2000)
    clf.fit(X.to_numpy(), y)
    coef = dict(zip(X.columns, map(float, clf.coef_[0])))
    return {"features": list(feats), "scale": scale, "coef": coef, "C": C,
            "standalone": standalone, "n_fit": int(len(y))}


def predict(art: dict, rows: pd.DataFrame, p_market: np.ndarray) -> np.ndarray:
    X, _ = design(rows, p_market, art["features"], art["scale"])
    if art.get("standalone"):
        X = X.drop(columns=["logit_market"])
    z = sum(X[c].to_numpy() * w for c, w in art["coef"].items())
    return 1.0 / (1.0 + np.exp(-z))


def sha256_file(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save_artifact(art: dict, path: pathlib.Path = ARTIFACT) -> str:
    path.write_text(json.dumps(art, indent=1, sort_keys=True) + "\n")
    return sha256_file(path)


def load_artifact(path: pathlib.Path = ARTIFACT) -> dict:
    return json.loads(path.read_text())
