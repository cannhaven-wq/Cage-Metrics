-- =============================================================================
-- t061_pro_gates.DRAFT.sql — what the Free/Pro gates would look like in SQL.
-- DRAFT. NOT APPLIED. NOT TO BE APPLIED BY HABIT. Written 2026-10-21.
-- =============================================================================
-- PLAIN ENGLISH: this file shows, in the database's own language, exactly which
-- parts of CFL would stop answering a free reader once a paid tier exists. It
-- is a drawing of the gate, not the gate. It lives under research/, not at the
-- repo root, so no "apply every root .sql" habit can pick it up, and it refuses
-- to run unless the session says on purpose that it means to.
--
-- WHY IT IS NOT APPLIED
--   D-019 (owner, 2026-09-21): no paywall before there is a way to pay. T-061
--   is blocked on T-054, T-048, a price (T-067), a Stripe account (T-068) and a
--   test-mode checkout (T-069). Applying this is also CRITICAL_GATES item 5
--   (an RLS change on production) and item 7 (monetisation): L3.
--
-- THE ONE RULE IT FOLLOWS
--   Every gate calls public.current_user_is_pro() and nothing else.
--   entitlements.js only decides what a page DRAWS; this decides what the
--   database SENDS. The browser key is public, so a gate that exists only in
--   JavaScript is not a gate.
--
-- WHAT IT GATES (mirrors entitlements.js::PRO_GATES_DRAFT, and a test keeps
-- the two in step)
--   movement_chart_history  v_pro_fight_chart_series       view, pro only
--   book_by_book_history    v_pro_fight_chart_books        view, pro only
--   historical_lookback     v_fight_market_movement_lookback
--                                                          view, pro OR the
--                                                          free window
--   watchlists              "watchlist insert own (pro)"   INSERT policy
--   price_alerts            alert_quota()                  the quota function
--   movement_alerts         alert_quota()                  the quota function
--   since_last_visit        -- not built, nothing to gate
--   advanced_matchup        -- not built, nothing to gate
--
-- WHAT IT MUST NEVER TOUCH
--   Every free surface: v_fight_market_movement, v_fight_odds_latest_by_book,
--   v_fight_market_vigfree, v_fight_chart_meta, every fighter/event/Factor Lab
--   read, the Model Archive. The test asserts none of those names appears in a
--   REVOKE here.
--
-- CONSEQUENCES THE OWNER SHOULD SEE BEFORE APPLYING
--   1. Card Lab and Fight Lab draw the movement chart for everybody today
--      (market-chart.js reads v_fight_chart_series and v_fight_chart_books).
--      PRODUCT_BOUNDARY.md puts the full plotted series in Pro. Applying this
--      takes the chart away from free readers; the page change (read the
--      v_pro_* names, draw entitlements.decide()'s upsell instead) ships in
--      the SAME pull request, or free readers see an empty chart and no reason.
--   2. While beta_premium is true for every account (it is, today),
--      current_user_is_pro() is true for every signed-in reader. Applying this
--      during beta gates logged-out visitors only. Ending the beta grant is its
--      own owner decision.
--   3. Alerts: the documented split (alerts_migration.sql §0, D-019) is 50
--      active alerts for Pro and 3 for Free, so alerts are METERED, not walled.
--      entitlements.js lists price/movement alerts as Pro. Those two disagree
--      on whether a free reader gets any alerts; this draft follows the written
--      SQL spec (3) and the owner settles it at T-061.
--   4. A member whose subscription lapses keeps READ and DELETE on the
--      watchlist rows and alerts they already made. Nothing they created is
--      hidden from them or deleted. Whether build/send-alerts.js keeps
--      EMAILING a lapsed member's existing alerts is a sender rule this file
--      does not decide.
--   5. FREE_WINDOW_DAYS below is a placeholder. How far back a free reader may
--      look is a product decision (T-061), not a number this draft chose.
--
-- Re-run safe. No DROP TABLE, no DELETE, no TRUNCATE, no RAISE NOTICE and no
-- DROP TRIGGER IF EXISTS (CLAUDE.md: either hangs the Supabase MCP tool).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 0. Refuse to run by accident. Set the flag in the same session to mean it:
--      SET cfl.t061_apply = 'yes';
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF current_setting('cfl.t061_apply', true) IS DISTINCT FROM 'yes' THEN
    RAISE EXCEPTION 't061_pro_gates.DRAFT.sql is a draft. Applying it is T-061 '
      '(L3: CRITICAL_GATES items 5 and 7). Set cfl.t061_apply = ''yes'' in the '
      'session only when the owner has approved it.';
  END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- 1. movement_chart_history — the full plotted series is Pro.
--    The headline move (v_fight_market_movement) stays free and is untouched.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_pro_fight_chart_series AS
SELECT s.*
FROM public.v_fight_chart_series s
WHERE public.current_user_is_pro();

COMMENT ON VIEW public.v_pro_fight_chart_series IS
  'T-061 DRAFT. The movement chart series, returned only when '
  'current_user_is_pro(). A free reader gets zero rows, not an error.';

REVOKE ALL ON public.v_pro_fight_chart_series FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.v_pro_fight_chart_series TO anon, authenticated;
-- The ungated series stops being readable from the browser. The wrapper above
-- is an owner-rights view, so it keeps reading it.
REVOKE ALL ON public.v_fight_chart_series FROM PUBLIC, anon, authenticated;

-- ---------------------------------------------------------------------------
-- 2. book_by_book_history — every sportsbook's own history is Pro.
--    The CURRENT per-book table (v_fight_odds_latest_by_book) stays free.
--    The raw tick history (v_fight_market_quotes) is already ungranted.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_pro_fight_chart_books AS
SELECT b.*
FROM public.v_fight_chart_books b
WHERE public.current_user_is_pro();

COMMENT ON VIEW public.v_pro_fight_chart_books IS
  'T-061 DRAFT. Each sportsbook''s own price history, only when '
  'current_user_is_pro(). The current per-book table stays free.';

REVOKE ALL ON public.v_pro_fight_chart_books FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.v_pro_fight_chart_books TO anon, authenticated;
REVOKE ALL ON public.v_fight_chart_books FROM PUBLIC, anon, authenticated;

-- ---------------------------------------------------------------------------
-- 3. historical_lookback — past cards beyond the free window are Pro.
--    The window is one function so there is one number to change.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.cfl_free_window_days()
RETURNS integer
LANGUAGE sql
IMMUTABLE
SET search_path TO 'public'
AS $$
  -- FREE_WINDOW_DAYS. PLACEHOLDER. The owner sets this at T-061.
  SELECT 14;
$$;

CREATE OR REPLACE FUNCTION public.cfl_fight_in_free_window(p_fight_id bigint)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path TO 'public'
AS $$
  -- An upcoming card, or one inside the window, is free. A fight with no
  -- event date is treated as current: refusing it would hide the very card a
  -- reader came for because a scraper had not filled a column yet.
  SELECT COALESCE((
    SELECT e.event_date IS NULL
        OR e.event_date >= (now() AT TIME ZONE 'utc')::date - public.cfl_free_window_days()
    FROM public.fights f
    LEFT JOIN public.events e ON e.id = f.event_id
    WHERE f.id = p_fight_id
  ), false);
$$;

REVOKE ALL ON FUNCTION public.cfl_fight_in_free_window(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.cfl_fight_in_free_window(bigint) TO anon, authenticated;

CREATE OR REPLACE VIEW public.v_fight_market_movement_lookback AS
SELECT m.*
FROM public.v_fight_market_movement m
WHERE public.current_user_is_pro()
   OR public.cfl_fight_in_free_window(m.fight_id);

COMMENT ON VIEW public.v_fight_market_movement_lookback IS
  'T-061 DRAFT. Movement for any card for Pro; for the free window only '
  'otherwise. v_fight_market_movement itself is NOT revoked: the current card '
  'stays free on every surface that reads it today.';

REVOKE ALL ON public.v_fight_market_movement_lookback FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.v_fight_market_movement_lookback TO anon, authenticated;

-- ---------------------------------------------------------------------------
-- 4. watchlists — ADDING a fight to a watchlist is Pro.
--    SELECT and DELETE stay owner-scoped and ungated: a member whose
--    subscription lapses can still see, and remove, what they made.
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "watchlist insert own" ON public.user_watchlist;
DROP POLICY IF EXISTS "watchlist insert own (pro)" ON public.user_watchlist;
CREATE POLICY "watchlist insert own (pro)" ON public.user_watchlist
  FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = user_id AND public.current_user_is_pro());

-- ---------------------------------------------------------------------------
-- 5. price_alerts / movement_alerts — the allowance, in its ONE place.
--    alerts_migration.sql §0 says the split lands here and nowhere else. This
--    is the line it documents, verbatim.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.alert_quota()
RETURNS integer
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path TO 'public'
AS $$
  SELECT CASE WHEN public.current_user_is_pro() THEN 50 ELSE 3 END;
$$;

COMMENT ON FUNCTION public.alert_quota() IS
  'Max active alerts per member. T-061: 50 for Pro, 3 for Free, decided by '
  'current_user_is_pro(). One number, one place.';

REVOKE ALL ON FUNCTION public.alert_quota() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.alert_quota() TO anon, authenticated;

-- ---------------------------------------------------------------------------
-- 6. since_last_visit, advanced_matchup — not built. There is no table or view
--    behind either, so there is nothing to gate, and entitlements.js keeps
--    both at enforced: false with gate kind 'not_built'.
-- ---------------------------------------------------------------------------
