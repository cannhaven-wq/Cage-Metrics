# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-16 — CLV-001 v1.0.8: Amendment 5.1, four consistency fixes

**From:** Claude
**To:** Reed → ChatGPT review
**Date:** 2026-09-16

**No migration applied.** All three remain proposed and unapplied.

The v1.0.7 methodology is unchanged. These make the code, schema, view, tests and
documents agree with it.

### 1. No bell override inside this version

Amendment 5 admitted a confirmed bell "wherever one exists". Withdrawn. The
cutoff is **exactly two cases, always**: card scheduled start for bout 1, exact
previous-bout completion for bouts 2..N.

The reason it mattered: a bell override would silently make one version behave as
**two** — fights with a bell scored one way, fights without scored another,
inside the same summary statistic. A rule that depends on which optional field
happens to be populated is not frozen.

`bell_at` is retained as an audit field (`v_clv_close_reference.actual_bell_at`,
`fights.bell_at`) and never substituted for the cutoff. Scoring against real
bells is a **new protocol version**. `scoring.py`, `protocol.json`, the markdown,
the view, the tests and the comments all agree.

### 2. The cutoff is no longer dressed up as a start

`bout_started_at` was falling back to the previous bout's completion — asserting
that fight N+1 began the instant fight N ended. It did not; the walkout sits
between them, and that column's only job is to hold facts.

| field | now filled by |
|---|---|
| `fight_odds.bout_started_at` | a **confirmed bell**, nothing else |
| `fight_odds.is_live` | keyed to `bout_started_at`; `NULL` when unknown |
| `fight_odds.proxy_cutoff_at` | **new** — the frozen cutoff, under its own name |

CLV scoring excludes quotes at or after the cutoff **directly**, against the
cutoff. It never reads `is_live`, so no liveness fact is manufactured to achieve
an exclusion it can perform honestly.

### 3. Corrections resolve by observation, not by clock

`prev_done` used `max(completed_at)`. The ledger is append-only, so a correction
is a new row — and a correction usually moves the instant **earlier** (9:31
misheard, 9:30 confirmed). `max()` would keep returning the superseded 9:31
forever, leaving a minute of in-window quotes wrongly eligible.

Now `ORDER BY observed_at DESC, id DESC LIMIT 1`. **A correction from 9:31 to
9:30 resolves to 9:30.** The capture job uses the same ordering; the running-order
and card-schedule CTEs already did, and there are now tests for all three.

### 4. Tier-4 language gone

`protocol.json`'s `missing_inputs_for_tier_2` block — which still called exact
bout completions "an IMPROVEMENT rather than a prerequisite" and carried obsolete
Tier 4 coverage arithmetic — is replaced by `required_inputs`. Under Amendment 5
the previous bout's exact completion **is** the cutoff for bouts 2..N, so without
it those fights cannot be scored at all.

The remaining Tier-4 mentions are inside the superseded Amendment 4/4.1/4.2
records, which stay as filed — that is the audit trail, not live rule text.

### Files changed

| file | what |
|---|---|
| `cfl_engine/clv/scoring.py` | `bell_at` → `AUDIT_ONLY_BASES`; two-case cutoff; v1.0.8 |
| `cfl_engine/clv/test_scoring.py` | bell-override and lead-time tests rewritten |
| `cfl_engine/settle_clv.py` | `proxy_cutoff_at` in the capture probe; comments |
| `build/fetch-odds.js` | `proxyCutoffAt()` split out; `boutStartedAt()` bell-only; corrections by `observed_at` |
| `build/test-fetch-odds.js` | 10 tests for the cutoff/start split |
| `research/clv/CLV_MEASUREMENT_PROTOCOL.md` | Amendment 5.1; v1.0.8 |
| `research/clv/protocol.json` | `required_inputs` replaces the Tier-4 block; `bell_at_is_audit_only`; amendment 5.1 |
| `research/clv/proposed_2026-09-16_event_flow.sql` | no bell in `reference_at`; `observed_at DESC, id DESC` |
| `research/clv/proposed_2026-09-16_fight_odds_capture.sql` | `proxy_cutoff_at` column; corrected `bout_started_at` / `is_live` semantics |
| `tests/test_migrations_idempotent.py` | +7 tests: correction ordering, no bell override |
| `coordination/STATE.md`, `coordination/HANDOFF.md` | this |

### Tests

| suite | result |
|---|---|
| `tests/` (repo) | **109 passed**, 3 skipped |
| `cfl_engine/clv/` | **112 passed** |
| `build/test-fetch-odds.js` (Node) | **58 passed** |

All green. Hash chain verified across 8 amendments; publication gate confirmed
shut at 0 of 100 / 0 of 20.

### Preserved, as instructed

CFL closing-price proxy naming; full per-row provenance; the 500-credit governor
with its STOP condition and non-raisable ceiling; migration idempotency (15 tests);
append-only ledgers on all three tables; fail-closed publication.

### Remaining blockers

1. **Exact bout completions have no source** — now formally *required* for bouts
   2..N, not an improvement. The difference between ~1 and ~12.5 observations per
   card.
2. **Running order is not captured** — free to fix; without it nothing scores.
3. **Nothing is applied.**

### New L3 decisions required

**None new.** The bout-completions L3 is unchanged in substance and sharper in
framing: it is now a requirement rather than an accuracy improvement. The Odds
API allowance is untouched at the free 500.

## Next action

**ChatGPT:** review Amendment 5.1.

**Reed, after that:** apply in order — `..._fight_odds_capture.sql`,
`..._event_flow.sql`, `..._clv001_columns.sql`.

---

## 2026-09-16 — CLV-001 v1.0.7: the operational cutoff frozen, plus four implementation fixes

**From:** Claude
**To:** Reed → ChatGPT review
**Date:** 2026-09-16

**No migration applied.** All three remain proposed and unapplied.

### Amendment 5 — the operational cutoff, frozen

| | cutoff |
|---|---|
| bout 1 | the card's **scheduled start time** |
| bouts 2..N | the **exact completion of the immediately previous bout** |
| any bout with a confirmed bell | the **bell**, which outranks both |

Scored price = the latest eligible sportsbook snapshot **strictly before** that
cutoff.

This **supersedes Amendment 4.2**, which refused this cutoff because it precedes
the bell — and in doing so refused to score anything at all. Previous-bout
completion now has both its roles: this version's **scoring cutoff** and the
**capture trigger**. All "opener only, never a cutoff" language is gone from the
code, the view, the migrations and the protocol.

Named the **CFL closing-price proxy** (long form *late pre-fight closing-price
proxy*), never the exact sportsbook closing line. For later bouts it sits several
minutes before the bell; `clv_lead_time_is_lower_bound` marks exactly those rows
rather than hiding the gap.

Every scored observation preserves cutoff timestamp, cutoff basis, selected quote
timestamp, lead time to cutoff, source quote IDs and consensus provenance, and
protocol version — and the storage constraint requires all of them, so a figure
missing any is not writable. Reliable bell timestamps would be a **new protocol
version**; rows scored under this one are never reinterpreted.

### Fix 1 — the budget now actually declines

The real bug, and it was worse than cosmetic: clamping a 19,500-credit provider
balance to 500 on **every run** made the budget read 500 every time. It never
declined, the governor never degraded, and the ceiling was decorative.

Month-to-date spend is now the **sum of `odds_api_usage.credits_charged`** for
the current month — our own count, which nothing upstream can reset. The
provider's header is a cross-check and is believed only when **smaller** (it
catches calls we made but failed to log). The clamp stays as the second half.

A regression test pushes 40 calls through a 19,500-credit balance and asserts the
balance falls on every single one; another asserts a spent-out month reaches STOP
through our own count alone.

The 500 free allowance stays the ceiling. No paid tier assumed or enabled.

### Fix 2 — the migrations are genuinely re-runnable

Three files claimed idempotency while containing **13 bare `ADD CONSTRAINT`
statements**, each of which errors on a second run — so a routine re-apply would
have half-applied. All 13 are now wrapped in `DO` blocks that check
`pg_constraint` first. `tests/test_migrations_idempotent.py` (8 tests) enforces
it, including a check that a file *claiming* idempotency actually is, so the
claim and the reality cannot drift apart again.

One constraint was removed rather than guarded:
`model_edges_clv_window_opens_before_it_closes` asserted an ordering that
Amendment 5 inverts. `clv_lead_time_positive` already encodes the ordering that
matters.

### Fixes 3–5 — preserved

Append-only protections on all three ledgers are intact and now have their own
tests. Publication stays fail-closed at 0 of 100 / 0 of 20. Naming is the CFL
closing-price proxy throughout.

### Files changed

| file | what |
|---|---|
| `cfl_engine/clv/scoring.py` | Amendment 5 cutoff set, `PRECEDES_BELL_BASES`, new unscored reason, v1.0.7 |
| `cfl_engine/clv/test_scoring.py` | cutoff/lead-time/provenance tests rewritten |
| `cfl_engine/settle_clv.py` | `is_first_bout` threaded through; preflight text; `prev_bout_completed_at` |
| `build/fetch-odds.js` | `spentThisMonth`, `remainingCredits`, `credits_charged` recording |
| `build/test-fetch-odds.js` | 6 credit-accounting regression tests |
| `research/clv/CLV_MEASUREMENT_PROTOCOL.md` | Amendment 5; v1.0.7 |
| `research/clv/protocol.json` | amendment chain, benchmark naming, accounting note |
| `research/clv/proposed_2026-09-16_event_flow.sql` | view cutoff, `credits_charged`, DO blocks |
| `research/clv/proposed_2026-09-16_clv001_columns.sql` | basis vocabulary, constraints, DO blocks |
| `research/clv/proposed_2026-09-16_fight_odds_capture.sql` | DO blocks |
| `tests/test_migrations_idempotent.py` | **new** — 8 tests |
| `coordination/STATE.md`, `coordination/HANDOFF.md` | this |

### Tests

| suite | result |
|---|---|
| `tests/` (repo, incl. new migration tests) | **102 passed**, 3 skipped |
| `cfl_engine/clv/` (scoring + devig) | **111 passed** |
| `build/test-fetch-odds.js` (Node) | **60 passed** |

All green. Protocol hash chain verified across 7 amendments; publication gate
confirmed shut.

### Remaining blockers

1. **Exact bout completions have no source.** Under Amendment 5 these are the
   *scoring cutoff* for bouts 2..N, not just a trigger — so they are now the
   difference between ~1 and ~12.5 observations per card. This is the single
   highest-leverage open item.
2. **Running order is not captured.** Free to fix (ufcstats lists cards in
   order); without it no fight is identifiable as bout 1 and no bout has a
   "previous" one, so nothing scores at all.
3. **Nothing is applied.** Migrations wait on Reed. The 5-minute cadence starts
   when the event-flow migration lands, since `odds_api_usage` lives there.

### New L3 decisions required

**One, and it is the same one, now sharper:** where exact bout completion times
come from. Under Amendment 5 they are load-bearing for the metric rather than an
accuracy improvement. Options and costs are in
`research/clv/L3_ESCALATION_2026-09-16_bout_completions.md` — nothing has been
bought, priced or enabled. No other L3 is raised by this change; the Odds API
allowance is unchanged at the free 500.

## Next action

**ChatGPT:** review Amendment 5 and the four fixes.

**Reed, after that:** apply in order — `..._fight_odds_capture.sql`,
`..._event_flow.sql`, `..._clv001_columns.sql`.

---

## 2026-09-16 — CLV-001 v1.0.6: an opener is not a cutoff, and the allowance is hard-coded

**From:** Claude
**To:** Reed
**Date:** 2026-09-16

**No migration applied.** All three remain proposed and unapplied.

### The bug, and you were right about it

A pre-fight window has two ends and only one of them is the close. It **opens**
when the previous bout finishes — that is when the market starts pricing the next
fight in earnest, and when capture goes aggressive. It **closes** when *this*
fight starts.

Amendment 3 used the opener as the cutoff. Bout 4 ends at 9:30, bout 5 walks out
at 9:38 — taking 9:30 as bout 5's cutoff selects the last quote **before** 9:30, a
price quoted while bout 4 was still being fought, and throws away the eight
minutes that actually priced bout 5.

Worse, it made the five-minute capture self-defeating: the job would have
collected precisely the snapshots the scorer then discarded. The docs said "the
trigger is not the close"; the rule did not.

### What changed

| | |
|---|---|
| **scoring cutoffs** | `bell_at` (any bout), `scheduled_first_bout` (bout 1 only, where the card's start *is* this fight's start) |
| **window openers** | `previous_bout_completion`, `card_scheduled_start` — capture triggers, reported, never cutoffs |

`previous_bout_completion` is out of `CLOSE_REFERENCE_BASES` and out of
`v_clv_close_reference.reference_at`. A new `window_opens_at` column carries it
instead, so the snapshots taken inside the window stay identifiable and become
scorable **retrospectively** the moment a confirmed bell arrives — including on
cards already captured. The migration also constrains
`clv_window_opened_at <= clv_proxy_quoted_at`, so if a window ever closes before
it opens, that is this defect coming back and the database refuses it.

### The three unscorable states are now told apart

| reason | meaning | distance from scorable |
|---|---|---|
| `fight_start_unverified` | window opened, snapshots exist, nothing says where it closed | **one confirmed bell** |
| `only_pre_card_price` | only the card's scheduled start on file; hours early on a late bout | needs order *and* a bell |
| `no_scheduled_start` | nothing at all | furthest |

That distinction is the operationally useful one: it tells you exactly how many
observations a bell-time source would unlock, rather than lumping everything
under "no data".

**And nothing was manufactured to compensate.** Bouts 2..N stay unscored. Per
your instruction, no end-of-window marker was invented to raise coverage.

### The money safeguard

`ODDS_MONTHLY_CAP` can no longer widen anything. The approved allowance is a hard
constant:

- an environment variable may **lower** the cap, never raise it;
- it may **raise** the reserve, never lower it — lowering a reserve frees credits
  the governor was told to hold back, which is the same decision as raising the
  cap wearing a different hat;
- a **provider quota above the ceiling** is clamped and flagged, not spent. If
  someone attaches a paid plan upstream, the job treats the balance as 500 and
  says so. A larger quota is not authorisation.

Seven tests cover it, including one end-to-end: an inflated quota must not buy a
finer cadence than the real allowance would.

### Still true

Publication untouched and fail-closed — 0 of 100 observations, 0 of 20 events.
No paid tier, no incremental cost, nothing bought or enabled.
`v_fight_start_best` untouched.

Tests rerun: **108 CLV Python, 94 repo Python, 54 Node. All green.**

## Next action

**Reed:** review. When you're satisfied, apply in order —
`proposed_2026-09-16_fight_odds_capture.sql`,
`proposed_2026-09-16_event_flow.sql`, then
`proposed_2026-09-16_clv001_columns.sql` last.

Sequencing note unchanged: `odds_api_usage` is created by the second migration,
and until it exists the governor reads the budget as unknown and holds at 30
minutes. The 5-minute cadence starts when that lands.

The open L3 is now the whole remaining question for scoring coverage: a confirmed
bell time per fight is what turns `fight_start_unverified` into scored
observations, and the snapshots to score are already being collected.

---

*Older entries are in git history — the convention at the top of this file is
to keep the last three.*
