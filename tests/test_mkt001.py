"""MKT-001 — the committed result follows its preregistered rule, and reruns exactly."""
import hashlib
import json
import pathlib
import subprocess
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
EXP = REPO / "research" / "experiments" / "MKT-001"
DATA = REPO / "research" / "discovery" / "data" / "dev" / "fights.csv"


class CommittedResult(unittest.TestCase):
    def setUp(self):
        self.r = json.loads((EXP / "results.json").read_text())

    def test_scored_set_is_pred001_dev(self):
        self.assertEqual(self.r["data"]["decided_priced"], 6824)
        self.assertLessEqual(self.r["data"]["years"][1], 2024)

    def test_decision_follows_the_preregistered_rule(self):
        ll = {m: v["all"]["log_loss"] for m, v in self.r["methods"].items()}
        best = min(ll, key=ll.get)
        self.assertEqual(self.r["decision"]["lowest_log_loss"], best)
        wins = []
        for o in (m for m in ll if m != best):
            k = f"{best}_vs_{o}" if f"{best}_vs_{o}" in self.r["paired"] else f"{o}_vs_{best}"
            p = self.r["paired"][k]
            better = p["mean_ll_advantage"] > 0 if k.startswith(best) else p["mean_ll_advantage"] < 0
            wins.append(better and p["holm_survives"])
        self.assertEqual(self.r["decision"]["recommended_reporting_baseline"], best if all(wins) else None)

    def test_band_free_devig_matches_the_frozen_helpers(self):
        self.assertLess(self.r["band_free_cross_check"]["max_abs_diff"], 1e-9)


@unittest.skipUnless(DATA.exists(), "the DEV export is not committed (D-034); see research/discovery/WITHHELD.json")
class Rerun(unittest.TestCase):
    def test_rerun_is_byte_identical(self):
        before = (EXP / "results.json").read_bytes()
        try:
            subprocess.run([sys.executable, "-I", str(EXP / "run.py")], check=True, capture_output=True)
            self.assertEqual(hashlib.sha256((EXP / "results.json").read_bytes()).hexdigest(),
                             hashlib.sha256(before).hexdigest())
        finally:
            (EXP / "results.json").write_bytes(before)


if __name__ == "__main__":
    unittest.main()
