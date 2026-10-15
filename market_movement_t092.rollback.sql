-- Rollback for market_movement_t092.sql: restores v_fight_market_movement to
-- the definition in market_movement_views.sql (D-012, applied 2026-09-21; the
-- production text hashed md5 eaa359c191adee7db809e6ca33f4d590 under
-- pg_get_viewdef on 2026-10-15). Same columns, so dependents and grants stay.
-- No data is touched. Safe to re-run.

BEGIN;
SET LOCAL lock_timeout = '3s';
CREATE OR REPLACE VIEW public.v_fight_market_movement AS
WITH base AS (
  SELECT * FROM public.v_fight_market_broad_baseline
),
-- each book's latest quote at or before the first broad capture instant
baseline_cohort AS (
  SELECT DISTINCT ON (q.fight_id, q.book_id)
    q.fight_id, q.book_id, q.fair_a, q.quoted_at
  FROM public.v_fight_market_quotes q
  JOIN base ON base.fight_id = q.fight_id
  WHERE q.quoted_at <= base.baseline_at
  ORDER BY q.fight_id, q.book_id, q.quoted_at DESC
),
-- each book's latest quote overall
current_cohort AS (
  SELECT DISTINCT ON (q.fight_id, q.book_id)
    q.fight_id, q.book_id, q.fair_a, q.quoted_at,
    q.american_odds_a, q.american_odds_b
  FROM public.v_fight_market_quotes q
  ORDER BY q.fight_id, q.book_id, q.quoted_at DESC
),

-- THE MATCHED COHORT: books quoting at BOTH ends. A book that has since pulled
-- the market leaves both sides of the comparison, never just one.
matched AS (
  SELECT b.fight_id, b.book_id,
         b.fair_a     AS baseline_fair_a,
         b.quoted_at  AS baseline_quoted_at,
         c.fair_a     AS current_fair_a,
         c.quoted_at  AS current_quoted_at
  FROM baseline_cohort b
  JOIN current_cohort c
    ON c.fight_id = b.fight_id AND c.book_id = b.book_id
),
agg AS (
  SELECT m.fight_id,
    COUNT(*)::integer                                                         AS matched_book_count,
    (percentile_cont(0.5) WITHIN GROUP (ORDER BY m.baseline_fair_a))::numeric AS baseline_p_a,
    (percentile_cont(0.5) WITHIN GROUP (ORDER BY m.current_fair_a))::numeric  AS matched_p_a,
    MAX(m.baseline_quoted_at)                                                 AS baseline_quote_at
  FROM matched m GROUP BY m.fight_id
),
cur AS (
  SELECT c.fight_id,
    (percentile_cont(0.5) WITHIN GROUP (ORDER BY c.fair_a))::numeric AS market_p_a,
    COUNT(*)::integer                                                 AS book_count,
    MAX(c.quoted_at)                                                  AS last_updated,
    MIN(c.quoted_at)                                                  AS oldest_current_quote_at,
    ((MAX(c.fair_a) - MIN(c.fair_a)) * 100)::numeric                  AS book_spread_pts,
    MAX(c.american_odds_a)                                            AS best_american_a,
    (array_agg(sb.name ORDER BY c.american_odds_a DESC))[1]           AS best_book_a,
    MAX(c.american_odds_b)                                            AS best_american_b,
    (array_agg(sb.name ORDER BY c.american_odds_b DESC))[1]           AS best_book_b,
    MIN(c.american_odds_a)                                            AS worst_american_a,
    MIN(c.american_odds_b)                                            AS worst_american_b
  FROM current_cohort c
  JOIN public.v_odds_books_sportsbooks sb ON sb.id = c.book_id
  GROUP BY c.fight_id
),
-- The 24-hour horizon, from the shared matched-cohort rule (T-046). NOT a
-- median over "every book with an old quote" — that was the defect.
back24 AS (
  SELECT fight_id,
    then_p_a           AS market_p_a_24h,
    matched_book_count AS book_count_24h,
    movement_pts_a     AS movement_pts_a_24h,
    movement_status    AS movement_status_24h
  FROM public.v_fight_market_horizons
  WHERE horizon = 'h24'
),
base_counts AS (
  SELECT fight_id, COUNT(*)::integer AS baseline_book_count
  FROM baseline_cohort GROUP BY fight_id
),
seen AS (
  SELECT fight_id, MIN(quoted_at) AS first_seen_at,
         COUNT(DISTINCT quoted_at)::integer AS capture_count
  FROM public.v_fight_market_quotes GROUP BY fight_id
)
SELECT
  s.fight_id,
  fi.event_id,
  -- current market
  cur.market_p_a,
  (1 - cur.market_p_a)::numeric                              AS market_p_b,
  cur.book_count,
  cur.last_updated,
  cur.oldest_current_quote_at,
  -- the honest baseline
  base.baseline_at,
  agg.baseline_quote_at,
  COALESCE(bc.baseline_book_count, 0)                        AS baseline_book_count,
  COALESCE(agg.matched_book_count, 0)                        AS matched_book_count,
  CASE WHEN COALESCE(agg.matched_book_count, 0) >= 3
       THEN agg.baseline_p_a END                             AS baseline_p_a,
  CASE WHEN COALESCE(agg.matched_book_count, 0) >= 3
       THEN (1 - agg.baseline_p_a)::numeric END              AS baseline_p_b,
  CASE WHEN COALESCE(agg.matched_book_count, 0) >= 3
       THEN agg.matched_p_a END                              AS matched_current_p_a,
  CASE WHEN COALESCE(agg.matched_book_count, 0) >= 3
       THEN ((agg.matched_p_a - agg.baseline_p_a) * 100)::numeric END AS movement_pts_a,
  CASE
    WHEN base.fight_id IS NULL                      THEN 'no_broad_capture'
    WHEN COALESCE(agg.matched_book_count, 0) < 3    THEN 'insufficient_matched_books'
    ELSE 'ok'
  END                                                        AS movement_status,
  'matched_cohort_median_vigfree_v1'                         AS movement_method,
  -- CFL's own earliest sighting. Honestly named: NOT an opening line.
  s.first_seen_at,
  s.capture_count,
  -- 24h lookback, matched cohort (T-046). market_p_a_24h is the median across
  -- the books quoting BOTH 24 h ago and now — not across whichever books
  -- happened to have an old quote.
  b24.market_p_a_24h,
  (1 - b24.market_p_a_24h)::numeric                          AS market_p_b_24h,
  COALESCE(b24.book_count_24h, 0)                            AS book_count_24h,
  -- best observed price, mechanically the best American number on offer.
  -- No commercial input of any kind reaches this ordering.
  cur.best_american_a, cur.best_book_a,
  cur.best_american_b, cur.best_book_b,
  cur.worst_american_a, cur.worst_american_b,
  cur.book_spread_pts,
  -- appended by T-046: the 24 h move computed in SQL over the matched cohort,
  -- so a surface subtracts nothing and cannot mix two cohorts by accident.
  b24.movement_pts_a_24h,
  COALESCE(b24.movement_status_24h, 'insufficient_matched_books') AS movement_status_24h
FROM seen s
JOIN public.fights fi    ON fi.id      = s.fight_id
JOIN cur                 ON cur.fight_id = s.fight_id
LEFT JOIN base           ON base.fight_id = s.fight_id
LEFT JOIN agg            ON agg.fight_id  = s.fight_id
LEFT JOIN base_counts bc ON bc.fight_id   = s.fight_id
LEFT JOIN back24 b24     ON b24.fight_id  = s.fight_id;

COMMENT ON VIEW public.v_fight_market_movement IS
  'Vig-free market movement since the first broad CFL capture, computed over '
  'the books present at BOTH ends (matched cohort), NULL below 3 matched books. '
  'baseline_at and first_seen_at are never an opening line. See '
  'market_movement_views.sql.';

GRANT SELECT ON public.v_fight_market_movement TO anon, authenticated;

COMMIT;
