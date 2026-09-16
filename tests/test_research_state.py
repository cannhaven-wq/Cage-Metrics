"""Tripwire: the frozen research files must still be the bytes we froze.

    python -m unittest tests/test_research_state.py -v

DUR-001 rests on a claim that is easy to state and easy to break by accident:
the model, the feature code, the lock script, the migration and the
preregistration have not changed since the experiment was frozen. A one-line
edit to build_features.py invalidates every lock already on the ledger, and
nothing else in the repo would notice.

So this test recomputes the sha256 of each frozen file and compares it against
the hash recorded in BOTH registries:

  * CFL_RESEARCH_STATE.md   - the human-readable table
  * research/registry.json  - the machine-readable mirror

A failure means one of two things, and the test tells you which:

  * the FILE changed   -> you edited something frozen. Do not update the hash.
    Bump the model version and write a new preregistration.
  * the REGISTRY changed -> the two registries disagree with each other.

Design note: the hashes here are not "whatever is on disk today". They were
pinned to each file's freeze commit and verified byte-identical at the time the
registry was written. A test that regenerates its own expected value from the
thing it is testing passes by construction and proves nothing.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
STATE_MD = REPO / "CFL_RESEARCH_STATE.md"
REGISTRY = REPO / "research" / "registry.json"

# A sha256 is 64 lowercase hex chars; a row in the frozen-files table looks like
#   | `path/to/file` | `<64 hex>` | `<commit>` |
# The third cell may carry an amendment note after the commit, e.g.
#   | `...PREREGISTRATION.md` | `<64 hex>` | `1bc3fdd`, **amended 2026-09-16** |
# so it is matched loosely after the commit hash. The first two cells are not:
# a row whose path or sha256 is malformed must fail to parse rather than be
# skipped, or the tripwire goes blind exactly where it matters.
FROZEN_ROW = re.compile(
    r"^\|\s*`([^`]+)`\s*\|\s*`([0-9a-f]{64})`\s*\|\s*`([0-9a-f]{7,40})`[^|]*\|\s*$"
)


def sha256_of(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_from_markdown() -> dict[str, str]:
    """{path: sha256} from the 'Frozen files' table in CFL_RESEARCH_STATE.md."""
    rows: dict[str, str] = {}
    in_section = False
    for line in STATE_MD.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("## Frozen files"):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section:
            m = FROZEN_ROW.match(line)
            if m:
                rows[m.group(1)] = m.group(2)
    return rows


def frozen_from_registry() -> dict[str, dict[str, str]]:
    """{experiment_id: {path: sha256}} from research/registry.json."""
    doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
    out: dict[str, dict[str, str]] = {}
    for exp in doc["experiments"]:
        out[exp["experiment_id"]] = {
            f["path"]: f["sha256"] for f in exp.get("frozen_files") or []
        }
    return out


class TestRegistriesExist(unittest.TestCase):
    def test_state_markdown_exists(self):
        self.assertTrue(STATE_MD.is_file(), f"missing {STATE_MD}")

    def test_registry_json_exists(self):
        self.assertTrue(REGISTRY.is_file(), f"missing {REGISTRY}")

    def test_registry_json_parses(self):
        doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
        self.assertIn("experiments", doc)
        self.assertGreater(len(doc["experiments"]), 0)

    def test_markdown_lists_some_frozen_files(self):
        self.assertGreater(
            len(frozen_from_markdown()), 0,
            "the 'Frozen files' table in CFL_RESEARCH_STATE.md parsed to zero rows - "
            "the table format probably changed and this tripwire is now blind",
        )


class TestFrozenFilesUnchanged(unittest.TestCase):
    """The load-bearing check: recorded hash == hash of the bytes on disk."""

    def test_markdown_hashes_match_disk(self):
        for rel, recorded in sorted(frozen_from_markdown().items()):
            with self.subTest(file=rel):
                path = REPO / rel
                self.assertTrue(path.is_file(), f"frozen file is missing: {rel}")
                actual = sha256_of(path)
                self.assertEqual(
                    recorded, actual,
                    f"\n\nFROZEN FILE CHANGED: {rel}\n"
                    f"  recorded in CFL_RESEARCH_STATE.md: {recorded}\n"
                    f"  actually on disk:                  {actual}\n\n"
                    f"Do NOT just update the hash to make this pass. There are "
                    f"exactly two legitimate routes:\n"
                    f"  1. a dated amendment (preregistration only) - record it in "
                    f"its own '## Amendments' section, in the amendment log in "
                    f"CFL_RESEARCH_STATE.md, and in registry.json's "
                    f"preregistration_amendments, all in the same commit;\n"
                    f"  2. a new model_version with its own preregistration.\n"
                    f"Anything else is a silent edit, which is what this test exists "
                    f"to catch.\n",
                )

    def test_registry_hashes_match_disk(self):
        for exp_id, files in sorted(frozen_from_registry().items()):
            for rel, recorded in sorted(files.items()):
                with self.subTest(experiment=exp_id, file=rel):
                    path = REPO / rel
                    self.assertTrue(path.is_file(), f"frozen file is missing: {rel}")
                    actual = sha256_of(path)
                    self.assertEqual(
                        recorded, actual,
                        f"\n\nFROZEN FILE CHANGED: {rel} (experiment {exp_id})\n"
                        f"  recorded in research/registry.json: {recorded}\n"
                        f"  actually on disk:                   {actual}\n\n"
                        f"Do NOT update the hash to make this pass.\n",
                    )


class TestRegistriesAgree(unittest.TestCase):
    """The two registries are written by hand and by script. They must not drift."""

    def test_every_registry_frozen_file_is_in_the_markdown_table(self):
        """Checked as a subset, not an equality.

        Experiments do not all freeze the same set — DUR-001 and PROP-0001 freeze
        the DUR-001 preregistration, DUR-002 freezes its own — so the markdown
        table is the UNION across experiments. What must hold is that every file
        an experiment freezes appears there with the same hash.

        A DRAFT experiment legitimately declares none; it is skipped here and
        caught by `test_only_a_draft_may_declare_no_frozen_files`.
        """
        md = frozen_from_markdown()
        for exp_id, files in sorted(frozen_from_registry().items()):
            if not files:
                continue
            for rel in sorted(files):
                with self.subTest(experiment=exp_id, file=rel):
                    self.assertIn(
                        rel, md,
                        f"{exp_id} freezes {rel} but it is missing from the "
                        f"'Frozen files' table in CFL_RESEARCH_STATE.md",
                    )
                    self.assertEqual(
                        md[rel], files[rel],
                        f"hash disagreement for {rel} between the two registries",
                    )

    def test_the_markdown_table_has_no_orphan_rows(self):
        """The other direction: a row nobody freezes is stale, and a stale row is
        how a file quietly stops being anyone's responsibility."""
        claimed = set()
        for files in frozen_from_registry().values():
            claimed |= set(files)
        for rel in sorted(frozen_from_markdown()):
            with self.subTest(file=rel):
                self.assertIn(
                    rel, claimed,
                    f"{rel} is listed in CFL_RESEARCH_STATE.md but no experiment in "
                    f"registry.json freezes it",
                )

    def test_only_a_draft_may_declare_no_frozen_files(self):
        """An experiment in force with no frozen files would be outside the tripwire."""
        doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
        for exp in doc["experiments"]:
            if exp.get("frozen_files"):
                continue
            with self.subTest(experiment=exp.get("experiment_id")):
                self.assertEqual(
                    exp.get("status"), "draft",
                    f"{exp.get('experiment_id')} declares no frozen files but is not "
                    f"a draft. Only a draft may sit outside the frozen-file tripwire.",
                )

    def test_a_draft_experiment_has_no_freeze_timestamp(self):
        """Draft means not frozen. A freeze timestamp on a draft is a contradiction
        that would let an unsigned preregistration look binding."""
        doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
        for exp in doc["experiments"]:
            if exp.get("status") != "draft":
                continue
            with self.subTest(experiment=exp.get("experiment_id")):
                self.assertIsNone(
                    exp.get("freeze_timestamp"),
                    "a draft experiment must not carry a freeze_timestamp",
                )
                self.assertIsNone(
                    exp.get("verdict"),
                    "a draft experiment cannot have a verdict",
                )


class TestRegistrySchema(unittest.TestCase):
    """Every field the registry promises is present. null is allowed; missing is not.

    The point of the distinction: null says "we looked and there is no value".
    A missing key says nothing at all, and is how a registry quietly rots.
    """

    REQUIRED = [
        "experiment_id", "status", "hypothesis", "economic_rationale",
        "population", "market", "challenger_model", "market_benchmark",
        "prediction_time_rule", "primary_endpoint", "minimum_useful_effect",
        "observation_unit", "cluster_unit", "eligibility_rules",
        "preregistration_path", "preregistration_sha256",
        "model_artifact_sha256", "data_artifact_sha256", "freeze_timestamp",
        "formal_analysis_points", "kill_rule", "allowed_sensitivities",
        "forbidden_changes", "results_artifact", "verdict", "verdict_timestamp",
        "frozen_files",
    ]

    def test_all_fields_present(self):
        doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
        for exp in doc["experiments"]:
            for field in self.REQUIRED:
                with self.subTest(experiment=exp.get("experiment_id"), field=field):
                    self.assertIn(field, exp)

    def test_preregistration_sha_matches_its_path(self):
        """If an experiment names a preregistration, its hash must be that file's."""
        doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
        for exp in doc["experiments"]:
            path, recorded = exp.get("preregistration_path"), exp.get("preregistration_sha256")
            with self.subTest(experiment=exp.get("experiment_id")):
                if path is None:
                    self.assertIsNone(
                        recorded,
                        "preregistration_sha256 is set but preregistration_path is null",
                    )
                    continue
                f = REPO / path
                self.assertTrue(f.is_file(), f"preregistration missing: {path}")
                self.assertEqual(recorded, sha256_of(f))

    def test_frozen_files_entries_well_formed(self):
        doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
        for exp in doc["experiments"]:
            for entry in exp.get("frozen_files") or []:
                with self.subTest(experiment=exp.get("experiment_id"), path=entry.get("path")):
                    self.assertIn("path", entry)
                    self.assertIn("sha256", entry)
                    self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")

    def test_verdict_is_a_known_value(self):
        allowed = {
            None, "PROMOTE", "HOLD", "HOLD-PASSIVE",
            "REJECT FOR PRACTICAL VALUE", "NO VERDICT - DATA FAILURE",
        }
        doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
        for exp in doc["experiments"]:
            with self.subTest(experiment=exp.get("experiment_id")):
                self.assertIn(exp.get("verdict"), allowed)

    def test_verdict_and_timestamp_agree(self):
        """A verdict without a date, or a date without a verdict, is a half-recorded
        decision. Either both or neither."""
        doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
        for exp in doc["experiments"]:
            with self.subTest(experiment=exp.get("experiment_id")):
                self.assertEqual(
                    exp.get("verdict") is None,
                    exp.get("verdict_timestamp") is None,
                    "verdict and verdict_timestamp must be set together",
                )


class TestAmendmentsAreRecorded(unittest.TestCase):
    """A frozen file may drift from its freeze hash ONLY via a recorded amendment.

    Updating the recorded hash is the move that makes the tripwire pass, so on its
    own it would be a way to launder a silent edit. These tests require the
    paperwork to exist alongside it: an entry in `preregistration_amendments`,
    matching before/after hashes, and a non-empty `## Amendments` section in the
    preregistration itself.
    """

    def _experiments(self):
        return json.loads(REGISTRY.read_text(encoding="utf-8"))["experiments"]

    def test_drift_from_freeze_requires_an_amendment(self):
        """Checked document-wide, not per experiment.

        Experiments share one frozen-file list, but an amendment belongs to the
        experiment that OWNS the preregistration (PROP-0001 has none of its own).
        So the question is whether *some* experiment records an amendment for the
        drifted path, not whether every experiment listing it does.
        """
        exps = self._experiments()
        amended_paths = {
            exp["preregistration_path"]
            for exp in exps
            if exp.get("preregistration_amendments") and exp.get("preregistration_path")
        }
        for exp in exps:
            for f in exp.get("frozen_files") or []:
                at_freeze = f.get("sha256_at_freeze")
                if at_freeze is None or at_freeze == f["sha256"]:
                    continue                      # unchanged since freeze
                with self.subTest(experiment=exp["experiment_id"], file=f["path"]):
                    self.assertTrue(
                        f.get("amended"),
                        f"{f['path']} differs from its freeze hash but is not "
                        f"marked amended",
                    )
                    self.assertIn(
                        f["path"], amended_paths,
                        f"{f['path']} differs from its freeze hash but no "
                        f"experiment records an amendment for it. A hash change "
                        f"with no amendment behind it is a silent edit.",
                    )

    def test_a_file_marked_amended_actually_drifted(self):
        """The converse: `amended` must not be set on a file that never moved."""
        for exp in self._experiments():
            for f in exp.get("frozen_files") or []:
                if not f.get("amended"):
                    continue
                with self.subTest(experiment=exp["experiment_id"], file=f["path"]):
                    self.assertIsNotNone(
                        f.get("sha256_at_freeze"),
                        f"{f['path']} is marked amended but records no freeze hash",
                    )
                    self.assertNotEqual(
                        f["sha256_at_freeze"], f["sha256"],
                        f"{f['path']} is marked amended but its hash is unchanged",
                    )

    def test_amendment_hashes_chain_correctly(self):
        """before -> after must chain from the freeze hash to what is on disk."""
        for exp in self._experiments():
            ams = exp.get("preregistration_amendments")
            path = exp.get("preregistration_path")
            if not ams or not path:
                continue
            with self.subTest(experiment=exp["experiment_id"]):
                ams = sorted(ams, key=lambda a: a["number"])
                frozen = {f["path"]: f for f in exp["frozen_files"]}[path]
                self.assertEqual(
                    ams[0]["sha256_before"], frozen["sha256_at_freeze"],
                    "the first amendment must start from the freeze hash",
                )
                for prev, nxt in zip(ams, ams[1:]):
                    self.assertEqual(prev["sha256_after"], nxt["sha256_before"],
                                     "amendment hashes must chain")
                self.assertEqual(
                    ams[-1]["sha256_after"], sha256_of(REPO / path),
                    "the last amendment's after-hash must be the file on disk",
                )

    def test_amended_preregistration_has_a_populated_amendments_section(self):
        for exp in self._experiments():
            ams, path = exp.get("preregistration_amendments"), exp.get("preregistration_path")
            if not ams or not path:
                continue
            with self.subTest(experiment=exp["experiment_id"]):
                body = (REPO / path).read_text(encoding="utf-8")
                self.assertIn("## Amendments", body)
                tail = body.split("## Amendments", 1)[1]
                self.assertNotIn(
                    "_None._", tail,
                    "registry records an amendment but the preregistration's "
                    "Amendments section still says None",
                )
                for a in ams:
                    self.assertIn(
                        a["date"], tail,
                        f"amendment {a['number']} is in the registry but its date "
                        f"{a['date']} does not appear in the preregistration",
                    )

    def test_no_amendment_claims_to_follow_observed_results(self):
        """The preregistration forbids amendments motivated by observed results."""
        for exp in self._experiments():
            for a in exp.get("preregistration_amendments") or []:
                with self.subTest(experiment=exp["experiment_id"], amendment=a["number"]):
                    self.assertIs(
                        a.get("motivated_by_observed_results"), False,
                        "an amendment motivated by observed results is not "
                        "permitted; it must be recorded as False and be true",
                    )


class TestExperimentLifecycle(unittest.TestCase):
    """draft -> frozen -> armed -> collecting.

    The distinction that earns its keep is `armed` vs `collecting`: an experiment
    whose specification and implementation are both frozen but which has recorded
    zero observations is NOT collecting, and calling it so overstates the record.
    The transition is objective — the first row landing — so these tests check the
    status against the recorded evidence rather than trusting the label.
    """

    STATES = ("draft", "frozen", "armed", "collecting")

    def _experiments(self):
        return json.loads(REGISTRY.read_text(encoding="utf-8"))["experiments"]

    def test_lifecycle_is_declared(self):
        doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
        self.assertIn("experiment_lifecycle", doc)
        self.assertEqual(tuple(doc["experiment_lifecycle"]["states"]), self.STATES)

    def test_status_is_a_known_state(self):
        for exp in self._experiments():
            with self.subTest(experiment=exp["experiment_id"]):
                # PROP-0001 is a model artifact, not an experiment on this ladder
                if exp["experiment_id"] == "PROP-0001":
                    continue
                self.assertIn(exp["status"], self.STATES)

    def test_anything_past_draft_has_a_freeze_timestamp(self):
        for exp in self._experiments():
            if exp["status"] in ("draft",) or exp["experiment_id"] == "PROP-0001":
                continue
            with self.subTest(experiment=exp["experiment_id"]):
                self.assertIsNotNone(
                    exp.get("freeze_timestamp"),
                    f"{exp['experiment_id']} is {exp['status']} but records no "
                    f"freeze_timestamp — only a draft may be unfrozen",
                )

    def test_armed_means_zero_observations(self):
        """The whole point of the state: armed and non-empty is a contradiction."""
        for exp in self._experiments():
            if exp.get("status") != "armed":
                continue
            with self.subTest(experiment=exp["experiment_id"]):
                fc = exp.get("first_collection") or {}
                self.assertEqual(
                    fc.get("rows_written", 0), 0,
                    "an armed experiment has recorded no observations; if rows "
                    "exist it is collecting",
                )
                self.assertIsNone(
                    fc.get("first_lock_at"),
                    "an armed experiment cannot have a first-lock timestamp",
                )
                self.assertIsNone(exp.get("verdict"))

    def test_armed_requires_an_implementation(self):
        """frozen -> armed is earned by having something that can actually run."""
        for exp in self._experiments():
            if exp.get("status") != "armed":
                continue
            with self.subTest(experiment=exp["experiment_id"]):
                ls = exp.get("lock_script") or {}
                self.assertTrue(
                    ls.get("exists"),
                    "armed requires a written lock script; without one the "
                    "experiment is merely frozen",
                )
                self.assertRegex(ls.get("sha256", ""), r"^[0-9a-f]{64}$")

    def test_collecting_means_observations_are_recorded(self):
        for exp in self._experiments():
            if exp.get("status") != "collecting":
                continue
            with self.subTest(experiment=exp["experiment_id"]):
                fc = exp.get("first_collection") or {}
                self.assertIsNotNone(
                    fc.get("first_lock_at"),
                    f"{exp['experiment_id']} claims to be collecting but records no "
                    f"first-lock timestamp. Zero observations is 'armed'.",
                )
                self.assertGreater(fc.get("rows_written", 0), 0)

    def test_an_unfrozen_lock_script_means_not_yet_collecting(self):
        """A lock script freezes at first collection. One still marked unfrozen on a
        collecting experiment means the transition was recorded incompletely."""
        for exp in self._experiments():
            ls = exp.get("lock_script") or {}
            if not ls or exp.get("status") != "collecting":
                continue
            with self.subTest(experiment=exp["experiment_id"]):
                self.assertTrue(
                    ls.get("frozen"),
                    f"{exp['experiment_id']} is collecting but its lock script is "
                    f"still marked unfrozen — freeze it and move it into "
                    f"frozen_files as part of the transition",
                )


class TestWithdrawnFigures(unittest.TestCase):
    """A withdrawn number must not quietly come back.

    0.483378 / 3,793 was withdrawn by the statistics director on 2026-09-15
    pending an artifact. This test fails if it reappears anywhere in the tracked
    research surfaces other than the line that records the withdrawal.
    """

    WITHDRAWN = ["0.483378", "3,793", "3793"]
    SEARCH = [
        "CFL_RESEARCH_STATE.md",
        "research/registry.json",
        "cfl_engine/dur001/PREREGISTRATION.md",
        "cfl_engine/dur001/README.md",
    ]

    def test_withdrawn_figure_not_cited(self):
        for rel in self.SEARCH:
            path = REPO / rel
            if not path.is_file():
                continue
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "WITHDRAWN" in line.upper() or "withdrawn" in line:
                    continue          # the line that records the withdrawal
                for token in self.WITHDRAWN:
                    with self.subTest(file=rel, line=i, token=token):
                        self.assertNotIn(
                            token, line,
                            f"{rel}:{i} cites the withdrawn figure {token!r}. "
                            f"It has no artifact; it may not be republished.",
                        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
