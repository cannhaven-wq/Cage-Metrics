# C2 — Locking stored odds against edits: readiness check (2026-10-21)

**Verdict: safe to apply. Every active writer is compatible. Not applied; it
waits for the CFL Owner's explicit go-ahead.** Target: Sunday 2026-10-25,
after UFC 333 and before the next card.

## What gets applied

1. `research/clv/proposed_2026-09-16_fight_odds_immutability.sql`. Triggers
   reject DELETE, TRUNCATE and any UPDATE except to `is_opener` / `is_closer`,
   for every role including `service_role`. It writes nothing and leaves
   every existing row byte-identical.
2. `research/clv/proposed_2026-10-21_fight_odds_corrections.sql` (new): the
   auditable correction mechanism. A wrong quote is never edited. A person
   adds a row to `fight_odds_corrections` that names the quote, what to do
   with it (`exclude`, or `reassign_fight` with a target), a reason of at
   least 10 characters, who, and when. That table is append-only as well and
   unreachable from browser roles. Nothing reads it yet; a reader that wants
   corrected data joins it.

## Compatibility with every writer (checked 2026-10-21)

| writer | where | how it writes `fight_odds` | compatible |
|---|---|---|---|
| Odds API capture (`odds-api-v4`, 12,682 rows in 30 days) | this repo, `build/fetch-odds.js` | INSERT; UPDATE `is_closer` only (line ~1183) | yes |
| Railway odds scraper (3,017 rows in 30 days) | `cage-metrics-odds-scrapper/odds_scraper.py` | INSERT only (line 517) | yes |
| Polymarket capture (1,194 rows in 30 days) | `cage-metrics-odds-scrapper/polymarket/scrape.py` | INSERT; UPDATE `is_opener`, `is_closer` only | yes |
| Polymarket history backfill | `…/polymarket/backfill_history.py` | INSERT; UPDATE `is_opener` only | yes |
| fighter / event scrapers | `cage-metrics-scrapper`, `cage-metrics-event-scrapper` | none | n/a |
| database functions and triggers | production catalog | none update or delete `fight_odds`; no triggers exist yet | n/a |
| `dead_booking_cleanup.sql` | this repo | would UPDATE `fight_id`; already marked DO NOT RUN | **blocked, as intended** |

Production table statistics since the last reset: 5,509 inserts, 839 updates
and **0 deletes**. Every known update path touches only the two allowed
flags. The statistics cannot show which columns an update changed, so if an
unknown writer exists, the first night after applying will surface it as a
loud error rather than a silent edit.

## Tests

`tests/test_sql_behaviour.py` runs both files on a throwaway Postgres:
- the closer flag still moves;
- price, capture time and provenance can't be rewritten;
- DELETE and TRUNCATE fail;
- a correction row is recorded while the quote stays untouched;
- a correction can't be edited, deleted or truncated;
- a reassignment needs a target, and a reason must be real;
- browser roles have no access;
- both files re-run cleanly.

30 passed.

## Procedure, once authorized

1. Confirm no card is in progress.
2. `psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f research/clv/proposed_2026-09-16_fight_odds_immutability.sql`
3. `psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f research/clv/proposed_2026-10-21_fight_odds_corrections.sql`
4. Check the result:
   - `select tgname from pg_trigger where tgrelid='public.fight_odds'::regclass and not tgisinternal` returns the three lock triggers.
   - An `update fight_odds set american_odds = american_odds where id = <any>` inside `begin … rollback` fails.
   - The next odds capture succeeds.
5. Rollback, if a legitimate writer breaks: `drop trigger` on the three
   triggers. The data is unaffected, because the lock never writes.
