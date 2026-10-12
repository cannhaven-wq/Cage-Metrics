"""PRED-002 Stage 1 code: the properties it must have before it is run once.

Fast, offline, no data: hand-built fights. The full pipeline was also run end
to end on the engine's synthetic data before the freeze (see
research/experiments/PRED-002/ARTIFACT_RECORD.md); that takes minutes and is
not repeated here.
"""
from __future__ import annotations

import os
import re
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXP = os.path.join(REPO, "research", "experiments", "PRED-002")
sys.path.insert(0, EXP)

try:
    import numpy as np
    import pandas as pd
    import stage1
    HAVE = True
except ImportError:
    HAVE = False


def _fights(rows):
    f = pd.DataFrame(rows, columns=["fight_id", "event_date", "fighter_a_id", "fighter_b_id"])
    f["event_date"] = pd.to_datetime(f["event_date"])
    return f


def _rounds(rows):
    return pd.DataFrame(rows, columns=["fight_id", "fighter_id", "distance_landed", "clinch_landed",
                                       "ground_landed", "td_landed", "ctrl_seconds", "fight_seconds"])


@unittest.skipUnless(HAVE, "engine dependencies not installed")
class TestRatings(unittest.TestCase):
    def setUp(self):
        # fighter 1 beats up 2 on day 1; 1 meets 3 on day 2 and 4 meets 5 the same night;
        # day 3: 1 vs 4
        self.f = _fights([(10, "2020-01-01", 1, 2), (11, "2020-02-01", 1, 3),
                          (12, "2020-02-01", 4, 5), (13, "2020-03-01", 1, 4)])
        self.r = _rounds([(10, 1, 60, 10, 10, 2, 300, 900), (10, 2, 10, 2, 0, 0, 0, 900),
                          (11, 1, 30, 5, 5, 1, 100, 600), (11, 3, 30, 5, 5, 1, 100, 600),
                          (12, 4, 40, 5, 5, 0, 50, 900), (12, 5, 20, 5, 5, 0, 50, 900)])
        self.pairs = stage1.stat_pairs(self.f, self.r, 0.05)
        self.mu = self.pairs[[f"lr_{k}" for k in stage1.CATS]].mean().to_numpy()

    def test_a_fight_never_sees_its_own_result(self):
        feats, prior, _ = stage1.run_ratings(self.pairs, self.f, self.mu, 0.1)
        self.assertTrue(np.allclose(feats[10], 0.0))          # nobody has history yet
        self.assertEqual(prior[10], (False, False))

    def test_same_night_results_are_invisible_to_each_other(self):
        feats, prior, _ = stage1.run_ratings(self.pairs, self.f, self.mu, 0.1)
        # fight 12 (4 vs 5) shares 2020-02-01 with fight 11: both debut-state
        self.assertTrue(np.allclose(feats[12], 0.0))
        self.assertEqual(prior[11], (True, False))

    def test_features_are_antisymmetric(self):
        swapped = self.f.rename(columns={"fighter_a_id": "fighter_b_id", "fighter_b_id": "fighter_a_id"})
        f1, _, _ = stage1.run_ratings(self.pairs, self.f, self.mu, 0.1)
        f2, _, _ = stage1.run_ratings(self.pairs, swapped, self.mu, 0.1)
        for fid in f1:
            np.testing.assert_allclose(f1[fid], -f2[fid], atol=1e-15)

    def test_a_cut_history_gives_the_same_eve_of_fight_state(self):
        full, _, _ = stage1.run_ratings(self.pairs, self.f, self.mu, 0.1)
        cut = self.pairs[self.pairs["event_date"] < pd.Timestamp("2020-03-01")]
        part, _, _ = stage1.run_ratings(cut, self.f[self.f["fight_id"] == 13], self.mu, 0.1)
        np.testing.assert_array_equal(full[13], part[13])

    def test_the_blend_has_no_corner_term(self):
        rng = np.random.default_rng(0)
        X = rng.normal(size=(400, 3))
        y = (rng.random(400) < 1 / (1 + np.exp(-X[:, 0]))).astype(int)
        b = stage1.fit_blend(X, y, 100.0)
        p, p_flip = stage1.sigmoid(X @ b), stage1.sigmoid(-X @ b)
        np.testing.assert_allclose(p + p_flip, 1.0, atol=1e-12)

    def test_devig_sensitivities_are_probabilities_that_respect_the_favourite(self):
        for fn in (stage1.devig_power, stage1.devig_shin):
            with self.subTest(fn=fn.__name__):
                p = fn(0.62, 0.43)
                self.assertTrue(0.5 < p < 1)
                self.assertAlmostEqual(fn(0.52, 0.52), 0.5, places=9)


@unittest.skipUnless(HAVE, "engine dependencies not installed")
class TestReport(unittest.TestCase):
    def test_every_verdict_opens_with_the_three_framing_lines(self):
        for verdict in ("PASS_STAGE1", "STOP_STAGE1", "INVALID", "SUSPECT"):
            with self.subTest(verdict=verdict):
                md = stage1.render({"verdict": verdict, "verdict_reasons": ["x"]})
                head = md.split("**Verdict")[0]
                for line in stage1.FRAMING:
                    self.assertIn(line, head)
                self.assertIn("0.010", head)
                self.assertIn("not a statement about money", head)


class TestConstantsMatchThePreregistration(unittest.TestCase):
    """The code may not quietly hold a different bar from the frozen text."""

    def test_thresholds(self):
        src = open(os.path.join(EXP, "stage1.py"), encoding="utf-8").read()
        prereg = open(os.path.join(EXP, "PREREGISTRATION.md"), encoding="utf-8").read()
        for key, val, text in [
            ("S1_1_min_delta_B", "0.002", "Δ_B ≥ 0.002"),
            ("S1_3_min_delta_M", "0.006", "Δ_M ≥ 0.006"),
            ("S1_4_min_positive_years", "6", "at least 6 of the 9"),
            ("S1_6_max_delta_M", "0.015", "Δ_M ≤ 0.015"),
            ("A1_min_coverage_overall", "0.75", "75%"),
            ("A1_min_coverage_per_year", "0.70", "70%"),
        ]:
            with self.subTest(key=key):
                self.assertRegex(src, rf'"{key}":\s*{re.escape(val)}\b')
                self.assertIn(text, prereg)

    def test_the_experiment_folder_never_reads_a_database(self):
        for name in os.listdir(EXP):
            if name.endswith((".py", ".md")):
                with self.subTest(file=name):
                    body = open(os.path.join(EXP, name), encoding="utf-8").read()
                    self.assertNotRegex(body, re.compile(r"supabase|psql|SUPABASE_|DATABASE_URL|create_client", re.I))


if __name__ == "__main__":
    unittest.main()
