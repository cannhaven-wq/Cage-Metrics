-- =============================================================================
-- market_movement_views.sql — a defensible baseline for "the market moved".
-- Applied 2026-09-21. Safe to re-run. Additive: creates views only, changes no
-- existing view, writes no row, touches no trigger, no RLS policy and no table.
-- =============================================================================
--
-- THE PROBLEM THIS EXISTS TO SOLVE
--
-- Two things carried it. `v_fight_market_at_lock` (fight_week_views.sql)
-- compares a lock-time cohort against a current one and is still to be
-- reconciled (T-046). The other was `v_fight_market_movement`, defined by
-- `market_lab_views.sql` on the repositioning branch and applied to the live
-- database the same day, exposing `open_p_a`, `open_p_b` and `books_at_open` —
-- where "open" meant `min(captured_at)`, CFL's single earliest capture
-- instant. That file was careful about it and required every surface to print
-- the book count beside the number and to call it "our first capture", never
-- "the opening line". The disclosure was honest and the number was still
-- wrong: on 22 of 79 fights that instant held ONE sportsbook, and the figure
-- it produced overstated real movement by as much as 12.7 points. This file
-- replaces that view in place and keeps every defensible column it had;
-- `market_lab_views.sql` is now a pointer here.
--
-- `v_fight_market_at_lock` (fight_week_views.sql) compares a vig-free median
-- taken over whatever sportsbooks CFL had captured by the lock instant against
-- a vig-free median taken over whatever sportsbooks CFL has captured now. Those
-- are not the same cohort. Measured against the live table on 2026-09-21:
--
--     79 fights have real sportsbook quotes
--     22 of them (28%) have exactly ONE sportsbook in their first capture
--     77 of them eventually reach three or more sportsbooks
--
-- So for better than a quarter of fights, "the line moved from 50.0% to 56.3%"
-- would be partly, and possibly entirely, the arrival of five more sportsbooks.
-- That is a composition change wearing the costume of a market move, and it is
-- not something CFL can defend to a sceptical reader.
--
-- WHAT CFL ACTUALLY KNOWS
--
-- CFL knows when CFL first captured a price. It does NOT know when a sportsbook
-- first posted one. Nothing downstream of these views may call any instant here
-- an "opening line", an "open", or an "opening market" — see §Terminology.
--
-- THE RULE
--
--   1. Real sportsbooks only. The synthetic "CFL Consensus (Odds API)" median
--      row and the prediction markets (Polymarket, Kalshi) are excluded via
--      v_odds_books_sportsbooks. A synthetic row is never counted as a book.
--   2. Pre-fight, open markets only: is_live is not true, and market_status is
--      either absent (legacy rows, all pre-fight) or 'open'.
--   3. Each book is de-vigged on its own two-sided pair, at one capture instant.
--      Verified 2026-09-21: all 42,432 A-side rows have a B-side row at the
--      identical captured_at, so a "quote" is unambiguous and needs no
--      time-bucketing or batch id. See §Grouping.
--   4. FIRST BROAD CFL CAPTURE = the earliest instant at which CFL held a
--      two-sided quote from at least MIN_BOOKS (= 3) distinct sportsbooks on
--      that fight. Concretely: the first-quote time of the third distinct book.
--   5. Movement is computed over the MATCHED BOOK COHORT — the books present
--      BOTH in the baseline cohort and in the current cohort — and only when
--      that cohort has at least MIN_BOOKS books. Baseline and current medians
--      are taken over that same set of books. A book that has since pulled the
--      market drops out of both sides, not just one.
--   6. If the matched cohort is smaller than MIN_BOOKS, movement is NULL and
--      `movement_status` says why. Nothing falls back to a wider cohort.
--
-- MIN_BOOKS is 3, repeated literally in each view below (Postgres views take no
-- parameters). It is mirrored in market-movement.js as MIN_MATCHED_BOOKS and
-- pinned by tests/market-movement.test.js — change all three together.
--
-- §Grouping — HOW CAPTURES ARE GROUPED, EXACTLY
--
-- A quote is the pair (fight_id, book_id, captured_at) carrying both sides.
-- `captured_at` is the grouping key and nothing coarser is used: no rounding,
-- no time bucket, no batch window. `retrieved_at` (the capture-run instant
-- added by the CLV-001 §4 capture migration) is carried through as an audit
-- field only, because it is populated on 3,686 of 115,588 rows — it identifies
-- the run, not the quote, and a rule that depended on it would silently change
-- behaviour at the 2026-09-19 boundary.
--
-- §Terminology — the only labels these columns license
--
--   baseline_at   -> "first broad capture" / "when CFL first saw 3+ books"
--   current_at    -> "latest capture"
--   movement_pts  -> "moved N points since CFL first saw 3+ books"
--   NEVER         -> "opening line", "open", "opening market", "the market
--                    opened at", or any phrasing implying CFL observed the
--                    sportsbook opener.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Every eligible two-sided sportsbook quote, de-vigged on its own pair.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_fight_market_quotes AS
WITH q AS (
  SELECT o.fight_id, o.book_id, o.side, o.implied_prob, o.captured_at,
         o.retrieved_at, o.american_odds
  FROM public.fight_odds o
  JOIN public.v_odds_books_sportsbooks b ON b.id = o.book_id
  WHERE o.captured_at > TIMESTAMPTZ '2010-01-01'   -- skip fake epoch opener rows
    AND o.implied_prob IS NOT NULL
    AND o.implied_prob > 0
    AND o.is_live IS NOT TRUE
    AND (o.market_status IS NULL OR o.market_status = 'open')
)
SELECT
  a.fight_id,
  a.book_id,
  a.captured_at                                                   AS quoted_at,
  (a.implied_prob / (a.implied_prob + b.implied_prob))::numeric    AS fair_a,
  (b.implied_prob / (a.implied_prob + b.implied_prob))::numeric    AS fair_b,
  a.american_odds                                                  AS american_odds_a,
  b.american_odds                                                  AS american_odds_b,
  -- audit only; see §Grouping. Never a grouping key.
  a.retrieved_at                                                   AS retrieved_at
FROM q a
JOIN q b
  ON  b.fight_id    = a.fight_id
  AND b.book_id     = a.book_id
  AND b.captured_at = a.captured_at
  AND b.side        = 'B'
WHERE a.side = 'A';

-- NOT granted to anon/authenticated. This is the full per-book tick history:
-- the thing a Pro tier would sell, and no free surface reads it. The three
-- views below are owner-rights views (security_invoker is off, matching
-- fight_week_views.sql), so they keep reading it regardless.
REVOKE SELECT ON public.v_fight_market_quotes FROM anon, authenticated;

-- ---------------------------------------------------------------------------
-- 2. The first broad CFL capture instant, per fight: when the third distinct
--    sportsbook's first quote landed.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_fight_market_broad_baseline AS
WITH first_seen AS (
  SELECT fight_id, book_id, MIN(quoted_at) AS first_quoted_at
  FROM public.v_fight_market_quotes
  GROUP BY fight_id, book_id
),
ranked AS (
  SELECT fight_id, book_id, first_quoted_at,
         ROW_NUMBER() OVER (PARTITION BY fight_id
                            ORDER BY first_quoted_at, book_id) AS book_rank
  FROM first_seen
)
SELECT
  fight_id,
  first_quoted_at AS baseline_at,
  3               AS min_books          -- MIN_BOOKS, stated in the row itself
FROM ranked
WHERE book_rank = 3;

COMMENT ON VIEW public.v_fight_market_broad_baseline IS
  'First broad CFL capture: the instant CFL first held two-sided quotes from 3 '
  'distinct real sportsbooks on a fight. NOT the sportsbook opening line — CFL '
  'does not observe openers. See market_movement_views.sql.';

GRANT SELECT ON public.v_fight_market_broad_baseline TO anon, authenticated;

-- ---------------------------------------------------------------------------
-- 3. Movement, over the matched book cohort only, with full provenance.
--
--    This REPLACES the fight-week-v2 view of the same name. Kept from it, all
--    defensible: market_p_a/b, book_count, last_updated, the 24h lookback,
--    best price + best book, book_spread_pts, capture_count. Removed from it:
--    open_p_a, open_p_b, books_at_open — CFL does not observe openers, and
--    those were a single-instant median that could rest on one sportsbook.
--    Also removed: its `e.event_date >= CURRENT_DATE - 14` window, so a fight
--    page older than a fortnight keeps its market history instead of going
--    blank.
-- ---------------------------------------------------------------------------
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
-- each book's latest quote at least 24h old, for the short lookback
cohort_24h AS (
  SELECT DISTINCT ON (q.fight_id, q.book_id)
    q.fight_id, q.book_id, q.fair_a
  FROM public.v_fight_market_quotes q
  WHERE q.quoted_at <= now() - INTERVAL '24 hours'
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
back24 AS (
  SELECT fight_id,
    (percentile_cont(0.5) WITHIN GROUP (ORDER BY fair_a))::numeric AS market_p_a_24h,
    COUNT(*)::integer                                               AS book_count_24h
  FROM cohort_24h GROUP BY fight_id
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
  -- 24h lookback (all books with a quote that old; a lookback, not the baseline)
  b24.market_p_a_24h,
  (1 - b24.market_p_a_24h)::numeric                          AS market_p_b_24h,
  COALESCE(b24.book_count_24h, 0)                            AS book_count_24h,
  -- best observed price, mechanically the best American number on offer.
  -- No commercial input of any kind reaches this ordering.
  cur.best_american_a, cur.best_book_a,
  cur.best_american_b, cur.best_book_b,
  cur.worst_american_a, cur.worst_american_b,
  cur.book_spread_pts
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

-- ---------------------------------------------------------------------------
-- 4. The matched cohort itself, book by book — the "show your working" row set
--    behind any movement number a surface prints.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_fight_market_movement_books AS
WITH base AS (SELECT * FROM public.v_fight_market_broad_baseline),
baseline_cohort AS (
  SELECT DISTINCT ON (q.fight_id, q.book_id)
    q.fight_id, q.book_id, q.fair_a, q.quoted_at
  FROM public.v_fight_market_quotes q
  JOIN base ON base.fight_id = q.fight_id
  WHERE q.quoted_at <= base.baseline_at
  ORDER BY q.fight_id, q.book_id, q.quoted_at DESC
),
current_cohort AS (
  SELECT DISTINCT ON (q.fight_id, q.book_id)
    q.fight_id, q.book_id, q.fair_a, q.quoted_at, q.american_odds_a, q.american_odds_b
  FROM public.v_fight_market_quotes q
  ORDER BY q.fight_id, q.book_id, q.quoted_at DESC
)
SELECT
  c.fight_id,
  c.book_id,
  sb.name                                          AS book_name,
  sb.short_code                                    AS book_code,
  b.fight_id IS NOT NULL                           AS in_matched_cohort,
  b.fair_a                                         AS baseline_fair_a,
  b.quoted_at                                      AS baseline_quoted_at,
  c.fair_a                                         AS current_fair_a,
  c.quoted_at                                      AS current_quoted_at,
  c.american_odds_a,
  c.american_odds_b,
  CASE WHEN b.fight_id IS NOT NULL
       THEN ((c.fair_a - b.fair_a) * 100)::numeric END AS movement_pts_a
FROM current_cohort c
JOIN public.v_odds_books_sportsbooks sb ON sb.id = c.book_id
LEFT JOIN baseline_cohort b
  ON b.fight_id = c.fight_id AND b.book_id = c.book_id;

GRANT SELECT ON public.v_fight_market_movement_books TO anon, authenticated;
