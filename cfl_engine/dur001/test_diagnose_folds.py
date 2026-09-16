"""Tests for the fold-by-fold calibration diagnostic.

    python -m unittest cfl_engine/dur001/test_diagnose_folds.py -v

The diagnostic's job is to name the EARLIEST stage at which two walk-forward
runs diverge. Getting that ordering wrong is the failure that matters: a benign
difference reported as the headline buries the real one, which is exactly what
happened on the first pass here (a final-fold data-window artifact masked a
calibration difference).
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from diagnose_folds import agreement, classify, pair_folds  # noqa: E402


def fz(start, end="x", n_test=100, calibrated=True, ll=0.50, const=0.52):
    return {"block_start": start, "block_end": end, "n_train": 1000,
            "n_test": n_test, "calibrated": calibrated,
            "model_logloss": ll, "const_logloss": const, "model_brier": 0.16}


def me(start, end="x", n_test=100, calibrated=True, raw=0.50, cal=0.50, const=0.52):
    return {"fold": 0, "start": start, "end": end, "n_test_rows": n_test,
            "calibrated": calibrated, "n_cal_rows": 900 if calibrated else 0,
            "raw_logloss": raw, "test_logloss": cal, "const_logloss": const,
            "calibration_gain": round(raw - cal, 4)}


class TestPairFolds(unittest.TestCase):
    def test_pairs_on_block_start_not_index(self):
        """Index-matching would mis-pair if either side skipped a fold."""
        rows = pair_folds([fz("2018-01-01"), fz("2018-07-01")],
                          [me("2018-07-01")])
        by = {r["start"]: r for r in rows}
        self.assertIsNone(by["2018-01-01"]["mine"], "missing fold must pair to None")
        self.assertIsNotNone(by["2018-07-01"]["mine"])

    def test_folds_only_in_the_new_run_are_kept(self):
        rows = pair_folds([fz("2018-01-01")], [me("2018-01-01"), me("2019-01-01")])
        extra = [r for r in rows if r["start"] == "2019-01-01"][0]
        self.assertIsNone(extra["frozen"])

    def test_identical_inputs_pair_one_to_one(self):
        rows = pair_folds([fz("a"), fz("b")], [me("a"), me("b")])
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["frozen"] and r["mine"] for r in rows))


class TestStageOrdering(unittest.TestCase):
    """Earliest differing stage wins — later stages are meaningless before it."""

    def test_no_difference_reports_none(self):
        v = classify(pair_folds([fz("a")], [me("a")]))
        self.assertEqual(v["earliest_differing_stage"], "NONE")

    def test_missing_fold_is_fold_structure(self):
        v = classify(pair_folds([fz("a"), fz("b")], [me("a")]))
        self.assertEqual(v["earliest_differing_stage"], "FOLD_STRUCTURE")

    def test_interior_row_count_difference_is_data_selection(self):
        v = classify(pair_folds([fz("a", n_test=100), fz("b")],
                                [me("a", n_test=99), me("b")]))
        self.assertEqual(v["earliest_differing_stage"], "DATA_SELECTION")

    def test_fold_structure_outranks_data_selection(self):
        v = classify(pair_folds([fz("a", n_test=100), fz("b")],
                                [me("a", n_test=99)]))
        self.assertEqual(v["earliest_differing_stage"], "FOLD_STRUCTURE")

    def test_calibration_difference_is_reported_when_rows_agree(self):
        v = classify(pair_folds([fz("a", calibrated=False)], [me("a", calibrated=True)]))
        self.assertEqual(v["earliest_differing_stage"], "CALIBRATION")
        self.assertEqual(v["folds_with_calibration_diff"], ["a"])

    def test_data_selection_outranks_calibration(self):
        v = classify(pair_folds([fz("a", n_test=100, calibrated=False), fz("b")],
                                [me("a", n_test=50, calibrated=True), me("b")]))
        self.assertEqual(v["earliest_differing_stage"], "DATA_SELECTION")

    def test_baseline_only_difference_is_reported_last(self):
        v = classify(pair_folds([fz("a", const=0.52)], [me("a", const=0.55)]))
        self.assertEqual(v["earliest_differing_stage"], "BASELINE")

    def test_calibration_outranks_baseline(self):
        v = classify(pair_folds([fz("a", calibrated=False, const=0.52)],
                                [me("a", calibrated=True, const=0.55)]))
        self.assertEqual(v["earliest_differing_stage"], "CALIBRATION")


class TestFinalFoldWindowArtifact(unittest.TestCase):
    """The regression this guards.

    Two runs generated on different days differ in the final partial fold only.
    Reporting that as DATA_SELECTION buried a real calibration difference behind
    a known, benign artifact.
    """

    def test_final_fold_only_difference_does_not_mask_calibration(self):
        frozen = [fz("a", calibrated=False), fz("b"), fz("c", n_test=94)]
        mine = [me("a", calibrated=True), me("b"), me("c", n_test=193)]
        v = classify(pair_folds(frozen, mine))
        self.assertTrue(v["final_fold_window_difference_only"])
        self.assertEqual(v["earliest_differing_stage"], "CALIBRATION")

    def test_final_fold_difference_is_still_recorded(self):
        """Not masked, but not hidden either — it stays in the detail fields."""
        v = classify(pair_folds([fz("a"), fz("b", n_test=94)],
                                [me("a"), me("b", n_test=193)]))
        self.assertEqual(v["folds_with_test_row_diff"], ["b"])

    def test_an_interior_difference_is_not_treated_as_a_window_artifact(self):
        v = classify(pair_folds([fz("a", n_test=100), fz("b"), fz("c")],
                                [me("a", n_test=50), me("b"), me("c")]))
        self.assertFalse(v["final_fold_window_difference_only"])
        self.assertEqual(v["earliest_differing_stage"], "DATA_SELECTION")

    def test_interior_and_final_together_is_data_selection(self):
        v = classify(pair_folds([fz("a", n_test=100), fz("b", n_test=94)],
                                [me("a", n_test=50), me("b", n_test=193)]))
        self.assertFalse(v["final_fold_window_difference_only"])
        self.assertEqual(v["earliest_differing_stage"], "DATA_SELECTION")


class TestAgreement(unittest.TestCase):
    """Which of our two series does the frozen log loss actually track?"""

    def test_detects_that_frozen_tracks_raw(self):
        rows = pair_folds([fz("a", ll=0.50), fz("b", ll=0.60)],
                          [me("a", raw=0.50, cal=0.55), me("b", raw=0.60, cal=0.66)])
        a = agreement(rows)
        self.assertEqual(a["frozen_tracks"], "raw")
        self.assertEqual(len(a["folds_where_raw_matches_frozen"]), 2)
        self.assertEqual(len(a["folds_where_calibrated_matches_frozen"]), 0)

    def test_detects_that_frozen_tracks_calibrated(self):
        rows = pair_folds([fz("a", ll=0.55)], [me("a", raw=0.50, cal=0.55)])
        self.assertEqual(agreement(rows)["frozen_tracks"], "calibrated")

    def test_folds_with_different_row_counts_are_excluded(self):
        """Comparing log loss across different test sets is meaningless."""
        rows = pair_folds([fz("a", n_test=100, ll=0.50), fz("b", n_test=94, ll=0.9)],
                          [me("a", n_test=100, raw=0.50, cal=0.55),
                           me("b", n_test=193, raw=0.1, cal=0.1)])
        self.assertEqual(agreement(rows)["comparable_folds"], 1)

    def test_no_comparable_folds_reports_zero(self):
        rows = pair_folds([fz("a", n_test=100)], [me("a", n_test=1)])
        self.assertEqual(agreement(rows)["comparable_folds"], 0)

    def test_unmatched_folds_are_skipped(self):
        rows = pair_folds([fz("a"), fz("b")], [me("a")])
        self.assertEqual(agreement(rows)["comparable_folds"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
