"""The gate: every check a DUR-001 backfill must clear before it may run.

    from research.dur001_backfill.gate import check, assert_clear

    violations = check(spec)          # list, empty means clear
    assert_clear(spec)                # raises SpecViolation instead

Each check maps to a line of PREREGISTRATION.md §13 or to a rule the §13
paragraph depends on. The codes are stable so a caller can test for a specific
refusal without string-matching a message.

  LOCK_TABLE          a backfill may never write to prop_model_locks
  FORBIDDEN_TABLE     nor to the other append-only ledgers
  DB_WRITE            a backfill is read-only against the database
  MODEL_VERSION       must carry a distinct, non-empty model_version
  LEAKY_ROW           training_cutoff must be strictly before fight_start
  TIMING_RULE         must name the historical rule frozen by amendment 1.2
  TIMING_REJECTED     and must not name the candidate that amendment rejected
  TIMING_UNAPPROVED   and the spec must assert it is running under that rule
  ODDS_API            a backfill does not spend Odds API credits
  NO_ROWS             a backfill with nothing to score is a no-op, not a run

The LEAKY_ROW check is the one that matters most and the one that is easiest to
get subtly wrong. `training_cutoff < fight_start` must hold **strictly** and
**per row**: a cutoff equal to the start still lets the fight's own result into
the training set on a same-timestamp boundary, and a spec that holds on average
but fails on nine fights is not walk-forward.
"""
from __future__ import annotations

from .spec import (
    FORBIDDEN_TABLES,
    FROZEN_TIMING_RULE,
    LOCKED_MODEL_VERSION,
    REJECTED_TIMING_RULES,
    TIMING_RULES,
    BackfillSpec,
    SpecViolation,
    Violation,
)


def check(spec: BackfillSpec) -> list[Violation]:
    """Every violation in `spec`. Empty list means the backfill may run.

    Returns all violations rather than the first: someone fixing a spec should
    see the whole list, not peel them off one run at a time.
    """
    v: list[Violation] = []

    # ---- §13: never written to prop_model_locks
    target = (spec.target_table or "").strip().lower()
    if target == "prop_model_locks":
        v.append(Violation(
            "LOCK_TABLE",
            "target_table is prop_model_locks. A backfill may never be written to "
            "the lock ledger — that ledger's only property is that every row was "
            "recorded before its fight."))
    elif target in FORBIDDEN_TABLES:
        v.append(Violation(
            "FORBIDDEN_TABLE",
            f"target_table {target!r} is an append-only ledger a backfill may not "
            f"write to."))

    if spec.writes_to_database:
        v.append(Violation(
            "DB_WRITE",
            "writes_to_database is set. A historical backfill is read-only; its "
            "output belongs in a file under research/, not in a table."))

    # ---- §13: carry a distinct model_version
    mv = (spec.model_version or "").strip()
    if not mv:
        v.append(Violation(
            "MODEL_VERSION",
            "model_version is empty. A backfill must carry its own version so its "
            "rows can never be confused with prospective locks."))
    elif mv == LOCKED_MODEL_VERSION:
        v.append(Violation(
            "MODEL_VERSION",
            f"model_version is {mv!r}, the live prospective lock version. A "
            f"backfill must carry a DISTINCT version."))

    # ---- §13: walk-forward with training_cutoff < fight_start
    if not spec.rows:
        v.append(Violation(
            "NO_ROWS",
            "the spec scores no fights. An empty backfill is a no-op; do not run it "
            "to produce an empty artifact that looks like a result."))
    leaky = [r for r in spec.rows if not (r.training_cutoff < r.fight_start)]
    if leaky:
        shown = ", ".join(str(r.fight_id) for r in leaky[:5])
        more = f" (+{len(leaky) - 5} more)" if len(leaky) > 5 else ""
        v.append(Violation(
            "LEAKY_ROW",
            f"{len(leaky)} row(s) have training_cutoff >= fight_start: {shown}{more}. "
            f"Each one would train on the fight it is predicting. The comparison "
            f"must be strict — an equal timestamp is still a leak."))

    # ---- the historical timing rule (frozen by preregistration amendment 1.2)
    if spec.timing_rule is None:
        v.append(Violation(
            "TIMING_RULE",
            f"no historical timing rule set. Preregistration amendment 1.2 freezes "
            f"it to {FROZEN_TIMING_RULE!r}; name it explicitly rather than "
            f"defaulting into it."))
    elif spec.timing_rule in REJECTED_TIMING_RULES:
        v.append(Violation(
            "TIMING_REJECTED",
            f"timing_rule {spec.timing_rule!r} was REJECTED by preregistration "
            f"amendment 1.2 and is not retained as a sensitivity. It excludes "
            f"fights on a capture property, which conditions the cohort on events "
            f"after the sampling decision. Use {FROZEN_TIMING_RULE!r}."))
    elif spec.timing_rule != FROZEN_TIMING_RULE:
        v.append(Violation(
            "TIMING_RULE",
            f"timing_rule {spec.timing_rule!r} is not the frozen rule. Amendment "
            f"1.2 permits exactly one: {FROZEN_TIMING_RULE!r}."))
    elif not spec.timing_rule_approved:
        v.append(Violation(
            "TIMING_UNAPPROVED",
            f"timing_rule {spec.timing_rule!r} is the frozen rule but the spec does "
            f"not assert approval. Set timing_rule_approved once you have confirmed "
            f"you are running under amendment 1.2, not re-deciding it."))

    # ---- credits
    if spec.uses_odds_api:
        v.append(Violation(
            "ODDS_API",
            "uses_odds_api is set. A backfill runs off stored snapshots; it does not "
            "spend live credits."))

    return v


def assert_clear(spec: BackfillSpec) -> None:
    """Raise SpecViolation unless the spec clears every gate."""
    violations = check(spec)
    if violations:
        raise SpecViolation(violations)


def is_clear(spec: BackfillSpec) -> bool:
    return not check(spec)


def explain(spec: BackfillSpec) -> str:
    """Human-readable gate report, for the CLI and for a refusal message."""
    violations = check(spec)
    if not violations:
        return ("GATE CLEAR — every PREREGISTRATION.md §13 condition is satisfied.\n"
                f"  model_version : {spec.model_version}\n"
                f"  timing_rule   : {spec.timing_rule} (approved)\n"
                f"  rows          : {len(spec.rows)}\n")
    lines = [f"GATE REFUSED — {len(violations)} violation(s):"]
    lines += [f"  [{x.code}] {x.message}" for x in violations]
    lines.append("")
    lines.append("Fix the backfill, or amend the preregistration. Do not edit the gate.")
    return "\n".join(lines)
