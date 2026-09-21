-- =============================================================================
-- alerts_migration.sql — watchlists and market alerts. 2026-09-21.
-- =============================================================================
-- PLAIN ENGLISH FIRST (CLAUDE.md): a signed-in member can star the fights they
-- care about, and ask CFL to email them when a price they want shows up, or
-- when a market moves further than they are willing to ignore. Nobody who has
-- not asked for an email gets one. Nothing on the site is paywalled by this.
--
-- -----------------------------------------------------------------------------
-- THE RULE THIS FILE EXISTS TO ENFORCE
-- -----------------------------------------------------------------------------
-- An alert must never fire from a market comparison CFL would refuse to print.
--
-- Card Lab will not show a movement figure computed over fewer than three
-- matched books, because CFL measured that error at up to 12.7 points and three
-- markets that had not moved reading as moving 3+ (D-012). An email is a
-- STRONGER claim than a number on a page: the member did not go looking for it,
-- it arrives with their attention already granted, and it may send them to a
-- sportsbook to act. So the alert path applies the same refusals as the display
-- path and several more, and every refusal has a NAME — `v_fight_alert_market`
-- below emits `alert_refusal` the same way `v_fight_market_movement` emits
-- `movement_status`. A silent non-fire is indistinguishable from a broken job.
--
-- The refusals, in the order they are checked:
--
--   fight_settled            the fight is over. Never alert on a result.
--   event_past               the card has been and gone.
--   fight_inactive           the bout came off the card.
--   stale_market             our newest quote is older than 45 minutes. This is
--                            the frozen CLV staleness limit, reused deliberately:
--                            a price we cannot vouch for is a price we must not
--                            send somebody to a sportsbook for.
--   thin_book_count          fewer than 3 sportsbooks are quoting at all.
--   insufficient_matched_books  movement is NULL because the matched cohort is
--                            under three (movement alerts only).
--   no_broad_capture         CFL never held three books at once on this fight,
--                            so there is no honest baseline (movement only).
--
-- NOTHING WIDENS A COHORT TO PRODUCE AN ALERT. There is no fallback path, no
-- "best effort" comparison and no second-choice baseline. If the market cannot
-- be described honestly, the member hears nothing, and the reason is recorded.
--
-- -----------------------------------------------------------------------------
-- THE COHORT FINGERPRINT, AND WHY A COUNT IS NOT ENOUGH
-- -----------------------------------------------------------------------------
-- A movement alert fires once and must then know when to speak again. The naive
-- re-arm subtracts the movement value now from the value when it last fired.
-- That is exactly the mixed-cohort error D-012 removed from the product: the
-- two readings can be medians over DIFFERENT sets of books, and their
-- difference is then a number about bookmaker turnover rather than about the
-- market.
--
-- So an alert stores the fingerprint of the cohort it fired over --- an md5 of
-- the sorted matched book ids, not merely how many there were, because one book
-- leaving as another joins keeps the count identical and changes the median.
-- If the fingerprint or the baseline instant has changed, the alert RE-BASELINES
-- SILENTLY and does not fire. It costs one notification. The alternative costs
-- the member's trust in every notification.
--
-- -----------------------------------------------------------------------------
-- READY FOR PRO, GATED BY NOTHING (D-019)
-- -----------------------------------------------------------------------------
-- Watchlists and alerts are intended to become CFL Pro features once checkout
-- exists. NOTHING HERE IS GATED TODAY and that is deliberate: enforcement is
-- T-061, which D-019 moved behind the gates that make paying possible. There is
-- no paywall in front of a product nobody can buy.
--
-- When the boundary does land, it lands in ONE place: `public.alert_quota()`
-- below. Today it returns the same allowance to everyone. The gate is the
-- commented line inside it, and nowhere else --- not in a policy, not in the
-- browser, not in the sender.
--
-- Re-run safe. Additive: four new tables, three new views, one function. Touches
-- no existing table, policy or trigger.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 0. The allowance. The single place a Free/Pro split will ever live.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.alert_quota()
RETURNS integer
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path TO 'public'
AS $$
  -- T-061 turns this into:
  --     SELECT CASE WHEN public.current_user_is_pro() THEN 50 ELSE 3 END;
  -- and nothing else in this file changes. Until then everyone gets the same
  -- allowance, which exists to protect the sender from a runaway account rather
  -- than to sell anything.
  SELECT 50;
$$;

COMMENT ON FUNCTION public.alert_quota() IS
  'Max active alerts per member. One number, one place: this is where the '
  'Free/Pro split lands at T-061. Returns the same value for everyone today.';

REVOKE ALL ON FUNCTION public.alert_quota() FROM public;
GRANT EXECUTE ON FUNCTION public.alert_quota() TO anon, authenticated;

-- -----------------------------------------------------------------------------
-- 1. user_watchlist — the fights a member is following.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.user_watchlist (
  user_id    uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  fight_id   bigint      NOT NULL REFERENCES public.fights(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, fight_id)
);

CREATE INDEX IF NOT EXISTS idx_user_watchlist_user
  ON public.user_watchlist (user_id, created_at DESC);

ALTER TABLE public.user_watchlist ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "watchlist select own" ON public.user_watchlist;
DROP POLICY IF EXISTS "watchlist insert own" ON public.user_watchlist;
DROP POLICY IF EXISTS "watchlist delete own" ON public.user_watchlist;

CREATE POLICY "watchlist select own" ON public.user_watchlist
  FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "watchlist insert own" ON public.user_watchlist
  FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "watchlist delete own" ON public.user_watchlist
  FOR DELETE TO authenticated USING (auth.uid() = user_id);
-- No UPDATE policy and none needed: the row is (who, which fight) and there is
-- nothing in it to change. Adding one later would need a WITH CHECK pinning
-- user_id, or a member could hand their row to somebody else.

-- REVOKE FROM BOTH ROLES, then grant. Revoking from `anon` alone is not enough
-- and this is not theoretical: on first apply `authenticated` still held
-- TRUNCATE, UPDATE, DELETE, TRIGGER and REFERENCES here, inherited from
-- Supabase's default privileges. TRUNCATE is the one that matters --- it
-- BYPASSES ROW LEVEL SECURITY entirely, so any signed-in member could have
-- emptied every other member's watchlist and alerts, with RLS never consulted.
-- Verified after applying; the migration's own text is not the result.
REVOKE ALL ON public.user_watchlist FROM anon, authenticated;
GRANT SELECT, INSERT, DELETE ON public.user_watchlist TO authenticated;

-- -----------------------------------------------------------------------------
-- 2. user_alerts — the alert definitions, and their armed state.
-- -----------------------------------------------------------------------------
-- kind:
--   price_target  fire when the best price for `side` reaches `target_american`
--                 or better. "Better" is the American number and nothing else
--                 (CLAUDE.md), so +150 beats +120 beats -110 beats -200, and
--                 the test is a single >=.
--   market_move   fire when matched-cohort movement reaches `threshold_pts` in
--                 `direction`.
--
-- The armed_* columns are the memory described in the header. They are written
-- only by the sender (service_role); a member can read them and cannot forge
-- them, because forging them is how you make CFL email you in a loop.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.user_alerts (
  id                bigserial PRIMARY KEY,
  user_id           uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  fight_id          bigint      NOT NULL REFERENCES public.fights(id) ON DELETE CASCADE,
  kind              text        NOT NULL CHECK (kind IN ('price_target','market_move')),
  side              char(1)     CHECK (side IN ('A','B')),
  target_american   integer,
  threshold_pts     numeric(5,2) CHECK (threshold_pts IS NULL OR threshold_pts > 0),
  direction         text        CHECK (direction IN ('toward_a','toward_b','either')),
  channel           text        NOT NULL DEFAULT 'email' CHECK (channel IN ('email')),
  is_active         boolean     NOT NULL DEFAULT true,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),

  -- written by the sender only
  last_evaluated_at timestamptz,
  last_fired_at     timestamptz,
  fire_count        integer     NOT NULL DEFAULT 0,
  armed_value       numeric(8,3),
  armed_cohort_fp   text,
  armed_baseline_at timestamptz,

  -- A shape that cannot be half-specified. A price alert without a side and a
  -- target, or a movement alert without a threshold and a direction, is not a
  -- stricter alert --- it is an alert whose condition is undefined, and an
  -- undefined condition either never fires or always does.
  CONSTRAINT user_alerts_shape CHECK (
    (kind = 'price_target' AND side IS NOT NULL AND target_american IS NOT NULL
       AND threshold_pts IS NULL AND direction IS NULL)
    OR
    (kind = 'market_move' AND threshold_pts IS NOT NULL AND direction IS NOT NULL
       AND target_american IS NULL)
  ),
  -- One alert of a kind per side per fight per member: two identical alerts are
  -- two emails about one event, which is the thing this sprint exists not to do.
  -- NOT a table constraint, because `side` is NULL for a symmetric movement
  -- alert and Postgres treats NULLs in a UNIQUE constraint as all distinct ---
  -- which would have let one member stack unlimited movement alerts on one
  -- fight and get one email per copy. The unique INDEX below coalesces instead.
  CONSTRAINT user_alerts_side_required_for_price
    CHECK (kind <> 'price_target' OR side IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_alerts_one_per_target
  ON public.user_alerts (user_id, fight_id, kind, COALESCE(side, '*'));

CREATE INDEX IF NOT EXISTS idx_user_alerts_user
  ON public.user_alerts (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_alerts_active
  ON public.user_alerts (fight_id) WHERE is_active;

ALTER TABLE public.user_alerts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "alerts select own" ON public.user_alerts;
DROP POLICY IF EXISTS "alerts insert own" ON public.user_alerts;
DROP POLICY IF EXISTS "alerts update own" ON public.user_alerts;
DROP POLICY IF EXISTS "alerts delete own" ON public.user_alerts;

CREATE POLICY "alerts select own" ON public.user_alerts
  FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "alerts insert own" ON public.user_alerts
  FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "alerts delete own" ON public.user_alerts
  FOR DELETE TO authenticated USING (auth.uid() = user_id);

-- The member may update their own alert. WHICH COLUMNS they may update is
-- enforced by the trigger below rather than by a WITH CHECK subquery.
--
-- The `profiles` policy pins its columns with `IS NOT DISTINCT FROM (SELECT ...
-- WHERE p.id = auth.uid())`, which works there because there is exactly one
-- profile per member. This table has many rows per member, so the subquery
-- would have to key on the NEW row's own id --- a self-reference inside the
-- table's own policy, re-entering RLS on every check. A trigger says the same
-- thing without that, and it applies to every path into the table rather than
-- to the `authenticated` role alone.
CREATE POLICY "alerts update own" ON public.user_alerts
  FOR UPDATE TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

REVOKE ALL ON public.user_alerts FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_alerts TO authenticated;
GRANT USAGE, SELECT ON SEQUENCE public.user_alerts_id_seq TO authenticated;

-- The suppression memory is the sender's, not the member's.
--
-- armed_value, armed_cohort_fp, armed_baseline_at, last_fired_at, fire_count
-- and last_evaluated_at are what stop CFL emailing somebody twice about one
-- thing, and what stop a movement alert firing off a comparison CFL would
-- refuse to print. A member who could clear them could put themselves in a
-- notification loop; a member who could set armed_cohort_fp could defeat the
-- cohort check described at the top of this file.
--
-- Same lesson as the profiles P0 (D-017): protection covers exactly the columns
-- it names, so EVERY column added to this table is unprotected until it is
-- added here. `tests/alerts.test.js` asserts on the omission.
--
-- It restores rather than raises, deliberately. A client that reads a row,
-- flips `is_active` and writes the whole row back is doing something ordinary,
-- not something hostile; failing that write teaches nothing and breaks the UI.
-- The write succeeds and the sender's columns simply do not move.
--
-- TWO CORRECTIONS, both found by testing the trigger's behaviour rather than
-- reading it, and neither visible on the page:
--
--   1. The first version keyed on `auth.role()`, the JWT claim. A migration or
--      a psql session has no JWT, so auth.role() is NULL and the trigger
--      reverted the SENDER'S own writes --- the alerts would never have armed.
--   2. The second version used `current_user` but was SECURITY DEFINER, and
--      inside a definer function `current_user` is the function's OWNER, not
--      the caller. The guard was therefore ALWAYS true: the protection read as
--      though it worked and did nothing at all.
--
-- It is SECURITY INVOKER (the default) because it needs no elevated rights ---
-- it touches NEW and nothing else --- and because invoker is what makes
-- `current_user` mean "the role actually doing this write".
CREATE OR REPLACE FUNCTION public.user_alerts_pin_sender_columns()
RETURNS trigger
LANGUAGE plpgsql
SET search_path TO 'public'
AS $$
BEGIN
  IF current_user IN ('service_role', 'postgres', 'supabase_admin') THEN
    RETURN NEW;                      -- the sender, which owns these columns
  END IF;
  NEW.last_evaluated_at := OLD.last_evaluated_at;
  NEW.last_fired_at     := OLD.last_fired_at;
  NEW.fire_count        := OLD.fire_count;
  NEW.armed_value       := OLD.armed_value;
  NEW.armed_cohort_fp   := OLD.armed_cohort_fp;
  NEW.armed_baseline_at := OLD.armed_baseline_at;
  NEW.user_id           := OLD.user_id;   -- never hand a row to somebody else
  NEW.created_at        := OLD.created_at;
  NEW.updated_at        := now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_user_alerts_pin ON public.user_alerts;
CREATE TRIGGER trg_user_alerts_pin
  BEFORE UPDATE ON public.user_alerts
  FOR EACH ROW EXECUTE FUNCTION public.user_alerts_pin_sender_columns();

-- The allowance, enforced where it cannot be skipped. A browser check is a
-- convenience; this is the control.
CREATE OR REPLACE FUNCTION public.user_alerts_quota_check()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
DECLARE
  n integer;
  q integer := public.alert_quota();
BEGIN
  SELECT count(*) INTO n
  FROM public.user_alerts
  WHERE user_id = NEW.user_id AND is_active;
  IF n >= q THEN
    RAISE EXCEPTION 'alert quota reached (% active alerts allowed)', q
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_user_alerts_quota ON public.user_alerts;
CREATE TRIGGER trg_user_alerts_quota
  BEFORE INSERT ON public.user_alerts
  FOR EACH ROW WHEN (NEW.is_active)
  EXECUTE FUNCTION public.user_alerts_quota_check();

-- -----------------------------------------------------------------------------
-- 3. user_alert_prefs — how loud a member is willing for this to be.
-- -----------------------------------------------------------------------------
-- Quiet hours are stored in UTC and are NULL by default, which means OFF. CFL
-- does not know what time zone a member is in and will not guess one: a guessed
-- quiet window silences the alerts somebody asked for, at the hours they most
-- wanted them. When the UI collects a zone this becomes useful; until then the
-- protection that actually works is the cooldown and the daily cap.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.user_alert_prefs (
  user_id          uuid        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email_enabled    boolean     NOT NULL DEFAULT true,
  cooldown_minutes integer     NOT NULL DEFAULT 360
                     CHECK (cooldown_minutes BETWEEN 15 AND 10080),
  max_per_day      integer     NOT NULL DEFAULT 6
                     CHECK (max_per_day BETWEEN 1 AND 50),
  quiet_start_utc  smallint    CHECK (quiet_start_utc BETWEEN 0 AND 23),
  quiet_end_utc    smallint    CHECK (quiet_end_utc   BETWEEN 0 AND 23),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.user_alert_prefs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "alert prefs select own" ON public.user_alert_prefs;
DROP POLICY IF EXISTS "alert prefs insert own" ON public.user_alert_prefs;
DROP POLICY IF EXISTS "alert prefs update own" ON public.user_alert_prefs;

CREATE POLICY "alert prefs select own" ON public.user_alert_prefs
  FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "alert prefs insert own" ON public.user_alert_prefs
  FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "alert prefs update own" ON public.user_alert_prefs
  FOR UPDATE TO authenticated
  USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

REVOKE ALL ON public.user_alert_prefs FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.user_alert_prefs TO authenticated;

-- -----------------------------------------------------------------------------
-- 4. user_alert_deliveries — what was actually sent, and the dedupe primitive.
-- -----------------------------------------------------------------------------
-- `dedupe_key` is UNIQUE, and that is the duplicate suppression. Not a check in
-- the sender: the sender can run twice concurrently (a re-dispatched workflow, a
-- retry, two runners), and two concurrent passes both survive a SELECT-then-
-- INSERT test. The insert is attempted FIRST and a 23505 means "somebody else
-- already told them", exactly as billing_events handles Stripe's at-least-once
-- delivery (D-018).
--
-- A member may READ their own delivery history and may not write or erase it.
-- Erasing a delivery row is how you defeat the dedupe key.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.user_alert_deliveries (
  id           bigserial PRIMARY KEY,
  user_id      uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  alert_id     bigint      REFERENCES public.user_alerts(id) ON DELETE SET NULL,
  fight_id     bigint      REFERENCES public.fights(id) ON DELETE SET NULL,
  kind         text        NOT NULL,
  dedupe_key   text        NOT NULL UNIQUE,
  fired_at     timestamptz NOT NULL DEFAULT now(),
  channel      text        NOT NULL DEFAULT 'email',
  send_status  text        NOT NULL DEFAULT 'pending'
                 CHECK (send_status IN ('pending','sent','failed','dry_run','suppressed')),
  suppressed_reason text,
  -- The numbers exactly as they were sent. If a member ever says "you told me
  -- it moved six points and it had not", this is the answer, and it is the
  -- reason the row is written before the email leaves rather than after.
  payload      jsonb       NOT NULL DEFAULT '{}'::jsonb,
  sent_at      timestamptz,
  error        text
);

CREATE INDEX IF NOT EXISTS idx_alert_deliveries_user
  ON public.user_alert_deliveries (user_id, fired_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_deliveries_alert
  ON public.user_alert_deliveries (alert_id, fired_at DESC);

ALTER TABLE public.user_alert_deliveries ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "deliveries select own" ON public.user_alert_deliveries;
CREATE POLICY "deliveries select own" ON public.user_alert_deliveries
  FOR SELECT TO authenticated USING (auth.uid() = user_id);
-- No INSERT, UPDATE or DELETE policy for any member role, at any tier. The
-- sender writes these with service_role, which bypasses RLS.

REVOKE ALL ON public.user_alert_deliveries FROM anon, authenticated;
GRANT SELECT ON public.user_alert_deliveries TO authenticated;

-- -----------------------------------------------------------------------------
-- 5. v_fight_alert_market — everything an alert may be decided from, and the
--    named reason when it may not be decided at all.
-- -----------------------------------------------------------------------------
-- This view is the ONLY market input the sender reads. That is the point: the
-- refusals live in one place, next to the numbers they refuse, instead of being
-- re-implemented in a Node script where a later edit could quietly relax one.
--
-- THREE REFUSAL COLUMNS, NOT ONE, BECAUSE A PRICE AND A MOVE ARE DIFFERENT
-- CLAIMS
--
--   alert_refusal   universal. The fight is over, off the card, or CFL holds
--                   fewer than three sportsbooks on it. Nothing may be said.
--   price_refusal   adds the 120-minute ceiling. A PRICE IS AN OFFER: it says
--                   "this number is available at this book" and a member may
--                   act on it at a sportsbook.
--   move_refusal    adds the matched-cohort rules and a 24-hour ceiling. A MOVE
--                   IS A HISTORICAL FACT: "this market moved four points since
--                   our first broad capture" is as true three hours later.
--
-- The first version of this view applied ONE 45-minute ceiling to both,
-- borrowed from the frozen CLV staleness limit. That limit governs a scored
-- settlement price, which is a different job, and against CFL's real capture
-- cadence — 5 minutes only while a card is in flow, hourly on card day and the
-- day before, otherwise ONE capture a day (CLAUDE.md) — it means no alert of
-- any kind can ever fire. Measured on the live table: 0 of 79 fights alertable.
-- The feature would have shipped permanently silent, and a silent alert system
-- is indistinguishable from a broken one.
--
-- Every email prints the capture time and the book count beside the number
-- regardless, exactly as the display path does. Freshness is disclosed, not
-- implied; the ceilings are the point past which disclosure stops being enough.
--
-- NOTHING WIDENS A COHORT TO PRODUCE AN ALERT. There is no fallback path, no
-- best-effort comparison and no second-choice baseline.
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS public.v_my_watchlist;
DROP VIEW IF EXISTS public.v_my_alerts;
DROP VIEW IF EXISTS public.v_fight_alert_market;

CREATE VIEW public.v_fight_alert_market AS
WITH fp AS (
  -- The cohort fingerprint. md5 over the SORTED matched book ids, not the
  -- count: one book leaving as another joins holds the count still and moves
  -- the median, and a re-arm compared across that is a statement about
  -- bookmaker turnover rather than about the market.
  SELECT b.fight_id,
         md5(string_agg(b.book_id::text, ',' ORDER BY b.book_id)) AS cohort_fp,
         count(*)::integer                                        AS cohort_books
  FROM public.v_fight_market_movement_books b
  WHERE b.in_matched_cohort
  GROUP BY b.fight_id
), base AS (
  SELECT
    m.fight_id, m.event_id, e.name AS event_name, e.event_date,
    f.fighter_a_name, f.fighter_b_name, f.is_main_event, f.bout_order,
    m.market_p_a, m.book_count, m.last_updated,
    m.best_american_a, m.best_book_a, m.best_american_b, m.best_book_b,
    m.book_spread_pts,
    (EXTRACT(EPOCH FROM (now() - m.last_updated)) / 60.0)::numeric AS market_age_minutes,
    m.movement_pts_a, m.movement_status, m.matched_book_count,
    m.baseline_at, m.movement_method,
    COALESCE(fp.cohort_fp, '')   AS cohort_fp,
    COALESCE(fp.cohort_books, 0) AS cohort_books,
    CASE
      WHEN f.winner_id IS NOT NULL OR f.method IS NOT NULL THEN 'fight_settled'
      WHEN f.is_active IS FALSE                            THEN 'fight_inactive'
      WHEN e.event_date < (now() AT TIME ZONE 'UTC')::date THEN 'event_past'
      WHEN m.last_updated IS NULL                          THEN 'no_market'
      WHEN COALESCE(m.book_count, 0) < 3                   THEN 'thin_book_count'
      ELSE NULL
    END AS alert_refusal
  FROM public.v_fight_market_movement m
  JOIN public.fights f ON f.id = m.fight_id
  JOIN public.events e ON e.id = m.event_id
  LEFT JOIN fp         ON fp.fight_id = m.fight_id
)
SELECT b.*,
  CASE
    WHEN b.alert_refusal IS NOT NULL THEN b.alert_refusal
    WHEN b.market_age_minutes > 120  THEN 'stale_for_price'
    WHEN b.best_american_a IS NULL OR b.best_american_b IS NULL THEN 'no_best_price'
    ELSE NULL
  END AS price_refusal,
  CASE
    WHEN b.alert_refusal IS NOT NULL                      THEN b.alert_refusal
    WHEN b.movement_status = 'no_broad_capture'           THEN 'no_broad_capture'
    WHEN b.movement_status = 'insufficient_matched_books' THEN 'insufficient_matched_books'
    WHEN b.movement_pts_a IS NULL                         THEN 'no_movement_figure'
    WHEN b.cohort_books < 3                               THEN 'insufficient_matched_books'
    WHEN b.market_age_minutes > 1440                      THEN 'stale_for_move'
    ELSE NULL
  END AS move_refusal
FROM base b;

COMMENT ON VIEW public.v_fight_alert_market IS
  'The only market input the alert sender reads. alert_refusal is universal; '
  'price_refusal adds the 120-minute offer ceiling; move_refusal adds the '
  'matched-cohort rules and a 24-hour ceiling. A price is an offer, a move is '
  'a historical fact, and they do not share a staleness rule. Refusals are '
  'named, never silent.';

GRANT SELECT ON public.v_fight_alert_market TO anon, authenticated;

-- -----------------------------------------------------------------------------
-- 6. v_my_watchlist / v_my_alerts — a member's own rows, for rendering.
-- -----------------------------------------------------------------------------
-- Both filter on auth.uid() and are security_invoker, so RLS on the underlying
-- table does the work and these views cannot widen it. They exist so the
-- watchlist page makes one request instead of four.
-- -----------------------------------------------------------------------------
CREATE VIEW public.v_my_watchlist WITH (security_invoker = true) AS
SELECT w.user_id, w.fight_id, w.created_at,
  am.event_id, am.event_name, am.event_date,
  am.fighter_a_name, am.fighter_b_name, am.is_main_event, am.bout_order,
  am.market_p_a, am.book_count, am.last_updated, am.market_age_minutes,
  am.best_american_a, am.best_book_a, am.best_american_b, am.best_book_b,
  am.movement_pts_a, am.movement_status, am.matched_book_count,
  am.alert_refusal, am.price_refusal, am.move_refusal,
  (SELECT count(*) FROM public.user_alerts a
    WHERE a.user_id = w.user_id AND a.fight_id = w.fight_id AND a.is_active)::integer
    AS active_alert_count
FROM public.user_watchlist w
LEFT JOIN public.v_fight_alert_market am ON am.fight_id = w.fight_id
WHERE w.user_id = auth.uid();

GRANT SELECT ON public.v_my_watchlist TO authenticated;

-- `alert_state` is what the member is owed as an explanation when an alert is
-- quiet. A member who cannot see WHY nothing arrived assumes the feature is
-- broken, and they are right to: a silent refusal and a bug look identical
-- from outside.
CREATE VIEW public.v_my_alerts WITH (security_invoker = true) AS
SELECT a.id, a.user_id, a.fight_id, a.kind, a.side, a.target_american,
  a.threshold_pts, a.direction, a.channel, a.is_active,
  a.created_at, a.last_fired_at, a.fire_count,
  am.event_name, am.event_date, am.fighter_a_name, am.fighter_b_name,
  am.best_american_a, am.best_book_a, am.best_american_b, am.best_book_b,
  am.movement_pts_a, am.movement_status, am.matched_book_count,
  am.book_count, am.market_age_minutes,
  am.alert_refusal, am.price_refusal, am.move_refusal,
  CASE
    WHEN NOT a.is_active           THEN 'paused'
    WHEN am.fight_id IS NULL       THEN 'no_market_yet'
    WHEN a.kind = 'price_target' AND am.price_refusal IS NOT NULL THEN am.price_refusal
    WHEN a.kind = 'market_move'  AND am.move_refusal  IS NOT NULL THEN am.move_refusal
    ELSE 'watching'
  END AS alert_state
FROM public.user_alerts a
LEFT JOIN public.v_fight_alert_market am ON am.fight_id = a.fight_id
WHERE a.user_id = auth.uid();

GRANT SELECT ON public.v_my_alerts TO authenticated;
