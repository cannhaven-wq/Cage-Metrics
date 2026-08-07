"""Per fighter-round count models: significant strikes and takedowns.

Sig strikes  -- negative-binomial (NB2) GLM, offset = log(round minutes).
    Covariates: own offense rate, opponent sig-strikes-ALLOWED rate (their
    defense, computed point-in-time from the fights/rounds data -- never a career
    str_def field), style matchup (own & opponent grappling activity), round
    number, and an own decay slope (late-round fade interacted with round number).

Takedowns   -- hurdle model:
    stage 1  logistic  P(at least one TD this round)
    stage 2  zero-truncated NB2 for the count given >= 1.
    Covariates: own TD rate, opponent TD-ALLOWED rate, style matchup, round.

Both expose params_for(df) so the simulator can request the round-level
distribution parameters for any (fighter, opponent, round, minutes) context using
exactly the same feature construction as training -- no train/serve skew.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from _mle import fit_nb2, fit_truncnb2, predict_mu, sample_nb2, sample_truncnb2

C_STR = 0.1
C_TD = 0.02
HALFLIFE_YEARS = 2.0     # recency decay, matching the engine's 2-year half-life


def _log(x, c):
    return np.log(np.asarray(x, float) + c)


def recency_weights(df, halflife_years=HALFLIFE_YEARS):
    """0.5 ** (age / halflife) relative to the newest row -- corrects the
    train->serve strike-volume drift that otherwise biases predictions high."""
    if "event_date" not in df.columns:
        return np.ones(len(df))
    d = pd.to_datetime(df["event_date"])
    age_days = (d.max() - d).dt.days.to_numpy(float)
    return 0.5 ** (age_days / (365.25 * halflife_years))


def sig_design(df):
    rn = df["round_number"].to_numpy(float)
    round_c = rn - 1.0
    decay_slope = (df["own_decay"].to_numpy(float) - 1.0) * round_c
    X = np.column_stack([
        np.ones(len(df)),
        _log(df["own_sig_off_pm"], C_STR),
        _log(df["opp_sig_def_pm"], C_STR),
        _log(df["opp_grapp_pm"], C_STR),
        _log(df["own_grapp_pm"], C_STR),
        round_c,
        decay_slope,
    ])
    names = ["intercept", "own_off", "opp_def", "opp_grapp", "own_grapp",
             "round", "decay_slope"]
    return X, names


def td_design(df, with_minutes=False):
    rn = df["round_number"].to_numpy(float)
    cols = [
        np.ones(len(df)),
        _log(df["own_td_off_pm"], C_TD),
        _log(df["opp_td_def_pm"], C_TD),
        _log(df["own_grapp_pm"], C_STR),
        _log(df["opp_grapp_pm"], C_STR),
        rn - 1.0,
    ]
    names = ["intercept", "own_td", "opp_tddef", "own_grapp", "opp_grapp", "round"]
    if with_minutes:
        cols.append(np.log(df["round_minutes"].to_numpy(float)))
        names.append("log_min")
    return np.column_stack(cols), names


class SigStrikeModel:
    """NB2 GLM for significant strikes landed per round."""

    def __init__(self):
        self.fit_ = None
        self.names = None
        self.cal_ = 1.0                       # multiplicative drift recalibration

    def fit(self, df, halflife_years=HALFLIFE_YEARS, calibrate_tail_days=365):
        X, self.names = sig_design(df)
        offset = np.log(df["round_minutes"].to_numpy(float))
        w = recency_weights(df, halflife_years)
        self.fit_ = fit_nb2(X, df["sig_landed"].to_numpy(float), offset, weights=w)
        self.cal_ = self._fit_recalibration(df, calibrate_tail_days)
        return self

    def _fit_recalibration(self, df, tail_days):
        """PIT-safe level correction: on the most recent tail of TRAINING, the
        all-history fit over-predicts by the same drift it will at serve time, so
        c = sum(actual)/sum(predicted) there cancels it. Strictly before test."""
        if "event_date" not in df.columns or tail_days is None:
            return 1.0
        d = pd.to_datetime(df["event_date"])
        mask = (d >= d.max() - pd.Timedelta(days=tail_days)).to_numpy()
        if mask.sum() < 200:
            mask = np.ones(len(df), bool)
        sub = df[mask]
        X, _ = sig_design(sub)
        mu = predict_mu(self.fit_, X, np.log(sub["round_minutes"].to_numpy(float)))
        y = sub["sig_landed"].to_numpy(float)
        return float(y.sum() / max(mu.sum(), 1e-9))

    def params_for(self, df):
        """Return (mu array, r) for the given rows (drift-recalibrated)."""
        X, _ = sig_design(df)
        offset = np.log(df["round_minutes"].to_numpy(float))
        mu = predict_mu(self.fit_, X, offset) * self.cal_
        return mu, self.fit_["r"]

    def sample(self, rng, df):
        mu, r = self.params_for(df)
        return sample_nb2(rng, mu, r)

    def mu_per_min(self, df):
        """mu at exactly 1 minute (= exp(X.beta)); mu scales linearly with min."""
        d = df.copy(); d["round_minutes"] = 1.0
        mu, r = self.params_for(d)
        return mu, r

    def logpmf(self, df):
        from scipy.special import gammaln
        mu, r = self.params_for(df)
        y = df["sig_landed"].to_numpy(float)
        rpm = r + mu
        return (gammaln(y + r) - gammaln(r) - gammaln(y + 1.0)
                + r * (np.log(r) - np.log(rpm)) + y * (np.log(mu) - np.log(rpm)))


class TakedownModel:
    """Hurdle: logistic P(any TD) x zero-truncated NB2 count | >=1."""

    def __init__(self):
        self.clf = None
        self.trunc = None
        self.s1_names = None

    def fit(self, df, halflife_years=HALFLIFE_YEARS):
        X1, self.s1_names = td_design(df, with_minutes=True)
        y_any = df["td_any"].to_numpy(int)
        w = recency_weights(df, halflife_years)
        self.clf = LogisticRegression(C=2.0, max_iter=1000)
        self.clf.fit(X1[:, 1:], y_any, sample_weight=w)   # sklearn adds its intercept
        pos = df[df["td_any"] == 1]
        if len(pos) >= 50:
            X2, _ = td_design(pos)
            offset = np.log(pos["round_minutes"].to_numpy(float))
            wp = recency_weights(pos, halflife_years)
            self.trunc = fit_truncnb2(X2, pos["td_landed"].to_numpy(float), offset,
                                      weights=wp)
        else:                                   # too few positives: degenerate to 1
            self.trunc = None
        return self

    def p_any(self, df):
        X1, _ = td_design(df, with_minutes=True)
        return self.clf.predict_proba(X1[:, 1:])[:, 1]

    def params_for(self, df):
        """Return (p_any, mu2, r2). mu2/r2 describe the count given >=1."""
        p = self.p_any(df)
        if self.trunc is None:
            return p, np.ones(len(df)), 1e6
        X2, _ = td_design(df)
        offset = np.log(df["round_minutes"].to_numpy(float))
        mu2 = predict_mu(self.trunc, X2, offset)
        return p, mu2, self.trunc["r"]

    def stage1_ab(self, df):
        """P(any TD) as sigmoid(a + b*log(minutes)): return (a per row, b scalar).

        Lets the simulator vary round minutes cheaply without rebuilding designs.
        """
        X1, names = td_design(df, with_minutes=True)
        j = names.index("log_min") - 1          # sklearn coef excludes intercept col
        coef = self.clf.coef_[0]
        b = float(coef[j])
        cols = X1[:, 1:].copy()
        cols[:, j] = 0.0                          # strip the log_min contribution
        a = self.clf.intercept_[0] + cols @ coef
        return a, b

    def stage2_mu_per_min(self, df):
        """Truncated-NB2 mu at 1 minute, and its dispersion r."""
        if self.trunc is None:
            return np.ones(len(df)), 1e6
        d = df.copy(); d["round_minutes"] = 1.0
        X2, _ = td_design(d)
        offset = np.zeros(len(d))                 # log(1)=0
        return predict_mu(self.trunc, X2, offset), self.trunc["r"]

    def expected(self, df):
        """E[TD] = P(any) * E[count | >=1]. E of trunc-NB2 = mu/(1-P0)."""
        p, mu2, r = self.params_for(df)
        p0 = (r / (r + mu2)) ** r
        e_given = mu2 / np.clip(1.0 - p0, 1e-6, 1.0)
        return p * e_given

    def sample(self, rng, df):
        p, mu2, r = self.params_for(df)
        any_td = rng.random(len(df)) < p
        counts = np.zeros(len(df), int)
        if any_td.any():
            counts[any_td] = sample_truncnb2(rng, mu2[any_td], r)
        return counts


# --------------------------------------------------------------- baselines ---
class BaselineSig:
    """Marginal NB2: intercept + offset only (no covariates)."""
    def __init__(self):
        self.fit_ = None

    def fit(self, df, halflife_years=HALFLIFE_YEARS):
        X = np.ones((len(df), 1))
        offset = np.log(df["round_minutes"].to_numpy(float))
        w = recency_weights(df, halflife_years)
        self.fit_ = fit_nb2(X, df["sig_landed"].to_numpy(float), offset, weights=w)
        return self

    def params_for(self, df):
        X = np.ones((len(df), 1))
        offset = np.log(df["round_minutes"].to_numpy(float))
        return predict_mu(self.fit_, X, offset), self.fit_["r"]

    def logpmf(self, df):
        from scipy.special import gammaln
        mu, r = self.params_for(df)
        y = df["sig_landed"].to_numpy(float)
        rpm = r + mu
        return (gammaln(y + r) - gammaln(r) - gammaln(y + 1.0)
                + r * (np.log(r) - np.log(rpm)) + y * (np.log(mu) - np.log(rpm)))


class BaselineTD:
    """Marginal hurdle: constant P(any) and constant mean count | >=1."""
    def __init__(self):
        self.p = None
        self.mu_given = None

    def fit(self, df, halflife_years=HALFLIFE_YEARS):
        w = recency_weights(df, halflife_years)
        self.p = float(np.average(df["td_any"].to_numpy(float), weights=w))
        pos = df[df["td_any"] == 1]
        if len(pos):
            wp = recency_weights(pos, halflife_years)
            self.mu_given = float(np.average(pos["td_landed"].to_numpy(float), weights=wp))
        else:
            self.mu_given = 1.0
        return self

    def expected(self, df):
        return np.full(len(df), self.p * self.mu_given)
