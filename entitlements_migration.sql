-- =============================================================================
-- entitlements_migration.sql — who is Pro, decided in Postgres. 2026-09-21.
-- =============================================================================
-- PLAIN ENGLISH: the database learns, for itself, whether the person asking is
-- a paying member. Nothing on the site is paywalled by this file and no page
-- changes. It exists so that when something IS gated, the gate is somewhere a
-- browser cannot argue with.
--
-- Why now: `CLAUDE.md` has always said the frontend tier check is presentation
-- only and real enforcement is RLS — but there was nothing in the database to
-- enforce WITH. `cflAuth.isPremium()` was the only thing that knew, and it runs
-- on the reader's machine. A Pro feature gated in JavaScript is not gated.
--
-- =============================================================================
-- §1. THE P0 THIS SPRINT FOUND — privilege escalation via profiles UPDATE
-- =============================================================================
-- The UPDATE policy on `profiles` pinned `tier`, `tier_expires_at` and
-- `stripe_customer_id` in its WITH CHECK. It did NOT pin `is_admin` or
-- `beta_premium`. Both are security-bearing:
--
--   is_admin      current_user_is_admin() reads it, and that function IS the
--                 SELECT policy on `fight_odds` and `odds_books`; the
--                 `email_subscribers` read policy checks it directly.
--   beta_premium  cflAuth.getTier() ORs it to return 'premium'.
--
-- So any signed-in user could
--
--     update profiles set is_admin = true where id = auth.uid()
--
-- and then read **every subscriber's email address** and the whole of
-- `fight_odds`. `_auth.js::updateProfile` strips those fields and its comment
-- said "RLS will reject anyway". RLS did not. The publishable key is public by
-- design, so the REST endpoint is reachable without going through the JS at
-- all — stripping a field in the client is not a control.
--
-- Fixed by pinning both columns the same way the other three already were.
-- Verified as the `authenticated` role against a real profile, in a rolled-back
-- transaction: changing `is_admin` and changing `beta_premium` both fail
-- 42501, and an ordinary same-value write still succeeds so profile editing is
-- unaffected.
--
-- The lesson worth keeping: a WITH CHECK that lists the columns it protects
-- protects exactly those columns. Every column added to `profiles` after this
-- is unprotected until someone adds it to the list. Prefer pinning by
-- exception — see §4.
-- =============================================================================

DROP POLICY IF EXISTS "Users can update own profile (except tier)" ON public.profiles;
DROP POLICY IF EXISTS "Users can update own profile (identity fields pinned)" ON public.profiles;

CREATE POLICY "Users can update own profile (identity fields pinned)"
ON public.profiles
FOR UPDATE
USING (auth.uid() = id)
WITH CHECK (
  auth.uid() = id
  AND tier               IS NOT DISTINCT FROM (SELECT p.tier               FROM public.profiles p WHERE p.id = auth.uid())
  AND tier_expires_at    IS NOT DISTINCT FROM (SELECT p.tier_expires_at    FROM public.profiles p WHERE p.id = auth.uid())
  AND stripe_customer_id IS NOT DISTINCT FROM (SELECT p.stripe_customer_id FROM public.profiles p WHERE p.id = auth.uid())
  AND is_admin           IS NOT DISTINCT FROM (SELECT p.is_admin           FROM public.profiles p WHERE p.id = auth.uid())
  AND beta_premium       IS NOT DISTINCT FROM (SELECT p.beta_premium       FROM public.profiles p WHERE p.id = auth.uid())
);

-- =============================================================================
-- §2. THE ENTITLEMENT, computed in one place
-- =============================================================================
-- 'pro' when a paid tier is current, OR while the beta grant is on.
-- 'free' otherwise. There is no third answer, and no page decides it.
--
-- A SECOND BUG THIS FIXES: `tier_expires_at` was never honoured anywhere.
-- `cflAuth.getTier()` returned 'premium' from `tier` alone, so a lapsed
-- subscription would have kept full access indefinitely. That costs nothing
-- today because nobody has paid — and it would have cost money on the first
-- renewal failure, which is exactly the sprint that comes next.
CREATE OR REPLACE FUNCTION public.current_user_entitlement()
RETURNS text
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path TO 'public'
AS $$
  SELECT CASE
    WHEN auth.uid() IS NULL THEN 'free'
    WHEN EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = auth.uid()
        AND (
          p.beta_premium
          OR (p.tier IN ('premium', 'pro')
              AND (p.tier_expires_at IS NULL OR p.tier_expires_at > now()))
        )
    ) THEN 'pro'
    ELSE 'free'
  END;
$$;

COMMENT ON FUNCTION public.current_user_entitlement() IS
  'free | pro for the calling user. The single source of truth for entitlement. '
  'Honours tier_expires_at, which the frontend never did. Safe in RLS policies.';

CREATE OR REPLACE FUNCTION public.current_user_is_pro()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path TO 'public'
AS $$
  SELECT public.current_user_entitlement() = 'pro';
$$;

COMMENT ON FUNCTION public.current_user_is_pro() IS
  'Boolean form of current_user_entitlement(), for use directly in RLS policies '
  'and definer views. This is what a Pro gate must call — never a client claim.';

GRANT EXECUTE ON FUNCTION public.current_user_entitlement() TO anon, authenticated;
GRANT EXECUTE ON FUNCTION public.current_user_is_pro()      TO anon, authenticated;

-- =============================================================================
-- §3. What the browser may ask about ITSELF
-- =============================================================================
-- One row, always the caller's own. The browser needs to know what to render;
-- it must not be able to enumerate anyone else's standing. `is_beta` is exposed
-- so the UI can say "free during beta" honestly rather than implying payment.
CREATE OR REPLACE VIEW public.v_my_entitlement AS
SELECT
  auth.uid()                                AS user_id,
  public.current_user_entitlement()         AS entitlement,
  COALESCE(p.beta_premium, false)           AS is_beta,
  p.tier                                    AS paid_tier,
  p.tier_expires_at,
  (p.tier IN ('premium','pro')
   AND p.tier_expires_at IS NOT NULL
   AND p.tier_expires_at <= now())          AS paid_tier_expired
FROM (SELECT 1) dummy
LEFT JOIN public.profiles p ON p.id = auth.uid();

COMMENT ON VIEW public.v_my_entitlement IS
  'The calling user''s own entitlement, one row. Never another user''s. '
  'Presentation input only — a gate calls current_user_is_pro() server-side.';

GRANT SELECT ON public.v_my_entitlement TO anon, authenticated;

-- =============================================================================
-- §4. NOTHING IS GATED BY THIS FILE, and that is deliberate
-- =============================================================================
-- Applying the Free/Pro boundary is a separate step in the owner's sequence
-- (step 5), after Stripe. This file builds the machinery and gates nothing:
-- every view that was readable before is readable now, on the same terms.
--
-- When a gate is added, it belongs in the view or policy — e.g.
--
--     CREATE VIEW public.v_something_pro AS
--     SELECT ... FROM ... WHERE public.current_user_is_pro();
--
-- and never as an `if (cflAuth.isPro())` around a fetch. The browser decides
-- what to DRAW; the database decides what to SEND.
--
-- Pinning by exception, for whoever adds the next profiles column: the WITH
-- CHECK in §1 lists what is protected, so a new column is unprotected until it
-- is added there. `tests/entitlements.test.js` fails when `profiles` grows a
-- column that the policy does not mention, so the omission is caught rather
-- than discovered.
-- =============================================================================
