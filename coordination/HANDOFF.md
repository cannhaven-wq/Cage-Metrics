# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-18 (b) — review corrections: split PRs, id collision, gated evidence

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

- `FACTOR_EVIDENCE_2026-09-18.md` no longer licenses the `edges.html`
  correction. What it still licenses is narrower and still true: these ranges
  were never measured against the market at all, which is a provenance fact
  rather than a performance claim.
- `DRAFT_edges_correction_2026-09-18.md` carries a **DO NOT SHIP** header until
  T-024 runs, and its takedown-defence paragraph is weakened to match.
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

**Worth the owner's attention:** that branch also marks its T-010 `done` while
PR #22 is unmerged — the same mistake ChatGPT just corrected here. It is
another session's branch and was not edited from here.

### The branch is now four PRs, not one merge

| PR | what | risk |
|---|---|---|
| [#22](https://github.com/cannhaven-wq/Cage-Metrics/pull/22) | CI (owned by the other session; pytest pinned to 9.1.1) | none — adds one file |
| [#23](https://github.com/cannhaven-wq/Cage-Metrics/pull/23) | the homepage live/replay pooling defect | **changes a published number — gate #8** |
| #24 | coordination and audit documents | none — documents only |
| #25 | Proof Center nav + the explanation label | reversible UI |
| #26 | factor research (script, tests, evidence, drafts) | none — nothing applied |

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

**Owner:** merge in this order — #22 (CI, protects the rest), then #24 and #26
(documents only), then #25 (UI). **#23 is the one that needs a decision, not
just a review**: it changes what the homepage headline is computed from, the
number will move, and which record it should show is yours to pick. It is
currently set to the replay record, matching the "(simulated)" label already
beside it.

**ChatGPT:** two things. Whether the narrowed evidence artifact now states the
takedown-defence position correctly. And whether the replay record is the right
choice for the homepage headline, or whether both records should be shown at
their real sizes.

**Claude, when unblocked:** run `measure_edges_bands.js` with a service key,
commit `edges_bands_measured.json`, update §1 and §2 of the evidence artifact
with the gated result, and only then revisit T-025.

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
| 2 | CI running the whole test suite on push and PR | PR #22, **unmerged** |
| 3 | Proof Center in the nav and footer, with analytics (T-022) | `_shared.js`, `_shared.css`, `proof.html` |
| 4 | The matchup bullets labelled for what they are (T-023) | `fight-insights.js` + its three consumers |
| 5 | Replacement copy for the contradicted claims, **applied to nothing** | [`DRAFT_trust_copy_2026-09-18.md`](DRAFT_trust_copy_2026-09-18.md) |
| 6 | Factor evidence, partial, plus the script to finish it | [`research/factors/`](../research/factors/) |

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

> **Corrected by the 2026-09-18 (b) entry above.** The paragraph below claims
> the takedown-defence comparison "needed no new run". The bands match; the
> cohorts do not, because `factor-rates.js` applies no `willHaveWrestling()`
> gate. The 49.3% is evidence against the generic factor, not a test of the
> shipped rule. The original wording is left as written rather than rewritten.

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
- **T-025** — the dated correction to `edges.html`'s factor table, drafted at
  `research/factors/DRAFT_edges_correction_2026-09-18.md`. It can ship on the
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

**ChatGPT:** review `research/factors/FACTOR_EVIDENCE_2026-09-18.md` — in
particular whether the takedown-defence comparison is close enough to exact to
license the `edges.html` correction before the pending run, given that
`factor-rates.js` applies no `willHaveWrestling` gate and rebuilds the metric
point-in-time where `edges.js` reads the career figure.

**Claude, when unblocked:** run `measure_edges_bands.js` from an environment
with egress and a service key, commit
`research/factors/edges_bands_measured.json`, and update §2 of the evidence
artifact with the per-band record result.

---

## 2026-09-17 — consolidation: three merges landed, CLV-001 rebased and held

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-17

**No migration applied. No production write. No CLV published. No paid API call.**
No `fight_odds` row deleted or rewritten, here or anywhere. Every database call
made in this session was read-only.

### What landed

Consolidation in a fixed order, each step verified on the remote before the next
began — not merely committed locally.

| # | what | result |
|---|---|---|
| 1 | PR #14 — DUR-002's first collection | merged, `1a5cf890` |
| 2 | PR #15 — the `coordination/` layer | merged, `934721ba` |
| 3 | odds scrapper retirement | merged, `cage-metrics-odds-scrapper@af54180` (PR #1) |
| 4 | PR #16 — CLV-001 v1.0.10 | rebased onto the new `main`, **held unmerged** |

**Step 1** put DUR-002's 48 prospective observations on `main`. Verified before
merge: `lock_prop0002.py`'s sha256 on `main` is byte-identical to the value
recorded in `registry.json` and the register.

**Step 2** put the coordination layer on `main` and wired it into `CLAUDE.md`.

**Step 3** is the one that was only ever a branch. `backfill_odds.py` is now
retired on `main`: it imports `sys` alone, holds no write verb, and exits
non-zero. Confirmed before merge that no workflow and no `nixpacks.toml` start
command invokes it.

**Step 4** rebased 19 commits onto the new `main` with **zero conflicts**, and
confirmed the rebase did not revert DUR-002 to `armed` — both branches edit
`research/registry.json` and only that check rules it out.

### What I corrected in the rebase

The coordination records were written before steps 1–3 landed and had gone stale:

- `STATE.md` — DUR-002 read "**armed**, zero observations". Now collecting, 48
  rows on 12 fights. **This was the load-bearing one**: `STATE.md` is the file
  `CLAUDE.md` tells every session to read first, and nothing cross-checks it
  against the research register, so it would have gone on being wrong silently.
- `CRITICAL_GATES.md` — same stale assertion in the read-only clause.
- `TASK_QUEUE.md` — T-001 **dropped**. It asked to automate a one-shot
  transition that has now happened; automation for it has no remaining value.
  Reason recorded rather than deleted.
- `FIGHT_ODDS_WRITER_INVENTORY.md` — the retirement is merged, not a branch.

### The Railway service is still open, and it is a gate

The odds scrapper's README describes a **second Railway service** whose start
command was overridden to `backfill_odds.py`. Railway config is not in git and
this session holds no Railway credential, so it cannot be confirmed from here.

Measured instead, read-only, to bound the risk: the backfill's last write sits
at `fight_odds.id ≤ 384002`, and the rows written immediately after it captured
at **2026-05-26T23:02:20Z**. It has not written in nearly four months, and as of
`af54180` it cannot write if invoked. That shows the service has not *run*. It
cannot show it does not *exist*.

**`proposed_2026-09-16_fight_odds_immutability.sql` stays gated on the owner's
dashboard check.** The other four migrations are additive and not gated on it.

## Next action

**Owner:** remove or disable the second Railway backfill service, and confirm —
that closes the last precondition on the immutability migration. PR #16 is
rebased, green and waiting on your word to merge; it was deliberately not
merged in this session.

**ChatGPT:** the migration application plan, for five migrations applied
deliberately and sequentially. Every one is still unapplied.

---
