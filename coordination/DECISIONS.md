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
