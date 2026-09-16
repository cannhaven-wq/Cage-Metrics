"""Tests for the UFCStats running-order ingestion path.

    python -m unittest cfl_engine.event_flow.test_event_flow -v

Three things are actually load-bearing here and each has a test that bites:

  1. the page is read bottom-up — the main event is the LAST walkout, not the
     first. Getting this backwards silently inverts every card;
  2. a card that cannot be linked completely writes nothing;
  3. linkage is by UFCStats fight id only, never by fighter name.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from cfl_engine.event_flow.bout_order import (
    SOURCE,
    BoutOrderRefused,
    FightRow,
    build_rows,
    card_position,
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

    def test_insert_ignores_duplicates_and_never_upserts(self):
        """A re-run must be a no-op, and a correction must append rather than
        overwrite. `merge-duplicates` here would be an in-place rewrite."""
        import inspect
        import cfl_engine.event_flow.ingest_bout_order as ing
        src = inspect.getsource(ing.rest_insert)
        self.assertIn("resolution=ignore-duplicates", src)
        self.assertNotIn("merge-duplicates", src)
        self.assertNotIn("PATCH", src)
        self.assertNotIn("DELETE", src)

    def test_execute_is_not_the_default(self):
        import cfl_engine.event_flow.ingest_bout_order as ing
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("--execute", action="store_true")
        self.assertFalse(ap.parse_args([]).execute)
        self.assertEqual(ing.LEDGER, "fight_bout_order")


if __name__ == "__main__":
    unittest.main()
