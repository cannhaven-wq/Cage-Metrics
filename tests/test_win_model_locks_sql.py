"""Static guards on the proposed PRED-001 forecast-lock migration.

The behaviour was checked against the real database in rolled-back
transactions (see research/protocol/verify_win_model_locks.sql and the
2026-10-13 HANDOFF entry). These keep the properties that behaviour depends on
from being edited out of the file before it is applied.
"""
import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
MIG = REPO / "research" / "protocol" / "proposed_2026-10-13_win_model_locks.sql"
VERIFY = REPO / "research" / "protocol" / "verify_win_model_locks.sql"


class WinModelLocksMigration(unittest.TestCase):
    sql = MIG.read_text()

    def test_append_only_for_every_operation(self):
        for op in ("update", "delete", "truncate"):
            self.assertRegex(self.sql, rf"before {op} on public\.win_model_locks",
                             f"no BEFORE {op.upper()} trigger")

    def test_lock_time_is_the_database_clock(self):
        self.assertIn("new.actual_lock_at := now();", self.sql)

    def test_guard_refuses_the_known_ways_to_lock_late_or_wrong(self):
        for needle in ("already has a result on file", "retired booking", "do not match fight",
                       "no start time can be established", "training_cutoff", "market snapshot"):
            self.assertIn(needle, self.sql)

    def test_private_to_both_browser_roles(self):
        self.assertIn("enable row level security", self.sql)
        self.assertRegex(self.sql, r"revoke all on public\.win_model_locks from anon, authenticated")
        self.assertRegex(self.sql, r"revoke all on public\.v_win_model_locks_graded from anon, authenticated")
        self.assertNotRegex(self.sql, r"(?i)grant\s+[^;]*\bto\s+(anon|authenticated)")
        self.assertIn("security_invoker = true", self.sql)

    def test_fails_fast_on_a_lock_wait(self):
        self.assertIn("set local lock_timeout", self.sql)

    def test_one_forecast_per_fight_per_build(self):
        self.assertIn("win_model_locks_one_per_build", self.sql)

    def test_still_marked_proposed(self):
        self.assertIn("STATUS: PROPOSED. NOT APPLIED.", self.sql)

    def test_verify_script_tests_these_exact_bytes(self):
        v = VERIFY.read_text()
        self.assertIn(self.sql, v, "verify_win_model_locks.sql no longer inlines the migration verbatim")
        self.assertEqual(len(re.findall(r"n := n \+ 1", v)), 10)
        self.assertIn("raise exception 'VERIFY-ROLLBACK", v)


if __name__ == "__main__":
    unittest.main()
