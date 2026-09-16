# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

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

## 2026-09-16 — CLV-001 v1.0.3: the event-flow rule, and one L3 back to you

**From:** Claude
**To:** Reed
**Date:** 2026-09-16

### What your decision fixed

Amendment 2 (b), frozen an hour earlier, admitted `provider_commence` — the
card-level commence time — as the close reference for **every** fight on the
card. Your rule makes that right for one fight in thirteen and wrong for the
rest, which is what it always was.

Wrong in the expensive direction, too. Keyed to the card's commence time,
`is_live` would have marked **every quote taken after the first bell as in-play
for all thirteen fights** — discarding exactly the quotes the later fights close
on. Caught before a single such quote exists, because none of this is applied.

### Amendment 3, as implemented

**The close reference, per fight:**

| tier | basis | applies to |
|---|---|---|
| 1 | actual confirmed bell | any bout |
| 2 | the previous bout's **exact** completion | any bout after the first |
| 3 | the card's scheduled start | **the first bout only** |
| — | anything else | nothing — the fight is unscored |

A fight whose running order is unknown has no admissible reference at all:
without an order there is no "previous bout", and no fight can be identified as
the card's first. `is_first_bout` is `None` in that state and `None` is not a
yes — there is a test named for it.

**The trigger is not the close.** Your distinction, encoded in three places so it
cannot be collapsed by accident: the previous bout ending starts the 30-minute
capture window and governs only how much data exists; the close is the last valid
pre-live quote for the upcoming fight, and any quote at or after that fight
started is excluded, strictly. Four tests under `TestTriggerIsNotTheClose`,
including one that proves a late-card fight's quotes — which only exist *because*
the trigger fired — still score.

**The audit field stays separate.** `fights.bell_at` remains the record of when a
fight actually began, reserved for a confirmed bell and never written by the odds
job. `fight_odds.bout_started_at` is a different thing: the capture-time *belief*,
stamped per quote so the close a quote was judged against stays recoverable if a
better account arrives later. A correction to one never rewrites the other.

**Capture.** `odds.yml` wakes every 15 minutes; a card is "in flow" from 3h
before its scheduled start until every bout has an exact completion or 7h passes,
and capture runs every 30 minutes throughout. Previously the window was anchored
to the single published commence time, which would have given bout 1 a fresh
quote and left the other twelve closing on a line hours stale.

**No spend increase.** Still ~33 credits on a card day, ~286/month, inside the
500 free tier — the test asserts the ceiling. So nothing to escalate for the
cadence itself.

`v_fight_start_best` is untouched. It lives in `dur001_migration.sql`, a frozen
file serving a running experiment, so CLV-001 got its own `v_clv_close_reference`
rather than a `create or replace` on DUR-001's view.

### The L3 back to you

[`L3_ESCALATION_2026-09-16_bout_completions.md`](../research/clv/L3_ESCALATION_2026-09-16_bout_completions.md).
**Nothing has been bought, priced, signed up for or enabled.**

Tier 2 needs two things the database does not have:

- **Running order** — `fights` has no order column, only `is_main_event` (the
  last bout). Sorting by id would be an inference dressed as a record, and it
  breaks exactly when a card is reshuffled. **Free to fix**: ufcstats lists a
  card in order and the event scraper can write `fight_bout_order` on the pass it
  already makes. No L3 needed.
- **Exact bout completions** — nothing records when a bout ended, and the result
  scraper cannot stand in. It gives *completion plus unknown lag*: an upper
  bound, and used as the next bout's start it would admit in-play prices as that
  fight's close, invisibly. `is_exact = false` marks such rows and the view
  ignores them.

Options are A do nothing (bout 1 only), B manual entry during the card, C a paid
live feed, D derive it from market disappearance. **I did not implement D**,
though it is free and uses data the new capture already produces — "the market
disappeared" is not "the fight started", and adding a new measurement definition
to a protocol frozen this morning, to relieve a coverage problem I reported this
afternoon, is the move the freeze exists to stop. It is a fresh L3 if you want it.

**Recommendation: take the free half now, decide the paid half later.** Populate
`fight_bout_order`, let a few cards of real coverage accumulate, then decide with
a real count in front of you rather than my estimate.

### The number that matters most

Until exact completions exist, **only the first bout of each card is scorable** —
about one observation per event, against a floor of 100 across 20 distinct
events. That is roughly 100 cards. It is the single biggest fact about the CLV
timeline and it is now recorded in the protocol, the migration and the preflight
rather than living in my head.

### Publication

Untouched and fail-closed. 0 of 100 observations, 0 of 20 events, still blocked
on `sample_floor_met` and `interval_excludes_zero`. Nothing in Amendment 3 moves
it — it changes how fast observations accumulate, never whether one may be shown.

Tests: 93 CLV Python, 94 repo Python, 36 Node. All green.

## Next action

**Reed:** two things, independent of each other.

1. **Answer the L3** on bout completions — or say "A for now", which is a
   complete answer and needs nothing built.
2. **Apply `proposed_2026-09-16_fight_odds_capture.sql`**, then
   `proposed_2026-09-16_event_flow.sql`. Both additive-only, both unapplied.
   Every card that passes before they land is permanently unscorable.

I have not applied any migration, called The Odds API, written to Supabase, or
enabled any paid service.

---

*Older entries are in git history — the convention at the top of this file is
to keep the last three.*
