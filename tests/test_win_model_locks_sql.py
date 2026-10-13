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

    def test_lock_time_is_the_wall_clock_not_the_transaction_start(self):
        self.assertIn("new.actual_lock_at := clock_timestamp();", self.sql)
        self.assertNotRegex(self.sql, r"actual_lock_at\s*:=\s*now\(\)")

    def test_event_date_and_deadline_come_from_the_database(self):
        self.assertIn("select event_date into new.event_date from public.events", self.sql)
        self.assertIn("into v_start from public.v_fight_start_best where event_id = f.event_id", self.sql)
        # a fallback start counts from midnight UTC, never from 18:00
        self.assertIn("then (event_date::timestamp at time zone 'UTC') else start_at end", self.sql)

    def test_an_abstention_lock_is_allowed(self):
        self.assertIn("check (p_a is null or (p_a > 0 and p_a < 1))", self.sql)

    def test_quotes_agree_with_book_count(self):
        self.assertIn("jsonb_array_length(market_quotes) = market_book_count", self.sql)

    def test_market_snapshot_is_required(self):
        for col in ("market_p_a_vigfree    numeric not null", "market_quotes         jsonb   not null",
                    "market_captured_at    timestamptz not null"):
            self.assertIn(col, self.sql)

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

    def test_fails_fast_on_a_lock_wait_inside_one_transaction(self):
        self.assertRegex(self.sql, r"begin;\nset local lock_timeout")
        self.assertTrue(self.sql.rstrip().endswith("commit;"))

    def test_one_forecast_per_fight_per_experiment(self):
        self.assertIn("on public.win_model_locks (fight_id, experiment_id);", self.sql)

    def test_marked_applied_with_its_decision(self):
        self.assertIn("STATUS: APPLIED 2026-10-13 on the owner's approval (D-024)", self.sql)

    def test_verify_script_tests_these_exact_bytes(self):
        v = VERIFY.read_text()
        body = self.sql[self.sql.index("set local lock_timeout"):self.sql.rindex("commit;")].rstrip() + "\n"
        self.assertIn(body, v, "verify_win_model_locks.sql no longer inlines the migration body verbatim")
        self.assertEqual(len(re.findall(r"n := n \+ 1", v)), 12)
        self.assertIn("raise exception 'VERIFY-ROLLBACK", v)


if __name__ == "__main__":
    unittest.main()
