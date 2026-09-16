# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

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

## 2026-09-16 — CLV-001 v1.0.4: the late pre-fight price proxy, and a credit governor

**From:** Claude
**To:** Reed
**Date:** 2026-09-16

### The timeline just moved from ~100 cards to ~20

That is what your decision bought, and it is worth putting first.

Tier 4 is the card's scheduled start used as a **lower bound**: a fight cannot
begin before its own card begins, so the last quote before the card's scheduled
start is **verifiably pre-fight for every fight on that card** — no running
order, no completion times, nothing new captured.

| | before | after |
|---|---|---|
| scorable observations per card | ~1 | ~12.5 (measured) |
| cards to reach 100 observations | ~100 | ~8 |
| cards to reach 20 distinct events | 20 | 20 |
| binding constraint | observation count | **event count** |

**Tier 4 bounds; it does not guess.** That is the line that keeps it admissible
where the event-date fallback is not. The fallback invents 18:00 UTC. Tier 4
uses a real published time and makes only the claim that time supports.

### Naming, as you specified

`BENCHMARK_NAME = "late pre-fight price proxy"`, long form *scheduled/late
closing-price proxy*. **Never "the closing line"** — there is a test asserting
the string contains "proxy", and the stored consensus artifact carries the name
so a row can never be read as something it is not.

Every scored row now carries `clv_close_basis`, `clv_lead_time_minutes`,
`clv_lead_time_is_lower_bound` and `clv_proxy_quoted_at`, and the migration's
completeness constraint **requires all four on a scored row**. A CLV figure
without its lead time is not writable, by construction. `lead_time_is_lower_bound`
is `null` when the basis is unknown — never `false`, which would assert the lead
time is exact.

### Five-minute capture, and the ceiling that makes it safe

The cron is now `*/5`. Every snapshot is stored with its exact timestamp.

**I need to flag the arithmetic, because it does not fit naively.** A card at
5-minute cadence costs ~123 credits. Measured event rate is 3.7 a month with 6 in
the busiest month observed. Six cards at 5 minutes plus daily baselines is well
past a 500-credit allowance — so a fixed 5-minute schedule would have broken the
free tier, silently, in a busy month.

So five minutes is the **target** and the ceiling is a **governor**: before each
call the job reads the provider's own `x-requests-remaining` header (persisted in
a new `odds_api_usage` ledger, because each Actions run is a fresh process),
counts the cards still to come this month, reserves each one's floor cost, and
takes the finest rung of 5 → 10 → 15 → 30 that fits. Below a hard floor it stops
rather than spending a credit that does not exist.

Two things I got wrong first and fixed, both caught by the month-walk test:

- dividing the balance evenly by cards remaining let the early cards of a busy
  month spend generously and left the last one short — it went **8 credits over**;
  now each card reserves the floor cost of every card after it;
- the projection counted only flow calls and not the card day's hourly tail,
  understating a card by ~15 — four cards' worth of that is a blown allowance.

The reserve is 75, not 45: walked across months of 1 to 8 cards, 45 goes over at
seven cards and 75 leaves a worst case of +19. The test asserts every month shape
from 1 to 8 cards fits.

**`FORCE` overrides the cadence, never the ceiling.** A hand-fired run was
bypassing the budget entirely — my gap, now closed. It can ignore the beat so a
manual check is never a silent skip; it cannot spend past the floor.

**Totals no longer ride every call.** They cost a second credit each time, which
at 5-minute cadence would double a card's bill. Capped at one totals call per 30
minutes — exactly the density DUR-001 already had, never less.

Degrading to 30 minutes still clears the frozen 45-minute staleness limit. **The
governor costs lead time and never correctness.** No paid tier, no incremental
cost, nothing bought or enabled.

### Previous-bout completion, as you framed it

Still useful, no longer required. It upgrades a later bout from a lower-bound
lead time to an exact one, and it still identifies event flow for the capture
window. The L3 doc is updated: **resolved as a blocker, open as an improvement.**
Doing nothing now costs precision, not the metric.

### What is still true

Publication untouched and fail-closed — 100 observations, 20 distinct events,
interval excluding zero, currently 0 and 0. Amendment 4 changes how fast
observations accumulate, never whether one may be shown.

Three migrations written, **none applied**. All additive-only. None touches
`v_fight_start_best`, which is in a frozen file serving DUR-001.

Tests: 105 CLV Python, 94 repo Python, 44 Node. All green.

## Next action

**Reed:** apply the migrations in order —
`proposed_2026-09-16_fight_odds_capture.sql`, then
`proposed_2026-09-16_event_flow.sql`. The second one creates `odds_api_usage`,
and until it exists the governor reads the budget as unknown and holds the
cadence at 30 minutes. That is safe but it is not what you asked for, so the
5-minute cadence only starts once that migration lands.

`proposed_2026-09-16_clv001_columns.sql` stays last, for after the first card is
captured.

I have not applied any migration, called The Odds API, written to Supabase, or
enabled any paid service.

---

*Older entries are in git history — the convention at the top of this file is
to keep the last three.*
