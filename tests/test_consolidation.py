"""Research consolidation (D-034): the clean integration stays verifiable.

  * every file carried over from the two research branches is either
    byte-identical to its source commit or recorded as deliberately changed,
    with its current hash;
  * no raw data export is tracked anywhere under research/;
  * the frozen PRED-001 files are exactly what FREEZE.json's last entry says
    (the contamination amendment is prepared, not applied).
"""
import hashlib
import json
import pathlib
import subprocess
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
PROV = REPO / "research" / "consolidation" / "PROVENANCE.json"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


class Provenance(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(PROV.read_text())

    def test_every_carried_file_matches_its_record(self):
        for rel, m in self.doc["files"].items():
            p = REPO / rel
            self.assertTrue(p.exists(), f"{rel} was carried over and is now missing")
            want = m["source_sha256"] if m["status"] == "unchanged" else m["sha256_now"]
            self.assertEqual(sha(p), want, f"{rel} changed without its provenance record being updated")

    def test_changed_files_are_not_claimed_unchanged(self):
        for rel, m in self.doc["files"].items():
            if m["status"] == "changed_in_consolidation":
                self.assertNotEqual(m["sha256_now"], m["source_sha256"], rel)

    def test_no_data_export_is_tracked_under_research(self):
        tracked = subprocess.check_output(["git", "ls-files", "research"], cwd=REPO, text=True).split()
        exports = [f for f in tracked if f.endswith(".csv") and ("/data/" in f or "oos_predictions" in f)
                   and "-synthetic/" not in f]
        allowed = {"research/backtest/data/actionable_coverage_by_card.csv"}   # on main before D-034: counts, no outcomes
        self.assertEqual(set(exports) - allowed, set())


class FrozenProtocolUntouched(unittest.TestCase):
    def test_pred001_files_match_the_last_freeze_entry(self):
        freeze = json.loads((REPO / "research" / "protocol" / "FREEZE.json").read_text())
        last = freeze["history"][-1]
        self.assertEqual(last["version"], "1.1.0", "an amendment was applied; it needs the owner's approval")
        for rel, h in last["files"].items():
            self.assertEqual(sha(REPO / rel), h, rel)


if __name__ == "__main__":
    unittest.main()
