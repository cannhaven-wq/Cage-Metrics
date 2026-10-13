-- =============================================================================
-- ROLLBACK for fighter_ufc_record_view.sql (T-084).
-- =============================================================================
-- Removes the view. Nothing else depends on it in the database, and no data
-- is touched: it only ever read `fights` and `events`.
--
-- ORDER: revert the page deploy FIRST (pages that call ufc-record.js against
-- a missing view show "—" or the labelled career record, never a stale
-- number), then run this. Safe to re-run.
-- =============================================================================

DROP VIEW IF EXISTS public.v_fighter_ufc_record;
