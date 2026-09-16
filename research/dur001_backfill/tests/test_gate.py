"""Tests for the DUR-001 backfill spec gate.

    python -m unittest discover -s research/dur001_backfill/tests

The gate's whole job is to refuse. So most of these assert that a specific
malformed spec is rejected with a specific code — and one asserts that a fully
correct spec is allowed, because a gate that refuses everything is no safer than
one that refuses nothing, it just fails differently.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")))

from research.dur001_backfill.gate import (  # noqa: E402
    assert_clear,
    check,
    explain,
    is_clear,
)
from research.dur001_backfill.spec import (  # noqa: E402
    LOCKED_MODEL_VERSION,
    BackfillRow,
    BackfillSpec,
    SpecViolation,
)

START = dt.datetime(2026, 5, 1, 22, 0, tzinfo=dt.timezone.utc)
CUTOFF = dt.datetime(2026, 5, 1, 0, 0, tzinfo=dt.timezone.utc)


def good_rows(n=3):
    return tuple(
        BackfillRow(fight_id=i, fight_start=START, training_cutoff=CUTOFF)
        for i in range(1, n + 1)
    )


def good_spec(**over):
    base = dict(
        model_version="PROP-0001-BACKFILL@v1",
        target_table="research_backfill_results",
        timing_rule="t10_earliest_observed_start",
        timing_rule_approved=True,
        writes_to_database=False,
        uses_odds_api=False,
        rows=good_rows(),
    )
    base.update(over)
    return BackfillSpec(**base)


def codes(spec):
    return {v.code for v in check(spec)}


class TestCleanSpecPasses(unittest.TestCase):
    def test_a_correct_spec_is_clear(self):
        self.assertEqual(check(good_spec()), [])
        self.assertTrue(is_clear(good_spec()))

    def test_assert_clear_does_not_raise(self):
        assert_clear(good_spec())

    def test_explain_says_clear(self):
        self.assertIn("GATE CLEAR", explain(good_spec()))

    def test_either_timing_rule_is_acceptable_once_approved(self):
        self.assertTrue(is_clear(good_spec(timing_rule="self_consistent_walkback")))


class TestLockLedgerIsUntouchable(unittest.TestCase):
    """PREREGISTRATION §13: never written to prop_model_locks."""

    def test_targeting_the_lock_table_is_refused(self):
        self.assertIn("LOCK_TABLE", codes(good_spec(target_table="prop_model_locks")))

    def test_lock_table_check_is_case_insensitive(self):
        self.assertIn("LOCK_TABLE", codes(good_spec(target_table="PROP_MODEL_LOCKS")))

    def test_lock_table_check_ignores_surrounding_space(self):
        self.assertIn("LOCK_TABLE", codes(good_spec(target_table="  prop_model_locks ")))

    def test_other_append_only_ledgers_are_refused(self):
        for t in ("prop_odds", "fight_odds", "pre_fight_snapshots"):
            with self.subTest(table=t):
                self.assertIn("FORBIDDEN_TABLE", codes(good_spec(target_table=t)))

    def test_any_database_write_is_refused(self):
        self.assertIn("DB_WRITE", codes(good_spec(writes_to_database=True)))


class TestDistinctModelVersion(unittest.TestCase):
    def test_reusing_the_live_lock_version_is_refused(self):
        self.assertIn("MODEL_VERSION", codes(good_spec(model_version=LOCKED_MODEL_VERSION)))

    def test_empty_version_is_refused(self):
        self.assertIn("MODEL_VERSION", codes(good_spec(model_version="")))

    def test_whitespace_only_version_is_refused(self):
        self.assertIn("MODEL_VERSION", codes(good_spec(model_version="   ")))

    def test_a_distinct_version_is_accepted(self):
        self.assertNotIn("MODEL_VERSION", codes(good_spec(model_version="PROP-0001-HIST@v2")))


class TestWalkForwardRows(unittest.TestCase):
    """training_cutoff must be strictly before fight_start, per row."""

    def test_cutoff_after_start_is_refused(self):
        bad = (BackfillRow(1, START, START + dt.timedelta(hours=1)),)
        self.assertIn("LEAKY_ROW", codes(good_spec(rows=bad)))

    def test_cutoff_equal_to_start_is_refused(self):
        """Equal is still a leak — the comparison is strict on purpose."""
        bad = (BackfillRow(1, START, START),)
        self.assertIn("LEAKY_ROW", codes(good_spec(rows=bad)))

    def test_one_bad_row_among_many_is_caught(self):
        rows = good_rows(20) + (BackfillRow(999, START, START + dt.timedelta(seconds=1)),)
        self.assertIn("LEAKY_ROW", codes(good_spec(rows=rows)))

    def test_message_names_the_offending_fights(self):
        rows = (BackfillRow(4242, START, START),)
        msg = [v.message for v in check(good_spec(rows=rows)) if v.code == "LEAKY_ROW"][0]
        self.assertIn("4242", msg)

    def test_message_truncates_a_long_list(self):
        rows = tuple(BackfillRow(i, START, START) for i in range(1, 12))
        msg = [v.message for v in check(good_spec(rows=rows)) if v.code == "LEAKY_ROW"][0]
        self.assertIn("+6 more", msg)

    def test_empty_row_set_is_refused(self):
        self.assertIn("NO_ROWS", codes(good_spec(rows=())))


class TestTimingRule(unittest.TestCase):
    """Amendment item (i) is unapproved, so a backfill cannot run yet."""

    def test_unset_rule_is_refused(self):
        self.assertIn("TIMING_RULE", codes(good_spec(timing_rule=None)))

    def test_unknown_rule_is_refused(self):
        self.assertIn("TIMING_RULE", codes(good_spec(timing_rule="whatever_looks_best")))

    def test_known_but_unapproved_rule_is_refused(self):
        c = codes(good_spec(timing_rule_approved=False))
        self.assertIn("TIMING_UNAPPROVED", c)
        self.assertNotIn("TIMING_RULE", c)

    def test_default_spec_refuses_on_the_timing_rule(self):
        """A spec built with no arguments must not be permissive."""
        self.assertIn("TIMING_RULE", codes(BackfillSpec()))


class TestCredits(unittest.TestCase):
    def test_odds_api_use_is_refused(self):
        self.assertIn("ODDS_API", codes(good_spec(uses_odds_api=True)))


class TestRefusalBehaviour(unittest.TestCase):
    def test_assert_clear_raises_spec_violation(self):
        with self.assertRaises(SpecViolation):
            assert_clear(good_spec(target_table="prop_model_locks"))

    def test_exception_carries_every_violation(self):
        spec = BackfillSpec(target_table="prop_model_locks")   # many things wrong
        with self.assertRaises(SpecViolation) as ctx:
            assert_clear(spec)
        self.assertGreater(len(ctx.exception.violations), 1)

    def test_exception_message_points_at_the_preregistration(self):
        with self.assertRaises(SpecViolation) as ctx:
            assert_clear(BackfillSpec())
        self.assertIn("PREREGISTRATION.md", str(ctx.exception))

    def test_all_violations_reported_not_just_the_first(self):
        spec = good_spec(target_table="prop_model_locks",
                         model_version=LOCKED_MODEL_VERSION,
                         uses_odds_api=True)
        self.assertEqual({"LOCK_TABLE", "MODEL_VERSION", "ODDS_API"}, codes(spec))

    def test_explain_lists_refusals(self):
        out = explain(good_spec(target_table="prop_model_locks"))
        self.assertIn("GATE REFUSED", out)
        self.assertIn("LOCK_TABLE", out)
        self.assertIn("Do not edit the gate", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
