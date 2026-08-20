-- =============================================================================
-- 2026-08-19_v6_honest_window.sql — restate v6's record on an honest window
-- =============================================================================
-- Supersedes the unapplied fix_v6_honest_window.sql that sat at repo root from
-- the July 2026 audit. Same structural fix, recomputed numbers.
--
-- THE BUG
-- v6's test_start_date was 2021-01-01 but its train_end_date is 2024-12-31, so
-- the "out-of-sample" window opened four years INSIDE the training data. Every
-- surface that gates stats to test_start_date was grading v6 partly on fights
-- it had already learned. The published 2,602 / 67.5% was in-sample.
--
-- WHY NOT JUST RUN THE JULY FILE
-- Its numbers were computed correctly but are eight months stale. Verified
-- against the table before rewriting: on the July 15 cutoff the shipped rule
-- returns exactly 87 bets, 66 wins, $1,477.97 — matching the July description's
-- "66-21 ... +$1,478" to the dollar. Method confirmed; only the window moved.
--
-- WHAT CHANGES (v6)
--   test_start_date  2021-01-01 -> 2025-01-01   (day after the training cutoff)
--   test_size        2602       -> 412          (graded fights, deduped)
--   test_accuracy    0.6745     -> 0.7087
--   test_log_loss    0.6209     -> 0.5956
--   test_brier       0.2153     -> 0.2036
--   description      restated with current, recomputed figures
--
-- Accuracy goes UP, not down: the honest window is v6's recent record, and the
-- in-sample years it used to include were its weaker ones. The number that
-- falls is the sample — 2,602 claimed, 412 real.
--
-- Two claims from the July description are NOT carried forward: "+$1,103
-- (+12.7%) re-priced at closing odds" and "beat the closing line on 57 of 87
-- bets". model_predictions has no closing-odds column, so neither is
-- recomputable here and neither should be republished as current.
--
-- Metrics are over one row per fight (a handful of fights carry two rows with
-- model_p > 0.5 — reconstructed / duplicate bookings — deduped on max model_p).
-- Window covers 2025-01-11 through 2026-08-15.
--
-- Before-state snapshot: migrations/2026-08-19_v6_honest_window.before.json
-- =============================================================================

UPDATE model_versions
SET
  test_start_date = '2025-01-01',
  test_size       = 412,
  test_accuracy   = 0.7087,
  test_log_loss   = 0.5956,
  test_brier      = 0.2036,
  description     = 'The ROI model. Trained with the opening line as an input, so it learns where the market''s opener is systematically wrong instead of re-deriving the market. Picks are locked at first write and never re-priced. Honest out-of-sample record, restated August 2026 — only fights after the December 2024 training cutoff, none of them seen in training: 412 graded fights at 70.9% accuracy. The shipped rule (favorites with 3+ points of edge, $100 flat) has gone 75-24 (75.8%) through August 15, 2026: +$1,907 on $9,900 staked, a 19.3% return at the opening price. This record is a point-in-time simulation; the live locked record starts July 2026.'
WHERE id = 'v6';

SELECT id, train_end_date, test_start_date, test_size,
       test_accuracy, test_log_loss, test_brier
FROM model_versions WHERE id = 'v6';
