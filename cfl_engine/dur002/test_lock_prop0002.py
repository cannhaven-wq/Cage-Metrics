"""Conformance tests for the PROP-0001@v2 lock implementation.

    python -m unittest cfl_engine/dur002/test_lock_prop0002.py -v

These prove that `lock_prop0002.py` implements the frozen DUR-002 specification
and nothing else. They are **implementation verification**, not a backtest and
not a model comparison: no historical performance is computed, v1 and v2 are
never scored against each other, and nothing here could inform a modelling
choice.

The load-bearing claim is:

    v2's probability equals the RAW, pre-calibration probability produced by the
    existing v1 pipeline for the same input.

That is checked at three levels — per-round hazard, fight distribution, and the
threshold probabilities that actually land on a lock row — on a deterministic
synthetic fixture, with exact equality rather than a tolerance.

Every test also guards against being vacuous: each equality check is paired with
a check that the isotonic map it bypasses is non-trivial, so a silently-broken
calibrator cannot make these pass for the wrong reason.
"""
from __future__ import annotations

import os
import sys
import unittest

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ENGINE, "dur001"))
sys.path.insert(0, os.path.join(ENGINE, "features"))
sys.path.insert(0, os.path.join(ENGINE, "models"))

import lock_prop0001 as v1                                    # noqa: E402
import lock_prop0002 as v2                                    # noqa: E402
from duration import DurationHazardModel                      # noqa: E402

COV = ["x1", "x2", "x3"]


def synthetic_panel(n_fights: int = 400, seed: int = 7) -> pd.DataFrame:
    """Deterministic person-period panel: one row per (fight, round reached).

    Not real data and not meant to be — these tests check that two code paths
    agree on the same input, which does not depend on the input being realistic.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for fid in range(n_fights):
        x = rng.normal(size=3)
        for rnd in (1, 2, 3):
            z = -1.6 + 0.4 * x[0] - 0.3 * x[1] + 0.15 * x[2] + 0.1 * rnd
            p = 1.0 / (1.0 + np.exp(-z))
            event = int(rng.random() < p)
            rows.append({
                "fight_id": fid, "round": rnd, "event": event,
                "r1": float(rnd == 1), "r2": float(rnd == 2), "r3": float(rnd == 3),
                "x1": x[0], "x2": x[1], "x3": x[2],
                "event_date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=fid),
            })
            if event:
                break
    return pd.DataFrame(rows)


def fitted_pair():
    """One fitted model with a calibrator, and the same model with it stripped."""
    panel = synthetic_panel()
    calibrated = DurationHazardModel().fit(panel, COV)
    calibrated.fit_calibration(panel)
    stripped = DurationHazardModel().fit(panel, COV)
    stripped.fit_calibration(panel)
    v2.strip_calibration(stripped)
    return panel, calibrated, stripped


class TestCalibratorIsNonTrivial(unittest.TestCase):
    """Guard against vacuous tests: if the isotonic map were an identity, every
    equality below would pass for the wrong reason."""

    def test_the_fixture_calibrator_actually_changes_predictions(self):
        panel, calibrated, _ = fitted_pair()
        raw = calibrated.predict_hazard(panel, calibrated=False)
        cal = calibrated.predict_hazard(panel, calibrated=True)
        self.assertIsNotNone(calibrated.iso_)
        self.assertFalse(
            np.allclose(raw, cal),
            "the fixture's isotonic map is an identity — these conformance tests "
            "would pass even if strip_calibration did nothing",
        )


class TestStripCalibration(unittest.TestCase):
    def test_strip_sets_iso_to_none(self):
        _, _, stripped = fitted_pair()
        self.assertIsNone(stripped.iso_)

    def test_strip_returns_the_same_object(self):
        _, calibrated, _ = fitted_pair()
        self.assertIs(v2.strip_calibration(calibrated), calibrated)

    def test_strip_is_idempotent(self):
        _, _, stripped = fitted_pair()
        v2.strip_calibration(stripped)
        self.assertIsNone(stripped.iso_)


class TestHazardConformance(unittest.TestCase):
    """Level 1: the per-round hazard."""

    def test_stripped_equals_raw_exactly(self):
        panel, calibrated, stripped = fitted_pair()
        expected = calibrated.predict_hazard(panel, calibrated=False)
        actual = stripped.predict_hazard(panel, calibrated=True)
        np.testing.assert_array_equal(
            actual, expected,
            "v2's hazard must be bit-identical to the v1 pipeline's raw hazard",
        )

    def test_stripped_ignores_the_calibrated_flag(self):
        """With no map attached, calibrated=True and False are the same call."""
        panel, _, stripped = fitted_pair()
        np.testing.assert_array_equal(
            stripped.predict_hazard(panel, calibrated=True),
            stripped.predict_hazard(panel, calibrated=False),
        )

    def test_stripped_differs_from_the_calibrated_model(self):
        """The change is real, not cosmetic."""
        panel, calibrated, stripped = fitted_pair()
        self.assertFalse(np.allclose(
            stripped.predict_hazard(panel, calibrated=True),
            calibrated.predict_hazard(panel, calibrated=True),
        ))

    def test_coefficients_are_untouched(self):
        """Stripping the calibrator must not disturb the fit itself — the
        training path is identical between versions by design."""
        _, calibrated, stripped = fitted_pair()
        pd.testing.assert_series_equal(calibrated.params_, stripped.params_)


class TestFightDistributionConformance(unittest.TestCase):
    """Level 2: the fight-level duration distribution."""

    def _fight_frame(self, panel):
        return panel.drop_duplicates(subset="fight_id")[["fight_id"] + COV].head(50)

    def test_distribution_matches_raw(self):
        panel, calibrated, stripped = fitted_pair()
        f = self._fight_frame(panel)
        expected = calibrated.fight_distribution(f, calibrated=False)
        actual = stripped.fight_distribution(f, calibrated=True)
        pd.testing.assert_frame_equal(actual, expected)

    def test_hazards_and_survival_are_consistent(self):
        panel, _, stripped = fitted_pair()
        d = stripped.fight_distribution(self._fight_frame(panel), calibrated=True)
        total = d.p_ends_r1 + d.p_ends_r2 + d.p_ends_r3 + d.p_decision
        np.testing.assert_allclose(total.to_numpy(), 1.0, atol=1e-12)


class TestThresholdProbabilityConformance(unittest.TestCase):
    """Level 3: the numbers that actually land on a lock row."""

    def test_threshold_probs_match_raw(self):
        panel, calibrated, stripped = fitted_pair()
        f = panel.drop_duplicates(subset="fight_id")[["fight_id"] + COV].head(25)
        phi = {1: 0.47, 2: 0.43, 3: 0.46}

        exp_d = calibrated.fight_distribution(f, calibrated=False)
        act_d = stripped.fight_distribution(f, calibrated=True)
        for i in range(len(f)):
            with self.subTest(row=i):
                exp = v1.threshold_probs(float(exp_d.haz_r1[i]), float(exp_d.haz_r2[i]),
                                         float(exp_d.haz_r3[i]), phi)
                act = v1.threshold_probs(float(act_d.haz_r1[i]), float(act_d.haz_r2[i]),
                                         float(act_d.haz_r3[i]), phi)
                for k in (0.5, 1.5, 2.5, "distance"):
                    self.assertEqual(act[k], exp[k])
                for r in (1, 2, 3):
                    self.assertEqual(act["p_ends"][r], exp["p_ends"][r])

    def test_v2_uses_the_frozen_threshold_mapping(self):
        """The threshold mapping is inherited, not redefined."""
        self.assertEqual(v2.THRESHOLDS, v1.THRESHOLDS)
        self.assertEqual(v2.THRESHOLDS, (0.5, 1.5, 2.5))


class TestVersionGuards(unittest.TestCase):
    """v2 rows must be unmistakable, and a v1 row must never be written."""

    def test_model_version_is_hardcoded_to_v2(self):
        self.assertEqual(v2.MODEL_VERSION, "PROP-0001@v2")

    def test_v2_does_not_inherit_v1s_version(self):
        self.assertNotEqual(v2.MODEL_VERSION, v1.MODEL_VERSION)
        self.assertEqual(v2.V1_MODEL_VERSION, v1.MODEL_VERSION)

    def test_model_name_is_shared(self):
        self.assertEqual(v2.MODEL_NAME, v1.MODEL_NAME)

    def test_assert_v2_only_passes_clean_rows(self):
        rows = [{"model_version": "PROP-0001@v2", "model_name": "PROP-0001"}]
        v2.assert_v2_only(rows)                        # must not raise

    def test_assert_v2_only_aborts_on_a_v1_row(self):
        rows = [{"model_version": "PROP-0001@v2", "model_name": "PROP-0001"},
                {"model_version": "PROP-0001@v1", "model_name": "PROP-0001"}]
        with self.assertRaises(SystemExit) as ctx:
            v2.assert_v2_only(rows)
        self.assertIn("PROP-0001@v1", str(ctx.exception))

    def test_assert_v2_only_aborts_on_a_missing_version(self):
        with self.assertRaises(SystemExit):
            v2.assert_v2_only([{"model_name": "PROP-0001"}])

    def test_assert_v2_only_aborts_on_an_unexpected_model_name(self):
        with self.assertRaises(SystemExit):
            v2.assert_v2_only([{"model_version": "PROP-0001@v2", "model_name": "OTHER"}])


class TestProvenanceRecording(unittest.TestCase):
    def test_script_sha256_is_a_sha256_of_the_file_on_disk(self):
        import hashlib
        with open(os.path.join(HERE, "lock_prop0002.py"), "rb") as fh:
            expected = hashlib.sha256(fh.read()).hexdigest()
        self.assertEqual(v2.script_sha256(), expected)
        self.assertRegex(v2.script_sha256(), r"^[0-9a-f]{64}$")

    def test_frozen_timestamp_matches_the_preregistration(self):
        pre = os.path.join(HERE, "PREREGISTRATION.md")
        with open(pre, encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn(v2.FROZEN_AT, body,
                      "the freeze timestamp in the script must match the "
                      "preregistration it implements")

    def test_preregistration_path_points_at_a_real_file(self):
        self.assertTrue(os.path.isfile(
            os.path.join(ENGINE, os.pardir, v2.PREREGISTRATION)))


class TestNoModellingDivergence(unittest.TestCase):
    """v2 must not quietly redefine anything it is supposed to inherit."""

    def test_shared_objects_are_the_same_objects(self):
        for name in ("LOCK_TABLE", "EPS"):
            with self.subTest(attr=name):
                self.assertEqual(getattr(v2, name), getattr(v1, name))

    def test_v2_defines_no_fitting_or_feature_code(self):
        """The wrapper must not carry its own model or feature implementation."""
        for forbidden in ("fit_prop0001", "matchup_features", "covariate_columns",
                          "PITWorld", "serve_fight", "threshold_probs"):
            with self.subTest(symbol=forbidden):
                self.assertNotIn(
                    forbidden, v2.__dict__,
                    f"{forbidden} must be used from the frozen v1 module, not "
                    f"redefined in lock_prop0002.py",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
