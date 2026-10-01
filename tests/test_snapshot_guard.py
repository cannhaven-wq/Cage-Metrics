"""The pre-fight snapshot must survive a column it does not have.

    python -m unittest tests/test_snapshot_guard.py -v

WHY THIS FILE EXISTS

`pre_fight_snapshots` carries the hard rule: no fight goes off without our
prediction already on record. The table is append-only and refuses to snapshot a
settled card, so a missed card is missed FOREVER -- there is no backfill, by
design.

On 2026-09-26 the snapshotter missed a whole card. Not because the cron was
dead, not because the window was wrong, and not because the data was bad: it
built all 12 rows, printed them, and then died probing for an optional column
that a proposed-but-unapplied migration had not added yet.

The guard for exactly that case was already there. It read:

    try:
        fetch_all(...)                      # raises SystemExit on HTTP 400
    except Exception:                       # SystemExit is NOT an Exception
        ...drop the column and carry on...

`SystemExit` inherits from `BaseException`, so the except clause never fired.
The protection read as though it worked and did nothing — the same shape as the
alerts pin trigger that was `SECURITY DEFINER` (D-020), and the same lesson:
**a guard is only real if something exercises it.**

UFC Fight Night: Rosas Jr. vs. Barcelos went off with 0 of 13 fights on record.
Those 13 are gone permanently. This test is what stops the fourteenth.

It calls the real function with a stubbed transport, so narrowing the except
clause, or swapping the probe for another fatal helper, fails here.
"""

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "cfl_engine" / "snapshot_predictions.py"


def load_module():
    spec = importlib.util.spec_from_file_location("snapshot_predictions", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestOptionalColumnProbe(unittest.TestCase):
    def setUp(self):
        self.mod = load_module()
        self.logged = []

    def _rows(self):
        # Two fights, each carrying both optional columns and the real payload.
        return [
            {"fight_id": 1, "model_pick_fighter_id": 10,
             "edge_model_edge_id": "e1", "edge_published_at": "2026-09-26T00:00:00Z"},
            {"fight_id": 2, "model_pick_fighter_id": 20,
             "edge_model_edge_id": "e2", "edge_published_at": "2026-09-26T00:00:00Z"},
        ]

    def test_missing_column_does_not_kill_the_run(self):
        """THE REGRESSION. A 400 on the probe must drop the column, not the card."""
        def boom(base_url, key, table, query):
            raise SystemExit(
                "ERROR GET pre_fight_snapshots?select=edge_model_edge_id -> "
                "HTTP 400: column pre_fight_snapshots.edge_model_edge_id does not exist")

        self.mod.fetch_all = boom
        rows = self._rows()
        try:
            out = self.mod._drop_unknown_columns("u", "k", rows, log=self.logged.append)
        except SystemExit as e:                        # the 2026-09-26 failure
            self.fail(
                "the optional-column probe killed the process instead of dropping "
                "the column — this is the defect that cost a whole card its "
                f"pre-fight record: {e}")

        self.assertEqual(len(out), 2, "rows were lost")
        for r in out:
            for col in self.mod.OPTIONAL_COLUMNS:
                self.assertNotIn(
                    col, r, f"{col} was not dropped after the table rejected it")
        # The operator has to be able to see it degraded, not just infer it.
        self.assertTrue(
            any("not present" in m for m in self.logged),
            "the fallback happened silently — a degraded snapshot must say so")

    def test_every_optional_column_is_probed_independently(self):
        """One missing column must not stop the others being checked."""
        seen = []

        def half_broken(base_url, key, table, query):
            seen.append(query)
            if "edge_model_edge_id" in query:
                raise SystemExit("HTTP 400: column does not exist")
            return []

        self.mod.fetch_all = half_broken
        self.mod._drop_unknown_columns("u", "k", self._rows(), log=self.logged.append)
        for col in self.mod.OPTIONAL_COLUMNS:
            self.assertTrue(any(col in q for q in seen),
                            f"{col} was never probed — an early failure short-circuited")

    def test_a_healthy_table_keeps_the_columns(self):
        """The guard must not strip columns that are genuinely there."""
        self.mod.fetch_all = lambda *a, **k: []
        out = self.mod._drop_unknown_columns("u", "k", self._rows(), log=self.logged.append)
        for r in out:
            self.assertIn("edge_model_edge_id", r,
                          "a present column was dropped — snapshots would lose precision")

    def test_the_probe_never_catches_a_keyboard_interrupt(self):
        """Broad is not the same as blind. Ctrl-C must still stop the run."""
        def interrupted(*a, **k):
            raise KeyboardInterrupt()

        self.mod.fetch_all = interrupted
        with self.assertRaises(KeyboardInterrupt):
            self.mod._drop_unknown_columns("u", "k", self._rows(), log=self.logged.append)


class TestGuardShape(unittest.TestCase):
    """Read the source too: the behavioural test above can be satisfied by a
    bare `except BaseException`, which would also swallow Ctrl-C and a real
    MemoryError. The clause must name what it means."""

    def test_the_except_clause_names_SystemExit(self):
        src = SRC.read_text(encoding="utf-8")
        start = src.index("def _drop_unknown_columns")
        body = src[start:start + 2500]
        self.assertIn("SystemExit", body,
                      "the probe's except clause no longer names SystemExit — "
                      "the transport raises it, and `except Exception` cannot catch it")
        self.assertNotIn("except BaseException", body,
                         "the probe catches BaseException, which also swallows "
                         "KeyboardInterrupt and MemoryError")


if __name__ == "__main__":
    unittest.main()
