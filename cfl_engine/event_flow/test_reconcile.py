"""Reconciliation proposes. It cannot act, and the tests prove that."""
from __future__ import annotations

import copy
import inspect
import unittest

from cfl_engine.event_flow import reconcile as rec
from cfl_engine.event_flow.reconcile import (
    ABSENT_FROM_CARD,
    DUPLICATE_FIGHTER,
    MAIN_EVENT_CONFLICT,
    MISSING_FROM_DB,
    NO_ACTION,
    PROPOSE_INACTIVE,
    PROPOSE_INSERT,
    PROPOSE_REVIEW,
    reconcile,
)
from cfl_engine.event_flow.ufcstats_card import parse_event_page

EVENT = {"id": 4433, "name": "UFC 331: Van vs. Pantoja 2"}

# The live UFCStats card: 12 bouts, page order (main event first).
PAGE = [
    ("568ec6af4008355a", "Joshua Van", "Alexandre Pantoja"),
    ("fe612d20eec7ef35", "Arman Tsarukyan", "Mauricio Ruffy"),
    ("f7810c98786c3dd8", "Patricio Pitbull", "Dooho Choi"),
    ("023ce4fa7b7b76f9", "Gable Steveson", "Sean Sharaf"),
    ("196c64693a2ce308", "Alonzo Menifield", "Iwo Baraniewski"),
    ("d0361fe28d05a0b5", "Marlon Vera", "Charles Jourdain"),
    ("3f2d637ffb324a51", "Tai Tuivasa", "Robelis Despaigne"),
    ("d89cc2cb92cd8407", "Michael Aswell Jr.", "JooSang Yoo"),
    ("51789f77811b1817", "Ryan Gandra", "Ozzy Diaz"),
    ("9be47241c960d082", "Edmen Shahbazyan", "Brunno Ferreira"),
    ("73304588cef4f88b", "Casey O'Neill", "Eduarda Moura"),
    ("2e35163040eb3189", "Giga Chikadze", "Joanderson Brito"),
]

# The 13 rows CFL actually holds for event 4433. Real ids.
DB = [
    (47325, "568ec6af4008355a", "Joshua Van", "Alexandre Pantoja", True),
    (47326, "fe612d20eec7ef35", "Arman Tsarukyan", "Mauricio Ruffy", False),
    (47327, "f7810c98786c3dd8", "Patricio Pitbull", "Dooho Choi", False),
    (47328, "e94b96416deaa28f", "Renato Moicano", "Brian Ortega", False),   # cancelled
    (47329, "196c64693a2ce308", "Alonzo Menifield", "Iwo Baraniewski", False),
    (47330, "023ce4fa7b7b76f9", "Gable Steveson", "Sean Sharaf", False),
    (47331, "d0361fe28d05a0b5", "Marlon Vera", "Charles Jourdain", False),
    (47332, "3f2d637ffb324a51", "Tai Tuivasa", "Robelis Despaigne", False),
    (47333, "9be47241c960d082", "Edmen Shahbazyan", "Brunno Ferreira", False),
    (47334, "2e35163040eb3189", "Giga Chikadze", "Joanderson Brito", False),
    (47335, "73304588cef4f88b", "Casey O'Neill", "Eduarda Moura", False),
    (47336, "51789f77811b1817", "Ryan Gandra", "Ozzy Diaz", False),
    (47337, "d89cc2cb92cd8407", "Michael Aswell Jr.", "JooSang Yoo", False),
]


def page_html(rows):
    trs = "".join(
        f'<tr data-link="http://ufcstats.com/fight-details/{fid}">'
        f'<td class="b-fight-details__table-col l-page_align_left">'
        f'<p><a href="http://ufcstats.com/fighter-details/{"a" * 16}" class="b-link">{a}</a></p>'
        f'<p><a href="http://ufcstats.com/fighter-details/{"b" * 16}" class="b-link">{b}</a></p>'
        f"</td></tr>"
        for fid, a, b in rows
    )
    return f"<html><body><table><tbody>{trs}</tbody></table></body></html>"


def db_rows(extra=None, drop=None):
    rows = []
    for i, (fid, ufc, a, b, main) in enumerate(DB):
        if drop and fid in drop:
            continue
        rows.append({"id": fid, "ufc_fight_id": ufc, "fighter_a_name": a,
                     "fighter_b_name": b, "is_main_event": main,
                     "fighter_a_id": 1000 + i * 2, "fighter_b_id": 1001 + i * 2})
    return rows + list(extra or [])


def run(page=None, db=None):
    return reconcile(EVENT, parse_event_page(page_html(page or PAGE)).bouts,
                     db if db is not None else db_rows())


class TestUFC331(unittest.TestCase):
    """The primary case: one pre-existing cancelled booking, 12 live bouts."""

    def test_moicano_ortega_is_the_only_finding(self):
        r = run()
        self.assertEqual(r.page_bout_count, 12)
        self.assertEqual(r.db_fight_count, 13)
        self.assertEqual(len(r.findings), 1)

        f = r.findings[0]
        self.assertEqual(f.cfl_fight_id, 47328)
        self.assertEqual(f.matchup, "Renato Moicano vs Brian Ortega")
        self.assertEqual(f.kind, ABSENT_FROM_CARD)
        self.assertEqual(f.action, PROPOSE_INACTIVE)
        self.assertIs(f.evidence["on_live_card"], False)

    def test_the_twelve_live_bouts_are_untouched(self):
        r = run()
        flagged = {f.cfl_fight_id for f in r.findings}
        for fid, *_ in DB:
            if fid != 47328:
                self.assertNotIn(fid, flagged, f"live bout {fid} was flagged")
        self.assertEqual(r.proposed_inactive, (47328,))

    def test_the_report_names_the_evidence(self):
        text = run().report()
        self.assertIn("READ ONLY", text)
        self.assertIn("Renato Moicano vs Brian Ortega", text)
        self.assertIn("absent from the current UFCStats card", text)

    def test_an_already_inactive_booking_proposes_nothing(self):
        rows = db_rows()
        for row in rows:
            if row["id"] == 47328:
                row["is_active"] = False
        r = reconcile(EVENT, parse_event_page(page_html(PAGE)).bouts, rows)
        self.assertEqual(r.findings[0].action, NO_ACTION)
        self.assertEqual(r.proposed_inactive, ())

    def test_a_card_that_matches_exactly_is_clean(self):
        r = run(db=db_rows(drop={47328}))
        self.assertTrue(r.clean)
        self.assertIn("No differences", r.report())


class TestOtherAnomalies(unittest.TestCase):
    def test_a_bout_on_the_card_with_no_row_is_proposed_for_insert(self):
        r = run(db=db_rows(drop={47334}))
        kinds = {(f.kind, f.action) for f in r.findings}
        self.assertIn((MISSING_FROM_DB, PROPOSE_INSERT), kinds)
        missing = next(f for f in r.findings if f.kind == MISSING_FROM_DB)
        self.assertEqual(missing.ufc_fight_id, "2e35163040eb3189")
        self.assertIsNone(missing.cfl_fight_id)

    def test_one_fighter_in_two_LIVE_bouts_needs_a_person(self):
        rows = db_rows()
        rows[1]["fighter_a_id"] = rows[0]["fighter_a_id"]      # both on the card
        r = reconcile(EVENT, parse_event_page(page_html(PAGE)).bouts, rows)
        dupes = [f for f in r.findings if f.kind == DUPLICATE_FIGHTER]
        self.assertEqual(len(dupes), 2)
        self.assertTrue(all(f.action == PROPOSE_REVIEW for f in dupes),
                        "a duplicate was auto-resolved instead of escalated")

    def test_a_stale_booking_is_not_also_reported_as_a_duplicate(self):
        """47328 shares no fighter with a live bout, but the principle holds:
        finding 1 owns it, and the duplicate check looks only at live bouts."""
        r = run()
        self.assertEqual([f.kind for f in r.findings], [ABSENT_FROM_CARD])

    def test_two_live_main_events_need_a_person(self):
        rows = db_rows()
        rows[1]["is_main_event"] = True
        r = reconcile(EVENT, parse_event_page(page_html(PAGE)).bouts, rows)
        conflicts = [f for f in r.findings if f.kind == MAIN_EVENT_CONFLICT]
        self.assertEqual(len(conflicts), 2)
        self.assertTrue(all(f.action == PROPOSE_REVIEW for f in conflicts))

    def test_findings_are_deterministic(self):
        a, b = run().findings, run().findings
        self.assertEqual([f.line() for f in a], [f.line() for f in b])
        shuffled = list(reversed(db_rows()))
        c = reconcile(EVENT, parse_event_page(page_html(PAGE)).bouts, shuffled)
        self.assertEqual([f.line() for f in a], [f.line() for f in c.findings],
                         "row order changed the report")


class TestCannotMutateProductionState(unittest.TestCase):
    """The safety property. Reconciliation proposes and never acts."""

    @staticmethod
    def _code_only() -> str:
        """The module's source with docstrings stripped.

        Scanning raw text would match the word "winner" in a docstring and the
        word INSERT inside `PROPOSE_INSERT`, which proves nothing. What matters
        is what the code imports and calls.
        """
        import ast
        tree = ast.parse(inspect.getsource(rec))
        for node in ast.walk(tree):
            if (isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
                    and ast.get_docstring(node)):
                node.body = node.body[1:]
        return ast.unparse(tree)

    def test_the_module_imports_nothing_capable_of_io(self):
        """Every import in the file, checked against an allowlist."""
        import ast
        imported = set()
        for node in ast.walk(ast.parse(inspect.getsource(rec))):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertEqual(
            imported - {"dataclasses", "__future__"}, set(),
            "reconcile.py imports something beyond dataclasses — it is meant to "
            "be pure, and an import is how IO gets in")

    def test_the_code_performs_no_write_and_no_io(self):
        code = self._code_only()
        for forbidden in ("supabase", "urllib", "requests", "psycopg",
                          "open(", "environ", "getenv", "subprocess",
                          "execute", "commit(", "PATCH", "POST"):
            self.assertNotIn(forbidden, code,
                             f"reconcile.py's code references {forbidden!r}")

    def test_the_module_defines_no_function_that_writes(self):
        """Nothing here takes a connection, a url or a key."""
        for name, fn in inspect.getmembers(rec, inspect.isfunction):
            params = set(inspect.signature(fn).parameters)
            self.assertFalse(
                params & {"conn", "cursor", "base_url", "key", "session", "client"},
                f"{name}() takes a write-capable argument: {params}")

    def test_reconciling_does_not_mutate_its_inputs(self):
        rows = db_rows()
        before = copy.deepcopy(rows)
        bouts = parse_event_page(page_html(PAGE)).bouts
        reconcile(EVENT, bouts, rows)
        self.assertEqual(rows, before, "reconcile mutated the fight rows it was given")

    def test_running_it_twice_changes_nothing(self):
        rows = db_rows()
        first = reconcile(EVENT, parse_event_page(page_html(PAGE)).bouts, rows)
        second = reconcile(EVENT, parse_event_page(page_html(PAGE)).bouts, rows)
        self.assertEqual([f.line() for f in first.findings],
                         [f.line() for f in second.findings])

    def test_every_action_is_a_proposal(self):
        """No action verb in the vocabulary applies anything."""
        rows = db_rows(drop={47334})
        rows[1]["is_main_event"] = True
        r = reconcile(EVENT, parse_event_page(page_html(PAGE)).bouts, rows)
        self.assertTrue(r.findings)
        for f in r.findings:
            self.assertIn(f.action,
                          {PROPOSE_INACTIVE, PROPOSE_INSERT, PROPOSE_REVIEW, NO_ACTION})

    def test_no_cancellation_is_inferred_from_a_missing_winner(self):
        """`winner_id` is not consulted. It conflates cancellations with
        ungraded history — 192 rows carry it, the earliest from 1995."""
        self.assertNotIn("winner", self._code_only(),
                         "winner_id is consulted in executable code")
        rows = db_rows()
        for row in rows:
            row["winner_id"] = None          # every fight ungraded
        r = reconcile(EVENT, parse_event_page(page_html(PAGE)).bouts, rows)
        self.assertEqual(r.proposed_inactive, (47328,),
                         "a missing winner was treated as evidence of cancellation")


if __name__ == "__main__":
    unittest.main()
