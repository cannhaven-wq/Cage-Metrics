# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

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

## 2026-09-16 — CLV-001 v1.0.2: book list frozen, capture path written and verified, nothing applied

**From:** Claude
**To:** Reed
**Date:** 2026-09-16

### First, a correction to what I gave you an hour ago

**The dry run said the scheduled-start mechanism did not exist. It does, and I
missed it.** I checked `fights.bell_at` (0 of 8,994) and `events` (a DATE, no
time) and stopped. I did not check for a start-time ledger, and there is one:
**`fight_start_estimates` + `v_fight_start_best`**, shipped in
`dur001_migration.sql`, collecting provider commence times since 2026-09-14 and
already resolving 16 future fights.

The 47 rows still fail — every settled card resolves to the event-date fallback,
because the ledger started after them. But "the field does not exist" implies
building something, and "the ledger started collecting two days ago" implies
waiting one card. The second is true, and it is a materially better position than
I reported. Correction is at the top of `DRY_RUN_2026-09-16.md`.

The same sweep found `v_odds_books_sportsbooks`, also from DUR-001, which already
encodes the sportsbook / aggregate / prediction-market split — and it turned out
to be the right answer to the book-list question below.

### 1. The eligible book list is frozen — Amendment 2 (a)

Ten sportsbooks: FanDuel, DraftKings, BetMGM, Caesars, BetRivers, BetWay, Unibet,
BetOnline.ag, Bovada, BetUS. v1.0.1 → v1.0.2, chain `c2e3f5aa…` → `06fa587a…`.

**Where the list came from matters more than its contents.** It is the membership
of `v_odds_books_sportsbooks` — a view written for the **totals** market *before
CLV-001 existed*, defined as every book whose name does not contain "consensus"
and is not Polymarket or Kalshi. It was not assembled by looking at which books
would suit a CLV number; it was already in the repo, under a rule anyone can
read. That is better provenance than anything I could have composed today.

Two facts make `motivated_by_observed_results: false` checkable rather than
merely asserted here: no CLV figure has ever been computed, and the dry run
establishes none is computable on the present record.

**Coverage was deliberately not a criterion.** Caesars, BetWay and Unibet have not
appeared in the feed since 2026-05-31 and are on the list anyway. Dropping a book
for thin coverage is a judgement about which prices count, made now, and it is
exactly what freezing forecloses. A book that never quotes never enters a
consensus, which costs nothing.

### 2. A second amendment part you did not ask for, and I think you need

**Amendment 2 (b): only `bell_at` and `provider_commence` count as a scheduled
start. The event-date fallback does not.**

`v_fight_start_best` *always* answers — it falls back to the event date at 18:00
UTC. Reading `start_at` without reading `start_basis` therefore hands every fight
in the database, back to 1994, a plausible-looking schedule. That is the same
defect shape as R-13: a populated placeholder sailing through a presence check,
and it would have decided staleness by a constant nobody chose for this purpose.
A fight resting on the fallback is unscored, which is what it is.

### 3. Capture: written, verified offline, unapplied

The moneyline path was throwing away everything the totals path keeps — same
loop, same payload, same provider metadata. That asymmetry is the whole reason
CLV-001's capture requirements read as unmet: **the mechanism was already running
in the next table over.** So the column names are copied from `prop_odds`, not
invented.

| §4 | requirement | column |
|---|---|---|
| 9 | provider market IDs | `source_event_id` |
| 7 | scheduled bout-start timing | `source_commence_at` (+ `is_live`) |
| 11 | provider AND retrieval timestamps | `provider_last_update` + `retrieved_at` |
| 10 | opponent identity at quote time | `opponent_fighter_id` |
| 8 | market suspension / takedown | `market_status` |
| 6 | provider and feed version | `feed_version` |
| 12 | immutable link to the source quote | `raw` |

`research/clv/proposed_2026-09-16_fight_odds_capture.sql` — additive only, every
column NULLable with no default, so all 110,032 existing rows are untouched and
NULL honestly means "predates the column". **Unapplied.** `build/fetch-odds.js`
strips these keys when the columns are absent, so an un-migrated database keeps
capturing exactly what it captured before and logs that the quotes it is taking
can never be scored.

**Two-sided near-bell capture.** `odds.yml` now wakes every 15 minutes;
`shouldCaptureNow()` gates each wake — 30 minutes near a real bell, hourly on a
card day, once daily otherwise. ~33 credits on a card day, ~286/month, inside the
500 free tier.

The 30 minutes is forced, not chosen: the frozen 45-minute staleness limit was
derived from a measured 30-minute interval plus grace, and **hourly capture
cannot satisfy it** — a bell at :59 leaves the freshest quote 59 minutes old and
the row goes unscored on a stale price. At 30 minutes the worst case is 29.

### How "verified" was interpreted, since you said verify before applying

The only thing checkable before the migration exists is the code that will fill
it. So I pulled the row builders out of the main loop, made them pure, and wrote
`build/test-fetch-odds.js` — **25 checks, no API key, no Supabase key, no
network, no credit, nothing written.** It replays the saved Odds API fixture and
asserts every §4 field lands on every row; that sides map by fighter name and not
the provider's home/away order; that a Draw outcome is dropped rather than
guessed onto a corner; that `is_live` is *null* and not *false* when there is no
commence time; that stripping leaves the legacy shape untouched; and — walking
every possible bell minute — that the freshest pre-bell quote is always inside 45
minutes.

**What that does not verify**, and must not be read as verifying: that the
provider keeps sending these fields, that the columns accept them, or that a real
card yields three two-sided books inside 45 minutes of a bell. Those need the
migration applied and one card captured.

### Publication is untouched

Amendment 2 removes a blocker from the **write** path. It does not touch the
**publish** path, and there is now a test that says so by name:
`test_freezing_the_list_did_not_open_publication`. The gate is still 0 of 100
observations and 0 of 20 events, still fail-closed, still blocked on
`sample_floor_met` and `interval_excludes_zero`.

Tests: 86 CLV Python, 94 repo Python, 25 Node. All green.

## Next action

**Reed:** apply `research/clv/proposed_2026-09-16_fight_odds_capture.sql` — that
one only. Everything downstream waits on real captured rows, and every card that
passes before it lands is permanently unscorable.

Then the sequence runs itself: the next card captures under the new path →
`--clv001 --report` shows real per-row reasons instead of one blanket one → if
three named books quote both corners inside the window, apply
`proposed_2026-09-16_clv001_columns.sql` and turn on `--write`.

I have not applied either migration, called The Odds API, or written to Supabase.

---

*Older entries are in git history — the convention at the top of this file is
to keep the last three.*
