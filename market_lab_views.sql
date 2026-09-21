-- =============================================================================
-- market_lab_views.sql — the read layer behind Card Lab, Fight Lab and
-- Market Lab (September 2026, the research repositioning).
-- =============================================================================
-- One view, additive, read-only, computed on read. Nothing here writes and
-- nothing here replaces an existing object: `v_fight_market_vigfree`,
-- `v_fight_market_at_lock`, `v_fight_odds_latest_by_book` and
-- `v_fight_odds_consensus` are all left exactly as they were.
--
--   v_fight_market_movement   one row per fight on a current-window card:
--                             where the vig-free market sits now, where it sat
--                             at our first capture and where it sat 24 hours
--                             ago, plus the best price on each side, which book
--                             is posting it, how far apart the books are, and
--                             when we last heard from them.
--
-- Why this exists: `v_fight_market_vigfree` answers "what is the price now"
-- and nothing else. Every question the research product is built to answer —
-- what moved, how far, which book is out of line, is this number stale —
-- needs the same fight at more than one instant, and `fight_odds` has no
-- SELECT policy for `anon`, so the browser cannot assemble it itself. This
-- view runs with the definer's rights the same way the existing market views
-- do, and exposes only aggregates plus the best posted price per side.
--
-- -----------------------------------------------------------------------------
-- What "open" means here, exactly
-- -----------------------------------------------------------------------------
-- `open_p_a` is the median vig-free price across the sportsbooks present in
-- OUR FIRST CAPTURE of that fight — not the true market open, which happened
-- before we were watching. `books_at_open` is published beside it for exactly
-- that reason: on a card first captured by a single offshore book, a reader who
-- is not told it was one book would read a two-book disagreement as a move.
-- Every surface that shows `open_p_a` must show `books_at_open` and
-- `first_seen_at` with it, and must call it "our first capture", never "the
-- opening line".
--
-- The 24-hour column is each book's own latest quote at or before
-- now() - 24h, then the median across books — the standard "where was this
-- yesterday", and NULL for a fight we have not been watching that long.
--
-- Pairs are same-instant only: side A and side B must carry the same
-- `captured_at`, so each book is de-vigged against its own quote rather than
-- against a price from a different hour. In-play rows (`is_live`) are excluded;
-- a price quoted after the bell is not a pre-fight market observation.
--
-- Best price is the maximum American number on that side across books, which
-- is the actual best payout (+150 beats +120 beats -110 beats -150) and is
-- never ordered by anything else. If affiliate economics ever enter this
-- product, they do not enter here.
--
-- Safe to re-run.
-- =============================================================================

CREATE OR REPLACE VIEW public.v_fight_market_movement AS
WITH window_fights AS (
  -- Same window as v_fight_odds_latest_by_book: cards in the last two weeks
  -- or still to come.
  SELECT f.id AS fight_id, f.event_id
  FROM public.fights f
  JOIN public.events e ON e.id = f.event_id
  WHERE e.event_date >= CURRENT_DATE - 14
),
pairs AS (
  -- Every two-sided sportsbook quote, at every instant we captured one.
  SELECT
    a.fight_id,
    w.event_id,
    a.book_id,
    sb.name                                                         AS book_name,
    sb.short_code                                                   AS book_code,
    a.captured_at,
    (a.implied_prob / (a.implied_prob + b.implied_prob))::numeric   AS fair_a,
    a.american_odds                                                 AS american_odds_a,
    b.american_odds                                                 AS american_odds_b
  FROM public.fight_odds a
  JOIN public.fight_odds b
    ON  b.fight_id    = a.fight_id
    AND b.book_id     = a.book_id
    AND b.captured_at = a.captured_at
    AND b.side        = 'B'
  JOIN window_fights w                     ON w.fight_id = a.fight_id
  JOIN public.v_odds_books_sportsbooks sb  ON sb.id      = a.book_id
  WHERE a.side = 'A'
    AND a.captured_at > TIMESTAMPTZ '2010-01-01'   -- skip fake epoch opener rows
    AND a.implied_prob IS NOT NULL AND a.implied_prob > 0
    AND b.implied_prob IS NOT NULL AND b.implied_prob > 0
    AND a.is_live IS NOT TRUE
),
marked AS (
  SELECT
    p.*,
    min(p.captured_at) OVER (PARTITION BY p.fight_id)                       AS t0,
    row_number() OVER (PARTITION BY p.fight_id, p.book_id
                       ORDER BY p.captured_at DESC)                         AS rn_now,
    (p.captured_at <= now() - interval '24 hours')                          AS before_24h,
    -- Partitioning on the boolean gives "each book's latest quote at or before
    -- the 24-hour mark" in the same pass, without a second scan.
    row_number() OVER (PARTITION BY p.fight_id, p.book_id,
                                    (p.captured_at <= now() - interval '24 hours')
                       ORDER BY p.captured_at DESC)                         AS rn_24h
  FROM pairs p
)
SELECT
  fight_id,
  event_id,

  -- Now
  (percentile_cont(0.5) WITHIN GROUP (ORDER BY fair_a)
     FILTER (WHERE rn_now = 1))::numeric                              AS market_p_a,
  (1 - percentile_cont(0.5) WITHIN GROUP (ORDER BY fair_a)
     FILTER (WHERE rn_now = 1))::numeric                              AS market_p_b,
  (count(*) FILTER (WHERE rn_now = 1))::integer                       AS book_count,
  max(captured_at)                                                    AS last_updated,

  -- Our first capture. Read books_at_open before reading open_p_a.
  (percentile_cont(0.5) WITHIN GROUP (ORDER BY fair_a)
     FILTER (WHERE captured_at = t0))::numeric                        AS open_p_a,
  (1 - percentile_cont(0.5) WITHIN GROUP (ORDER BY fair_a)
     FILTER (WHERE captured_at = t0))::numeric                        AS open_p_b,
  (count(*) FILTER (WHERE captured_at = t0))::integer                 AS books_at_open,
  min(t0)                                                             AS first_seen_at,

  -- 24 hours ago; NULL if we were not watching this fight that long ago.
  (percentile_cont(0.5) WITHIN GROUP (ORDER BY fair_a)
     FILTER (WHERE rn_24h = 1 AND before_24h))::numeric               AS market_p_a_24h,
  (1 - percentile_cont(0.5) WITHIN GROUP (ORDER BY fair_a)
     FILTER (WHERE rn_24h = 1 AND before_24h))::numeric               AS market_p_b_24h,
  (count(*) FILTER (WHERE rn_24h = 1 AND before_24h))::integer        AS book_count_24h,

  -- Best posted price on each side, and who is posting it. Ordered by the
  -- American number and by nothing else.
  max(american_odds_a) FILTER (WHERE rn_now = 1)                      AS best_american_a,
  (array_agg(book_name ORDER BY american_odds_a DESC)
     FILTER (WHERE rn_now = 1))[1]                                    AS best_book_a,
  max(american_odds_b) FILTER (WHERE rn_now = 1)                      AS best_american_b,
  (array_agg(book_name ORDER BY american_odds_b DESC)
     FILTER (WHERE rn_now = 1))[1]                                    AS best_book_b,

  -- How far apart the books are right now, in vig-free points on side A.
  ((max(fair_a) FILTER (WHERE rn_now = 1)
    - min(fair_a) FILTER (WHERE rn_now = 1)) * 100)::numeric          AS book_spread_pts,
  (min(american_odds_a) FILTER (WHERE rn_now = 1))                    AS worst_american_a,
  (min(american_odds_b) FILTER (WHERE rn_now = 1))                    AS worst_american_b,

  -- How many distinct instants we have for this fight — the honest depth of
  -- the movement history behind the numbers above.
  (count(DISTINCT captured_at))::integer                              AS capture_count
FROM marked
GROUP BY fight_id, event_id;

GRANT SELECT ON public.v_fight_market_movement TO anon, authenticated;
