"""Tests for the DUR-001 dead-man alert.

    python -m unittest cfl_engine/dur001/test_alert.py -v

The grading functions are pure on purpose — they take ages in hours and return
(level, message) pairs — so the whole alert can be tested without a database,
a webhook, or a clock.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from alert import (  # noqa: E402
    CAPTURE_MAX_AGE_H,
    CAPTURE_MAX_AGE_FAR_H,
    NEAR_CARD_HOURS,
    fmt_age,
    grade_extra,
    grade_locks,
    hours_since,
    overall,
)


def levels(lines):
    return [lvl for lvl, _ in lines]


def text(lines):
    return " | ".join(msg for _, msg in lines)


class TestSilentCaptureNearCard(unittest.TestCase):
    """The failure this alert exists for: one stream stalls, the other does not."""

    def test_silent_capture_near_card_is_red(self):
        """A totals-only stall must be RED and must name totals.

        prop_age 5.0h is past CAPTURE_MAX_AGE_H; ml_age 1.0h is healthy. Grading
        the two together on the newer age would call this fine and lose the
        card's closing totals silently.
        """
        lines = grade_extra(hours_to_card=6.0, prop_age_h=5.0, ml_age_h=1.0)

        self.assertEqual(overall(lines), "RED")
        self.assertEqual(len(lines), 1, f"expected exactly one line, got {lines}")

        lvl, msg = lines[0]
        self.assertEqual(lvl, "RED")
        self.assertIn("totals", msg)
        self.assertNotIn("moneyline", msg)
        self.assertIn("5.0h", msg)

    def test_moneyline_only_stall_is_red_and_names_moneyline(self):
        """The mirror case, so the fix is not accidentally one-sided."""
        lines = grade_extra(hours_to_card=6.0, prop_age_h=1.0, ml_age_h=5.0)

        self.assertEqual(overall(lines), "RED")
        self.assertEqual(len(lines), 1)
        lvl, msg = lines[0]
        self.assertEqual(lvl, "RED")
        self.assertIn("moneyline", msg)
        self.assertNotIn("totals", msg)

    def test_both_stalled_gives_two_separate_red_lines(self):
        lines = grade_extra(hours_to_card=6.0, prop_age_h=5.0, ml_age_h=9.0)

        self.assertEqual(overall(lines), "RED")
        self.assertEqual(levels(lines), ["RED", "RED"])
        self.assertIn("totals", text(lines))
        self.assertIn("moneyline", text(lines))

    def test_both_healthy_near_card_is_silent(self):
        lines = grade_extra(hours_to_card=6.0, prop_age_h=1.0, ml_age_h=1.0)
        self.assertEqual(lines, [])
        self.assertEqual(overall(lines), "GREEN")


class TestNeverWritten(unittest.TestCase):
    """None means the table has never been written. That is the worst case, not
    a missing value to be skipped."""

    def test_none_totals_is_red_near_card(self):
        lines = grade_extra(hours_to_card=2.0, prop_age_h=None, ml_age_h=1.0)
        self.assertEqual(overall(lines), "RED")
        self.assertIn("NEVER", text(lines))
        self.assertIn("totals", text(lines))

    def test_none_is_red_even_far_from_card(self):
        """An empty table is never merely a YELLOW: there is no capture at all."""
        lines = grade_extra(hours_to_card=200.0, prop_age_h=None, ml_age_h=None)
        self.assertEqual(levels(lines), ["RED", "RED"])

    def test_no_card_scheduled_is_silent(self):
        """Nothing to be late for."""
        self.assertEqual(grade_extra(hours_to_card=None, prop_age_h=99.0, ml_age_h=None), [])


class TestNearFarBoundary(unittest.TestCase):
    def test_far_from_card_a_stall_is_only_yellow(self):
        lines = grade_extra(hours_to_card=200.0,
                            prop_age_h=CAPTURE_MAX_AGE_FAR_H + 1, ml_age_h=1.0)
        self.assertEqual(levels(lines), ["YELLOW"])
        self.assertEqual(overall(lines), "YELLOW")

    def test_far_from_card_tolerates_the_near_limit(self):
        """An age that would be RED near the card is fine when the card is days out."""
        lines = grade_extra(hours_to_card=200.0,
                            prop_age_h=CAPTURE_MAX_AGE_H + 1, ml_age_h=1.0)
        self.assertEqual(lines, [])

    def test_exactly_at_the_limit_is_not_a_failure(self):
        """Strictly greater than, so the limit itself passes."""
        self.assertEqual(
            grade_extra(hours_to_card=1.0,
                        prop_age_h=CAPTURE_MAX_AGE_H, ml_age_h=CAPTURE_MAX_AGE_H),
            [],
        )

    def test_just_past_the_limit_fails(self):
        lines = grade_extra(hours_to_card=1.0,
                            prop_age_h=CAPTURE_MAX_AGE_H + 0.01, ml_age_h=1.0)
        self.assertEqual(levels(lines), ["RED"])

    def test_boundary_hour_counts_as_near(self):
        """At exactly NEAR_CARD_HOURS the strict near-card limit already applies."""
        lines = grade_extra(hours_to_card=NEAR_CARD_HOURS,
                            prop_age_h=CAPTURE_MAX_AGE_H + 1, ml_age_h=1.0)
        self.assertEqual(levels(lines), ["RED"])

    def test_card_already_started_is_still_near(self):
        """Negative hours_to_card means the bell has gone; still the strict limit."""
        lines = grade_extra(hours_to_card=-2.0,
                            prop_age_h=CAPTURE_MAX_AGE_H + 1, ml_age_h=1.0)
        self.assertEqual(levels(lines), ["RED"])


class TestLockGrading(unittest.TestCase):
    def test_unlocked_fights_near_card_is_red(self):
        lines = grade_locks({"eligible": 12, "locked_fights": 10}, hours_to_card=3.0)
        self.assertEqual(levels(lines), ["RED"])
        self.assertIn("2 eligible fight(s) still unlocked", text(lines))

    def test_unlocked_fights_far_from_card_is_yellow(self):
        lines = grade_locks({"eligible": 12, "locked_fights": 10}, hours_to_card=200.0)
        self.assertEqual(levels(lines), ["YELLOW"])

    def test_fully_locked_is_silent(self):
        self.assertEqual(grade_locks({"eligible": 12, "locked_fights": 12}, 3.0), [])

    def test_no_locks_info_is_silent(self):
        self.assertEqual(grade_locks(None, 3.0), [])


class TestOverall(unittest.TestCase):
    def test_red_wins_over_yellow(self):
        self.assertEqual(overall([("YELLOW", "a"), ("RED", "b")]), "RED")

    def test_yellow_when_no_red(self):
        self.assertEqual(overall([("YELLOW", "a")]), "YELLOW")

    def test_green_when_empty(self):
        self.assertEqual(overall([]), "GREEN")


class TestHelpers(unittest.TestCase):
    def test_hours_since_none_is_none(self):
        self.assertIsNone(hours_since(None, __import__("datetime").datetime.now()))

    def test_hours_since_parses_z_suffix(self):
        import datetime as dt
        now = dt.datetime(2026, 9, 15, 12, 0, tzinfo=dt.timezone.utc)
        self.assertAlmostEqual(hours_since("2026-09-15T09:00:00Z", now), 3.0, places=6)

    def test_hours_since_assumes_utc_when_naive(self):
        import datetime as dt
        now = dt.datetime(2026, 9, 15, 12, 0, tzinfo=dt.timezone.utc)
        self.assertAlmostEqual(hours_since("2026-09-15T09:00:00", now), 3.0, places=6)

    def test_fmt_age_none_reads_never(self):
        self.assertEqual(fmt_age(None), "never")

    def test_fmt_age_signed(self):
        self.assertEqual(fmt_age(3.0, signed=True), "+3.0h")


if __name__ == "__main__":
    unittest.main(verbosity=2)
