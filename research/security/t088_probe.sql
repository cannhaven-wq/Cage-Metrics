-- =============================================================================
-- t088_probe.sql — what can each browser role actually do? (T-088)
-- =============================================================================
-- Runs every LEGITIMATE browser action and every ATTACK we care about, as the
-- real role (anon / authenticated with a JWT subject / supabase_auth_admin /
-- service_role), and reports one line per probe:
--
--     <role>|<probe>|<outcome>
--
--   allowed        the statement ran (and touched at least one row, where the
--                  probe says rows matter)
--   denied         SQLSTATE 42501: no privilege, or RLS refused the row
--   zero_rows      ran, but RLS hid every row (a silent refusal)
--   err:<SQLSTATE> passed privilege and RLS, then hit a constraint
--
-- IT ALWAYS ROLLS BACK. Each probe runs in its own sub-block (a savepoint) and
-- is undone; the whole script then ends by raising T088_RESULT, which aborts
-- the transaction, fixtures included. Nothing it does survives.
--
-- Where it runs:
--   * the throwaway local replica (the "Rehearsal" section of research/security/T-088_PRIVILEGE_AUDIT_2026-10-13.md),
--     before and after proposed_2026-10-13_t088_least_privilege.sql;
--   * production, ONLY as part of an approved rehearsal: append it after the
--     migration body in ONE transaction, so the migration is rolled back too.
--     It inserts fixture rows into auth.users inside that transaction; they are
--     rolled back with everything else.
--
-- No RAISE NOTICE anywhere (it hangs the Supabase MCP tool; CLAUDE.md).
-- =============================================================================
DO $probe$
DECLARE
  u1 uuid := '00000000-0000-4000-8000-0000000000a1';
  u2 uuid := '00000000-0000-4000-8000-0000000000b2';
  u3 uuid := '00000000-0000-4000-8000-0000000000c3';
  fid bigint; fighter bigint; seed_bet bigint; seed_alert bigint; tok text;
  out text := '';
  n bigint;
  p record;
BEGIN
  -- ---------- fixtures (superuser / owner; rolled back at the end) ----------
  INSERT INTO auth.users (id, email) VALUES (u1, 't088-u1@example.invalid'), (u2, 't088-u2@example.invalid');
  SELECT min(id) INTO fid FROM public.fights;
  IF fid IS NULL THEN
    INSERT INTO public.events (id, ufc_event_id, name, event_date) VALUES (900001, 't088-ev', 'T-088 probe card', current_date + 7);
    INSERT INTO public.fighters (id, name) VALUES (900001, 'Probe A'), (900002, 'Probe B');
    INSERT INTO public.fights (id, ufc_fight_id, event_id, fighter_a_id, fighter_b_id) VALUES (900001, 't088-f', 900001, 900001, 900002);
    fid := 900001;
  END IF;
  SELECT fighter_a_id INTO fighter FROM public.fights WHERE id = fid;
  INSERT INTO public.user_bets (user_id, fight_id, fighter_id, side, book, placed_price_american, stake_usd)
    VALUES (u1, fid, fighter, 'A', 'probe', 150, 1) RETURNING id INTO seed_bet;
  INSERT INTO public.user_bets (user_id, fight_id, fighter_id, side, book, placed_price_american, stake_usd)
    VALUES (u2, fid, fighter, 'A', 'probe', 150, 1);
  INSERT INTO public.user_alerts (user_id, fight_id, kind, threshold_pts, direction)
    VALUES (u1, fid, 'market_move', 3, 'either') RETURNING id INTO seed_alert;
  INSERT INTO public.email_subscribers (email, source) VALUES ('t088-dup@example.invalid', 'probe')
    RETURNING unsubscribe_token INTO tok;

  -- ---------- the probes ----------
  -- (role, jwt subject or NULL, label, sql, rows_matter)
  FOR p IN SELECT * FROM (VALUES
    -- LEGITIMATE: signup, Card Brief, waitlist, analytics, unsubscribe
    ('supabase_auth_admin', NULL::uuid, 'L_signup_creates_profile',
       format('INSERT INTO auth.users (id, email) VALUES (%L, %L)', u3, 't088-u3@example.invalid'), false),
    ('anon', NULL, 'L_card_brief_subscribe',
       $$INSERT INTO public.email_subscribers (email, source) VALUES ('t088-new-anon@example.invalid', 'probe')$$, false),
    ('anon', NULL, 'L_card_brief_resubscribe_is_23505',
       $$INSERT INTO public.email_subscribers (email, source) VALUES ('t088-dup@example.invalid', 'probe')$$, false),
    ('authenticated', u1, 'L_card_brief_subscribe',
       $$INSERT INTO public.email_subscribers (email, source) VALUES ('t088-new-auth@example.invalid', 'probe')$$, false),
    ('anon', NULL, 'L_waitlist_join',
       $$INSERT INTO public.premium_waitlist (email, source) VALUES ('t088-wait@example.invalid', 'probe')$$, false),
    ('anon', NULL, 'L_funnel_event',
       $$INSERT INTO public.funnel_events (event, session_id, path, props) VALUES ('landing_view', 't088-session', '/', '{}')$$, false),
    ('authenticated', u1, 'L_funnel_event',
       $$INSERT INTO public.funnel_events (event, session_id, path, props) VALUES ('landing_view', 't088-session', '/', '{}')$$, false),
    ('anon', NULL, 'L_unsubscribe_link',
       format('SELECT public.unsubscribe_email(%L)', tok), false),
    -- LEGITIMATE: public reads
    ('anon', NULL, 'L_read_fights', 'SELECT 1 FROM public.fights LIMIT 1', false),
    ('anon', NULL, 'L_read_fighters', 'SELECT 1 FROM public.fighters LIMIT 1', false),
    ('anon', NULL, 'L_read_pre_fight_snapshots', 'SELECT 1 FROM public.pre_fight_snapshots LIMIT 1', false),
    ('authenticated', u1, 'L_read_events', 'SELECT 1 FROM public.events LIMIT 1', false),
    -- LEGITIMATE: account, My Book, watchlist, alerts
    ('authenticated', u1, 'L_profile_read_own', format('SELECT 1 FROM public.profiles WHERE id = %L', u1), true),
    ('authenticated', u1, 'L_profile_set_display_name', format('UPDATE public.profiles SET display_name = %L WHERE id = %L', 'Probe', u1), true),
    ('authenticated', u1, 'L_bet_add',
       format('INSERT INTO public.user_bets (user_id, fight_id, fighter_id, side, book, placed_price_american, stake_usd) VALUES (%L, %s, %s, %L, %L, -110, 5)', u1, fid, fighter, 'A', 'probe'), false),
    ('authenticated', u1, 'L_bet_settle_own', format('UPDATE public.user_bets SET status = %L, won = true WHERE id = %s', 'won', seed_bet), true),
    ('authenticated', u1, 'L_bet_delete_own', format('DELETE FROM public.user_bets WHERE id = %s', seed_bet), true),
    ('authenticated', u1, 'L_bets_read_own', format('SELECT 1 FROM public.user_bets WHERE user_id = %L', u1), true),
    ('authenticated', u1, 'L_bankroll_create_then_update',
       format('INSERT INTO public.user_bankrolls (user_id, current_amount, initial_deposit) VALUES (%L, 100, 100); UPDATE public.user_bankrolls SET current_amount = 90 WHERE user_id = %L', u1, u1), true),
    ('authenticated', u1, 'L_watchlist_star_unstar',
       format('INSERT INTO public.user_watchlist (user_id, fight_id) VALUES (%L, %s); DELETE FROM public.user_watchlist WHERE user_id = %L AND fight_id = %s', u1, fid, u1, fid), true),
    ('authenticated', u1, 'L_alert_create',
       format('INSERT INTO public.user_alerts (user_id, fight_id, kind, side, target_american) VALUES (%L, %s, %L, %L, 150)', u1, fid, 'price_target', 'A'), false),
    ('authenticated', u1, 'L_alert_pause_own', format('UPDATE public.user_alerts SET is_active = false WHERE id = %s', seed_alert), true),
    ('authenticated', u1, 'L_alert_delete_own', format('DELETE FROM public.user_alerts WHERE id = %s', seed_alert), true),
    ('authenticated', u1, 'L_alert_prefs_upsert',
       format('INSERT INTO public.user_alert_prefs (user_id, cooldown_minutes) VALUES (%L, 120) ON CONFLICT (user_id) DO UPDATE SET cooldown_minutes = EXCLUDED.cooldown_minutes', u1), false),
    ('authenticated', u1, 'L_alert_deliveries_read_own', format('SELECT 1 FROM public.user_alert_deliveries WHERE user_id = %L', u1), false),
    -- LEGITIMATE: backend writers keep working
    ('service_role', NULL, 'L_service_writes_fighters', $$UPDATE public.fighters SET updated_at = now() WHERE id = (SELECT min(id) FROM public.fighters)$$, true),
    ('service_role', NULL, 'L_service_replaces_prop_projections', 'DELETE FROM public.prop_projections', false),
    ('service_role', NULL, 'L_service_reads_subscribers', 'SELECT 1 FROM public.email_subscribers LIMIT 1', true),

    -- ATTACKS: TRUNCATE ignores RLS
    ('anon', NULL, 'A_truncate_pre_fight_snapshots', 'TRUNCATE public.pre_fight_snapshots', false),
    ('authenticated', u1, 'A_truncate_user_bets', 'TRUNCATE public.user_bets', false),
    ('authenticated', u1, 'A_truncate_profiles', 'TRUNCATE public.profiles CASCADE', false),
    ('anon', NULL, 'A_truncate_email_subscribers', 'TRUNCATE public.email_subscribers', false),
    ('anon', NULL, 'A_truncate_fights', 'TRUNCATE public.fights CASCADE', false),
    -- ATTACKS: writes the site never makes
    ('anon', NULL, 'A_insert_fighter', $$INSERT INTO public.fighters (name) VALUES ('forged')$$, false),
    ('authenticated', u1, 'A_update_events', $$UPDATE public.events SET name = 'forged'$$, true),
    ('anon', NULL, 'A_insert_hub_visit',
       $$INSERT INTO public.hub_visits (id, visitor_key, event_id, page) VALUES (990001, gen_random_uuid(), 1, 'home')$$, false),
    ('anon', NULL, 'A_subscribe_with_forged_token',
       $$INSERT INTO public.email_subscribers (email, source, unsubscribe_token) VALUES ('t088-forged@example.invalid', 'probe', 'chosen')$$, false),
    ('anon', NULL, 'A_unsubscribe_everyone', 'UPDATE public.email_subscribers SET unsubscribed_at = now()', true),
    ('authenticated', u1, 'A_profile_self_admin', format('UPDATE public.profiles SET is_admin = true WHERE id = %L', u1), true),
    ('authenticated', u1, 'A_profile_rewrite_email', format('UPDATE public.profiles SET email = %L WHERE id = %L', 'x@example.invalid', u1), true),
    ('authenticated', u1, 'A_bet_as_other_user',
       format('INSERT INTO public.user_bets (user_id, fight_id, fighter_id, side, book, placed_price_american, stake_usd) VALUES (%L, %s, %s, %L, %L, 100, 1)', u2, fid, fighter, 'A', 'probe'), false),
    ('authenticated', u1, 'A_edit_other_users_bets', format('UPDATE public.user_bets SET stake_usd = 0 WHERE user_id = %L', u2), true),
    ('authenticated', u1, 'A_forge_alert_delivery',
       format('INSERT INTO public.user_alert_deliveries (user_id, kind, dedupe_key) VALUES (%L, %L, %L)', u1, 'price_target', 't088'), false),
    ('anon', NULL, 'A_write_through_invoker_view', $$INSERT INTO public.v_prop_projections_current (event_id, fight_id, side) VALUES (1, 1, 'a')$$, false),
    ('anon', NULL, 'A_setval_sequence', $$SELECT setval('public.user_bets_id_seq', 1)$$, false)
  ) AS v(role_name, sub, label, stmt, rows_matter) LOOP
    BEGIN
      EXECUTE format('SET LOCAL ROLE %I', p.role_name);
      PERFORM set_config('request.jwt.claims',
        CASE WHEN p.sub IS NULL THEN json_build_object('role', p.role_name)::text
             ELSE json_build_object('role', p.role_name, 'sub', p.sub)::text END, true);
      EXECUTE p.stmt;
      GET DIAGNOSTICS n = ROW_COUNT;
      IF p.label = 'L_signup_creates_profile' THEN
        RESET ROLE;
        IF NOT EXISTS (SELECT 1 FROM public.profiles WHERE id = u3) THEN
          RAISE EXCEPTION USING ERRCODE = 'ZT002', MESSAGE = 'no profile';
        END IF;
      END IF;
      IF p.rows_matter AND n = 0 THEN
        RAISE EXCEPTION USING ERRCODE = 'ZT003', MESSAGE = 'zero rows';
      END IF;
      RAISE EXCEPTION USING ERRCODE = 'ZT004', MESSAGE = 'allowed';
    EXCEPTION
      WHEN insufficient_privilege THEN out := out || E'\n' || p.role_name || '|' || p.label || '|denied';
      WHEN OTHERS THEN
        out := out || E'\n' || p.role_name || '|' || p.label || '|' ||
          CASE SQLSTATE WHEN 'ZT004' THEN 'allowed' WHEN 'ZT003' THEN 'zero_rows'
                        WHEN 'ZT002' THEN 'err:no_profile' ELSE 'err:' || SQLSTATE END;
    END;
  END LOOP;

  -- DEFAULT PRIVILEGES: is a brand-new table born writable by the browser?
  BEGIN
    SET LOCAL ROLE postgres;
    CREATE TABLE public.t088_default_probe (id int);
    out := out || E'\n' || 'postgres|D_new_table_anon_can_write|' ||
      CASE WHEN has_table_privilege('anon', 'public.t088_default_probe', 'INSERT,UPDATE,DELETE,TRUNCATE') THEN 'allowed' ELSE 'denied' END;
    out := out || E'\n' || 'postgres|D_new_table_anon_can_read|' ||
      CASE WHEN has_table_privilege('anon', 'public.t088_default_probe', 'SELECT') THEN 'allowed' ELSE 'denied' END;
    RAISE EXCEPTION USING ERRCODE = 'ZT004', MESSAGE = 'undo';
  EXCEPTION WHEN OTHERS THEN
    IF SQLSTATE <> 'ZT004' THEN out := out || E'\n' || 'postgres|D_new_table|err:' || SQLSTATE; END IF;
  END;

  RAISE EXCEPTION 'T088_RESULT%', out;
END
$probe$;
