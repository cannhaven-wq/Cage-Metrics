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
                    if n.startswith("wikipedia_UFC_Fight_Night__Buckley"))
        text, _ = _fixture(name)
        w = parse_wikipedia_results(text, e.event_name)
        self.assertEqual(direction(SourceCard(w.source, None, e.event_name, None, w.bouts))[0],
                         "confirmed")
        r = compare_orders(e, w)
        self.assertEqual(r["shared"], 13, r)
        self.assertTrue(r["same_relative_order"], r)
        self.assertEqual(r["disagreements"], [], r)

    def test_wikipedia_agrees_with_espn_on_the_upcoming_card(self):
        """UFC 333: three sections (early prelims, prelims, main card) and two
        sources that spell four fighters differently still agree on all 14."""
        [e] = self.espn("espn_scoreboard_current.json")
        text, _ = _fixture("wikipedia_UFC_333_rev1381287088.wikitext")
        w = parse_wikipedia_results(text, e.event_name)
        self.assertEqual(len(w.bouts), 14)
        r = compare_orders(e, w)
        self.assertEqual((r["shared"], r["disagreements"]), (14, []), r)
        # Section starts never go backwards along the walkout order, and there
        # are three sections.
        starts = [b.section_start for b in e.bouts]
        self.assertEqual(starts, sorted(starts))
        self.assertEqual(len(set(starts)), 3)

    def test_wikipedia_piped_links_and_champion_marks(self):
        text, _ = _fixture("wikipedia_UFC_333_rev1381287088.wikitext")
        w = parse_wikipedia_results(text)
        names = {n for b in w.bouts for n in b.fighter_names}
        self.assertIn("Alexander Volkov", names)       # [[Alexander Volkov (fighter)|...]]
        self.assertIn("Alexander Volkanovski", names)  # "(c)" dropped
        self.assertIn("Daniel Santos", names)
        self.assertEqual(w.main_event.fighter_names, ("Alexander Volkanovski", "Movsar Evloev"))


if __name__ == "__main__":
    unittest.main()


class _EspnRest:
    """`fights` + `fighters` + an append-only ledger, for the ESPN path end to end."""

    INACTIVE = {47881, 48644, 50990}

    def __init__(self, event_id, rows):
        import datetime as dt
        self.event_id = event_id
        self.fighters, self.fights = {}, []
        for fid, a, b in rows:
            ia, ib = len(self.fighters) + 1, len(self.fighters) + 2
            self.fighters[ia], self.fighters[ib] = a, b
            self.fights.append({"id": fid, "ufc_fight_id": f"{fid:016x}", "event_id": event_id,
                                "is_active": fid not in self.INACTIVE,
                                "fighter_a_id": ia, "fighter_b_id": ib})
        self.ledger, self.clock = [], dt.datetime(2026, 10, 15, tzinfo=dt.timezone.utc)

    def rest_get(self, base_url, key, path, params):
        if path == "fights":
            return [dict(f) for f in self.fights]
        if path == "fighters":
            ids = [int(x) for x in params["id"][4:-1].split(",")]
            return [{"id": i, "name": self.fighters[i]} for i in ids]
        if path == "fight_bout_order":
            src = params["source"][3:]
            return sorted((r for r in self.ledger if r["source"] == src),
                          key=lambda r: (r["observed_at"], r["id"]), reverse=True)
        raise AssertionError(path)

    def rest_append(self, base_url, key, path, rows):
        import datetime as dt
        assert path == "fight_bout_order", path
        self.clock += dt.timedelta(hours=12)
        for r in rows:
            self.ledger.append({**r, "id": len(self.ledger) + 1,
                                "observed_at": self.clock.isoformat()})
        return len(rows)


@unittest.skipUnless((FIX / "SOURCES.json").is_file(), "real samples not recorded")
class TestIngestFromEspn(unittest.TestCase):
    """The ingester's --source espn path on the real 2026-10-17 scoreboard."""

    EVENT = {"id": 4368, "name": "UFC Fight Night: Buckley vs. Malott",
             "event_date": "2026-10-17", "ufc_event_id": "55e94a9b525dcf45"}

    def run_once(self, rest, execute=True, page=None, event=None):
        import cfl_engine.event_flow.ingest_bout_order as ing
        page = page or _fixture("espn_scoreboard_20261017.json")[0]
        lines = []
        get, append = ing.rest_get, ing.rest_append
        ing.rest_get, ing.rest_append = rest.rest_get, rest.rest_append
        try:
            out = ing.ingest_event(event or self.EVENT, "https://x", "k", execute,
                                   page_html=page, log=lines.append, source="espn")
        finally:
            ing.rest_get, ing.rest_append = get, append
        return out, "\n".join(lines)

    def test_writes_the_whole_card_first_walkout_first(self):
        rest = _EspnRest(4368, CFL_4368)
        out, log = self.run_once(rest)
        self.assertEqual(out, "written", log)
        self.assertEqual(len(rest.ledger), 13)
        self.assertEqual({r["source"] for r in rest.ledger}, {"espn_scoreboard"})
        order = {r["fight_id"]: r["bout_order"] for r in rest.ledger}
        self.assertEqual(order[46774], 13)                     # Buckley vs Malott
        self.assertEqual(order[47879], 12)                     # Blanchfield vs Jasudavicius
        self.assertEqual(order[51091], 1)                      # You vs Chovancek
        self.assertEqual(sorted(order.values()), list(range(1, 14)))
        self.assertFalse(set(order) & _EspnRest.INACTIVE)
        self.assertIn("3 fight row(s) on this event are not on the page", log)
        # unchanged on the second read
        self.assertEqual(self.run_once(rest)[0], "unchanged")
        self.assertEqual(len(rest.ledger), 13)

    def test_a_dry_run_writes_nothing(self):
        rest = _EspnRest(4368, CFL_4368)
        self.assertEqual(self.run_once(rest, execute=False)[0], "dry-run")
        self.assertEqual(rest.ledger, [])

    def test_refuses_when_no_espn_event_matches_the_cfl_event(self):
        rest = _EspnRest(4368, CFL_4368)
        event = {**self.EVENT, "name": "UFC Fight Night: Somebody vs. Else"}
        out, log = self.run_once(rest, event=event)
        self.assertEqual(out, "refused")
        self.assertEqual(rest.ledger, [])

    def test_refuses_a_card_that_does_not_link_completely(self):
        rest = _EspnRest(4368, [r for r in CFL_4368 if r[0] != 47884])   # drop Jourdain
        out, log = self.run_once(rest)
        self.assertEqual(out, "refused", log)
        self.assertIn("Louis Jourdain", log)
        self.assertEqual(rest.ledger, [])

    def test_refuses_an_inverted_card(self):
        data = json.loads(_fixture("espn_scoreboard_20261017.json")[0])
        comps = data["events"][0]["competitions"]
        data["events"][0]["competitions"] = list(reversed(comps))
        for c in data["events"][0]["competitions"]:       # keep start times monotone
            c["startDate"] = c["date"] = "2026-10-17T21:00Z"
        out, log = self.run_once(_EspnRest(4368, CFL_4368), page=json.dumps(data))
        self.assertEqual(out, "refused", log)
        self.assertIn("backwards", log)


if __name__ == "__main__":
    unittest.main()
