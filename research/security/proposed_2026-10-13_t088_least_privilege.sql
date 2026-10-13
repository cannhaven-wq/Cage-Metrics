-- =============================================================================
-- proposed_2026-10-13_t088_least_privilege.sql — T-088. PROPOSED. NOT APPLIED.
-- =============================================================================
-- Applying this is an L3 gate (coordination/CRITICAL_GATES.md item 5). It is
-- here for review. Its evidence, the rehearsal and the decisions it needs are in
-- research/security/T-088_PRIVILEGE_AUDIT_2026-10-13.md. Do not apply it by habit.
--
-- IN PLAIN TERMS
--   The website's two database roles (anon = a visitor, authenticated = a
--   signed-in member) can currently write to almost every table. Row security
--   stops most of it; TRUNCATE skips row security entirely, and three writes
--   get through today. This keeps exactly the writes the site makes and removes
--   the rest. Reads are not changed at all.
--
-- WHAT IT KEEPS (each one is exercised by research/security/t088_probe.sql)
--   visitor + member : Card Brief signup  INSERT (email, source)   email_subscribers
--                      waitlist           INSERT (email, source)   premium_waitlist
--                      analytics          INSERT (event, session_id, path, props) funnel_events
--                      unsubscribe link   EXECUTE unsubscribe_email (unchanged)
--   member only      : display name       UPDATE (display_name)    profiles
--                      My Book            INSERT, UPDATE, DELETE   user_bets
--                                         INSERT, UPDATE           user_bankrolls
--                      alerts             INSERT, UPDATE, DELETE   user_alerts
--                                         INSERT, UPDATE           user_alert_prefs
--                      watchlist          INSERT, DELETE           user_watchlist
--   signup itself goes through handle_new_user(), SECURITY DEFINER, owned by
--   postgres: no browser grant is involved and none is needed.
--   Every RLS policy stays exactly as it is; this narrows privileges under them.
--
-- WHAT IT REMOVES
--   * every other INSERT / UPDATE / DELETE / TRUNCATE / REFERENCES / TRIGGER /
--     MAINTAIN held by PUBLIC, anon or authenticated on any table or view in
--     public — including TRUNCATE on pre_fight_snapshots, fights, profiles,
--     user_bets and email_subscribers;
--   * whole-row INSERT on email_subscribers (a visitor could choose their own
--     unsubscribe_token) and whole-row UPDATE on profiles (a member could
--     rewrite profiles.email; the policy pins nine columns, not that one);
--   * hub_visits writes — nothing in any repo writes it; its 20 rows date from
--     six minutes on 2026-09-16;
--   * UPDATE/SELECT on every sequence (setval). USAGE stays only where the
--     browser inserts into a serial column.
--   * the default grant that makes every NEW table in public writable by both
--     browser roles. New tables are still readable by default (unchanged
--     convention, owner decision D-T088-2 in the audit).
--
-- NOT IN THIS FILE (separate decisions, see the audit)
--   * the TRUNCATE guard on pre_fight_snapshots — proposed_2026-10-13_t088_pre_fight_truncate_guard.sql
--   * fight_odds append-only triggers — already proposed in
--     research/clv/proposed_2026-09-16_fight_odds_immutability.sql
--   * SECURITY DEFINER functions callable by anon: they are the RLS helpers
--     (current_user_is_admin() IS the fight_odds policy), the alert quota and
--     the unsubscribe link. RLS evaluates them as the caller, so revoking
--     EXECUTE would break every policy that names them.
--
-- MAINTAIN is a PostgreSQL 17 privilege (production is 17). The local PG16
-- rehearsal strips that one word; nothing else differs.
-- No statement raises a NOTICE (CLAUDE.md "Supabase MCP gotcha").
-- =============================================================================

BEGIN;

-- What both browser roles can read right now, so step 5 can prove it did not move.
CREATE TEMP TABLE t088_reads_before ON COMMIT DROP AS
SELECT c.relname,
       has_table_privilege('anon', c.oid, 'SELECT')          AS anon_sel,
       has_table_privilege('authenticated', c.oid, 'SELECT') AS auth_sel
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f');

-- 1. Remove every browser write on every table and view in public ------------
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN
  ON ALL TABLES IN SCHEMA public
  FROM PUBLIC, anon, authenticated;

-- 2. Give back exactly the writes the website makes --------------------------
GRANT INSERT (email, source)                   ON public.email_subscribers TO anon, authenticated;
GRANT INSERT (email, source)                   ON public.premium_waitlist  TO anon, authenticated;
GRANT INSERT (event, session_id, path, props)  ON public.funnel_events     TO anon, authenticated;

GRANT UPDATE (display_name)     ON public.profiles         TO authenticated;
GRANT INSERT, UPDATE, DELETE    ON public.user_bets        TO authenticated;
GRANT INSERT, UPDATE            ON public.user_bankrolls   TO authenticated;
GRANT INSERT, UPDATE, DELETE    ON public.user_alerts      TO authenticated;
GRANT INSERT, UPDATE            ON public.user_alert_prefs TO authenticated;
GRANT INSERT, DELETE            ON public.user_watchlist   TO authenticated;

-- 3. Sequences: USAGE only where the browser inserts a serial id -------------
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SEQUENCE public.email_subscribers_id_seq,
                        public.premium_waitlist_id_seq,
                        public.funnel_events_id_seq      TO anon, authenticated;
GRANT USAGE ON SEQUENCE public.user_bets_id_seq,
                        public.user_alerts_id_seq        TO authenticated;

-- 4. New objects stop being born writable -------------------------------------
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE ALL ON SEQUENCES FROM anon, authenticated;

-- 5. Prove it before committing -----------------------------------------------
DO $$
DECLARE
  bad text := '';
  r record;
  allowed_write text;
  -- (role, table, privilege, column or NULL for table-level) — the whole allowlist.
  allow constant text[] := ARRAY[
    'anon|email_subscribers|INSERT|email', 'anon|email_subscribers|INSERT|source',
    'authenticated|email_subscribers|INSERT|email', 'authenticated|email_subscribers|INSERT|source',
    'anon|premium_waitlist|INSERT|email', 'anon|premium_waitlist|INSERT|source',
    'authenticated|premium_waitlist|INSERT|email', 'authenticated|premium_waitlist|INSERT|source',
    'anon|funnel_events|INSERT|event', 'anon|funnel_events|INSERT|session_id',
    'anon|funnel_events|INSERT|path', 'anon|funnel_events|INSERT|props',
    'authenticated|funnel_events|INSERT|event', 'authenticated|funnel_events|INSERT|session_id',
    'authenticated|funnel_events|INSERT|path', 'authenticated|funnel_events|INSERT|props',
    'authenticated|profiles|UPDATE|display_name',
    'authenticated|user_bets|INSERT|', 'authenticated|user_bets|UPDATE|', 'authenticated|user_bets|DELETE|',
    'authenticated|user_bankrolls|INSERT|', 'authenticated|user_bankrolls|UPDATE|',
    'authenticated|user_alerts|INSERT|', 'authenticated|user_alerts|UPDATE|', 'authenticated|user_alerts|DELETE|',
    'authenticated|user_alert_prefs|INSERT|', 'authenticated|user_alert_prefs|UPDATE|',
    'authenticated|user_watchlist|INSERT|', 'authenticated|user_watchlist|DELETE|'];
BEGIN
  -- (a) no browser write exists outside the allowlist, table- or column-level
  FOR r IN
    SELECT ro.rolname, c.relname, p.priv, a.attname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
    CROSS JOIN (VALUES ('anon'), ('authenticated')) ro(rolname)
    CROSS JOIN (VALUES ('INSERT'), ('UPDATE'), ('DELETE'), ('TRUNCATE'), ('REFERENCES'), ('TRIGGER')) p(priv)
    LEFT JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
                            AND p.priv IN ('INSERT', 'UPDATE', 'REFERENCES')
    WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
  LOOP
    IF r.attname IS NULL THEN
      IF has_table_privilege(r.rolname, format('public.%I', r.relname), r.priv)
         AND NOT (format('%s|%s|%s|', r.rolname, r.relname, r.priv) = ANY (allow)) THEN
        bad := bad || format(' %s:%s on %s;', r.rolname, r.priv, r.relname);
      END IF;
    ELSIF has_column_privilege(r.rolname, format('public.%I', r.relname), r.attname, r.priv)
          AND NOT (format('%s|%s|%s|%s', r.rolname, r.relname, r.priv, r.attname) = ANY (allow))
          AND NOT (format('%s|%s|%s|', r.rolname, r.relname, r.priv) = ANY (allow)) THEN
      bad := bad || format(' %s:%s(%s) on %s;', r.rolname, r.priv, r.attname, r.relname);
    END IF;
  END LOOP;

  -- (b) every allowlisted write is actually present
  FOREACH allowed_write IN ARRAY allow LOOP
    IF split_part(allowed_write, '|', 4) = '' THEN
      IF NOT has_table_privilege(split_part(allowed_write, '|', 1),
               'public.' || split_part(allowed_write, '|', 2), split_part(allowed_write, '|', 3)) THEN
        bad := bad || ' missing ' || allowed_write || ';';
      END IF;
    ELSIF NOT has_column_privilege(split_part(allowed_write, '|', 1),
               'public.' || split_part(allowed_write, '|', 2), split_part(allowed_write, '|', 4),
               split_part(allowed_write, '|', 3)) THEN
      bad := bad || ' missing ' || allowed_write || ';';
    END IF;
  END LOOP;

  -- (c) reads did not move
  FOR r IN
    SELECT b.relname FROM t088_reads_before b
    JOIN pg_class c ON c.relname = b.relname
    JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
    WHERE b.anon_sel <> has_table_privilege('anon', c.oid, 'SELECT')
       OR b.auth_sel <> has_table_privilege('authenticated', c.oid, 'SELECT')
  LOOP
    bad := bad || format(' read changed on %s;', r.relname);
  END LOOP;

  -- (d) sequences: USAGE only where listed, never UPDATE or SELECT
  FOR r IN
    SELECT ro.rolname, c.relname FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
    CROSS JOIN (VALUES ('anon'), ('authenticated')) ro(rolname)
    WHERE c.relkind = 'S'
      AND (has_sequence_privilege(ro.rolname, c.oid, 'UPDATE')
        OR has_sequence_privilege(ro.rolname, c.oid, 'SELECT')
        OR (has_sequence_privilege(ro.rolname, c.oid, 'USAGE')
            AND NOT (c.relname IN ('email_subscribers_id_seq', 'premium_waitlist_id_seq', 'funnel_events_id_seq')
                     OR (ro.rolname = 'authenticated' AND c.relname IN ('user_bets_id_seq', 'user_alerts_id_seq')))))
  LOOP
    bad := bad || format(' %s on sequence %s;', r.rolname, r.relname);
  END LOOP;

  -- (e) the default no longer hands browser roles writes on new tables
  IF EXISTS (
    SELECT 1 FROM pg_default_acl d
    JOIN pg_namespace n ON n.oid = d.defaclnamespace AND n.nspname = 'public'
    CROSS JOIN LATERAL aclexplode(d.defaclacl) a
    WHERE d.defaclrole = 'postgres'::regrole AND d.defaclobjtype IN ('r', 'S')
      AND a.grantee IN ('anon'::regrole, 'authenticated'::regrole)
      AND (d.defaclobjtype = 'S' OR a.privilege_type <> 'SELECT')
  ) THEN
    bad := bad || ' default privileges still grant browser writes;';
  END IF;

  IF bad <> '' THEN
    RAISE EXCEPTION 'T-088 least-privilege check failed:%', bad;
  END IF;
END
$$;

COMMIT;
