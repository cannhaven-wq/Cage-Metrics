-- =============================================================================
-- fight_week_views.sql — the read layer behind the Event Hub, fight pages and
-- the Market Board (September 2026, fight-week-v2).
-- =============================================================================
-- Four views, all read-only, all computed on read. Nothing here writes, and
-- nothing here changes an existing view — v_fight_odds_consensus is left
-- exactly as it was.
--
--   v_fight_locked_forecast    the CFL number for a fight, from the locked
--                              pre-fight record only (pre_fight_snapshots, or
--                              the insert-only model_picks live row while the
--                              snapshot has not been taken yet). NEVER computed
--                              at page render.
--   v_fight_market_vigfree     the market's number with the book's cut removed,
--                              from real sportsbooks only, with the book count
--                              and the last time a quote landed.
--   v_fight_market_at_lock     the same vig-free number, but using only quotes
--                              captured at or before the forecast was locked —
--                              so "line movement since lock" is a real
--                              before/after and not a guess.
--   v_fight_odds_latest_by_book  the latest quote from each real sportsbook on
--                              fights from cards in the last two weeks or
--                              upcoming, for the Market Board's price watch.
--
-- Why a new vig-free view instead of reading implied_prob_a/b off
-- v_fight_odds_consensus: that view averages every row in fight_odds, and
-- fight_odds also holds the synthetic "CFL Consensus (Odds API)" median row
-- (so the consensus is counted twice) and prediction-market prices (Polymarket,
-- Kalshi), and its bookmaker_count counts all of them. A page that says
-- "7 books" off that number would be saying something untrue. The views below
-- use sportsbook quotes only, de-vig each book's pair on its own, then take the
-- median across books.
--
-- fight_odds and odds_books have no SELECT policy for anon (admin-only), so
-- these views run with the definer's rights the same way v_fight_odds_consensus
-- does. That is deliberate and documented: they expose only the aggregated,
-- per-fight numbers the site has always shown, plus the latest per-book quote
-- for the current card window.
--
-- Safe to re-run.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Real sportsbooks: everything in odds_books except our own synthetic median
-- row and the prediction markets. Mirrored in books.js (SPORTSBOOK_EXCLUDE) —
-- keep the two lists in step.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_odds_books_sportsbooks AS
SELECT id, name, short_code
FROM public.odds_books
WHERE name NOT ILIKE '%consensus%'
  AND lower(name) NOT IN ('polymarket', 'kalshi');

GRANT SELECT ON public.v_odds_books_sportsbooks TO anon, authenticated;

-- ---------------------------------------------------------------------------
-- The locked CFL forecast, one row per fight that has one.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_fight_locked_forecast AS
WITH live AS (
  -- model_picks is insert-only; one live row per fight (earliest wins if the
  -- guarantee ever slips).
  SELECT DISTINCT ON (fight_id)
    fight_id, pick_side, pick_fighter_id, p_cal, tier, model_version, published_at
  FROM public.model_picks
  WHERE source = 'live'
  ORDER BY fight_id, published_at ASC, id ASC
),
snap AS (
  SELECT fight_id, snapshot_at, snapshot_label, engine_pick_side, engine_pick_fighter_id,
         engine_p_cal, engine_tier, engine_model_version, engine_published_at,
         implied_prob_a, implied_prob_b, bookmaker_count, odds_fetched_at
  FROM public.pre_fight_snapshots
  WHERE engine_p_cal IS NOT NULL
)
SELECT
  f.id                                                     AS fight_id,
  f.event_id,
  f.fighter_a_id,
  f.fighter_b_id,
  f.fighter_a_name,
  f.fighter_b_name,
  COALESCE(s.engine_pick_side, l.pick_side)                AS pick_side,
  COALESCE(s.engine_pick_fighter_id, l.pick_fighter_id)    AS pick_fighter_id,
  -- Probability for each corner, derived from the locked pick-side number.
  CASE WHEN COALESCE(s.engine_pick_side, l.pick_side) = 'a'
       THEN COALESCE(s.engine_p_cal, l.p_cal)
       ELSE 1 - COALESCE(s.engine_p_cal, l.p_cal) END::numeric AS cfl_p_a,
  CASE WHEN COALESCE(s.engine_pick_side, l.pick_side) = 'b'
       THEN COALESCE(s.engine_p_cal, l.p_cal)
       ELSE 1 - COALESCE(s.engine_p_cal, l.p_cal) END::numeric AS cfl_p_b,
  COALESCE(s.engine_tier, l.tier)                          AS tier,
  COALESCE(s.engine_model_version, l.model_version)        AS model_version,
  -- When the forecast was first written. The snapshot re-records the same
  -- number later; the lock time is the first write.
  COALESCE(l.published_at, s.engine_published_at, s.snapshot_at) AS locked_at,
  CASE WHEN s.fight_id IS NOT NULL THEN 'snapshot' ELSE 'model_picks_live' END AS record_source,
  s.snapshot_at,
  s.snapshot_label,
  s.implied_prob_a                                          AS snapshot_market_p_a,
  s.implied_prob_b                                          AS snapshot_market_p_b,
  s.bookmaker_count                                         AS snapshot_book_count,
  s.odds_fetched_at                                         AS snapshot_odds_at,
  f.winner_id,
  f.method,
  f.end_round,
  f.end_time,
  CASE WHEN f.winner_id IS NULL THEN NULL
       ELSE f.winner_id = COALESCE(s.engine_pick_fighter_id, l.pick_fighter_id) END AS forecast_hit
FROM public.fights f
LEFT JOIN snap s ON s.fight_id = f.id
LEFT JOIN live l ON l.fight_id = f.id
WHERE s.fight_id IS NOT NULL OR l.fight_id IS NOT NULL;

GRANT SELECT ON public.v_fight_locked_forecast TO anon, authenticated;

-- ---------------------------------------------------------------------------
-- Vig-free market number, current: latest quote per real sportsbook, each
-- book's pair normalised on its own, median across books.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_fight_market_vigfree AS
WITH latest AS (
  SELECT DISTINCT ON (o.fight_id, o.book_id, o.side)
    o.fight_id, o.book_id, o.side, o.american_odds, o.implied_prob, o.captured_at
  FROM public.fight_odds o
  JOIN public.v_odds_books_sportsbooks b ON b.id = o.book_id
  WHERE o.captured_at > TIMESTAMPTZ '2010-01-01'   -- skip fake epoch opener rows
    AND o.implied_prob IS NOT NULL AND o.implied_prob > 0
  ORDER BY o.fight_id, o.book_id, o.side, o.captured_at DESC
),
pairs AS (
  SELECT a.fight_id, a.book_id,
         a.implied_prob / (a.implied_prob + b.implied_prob) AS fair_a,
         GREATEST(a.captured_at, b.captured_at)              AS captured_at
  FROM latest a
  JOIN latest b ON b.fight_id = a.fight_id AND b.book_id = a.book_id AND b.side = 'B'
  WHERE a.side = 'A'
)
SELECT
  p.fight_id,
  f.event_id,
  (percentile_cont(0.5) WITHIN GROUP (ORDER BY p.fair_a))::numeric        AS market_p_a,
  (1 - percentile_cont(0.5) WITHIN GROUP (ORDER BY p.fair_a))::numeric    AS market_p_b,
  COUNT(*)::integer                                                       AS book_count,
  MAX(p.captured_at)                                                      AS last_updated,
  MIN(p.captured_at)                                                      AS oldest_quote_at
FROM pairs p
JOIN public.fights f ON f.id = p.fight_id
GROUP BY p.fight_id, f.event_id;

GRANT SELECT ON public.v_fight_market_vigfree TO anon, authenticated;

-- ---------------------------------------------------------------------------
-- v_fight_market_at_lock — SUPERSEDED 2026-09-21 (T-046). Defined in
-- market_horizon_views.sql; this file no longer creates it.
-- ---------------------------------------------------------------------------
-- The definition that stood here compared a median over the books captured by
-- the forecast-lock instant against a median over the books quoting now. Those
-- are different cohorts. Measured on the live table: of 14 fights with a lock,
-- 4 had a different cohort at the two ends, 1 rested on a SINGLE book at lock,
-- and the worst disagreement against a matched cohort was 5.2 points.
--
-- It is now built from `v_fight_market_horizons`, which holds the one
-- matched-cohort intersection every movement figure on the site is built from,
-- and it publishes `matched_book_count_at_lock` and `movement_status_at_lock`
-- so a reader can see the cohort behind the number.
--
-- Two files defining one view is how the two drift — the same lesson
-- market_lab_views.sql learned on the same day. The original text is in git
-- history and is not reproduced here.
--
-- Note it is research-layer only: the forecast is off every public surface
-- (D-011), so "since lock" answers a question about CFL, not about the product.

-- ---------------------------------------------------------------------------
-- Latest quote per real sportsbook, current card window only (events dated
-- within the last 14 days or upcoming). Feeds the Market Board price watch.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_fight_odds_latest_by_book AS
WITH window_fights AS (
  SELECT f.id AS fight_id, f.event_id
  FROM public.fights f
  JOIN public.events e ON e.id = f.event_id
  WHERE e.event_date >= CURRENT_DATE - 14
),
latest AS (
  SELECT DISTINCT ON (o.fight_id, o.book_id, o.side)
    o.fight_id, o.book_id, o.side, o.american_odds, o.implied_prob, o.captured_at
  FROM public.fight_odds o
  JOIN window_fights w ON w.fight_id = o.fight_id
  JOIN public.v_odds_books_sportsbooks b ON b.id = o.book_id
  WHERE o.captured_at > TIMESTAMPTZ '2010-01-01'
    AND o.implied_prob IS NOT NULL AND o.implied_prob > 0
  ORDER BY o.fight_id, o.book_id, o.side, o.captured_at DESC
)
SELECT
  a.fight_id,
  w.event_id,
  a.book_id,
  b.name                                                   AS book_name,
  b.short_code                                             AS book_code,
  a.american_odds                                          AS american_odds_a,
  bb.american_odds                                         AS american_odds_b,
  (a.implied_prob / (a.implied_prob + bb.implied_prob))::numeric  AS fair_prob_a,
  (bb.implied_prob / (a.implied_prob + bb.implied_prob))::numeric AS fair_prob_b,
  GREATEST(a.captured_at, bb.captured_at)                  AS captured_at
FROM latest a
JOIN latest bb ON bb.fight_id = a.fight_id AND bb.book_id = a.book_id AND bb.side = 'B'
JOIN window_fights w ON w.fight_id = a.fight_id
JOIN public.v_odds_books_sportsbooks b ON b.id = a.book_id
WHERE a.side = 'A';

GRANT SELECT ON public.v_fight_odds_latest_by_book TO anon, authenticated;
