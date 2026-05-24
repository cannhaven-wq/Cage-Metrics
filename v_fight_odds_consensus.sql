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
--   cron, average the implied probabilities across books per side, vig-remove
--   by normalizing the two sides to sum to 1.0, and back-derive a "consensus"
--   American odds for display.
--
--   Filters out fake epoch (1970) opener rows produced by historical backfills,
--   so only real polled data feeds the consensus.
--
-- Read by: index.html (loadOddsMap), event.html (renderEvent).
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
    AVG(implied_prob)::numeric        AS avg_implied,
    COUNT(DISTINCT book_id)::integer  AS book_count,
    MAX(captured_at)                  AS latest_capture
  FROM latest_per_book
  GROUP BY fight_id, side
),
pivoted AS (
  SELECT
    a.fight_id,
    a.avg_implied                       AS raw_implied_a,
    b.avg_implied                       AS raw_implied_b,
    GREATEST(a.book_count, b.book_count) AS bookmaker_count,
    GREATEST(a.latest_capture, b.latest_capture) AS fetched_at
  FROM side_avg a
  JOIN side_avg b USING (fight_id)
  WHERE a.side = 'A' AND b.side = 'B'
),
devigged AS (
  SELECT
    fight_id,
    -- vig-remove: normalize so the two sides sum to 1.0
    (raw_implied_a / NULLIF(raw_implied_a + raw_implied_b, 0))::real AS implied_prob_a,
    (raw_implied_b / NULLIF(raw_implied_a + raw_implied_b, 0))::real AS implied_prob_b,
    bookmaker_count,
    fetched_at
  FROM pivoted
)
SELECT
  d.fight_id,
  f.event_id,
  f.fighter_a_id,
  f.fighter_b_id,
  f.fighter_a_name,
  f.fighter_b_name,
  -- back-derive American odds from the vig-removed implied prob
  CASE
    WHEN d.implied_prob_a IS NULL THEN NULL
    WHEN d.implied_prob_a >= 0.5
      THEN ROUND(-100.0 * d.implied_prob_a / NULLIF(1 - d.implied_prob_a, 0))::integer
    ELSE  ROUND( 100.0 * (1 - d.implied_prob_a) / NULLIF(d.implied_prob_a, 0))::integer
  END AS american_odds_a,
  CASE
    WHEN d.implied_prob_b IS NULL THEN NULL
    WHEN d.implied_prob_b >= 0.5
      THEN ROUND(-100.0 * d.implied_prob_b / NULLIF(1 - d.implied_prob_b, 0))::integer
    ELSE  ROUND( 100.0 * (1 - d.implied_prob_b) / NULLIF(d.implied_prob_b, 0))::integer
  END AS american_odds_b,
  d.implied_prob_a,
  d.implied_prob_b,
  d.bookmaker_count,
  d.fetched_at
FROM devigged d
JOIN fights f ON f.id = d.fight_id;

-- Public-data view: anon + authenticated must both have SELECT, otherwise
-- signed-in users see empty results with HTTP 200 and no error (per CLAUDE.md).
GRANT SELECT ON v_fight_odds_consensus TO anon, authenticated;
