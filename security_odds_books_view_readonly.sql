-- =============================================================================
-- SECURITY (2026-10-13): v_odds_books_sportsbooks must be read-only to browsers
-- =============================================================================
-- FOUND. v_odds_books_sportsbooks is a SECURITY DEFINER view (owner postgres,
-- which bypasses RLS) over the admin-only `odds_books` table. It is a simple
-- single-table filter, so Postgres treats it as AUTO-UPDATABLE. anon and
-- authenticated held INSERT / UPDATE / DELETE on it (Supabase default grants).
-- So anyone holding the publishable key could write odds_books through
-- PostgREST:
--   rename, add or delete a sportsbook;
--   and because fight_odds.book_id is ON DELETE CASCADE, a delete would also
--   erase every quote CFL ever captured from that book.
-- Reproduced on a throwaway Postgres by tests/test_security_odds_books_view.py.
-- No write was attempted against production.
--
-- FIX. Browsers only ever read this view. Remove every other privilege from
-- both browser roles and keep SELECT. Nothing that legitimately writes
-- odds_books uses the view: the scrapers use service_role against the table.
--
-- ROLLBACK (not recommended): GRANT INSERT, UPDATE, DELETE ON
-- public.v_odds_books_sportsbooks TO anon, authenticated;
-- Safe to re-run.
-- =============================================================================

REVOKE ALL ON public.v_odds_books_sportsbooks FROM anon, authenticated;
GRANT SELECT ON public.v_odds_books_sportsbooks TO anon, authenticated;
