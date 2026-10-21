"""Source adapters: the real ESPN and Wikipedia samples, and name-pair linking.

The fixtures under fixtures/ are REAL responses fetched by
.github/workflows/event-flow-source-probe.yml on a GitHub runner, cut down by
`sources.espn_fixture` / `sources.wikipedia_results_section` (no value
changed). Each fixture's sha256 was printed by the run that fetched it and is
asserted here, so a hand edit to a fixture fails loudly.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from cfl_engine.event_flow.sources import (
    ESPN,
    LinkRefused,
    NamedFight,
    SourceBout,
    SourceCard,
    SourceError,
    compare_orders,
    direction,
    fixture_canonical_sha,
    link_by_pair,
    parse_espn_scoreboard,
    parse_wikipedia_results,
    same_pair,
)

FIX = Path(__file__).parent / "fixtures"

# CFL's own `fights` rows for the two cards, read 2026-10-21 (read-only query).
# Inactive rows included on purpose: linking must never pick a retired twin.
CFL_4368 = [
    (46774, "Joaquin Buckley", "Mike Malott"), (47339, "Mandel Nallo", "Nate Landwehr"),
    (47879, "Erin Blanchfield", "Jasmine Jasudavicius"),
    (47880, "Marc-Andre Barriault", "Kyle Daukaus"),
    (47881, "Jamey-Lyn Horth", "Katlyn Cerminara"),           # inactive
    (47882, "Tanner Boser", "Jhonata Diniz"), (47883, "Melissa Croden", "Chelsea Chandler"),
    (47884, "Louis Jourdain", "Timmy Cuamba"),
    (48644, "Julien Leblanc", "Gilbert Urbina"),              # inactive
    (49168, "Chad Anheliger", "Steven Koslow"),
    (50990, "Javad Mahjoub", "Louie Sutherland"),             # inactive
    (51091, "Cody Chovancek", "SuYoung You"), (52117, "Kyle Nelson", "Cristian Perez"),
    (53618, "Julien Leblanc", "Nick Galanti"), (53619, "Javad Mahjoub", "Joel Faglier"),
    (53620, "Katlyn Cerminara", "Mackenzie Stiller"),
]
CFL_4542 = [
    (48438, "Alexander Volkanovski", "Movsar Evloev"), (48439, "Petr Yan", "Merab Dvalishvili"),
    (48440, "Lone'er Kavanagh", "Ramazan Temirov"), (48441, "Azamat Murzakanov", "Dominick Reyes"),
    (48442, "Grant Dawson", "Nurullo Aliev"),
    (48648, "Arnold Allen", "Aaron Pico"),                    # inactive
    (48650, "Abus Magomedov", "Cam Rowston"), (48651, "Nikita Krylov", "Abdul Rakhman Yakhyaev"),
    (50696, "Alexander Volkov", "Rizvan Kuniev"), (53413, "Aaron Pico", "Losene Keita"),
    (63228, "Colby Thicknesse", "Asaf Chopurov"), (63229, "Abubakar Vagaev", "Jacob Malkoun"),
    (72704, "Bolaji Oki", "Daniel Santos"), (72705, "Kody Steele", "Noah Gugnon"),
    (72706, "Iasmin Lucindo", "Nicolle Caliari"),
]


def named(event_id, rows):
    return [NamedFight(id=i, event_id=event_id, fighter_names=(a, b)) for i, a, b in rows]


def card(names, title="UFC Fight Night: A vs. B"):
    return SourceCard(ESPN, "1", title, None, tuple(
        SourceBout(walkout=i + 1, fighter_names=n, source_bout_id=str(i))
        for i, n in enumerate(names)))


class TestNames(unittest.TestCase):
    def test_spelling_differences_that_must_not_decide(self):
        for a, b in [("Julien LeBlanc", "Julien Leblanc"), ("Cristian Pérez", "Cristian Perez"),
                     ("Abdul-Rakhman Yakhyaev", "Abdul Rakhman Yakhyaev"),
                     ("Su Young You", "SuYoung You"), ("Lone'er Kavanagh", "Loneer Kavanagh")]:
            self.assertTrue(same_pair((a, "X Y"), ("X Y", b)), (a, b))

    def test_a_different_person_is_not_folded_away(self):
        self.assertFalse(same_pair(("Julien Leblanc", "Nick Galanti"),
                                   ("Julien Leblanc", "Gilbert Urbina")))
        self.assertFalse(same_pair(("Aaron Pico", "Losene Keita"), ("Arnold Allen", "Aaron Pico")))


class TestLinking(unittest.TestCase):
    def test_a_card_links_completely_or_not_at_all(self):
        c = card([("Javad Mahjoub", "Joel Faglier"), ("Nobody Known", "Also Unknown")])
        with self.assertRaises(LinkRefused) as cm:
            link_by_pair(c, named(4368, CFL_4368), 4368)
        self.assertIn("Nobody Known", str(cm.exception))

    def test_the_retired_twin_is_never_picked(self):
        c = card([("Javad Mahjoub", "Joel Faglier"), ("Julien LeBlanc", "Nick Galanti")])
        self.assertEqual(link_by_pair(c, named(4368, CFL_4368), 4368),
                         [(53619, 1), (53618, 2)])

    def test_fights_on_another_event_are_not_candidates(self):
        c = card([("Joaquin Buckley", "Mike Malott")])
        with self.assertRaises(LinkRefused):
            link_by_pair(c, named(4368, CFL_4368), 4542)

    def test_two_matching_rows_refuse(self):
        rows = named(1, [(1, "A B", "C D"), (2, "C D", "A B")])
        with self.assertRaises(LinkRefused):
            link_by_pair(card([("A B", "C D")]), rows, 1)


class TestDirectionAndComparison(unittest.TestCase):
    def test_named_bout_last_is_confirmed_first_is_contradicted(self):
        good = card([("Ana One", "Bea Two"), ("Joaquin Buckley", "Mike Malott")],
                    "UFC Fight Night: Buckley vs. Malott")
        self.assertEqual(direction(good)[0], "confirmed")
        bad = card([("Joaquin Buckley", "Mike Malott"), ("Ana One", "Bea Two")],
                   "UFC Fight Night: Buckley vs. Malott")
        self.assertEqual(direction(bad)[0], "contradicted")
        self.assertEqual(direction(card([("A B", "C D")], "UFC 400"))[0], "unconfirmable")

    def test_compare_orders(self):
        a = card([("A A", "B B"), ("C C", "D D"), ("E E", "F F")])
        b = SourceCard("wikipedia", None, None, None, tuple(
            SourceBout(walkout=i + 1, fighter_names=n, source_bout_id=str(i))
            for i, n in enumerate([("B B", "A A"), ("C C", "D D"), ("G G", "H H")])))
        r = compare_orders(a, b)
        self.assertEqual(r["shared"], 2)
        self.assertTrue(r["same_relative_order"])
        self.assertEqual(r["only_in_espn_scoreboard"], ["E E vs F F"])
        self.assertEqual(r["only_in_wikipedia"], ["G G vs H H"])


class TestEspnRefusals(unittest.TestCase):
    def test_a_start_time_going_backwards_is_not_a_running_order(self):
        data = {"events": [{"id": "1", "name": "X", "date": "2026-10-17T21:00Z", "competitions": [
            {"id": "a", "startDate": "2026-10-18T00:00Z", "competitors": [
                {"order": 1, "athlete": {"displayName": "A A"}},
                {"order": 2, "athlete": {"displayName": "B B"}}]},
            {"id": "b", "startDate": "2026-10-17T21:00Z", "competitors": [
                {"order": 1, "athlete": {"displayName": "C C"}},
                {"order": 2, "athlete": {"displayName": "D D"}}]}]}]}
        with self.assertRaises(SourceError):
            parse_espn_scoreboard(data)

    def test_a_bout_without_two_names_refuses(self):
        data = {"events": [{"id": "1", "competitions": [
            {"id": "a", "competitors": [{"athlete": {"displayName": "A A"}}]}]}]}
        with self.assertRaises(SourceError):
            parse_espn_scoreboard(data)


def _fixture(name: str) -> tuple[str, dict]:
    meta = json.loads((FIX / "SOURCES.json").read_text("utf-8"))[name]
    text = (FIX / name).read_text("utf-8")
    return text, meta


@unittest.skipUnless((FIX / "SOURCES.json").is_file(), "real samples not recorded")
class TestRealSamples(unittest.TestCase):
    """Real responses from a GitHub runner, 2026-10-21. See fixtures/SOURCES.json."""

    def test_every_fixture_is_what_the_run_printed(self):
        """Content-exact: the canonical sha256 the fetching run printed."""
        meta = json.loads((FIX / "SOURCES.json").read_text("utf-8"))
        for name, m in meta.items():
            with self.subTest(fixture=name):
                text = (FIX / name).read_text("utf-8")
                self.assertEqual(fixture_canonical_sha(name, text), m["canonical_sha256"])

    def espn(self, name):
        text, _ = _fixture(name)
        return parse_espn_scoreboard(json.loads(text))

    def test_espn_buckley_malott_is_first_walkout_first(self):
        [c] = self.espn("espn_scoreboard_20261017.json")
        self.assertEqual(c.event_name, "UFC Fight Night: Buckley vs. Malott")
        self.assertEqual(len(c.bouts), 13)
        self.assertEqual(direction(c)[0], "confirmed")
        self.assertTrue(same_pair(c.main_event.fighter_names, ("Joaquin Buckley", "Mike Malott")))

    def test_espn_links_completely_to_cfl_4368(self):
        [c] = self.espn("espn_scoreboard_20261017.json")
        links = link_by_pair(c, named(4368, CFL_4368), 4368)
        self.assertEqual(len(links), 13)
        self.assertEqual(dict(links)[46774], 13, "the main event must walk out last")
        self.assertFalse({47881, 48644, 50990} & {f for f, _ in links},
                         "a retired booking was linked")

    def test_espn_upcoming_card_links_to_cfl_4542(self):
        [c] = self.espn("espn_scoreboard_current.json")
        self.assertEqual(direction(c)[0], "confirmed")
        links = dict(link_by_pair(c, named(4542, CFL_4542), 4542))
        self.assertEqual(links[48438], len(c.bouts))
        self.assertNotIn(48648, links)

    def test_wikipedia_agrees_with_espn_on_the_completed_card(self):
        [e] = self.espn("espn_scoreboard_20261017.json")
        name = next(n for n in json.loads((FIX / "SOURCES.json").read_text("utf-8"))
                    if n.startswith("wikipedia_UFC_Fight_Night_Buckley"))
        text, _ = _fixture(name)
        w = parse_wikipedia_results(text, e.event_name)
        self.assertEqual(direction(SourceCard(w.source, None, e.event_name, None, w.bouts))[0],
                         "confirmed")
        r = compare_orders(e, w)
        self.assertEqual(r["shared"], 13, r)
        self.assertTrue(r["same_relative_order"], r)
        self.assertEqual(r["disagreements"], [], r)


if __name__ == "__main__":
    unittest.main()
