-- ============================================================================
-- PROPOSED — NOT APPLIED. fight_odds correction ledger (decision packet C2).
--
-- Plain version: once fight_odds is locked against edits
-- (proposed_2026-09-16_fight_odds_immutability.sql), a quote that turns out to
-- be wrong is never changed. Instead a person writes a correction row here:
-- which quote, what to do with it (exclude it, or treat it as belonging to a
-- different fight), why, who, and when. The original quote stays exactly as
-- captured; the correction is itself append-only, so the history of
-- corrections cannot be rewritten either.
--
-- Apply together with the immutability migration, between cards, only after
-- the CFL Owner explicitly authorizes execution. Re-runnable; raises no
-- NOTICE (every create is behind a catalog check), so it is also safe through
-- the Supabase tool.
--
-- Readers that want corrected data join this table; nothing reads it yet.
-- ============================================================================

begin;

do $$
begin
  if not exists (select 1 from pg_class c join pg_namespace n on n.oid = c.relnamespace
                  where n.nspname = 'public' and c.relname = 'fight_odds_corrections') then
    create table public.fight_odds_corrections (
      id                 bigint generated always as identity primary key,
      fight_odds_id      bigint      not null references public.fight_odds (id),
      action             text        not null
                           check (action in ('exclude', 'reassign_fight')),
      corrected_fight_id bigint,
      reason             text        not null check (length(btrim(reason)) >= 10),
      recorded_by        text        not null default current_user,
      recorded_at        timestamptz not null default clock_timestamp(),
      constraint fight_odds_corrections_reassign_needs_target
        check ((action = 'reassign_fight') = (corrected_fight_id is not null))
    );
  end if;
end $$;

create or replace function public.fight_odds_corrections_append_only()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  raise exception
    'fight_odds_corrections is append-only: % rejected. A wrong correction is '
    'answered by a new correction row, never by editing the old one.', tg_op;
end $$;

do $$
begin
  if not exists (select 1 from pg_trigger where tgname = 'fight_odds_corrections_no_update') then
    create trigger fight_odds_corrections_no_update
      before update or delete on public.fight_odds_corrections
      for each row execute function public.fight_odds_corrections_append_only();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'fight_odds_corrections_no_truncate') then
    create trigger fight_odds_corrections_no_truncate
      before truncate on public.fight_odds_corrections
      for each statement execute function public.fight_odds_corrections_append_only();
  end if;
end $$;

-- Browser roles get nothing, either direction. Supabase defaults grant ALL
-- (TRUNCATE included) to both, so revoke from both, then grant the writer.
revoke all on public.fight_odds_corrections from public, anon, authenticated;
grant select, insert on public.fight_odds_corrections to service_role;

-- Verify inside the transaction; any failure rolls the whole file back.
do $$
begin
  if has_table_privilege('anon', 'public.fight_odds_corrections', 'select')
     or has_table_privilege('authenticated', 'public.fight_odds_corrections', 'select')
     or has_table_privilege('authenticated', 'public.fight_odds_corrections', 'insert')
     or has_table_privilege('authenticated', 'public.fight_odds_corrections', 'truncate') then
    raise exception 'verification failed: a browser role can reach fight_odds_corrections';
  end if;
  if (select count(*) from pg_trigger
       where tgrelid = 'public.fight_odds_corrections'::regclass and not tgisinternal) <> 2 then
    raise exception 'verification failed: append-only triggers missing';
  end if;
end $$;

commit;
