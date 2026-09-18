"""Tests for the UFCStats running-order ingestion path.

    python -m unittest cfl_engine.event_flow.test_event_flow -v

Three things are actually load-bearing here and each has a test that bites:

  1. the page is read bottom-up — the main event is the LAST walkout, not the
     first. Getting this backwards silently inverts every card;
  2. a card that cannot be linked completely writes nothing;
  3. linkage is by UFCStats fight id only, never by fighter name.
"""
from __future__ import annotations

import datetime as dt
import io
import re
import unittest
from pathlib import Path

from cfl_engine.event_flow.bout_order import (
    SOURCE,
    BoutOrderRefused,
    FightRow,
    LedgerRow,
    Observation,
    build_rows,
    card_position,
    latest_state,
    plan_append,
    walkout_order,
)
from cfl_engine.event_flow.ufcstats_card import CardParseError, parse_event_page

FIXTURE = Path(__file__).parent / "fixtures" / "ufcstats_event_page.html"
FIXTURE_EVENT_ID = "6d066a2d94981620"
MAIN_EVENT_FIGHT = "15a2ed7bcb852da7"
FIRST_PRELIM_FIGHT = "0f95cb45ff6c4db0"
CFL_EVENT_ID = 4433


def load_card():
    return parse_event_page(FIXTURE.read_text(encoding="utf-8"))


def fights_for(card, event_id=CFL_EVENT_ID, start_id=900):
    """One `fights` row per page bout, in an order deliberately unrelated to the
    page order — an id sort must not be able to reproduce the answer."""
    shuffled = sorted(card.bouts, key=lambda b: b.ufc_fight_id)
    return [
        FightRow(id=start_id + i, ufc_fight_id=b.ufc_fight_id, event_id=event_id)
        for i, b in enumerate(shuffled)
    ]


class TestParser(unittest.TestCase):
    def test_reads_every_bout_in_page_order(self):
        card = load_card()
        self.assertEqual(len(card), 13)
        self.assertEqual(card.ufc_event_id, FIXTURE_EVENT_ID)
        self.assertEqual(card.bouts[0].ufc_fight_id, MAIN_EVENT_FIGHT)
        self.assertEqual(card.bouts[-1].ufc_fight_id, FIRST_PRELIM_FIGHT)
        self.assertEqual([b.page_index for b in card.bouts], list(range(13)))

    def test_each_row_yields_two_named_fighters(self):
        for bout in load_card().bouts:
            with self.subTest(fight=bout.ufc_fight_id):
                self.assertEqual(len(bout.fighter_names), 2)
                self.assertEqual(len(bout.ufc_fighter_ids), 2)
                self.assertTrue(all(n.strip() for n in bout.fighter_names))

    def test_main_event_is_the_top_row(self):
        self.assertEqual(load_card().bouts[0].matchup, "Alexandre Pantoja vs Joshua Van")

    def test_empty_page_raises(self):
        with self.assertRaises(CardParseError):
            parse_event_page("")

    def test_page_with_no_bout_rows_raises(self):
        with self.assertRaises(CardParseError):
            parse_event_page("<html><body><p>Event postponed</p></body></html>")

    def test_row_with_one_fighter_raises(self):
        html = (
            '<tr data-link="http://ufcstats.com/fight-details/aaaaaaaaaaaaaaaa">'
            '<td><a href="http://ufcstats.com/fighter-details/bbbbbbbbbbbbbbbb">Solo</a></td>'
            "</tr>"
        )
        with self.assertRaises(CardParseError):
            parse_event_page(html)

    def test_repeated_fight_id_raises(self):
        """A duplicated row means the order cannot be read unambiguously."""
        one = (
            '<tr data-link="http://ufcstats.com/fight-details/aaaaaaaaaaaaaaaa">'
            '<td><a href="http://ufcstats.com/fighter-details/bbbbbbbbbbbbbbbb">A B</a>'
            '<a href="http://ufcstats.com/fighter-details/cccccccccccccccc">C D</a></td>'
            "</tr>"
        )
        with self.assertRaises(CardParseError):
            parse_event_page(one + one)

    def test_a_truncated_page_raises_rather_than_returning_a_short_card(self):
        """A dropped row does not look like a missing bout — it looks like a
        smaller card, and renumbers every bout on it."""
        full = FIXTURE.read_text(encoding="utf-8")
        cut = full[: full.rindex("</tr>") + 2]   # ends mid-row
        with self.assertRaises(CardParseError) as cm:
            parse_event_page(cut)
        self.assertIn("ended inside bout row", str(cm.exception))

    def test_short_or_malformed_fight_id_is_not_a_bout_row(self):
        """A 12-char id is not a UFCStats id; the row is not treated as a bout,
        and a page of only such rows has no readable order."""
        html = (
            '<tr data-link="http://ufcstats.com/fight-details/abc123">'
            '<td><a href="http://ufcstats.com/fighter-details/bbbbbbbbbbbbbbbb">A B</a></td>'
            "</tr>"
        )
        with self.assertRaises(CardParseError):
            parse_event_page(html)


class TestWalkoutDirection(unittest.TestCase):
    """The flip. If these pass backwards, every card in the ledger is inverted."""

    def test_main_event_walks_out_last(self):
        self.assertEqual(walkout_order(page_index=0, n_bouts=13), 13)

    def test_bottom_of_page_walks_out_first(self):
        self.assertEqual(walkout_order(page_index=12, n_bouts=13), 1)

    def test_the_two_conventions_are_opposites(self):
        """`fights.bout_order` counts 1 = main event; the ledger counts the other
        way. Same word, opposite meaning — asserted so a future join notices."""
        n = 13
        for i in range(n):
            self.assertEqual(card_position(i) + walkout_order(i, n), n + 1)
        self.assertEqual(card_position(0), 1)
        self.assertEqual(walkout_order(0, n), n)

    def test_out_of_range_refuses(self):
        for bad in (-1, 13):
            with self.subTest(i=bad), self.assertRaises(BoutOrderRefused):
                walkout_order(bad, 13)
        with self.assertRaises(BoutOrderRefused):
            walkout_order(0, 0)


class TestBuildRows(unittest.TestCase):
    def test_full_card_numbers_1_to_n(self):
        card = load_card()
        rows = build_rows(card, fights_for(card), CFL_EVENT_ID)
        self.assertEqual(len(rows), 13)
        self.assertEqual(sorted(r.bout_order for r in rows), list(range(1, 14)))
        self.assertTrue(all(r.source == SOURCE for r in rows))
        self.assertTrue(all(r.event_id == CFL_EVENT_ID for r in rows))

    def test_order_comes_from_the_page_not_from_ids(self):
        """The fight rows are built in id order that is unrelated to page order,
        so a row numbered by id would disagree with the page."""
        card = load_card()
        fights = fights_for(card)
        rows = build_rows(card, fights, CFL_EVENT_ID)
        by_ufc = {f.ufc_fight_id: f.id for f in fights}
        main = next(r for r in rows if r.fight_id == by_ufc[MAIN_EVENT_FIGHT])
        prelim = next(r for r in rows if r.fight_id == by_ufc[FIRST_PRELIM_FIGHT])
        self.assertEqual(main.bout_order, 13)
        self.assertEqual(prelim.bout_order, 1)
        id_sorted = [r.fight_id for r in sorted(rows, key=lambda r: r.bout_order)]
        self.assertNotEqual(id_sorted, sorted(id_sorted),
                            "fixture no longer exercises the id-order trap")

    def test_one_missing_fight_row_refuses_the_whole_card(self):
        card = load_card()
        fights = [f for f in fights_for(card) if f.ufc_fight_id != FIRST_PRELIM_FIGHT]
        with self.assertRaises(BoutOrderRefused) as cm:
            build_rows(card, fights, CFL_EVENT_ID)
        self.assertIn("no fight row", str(cm.exception))

    def test_a_fight_on_another_event_refuses(self):
        card = load_card()
        fights = fights_for(card)
        fights[0] = FightRow(fights[0].id, fights[0].ufc_fight_id, event_id=9999)
        with self.assertRaises(BoutOrderRefused) as cm:
            build_rows(card, fights, CFL_EVENT_ID)
        self.assertIn("different event", str(cm.exception))

    def test_two_fight_rows_sharing_a_ufc_id_refuses(self):
        card = load_card()
        fights = fights_for(card)
        fights.append(FightRow(id=99999, ufc_fight_id=MAIN_EVENT_FIGHT, event_id=CFL_EVENT_ID))
        with self.assertRaises(BoutOrderRefused) as cm:
            build_rows(card, fights, CFL_EVENT_ID)
        self.assertIn("more than one fight row", str(cm.exception))

    def test_dead_bookings_are_ignored_not_ordered(self):
        """Extra `fights` rows the page does not list get no order row — that is
        how a booking that fell off the card stays out of the running order."""
        card = load_card()
        fights = fights_for(card) + [
            FightRow(id=70001, ufc_fight_id="dead0000dead0000", event_id=CFL_EVENT_ID),
            FightRow(id=70002, ufc_fight_id="dead1111dead1111", event_id=CFL_EVENT_ID),
        ]
        rows = build_rows(card, fights, CFL_EVENT_ID)
        self.assertEqual(len(rows), 13)
        self.assertNotIn(70001, [r.fight_id for r in rows])

    def test_a_reshuffle_produces_a_different_order_for_the_same_fight(self):
        """Append-only means the ledger must be able to say a different thing
        about the same fight later. Here the card loses its opener, so every
        remaining bout moves down one."""
        card = load_card()
        fights = fights_for(card)
        rows_before = {r.fight_id: r.bout_order for r in build_rows(card, fights, CFL_EVENT_ID)}

        from cfl_engine.event_flow.ufcstats_card import ParsedCard, PageBout
        kept = [b for b in card.bouts if b.ufc_fight_id != FIRST_PRELIM_FIGHT]
        renumbered = ParsedCard(
            ufc_event_id=card.ufc_event_id,
            bouts=tuple(PageBout(i, b.ufc_fight_id, b.fighter_names, b.ufc_fighter_ids)
                        for i, b in enumerate(kept)),
        )
        rows_after = {r.fight_id: r.bout_order for r in build_rows(renumbered, fights, CFL_EVENT_ID)}

        moved = [fid for fid, o in rows_after.items() if rows_before[fid] != o]
        self.assertEqual(len(rows_after), 12)
        self.assertEqual(len(moved), 12, "dropping the opener should move every other bout")
        main_id = next(f.id for f in fights if f.ufc_fight_id == MAIN_EVENT_FIGHT)
        self.assertEqual(rows_before[main_id], 13)
        self.assertEqual(rows_after[main_id], 12)

    def test_payload_carries_no_client_timestamp(self):
        """observed_at is the database's to stamp. A client clock in an
        append-only ledger is a client-controlled history."""
        card = load_card()
        payload = build_rows(card, fights_for(card), CFL_EVENT_ID)[0].to_payload()
        self.assertEqual(set(payload), {"fight_id", "event_id", "bout_order", "source"})
        self.assertEqual(payload["source"], "ufcstats_card")


# ---------------------------------------------------------------------------
# The ledger-history defect: a bout returning to a position it held before
# ---------------------------------------------------------------------------
T0 = dt.datetime(2026, 9, 10, 12, 0, tzinfo=dt.timezone.utc)
FIGHT = 47331
EVENT = CFL_EVENT_ID


def obs(row_id: int, bout_order: int, minutes: int, fight_id: int = FIGHT) -> Observation:
    return Observation(id=row_id, fight_id=fight_id, bout_order=bout_order,
                       observed_at=T0 + dt.timedelta(minutes=minutes))


def downstream_resolution(ledger: list[Observation], fight_id: int) -> int:
    """What `v_clv_close_reference` would conclude, by its own rule.

        select distinct on (fight_id) ... order by fight_id, observed_at desc, id desc

    Reimplemented here rather than imported so the test is checking the ledger
    CONTENTS against the consumer's rule, not checking our own helper against
    itself. If `latest_state` were wrong in the same way, this would still catch
    it.
    """
    rows = [o for o in ledger if o.fight_id == fight_id]
    if not rows:
        raise AssertionError(f"fight {fight_id} has no observations")
    return max(rows, key=lambda o: (o.observed_at, o.id)).bout_order


class TestReturnToAPreviousPosition(unittest.TestCase):
    """5 -> 6 -> 5.

    This is the defect the old design had. The ledger's unique index on
    (fight_id, source, bout_order) plus `resolution=ignore-duplicates` meant the
    third observation was dropped as a duplicate of the first, leaving the
    ledger holding 5 and 6 with 6 the newer — so every downstream reader
    concluded 6. The card was at 5.
    """

    def _card_at(self, order: int) -> list[LedgerRow]:
        return [LedgerRow(fight_id=FIGHT, event_id=EVENT, bout_order=order)]

    def test_the_move_back_is_appended_and_downstream_resolves_to_5(self):
        ledger: list[Observation] = []
        next_id = iter(range(101, 200))

        for step, (order, minute) in enumerate([(5, 0), (6, 60), (5, 120)], start=1):
            plan = plan_append(self._card_at(order), ledger)
            self.assertTrue(
                plan.append,
                f"step {step}: observing bout {order} was treated as no change. "
                f"A position held in the past must never block a later "
                f"observation of it.",
            )
            ledger.append(obs(next(next_id), order, minute))

        self.assertEqual(len(ledger), 3,
                         "all three observations must be on record — the ledger "
                         "is the history, not just the current answer")
        self.assertEqual([o.bout_order for o in ledger], [5, 6, 5])

        # The point of the whole exercise.
        self.assertEqual(downstream_resolution(ledger, FIGHT), 5)
        self.assertEqual(latest_state(ledger)[FIGHT].bout_order, 5)

    def test_the_old_ignore_duplicates_behaviour_would_have_failed_this(self):
        """Proof the regression test is actually testing something.

        Replay the same three observations under the old rule — drop any row
        whose (fight, source, order) already exists — and watch downstream land
        on 6.
        """
        ledger: list[Observation] = []
        seen: set[tuple[int, str, int]] = set()
        for i, (order, minute) in enumerate([(5, 0), (6, 60), (5, 120)]):
            key = (FIGHT, SOURCE, order)
            if key in seen:
                continue          # what the unique index did
            seen.add(key)
            ledger.append(obs(101 + i, order, minute))

        self.assertEqual([o.bout_order for o in ledger], [5, 6],
                         "the third observation should have been swallowed")
        self.assertEqual(
            downstream_resolution(ledger, FIGHT), 6,
            "if this is not 6, the old behaviour was not reproduced and the "
            "regression test above proves nothing",
        )

    def test_an_unchanged_card_appends_nothing(self):
        """The no-op case still has to be a no-op, or the ledger fills with
        identical rows twice a day."""
        ledger = [obs(101, 5, 0)]
        plan = plan_append(self._card_at(5), ledger)
        self.assertFalse(plan.append)
        self.assertEqual(plan.unchanged, 1)
        self.assertIn("no change", plan.reason)

    def test_one_bout_moving_appends_the_whole_card(self):
        """A running order is one joint fact. Appending only the movers would
        leave a snapshot that has to be assembled from different instants."""
        card = load_card()
        fights = fights_for(card)
        rows = build_rows(card, fights, EVENT)
        ledger = [
            Observation(id=200 + i, fight_id=r.fight_id, bout_order=r.bout_order,
                        observed_at=T0)
            for i, r in enumerate(rows)
        ]
        moved = ledger[0]
        ledger[0] = Observation(id=moved.id, fight_id=moved.fight_id,
                                bout_order=moved.bout_order + 1, observed_at=T0)

        plan = plan_append(rows, ledger)
        self.assertTrue(plan.append)
        self.assertEqual(len(plan.changes), 1)
        self.assertEqual(plan.unchanged, len(rows) - 1)

    def test_a_tie_on_observed_at_is_broken_by_id_not_by_luck(self):
        """Two observations can share an `observed_at` — `now()` is the
        transaction's start time, so a retry lands on the same microsecond. The
        tiebreak has to be deterministic and has to match the consumer's."""
        ledger = [obs(101, 5, 0), obs(102, 6, 0)]
        self.assertEqual(downstream_resolution(ledger, FIGHT), 6)
        self.assertEqual(latest_state(ledger)[FIGHT].bout_order, 6)
        self.assertEqual(downstream_resolution(list(reversed(ledger)), FIGHT), 6,
                         "resolution must not depend on the order rows arrive in")

    def test_out_of_order_arrival_still_resolves_to_the_newest(self):
        """PostgREST returns newest-first; nothing should depend on that."""
        ledger = [obs(103, 5, 120), obs(101, 5, 0), obs(102, 6, 60)]
        self.assertEqual(downstream_resolution(ledger, FIGHT), 5)
        self.assertEqual(latest_state(ledger)[FIGHT].bout_order, 5)

    def test_a_fight_that_left_the_card_is_reported_not_erased(self):
        """The ledger cannot say 'removed', and inventing a way would record
        something we did not observe. It is surfaced instead."""
        card = load_card()
        rows = build_rows(card, fights_for(card), EVENT)
        gone = 99999
        ledger = [Observation(id=300, fight_id=gone, bout_order=1, observed_at=T0)]
        plan = plan_append(rows, ledger)
        self.assertEqual(plan.stale_fights, (gone,))
        self.assertTrue(plan.append)

    def test_latest_state_is_empty_for_an_untouched_event(self):
        self.assertEqual(latest_state([]), {})
        plan = plan_append([LedgerRow(FIGHT, EVENT, 1)], [])
        self.assertTrue(plan.append)
        self.assertIn("not yet observed", plan.changes[0])


# ---------------------------------------------------------------------------
# End to end through the runner, against a fake append-only ledger
# ---------------------------------------------------------------------------
def build_page(matchups: list[tuple[str, str, str]]) -> str:
    """A UFCStats-shaped page from (fight_id, name_a, name_b), main event first."""
    rows = "".join(
        f'<tr data-link="http://ufcstats.com/fight-details/{fid}">'
        f'<td class="b-fight-details__table-col l-page_align_left">'
        f'<p><a href="http://ufcstats.com/fighter-details/{"a" * 16}" class="b-link">{a}</a></p>'
        f'<p><a href="http://ufcstats.com/fighter-details/{"b" * 16}" class="b-link">{b}</a></p>'
        f"</td></tr>"
        for fid, a, b in matchups
    )
    return ('<html><body><a href="http://ufcstats.com/event-details/'
            f'{FIXTURE_EVENT_ID}">e</a><table><tbody>{rows}</tbody></table></body></html>')


class FakeLedger:
    """An append-only `fight_bout_order`, and a `fights` table to link against.

    Append-only is enforced here the way the real table enforces it — by
    refusing — so a test cannot pass by doing something the database would
    reject. `reject_repeat_order` reinstates the unique index that the migration
    still carries, so the diagnosis path can be exercised too.
    """

    def __init__(self, fights: list[FightRow], reject_repeat_order: bool = False):
        self.fights = fights
        self.rows: list[dict] = []
        self.next_id = 1
        self.clock = T0
        self.reject_repeat_order = reject_repeat_order

    # -- the two REST entry points the runner uses --------------------------
    def rest_get(self, base_url, key, path, params):
        if path == "fights":
            return [{"id": f.id, "ufc_fight_id": f.ufc_fight_id, "event_id": f.event_id}
                    for f in self.fights]
        if path == "fight_bout_order":
            return sorted(self.rows,
                          key=lambda r: (r["observed_at"], r["id"]), reverse=True)
        raise AssertionError(f"unexpected read of {path}")

    def rest_append(self, base_url, key, path, payloads):
        assert path == "fight_bout_order"
        self.clock += dt.timedelta(minutes=30)      # one now() for the whole batch
        stamped = []
        for payload in payloads:
            if self.reject_repeat_order and any(
                r["fight_id"] == payload["fight_id"]
                and r["source"] == payload["source"]
                and r["bout_order"] == payload["bout_order"]
                for r in self.rows
            ):
                import urllib.error
                raise urllib.error.HTTPError(
                    "u", 409, "Conflict", {}, io.BytesIO(
                        b'{"code":"23505","message":"duplicate key value violates '
                        b'unique constraint \\"fight_bout_order_unique_idx\\""}'))
            stamped.append({**payload, "id": self.next_id,
                            "observed_at": self.clock.isoformat()})
            self.next_id += 1
        self.rows.extend(stamped)                    # one statement, all or nothing
        return stamped

    # -- what a consumer would conclude -------------------------------------
    def resolves_to(self, fight_id: int) -> int:
        rows = [r for r in self.rows if r["fight_id"] == fight_id]
        return max(rows, key=lambda r: (r["observed_at"], r["id"]))["bout_order"]


class TestIngestEventEndToEnd(unittest.TestCase):
    """Drives `ingest_event` itself, not just the planner, so the read →
    compare → append wiring is covered rather than assumed."""

    EVENT = {"id": CFL_EVENT_ID, "name": "UFC Fixture", "event_date": "2026-09-19",
             "ufc_event_id": FIXTURE_EVENT_ID}

    # Four bouts. Moving the bottom two past each other moves the fight we
    # watch between walkout 1 and walkout 2 — the 5 -> 6 -> 5 shape, smaller.
    TOP = ("f" + "0" * 15, "Main A", "Main B")
    SECOND = ("f" + "1" * 15, "Second A", "Second B")
    WATCHED = ("f" + "2" * 15, "Watched A", "Watched B")
    OTHER = ("f" + "3" * 15, "Other A", "Other B")

    def setUp(self):
        self.fights = [
            FightRow(id=900 + i, ufc_fight_id=fid, event_id=CFL_EVENT_ID)
            for i, (fid, _, _) in enumerate(
                [self.TOP, self.SECOND, self.WATCHED, self.OTHER])
        ]
        self.watched_id = next(f.id for f in self.fights
                               if f.ufc_fight_id == self.WATCHED[0])

    def run_page(self, ledger, matchups, execute=True):
        import cfl_engine.event_flow.ingest_bout_order as ing
        get, append = ing.rest_get, ing.rest_append
        ing.rest_get, ing.rest_append = ledger.rest_get, ledger.rest_append
        try:
            return ing.ingest_event(self.EVENT, "https://x.supabase.co", "k",
                                    execute=execute,
                                    page_html=build_page(matchups),
                                    log=lambda *a, **k: None)
        finally:
            ing.rest_get, ing.rest_append = get, append

    def test_five_six_five_through_the_runner(self):
        ledger = FakeLedger(self.fights)

        # WATCHED is second from the bottom -> walkout 2.
        page_a = [self.TOP, self.SECOND, self.WATCHED, self.OTHER]
        # the two prelims swap -> WATCHED is last on the page -> walkout 1.
        page_b = [self.TOP, self.SECOND, self.OTHER, self.WATCHED]

        self.assertEqual(self.run_page(ledger, page_a), "written")
        self.assertEqual(ledger.resolves_to(self.watched_id), 2)

        self.assertEqual(self.run_page(ledger, page_b), "written")
        self.assertEqual(ledger.resolves_to(self.watched_id), 1)

        # …and back. This is the observation the old design dropped.
        self.assertEqual(self.run_page(ledger, page_a), "written")
        self.assertEqual(
            ledger.resolves_to(self.watched_id), 2,
            "the card moved back and the ledger did not record it — this is the "
            "5 -> 6 -> 5 defect",
        )
        self.assertEqual(len(ledger.rows), 12, "three complete 4-bout observations")

    # -- regression: a booking that fell off the card ------------------------
    # UFC 331 (CFL event 4433), 2026-09-18. The live UFCStats page carried TWELVE
    # bouts; `fights` carried THIRTEEN. The extra row was Moicano vs Ortega, a
    # real booking that was announced and then cancelled when Ortega withdrew
    # injured — not a scrape defect and not a parser defect.
    #
    # The failure this guards against is arithmetic, not cosmetic. bout_order is
    # n_bouts - page_index, so if a cancelled booking were ever allowed to inflate
    # n_bouts, EVERY bout on the card would be numbered one too high and the main
    # event would land at 13 on a 12-bout card. Nothing would raise. The running
    # order must come from the page, and only from the page.
    CANCELLED = ("f" + "9" * 15, "Withdrawn A", "Withdrawn B")

    def test_a_cancelled_booking_does_not_inflate_the_running_order(self):
        """The card's length is what the page says, not what `fights` holds."""
        ledger = FakeLedger(self.fights + [
            FightRow(id=947328, ufc_fight_id=self.CANCELLED[0], event_id=CFL_EVENT_ID)
        ])

        # Four bouts on the page; five bookings in the database.
        page = [self.TOP, self.SECOND, self.WATCHED, self.OTHER]
        self.assertEqual(self.run_page(ledger, page), "written")

        self.assertEqual(len(ledger.rows), 4,
                         "the cancelled booking was numbered as if it were on the card")

        orders = sorted(r["bout_order"] for r in ledger.rows)
        self.assertEqual(orders, [1, 2, 3, 4],
                         "running order must be contiguous over the PAGE's bouts")

        top_id = next(f.id for f in ledger.fights
                      if f.ufc_fight_id == self.TOP[0])
        self.assertEqual(
            ledger.resolves_to(top_id), 4,
            "the main event took its number from the database's count, not the "
            "page's — this is the UFC 331 defect",
        )

        self.assertNotIn(947328, [r["fight_id"] for r in ledger.rows],
                         "a cancelled booking must never receive a bout_order")

    def test_a_booking_that_disappears_between_refreshes_is_reported_not_erased(self):
        """Announced, observed, then withdrawn. The first observation stands."""
        ledger = FakeLedger(self.fights)

        # First refresh: four bouts, all on the card.
        before = [self.TOP, self.SECOND, self.WATCHED, self.OTHER]
        self.assertEqual(self.run_page(ledger, before), "written")
        self.assertEqual(ledger.resolves_to(self.watched_id), 2)
        rows_before = len(ledger.rows)

        # Second refresh: WATCHED has fallen off the card entirely.
        after = [self.TOP, self.SECOND, self.OTHER]
        self.assertEqual(self.run_page(ledger, after), "written")

        # Its history survives — an append-only ledger never unsays an
        # observation, and the pick locked against it still needs to resolve.
        self.assertEqual(
            ledger.resolves_to(self.watched_id), 2,
            "the withdrawn booking's last observation was erased or overwritten",
        )
        self.assertGreater(len(ledger.rows), rows_before)

        # …and the three that remain renumber over the SHORTER card.
        newest = max(r["observed_at"] for r in ledger.rows)
        current = {r["fight_id"]: r["bout_order"]
                   for r in ledger.rows if r["observed_at"] == newest}
        self.assertEqual(len(current), 3, "the new observation is the whole card")
        self.assertEqual(sorted(current.values()), [1, 2, 3])
        self.assertNotIn(self.watched_id, current,
                         "a fight absent from the page joined the current card")

    def test_re_running_an_unchanged_card_writes_nothing(self):
        ledger = FakeLedger(self.fights)
        page = [self.TOP, self.SECOND, self.WATCHED, self.OTHER]
        self.assertEqual(self.run_page(ledger, page), "written")
        self.assertEqual(len(ledger.rows), 4)
        for _ in range(3):
            self.assertEqual(self.run_page(ledger, page), "unchanged")
        self.assertEqual(len(ledger.rows), 4, "an unchanged card appended rows")

    def test_a_dry_run_writes_nothing_even_when_the_card_changed(self):
        ledger = FakeLedger(self.fights)
        page = [self.TOP, self.SECOND, self.WATCHED, self.OTHER]
        self.assertEqual(self.run_page(ledger, page, execute=False), "dry-run")
        self.assertEqual(ledger.rows, [])

    def test_the_whole_card_shares_one_observed_at(self):
        """A card observation has to read back as one coherent snapshot."""
        ledger = FakeLedger(self.fights)
        self.run_page(ledger, [self.TOP, self.SECOND, self.WATCHED, self.OTHER])
        self.assertEqual(len({r["observed_at"] for r in ledger.rows}), 1)

    def test_the_still_unique_ledger_halts_at_the_very_first_reshuffle(self):
        """With the migration's index still in place, a complete-card append
        fails on the FIRST reshuffle, not just on a bout returning to an old
        position — every bout that did NOT move collides with its own existing
        row. The run must stop and name the fix rather than write a partial
        card."""
        import contextlib
        import cfl_engine.event_flow.ingest_bout_order as ing

        ledger = FakeLedger(self.fights, reject_repeat_order=True)
        page_a = [self.TOP, self.SECOND, self.WATCHED, self.OTHER]
        page_b = [self.TOP, self.SECOND, self.OTHER, self.WATCHED]

        self.assertEqual(self.run_page(ledger, page_a), "written")
        self.assertEqual(len(ledger.rows), 4)

        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            self.run_page(ledger, page_b)

        self.assertEqual(cm.exception.code, ing.EXIT_LEDGER_SHAPE)
        msg = err.getvalue()
        self.assertIn("fight_bout_order_unique_idx", msg)
        self.assertIn("MIGRATION_ADJUSTMENT.md", msg)
        self.assertIn("Nothing was written", msg)
        self.assertEqual(len(ledger.rows), 4,
                         "a partial card was written — the append must be all "
                         "or nothing")

    def test_without_the_index_the_same_reshuffle_records_cleanly(self):
        """The control for the test above: the only difference is the index."""
        ledger = FakeLedger(self.fights, reject_repeat_order=False)
        self.assertEqual(
            self.run_page(ledger, [self.TOP, self.SECOND, self.WATCHED, self.OTHER]),
            "written")
        self.assertEqual(
            self.run_page(ledger, [self.TOP, self.SECOND, self.OTHER, self.WATCHED]),
            "written")
        self.assertEqual(len(ledger.rows), 8)
        self.assertEqual(ledger.resolves_to(self.watched_id), 1)


class TestProductionWriteGate(unittest.TestCase):
    """Writing is gated on somebody having read one real UFCStats page."""

    def test_the_gate_is_currently_shut(self):
        import cfl_engine.event_flow.ingest_bout_order as ing
        self.assertFalse(
            ing.VERIFICATION.is_file(),
            "a verification record exists — if a real page really was checked, "
            "say so in the handoff; this test guards against the file being "
            "added without that happening",
        )

    def test_missing_verification_refuses_to_write(self):
        import contextlib
        import io

        import cfl_engine.event_flow.ingest_bout_order as ing

        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            ing.require_real_page_verified()
        self.assertEqual(cm.exception.code, ing.EXIT_CONFIG)
        msg = err.getvalue()
        self.assertIn("no real UFCStats page has been checked", msg)
        self.assertIn("--from-file", msg)

    def test_an_incomplete_verification_record_is_refused(self):
        import contextlib
        import io
        import json
        import tempfile
        from pathlib import Path

        import cfl_engine.event_flow.ingest_bout_order as ing

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "REAL_PAGE_CHECK.json"
            path.write_text(json.dumps({"ufc_event_id": "8a0a35e7c74bebcc"}),
                            encoding="utf-8")
            original, err = ing.VERIFICATION, io.StringIO()
            ing.VERIFICATION = path
            try:
                with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
                    ing.require_real_page_verified()
                self.assertEqual(cm.exception.code, ing.EXIT_CONFIG)
                self.assertIn("checked_by", err.getvalue())
            finally:
                ing.VERIFICATION = original

    def test_a_complete_verification_record_opens_the_gate(self):
        import json
        import tempfile
        from pathlib import Path

        import cfl_engine.event_flow.ingest_bout_order as ing

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "REAL_PAGE_CHECK.json"
            path.write_text(json.dumps({
                "ufc_event_id": "8a0a35e7c74bebcc",
                "cfl_event_id": 4433,
                "checked_by": "Reed Cannon",
                "checked_at": "2026-09-17",
                "main_event_bout_order": 13,
                "first_walkout_matchup": "Michael Aswell Jr. vs JooSang Yoo",
            }), encoding="utf-8")
            original = ing.VERIFICATION
            ing.VERIFICATION = path
            try:
                ing.require_real_page_verified()   # must not raise
            finally:
                ing.VERIFICATION = original

    def test_a_dry_run_is_never_gated(self):
        """The dry run is how you produce the confirmation, so gating it would
        make the gate impossible to open."""
        import inspect
        import cfl_engine.event_flow.ingest_bout_order as ing
        src = inspect.getsource(ing.main)
        self.assertIn("if args.execute:\n        require_real_page_verified()", src)


class TestUniqueIndexDiagnosis(unittest.TestCase):
    """If the migration still carries the unique index, say exactly that."""

    def test_a_unique_violation_is_recognised(self):
        from cfl_engine.event_flow.ingest_bout_order import unique_index_still_present
        self.assertTrue(unique_index_still_present(
            '{"code":"23505","message":"duplicate key value violates unique '
            'constraint \"fight_bout_order_unique_idx\""}'))
        self.assertFalse(unique_index_still_present(
            '{"code":"42501","message":"permission denied"}'))

    def test_the_error_names_the_migration_fix(self):
        import inspect
        import cfl_engine.event_flow.ingest_bout_order as ing
        src = inspect.getsource(ing.ingest_event)
        self.assertIn("MIGRATION_FIX", src)
        self.assertIn("EXIT_LEDGER_SHAPE", src)
        self.assertIn("Nothing was written", src)
        self.assertEqual(ing.MIGRATION_FIX,
                         "cfl_engine/event_flow/MIGRATION_ADJUSTMENT.md")


class TestRunnerGuards(unittest.TestCase):
    def test_from_file_without_event_id_exits_with_the_config_code(self):
        """The exit CODE is the contract a workflow branches on, so the message
        and the code are asserted together."""
        import contextlib
        import io
        import sys

        import cfl_engine.event_flow.ingest_bout_order as ing

        argv, err = sys.argv, io.StringIO()
        sys.argv = ["ingest", "--from-file", str(FIXTURE)]
        try:
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
                ing.main()
            self.assertEqual(cm.exception.code, ing.EXIT_CONFIG)
            self.assertIn("--from-file needs --event-id", err.getvalue())
        finally:
            sys.argv = argv

    def test_the_exit_codes_are_distinct(self):
        import cfl_engine.event_flow.ingest_bout_order as ing
        codes = [ing.EXIT_OK, ing.EXIT_CONFIG, ing.EXIT_REFUSED, ing.EXIT_FETCH]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(ing.EXIT_OK, 0)

    def test_missing_ledger_exits_and_never_creates_it(self):
        """If the migration has not been applied, the run stops. It must not
        fall back to creating the table or to writing somewhere else."""
        import urllib.error
        import cfl_engine.event_flow.ingest_bout_order as ing

        def boom(*a, **k):
            raise urllib.error.HTTPError(
                "u", 404, "Not Found", {},
                __import__("io").BytesIO(b'{"message":"relation does not exist"}'))

        import contextlib
        import io

        original, err = ing.rest_get, io.StringIO()
        ing.rest_get = boom
        try:
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
                ing.require_ledger("https://x.supabase.co", "k")
            self.assertEqual(cm.exception.code, ing.EXIT_CONFIG)
            msg = err.getvalue()
            self.assertIn("fight_bout_order", msg)
            self.assertIn("does not create tables", msg)
            self.assertIn(ing.MIGRATION, msg)
        finally:
            ing.rest_get = original

    def test_append_uses_no_conflict_resolution_at_all(self):
        """`resolution=ignore-duplicates` is what broke 5 -> 6 -> 5: it told the
        database to drop the one observation we needed. Whether anything changed
        is decided by reading the ledger, never by a constraint."""
        import ast
        import inspect
        import cfl_engine.event_flow.ingest_bout_order as ing

        # The docstring explains why the header is absent, so the prose is
        # stripped before looking — otherwise the explanation trips the check.
        fn = ast.parse(inspect.getsource(ing.rest_append)).body[0]
        body = ast.unparse(fn.body[1:]) if ast.get_docstring(fn) else ast.unparse(fn.body)

        prefer = [n.value for n in ast.walk(ast.parse(body))
                  if isinstance(n, ast.Constant) and isinstance(n.value, str)
                  and "=" in n.value and "return" in n.value]
        self.assertEqual(prefer, ["return=representation"],
                         f"unexpected Prefer directives: {prefer}")
        for banned in ("ignore-duplicates", "merge-duplicates", "on_conflict",
                       "PATCH", "DELETE"):
            self.assertNotIn(banned, body, f"rest_append mentions {banned}")
        self.assertFalse(hasattr(ing, "rest_insert"),
                         "the old ignore-duplicates path is still importable")

    def test_execute_is_not_the_default(self):
        import cfl_engine.event_flow.ingest_bout_order as ing
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("--execute", action="store_true")
        self.assertFalse(ap.parse_args([]).execute)
        self.assertEqual(ing.LEDGER, "fight_bout_order")


if __name__ == "__main__":
    unittest.main()
