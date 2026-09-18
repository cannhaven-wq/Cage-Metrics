"""Turn a parsed UFCStats card into `fight_bout_order` rows — or refuse to.

Plain English
-------------
UFCStats prints a card with the main event first. The ledger stores the opposite:
`bout_order = 1` is the fight that walks out first, because that is the only bout
whose start time the card's schedule actually names. So the page has to be read
bottom-up, and this module is where that flip happens, once, with a test on it.

    page row 0 (main event)  ->  walkout order N
    page row N-1 (first prelim) -> walkout order 1

Two columns, one name, opposite meanings
----------------------------------------
`fights.bout_order` — proposed in the repo's unapplied `add_bout_order_migration.sql`
— counts 1 = main event. `fight_bout_order.bout_order` counts 1 = first walkout.
They are not interchangeable and nothing here writes the former. If both ever
exist, read the column comment before joining them.

Why it refuses so much
----------------------
A running order is positional. If one bout on the page cannot be linked to a
fight row, every bout below it still gets a number — a wrong one, silently. So a
card links completely or not at all. That is the whole design:

  * every page bout must resolve to exactly one `fights` row, by UFCStats fight
    id and nothing else. No name matching: two fighters can share a name (eight
    pairs do in this database), and a near-miss here misdates a price;
  * every linked fight must already sit on the event we are ingesting;
  * a fight row the page does not list is fine and gets no row. Dead bookings
    stay in `fights` — 36 of them on settled 2026 cards — and the page not
    listing them is exactly the signal that they are dead.

How a reshuffle is recorded
---------------------------
By appending. Never by rewriting, and never by relying on the database to
reject a repeat.

The rule is: read the latest observation for every bout on the card, compare it
to what the page says now, and if **anything** differs, append the **whole card**
as one new observation. If nothing differs, write nothing at all.

That is deliberately not "insert and let a unique index swallow the duplicates",
which is what this module used to do and which had a real hole in it:

    a fight is observed at bout 5, moves to 6, then moves back to 5

Under a unique index on (fight_id, source, bout_order), the third observation is
rejected — a row saying 5 already exists. The ledger is then left holding 5 and
6, with 6 carrying the later `observed_at`, so every downstream reader that
takes the latest observation concludes the fight is at 6. It is at 5. The card
moved back and the ledger could not say so.

**A position the card held before must always be re-recordable.** History
constrains nothing about the future. So there is no uniqueness on
(fight_id, source, bout_order) here, the ingester never sends
`resolution=ignore-duplicates`, and "has this changed?" is answered by reading
the ledger, not by catching a constraint violation.

`fight_bout_order_unique_idx` in the CLV session's migration still declares that
uniqueness. It has to go; see MIGRATION_ADJUSTMENT.md. Until it does, the third
observation of a returning bout is rejected by the database, and the ingester
reports that specific failure rather than continuing.

Why the whole card and not just the bouts that moved
-----------------------------------------------------
Because a running order is one joint fact, not thirteen independent ones. A card
that loses its opener moves every bout on it; a card where two bouts swap moves
two. Appending the complete card on any change means every observation in the
ledger is a self-consistent snapshot that can be read back as "this is what the
card looked like at that moment", and they share one `observed_at` because they
land in one statement. Appending only the movers would leave a snapshot that has
to be assembled per-fight from different instants.

It costs nothing when nothing moves, which is almost always: an unchanged card
writes zero rows.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .ufcstats_card import ParsedCard

SOURCE = "ufcstats_card"


class BoutOrderRefused(Exception):
    """The card could not be linked completely. Nothing is written."""


@dataclass(frozen=True)
class FightRow:
    """The fields of a `fights` row this module needs."""

    id: int
    ufc_fight_id: str
    event_id: int


@dataclass(frozen=True)
class LedgerRow:
    fight_id: int
    event_id: int
    bout_order: int          # 1 = first bout to walk out
    source: str = SOURCE

    def to_payload(self) -> dict:
        # observed_at is deliberately absent: the database default stamps it at
        # insert. A client-supplied observation time is a client-supplied clock.
        return {
            "fight_id": self.fight_id,
            "event_id": self.event_id,
            "bout_order": self.bout_order,
            "source": self.source,
        }


def walkout_order(page_index: int, n_bouts: int) -> int:
    """Page position (0 = main event) -> walkout order (1 = first bout)."""
    if n_bouts < 1:
        raise BoutOrderRefused("a card with no bouts has no running order")
    if not 0 <= page_index < n_bouts:
        raise BoutOrderRefused(
            f"page index {page_index} is outside a card of {n_bouts} bouts"
        )
    return n_bouts - page_index


def card_position(page_index: int) -> int:
    """Page position -> the OTHER convention: 1 = main event.

    Here only so the difference is nameable in code rather than a comment. The
    ledger never stores this.
    """
    return page_index + 1


def build_rows(
    card: ParsedCard,
    fights: list[FightRow],
    event_id: int,
) -> list[LedgerRow]:
    """Link a parsed card to fight rows and return the ledger rows to insert.

    Raises `BoutOrderRefused` unless every bout on the page links to exactly one
    fight row on `event_id`.
    """
    if len(card) == 0:
        raise BoutOrderRefused("the page listed no bouts")

    by_ufc_id: dict[str, list[FightRow]] = {}
    for f in fights:
        by_ufc_id.setdefault(f.ufc_fight_id, []).append(f)

    unlinked: list[str] = []
    wrong_event: list[str] = []
    ambiguous: list[str] = []
    rows: list[LedgerRow] = []
    n = len(card)

    for bout in card.bouts:
        matches = by_ufc_id.get(bout.ufc_fight_id, [])
        if not matches:
            unlinked.append(f"{bout.ufc_fight_id} ({bout.matchup})")
            continue
        if len(matches) > 1:
            ambiguous.append(
                f"{bout.ufc_fight_id} -> fight ids {[m.id for m in matches]}"
            )
            continue
        fight = matches[0]
        if fight.event_id != event_id:
            wrong_event.append(
                f"{bout.ufc_fight_id} is fight {fight.id} on event "
                f"{fight.event_id}, not {event_id}"
            )
            continue
        rows.append(
            LedgerRow(
                fight_id=fight.id,
                event_id=event_id,
                bout_order=walkout_order(bout.page_index, n),
            )
        )

    problems = []
    if unlinked:
        problems.append(
            f"{len(unlinked)} bout(s) on the page have no fight row: "
            + "; ".join(unlinked)
        )
    if ambiguous:
        problems.append(
            f"{len(ambiguous)} UFCStats fight id(s) match more than one fight row: "
            + "; ".join(ambiguous)
        )
    if wrong_event:
        problems.append(
            f"{len(wrong_event)} bout(s) belong to a different event: "
            + "; ".join(wrong_event)
        )
    if problems:
        raise BoutOrderRefused(
            "refusing to write a partial running order for event "
            f"{event_id} — one missing bout renumbers every bout below it. "
            + " | ".join(problems)
        )

    orders = sorted(r.bout_order for r in rows)
    if orders != list(range(1, n + 1)):
        # Unreachable given the checks above; kept because the cost of being
        # wrong here is a mis-numbered card and the cost of the check is nil.
        raise BoutOrderRefused(
            f"built orders {orders} are not 1..{n} — refusing to write"
        )
    return rows


def describe(rows: list[LedgerRow], card: ParsedCard) -> str:
    """One line per bout, first walkout first — what a dry run prints."""
    by_fight = {r.bout_order: r for r in rows}
    n = len(card)
    lines = []
    for bout in sorted(card.bouts, key=lambda b: -b.page_index):
        order = walkout_order(bout.page_index, n)
        row = by_fight.get(order)
        tag = "MAIN EVENT" if bout.page_index == 0 else ""
        lines.append(
            f"  bout {order:>2} of {n}  fight_id={row.fight_id if row else '?':<6} "
            f"{bout.matchup} {tag}".rstrip()
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Reading the ledger back: what do we currently believe, and has it changed?
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Observation:
    """One row as read back out of `fight_bout_order`."""

    id: int
    fight_id: int
    bout_order: int
    observed_at: dt.datetime
    source: str = SOURCE


def latest_state(observations: list[Observation]) -> dict[int, Observation]:
    """The current belief: the newest observation per fight.

    This mirrors, exactly, what `v_clv_close_reference` does in SQL:

        select distinct on (fight_id) ...
        order by fight_id, observed_at desc, id desc

    The `id desc` tiebreak is not decoration. Two observations of one fight can
    share an `observed_at` — `now()` is the transaction's start time, so a
    retried or doubled write lands on the same microsecond — and without a
    deterministic tiebreak the "latest" would be whichever row the planner
    happened to hand over first. Ledger reads have to be reproducible, so the
    tiebreak is part of the rule and is tested.

    Keeping this in Python rather than asking the database means the ingester
    can decide whether anything changed without depending on a view it does not
    own, and the decision is unit-testable with no database at all.
    """
    best: dict[int, Observation] = {}
    for obs in observations:
        current = best.get(obs.fight_id)
        if current is None or (obs.observed_at, obs.id) > (current.observed_at, current.id):
            best[obs.fight_id] = obs
    return best


@dataclass(frozen=True)
class AppendPlan:
    """Whether to append, and the plain-English reason either way."""

    append: bool
    changes: tuple[str, ...]        # one line per bout that moved or is new
    unchanged: int                  # bouts already on record at this position
    stale_fights: tuple[int, ...]   # ordered before, no longer on the page

    @property
    def reason(self) -> str:
        if not self.append:
            return f"no change — all {self.unchanged} bouts already on record at these positions"
        return f"{len(self.changes)} bout(s) differ from the latest observation"


def plan_append(rows: list[LedgerRow], observations: list[Observation]) -> AppendPlan:
    """Compare the card we just read against what the ledger last said.

    Appends the whole card if anything moved, nothing if nothing did. A position
    the card held at some point in the past is **not** a reason to skip: the
    comparison is against the latest observation only, which is what makes
    5 -> 6 -> 5 record correctly.
    """
    latest = latest_state(observations)
    changes: list[str] = []
    unchanged = 0

    for row in sorted(rows, key=lambda r: r.bout_order):
        prior = latest.get(row.fight_id)
        if prior is None:
            changes.append(f"fight {row.fight_id}: not yet observed -> bout {row.bout_order}")
        elif prior.bout_order != row.bout_order:
            changes.append(
                f"fight {row.fight_id}: bout {prior.bout_order} -> {row.bout_order}"
            )
        else:
            unchanged += 1

    on_page = {r.fight_id for r in rows}
    # A bout that was ordered before and is not on the page now. Its last
    # observation stands, because the ledger has no way to say "removed" and
    # inventing one would be a fact we did not observe. Surfaced so the run says
    # it out loud rather than leaving a stale order to be discovered later.
    stale = tuple(sorted(fid for fid in latest if fid not in on_page))

    return AppendPlan(
        append=bool(changes),
        changes=tuple(changes),
        unchanged=unchanged,
        stale_fights=stale,
    )
