# T-092: the market view, rebuilt to read only the fights it is asked for

**Status: proposed, not applied (L3, CRITICAL_GATES item 5).**
Files: `market_movement_t092.sql`, `market_movement_t092.rollback.sql`,
`tests/test_t092_market_movement_sql.py`.

## Plain version

Card Lab, Fight Lab and Market Lab all ask the database for one card's prices.
The database worked out the prices for **every fight we have ever priced**,
then kept the one card's rows. That took 5.6 seconds, and visitors get 8. When
a few people loaded pages at once, some page loads failed.

The new version works out only the fights the page asked for. It gives the
same answers, about 500 times faster.

## Measured on production, 2026-10-15 (EXPLAIN ANALYZE)

| read | today | proposed |
|---|---|---|
| one card (`event_id = 4368`, 12 priced fights) | 5,646 ms | **11.6 ms** |
| one fight (`fight_id = 53618`) | 755 ms | **4.3 ms** |
| the whole view (120 fights; the alert sender's shape) | > 5,600 ms | **449 ms** |

The browser roles' `statement_timeout` is 8 s. The old card read used 70% of
that before any concurrent load. The new one uses 0.15%.

## Same answers: how that was proved

The candidate was built as `cfl_audit.v_mm_candidate` (a private schema the
browser API cannot see) and compared with the live view on production, over all
120 fights:

| check | result |
|---|---|
| rows | 120 and 120, none unmatched |
| every column except `best_book_a` / `best_book_b` | **0 differences** |
| `best_book_a` / `best_book_b` differences | 22 |
| of those, NOT between books posting the same best price | **0** |
| statuses covered | 113 `ok`, 7 `no_broad_capture`, 113 with a 24 h move |

**About the 22 book names.** When two books post the same best number, for
example Bovada and BetMGM both at -600, the old view's pick between them came
from an unstable sort, so it was arbitrary. The new view is arbitrary in the
same way. "Best price" is still ordered by the American number and by nothing
else, as CLAUDE.md requires.

A deterministic tie-break (alphabetical, say) would be a one-line follow-up.
It is a wording decision, so it is not taken here.

## What changed and what did not

- **Changed:** the view now starts from `fights`. Each fight's numbers come from
  a `LATERAL` subquery that reads that fight's quotes through
  `idx_fight_odds_fight_book_time` / `fight_odds_pre_start_idx`.
- **Not changed:**
  - every expression: D-012's matched cohort; the first broad capture (the third
    book's first quote); medians as `percentile_cont` over float8; the 24 h
    horizon exactly as `v_fight_market_horizons` defines it; the refusal
    statuses;
  - the column names, types and order, so `v_fight_alert_market` keeps working
    and every grant survives `CREATE OR REPLACE`;
  - no page or script changes.

## Safety built into the migration

- It runs as one `REPEATABLE READ` transaction, with `lock_timeout` set to 3 s.
- It snapshots the live view's output, replaces the view, recomputes the
  output, and **raises, rolling everything back**, if:
  - any row is missing;
  - any value differs;
  - any book name changes other than between tied books.
- The test proves this: a candidate with one deliberate error (the second book
  used instead of the third) is refused, and the old view stays.

## Local tests (throwaway Postgres 16, 6 pass)

- the synthetic fixture reaches every branch: excluded consensus and prediction
  market books, live and closed quotes, fights below three books, quotes either
  side of the 24 h line, odds for a fight not in `fights`;
- the migration applies, and its answers equal the old view's;
- filtered reads (`event_id`, `fight_id`) match the same rows;
- the guard refuses a wrong candidate and changes nothing;
- the rollback restores the old answers.

## To apply (owner)

```
psql "$SUPABASE_DB_URL" -f market_movement_t092.sql
```

or paste the file into the SQL editor.

**Rollback:** `market_movement_t092.rollback.sql`. It restores
`market_movement_views.sql`'s definition; no data is touched.

**After applying:**
- run verify-live, where the Fight Lab job should show no 500s;
- update `market_movement_views.sql` to the new definition, so the two files
  cannot drift;
- drop `cfl_audit.v_mm_candidate`.
