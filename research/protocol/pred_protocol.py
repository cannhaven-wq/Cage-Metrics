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
import re
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
# 6. Registration: what the experiment froze, read from its preregistration
# ---------------------------------------------------------------------------

REG_FIELDS = ("experiment_id", "model_artifact_sha256", "model_class", "target_effect",
              "sd_used", "n_required", "author_sessions")
_REG_BLOCK = re.compile(r"```pred-registration\s*\n(.*?)\n```", re.S)


def _registration_block(text: str) -> dict:
    m = _REG_BLOCK.search(text)
    if not m:
        raise ProtocolViolation("the preregistration has no ```pred-registration``` block")
    return json.loads(m.group(1))


def load_registration(experiment_id: str, registry_path: pathlib.Path = None) -> dict:
    """The frozen facts a look is judged against.

    They are read from the ```pred-registration``` block INSIDE the hashed
    preregistration file, and the registry entry must repeat them exactly. So
    editing n_required or the artifact hash after a look means editing a
    frozen file, which changes its hash, which the registry and a test against
    main both record. The caller supplies none of it.
    """
    reg = json.loads((registry_path or REGISTRY_PATH).read_text())
    hits = [e for e in reg.get("experiments", []) if e.get("experiment_id") == experiment_id]
    if len(hits) != 1:
        raise ProtocolViolation(f"{experiment_id} is not registered exactly once in research/registry.json")
    e = hits[0]
    if e.get("protocol") != "PRED-001":
        raise ProtocolViolation(f"{experiment_id} is not a PRED-001 experiment")
    for k in ("preregistration_path", "preregistration_sha256"):
        if not e.get(k):
            raise ProtocolViolation(f"{experiment_id} registry entry lacks {k}")
    path = REPO / e["preregistration_path"]
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != e["preregistration_sha256"]:
        raise ProtocolViolation(f"{experiment_id}: preregistration on disk does not match its frozen sha256")
    block = _registration_block(path.read_text())
    for k in REG_FIELDS:
        if k not in block:
            raise ProtocolViolation(f"{experiment_id}: pred-registration block lacks {k}")
        if e.get(k) != block[k]:
            raise ProtocolViolation(f"{experiment_id}: registry {k} disagrees with the frozen preregistration")
    if block["experiment_id"] != experiment_id:
        raise ProtocolViolation("the preregistration names a different experiment")
    if not re.fullmatch(r"[0-9a-f]{64}", str(block["model_artifact_sha256"])):
        raise ProtocolViolation(f"{experiment_id}: model_artifact_sha256 is not a sha256")
    if block["model_class"] != "incremental":
        raise ProtocolViolation(
            f"{experiment_id}: model_class {block['model_class']!r}. Confirmatory looks score the "
            f"incremental (market + model, weights frozen on DEV) form only - PRED-001 §4.")
    if not (T["min_target_effect"] <= block["target_effect"] <= T["leak_tripwire_delta_ll"]):
        raise ProtocolViolation(
            f"{experiment_id}: target_effect must lie in [{T['min_target_effect']}, "
            f"{T['leak_tripwire_delta_ll']}]; above the leak tripwire a pass would read as a leak")
    if block["sd_used"] < T["sd_floor_incremental"]:
        raise ProtocolViolation(f"{experiment_id}: sd_used below the floor {T['sd_floor_incremental']}")
    need = required_n(block["sd_used"], block["target_effect"], T["alpha_prospective_per_evaluation"],
                      T["power"], mue=T["minimum_useful_effect"])
    if int(block["n_required"]) < need:
        raise ProtocolViolation(f"{experiment_id}: n_required {block['n_required']} is below the {need} its own target and SD imply")
    if not block["author_sessions"]:
        raise ProtocolViolation(f"{experiment_id}: author_sessions is empty; the auditor check needs it")
    return dict(e)


# ---------------------------------------------------------------------------
# 7. The decision rule (pure) and the look (provenance-checked)
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


def _invalid(stage, n, fid_sha, reasons) -> Evaluation:
    nan = float("nan")
    return Evaluation(stage, n, 0, 0.0, nan, nan, nan, nan, nan, nan, nan, nan,
                      nan, nan, nan, nan, fid_sha, "INVALID", list(reasons))


def _input_problems(y, p_model, p_market, clusters) -> list[str]:
    out = []
    n = len(y)
    if n == 0:
        return ["no fights supplied"]
    if not (len(p_model) == len(p_market) == len(clusters) == n):
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
    events = len({str(c) for c in clusters})
    if events < T["min_events_scored"]:
        out.append(f"fewer than {T['min_events_scored']} events scored")
    elif n / events < 2:
        out.append("fewer than two fights per event on average: clusters are not cards")
    return out


def decide(y, p_model, p_market, clusters, *, stage: str, n_required: int = 0,
           fight_ids_sha256: str = "") -> Evaluation:
    """The decision rule alone, on arrays. PURE AND UNCHECKED: it trusts its
    inputs. It is exposed so the rule itself can be tested in synthetic worlds.
    Nothing it returns is a look; only an entry run_look writes to the ledger
    on main counts.

    Verdicts, in the order they are checked:
      INVALID           an input or precondition failed; nothing else is read
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
    n = len(y)
    probs = _input_problems(y, p_model, p_market, clusters)
    if probs:
        return _invalid(stage, n, fight_ids_sha256, probs)

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
                    acc_m, acc_k, a, b, ak, bk, fight_ids_sha256, "INCONCLUSIVE", [])
    R = ev.reasons
    mue = T["minimum_useful_effect"]

    if coverage < T["min_coverage"]:
        ev.verdict = "INVALID"
        R.append(f"coverage {coverage:.1%} below {T['min_coverage']:.0%}")
        return ev

    if delta > T["leak_tripwire_delta_ll"]:
        R.append(f"log-loss gain {delta:.4f} exceeds the leak tripwire {T['leak_tripwire_delta_ll']}")
    if acc_m - acc_k > T["leak_tripwire_accuracy_lift"]:
        R.append(f"accuracy {acc_m:.1%} beats the market's {acc_k:.1%} by more than "
                 f"{T['leak_tripwire_accuracy_lift']:.0%}")
    if R:
        ev.verdict = "SUSPECT"
        return ev

    if stage == "PROSPECTIVE_INTERIM":
        if n >= n_required * T["futility_min_fraction"] and hi95 < mue:
            R.append(f"futility: at {n} of {n_required} fights the 95% range tops out at "
                     f"{hi95:.4f}, below the minimum useful effect {mue}")
            ev.verdict = "REJECT"
        else:
            R.append(f"interim look at {n} of {n_required}; no success rule applies before n")
            ev.verdict = "UNDERPOWERED"
        return ev

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


def _sha(parts: Iterable[str]) -> str:
    return hashlib.sha256(",".join(parts).encode()).hexdigest()


def _is_int(v) -> bool:
    return type(v) is int  # bool, float, str and numpy types are refused, not coerced


def _h1_inputs(rows: list[dict]):
    """H1 rows carry raw facts, not derived numbers: fight id, event id, the
    outcome, the two BFO closing American prices, the model probability. Every
    fact must be a plain int and is checked against the manifest's
    fingerprints; the SAME parsed ints are what is then scored and clustered,
    and the market probability is de-vigged here. Round 3 of the review showed
    why both halves matter: hashing int(x) while scoring x let 1000.1 / 1000.2
    split a card and +/-0.99 on a price move the result."""
    keys = ("fight_id", "event_id", "y", "american_a", "american_b")
    for r in rows:
        if not isinstance(r, dict) or any(not _is_int(r.get(k)) for k in keys) or "p_model" not in r:
            return None, ["H1 rows need plain-int fight_id, event_id, y, american_a, american_b, and a p_model"]
    rs = sorted(rows, key=lambda r: r["fight_id"])
    h1 = MANIFEST["partitions"]["H1"]
    checks = {
        "fight set": (_sha(str(r["fight_id"]) for r in rs), h1["priced_ids_sha256"]),
        "benchmark prices": (_sha(f"{r['fight_id']}:{r['american_a']}:{r['american_b']}" for r in rs),
                             h1["priced_prices_sha256"]),
        "outcomes": (_sha(f"{r['fight_id']}:{r['y']}" for r in rs), h1["priced_outcomes_sha256"]),
        "card assignment": (_sha(f"{r['fight_id']}:{r['event_id']}" for r in rs), h1["priced_events_sha256"]),
    }
    probs = [f"the H1 {name} does not match holdout_manifest.json" for name, (got, want) in checks.items() if got != want]
    if probs:
        return None, probs
    y = [r["y"] for r in rs]
    pk = [devig_proportional(r["american_a"], r["american_b"]) for r in rs]
    pm = [r["p_model"] for r in rs]
    cl = [str(r["event_id"]) for r in rs]
    return (y, pm, pk, cl, checks["fight set"][0]), []


def _ts(v) -> _dt.datetime:
    """A timestamp, parsed. Comparing them as text reorders 'T' against ' ' and
    'Z' against '+00'. A naive timestamp is refused rather than assumed UTC."""
    t = _dt.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("timestamp without a time zone")
    return t


def _prospective_inputs(rows: list[dict], reg: dict, stage: str, card_population: dict | None):
    """Prospective rows are the experiment's rows of v_win_model_locks_graded.
    The scored set is derived here, never chosen by the caller:

    * Cards, not fights, are the unit. Cards are taken whole, in start order,
      from the experiment's first locked card. A confirmatory look takes cards
      until the eligible locks (graded, corners unchanged) reach n_required -
      so n is at least n_required and no card is ever cut in half.
    * Every priced card in that run must be covered: at least min_coverage of
      its priced bouts carry a lock. Coverage counts ALL locks, including bouts
      that later went to a draw or no contest, so an honest card is never
      failed by its result. A card with no locks at all - dropped, or rolled
      back after the fights - fails it. That is what stops cherry-picking
      cards, in the code or in the database.

    card_population maps event_id -> {"start": ISO timestamp, "priced": [fight
    ids with a two-sided market before the start]}, produced by the committed
    recipe research/protocol/card_population.sql; its hash is recorded with the
    look so a third party can re-derive it.
    """
    n_req = int(reg["n_required"])
    if not card_population:
        return None, ["card_population is required (research/protocol/card_population.sql)"]
    try:
        cards = sorted(((str(k), _ts(v["start"]), {int(x) for x in v["priced"]}) for k, v in card_population.items()),
                       key=lambda c: (c[1], c[0]))
        for r in rows:
            if r.get("experiment_id") != reg["experiment_id"] or r.get("artifact_sha256") != reg["model_artifact_sha256"]:
                return None, ["a lock row belongs to another experiment or another artifact"]
            _ts(r["actual_lock_at"]); int(r["lock_id"]); int(r["fight_id"])
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        return None, [f"malformed lock rows or card_population: {e}"]
    if len({int(r["fight_id"]) for r in rows}) != len(rows):
        return None, ["a fight is locked twice under one experiment"]
    if not rows:
        return None, ["no locks"]

    by_card = {}
    for r in rows:
        by_card.setdefault(str(r["event_id"]), []).append(r)
    # Locks on a card the population does not list yet are the next card,
    # written the night before: set aside while every one of them is still
    # ungraded. A GRADED lock on an unlisted card means the population is
    # wrong, and that is INVALID.
    known = {c[0] for c in cards}
    for ev_id in sorted(set(by_card) - known):
        if any(r.get("y_a") in (0, 1) for r in by_card[ev_id]):
            return None, [f"graded locks on card {ev_id}, which card_population does not list"]
        del by_card[ev_id]
    if not by_card:
        return None, ["no locks on any card in card_population"]
    locked_idx = [i for i, c in enumerate(cards) if c[0] in by_card]
    first, last = locked_idx[0], locked_idx[-1]

    eligible_of = lambda rs: [r for r in rs if r.get("y_a") in (0, 1) and r.get("corners_unchanged") is True
                              and r.get("market_p_a_vigfree") is not None]
    # Coverage, two layers (round 4): pooled over the run, at least min_coverage
    # of priced bouts carry a lock; and on EVERY card in the run at most
    # max(1, 5%) priced bouts may be missing. A single late replacement or a
    # debutant the model cannot price does not void an honest card; a card
    # with no locks - dropped, or rolled back after the fights - always fails.
    scored, total, pooled_locked, pooled_priced = [], 0, 0, 0
    for ev_id, _start, priced in cards[first:last + 1]:
        if stage == "PROSPECTIVE" and total >= n_req:
            break
        locked = {int(r["fight_id"]) for r in by_card.get(ev_id, [])}
        covered = len(locked & priced)
        allowed_missing = max(1, math.floor(len(priced) * (1 - T["min_coverage"])))
        if not priced or not locked or len(priced) - covered > allowed_missing:
            return None, [f"card {ev_id}: locks cover {covered} of {len(priced)} priced bouts; every priced "
                          f"card in the run must be covered (at most {allowed_missing} missing) - "
                          f"skipping cards is not allowed"]
        pooled_locked += covered
        pooled_priced += len(priced)
        elig = eligible_of(by_card.get(ev_id, []))
        scored.extend(elig)
        total += len(elig)
    if pooled_priced and pooled_locked / pooled_priced < T["min_coverage"]:
        return None, [f"locks cover {pooled_locked} of {pooled_priced} priced bouts across the run, "
                      f"below {T['min_coverage']:.0%}"]
    if stage == "PROSPECTIVE" and total < n_req:
        return None, [f"only {total} eligible locks on whole cards; the confirmatory look needs {n_req}"]
    if stage == "PROSPECTIVE_INTERIM" and total >= n_req:
        return None, ["at or past n_required the look is confirmatory, not interim"]
    try:
        y = [int(r["y_a"]) for r in scored]
        pm = [float(r["p_a"]) for r in scored]
        pk = [float(r["market_p_a_vigfree"]) for r in scored]
    except (KeyError, TypeError, ValueError) as e:
        return None, [f"malformed lock rows: {e}"]
    cl = [str(r["event_id"]) for r in scored]
    pop_sha = hashlib.sha256(json.dumps({k: {"start": str(v["start"]), "priced": sorted(int(x) for x in v["priced"])}
                                         for k, v in card_population.items()}, sort_keys=True).encode()).hexdigest()
    fid = _sha([_sha(str(int(r["lock_id"])) for r in sorted(scored, key=lambda r: int(r["lock_id"]))), pop_sha])
    return (y, pm, pk, cl, fid), []


def evaluate(rows: list[dict], *, stage: str, experiment_id: str, artifact_sha256: str,
             pit_audit_passed: bool, symmetry_passed: bool,
             registry_path: pathlib.Path = None, card_population: dict | None = None) -> Evaluation:
    """One look's verdict, with its inputs checked rather than trusted.

    The registration is loaded from the frozen preregistration; H1 facts are
    checked against the manifest fingerprints; prospective inputs are derived
    from the lock rows. Still not a look on its own - see run_look.
    """
    if stage not in STAGES:
        raise ValueError(stage)
    reg = load_registration(experiment_id, registry_path)
    pre = []
    if artifact_sha256 != reg["model_artifact_sha256"]:
        pre.append("model artifact does not match the one the preregistration froze")
    if not pit_audit_passed:
        pre.append("point-in-time audit failed: a feature used information not available before the fight")
    if not symmetry_passed:
        pre.append("model is not corner-symmetric")
    if stage == "H1":
        got, probs = _h1_inputs(rows)
    else:
        got, probs = _prospective_inputs(rows, reg, stage, card_population)
    pre += probs
    if pre:
        return _invalid(stage, len(rows), got[4] if got else "", pre)
    y, pm, pk, cl, fid = got
    return decide(y, pm, pk, cl, stage=stage, n_required=int(reg["n_required"]), fight_ids_sha256=fid)


# ---------------------------------------------------------------------------
# 8. The only look that counts: evaluate AND record, or neither
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


AUDITOR_ID = re.compile(r"session_[A-Za-z0-9]{8,}")


def run_look(*, experiment_id: str, stage: str, rows: list[dict], artifact_sha256: str,
             pit_audit_passed: bool, symmetry_passed: bool, auditor: str, evaluated_at: str,
             card_population: dict | None = None,
             _ledger_path: pathlib.Path = None, _registry_path: pathlib.Path = None,
             _authors_from_git: bool = True) -> Evaluation:
    """Evaluate one look and append it to the ledger in the same step.

    Refuses BEFORE computing anything when the look would break a budget,
    repeat a look, or be run by one of the model's authors. Every look that
    computes is recorded - INVALID, REJECT and crashes included. The entry is
    hash-chained to the one before it.

    THE TRUST MODEL, stated once: a look COUNTS only when its entry is
    committed to the ledger on main. The underscore arguments exist for the
    test sandbox; a look recorded anywhere else is not a look, and a person
    with database access can always compute a log loss on H1 by hand. That is
    why no claim rests on H1 (PRED-001 §9): prospective outcomes do not exist
    when the lock is written, and no code path can leak them.
    """
    if not AUDITOR_ID.fullmatch(auditor or ""):
        raise ProtocolViolation("auditor must be a Claude session id (session_...) so it can be checked")
    ledger_path = _ledger_path or LEDGER_PATH
    ledger = json.loads(ledger_path.read_text())
    probs = verify_ledger_chain(ledger)
    if probs:
        raise ProtocolViolation("ledger is damaged: " + "; ".join(probs))
    reg = load_registration(experiment_id, _registry_path)
    ents = ledger["entries"]

    if stage == "H1":
        if sum(e["stage"] == "H1" for e in ents) >= ledger["h1_budget"]:
            raise ProtocolViolation("the H1 budget is spent; H1 is retired")
        if any(e["stage"] == "H1" and (e["experiment_id"] == experiment_id
                                       or e["artifact_sha256"] == artifact_sha256) for e in ents):
            raise ProtocolViolation("this experiment or artifact has already had its H1 look; a successor is a new experiment")
    if stage == "PROSPECTIVE":
        if sum(e["stage"] == "PROSPECTIVE" for e in ents) >= ledger["prospective_budget"]:
            raise ProtocolViolation("the prospective budget is spent")
        if any(e["stage"] == "PROSPECTIVE" and e["experiment_id"] == experiment_id for e in ents):
            raise ProtocolViolation("this experiment has already had its confirmatory look")

    # Authorship from the repository itself, not from what the author declared:
    # every commit that touched the experiment's folder carries a
    # Claude-Session trailer, and the auditor's session must not be among them.
    git_sessions = []
    if _authors_from_git:
        exp_dir = str(pathlib.Path(reg["preregistration_path"]).parent)
        # The experiment folder plus any model code the frozen block names
        # (e.g. a feature builder under cfl_engine/).
        paths = [exp_dir] + [str(x) for x in (_registration_block((REPO / reg["preregistration_path"]).read_text())
                                              .get("code_paths") or [])]
        log = _git("log", "--format=%(trailers:key=Claude-Session,valueonly)%n%ae", "--", *paths)
        if not log.strip():
            raise ProtocolViolation("no git history for the experiment folder; commit it before any look")
        git_sessions = sorted(set(re.findall(r"session_[A-Za-z0-9]+", log)))
    author_sessions = sorted(set(reg["author_sessions"]) | set(git_sessions))
    if auditor in author_sessions:
        raise ProtocolViolation("the auditor is one of the model's authors")

    try:
        ev = evaluate(rows, stage=stage, experiment_id=experiment_id, artifact_sha256=artifact_sha256,
                      pit_audit_passed=pit_audit_passed, symmetry_passed=symmetry_passed,
                      registry_path=_registry_path, card_population=card_population)
    except Exception as exc:  # noqa: BLE001 - a crash is recorded, not retried quietly
        ev = _invalid(stage, len(rows), "", [f"evaluation raised {type(exc).__name__}: {exc}"])

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
        "author_sessions_from_git": git_sessions,
        "evaluated_at": evaluated_at,
        "n_scored": ev.n_eligible,
        "fight_ids_sha256": ev.fight_ids_sha256,
        "inputs_sha256": hashlib.sha256(json.dumps({"rows": rows, "card_population": card_population},
                                                   sort_keys=True, default=str).encode()).hexdigest(),
        "delta_ll": None if math.isnan(ev.delta_ll) else round(ev.delta_ll, 6),
        "verdict": ev.verdict,
        "prev_entry_sha256": ents[-1]["entry_sha256"] if ents else "0" * 64,
    }
    entry["entry_sha256"] = _entry_hash(entry)
    ledger["entries"].append(entry)
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")
    return ev
