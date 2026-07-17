-- =============================================================================
-- fix_v6_honest_window.sql — restate v6's record honestly (July 2026 audit)
-- =============================================================================
-- Paste into the Supabase SQL Editor and run once.
--
-- Why: v6's test_start_date (2021-01-01) predates its train_end_date
-- (2024-12-31), so every public surface that gates "out-of-sample" stats to
-- test_start_date was including four years of fights the model TRAINED on.
-- 98 of the 184 advertised bets were training fights. The metrics below are
-- recomputed on the honest window - fights after the training cutoff only.
--
-- The frontend now also clamps every model's window to after train_end_date
-- (belt and braces), but this row is what the About/methodology surfaces
-- display, so the text and numbers should be true at the source.
--
-- Backup of the previous row values:
--   scratchpad model_versions_backup_2026-07-14.json (Claude session dir)
--   and in git history of this file's PR description.
-- =============================================================================

UPDATE model_versions
SET
  test_start_date = '2025-01-01',
  test_size       = 395,
  test_accuracy   = 0.6987,
  test_log_loss   = 0.6038,
  test_brier      = 0.2074,
  description     = 'The ROI model. Trained with the opening line as an input, so it learns where the market''s opener is systematically wrong instead of re-deriving the market. Picks are locked at first write and never re-priced. Honest out-of-sample record, restated July 2026 — only fights after the December 2024 training cutoff, none seen in training: 395 graded fights at 69.9% accuracy; the shipped rule (favorites with 3+ points of edge, $100 flat) has gone 66-21 (75.9%) as of July 15, 2026: +$1,478 at the opening price (+17.0% ROI), still +$1,103 (+12.7%) re-priced at closing odds. It beat the closing line on 57 of 87 bets. This record is simulated point-in-time; the live record starts July 2026.'
WHERE id = 'v6';

-- Reposition v3 as the tape-only Accuracy model (odds-free by construction).
UPDATE model_versions
SET
  name        = 'Accuracy — tape only (no odds)',
  description = 'Predicts winners from fighter data alone — Elo, recency, style, durability. It never sees a betting line, so its number is fully independent of the market: 63.6% on out-of-sample fights, next to the closing favorite''s 68.4%. We publish both because getting within five points of Vegas without looking at Vegas is the honest baseline for what fight data alone can do — and the fights where this model and the market disagree are where the interesting analysis lives.'
WHERE id = 'v3';

SELECT id, name, train_end_date, test_start_date, test_size, test_accuracy
FROM model_versions ORDER BY id;
