"""What the database says about a card, against what UFCStats says today.

Plain English
-------------
Event Flow's retirement rule only works for bookings it has *seen*: a fight has
to appear in a card observation before its absence can mean anything. Every
booking created before the ledger existed is therefore invisible to it — the
ledger is empty, so those rows can never become candidates, and Moicano vs
Ortega on UFC 331 is exactly that case.

This module closes that gap without guessing. It compares the `fights` rows for
an event against the live UFCStats card and reports the differences, with the
evidence for each one. It proposes; it never acts.

It cannot mutate anything, by construction
------------------------------------------
There is no database client here, no HTTP, no file write and no environment
read. Every function takes data the caller already has and returns a value. The
only way this module could change production is if the caller took its output
and wrote it, which is a separate, gated decision.

What it deliberately does NOT do
--------------------------------
It never infers cancellation from "past event with no winner". That signal
conflates real cancellations with ungraded history — 192 rows carry it and the
earliest is from 1995 — so acting on it would retire thirty years of legitimate
fights. Presence on the live card is the only evidence this module uses.

It also does not rank by insert id to break ties. `id DESC` is arrival order,
not truth, and the heuristic that used it was removed from
add_bout_order_migration.sql for that reason.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Finding kinds.
ABSENT_FROM_CARD = "absent_from_card"        # in CFL, not on UFCStats today
MISSING_FROM_DB = "missing_from_db"          # on UFCStats, not in CFL
DUPLICATE_FIGHTER = "duplicate_fighter"      # one fighter, two live bouts
MAIN_EVENT_CONFLICT = "main_event_conflict"  # more than one is_main_event

# Proposed actions. Every one is a proposal; nothing here applies them.
PROPOSE_INACTIVE = "propose_inactive"
PROPOSE_INSERT = "propose_insert"
PROPOSE_REVIEW = "propose_review"
NO_ACTION = "no_action"


@dataclass(frozen=True)
class Finding:
    kind: str
    action: str
    cfl_fight_id: int | None
    ufc_fight_id: str | None
    matchup: str
    reason: str
    evidence: dict = field(default_factory=dict)

    def line(self) -> str:
        who = f"cfl:{self.cfl_fight_id}" if self.cfl_fight_id else f"ufc:{self.ufc_fight_id}"
        return f"[{self.action}] {who}  {self.matchup}\n    {self.reason}"


@dataclass(frozen=True)
class Reconciliation:
    event_id: int
    event_name: str
    page_bout_count: int
    db_fight_count: int
    findings: tuple[Finding, ...]

    @property
    def proposed_inactive(self) -> tuple[int, ...]:
        return tuple(f.cfl_fight_id for f in self.findings
                     if f.action == PROPOSE_INACTIVE and f.cfl_fight_id is not None)

    @property
    def clean(self) -> bool:
        return not self.findings

    def report(self) -> str:
        head = (f"Reconciliation — {self.event_name} [event_id={self.event_id}]\n"
                f"  UFCStats card: {self.page_bout_count} bouts\n"
                f"  CFL fights:    {self.db_fight_count} rows\n"
                f"  findings:      {len(self.findings)}\n"
                f"  READ ONLY. Nothing here has been applied.")
        if not self.findings:
            return head + "\n\n  No differences. Every CFL row is on the card and vice versa."
        return head + "\n\n" + "\n".join(f.line() for f in self.findings)


def reconcile(event: dict, page_bouts: list, db_fights: list[dict]) -> Reconciliation:
    """Compare one event's `fights` rows against its live UFCStats card.

    `page_bouts` are `PageBout`s from `ufcstats_card.parse_event_page`.
    `db_fights` are plain rows: id, ufc_fight_id, fighter_a_id, fighter_b_id,
    fighter_a_name, fighter_b_name, is_main_event (is_active optional).

    Findings come out in a deterministic order — by kind, then by id — so two
    runs over the same inputs produce the same report, byte for byte.
    """
    page_by_id = {b.ufc_fight_id: b for b in page_bouts}
    db_by_ufc = {f["ufc_fight_id"]: f for f in db_fights if f.get("ufc_fight_id")}

    findings: list[Finding] = []

    def name_of(f: dict) -> str:
        return f"{f.get('fighter_a_name')} vs {f.get('fighter_b_name')}"

    # 1. In CFL, absent from the live card. The Moicano vs Ortega case.
    for f in sorted((f for f in db_fights if f.get("ufc_fight_id") not in page_by_id),
                    key=lambda r: r["id"]):
        already_inactive = f.get("is_active") is False
        findings.append(Finding(
            kind=ABSENT_FROM_CARD,
            action=NO_ACTION if already_inactive else PROPOSE_INACTIVE,
            cfl_fight_id=f["id"],
            ufc_fight_id=f.get("ufc_fight_id"),
            matchup=name_of(f),
            reason=("already is_active=false; nothing to do" if already_inactive else
                    "present in CFL, absent from the current UFCStats card. "
                    "Propose is_active=false. The row, its predictions, its "
                    "captured quotes and any snapshot against it are kept."),
            evidence={"on_live_card": False,
                      "ufc_fight_id": f.get("ufc_fight_id"),
                      "is_main_event": f.get("is_main_event"),
                      "current_is_active": f.get("is_active")},
        ))

    # 2. On the card, missing from CFL. The scraper has not caught up.
    for ufc_id in sorted(set(page_by_id) - set(db_by_ufc)):
        bout = page_by_id[ufc_id]
        findings.append(Finding(
            kind=MISSING_FROM_DB, action=PROPOSE_INSERT,
            cfl_fight_id=None, ufc_fight_id=ufc_id, matchup=bout.matchup,
            reason=("on the UFCStats card, no `fights` row. The event scraper "
                    "has not picked it up. Propose insert — not done here."),
            evidence={"page_index": bout.page_index, "on_live_card": True},
        ))

    # 3. A fighter in two bouts that are BOTH on the live card. Two live bouts
    #    for one fighter is a real anomaly; a stale booking beside a live one is
    #    finding 1 and is not double-counted here.
    live = [f for f in db_fights if f.get("ufc_fight_id") in page_by_id]
    seen: dict[int, list[dict]] = {}
    for f in live:
        for fid in (f.get("fighter_a_id"), f.get("fighter_b_id")):
            if fid is not None:
                seen.setdefault(fid, []).append(f)
    for fighter_id, rows in sorted(seen.items()):
        if len(rows) > 1:
            for f in sorted(rows, key=lambda r: r["id"]):
                findings.append(Finding(
                    kind=DUPLICATE_FIGHTER, action=PROPOSE_REVIEW,
                    cfl_fight_id=f["id"], ufc_fight_id=f.get("ufc_fight_id"),
                    matchup=name_of(f),
                    reason=(f"fighter {fighter_id} appears in {len(rows)} bouts "
                            f"that are both on the live card. Needs a person: "
                            f"picking by insert id would be a guess."),
                    evidence={"fighter_id": fighter_id,
                              "fight_ids": sorted(r["id"] for r in rows)},
                ))

    # 4. More than one live main event.
    mains = sorted((f for f in live if f.get("is_main_event")), key=lambda r: r["id"])
    if len(mains) > 1:
        for f in mains:
            findings.append(Finding(
                kind=MAIN_EVENT_CONFLICT, action=PROPOSE_REVIEW,
                cfl_fight_id=f["id"], ufc_fight_id=f.get("ufc_fight_id"),
                matchup=name_of(f),
                reason=(f"{len(mains)} live bouts are flagged is_main_event. The "
                        f"card's top row is the main event; this needs a person."),
                evidence={"claimants": [r["id"] for r in mains]},
            ))

    order = {ABSENT_FROM_CARD: 0, MISSING_FROM_DB: 1,
             DUPLICATE_FIGHTER: 2, MAIN_EVENT_CONFLICT: 3}
    findings.sort(key=lambda f: (order[f.kind], f.cfl_fight_id or 0, f.ufc_fight_id or ""))

    return Reconciliation(
        event_id=event["id"], event_name=event.get("name", ""),
        page_bout_count=len(page_bouts), db_fight_count=len(db_fights),
        findings=tuple(findings),
    )
