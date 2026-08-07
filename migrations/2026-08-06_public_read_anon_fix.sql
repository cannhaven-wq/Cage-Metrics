-- public_read_anon_fix.sql
-- =============================================================================
-- FIX: logged-out (anon) visitors were seeing an empty site.
--
-- Symptom: anonymous requests via the publishable key returned HTTP 200 with
-- `[]` from every public-data table (fights, fighters, events,
-- model_predictions, model_versions) and therefore from every security-invoker
-- v_* view that reads them. Signed-in (authenticated) users saw everything.
--
-- Cause: the SELECT RLS policies on these public-data tables were scoped
-- `TO authenticated` only. The table-level GRANT to anon was present (hence
-- 200 + empty, not a 401), but RLS filtered out all rows for the anon role.
--
-- This migration is idempotent: it (re)creates a permissive public-read policy
-- named the same on each table and (re)asserts the table grant. Re-running it
-- is safe. It ONLY touches public-data tables — private tables (profiles,
-- premium_waitlist, email_subscribers, bet tracking) are deliberately excluded.
--
-- See CLAUDE.md "Data layer (Supabase)" — public-data tables must grant
-- SELECT TO anon, authenticated.
-- =============================================================================

do $$
declare
  t text;
  public_tables text[] := array[
    'events',
    'fighters',
    'fights',
    'fight_rounds',
    'model_versions',
    'model_predictions'
  ];
begin
  foreach t in array public_tables loop
    -- Only act on tables that actually exist, so a missing optional table
    -- doesn't abort the whole migration.
    if to_regclass('public.' || t) is null then
      raise notice 'skipping % (does not exist)', t;
      continue;
    end if;

    -- RLS must be on for policies to apply (idempotent).
    execute format('alter table public.%I enable row level security;', t);

    -- Replace any prior copy of our policy so the role list is deterministic.
    execute format('drop policy if exists "anon and authenticated can read" on public.%I;', t);
    execute format(
      'create policy "anon and authenticated can read" on public.%I '
      || 'for select to anon, authenticated using (true);', t);

    -- Belt-and-suspenders: ensure the table grant is present too.
    execute format('grant select on public.%I to anon, authenticated;', t);

    raise notice 'opened public read on %', t;
  end loop;
end $$;

-- Views are security-invoker over the base tables above, so fixing the base
-- tables restores them automatically. We still re-assert the grants in case any
-- view was created without them.
do $$
declare
  v text;
  public_views text[] := array[
    'v_fighter_consistency',
    'v_fighter_style',
    'v_fighter_finish_rate',
    'v_fight_odds_consensus',
    'v_younger_fighter_winrate',
    'v_southpaw_vs_orthodox',
    'v_reach_advantage_winrate',
    'v_title_finish_rate',
    'v_finish_rate_by_division',
    'v_main_event_finish_rate'
  ];
begin
  foreach v in array public_views loop
    if to_regclass('public.' || v) is null then
      raise notice 'skipping view % (does not exist)', v;
      continue;
    end if;
    execute format('grant select on public.%I to anon, authenticated;', v);
    raise notice 'granted select on view %', v;
  end loop;
end $$;
