"""Discovery Engine, Phase 1 - tripwires and behaviour.

    python -m pytest tests/test_discovery.py -q

What this file guarantees:

  * the committed DEV export holds no fight on or after 2025-01-01, matches
    PRED-001's frozen DEV fingerprints, and its loader refuses a sealed row;
  * the discovery code has no route to a database and no unreviewable files;
  * the model is corner-symmetric by PRED-001's own checker;
  * each leakage detector catches the leak it exists for (a feature built
    from the fight's own result, a corner-label reader, a forbidden source,
    a too-good result);
  * end to end, on clearly labelled synthetic data where the truth is known,
    the engine finds a planted effect, finds nothing in a null world, and
    quarantines an effect that is too good to be true;
  * the run ledger is an intact hash chain, every recorded file exists
    unchanged, and no entry present on main disappears - so an unsuccessful
    run cannot be deleted to leave only the good one;
  * a discovery run cannot loosen a PRED-001 threshold;
  * engine 1.1 (consolidation audit): the de-vig stability check can never
    pass without being run (E1), the 0.003 size test is against the
    re-weighted market (E2), and features whose verdict CFL has already seen
    on sealed years are flagged (E3);
  * raw data exports and per-fight predictions are never committed (D-034),
    and every withheld file is still pinned by sha256.

The tests that need the DEV export itself skip, with the reason printed, when
it is not on disk: it is no longer committed. Obtain it as WITHHELD.json says
and they run.
"""
import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

REPO = pathlib.Path(__file__).resolve().parent.parent
DISC = REPO / "research" / "discovery"
sys.path.insert(0, str(DISC))

from cfl_discovery import candidates as C  # noqa: E402
from cfl_discovery import data as D  # noqa: E402
from cfl_discovery import evaluate as E  # noqa: E402
from cfl_discovery import features as F  # noqa: E402
from cfl_discovery import leakage as L  # noqa: E402
from cfl_discovery import ledger as LG  # noqa: E402
from cfl_discovery import model as M  # noqa: E402
from cfl_discovery import run as RUN  # noqa: E402
from cfl_discovery import synthetic as SY  # noqa: E402
import pred_protocol as pp  # noqa: E402

# Full-size synthetic world: 4,752 fights. A smaller one is honestly too
# underpowered to find a realistic planted effect after correction.
SMALL = dict(n_fighters=700, events_per_year=24, fights_per_event=11)
FAST = {"interactions": False, "permutations": 2, "pit_audit_dates": 2, "noise_controls": 6,
        "bootstrap_screen": 300, "bootstrap_confirm": 1000}


def _run_synthetic(tmp: pathlib.Path, planted: float, **cfg):
    ov = dict(FAST, **cfg)
    return RUN.run("synthetic", cfg_overrides=ov, out_root=tmp / "runs", ledger_path=tmp / "ledger.jsonl",
                   synthetic_kwargs=dict(SMALL, planted_reach=planted), verbose=False)


DEV_DIR = DISC / "data" / "dev"
HAVE_DEV = (DEV_DIR / "fights.csv").exists() and (DEV_DIR / "fighters.csv").exists()
NO_DEV = "the DEV export is not committed (D-034); obtain it as research/discovery/WITHHELD.json says"


def _withheld():
    return json.loads((DISC / "WITHHELD.json").read_text())["files"]


# ----------------------------------------------------------------------------- data
class WithheldData(unittest.TestCase):
    """Runs everywhere, with or without the data on disk."""

    def test_no_raw_export_or_real_per_fight_file_is_tracked(self):
        out = subprocess.check_output(["git", "ls-files", "research/discovery", "research/experiments"],
                                      cwd=REPO, text=True).split()
        for f in out:
            if f.endswith(".csv"):
                self.assertTrue(f.startswith("research/discovery/runs/") and "-synthetic/" in f,
                                f"{f} is tracked; data exports and real per-fight files stay out (D-034)")

    def test_withheld_hashes_agree_with_the_manifest_and_the_ledger(self):
        held = _withheld()
        man = json.loads((DEV_DIR / "DATA_MANIFEST.json").read_text())
        for name, meta in man["files"].items():
            self.assertEqual(held[f"data/dev/{name}"]["sha256"], meta["sha256"], name)
        for e in LG.read(DISC / "ledger.jsonl"):
            if e["mode"] == "real-dev":
                for name, sha in e["data_sha256"].items():
                    self.assertEqual(held[f"data/dev/{name}"]["sha256"], sha, name)

    def test_local_copies_if_present_match_their_hash(self):
        for rel, meta in _withheld().items():
            p = DISC / rel
            if p.exists():
                self.assertEqual(D.file_sha256(p), meta["sha256"], rel)

    def test_missing_export_says_how_to_get_it(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(FileNotFoundError, "WITHHELD.json"):
                D.load_dev(pathlib.Path(t))

    def test_ledger_accepts_a_withheld_file_only_with_the_recorded_hash(self):
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            p = t / "l.jsonl"
            LG.append(p, {"run_id": "a", "files": {"gone.csv": "ab" * 32}})
            self.assertTrue(LG.verify(LG.read(p), root=t))                     # missing, not withheld
            (t / "WITHHELD.json").write_text(json.dumps({"files": {"gone.csv": {"sha256": "cd" * 32}}}))
            self.assertTrue(LG.verify(LG.read(p), root=t))                     # withheld, wrong hash
            (t / "WITHHELD.json").write_text(json.dumps({"files": {"gone.csv": {"sha256": "ab" * 32}}}))
            self.assertEqual(LG.verify(LG.read(p), root=t), [])                # withheld, right hash
            (t / "gone.csv").write_text("edited")
            self.assertTrue(LG.verify(LG.read(p), root=t))                     # present must still match


    def test_loader_refuses_a_sealed_row_without_the_real_data(self):
        dev = SY.make(**SMALL)
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            f = dev.fights.copy()
            f["event_date"] = f["event_date"].astype(str)
            f.loc[len(f) - 1, "event_date"] = "2025-01-11"
            f.to_csv(t / "fights.csv", index=False)
            dev.fighters.to_csv(t / "fighters.csv", index=False)
            with self.assertRaises(pp.HoldoutAccessError):
                D.load_dev(t, require_manifest=False)


class EngineV11(unittest.TestCase):
    """Consolidation audit fixes E1-E3 (engine 1.1.0)."""
    CFG = {"devig_sensitivities": ["q_close_power", "q_close_shin"]}

    def test_e1_an_unevaluated_devig_check_fails_instead_of_passing(self):
        self.assertFalse(RUN.devig_stable({}, self.CFG))
        self.assertFalse(RUN.devig_stable({"devig_sensitivity_delta_vs_recalibrated": {"q_close_power": 0.01}},
                                          self.CFG))
        self.assertFalse(RUN.devig_stable({"devig_sensitivity_delta_vs_recalibrated":
                                           {"q_close_power": 0.01, "q_close_shin": -0.001}}, self.CFG))
        self.assertTrue(RUN.devig_stable({"devig_sensitivity_delta_vs_recalibrated":
                                          {"q_close_power": 0.01, "q_close_shin": 0.002}}, self.CFG))
        self.assertFalse(RUN.devig_stable({"devig_sensitivity_delta_vs_recalibrated": {}},
                                          {"devig_sensitivities": []}))

    def test_e2_size_is_judged_against_the_reweighted_market(self):
        # 0.004 over the raw market, of which 0.003 is the de-vig's own bias
        self.assertFalse(RUN.useful_size({"delta_vs_market": 0.004, "delta_vs_recalibrated": 0.001}, 0.003))
        self.assertTrue(RUN.useful_size({"delta_vs_market": 0.002, "delta_vs_recalibrated": 0.0031}, 0.003))

    def test_e3_contaminated_features_and_everything_built_on_them_are_flagged(self):
        fights, stats, fighters = D.prepare(SY.make(**SMALL))
        _, specs = F.build(fights, stats, fighters)
        flagged = {s.name for s in specs if s.h1_contaminated}
        for n in ("d_age", "d_ufc_raw_rate", "d_ufc_net", "d_win_rate", "d_td_def"):
            self.assertIn(n, flagged)
        self.assertNotIn("d_streak", flagged)
        cands = {c.cid: c for c in C.build_catalog(specs, {"interactions": True})}
        self.assertTrue(cands["S:d_age"].h1_contaminated)
        self.assertTrue(cands["I:d_streak*c_age_mean"].h1_contaminated)     # via its context
        self.assertFalse(cands["S:d_streak"].h1_contaminated)

    def test_new_runs_use_the_v1_1_config_and_the_record_keeps_v1(self):
        self.assertEqual(RUN.load_config()["config_id"], "DISC-P1-v1.1")
        e = LG.read(DISC / "ledger.jsonl")[0]
        self.assertEqual(e["config_id"], "DISC-P1-v1")


@unittest.skipUnless(HAVE_DEV, NO_DEV)
class DevExport(unittest.TestCase):
    def test_loads_and_matches_the_frozen_manifest(self):
        dev = D.load_dev()
        self.assertTrue(dev.manifest_check["match"], dev.manifest_check)
        self.assertEqual(dev.manifest_check["recomputed"]["decided_priced"], 6824)

    def test_no_sealed_fight_in_any_committed_data_file(self):
        # The fight data files only: DATA_MANIFEST.json legitimately carries
        # the date the export was taken.
        f = pd.read_csv(DISC / "data" / "dev" / "fights.csv", usecols=["event_date"])
        self.assertLess(f.event_date.max(), "2025-01-01")
        sealed = re.compile(r"\b20(2[5-9])[-/._]?(0[1-9]|1[0-2])[-/._]?(0[1-9]|[12]\d|3[01])\b")
        for p in (DISC / "data").rglob("*"):
            if p.is_file() and p.suffix == ".csv":
                m = sealed.search(p.read_text(errors="ignore"))
                self.assertIsNone(m, f"{p.relative_to(REPO)} contains a sealed date ({m and m.group(0)})")

    def test_data_manifest_matches_the_files(self):
        man = json.loads((DISC / "data" / "dev" / "DATA_MANIFEST.json").read_text())
        for name, meta in man["files"].items():
            self.assertEqual(D.file_sha256(DISC / "data" / "dev" / name), meta["sha256"], name)
        self.assertEqual(D.file_sha256(DISC / "export_dev.sql"), man["recipe_sha256"])

    def test_loader_refuses_a_sealed_row(self):
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            for n in ("fights.csv", "fighters.csv"):
                shutil.copy(DISC / "data" / "dev" / n, t / n)
            f = pd.read_csv(t / "fights.csv", dtype=str, keep_default_na=False)
            f.loc[len(f) - 1, "event_date"] = "2025-01-11"
            f.to_csv(t / "fights.csv", index=False)
            with self.assertRaises(pp.HoldoutAccessError):
                D.load_dev(t, require_manifest=False)

    def test_loader_refuses_an_export_that_drifted(self):
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            for n in ("fights.csv", "fighters.csv"):
                shutil.copy(DISC / "data" / "dev" / n, t / n)
            f = pd.read_csv(t / "fights.csv", dtype=str, keep_default_na=False)
            i = f.index[(f.winner == "a") & (f.bfo_close_a != "")][0]
            f.loc[i, "winner"] = "b"          # one flipped outcome
            f.to_csv(t / "fights.csv", index=False)
            with self.assertRaises(ValueError):
                D.load_dev(t)


class ResearchFolderLint(unittest.TestCase):
    """Same tripwires PRED-001 applies to research/experiments/, applied here."""
    FORBIDDEN = re.compile(r"supabase|psql|postgres(ql)?://|SUPABASE_|DATABASE_URL|create_client|"
                           r"\bpsycopg|\bfetch_odds\b|export_data", re.I)
    ALLOWED = (".py", ".md", ".json", ".csv", ".txt", ".sql", ".jsonl")

    def files(self):
        return [p for p in DISC.rglob("*") if p.is_file() and "__pycache__" not in p.parts]

    def test_no_database_route_in_code(self):
        for p in self.files():
            if p.suffix in (".py",):
                m = self.FORBIDDEN.search(p.read_text())
                self.assertIsNone(m, f"{p.relative_to(REPO)} reaches a database ({m and m.group(0)})")

    def test_only_reviewable_files(self):
        for p in self.files():
            self.assertIn(p.suffix, self.ALLOWED, f"{p.relative_to(REPO)} is not reviewable text")

    def test_no_network_or_clock_in_scoring_code(self):
        for name in ("evaluate.py", "model.py", "features.py", "candidates.py", "leakage.py"):
            src = (DISC / "cfl_discovery" / name).read_text()
            for bad in ("urllib", "requests", "socket", "datetime.now", "time.time"):
                self.assertNotIn(bad, src, f"{name} uses {bad}")


# ----------------------------------------------------------------------------- model + statistics
class ModelAndStatistics(unittest.TestCase):
    def test_scaler_is_odd_so_corner_symmetry_survives_scaling(self):
        rng = np.random.default_rng(0)
        X = rng.standard_normal((500, 3)) + 0.4      # deliberately not centred
        X[::7, 1] = np.nan
        sc = M.Scaler().fit(X)
        np.testing.assert_allclose(sc.transform(-X), -sc.transform(X))

    def test_fitted_model_passes_pred001_symmetry_check(self):
        rng = np.random.default_rng(1)
        n = 3000
        x = rng.standard_normal(n)
        q = 1 / (1 + np.exp(-rng.standard_normal(n)))
        y = (rng.random(n) < 1 / (1 + np.exp(-(M.logit(q) + 0.3 * x)))).astype(float)
        sc = M.Scaler().fit(x[:, None])
        th = M.fit_offset_logistic(sc.transform(x[:, None]), M.logit(q), y, ridge=1.0)
        self.assertGreater(th[1], 0.1)
        rows = [{"x": float(x[i]), "q": float(q[i])} for i in range(200)]
        pred = lambda r: float(M.predict_offset_logistic(th, sc.transform(np.array([[r["x"]]])),
                                                         np.array([M.logit(r["q"])]))[0])
        swap = lambda r: {"x": -r["x"], "q": 1 - r["q"]}
        self.assertEqual(pp.symmetry_violations(pred, rows, swap), [])

    def test_no_information_means_the_market(self):
        rng = np.random.default_rng(2)
        q = rng.uniform(0.2, 0.8, 4000)
        y = (rng.random(4000) < q).astype(float)
        th = M.fit_offset_logistic(np.zeros((4000, 0)), M.logit(q), y, ridge=1.0)
        self.assertLess(abs(th[0]), 0.1)

    def test_bh_and_holm(self):
        p = np.array([0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216])
        self.assertEqual(E.benjamini_hochberg(p, 0.05).sum(), 2)
        self.assertEqual(E.holm(p, 0.05).sum(), 1)
        adj = E.bh_adjusted(p)
        self.assertTrue(np.all(np.diff(adj[np.argsort(p)]) >= -1e-12))

    def test_cluster_se_matches_a_hand_computation(self):
        d = np.array([1.0, 2.0, 3.0, 5.0])
        cl = np.array(["a", "a", "b", "b"])
        m, se = E.cluster_z(d, cl)
        s = np.array([(1 - m) + (2 - m), (3 - m) + (5 - m)])
        self.assertAlmostEqual(se, np.sqrt(np.sum(s ** 2) * 2 / 1) / 4)

    def test_a_run_cannot_loosen_a_pred001_threshold(self):
        for k, v in (("leak_delta", 0.05), ("minimum_useful_effect", 0.001), ("leak_accuracy_lift", 0.2)):
            with self.assertRaises(ValueError):
                RUN.load_config(overrides={k: v})

    def test_a_run_cannot_test_on_a_sealed_year(self):
        with self.assertRaises(ValueError):
            RUN.load_config(overrides={"confirm_years": [2023, 2024, 2025]})


# ----------------------------------------------------------------------------- leakage detectors
class LeakageDetectors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dev = SY.make(n_fighters=200, events_per_year=6, fights_per_event=6, years=(2015, 2018), seed=3)
        f, s, x = D.prepare(cls.dev)
        cls.table, cls.specs = F.build(f, s, x)

    def test_clean_features_pass_both_audits(self):
        b = lambda f, s, x: F.build(f, s, x)
        self.assertTrue(L.pit_audit(self.dev, self.table, self.specs, b, 3, seed=1)["passed"])
        self.assertTrue(L.swap_audit(self.dev, self.table, self.specs, b)["passed"])
        self.assertEqual(L.manifest_check(self.specs), [])
        self.assertEqual(L.corner_readers(self.table, self.specs), [])

    def test_pit_audit_catches_a_feature_built_from_the_fights_own_result(self):
        def leaky(f, s, x):
            T, specs = F.build(f, s, x)
            own = f.set_index("fight_id")
            T["leak_own_strikes"] = (own.a_sig_landed - own.b_sig_landed).reindex(T.fight_id).to_numpy()
            specs = specs + [F.FeatureSpec("leak_own_strikes", "anti", "style", ["fights.a_sig_str_landed"],
                                           F.HIST, False, "test leak")]
            return T, specs
        T, specs = leaky(*D.prepare(self.dev))
        res = L.pit_audit(self.dev, T, specs, leaky, 3, seed=1)
        self.assertFalse(res["passed"])
        self.assertEqual(res["failed_features"], ["leak_own_strikes"])

    def test_swap_audit_and_corner_reader_catch_the_corner_label(self):
        def corner(f, s, x):
            T, specs = F.build(f, s, x)
            T["corner_label"] = 1.0
            return T, specs + [F.FeatureSpec("corner_label", "anti", "history", [], F.BOOK, False, "A corner")]
        T, specs = corner(*D.prepare(self.dev))
        self.assertIn("corner_label", L.swap_audit(self.dev, T, specs, corner)["failed_features"])
        self.assertTrue(any(r.startswith("corner_label") for r in L.corner_readers(T, specs)))

    def test_manifest_check_catches_forbidden_sources(self):
        bad = [F.FeatureSpec("d_career_slpm", "anti", "style", ["fighters.slpm"], F.HIST, True, ""),
               F.FeatureSpec("d_result", "anti", "history", ["fights.winner_id"], F.BOOK, False, ""),
               F.FeatureSpec("d_reach_unflagged", "anti", "physical", ["fighters.reach_in"], F.HIST, False, "")]
        probs = L.manifest_check(bad)
        for name in ("d_career_slpm", "d_result", "d_reach_unflagged"):
            self.assertTrue(any(p.startswith(name) for p in probs), (name, probs))


# ----------------------------------------------------------------------------- end to end, synthetic
class EndToEndSynthetic(unittest.TestCase):
    """Clearly labelled synthetic worlds where the truth is known."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        cls.planted = _run_synthetic(cls.tmp / "planted", 0.22)
        cls.null = _run_synthetic(cls.tmp / "null", 0.0)
        cls.strong = _run_synthetic(cls.tmp / "strong", 0.45)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_finds_the_planted_effect(self):
        R = self.planted["results"]
        self.assertIn("S:d_reach_in", R["shortlist"])
        self.assertIn(R["candidates"]["S:d_reach_in"]["tier"], ("RESEARCH_LEAD", "BELOW_USEFUL_EFFECT"))

    def test_finds_nothing_in_a_null_world(self):
        R = self.null["results"]
        self.assertEqual(R["tier_counts"]["RESEARCH_LEAD"], 0)
        self.assertNotIn("S:d_reach_in", R["shortlist"])

    def test_too_good_is_quarantined_not_promoted(self):
        c = self.strong["results"]["candidates"]["S:d_reach_in"]
        self.assertEqual(c["tier"], "LEAK_SUSPECT")
        self.assertNotIn("S:d_reach_in", self.strong["results"]["shortlist"])

    def test_noise_controls_are_never_in_the_family_or_the_shortlist(self):
        for r in (self.planted, self.null):
            R = r["results"]
            for cid, c in R["candidates"].items():
                if c["kind"] == "control":
                    self.assertFalse(c["family_member"])
                    self.assertNotIn(cid, R["shortlist"])

    def test_every_candidate_tested_is_recorded_with_both_stages(self):
        R = self.planted["results"]
        cat = json.loads((self.planted["out"] / "catalog.json").read_text())
        self.assertEqual({c["cid"] for c in cat}, set(R["candidates"]))
        for c in R["candidates"].values():
            self.assertIn("screen", c)
            self.assertIn("confirm", c)
            self.assertIn("tier", c)

    def test_shortlist_is_fixed_before_confirmation(self):
        R = self.planted["results"]
        sl = json.loads((self.planted["out"] / "shortlist.json").read_text())
        self.assertEqual(sl["shortlist"], R["shortlist"])
        self.assertEqual(D.file_sha256(self.planted["out"] / "shortlist.json"), R["meta"]["shortlist_sha256"])
        for cid, c in R["candidates"].items():
            if c["tier"] in ("RESEARCH_LEAD", "BELOW_USEFUL_EFFECT", "UNSTABLE", "FAILED_CONFIRMATION"):
                self.assertIn(cid, R["shortlist"])

    def test_audits_ran_and_passed_and_the_detector_works(self):
        A = self.planted["results"]["audits"]
        self.assertTrue(A["pit"]["passed"])
        self.assertTrue(A["swap"]["passed"])
        self.assertTrue(A["detector_self_check"]["detector_works"])
        self.assertTrue(self.planted["results"]["symmetry"]["passed"])

    def test_no_betting_return_and_no_promotion_language(self):
        txt = (self.planted["out"] / "SUMMARY.md").read_text()
        self.assertIn("never a price anyone could bet", txt)
        for bad in ("ROI", "profit", "units won", "betting edge", "beats the market"):
            self.assertNotIn(bad, txt)
        R = self.planted["results"]
        for c in R["candidates"].values():
            self.assertNotIn(c["tier"], ("APPROVED", "PROMOTED", "PUBLISH"))

    def test_devig_sensitivity_was_actually_evaluated(self):
        R = self.planted["results"]
        for q in ("q_close_power", "q_close_shin"):
            self.assertTrue(R["devig_sensitivity"][q]["evaluated"], q)
        for cid in R["shortlist"]:
            got = R["candidates"][cid]["confirm"]["devig_sensitivity_delta_vs_recalibrated"]
            self.assertEqual(set(got), {"q_close_power", "q_close_shin"})

    def test_a_lead_clears_the_size_bar_against_the_reweighted_market(self):
        for r in (self.planted, self.null):
            for c in r["results"]["candidates"].values():
                if c["tier"] == "RESEARCH_LEAD":
                    self.assertGreaterEqual(c["confirm"]["delta_vs_recalibrated"], 0.003)

    def test_ledger_records_the_run(self):
        entries = LG.read(self.tmp / "planted" / "ledger.jsonl")
        self.assertEqual(len(entries), 1)
        self.assertEqual(LG.verify(entries, root=self.tmp / "planted"), [])


# ----------------------------------------------------------------------------- the committed ledger
class Ledger(unittest.TestCase):
    PATH = DISC / "ledger.jsonl"

    def test_chain_and_files_intact(self):
        entries = LG.read(self.PATH)
        self.assertEqual(LG.verify(entries, root=DISC), [])

    def test_every_committed_run_is_in_the_ledger(self):
        recorded = {e["run_id"] for e in LG.read(self.PATH)}
        runs = DISC / "runs"
        on_disk = {p.name for p in runs.iterdir() if p.is_dir()} if runs.exists() else set()
        self.assertEqual(on_disk - recorded, set(), "a run directory with no ledger entry")
        self.assertEqual(recorded - on_disk, set(), "a ledger entry whose run directory is gone")

    def test_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "l.jsonl"
            (pathlib.Path(t) / "r.json").write_text("{}")
            LG.append(p, {"run_id": "a", "files": {"r.json": D.file_sha256(pathlib.Path(t) / "r.json")}})
            LG.append(p, {"run_id": "b", "files": {}})
            self.assertEqual(LG.verify(LG.read(p), root=pathlib.Path(t)), [])
            (pathlib.Path(t) / "r.json").write_text('{"edited": true}')
            self.assertTrue(LG.verify(LG.read(p), root=pathlib.Path(t)))
            lines = p.read_text().splitlines()
            p.write_text(lines[1] + "\n")                    # drop the first run
            self.assertTrue(LG.verify(LG.read(p)))
            e = json.loads(lines[0]); e["tier_counts"] = {"RESEARCH_LEAD": 9}
            p.write_text(json.dumps(e) + "\n" + lines[1] + "\n")
            self.assertTrue(LG.verify(LG.read(p)))

    def test_ledger_only_grows_relative_to_main(self):
        base = os.environ.get("PRED_BASE_REF", "origin/main")
        rel = str(self.PATH.relative_to(REPO))
        try:
            old = subprocess.check_output(["git", "show", f"{base}:{rel}"], cwd=REPO,
                                          stderr=subprocess.DEVNULL, text=True)
        except subprocess.CalledProcessError:
            if os.environ.get("CI") and os.environ.get("PRED_BASE_REF"):
                try:
                    subprocess.check_output(["git", "cat-file", "-e", base], cwd=REPO, stderr=subprocess.DEVNULL)
                except subprocess.CalledProcessError:
                    self.fail(f"cannot read the base {base} to check the ledger")
            return  # the ledger does not exist on the base yet
        now = self.PATH.read_text().splitlines()
        old = old.splitlines()
        self.assertEqual(now[: len(old)], old, "a ledger entry present on main was changed or removed")


if __name__ == "__main__":
    unittest.main()
