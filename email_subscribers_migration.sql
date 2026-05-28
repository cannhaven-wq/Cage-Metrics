-- =============================================================================
-- Email subscribers (traffic funnel — weekly digest list)
-- =============================================================================
-- Lead-magnet table for visitors who want the weekly fight preview email
-- without yet creating a full account. Two-step funnel:
--     email-capture ──► weekly digest ──► CTA in digest ──► signup.html
--
-- A subscriber may also be a full profile (matching email), or not. We do NOT
-- foreign-key to profiles or auth.users — anon visitors can subscribe before
-- they ever sign up.
--
-- Re-run safe.
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.email_subscribers (
  id              bigserial PRIMARY KEY,
  email           text NOT NULL,
  source          text NOT NULL DEFAULT 'unknown',
  created_at      timestamptz NOT NULL DEFAULT now(),
  last_sent_at    timestamptz,
  unsubscribed_at timestamptz,
  unsubscribe_token text NOT NULL DEFAULT encode(gen_random_bytes(16), 'hex'),
  CONSTRAINT email_subscribers_email_lower CHECK (email = lower(email))
);

-- One active row per email. If somebody re-subscribes after unsubscribing we
-- want to update the existing row, not create a duplicate, so this needs to
-- be a UNIQUE constraint we can target with ON CONFLICT.
CREATE UNIQUE INDEX IF NOT EXISTS email_subscribers_email_uniq
  ON public.email_subscribers (email);

CREATE INDEX IF NOT EXISTS email_subscribers_active_idx
  ON public.email_subscribers (created_at)
  WHERE unsubscribed_at IS NULL;

ALTER TABLE public.email_subscribers ENABLE ROW LEVEL SECURITY;

-- Anon visitors may INSERT their own row. The frontend lowercases the email
-- before calling, but we double-enforce it with the CHECK constraint above.
-- Reads are admin-only — the list never goes to the browser. The digest sender
-- uses the service-role key in CI to bypass RLS.
DROP POLICY IF EXISTS email_subscribers_insert_anon ON public.email_subscribers;
CREATE POLICY email_subscribers_insert_anon
  ON public.email_subscribers
  FOR INSERT
  TO anon, authenticated
  WITH CHECK (true);

DROP POLICY IF EXISTS email_subscribers_admin_read ON public.email_subscribers;
CREATE POLICY email_subscribers_admin_read
  ON public.email_subscribers
  FOR SELECT
  TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.profiles p
    WHERE p.id = auth.uid() AND p.is_admin = true
  ));

-- Unsubscribe: the digest email's unsubscribe link points at a public
-- token-protected RPC so the recipient doesn't need to sign in. We expose
-- it as a SECURITY DEFINER function rather than a UPDATE policy so the
-- token comparison happens inside Postgres.
CREATE OR REPLACE FUNCTION public.unsubscribe_email(p_token text)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  updated int;
BEGIN
  UPDATE public.email_subscribers
     SET unsubscribed_at = now()
   WHERE unsubscribe_token = p_token
     AND unsubscribed_at IS NULL;
  GET DIAGNOSTICS updated = ROW_COUNT;
  RETURN updated > 0;
END;
$$;

GRANT EXECUTE ON FUNCTION public.unsubscribe_email(text) TO anon, authenticated;
