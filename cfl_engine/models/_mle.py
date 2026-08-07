"""Maximum-likelihood fitting + sampling for NB2 and zero-truncated NB2.

statsmodels is not a dependency here, so the negative-binomial GLM is fitted by
hand with scipy.optimize (L-BFGS-B) and analytic gradients. NB2 parameterisation:

    mu    = exp(offset + X @ beta)          conditional mean
    r     = 1 / alpha                        dispersion (r -> inf is Poisson)
    Var   = mu + alpha * mu^2
    p     = r / (r + mu)                     numpy's success prob

Per-observation log-likelihood:
    l = gammaln(y+r) - gammaln(r) - gammaln(y+1)
        + r*log(r/(r+mu)) + y*log(mu/(r+mu))

Gradients used below:
    dl/d(eta) = r*(y - mu)/(r + mu)                         -> dL/dbeta = X^T . that
    dl/dr     = psi(y+r) - psi(r) + log(r/(r+mu)) + 1 - (r+y)/(r+mu)
We optimise theta = log(alpha) with r = exp(-theta), so dl/dtheta = (dl/dr)*(-r).
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln, digamma

MAX_ETA = 30.0   # clamp to keep exp() finite


def _mu(beta, X, offset):
    eta = offset + X @ beta
    np.clip(eta, -MAX_ETA, MAX_ETA, out=eta)
    return np.exp(eta)


def _nb2_nll_grad(params, X, y, offset, w):
    beta, theta = params[:-1], params[-1]
    r = np.exp(-theta)
    eta = offset + X @ beta
    np.clip(eta, -MAX_ETA, MAX_ETA, out=eta)
    mu = np.exp(eta)
    rpm = r + mu
    ll = (gammaln(y + r) - gammaln(r) - gammaln(y + 1.0)
          + r * (np.log(r) - np.log(rpm)) + y * (np.log(mu) - np.log(rpm)))
    nll = -(w * ll).sum()

    d_eta = w * r * (y - mu) / rpm                   # w * dl/deta
    g_beta = -(X.T @ d_eta)
    dl_dr = (digamma(y + r) - digamma(r) + np.log(r) - np.log(rpm)
             + 1.0 - (r + y) / rpm)
    g_theta = -(w * dl_dr * (-r)).sum()
    grad = np.append(g_beta, g_theta)
    if not np.isfinite(nll):
        return 1e12, np.zeros_like(params)
    return nll, grad


def fit_nb2(X, y, offset, weights=None, l2=1e-4):
    """Fit an NB2 GLM. X includes its own intercept column. Returns a dict.

    weights: optional per-observation weights (e.g. recency decay). They rescale
    the log-likelihood, so the fitted mean tracks the weighted (recent) data.
    """
    X = np.asarray(X, float); y = np.asarray(y, float); offset = np.asarray(offset, float)
    w = np.ones_like(y) if weights is None else np.asarray(weights, float)
    k = X.shape[1]

    def obj(p):
        nll, grad = _nb2_nll_grad(p, X, y, offset, w)
        # ridge on slopes only (not intercept, not theta)
        pen = l2 * np.sum(p[1:-1] ** 2)
        gpen = np.zeros_like(p); gpen[1:-1] = 2 * l2 * p[1:-1]
        return nll + pen, grad + gpen

    p0 = np.zeros(k + 1)
    p0[0] = np.log(max(y.mean(), 0.1))        # intercept ~ log mean rate
    p0[-1] = 0.0                              # log alpha = 0 -> alpha=1
    res = minimize(obj, p0, jac=True, method="L-BFGS-B",
                   options=dict(maxiter=500, ftol=1e-9))
    beta = res.x[:-1]; alpha = float(np.exp(res.x[-1])); r = 1.0 / alpha
    return dict(beta=beta, alpha=alpha, r=r, loglik=-res.fun, success=bool(res.success))


def _truncnb2_nll(params, X, y, offset, w):
    """Zero-truncated NB2 (y >= 1 only). Subtract log(1 - P(0)) per obs."""
    beta, theta = params[:-1], params[-1]
    r = np.exp(-theta)
    eta = offset + X @ beta
    np.clip(eta, -MAX_ETA, MAX_ETA, out=eta)
    mu = np.exp(eta)
    rpm = r + mu
    ll = (gammaln(y + r) - gammaln(r) - gammaln(y + 1.0)
          + r * (np.log(r) - np.log(rpm)) + y * (np.log(mu) - np.log(rpm)))
    logp0 = r * (np.log(r) - np.log(rpm))            # log P(Y=0)
    p0 = np.exp(np.clip(logp0, -700, -1e-12))
    ll = ll - np.log1p(-p0)
    nll = -(w * ll).sum()
    return nll if np.isfinite(nll) else 1e12


def fit_truncnb2(X, y, offset, weights=None, l2=1e-4):
    """Fit zero-truncated NB2 on the y>=1 subset (numeric gradient)."""
    X = np.asarray(X, float); y = np.asarray(y, float); offset = np.asarray(offset, float)
    w = np.ones_like(y) if weights is None else np.asarray(weights, float)
    k = X.shape[1]

    def obj(p):
        return _truncnb2_nll(p, X, y, offset, w) + l2 * np.sum(p[1:-1] ** 2)

    p0 = np.zeros(k + 1)
    p0[0] = np.log(max(y.mean() - 1.0, 0.1))
    res = minimize(obj, p0, method="L-BFGS-B", options=dict(maxiter=500))
    beta = res.x[:-1]; alpha = float(np.exp(res.x[-1])); r = 1.0 / alpha
    return dict(beta=beta, alpha=alpha, r=r, loglik=-res.fun, success=bool(res.success))


def predict_mu(fit, X, offset):
    return _mu(fit["beta"], np.asarray(X, float), np.asarray(offset, float))


# ------------------------------------------------------------------ sampling ---
def sample_nb2(rng, mu, r):
    """Vectorised NB2 draw with mean mu, dispersion r (=1/alpha)."""
    mu = np.asarray(mu, float)
    p = r / (r + mu)
    p = np.clip(p, 1e-9, 1 - 1e-12)
    return rng.negative_binomial(r, p)


def sample_truncnb2(rng, mu, r, max_passes=6):
    """Zero-truncated NB2 draw (values >= 1) via rejection, clamped to >=1."""
    mu = np.asarray(mu, float)
    out = sample_nb2(rng, mu, r)
    zeros = out == 0
    passes = 0
    while zeros.any() and passes < max_passes:
        out[zeros] = sample_nb2(rng, mu[zeros], r)
        zeros = out == 0
        passes += 1
    out[out == 0] = 1                     # residual: floor to 1 (rare)
    return out
