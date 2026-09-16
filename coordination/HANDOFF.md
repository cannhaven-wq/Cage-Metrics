# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-16 — CLV-001 FROZEN v1.0.0; one amendment proposed before settle_clv

**From:** Claude
**To:** Reed
**Date:** 2026-09-16

### What changed

Your L3 approvals are recorded and **CLV-001 is frozen at v1.0.0**
(2026-09-16T10:30:00Z, sha256 `ef912fce…`). Q-14 recorded first, `CLAUDE.md`
amended with your exact replacement rule, then Q-05/06/07/08/11/13 resolved.

**Freezing did not open publication, and I had to restructure the gate to keep
it that way.** The freeze procedure literally said *"publication_gate.
publication_allowed becomes true"* — following it would have published on a
sample of zero, against your explicit instruction. The gate is now the AND of
three conditions:

| condition | state |
|---|---|
| `protocol_frozen` | **true** |
| `sample_floor_met` | **false** — 0 of 100 observations, 0 of 20 events |
| `interval_excludes_zero` | **false** — unevaluable, and fail-closed |

Three of the original gate tests *skip* once frozen — they policed the run-up to
a freeze. That meant freezing would silently remove every check on publication
at the exact moment publication becomes conceivable. Eight new tests cover the
frozen state; flipping `publication_allowed` to true now fails with
`CLV publication is ALLOWED at 0/100 observations and 0/20 events`.

### The thing I need you to rule on

**Implementing the power de-vig found a mathematical error in the protocol you
froze this morning.** §6 says *"the sum is strictly decreasing in k"*. For the
formula it specifies, `q^(1/k)`, the sum is strictly **increasing** in k. It
decreases only under the other convention, `q^k`.

**No number changes.** The two are exact reparametrisations — the `q^k` root is
the reciprocal — so the fair probabilities are bit-identical, and both roots sit
inside the stated `[0.5, 5.0]` bracket. Verified on three pairs.

It still matters: an implementer trusting the stated direction inverts their sign
test and fails to converge. And it is a false statement inside a document whose
value is that you do not have to re-derive its claims.

Proposal at
[`research/clv/AMENDMENT_PROPOSAL_2026-09-16_devig_direction.md`](../research/clv/AMENDMENT_PROPOSAL_2026-09-16_devig_direction.md).

**I did not quietly fix it.** The protocol was frozen hours earlier, and
correcting a frozen document silently — even for something numerically inert —
is the exact habit the freeze exists to prevent. Afterwards it would be
indistinguishable from quietly correcting something that *did* change a number.

The implementation does not depend on the claim either way: `_bisect` reads the
sign at both bracket ends. Two tests pin the equivalence, and one is written to
start **failing** if the protocol's claim ever becomes true, so the note cannot
outlive its cause.

### What shipped

`cfl_engine/clv/devig.py` — the frozen arithmetic as pure functions: power
de-vig (primary), proportional and Shin (frozen sensitivities), the ≥3-book
consensus with per-book de-vig *then* median, and `CLV_return`. 33 tests, no DB.

One test earned its place immediately: **de-vig-then-median and
median-then-de-vig can coincide**, when one book is median on both sides. My
first version of that test asserted they always differ and failed. They differ
only when the median pair is *synthetic* — a pair no book quoted — which is the
situation Q-02's ordering exists to rule out. Both directions are now pinned.

### What I did NOT do

**`settle_clv.py` is untouched.** Two reasons, and I want you to pick:

1. `model_edges` has **no column** for `clv_return`, the closing fair
   probability, the book count, or an unscored reason. Writing the frozen
   measure needs a migration, and I do not apply migrations.
2. I cannot run it — no service key here — and it is a live daily writer.
   Shipping an unverified rewrite of it blind is how the 1970-timestamp class of
   defect gets introduced rather than found.

### Next action

**Reed: approve or reject the de-vig amendment, and say how you want
`settle_clv.py` reconciled** — a proposed-unapplied migration plus a
column-detecting script that reports `CLV_return` until the columns exist, or
wait until you can run it yourself.

Publication stays shut either way. 0 of 100.

---

## 2026-09-16 — CLV-001 v0.3.0-draft: review complete, L3 set ready for Reed

**From:** Claude
**To:** Reed
**Date:** 2026-09-16

### What changed

ChatGPT's **second pass** is applied. The methodological review is **complete**:
all six L2 questions resolved, all five L3 have a recommendation attached.

Both fixes it asked for are in:

1. **Q-05's blocker was contradicting the primary definition.** It still said
   two-sided capture *at publish*. Corrected to **at close** — under
   `CLV_return` the publish side is used as posted and is never de-vigged.
2. **Q-01b now has a number.** Staleness limit **45 minutes**, derived as one
   normal capture interval + a 15-minute operational grace, fixed before any CLV
   result was looked at.

Resolved this pass: **Q-02** (named book list, ≥3 books, de-vig per book *then*
median — that order matters), **Q-10** (unscored unless re-locked; match on
fighter + provider market ID), **Q-12** (power de-vig, matching DUR-001
Amendment 1.1). Recommendations recorded on **Q-11** and **Q-13**.

### Two things the measurement turned up

Both found read-only while deriving the staleness number. Neither is a CLV
result; both are operational properties of the capture pipeline.

**1. 28% of `fight_odds` is epoch-dated — and R-02 would not have caught it.**
30,724 of 110,032 rows, across 7,681 fights, carry
`captured_at = 1970-01-01`. Live capture starts 2026-05-22; everything before is
a historical import whose capture instant was never recorded.

R-02 excludes a *missing* timestamp. A populated fake one passes it. New rule
**R-13** closes that. The consequence is a coverage fact, not a gap to hide:
**CLV can only ever be computed on the live-capture era**, and those 7,681
fights can never enter the measure.

It is also the worst possible failure mode here specifically — an epoch stamp is
always "before the fight", so a sentinel row looks *eligible* to every ordering
rule and would be selected as the opener every time.

**2. The capture cadence is bimodal, and the naive reading is an order of
magnitude wrong.** ~30 min during a fight week (p50 30.0, p75 32.0); ~24 h
between cards (p90 1426.6 min, max 2952). Only the near-card mode is relevant,
because a staleness limit only binds near the close. Deriving the limit from the
overall p90 would have produced a **24-hour** staleness rule. That caveat now
travels with the number, with a test to keep it there.

### The one thing I need you to look at first

**Q-14 — may CLV appear in the user interface at all?** Two documents you own
give opposite answers:

> `CLAUDE.md`, line 3: "**No closing line value**, no edge percentages, and no
> market language **anywhere in the user interface**."

> `COPY_STYLE.md`, rule 3: "**CLV is the north star**, not win rate… **Say so.**"

These cannot both hold. **Q-11 spends its whole effort on how a positive CLV
figure may be phrased on a surface, and `CLAUDE.md` says no such figure may be
on a surface at all.** So Q-14 decides whether Q-11 has a subject.

No recommendation is offered on it, deliberately — it is a product-voice
decision, and a reviewer cannot resolve a conflict between two rules the owner
wrote. Whichever way it goes, **one of the two documents has to be amended.**

Worth knowing which way the work has been leaning: the protocol assumes a CLV
figure eventually reaches a surface, because that is what R-10's publication
gate exists to hold shut. If `CLAUDE.md` governs, R-10 is not a gate but a
permanent wall, and it should say so plainly instead.

### What is waiting on you

| | |
|---|---|
| **Q-14** | **first** — decides whether Q-11 has a subject |
| Q-11 | how positive CLV may be described, if at all |
| Q-05, Q-06 | what the headline number is |
| Q-07, Q-08, Q-13 | aggregation, and when a figure may appear |

Everything else is settled and recorded. The protocol stays **draft** and the
publication gate stays **shut** until you rule.

### What I did not do

**I did not touch `settle_clv.py`.** It still ships the `clv_pp` convention,
which v0.3.0 keeps as a secondary measure. Reconciling it is a freeze-time task.

**I did not resolve Q-14 myself**, and I did not amend `CLAUDE.md` or
`COPY_STYLE.md` to make the contradiction go away. Picking one would be choosing
the product voice on your behalf.

**No CLV figure was computed.** `results_computed_before_freeze` is still false.

### Next action

**Reed rules on Q-14 first, then Q-11, Q-05, Q-06, Q-07, Q-08 and Q-13.**

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
