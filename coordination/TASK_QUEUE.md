# Task queue

What is queued, who owns it, and what level it sits at. One row per task.

**Levels** are defined in [`CRITICAL_GATES.md`](CRITICAL_GATES.md): `L0`
execute, `L1` AI-to-AI, `L2` proceed and notify, `L3` owner only.
**Owners**: `Claude` (build), `ChatGPT` (spec / review), `Owner` (Michael Cannon).
**Status**: `proposed`, `queued`, `in-progress`, `blocked`, `done`, `dropped`.

An `L3` task cannot be marked `done` until [`DECISIONS.md`](DECISIONS.md)
records the decision against its id. `tests/test_coordination.py` enforces it.

Ids are never reused. A task that dies is `dropped`, not deleted — the reason
it died is usually worth more than the task was.

---

## Open

| id | task | level | owner | status |
|---|---|---|---|---|
| T-002 | Individual votes on the nine held amendment clauses — (a) (b) (c) (d) (e) (f) (g) (j) (k) | L3 | Owner | blocked |
| T-003 | Review the CLV measurement protocol draft before freeze | L1 | ChatGPT | in-progress |
| T-004 | Collapse the `picks.html` → `card-lab.html` → `/` redirect to a single hop | L1 | Claude | queued |
| T-006 | Two-sided quote capture at the publish instant | L1 | Claude | queued |
| T-007 | Resolve the five L3 questions in the CLV protocol, then freeze it | L3 | Owner | blocked |
| T-009 | Confirm how the owner is named in the governance records — "Reed Cannon" or "Michael Cannon" | L3 | Owner | blocked |
| T-011 | Pin the CI Python dependency set — `cfl_engine/requirements.txt` is `>=` ranges, so the suite can redden on an upstream release | L1 | Claude | queued |
| T-020 | Replacement copy for the four contradicted public claims on `index.html` | L3 | Owner | blocked |
| T-021 | A model-vs-market representation that makes no unsupported edge claim | L3 | Owner | blocked |
| T-024 | Remeasure the exact `edges.js` record / td_def bands, and age, under market control — **owned by FE-001** | L1 | Claude | in-progress |
| T-025 | Dated correction to the `edges.html` factor table, once T-024 lands — **FE-001 supplies the evidence** | L3 | Owner | blocked |
| T-029 | Seed `odds_api_usage` from the provider's own `x-requests-remaining` before applying the event-flow migration — an empty ledger reads as "0 spent, 500 left" | L1 | Claude | queued |
| T-030 | Event Flow activation: produce `REAL_PAGE_CHECK.json` from a real UFCStats fetch, then uncomment the schedule | L1 | Claude | blocked |
| T-031 | Apply `proposed_2026-09-16_fight_odds_immutability.sql` — **between cards**, never during one | L3 | Owner | queued |
| T-032 | Retire a stale booking from the Event Flow observation instead of by hand, per `STALE_BOOKING_LIFECYCLE.md` §1 | L1 | Claude | queued |

## Closed

| id | task | level | owner | status |
|---|---|---|---|---|
| T-001 | Automate DUR-002's `armed → collecting` transition, guard-gated, with provenance recorded | L1 | Claude | dropped |
| T-005 | Build the `coordination/` layer and wire it into `CLAUDE.md` | L1 | Claude | done |
| T-008 | Draft the CLV measurement protocol | L1 | Claude | done |
| T-010 | Run the existing Python and JS test suites in CI, on push and pull request | L0 | Claude | done |
| T-022 | Proof Center into the nav and footer, with analytics | L2 | Claude | done |
| T-023 | Label the explanation layer as matchup context, not model internals | L2 | Claude | done |
| T-026 | Stop the homepage headline pooling the live and replay records | L3 | Owner | done |
| T-027 | Settle the unordered `.range()` paging in `build/factor-rates.js`, and publish the corrected cohort | L3 | Owner | done |
| T-028 | UFC 331 launch activation — apply the additive capture migrations, reconcile the card | L3 | Owner | done |

---

## Notes on the open rows

**T-009** is attribution, which is the one thing an append-only log exists to
get right. The records name the owner two ways: `protocol.json` resolves Q-14 by
**"Reed Cannon"** and `CLAUDE.md` names the owner that way, while
[D-004](DECISIONS.md) records **"Michael Cannon (owner)"**; both appear across
`STATE.md`, `HANDOFF.md` and the protocol document.

Whether that is one person recorded two ways or a genuine mis-attribution is
**not** something Claude or ChatGPT may settle by inference — which is why
nothing has been normalised and every entry still reads exactly as it was
written. L3 and blocked on the owner. The fix is a new `DECISIONS.md` entry
stating which name is correct, never an edit to the existing ones.

**T-002** is the live bottleneck on DUR-001's specification. The clauses are not
approved en bloc and are split by risk in the register. Six of them change data
eligibility, scoring, model behaviour or interpretation; three are governance
only. The three low-risk ones could move first if the owner wants to clear the
backlog without touching anything that affects a result.

**T-003** is with ChatGPT now. The draft is
[`research/clv/CLV_MEASUREMENT_PROTOCOL.md`](../research/clv/CLV_MEASUREMENT_PROTOCOL.md);
the review checklist is §7. Twelve decided rules, eleven open questions. It is a
**measurement protocol, not an experiment** — no hypothesis, no challenger, no
verdict, so it stays out of the DUR register.

**T-004** is small and self-contained, and is named in `CLAUDE.md` as worth
doing. Good filler when a larger line is blocked.

**T-006** is urgent in a way its size hides. Q-05's de-vigged variant needs both
sides of the market captured at the publish instant, and that can never be
backfilled — every card that goes by without it is permanently unavailable to
that definition. It does not wait on the protocol freeze, because capturing more
than you end up needing costs nothing and capturing less is irreversible.

**T-011** is what T-010 left unpinned. `tests.yml` pins its runner exactly
(`pytest==9.1.1`) but installs `cfl_engine/requirements.txt` as written, and that
file carries `>=` ranges for pandas, numpy, scikit-learn, scipy, statsmodels,
pyarrow, xgboost and tabulate. So the suite can go red on somebody else's
release, with no change in this repo behind it — the exact failure the pytest pin
exists to prevent, left standing on the larger half of the dependency set.

It was not fixed inside T-010 because `requirements.txt` is the **engine's** own
manifest, shared with the jobs that actually run the model. Pinning it is a
change to the engine's runtime, not to CI, and it deserves a deliberate run
rather than a line slipped into a CI pull request. The likely shape is a
CI-only constraints file rather than narrowing the manifest, so the engine keeps
its ranges and the test job stops floating.

**T-007** is the freeze. Five questions need the owner: Q-05 (vigged or de-vigged),
Q-06 (published probability or wager price), Q-07 (aggregation and weighting),
Q-08 (minimum sample), Q-11 (how it may be described). Each changes what a
published number means. It is blocked behind T-003 — ChatGPT reviews the
methodology first, so the questions reaching the owner have been through a
statistician.


**T-010 to T-026 come out of the 2026-09-18 read-only audit**
([`AUDIT_2026-09-18.md`](AUDIT_2026-09-18.md)). Three are the owner's.

**T-010** is the one with the best ratio of value to risk in the whole audit.
Seven test files — 168 tests, 4,227 subtests and 71 JS assertions — guard the
frozen-file hashes, the CLV publication gate, the proof-gate record separation
and the coordination invariants. They all pass. Nothing runs them: only
`event-flow.yml` invokes a single unittest module. A frozen hash could drift on
`main` and no gate would notice.

**T-020 and T-021 are L3 because of gate #8**, not because the finding is
debatable. Four public claims on `index.html` contradict artifacts in this
repository — including "graded at real closing prices", which is exactly the
claim CLV-001 exists to withhold. Replacement copy is drafted and no public
claim has been edited. What needs the owner is the wording that ships, not
whether the current wording is wrong.

**T-021 carries a standing direction** from the owner, 2026-09-18: the
governance rule in `CLAUDE.md` is preserved, and `CLAUDE.md` is **not** to be
amended merely to keep the percentage UI. The replacement must express the
model-versus-market comparison without asserting an edge the evidence does not
support.

**T-022 and T-023 are L2** — reversible, publish no new number, and T-023 can
only narrow what the page asserts. Proceed and notify.

**Ids T-020 to T-026 were renumbered on 2026-09-18, and the reason matters.**
They were first allocated as T-011 to T-016. While this session was working, a
second session allocated **T-011 to a different task** on the
`claude/brave-cray-rssmll-ci` branch. Two live meanings for one id in an
append-only log is the failure this file's "ids are never reused" rule exists
to prevent, so this session's block moved up and out of the way rather than
contest it. The gap from T-017 to T-019 is deliberate slack against the same
race happening again. Nothing was deleted: T-011 as used here never reached
`main`.

**T-022 and T-023 shipped 2026-09-18** in
[#25](https://github.com/cannhaven-wq/Cage-Metrics/pull/25), merged to `main`
at `e91a7da`. They were briefly marked `done` while existing only on a branch,
which was wrong — branch-only work is not shipped work — and they stayed
`in-progress` until the merge. Recorded as [D-006](DECISIONS.md).

The merge carried one addition found during consolidation: `fight-insights.js`
was changed without bumping its `?v=6` cache-bust, so a returning visitor would
have received the new heading over a cached script with no `CONTEXT_NOTE` — the
new heading with its explanation silently missing, which asserts less than the
copy it replaced. Bumped to `?v=7` on all three consumers before merge.

**T-026 shipped 2026-09-18** in
[#23](https://github.com/cannhaven-wq/Cage-Metrics/pull/23), merged to `main` at
`b1bc881a`, under [D-007](DECISIONS.md). It was L3 because it changes a
published number, not because the defect was arguable: the headline was computed
over the live and replay records pooled together, the fix computes it over one,
and **the number moves**. The owner chose the replay record, matching the
`(simulated)` label already beside it.

It also carries a second fix found reviewing the first. `assertOneRecord`
ignores UNKNOWN, so a graded row whose `source` resolved to no record passed the
gate and was then counted anyway — the aggregate runs over the graded rows, not
over the rows the assertion approved. `headlineFromPicks` now fails closed via
`assertEveryRow`. `flatStakeLedger` and `straightRecord` still use the
permissive assertion; extending it to them is open and named in the handoff.

**T-024 and T-025 moved out of this line on 2026-09-18.** A dedicated
factor-evidence workstream (**FE-001**) now owns the exact market-controlled
measurement and has run it; this line's preliminary work is parked rather than
merged, so there is one authoritative factor artifact instead of two competing
ones. Nothing about the finding changed — `edges.js` publishes 60–72% for a
record gap and 52–56% for takedown defence, and neither range traces to an
artifact — only who establishes the replacement numbers.

**The distinction that must survive the handover**, because it is the one that
was got wrong once already: `factor-rates.json` matches `edges.js`'s 10/20/30
takedown-defence bands but applies **no `willHaveWrestling()` gate**, and it
bands the **raw** record gap where `edges.js` bands a **Laplace-smoothed** one.
So any figure taken from it is evidence about the generic factor, never a
measurement of the shipped rule. Age clearing 50% standalone is likewise not
authority to reinstate it: the engine already carries age among its 49
covariates, so incremental value is a separate question.

**T-025 stays the owner's** under gate #8 whoever supplies the evidence.

**T-027 is diagnosed and fixed in code; it became L3 on the way.** See
[`research/factors/T-027_PAGINATION.md`](../research/factors/T-027_PAGINATION.md).

`build/factor-rates.js` paged every read with `.range()` and no `.order()` —
separate statements whose row order Postgres does not fix, so pages overlapped
and skipped. The evidence localises the loss to the `fight_odds` read alone:
`fights_scored` is 8,739 in both the published artifact and FE-001's independent
SQL, so the other three reads came back complete, and the market-even flag has
no other input. Replaced with keyset paging (`build/paginate.js`), which also
survives the concurrent writes `fight_odds` takes every five minutes; ordering
alone would not.

**It is L3, and the owner's, because a corrected run moves published
verdicts.** It was briefly worse than that: `prerender.yml` regenerated and
committed `factor-rates.json` every six hours, so merging the reader fix would
have performed and published a corrected run unattended. That route is closed —
the Factor Lab is out of the cron, and regeneration is now a manual workflow
running under `contents: read` that commits nothing.

So the remaining decision is narrower and cleaner: run the validation workflow,
read the comparison, and decide whether to publish the candidate. Publishing is
a deliberate commit of `factor-rates.json` in a pull request where the moved
verdicts show in the diff. The procedure is in the document above.

**T-027 closed 2026-09-18** under [D-008](DECISIONS.md), PR #34 at `f40fd27c`.
869 → 1,220, matching FE-001 exactly; the `fights_scored` control held at 8,739;
seven verdicts moved, one downward. The artifact published is the byte-verified
candidate (sha256 `ba3c9077…`), alongside the copy that keeps it honest —
`ufc_record` clearing the bar is **not** evidence for `edges.js`'s record
factor, and the displayed name is now "UFC-only record" so the one-line summary
says which record it means without relying on a caveat above it.
`tests/record-factors-distinct.test.js` stops that drifting back.

**What T-027 did not settle, deliberately:** the shipped `edges.js` record and
takedown-defence heuristics are still unsupported and still shipped. That is the
next product question and it is not a consequence of this one.

Deliberately excluded from the 2026-09-18 consolidation, which was merging
finished work rather than opening new lines.

---

## Notes on the closed rows

**T-010 — done 2026-09-18.** The repo had seventeen test modules and no workflow
that ran them; the only test invoked anywhere in `.github/workflows/` was a
single `unittest` module inside `event-flow.yml`. `.github/workflows/tests.yml`
now runs the whole suite on every push and pull request — `pytest` from the repo
root, not `pytest tests/`, so `cfl_engine/` and `research/` are in it too. 624
Python tests and two Node files, against the 168 the first draft of the workflow
would have covered.

It is **L0**, not L1: it adds no feature, asserts nothing new, and changes no
product behaviour — it pulls tripwires that were already built. What it buys is
that the frozen-file hash check, the CLV publication gate, the L3 gate and
`test_lock_prop0002.py`'s conformance proof stop depending on somebody
remembering to run them. For a gate, that is the difference between a guard and
a note.

The audit that found it is
[`reviews/2026-09-18-claude-ci-audit.md`](reviews/2026-09-18-claude-ci-audit.md).
The one thing it did not settle is **T-011**, above.

---

## Why T-001 was dropped

**T-001 — dropped 2026-09-17, not built.** It asked for automation of DUR-002's
`armed → collecting` transition. That transition is a **one-shot**: DUR-002
crosses it exactly once, and it has now crossed it. It was performed manually
and is on `main` — first lock 2026-09-16T01:29:00Z, 48 rows across 12 fights,
`lock_prop0002.py` frozen into DUR-002's frozen files, full guards rerun green.

Automation for an event that has already happened and cannot recur has no
remaining value. The task is dropped rather than deleted because the reasoning
is worth more than the task was: the *shape* of the work — detect first row,
record provenance, freeze the script, rerun guards, and **stop if any guard
fails** — is the template for the next experiment that arms, and D-002's
classification of it as L1 execution rather than an L3 decision still stands.

---

## The UFC 331 launch block (T-028 to T-032)

**T-028 — done 2026-09-19** under [D-009](DECISIONS.md). It is L3 because it
applies production migrations (gate #5), not because any step was arguable.

The finding that made it urgent rather than routine: **the odds job had captured
nothing on a card day.** `.github/workflows/odds.yml` wakes on `*/5`, and every
cadence tier gated on the wall clock — `min % cadence < WAKE_INTERVAL_MIN`.
That is equivalent to a cadence only if the cron really fires every five
minutes. GitHub throttles a `*/5` schedule to a handful of deliveries a day at
arbitrary minutes: on 2026-09-19 they landed at :43, :30, :35 and :35, never
once inside minutes 0–4. So the gate never opened, and the only UFC 331
moneyline rows on file that morning came from another writer.

Fixed in `build/fetch-odds.js` by measuring **elapsed time since our own last
capture** instead of the clock's phase, falling back to the phase test whenever
the last capture is unreadable — so a missing ledger degrades to the old
behaviour and never to "capture every wake". Seven regression tests, two of them
mutation-checked, including a replay of the four real wakes. Simulated against
tonight's card the same throttled wakes yield **10 captures instead of 1**.

**T-029** is the reason the event-flow migration did not go with it. It creates
`odds_api_usage` empty, and `remainingCredits([], undefined)` returns the full
500 — so the governor would read "nothing spent this month", which is false, and
take the finest rung. Seed the ledger from the provider's own
`x-requests-remaining` on a capture first; then the migration is safe.

**T-030** is blocked on the environment, not on a decision. `--execute` refuses
until `cfl_engine/event_flow/REAL_PAGE_CHECK.json` exists, and it cannot be
produced from CI or from an agent session: UFCStats answers 403 to both.

**T-031** carries its own timing rule. It adds triggers to `fight_odds` while
another repository writes to it, so it lands **between cards**. D-004 already
records that it is the owner's to apply.

**T-032** is the principled version of what T-028 did by hand. 47328 was retired
from three independent observations, but `STALE_BOOKING_LIFECYCLE.md` §1 wants
the retirement to fall out of `plan_append`'s `stale_fights` automatically. That
needs T-030 first.
