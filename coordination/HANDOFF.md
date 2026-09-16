# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

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

## 2026-09-16 — CLV-001 v1.0.5: tier 4 withdrawn, governor hole closed, ledgers sealed

**From:** Claude
**To:** Reed
**Date:** 2026-09-16

**No migration has been applied.** All three remain proposed and unapplied, as
instructed.

### 1. Tier 4 is withdrawn from scoring

You were right that it overreached. The argument held — a fight cannot begin
before its card does — but the conclusion did not follow: such a quote is safely
pre-fight and **not late**. Scoring it would have made the benchmark mean five
minutes before the bell on bout one and four hours before it on bout twelve,
both under one name. That is not a consistently measured benchmark.

`card_scheduled_start` is now **recognised and never scored**. A fight in that
state reports a new unscored reason, `only_pre_card_price`, kept distinct from
`no_scheduled_start` on purpose: "we hold a verifiably pre-fight price that is
not late enough" and "we hold nothing" are different problems with different
fixes, and collapsing them would hide which one is in front of you.

`LOWER_BOUND_REFERENCE_BASES` is now empty, with a test asserting it, so
re-admitting a bounded basis is a deliberate act that fails a test rather than a
quiet widening. The migration's constraint enforces the same thing at the
storage layer: a scored row cannot carry a lower-bound lead time.

**The cost, plainly:** scoring coverage returns to ~1 observation per card until
a running order and exact completions exist — on the order of 100 cards for 100
observations, not the ~8 I projected under Amendment 4. That is the price of a
consistent benchmark and it is recorded in the protocol, the migration and the
handoff rather than left implicit.

### 2. Capture is unchanged, and that is the point

Five-minute capture runs through the whole card and **every snapshot is stored**.
Nothing is discarded. The dense snapshots are exactly what makes a genuinely late
proxy available the moment a fight's start becomes verifiable — including
retrospectively, for cards already captured. The stored history is the asset; the
scoring rule is what stays strict.

### 3. The governor no longer has a hole in it

`planLiveCadence` used to fall through to the coarsest rung when nothing fitted,
which turned "we cannot afford any cadence" into "spend at 30 minutes anyway" —
and it did so exactly when the budget was tightest. It now returns **null / STOP**.

`test_when_NO_cadence_fits_the_budget_the_governor_returns_STOP_not_30_minutes`
is the specific test you asked for. It constructs a balance **above** the hard
floor — so the earlier guard cannot mask the result — and asserts the fixture is
genuinely one where even the coarsest rung is unaffordable before checking that
`planLiveCadence` returns null and `shouldCaptureNow` declines.

One branch still returns the coarsest rung without a fit check: an **unknown**
budget, on a fresh database or the first run of a month. That is not "the budget
says 30 does not fit", it is "the budget says nothing". I added
`the coarsest rung alone can never exhaust the allowance`, which walks months of
1 to 8 cards entirely at 30 minutes and proves the branch is safe by
construction rather than by hope.

### 4. The three ledgers are genuinely append-only

`fight_bout_order`, `fight_bout_completions` and `odds_api_usage` each get a
`BEFORE UPDATE` / `BEFORE DELETE` trigger that raises for **every role,
service_role included**, plus RLS enabled and `revoke all from anon,
authenticated` — the same shape as `fight_start_estimates`, `prop_odds`,
`prop_model_locks` and `pre_fight_snapshots`. RLS alone would not do it: the
scripts that write these hold service_role, which bypasses policies.

`odds_api_usage` matters most here. A quota reading that can be edited after the
fact is a budget that can be talked into allowing one more call, and one more
call past a free tier is paid usage.

### 5. Reschedules are read by `observed_at`, not `max(start_at)`

The `sched` CTE took `max(start_at)`, which breaks precisely when a card is moved
**earlier**: the superseded later time keeps winning, and a quote taken after the
new start still looks pre-fight. It is now `DISTINCT ON (event_id) … ORDER BY
observed_at DESC`, which takes what the provider most recently said and survives
a reschedule in either direction.

### Still true

Publication untouched and fail-closed — 100 observations, 20 distinct events,
interval excluding zero, currently 0 and 0. No paid tier, no incremental cost,
nothing bought or enabled. `v_fight_start_best` untouched.

Tests rerun: **105 CLV Python, 94 repo Python, 47 Node. All green.**

## Next action

**Reed:** review, then apply in order when you're ready —
`proposed_2026-09-16_fight_odds_capture.sql`,
`proposed_2026-09-16_event_flow.sql`, and
`proposed_2026-09-16_clv001_columns.sql` last.

Note the sequencing: `odds_api_usage` is created by the second migration, and
until it exists the governor reads the budget as unknown and holds at 30 minutes.
The 5-minute cadence starts when that migration lands.

The open L3 is unchanged: exact bout completions have no free source, and they
are now what makes bouts 2..N scorable at all.

---

*Older entries are in git history — the convention at the top of this file is
to keep the last three.*
