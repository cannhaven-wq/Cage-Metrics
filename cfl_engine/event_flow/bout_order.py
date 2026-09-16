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

Reshuffles append, they never rewrite. The ledger's unique index is
(fight_id, source, bout_order): re-observing the same order is a no-op, a moved
bout appends a new observation, and the latest one wins downstream.
"""
from __future__ import annotations

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
