"""The one model family Phase 1 uses: the market, nudged.

    logit p(A wins) = (1 + g) * logit(q_market) + sum_j b_j * x_j

q_market is the de-vigged closing consensus. Every x_j is antisymmetric (A minus
B) and there is no intercept, so p(A) = 1 - p(B) exactly. g and b are
ridge-shrunk toward zero, so with no information the model IS the market.

This is PRED-001's incremental form (section 4): a combination of market and
model, scored against the market quote it consumed. A candidate is never fitted
standalone except in one clearly labelled context model.

Pure numpy. No randomness, no clock, no I/O.
"""
from __future__ import annotations

import numpy as np

CLIP = 1e-4


def logit(p):
    p = np.clip(np.asarray(p, dtype=float), CLIP, 1 - CLIP)
    return np.log(p / (1 - p))


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(np.asarray(z, dtype=float), -35.0, 35.0)))


def fit_offset_logistic(X: np.ndarray, offset: np.ndarray, y: np.ndarray, ridge: float,
                        market_slope: bool = True, iters: int = 50, tol: float = 1e-9) -> np.ndarray:
    """Newton-Raphson with an L2 penalty. Returns theta = [g, b_1..b_k] (g
    omitted when market_slope is False). X must already be scaled; rows with
    a missing value must already be 0 (= "no difference")."""
    X = np.asarray(X, dtype=float).reshape(len(y), -1)
    Z = np.column_stack([offset, X]) if market_slope else X
    k = Z.shape[1]
    theta = np.zeros(k)
    if k == 0:
        return theta
    lam = ridge * np.eye(k)
    for _ in range(iters):
        mu = sigmoid(offset + Z @ theta)
        W = mu * (1 - mu)
        g = Z.T @ (y - mu) - ridge * theta
        H = (Z.T * W) @ Z + lam
        step = np.linalg.solve(H + 1e-10 * np.eye(k), g)
        theta = theta + step
        if np.max(np.abs(step)) < tol:
            break
    return theta


def predict_offset_logistic(theta: np.ndarray, X: np.ndarray, offset: np.ndarray,
                            market_slope: bool = True) -> np.ndarray:
    X = np.asarray(X, dtype=float).reshape(len(offset), -1)
    Z = np.column_stack([offset, X]) if market_slope else X
    if Z.shape[1] == 0:
        return sigmoid(offset)
    return sigmoid(offset + Z @ theta)


class Scaler:
    """Fitted on a training fold only. Antisymmetric columns are clipped at the
    99th percentile of |x| and divided by their root-mean-square - never
    centred, because subtracting a mean from an A-minus-B column smuggles in
    an intercept, i.e. reads the corner label. Missing values become 0."""

    def __init__(self, clip_q: float = 0.99):
        self.clip_q = clip_q

    def fit(self, X: np.ndarray) -> "Scaler":
        X = np.asarray(X, dtype=float)
        A = np.abs(X)
        self.cap = np.array([np.nanquantile(c, self.clip_q) if np.isfinite(c).any() else 1.0
                             for c in A.T])
        self.cap[~np.isfinite(self.cap) | (self.cap <= 0)] = 1.0
        C = np.clip(X, -self.cap, self.cap)
        rms = np.sqrt(np.nanmean(C ** 2, axis=0))
        self.rms = np.where(np.isfinite(rms) & (rms > 0), rms, 1.0)
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        X = np.clip(np.asarray(X, dtype=float), -self.cap, self.cap) / self.rms
        return np.nan_to_num(X, nan=0.0)


class CtxScaler:
    """Symmetric context columns may be centred (they never enter alone).
    Missing context reads as the training mean, i.e. 'typical'."""

    def fit(self, c: np.ndarray) -> "CtxScaler":
        c = np.asarray(c, dtype=float)
        self.lo, self.hi = np.nanquantile(c, 0.01), np.nanquantile(c, 0.99)
        cc = np.clip(c, self.lo, self.hi)
        self.mu = float(np.nanmean(cc))
        sd = float(np.nanstd(cc))
        self.sd = sd if sd > 0 else 1.0
        return self

    def transform(self, c: np.ndarray) -> np.ndarray:
        z = (np.clip(np.asarray(c, dtype=float), self.lo, self.hi) - self.mu) / self.sd
        return np.nan_to_num(z, nan=0.0)
