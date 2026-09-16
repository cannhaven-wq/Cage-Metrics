"""Tests for the PROP-0001 walk-forward harness.

    python -m unittest cfl_engine/dur001/test_walkforward_prop0001.py -v

Covers the fold construction, the metrics, and the harness comparison — the
parts that decide whether a run is trustworthy — without touching Supabase.
The end-to-end walk is exercised on a small synthetic panel.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from walkforward_prop0001 import (  # noqa: E402
    MATCH_TOL,
    block_folds,
    brier,
    calibration_table,
    compare_to_harness,
    event_folds,
    gtd_block,
    logloss,
)


class TestBlockFolds(unittest.TestCase):
    def setUp(self):
        self.dates = pd.Series(pd.to_datetime(
            ["2018-02-01", "2019-06-01", "2020-01-15", "2020-11-30"]))

    def test_six_month_blocks_are_contiguous(self):
        folds = block_folds(self.dates, pd.Timestamp("2018-01-01"),
                            pd.Timestamp("2020-01-01"), 6)
        self.assertEqual(len(folds), 4)
        for (_, prev_end), (nxt_start, _) in zip(folds, folds[1:]):
            self.assertEqual(prev_end, nxt_start, "folds must not overlap or gap")

    def test_first_fold_starts_at_start(self):
        folds = block_folds(self.dates, pd.Timestamp("2018-01-01"), None, 6)
        self.assertEqual(folds[0][0], pd.Timestamp("2018-01-01"))

    def test_end_is_respected(self):
        folds = block_folds(self.dates, pd.Timestamp("2018-01-01"),
                            pd.Timestamp("2019-01-01"), 6)
        self.assertLessEqual(folds[-1][1], pd.Timestamp("2019-01-01"))

    def test_without_end_covers_the_last_date(self):
        folds = block_folds(self.dates, pd.Timestamp("2018-01-01"), None, 6)
        self.assertGreater(folds[-1][1], self.dates.max())

    def test_block_months_changes_fold_count(self):
        a = block_folds(self.dates, pd.Timestamp("2018-01-01"), pd.Timestamp("2020-01-01"), 6)
        b = block_folds(self.dates, pd.Timestamp("2018-01-01"), pd.Timestamp("2020-01-01"), 12)
        self.assertEqual(len(a), 4)
        self.assertEqual(len(b), 2)


class TestEventFolds(unittest.TestCase):
    def setUp(self):
        self.fdf = pd.DataFrame({
            "fight_id": [1, 2, 3, 4],
            "event_date": pd.to_datetime(
                ["2023-01-01", "2023-01-01", "2024-05-05", "2026-01-01"]),
        })

    def test_one_fold_per_distinct_date(self):
        folds = event_folds(self.fdf, pd.Timestamp("2023-01-01"), pd.Timestamp("2025-12-31"))
        self.assertEqual(len(folds), 2, "two distinct dates in range")

    def test_range_excludes_out_of_window_events(self):
        folds = event_folds(self.fdf, pd.Timestamp("2023-01-01"), pd.Timestamp("2025-12-31"))
        self.assertTrue(all(f[0] <= pd.Timestamp("2025-12-31") for f in folds))

    def test_folds_are_one_day_wide(self):
        for lo, hi in event_folds(self.fdf, pd.Timestamp("2023-01-01"), None):
            self.assertEqual(hi - lo, pd.Timedelta(days=1))

    def test_folds_are_chronological(self):
        folds = event_folds(self.fdf, pd.Timestamp("2023-01-01"), None)
        self.assertEqual([f[0] for f in folds], sorted(f[0] for f in folds))


class TestMetrics(unittest.TestCase):
    def test_logloss_of_perfect_prediction_is_zero(self):
        self.assertAlmostEqual(logloss([1, 0, 1], [1, 0, 1]), 0.0, places=10)

    def test_logloss_of_coin_flip_is_ln2(self):
        self.assertAlmostEqual(logloss([1, 0], [0.5, 0.5]), np.log(2), places=10)

    def test_logloss_clips_rather_than_exploding(self):
        """A confidently wrong prediction must be finite, not inf."""
        self.assertTrue(np.isfinite(logloss([1], [0.0])))

    def test_brier_of_perfect_prediction_is_zero(self):
        self.assertAlmostEqual(brier([1, 0], [1, 0]), 0.0, places=10)

    def test_brier_of_coin_flip(self):
        self.assertAlmostEqual(brier([1, 0], [0.5, 0.5]), 0.25, places=10)

    def test_calibration_table_bins_sum_to_n(self):
        rng = np.random.default_rng(0)
        p = rng.uniform(size=500)
        y = (rng.uniform(size=500) < p).astype(float)
        rows, maxdev = calibration_table(y, p, bins=10)
        self.assertEqual(sum(r["n"] for r in rows), 500)
        self.assertEqual(len(rows), 10)
        self.assertIsNotNone(maxdev)

    def test_calibration_of_a_well_calibrated_stream_is_tight(self):
        rng = np.random.default_rng(1)
        p = rng.uniform(size=20000)
        y = (rng.uniform(size=20000) < p).astype(float)
        _, maxdev = calibration_table(y, p, bins=10)
        self.assertLess(maxdev, 0.05, "a calibrated stream should not deviate much")

    def test_calibration_table_empty_input(self):
        rows, maxdev = calibration_table([], [])
        self.assertEqual(rows, [])
        self.assertIsNone(maxdev)


class TestGtdBlock(unittest.TestCase):
    """gtd_block takes FIGHT-level predictions, one row per scored fight."""

    def test_rates_come_from_the_fight_level_frame(self):
        fight_pred = pd.DataFrame({"fight_id": [1, 2], "p_gtd": [0.512, 0.488]})
        fdf = pd.DataFrame({"fight_id": [1, 2], "outcome_kind": ["decision", "finish"]})
        out = gtd_block(fight_pred, fdf)
        self.assertEqual(out["n_fights"], 2)
        self.assertAlmostEqual(out["pred_gtd_rate"], 0.5, places=4)
        self.assertAlmostEqual(out["actual_gtd_rate"], 0.5, places=4)

    def test_every_scored_fight_counts_including_early_finishes(self):
        """The regression this guards: a fight finished in round 1 has no r2/r3
        person-period row, so an implementation that rebuilt P(GTD) from those
        rows would drop it and report a goes-the-distance rate near 1."""
        fight_pred = pd.DataFrame({"fight_id": [1, 2, 3, 4],
                                   "p_gtd": [0.5, 0.5, 0.5, 0.5]})
        fdf = pd.DataFrame({
            "fight_id": [1, 2, 3, 4],
            "outcome_kind": ["finish", "finish", "finish", "decision"],
        })
        out = gtd_block(fight_pred, fdf)
        self.assertEqual(out["n_fights"], 4, "early finishes must not be dropped")
        self.assertAlmostEqual(out["actual_gtd_rate"], 0.25, places=4)

    def test_only_decisions_count_as_going_the_distance(self):
        fight_pred = pd.DataFrame({"fight_id": [1], "p_gtd": [0.5]})
        fdf = pd.DataFrame({"fight_id": [1], "outcome_kind": ["finish"]})
        self.assertEqual(gtd_block(fight_pred, fdf)["actual_gtd_rate"], 0.0)

    def test_empty_input(self):
        out = gtd_block(pd.DataFrame(columns=["fight_id", "p_gtd"]),
                        pd.DataFrame(columns=["fight_id", "outcome_kind"]))
        self.assertEqual(out["n_fights"], 0)

    def test_none_input(self):
        self.assertEqual(gtd_block(None, pd.DataFrame())["n_fights"], 0)


class TestHarnessComparison(unittest.TestCase):
    """The comparison must not quietly pass when numbers disagree."""

    def _frozen_pooled(self):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "harness", "walkforward_report.json")) as fh:
            return json.load(fh)["pooled"]

    def test_identical_pooled_matches(self):
        out = compare_to_harness(dict(self._frozen_pooled()))
        self.assertEqual(out["status"], "MATCHES")
        self.assertTrue(all(r["match"] for r in out["fields"]))

    def test_a_shifted_logloss_differs(self):
        pooled = dict(self._frozen_pooled())
        pooled["model_logloss"] = pooled["model_logloss"] + 0.01
        out = compare_to_harness(pooled)
        self.assertEqual(out["status"], "DIFFERS")
        bad = [r for r in out["fields"] if r["field"] == "model_logloss"][0]
        self.assertFalse(bad["match"])

    def test_difference_inside_tolerance_still_matches(self):
        """The frozen report stores 4 decimals; a sub-rounding difference is the
        same number printed twice, not a disagreement."""
        pooled = dict(self._frozen_pooled())
        pooled["model_logloss"] = pooled["model_logloss"] + MATCH_TOL / 2
        self.assertEqual(compare_to_harness(pooled)["status"], "MATCHES")

    def test_row_count_mismatch_differs(self):
        pooled = dict(self._frozen_pooled())
        pooled["n_test_rows"] = pooled["n_test_rows"] + 1
        self.assertEqual(compare_to_harness(pooled)["status"], "DIFFERS")

    def test_missing_field_is_not_silently_a_match(self):
        pooled = dict(self._frozen_pooled())
        del pooled["model_brier"]
        out = compare_to_harness(pooled)
        self.assertEqual(out["status"], "DIFFERS")
        row = [r for r in out["fields"] if r["field"] == "model_brier"][0]
        self.assertIsNone(row["match"])

    def test_market_subset_is_not_compared(self):
        """The run performs no market comparison, so the comparison must not
        claim to have checked one."""
        out = compare_to_harness(dict(self._frozen_pooled()))
        self.assertNotIn("market_odds_subset", [r["field"] for r in out["fields"]])
        self.assertIn("no comparison against market data", out["note"])

    def test_missing_reference_reports_no_reference(self):
        import walkforward_prop0001 as wf
        original = wf.HARNESS_REPORT
        try:
            wf.HARNESS_REPORT = os.path.join(tempfile.gettempdir(), "does-not-exist.json")
            self.assertEqual(wf.compare_to_harness({})["status"], "NO_REFERENCE")
        finally:
            wf.HARNESS_REPORT = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
