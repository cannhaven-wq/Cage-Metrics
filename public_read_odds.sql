-- =============================================================================
-- public_read_odds.sql — RETIRED. DO NOT APPLY. Running this file now fails.
-- =============================================================================
-- This file used to GRANT SELECT on fight_odds and odds_books to anon and
-- authenticated, so parlay.html could read raw odds rows directly. That is the
-- opposite of the rule every market surface is built on:
--
--   fight_odds and odds_books are private_lockdown_admin_only for anon AND
--   authenticated. The browser reads odds only through the definer views
--   (v_fight_market_movement, v_fight_odds_latest_by_book, ...). See CLAUDE.md
--   "Data layer" and D-012.
--
-- Verified 2026-10-12: the live database carries only the
-- private_lockdown_admin_only policy on both tables, so this file was either
-- never applied or was reverted. parlay.html was fixed to read
-- v_fight_odds_latest_by_book instead.
--
-- It was retired rather than deleted so that anyone following an old link or
-- note finds the reason, and so the habit of applying root *.sql files cannot
-- open the raw quote table by accident. The original text is in git history
-- (git log -p -- public_read_odds.sql). tests/sql-hazards.test.js fails if a
-- root SQL file grants anon read on either table again.
-- =============================================================================

DO $$
BEGIN
  RAISE EXCEPTION 'public_read_odds.sql is retired: fight_odds and odds_books stay admin-only. Read odds through the definer views. See the header of this file.';
END
$$;
