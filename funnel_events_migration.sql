-- =============================================================================
-- funnel_events_migration.sql — anonymous funnel counting. Applied 2026-09-21.
-- =============================================================================
-- PLAIN ENGLISH FIRST (CLAUDE.md): the site starts counting, anonymously, which
-- pages people open and which things they click — landing, Card Lab, opening a
-- fight, expanding a sportsbook table, signing up for the Brief, viewing
-- pricing. A visitor sees nothing new. No cookie is set, no new third party is
-- added, and nothing that identifies a person is stored.
--
-- Why it exists: CFL is about to build a paid tier and today cannot answer
-- "did anyone reach Card Lab" or "did anyone open a fight". The nine questions
-- this has to answer, and the exact event list, are in ANALYTICS_SCHEMA.md.
-- That document is the specification; this file is its storage.
--
-- Additive: one new table, one new view. Touches no existing table, no existing
-- policy and no trigger.
--
-- -----------------------------------------------------------------------------
-- The access shape, and why it is this shape
-- -----------------------------------------------------------------------------
-- INSERT is granted to anon and authenticated, because the browser writes here.
-- SELECT is granted to NEITHER. An analytics table a visitor can read back is a
-- list of what every other visitor did, and the browser has no reason to read
-- its own writes. Counts are read through v_funnel_daily, which is an
-- owner-rights view exposing aggregates only — never a row.
--
UPDATE and DELETE are revoked explicitly, and this is not belt-and-braces for
-- its own sake. A new table in `public` INHERITS broad grants from Supabase's
-- default privileges: on first apply, `anon` held UPDATE and DELETE on this
-- table. RLS denied both (no policy means deny), so nothing was exploitable —
-- but that is one layer doing the work of two, and it silently becomes zero
-- layers the day someone adds a permissive `FOR ALL` policy. Checked after
-- applying, not assumed; the check is what found it.
--
-- This is NOT an append-only table in the sense pre_fight_snapshots is: no
-- trigger enforces it and `service_role` can still prune. That is intended —
-- these are counts, not evidence, and a retention prune must stay possible.
--
-- -----------------------------------------------------------------------------
-- What is NOT stored, by construction
-- -----------------------------------------------------------------------------
-- No email, no name, no user id, no IP address, no device fingerprint, no
-- advertising identifier, and no bet amount. `session_id` is a random value the
-- browser keeps in sessionStorage for one session and never joins to an
-- account. The CHECK constraints below make the shape enforceable rather than
-- merely documented: props is capped and the event name must be a known one.
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.funnel_events (
  id          bigserial PRIMARY KEY,
  event       text        NOT NULL,
  session_id  text        NOT NULL,
  path        text,
  props       jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- The closed event list, mirrored in ANALYTICS_SCHEMA.md and in _shared.js
-- (cfl.EVENTS). A typo becomes a rejected insert rather than a phantom funnel
-- step nobody notices is missing. Adding an event means editing all three.
-- Dropped and recreated rather than added-if-absent. The add-if-absent form is
-- re-run safe and is NOT re-run correct: once the constraint exists it can
-- never learn a new name, so editing the list here would change the file and
-- not the database, and the two would silently disagree about which events are
-- legal. Five names were added on 2026-09-21 (watchlists and alerts) and that
-- is exactly the case it would have failed at.
ALTER TABLE public.funnel_events DROP CONSTRAINT IF EXISTS funnel_events_known_event;
DO $$
BEGIN
    ALTER TABLE public.funnel_events ADD CONSTRAINT funnel_events_known_event
      CHECK (event IN (
        'landing_view',
        'card_lab_view',
        'fight_opened',
        'market_lab_view',
        'book_breakdown_expanded',
        'market_sort_changed',
        'factor_lab_view',
        'methodology_opened',
        'fighter_page_view',
        'event_page_view',
        'best_price_clicked',
        'fight_shared',
        'card_brief_signup_started',
        'card_brief_signup_completed',
        'pricing_view',
        'pro_cta_clicked',
        'watchlist_added',
        'watchlist_removed',
        'alert_created',
        'alert_fired',
        'alert_clicked',
        'checkout_started',
        'checkout_completed',
        'return_visit'
      ));

  -- A runaway props object is how an analytics table becomes a data-retention
  -- problem. 2 KB is far more than any event in the schema needs.
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'funnel_events_props_bounded'
  ) THEN
    ALTER TABLE public.funnel_events ADD CONSTRAINT funnel_events_props_bounded
      CHECK (pg_column_size(props) <= 2048);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'funnel_events_session_bounded'
  ) THEN
    ALTER TABLE public.funnel_events ADD CONSTRAINT funnel_events_session_bounded
      CHECK (length(session_id) BETWEEN 8 AND 64);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS funnel_events_event_time_idx
  ON public.funnel_events (event, created_at DESC);
CREATE INDEX IF NOT EXISTS funnel_events_session_idx
  ON public.funnel_events (session_id, created_at);

ALTER TABLE public.funnel_events ENABLE ROW LEVEL SECURITY;

-- INSERT only, for both roles. See the access-shape note above.
DROP POLICY IF EXISTS funnel_events_anon_insert ON public.funnel_events;
CREATE POLICY funnel_events_anon_insert ON public.funnel_events
  FOR INSERT TO anon, authenticated
  WITH CHECK (true);

GRANT INSERT ON public.funnel_events TO anon, authenticated;
GRANT USAGE, SELECT ON SEQUENCE public.funnel_events_id_seq TO anon, authenticated;

-- Everything except INSERT is revoked, stated as revokes so a re-run cannot
-- leave an inherited grant behind. See the access-shape note above for why the
-- UPDATE/DELETE revokes are load-bearing rather than decorative.
REVOKE SELECT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON public.funnel_events FROM anon, authenticated;

COMMENT ON TABLE public.funnel_events IS
  'Anonymous funnel counts. INSERT only for anon/authenticated; no SELECT for '
  'either. No email, name, user id, IP or bet amount is ever stored. '
  'session_id is a per-session random value, never joined to an account. '
  'Specification: ANALYTICS_SCHEMA.md.';

-- ---------------------------------------------------------------------------
-- Reading it: aggregates only. Owner-rights view, the same pattern the market
-- views use, so a reader gets counts and never a row.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_funnel_daily AS
SELECT
  date_trunc('day', created_at)::date AS day,
  event,
  COUNT(*)::bigint                    AS events,
  COUNT(DISTINCT session_id)::bigint  AS sessions
FROM public.funnel_events
GROUP BY 1, 2;

COMMENT ON VIEW public.v_funnel_daily IS
  'Daily funnel counts per event. Aggregates only — funnel_events itself is '
  'not readable by anon or authenticated.';

GRANT SELECT ON public.v_funnel_daily TO anon, authenticated;
