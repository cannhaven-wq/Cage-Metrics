# T-086 — Complete migration plan for final approval (2026-10-13)

**APPROVED by the owner on 2026-10-13 ([D-026](../../coordination/DECISIONS.md)),
including moving the event row, with gates.** It may not run until:
- PR #69's CI is green on its final commit;
- event-scraper PR #1 is merged and verified;
- fingerprints, foreign-key references and rollback preconditions are
  rechecked;
- readiness has been reported.

Stop if anything differs.

The RESERVE and PROP-0001 records are in
[`T-086_RESEARCH_CORRECTIONS_2026-10-13.md`](T-086_RESEARCH_CORRECTIONS_2026-10-13.md).

**Nothing in this plan has been run against production.** No fight has been
moved, deleted or changed. Everything below was demonstrated on a throwaway
Postgres or checked with read-only queries.

This supersedes the review draft
[`T-086_DWCS_PLAN_2026-10-13.md`](T-086_DWCS_PLAN_2026-10-13.md).

## Plain version

"DWCS 10.3" was a Contender Series card, not a UFC event. It is stored as if
it were UFC, so ten fighters each show one extra UFC fight. Nicholas Galanti,
who fights on Saturday, reads UFC 1-0 instead of debuting.

The fix moves that one card, its 5 fights and their 8 round records into
three side tables, word for word and with the same ids. The UFC tables then
hold UFC fights only, and every page is right without being edited. The card's
old links still work, and say plainly that it was not a UFC event. Its results
are kept, but they never count toward a UFC record.

## One change from the plan approved in principle — approved 2026-10-13 (D-026)

Option C as approved **kept the event row in `events`** and added a
`promotion` column. This plan **moves the event row as well**, into
`events_non_ufc`, and adds no column to `events`.

**Why:**
- About 20 places on the site and in the build scripts choose "the next card"
  or "recent cards" from `events` with no promotion filter. These include the
  homepage, Market Lab, the odds fetcher (which spends API credits), the
  digest and the RSS feed.
- Leaving DWCS there would show an empty card. Worse, a future Contender
  Series episode could become the homepage's "next card".
- With the event moved, the existing foreign key from `fights` to `events`
  makes it **physically impossible** for a fight in the UFC tables to sit on a
  non-UFC card.

A name CHECK on `events` keeps non-UFC cards out of it from then on.

If you would rather keep the column design, say so. It needs a filter on each
of those ~20 readers, which is a larger and more fragile change.

## Your requirements, one by one

| requirement | how it is met | evidence |
|---|---|---|
| Preserve all five fights and their eight round records, losing nothing | Same columns, same order, same ids. Every row is fingerprinted before the originals are removed; any mismatch aborts. The fingerprint is stored on the new tables, so the rollback can prove it restored the original bytes. | `test_every_column_of_every_moved_row_survives`, `test_rollback_restores_the_original_bytes_and_cycles`, `test_rollback_detects_a_tampered_copy` |
| Verify constraints, permissions, RLS, indexes and foreign keys explicitly; don't trust `LIKE INCLUDING ALL` | Nothing is inherited; every item is written out in the migration (see the table below). `LIKE` would have missed the foreign keys, RLS, policies and grants, and given each new table its own id sequence. | `test_constraints_and_foreign_keys_are_explicit` (full list of 14 constraints compared exactly), `test_indexes_are_explicit` (16), `test_rls_policies_and_grants_are_explicit` (7 privileges × 2 roles × 3 tables) |
| No impact on frozen research datasets or prospective-model integrity | H1 is untouched, and its hashes were re-derived today. One count in RESERVE and one already-written PROP lock are affected; both are set out below for you. | "Frozen research and model integrity" below |
| Update the event scraper before the migration | Both scrapers classify each card by name. A non-UFC card goes to the side tables, or is skipped if they don't exist yet. It **never** goes to `events` / `fights`. The database CHECK also stops the old scraper. | cage-metrics-event-scrapper `claude/pensive-fermi-d6pbi0` (`7a7b011`), `test_promotion.py`; `test_a_non_ufc_card_cannot_reenter_the_ufc_tables` |
| Account for event pages, URLs and sitemap | `event.html?id=4259` and `/e/dwcs-10-3-4259.html` keep working: noindex, labelled "Not a UFC event", with the results listed. The card is removed from the sitemap. | `tests/non-ufc-event.test.js` |
| Demonstrate migration and rollback in a temporary database | 13 tests on a throwaway Postgres built in production's shape. Includes migrate → rollback → migrate → rollback, byte-identical. | `tests/test_t086_dwcs_migration_sql.py` |
| Return the plan for final approval | This document | — |

## Production facts, verified read-only on 2026-10-13

**What moves:**
- Event 4259 "DWCS 10.3", 2026-08-25.
- Fights 49307–49311. These are the only 5 fights on the event.
- Round rows 86132–86139 (8 rows).

**Fingerprints of the exact rows to be moved.** Recheck these immediately
before applying; the migration also re-checks counts itself.

| | md5 |
|---|---|
| fights (whole rows, by id) | `c214474a3890cf8ad8a72f3ead72dd5c` |
| fight_rounds (whole rows, by id) | `061a9bf975efa8a021dac54e9ffcb287` |
| event row | `385f53c7b92156979c929089f9001318` |

**Every table that references `fights` or `events` holds 0 rows for these
ids.** Checked one by one:
- `fight_odds`, `fight_start_estimates`, `model_edges`, `model_picks`,
  `model_predictions`, `predictions`;
- `prop_model_locks`, `prop_odds`;
- `user_alert_deliveries`, `user_alerts`, `user_bets`, `user_watchlist`;
- `win_model_locks`, `pre_fight_snapshots`;
- `master_dataset`, `master_dataset_v2`;
- `cardio_style_snapshots`, `streak_effect_cache`, `fighter_cardio`,
  `fighter_snapshot_2025`.

This matters because 8 foreign keys to `fights` are ON DELETE CASCADE. The
migration **re-checks every foreign key generically at run time**, so a table
added later is covered too. Any hit aborts the migration with nothing applied
(tested).

**The CHECK rule.** Run against all 801 event names in production, it rejects
exactly one: 4259.

## What the migration creates

| | events_non_ufc | fights_non_ufc | fight_rounds_non_ufc |
|---|---|---|---|
| columns | `events`' 8, then `promotion` (DWCS / RTU / OTHER) and `moved_at` | identical to `fights` (54, same order, types, NOT NULLs, defaults) | identical to `fight_rounds` (37) |
| primary key | id | id | id |
| unique | ufc_event_id | ufc_fight_id | (fight_id, round_number) |
| foreign keys | — | event_id → events_non_ufc **ON DELETE RESTRICT**; fighter_a / fighter_b / winner → fighters | fight_id → fights_non_ufc ON DELETE CASCADE (as production); fighter_a / fighter_b → fighters |
| indexes | event_date DESC, is_upcoming | the 7 that `fights` has | fight_id |
| id default | `events_id_seq` | `fights_id_seq` | `fight_rounds_id_seq` |
| RLS | on | on | on |
| policy | SELECT to anon, authenticated | same | same |
| grants | REVOKE ALL from PUBLIC, anon, authenticated; then SELECT to both browser roles; SELECT / INSERT / UPDATE / DELETE to service_role | same | same |

**Two choices that differ from the UFC tables on purpose:**

1. **RESTRICT instead of CASCADE from fights to event.** Deleting a non-UFC
   card should never silently erase its results.
2. **Shared id sequences.** An id is unique across a UFC table and its
   sibling, so a row can always move back without a collision.

**Grants.** Production gives `anon` every privilege on `fights` / `events` /
`fight_rounds`. RLS and PostgREST's lack of a TRUNCATE endpoint keep that
harmless today. The new tables do not copy it.

**Guard.** `events_ufc_name_only` CHECK, the same rule as
`build/promotion.js`, the integrity check, the T-083 reconciliation and the
scraper. `tests/test_promotion_rule.py` holds the copies to the same answers.

**Detection.** The `non_ufc_card_in_events` integrity check goes from 1 to 0
after the migration. Anything above 0 later means the guard was removed.

## Frozen research and model integrity

**PRED-001 H1 (sealed holdout) is unaffected.**
- Re-derived today with the frozen recipe: 710 fights, 63 events. All four
  hashes match `holdout_manifest.json`.
- The DWCS bouts cannot enter H1. They fall outside its dates, have no
  BestFightOdds closing price, and are not in `h1_fight_ids.txt`.

**PRED-001 RESERVE: one recorded count changes. Needs your acknowledgement.**
- RESERVE (2026-07-18 → 2026-10-10) is sealed, unscored, and has no hash. Its
  manifest records `"decided": 169`, and that **includes the 5 DWCS bouts**
  (re-derived today: 169, of which 5 are DWCS). After the move it re-derives
  as 164.
- The manifest is hash-pinned by PRED-001, so this plan **does not edit it**.
- **Recommended:** record the correction in DECISIONS when the migration
  runs, with the 5 ids. Any future use of RESERVE then starts from 164 with
  the reason on file.
- An auditor re-deriving RESERVE today would otherwise find a difference with
  no explanation.

**PROP-0001 locks for Saturday's Leblanc vs Galanti (fight 53618): the record
stands as written.**
- 8 `prop_model_locks` rows were written on 2026-10-09, for v1 and v2. Their
  stored features show `m_fh_n_fights = 1.0`, meaning the model counted
  Galanti's Contender Series bout as fight history.
- Those rows are append-only evidence of what the model saw. The migration
  does not and cannot touch them.
- **Recommended, decided before the bell so it is not chosen after the
  result:** grade 53618 as locked, with no exclusion, and add a note that one
  input was a non-UFC bout. Excluding it after the result would be
  cherry-picking.
- PROP-0001's training count (6,881) included these 5 fights. A retrain from
  the database after the move would see 6,876. The frozen artifact is
  unchanged, and nothing fingerprints that training set.

**Untouched:**
- `win_model_locks`, `pre_fight_snapshots`, `predictions`: 0 rows for any of
  these fights.
- `master_dataset` / `_v2`: 0.
- The frozen snapshot tables: 0.

**Self-correcting:**
- `prop_projections` holds one Galanti row built on the old data. It is fully
  replaced daily at 10:00 UTC (`props-refresh.yml`), or can be refreshed by
  hand after the move.
- Friday's 23:00 UTC pre-fight snapshot then freezes the corrected board.
- `v_fighter_consistency` loses 4 rows that came only from this card.

## Open question, not part of this migration: "UFC - Road to UFC 4.6"

Event 146 (2025-08-22) holds 2 completed bouts, 417 and 418, with BestFightOdds
closing prices.

**Both are in the sealed H1 holdout.** Moving them would break PRED-001's
fingerprint and invalidate any later look.

**They may well be genuine UFC bouts.** UFCStats lists only these two on that
card, not the tournament bouts, which suggests they were the UFC-sanctioned
fights on the broadcast.

**So this plan leaves them where they are.** Every copy of the rule counts
"UFC - Road to UFC …" as UFC, so the guard does not block them. A
name-starting "Road to UFC …" card is still treated as non-UFC.

**If you want them checked:** that is a separate audit, and any change would
need a PRED-001 amendment first.

## Deployment order

The rule throughout: **the scraper first, the database second, the pages
last.** Each step is safe if the next one never happens.

### 0. Approvals (you)
1. This plan, including the event-row refinement.
2. The RESERVE note.
3. The 53618 grading note.

### 1. Scraper
1. Merge cage-metrics-event-scrapper `claude/pensive-fermi-d6pbi0` into `main`.
2. Railway redeploys both services from `main`.
   - **Merging starts a full `events_scraper.py` run (3–4 h).** That service
     has no cron and runs on every deploy.
   - "Weekly Scraper" (`weekly_refresh.py`) runs daily at 00:00 UTC.
3. Until step 2 runs, a non-UFC card is skipped and logged ("does not exist
   yet (T-086 not applied)"). It is never written.
4. **Check:**
   - the deploy logs show the full run reaching DWCS 10.3 and skipping it;
   - `select count(*) from fights where event_id = 4259` is still 5, and
     unchanged.

### 2. Database (L3, after step 1 is live)
1. Re-run the fingerprint query. All three md5s must match the table above.
2. Apply `t086_dwcs_non_ufc.sql`. One transaction: preconditions → create →
   copy → verify → delete → guard → postconditions. Any failure applies
   nothing.
   - **With `psql`:** use `SUPABASE_DB_URL`. It is not set in this
     environment.
   - **With the Supabase tool:** use `apply_migration` with the file's
     `BEGIN;` / `COMMIT;` lines removed, because the tool wraps a migration
     in its own transaction and a nested `BEGIN` raises a warning that hangs
     it. A failed assertion also hangs the tool, but applies nothing. After
     a hang, check that `to_regclass('public.fights_non_ufc')` is NULL before
     trying anything else.
3. **Checks:**
   - fights 49307–49311 are absent;
   - the side tables hold 1 / 5 / 8 rows;
   - Galanti's completed UFC bouts: 0;
   - as `anon`: `fights_non_ufc` reads 5 rows, and a write is refused;
   - privileges are SELECT only for both browser roles;
   - the integrity check `non_ufc_card_in_events` reads 0;
   - the H1 manifest query still matches all four hashes;
   - the security advisor shows no new findings.
4. **Fight Lab is correct immediately.** It counts records from `fights`, so
   Galanti shows a debut. So does T-084's `v_fighter_ufc_record` once PR #66
   lands.
5. Trigger `props-refresh.yml`, or let the 10:00 UTC run do it.

### 3. Pages (this PR)
1. Merge. GitHub Pages deploys `event.html`, the regenerated DWCS stub and the
   sitemap without that card.
2. Check `event.html?id=4259` in a browser. It should show the five results,
   "Not a UFC event", and noindex.

**Order with PR #66 (T-084/T-085):** independent. Either can go first.

### Before Saturday (Galanti fights 2026-10-17)

If approved Wednesday 10-14:
- **Wednesday:** scraper merged; the full run is finished by that evening.
- **Thursday 10-15:** migration and page merge.
- **Friday:** the 10:00 UTC props refresh, then the 23:00 UTC snapshot, both
  on corrected data.

If approval comes later, Galanti's record is still corrected the moment step 2
runs, and nothing in the order needs to be rushed.

## Rollback

**Database:** `t086_dwcs_non_ufc.rollback.sql`, in one transaction:
1. Drops the guard.
2. Copies the event, fights and rounds back with the same ids.
3. **Proves the restored rows are byte-identical**, using the fingerprints the
   migration stored.
4. Drops the side tables.

It **refuses** if the side tables hold any other card (the new scraper may
have stored one), because dropping them would lose it. It never discards data.

**Pages:** revert the merge. The fallback is harmless while the event is back
in `events`, because `event.html` only uses it when the UFC lookup misses.

**Scraper:** revert its merge. That is safe either way. If the scraper is
reverted but the migration is kept, the database guard still keeps non-UFC
cards out of `events`, and the old scraper logs an error for each one.

## Files

| repo | file | what |
|---|---|---|
| Cage-Metrics | `t086_dwcs_non_ufc.sql` | the migration |
| | `t086_dwcs_non_ufc.rollback.sql` | the rollback |
| | `tests/test_t086_dwcs_migration_sql.py` | 13 tests, throwaway Postgres |
| | `build/promotion.js`, `tests/test_promotion_rule.py` | the shared rule and its parity test across SQL / Python / JS |
| | `event.html`, `build/templates.js`, `build/prerender.js`, `e/dwcs-10-3-4259.html`, `sitemap.xml`, `tests/non-ufc-event.test.js` | pages, stubs and sitemap |
| | `cfl_engine/integrity/checks.py` | `non_ufc_card_in_events` |
| cage-metrics-event-scrapper | `promotion.py`, `events_scraper.py`, `weekly_refresh.py`, `test_promotion.py` | the scraper guard |
