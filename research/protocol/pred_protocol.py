"""PRED-001 - the executable half of the prediction research protocol.

Everything a verdict depends on lives here, in protocol.json and in
holdout_manifest.json, so the acceptance and rejection rules in
PREDICTION_RESEARCH_PROTOCOL.md can be re-run by anyone with the repo and the
scored rows, and give the same answer. FREEZE.json pins all of them.

Plain version: a model is compared with the betting market fight by fight. The
score is how much less surprised the model was by the result than the market
was (log loss). Fights are resampled a whole card at a time to get a range.
The decision is a lookup on that range, never a judgement call.

Amendment 1 (2026-10-13) closed the routes an independent review found round
the v1.0 rules: the caller no longer chooses the fight set, the sample size,
or whether a look is recorded. See the protocol's ## Amendments.

Stdlib + numpy only. No network, no database, no clock of its own.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
import pathlib
import subprocess
from dataclasses import dataclass, field
from statistics import NormalDist
from typing import Callable, Iterable, Sequence

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
PROTOCOL = json.loads((HERE / "protocol.json").read_text())
MANIFEST = json.loads((HERE / "holdout_manifest.json").read_text())
LEDGER_PATH = HERE / "holdout_ledger.json"
REGISTRY_PATH = REPO / "research" / "registry.json"

T = PROTOCOL["thresholds"]
P = PROTOCOL["partitions"]

EPS = T["probability_clip"]
DEV_END = _dt.date.fromisoformat(P["dev"]["end_exclusive"])
H1_START = _dt.date.fromisoformat(P["h1"]["start"])
H1_END = _dt.date.fromisoformat(P["h1"]["end_inclusive"])

STAGES = ("H1", "PROSPECTIVE_INTERIM", "PROSPECTIVE")
CONFIRMATORY = ("H1", "PROSPECTIVE")


# ---------------------------------------------------------------------------
# 1. Partitions and the development guard
# ---------------------------------------------------------------------------

class HoldoutAccessError(RuntimeError):
    """Raised when development code touches a sealed fight."""


class ProtocolViolation(RuntimeError):
    """Raised when a look would break a PRED-001 rule. Nothing is recorded."""


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
    """The sanctioned gate for development data. It refuses rather than
    filters: a loader that silently drops 2025 rows lets a query that ASKED for
    them look fine."""
    out = []
    for r in rows:
        if partition_of(r[date_key]) != "DEV":
            raise HoldoutAccessError(
                f"row dated {r[date_key]} is sealed (dev data ends before "
                f"{DEV_END}). Development code may not read it; only the "
                f"auditor's run_look may, once, through the ledger."
            )
        out.append(r)
    return out


def ids_sha256(fight_ids: Iterable) -> str:
    """The manifest's id fingerprint: ascending integer ids joined by ','."""
    return hashlib.sha256(",".join(str(i) for i in sorted(int(x) for x in fight_ids)).encode()).hexdigest()


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
    card - not the fight - is the unit that is resampled. Cluster ids are
    compared as strings, so 7 and "7" are one card, not two."""
    v = np.asarray(values, dtype=float)
    keys = {}
    idx = np.array([keys.setdefault(str(c), len(keys)) for c in clusters])
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
               power: float, design_effect: float = 1.0,
               mue: float | None = None) -> int:
    """Fights needed so that, if the true gain is `effect`, the PASS rule is
    met with probability `power`.

    The PASS rule has two parts: the one-sided lower bound clears 0 AND the
    point estimate is at least the minimum useful effect. Sizing for the first
    part alone (the v1.0 formula, still returned when mue is None) gives about
    50% power at effect = mue. With mue given, both parts are required:
        n >= sd^2 (z_a + z_b)^2 / effect^2      (lower bound clears 0)
        n >= sd^2 z_b^2 / (effect - mue)^2      (estimate clears mue)
    design_effect >= 1 inflates for clustering and is floored at 1.
    """
    z = NormalDist().inv_cdf
    deff = max(1.0, design_effect)
    n_alpha = deff * ((z(1 - alpha_one_sided) + z(power)) * sd / effect) ** 2
    if mue is None:
        return math.ceil(n_alpha)
    if effect <= mue:
        raise ValueError(f"target effect {effect} must exceed the minimum useful effect {mue}")
    n_mue = deff * (z(power) * sd / (effect - mue)) ** 2
    return math.ceil(max(n_alpha, n_mue))


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
# 6. Registration: what the experiment froze, read from the registry
# ---------------------------------------------------------------------------

def load_registration(experiment_id: str, registry_path: pathlib.Path = None) -> dict:
    """The frozen facts a look is judged against, taken from research/registry.json
    and checked against the bytes on disk. The caller cannot supply them."""
    reg = json.loads((registry_path or REGISTRY_PATH).read_text())
    hits = [e for e in reg.get("experiments", []) if e.get("experiment_id") == experiment_id]
    if len(hits) != 1:
        raise ProtocolViolation(f"{experiment_id} is not registered exactly once in research/registry.json")
    e = hits[0]
    if e.get("protocol") != "PRED-001":
        raise ProtocolViolation(f"{experiment_id} is not a PRED-001 experiment")
    for k in ("preregistration_path", "preregistration_sha256", "model_artifact_sha256",
              "model_class", "target_effect", "sd_used", "n_required"):
        if e.get(k) in (None, ""):
            raise ProtocolViolation(f"{experiment_id} registry entry lacks {k}")
    path = REPO / e["preregistration_path"]
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != e["preregistration_sha256"]:
        raise ProtocolViolation(f"{experiment_id}: preregistration on disk does not match its frozen sha256")
    if e["model_class"] != "incremental":
        raise ProtocolViolation(
            f"{experiment_id}: model_class {e['model_class']!r}. Confirmatory looks score the "
            f"incremental (market + model, weights frozen on DEV) form only - PRED-001 §4.")
    if e["target_effect"] < T["min_target_effect"]:
        raise ProtocolViolation(f"{experiment_id}: target_effect below {T['min_target_effect']}")
    if e["sd_used"] < T["sd_floor_incremental"]:
        raise ProtocolViolation(f"{experiment_id}: sd_used below the floor {T['sd_floor_incremental']}")
    need = required_n(e["sd_used"], e["target_effect"], T["alpha_prospective_per_evaluation"],
                      T["power"], mue=T["minimum_useful_effect"])
    if int(e["n_required"]) < need:
        raise ProtocolViolation(f"{experiment_id}: n_required {e['n_required']} is below the {need} its own target and SD imply")
    return e


# ---------------------------------------------------------------------------
# 7. The decision
# ---------------------------------------------------------------------------

@dataclass
class Evaluation:
    stage: str
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
    market_calib_intercept: float
    market_calib_slope: float
    fight_ids_sha256: str
    verdict: str
    reasons: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def _input_problems(y, p_model, p_market, clusters, fight_ids) -> list[str]:
    out = []
    n = len(y)
    if n == 0:
        return ["no fights supplied"]
    if not (len(p_model) == len(p_market) == len(clusters) == len(fight_ids) == n):
        return ["inputs have different lengths"]
    ya = np.asarray(y, dtype=float)
    if not np.all(np.isin(ya, (0.0, 1.0))):
        out.append("an outcome is not exactly 0 or 1")
    pk = np.asarray(p_market, dtype=float)
    if not np.all(np.isfinite(pk)) or np.any(pk <= 0) or np.any(pk >= 1):
        out.append("a market probability is missing or outside (0, 1)")
    for v in p_model:
        if v is None:
            continue
        f = float(v)
        if not math.isfinite(f) or f < 0 or f > 1:
            out.append("a model probability is outside [0, 1]")
            break
    if len(set(int(i) for i in fight_ids)) != n:
        out.append("a fight id appears twice")
    events = len({str(c) for c in clusters})
    if events < T["min_events_scored"]:
        out.append(f"fewer than {T['min_events_scored']} events scored")
    elif n / events < 2:
        out.append("fewer than two fights per event on average: clusters are not cards")
    return out


def evaluate(y, p_model, p_market, clusters, fight_ids, *, stage: str,
             registration: dict, artifact_sha256: str,
             pit_audit_passed: bool, symmetry_passed: bool) -> Evaluation:
    """Score one frozen model against the market on one eligible fight set.

    The fight set, the sample size and the model's identity are NOT the
    caller's to choose:
      * H1 must be exactly the sealed set in holdout_manifest.json (by hash);
      * a confirmatory PROSPECTIVE look must be exactly n_required fights, the
        number frozen in the registry, not one more or one fewer;
      * the artifact must be the one the registry froze.

    p_model may contain None for fights the model abstained on. Those are
    scored at the market's probability - a zero contribution - so abstaining on
    hard fights cannot improve the result.

    Verdicts, in the order they are checked:
      INVALID           a precondition failed; nothing else is read
      SUSPECT           too good to be honest; frozen pending a written leak audit
      REJECT            no meaningful incremental information (incl. futility)
      UNDERPOWERED      an interim look: never a pass
      FAIL_CALIBRATION  beats the market on average but is mis-calibrated,
                        judged against the market's own calibration
      PASS_H1           historical signal; licenses a prospective test, nothing else
      PASS_PROSPECTIVE  the only verdict that supports a claim of information
                        beyond the market - and still not a profit claim
      INCONCLUSIVE      everything else; a failure for every claim
    """
    if stage not in STAGES:
        raise ValueError(stage)
    reasons = _input_problems(y, p_model, p_market, clusters, fight_ids)
    fid_sha = ids_sha256(fight_ids) if not any("twice" in r for r in reasons) and len(fight_ids) else ""

    if artifact_sha256 != registration.get("model_artifact_sha256"):
        reasons.append("model artifact does not match the one the registry froze")
    if not pit_audit_passed:
        reasons.append("point-in-time audit failed: a feature used information not available before the fight")
    if not symmetry_passed:
        reasons.append("model is not corner-symmetric")
    n = len(y)
    n_req = int(registration.get("n_required") or 0)
    if stage == "H1" and fid_sha != MANIFEST["partitions"]["H1"]["priced_ids_sha256"]:
        reasons.append("the fight set is not the sealed H1 set in holdout_manifest.json")
    if stage == "PROSPECTIVE" and n != n_req:
        reasons.append(f"a confirmatory prospective look scores exactly the first {n_req} eligible locks, not {n}")
    if stage == "PROSPECTIVE_INTERIM" and n >= n_req:
        reasons.append("at or past n_required the look is confirmatory, not interim")

    nan = float("nan")
    if reasons:
        return Evaluation(stage, n, 0, 0.0, nan, nan, nan, nan, nan, nan, nan, nan,
                          nan, nan, nan, nan, fid_sha, "INVALID", reasons)

    y = np.asarray(y, dtype=float)
    pk = _clip(p_market)
    raw = np.array([np.nan if v is None else float(v) for v in p_model])
    covered = ~np.isnan(raw)
    pm = _clip(np.where(covered, raw, pk))

    coverage = float(covered.mean())
    d = log_loss_each(y, pk) - log_loss_each(y, pm)
    delta = float(d.mean())
    alpha = T["alpha_h1_per_evaluation"] if stage == "H1" else T["alpha_prospective_per_evaluation"]
    boots = cluster_bootstrap(d, clusters, T["bootstrap_resamples"], T["bootstrap_seed"])
    lo_conf = float(np.quantile(boots, alpha))
    lo95, hi95 = (float(q) for q in np.quantile(boots, [0.025, 0.975]))
    a, b = calibration_fit(y, pm)
    ak, bk = calibration_fit(y, pk)
    acc_m = float(((pm >= 0.5) == (y == 1)).mean())
    acc_k = float(((pk >= 0.5) == (y == 1)).mean())

    ev = Evaluation(stage, n, int(covered.sum()), coverage, delta, lo_conf, lo95, hi95,
                    float(brier_each(y, pm).mean()), float(brier_each(y, pk).mean()),
                    acc_m, acc_k, a, b, ak, bk, fid_sha, "INCONCLUSIVE", [])
    R = ev.reasons
    mue = T["minimum_useful_effect"]

    if coverage < T["min_coverage"]:
        ev.verdict = "INVALID"
        R.append(f"coverage {coverage:.1%} below {T['min_coverage']:.0%}")
        return ev

    # SUSPECT - leak tripwires, both measured against the market so a
    # favourite-heavy population does not trip them on its own.
    if delta > T["leak_tripwire_delta_ll"]:
        R.append(f"log-loss gain {delta:.4f} exceeds the leak tripwire {T['leak_tripwire_delta_ll']}")
    if acc_m - acc_k > T["leak_tripwire_accuracy_lift"]:
        R.append(f"accuracy {acc_m:.1%} beats the market's {acc_k:.1%} by more than "
                 f"{T['leak_tripwire_accuracy_lift']:.0%}")
    if R:
        ev.verdict = "SUSPECT"
        return ev

    if stage == "PROSPECTIVE_INTERIM":
        if n >= n_req * T["futility_min_fraction"] and hi95 < mue:
            R.append(f"futility: at {n} of {n_req} fights the 95% range tops out at "
                     f"{hi95:.4f}, below the minimum useful effect {mue}")
            ev.verdict = "REJECT"
        else:
            R.append(f"interim look at {n} of {n_req}; no success rule applies before n")
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

    slope_band = max(T["calibration_slope_tolerance"], abs(bk - 1) + T["calibration_relative_margin"])
    int_band = max(T["calibration_intercept_max_abs"], abs(ak) + T["calibration_relative_margin"] / 2)
    if abs(b - 1) > slope_band or abs(a) > int_band:
        R.append(f"calibration intercept {a:.3f} / slope {b:.3f} outside the band "
                 f"(market: {ak:.3f} / {bk:.3f})")
        ev.verdict = "FAIL_CALIBRATION"
        return ev

    if lo_conf > 0 and delta >= mue:
        ev.verdict = "PASS_H1" if stage == "H1" else "PASS_PROSPECTIVE"
        R.append(f"one-sided lower bound {lo_conf:.4f} > 0 at alpha {alpha} and gain {delta:.4f} >= {mue}")
        return ev

    R.append(f"lower bound {lo_conf:.4f} at alpha {alpha} does not clear 0, or gain below {mue}")
    return ev


# ---------------------------------------------------------------------------
# 8. The only sanctioned way to look: evaluate AND record, or neither
# ---------------------------------------------------------------------------

def _entry_hash(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "entry_sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify_ledger_chain(ledger: dict) -> list[str]:
    """Problems with the ledger's hash chain, numbering and budgets. Empty is good."""
    probs = []
    prev = "0" * 64
    for i, e in enumerate(ledger.get("entries", []), 1):
        if e.get("entry") != i:
            probs.append(f"entry {i} is numbered {e.get('entry')}")
        if e.get("prev_entry_sha256") != prev:
            probs.append(f"entry {i} does not chain to the entry before it")
        if e.get("entry_sha256") != _entry_hash(e):
            probs.append(f"entry {i} was edited after it was written")
        prev = e.get("entry_sha256")
    ents = ledger.get("entries", [])
    if sum(e.get("stage") == "H1" for e in ents) > ledger.get("h1_budget", 0):
        probs.append("H1 budget exceeded")
    if sum(e.get("stage") == "PROSPECTIVE" for e in ents) > ledger.get("prospective_budget", 0):
        probs.append("prospective budget exceeded")
    return probs


def _git(*args) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def run_look(*, experiment_id: str, stage: str, y, p_model, p_market, clusters, fight_ids,
             artifact_sha256: str, pit_audit_passed: bool, symmetry_passed: bool,
             auditor: str, evaluated_at: str, ledger_path: pathlib.Path = None,
             registry_path: pathlib.Path = None) -> Evaluation:
    """Evaluate one look and append it to the ledger in the same step.

    Refuses BEFORE computing anything when the look would break a budget or
    repeat a look. Every look that computes is recorded - INVALID, REJECT and
    failures included - so a bad look cannot be quietly retried. The ledger
    entry is hash-chained to the one before it.
    """
    ledger_path = ledger_path or LEDGER_PATH
    ledger = json.loads(ledger_path.read_text())
    probs = verify_ledger_chain(ledger)
    if probs:
        raise ProtocolViolation("ledger is damaged: " + "; ".join(probs))
    reg = load_registration(experiment_id, registry_path)
    ents = ledger["entries"]

    if stage == "H1":
        if sum(e["stage"] == "H1" for e in ents) >= ledger["h1_budget"]:
            raise ProtocolViolation("the H1 budget is spent; H1 is retired")
        if any(e["stage"] == "H1" and e["artifact_sha256"] == artifact_sha256 for e in ents):
            raise ProtocolViolation("this artifact has already had its H1 look")
        if any(e["stage"] == "H1" and e["experiment_id"] == experiment_id for e in ents):
            raise ProtocolViolation("this experiment has already had its H1 look; a successor is a new experiment")
    if stage == "PROSPECTIVE":
        if sum(e["stage"] == "PROSPECTIVE" for e in ents) >= ledger["prospective_budget"]:
            raise ProtocolViolation("the prospective budget is spent")
        if any(e["stage"] == "PROSPECTIVE" and e["experiment_id"] == experiment_id for e in ents):
            raise ProtocolViolation("this experiment has already had its confirmatory look")

    try:
        authors = sorted(set(_git("log", "--format=%ae", "--", reg["preregistration_path"]).split()))
    except Exception:  # noqa: BLE001 - a missing history is recorded, not guessed
        authors = []
    author_sessions = sorted(set(reg.get("author_sessions") or []))
    if auditor in author_sessions or auditor in authors:
        raise ProtocolViolation("the auditor is one of the model's authors")

    ev = evaluate(y, p_model, p_market, clusters, fight_ids, stage=stage, registration=reg,
                  artifact_sha256=artifact_sha256, pit_audit_passed=pit_audit_passed,
                  symmetry_passed=symmetry_passed)

    inputs = {"y": [int(v) for v in y], "p_model": [None if v is None else float(v) for v in p_model],
              "p_market": [float(v) for v in p_market], "clusters": [str(c) for c in clusters],
              "fight_ids": [int(i) for i in fight_ids]}
    try:
        commit = _git("rev-parse", "HEAD")
    except Exception:  # noqa: BLE001
        commit = "unknown"
    entry = {
        "entry": len(ents) + 1,
        "experiment_id": experiment_id,
        "stage": stage,
        "artifact_sha256": artifact_sha256,
        "code_commit": commit,
        "auditor": auditor,
        "author_sessions": author_sessions,
        "author_git_emails": authors,
        "evaluated_at": evaluated_at,
        "n_scored": ev.n_eligible,
        "fight_ids_sha256": ev.fight_ids_sha256,
        "inputs_sha256": hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(),
        "delta_ll": None if math.isnan(ev.delta_ll) else round(ev.delta_ll, 6),
        "verdict": ev.verdict,
        "prev_entry_sha256": ents[-1]["entry_sha256"] if ents else "0" * 64,
    }
    entry["entry_sha256"] = _entry_hash(entry)
    ledger["entries"].append(entry)
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")
    return ev
