"""PRED-001 tripwires.

The prediction research protocol is only worth having if its rules execute
and its paperwork cannot drift. These tests check four things:

  * the frozen protocol and its code still match the hashes recorded at freeze;
  * the development guard refuses sealed fights;
  * the decision rules give the right verdict in synthetic worlds where the
    truth is known: a model with real information passes, a copy of the
    market and a noisy market are rejected, a leak is flagged, and a real but
    small gain is NOT confirmed;
  * the holdout ledger keeps its budgets and its shape.
"""
import hashlib
import json
import pathlib
import re
import sys
import unittest

import numpy as np

REPO = pathlib.Path(__file__).resolve().parent.parent
PROTO_DIR = REPO / "research" / "protocol"
sys.path.insert(0, str(PROTO_DIR))

import pred_protocol as pp  # noqa: E402

PROTOCOL = json.loads((PROTO_DIR / "protocol.json").read_text())
MANIFEST = json.loads((PROTO_DIR / "holdout_manifest.json").read_text())
LEDGER = json.loads((PROTO_DIR / "holdout_ledger.json").read_text())
OK = dict(pit_audit_passed=True, symmetry_passed=True, preregistration_intact=True)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def world(seed, n_events=300, per=12, market_noise=0.3):
    """Fights whose true probability is known. The market sees the truth
    through noise; a model given the truth has real extra information."""
    r = np.random.default_rng(seed)
    n = n_events * per
    true_logit = r.normal(0, 1.0, n)
    p_true = 1 / (1 + np.exp(-true_logit))
    y = (r.random(n) < p_true).astype(int)
    mkt_logit = true_logit + r.normal(0, market_noise, n)
    p_mkt = 1 / (1 + np.exp(-mkt_logit))
    clusters = np.repeat(np.arange(n_events), per)
    return y, p_true, p_mkt, true_logit, mkt_logit, clusters


class FrozenHashes(unittest.TestCase):
    def test_protocol_is_frozen(self):
        self.assertEqual(PROTOCOL["status"], "frozen")
        self.assertEqual(PROTOCOL["protocol_id"], "PRED-001")

    def test_protocol_text_matches_freeze(self):
        self.assertEqual(
            sha256(REPO / PROTOCOL["protocol_path"]), PROTOCOL["protocol_sha256"],
            "PREDICTION_RESEARCH_PROTOCOL.md changed after freeze. Changing a frozen "
            "protocol is an L3 amendment: date it under '## Amendments' and record the "
            "new hash in protocol.json in the same commit.")

    def test_protocol_code_matches_freeze(self):
        self.assertEqual(
            sha256(REPO / PROTOCOL["code_path"]), PROTOCOL["code_sha256"],
            "pred_protocol.py changed after freeze. The decision rules are the protocol; "
            "changing them is an amendment, not a refactor.")

    def test_amendments_section_exists(self):
        text = (REPO / PROTOCOL["protocol_path"]).read_text()
        self.assertIn("## Amendments", text)


class Partitions(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(pp.partition_of("2024-12-31"), "DEV")
        self.assertEqual(pp.partition_of("2025-01-01"), "H1")
        self.assertEqual(pp.partition_of("2026-07-11"), "H1")
        self.assertEqual(pp.partition_of("2026-07-12"), "SEALED")
        self.assertEqual(pp.partition_of("2027-03-01"), "SEALED")

    def test_dev_guard_refuses_sealed_rows(self):
        rows = [{"event_date": "2024-11-02"}, {"event_date": "2025-02-08"}]
        with self.assertRaises(pp.HoldoutAccessError):
            pp.dev_only(rows)

    def test_dev_guard_passes_dev_rows(self):
        rows = [{"event_date": "2019-05-04"}, {"event_date": "2024-12-14"}]
        self.assertEqual(len(pp.dev_only(rows)), 2)

    def test_manifest_agrees_with_protocol(self):
        h1 = MANIFEST["partitions"]["H1"]["event_dates"]
        self.assertGreaterEqual(h1[0], PROTOCOL["partitions"]["h1"]["start"])
        self.assertLessEqual(h1[1], PROTOCOL["partitions"]["h1"]["end_inclusive"])
        self.assertLess(MANIFEST["partitions"]["DEV"]["event_dates"][1],
                        PROTOCOL["partitions"]["dev"]["end_exclusive"])
        for part in ("DEV", "H1"):
            for k in ("priced_ids_sha256", "priced_outcomes_sha256"):
                self.assertRegex(MANIFEST["partitions"][part][k], r"^[0-9a-f]{64}$")

    def test_contamination_is_disclosed(self):
        text = " ".join(MANIFEST["known_contamination"])
        self.assertIn("Factor Lab", text)
        self.assertIn("non-confirmatory", text)


class SampleSize(unittest.TestCase):
    """The table in §6 of the protocol is reproduced from the code."""

    def test_table(self):
        n = pp.required_n
        expected = {
            (0.064, 0.020, 0.005): 120, (0.064, 0.020, 0.01): 103,
            (0.064, 0.010, 0.005): 479, (0.064, 0.010, 0.01): 412,
            (0.064, 0.005, 0.005): 1914, (0.064, 0.005, 0.01): 1645,
            (0.064, 0.003, 0.005): 5316, (0.064, 0.003, 0.01): 4568,
            (0.32, 0.020, 0.01): 2570, (0.32, 0.010, 0.01): 10277,
            (0.32, 0.005, 0.01): 41108, (0.32, 0.003, 0.01): 114188,
        }
        for (sd, eff, a), want in expected.items():
            self.assertEqual(n(sd, eff, a, 0.8), want, (sd, eff, a))

    def test_h1_detectable_effect(self):
        self.assertAlmostEqual(pp.detectable_effect(0.064, 713, 0.005, 0.8), 0.0082, places=4)
        self.assertAlmostEqual(pp.detectable_effect(0.32, 713, 0.005, 0.8), 0.041, places=3)

    def test_design_effect_is_floored(self):
        self.assertEqual(pp.required_n(0.064, 0.01, 0.01, 0.8, design_effect=0.7),
                         pp.required_n(0.064, 0.01, 0.01, 0.8))

    def test_budget_alphas_hold_familywise_rate(self):
        t = PROTOCOL["thresholds"]
        self.assertLessEqual(t["alpha_h1_per_evaluation"] * t["h1_evaluation_budget"],
                             t["h1_familywise_alpha"] + 1e-12)
        self.assertLessEqual(t["alpha_prospective_per_evaluation"] * t["prospective_confirmatory_budget"],
                             t["prospective_familywise_alpha"] + 1e-12)


class Decisions(unittest.TestCase):
    def test_real_information_passes(self):
        y, pt, pk, *_, cl = world(1, market_noise=0.3)
        ev = pp.evaluate(y, pt, pk, cl, stage="H1", **OK)
        self.assertEqual(ev.verdict, "PASS_H1", ev.reasons)

    def test_small_real_gain_is_not_confirmed(self):
        # True gain ~0.004 on 3,600 fights - the size of the best blend gain
        # ever measured here. The protocol must not call it confirmed.
        y, pt, pk, *_, cl = world(1, market_noise=0.2)
        ev = pp.evaluate(y, pt, pk, cl, stage="H1", **OK)
        self.assertGreater(ev.delta_ll, 0)
        self.assertNotIn(ev.verdict, ("PASS_H1", "PASS_PROSPECTIVE"))

    def test_copy_of_market_is_rejected(self):
        y, _, pk, *_, cl = world(2)
        ev = pp.evaluate(y, pk, pk, cl, stage="H1", **OK)
        self.assertEqual(ev.verdict, "REJECT")

    def test_noisy_market_is_rejected(self):
        y, _, pk, _, ml, cl = world(2)
        r = np.random.default_rng(3)
        pm = 1 / (1 + np.exp(-(ml + r.normal(0, 0.3, len(y)))))
        ev = pp.evaluate(y, pm, pk, cl, stage="H1", **OK)
        self.assertEqual(ev.verdict, "REJECT")

    def test_leak_is_suspect_not_pass(self):
        y, _, pk, *_, cl = world(4)
        ev = pp.evaluate(y, np.where(y == 1, 0.8, 0.2), pk, cl, stage="H1", **OK)
        self.assertEqual(ev.verdict, "SUSPECT")

    def test_overconfident_model_fails_calibration(self):
        y, _, pk, tl, _, cl = world(1, market_noise=0.3)
        ev = pp.evaluate(y, 1 / (1 + np.exp(-1.5 * tl)), pk, cl, stage="H1", **OK)
        self.assertEqual(ev.verdict, "FAIL_CALIBRATION")

    def test_preconditions_make_it_invalid(self):
        y, pt, pk, *_, cl = world(1)
        for bad in ("pit_audit_passed", "symmetry_passed", "preregistration_intact"):
            kw = dict(OK, **{bad: False})
            self.assertEqual(pp.evaluate(y, pt, pk, cl, stage="H1", **kw).verdict, "INVALID", bad)

    def test_too_few_events_is_invalid(self):
        y, pt, pk, *_, cl = world(1, n_events=10, per=12)
        self.assertEqual(pp.evaluate(y, pt, pk, cl, stage="H1", **OK).verdict, "INVALID")

    def test_abstention_cannot_help(self):
        # Abstain on every fight the model would have lost to the market. The
        # abstained fights score at the market's probability, contributing
        # zero; coverage falls under 95% and the look is INVALID anyway.
        y, _, pk, _, ml, cl = world(5)
        r = np.random.default_rng(6)
        pm = 1 / (1 + np.exp(-(ml + r.normal(0, 0.3, len(y)))))
        worse = pp.log_loss_each(y, pm) > pp.log_loss_each(y, pk)
        picked = [None if w else float(p) for w, p in zip(worse, pm)]
        ev = pp.evaluate(y, picked, pk, cl, stage="H1", **OK)
        self.assertEqual(ev.verdict, "INVALID")
        self.assertLess(ev.coverage, 0.95)

    def test_prospective_never_passes_early(self):
        y, pt, pk, *_, cl = world(1, market_noise=0.3)
        ev = pp.evaluate(y, pt, pk, cl, stage="PROSPECTIVE", n_required=len(y) * 3, **OK)
        self.assertEqual(ev.verdict, "UNDERPOWERED")

    def test_prospective_futility_stop(self):
        y, _, pk, *_, cl = world(2)
        ev = pp.evaluate(y, pk, pk, cl, stage="PROSPECTIVE", n_required=int(len(y) * 1.5), **OK)
        self.assertEqual(ev.verdict, "REJECT")
        self.assertTrue(any("futility" in r for r in ev.reasons))

    def test_prospective_passes_at_n(self):
        y, pt, pk, *_, cl = world(1, market_noise=0.3)
        ev = pp.evaluate(y, pt, pk, cl, stage="PROSPECTIVE", n_required=len(y), **OK)
        self.assertEqual(ev.verdict, "PASS_PROSPECTIVE", ev.reasons)

    def test_deterministic(self):
        y, pt, pk, *_, cl = world(7)
        a = pp.evaluate(y, pt, pk, cl, stage="H1", **OK).as_dict()
        b = pp.evaluate(y, pt, pk, cl, stage="H1", **OK).as_dict()
        self.assertEqual(a, b)

    def test_every_verdict_is_declared(self):
        src = (PROTO_DIR / "pred_protocol.py").read_text()
        returned = set(re.findall(r'verdict = "([A-Z_]+)"', src)) | {"PASS_H1", "PASS_PROSPECTIVE"}
        self.assertTrue(returned <= set(PROTOCOL["verdicts"]), returned - set(PROTOCOL["verdicts"]))


class Benchmark(unittest.TestCase):
    def test_devig(self):
        self.assertAlmostEqual(pp.devig_proportional(-110, -110), 0.5)
        p = pp.devig_proportional(-200, 170)
        self.assertAlmostEqual(p, (2 / 3) / (2 / 3 + 100 / 270))

    def test_symmetry_check_catches_corner_reader(self):
        rows = [{"a": 1.0, "b": 0.0, "corner": "A"}]
        swap = lambda r: {"a": r["b"], "b": r["a"], "corner": "B" if r["corner"] == "A" else "A"}
        fair = lambda r: 1 / (1 + np.exp(-(r["a"] - r["b"])))
        reader = lambda r: fair(r) + (0.05 if r["corner"] == "A" else -0.0)
        self.assertEqual(pp.symmetry_violations(fair, rows, swap), [])
        self.assertEqual(len(pp.symmetry_violations(reader, rows, swap)), 1)


class Ledger(unittest.TestCase):
    FIELDS = ["entry", "experiment_id", "stage", "artifact_sha256", "code_commit",
              "auditor", "author_sessions", "evaluated_at", "n_scored", "delta_ll",
              "verdict", "inputs_sha256"]

    def test_budgets_match_protocol(self):
        t = PROTOCOL["thresholds"]
        self.assertEqual(LEDGER["h1_budget"], t["h1_evaluation_budget"])
        self.assertEqual(LEDGER["prospective_budget"], t["prospective_confirmatory_budget"])

    def test_entries_well_formed_and_within_budget(self):
        entries = LEDGER["entries"]
        self.assertLessEqual(sum(e["stage"] == "H1" for e in entries), LEDGER["h1_budget"])
        self.assertLessEqual(sum(e["stage"] == "PROSPECTIVE" for e in entries), LEDGER["prospective_budget"])
        for i, e in enumerate(entries, 1):
            for f in self.FIELDS:
                self.assertIn(f, e, f"ledger entry {i} lacks {f}")
            self.assertEqual(e["entry"], i, "ledger entries are numbered 1..n with no gaps; none may be removed")
            self.assertIn(e["verdict"], PROTOCOL["verdicts"])
            self.assertNotIn(e["auditor"], e["author_sessions"],
                             "the auditor must not be one of the model's authors")

    def test_one_h1_look_per_artifact(self):
        seen = [e["artifact_sha256"] for e in LEDGER["entries"] if e["stage"] == "H1"]
        self.assertEqual(len(seen), len(set(seen)))


class ExperimentCode(unittest.TestCase):
    """Experiment code gets DEV data as an export, never as a live query."""
    FORBIDDEN = re.compile(r"supabase|psql|SUPABASE_|DATABASE_URL|create_client", re.I)

    def test_no_direct_database_access(self):
        root = REPO / "research" / "experiments"
        if not root.exists():
            return
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in (".py", ".js", ".sql", ".sh", ".ipynb"):
                m = self.FORBIDDEN.search(path.read_text(errors="ignore"))
                self.assertIsNone(m, f"{path.relative_to(REPO)} reaches the database directly ({m and m.group(0)})")


if __name__ == "__main__":
    unittest.main()
