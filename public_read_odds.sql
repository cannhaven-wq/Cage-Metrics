-- =============================================================================
-- public_read_odds.sql — grant public (anon + authenticated) read on the live
-- odds tables so the Parlay Builder can read them directly.
-- =============================================================================
-- Symptom this fixes: parlay.html queries `fight_odds` (and `odds_books` for
-- book names) with the publishable anon key and gets ZERO rows, HTTP 200, no
-- error — the documented anon-RLS trap. The consensus VIEW already works for
-- anon (index/event/picks show odds) because it's owned by a privileged role,
-- but the base-table reads in parlay.html are blocked.
--
-- Writes are unaffected: the odds workflow uses the service_role key, which
-- bypasses RLS. This only opens up SELECT, matching every other public table.
--
-- Apply via Supabase → SQL Editor (direct DB is IPv6-only from this machine).
-- Idempotent — safe to re-run.
-- =============================================================================

ALTER TABLE fight_odds ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "public read fight_odds" ON fight_odds;
CREATE POLICY "public read fight_odds" ON fight_odds
  FOR SELECT TO anon, authenticated USING (true);
GRANT SELECT ON fight_odds TO anon, authenticated;

ALTER TABLE odds_books ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "public read odds_books" ON odds_books;
CREATE POLICY "public read odds_books" ON odds_books
  FOR SELECT TO anon, authenticated USING (true);
GRANT SELECT ON odds_books TO anon, authenticated;
