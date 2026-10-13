-- =============================================================================
-- odds_write_lockdown_migration.sql — T-087, applied 2026-10-13
-- =============================================================================
-- WHAT WAS WRONG
--   Supabase's default privileges hand every new table, view and sequence in
--   `public` to anon AND authenticated with ALL privileges (arwdDxtm / rwU).
--   Nobody revoked them on the odds tables, so as of 2026-10-13 both browser
--   roles held INSERT, UPDATE, DELETE, TRUNCATE, TRIGGER and REFERENCES on:
--
--     fight_odds, odds_books       RLS on with one admin-only SELECT policy, so
--                                  REST writes were refused by RLS — but
--                                  TRUNCATE ignores RLS entirely, and the grant
--                                  was one permissive policy away from open.
--     odds_aliases, unmatched_odds RLS OFF. Writable by anyone holding the
--                                  public key, straight through /rest/v1.
--     every view reading them      not auto-updatable today, so the write
--                                  grants were inert — except
--                                  v_odds_books_sportsbooks, which IS
--                                  auto-updatable and runs as its owner
--                                  (bypasses RLS on odds_books). It already
--                                  held SELECT only; this keeps it that way.
--     their id sequences           USAGE + UPDATE (nextval / setval).
--
-- WHAT THIS DOES
--   Privileges only. No row, column, policy, view body or RLS flag changes.
--   1. REVOKE from PUBLIC, anon, authenticated on every relation that holds or
--      reads sportsbook data, and ALL on the odds sequences.
--   2. On fight_odds / odds_books revoke only the write privileges: they keep
--      the SELECT they had, because their admin-only RLS policy decides who
--      sees rows (browser roles get 0; lab.html's admin gets them). On every
--      view the website reads, GRANT SELECT back to anon + authenticated
--      (CLAUDE.md: public reads go to BOTH roles).
--   3. odds_aliases and unmatched_odds get NO browser grant back: their only
--      readers and writers (cage-metrics-odds-scrapper odds_scraper.py,
--      diagnose_unmatched.py) use the service-role key.
--   4. Assert the result inside the transaction. Any browser role still able
--      to write, or a website read lost, raises and rolls the whole thing back.
--
-- NOT CHANGED (remaining exposure, see coordination/TASK_QUEUE.md T-087)
--   - Default privileges in `public` still grant ALL to anon/authenticated, so
--     the NEXT table created there is born writable. Changing them affects
--     every future migration and is its own decision.
--   - RLS is still off on odds_aliases / unmatched_odds. With no browser grant
--     that is no longer reachable from the browser, but the advisor still
--     flags it.
--
-- Idempotent: re-running revokes and re-grants the same set. Contains no
-- statement that raises a NOTICE (see CLAUDE.md "Supabase MCP gotcha").
-- tests/odds-write-lockdown.test.js holds this file to its promise.
-- =============================================================================

BEGIN;

-- 1. Strip every browser privilege -------------------------------------------
-- The two raw quote tables keep the SELECT they already had: their admin-only
-- RLS policy is what decides who sees rows, and re-granting SELECT on them in
-- a root file is exactly what tests/sql-hazards.test.js forbids. So only the
-- write privileges come off.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN
  ON TABLE public.fight_odds, public.odds_books
  FROM PUBLIC, anon, authenticated;

REVOKE ALL ON TABLE
  public.odds_aliases,
  public.unmatched_odds,
  public.v_fight_alert_market,
  public.v_fight_chart_books,
  public.v_fight_chart_meta,
  public.v_fight_chart_series,
  public.v_fight_market_at_lock,
  public.v_fight_market_broad_baseline,
  public.v_fight_market_horizon_cohorts,
  public.v_fight_market_horizons,
  public.v_fight_market_movement,
  public.v_fight_market_movement_books,
  public.v_fight_market_quotes,
  public.v_fight_market_vigfree,
  public.v_fight_odds_consensus,
  public.v_fight_odds_latest_by_book,
  public.v_my_alerts,
  public.v_my_watchlist,
  public.v_odds_books_sportsbooks,
  public.v_odds_capture_health
FROM PUBLIC, anon, authenticated;

REVOKE ALL ON SEQUENCE
  public.fight_odds_id_seq,
  public.odds_books_id_seq,
  public.odds_aliases_id_seq,
  public.unmatched_odds_id_seq,
  public.prop_odds_id_seq
FROM PUBLIC, anon, authenticated;

-- 2. Give back read, and only read, where the website reads ------------------
GRANT SELECT ON TABLE
  public.v_fight_alert_market,
  public.v_fight_chart_books,
  public.v_fight_chart_meta,
  public.v_fight_chart_series,
  public.v_fight_market_at_lock,
  public.v_fight_market_broad_baseline,
  public.v_fight_market_horizons,
  public.v_fight_market_movement,
  public.v_fight_market_movement_books,
  public.v_fight_market_vigfree,
  public.v_fight_odds_consensus,
  public.v_fight_odds_latest_by_book,
  public.v_my_alerts,
  public.v_my_watchlist,
  public.v_odds_books_sportsbooks
TO anon, authenticated;

-- 3. Prove it before committing ----------------------------------------------
DO $$
DECLARE
  r record;
  bad text := '';
  readable text[] := ARRAY[
    'fight_odds','odds_books','v_fight_alert_market','v_fight_chart_books',
    'v_fight_chart_meta','v_fight_chart_series','v_fight_market_at_lock',
    'v_fight_market_broad_baseline','v_fight_market_horizons',
    'v_fight_market_movement','v_fight_market_movement_books',
    'v_fight_market_vigfree','v_fight_odds_consensus',
    'v_fight_odds_latest_by_book','v_my_alerts','v_my_watchlist',
    'v_odds_books_sportsbooks'];
  locked text[] := ARRAY[
    'fight_odds','odds_books','odds_aliases','unmatched_odds',
    'v_fight_alert_market','v_fight_chart_books','v_fight_chart_meta',
    'v_fight_chart_series','v_fight_market_at_lock',
    'v_fight_market_broad_baseline','v_fight_market_horizon_cohorts',
    'v_fight_market_horizons','v_fight_market_movement',
    'v_fight_market_movement_books','v_fight_market_quotes',
    'v_fight_market_vigfree','v_fight_odds_consensus',
    'v_fight_odds_latest_by_book','v_my_alerts','v_my_watchlist',
    'v_odds_books_sportsbooks','v_odds_capture_health'];
  role_name text;
  rel text;
BEGIN
  FOREACH role_name IN ARRAY ARRAY['anon','authenticated'] LOOP
    FOREACH rel IN ARRAY locked LOOP
      IF has_table_privilege(role_name, ('public.'||rel)::regclass,
           'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES')
         OR has_any_column_privilege(role_name, ('public.'||rel)::regclass,
           'INSERT,UPDATE,REFERENCES') THEN
        bad := bad || format(' %s can still write %s;', role_name, rel);
      END IF;
    END LOOP;
    FOREACH rel IN ARRAY readable LOOP
      IF NOT has_table_privilege(role_name, ('public.'||rel)::regclass, 'SELECT') THEN
        bad := bad || format(' %s lost SELECT on %s;', role_name, rel);
      END IF;
    END LOOP;
    FOR r IN SELECT c.relname FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'public' AND c.relkind = 'S'
               AND c.relname IN ('fight_odds_id_seq','odds_books_id_seq',
                     'odds_aliases_id_seq','unmatched_odds_id_seq','prop_odds_id_seq')
               AND (has_sequence_privilege(role_name, c.oid, 'USAGE')
                 OR has_sequence_privilege(role_name, c.oid, 'UPDATE')) LOOP
      bad := bad || format(' %s can still use %s;', role_name, r.relname);
    END LOOP;
  END LOOP;
  IF bad <> '' THEN
    RAISE EXCEPTION 'odds write lockdown incomplete:%', bad;
  END IF;
END
$$;

COMMIT;
