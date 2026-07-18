-- =============================================================================
-- cleanup_stale_live_picks.sql — one-time reset of the first live publish
-- =============================================================================
-- The first predict_upcoming.py --execute (2026-07-17) published live picks for
-- ALL 8 upcoming cards at once (71 picks / 10 edges). That was a bug: live rows
-- are insert-only (locked, never re-priced), so cards weeks out got locked onto
-- point-in-time history as of the 2026-07-11 export and can never self-correct.
-- It also published 3 dead double-bookings (fights 27577, 27579, 27582) that the
-- fixed exporter/serving now drop.
--
-- The fix (cfl_engine/predict_upcoming.py) now only publishes events within
-- ~12 days and de-dupes dead bookings. This file clears the stale first publish
-- so the corrected script can republish just the imminent card(s), locked on
-- current history. Backtest rows (source='backtest') are the track record and
-- are NOT touched.
--
-- Run in the Supabase SQL Editor, THEN re-run:
--   PYTHONPATH=cfl_engine python cfl_engine/predict_upcoming.py --execute
-- =============================================================================

DELETE FROM model_edges WHERE source = 'live';
DELETE FROM model_picks WHERE source = 'live';

-- Verify (both should be 0 until the corrected republish):
-- SELECT source, count(*) FROM model_picks GROUP BY source;
-- SELECT source, count(*) FROM model_edges GROUP BY source;
