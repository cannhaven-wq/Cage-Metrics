"""PRED-001 tripwires.

The prediction research protocol is only worth having if its rules execute
and its paperwork cannot drift quietly. These tests check that:

  * every governed file still matches the last entry of FREEZE.json, the hash
    history starts at the v1.0 freeze pinned below, and each later entry is a
    recorded amendment;
  * the development guard refuses sealed fights;
  * the decision rules give the right verdict in synthetic worlds where the
    truth is known - including that a real but small gain is NOT confirmed;
  * the caller cannot choose the fight set, the sample size or the artifact;
  * every look goes through run_look, is hash-chained into the ledger, and
    the budgets and one-look rules hold;
  * experiment code and data cannot reach sealed fights by the obvious routes.

Amendment 1 (2026-10-13) added most of this after an independent review showed
v1.0's thresholds could be loosened, and its fight set narrowed, with every
test still green.
"""
import hashlib
import json
import math
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np

REPO = pathlib.Path(__file__).resolve().parent.parent
PROTO_DIR = REPO / "research" / "protocol"
sys.path.insert(0, str(PROTO_DIR))

import pred_protocol as pp  # noqa: E402

PROTOCOL = json.loads((PROTO_DIR / "protocol.json").read_text())
MANIFEST = json.loads((PROTO_DIR / "holdout_manifest.json").read_text())
LEDGER = json.loads((PROTO_DIR / "holdout_ledger.json").read_text())
FREEZE = json.loads((PROTO_DIR / "FREEZE.json").read_text())
H1_IDS = [int(x) for x in (PROTO_DIR / "h1_fight_ids.txt").read_text().strip().split(",")]

# The v1.0 freeze, 2026-10-12, commit bc945687. Pinned here so the history
# cannot be rewritten from its first entry: changing these lines is a visible
# edit to the test that guards them.
FIRST_FREEZE = {
    "research/protocol/PREDICTION_RESEARCH_PROTOCOL.md": "95c925c971ad66676d54b282dc567d79adc42ee8eaabbc7e211038dfa2612077",
    "research/protocol/pred_protocol.py": "ff3dd9ba2436aa1ca568121cf2aed8e09c06554c6f96523db3425cf9418ac1d8",
    "research/protocol/protocol.json": "e5f6927e0f5797f073c4eca09484dff136198bec8f7607085318bd07f7ac8c57",
    "research/protocol/holdout_manifest.json": "525d1ae4cfe5cd4c728e335d3aeca5b4cbffb0f5f59c21ec3add27d1a8c1324e",
}


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
    ids = np.arange(100000, 100000 + n)
    return y, p_true, p_mkt, true_logit, mkt_logit, clusters, ids


ART = "b" * 64
AUDITOR = "session_auditor0001"
BUILDER = "session_builder0001"


def sandbox(test, n_required=412, target=0.01, **block_overrides):
    """A temp preregistration (with its pred-registration block), registry and
    ledger. Returns (registry_path, ledger_path)."""
    d = pathlib.Path(tempfile.mkdtemp())
    test.addCleanup(shutil.rmtree, d)
    block = {"experiment_id": "PRED-900", "model_artifact_sha256": ART, "model_class": "incremental",
             "target_effect": target, "sd_used": 0.064, "n_required": n_required,
             "author_sessions": [BUILDER]}
    block.update(block_overrides)
    pre = d / "PREREG.md"
    pre.write_text("# PRED-900\n\n```pred-registration\n" + json.dumps(block) + "\n```\n")
    entry = dict(block, protocol="PRED-001", preregistration_path=str(pre), preregistration_sha256=sha256(pre))
    regf = d / "registry.json"
    regf.write_text(json.dumps({"experiments": [entry]}))
    led = d / "ledger.json"
    led.write_text(json.dumps({"h1_budget": 10, "prospective_budget": 5, "entries": []}))
    return regf, led


def lock_rows(y, p_a, p_mkt, clusters, ids, experiment="PRED-900", artifact=ART):
    return [{"lock_id": i + 1, "fight_id": int(ids[i]), "event_id": int(clusters[i]),
             "actual_lock_at": f"2027-01-{1 + i // 1000:02d}T00:00:{i % 60:02d}+00:00#{i:06d}",
             "p_a": float(p_a[i]), "market_p_a_vigfree": float(p_mkt[i]), "y_a": int(y[i]),
             "corners_unchanged": True, "experiment_id": experiment, "artifact_sha256": artifact}
            for i in range(len(y))]


def population(rows):
    pop = {}
    for r in rows:
        pop.setdefault(str(r["event_id"]), []).append(r["fight_id"])
    return pop


def prospective(y, pm, pk, cl, ids, n_required=None, stage="PROSPECTIVE"):
    """The pure decision rule; provenance is tested separately below."""
    return pp.decide(y, pm, pk, cl, stage=stage, n_required=len(y) if n_required is None else n_required)


class FreezeHistory(unittest.TestCase):
    def test_status(self):
        self.assertEqual(PROTOCOL["status"], "frozen")
        self.assertEqual(PROTOCOL["protocol_id"], "PRED-001")

    def test_first_entry_is_the_v1_freeze(self):
        first = FREEZE["history"][0]
        self.assertEqual(first["version"], "1.0.0")
        for path, sha in FIRST_FREEZE.items():
            self.assertEqual(first["files"].get(path), sha, path)

    def test_current_files_match_the_last_entry(self):
        last = FREEZE["history"][-1]
        self.assertEqual(last["version"], PROTOCOL["version"])
        for path, sha in last["files"].items():
            self.assertEqual(
                sha256(REPO / path), sha,
                f"{path} changed after its last recorded freeze. Changing a frozen PRED-001 "
                f"file is an L3 amendment: date it under '## Amendments', record a decision, and "
                f"append a NEW entry to FREEZE.json in the same commit.")

    def test_every_governed_file_is_frozen(self):
        last = set(FREEZE["history"][-1]["files"])
        for p in ("research/protocol/PREDICTION_RESEARCH_PROTOCOL.md",
                  "research/protocol/pred_protocol.py", "research/protocol/protocol.json",
                  "research/protocol/holdout_manifest.json", "research/protocol/holdout_manifest.sql",
                  "research/protocol/h1_fight_ids.txt", "tests/test_prediction_protocol.py"):
            self.assertIn(p, last)

    def test_each_later_entry_is_a_recorded_amendment_with_a_decision(self):
        text = (REPO / "research/protocol/PREDICTION_RESEARCH_PROTOCOL.md").read_text()
        decisions = (REPO / "coordination/DECISIONS.md").read_text()
        section = text.split("## Amendments", 1)[1]
        documented = re.findall(r"^### Amendment (\d+) — (\d{4}-\d{2}-\d{2})", section, re.M)
        later = FREEZE["history"][1:]
        self.assertEqual(len(documented), len(later),
                         "FREEZE.json and the protocol's ## Amendments disagree on how many amendments exist")
        for (num, date), e in zip(documented, later):
            self.assertEqual(int(num), e["amendment"])
            self.assertEqual(date, e["date"])
            self.assertIs(e["motivated_by_observed_results"], False)
            self.assertRegex(e.get("decision", ""), r"^D-\d{3}$", "an amendment needs an owner decision")
            self.assertIn(f"## {e['decision']} ", decisions, f"{e['decision']} is not in DECISIONS.md")
            self.assertLessEqual(e["looks_taken_before"], len(LEDGER["entries"]))

    def test_history_only_grows_relative_to_main(self):
        """The anti-rewrite check: an entry already on main can never change.
        Rewriting the latest entry in place on a branch - instead of adding an
        amendment - fails here once that entry has merged."""
        main = _from_main("research/protocol/FREEZE.json")
        if main is None:
            self.skipTest("main has no FREEZE.json yet (first merge)")
        base = json.loads(main)["history"]
        self.assertEqual(FREEZE["history"][:len(base)], base,
                         "a FREEZE.json entry that exists on main was edited or removed")

    def test_registered_experiments_are_unchanged_relative_to_main(self):
        main = _from_main("research/registry.json")
        if main is None:
            return
        now = {e["experiment_id"]: e for e in json.loads((REPO / "research/registry.json").read_text())["experiments"]}
        for e in json.loads(main).get("experiments", []):
            if e.get("protocol") != "PRED-001":
                continue
            cur = now.get(e["experiment_id"])
            self.assertIsNotNone(cur, f"{e['experiment_id']} was removed from the registry")
            for k in pp.REG_FIELDS + ("preregistration_path", "preregistration_sha256"):
                self.assertEqual(cur.get(k), e.get(k), f"{e['experiment_id']}.{k} changed after it merged")


def _from_main(path):
    """A file as it is on origin/main, or None if main has no such file.
    In CI the ref must exist: a missing main is a failure, not a skip."""
    has_ref = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify", "-q", "origin/main"],
                             capture_output=True).returncode == 0
    if not has_ref:
        if os.environ.get("CI"):
            raise AssertionError("origin/main is not fetched in CI; the anti-rewrite checks cannot run")
        return None
    r = subprocess.run(["git", "-C", str(REPO), "show", f"origin/main:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


# ---------------------------------------------------------------------------
class Partitions(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(pp.partition_of("2024-12-31"), "DEV")
        self.assertEqual(pp.partition_of("2025-01-01"), "H1")
        self.assertEqual(pp.partition_of("2026-07-11"), "H1")
        self.assertEqual(pp.partition_of("2026-07-12"), "SEALED")

    def test_dev_guard_refuses_sealed_rows(self):
        with self.assertRaises(pp.HoldoutAccessError):
            pp.dev_only([{"event_date": "2024-11-02"}, {"event_date": "2025-02-08"}])

    def test_dev_guard_passes_dev_rows(self):
        self.assertEqual(len(pp.dev_only([{"event_date": "2019-05-04"}, {"event_date": "2024-12-14"}])), 2)

    def test_id_file_matches_manifest(self):
        h1 = MANIFEST["partitions"]["H1"]
        self.assertEqual(len(H1_IDS), h1["decided_priced"])
        self.assertEqual(pp.ids_sha256(H1_IDS), h1["priced_ids_sha256"])
        for rebooked in (43, 46, 8780):
            self.assertNotIn(rebooked, H1_IDS)

    def test_manifest_recipe_and_disclosures(self):
        sql = (PROTO_DIR / "holdout_manifest.sql").read_text()
        h1 = MANIFEST["partitions"]["H1"]
        for k in ("priced_ids_sha256", "priced_prices_sha256", "priced_outcomes_sha256"):
            self.assertIn(h1[k], sql, f"the recipe's expected {k} disagrees with the manifest")
        text = " ".join(MANIFEST["known_contamination"])
        self.assertIn("Factor Lab", text)
        self.assertIn("non-confirmatory", text)
        self.assertIn("first-opened", text)


# ---------------------------------------------------------------------------
class SampleSize(unittest.TestCase):
    def test_table_two_condition(self):
        mue = PROTOCOL["thresholds"]["minimum_useful_effect"]
        want = {(0.020, 0.01): 103, (0.010, 0.01): 412, (0.006, 0.01): 1142,
                (0.005, 0.01): 1645, (0.004, 0.01): 2902,
                (0.020, 0.005): 120, (0.010, 0.005): 479, (0.005, 0.005): 1914}
        for (eff, a), n in want.items():
            self.assertEqual(pp.required_n(0.064, eff, a, 0.8, mue=mue), n, (eff, a))

    def test_target_at_the_minimum_is_refused(self):
        with self.assertRaises(ValueError):
            pp.required_n(0.064, 0.003, 0.01, 0.8, mue=0.003)

    def test_h1_detectable_effect(self):
        self.assertAlmostEqual(pp.detectable_effect(0.064, 710, 0.005, 0.8), 0.0082, places=4)
        self.assertAlmostEqual(pp.detectable_effect(0.32, 710, 0.005, 0.8), 0.041, places=3)

    def test_design_effect_is_floored(self):
        self.assertEqual(pp.required_n(0.064, 0.01, 0.01, 0.8, design_effect=0.7),
                         pp.required_n(0.064, 0.01, 0.01, 0.8))

    def test_budget_alphas_hold_familywise_rate(self):
        t = PROTOCOL["thresholds"]
        self.assertLessEqual(t["alpha_h1_per_evaluation"] * t["h1_evaluation_budget"], t["h1_familywise_alpha"] + 1e-12)
        self.assertLessEqual(t["alpha_prospective_per_evaluation"] * t["prospective_confirmatory_budget"],
                             t["prospective_familywise_alpha"] + 1e-12)


# ---------------------------------------------------------------------------
class Decisions(unittest.TestCase):
    def test_real_information_passes(self):
        y, pt, pk, *_, cl, ids = world(1)
        ev = prospective(y, pt, pk, cl, ids)
        self.assertEqual(ev.verdict, "PASS_PROSPECTIVE", ev.reasons)

    def test_small_real_gain_is_not_confirmed(self):
        # A real gain of the size the best blend ever showed, on a sample the
        # size of the sealed window (720 fights): not enough to confirm it.
        y, pt, pk, *_, cl, ids = world(1, n_events=60, market_noise=0.2)
        ev = prospective(y, pt, pk, cl, ids)
        self.assertGreater(ev.delta_ll, 0)
        self.assertNotIn(ev.verdict, ("PASS_H1", "PASS_PROSPECTIVE"))

    def test_copy_of_market_is_rejected(self):
        y, _, pk, *_, cl, ids = world(2)
        self.assertEqual(prospective(y, pk, pk, cl, ids).verdict, "REJECT")

    def test_noisy_market_is_rejected(self):
        y, _, pk, _, ml, cl, ids = world(2)
        pm = 1 / (1 + np.exp(-(ml + np.random.default_rng(3).normal(0, 0.3, len(y)))))
        self.assertEqual(prospective(y, pm, pk, cl, ids).verdict, "REJECT")

    def test_leak_is_suspect_not_pass(self):
        y, _, pk, *_, cl, ids = world(4)
        self.assertEqual(prospective(y, np.where(y == 1, 0.8, 0.2), pk, cl, ids).verdict, "SUSPECT")

    def test_favourite_heavy_copy_of_market_is_not_suspect(self):
        # v1.0 used an absolute 72% accuracy tripwire: an exact copy of the
        # market on a favourite-heavy set tripped it.
        y, _, pk, *_, cl, ids = world(5)
        keep = (pk > 0.85) | (pk < 0.15)
        cards = np.arange(keep.sum()) // 10
        ev = prospective(y[keep], pk[keep], pk[keep], cards, ids[keep])
        self.assertGreater(ev.acc_market, 0.72)
        self.assertNotEqual(ev.verdict, "SUSPECT")

    def test_overconfident_model_fails_calibration(self):
        y, _, pk, tl, _, cl, ids = world(1)
        ev = prospective(y, 1 / (1 + np.exp(-1.5 * tl)), pk, cl, ids)
        self.assertEqual(ev.verdict, "FAIL_CALIBRATION")

    def test_bad_inputs_are_invalid(self):
        y, pt, pk, *_, cl, ids = world(1)
        cases = {
            "y=0.5": (np.where(np.arange(len(y)) == 0, 0.5, y), pt, pk, ids),
            "nan market": (y, pt, np.where(np.arange(len(y)) == 0, np.nan, pk), ids),
            "model 1.7": (y, np.where(np.arange(len(y)) == 0, 1.7, pt), pk, ids),
        }
        for name, (yy, pm, pkk, ii) in cases.items():
            self.assertEqual(prospective(yy, pm, pkk, cl, ii).verdict, "INVALID", name)
        self.assertEqual(pp.decide([], [], [], [], stage="PROSPECTIVE", n_required=1).verdict, "INVALID")

    def test_too_few_events_is_invalid(self):
        y, pt, pk, *_, cl, ids = world(1, n_events=10, per=12)
        self.assertEqual(prospective(y, pt, pk, cl, ids).verdict, "INVALID")

    def test_cluster_ids_are_compared_as_strings(self):
        y, pt, pk, *_, cl, ids = world(1)
        mixed = [c if i % 2 else str(c) for i, c in enumerate(cl)]
        a = prospective(y, pt, pk, cl, ids)
        b = prospective(y, pt, pk, mixed, ids)
        self.assertEqual((a.ci_low95, a.ci_high95), (b.ci_low95, b.ci_high95))

    def test_abstention_cannot_help(self):
        y, _, pk, _, ml, cl, ids = world(5)
        pm = 1 / (1 + np.exp(-(ml + np.random.default_rng(6).normal(0, 0.3, len(y)))))
        worse = pp.log_loss_each(y, pm) > pp.log_loss_each(y, pk)
        picked = [None if w else float(p) for w, p in zip(worse, pm)]
        ev = prospective(y, picked, pk, cl, ids)
        self.assertEqual(ev.verdict, "INVALID")

    def test_deterministic(self):
        y, pt, pk, *_, cl, ids = world(7)
        self.assertEqual(prospective(y, pt, pk, cl, ids).as_dict(), prospective(y, pt, pk, cl, ids).as_dict())

    def test_every_verdict_is_declared(self):
        src = (PROTO_DIR / "pred_protocol.py").read_text()
        returned = set(re.findall(r'"(INVALID|SUSPECT|REJECT|UNDERPOWERED|FAIL_CALIBRATION|PASS_H1|PASS_PROSPECTIVE|INCONCLUSIVE)"', src))
        self.assertTrue(returned <= set(PROTOCOL["verdicts"]))


# ---------------------------------------------------------------------------
class Provenance(unittest.TestCase):
    """evaluate() checks every input against a fingerprint or derives it.
    Round 2 of the review: flipping 5% of H1 outcomes on the correct ids
    turned REJECT into PASS_H1, and pseudo-cards narrowed the interval."""

    def _h1(self, seed=11):
        r = np.random.default_rng(seed)
        n = len(H1_IDS)
        tl = r.normal(0, 1, n)
        y = (r.random(n) < 1 / (1 + np.exp(-tl))).astype(int)
        p_mkt = 1 / (1 + np.exp(-(tl + r.normal(0, 0.3, n))))
        # American prices whose proportional de-vig is close to p_mkt
        amer = lambda p: int(round(-100 * p / (1 - p))) if p >= 0.5 else int(round(100 * (1 - p) / p))
        rows = [{"fight_id": fid, "event_id": 900 + (i % 63), "y": int(y[i]),
                 "american_a": amer(min(max(p_mkt[i], 0.02), 0.98)), "american_b": amer(1 - min(max(p_mkt[i], 0.02), 0.98)),
                 "p_model": float(1 / (1 + np.exp(-tl[i])))} for i, fid in enumerate(H1_IDS)]
        return rows

    def _patch_manifest(self, rows):
        rs = sorted(rows, key=lambda r: r["fight_id"])
        h = lambda parts: hashlib.sha256(",".join(parts).encode()).hexdigest()
        patched = json.loads(json.dumps(pp.MANIFEST))
        patched["partitions"]["H1"].update({
            "priced_ids_sha256": h(str(r["fight_id"]) for r in rs),
            "priced_prices_sha256": h(f"{r['fight_id']}:{r['american_a']}:{r['american_b']}" for r in rs),
            "priced_outcomes_sha256": h(f"{r['fight_id']}:{r['y']}" for r in rs),
            "priced_events_sha256": h(f"{r['fight_id']}:{r['event_id']}" for r in rs)})
        old = pp.MANIFEST
        pp.MANIFEST = patched
        self.addCleanup(setattr, pp, "MANIFEST", old)

    def _eval(self, rows, regf, stage="H1", **kw):
        args = dict(stage=stage, experiment_id="PRED-900", artifact_sha256=ART, pit_audit_passed=True,
                    symmetry_passed=True, registry_path=regf)
        args.update(kw)
        return pp.evaluate(rows, **args)

    def test_h1_honest_rows_are_scored(self):
        regf, _ = sandbox(self)
        rows = self._h1()
        self._patch_manifest(rows)
        self.assertNotEqual(self._eval(rows, regf).verdict, "INVALID")

    def test_h1_real_manifest_rejects_synthetic_rows(self):
        regf, _ = sandbox(self)
        ev = self._eval(self._h1(), regf)
        self.assertEqual(ev.verdict, "INVALID")

    def test_h1_tampering_is_invalid(self):
        regf, _ = sandbox(self)
        rows = self._h1()
        self._patch_manifest(rows)
        flipped = [dict(r, y=1 - r["y"]) if i % 20 == 0 else r for i, r in enumerate(rows)]
        repriced = [dict(r, american_a=r["american_a"] + 5) if i == 3 else r for i, r in enumerate(rows)]
        pseudo = [dict(r, event_id=10000 + i // 2) for i, r in enumerate(rows)]
        dropped = rows[:-35]
        for name, bad in (("flipped outcomes", flipped), ("repriced", repriced),
                          ("pseudo-cards", pseudo), ("dropped fights", dropped)):
            self.assertEqual(self._eval(bad, regf).verdict, "INVALID", name)

    def test_preconditions_make_it_invalid(self):
        regf, _ = sandbox(self)
        rows = self._h1()
        self._patch_manifest(rows)
        for kw in ({"pit_audit_passed": False}, {"symmetry_passed": False}, {"artifact_sha256": "c" * 64}):
            self.assertEqual(self._eval(rows, regf, **kw).verdict, "INVALID", kw)

    def _locks(self, n_events=300):
        y, pt, pk, *_, cl, ids = world(1, n_events=n_events)
        return lock_rows(y, pt, pk, cl, ids)

    def test_prospective_scores_exactly_the_first_n_required_locks(self):
        regf, _ = sandbox(self, n_required=3000)
        rows = self._locks()
        ev = self._eval(rows, regf, stage="PROSPECTIVE", card_population=population(rows))
        self.assertEqual(ev.n_eligible, 3000)
        shuffled = list(reversed(rows))
        ev2 = self._eval(shuffled, regf, stage="PROSPECTIVE", card_population=population(rows))
        self.assertEqual(ev.fight_ids_sha256, ev2.fight_ids_sha256, "order must come from lock time, not the caller")

    def test_prospective_refusals(self):
        regf, _ = sandbox(self, n_required=3000)
        rows = self._locks()
        pop = population(rows)
        cases = {
            "too few locks": (rows[:2000], pop),
            "foreign artifact": ([dict(r, artifact_sha256="c" * 64) if i == 0 else r for i, r in enumerate(rows)], pop),
            "selective locking": ([r for r in rows if r["y_a"] == 1 or r["lock_id"] % 3], pop),
            "no population": (rows, None),
        }
        for name, (rr, pp_) in cases.items():
            self.assertEqual(self._eval(rr, regf, stage="PROSPECTIVE", card_population=pp_).verdict, "INVALID", name)

    def test_interim_is_interim(self):
        regf, _ = sandbox(self, n_required=3000)
        rows = self._locks(n_events=150)
        ev = self._eval(rows, regf, stage="PROSPECTIVE_INTERIM", card_population=population(rows))
        self.assertIn(ev.verdict, ("UNDERPOWERED", "REJECT"))
        big = self._locks()
        ev = self._eval(big, regf, stage="PROSPECTIVE_INTERIM", card_population=population(big))
        self.assertEqual(ev.verdict, "INVALID")


class Registration(unittest.TestCase):
    """Round 2: registry n_required and artifact could be edited after a look
    because only the preregistration file was hashed. They are now read from
    the hashed file and the registry must repeat them."""

    def test_good_registration_loads(self):
        regf, _ = sandbox(self)
        self.assertEqual(pp.load_registration("PRED-900", regf)["n_required"], 412)

    def test_registry_disagreeing_with_the_frozen_file_is_refused(self):
        regf, _ = sandbox(self)
        reg = json.loads(regf.read_text())
        for k, v in (("n_required", 1), ("model_artifact_sha256", "c" * 64), ("target_effect", 0.02)):
            bad = json.loads(json.dumps(reg))
            bad["experiments"][0][k] = v
            regf.write_text(json.dumps(bad))
            with self.assertRaises(pp.ProtocolViolation, msg=k):
                pp.load_registration("PRED-900", regf)

    def test_frozen_values_are_validated(self):
        for kw in ({"n_required": 100}, {"model_class": "standalone"}, {"target_effect": 0.003},
                   {"target_effect": 0.05}, {"sd_used": 0.03}, {"author_sessions": []}):
            regf, _ = sandbox(self, **kw)
            with self.assertRaises(pp.ProtocolViolation, msg=str(kw)):
                pp.load_registration("PRED-900", regf)

    def test_edited_preregistration_is_refused(self):
        regf, _ = sandbox(self)
        pre = pathlib.Path(json.loads(regf.read_text())["experiments"][0]["preregistration_path"])
        pre.write_text(pre.read_text().replace('"n_required": 412', '"n_required": 999'))
        with self.assertRaises(pp.ProtocolViolation):
            pp.load_registration("PRED-900", regf)


# ---------------------------------------------------------------------------
class Benchmark(unittest.TestCase):
    def test_devig(self):
        self.assertAlmostEqual(pp.devig_proportional(-110, -110), 0.5)
        self.assertAlmostEqual(pp.devig_proportional(-200, 170), (2 / 3) / (2 / 3 + 100 / 270))

    def test_symmetry_check_catches_corner_reader(self):
        rows = [{"a": 1.0, "b": 0.0, "corner": "A"}]
        swap = lambda r: {"a": r["b"], "b": r["a"], "corner": "B" if r["corner"] == "A" else "A"}
        fair = lambda r: 1 / (1 + np.exp(-(r["a"] - r["b"])))
        reader = lambda r: fair(r) + (0.05 if r["corner"] == "A" else 0.0)
        self.assertEqual(pp.symmetry_violations(fair, rows, swap), [])
        self.assertEqual(len(pp.symmetry_violations(reader, rows, swap)), 1)


# ---------------------------------------------------------------------------
class Ledger(unittest.TestCase):
    def test_committed_ledger_is_intact(self):
        self.assertEqual(pp.verify_ledger_chain(LEDGER), [])
        t = PROTOCOL["thresholds"]
        self.assertEqual(LEDGER["h1_budget"], t["h1_evaluation_budget"])
        self.assertEqual(LEDGER["prospective_budget"], t["prospective_confirmatory_budget"])

    def test_ledger_only_grows_relative_to_main(self):
        main = _from_main("research/protocol/holdout_ledger.json")
        if main is None:
            self.skipTest("main has no ledger yet (first merge)")
        main_entries = json.loads(main)["entries"]
        self.assertEqual(LEDGER["entries"][:len(main_entries)], main_entries,
                         "an entry that exists on main was removed or edited")

    def _look(self, regf, led, stage="PROSPECTIVE", auditor=AUDITOR, n_events=300):
        y, pt, pk, *_, cl, ids = world(1, n_events=n_events)
        rows = lock_rows(y, pt, pk, cl, ids)
        return pp.run_look(experiment_id="PRED-900", stage=stage, rows=rows, artifact_sha256=ART,
                           pit_audit_passed=True, symmetry_passed=True, auditor=auditor,
                           evaluated_at="2027-01-01T00:00:00Z", card_population=population(rows),
                           _ledger_path=led, _registry_path=regf, _authors_from_git=False)

    def test_run_look_records_and_chains(self):
        regf, led = sandbox(self, n_required=3600)
        self._look(regf, led, stage="PROSPECTIVE_INTERIM", n_events=150)
        ev = self._look(regf, led)
        self.assertEqual(ev.verdict, "PASS_PROSPECTIVE", ev.reasons)
        data = json.loads(led.read_text())
        self.assertEqual([e["stage"] for e in data["entries"]], ["PROSPECTIVE_INTERIM", "PROSPECTIVE"])
        self.assertEqual(pp.verify_ledger_chain(data), [])

    def test_second_confirmatory_look_is_refused(self):
        regf, led = sandbox(self, n_required=3600)
        self._look(regf, led)
        with self.assertRaises(pp.ProtocolViolation):
            self._look(regf, led)

    def test_auditor_must_be_identifiable_and_not_an_author(self):
        regf, led = sandbox(self, n_required=3600)
        for who in (BUILDER, "me", ""):
            with self.assertRaises(pp.ProtocolViolation, msg=who):
                self._look(regf, led, auditor=who)
        self.assertEqual(json.loads(led.read_text())["entries"], [])

    def test_a_crash_is_recorded(self):
        regf, led = sandbox(self, n_required=3600)
        pp.run_look(experiment_id="PRED-900", stage="PROSPECTIVE", rows=[{"nonsense": True}], artifact_sha256=ART,
                    pit_audit_passed=True, symmetry_passed=True, auditor=AUDITOR, evaluated_at="x",
                    card_population={"1": [1]}, _ledger_path=led, _registry_path=regf, _authors_from_git=False)
        e = json.loads(led.read_text())["entries"]
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0]["verdict"], "INVALID")

    def test_tampering_is_detected(self):
        regf, led = sandbox(self, n_required=3600)
        self._look(regf, led, stage="PROSPECTIVE_INTERIM", n_events=150)
        self._look(regf, led)
        data = json.loads(led.read_text())
        data["entries"][0]["verdict"] = "PASS_PROSPECTIVE"
        self.assertTrue(pp.verify_ledger_chain(data))
        data = json.loads(led.read_text())
        del data["entries"][0]
        self.assertTrue(pp.verify_ledger_chain(data))


class ExperimentCode(unittest.TestCase):
    """Conventions with tripwires, not a sandbox: an agent holding database
    credentials can still read 2025 results. These catch the obvious routes."""
    ALLOWED = (".py", ".md", ".json", ".csv", ".txt", ".yaml", ".yml", ".ipynb")
    FORBIDDEN = re.compile(r"supabase|psql|postgres(ql)?://|SUPABASE_|DATABASE_URL|create_client|"
                           r"\bpsycopg|\bfetch_odds\b|export_data", re.I)
    SEALED_DATE = re.compile(r"\b20(2[5-9])[-/._]?(0[1-9]|1[0-2])[-/._]?(0[1-9]|[12]\d|3[01])\b")
    DATA_SUFFIXES = (".csv", ".json", ".txt", ".yaml", ".yml")

    def _files(self):
        root = REPO / "research" / "experiments"
        if not root.exists():
            return []
        return [p for p in root.rglob("*") if p.is_file()]

    def test_only_reviewable_file_types(self):
        for path in self._files():
            self.assertIn(path.suffix.lower(), self.ALLOWED,
                          f"{path.relative_to(REPO)}: binary or unreviewable data (parquet, pickle, npy...) "
                          f"cannot be checked for sealed rows and is not allowed in an experiment folder")

    def test_no_direct_database_access(self):
        for path in self._files():
            if path.suffix == ".md":
                continue
            m = self.FORBIDDEN.search(path.read_text(errors="ignore"))
            self.assertIsNone(m, f"{path.relative_to(REPO)} reaches the database directly ({m and m.group(0)})")

    def test_committed_data_holds_no_sealed_fight_dates(self):
        for path in self._files():
            if path.suffix.lower() in self.DATA_SUFFIXES:
                m = self.SEALED_DATE.search(path.read_text(errors="ignore"))
                self.assertIsNone(m, f"{path.relative_to(REPO)} contains a sealed date ({m and m.group(0)})")

    def test_the_date_pattern_catches_the_common_spellings(self):
        for d in ("2025-01-11", "2025/01/11", "20250111", "2026.07.11"):
            self.assertRegex(d, self.SEALED_DATE)
        for d in ("2024-12-31", "20241231"):
            self.assertNotRegex(d, self.SEALED_DATE)


if __name__ == "__main__":
    unittest.main()
