"""Discrete-time logistic hazard model for 3-round fight duration.

The dataset (features/build_features.py) is a person-period table: one row per
(fight, round the fight reached), with event = 1 iff the fight ended (was
finished) in that round. Fitting a logistic regression to

    P(event=1 | reached this round) = sigmoid( a1*r1 + a2*r2 + a3*r3 + b.x )

gives the discrete-time hazard h_r. The round dummies carry the baseline
per-round hazard shape; covariates x shift it. From the three hazards the full
duration distribution follows by the survival identity:

    P(ends R1) = h1
    P(ends R2) = (1-h1) h2
    P(ends R3) = (1-h1)(1-h2) h3        (a round-3 finish)
    P(decision / go the distance) = (1-h1)(1-h2)(1-h3)
    E[minutes]  = h1*2.5 + (1-h1)[5 + h2*2.5 + (1-h2)(5 + h3*2.5 + (1-h3)*5)]
                  (a finish is assumed to land mid-round on average)

Primary fitter is statsmodels Logit so we get proper coefficient CIs. If the
MLE fails to converge / separates, we fall back to an L2-regularized fit and
flag that Wald CIs are unavailable. Isotonic recalibration is fit ONLY on
validation rows the caller supplies (the harness fits it on prior OOS folds).
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

try:
    import statsmodels.api as sm
    _HAVE_SM = True
except Exception:                                    # pragma: no cover
    _HAVE_SM = False

ROUND_COLS = ["r1", "r2", "r3"]
EPS = 1e-6


class DurationHazardModel:
    def __init__(self, round_cols=ROUND_COLS, l2_alpha: float = 1.0):
        self.round_cols = list(round_cols)
        self.l2_alpha = l2_alpha            # used only by the regularized fallback
        self.cov_cols_: list[str] = []
        self.kept_cov_: list[str] = []
        self.mu_ = None
        self.sd_ = None
        self.params_ = None                 # pd.Series indexed by design column
        self.conf_int_ = None               # DataFrame or None (None if regularized)
        self.regularized_ = False
        self.iso_: IsotonicRegression | None = None

    # ---------------------------------------------------------------- design
    def _design(self, df: pd.DataFrame) -> pd.DataFrame:
        """Round dummies (raw) + standardized covariates, in a stable column order."""
        rd = df[self.round_cols].astype(float).reset_index(drop=True)
        cov = df[self.kept_cov_].astype(float).reset_index(drop=True)
        cov = (cov - self.mu_) / self.sd_
        X = pd.concat([rd, cov], axis=1)
        X.columns = self.round_cols + self.kept_cov_
        return X

    # ---------------------------------------------------------------- fit
    def fit(self, df: pd.DataFrame, cov_cols: list[str]):
        self.cov_cols_ = list(cov_cols)
        # drop covariates with no variance in THIS training slice (sparse one-hots)
        sub = df[self.cov_cols_].astype(float)
        var = sub.var(axis=0, ddof=0)
        self.kept_cov_ = [c for c in self.cov_cols_ if var.get(c, 0.0) > 1e-12]
        self.mu_ = sub[self.kept_cov_].mean(axis=0)
        self.sd_ = sub[self.kept_cov_].std(axis=0, ddof=0).replace(0.0, 1.0)

        X = self._design(df)
        y = df["event"].astype(float).reset_index(drop=True).to_numpy()

        if not _HAVE_SM:
            self._fit_sklearn(X, y)
            return self
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                res = sm.Logit(y, X.to_numpy()).fit(method="newton", maxiter=100, disp=0)
                if not res.mle_retvals.get("converged", False):
                    res = sm.Logit(y, X.to_numpy()).fit(method="bfgs", maxiter=500, disp=0)
                if (not res.mle_retvals.get("converged", False)
                        or not np.all(np.isfinite(res.params))):
                    raise ValueError("MLE did not converge")
                self.params_ = pd.Series(res.params, index=X.columns)
                ci = res.conf_int()
                self.conf_int_ = pd.DataFrame(ci, index=X.columns,
                                              columns=["ci_low", "ci_high"])
                self.regularized_ = False
            except Exception as e:                    # separation / singular / non-conv
                warnings.warn(f"MLE failed ({e}); L2-regularized fallback, CIs off.")
                res = sm.Logit(y, X.to_numpy()).fit_regularized(
                    alpha=self.l2_alpha, maxiter=200, disp=0)
                self.params_ = pd.Series(res.params, index=X.columns)
                self.conf_int_ = None
                self.regularized_ = True
        return self

    def _fit_sklearn(self, X, y):
        from sklearn.linear_model import LogisticRegression
        lr = LogisticRegression(penalty="l2", C=1.0 / self.l2_alpha,
                                fit_intercept=False, max_iter=500)
        lr.fit(X.to_numpy(), y)
        self.params_ = pd.Series(lr.coef_[0], index=X.columns)
        self.conf_int_ = None
        self.regularized_ = True

    # ---------------------------------------------------------------- predict
    def _raw_hazard(self, df: pd.DataFrame) -> np.ndarray:
        X = self._design(df)
        z = X.to_numpy() @ self.params_.to_numpy()
        return 1.0 / (1.0 + np.exp(-z))

    def predict_hazard(self, df: pd.DataFrame, calibrated: bool = True) -> np.ndarray:
        """Per person-period-row hazard P(finish this round | reached it)."""
        h = self._raw_hazard(df)
        if calibrated and self.iso_ is not None:
            h = self.iso_.predict(np.clip(h, EPS, 1 - EPS))
        return np.clip(h, EPS, 1 - EPS)

    # -------------------------------------------------------- recalibration
    def fit_calibration(self, df_val: pd.DataFrame):
        """Fit isotonic on VALIDATION rows only (raw hazard -> observed event)."""
        raw = self._raw_hazard(df_val)
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(np.clip(raw, EPS, 1 - EPS), df_val["event"].astype(float).to_numpy())
        self.iso_ = iso
        return self

    # -------------------------------------------------- fight-level distribution
    def fight_distribution(self, fight_df: pd.DataFrame, calibrated: bool = True) -> pd.DataFrame:
        """One row per fight in -> duration distribution, P(GTD), E[minutes] out.

        fight_df needs the covariate columns (round dummies are set internally).
        """
        base = fight_df.reset_index(drop=True).copy()
        n = len(base)
        h = {}
        for r in (1, 2, 3):
            d = base.copy()
            d["r1"] = 1.0 if r == 1 else 0.0
            d["r2"] = 1.0 if r == 2 else 0.0
            d["r3"] = 1.0 if r == 3 else 0.0
            h[r] = self.predict_hazard(d, calibrated=calibrated)
        h1, h2, h3 = h[1], h[2], h[3]
        s1, s2 = 1 - h1, 1 - h2
        p_r1, p_r2, p_r3 = h1, s1 * h2, s1 * s2 * h3
        p_dec = s1 * s2 * (1 - h3)
        exp_min = h1 * 2.5 + s1 * (5 + h2 * 2.5 + s2 * (5 + h3 * 2.5 + (1 - h3) * 5))
        out = pd.DataFrame({
            "p_ends_r1": p_r1, "p_ends_r2": p_r2, "p_ends_r3": p_r3,
            "p_decision": p_dec, "p_gtd": p_dec, "exp_minutes": exp_min,
            "haz_r1": h1, "haz_r2": h2, "haz_r3": h3,
        }, index=base.index)
        if "fight_id" in base.columns:
            out.insert(0, "fight_id", base["fight_id"].to_numpy())
        return out

    # ---------------------------------------------------------------- reporting
    def coef_table(self) -> pd.DataFrame:
        t = pd.DataFrame({"coef": self.params_})
        if self.conf_int_ is not None:
            t["ci_low"] = self.conf_int_["ci_low"]
            t["ci_high"] = self.conf_int_["ci_high"]
        t["regularized_no_ci"] = self.regularized_
        return t
