"""Tests for the integrity check catalogue and its runner.

    python -m unittest cfl_engine.integrity.test_integrity -v

These cannot check the counts — that needs the database, and the counts were
verified against it on 2026-09-16 (all 21 matched, see
research/integrity/DATA_INTEGRITY_AUDIT_2026-09-16.md). What they can check is
that the catalogue stays honest: every check reads and never writes, every one
says in plain English why it matters, and every one names who decides.
"""
from __future__ import annotations

import re
import unittest

from cfl_engine.integrity import checks as mod
from cfl_engine.integrity.checks import AUTO, CHECKS, L3, NOTE, REVIEW, by_key


def run_audit_dir() -> str:
    import cfl_engine.integrity.run_audit as ra
    from pathlib import Path
    return str(Path(ra.__file__).parent)

WRITE_WORDS = re.compile(
    r"\b(insert|update|delete|truncate|drop|alter|create|grant|revoke|copy|"
    r"merge|upsert|refresh|vacuum|call|do)\b",
    re.I,
)


class TestCatalogue(unittest.TestCase):
    def test_there_are_checks(self):
        self.assertGreaterEqual(len(CHECKS), 20)

    def test_keys_are_unique(self):
        keys = [c.key for c in CHECKS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_every_check_is_read_only(self):
        """The whole catalogue is SELECT. A check that writes is not a check."""
        for c in CHECKS:
            with self.subTest(check=c.key):
                sql = c.sql.strip()
                self.assertTrue(sql.lower().startswith("select"),
                                f"{c.key} does not start with SELECT")
                hit = WRITE_WORDS.search(sql)
                self.assertIsNone(hit, f"{c.key} contains a write keyword: {hit}")
                self.assertNotIn(";", sql, f"{c.key} contains a statement separator")

    def test_every_check_returns_a_column_named_n(self):
        """run_audit wraps each query and selects `n` from it."""
        for c in CHECKS:
            with self.subTest(check=c.key):
                self.assertRegex(c.sql, r"\bn\b", f"{c.key} has no column n")

    def test_every_classification_is_one_of_the_four(self):
        allowed = {AUTO, REVIEW, L3, NOTE}
        for c in CHECKS:
            with self.subTest(check=c.key):
                self.assertIn(c.classification, allowed)

    def test_every_check_explains_itself_without_jargon(self):
        """`why` is read by somebody who does not write SQL. It has to be a real
        sentence, and it must not lean on words the audience does not have."""
        banned = ("foreign key", "cardinality", "referential", "null-safe",
                  "left join", "cte", "idempotent")
        for c in CHECKS:
            with self.subTest(check=c.key):
                self.assertGreater(len(c.why), 60, f"{c.key}: why is too short to be an explanation")
                self.assertTrue(c.why.rstrip().endswith("."), f"{c.key}: why is not a sentence")
                low = c.why.lower()
                for word in banned:
                    self.assertNotIn(word, low, f"{c.key}: '{word}' is jargon")

    def test_titles_are_present_and_distinct(self):
        titles = [c.title for c in CHECKS]
        self.assertEqual(len(titles), len(set(titles)))
        for c in CHECKS:
            self.assertGreater(len(c.title), 10)

    def test_baselines_are_non_negative(self):
        for c in CHECKS:
            with self.subTest(check=c.key):
                self.assertGreaterEqual(c.baseline, 0)

    def test_by_key_finds_and_raises(self):
        self.assertEqual(by_key("orphan_rows").key, "orphan_rows")
        with self.assertRaises(KeyError):
            by_key("no_such_check")


class TestClassificationDiscipline(unittest.TestCase):
    """The classifications are the governance surface. If AUTO can be applied to
    anything that rewrites history, the ladder is decorative."""

    # Every defect whose only honest repair would delete or invent an
    # observation. None of these may ever be AUTO.
    NEVER_AUTO = {
        "odds_epoch_capture_time",        # we do not know when those were seen
        "odds_fighter_not_in_fight",      # the price was really taken; on what, is the question
        "preds_fighter_not_in_fight",     # the pick was really published
        "duplicate_bout_same_event",      # one of the two is real history
        "settled_card_fight_with_no_result",
        "odds_resolved_market_as_closer",
        "odds_side_contradicts_fighter",
        "fighter_twice_on_modern_card",
        "odds_extreme_price",
        "multi_main_event",
    }

    def test_history_touching_checks_are_never_auto(self):
        for key in self.NEVER_AUTO:
            with self.subTest(check=key):
                self.assertNotEqual(
                    by_key(key).classification, AUTO,
                    f"{key} is classified AUTO, but fixing it means deleting or "
                    f"inventing an observation",
                )

    def test_auto_checks_are_all_currently_clean(self):
        """Everything marked safe-to-fix stands at zero. Marking a defect that
        actually exists as AUTO and then not fixing it is the worst of both."""
        for c in CHECKS:
            if c.classification == AUTO:
                with self.subTest(check=c.key):
                    self.assertEqual(
                        c.baseline, 0,
                        f"{c.key} is AUTO with a baseline of {c.baseline} — either "
                        f"fix it or reclassify it",
                    )

    def test_l3_checks_exist_and_are_named(self):
        l3 = [c.key for c in CHECKS if c.classification == L3]
        self.assertGreaterEqual(len(l3), 1)
        self.assertIn("odds_resolved_market_as_closer", l3)

    def test_note_checks_are_not_reported_as_regressions(self):
        """`fights_with_a_bell_time` counts a thing we want to go UP. Treating
        that as a regression would train everyone to ignore the report."""
        self.assertEqual(by_key("fights_with_a_bell_time").classification, NOTE)


class TestRunner(unittest.TestCase):
    def test_runner_only_ever_calls_the_read_only_rpc(self):
        """Every request it makes goes to one endpoint, and it sends no Prefer
        header — which is the header PostgREST writes need. Combined with the
        SELECT-only guard inside count_rpc.sql, there is no path from this
        script to a write."""
        import inspect
        from cfl_engine.integrity import run_audit
        src = inspect.getsource(run_audit)
        endpoints = re.findall(r"\{base_url\}(/rest/v1[^\"\']*)", src)
        self.assertEqual(endpoints, ["/rest/v1/rpc/{RPC}"],
                         f"runner touches endpoints other than the RPC: {endpoints}")
        self.assertNotIn("Prefer", src, "runner sends a Prefer header")
        self.assertEqual(src.count("method=\"POST\""), 1)

    def test_the_rpc_migration_refuses_anything_but_select(self):
        """The guard is in the SQL, so it is asserted against the SQL."""
        from pathlib import Path
        sql = (Path(run_audit_dir()) / "count_rpc.sql").read_text(encoding="utf-8")
        self.assertIn("security invoker", sql.lower())
        self.assertIn("set local transaction read only", sql.lower())
        self.assertIn("only runs SELECT", sql)
        self.assertIn("no semicolons", sql)
        self.assertIn("revoke all on function public.cfl_integrity_count(text) "
                      "from public, anon, authenticated", sql)
        self.assertNotIn("security definer", sql.lower())

    def test_runner_requires_a_service_key(self):
        import os
        from cfl_engine.integrity import run_audit
        saved = {k: os.environ.pop(k, None)
                 for k in ("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY",
                           "SUPABASE_SERVICE_KEY")}
        try:
            with self.assertRaises(SystemExit) as cm:
                run_audit.env_key()
            self.assertIn("clean database", str(cm.exception))
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_module_constants_line_up(self):
        from cfl_engine.integrity import run_audit
        self.assertEqual(run_audit.RPC, "cfl_integrity_count")
        self.assertIs(run_audit.NOTE, mod.NOTE)


if __name__ == "__main__":
    unittest.main()
