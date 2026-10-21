-- =============================================================================
-- card_brief_double_optin_migration.sql — T-090, Card Brief double opt-in.
-- STATUS: PROPOSED. NOT APPLIED. Applying it is L3 (CRITICAL_GATES item 5,
-- owner decision D-027 / D-T088-5). Do not apply it by habit.
-- =============================================================================
-- PLAIN ENGLISH FIRST (CLAUDE.md): anyone can type anyone's address into the
-- Card Brief form. So before the Brief is ever emailed to an address, that
-- address gets one email with a link in it, and only a click on that link
-- marks it confirmed. The Brief goes only to confirmed addresses.
--
-- WHAT IT ADDS to public.email_subscribers (additive; no row is changed)
--   confirmed_at              when the address clicked its link. NULL = not
--                             confirmed, and the Brief never goes to it.
--   confirm_token_hash        sha256 (lower-case hex) of the link's token. The
--                             raw token is NEVER stored: it exists only in the
--                             email. Someone who can read this table still
--                             cannot confirm an address.
--   confirm_token_expires_at  the link stops working after this instant.
--   confirm_sent_at           when the confirmation email was last recorded
--                             as issued (recorded BEFORE it is sent).
--   confirm_send_count        how many confirmation emails were issued. The
--                             sender (build/card-brief-confirm.js) sends at most
--                             MAX_CONFIRM_SENDS, so an address that never asked
--                             is not mailed again and again.
--
-- public.confirm_email_subscription(p_token text) RETURNS boolean
--   The one thing a visitor can do with this. SECURITY DEFINER, search_path
--   pinned to ''. It hashes the token inside Postgres and compares hashes. It
--   returns TRUE when that link's address is (now, or already) confirmed and
--   FALSE for everything else — wrong token, expired token, unsubscribed
--   address, malformed input. It never says whether an address exists, and it
--   takes no address, so it cannot be used to test one.
--   Re-clicking a used link returns TRUE again and changes nothing.
--
-- PRIVILEGES — revoke everything from both browser roles, then grant back
-- exactly the signup (owner, D-T088-2: private by default):
--   anon, authenticated : INSERT (email, source) only — the Card Brief form,
--                         unchanged (_auth.js::subscribeEmail, plain insert,
--                         23505 = already subscribed = success);
--                         USAGE on the id sequence (the serial id);
--                         EXECUTE confirm_email_subscription;
--                         EXECUTE unsubscribe_email (unchanged, not touched).
--   Removed from both browser roles: SELECT (the list is private; no page reads
--   it, and the insert needs no SELECT — funnel_events works the same way). An
--   admin reading the list from a browser session therefore stops working;
--   nothing in the repo does that. The service role is not touched.
--   A browser insert also can never arrive confirmed: the column grant covers
--   only (email, source), and a SECURITY INVOKER trigger blanks every
--   confirmation column on any insert made as anon or authenticated, in case a
--   wider grant is ever handed back.
--
-- RE-RUN SAFE, AND NO NOTICES. Every ADD is behind a catalog check, so a second
-- run raises nothing (an `IF NOT EXISTS` that skips raises a NOTICE, and a
-- NOTICE hangs the Supabase MCP tool — CLAUDE.md). It checks its own result
-- before COMMIT and aborts the whole transaction if any check fails.
--
-- APPLY (owner approval first; production is PostgreSQL 17, Supabase):
--   psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f card_brief_double_optin_migration.sql
-- then verify grants from the catalogs, not from this text (CLAUDE.md).
-- Rehearsed by tests/test_card_brief_optin_sql.py on a replica of production's
-- post-T-088 schema, applied twice.
--
-- ROLLBACK (no data is lost; confirmations recorded would be lost):
--   drop function public.confirm_email_subscription(text);
--   drop trigger email_subscribers_pin_confirmation on public.email_subscribers;
--   drop function public.email_subscribers_pin_confirmation();
--   alter table public.email_subscribers drop column confirmed_at, ... ;
--   and re-grant the previous browser SELECT if it is wanted back.
-- =============================================================================

BEGIN;

-- Never queue behind live traffic: a queued lock blocks every reader after it.
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '60s';

-- 1. Columns ------------------------------------------------------------------
DO $$
DECLARE
  col record;
BEGIN
  FOR col IN
    SELECT * FROM (VALUES
      ('confirmed_at',             'timestamptz'),
      ('confirm_token_hash',       'text'),
      ('confirm_token_expires_at', 'timestamptz'),
      ('confirm_sent_at',          'timestamptz'),
      ('confirm_send_count',       'integer NOT NULL DEFAULT 0')
    ) AS v(name, ddl)
  LOOP
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns
       WHERE table_schema = 'public' AND table_name = 'email_subscribers'
         AND column_name = col.name
    ) THEN
      EXECUTE format('ALTER TABLE public.email_subscribers ADD COLUMN IF NOT EXISTS %I %s',
                     col.name, col.ddl);
    END IF;
  END LOOP;
END $$;

-- 2. Constraints and the token index -----------------------------------------
DO $$
BEGIN
  -- A stored hash is exactly a lower-case hex sha256. A raw token stored here
  -- by mistake (also 64 hex) cannot be told apart by shape, so the sender's
  -- tests pin that only the hash is ever written (tests/card-brief-confirm.test.js).
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname = 'email_subscribers_confirm_hash_format'
                    AND conrelid = 'public.email_subscribers'::regclass) THEN
    ALTER TABLE public.email_subscribers
      ADD CONSTRAINT email_subscribers_confirm_hash_format
      CHECK (confirm_token_hash IS NULL OR confirm_token_hash ~ '^[0-9a-f]{64}$');
  END IF;
  -- A token without an expiry would be a link that works forever.
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname = 'email_subscribers_confirm_hash_has_expiry'
                    AND conrelid = 'public.email_subscribers'::regclass) THEN
    ALTER TABLE public.email_subscribers
      ADD CONSTRAINT email_subscribers_confirm_hash_has_expiry
      CHECK ((confirm_token_hash IS NULL) = (confirm_token_expires_at IS NULL));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conname = 'email_subscribers_confirm_send_count_nonneg'
                    AND conrelid = 'public.email_subscribers'::regclass) THEN
    ALTER TABLE public.email_subscribers
      ADD CONSTRAINT email_subscribers_confirm_send_count_nonneg
      CHECK (confirm_send_count >= 0);
  END IF;
  -- One address per token, and the lookup the confirm function makes.
  IF NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                  WHERE n.nspname = 'public' AND c.relname = 'email_subscribers_confirm_token_hash_uniq') THEN
    CREATE UNIQUE INDEX IF NOT EXISTS email_subscribers_confirm_token_hash_uniq
      ON public.email_subscribers (confirm_token_hash)
      WHERE confirm_token_hash IS NOT NULL;
  END IF;
END $$;

COMMENT ON COLUMN public.email_subscribers.confirmed_at IS
  'T-090: when the address clicked its confirmation link. NULL = unconfirmed; the Card Brief is never sent to it.';
COMMENT ON COLUMN public.email_subscribers.confirm_token_hash IS
  'T-090: sha256 (hex) of the confirmation token. The raw token is never stored.';

-- 3. A browser insert never arrives confirmed ---------------------------------
-- SECURITY INVOKER on purpose: inside a SECURITY DEFINER function current_user
-- is the function's owner, so this guard would always read false and protect
-- nothing (the alerts trigger shipped that way for one revision — CLAUDE.md).
CREATE OR REPLACE FUNCTION public.email_subscribers_pin_confirmation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $$
BEGIN
  IF current_user IN ('anon', 'authenticated') THEN
    NEW.confirmed_at             := NULL;
    NEW.confirm_token_hash       := NULL;
    NEW.confirm_token_expires_at := NULL;
    NEW.confirm_sent_at          := NULL;
    NEW.confirm_send_count       := 0;
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER email_subscribers_pin_confirmation
  BEFORE INSERT ON public.email_subscribers
  FOR EACH ROW EXECUTE FUNCTION public.email_subscribers_pin_confirmation();

-- 4. The confirm link ---------------------------------------------------------
CREATE OR REPLACE FUNCTION public.confirm_email_subscription(p_token text)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_hash text;
BEGIN
  -- The sender only ever issues 64 lower-case hex characters. Anything else is
  -- refused before it is hashed, with the same FALSE as a wrong token.
  IF p_token IS NULL OR p_token !~ '^[0-9a-f]{64}$' THEN
    RETURN false;
  END IF;
  v_hash := pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p_token, 'UTF8')), 'hex');

  UPDATE public.email_subscribers
     SET confirmed_at = pg_catalog.now()
   WHERE confirm_token_hash = v_hash
     AND confirmed_at IS NULL
     AND unsubscribed_at IS NULL
     AND confirm_token_expires_at > pg_catalog.now();
  IF FOUND THEN
    RETURN true;
  END IF;

  -- A second click on a link that already worked is still a success, and
  -- changes nothing. An unsubscribed address never reads as confirmed.
  RETURN EXISTS (
    SELECT 1 FROM public.email_subscribers
     WHERE confirm_token_hash = v_hash
       AND confirmed_at IS NOT NULL
       AND unsubscribed_at IS NULL
  );
END;
$$;

COMMENT ON FUNCTION public.confirm_email_subscription(text) IS
  'T-090: confirm a Card Brief address from the raw token in its email link. TRUE = confirmed (now or already); FALSE = anything else. Reveals nothing about any address.';

-- 5. Privileges ---------------------------------------------------------------
REVOKE ALL ON TABLE public.email_subscribers FROM PUBLIC, anon, authenticated;
GRANT INSERT (email, source) ON public.email_subscribers TO anon, authenticated;

REVOKE ALL ON SEQUENCE public.email_subscribers_id_seq FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SEQUENCE public.email_subscribers_id_seq TO anon, authenticated;

REVOKE ALL ON FUNCTION public.confirm_email_subscription(text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.confirm_email_subscription(text) TO anon, authenticated;

REVOKE ALL ON FUNCTION public.email_subscribers_pin_confirmation() FROM PUBLIC, anon, authenticated;

-- 6. Prove it before committing ----------------------------------------------
DO $$
DECLARE
  bad text := '';
  r text;
  p text;
  c text;
BEGIN
  FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
    FOREACH p IN ARRAY ARRAY['SELECT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'] LOOP
      IF has_table_privilege(r, 'public.email_subscribers', p) THEN
        bad := bad || format(' %s holds %s;', r, p);
      END IF;
    END LOOP;
    FOREACH p IN ARRAY ARRAY['SELECT', 'UPDATE'] LOOP
      IF has_any_column_privilege(r, 'public.email_subscribers', p) THEN
        bad := bad || format(' %s holds column %s;', r, p);
      END IF;
    END LOOP;
    FOREACH c IN ARRAY ARRAY['email', 'source'] LOOP
      IF NOT has_column_privilege(r, 'public.email_subscribers', c, 'INSERT') THEN
        bad := bad || format(' %s lost INSERT (%s) — signup would break;', r, c);
      END IF;
    END LOOP;
    FOREACH c IN ARRAY ARRAY['id', 'created_at', 'last_sent_at', 'unsubscribed_at', 'unsubscribe_token',
                             'confirmed_at', 'confirm_token_hash', 'confirm_token_expires_at',
                             'confirm_sent_at', 'confirm_send_count'] LOOP
      IF has_column_privilege(r, 'public.email_subscribers', c, 'INSERT') THEN
        bad := bad || format(' %s may INSERT %s;', r, c);
      END IF;
    END LOOP;
    IF NOT has_sequence_privilege(r, 'public.email_subscribers_id_seq', 'USAGE') THEN
      bad := bad || format(' %s lost USAGE on the id sequence — signup would break;', r);
    END IF;
    IF has_sequence_privilege(r, 'public.email_subscribers_id_seq', 'SELECT')
       OR has_sequence_privilege(r, 'public.email_subscribers_id_seq', 'UPDATE') THEN
      bad := bad || format(' %s holds SELECT/UPDATE on the id sequence;', r);
    END IF;
    IF NOT has_function_privilege(r, 'public.confirm_email_subscription(text)', 'EXECUTE') THEN
      bad := bad || format(' %s cannot EXECUTE confirm_email_subscription;', r);
    END IF;
  END LOOP;

  IF NOT EXISTS (SELECT 1 FROM pg_proc
                  WHERE oid = 'public.confirm_email_subscription(text)'::regprocedure
                    AND prosecdef
                    AND proconfig @> ARRAY['search_path=""']) THEN
    bad := bad || ' confirm_email_subscription is not SECURITY DEFINER with search_path pinned;';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_proc
              WHERE oid = 'public.email_subscribers_pin_confirmation()'::regprocedure
                AND prosecdef) THEN
    bad := bad || ' the pin trigger is SECURITY DEFINER, which makes its guard inert;';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_trigger
                  WHERE tgrelid = 'public.email_subscribers'::regclass
                    AND tgname = 'email_subscribers_pin_confirmation'
                    AND tgenabled <> 'D') THEN
    bad := bad || ' the pin trigger is missing or disabled;';
  END IF;
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid = 'public.email_subscribers'::regclass) THEN
    bad := bad || ' row level security is off;';
  END IF;

  IF bad <> '' THEN
    RAISE EXCEPTION 'T-090 double opt-in check failed:%', bad;
  END IF;
END $$;

COMMIT;
