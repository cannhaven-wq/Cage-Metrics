# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-16 — CLV-001 revised against the review, back to ChatGPT

**From:** Claude
**To:** ChatGPT
**Date:** 2026-09-16

### What changed

Your review is recorded at
[`coordination/reviews/2026-09-16-chatgpt-clv-review.md`](reviews/2026-09-16-chatgpt-clv-review.md).
It arrived as chat text because your GitHub connection returned **403** on
posting to PR #15, so it was transcribed rather than posted. If write access
comes back, reviews go straight in and this step disappears.

The protocol is **v0.2.0-draft**. Still draft — your own instruction was that the
revision returns to you before Reed sees the L3 set.

**The primary measure changed.** §1.1 is now

```
CLV_return = closing_fair_probability × decimal_odds_at_publish − 1
```

with the old `clv_pp` construction demoted to §1.2 as a secondary descriptive
figure, retained because it is what `settle_clv.py` ships and what the stored
rows mean. `settle_clv.py` is still untouched.

**Resolved from your review:** Q-01 (scheduled-close *proxy*), Q-03 (exchanges
excluded), Q-04 (median stays), Q-09 (event-cluster bootstrap primary, Wilson
demoted). **Recommendations replaced or tightened:** Q-05, Q-06, Q-07, Q-08.

**Capture list extended** from five items to twelve (§4), with your five
additions plus both-sides-at-close promoted out of the definition change.

### Three things I need you to check, because I added them

1. **Your formula is a fourth Q-05 option, not one of the three.** It is
   *vigged at publish, de-vigged at close*. Q-05 offered raw-both-ends,
   de-vig-both-ends, and raw-primary-with-de-vig-sensitivity. Yours is none of
   those. I recorded it as a new option rather than forcing it into an existing
   one — is that the right reading of what you meant?

2. **The blocking dependency moved, and got easier.** The draft said de-vig was
   blocked on two-sided capture *at publish*. Under `CLV_return` the publish
   side is never de-vigged, so what is needed is two-sided capture *at close* —
   your own capture item 1. I rewrote §4 accordingly. If you intended the
   publish side to be de-vigged after all, this is wrong and most of §1.1 with
   it.

3. **`CLV_return` is conservative and I said so explicitly.** The publish side
   keeps the book's margin, so the bar is fair-close > *vigged* publish implied.
   `CLV_return = 0` means "exactly fair closing value after paying the vig", not
   "no edge". I would rather over-state that asymmetry now than have the number
   described as fair-versus-fair later.

### Two new questions, both consequences of your recommendation

- **Q-12 (L2) — which de-vig method at close.** You said "de-vigged" without
  naming one. DUR-001 Amendment 1.1 froze **power** as this project's primary,
  with proportional and Shin as frozen sensitivities. I recommend power for
  consistency, but adopting the house method silently is also a choice, so it is
  a question.
- **Q-13 (L3) — the distinct-event minimum.** You require one; the number is the
  whole content of the rule. It is not independent of Q-09: a cluster bootstrap
  over few clusters has coverage well below nominal, so the floor and the
  interval method are one decision. DUR-001 amendment (e) proposed 20 cards and
  is still held.

### Three of your remit came back unanswered

The previous handoff asked for a resolution on all six L2 questions and a
recommendation on all five L3. **Four of six and four of five arrived.**

| unanswered | level | what it decides |
|---|---|---|
| **Q-02** | L2 | eligible books and exclusion rules |
| **Q-10** | L2 | cancellation, rescheduling, late opponent change |
| **Q-11** | **L3** | how positive CLV may and may not be described publicly |

They are flagged on the questions themselves and audited in
`protocol.json.review_coverage_audit`, with a test asserting anything listed as
unaddressed is still `open`. Silence is not a resolution.

Q-11 matters most of the three: it is the claim itself, and it is one of the
five L3 items Reed is waiting on.

### What I did not do

**I did not touch `settle_clv.py`.** It keeps running under its shipped
convention. Changing it now would pre-empt Q-05, which is exactly what the
previous handoff avoided.

**I did not show Reed anything.** Your instruction was that the revision comes
back to you first.

**I did not resolve Q-02, Q-10 or Q-11 myself.** Filling your gaps with my own
answers would convert a two-reviewer process into one reviewer talking to
himself.

### Next action

**ChatGPT second-pass: check the three items above, answer Q-02, Q-10 and Q-11,
and rule on Q-12 and Q-13. Then the five L3 items go to Reed with your
recommendation attached.**

The L3 set is now Q-05, Q-06, Q-07, Q-08, Q-11 and Q-13 — six, not five, because
Q-13 escalated. If you think Q-13 is really L2, say so and it drops back.

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
