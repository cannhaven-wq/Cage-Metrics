-- =============================================================================
-- market_chart_views.sql — the movement chart's data, on a fixed cohort.
-- Applied 2026-09-21. Safe to re-run.
-- =============================================================================
-- PLAIN ENGLISH: the line on the chart is the middle sportsbook price over
-- time. Every point on that line is computed from THE SAME sportsbooks — the
-- ones quoting both at the start of the window and now. If a book joins
-- halfway through, it does not join the line halfway through, because a line
-- that gains a book mid-flight shows a step that no market actually made.
--
-- Under that line, each sportsbook can be drawn on its own, using its own real
-- quotes. Those are observations, not an average, so they need no cohort.
--
-- -----------------------------------------------------------------------------
-- §The fixed cohort, and why it is not a new idea
-- -----------------------------------------------------------------------------
-- The chart cohort IS the `broad_baseline` matched cohort from
-- market_horizon_views.sql (T-046) — the books quoting both at the first broad
-- CFL capture and now. Nothing new is defined here.
--
-- That also fixes the window for free. The plot starts at `baseline_at`, the
-- instant a third sportsbook first priced the fight. Before that moment there
-- were fewer than three books, so there was never a defensible consensus to
-- draw; starting earlier would mean drawing one or two books and calling it
-- the market.
--
-- MIN_BOOKS is 3. Below it `v_fight_chart_meta.series_status` is
-- `insufficient_matched_books` and `v_fight_chart_series` returns NO ROWS for
-- that fight. The series is refused, not thinned, not interpolated, and not
-- quietly recomputed on a different cohort.
--
-- §Carrying a price forward is not interpolation
-- Between its own quotes a sportsbook's price does not move — the number it
-- posted is the number standing until it posts another. So each cohort book
-- contributes its latest quote at or before each tick. That is the price that
-- was actually on the board, not a guess between two points. Nothing here
-- invents a value a book never posted, and nothing is smoothed.
--
-- §Ticks
-- One point per instant at which any COHORT book quoted, inside the window. No
-- fixed grid and no resampling: every x is a real capture, so the chart cannot
-- show a movement at a time when nothing was captured. A fight averages ~107
-- such instants and the busiest has 892 — small enough to send whole.
--
-- §Performance — READ THIS BEFORE ADDING A SECOND CHART
--
-- `v_fight_market_quotes` was rewritten the same day to drop a
-- multiply-referenced CTE. That CTE was an optimization fence:
-- `WHERE fight_id = X` could not push through it, so every reference re-scanned
-- ~85k rows. As a direct self-join the predicate reaches
-- `idx_fight_odds_fight_book_time`. Measured on the live database:
--
--     one fight, literal fight_id = X ...........   22 ms   (was 3,412 ms)
--     twelve fights, literal IN (...) ........... 4,607 ms
--     `fight_id IN (SELECT ...)` ................ times out (>60 s)
--     whole view, no predicate .................. times out (>60 s)
--
-- **`v_fight_chart_series` IS A SINGLE-FIGHT VIEW.** Query it with one literal
-- `fight_id` and nothing else. The cost is superlinear in the number of fights,
-- because with several ids the cohort CTE loses its per-fight index path, and a
-- subquery predicate does not push down at all.
--
-- That is why the chart lives on Fight Lab, one fight to a page, and why
-- Market Lab has **no** per-row sparkline. A twelve-row board would cost 4.6
-- seconds. If card-wide charts are ever wanted, this view is the wrong shape
-- for them: it needs a materialized view refreshed on capture, or a
-- set-returning function called once per fight. Queued rather than guessed at.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Per-fight chart metadata: the window, the cohort, and whether we will
--    draw a consensus line at all. A surface reads this FIRST and renders the
--    refusal from it without fetching a series it is not going to get.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_fight_chart_meta AS
WITH cohort AS (
  SELECT fight_id, COUNT(*)::integer AS cohort_books
  FROM public.v_fight_market_horizon_cohorts
  WHERE horizon = 'broad_baseline'
  GROUP BY fight_id
),
span AS (
  SELECT q.fight_id, MIN(q.quoted_at) AS first_seen_at, MAX(q.quoted_at) AS last_seen_at,
         COUNT(DISTINCT q.book_id)::integer AS books_ever
  FROM public.v_fight_market_quotes q
  GROUP BY q.fight_id
)
SELECT
  s.fight_id,
  b.baseline_at                              AS window_start,
  s.last_seen_at                             AS window_end,
  s.first_seen_at,
  s.books_ever,
  COALESCE(c.cohort_books, 0)                AS cohort_books,
  3                                          AS min_books,
  CASE
    WHEN b.fight_id IS NULL                  THEN 'no_broad_capture'
    WHEN COALESCE(c.cohort_books, 0) < 3     THEN 'insufficient_matched_books'
    ELSE 'ok'
  END                                        AS series_status,
  'fixed_cohort_median_vigfree_v1'           AS series_method
FROM span s
LEFT JOIN public.v_fight_market_broad_baseline b ON b.fight_id = s.fight_id
LEFT JOIN cohort c ON c.fight_id = s.fight_id;

COMMENT ON VIEW public.v_fight_chart_meta IS
  'Per-fight chart window and cohort. series_status ok / '
  'insufficient_matched_books / no_broad_capture. When it is not ok, '
  'v_fight_chart_series returns no rows for that fight by design.';

GRANT SELECT ON public.v_fight_chart_meta TO anon, authenticated;

-- ---------------------------------------------------------------------------
-- 2. The consensus series. Every point, the same books.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_fight_chart_series AS
WITH cohort AS (
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

GRANT SELECT ON public.v_fight_chart_series TO anon, authenticated;

-- ---------------------------------------------------------------------------
-- 3. Per-sportsbook history, native. One row per real quote — no cohort, no
--    carry-forward, no median. These are observations of one book, so the
--    reasons the consensus needs a fixed cohort do not apply.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_fight_chart_books AS
SELECT
  q.fight_id,
  q.book_id,
  sb.name       AS book_name,
  sb.short_code AS book_code,
  q.quoted_at   AS at,
  q.fair_a,
  q.fair_b,
  q.american_odds_a,
  q.american_odds_b,
  EXISTS (
    SELECT 1 FROM public.v_fight_market_horizon_cohorts h
    WHERE h.horizon = 'broad_baseline'
      AND h.fight_id = q.fight_id AND h.book_id = q.book_id
  )             AS in_cohort
FROM public.v_fight_market_quotes q
JOIN public.v_odds_books_sportsbooks sb ON sb.id = q.book_id;

COMMENT ON VIEW public.v_fight_chart_books IS
  'Per-sportsbook quote history, native: one row per real quote, no median and '
  'no carry-forward. in_cohort marks the books the consensus line is built '
  'from, so a reader can see which lines feed it.';

GRANT SELECT ON public.v_fight_chart_books TO anon, authenticated;

-- ---------------------------------------------------------------------------
-- 4. v_fight_odds_latest_by_book — the 14-day window removed (T-040).
--
--    It carried `WHERE e.event_date >= CURRENT_DATE - 14`, so a fight page more
--    than a fortnight old lost its per-sportsbook table entirely: the panel
--    rendered empty with no error and no explanation. The movement views shed
--    the same window under D-012 and T-046; this is the last one.
--
--    Nothing else about it changes. It is the latest quote per book per fight,
--    which is bounded by (fights x books) rather than by history, so dropping
--    the date filter does not change its shape — only which fights appear.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_fight_odds_latest_by_book AS
SELECT
  q.fight_id,
  f.event_id,
  q.book_id,
  sb.name       AS book_name,
  sb.short_code AS book_code,
  q.american_odds_a,
  q.american_odds_b,
  q.fair_a      AS fair_prob_a,
  q.fair_b      AS fair_prob_b,
  q.quoted_at   AS captured_at
FROM (
  SELECT DISTINCT ON (fight_id, book_id) *
  FROM public.v_fight_market_quotes
  ORDER BY fight_id, book_id, quoted_at DESC
) q
JOIN public.fights f ON f.id = q.fight_id
JOIN public.v_odds_books_sportsbooks sb ON sb.id = q.book_id;

COMMENT ON VIEW public.v_fight_odds_latest_by_book IS
  'Latest quote per sportsbook per fight, all history. The 14-day event window '
  'was removed by T-040: it made fight pages older than a fortnight render an '
  'empty sportsbook table with no error and no explanation.';

GRANT SELECT ON public.v_fight_odds_latest_by_book TO anon, authenticated;
