"""Tripwire: the mission must still be the first thing every agent reads.

    python -m unittest tests/test_mission.py -v

`MISSION.md` is the north star (D-035). It only keeps work on track if the
files each agent opens first still point at it: `CLAUDE.md` for Claude Code,
`AGENTS.md` for both agents. A mission that nothing links to reads fine and is
never opened.

This checks presence and references only. It cannot check whether a piece of
work actually served the mission; that is what naming the step in the handoff
is for.
"""
from __future__ import annotations

import pathlib
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent

MISSION = REPO / "MISSION.md"
AGENTS = REPO / "AGENTS.md"
CLAUDE = REPO / "CLAUDE.md"

NORTH_STAR = (
    "Find a real edge. Prove it exists. Make it actionable. "
    "Build a business around what we learn."
)

# CLAUDE.md is long. "Near its beginning" means a fresh session meets the
# mission before any of the build rules.
CLAUDE_HEAD_LINES = 25


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


class TestMission(unittest.TestCase):
    def test_mission_exists_at_the_root(self):
        self.assertTrue(MISSION.is_file(), "MISSION.md is missing from the repo root")

    def test_mission_carries_the_north_star(self):
        self.assertIn(
            NORTH_STAR, read(MISSION),
            "MISSION.md no longer carries the owner's north star line word for word",
        )

    def test_mission_says_it_opens_no_gate(self):
        """The mission must never read as permission to walk around a gate."""
        self.assertIn("CRITICAL_GATES.md", read(MISSION))

    def test_agents_md_exists_and_references_the_mission(self):
        self.assertTrue(AGENTS.is_file(), "AGENTS.md is missing from the repo root")
        self.assertIn("MISSION.md", read(AGENTS))

    def test_claude_md_references_the_mission_near_the_top(self):
        head = "\n".join(read(CLAUDE).splitlines()[:CLAUDE_HEAD_LINES])
        self.assertIn(
            "MISSION.md", head,
            f"CLAUDE.md must reference MISSION.md in its first {CLAUDE_HEAD_LINES} lines",
        )

    def test_mission_is_read_before_state(self):
        """Both entry points must send an agent to the mission before STATE.md,
        or the two instructions contradict each other."""
        for path in (CLAUDE, AGENTS):
            body = read(path)
            with self.subTest(file=path.name):
                self.assertIn("coordination/STATE.md", body)
                self.assertLess(
                    body.index("MISSION.md"), body.index("coordination/STATE.md"),
                    f"{path.name} names STATE.md before MISSION.md",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
