-- =============================================================================
-- T-085 (2026-10-13): v_fight_chart_series — cohort CTE NOT MATERIALIZED
-- =============================================================================
-- Only this view changes. Its source of truth stays market_chart_views.sql;
-- this file applies just the change, so the other chart views are not
-- re-created. Output is identical (md5 matched on 8 fights); one fight takes
-- 0.26 s instead of 5.8 s. Evidence:
-- research/data-integrity/T-085_CHART_SERIES_PERF_2026-10-13.md
--
-- SECURITY. This view stays SECURITY DEFINER (owner postgres) on purpose:
-- fight_odds is admin-only for both browser roles, and the market views are
-- the sanctioned definer path to it (CLAUDE.md, Data layer). Grants are
-- RESET to SELECT-only. Production had anon and authenticated holding
-- arwdDxtm on this view. That was not exploitable (an aggregate view is not
-- auto-updatable), but it was wider than needed.
--
-- ROLLBACK: chart_series_t085.rollback.sql restores the previous definition.
-- Safe to re-run.
-- =============================================================================

CREATE OR REPLACE VIEW public.v_fight_chart_series AS
-- NOT MATERIALIZED is load-bearing: see §Performance, 2026-10-13 correction.
WITH cohort AS NOT MATERIALIZED (
  SELECT h.fight_id, h.book_id
  FROM public.v_fight_market_horizon_cohorts h
  JOIN public.v_fight_chart_meta m
    ON m.fight_id = h.fight_id AND m.series_status = 'ok'
  WHERE h.horizon = 'broad_baseline'
),
ticks AS (
  SELECT DISTINCT q.fight_id, q.quoted_at AS at
  FROM public.v_fight_market_quotes q
  JOIN cohort c ON c.fight_id = q.fight_id AND c.book_id = q.book_id
  JOIN public.v_fight_chart_meta m ON m.fight_id = q.fight_id
  WHERE q.quoted_at >= m.window_start
),
-- each cohort book's standing price at each tick (§ "carrying a price forward")
standing AS (
  SELECT DISTINCT ON (t.fight_id, t.at, c.book_id)
    t.fight_id, t.at, c.book_id, q.fair_a
  FROM ticks t
  JOIN cohort c ON c.fight_id = t.fight_id
  JOIN public.v_fight_market_quotes q
    ON q.fight_id = c.fight_id AND q.book_id = c.book_id AND q.quoted_at <= t.at
  ORDER BY t.fight_id, t.at, c.book_id, q.quoted_at DESC
)
SELECT
  fight_id,
  at,
  (percentile_cont(0.5) WITHIN GROUP (ORDER BY fair_a))::numeric        AS market_p_a,
  (1 - percentile_cont(0.5) WITHIN GROUP (ORDER BY fair_a))::numeric    AS market_p_b,
  COUNT(*)::integer                                                     AS cohort_books
FROM standing
GROUP BY fight_id, at;

COMMENT ON VIEW public.v_fight_chart_series IS
  'Vig-free consensus over time on a FIXED cohort: the books quoting both at '
  'the first broad CFL capture and now. cohort_books is constant across a '
  'fight by construction. No rows when the cohort is under 3 - the series is '
  'refused rather than drawn on a shifting set of books.';

REVOKE ALL ON public.v_fight_chart_series FROM anon, authenticated, PUBLIC;
GRANT SELECT ON public.v_fight_chart_series TO anon, authenticated;
