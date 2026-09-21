-- =============================================================================
-- market_horizon_views.sql — every market horizon, one matched-cohort rule.
-- Applied 2026-09-21 (T-046). Safe to re-run.
-- =============================================================================
-- PLAIN ENGLISH: "the line moved" now means the same thing everywhere on the
-- site, whether we are comparing to last week, to yesterday, or to the moment a
-- research forecast was locked. In every case we compare only the sportsbooks
-- that were quoting at BOTH ends, and if fewer than three of them line up we
-- say so instead of printing a number.
--
-- D-012 fixed that for one horizon — the first broad capture — and left two
-- others on the old footing. This file finishes the job and, more importantly,
-- makes the rule live in ONE place so a fourth horizon cannot be added on the
-- wrong footing by accident.
--
-- -----------------------------------------------------------------------------
-- What was still wrong, measured on the live table 2026-09-21
-- -----------------------------------------------------------------------------
--
-- 1. `v_fight_market_at_lock` (fight_week_views.sql) medianed over the books
--    captured by the forecast-lock instant and compared that to a median over
--    the books quoting now. Of 14 fights with a lock: 4 had a different cohort
--    at the two ends, 1 rested on a SINGLE book at lock, and the worst
--    disagreement against a matched cohort was **5.2 points**.
--
-- 2. The 24-hour lookback inside `v_fight_market_movement` — the one D-012
--    shipped — had exactly the same shape: `market_p_a_24h` medianed every book
--    with a quote at least 24 h old, against every book quoting now. Of 77
--    fights, 8 had a different cohort at the two ends and 2 would fall below
--    the three-book floor. Worst disagreement: **0.5 points**, which is under
--    the 0.5 pt display threshold, so no rendered figure changed.
--
--    The 24 h case is small for a reason worth writing down: a day is short
--    enough that a book quoting yesterday is almost always quoting today. It
--    is NOT small in the case that matters most — a book pulling a market
--    during fight week is exactly when someone is watching the 24 h column.
--    A defect that is currently harmless and structurally identical is still
--    the defect.
--
-- -----------------------------------------------------------------------------
-- §The shape: one intersection, three horizons
-- -----------------------------------------------------------------------------
-- `v_fight_market_horizon_cohorts` is long-format: one row per
-- (fight, horizon, book) that quoted at BOTH that horizon's instant and now.
-- The intersection and the de-vigging happen once, there. Everything else
-- aggregates it. Adding a horizon means adding a row to the `h` CTE and
-- nothing else — no second copy of the cohort logic to keep in step.
--
-- MIN_BOOKS is 3, the same floor as D-012, and it is stated once here as a
-- column on `v_fight_market_horizons` so a reader can see the threshold beside
-- the number it gated. Mirrored in market_movement_views.sql, market.js
-- (MIN_MATCHED_BOOKS) and market-movement.js. Change all of them together.
--
-- §Terminology, unchanged and non-negotiable
-- CFL has never observed a sportsbook opener. No column, label or comment here
-- says "opening line", "open", "opened at" or "since open". `lock` means the
-- instant a research forecast was written down, which is a CFL event, not a
-- market event.
--
-- §A note on `lock`, and why it is kept
-- The forecast is off every public surface (D-011). `lock` therefore serves the
-- research and archive layer only — it answers "did the market move after we
-- wrote our number down", which is a question about CFL, not about the product.
-- D-011 is explicit that model infrastructure is not deleted to tidy up, so the
-- horizon stays and is measured correctly rather than being removed.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. The one intersection. Long format, one row per (fight, horizon, book).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_fight_market_horizon_cohorts AS
WITH fights_seen AS (
  SELECT DISTINCT fight_id FROM public.v_fight_market_quotes
),
h AS (
  -- first broad CFL capture: the instant a third distinct sportsbook appeared
  SELECT fight_id, 'broad_baseline'::text AS horizon, baseline_at AS as_of
  FROM public.v_fight_market_broad_baseline
  UNION ALL
  -- 24 hours ago
  SELECT fight_id, 'h24'::text, now() - INTERVAL '24 hours'
  FROM fights_seen
  UNION ALL
  -- the instant a research forecast was locked (research layer only; see §)
  SELECT fight_id, 'lock'::text, locked_at
  FROM public.v_fight_locked_forecast
  WHERE locked_at IS NOT NULL
),
then_cohort AS (
  -- each book's latest quote at or before that horizon's instant
  SELECT DISTINCT ON (h.fight_id, h.horizon, q.book_id)
    h.fight_id, h.horizon, h.as_of,
    q.book_id, q.fair_a AS then_fair_a, q.quoted_at AS then_quoted_at
  FROM h
  JOIN public.v_fight_market_quotes q
    ON q.fight_id = h.fight_id AND q.quoted_at <= h.as_of
  ORDER BY h.fight_id, h.horizon, q.book_id, q.quoted_at DESC
),
now_cohort AS (
  -- each book's latest quote overall
  SELECT DISTINCT ON (fight_id, book_id)
    fight_id, book_id, fair_a AS now_fair_a, quoted_at AS now_quoted_at
  FROM public.v_fight_market_quotes
  ORDER BY fight_id, book_id, quoted_at DESC
)
SELECT
  t.fight_id,
  t.horizon,
  t.as_of,
  t.book_id,
  t.then_fair_a,
  t.then_quoted_at,
  n.now_fair_a,
  n.now_quoted_at
FROM then_cohort t
-- THE INTERSECTION. A book that has since pulled the market leaves both sides
-- of the comparison, never just one.
JOIN now_cohort n
  ON n.fight_id = t.fight_id AND n.book_id = t.book_id;

COMMENT ON VIEW public.v_fight_market_horizon_cohorts IS
  'Long format: one row per (fight, horizon, sportsbook) quoting at BOTH that '
  'horizon and now. The single matched-cohort intersection every market '
  'movement figure is built from. See market_horizon_views.sql.';

-- Building block, not a public surface: the aggregates below are owner-rights
-- views and read it regardless.
REVOKE SELECT ON public.v_fight_market_horizon_cohorts FROM anon, authenticated;

-- ---------------------------------------------------------------------------
-- 2. One row per (fight, horizon): the movement, or an honest refusal.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_fight_market_horizons AS
WITH agg AS (
  SELECT
    fight_id, horizon,
    MIN(as_of)                                                            AS as_of,
    COUNT(*)::integer                                                     AS matched_book_count,
    (percentile_cont(0.5) WITHIN GROUP (ORDER BY then_fair_a))::numeric    AS then_p_a,
    (percentile_cont(0.5) WITHIN GROUP (ORDER BY now_fair_a))::numeric     AS now_p_a,
    MAX(then_quoted_at)                                                   AS then_quoted_at,
    MAX(now_quoted_at)                                                    AS now_quoted_at
  FROM public.v_fight_market_horizon_cohorts
  GROUP BY fight_id, horizon
)
SELECT
  a.fight_id,
  a.horizon,
  a.as_of,
  3                                        AS min_books,   -- MIN_BOOKS, stated
  a.matched_book_count,
  a.then_quoted_at,
  a.now_quoted_at,
  CASE WHEN a.matched_book_count >= 3 THEN a.then_p_a END                        AS then_p_a,
  CASE WHEN a.matched_book_count >= 3 THEN a.now_p_a  END                        AS now_p_a,
  CASE WHEN a.matched_book_count >= 3
       THEN ((a.now_p_a - a.then_p_a) * 100)::numeric END                        AS movement_pts_a,
  CASE WHEN a.matched_book_count >= 3 THEN 'ok'
       ELSE 'insufficient_matched_books' END                                     AS movement_status,
  'matched_cohort_median_vigfree_v1'                                             AS movement_method
FROM agg a;

COMMENT ON VIEW public.v_fight_market_horizons IS
  'Movement per fight per horizon (broad_baseline / h24 / lock), always over '
  'the books quoting at both ends, NULL below 3 of them. No horizon here is a '
  'sportsbook opener — CFL has never observed one.';

GRANT SELECT ON public.v_fight_market_horizons TO anon, authenticated;

-- ---------------------------------------------------------------------------
-- 3. v_fight_market_at_lock, rebuilt on the shared rule.
--
--    Its original columns are kept so nothing reading it breaks, and two are
--    added: `matched_book_count_at_lock` and `movement_status_at_lock`, because
--    a number whose cohort size is not published is a number a reader cannot
--    check. `market_p_a_at_lock` is now the matched-cohort median rather than a
--    median over whatever happened to be captured by then.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_fight_market_at_lock AS
SELECT
  h.fight_id,
  h.then_p_a                              AS market_p_a_at_lock,
  CASE WHEN h.then_p_a IS NULL THEN NULL
       ELSE (1 - h.then_p_a)::numeric END AS market_p_b_at_lock,
  h.matched_book_count                    AS book_count_at_lock,
  h.then_quoted_at                        AS quoted_at,
  -- added by T-046
  h.matched_book_count                    AS matched_book_count_at_lock,
  h.movement_status                       AS movement_status_at_lock,
  h.movement_pts_a                        AS movement_pts_a_since_lock,
  h.as_of                                 AS locked_at
FROM public.v_fight_market_horizons h
WHERE h.horizon = 'lock';

COMMENT ON VIEW public.v_fight_market_at_lock IS
  'The vig-free market at the instant a research forecast was locked, over the '
  'books quoting both then and now, NULL below 3. Research layer only — the '
  'forecast is off every public surface (D-011). Rebuilt on the shared '
  'matched-cohort rule by T-046; it previously compared a lock-time cohort '
  'against a current one and overstated movement by up to 5.2 points.';

GRANT SELECT ON public.v_fight_market_at_lock TO anon, authenticated;
