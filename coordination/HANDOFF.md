# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-16 — coordination layer is up

**From:** Claude
**To:** ChatGPT
**Date:** 2026-09-16

### What changed

`coordination/` now exists with five files — `STATE.md`, `TASK_QUEUE.md`,
`DECISIONS.md`, `HANDOFF.md`, `CRITICAL_GATES.md` — plus
`tests/test_coordination.py` and a pointer section in `CLAUDE.md`.

The pointer is the load-bearing part. `CLAUDE.md` is the only file a fresh
Claude session is guaranteed to read, so a coordination layer it does not
mention is a coordination layer that does not run.

Three deltas from the proposal as written are recorded in
[`DECISIONS.md`](DECISIONS.md) D-001: `STATE.md` defers to
`CFL_RESEARCH_STATE.md` rather than duplicating it, "reversible" is given a
four-part definition that accounts for append-only tables and published claims,
and the coordination files are tested.

### What did not change

No frozen file, no user-facing surface, no schema, no workflow. The duration
model was not touched. `tests/test_research_state.py` passes unchanged.

### Open questions for review

1. **Is the L3 list right, or is it too wide?** Nine gates is a lot for a
   one-owner project, and every gate is a place the loop stalls waiting on
   Reed. The candidate to cut is gate 2 (lifecycle moves): T-001's procedure is
   fully prescribed in the register, so the owner decision may be ceremonial.
   The argument for keeping it is that `armed → collecting` is the exact
   transition the `armed` state was invented to make honest.

2. **T-002 is the real bottleneck.** Nine clauses are held pending individual
   votes, and DUR-001's specification is unsettled until they land. The three
   governance-only clauses — (f) (j) (k) — could be voted separately from the
   six that touch eligibility, scoring or interpretation. Worth proposing that
   split to Reed as one batch rather than nine asks?

3. **Does T-003 need its own preregistration?** CLV is a public claim surface.
   If CFL is going to publish a CLV figure, the measurement rule should be
   frozen before the first observation, the same way DUR-001 and DUR-002 are —
   otherwise the first number published is the first number that looked good.
   My read is yes, but the specification is yours to write.

### Next action

**ChatGPT writes the specification for T-003 — market / closing-price capture
and CLV measurement.** It is the stated top priority in the research register.
Before any code: what is captured, at what time relative to the bell, from
which books, how the vig is removed, what "closing" means when books disagree,
and whether the whole thing is preregistered. Answer question 3 above as part
of it.

If T-003 is not the right call, the fallback is T-004 — one hop off the
`picks.html` redirect chain — which Claude can take unsupervised at L1.
