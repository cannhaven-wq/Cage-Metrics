"""The spec a DUR-001 historical backfill must satisfy before it may run.

PREREGISTRATION.md §13 is short and absolute:

  > A historical backfill, if ever attempted, must be walk-forward with
  > `training_cutoff < fight_start`, carry a distinct `model_version`, and never
  > be written to `prop_model_locks`.

This module turns that paragraph into checks that run before any work happens.
The tool is *spec-gated*: it refuses to produce a backfill at all until the spec
is satisfied, rather than producing one and leaving the caller to notice.

Why a gate rather than a note in a README: a historical backfill is the single
easiest way to destroy DUR-001. Score the frozen model on fights whose outcomes
are already in its training data and you get a number that looks excellent and
means nothing — and if that number ever reaches `prop_model_locks`, the ledger
stops being a record of what was predicted in advance, which is the only
property it has.

Nothing here reads the database or the Odds API.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Iterable

# The live prospective lock version. A backfill may never reuse it.
LOCKED_MODEL_VERSION = "PROP-0001@v1"

# Tables a backfill may never write to, at any time, for any reason.
FORBIDDEN_TABLES = frozenset({
    "prop_model_locks",     # §13, explicit
    "prop_odds",            # the market ledger; a backfill does not observe prices
    "fight_odds",
    "pre_fight_snapshots",  # the pre-fight record; append-only by trigger
})

# The historical timing rules that are pre-registrable. Amendment item (i) puts
# both to Reed; until one is picked and marked approved, neither is in force.
TIMING_RULES = frozenset({
    "t10_earliest_observed_start",   # candidate 1 — current tool, 0 extra credits
    "self_consistent_walkback",      # candidate 2 — up to 12 extra calls per moved fight
})


@dataclasses.dataclass(frozen=True)
class BackfillRow:
    """One fight a backfill proposes to score."""
    fight_id: int
    fight_start: dt.datetime
    training_cutoff: dt.datetime


@dataclasses.dataclass(frozen=True)
class BackfillSpec:
    """Everything the gate needs to decide whether a run may proceed.

    Fields default to the *refusing* value wherever a default could be unsafe:
    `timing_rule` and `timing_rule_approved` default to unset, so a spec built
    with no arguments is rejected rather than silently permitted.
    """
    model_version: str = ""
    target_table: str = ""
    timing_rule: str | None = None
    timing_rule_approved: bool = False
    writes_to_database: bool = False
    uses_odds_api: bool = False
    rows: tuple[BackfillRow, ...] = ()


@dataclasses.dataclass(frozen=True)
class Violation:
    code: str
    message: str

    def __str__(self) -> str:                      # pragma: no cover - display only
        return f"[{self.code}] {self.message}"


class SpecViolation(RuntimeError):
    """Raised when a backfill is asked to run against a spec it does not satisfy."""

    def __init__(self, violations: Iterable[Violation]):
        self.violations = list(violations)
        body = "\n".join(f"  [{v.code}] {v.message}" for v in self.violations)
        super().__init__(
            f"backfill refused — {len(self.violations)} spec violation(s):\n{body}\n\n"
            f"These come from PREREGISTRATION.md §13. Do not edit this gate to get "
            f"past them; change the backfill, or get the preregistration amended."
        )
