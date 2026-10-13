-- =============================================================================
-- ROLLBACK for chart_series_t085.sql — restores v_fight_chart_series exactly as
-- production defined it before T-085 (pg_get_viewdef, 2026-10-13): the
-- materialised `cohort` CTE. Grants stay SELECT-only; the rollback does not
-- re-widen them. Output is identical either way, only the speed differs.
-- Safe to re-run.
-- =============================================================================

CREATE OR REPLACE VIEW public.v_fight_chart_series AS
 WITH cohort AS (
         SELECT h.fight_id,
            h.book_id
           FROM v_fight_market_horizon_cohorts h
             JOIN v_fight_chart_meta m ON m.fight_id = h.fight_id AND m.series_status = 'ok'::text
          WHERE h.horizon = 'broad_baseline'::text
        ), ticks AS (
         SELECT DISTINCT q.fight_id,
            q.quoted_at AS at
           FROM v_fight_market_quotes q
             JOIN cohort c ON c.fight_id = q.fight_id AND c.book_id = q.book_id
             JOIN v_fight_chart_meta m ON m.fight_id = q.fight_id
          WHERE q.quoted_at >= m.window_start
        ), standing AS (
         SELECT DISTINCT ON (t.fight_id, t.at, c.book_id) t.fight_id,
            t.at,
            c.book_id,
            q.fair_a
           FROM ticks t
             JOIN cohort c ON c.fight_id = t.fight_id
             JOIN v_fight_market_quotes q ON q.fight_id = c.fight_id AND q.book_id = c.book_id AND q.quoted_at <= t.at
          ORDER BY t.fight_id, t.at, c.book_id, q.quoted_at DESC
        )
 SELECT fight_id,
    at,
    percentile_cont(0.5::double precision) WITHIN GROUP (ORDER BY (fair_a::double precision))::numeric AS market_p_a,
    (1::double precision - percentile_cont(0.5::double precision) WITHIN GROUP (ORDER BY (fair_a::double precision)))::numeric AS market_p_b,
    count(*)::integer AS cohort_books
   FROM standing
  GROUP BY fight_id, at;

REVOKE ALL ON public.v_fight_chart_series FROM anon, authenticated;
GRANT SELECT ON public.v_fight_chart_series TO anon, authenticated;
