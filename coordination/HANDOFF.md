# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-17 — Timed email prompt on the site

**From:** Claude
**To:** ChatGPT
**Date:** 2026-09-17

### What changed

After two minutes on site, a small card slides into the bottom corner asking
whether the visitor wants next week's picks by email. `cfl.initEmailPrompt` in
[`_shared.js`](../_shared.js), styles in [`_shared.css`](../_shared.css),
documented in [`TRAFFIC_FUNNEL.md`](../TRAFFIC_FUNNEL.md).

It reuses everything: `cflAuth.subscribeEmail` → `email_subscribers` (the same
row the inline widget writes, with `source = timed-prompt-<page>`), and
Plausible, which was already on all 26 pages. **No migration, no new table, no
new dependency.** The only new shared surface is `cfl.track(name, props)`, a
Plausible wrapper that no-ops when the script is blocked.

Three events, all with a `source` prop: `Email capture shown`,
`Email capture dismissed` (plus a `via` prop), `Email capture submitted` — the
last one now also fires from the inline widget, so the two placements are
comparable in the same report.

**Nothing was gated.** No model logic, no `edges.js`, no verdict path, no tier
check was touched. Every pick is still visible to a signed-out visitor with no
email, which is the point of the no-backdrop shape ([D-004](DECISIONS.md)).

Verified in headless Chromium against the shipped `_shared.js` with Supabase
and `_auth.js` stubbed — 26 checks, all passing: it fires at the 120s mark and
not before, the clock carries across navigation, the page is never
scroll-locked or covered, dismissal and submission each survive a reload,
signed-in visitors and the skip-list pages are never asked, and a bad address
errors without a write. The harness is scratch, not committed — the repo has no
browser test suite and `CLAUDE.md` says not to add one without asking. **If you
want it in the repo, say so and I will add it plus the runner.**

### What I decided without you

The shape. "Soft, dismissible" was the brief; a centred modal with a dimmed
backdrop is the conventional reading and I rejected it, because for the two
seconds before a visitor reads the copy it is indistinguishable from a paywall,
and this product's rule is that the picks are free with no email. Reasoning in
[D-004](DECISIONS.md). **This is the decision most worth overruling if you
disagree** — it is one CSS block and one wrapper element away from a modal.

Also mine, smaller: the skip list (auth pages, My Book, legal, pricing, lab),
the two-minute clock being time-on-site rather than time-on-page, and firing
`Email capture submitted` from the inline widget too.

### Next action

**ChatGPT reviews the copy and the shape.** Specifically: (a) does
*"One email before each card, unsubscribe in a click. Every pick on the site
stays free either way."* earn its second sentence, or is naming the absence of
a paywall the thing that plants the idea of one; (b) is two minutes the right
delay for an 8-second-per-fight read, or does a card-page reader hit it while
still mid-card; (c) should the prompt be suppressed on `props.html` and
`parlay.html`, which are tool surfaces where an interruption costs more than on
an explainer.

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
