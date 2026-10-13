# Data-integrity re-check, 2026-10-12

All 21 checks in `cfl_engine/integrity/checks.py`, re-run read-only against
production (the runner itself needs the unapplied `count_rpc.sql`, so the same
SQL was run directly). Baseline is 2026-09-16.

| check | 09-16 | 10-12 | moved | reading |
|---|---|---|---|---|
| odds_fighter_not_in_fight | 104 | 104 | — | finding 1, owner decision, unchanged |
| preds_fighter_not_in_fight | 8 | 8 | — | finding 1 |
| **odds_side_contradicts_fighter** | 1,578 | **1,598** | **+20** | finding 2 — **still being written** (below) |
| duplicate_bout_same_event | 4 | 4 | — | finding 4 |
| **fighter_twice_on_modern_card** | 31 | **37** | **+6** | finding 5 — **live on the next two cards** (below) |
| **settled_card_fight_with_no_result** | 36 | **39** | **+3** | finding 5 |
| multi_main_event | 3 | 3 | — | |
| odds_epoch_capture_time | 30,724 | 30,724 | — | finding 3, historical, not growing |
| odds_resolved_market_as_closer | 2 | 2 | — | finding 6, owner decision |
| **odds_extreme_price** | 61 | **62** | **+1** | finding 7 |
| fights_with_a_bell_time | 0 | 0 | — | finding 8 — no bell source exists (T-030) |
| the other 10 | 0 | 0 | — | clean |

## The two that are still happening

### 1. Corner-swapped prices are still being written — by the Polymarket capture

All 20 new rows are Polymarket, on two fights (49481 Brener vs Harrell,
2026-09-16→19; 50565 Soldic vs Williams, 09-20→23). The writer is the
`Scrape Polymarket` step of `train_models.yml` in **cage-metrics-odds-scrapper**,
not this repo. Polymarket is excluded from every sportsbook view
(`v_odds_books_sportsbooks`), so **no number on the site is wrong because of
it**; it does contaminate any research that reads Polymarket by corner.
Owner of the fix: the odds repo (match Polymarket outcomes by fighter id, not
by position). Nothing to change here.

### 2. Dead double-bookings on the next two cards

When a bout is rebooked, the event scraper inserts the new bout and never
retires the old one (it does not touch `is_active`). Event Flow was built to
retire them by observation but cannot run (T-030). So the Card Lab for this
Saturday currently lists bouts that will not happen:

| card | stale booking — no odds in 3 days | live booking — being priced |
|---|---|---|
| UFC FN Buckley vs. Malott, 10-17 | 47881 Jamey-Lyn Horth vs Katlyn Cerminara | 53620 Katlyn Cerminara vs Mackenzie Stiller |
| UFC FN Buckley vs. Malott, 10-17 | 48644 Julien Leblanc vs Gilbert Urbina | 53618 Julien Leblanc vs Nick Galanti |
| UFC FN Buckley vs. Malott, 10-17 | 50990 Javad Mahjoub vs Louie Sutherland | 53619 Javad Mahjoub vs Joel Faglier |
| UFC 333, 10-24 | 48648 Arnold Allen vs Aaron Pico | 53413 Aaron Pico vs Losene Keita |

**Proposed fix — not applied, needs owner approval.** The same retirement D-009
used for Moicano–Ortega: flag, never delete. Every odds row, snapshot and pick
on those ids is kept. `_shared.js::orderCard` already hides `is_active = false`.

```sql
-- retire four superseded bookings (reversible: set back to true)
update fights set is_active = false
 where id in (47881, 48644, 50990, 48648)
   and is_active is distinct from false;
-- expect: UPDATE 4
```

Rollback: `update fights set is_active = true where id in (47881, 48644, 50990, 48648);`

Do it before Friday 2026-10-16 if at all: the pre-fight snapshot for the 10-17
card is taken at 23:00 UTC that night and is append-only.

## Everything else

Findings 1 and 6 still need the owner's call (L3). Findings 3, 4 and 7 are
historical and not growing. Finding 8 needs a live bell source, which does not
exist.
