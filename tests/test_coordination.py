"""Tripwire: the coordination layer must still be internally consistent.

    python -m unittest tests/test_coordination.py -v

`coordination/` is how Claude and ChatGPT hand work back and forth without the owner
in the middle. It is plain markdown, which means nothing stops it rotting — a
task marked done with no decision behind it, a handoff with no next action, a
decision pointing at a task id that no longer exists. Each of those reads fine
and quietly breaks the loop.

The load-bearing check is `test_a_done_L3_task_has_a_recorded_decision`. L3 is
the set of things only the owner decides. If an L3 row can reach `done` with nothing
in DECISIONS.md against its id, the gate is decorative.

This file checks structure and cross-references only. It cannot check whether a
decision was the owner's — that is what quoting them in the entry is for.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
COORD = REPO / "coordination"

STATE = COORD / "STATE.md"
QUEUE = COORD / "TASK_QUEUE.md"
DECISIONS = COORD / "DECISIONS.md"
HANDOFF = COORD / "HANDOFF.md"
GATES = COORD / "CRITICAL_GATES.md"

REQUIRED_FILES = [STATE, QUEUE, DECISIONS, HANDOFF, GATES]

LEVELS = {"L0", "L1", "L2", "L3"}
# The OWNER role, not a person: live coordination text names the role so a
# change of who holds it is not a repo-wide rename. Historical entries in
# DECISIONS.md and older handoffs keep the name they were written with -
# rewriting those would falsify who actually decided what.
OWNERS = {"Claude", "ChatGPT", "Owner"}
STATUSES = {"proposed", "queued", "in-progress", "blocked", "done", "dropped"}

# | T-001 | some task | L3 | Owner | blocked |
TASK_ROW = re.compile(
    r"^\|\s*(T-\d{3})\s*\|\s*(.+?)\s*\|\s*(L[0-3])\s*\|\s*(\w+)\s*\|\s*([a-z-]+)\s*\|\s*$"
)
# ## D-001 — Title
DECISION_HEAD = re.compile(r"^##\s+(D-\d{3})\s+\S+\s+(.+?)\s*$")
# | field | value |
FIELD_ROW = re.compile(r"^\|\s*([a-z ]+?)\s*\|\s*(.+?)\s*\|\s*$")

ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def tasks() -> dict[str, dict[str, str]]:
    """{id: {task, level, owner, status}} from TASK_QUEUE.md."""
    out: dict[str, dict[str, str]] = {}
    for line in read(QUEUE).splitlines():
        m = TASK_ROW.match(line)
        if m:
            out[m.group(1)] = {
                "task": m.group(2),
                "level": m.group(3),
                "owner": m.group(4),
                "status": m.group(5),
            }
    return out


def decisions() -> dict[str, dict[str, str]]:
    """{id: {title, ...fields}} from DECISIONS.md, fields from each entry's table."""
    out: dict[str, dict[str, str]] = {}
    current: str | None = None
    for line in read(DECISIONS).splitlines():
        head = DECISION_HEAD.match(line)
        if head:
            current = head.group(1)
            out[current] = {"title": head.group(2)}
            continue
        if current is None:
            continue
        field = FIELD_ROW.match(line)
        if field and field.group(1) not in ("field", "---"):
            out[current].setdefault(field.group(1), field.group(2))
    return out


class TestFilesExist(unittest.TestCase):
    def test_all_five_coordination_files_exist(self):
        for path in REQUIRED_FILES:
            with self.subTest(file=path.name):
                self.assertTrue(path.is_file(), f"missing {path.relative_to(REPO)}")

    def test_state_indexes_every_sibling(self):
        """STATE.md is the entry point. A file it does not name is a file nobody
        opens — and a renamed file it still names is a dead link."""
        body = read(STATE)
        for path in REQUIRED_FILES:
            with self.subTest(file=path.name):
                self.assertIn(
                    path.name, body,
                    f"{path.name} exists but STATE.md does not link to it",
                )

    def test_state_records_a_parseable_date(self):
        m = re.search(r"^Last updated:\s*(\d{4}-\d{2}-\d{2})\s*$", read(STATE), re.M)
        self.assertIsNotNone(
            m, "STATE.md needs a line of the form 'Last updated: YYYY-MM-DD'"
        )
        dt.date.fromisoformat(m.group(1))


class TestTaskQueue(unittest.TestCase):
    def test_queue_parses_to_some_rows(self):
        self.assertGreater(
            len(tasks()), 0,
            "TASK_QUEUE.md parsed to zero rows — the table format probably "
            "changed and this tripwire is now blind",
        )

    def test_every_row_is_well_formed(self):
        for tid, row in sorted(tasks().items()):
            with self.subTest(task=tid):
                self.assertIn(row["level"], LEVELS)
                self.assertIn(row["owner"], OWNERS, f"unknown owner {row['owner']!r}")
                self.assertIn(row["status"], STATUSES, f"unknown status {row['status']!r}")
                self.assertTrue(row["task"].strip(), "empty task description")

    def test_task_ids_are_unique(self):
        """A reused id silently rewrites history in DECISIONS.md."""
        seen = [m.group(1) for line in read(QUEUE).splitlines()
                if (m := TASK_ROW.match(line))]
        dupes = {t for t in seen if seen.count(t) > 1}
        self.assertFalse(dupes, f"duplicate task ids: {sorted(dupes)}")

    def test_only_reed_owns_an_L3(self):
        """L3 means the owner decides. An L3 row owned by an AI is the gate
        already being walked around."""
        for tid, row in sorted(tasks().items()):
            if row["level"] != "L3":
                continue
            with self.subTest(task=tid):
                self.assertEqual(
                    row["owner"], "Owner",
                    f"{tid} is L3 but owned by {row['owner']}. L3 is the owner's by "
                    f"definition — see coordination/CRITICAL_GATES.md.",
                )

    def test_a_done_L3_task_has_a_recorded_decision(self):
        """The one that matters. Closing an L3 without a decision behind it makes
        the whole gate list decorative."""
        recorded = read(DECISIONS)
        for tid, row in sorted(tasks().items()):
            if row["level"] != "L3" or row["status"] != "done":
                continue
            with self.subTest(task=tid):
                self.assertIn(
                    tid, recorded,
                    f"\n\n{tid} is an L3 task marked done, but no entry in "
                    f"coordination/DECISIONS.md references it.\n"
                    f"An L3 is the owner's decision. Record it — with the date, the "
                    f"decider, and what he actually said — or move the task back "
                    f"off done.\n",
                )


class TestDecisions(unittest.TestCase):
    def test_decisions_parse(self):
        self.assertGreater(
            len(decisions()), 0,
            "DECISIONS.md parsed to zero entries — heading format probably changed",
        )

    def test_every_decision_has_date_decider_task_and_level(self):
        for did, entry in sorted(decisions().items()):
            for field in ("date", "decided by", "task", "level"):
                with self.subTest(decision=did, field=field):
                    self.assertIn(field, entry, f"{did} records no {field!r}")
                    self.assertTrue(entry[field].strip())

    def test_decision_dates_are_iso(self):
        for did, entry in sorted(decisions().items()):
            with self.subTest(decision=did):
                dt.date.fromisoformat(entry["date"])

    def test_decision_levels_are_known(self):
        for did, entry in sorted(decisions().items()):
            with self.subTest(decision=did):
                self.assertIn(entry["level"], LEVELS)

    def test_every_decision_points_at_a_real_task(self):
        """A decision whose task id does not exist is either a typo or a task
        someone deleted instead of marking dropped."""
        known = set(tasks())
        for did, entry in sorted(decisions().items()):
            ref = entry.get("task", "")
            if ref in ("none", "n/a", "—"):
                continue
            for tid in re.findall(r"T-\d{3}", ref):
                with self.subTest(decision=did, task=tid):
                    self.assertIn(
                        tid, known,
                        f"{did} settles {tid}, which is not in TASK_QUEUE.md. "
                        f"A task that dies is marked dropped, not deleted.",
                    )

    def test_decision_ids_are_unique_and_ascending(self):
        ids = [m.group(1) for line in read(DECISIONS).splitlines()
               if (m := DECISION_HEAD.match(line))]
        self.assertEqual(len(ids), len(set(ids)), f"duplicate decision ids in {ids}")
        self.assertEqual(
            ids, sorted(ids),
            "DECISIONS.md is append-only, newest at the bottom — ids must ascend",
        )


class TestHandoff(unittest.TestCase):
    def test_handoff_names_from_to_and_date(self):
        body = read(HANDOFF)
        for field in ("**From:**", "**To:**", "**Date:**"):
            with self.subTest(field=field):
                self.assertIn(field, body, f"the top handoff entry needs a {field} line")

    def test_handoff_date_is_iso(self):
        m = re.search(r"\*\*Date:\*\*\s*(\S+)", read(HANDOFF))
        self.assertIsNotNone(m, "no **Date:** line in HANDOFF.md")
        dt.date.fromisoformat(m.group(1))

    def test_handoff_has_a_populated_next_action(self):
        """A handoff without a next action is a status update, and the receiving
        side has to ask a question before it can start."""
        body = read(HANDOFF)
        self.assertIn("## Next action", body)
        tail = body.split("## Next action", 1)[1].strip()
        self.assertGreater(
            len(tail), 40,
            "the '## Next action' section is empty or near-empty. Name something "
            "specific enough to start on without asking a question back.",
        )


class TestGates(unittest.TestCase):
    def test_all_four_levels_are_defined(self):
        body = read(GATES)
        for level in sorted(LEVELS):
            with self.subTest(level=level):
                self.assertIn(
                    f"**{level}**", body,
                    f"{level} is used in the queue but not defined in CRITICAL_GATES.md",
                )

    def test_reversible_is_defined_against_append_only_tables(self):
        """The default rule leans on the word 'reversible'. If the definition ever
        loses the append-only clause, 'proceed without asking' starts covering
        rows that cannot be taken back."""
        body = read(GATES)
        for token in ("prop_model_locks", "pre_fight_snapshots"):
            with self.subTest(token=token):
                self.assertIn(
                    token, body,
                    "the definition of 'reversible' must still name the "
                    "append-only tables it is protecting",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
