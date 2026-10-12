"""T-083: every live engine forecast must be re-derivable.

T-082 re-ran the live engine for the days it had published and got different
numbers: a mean shift of 0.045 and 1 fight in 10 on the other side. These tests
hold the three fixes in place:

  1. the dependency set is pinned exactly;
  2. weight class has a fixed encoding that does not depend on row order or on
     which other labels a build happens to contain;
  3. a publish bundle re-derives every published probability IDENTICALLY, and a
     tampered bundle fails.

Plus the property the bundle relies on: the same inputs and the same versions
train the same model, bit for bit.

    python -m pytest tests/test_engine_reproducible.py -v
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(REPO, "cfl_engine")
sys.path.insert(0, ENGINE)

try:
    import numpy as np
    import pandas as pd
    import xgboost  # noqa: F401
    HAVE_ENGINE = True
except ImportError:          # the static checks still run without the engine deps
    HAVE_ENGINE = False


class TestPins(unittest.TestCase):
    def test_every_engine_dependency_is_pinned_exactly(self):
        with open(os.path.join(ENGINE, "requirements.txt"), encoding="utf-8") as f:
            lines = [ln.split("#")[0].strip() for ln in f]
        reqs = [ln for ln in lines if ln]
        self.assertGreater(len(reqs), 5)
        for ln in reqs:
            with self.subTest(line=ln):
                self.assertRegex(ln, r"^[A-Za-z0-9_.\-]+==[0-9][0-9A-Za-z.\-]*$",
                                 "a floating requirement lets each run train on a different library")

    def test_version_records_a_build_alongside_the_version(self):
        with open(os.path.join(ENGINE, "version.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertRegex(src, r'ENGINE_VERSION = "engine_v\d+"')
        self.assertRegex(src, r'ENGINE_BUILD = "[^"]+"')

    def test_factorize_is_gone_from_the_engine(self):
        with open(os.path.join(ENGINE, "engine.py"), encoding="utf-8") as f:
            self.assertNotIn("pd.factorize(", f.read())


# Every weight_class label in the live fights table on 2026-10-12 that is not a
# plain division, plus the divisions. None may come out NaN.
LABELS = {
    "Strawweight": 0, "Flyweight": 1, "Bantamweight": 2, "Featherweight": 3,
    "Lightweight": 4, "Welterweight": 5, "Middleweight": 6, "Light Heavyweight": 7,
    "Heavyweight": 8, "Super Heavyweight": 8, "Catch Weight": 9, "Open Weight": 10,
    "2 Tournament": 10, "Superfight Championship": 10, "Ultimate Ultimate '96 Tournament": 10,
    "13 Lightweight Tournament": 4, "Ultimate Japan Heavyweight Tournament": 8,
    "Ultimate Fighter 1 Light Heavyweight Tournament": 7,
    "Ultimate Fighter 18 Women's Bantamweight Tournament": 2,
    "Road To UFC 1 Lightweight Tournament": 4,
    "Road to UFC 3 Women's Strawweight Tournament Title": 0,
    "Ultimate Fighter 34 Women's Strawweight Tournament": 0,
    "TUF Nations Canada vs. Australia Middleweight Tournament": 6,
    "Ultimate Fighter 28 Women's Featherweight Tournament": 3,
}


@unittest.skipUnless(HAVE_ENGINE, "engine dependencies not installed")
class TestWeightClassEncoding(unittest.TestCase):
    def test_every_known_label_has_its_fixed_code(self):
        from engine import wc_code_of
        for label, code in LABELS.items():
            with self.subTest(label=label):
                self.assertEqual(wc_code_of(label), float(code))

    def test_an_unplaceable_label_is_nan_not_a_guess(self):
        from engine import wc_code_of
        for label in (None, "", "nan", "Mystery Division"):
            with self.subTest(label=label):
                self.assertTrue(np.isnan(wc_code_of(label)))

    def test_codes_do_not_depend_on_row_order_or_on_other_labels(self):
        """The defect T-082 found: the same fight got different codes in
        different builds. Build the column three ways and require one answer."""
        from engine import wc_code_of
        base = pd.Series(["Heavyweight", "Lightweight", "Flyweight",
                          "Road to UFC 4 Bantamweight Tournament"])
        shuffled = base.sample(frac=1.0, random_state=3)
        extra = pd.concat([pd.Series(["Ultimate Fighter 99 Lightweight Tournament"]), base])
        a = base.map(wc_code_of).to_numpy()
        b = shuffled.map(wc_code_of).sort_index().to_numpy()
        c = extra.map(wc_code_of).to_numpy()[1:]
        np.testing.assert_array_equal(a, b)
        np.testing.assert_array_equal(a, c)


@unittest.skipUnless(HAVE_ENGINE, "engine dependencies not installed")
class TestReproducibleTraining(unittest.TestCase):
    """Uses the engine's own synthetic generator — no database, no network."""

    @classmethod
    def setUpClass(cls):
        import make_synthetic
        from engine import build_features, load_data
        cls.tmp = tempfile.mkdtemp(prefix="t083-")
        make_synthetic.generate(cls.tmp)
        fights, stats, fighters = load_data(*(os.path.join(cls.tmp, n) for n in
                                              ("fights.csv", "fight_stats.csv", "fighters.csv")))
        # a small slice keeps the suite fast; determinism does not depend on size
        cut = fights["event_date"].sort_values().iloc[1500]
        cls.fights = fights[fights["event_date"] <= cut].reset_index(drop=True)
        cls.stats, cls.fighters = stats, fighters
        cls.feat = build_features(cls.fights, stats, fighters)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _train_and_predict(self):
        import predict_upcoming as pu
        from engine import make_matchup_features, predict_symmetric
        model, diff_cols = pu.train_final_model(self.feat, log=lambda *_: None)
        X, _, _ = make_matchup_features(self.feat.tail(200).reset_index(drop=True))
        p, _ = predict_symmetric(model, X, diff_cols)
        return model, diff_cols, X, p

    def test_same_inputs_same_versions_same_model(self):
        _, _, _, p1 = self._train_and_predict()
        _, _, _, p2 = self._train_and_predict()
        np.testing.assert_array_equal(p1, p2)

    def test_the_stored_isotonic_map_is_bit_identical_to_sklearn(self):
        from publish_bundle import _calibrate
        from sklearn.isotonic import IsotonicRegression
        rng = np.random.default_rng(0)
        p = rng.random(3000)
        y = (rng.random(3000) < p).astype(int)
        iso = IsotonicRegression(y_min=1e-4, y_max=1 - 1e-4, out_of_bounds="clip").fit(p, y)
        q = np.concatenate([rng.random(20000), [0.0, 1.0], iso.X_thresholds_])
        cal = {"kind": "isotonic", "x": iso.X_thresholds_.tolist(), "y": iso.y_thresholds_.tolist()}
        np.testing.assert_array_equal(_calibrate(cal, q), iso.predict(q))
        # and on the model's float32 output, which is what production feeds it
        q32 = q.astype("float32")
        np.testing.assert_array_equal(_calibrate(cal, q32), iso.predict(q32))

    def test_a_bundle_re_derives_every_number_and_a_tampered_one_fails(self):
        import publish_bundle
        import predict_upcoming as pu
        from sklearn.isotonic import IsotonicRegression
        model, diff_cols, X, p_raw = self._train_and_predict()
        rng = np.random.default_rng(1)
        # fitted on float64, as production fits it (on the OOS CSV); applied to
        # the model's float32 output, as production applies it
        iso = IsotonicRegression(y_min=1e-4, y_max=1 - 1e-4, out_of_bounds="clip").fit(
            p_raw.astype("float64"), (rng.random(len(p_raw)) < p_raw).astype(int))
        p_cal = np.clip(iso.predict(p_raw), pu.PUBLISH_P_MIN, pu.PUBLISH_P_MAX)
        tail = self.feat.tail(200).reset_index(drop=True)
        bundle = {
            "model": model, "diff_cols": diff_cols, "feature_cols": list(X.columns), "X_up": X,
            "calibrator": {"kind": "isotonic", "x": iso.X_thresholds_.tolist(),
                           "y": iso.y_thresholds_.tolist()},
            "blend": {"kind": "logistic", "coef": [[1.0, 1.0]], "intercept": [0.0]},
            "predictions": pd.DataFrame({
                "fight_id": tail["fight_id"], "fighter_a_id": tail["fighter_a_id"],
                "fighter_b_id": tail["fighter_b_id"], "p_raw_a": p_raw, "p_cal_a": p_cal,
                "p_blend_a": p_cal, "q_a": np.nan}),
        }
        inputs = {n: os.path.join(self.tmp, n) for n in ("fights.csv", "fight_stats.csv", "fighters.csv")}
        root = tempfile.mkdtemp(prefix="bundle-", dir=self.tmp)
        manifest = publish_bundle.write(bundle, root, inputs=inputs)
        self.assertRegex(manifest["manifest_sha256"], r"^[0-9a-f]{64}$")
        self.assertIn("model.ubj", manifest["files"])
        self.assertIn("inputs/fights.csv", manifest["files"])

        res = publish_bundle.verify(manifest["dir"])
        self.assertTrue(res["ok"], res["problems"])
        self.assertEqual(res["max_abs_diff_raw"], 0.0)
        self.assertEqual(res["max_abs_diff_cal"], 0.0)

        # a published number edited after the fact
        pred_path = os.path.join(manifest["dir"], "predictions.csv")
        df = pd.read_csv(pred_path, float_precision="round_trip")
        df.loc[0, "p_cal_a"] = df.loc[0, "p_cal_a"] + 1e-6
        df.to_csv(pred_path, index=False, float_format="%.17g")
        res = publish_bundle.verify(manifest["dir"])
        self.assertFalse(res["ok"])
        self.assertTrue(any("predictions.csv: sha256" in p for p in res["problems"]))
        self.assertTrue(any("p_cal_a differs" in p for p in res["problems"]))


@unittest.skipUnless(HAVE_ENGINE, "engine dependencies not installed")
class TestServeWorkflowKeepsTheBundle(unittest.TestCase):
    def test_engine_serve_uploads_the_bundle(self):
        with open(os.path.join(REPO, ".github", "workflows", "engine-serve.yml"), encoding="utf-8") as f:
            wf = f.read()
        self.assertIn("actions/upload-artifact", wf)
        self.assertIn("out_real/publish_bundle", wf)
        self.assertRegex(wf, r"retention-days:\s*90")


if __name__ == "__main__":
    unittest.main()
