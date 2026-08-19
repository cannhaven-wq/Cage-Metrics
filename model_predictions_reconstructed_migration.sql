-- =============================================================================
-- model_predictions_reconstructed_migration.sql — provenance flag for
-- reconstructed picks (Aug 2026 claims audit, follow-up)
-- =============================================================================
-- methodology.html documents one exception to "every pick locked before the
-- card": if an outage stops a model from recording its pick, the pick is
-- reconstructed afterward from point-in-time data, recorded for ACCURACY ONLY,
-- and excluded from every profit-and-loss figure. Until now nothing in the
-- database marked which rows those were, so the exclusion was unenforceable.
--
-- This adds the flag and backfills the only reconstruction that has ever
-- happened: model/v5/whatif_v5.py (odds-scrapper repo) backfilled v5's picks
-- for the two June 2026 cards it skipped when the fight_odds opener feed was
-- dry — event 116 (Kape vs Horiguchi) and event 2510 (Fiziev vs Torres),
-- 28 rows, written with would_bet=false and pnl_usd=null but WITH a proxy
-- opener (consensus odds), so without this flag they still enter edge-bucket
-- ROI denominators on predictor.html.
--
-- Frontend contract: reconstructed rows count toward straight-up accuracy
-- (that is their documented purpose) and are excluded from every betting /
-- ROI / P&L computation. Any future reconstruction MUST set this flag at
-- insert time.
--
-- Idempotent. Run via cfl_engine/run_sql_mgmt.py or the SQL Editor.
-- =============================================================================

ALTER TABLE model_predictions
  ADD COLUMN IF NOT EXISTS reconstructed boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN model_predictions.reconstructed IS
  'True when the pick was reconstructed after the event from point-in-time data (outage carve-out, methodology.html). Counts toward accuracy only; every P&L/ROI figure must exclude it.';

UPDATE model_predictions
SET reconstructed = true
WHERE model_version = 'v5'
  AND fight_id IN (SELECT id FROM fights WHERE event_id IN (116, 2510));

-- Verification: expect 28 flagged rows, all would_bet=false.
SELECT count(*) AS flagged,
       count(*) FILTER (WHERE would_bet) AS flagged_would_bet
FROM model_predictions
WHERE reconstructed;
