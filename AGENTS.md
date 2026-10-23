# AGENTS.md

Instructions for the AI agents working in this repository: **ChatGPT** (spec
and review) and **Claude Code** (build). The CFL Owner appears only at an L3
gate.

## Read in this order, every session

1. [`MISSION.md`](MISSION.md): the north star. *Find a real edge. Prove it
   exists. Make it actionable. Build a business around what we learn.*
2. [`coordination/STATE.md`](coordination/STATE.md): where the project
   actually is.
3. [`coordination/HANDOFF.md`](coordination/HANDOFF.md): the top entry names
   the next action.
4. [`coordination/TASK_QUEUE.md`](coordination/TASK_QUEUE.md): when choosing
   what to do next.
5. [`coordination/CRITICAL_GATES.md`](coordination/CRITICAL_GATES.md) before
   anything that might need the owner, and
   [`coordination/DECISIONS.md`](coordination/DECISIONS.md) when something
   feels already settled. It probably is.

Claude Code also follows [`CLAUDE.md`](CLAUDE.md), which holds the full build
rules. Every user-facing string follows [`COPY_STYLE.md`](COPY_STYLE.md).

## Rules for both agents

- **Name the mission step.** Every task, spec and handoff says which of the
  four steps in `MISSION.md` it serves. Work that serves none is flagged as a
  detour, not done quietly.
- **The mission never opens a gate.** `CRITICAL_GATES.md` decides who may do
  what. Never skip a gate, change a frozen specification, widen a test window
  or publish a number because it "serves the mission".
- **Proof before product.** No public page shows a CFL win probability, a
  pick, a confidence tier, a predicted winner, an edge percentage or a
  CFL-vs-market difference ([D-011](coordination/DECISIONS.md)). An edge
  returns to the product only on prospective evidence, published before the
  number is.
- **Plain English first.** State each task in plain English (what changes,
  why it matters, what the user sees differently) before any code or spec.
- **Decisions are append-only.** A wrong decision gets a new entry that
  supersedes it. An L3 approval quotes what the owner actually said; it is
  never inferred from silence or a general "go ahead".
- **Ids are never reused.** Before taking the next `T-` or `D-` id, check open
  pull requests as well as `main`: an open PR may already have claimed it.
- **Name the role, not the person.** New records say "CFL Owner", never a
  personal name ([D-033](coordination/DECISIONS.md), E2).
- **Finishing means handing off.** Update `coordination/STATE.md` and
  `coordination/HANDOFF.md` in the same commit as the work.
  `tests/test_coordination.py` and `tests/test_mission.py` check the structure.

## Roles

| agent | does | does not |
|---|---|---|
| ChatGPT | writes specifications, reviews Claude's work, proposes tasks and gates | record an owner decision, add or remove an L3 gate |
| Claude Code | builds, tests, opens pull requests, writes the handoff | record an owner decision from inference, add or remove an L3 gate |
| CFL Owner | decides every L3 item | — |
