-- =============================================================================
-- v_fight_odds_consensus — per-fight consensus odds, aggregated from the
-- cage-metrics-odds-scrapper snapshot table (fight_odds).
-- =============================================================================
-- Background:
--   The base `fight_odds` table is the per-poll snapshot table owned by the
--   cage-metrics-odds-scrapper repo. Each row is one (fight, side, book,
--   captured_at) sample from BestFightOdds. The frontend originally expected
--   a one-row-per-fight consensus table (event_id, american_odds_a/b,
--   implied_prob_a/b, bookmaker_count, fetched_at) created by the now-disabled
--   build/fetch-odds.js GitHub Action. The two table definitions collided on
--   `fight_odds`, so the consensus shape never materialized and odds queries
--   from index.html and event.html silently returned 400 ("column
--   american_odds_a does not exist").
--
-- What this view does:
--   For each fight, take the LATEST snapshot per (side, book) from the live
--   cron, then expose TWO sets of numbers:
--
--   1. american_odds_a / american_odds_b
--      Back-derived from the RAW consensus implied probability (vig-preserved).
--      These match what books actually show — asymmetric, with the vig baked
--      in. This is what bettors expect to see on display.
--
--   2. implied_prob_a / implied_prob_b
--      VIG-REMOVED probabilities, normalized so a + b = 1.0. These are the
--      "fair" probabilities for use by model-edge / value-pick math
--      (model_p − implied_prob = edge in pp). Do NOT display these as a
--      book price — they will always come out symmetric.
--
--   Filters out fake epoch (1970) opener rows produced by historical backfills,
--   so only real polled data feeds the consensus.
--
-- Read by: index.html (loadOddsMap, fighter odds chip),
--          event.html (renderEvent, market band).
-- Writers: NONE. The underlying base table is written by the Railway cron in
--          cage-metrics-odds-scrapper; this view is computed on read.
-- Safe to re-run.
-- =============================================================================

CREATE OR REPLACE VIEW v_fight_odds_consensus AS
WITH latest_per_book AS (
  SELECT DISTINCT ON (fight_id, side, book_id)
    fight_id,
    side,
    book_id,
    american_odds,
    implied_prob,
    captured_at
  FROM fight_odds
  WHERE captured_at > TIMESTAMPTZ '2010-01-01'   -- skip fake epoch opener rows
  ORDER BY fight_id, side, book_id, captured_at DESC
),
side_avg AS (
  SELECT
    fight_id,
    side,
    AVG(implied_prob)::numeric        AS avg_implied,   -- raw, vig-preserved
    COUNT(DISTINCT book_id)::integer  AS book_count,
    MAX(captured_at)                  AS latest_capture
  FROM latest_per_book
  GROUP BY fight_id, side
),
pivoted AS (
  SELECT
    a.fight_id,
    a.avg_implied                       AS raw_implied_a,   -- with vig
    b.avg_implied                       AS raw_implied_b,   -- with vig
    GREATEST(a.book_count, b.book_count) AS bookmaker_count,
    GREATEST(a.latest_capture, b.latest_capture) AS fetched_at
  FROM side_avg a
  JOIN side_avg b USING (fight_id)
  WHERE a.side = 'A' AND b.side = 'B'
)
SELECT
  p.fight_id,
  f.event_id,
  f.fighter_a_id,
  f.fighter_b_id,
  f.fighter_a_name,
  f.fighter_b_name,
  -- DISPLAY PRICES: back-derived from RAW (vig-preserved) consensus implied
  -- probability. Asymmetric, matches actual book lines.
  CASE
    WHEN p.raw_implied_a IS NULL THEN NULL
    WHEN p.raw_implied_a >= 0.5
      THEN ROUND(-100.0 * p.raw_implied_a / NULLIF(1 - p.raw_implied_a, 0))::integer
    ELSE  ROUND( 100.0 * (1 - p.raw_implied_a) / NULLIF(p.raw_implied_a, 0))::integer
  END AS american_odds_a,
  CASE
    WHEN p.raw_implied_b IS NULL THEN NULL
    WHEN p.raw_implied_b >= 0.5
      THEN ROUND(-100.0 * p.raw_implied_b / NULLIF(1 - p.raw_implied_b, 0))::integer
    ELSE  ROUND( 100.0 * (1 - p.raw_implied_b) / NULLIF(p.raw_implied_b, 0))::integer
  END AS american_odds_b,
  -- VIG-REMOVED FAIR PROBS: for model edge / value math. Sum to 1.0.
  (p.raw_implied_a / NULLIF(p.raw_implied_a + p.raw_implied_b, 0))::real AS implied_prob_a,
  (p.raw_implied_b / NULLIF(p.raw_implied_a + p.raw_implied_b, 0))::real AS implied_prob_b,
  -- RAW IMPLIED PROBS (with vig). Exposed for completeness; rarely needed
  -- directly since the display odds above already encode this.
  p.raw_implied_a::real AS implied_prob_a_raw,
  p.raw_implied_b::real AS implied_prob_b_raw,
  p.bookmaker_count,
  p.fetched_at
FROM pivoted p
JOIN fights f ON f.id = p.fight_id;

-- Public-data view: anon + authenticated must both have SELECT, otherwise
-- signed-in users see empty results with HTTP 200 and no error (per CLAUDE.md).
GRANT SELECT ON v_fight_odds_consensus TO anon, authenticated;
