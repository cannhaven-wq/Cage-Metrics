"""PRED-001 - the executable half of the prediction research protocol.

Everything a verdict depends on lives here or in protocol.json, so the
acceptance and rejection rules in PREDICTION_RESEARCH_PROTOCOL.md can be re-run
by anyone with the repo and the scored rows, and give the same answer.

Plain version: a model is compared with the betting market fight by fight. The
score is how much less surprised the model was by the result than the market
was (log loss). Fights are resampled a whole card at a time to get a range.
The decision is a lookup on that range, never a judgement call.

Stdlib + numpy only. No network, no database, no clock.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import pathlib
from dataclasses import dataclass, field
from statistics import NormalDist
from typing import Callable, Iterable, Sequence

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
PROTOCOL = json.loads((HERE / "protocol.json").read_text())

T = PROTOCOL["thresholds"]
P = PROTOCOL["partitions"]

EPS = T["probability_clip"]
DEV_END = _dt.date.fromisoformat(P["dev"]["end_exclusive"])
H1_START = _dt.date.fromisoformat(P["h1"]["start"])
H1_END = _dt.date.fromisoformat(P["h1"]["end_inclusive"])


# ---------------------------------------------------------------------------
# 1. Partitions and the development guard
# ---------------------------------------------------------------------------

class HoldoutAccessError(RuntimeError):
    """Raised when development code touches a sealed fight."""


def _as_date(d) -> _dt.date:
    if isinstance(d, _dt.datetime):
        return d.date()
    if isinstance(d, _dt.date):
        return d
    return _dt.date.fromisoformat(str(d)[:10])


def partition_of(event_date) -> str:
    """DEV, H1 or SEALED. Anything on or after the dev boundary is sealed to
    development work, whether or not it is in the scored H1 window."""
    d = _as_date(event_date)
    if d < DEV_END:
        return "DEV"
    if H1_START <= d <= H1_END:
        return "H1"
    return "SEALED"


def dev_only(rows: Iterable[dict], date_key: str = "event_date") -> list[dict]:
    """The sanctioned gate for development data.

    It refuses rather than filters. A loader that silently drops 2025 rows lets
    a query that *asked* for them look fine; a loader that raises makes the
    request itself the visible mistake.
    """
    out = []
    for r in rows:
        if partition_of(r[date_key]) != "DEV":
            raise HoldoutAccessError(
                f"row dated {r[date_key]} is sealed (dev data ends before "
                f"{DEV_END}). Development code may not read it; only the "
                f"auditor's evaluate step may, once, through the ledger."
            )
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# 2. Market benchmark
# ---------------------------------------------------------------------------

def american_to_implied(american: float) -> float:
    a = float(american)
    if a == 0 or abs(a) < 100:
        raise ValueError(f"not an American price: {american}")
    return 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)


def devig_proportional(american_a: float, american_b: float) -> float:
    """Vig-free probability of corner A, proportional (multiplicative) method.
    The primary de-vig for PRED-001. Sensitivities are reported, not chosen."""
    ia, ib = american_to_implied(american_a), american_to_implied(american_b)
    return ia / (ia + ib)


# ---------------------------------------------------------------------------
# 3. Metrics
# ---------------------------------------------------------------------------

def _clip(p):
    return np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)


def log_loss_each(y, p) -> np.ndarray:
    y = np.asarray(y, dtype=float)
    p = _clip(p)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def brier_each(y, p) -> np.ndarray:
    return (np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2


def calibration_fit(y, p, iters: int = 50) -> tuple[float, float]:
    """(intercept, slope) of logit P(y=1) = a + b * logit(p). Newton-Raphson.
    A perfectly calibrated forecaster has a = 0, b = 1."""
    y = np.asarray(y, dtype=float)
    x = np.log(_clip(p) / (1 - _clip(p)))
    X = np.column_stack([np.ones_like(x), x])
    beta = np.array([0.0, 1.0])
    for _ in range(iters):
        z = X @ beta
        mu = 1 / (1 + np.exp(-z))
        W = mu * (1 - mu)
        H = X.T @ (X * W[:, None])
        g = X.T @ (y - mu)
        step = np.linalg.solve(H + 1e-9 * np.eye(2), g)
        beta = beta + step
        if np.max(np.abs(step)) < 1e-10:
            break
    return float(beta[0]), float(beta[1])


def cluster_bootstrap(values: Sequence[float], clusters: Sequence, B: int,
                      seed: int) -> np.ndarray:
    """Means of `values` over B resamples of whole clusters (UFC events).
    Fights on one card share a night, a judging crew and a news cycle, so the
    card - not the fight - is the unit that is resampled."""
    v = np.asarray(values, dtype=float)
    keys = {}
    idx = np.array([keys.setdefault(c, len(keys)) for c in clusters])
    k = len(keys)
    sums = np.bincount(idx, weights=v, minlength=k)
    cnts = np.bincount(idx, minlength=k).astype(float)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, k, size=(B, k))
    return sums[draws].sum(axis=1) / cnts[draws].sum(axis=1)


# ---------------------------------------------------------------------------
# 4. Sample size
# ---------------------------------------------------------------------------

def required_n(sd: float, effect: float, alpha_one_sided: float,
               power: float, design_effect: float = 1.0) -> int:
    """Fights needed to detect a mean log-loss gain of `effect` with a
    one-sided test. Normal approximation; design_effect >= 1 inflates for
    clustering and is floored at 1 because a measured value below 1 is not a
    licence to need fewer fights."""
    z = NormalDist().inv_cdf
    deff = max(1.0, design_effect)
    return math.ceil(deff * ((z(1 - alpha_one_sided) + z(power)) * sd / effect) ** 2)


def detectable_effect(sd: float, n: int, alpha_one_sided: float,
                      power: float) -> float:
    z = NormalDist().inv_cdf
    return (z(1 - alpha_one_sided) + z(power)) * sd / math.sqrt(n)


# ---------------------------------------------------------------------------
# 5. Corner symmetry
# ---------------------------------------------------------------------------

def symmetry_violations(predict: Callable[[dict], float], rows: Iterable[dict],
                        swap: Callable[[dict], dict], tol: float = None) -> list:
    """Rows where p(A beats B) != 1 - p(B beats A).

    Corner A wins ~64% of historical UFC fights because the A/B label is not
    random. A model that can see which corner a fighter was listed in can read
    that label and look skilful. Every scored model must be corner-symmetric.
    """
    tol = T["symmetry_tolerance"] if tol is None else tol
    bad = []
    for r in rows:
        pa = predict(r)
        pb = predict(swap(r))
        if abs(pa + pb - 1.0) > tol:
            bad.append((r, pa, pb))
    return bad


# ---------------------------------------------------------------------------
# 6. The decision
# ---------------------------------------------------------------------------

@dataclass
class Evaluation:
    stage: str                      # "H1" or "PROSPECTIVE"
    n_eligible: int
    n_scored: int
    coverage: float
    delta_ll: float                 # mean(LL_market - LL_model); > 0 = model better
    ci_lower_confirm: float         # one-sided lower bound at the stage's alpha
    ci_low95: float
    ci_high95: float
    brier_model: float
    brier_market: float
    acc_model: float
    acc_market: float
    calib_intercept: float
    calib_slope: float
    verdict: str
    reasons: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def evaluate(y, p_model, p_market, clusters, *, stage: str,
             pit_audit_passed: bool, symmetry_passed: bool,
             preregistration_intact: bool, n_required: int | None = None,
             ) -> Evaluation:
    """Score one frozen model against the market on one eligible fight set.

    p_model may contain None/NaN for fights the model abstained on. Those are
    scored at the market's probability - a zero contribution - so abstaining on
    the hard fights cannot improve the result. That is the anti-cherry-picking
    rule, implemented rather than asked for.

    Verdicts, in the order they are checked:
      INVALID      a precondition failed; nothing else is read
      SUSPECT      too good to be honest; frozen pending a written leak audit
      REJECT       no meaningful incremental information
      FAIL_CALIBRATION   beats the market on average but is mis-calibrated
      UNDERPOWERED prospective: fixed n not yet reached (interim looks only)
      PASS_H1      historical signal; licenses a prospective test, nothing else
      PASS_PROSPECTIVE   the only verdict that supports a claim of information
                         beyond the market - and still not a profit claim
      INCONCLUSIVE everything else; treated as a failure for any claim
    """
    if stage not in ("H1", "PROSPECTIVE"):
        raise ValueError(stage)
    y = np.asarray(y, dtype=float)
    pk = _clip(p_market)
    raw = np.array([np.nan if v is None else float(v) for v in p_model])
    covered = ~np.isnan(raw)
    pm = np.where(covered, raw, pk)
    pm = _clip(pm)

    n = len(y)
    coverage = float(covered.mean()) if n else 0.0
    d = log_loss_each(y, pk) - log_loss_each(y, pm)
    delta = float(d.mean()) if n else float("nan")

    alpha = T["alpha_h1_per_evaluation"] if stage == "H1" else T["alpha_prospective_per_evaluation"]
    boots = cluster_bootstrap(d, clusters, T["bootstrap_resamples"], T["bootstrap_seed"])
    lo_conf = float(np.quantile(boots, alpha))
    lo95, hi95 = (float(q) for q in np.quantile(boots, [0.025, 0.975]))
    a, b = calibration_fit(y, pm)
    acc_m = float(((pm >= 0.5) == (y == 1)).mean())
    acc_k = float(((pk >= 0.5) == (y == 1)).mean())

    ev = Evaluation(stage, n, int(covered.sum()), coverage, delta, lo_conf,
                    lo95, hi95, float(brier_each(y, pm).mean()),
                    float(brier_each(y, pk).mean()), acc_m, acc_k, a, b,
                    "INCONCLUSIVE", [])
    R = ev.reasons
    mue = T["minimum_useful_effect"]

    # INVALID - preconditions, checked before any number is looked at.
    if not preregistration_intact:
        R.append("preregistration or model artifact does not match its frozen hash")
    if not pit_audit_passed:
        R.append("point-in-time audit failed: a feature used information not available before the fight")
    if not symmetry_passed:
        R.append("model is not corner-symmetric")
    if len(set(clusters)) < T["min_events_scored"]:
        R.append(f"fewer than {T['min_events_scored']} events scored")
    if coverage < T["min_coverage"]:
        R.append(f"coverage {coverage:.1%} below {T['min_coverage']:.0%}")
    if R:
        ev.verdict = "INVALID"
        return ev

    # SUSPECT - the leak tripwires. A result this good is evidence of a bug
    # before it is evidence of skill.
    if delta > T["leak_tripwire_delta_ll"]:
        R.append(f"log-loss gain {delta:.4f} exceeds the leak tripwire {T['leak_tripwire_delta_ll']}")
    if acc_m > T["leak_tripwire_accuracy"]:
        R.append(f"accuracy {acc_m:.1%} exceeds the leak tripwire {T['leak_tripwire_accuracy']:.0%}")
    if R:
        ev.verdict = "SUSPECT"
        return ev

    # PROSPECTIVE before its fixed n: success is never declared early. From
    # the futility point on, the one early stop allowed is futility.
    if stage == "PROSPECTIVE":
        if n_required is None:
            raise ValueError("a prospective evaluation needs its preregistered n_required")
        if n < n_required:
            if n >= n_required * T["futility_min_fraction"] and hi95 < mue:
                R.append(f"futility: at {n} of {n_required} fights the 95% range tops out "
                         f"at {hi95:.4f}, below the minimum useful effect {mue}")
                ev.verdict = "REJECT"
                return ev
            R.append(f"{n} of {n_required} preregistered fights scored; no success rule applies before n")
            ev.verdict = "UNDERPOWERED"
            return ev

    # REJECT - the explicit "no meaningful incremental information" rules.
    if delta <= 0:
        R.append("the market was at least as good on average (point estimate <= 0)")
    if hi95 < mue:
        R.append(f"95% range tops out at {hi95:.4f}, below the minimum useful effect {mue}")
    if R:
        ev.verdict = "REJECT"
        return ev

    if not (T["calibration_slope_min"] <= b <= T["calibration_slope_max"]) or \
            abs(a) > T["calibration_intercept_max_abs"]:
        R.append(f"calibration intercept {a:.3f} / slope {b:.3f} outside the allowed band")
        ev.verdict = "FAIL_CALIBRATION"
        return ev

    if lo_conf > 0 and delta >= mue:
        ev.verdict = "PASS_H1" if stage == "H1" else "PASS_PROSPECTIVE"
        R.append(f"one-sided lower bound {lo_conf:.4f} > 0 at alpha {alpha} and gain {delta:.4f} >= {mue}")
        return ev

    R.append(f"lower bound {lo_conf:.4f} at alpha {alpha} does not clear 0, or gain below {mue}")
    return ev
