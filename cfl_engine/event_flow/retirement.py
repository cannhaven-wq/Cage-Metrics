"""When a booking has actually left the card — and when it only looks like it.

Plain English
-------------
A fight is announced, we store it, a fighter withdraws, and the bout disappears
from the UFCStats card. The row has to stop counting as part of the current card
without being deleted, because picks and captured prices reference it.

The hard part is not noticing the absence. It is being sure the absence is real.
A fight missing from one page read might have been withdrawn — or the page might
have been half-built when we read it, or truncated in transit. Retiring a live
booking because of a bad read is worse than being slow, because the retraction
costs the card a bout and renumbers everything below it.

So this module never decides from one observation.

The rule
--------
A booking is CONFIRMED retired when both hold:

  1. it appears in at least one earlier complete card observation, and
  2. it is absent from the latest `REQUIRED_CONFIRMATIONS` complete card
     observations, consecutively.

Nothing else. No time window, no fighter-name matching, no "past event with no
winner", no row-number tiebreak. The rule is a function of the ledger and
nothing else, so two callers reading the same ledger always agree.

Why two observations, and not one or five
-----------------------------------------
One is not enough: a single bad parse would retire a live booking, and that is
the failure this exists to prevent.

Three or more is not free: every extra confirmation is another scrape interval
(twice daily, as proposed) during which the card count is wrong in the other
direction — a withdrawn bout still occupying a slot. Two is the smallest number
that cannot be tripped by a single bad read, which makes it the smallest
deterministic rule that is actually safe.

The layer beneath this one
--------------------------
This module is the SECOND line of defence, not the first. `ingest_bout_order.py`
already refuses to append a card it could not link completely — it exits 3
(`EXIT_REFUSED`) rather than record a partial card. So a broken scrape does not
usually become an observation at all; it produces no row, and the sequence this
module reads is unchanged.

That matters for the arithmetic: a failed scrape does not count as a
confirmation, because it never becomes an observation. Absence has to be
observed, twice, on cards we actually read.

What this module does NOT do
----------------------------
It writes nothing. It returns a verdict. Applying that verdict — setting
`fights.is_active = false`, with the observation that justified it — is a
separate step that does not exist yet, and deliberately: the column is not on the
table today.
"""
from __future__ import annotations

from dataclasses import dataclass

# Two: the smallest number that a single bad read cannot trip. See the module
# docstring for why this is not one and not five.
REQUIRED_CONFIRMATIONS = 2

# Verdicts.
NOT_A_CANDIDATE = "not_a_candidate"   # never observed on this card at all
ON_CARD = "on_card"                   # present in the latest observation
PENDING = "pending"                   # absent, but not yet confirmed
CONFIRMED = "confirmed"               # absent from the latest N observations


@dataclass(frozen=True)
class CardObservation:
    """One complete card, as appended in a single statement.

    Event Flow appends the WHOLE card at once and every row of that append shares
    one `observed_at`, so an observation is a set of fight ids at an instant —
    not a row per fight.
    """

    observed_at: str
    fight_ids: frozenset[int]


@dataclass(frozen=True)
class Verdict:
    state: str
    confirmations: int          # consecutive latest observations lacking it
    required: int
    observations_seen: int
    reason: str

    @property
    def should_retire(self) -> bool:
        return self.state == CONFIRMED


def card_observations(rows: list[dict]) -> list[CardObservation]:
    """Ledger rows -> complete card observations, NEWEST FIRST.

    Groups by `observed_at` because that is what makes an append one card. Rows
    arriving in any order produce the same grouping, so the caller's query plan
    cannot change the answer.
    """
    by_instant: dict[str, set[int]] = {}
    for r in rows:
        by_instant.setdefault(r["observed_at"], set()).add(r["fight_id"])
    return [
        CardObservation(observed_at=at, fight_ids=frozenset(ids))
        for at, ids in sorted(by_instant.items(), key=lambda kv: kv[0], reverse=True)
    ]


def verdict_for(rows: list[dict], fight_id: int,
                required: int = REQUIRED_CONFIRMATIONS) -> Verdict:
    """Has `fight_id` left the card, confirmed to `required` observations?"""
    observations = card_observations(rows)
    seen = len(observations)

    if not any(fight_id in o.fight_ids for o in observations):
        # Never on a card we read. A bout announced but not yet scraped, or one
        # belonging to another event. Absence proves nothing about it.
        return Verdict(NOT_A_CANDIDATE, 0, required, seen,
                       "never observed on this card; absence is not evidence")

    if fight_id in observations[0].fight_ids:
        return Verdict(ON_CARD, 0, required, seen,
                       "present in the latest complete card observation")

    # Count consecutive latest observations that lack it.
    missing = 0
    for o in observations:
        if fight_id in o.fight_ids:
            break
        missing += 1

    if seen < required:
        # One observation can never retire anything, however it reads.
        return Verdict(PENDING, missing, required, seen,
                       f"only {seen} observation(s) on record; {required} needed "
                       f"before an absence can be confirmed")

    if missing >= required:
        return Verdict(CONFIRMED, missing, required, seen,
                       f"absent from the latest {missing} complete card "
                       f"observations, consecutively")

    return Verdict(PENDING, missing, required, seen,
                   f"absent from the latest {missing} observation(s); "
                   f"{required} needed. A single bad read looks exactly like this")


# ---------------------------------------------------------------------------
# Turning verdicts into a plan
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RetirementPlan:
    """What the current card implies about `fights.is_active`.

    `awaiting_confirmation` is the load-bearing one, and it exists because of a
    property of `plan_append` that is easy to miss: a stale fight produces no
    change entry, because the comparison loop walks the PAGE's bouts. So once
    the remaining bouts settle at their new positions, nothing differs, nothing
    is appended, and a first absence would sit at one confirmation for ever —
    the rule could never reach two and no booking would ever retire.

    When a retirement is pending, the card is therefore re-observed on purpose.
    That is an honest append: we did read the card again, at a new instant, and
    it said the same thing. It is bounded — one extra observation per pending
    retirement, and once confirmed the reason to append goes away.
    """

    deactivate: tuple[int, ...]
    reactivate: tuple[int, ...]
    pending: tuple[tuple[int, int], ...]     # (fight_id, consecutive absences)
    awaiting_confirmation: bool

    @property
    def is_empty(self) -> bool:
        return not (self.deactivate or self.reactivate or self.pending)


def plan_retirements(
    ledger_rows: list[dict],
    on_page_fight_ids: set[int],
    active_by_fight: dict[int, bool | None] | None = None,
    required: int = REQUIRED_CONFIRMATIONS,
) -> RetirementPlan:
    """Decide which bookings to retire, which to bring back, which to wait on.

    `active_by_fight` maps fight id -> current `is_active`. A missing entry or
    None means unknown — which is the state before the column exists — and is
    treated as active, so the plan reports what it WOULD do rather than going
    quiet.
    """
    active_by_fight = active_by_fight or {}
    observations = card_observations(ledger_rows)
    ever_observed = {fid for o in observations for fid in o.fight_ids}

    deactivate: list[int] = []
    pending: list[tuple[int, int]] = []

    for fid in sorted(ever_observed - on_page_fight_ids):
        v = verdict_for(ledger_rows, fid, required=required)
        if v.state == CONFIRMED:
            if active_by_fight.get(fid) is not False:   # already inactive -> nothing to do
                deactivate.append(fid)
        elif v.state == PENDING and v.confirmations >= 1:
            pending.append((fid, v.confirmations))

    # A booking that was retired and is on the card again. The card is the
    # authority on what is current, in both directions — retiring is not a
    # one-way door, and a reinstated bout must come back rather than need a
    # human to notice.
    reactivate = sorted(
        fid for fid in on_page_fight_ids if active_by_fight.get(fid) is False
    )

    return RetirementPlan(
        deactivate=tuple(deactivate),
        reactivate=tuple(reactivate),
        pending=tuple(pending),
        awaiting_confirmation=bool(pending),
    )
