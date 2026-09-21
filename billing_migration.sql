-- =============================================================================
-- billing_migration.sql — the subscription record. 2026-09-21.
-- =============================================================================
-- PLAIN ENGLISH: the database gets somewhere to record what Stripe tells us
-- about a member's subscription, and a log of every message Stripe sends so the
-- same message can never be applied twice. **No payment can be taken yet** —
-- the checkout function refuses while T-054 and T-048 stand.
--
-- -----------------------------------------------------------------------------
-- §Where entitlement actually comes from, still
-- -----------------------------------------------------------------------------
-- Nothing here invents a second answer. `current_user_entitlement()` (D-017)
-- reads `profiles.tier` and `profiles.tier_expires_at`, and the webhook's only
-- job is to keep those two columns true to Stripe. That is deliberate: one
-- entitlement rule, one place, and billing is an input to it rather than a
-- parallel system.
--
-- It also means **expiry does the work of a grace period**. A subscription that
-- goes `past_due` keeps `tier_expires_at` at Stripe's `current_period_end`,
-- so the member keeps access while Stripe retries the card and loses it
-- automatically when the period runs out. No separate grace timer to get wrong.
--
-- -----------------------------------------------------------------------------
-- §Who may write
-- -----------------------------------------------------------------------------
-- Only `service_role`, i.e. only the webhook. `anon` and `authenticated` get
-- NOTHING on `billing_events` — not INSERT, not SELECT. A member reads their
-- own standing through `v_my_entitlement`, which already exists and already
-- scopes to `auth.uid()`.
--
-- The profiles columns this writes (`tier`, `tier_expires_at`,
-- `stripe_customer_id`) are the ones the UPDATE policy pins, so a member still
-- cannot set their own subscription state. That pin is what T-059 fixed; this
-- file depends on it and must not be applied without it.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Every Stripe event we have processed. Idempotency first, audit second.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.billing_events (
  id              bigserial PRIMARY KEY,
  -- Stripe's own event id. UNIQUE is the whole idempotency mechanism: Stripe
  -- retries deliveries, and at-least-once delivery means a duplicate WILL
  -- arrive. The insert is attempted FIRST; if it conflicts, the event has
  -- already been applied and the handler stops.
  stripe_event_id text        NOT NULL UNIQUE,
  event_type      text        NOT NULL,
  user_id         uuid        REFERENCES auth.users(id) ON DELETE SET NULL,
  stripe_customer_id text,
  subscription_id text,
  -- what the handler decided, so a disputed account can be reconstructed from
  -- this table alone without replaying Stripe
  applied_tier       text,
  applied_expires_at timestamptz,
  outcome         text        NOT NULL,
  detail          text,
  received_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS billing_events_user_idx     ON public.billing_events (user_id, received_at DESC);
CREATE INDEX IF NOT EXISTS billing_events_customer_idx ON public.billing_events (stripe_customer_id, received_at DESC);
CREATE INDEX IF NOT EXISTS billing_events_type_idx     ON public.billing_events (event_type, received_at DESC);

ALTER TABLE public.billing_events ENABLE ROW LEVEL SECURITY;

-- No policy is created on purpose. RLS with no policy denies every role that
-- is subject to it; `service_role` bypasses RLS and is the only writer.
REVOKE ALL ON public.billing_events FROM anon, authenticated;
REVOKE ALL ON SEQUENCE public.billing_events_id_seq FROM anon, authenticated;

COMMENT ON TABLE public.billing_events IS
  'Every Stripe webhook event, one row, deduplicated by stripe_event_id. '
  'service_role only: anon and authenticated have no access of any kind. '
  'Records what the handler DECIDED so an account can be reconstructed here.';

-- ---------------------------------------------------------------------------
-- 2. Subscription state on the profile.
--
--    `tier` and `tier_expires_at` already exist and are what entitlement
--    reads. These add the Stripe-side facts needed to reconcile, support a
--    member, and render honest copy ("your membership ends on the 14th"
--    rather than "cancelled").
-- ---------------------------------------------------------------------------
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS stripe_subscription_id text;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS subscription_status    text;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS cancel_at_period_end   boolean NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS profiles_stripe_customer_idx
  ON public.profiles (stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS profiles_stripe_subscription_idx
  ON public.profiles (stripe_subscription_id) WHERE stripe_subscription_id IS NOT NULL;

COMMENT ON COLUMN public.profiles.subscription_status IS
  'Stripe subscription status verbatim (active/trialing/past_due/canceled/...). '
  'Entitlement does NOT read this — it reads tier + tier_expires_at. This is '
  'for support and for honest UI copy.';

-- ---------------------------------------------------------------------------
-- 3. THE PIN, EXTENDED. T-059 fixed a privilege escalation by pinning the
--    security-bearing columns in the profiles UPDATE policy. This file adds
--    three more columns, and a WITH CHECK protects exactly the columns it
--    names — so they are added to the pin in the same migration that creates
--    them. Otherwise a member could set their own subscription_status.
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS "Users can update own profile (identity fields pinned)" ON public.profiles;

CREATE POLICY "Users can update own profile (identity fields pinned)"
ON public.profiles
FOR UPDATE
USING (auth.uid() = id)
WITH CHECK (
  auth.uid() = id
  AND tier                   IS NOT DISTINCT FROM (SELECT p.tier                   FROM public.profiles p WHERE p.id = auth.uid())
  AND tier_expires_at        IS NOT DISTINCT FROM (SELECT p.tier_expires_at        FROM public.profiles p WHERE p.id = auth.uid())
  AND stripe_customer_id     IS NOT DISTINCT FROM (SELECT p.stripe_customer_id     FROM public.profiles p WHERE p.id = auth.uid())
  AND is_admin               IS NOT DISTINCT FROM (SELECT p.is_admin               FROM public.profiles p WHERE p.id = auth.uid())
  AND beta_premium           IS NOT DISTINCT FROM (SELECT p.beta_premium           FROM public.profiles p WHERE p.id = auth.uid())
  AND stripe_subscription_id IS NOT DISTINCT FROM (SELECT p.stripe_subscription_id FROM public.profiles p WHERE p.id = auth.uid())
  AND subscription_status    IS NOT DISTINCT FROM (SELECT p.subscription_status    FROM public.profiles p WHERE p.id = auth.uid())
  AND cancel_at_period_end   IS NOT DISTINCT FROM (SELECT p.cancel_at_period_end   FROM public.profiles p WHERE p.id = auth.uid())
);

-- ---------------------------------------------------------------------------
-- 4. The member's own billing state, for rendering. Own row only.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.v_my_billing AS
SELECT
  auth.uid()                              AS user_id,
  public.current_user_entitlement()       AS entitlement,
  p.subscription_status,
  p.cancel_at_period_end,
  p.tier_expires_at                       AS current_period_end,
  (p.stripe_customer_id IS NOT NULL)      AS has_billing_account,
  COALESCE(p.beta_premium, false)         AS is_beta
FROM (SELECT 1) dummy
LEFT JOIN public.profiles p ON p.id = auth.uid();

COMMENT ON VIEW public.v_my_billing IS
  'The calling member''s own billing state, one row. Never another member''s. '
  'Deliberately omits stripe ids - the browser has no use for them.';

GRANT SELECT ON public.v_my_billing TO anon, authenticated;
