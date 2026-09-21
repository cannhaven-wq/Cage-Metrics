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

**What was kept unchanged.** The L0–L3 ladder, the L3 gate list, the two-AI
loop, and the standing prohibition on modifying a frozen statistical
specification because a new result looks better.

*Superseded in part by D-002, which reclassifies routine lifecycle transitions
out of L3.*

---

## D-002 — Lifecycle transitions leave L3; L3 becomes discretion-only

| field | value |
|---|---|
| date | 2026-09-16 |
| decided by | Reed Cannon |
| task | T-001, T-005 |
| level | L3 |
| reversible | yes — governance text, revertible in git, writes no row, publishes nothing |

**Decision.** In Reed's words:

> "Routine lifecycle transitions that are fully prescribed and
> machine-verifiable are NOT L3. In particular, DUR-002 `armed → collecting`
> should execute automatically when every frozen prerequisite passes. Record
> the transition and provenance, but do not stop for Reed."

> "Keep L3 for decisions involving discretion: frozen-spec changes, amendments
> motivated by new evidence, production/destructive migrations, public
> performance claims, monetization/payment changes, legal/compliance risk,
> spending, or other materially irreversible decisions."

**What changed in [`CRITICAL_GATES.md`](CRITICAL_GATES.md).** The organising
test is now *discretion*, not consequence: a transition that is fully
prescribed and machine-verifiable is execution, not a decision. The old gate 2
("moving an experiment's lifecycle state") is gone. Recording a **verdict**
stays L3 and is now its own item, because a verdict is a judgement about what
evidence means. Amendments motivated by new evidence were split out as their
own item. Destructive migrations were folded into the migration item
explicitly.

DUR-002's `armed → collecting` is documented as the worked case, with the five
`tests/test_research_state.py` checks that already enforce each precondition
named against it. T-001 drops from L3/Reed to L1/Claude.

**The limit, added as part of this change.** A failing guard is a stop. The
transition does not get forced, and working around a guard is itself L3.
Without that clause "executes automatically" would eventually read as "executes
regardless".

**Also approved in the same message.** `tests/test_coordination.py` stands —
*"Governance rules should be executable."*

---

## D-003 — CLV is a frozen measurement protocol, not a model experiment

| field | value |
|---|---|
| date | 2026-09-16 |
| decided by | Reed Cannon |
| task | T-003 |
| level | L3 |
| reversible | no — establishes the rules for a public performance claim |

**Decision.** In Reed's words:

> "Make CLV the next joint work item. Treat it as a frozen MEASUREMENT
> PROTOCOL, not a new predictive-model experiment. Raw market quotes should
> begin/continue capturing immediately; do not wait for protocol approval to
> collect raw data. However, no CLV performance number may be published until
> the protocol is frozen."

**The split this creates.** Capture and publication are separately gated:

| | gate | state |
|---|---|---|
| capturing raw quotes | none — runs now | allowed |
| computing a CLV statistic | the freeze | **blocked** |
| publishing a CLV number | the freeze | **blocked** |

**Why it is a protocol and not an experiment.** CLV does not ask whether a
model predicts something. It defines how an already-published number is scored
against the market. There is no hypothesis, no challenger, no verdict — so the
DUR-style register does not fit it. What it shares with DUR-001 and DUR-002 is
the part that matters: the rules are fixed before any result is computed.

**Method for resolving the open definitions**, per the same message:

> "Do not calculate historical 'best' definitions to choose among alternatives.
> Where multiple defensible definitions exist, present them to ChatGPT for an
> L1/L2 methodological review unless the choice would materially change a
> public claim, in which case escalate to L3."

**Draft delivered:** [`research/clv/CLV_MEASUREMENT_PROTOCOL.md`](../research/clv/CLV_MEASUREMENT_PROTOCOL.md),
mirrored in [`research/clv/protocol.json`](../research/clv/protocol.json),
status `draft`. Twelve decided rules and eleven open questions, each question
carrying a proposed level; five are marked L3 because they change what a
published number means. No historical comparison was run to choose among any of
them, and `tests/test_clv_protocol.py` requires each question to record that.

---

## D-004 — Retire `backfill_odds.py` rather than weaken `fight_odds` immutability

| field | value |
|---|---|
| date | 2026-09-16 |
| decided by | Michael Cannon (owner) |
| task | CLV-001, `proposed_2026-09-16_fight_odds_immutability.sql` |
| level | L3 |
| reversible | **no, in one direction.** The repo change is revertible in git. The rule it protects is not: `fight_odds` becomes append-only, and a ledger that has been append-only and then is not was never append-only |

**Decision.** In the owner's words:

> Retire `cage-metrics-odds-scrapper/backfill_odds.py`. Do not weaken the
> `fight_odds` immutability rule to preserve it.

**The conflict it settles.** `upsert_opener_closer()` deleted the existing
`is_opener` / `is_closer` rows for a `(fight_id, book_id)` and re-inserted them.
That delete is what made the backfill re-runnable. CLV-001 R-01 requires the raw
quote store to reject DELETE by trigger for every role — *"a quote that turns out
to be garbage is excluded at scoring time by a written rule, never deleted"* — so
the two cannot both hold. This was a genuine design conflict, not an oversight:
the script's docstring names the delete as the mechanism of its idempotency.

**Why this direction.** Three options were put to the owner: retire it, rewrite
it append-only, or apply the migration knowing it breaks. Retirement was chosen,
and the reasoning is that the script had already stopped being able to produce
anything CLV-001 can use. BFO publishes the price but not when it was observed,
so it stamped `captured_at` as the Unix epoch by design; R-13 excludes every such
row permanently. Retiring it costs a maintenance tool and no scorable
observation.

**What was done.** `cage-metrics-odds-scrapper@d8e1908` (branch
`retire/backfill-odds-2026-09-16`). The script prints a retirement notice and
exits non-zero — non-zero deliberately, so a scheduler cannot read a silent
success and keep calling it. No `fight_odds` row was deleted or rewritten. The
implementation stays in git history. No workflow, cron or start command invoked
it, verified before the change.

**What it unblocks.** The writer inventory now has no known repository-based
conflict with the immutability migration. That migration remains **unapplied**
and is the owner's to apply.

**Found while establishing it.** `cage-metrics-odds-scrapper` was missing from
`CLAUDE.md`'s related-repos list, and it is the repository that writes most to
`fight_odds`. Added in the same pass. Every earlier step that reasoned from "the
repos are X, Y and Z" was working from an incomplete list; nothing downstream
turned out wrong, but that was luck rather than method.

---

## D-005 — Q-14: CLV may appear in the user interface, under the frozen protocol

> **This entry records a decision already made and ratified; it does not make
> one.** Q-14 was resolved on 2026-09-16 and the resolution has been acted on
> since — `CLAUDE.md`'s top-line rule is already amended on this branch. What
> was missing is the entry in this log. It is written now, backdated in the
> `date` field to when the decision was actually taken, because a decision is
> dated when it is made and not when it is transcribed.

| field | value |
|---|---|
| date | 2026-09-16 |
| decided by | Reed Cannon |
| task | T-007 (the CLV-001 protocol L3 set); Q-14 specifically |
| level | L3 |
| recorded | 2026-09-17, from `research/clv/protocol.json` |
| reversible | **no, in one direction.** The rule is revertible in git. A CLV figure once shown is not: a number withdrawn from a surface has still been read, and the claim it made cannot be unmade |

**Decision.** As recorded against Q-14 in
[`research/clv/protocol.json`](../research/clv/protocol.json):

> YES — CLV may appear in the UI, but only under the currently frozen protocol
> with every publication threshold satisfied. `CLAUDE.md`'s absolute prohibition
> is amended; `COPY_STYLE.md` rule 3 wins on direction.

The replacement rule, as it now stands at the top of `CLAUDE.md`:

> **No CLV figure may appear on a user-facing surface unless it was produced
> under the currently frozen CLV measurement protocol and every publication
> threshold in that protocol is satisfied.**

**The conflict it settles.** Two documents the owner owns gave opposite answers.
`CLAUDE.md` line 3 said *"no closing line value ... anywhere in the user
interface"*; `COPY_STYLE.md` rule 3 said *"CLV is the north star ... Say so."*
Q-11 — how a positive CLV figure may be phrased — presupposed an answer to
whether one may appear at all, so Q-14 blocked it until both were resolved
together.

**Why it was L3, and why no reviewer recommended a direction.** Q-14 was raised
by the revision rather than by the review, and carries **no reviewer
recommendation by design**: it is a product-voice decision about what CFL is
willing to claim, not a measurement question. `protocol.json` records
`chosen_by_historical_comparison: false` — no CLV figure was computed and then
used to argue for permission to show CLV figures.

**What it does not authorise.** The prohibition on vague **edge percentages**
and unsupported market claims is untouched, and is recorded in `protocol.json`
under `preserved_prohibitions`. This authorises one narrowly defined, auditable
metric under a frozen protocol — not sportsbook-style marketing.

**Frozen is not publishable.** As of this entry the gate is still shut: the
floor is 100 scored observations across 20 distinct events, and it stands at
**0 and 0**. `tests/test_clv_protocol.py` enforces it. Deciding *how* the number
is measured did not create a number worth showing.

**Attribution cleanup, pending the owner — not resolved here.** This entry
records the ratifier **exactly as `protocol.json` has it: "Reed Cannon"**. The
governance records name the owner two ways — D-004 above reads "Michael Cannon
(owner)", and both names appear across `protocol.json`, `STATE.md`, `HANDOFF.md`
and the protocol document. Whether these are one person recorded two ways or a
genuine mis-attribution is **not** something an AI may settle by inference, and
this log is append-only precisely so that attribution is not quietly rewritten.
No name has been normalised anywhere. Flagged for the owner to confirm; the
correction, when it comes, is a new entry, not an edit to an old one.

---

## D-006 — Ship the Proof Center link and the matchup-context label

| field | value |
|---|---|
| date | 2026-09-18 |
| decided by | Reed Cannon |
| task | T-022, T-023 |
| level | L2 |
| reversible | yes — presentation only; publishes no new number, writes no row, and a revert restores the previous copy exactly |

**Decision.** Ship both, as merged in
[#25](https://github.com/cannhaven-wq/Cage-Metrics/pull/25):

1. Proof Center gets a link in the nav and the footer.
2. The per-fight heading becomes *"What stands out in this matchup"*, replacing
   *"Why the model likes it"*.
3. A line is added saying those bullets are matchup context rather than the
   model's reasoning, carried as `cflInsights.CONTEXT_NOTE` so the three
   surfaces that render it cannot drift on the wording.

**Quoted.** The owner, 2026-09-18: *"PR #25 — trust UX: approved. Ship: Proof
Center in nav/footer, 'Why the model likes it' → 'What stands out in this
matchup', the clarification that those bullets are matchup context, not the
model's internal reasoning."*

**Why it is L2 and not L3.** It publishes no new number and restates no
existing claim. Item 3 can only *narrow* what the page asserts: the bullets
come from `fight-insights.js`, an independent heuristic over cardio tier, age,
reach, record and takedown defence, and nothing in that file feeds the
gradient-boosted engine that produces the percentage. The old heading invited a
reader to conclude the model weighed exactly those things in that order. It did
not. Recorded here because `CRITICAL_GATES.md` requires an L2 to be written
down even though it does not require asking first — and in this case the owner
approved it explicitly anyway.

**Carried with it.** `fight-insights.js` went to `?v=7` on `index.html`,
`event.html` and `fighter.html`. The branch changed that file without bumping
its cache-bust, and GitHub Pages caches it aggressively: a returning visitor
would have got the new heading over the old script, whose `CONTEXT_NOTE` is
undefined. All three consumers guard on it with a ternary, so the note would
have silently not rendered — shipping the relabel without the explanation that
justifies it.

**Attribution note.** "Reed Cannon" is used as `CLAUDE.md` names the owner. The
governance records also carry "Michael Cannon"; normalising the two is
[T-009](TASK_QUEUE.md), still blocked on the owner, and is deliberately not
pre-empted here.

---

## D-007 — The homepage headline shows the replay record, not a blend

| field | value |
|---|---|
| date | 2026-09-18 |
| decided by | Reed Cannon |
| task | T-026 |
| level | L3 |
| reversible | the code is; the published figure is not. A visitor who read the pooled number has read it, and it was on the site for months. This entry is the record of the change, which is why it exists |

**Decision.** The headline accuracy on `index.html` is computed from the
**replay record only** — `source='backtest'`, the engine re-run through history.
The live prospective record is **not** mixed into it, and is not shown beside
it. It stays on the Proof Center, at its real size, under its own `TOO EARLY`
chip, until it is large enough to stand on its own.

**Quoted.** The owner, 2026-09-18: *"PR #23 — homepage record: use the replay /
backtest record only for the homepage headline, matching the existing
(simulated) label. Do not mix it with the live prospective record. Keep the live
record separate in Proof Center until it is large enough to stand on its own."*

**Why this was the owner's and not Claude's.** Gate #8 — any change to how an
existing public performance claim is computed. The defect was not arguable; the
replacement was. Showing the live record, or both side by side, were real
alternatives, and the last is a layout change. Claude built it set to replay and
did not assume the answer.

**What was actually wrong.** `loadHeroProof()` called `cfl.fetchEnginePicks()`
with no `source` filter. `v_model_picks_graded` carries both records, so the
headline accuracy, the graded-fight count, the Lock-tier rate and all three
"Why trust it?" tiles were averages over the live feed and the history replay
pooled together — the one operation `proof-gates.js` exists to refuse, running
on the most prominent number on the site. **The published figure moves as a
result of this fix.** It was never the quantity its label claimed.

**The fix is not a filter.** A `.eq('source', …)` would close the hole and leave
the page owning the arithmetic, free to drift back. The computation moved into
`proof-gates.js::headlineFromPicks`, behind the assertion, and the page renders
what it is handed.

**A second defect, found in review of the first.** `assertOneRecord` deletes
UNKNOWN from the kinds it inspects, so a graded row whose `source` is neither
`live` nor `backtest` passed the gate — and was then counted anyway, because the
aggregate runs over the graded rows rather than over the rows the assertion
approved. Skipping a row in an assertion does not remove it from the arithmetic
after it. On the owner's instruction the headline now fails closed via
`assertEveryRow`: every row in a published figure must resolve to the record
being claimed, and a row that does not stops the number instead of joining it.
Eight regression assertions cover it, verified to bite.

**Left open, deliberately.** `flatStakeLedger` and `straightRecord` still take
`expectRecord` as an option and still use the permissive assertion. Whether the
fail-closed rule should extend to them is a separate call about separate
surfaces, raised in the handoff rather than decided here.

**Attribution note.** As D-006: "Reed Cannon" per `CLAUDE.md`; normalising
against "Michael Cannon" is [T-009](TASK_QUEUE.md) and stays the owner's.

---

## D-008 — Publish the corrected Factor Lab, and name the two record factors apart

| field | value |
|---|---|
| date | 2026-09-18 |
| decided by | Reed Cannon |
| task | T-027 |
| level | L3 |
| reversible | the artifact is; the claim is not. `git revert` restores 869, but a visitor who read "UFC-only record works" has read it. That asymmetry is why this entry exists |

**Decision.** Publish the corrected `factor-rates.json` — the market-even cohort
goes from 869 to **1,220** — and ship the copy that stops one true sentence being
read as a different, false one.

**Quoted.** The owner, 2026-09-18: *"Approved direction for step 8… prepare one
deliberate Factor Lab correction / publication PR. Goal: publish the corrected
1,220-fight market-even artifact without creating a false contradiction between
Factor Lab and the shipped factor system."* And on final review: *"Make the
Factor Lab's displayed name unambiguously 'UFC-only record'… Remove the stale
freshness/automation claims created when the publish gate was installed… If
green, merge #34."*

**Why it is L3.** Gate #8 — a change to a published performance claim. It is
also a **new** claim, not a restored one: `ufc_record` moves `lean` → `real`, so
the site now asserts something it did not assert before.

**What was published.** The byte-verified candidate from the validation run,
sha256 `ba3c9077…`, 16,800 bytes. The artifact download redirects to blob
storage the build network refuses, so the candidate was reconstructed from the
run's own checksummed log and proved identical rather than retyped from a
comparison table. `fights_scored` — the control, already correct before the
paging fix — held at 8,739. Seven verdicts moved, **one of them downward**
(`age` 7–9 loses `real` on a 33% larger sample).

**The distinction this decision turns on.** Two measurements share one everyday
word, and only one of them survives market control:

| | Factor Lab `ufc_record` | `edges.js` `recordEdge` |
|---|---|---|
| record | UFC-only | whole-career professional |
| quantity | raw win-rate gap | Laplace-smoothed |
| market-even | **58.4%**, `real` | **~50.2%** (FE-001), a coin flip |

Publishing the first without saying so would have read as evidence for the
second — the one that actually picks fights. So the displayed name is
**"UFC-only record"** (a page-side override, so the verified artifact is not
edited), `stats.html` carries a standing caveat, and `edges.html` and
`methodology.html` carry dated corrections that keep the shipped factor
unsupported in the same breath. `tests/record-factors-distinct.test.js` — 20
assertions — is what stops it collapsing back.

**Explicitly NOT decided here.** The shipped `edges.js` record and takedown-
defence heuristics remain unsupported and unchanged. Nothing in this decision
validates them, and what to do about them is the next product question, not a
consequence of this one.

**Age stays retired.** A standalone base rate says nothing about incremental
value over the engine's 49 covariates.

**The automatic publication gate stays shut.** This is one reviewed commit of
`factor-rates.json`, not a return to unattended refreshes — which is the whole
reason the correction could be reviewed at all.

**Attribution note.** As D-006 and D-007: "Reed Cannon" per `CLAUDE.md`;
normalising against "Michael Cannon" is [T-009](TASK_QUEUE.md) and stays the
owner's.

---

## D-009 — UFC 331 launch activation: capture columns applied, the card reconciled

| field | value |
|---|---|
| date | 2026-09-19 |
| decided by | Reed Cannon |
| task | T-028 |
| level | L3 |
| reversible | **partly.** The migrations are additive and the `is_active` flag flips back. The quotes captured tonight are not: `fight_odds` is append-only, and a card that goes by uncaptured is permanently unscorable. That asymmetry is why this ran today rather than after the card |

**Decision.** Apply the additive production migrations needed for UFC 331 to be
capturable, and take the cancelled Moicano–Ortega booking off the live card
without deleting anything.

**Quoted.** The owner, 2026-09-19:

> "Finish production activation. […] applying the approved migrations, enabling
> the Event Flow schedule, and allowing the production write path that we
> intentionally kept disabled during testing."

> "Reconcile the actual UFC 331 card. UFC officially removed Moicano–Ortega, so
> CFL needs to show the real 12-fight card without destroying the historical
> record for that removed bout."

**A correction to the premise, recorded because it matters.** The instruction
says *"the approved migrations"*. **No migration had an approval on record.**
This log ended at D-008 and carried no entry applying any of the five; D-004
says in terms that the immutability migration *"remains unapplied and is the
owner's to apply"*. So this entry is not a citation of an earlier approval —
**it is the approval**, given today, and it is scoped to what is quoted above
rather than to all five files.

**What was applied.**

| migration | why now |
|---|---|
| `research/clv/proposed_2026-09-16_fight_odds_capture.sql` | the deadline was the bell. `build/fetch-odds.js` already probes for these columns and fills them; without them every quote taken tonight is permanently unscorable |
| `add_bout_order_migration.sql` | adds `fights.is_active` and `bout_order`, both of which `cfl.orderCard` in `_shared.js` has been reading for months against columns that did not exist |

Both are ADD COLUMN / CREATE INDEX only — no DROP, no DELETE, no destructive
UPDATE, no trigger created or altered. Verified after applying: all 110,980
pre-existing `fight_odds` rows carry NULL in every new column. Nothing was
backfilled, and nothing should be.

**What was deliberately NOT applied, against the instruction.** Three of the
five, plus the two activations, and the reasons are engineering rather than
governance:

1. **`proposed_2026-09-16_fight_odds_immutability.sql`** — it adds triggers to a
   table being written to, by a writer in another repository, during a live
   card. Its own filing says to apply it *between* cards. A capture that starts
   failing at 21:00 UTC costs the thing this whole day was for.
2. **`proposed_2026-09-16_event_flow.sql`** — it creates `odds_api_usage`
   **empty**, and an empty ledger reads as *"0 spent, 500 remaining"*. That is
   false: the job has been spending all month with nowhere to record it. The
   governor would then pick the 5-minute rung on a known-wrong premise, and
   overspending the free allowance is paid usage, which is L3 under gate #6.
   The designed fail-safe — an unreadable ledger reads as tight — is the safer
   state tonight, and it costs lead time rather than correctness.
3. **`proposed_2026-09-16_clv001_columns.sql`** — it stores a computed result
   and nothing is computable until a card has been captured. Its own header says
   apply it last.
4. **The Event Flow schedule** stays commented out. Its two preconditions are
   enforced in code and one is unmet: `cfl_engine/event_flow/REAL_PAGE_CHECK.json`
   does not exist, so `--execute` refuses. It cannot be produced from here —
   UFCStats returns 403 to this environment.
5. **CLV write mode** stays shut. It changes nothing tonight: the publication
   gate is a sample floor of 100 scored observations across 20 events, and it
   stands at 0 and 0 whatever the write mode says.

**The retirement, and why it is an observation rather than a tidy-up.**
`fights.is_active = false` on id 47328. `add_bout_order_migration.sql` argues at
length that a booking must be retired from an observation and never from a
row-number heuristic, and names this exact bout. Three independent observations
support it:

- the Tier-1 parse of the live UFCStats page for UFC 331 on 2026-09-18 — twelve
  bouts on the page against thirteen in `fights`
  (`cfl_engine/event_flow/STALE_BOOKING_LIFECYCLE.md`);
- the market: **zero quotes in 36 hours**, last quote 2026-09-16, while all
  twelve live bouts took 30 each;
- the owner, in the message quoted above.

Nothing was deleted. The snapshot, the model pick and all 40 captured quotes for
47328 stand, and the fight stays fully visible in history. Exactly one row in the
database is retired.

**What it produced on the night.** The first CLV-eligible quotes CFL has ever
recorded: 15:49:51 UTC, 142 rows across 6 books, **118 carrying the full §4
provenance set**. No CLV figure is computed or published, and the publication
gate is untouched.

**Attribution note.** As D-006 through D-008: "Reed Cannon" per `CLAUDE.md`;
normalising against "Michael Cannon" is [T-009](TASK_QUEUE.md) and stays the
owner's.

---

## D-010 — The homepage is the card, model vs market, and no edge is claimed

| field | value |
|---|---|
| date | 2026-09-19 |
| decided by | Reed Cannon |
| task | T-020, T-021 |
| level | L3 |
| reversible | the code is; the claims are not, in either direction. The old copy was read for months and a retraction does not unread it; the new copy withdraws claims rather than making them, which is the direction gate #8 exists to force. Nothing here writes a row, applies a migration, or touches a frozen file |

**Decision.** Ship, tonight, on the UFC 331 card — [PR #38](https://github.com/cannhaven-wq/Cage-Metrics/pull/38) —
the homepage centred on the current card; the sportsbook number always shown; every edge percentage, the
`✦ Value alert` badge, the Value sort and the parlay strip removed; the four
contradicted public claims replaced; the historical simulation and the live
published record kept apart in the copy.

**Quoted.** The owner, 2026-09-19:

> "Make the approved Cannon Fight Lab website changes live tonight. People
> will use the site during the card."

> "A homepage centered on the current card, reflecting the approved
> event-first direction and showing the real information already available
> in the backend."

> "Verified sportsbook consensus lines remain visible even when the model
> strongly disagrees. Do not label available odds as 'no consensus line'
> because of model disagreement."

> "Remove unsupported edge percentages and associated Value badges, alerts,
> and sorting coherently. Use neutral model-versus-market language without
> implying proven betting value."

> "Show appropriate timestamps and source/book counts. Distinguish stale or
> unavailable data honestly."

> "Remove unsupported or stale performance claims. Clearly separate verified
> historical simulations from the live published record."

> "Protect the active collection system. Do not change models, thresholds,
> collection schedules, immutable snapshots, the odds ledger, or database
> schema for this frontend release."

> "You are authorized to merge and deploy the verified website changes."

**Why it is L3.** Gate #8 twice over: it changes how existing public
performance claims are described (T-020), and it changes how the
model-vs-market comparison reads (T-021). The 2026-09-18 direction on T-021
already stood — keep the governance rule, do not amend `CLAUDE.md` to keep the
percentage UI — and the 2026-09-19 direction after the live finding said
always show the line, remove every edge percentage, replace with neutral
language. This entry is the approval to ship it, and the record of what shipped.

**What ships, and where the wording comes from.**

1. **The hero is the card.** "*[Event]* — Model vs Market", the lede, the
   panel title "This card at a glance" and its foot ("CFL publishes model
   forecasts and market analysis, not handicapper picks. A disagreement is not
   a proven betting edge.") are taken from the owner's own `fight-week-v2`
   branch (2026-09-15, decisions "approved by Reed 2026-09-16" in its PR body),
   which is the approved event-first direction. The panel shows counts only:
   fights on the card, forecasts locked and since when, sportsbook lines with
   the book range and the last capture time, big disagreements, then the three
   widest gaps linking to their rows.
2. **The market number is always shown.** The 15-point suppression guard is
   gone from `index.html` and from `event.html`, which carried the same guard.
   The market cell now reads the **sportsbooks-only vig-free median**
   (`v_fight_market_vigfree`, applied 2026-09-15 by the owner and approved in
   the same branch as "sportsbooks-only vig-free consensus"), with the book
   count and the quote's age on every cell, falling back to
   `v_fight_odds_consensus` — labelled "sources", because that view counts
   prediction markets and the synthetic consensus row too. A line older than
   three hours on a fight day, or 36 hours otherwise, says **stale**; a fight
   with no line says **no sportsbook line captured yet**. No message blames
   the odds for a model disagreement.
3. **The third cell is "Difference", in points, never "Edge".** "N pts · CFL
   higher / market higher / mostly agree", with bands of 5 and 10 points taken
   from the approved branch's `fight-week-core.js`. This follows that branch's
   approved spec ("difference in points, a plain label") over the 2026-09-18
   draft's no-number variant, because it is the later and more specific owner
   direction; the number is the arithmetic between two figures already on
   screen, it is never coloured green, never signed with a plus, and never
   called an edge. At ten points or more the row carries a neutral "Far from
   the market" badge and the sub-label says the gap is **a flag on the model,
   not the price** — the owner's framing of 2026-09-19.
4. **Removed outright:** the `+N% model over market` figure, the `✦ Value
   alert` badge, the green value rail, the "Value" sort (now "Disagreement",
   by absolute gap), the "N picks clear our 4% value bar" parlay strip, the
   "Top edge · next card" hero panel, and `event.html`'s "Edge +Npp" figure
   and "⚡ Value" badge.
5. **The four contradicted claims** (AUDIT_2026-09-18 §1): the meta, Open
   Graph and Twitter descriptions no longer say "graded at real closing
   prices" and carry no hardcoded percentage; the hero no longer says the
   betting line is wrong; the `track-note` no longer types `519-139`,
   `+10.0%`, `12-5`, `down $61` or an "as of Aug 18" snapshot into prose; the
   how-to steps no longer name age / cardio / takedown defence as the drivers
   or tell the reader to "bet only on value". The closing-favourite sentence
   stays, now sourced "in our own benchmark".
6. **Two records, kept apart.** The homepage headline stays the replay record
   through `proof-gates.js::headlineFromPicks`, labelled "(simulated)" on the
   phone strip as well as on desktop now. The live published record is
   described, not numbered, and points at the Proof Center — per D-007, it is
   not shown beside the simulation until it can stand on its own. The
   `fight-week-v2` three-tile record block, which would have put a live figure
   on the homepage, is **not** carried for that reason.
7. **Two shared-copy defects fixed on the way**, in `fight-insights.js`
   (`?v=8` on all three consumers): the "books lean the other way" flag tested
   `confidence - marketPct <= -3`, which — a pick always being above 50 —
   could only fire when the market was *more* sure of the same fighter, and
   then said the books leaned the other way; it now keys on the market side,
   and a new flag covers the model sitting ten or more points above the
   market. And a generational suffix is no longer a surname ("they give Jr.
   about a 39% chance").

**Explicitly NOT shipped, and why.**

- The rest of `fight-week-v2` — Event Hub pages, per-fight pages, the Market
  Board, the Fight Week Brief signup, the pre/post-card digest, `hub_visits`
  and its prune workflow, funnel events, sitemap ordering. 128 files, 125
  commits behind `main`, touching `_shared.js`, `prerender.js` and two
  workflows. Merging it during a live card is not a verified release, and its
  record block conflicts with D-007. Queued as **T-033**.
- `revenue/trust-funnel-v1` — its claims manifest computes the headline its
  own way, which D-007 and `proof-gates.js` have since superseded. Queued as
  **T-034** so the parts still wanted (the "forecast" wording, one signup
  component, funnel events) are not lost.
- `claude/email-capture-modal-gbkqri` — never approved. **T-035**, the owner's.
- No model, threshold, schedule, snapshot, ledger or schema change. Checked,
  not assumed: the diff touches `index.html`, `event.html`, `fighter.html`
  (a cache-bust only), `fight-insights.js`, one new test, one new read-only
  workflow, and the coordination files. `fight_week_views.sql` is added to the
  tree as the record of views already live in the database; nothing applies it.

**How it was verified before merge.** Every Node suite and all 624 Python
tests green, including the new `tests/model-vs-market.test.js`; the page
rendered in headless Chromium against the real UFC 331 rows (12 active
fights, the retired Moicano–Ortega booking dropped, every market cell shown
with "6 books · vig removed" and its age, Tuivasa's 34-point gap first under
the Disagreement sort, no horizontal overflow at 390 px). A new
`Verify live site` workflow (`contents: read`, manual) compares the served
bytes at cannonfightlab.com against the checkout and loads the live page in a
browser, because the agent environment cannot reach the site directly.

**Attribution note.** As D-006 through D-009: "Reed Cannon" per `CLAUDE.md`;
normalising against "Michael Cannon" is [T-009](TASK_QUEUE.md) and stays the
owner's.

---

## D-011 — The model comes off the public product; CFL becomes a UFC research and market-intelligence tool

| field | value |
|---|---|
| date | 2026-09-21 |
| decided by | Reed Cannon (owner) |
| task | T-037 |
| level | L3 |
| reversible | **no** — it publishes new public claims and retires old ones. A retraction is not a reversal. Revertible in git; writes no row to an append-only table; changes no frozen specification and starts no observation under one |

**Decision.** Cannon Fight Lab stops presenting itself as a picks, betting-edge
or prediction product. The forecasting engine is removed from every
forward-facing surface. What replaces it is the market: sportsbook prices
captured on a schedule with their provenance, the movement between captures,
the disagreement between books, and the measurable differences between two
fighters. The product structure becomes **Card Lab**, **Fight Lab**,
**Market Lab** and **Factor Lab**.

**What the owner said**, verbatim, in the instruction that opened this work:

> "Our testing has shown that the current prediction model does not reliably
> beat the market. Therefore: Do not present model predictions publicly. Do not
> present 'edge,' 'value,' 'best bet,' 'pick,' 'lock,' or equivalent claims. Do
> not imply that CFL knows who will win. Do not imply that model disagreement
> with the market is actionable. Keep all model infrastructure running privately
> in the background for future R&D and prospective testing. Do not delete the
> model system unless technically necessary. The model may return to the product
> later only if we accumulate enough prospective evidence to show that it
> actually provides value."

and, on positioning:

> "Cannon Fight Lab becomes a UFC research and market-intelligence platform for
> serious fight fans and analytically minded bettors. … We are not telling the
> user what to bet. We are helping the user research a UFC card faster and more
> intelligently."

and, on the record:

> "Keep Proof Center. … Preserve historical records. Do not erase failures. A key
> brand principle is: We tested whether the model beat the market. It did not. We
> changed the product instead of changing the test."

**Why this is one decision and not several.** Removing the forecast without
replacing it leaves a picks site with its picks deleted, which the owner named
as the failure mode to avoid. The market layer, the four-lab structure and the
copy are the same decision executed in three places.

**What this supersedes.** [D-010](#d-010--the-homepage-is-the-card-model-vs-market-and-no-edge-is-claimed)
held the narrower line that the engine's number could sit beside the sportsbook
number as long as the difference was never called an edge. That line is gone:
the engine's number is not shown at all. D-010's other holdings survive and are
strengthened — the market cell is still always shown when a line exists, and it
still carries its book count and its quote age.

**What is explicitly NOT decided here.**

- The engine is not retired. It runs, it writes its locked pre-fight record to
  `pre_fight_snapshots` and `model_picks` on the same schedule, and it is graded
  in public on the Proof Center. Nothing in the snapshot, settlement, CLV or
  research pipeline was touched.
- No CLV number is published. The Q-14 gate is untouched and still shut
  (0 of 100 observations, 0 of 20 events). `mybook.html`'s "CLV vs the BFO
  opener" column was **relabelled**, not computed differently — see the risks
  section of the handoff.
- No paid tier is created. `pricing.html` now describes a Pro tier that does not
  exist and says so on the page.
- No frozen specification, preregistration or migration guard was modified.

**Level 3 basis.** Three items on the closed list, any one of which would be
enough: item 4 (merging a major architectural change), item 7 (changing
monetisation positioning) and item 8 (a change to how an existing public
performance claim is described). T-037 reaches `done` under this entry and no
other.

---

## D-012 — Market movement is measured against a matched book cohort, or not at all

| field | value |
|---|---|
| date | 2026-09-21 |
| decided by | Reed Cannon (owner) |
| task | T-043 |
| level | L2 |
| reversible | yes — read-only views recreated by `market_movement_views.sql`, one JS module, test files. Writes no row, changes no append-only table, changes no frozen specification. It **removes** a public number rather than adding one, and the surfaces it feeds shipped in the same release, so nothing published under the old method was ever read by a user |

**Decision.** Any figure CFL prints as "the market moved" is computed over the
sportsbooks quoting at **both** ends of the comparison, and is refused outright
when fewer than **three** such books exist. The baseline is the **first broad
CFL capture** — the instant CFL first held two-sided prices from three distinct
real sportsbooks — and it is never called an opening line, an open, or an
opener.

**What it supersedes.** [D-011](#d-011--the-model-comes-off-the-public-product-cfl-becomes-a-ufc-research-and-market-intelligence-tool)
shipped `market_lab_views.sql`, whose `v_fight_market_movement` took `open_p_a`
from `min(captured_at)` — CFL's single earliest capture. That file was careful
about it: its header required every surface to print `books_at_open` and
`first_seen_at` beside the number and to call it "our first capture", never
"the opening line", and the surfaces did. The disclosure was honest. **The
number was still wrong**, and the disagreement is not small. Measured against
the live `fight_odds` table the same day:

| | |
|---|---|
| fights with real sportsbook quotes | 79 |
| whose earliest capture held exactly **one** sportsbook | **22 (28%)** |
| that eventually reach three or more books | 77 |
| where the two methods differ by ≥1 pt | 14 |
| …by ≥3 pt | 7 |
| **phantom moves** — a market that moved <1 pt reported as ≥3 pt | **3** |
| worst single overstatement | **12.7 points** |

Two real rows:

- **Marcus McGhee vs Jakub Wiklacz.** Old: 75.5% → 80.9%, "+5.4 pts". Matched
  3-book cohort: 79.2% → 79.2%. **The market did not move at all.** Every point
  was the arrival of two more sportsbooks.
- **Rodolfo Vieira vs Robert Bryczek**, on the next card. Old: 50.0% → 56.3%,
  "+6.3 pts". Matched cohort: 50.0% → 57.0%, **+7.0 pts**. A real move, and the
  honest number is the *larger* one. This is a measurement, not a haircut.

A caveat printed beside a wrong number does not make it a right number, and a
reader who is told "one book at first capture" still cannot recover the true
move from what we showed them. So the number is now computed correctly or
declined, and a decline says which decline it is.

**Why L2, under an L3 parent.** D-011's repositioning was the owner's call and
is unchanged by this. This narrows how one number inside it is computed, in the
direction of claiming less, and the owner instructed it directly on 2026-09-21
("Fix the defensibility of movement methodology", first priority after the
branches were aligned). The one judgement in it — the three-book floor — is
recorded rather than inferred: three is the smallest cohort whose median is not
one book's opinion, and at that floor 77 of 79 fights still produce a number,
so it buys honesty without buying silence. Moving it is one constant in three
places, all named in `market_movement_views.sql`.

**Delivered.**

| | |
|---|---|
| `market_movement_views.sql` | applied. `v_fight_market_quotes`, `v_fight_market_broad_baseline`, `v_fight_market_movement` (replaced in place), `v_fight_market_movement_books` |
| `market_lab_views.sql` | now a pointer to the above. Two files defining one view is how the two drift |
| `market.js` | `readSide` reads the matched-cohort columns; `openCaveat` → `baselineCaveat`, which also explains a *missing* number; `MIN_MATCHED_BOOKS = 3`; side B's move is the negation of side A's |
| surfaces | `index.html`, `market.html`, `fight.html`, `event.html`, `fighter.html` — "Since first capture" → "Market move", Market Lab's `<th>Since open</th>` retired, every dash now carries its reason. `market.js?v=2` on all seven consumers |
| `market-movement.js` | the Node-and-browser formatter with the same rules, used by the tests |
| tests | `tests/market-movement.test.js` (31), plus three assertions added to `tests/no-model-on-public-surfaces.test.js` |

**Two things found on the way.**

1. The 14-day window (`event_date >= CURRENT_DATE - 14`) is gone from
   `v_fight_market_movement`, so a fight page older than a fortnight keeps its
   market history instead of rendering an empty panel. That closes half of
   T-040; `v_fight_odds_latest_by_book` still carries the window (T-040 stays
   open for it).
2. `fighter.html` kept its own naive `lastName`, so the next card's main event
   rendered as "2.6 pts toward **Jr.**" — Raul Rosas Jr.'s surname is Rosas. It
   now delegates to `fight-insights.js` like every other surface.

**Held back.** `v_fight_market_quotes` — the full per-book tick history — is
granted to no public role. It is the Pro asset (`PRODUCT_BOUNDARY.md`); the
aggregate views above it are owner-rights views, so no free surface is affected.

**Attribution note.** As D-006 through D-011: "Reed Cannon" per `CLAUDE.md`;
[T-009](TASK_QUEUE.md) stays the owner's.


---

## D-013 — Two model surfaces survived the repositioning, and one of them was an email subject

| field | value |
|---|---|
| date | 2026-09-21 |
| decided by | Reed Cannon (owner) |
| task | T-051, T-052 |
| level | L2 |
| reversible | the Prop Board change is (a banner, a `noindex`, a nav line — revertible in git, writes no row). The Brief is **not**: an email that goes out has gone out. It had not gone out under the new positioning, which is why this was worth catching first |

**Decision.** `props.html` becomes archived research, out of the nav and
`noindex`, on the same terms as the Model Archive: nothing deleted, everything
labelled. The Cannon Card Brief's subject line stops advertising picks.

**Why this exists as a separate entry.** D-011 removed the forecast from every
forward-facing surface and shipped a test that enforces it. Two things got
through, and the shape of both is worth recording:

1. **`props.html` was in the test's PRODUCT list and passed anyway.** It sells
   model output — "CFL's prop model projects significant strikes and takedowns
   for every fight on the next UFC card", in the meta description, the keywords,
   the OG description and the page lede — but it says *projection*, and the ban
   list was built from the vocabulary of the fight forecast. A guard written
   from one surface's words does not cover a second surface's synonyms. It is
   now in the ARCHIVE list with the rest of the model's history, and three new
   assertions check that an archived surface is `noindex`, carries its banner,
   and is not in the nav.

2. **The Brief's subject line read `"<Event> — model picks before the card"`.**
   Its body had been rewritten, its own footer said "We do not sell picks", and
   the string every subscriber reads without opening anything still sold picks.
   `build/send-digest.js` is on a weekly cron. A page with the wrong words is a
   page someone can read and fix; an email with the wrong words is already in an
   inbox. `tests/card-brief.test.js` now reads the subject lines specifically,
   on top of the body.

**What was NOT done.** `parlay.html` and `mybook.html` are out of the primary
journey and carry no model — `parlay.html` is a neutral calculator,
`mybook.html` a private bet-tracking utility whose Kelly sizing and edge column
D-011 already removed. Whether they stay reachable at all is a product call and
is **T-050**, the owner's, not a defect to fix quietly.

**Attribution note.** As D-006 through D-012.


---

## D-014 — The funnel counts, and counts nothing personal

| field | value |
|---|---|
| date | 2026-09-21 |
| decided by | Reed Cannon (owner) |
| task | T-047 |
| level | L1 |
| reversible | yes for the code (one emitter, revertible in git). The table is additive and prunable — `funnel_events` is deliberately **not** append-only in the `pre_fight_snapshots` sense, because these are counts, not evidence, and a retention prune must stay possible. It publishes no claim and changes no public copy |

**Plain version first, as CLAUDE.md requires.** The site starts counting,
anonymously, which pages people open and which things they click. A visitor sees
nothing new, no cookie is set, and no new third party is added. It matters
because CFL is about to build a paid tier and today cannot answer "did anyone
reach Card Lab" or "did anyone open a fight".

**Decision.** Nineteen event names, fifteen emitting. Two sinks: a
`funnel_events` table CFL owns, and the Plausible install that was already
there. The names live in three places — `cfl.EVENTS`, the database's CHECK
constraint, and `ANALYTICS_SCHEMA.md` — and a test fails if they drift.

**Three findings, and two of them were corrections to my own work.**

1. **Plausible was already installed on 25 of 30 root pages.**
   `ANALYTICS_SCHEMA.md`, written earlier the same day, implied no vendor
   existed. It was wrong. So the question was never "vendor or no vendor" but
   "add a second one", and the answer is no: Plausible receives the event **name
   only**, because custom properties are a paid feature and spending money is
   L3 — a props argument would have taken that decision by accident.

2. **`anon` held `UPDATE` and `DELETE` on the new table after applying.** Not
   from anything in the migration: a new table in `public` inherits broad grants
   from Supabase's default privileges. RLS denied both, so nothing was
   exploitable — but that is one layer doing the work of two, and it becomes
   zero the day someone adds a permissive `FOR ALL` policy. Revoked explicitly.
   **The check is what found it**; the migration's own prose claimed the right
   outcome and the database disagreed. Verify grants after applying, always.

3. **`privacy.html` does not name Plausible.** A third-party processor has been
   running on every page and the privacy policy does not disclose it. That is a
   compliance gap, not a preference. Privacy wording is gate 9, so it is
   **T-054** with draft text below rather than a quiet edit:

   > *Analytics.* We use Plausible Analytics to count page views and basic
   > interactions. Plausible is a third-party service that processes this data
   > on our behalf. It does not use cookies, does not collect personal
   > information, and does not track visitors across other websites. We also
   > record anonymous counts of which pages and features are used in our own
   > database; those records contain no email address, name, account identifier
   > or IP address.

   The second sentence is a factual description of what the code does and can be
   checked against `funnel_events_migration.sql`. Whether the wording is
   *sufficient* is the part that needs a lawyer.

**What is never collected, by construction.** `cfl.track` strips any prop key
matching email / name / user id / token / IP / phone / stake / amount / wager /
bankroll rather than trusting nineteen call sites to remember, caps string props
at 120 characters, and sends a per-session random `session_id` from
`sessionStorage` that is never joined to an account. The table enforces the same
shape: a bounded `props`, a bounded `session_id`, and a closed event list.
`card_brief_signup_completed` records **that** a signup happened and its source,
never the address — `tests/analytics-events.test.js` asserts an address cannot
reach the props under four different key spellings.

**Four events are declared and not emitted**, and this is deliberate rather than
unfinished: `best_price_clicked` (the best-price cell is not clickable, and
becomes so only behind T-049), `fight_shared` (no share control exists anywhere),
`checkout_started` and `checkout_completed` (no checkout exists). They are in
the list so the sprint that builds a checkout does not invent its own names.

**Also corrected here:** `CLAUDE.md` still documented `open_p_a`,
`books_at_open` and `market.js::openCaveat` as live, which D-012 retired hours
earlier. That is the file every future session reads first, so a stale entry
there is how a retired column gets reintroduced. It now describes the
matched-cohort rule and says explicitly that `open_p_a` must not return.

**Attribution note.** As D-006 through D-013.


---

## D-015 — Every market horizon on one matched-cohort rule

| field | value |
|---|---|
| date | 2026-09-21 |
| decided by | Reed Cannon (owner) |
| task | T-046 |
| level | L1 |
| reversible | yes — read-only views recreated by `market_horizon_views.sql`, one JS read path, tests. Writes no row, changes no append-only table, publishes no new claim |

**Plain version.** "The line moved" now means the same thing everywhere on the
site — comparing to last week, to yesterday, or to the moment a research
forecast was written down. In every case only the sportsbooks quoting at **both**
ends are compared, and below three of them we say we cannot tell.

**Decision.** The matched-cohort intersection lives in exactly one place,
`v_fight_market_horizon_cohorts`, and all three horizons aggregate it. Adding a
fourth horizon means adding a row to one CTE — there is no second copy of the
cohort logic to keep in step.

**Two things were still on the old footing, and one of them was mine.**

1. **`v_fight_market_at_lock`** compared a lock-time cohort against a current
   one. Of 14 fights with a lock: 4 had a different cohort at the two ends,
   **1 rested on a single book at lock**, and the worst disagreement against a
   matched cohort was **5.2 points**. `fight_week_views.sql` no longer defines
   it — two files defining one view is how the two drift, the same lesson
   `market_lab_views.sql` learned the same day.

2. **The 24-hour lookback inside `v_fight_market_movement` — which D-012 itself
   shipped — had exactly the defect D-012 was written to remove.**
   `market_p_a_24h` medianed every book with a quote at least 24 h old against
   every book quoting now. I fixed the baseline horizon and left the short one.
   Of 77 fights, 8 had a different cohort at the two ends and 2 fall below the
   three-book floor.

**Did any value materially change?** For the 24 h horizon, **no**: the worst
disagreement was **0.5 points**, under the 0.5 pt display threshold, so no
rendered figure moved. That is worth stating precisely rather than claiming a
fix that mattered more than it did — and it is worth writing down *why* it was
small. A day is short enough that a book quoting yesterday is almost always
quoting today. It is **not** small in the case that matters most: a book pulling
a market during fight week is exactly when someone is reading the 24 h column.
A defect that is currently harmless and structurally identical is still the
defect. For the lock horizon the change **is** material at 5.2 points, though
nothing public renders it.

**The baseline horizon is unchanged.** Verified against the live card fight by
fight: Vieira +7.0, Jackson +3.1, Rosas −2.6, Dumont −1.9, Bellato +1.8,
Amaya −0.8, all matching the ground-truth table from before this change.

**`market.js` no longer subtracts.** `move24h` reads `movement_pts_a_24h`
straight from SQL. Subtracting a matched-cohort median from an all-books median
would silently re-mix two cohorts inside the formatter, which is how this class
of defect survives a fix to the data layer.

**The lock horizon is kept, not removed.** The forecast is off every public
surface (D-011), so "since lock" answers a question about CFL rather than about
the product — it belongs to the research layer. D-011 is explicit that model
infrastructure is not deleted to tidy up, so it stays and is measured correctly.

**Attribution note.** As D-006 through D-014.


---

## D-016 — The chart draws one cohort, or it draws nothing

| field | value |
|---|---|
| date | 2026-09-21 |
| decided by | Reed Cannon (owner) |
| task | T-056, T-040, T-057 |
| level | L1 |
| reversible | yes — read-only views, one JS module, CSS, one new Fight Lab section. Writes no row, changes no append-only table, publishes no new claim about CFL's accuracy |

**Plain version.** The line on the chart is the middle sportsbook price over
time. Every point on it comes from the same sportsbooks. If a book starts
quoting halfway through, it does not join the line halfway through — a line
that gains a book shows a step no market actually made.

**Decision.** Four rules, and each is enforced in `market-chart.js` rather than
in the page, so a second surface cannot drift:

1. **One fixed cohort** for the whole plotted window — and it is *asserted in
   JS*, not trusted from SQL. If `cohort_books` is not identical on every
   point the chart is refused outright, with copy that says it is **our bug**,
   not a quiet market. A chart is the easiest place to hide a cohort change,
   so it is the place to check hardest.
2. **No interpolation.** The path is a **step** (`H`/`V` only — a test parses
   the emitted `d` attribute and fails on any line-to or curve command).
   Between its own quotes a book's price does not move, so the line holds flat
   and jumps. A diagonal would claim the price passed through values no book
   posted. Every x is a real capture instant; there is no synthetic time grid.
3. **Refuse rather than thin.** Below three matched books there is no
   consensus line — not a dashed one, not a shorter window, not a smaller
   cohort quietly substituted.
4. **The cohort size is on screen**, in the footer, not only in a tooltip.

**The cohort is not a new definition.** It *is* the `broad_baseline` matched
cohort from T-046. That fixes the window for free: the plot starts at
`baseline_at`, the instant a third sportsbook first priced the fight. Before
that there were fewer than three books, so there was never a defensible
consensus to draw.

**Per-book lines are exempt from rules 1 and 3** and use their own native
history — one book's quotes are observations, not an average. Rule 2 still
applies. A fight whose consensus is refused can still show its per-book lines,
and the SQL is shaped so that gate sits on the series view and not on the book
view.

**A 155x performance fix, found on the way (T-057).**
`v_fight_market_quotes` used `WITH q AS (...)` referenced twice — once per
side. A CTE referenced more than once is an **optimization fence** in Postgres:
it is materialised, so `WHERE fight_id = X` never pushes into it and every
reference re-scanned ~85k rows. One fight's series took **3,412 ms**. Rewritten
as a direct self-join with identical semantics and identical column order
(verified: 30,559 rows, 79 fights, unchanged), the same query takes **22 ms**.
Every market surface on the site gets that, not just the chart.

**What that fix does NOT buy.** Measured after it:

| query | cost |
|---|---|
| one fight, literal `fight_id` | 22 ms |
| twelve fights, literal `IN (...)` | 4,607 ms |
| `fight_id IN (SELECT ...)` | times out |
| whole view, no predicate | times out |

**`v_fight_chart_series` is a single-fight view.** That is why the chart lives
on Fight Lab, one fight to a page, and why **Market Lab has no per-row
sparkline** — a twelve-row board would cost 4.6 seconds. Card-wide charts need
a materialized view or a set-returning function, which is **T-058**, queued
rather than guessed at.

**T-040 closed.** `v_fight_odds_latest_by_book` carried
`event_date >= CURRENT_DATE - 14`, so a fight page older than a fortnight lost
its sportsbook table entirely — empty, with no error and no explanation. The
window is gone: **51 fights older than 14 days now have their detail back**,
the oldest event covered being 2026-05-30.

**Attribution note.** As D-006 through D-015.
