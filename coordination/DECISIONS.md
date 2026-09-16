# Decisions

Append-only. Newest at the bottom. A decision is written here when it is made,
not when it is convenient — an undocumented decision gets relitigated.

Ids are `D-NNN`. Every entry names a date, a decider, and the task it settles.
An `L3` decision quotes what Reed actually said; an AI may not record his
approval from inference or silence.

Entries are not edited after the fact. A decision that turns out to be wrong
gets a **new** entry that supersedes it, and the old one stays.

---

## D-001 — Adopt the `coordination/` layer

| field | value |
|---|---|
| date | 2026-09-16 |
| decided by | Reed Cannon |
| task | T-005 |
| level | L1 |
| reversible | yes — documentation only, revertible in git, writes no row, publishes nothing |

**Decision.** The repo becomes the communication layer between Claude and
ChatGPT. Claude builds and writes a handoff; ChatGPT reviews and writes the
next specification; Reed appears only at an L3 gate. Five files under
`coordination/` carry it, and `CLAUDE.md` points at them so a fresh session
finds them.

**Origin.** Proposed by ChatGPT; handed to Claude by Reed on 2026-09-16 with
the instruction to build it.

**Deltas from the proposal as written.** Three, all in the direction of the
governance already in this repo:

1. **`STATE.md` does not own research truth.** The proposal had a single
   `STATE.md`. This repo already has `CFL_RESEARCH_STATE.md`, which is mirrored
   in `research/registry.json` and checked against disk by
   `tests/test_research_state.py`. A second state file with overlapping scope
   would drift, and the drifting copy would be the unchecked one.
   `coordination/STATE.md` summarises and links; the register wins on conflict.

2. **"Reversible" is defined.** The proposal's default — *if reversible,
   testable and within spec, proceed* — is load-bearing, and the obvious
   reading of "reversible" is wrong here. `prop_model_locks` and
   `pre_fight_snapshots` reject UPDATE and DELETE by trigger for every role.
   A published claim is not unpublished by a retraction. The four-part test is
   in `CRITICAL_GATES.md`.

3. **The coordination files are tested.** Every other governance artifact in
   this repo has a tripwire; a handoff protocol that nothing checks rots in a
   fortnight. `tests/test_coordination.py` checks the structure and, in
   particular, that no `L3` task is marked done without a decision recorded
   here against its id.

**What was kept unchanged.** The L0–L3 ladder, the nine L3 gates, the two-AI
loop, and the standing prohibition on modifying a frozen statistical
specification because a new result looks better.
