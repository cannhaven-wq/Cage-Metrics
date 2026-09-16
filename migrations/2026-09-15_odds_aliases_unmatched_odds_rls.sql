-- =============================================================================
-- Enable RLS on odds_aliases and unmatched_odds
-- =============================================================================
-- NOT YET APPLIED. Written 2026-09-15 for Reed to apply by hand
-- (python cfl_engine/run_sql_mgmt.py migrations/2026-09-15_odds_aliases_unmatched_odds_rls.sql
--  or paste into the Supabase SQL Editor).
--
-- Today both tables have RLS DISABLED and carry the default Supabase grants,
-- which means the anon key on the public website can SELECT, INSERT, UPDATE,
-- DELETE and TRUNCATE them. Nothing on the site needs that.
--
-- Who touches these tables (audit, 2026-09-15):
--
--   odds_aliases  (manual BFO name -> fighters.id overrides; 0 rows)
--     READ  cage-metrics-odds-scrapper/odds_scraper.py   (Railway; SUPABASE_SECRET_KEY = service_role)
--     READ  cage-metrics-odds-scrapper/backfill_odds.py  (manual;  SUPABASE_SECRET_KEY = service_role)
--
--   unmatched_odds (BFO rows that couldn't be linked to a fight; 11 rows)
--     WRITE cage-metrics-odds-scrapper/odds_scraper.py   (upsert; service_role)
--     READ  cage-metrics-odds-scrapper/diagnose_unmatched.py (manual; service_role)
--
--   Not referenced by: this repo's frontend (no *.html / *.js reads either
--   table), build/fetch-odds.js (The Odds API path; keeps its own unmatched
--   list in memory), cfl_engine/*, the snapshotter, or any GitHub Action.
--   Both are BFO-lineage tables; the BFO scraper's cron is retired but the
--   scripts still exist, and they all authenticate as service_role.
--
-- service_role bypasses RLS, so enabling it with NO anon/authenticated
-- policies keeps every one of those jobs working unchanged and closes the
-- anon write path. No SELECT policy is added for anon/authenticated because
-- the frontend never reads these tables; if that ever changes, add
--   CREATE POLICY ... FOR SELECT TO anon, authenticated USING (true);
-- (both roles, never anon alone — see CLAUDE.md, Data layer).
--
-- Belt and braces: also revoke the write grants from anon/authenticated so a
-- future "RLS off" slip can't reopen the write path. SELECT is revoked too
-- (nothing reads them). service_role keeps everything.
--
-- Re-run safe.
-- =============================================================================

ALTER TABLE public.odds_aliases   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.unmatched_odds ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.odds_aliases   FROM anon, authenticated;
REVOKE ALL ON TABLE public.unmatched_odds FROM anon, authenticated;

-- Sequences behind the bigserial ids: anon has no business calling nextval.
REVOKE ALL ON SEQUENCE public.odds_aliases_id_seq   FROM anon, authenticated;
REVOKE ALL ON SEQUENCE public.unmatched_odds_id_seq FROM anon, authenticated;

-- No policies on purpose: only service_role (which bypasses RLS) may touch
-- these tables. If the site ever needs to read them, add SELECT TO anon,
-- authenticated here.

-- Verify after applying:
--   select relname, relrowsecurity from pg_class
--    where relname in ('odds_aliases','unmatched_odds');          -- both true
--   select grantee, privilege_type from information_schema.role_table_grants
--    where table_name in ('odds_aliases','unmatched_odds')
--      and grantee in ('anon','authenticated');                   -- no rows
-- Then run cage-metrics-odds-scrapper/diagnose_unmatched.py once with the
-- service key to confirm the scraper-side reads still work.
