-- =============================================================================
-- T-092 — v_fight_market_movement reads only the fights it is asked for
-- =============================================================================
-- NOT APPLIED. Changes a view three public pages read (Card Lab, Fight Lab,
-- Market Lab) and the alert sender (through v_fight_alert_market), so L3 under
-- CRITICAL_GATES item 5. Evidence: research/performance/T-092_MARKET_MOVEMENT_2026-10-15.md
--
-- WHY. The old view built every CTE over all ~96k fight_odds quotes, about five
-- times, and only then joined to the card it was asked for: 5.6 s for one card
-- against the browser roles' 8 s statement_timeout. Under a few concurrent page
-- loads it timed out (HTTP 500), 4 times on 2026-10-15.
--
-- WHAT. The same rules, computed per fight: the view is driven from `fights`
-- and every number comes from a LATERAL subquery that reads only that fight's
-- quotes, by index. A page's `event_id=eq.X` / `fight_id=eq.X` filter now
-- lands on fights' own indexes first. Measured on production 2026-10-15:
--   one card (event 4368)      5,646 ms -> 11.6 ms
--   one fight (53618)            755 ms ->  4.3 ms
--   whole view (120 fights)  > 5,600 ms ->  449 ms
--
-- NOTHING ABOUT THE ANSWER CHANGES. Same columns, names, types and order (so
-- CREATE OR REPLACE keeps v_fight_alert_market and every grant). Each
-- expression is the old one: D-012's matched cohort, the first broad capture
-- (third book's first quote), medians as percentile_cont over float8, the 24 h
-- horizon of v_fight_market_horizons, "best" ordered by the American number
-- and nothing else. Compared on production over all 120 fights: identical,
-- except best_book_a/_b on 22 fights where two or more books post the SAME
-- best price -- the old view's pick among tied books was arbitrary (array_agg
-- order of an unstable sort), and so is this one's.
--
-- SAFETY. One REPEATABLE READ transaction: snapshot the live output, replace
-- the view, assert the new output equals the snapshot under the rule above,
-- or RAISE and roll back. Rollback file restores the old definition verbatim.
-- =============================================================================

BEGIN ISOLATION LEVEL REPEATABLE READ;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '60s';

CREATE TEMP TABLE t092_before ON COMMIT DROP AS
  SELECT * FROM public.v_fight_market_movement;

CREATE OR REPLACE VIEW public.v_fight_market_movement AS
SELECT
  fi.id AS fight_id,
  fi.event_id,
  m.market_p_a,
  (1 - m.market_p_a)::numeric                                AS market_p_b,
  m.book_count,
  m.last_updated,
  m.oldest_current_quote_at,
  m.baseline_at,
  m.baseline_quote_at,
  COALESCE(m.baseline_book_count, 0)                         AS baseline_book_count,
  COALESCE(m.matched_book_count, 0)                          AS matched_book_count,
  CASE WHEN COALESCE(m.matched_book_count, 0) >= 3 THEN m.baseline_p_a END AS baseline_p_a,
  CASE WHEN COALESCE(m.matched_book_count, 0) >= 3 THEN (1 - m.baseline_p_a)::numeric END AS baseline_p_b,
  CASE WHEN COALESCE(m.matched_book_count, 0) >= 3 THEN m.matched_p_a END AS matched_current_p_a,
  CASE WHEN COALESCE(m.matched_book_count, 0) >= 3
       THEN ((m.matched_p_a - m.baseline_p_a) * 100)::numeric END AS movement_pts_a,
  CASE
    WHEN m.baseline_at IS NULL                        THEN 'no_broad_capture'
    WHEN COALESCE(m.matched_book_count, 0) < 3        THEN 'insufficient_matched_books'
    ELSE 'ok'
  END                                                        AS movement_status,
  'matched_cohort_median_vigfree_v1'::text                   AS movement_method,
  m.first_seen_at,
  m.capture_count,
  CASE WHEN m.book_count_24h >= 3 THEN m.then_p_a_24h END    AS market_p_a_24h,
  (1 - CASE WHEN m.book_count_24h >= 3 THEN m.then_p_a_24h END)::numeric AS market_p_b_24h,
  COALESCE(m.book_count_24h, 0)                              AS book_count_24h,
  m.best_american_a, m.best_book_a,
  m.best_american_b, m.best_book_b,
  m.worst_american_a, m.worst_american_b,
  m.book_spread_pts,
  CASE WHEN m.book_count_24h >= 3 THEN (m.now_p_a_24h - m.then_p_a_24h) * (100)::numeric END AS movement_pts_a_24h,
  CASE WHEN m.book_count_24h >= 3 THEN 'ok'::text ELSE 'insufficient_matched_books'::text END AS movement_status_24h
FROM public.fights fi
CROSS JOIN LATERAL (
  WITH q AS (
    -- v_fight_market_quotes, for this one fight
    SELECT a.fight_id, a.book_id, a.captured_at AS quoted_at,
           (a.implied_prob / (a.implied_prob + b.implied_prob)) AS fair_a,
           a.american_odds AS american_odds_a, b.american_odds AS american_odds_b
      FROM public.fight_odds a
      JOIN public.fight_odds b ON b.fight_id = a.fight_id AND b.book_id = a.book_id
                              AND b.captured_at = a.captured_at AND b.side = 'B'::bpchar
      JOIN public.v_odds_books_sportsbooks sb ON sb.id = a.book_id
     WHERE a.fight_id = fi.id
       AND a.side = 'A'::bpchar AND a.captured_at > '2010-01-01 00:00:00+00'::timestamptz
       AND a.implied_prob IS NOT NULL AND a.implied_prob > 0
       AND b.implied_prob IS NOT NULL AND b.implied_prob > 0
       AND a.is_live IS NOT TRUE AND b.is_live IS NOT TRUE
       AND (a.market_status IS NULL OR a.market_status = 'open')
       AND (b.market_status IS NULL OR b.market_status = 'open')
  ),
  base AS (
    -- v_fight_market_broad_baseline: the third book's first quote
    SELECT f.first_quoted_at AS baseline_at
      FROM (SELECT q.book_id, min(q.quoted_at) AS first_quoted_at FROM q GROUP BY q.book_id) f
     ORDER BY f.first_quoted_at, f.book_id
    OFFSET 2 LIMIT 1
  ),
  cur_c AS (
    SELECT DISTINCT ON (q.book_id) q.book_id, q.fair_a, q.quoted_at, q.american_odds_a, q.american_odds_b
      FROM q ORDER BY q.book_id, q.quoted_at DESC
  ),
  base_c AS (
    SELECT DISTINCT ON (q.book_id) q.book_id, q.fair_a, q.quoted_at
      FROM q, base WHERE q.quoted_at <= base.baseline_at
     ORDER BY q.book_id, q.quoted_at DESC
  ),
  then24 AS (
    SELECT DISTINCT ON (q.book_id) q.book_id, q.fair_a
      FROM q WHERE q.quoted_at <= (now() - '24:00:00'::interval)
     ORDER BY q.book_id, q.quoted_at DESC
  )
  SELECT
    (SELECT q.fight_id FROM q LIMIT 1)                                        AS fight_id,
    (SELECT (percentile_cont(0.5) WITHIN GROUP (ORDER BY c.fair_a))::numeric FROM cur_c c) AS market_p_a,
    (SELECT COUNT(*)::integer FROM cur_c c JOIN public.v_odds_books_sportsbooks sb ON sb.id = c.book_id) AS book_count,
    (SELECT MAX(c.quoted_at) FROM cur_c c)                                    AS last_updated,
    (SELECT MIN(c.quoted_at) FROM cur_c c)                                    AS oldest_current_quote_at,
    (SELECT ((MAX(c.fair_a) - MIN(c.fair_a)) * 100)::numeric FROM cur_c c)    AS book_spread_pts,
    (SELECT MAX(c.american_odds_a) FROM cur_c c)                              AS best_american_a,
    (SELECT (array_agg(sb.name ORDER BY c.american_odds_a DESC))[1]
       FROM cur_c c JOIN public.v_odds_books_sportsbooks sb ON sb.id = c.book_id) AS best_book_a,
    (SELECT MAX(c.american_odds_b) FROM cur_c c)                              AS best_american_b,
    (SELECT (array_agg(sb.name ORDER BY c.american_odds_b DESC))[1]
       FROM cur_c c JOIN public.v_odds_books_sportsbooks sb ON sb.id = c.book_id) AS best_book_b,
    (SELECT MIN(c.american_odds_a) FROM cur_c c)                              AS worst_american_a,
    (SELECT MIN(c.american_odds_b) FROM cur_c c)                              AS worst_american_b,
    (SELECT base.baseline_at FROM base)                                       AS baseline_at,
    (SELECT NULLIF(COUNT(*), 0)::integer FROM base_c)                         AS baseline_book_count,
    (SELECT NULLIF(COUNT(*), 0)::integer FROM base_c b JOIN cur_c c ON c.book_id = b.book_id) AS matched_book_count,
    (SELECT (percentile_cont(0.5) WITHIN GROUP (ORDER BY b.fair_a))::numeric
       FROM base_c b JOIN cur_c c ON c.book_id = b.book_id)                   AS baseline_p_a,
    (SELECT (percentile_cont(0.5) WITHIN GROUP (ORDER BY c.fair_a))::numeric
       FROM base_c b JOIN cur_c c ON c.book_id = b.book_id)                   AS matched_p_a,
    (SELECT MAX(b.quoted_at) FROM base_c b JOIN cur_c c ON c.book_id = b.book_id) AS baseline_quote_at,
    (SELECT MIN(q.quoted_at) FROM q)                                          AS first_seen_at,
    (SELECT COUNT(DISTINCT q.quoted_at)::integer FROM q)                      AS capture_count,
    (SELECT NULLIF(COUNT(*), 0)::integer FROM then24 t JOIN cur_c c ON c.book_id = t.book_id) AS book_count_24h,
    (SELECT (percentile_cont((0.5)::double precision) WITHIN GROUP (ORDER BY (t.fair_a)::double precision))::numeric
       FROM then24 t JOIN cur_c c ON c.book_id = t.book_id)                   AS then_p_a_24h,
    (SELECT (percentile_cont((0.5)::double precision) WITHIN GROUP (ORDER BY (c.fair_a)::double precision))::numeric
       FROM then24 t JOIN cur_c c ON c.book_id = t.book_id)                   AS now_p_a_24h
) m
WHERE m.fight_id IS NOT NULL;

COMMENT ON VIEW public.v_fight_market_movement IS
  'Vig-free market movement since the first broad CFL capture, computed over '
  'the books present at BOTH ends (matched cohort), NULL below 3 matched books. '
  'baseline_at and first_seen_at are never an opening line. Computed per fight '
  '(T-092): filter by fight_id or event_id. See market_movement_views.sql.';

GRANT SELECT ON public.v_fight_market_movement TO anon, authenticated;

DO $assert$
DECLARE
  n_before int; n_after int; n_rows_diff int; n_vals_diff int; n_book_not_tie int;
BEGIN
  CREATE TEMP TABLE t092_after ON COMMIT DROP AS SELECT * FROM public.v_fight_market_movement;
  SELECT count(*) INTO n_before FROM t092_before;
  SELECT count(*) INTO n_after  FROM t092_after;

  SELECT count(*) INTO n_rows_diff FROM t092_before b FULL JOIN t092_after a USING (fight_id)
   WHERE b.fight_id IS NULL OR a.fight_id IS NULL;

  SELECT count(*) INTO n_vals_diff FROM t092_before b JOIN t092_after a USING (fight_id)
   WHERE (to_jsonb(b) - 'best_book_a' - 'best_book_b') IS DISTINCT FROM (to_jsonb(a) - 'best_book_a' - 'best_book_b');

  -- A different best book is allowed only when both books post that same best price.
  WITH latest AS (
    SELECT DISTINCT ON (q.fight_id, q.book_id) q.fight_id, sb.name, q.american_odds_a, q.american_odds_b
      FROM public.v_fight_market_quotes q JOIN public.v_odds_books_sportsbooks sb ON sb.id = q.book_id
     ORDER BY q.fight_id, q.book_id, q.quoted_at DESC)
  SELECT count(*) INTO n_book_not_tie FROM t092_before b JOIN t092_after a USING (fight_id)
   WHERE (b.best_book_a IS DISTINCT FROM a.best_book_a AND NOT EXISTS (
            SELECT 1 FROM latest l1 JOIN latest l2 USING (fight_id)
             WHERE l1.fight_id = b.fight_id AND l1.name = b.best_book_a AND l2.name = a.best_book_a
               AND l1.american_odds_a = b.best_american_a AND l2.american_odds_a = a.best_american_a))
      OR (b.best_book_b IS DISTINCT FROM a.best_book_b AND NOT EXISTS (
            SELECT 1 FROM latest l1 JOIN latest l2 USING (fight_id)
             WHERE l1.fight_id = b.fight_id AND l1.name = b.best_book_b AND l2.name = a.best_book_b
               AND l1.american_odds_b = b.best_american_b AND l2.american_odds_b = a.best_american_b));

  IF n_before <> n_after OR n_rows_diff <> 0 OR n_vals_diff <> 0 OR n_book_not_tie <> 0 THEN
    RAISE EXCEPTION 'T-092 aborted: before % rows, after % rows, % unmatched, % differing, % book changes not ties',
      n_before, n_after, n_rows_diff, n_vals_diff, n_book_not_tie;
  END IF;
END
$assert$;

COMMIT;
