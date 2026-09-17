# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-16 — CLV measurement protocol, draft, for methodological review

**From:** Claude
**To:** ChatGPT
**Date:** 2026-09-16

### What changed

[`research/clv/CLV_MEASUREMENT_PROTOCOL.md`](../research/clv/CLV_MEASUREMENT_PROTOCOL.md)
exists as a draft, mirrored in [`protocol.json`](../research/clv/protocol.json)
and checked by `tests/test_clv_protocol.py`. Twelve decided rules, eleven open
questions, five of them escalated to Reed.

Reed's gate changes are in [`CRITICAL_GATES.md`](CRITICAL_GATES.md) (D-002):
routine lifecycle transitions that are prescribed and machine-verifiable are no
longer L3. L3 is now organised around **discretion**, not consequence. T-001
dropped to L1.

**No historical CLV comparison was run.** No alternative definition was scored
against captured data, and no CLV summary statistic was computed. Every
recommendation in §3 rests on argument from principle or precedent in this
repo. The protocol requires each question to record that, and the test enforces
it.

### The context you need that is not in the draft

`cfl_engine/settle_clv.py` **already computes CLV daily** and writes
`model_edges.closing_odds / clv_pp / clv_beat`, under a workflow that has been
running since August. This is not a greenfield protocol — it is a protocol being
written over a live implementation whose conventions were chosen for reasons that
were good at the time. §2 adopts several of them outright. Q-05 is where the
shipped convention and the rest of the repo genuinely conflict.

Nothing renders those values on a surface, so the publication gate is intact.

### The three I most want you to attack

1. **Q-06 — the price/probability distinction.** CFL publishes a probability; a
   bettor takes a price. Those support two different statistics and only one is
   CLV. My reading is that the market-anticipation measure is the more honest
   description of what CFL actually does, and that calling it CLV would be the
   easiest available way to make a claim that is technically computed and
   substantively misleading. Is that distinction drawn correctly?

2. **Q-05 — vigged or de-vigged.** `settle_clv.py` compares raw single-side
   implied probabilities at both ends, deliberately, because the publish price
   is one-sided and cannot be de-vigged after the fact. That is internally
   consistent, but a raw single-side implied probability is a price with the
   book's margin inside it, not a probability. DUR-001 Amendment 1 froze the
   power method as this project's primary de-vig. I proposed raw as primary with
   de-vigged as a frozen sensitivity once two-sided capture exists. Does that
   hold, or does it just defer the contradiction?

3. **§4 — what cannot be backfilled.** The only error in this document that
   cannot be fixed later is an omission there. Two-sided capture at the publish
   instant is on it; capture cadence and feed version are on it. What is missing?

Also worth your scepticism: Q-04's "best available price" and Q-07's stake
weighting are the two options that would most flatter CLV. I rejected both. I
would rather you checked that I rejected them for the right reasons than that
you agreed with the conclusion.

### What I did not do

**I did not build the DUR-002 transition automation** (T-001). Reclassifying the
gate was the decision; the automation is a separate piece of work that needs DB
access and careful handling of the frozen-files table, and writing it blind
would have been worse than queuing it. It is L1/Claude and unblocked.

**I did not change `settle_clv.py`.** It keeps running under its existing
convention until the protocol freezes. Changing it now would pre-empt Q-05.

### Next action

**ChatGPT reviews the protocol methodology against the checklist in §7, and
returns a resolution for each of the six L1/L2 questions plus a recommendation
on each of the five L3 questions for Reed.**

The L3 five are Q-05, Q-06, Q-07, Q-08 and Q-11 — everything that changes what a
published number means. Reed sees those with your recommendation attached rather
than cold; that is the whole point of the review sitting between us.

If a question is mislevelled in either direction, say so — the level is proposed,
not fixed. Same for anything in §2 that you think is a disguised choice rather
than a settled rule.

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
