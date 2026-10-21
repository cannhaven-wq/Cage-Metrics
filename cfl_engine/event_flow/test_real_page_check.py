"""The real-page check: it must fail loudly on a backwards flip or a bot wall."""
from __future__ import annotations

import datetime as dt
import unittest

from cfl_engine.event_flow.real_page_check import (
    CONFIRMED,
    CONTRADICTED,
    UNCONFIRMABLE,
    build_report,
    check_page,
    fold,
    page_title,
    parse_listing,
    pick_events,
    title_matchup,
)

EID = "55e94a9b525dcf45"


def page(title: str, bouts: list[tuple[str, str]], event_id: str = EID) -> str:
    """A minimal page in UFCStats markup: rows listed main event first."""
    rows = []
    for i, (a, b) in enumerate(bouts):
        fid = f"{i:016x}"
        rows.append(
            f'<tr class="b-fight-details__table-row" '
            f'data-link="http://ufcstats.com/fight-details/{fid}">'
            f'<td><a href="http://ufcstats.com/fighter-details/{(2*i):016x}">{a}</a>'
            f'<a href="http://ufcstats.com/fighter-details/{(2*i+1):016x}">{b}</a></td></tr>')
    return (f'<html><h2 class="b-content__title"><span class="b-content__title-highlight">'
            f'{title}</span></h2><a href="http://ufcstats.com/event-details/{event_id}">e</a>'
            f'<table>{"".join(rows)}</table></html>')


CARD = [("Kevin Holland", "Rob Font Jr."), ("Joaquin Buckley", "Mike Malott"),
        ("Ana Silva", "Bea Jones"), ("Cal Ortiz", "Dan Wu")]


class TestDirection(unittest.TestCase):
    def test_title_on_the_top_row_confirms_main_event_first(self):
        html = page("UFC Fight Night: Buckley vs. Malott",
                    [CARD[1], CARD[0], CARD[2], CARD[3]])
        e = check_page(EID, html, 200)
        self.assertEqual(e["status"], "parsed")
        self.assertEqual(e["direction"], CONFIRMED)
        self.assertEqual(e["main_event_bout_order"], 4)
        self.assertEqual(e["bouts"][-1]["matchup"], "Joaquin Buckley vs Mike Malott")
        self.assertEqual(e["bouts"][0]["bout_order"], 1)
        self.assertEqual(e["first_walkout_matchup"], "Cal Ortiz vs Dan Wu")

    def test_title_on_the_bottom_row_is_contradicted(self):
        """If UFCStats ever listed first walkout first, every card would invert."""
        html = page("UFC Fight Night: Buckley vs. Malott",
                    [CARD[3], CARD[2], CARD[0], CARD[1]])
        e = check_page(EID, html, 200)
        self.assertEqual(e["direction"], CONTRADICTED)
        report = build_report([{**e, "kind": "completed"}], {"checked_by": "x",
                                                             "checked_at": "2026-10-21"})
        self.assertEqual(report["result"], "fail")
        self.assertIsNone(report["checked_by"], "a failed check satisfied the ingester gate")

    def test_title_without_a_matchup_is_not_a_pass(self):
        e = check_page(EID, page("UFC 400", CARD), 200)
        self.assertEqual(e["direction"], UNCONFIRMABLE)
        r = build_report([{**e, "kind": "completed"}], {"checked_by": "x", "checked_at": "d"})
        self.assertEqual(r["result"], "fail")

    def test_accents_and_suffixes_do_not_decide(self):
        html = page("UFC 330: Font Jr. vs. Holland", CARD)
        self.assertEqual(check_page(EID, html, 200)["direction"], CONFIRMED)
        self.assertEqual(fold("José Aldo"), "jose aldo")

    def test_multi_word_surnames(self):
        html = page("UFC Fight Night: de Ridder vs. Allen",
                    [("Reinier de Ridder", "Brendan Allen"), CARD[2]])
        self.assertEqual(check_page(EID, html, 200)["direction"], CONFIRMED)


class TestRefusals(unittest.TestCase):
    def test_bot_wall_is_unreadable_never_a_pass(self):
        html = "<html><title>Checking your browser</title><script>pow()</script></html>"
        e = check_page(EID, html, 200)
        self.assertEqual(e["status"], "page_unreadable")
        r = build_report([e], {"checked_by": "x", "checked_at": "d"})
        self.assertEqual(r["result"], "fail")
        self.assertIsNone(r["ufc_event_id"])

    def test_http_error_is_unreadable(self):
        self.assertEqual(check_page(EID, "Forbidden", 403)["status"], "page_unreadable")

    def test_truncated_page_is_a_parse_error(self):
        html = page("UFC Fight Night: Buckley vs. Malott", [CARD[1], CARD[0]])
        cut = html[: html.rindex("<tr")] + '<tr data-link="http://ufcstats.com/fight-details/00000000000000ff"><td>'
        self.assertEqual(check_page(EID, cut, 200)["status"], "parse_error")

    def test_a_page_for_another_event_is_not_parsed(self):
        html = page("UFC Fight Night: Buckley vs. Malott", [CARD[1]], event_id="0" * 16)
        self.assertEqual(check_page(EID, html, 200)["status"], "wrong_event")

    def test_one_bad_page_fails_the_whole_check(self):
        good = {**check_page(EID, page("UFC FN: Buckley vs. Malott", [CARD[1], CARD[0]]), 200),
                "kind": "completed"}
        bad = {**check_page("1" * 16, "", 403), "kind": "upcoming"}
        self.assertEqual(build_report([good, bad], {"checked_by": "x", "checked_at": "d"})["result"],
                         "fail")


class TestReport(unittest.TestCase):
    def test_pass_carries_the_fields_the_ingester_demands(self):
        done = {**check_page(EID, page("UFC FN: Buckley vs. Malott", [CARD[1], CARD[0]]), 200),
                "kind": "completed"}
        r = build_report([done], {"checked_by": "GitHub Actions run 1", "checked_at": "2026-10-21"})
        self.assertEqual(r["result"], "pass")
        for k in ("ufc_event_id", "checked_by", "checked_at", "main_event_bout_order",
                  "first_walkout_matchup"):
            self.assertTrue(r[k], k)
        self.assertEqual(r["main_event_bout_order"], 2)


class TestListing(unittest.TestCase):
    LISTING = (
        '<tr><td><i><a href="http://ufcstats.com/event-details/aaaaaaaaaaaaaaaa" class="b-link">'
        'UFC Fight Night: Next vs. Card</a><span class="b-statistics__date">October 25, 2026</span>'
        '</i></td></tr>'
        '<tr><td><i><a href="http://ufcstats.com/event-details/bbbbbbbbbbbbbbbb" class="b-link">'
        'UFC Fight Night: Buckley vs. Malott</a><span class="b-statistics__date">October 17, 2026'
        '</span></i></td></tr>'
        '<tr><td><i><a href="http://ufcstats.com/event-details/cccccccccccccccc" class="b-link">'
        'UFC 330</a><span class="b-statistics__date">October 10, 2026</span></i></td></tr>')

    def test_parse_and_pick(self):
        rows = parse_listing(self.LISTING)
        self.assertEqual([r["ufc_event_id"][0] for r in rows], ["a", "b", "c"])
        picked = pick_events(rows, rows, dt.date(2026, 10, 21))
        self.assertEqual([(p["kind"], p["ufc_event_id"][0]) for p in picked],
                         [("completed", "b"), ("upcoming", "a")])

    def test_title_helpers(self):
        self.assertEqual(title_matchup("UFC Fight Night: Buckley vs. Malott"), ("buckley", "malott"))
        self.assertIsNone(title_matchup("UFC 330"))
        self.assertEqual(page_title(page("UFC 1: A vs. B", CARD)), "UFC 1: A vs. B")


if __name__ == "__main__":
    unittest.main()
