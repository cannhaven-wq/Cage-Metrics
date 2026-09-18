# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-18 (d) — T-027 diagnosed: the Factor Lab was reading the wrong rows

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-18

Measurement integrity only. No feature, no migration, no Event Flow, no public
factor copy.

### Root cause

`build/factor-rates.js` paged every read with `.range(from, from+999)` and no
`.order()`. Those are separate SQL statements, and Postgres does not promise the
same row order across them — so page n+1 was a window into a differently ordered
result. Rows near every boundary were dropped and others duplicated, and the
duplicates also skewed the median-across-books.

**The count still looked right**, which is why it survived: ~16,000 rows either
way, just not the same ~16,000.

### Why it is the odds read, and not a definitional difference

`factor-rates.json` records `fights_scored: 8739`; FE-001's independent SQL
counts the same 8,739. So `events`, `fights` and `fighters` all came back
complete. The market-even flag has exactly one further input — the `fight_odds`
array — and both sides use the same ±140 band, the same `is_closer` filter and
the same median rule. Same denominator, different numerator, one possible
cause.

`fight_odds` is also the only one of the four reads that is large **and**
filtered (~110k narrowed to ~16k over sixteen requests), which is where a
parallel scan can reorder, and the only one being written to while it runs.

### Fixed with keyset, not with `.order()`

Ordering alone fixes unstable order and leaves the concurrent-write race:
`fight_odds` is append-only and written every five minutes, so an insert ahead
of the cursor still shifts every later OFFSET page. Keyset paging defines a page
by data rather than position and survives both. `build/paginate.js`, with 10
regression assertions that need no network or key.

The paginator throws on a missing or non-unique key rather than returning a
short result — silent truncation is the bug being removed. Writing that guard
caught a real defect in the first version of the fix.

### The publish gate went in first

This was going to be the hard part: `prerender.yml` regenerated and committed
`factor-rates.json` every six hours, so merging the reader fix would have
performed a corrected run unattended and put the new verdicts on `stats.html`
with nobody having looked.

That route is closed. The Factor Lab is out of the scheduled job, and
regeneration is now
[`factor-rates-validate.yml`](../.github/workflows/factor-rates-validate.yml) —
manual, `contents: read`, produces a candidate artifact and a comparison, and
commits nothing. `tests/publish-gate.test.js` keeps it that way.

**Consequence:** `factor-rates.json` goes stale until someone refreshes it on
purpose. That is the right way round — a stale number that was reviewed beats a
fresh one that was not.

The rerun procedure and `build/compare-factor-rates.js` (which exits non-zero if
any verdict moved) are in
[`research/factors/T-027_PAGINATION.md`](../research/factors/T-027_PAGINATION.md).

### Not fixed, reported

The same OFFSET-without-order pattern is in `build/prerender.js:37`,
`build/send-digest.js:261` and `build/fetch-odds.js`. In `prerender.js` it would
show as missing or duplicated SEO stubs rather than a wrong number. Left alone
to keep T-027 scoped; `build/paginate.js` is there for whoever takes them.

## Next action

**Owner:** the comparison is in — see STATE.md and
[`T-027_PAGINATION.md`](../research/factors/T-027_PAGINATION.md). The cohort
corrects 869 → 1,220, matching FE-001 exactly, and 7 verdicts move. Nothing is
published; the candidate is a workflow artifact.

The decision is whether to publish, and it is **not** a routine refresh:
`ufc_record` becomes `real`, which is a new public performance claim, falsifies
`CLAUDE.md`'s "only age currently survives market control", and sits awkwardly
beside FE-001's finding that the *shipped* record factor is a coin flip — a
different factor with the same everyday name. Publishing well probably means
publishing the distinction too, not just the number.

**ChatGPT:** the diagnosis is in the document above. The part worth challenging
is the elimination argument — that an identical `fights_scored` on both sides
proves the other three reads were complete. If that holds, the cause is the odds
read alone; if it does not, the remaining gap needs its own investigation.

---

## 2026-09-18 (c) — consolidation: #24, #25 and #23 merged

**From:** Claude (integration / release)
**To:** Owner → ChatGPT
**Date:** 2026-09-18

Consolidating the four parallel PRs one at a time, CI verified after each.
This entry covers the first two merges; it will be superseded when #23 and
FE-001 land.

### Merged

| PR | merge | what |
|---|---|---|
| [#24](https://github.com/cannhaven-wq/Cage-Metrics/pull/24) | `46144c1e` | the audit, the trust-copy drafts, T-020..T-026, the FE-001 scope reset |
| [#25](https://github.com/cannhaven-wq/Cage-Metrics/pull/25) | `e91a7dab` | Proof Center in the nav, the matchup-context label — T-022 / T-023, [D-006](DECISIONS.md) |

Both green on `.github/workflows/tests.yml`: 624 Python passed, 4 skipped, and
every `tests/*.test.js`.

### One defect caught in consolidation

#25 changed `fight-insights.js` and left its cache-bust at `?v=6`. GitHub Pages
caches that file hard, so a returning visitor would have received the new
heading over the old script — `CONTEXT_NOTE` undefined, every consumer guarding
on it with a ternary, the explanation silently absent. That is the relabel
without the sentence that justifies it, which asserts *less* than the copy it
replaced. Bumped to `?v=7` on `index.html`, `event.html` and `fighter.html`
before the merge.

### #23 merged — and the number on the homepage moved

`b1bc881a`, under [D-007](DECISIONS.md). The owner chose the **replay** record,
matching the `(simulated)` label. The live record stays on the Proof Center.

Two defects, not one. The original: `loadHeroProof()` fetched with no `source`
filter, so the headline pooled the live feed and the history replay. The second,
found reviewing the fix: `assertOneRecord` ignores UNKNOWN, so a graded row whose
`source` resolved to no record passed the gate — and was counted anyway, because
the aggregate runs over the graded rows rather than over the rows the assertion
approved. Skipping a row in an assertion does not remove it from the arithmetic
after it. `headlineFromPicks` now calls `assertEveryRow` and fails closed.

The test file had pinned the second defect as correct
(`eq(h.n, 3, 'unknown rows are still graded rows')`), which is how it survived
the first review. Replaced by eight assertions, verified to bite.

### One conflict, resolved without loss

#23 and #25 both edit `index.html`'s script block — flagged when the PRs were
split, and made real by the `?v=7` cache-bust. Both kept: `proof-gates.js` loads
before the inline script that calls it, `fight-insights.js` keeps `?v=7`,
`_shared.js` stays at `?v=rd17`. Verified after the resolution that the page
still filters by `source`, still asks `headlineFromPicks` for the number, and
still carries #25's heading and `CONTEXT_NOTE`.

### Still open on this line

- **#26** — parked, to be closed as superseded by FE-001. Branch preserved.
- **FE-001** — to be opened as a PR against this `main`, reviewed as the sole
  authoritative factor-evidence artifact.
- **T-027** — the `build/factor-rates.js` paging finding, queued not fixed. It
  is a measurement change, not a one-line patch: the cohort size it would move
  is what every `stats.html` verdict rests on, so the fix needs a re-run with a
  service key and a stated before/after.

### Not touched, deliberately

No Event Flow activation, no migration applied, no production write, no
monetisation work. The trust-copy drafts (T-020 / T-021) remain applied to
nothing and remain the owner's.

## Next action

**Claude:** finish the sequence — #23, then close #26, then FE-001.

**ChatGPT:** three merged PRs are on `main` and reviewable there. Two questions
are worth your attention, and neither is inside them:

1. Whether the fail-closed rule now enforced in `headlineFromPicks` should also
   apply to `flatStakeLedger` and `straightRecord`, which still take
   `expectRecord` as an option and still use the permissive assertion. They feed
   Proof Center surfaces, so the same argument appears to apply; it has not been
   made.
2. **T-027.** FE-001 reports the published market-even cohort is ~30% short
   because `build/factor-rates.js` pages without an explicit order. If that
   holds, several `stats.html` verdicts move, and the re-run matters more than
   the one-line fix.

---

## 2026-09-18 (b) — review corrections, split PRs, and a scope reset

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-18

ChatGPT reviewed the branch and found two things wrong. Both are fixed here,
and one of them changes a conclusion.

### Correction 1 — branch-only work was marked shipped

T-022 and T-023 were marked `done` while existing only on
`claude/brave-cray-rssmll`, with no PR and nothing on `main`. They are
`in-progress` until their PR merges. Branch-only work is not shipped work.

### Correction 2 — the takedown-defence conclusion was overstated

This one matters more. The claim was that `factor-rates.json` bands takedown
defence at exactly `edges.js`'s own edges, so the comparison needed no new run.
The bands do match — 10, 20, 30 — but **the cohorts do not**. `edges.js` fires
its takedown-defence factor only when `willHaveWrestling()` is true, i.e. only
when somebody in the fight actually shoots. `factor-rates.js` applies no such
gate and scores every fight with a takedown-defence gap.

Same bands, different population. So 49.3% market-even is **evidence against
takedown defence as a general signal, not a measurement of the shipped rule.**
The same caution applies to record: the headline cohort is not a test of the
Laplace-smoothed 8 / 15 / 25 / 40 bands, which sit on a different quantity.

Consequences, all applied:

- The preliminary factor artifacts no longer license the `edges.html`
  correction, and the correction draft carries a **DO NOT SHIP** header. Both
  then moved out of this line entirely — see the scope reset below. What
  survives regardless of who measures: these ranges were never tested against
  the market at all, which is a provenance fact rather than a performance
  claim.
- Age: clearing 50% in isolation is not evidence of **incremental** value. The
  engine already carries age among its 49 covariates, so a standalone base rate
  says nothing about what reinstating the factor would add. That needs its own
  test and is not proposed.

### A task-id collision, and how it was resolved

A second session allocated **T-011 to a different task** on
`claude/brave-cray-rssmll-ci` while this session was using T-011 to T-016. Two
live meanings for one id is exactly what this repo's "ids are never reused"
rule exists to prevent.

This session's block moved to **T-020 to T-026**, leaving T-017 to T-019 as
deliberate slack against the race recurring. Nothing was deleted; the earlier
numbering never reached `main`.

**Worth the owner's attention, now resolved:** that branch marked its T-010
`done` while #22 was unmerged. #22 has since merged, so the row is accurate as
it stands and needs no change. On the rebase its T-011 was kept exactly as
written and this session's duplicate T-010 row was dropped.

### The branch is now four PRs, not one merge

| PR | what | risk |
|---|---|---|
| [#22](https://github.com/cannhaven-wq/Cage-Metrics/pull/22) | CI (other session; pytest pinned to 9.1.1) | **MERGED** `4f9d4a8` |
| [#23](https://github.com/cannhaven-wq/Cage-Metrics/pull/23) | the homepage live/replay pooling defect | **changes a published number — gate #8** |
| [#24](https://github.com/cannhaven-wq/Cage-Metrics/pull/24) | coordination and audit documents | none — documents only |
| [#25](https://github.com/cannhaven-wq/Cage-Metrics/pull/25) | Proof Center nav + the explanation label | reversible UI |
| [#26](https://github.com/cannhaven-wq/Cage-Metrics/pull/26) | preliminary factor research | **PARKED — do not merge**, see below |

### Scope reset, 2026-09-18

This line owns **product trust** and nothing else: #23, #24, #25.

Factor evidence moved to a dedicated workstream, **FE-001**, which has run the
deeper market-controlled analysis this line could not. #26 is parked unmerged
so there is **one** authoritative factor artifact rather than two competing
ones, and FE-001 decides whether anything in it survives.

Three distinctions have to survive that handover, because the first two were
got wrong once already in this session:

1. `factor-rates.json` matches `edges.js`'s 10/20/30 takedown-defence bands but
   applies **no `willHaveWrestling()` gate**. Any figure from it is evidence
   about the generic factor, never a measurement of the shipped rule.
2. It bands the **raw** record gap; `edges.js` bands a **Laplace-smoothed** one.
   Different quantities, so the headline cohort is not a band-level test.
3. Age clearing 50% standalone is **not** authority to reinstate it. The engine
   already carries age among its 49 covariates, so incremental value is a
   separate question with its own test.

T-024 and T-025 are re-pointed at FE-001 in the queue. T-025 stays the owner's
under gate #8 whoever supplies the evidence.

### The homepage defect, which is the real find

`loadHeroProof()` called `fetchEnginePicks()` with no `source` filter, so the
headline accuracy, the graded-fight count, the Lock rate and the trust tiles
were averages over the live feed and the history replay **pooled together** —
the operation `proof-gates.js` throws rather than perform, on the most
prominent number on the site.

Fixed by moving the arithmetic into `proof-gates.js::headlineFromPicks`, which
asserts one record before computing and requires the caller to name which one.
A filter alone would have let the page drift back. 16 regression assertions,
including a reconstruction of the original defect that throws for either
argument, and static checks that the page actually routes through it.

## Next action

**Owner:** #22 merged to `main` at `4f9d4a8`, so CI is live and every PR below
is checked by it. Three PRs are ready, all green:

- **#24** — documents only, no risk. Merge first; it is what the other two
  refer back to.
- **#25** — reversible UI. Proof Center into the nav, the matchup bullets
  labelled as context rather than as the model's reasoning.
- **#23** — **needs a decision, not just a review.** It changes what the
  homepage headline is computed from: today that number averages the live feed
  and the history replay together, and afterwards it is one record. The figure
  will move. It is set to the replay record, matching the "(simulated)" label
  already beside it; live-only, or both side by side, are the alternatives and
  the last is a layout change.

**#26 is parked and should not be merged.** FE-001 owns factor evidence and
will say whether any of it survives.

Still outstanding and unchanged: the trust-copy drafts in
`DRAFT_trust_copy_2026-09-18.md` (T-020, T-021) are applied to nothing, so
`index.html` keeps shipping "graded at real closing prices" in its meta
description until they are ruled on.

**ChatGPT:** whether the replay record is the right choice for the homepage
headline, or whether both records should be shown at their real sizes. That is
the one open design question in this line's scope.

**This line, next:** nothing new until #23, #24 and #25 are resolved. No
further factor work, no new model research.

---

## 2026-09-18 — CI: the test suite now actually runs, and it is bigger than `tests/`

**From:** Claude
**To:** ChatGPT → Owner
**Date:** 2026-09-18

**No migration applied. No production write. No CLV published. No paid API call.**
No `fight_odds` row read, deleted or rewritten. This session made no database
call of any kind and no network call beyond git, PyPI and the GitHub API.

### What landed

| # | what | where |
|---|---|---|
| 1 | `.github/workflows/tests.yml` — the whole suite on every push and pull request | T-010, **done** |
| 2 | the read-only audit that found the gap | [`reviews/2026-09-18-claude-ci-audit.md`](reviews/2026-09-18-claude-ci-audit.md) |
| 3 | the engine dependency set, unpinned and recorded rather than quietly widened | T-011, **queued** |

**The finding, in one line: seventeen test modules existed and no workflow ran
any of them.** The only test invoked anywhere in `.github/workflows/` was one
`unittest` module inside `event-flow.yml`. Everything passed; nothing was
checking. For a frozen-file hash check, a publication gate and the L3 gate, a
tripwire nobody pulls is decoration.

Measured on this commit: `624 passed, 4 skipped, 4557 subtests passed` for
Python, `31` and `40` for the two Node files.

### `tests/` was not the whole suite, and the first draft only ran `tests/`

The workflow's first draft ran `pytest tests/` and reported 168 passing tests.
The repo has **624 across seventeen modules**; the other 456 live under
`cfl_engine/` and `research/` and are the ones guarding the frozen model path —
`test_lock_prop0002.py`'s conformance proof that DUR-002 is collecting against,
the CLV-001 scorer, the event-flow card resolution, the integrity checks.

A green tick over an untested engine is worse than no tick, because people
believe it. The workflow now runs `pytest` from the repo root, which needs
`cfl_engine/requirements.txt` installed: three modules reach
`cfl_engine/engine.py`, which imports numpy and pandas at module scope, and
without the wheels eight tests fail on `ModuleNotFoundError` — a red suite that
is really a missing install.

### What ChatGPT's review corrected, and what it got

Four items came back on PR #22. All four are addressed:

1. **The T-010 claim was false when written.** The pull request said T-010 was
   tracked in `TASK_QUEUE.md` and it was not — `main` ended at T-009 and the
   branch did not touch the queue. Fixed by making the claim true rather than by
   deleting it: T-010 is now a row, with a note, and T-011 alongside it.
2. **The dated audit did not exist.** Now written, under the existing reviews
   convention.
3. **Stale base.** Rebased from `1e0c3d3` onto `0c89b21` (the prerender
   auto-commit), zero conflicts, the whole suite rerun green on the new base.
4. **Unpinned `pytest`.** Now `pytest==9.1.1`, the version the green run was made
   on. An unbounded install lets a runner-side change turn the build red with no
   repo change behind it, and a build that reddens for reasons nobody caused is a
   build people stop reading.

### Three claims in my own pull request text that were wrong

Worth listing, because two of them were safety claims and the third is the kind
of number `CLAUDE.md` says not to write down.

1. **"No network and no database."** Half right. `tests/test_sql_behaviour.py`
   *does* use a database — a throwaway cluster it builds itself with `initdb` on
   a unix socket in a temp directory, torn down afterwards, never reading
   `SUPABASE_DB_URL`, skipping where `initdb` is absent. `ubuntu-latest` ships
   PostgreSQL, so those tests run in CI rather than skipping.
2. **One test in the repo talks to production.**
   `cfl_engine/dur001/test_dur001.py` holds a test that posts SQL to the Supabase
   **management API** for the live project — carefully, as a DO block that rolls
   the whole transaction back, but it is a production write path, and the
   repo-root pytest run now contains it. It is gated on `SUPABASE_ACCESS_TOKEN`
   and this workflow passes no secrets, so it skips. **That is load-bearing.**
   Adding a secret to `tests.yml` would make every pull request, fork ones
   included, a production write. The workflow header now says so beside the
   reason `contents: read` is enough.
3. **A subtest count written as a constant.** The body quoted `4,237`; the count
   moves with the data the suites walk. It is now written as a dated reading.

The security claim survives (1) and (2) intact. The sentences carrying it did
not, and have been replaced with ones that are true.

### What was deliberately left alone

`cfl_engine/requirements.txt` carries `>=` ranges for all eight of pandas, numpy,
scikit-learn, scipy, statsmodels, pyarrow, xgboost and tabulate, and the CI job
installs it as written. So the suite can still go red on somebody else's release
— the same failure the `pytest` pin prevents, left standing on the larger half of
the dependency set.

Not fixed here on purpose: that file is the **engine's** manifest, shared with
the jobs that run the model. Narrowing it is a change to the engine's runtime,
not to CI, and it should land with a run behind it rather than as a line slipped
into a CI pull request. Likely a CI-only constraints file. **T-011**, queued, not
started.

`HANDOFF.md` was also trimmed to the last three entries, which is what the top of
this file has always instructed and what the previous two handoffs did not do.
Git history holds the rest.

## Next action

**ChatGPT:** T-011 — say whether the CI Python job should install from a
CI-only constraints file pinning the eight engine packages, or whether
`cfl_engine/requirements.txt` itself should be narrowed. The second choice
changes what the model runs on, which is why it is not mine to pick.

**Owner:** nothing new. The two live asks are unchanged and both predate this
session — remove or disable the second Railway backfill service (the last
precondition on the immutability migration), and T-009, which name the
governance records should carry.

---

## 2026-09-18 — audit, CI, and the first trust fixes

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-18

**No migration applied. No production write. No CLV published. No paid API
call. No public performance claim changed.** Every database call attempted in
this session was read-only, and all of them failed: the environment's network
policy blocks `*.supabase.co`, which is why T-024 is blocked below.

### What landed

| # | what | where |
|---|---|---|
| 1 | Read-only audit of the five active workstreams | [`AUDIT_2026-09-18.md`](AUDIT_2026-09-18.md) |
| 2 | CI running the whole test suite on push and PR | PR #22, **merged** `4f9d4a8` |
| 3 | Proof Center in the nav and footer, with analytics (T-022) | `_shared.js`, `_shared.css`, `proof.html` |
| 4 | The matchup bullets labelled for what they are (T-023) | `fight-insights.js` + its three consumers |
| 5 | Replacement copy for the contradicted claims, **applied to nothing** | [`DRAFT_trust_copy_2026-09-18.md`](DRAFT_trust_copy_2026-09-18.md) |
| 6 | Factor evidence, partial, plus the script to finish it | `research/factors/` — parked, see (b) |

### The three findings that matter

**Four public claims on `index.html` contradict artifacts in this repository.**
The worst is *"value flags graded at real closing prices"* — the claim CLV-001
exists to withhold — and it sits in the meta description, so it ships in every
share. The hero says *"Find where the betting line is wrong"* while
`benchmark_report.md` records the engine losing to the close at 0.6511 log-loss
against 0.5978. Replacement copy is drafted for every one of them; **nothing
public was edited**, because that is gate #8.

**The test suite ran nowhere.** 624 tests, 4,565 subtests and 71 JS assertions —
including the 24 conformance tests DUR-002 is collecting against and the
frozen-file hash register — all passing, and nothing pulled them. PR #22 fixes
it. My first draft of that workflow ran `pytest tests/` and reported 168 tests;
it undercounted by 456, and the second commit on the branch corrects it to run
from the repo root with the engine requirements installed.

> **Corrected and superseded by the 2026-09-18 (b) entry above.** Two things.
> The paragraph below claims the takedown-defence comparison "needed no new
> run": the bands match, the cohorts do not, because `factor-rates.js` applies
> no `willHaveWrestling()` gate — so 49.3% is evidence against the generic
> factor, not a test of the shipped rule. And the factor workstream has since
> moved to FE-001, so the `research/factors/` files this entry names are parked
> rather than merged. The original wording is left as written rather than
> rewritten; its links are de-linked because the paths are not on `main`.

**`edges.js` publishes two factor strengths with no artifact, and one of them is
now refuted.** `factor-rates.json` bands takedown defence at exactly `edges.js`'s
own edges, so that comparison needed no new run: in the 30+ band the page claims
56% and the market-even measurement is **44.6%**, interval 35.2–54.3 — the claim
sits outside it and the band is worse than a coin flip. Record's headline is
55.1% with an interval that still includes 50, which cannot support a published
72%. Age, which `edges.js` retired in May, is the only one of the three whose
interval clears 50.

### What is drafted and waiting, not done

- **T-020 / T-021** — the claims rewrite and the `Edge` representation. Exact
  before/after strings in `DRAFT_trust_copy_2026-09-18.md`. The owner's
  standing direction is recorded there: the `CLAUDE.md` rule is preserved and
  is not to be amended to keep the percentage UI.
- **T-025** — the dated correction to `edges.html`'s factor table, drafted in the
  parked factor branch. It can ship on the
  evidence already in hand; the pending run only sharpens one paragraph.
- **One finding the audit missed, now in the draft.** `loadHeroProof()` pools
  live and replay rows into the homepage headline accuracy with no `source`
  filter — the operation `proof-gates.js` throws rather than perform. That is a
  code fix, not a wording fix, and it should land before any copy moves.

### T-024 is blocked, and on what

The measurement script and 18 offline tests are written, and the tests are
verified to fail when the constants are tampered with. The run needs a service
key and egress to Supabase. Nothing about it is a decision — it is an
environment.

## Next action

**Owner:** two things, in this order.

1. **Merge PR #22** if the workflow reads right. It adds one file, changes no
   product behaviour, and it is the thing that protects everything after it.
2. **Rule on `DRAFT_trust_copy_2026-09-18.md`** — approve the wording, amend
   it, or reject it. Until then `index.html` keeps shipping "graded at real
   closing prices" in its meta description, and that is the one claim CLV-001
   was written to prevent. If only one item is approved today, make it C3, the
   pooled-record fix, which is a wrong number rather than a stale one.

**ChatGPT:** review the factor evidence artifact — in
particular whether the takedown-defence comparison is close enough to exact to
license the `edges.html` correction before the pending run, given that
`factor-rates.js` applies no `willHaveWrestling` gate and rebuilds the metric
point-in-time where `edges.js` reads the career figure.

**Claude, when unblocked:** run the band measurement from an environment
with egress and a service key, commit
its measured output, and update §2 of the evidence
artifact with the per-band record result.

---
