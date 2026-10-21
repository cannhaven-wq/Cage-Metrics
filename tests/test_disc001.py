"""DISC-001 — the factor discovery run stays honest.

Checks that the committed results follow the preregistered rules, that the
features are point-in-time and corner-symmetric on the committed data, and
that a rerun reproduces the committed verdicts.
"""
import json
import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
EXP = REPO / "research" / "experiments" / "DISC-001"
# No __pycache__ in an experiment folder: ExperimentCode allows reviewable files only.
sys.dont_write_bytecode = True
sys.path.insert(0, str(EXP))

import discover as d  # noqa: E402


class Holm(unittest.TestCase):
    def test_step_down_stops_at_first_failure(self):
        # 0.01 <= 0.05/3, 0.02 <= 0.05/2, 0.06 > 0.05/1
        self.assertEqual(d.holm([0.02, 0.01, 0.06]), [True, True, False])
        # first fails, so nothing survives even though 0.04 < 0.05
        self.assertEqual(d.holm([0.03, 0.04]), [False, False])


class CommittedResults(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = json.loads((EXP / "results.json").read_text())

    def test_every_preregistered_factor_is_reported(self):
        self.assertEqual(list(self.r["primary"]), [k for k, _ in d.PRIMARY])
        self.assertEqual(list(self.r["interactions"]), [k for k, _ in d.INTERACTIONS])
        self.assertEqual(set(self.r["combined"]), {"C1", "C2"})

    def test_verdicts_follow_the_rules(self):
        for fam in ("primary", "interactions"):
            keys = list(self.r[fam])
            surv = d.holm([self.r[fam][k]["p_one_sided"] for k in keys])
            for k, s in zip(keys, surv):
                e = self.r[fam][k]
                self.assertEqual(e["holm_survives"], s, k)
                self.assertEqual(e["verdict"], d.verdict(e["fired"], e["p_one_sided"], s), k)

    def test_contaminated_factors_are_flagged(self):
        flagged = {k for k, e in self.r["primary"].items() if e["contaminated"]}
        self.assertEqual(flagged, {"F13", "F14"})

    def test_scored_window_is_dev_only(self):
        self.assertEqual(self.r["data"]["test_years"], [2012, 2024])


HAVE_DATA = all((EXP / "data" / n).exists() for n in ("dev_fights.csv", "dev_fighters.csv"))


class DataStaysOut(unittest.TestCase):
    """The export is not committed (D-034); its hashes are."""

    def test_withheld_hashes_are_recorded(self):
        readme = (EXP / "data" / "README.md").read_text()
        for sha in ("2904655f1cee82eb6fd9fb9c7dbb513b4f337e0343ed5576099d26eefe90df92",
                    "0ae32b6bd0e7f37f913462e6b79d25e65b2f60d6772840c747875d43348a30db"):
            self.assertIn(sha, readme)

    def test_local_copies_if_present_match_their_hash(self):
        import hashlib
        want = {"dev_fights.csv": "2904655f1cee82eb6fd9fb9c7dbb513b4f337e0343ed5576099d26eefe90df92",
                "dev_fighters.csv": "0ae32b6bd0e7f37f913462e6b79d25e65b2f60d6772840c747875d43348a30db"}
        for n, sha in want.items():
            p = EXP / "data" / n
            if p.exists():
                self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), sha, n)


@unittest.skipUnless(HAVE_DATA, "the DISC-001 export is not committed (D-034); "
                                "obtain it as research/experiments/DISC-001/data/README.md says")
class OnTheData(unittest.TestCase):
    """Runs the real pipeline on the DEV export (seconds, numpy only)."""

    @classmethod
    def setUpClass(cls):
        cls.fights, cls.dob = d.load()
        cls.feats = d.build(cls.fights, cls.dob)

    def test_point_in_time_and_corner_swap_audit(self):
        scored = [f for f in self.fights if f["date"].year in d.TEST_YEARS and f["res"] in ("A", "B")
                  and f["bfo_a"] is not None and f["bfo_b"] is not None]
        self.assertEqual(len(d.audit(self.fights, self.dob, self.feats, scored)), d.AUDIT_N)

    def test_rerun_reproduces_committed_verdicts(self):
        committed_text = (EXP / "results.json").read_text()
        committed = json.loads(committed_text)
        try:
            out = d.main()                      # main() rewrites results.json ...
        finally:
            (EXP / "results.json").write_text(committed_text)   # ... so put the record back
        for fam in ("primary", "interactions"):
            for k, e in committed[fam].items():
                self.assertEqual(out[fam][k]["verdict"], e["verdict"], k)
                self.assertAlmostEqual(out[fam][k]["gain"], e["gain"], places=12, msg=k)


if __name__ == "__main__":
    unittest.main()
