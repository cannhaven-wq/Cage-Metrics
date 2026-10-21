-- =============================================================================
-- apply_2026-10-21_running_order.sql — APPLY-READY. NOT APPLIED.
-- T-096 decision 1a / T-030 / T-032. Applying it is L3 (CRITICAL_GATES.md item 5,
-- a migration creating append-only tables): the owner approves, then a person
-- runs it. Procedure, rollback and the verification checklist:
--   research/event-card/RUNNING_ORDER_APPLY.md
-- =============================================================================
-- IN PLAIN TERMS
--   Creates the place CFL writes down what order a card runs in (one row per
--   bout, first walkout = 1), a public read-only view of the latest card so the
--   site can show "Bout 7 of 13", and a log that records WHY any booking was
--   taken off (or put back on) a card before that flag ever changes.
--
-- THIS FILE SUPERSEDES research/event-card/proposed_2026-10-15_card_running_order.sql
--   (now a pointer). It carries that file's two objects unchanged in meaning,
--   plus three additions:
--     * fight_booking_status_log — the decision record STALE_BOOKING_LIFECYCLE.md
--       §1-§2 asks for ("a decision recorded against that observation"); the
--       ingester appends to it BEFORE it sets fights.is_active, and sets nothing
--       if the log is absent;
--     * TRUNCATE guards on both append-only tables (row triggers do not fire on
--       TRUNCATE, which would otherwise empty either in one statement);
--     * an in-transaction verification block: if any check fails the whole
--       file rolls back and nothing is left half-applied.
--
-- WHAT IT DOES NOT DO
--   * it does not create odds_api_usage, fight_bout_completions or
--     v_clv_close_reference (the rest of research/clv/proposed_2026-09-16_event_flow.sql):
--     odds_api_usage created empty would mislead the odds credit governor (T-029);
--   * it does not touch fights, fight_odds, pre_fight_snapshots or any existing
--     object other than reading fights in a view and a trigger;
--   * no DROP of any existing object, no DELETE, no UPDATE, no backfill.
--
-- COMPATIBILITY: fight_bout_order's DDL is verbatim from proposed_2026-09-16_event_flow.sql
-- §1 (same columns, same index names, same triggers), so applying the CLV
-- migration later is a no-op for this table.
--
-- RE-RUNNABLE: every statement is guarded; tests/test_running_order_migration.py
-- applies it twice to a throwaway Postgres and checks the second run changes
-- nothing.
--
-- APPLY IN THE SUPABASE SQL EDITOR OR WITH psql, NOT THE MCP TOOL: the
-- `drop trigger if exists` and `if not exists` lines raise NOTICEs, which hang
-- execute_sql until its timeout (CLAUDE.md, "Supabase MCP gotcha").
-- Cost: none. No API, no credits, no paid service.
-- =============================================================================

begin;

set local lock_timeout = '3s';
set local statement_timeout = '60s';

-- 0. Preconditions -------------------------------------------------------------
do $$
begin
  if to_regclass('public.fights') is null then
    raise exception 'precondition: public.fights does not exist';
  end if;
  if not exists (select 1 from information_schema.columns
                 where table_schema = 'public' and table_name = 'fights'
                   and column_name = 'is_active') then
    raise exception 'precondition: fights.is_active is missing (add_bout_order_migration.sql). '
                    'v_card_running_order filters on it.';
  end if;
  -- The CLV draft once declared this index; it forbids a bout returning to a
  -- position it held before (cfl_engine/event_flow/MIGRATION_ADJUSTMENT.md).
  if to_regclass('public.fight_bout_order_unique_idx') is not null then
    raise exception 'precondition: fight_bout_order_unique_idx exists; see MIGRATION_ADJUSTMENT.md';
  end if;
end $$;

-- 1. The ledger — verbatim from proposed_2026-09-16_event_flow.sql §1 -----------
create table if not exists public.fight_bout_order (
  id          bigserial primary key,
  fight_id    bigint      not null references public.fights(id) on delete cascade,
  event_id    bigint      not null,
  bout_order  integer     not null,          -- 1 = first bout to walk out
  source      text        not null,          -- 'ufcstats_card' | 'manual' | 'provider'
  observed_at timestamptz not null default now(),
  constraint fight_bout_order_positive check (bout_order >= 1)
);

comment on table public.fight_bout_order is
  'Append-only record of where a fight sat in its card''s running order. '
  'bout_order 1 is the first bout to walk out - the only one whose start is the '
  'card''s scheduled start. Append-only, and DELIBERATELY NOT UNIQUE on '
  '(fight_id, source, bout_order): a reshuffled card can return a bout to a '
  'position it held before, and a unique index there would reject that '
  'observation and leave the ledger asserting the intermediate position for '
  'ever. Event Flow appends the WHOLE card as one observation sharing one '
  'observed_at; consumers resolve the latest COMPLETE CARD, not the latest row '
  'per fight. The observations before it stay readable.';

create index if not exists fight_bout_order_latest_idx
  on public.fight_bout_order (fight_id, source, observed_at desc, id desc);
create unique index if not exists fight_bout_order_one_per_instant_idx
  on public.fight_bout_order (fight_id, source, observed_at);
create index if not exists fight_bout_order_card_idx
  on public.fight_bout_order (event_id, source, observed_at desc, id desc);

create or replace function public.fight_bout_order_no_rewrite()
returns trigger language plpgsql as $$
begin
  raise exception
    'fight_bout_order is append-only: % rejected. A card''s running order is an '
    'observation - append a newer one and the latest wins.', tg_op;
end;
$$;
drop trigger if exists fight_bout_order_block_update on public.fight_bout_order;
create trigger fight_bout_order_block_update
  before update on public.fight_bout_order
  for each row execute function public.fight_bout_order_no_rewrite();
drop trigger if exists fight_bout_order_block_delete on public.fight_bout_order;
create trigger fight_bout_order_block_delete
  before delete on public.fight_bout_order
  for each row execute function public.fight_bout_order_no_rewrite();

alter table public.fight_bout_order enable row level security;
revoke all on public.fight_bout_order from anon, authenticated;

-- 1b. Addition: TRUNCATE skips row triggers, so guard it at statement level.
drop trigger if exists fight_bout_order_block_truncate on public.fight_bout_order;
create trigger fight_bout_order_block_truncate
  before truncate on public.fight_bout_order
  for each statement execute function public.fight_bout_order_no_rewrite();

-- 2. The decision log (T-032) --------------------------------------------------
-- One row per change of fights.is_active made by Event Flow, appended BEFORE
-- the flag is set, naming the card observations it rests on. The booking row
-- itself is never deleted or otherwise rewritten (STALE_BOOKING_LIFECYCLE.md §2).
create table if not exists public.fight_booking_status_log (
  id                   bigserial   primary key,
  fight_id             bigint      not null references public.fights(id),
  event_id             bigint      not null,
  is_active            boolean     not null,      -- the value the flag is set TO
  reason               text        not null,
  observed_at          timestamptz not null,      -- newest observation it rests on
  evidence_observed_at timestamptz[] not null,    -- every observation it rests on
  confirmations        integer     not null default 0,
  source               text        not null,      -- 'ufcstats_card' | 'manual'
  decided_at           timestamptz not null default now(),
  constraint fight_booking_status_log_reason check
    (reason in ('retired_absent_from_card', 'reactivated_back_on_card', 'manual')),
  constraint fight_booking_status_log_confirmations check (confirmations >= 0),
  constraint fight_booking_status_log_direction check
    ((reason = 'retired_absent_from_card' and not is_active)
     or (reason = 'reactivated_back_on_card' and is_active)
     or reason = 'manual')
);

comment on table public.fight_booking_status_log is
  'Append-only record of every fights.is_active change Event Flow makes, written '
  'BEFORE the flag changes. A retirement names the >= 2 consecutive latest card '
  'observations (fight_bout_order.observed_at) that lacked the booking; a '
  'reactivation names the observation that holds it again. Unique per '
  '(fight_id, observed_at, is_active): the same decision against the same '
  'observation is one decision, so a retried run cannot record it twice.';

create unique index if not exists fight_booking_status_log_once_idx
  on public.fight_booking_status_log (fight_id, observed_at, is_active);
create index if not exists fight_booking_status_log_fight_idx
  on public.fight_booking_status_log (fight_id, decided_at desc);

-- The evidence has to be real: every instant must be a recorded observation of
-- this event, and it must say what the decision claims. Checked in the
-- database so a caller cannot record a retirement the ledger does not support.
create or replace function public.fight_booking_status_log_check_evidence()
returns trigger language plpgsql as $$
declare
  at timestamptz;
begin
  if new.reason = 'manual' then
    return new;
  end if;
  if new.source <> 'ufcstats_card' then
    raise exception 'fight_booking_status_log: source % cannot carry an observed decision', new.source;
  end if;
  if coalesce(cardinality(new.evidence_observed_at), 0) = 0
     or new.observed_at <> (select max(x) from unnest(new.evidence_observed_at) x) then
    raise exception 'fight_booking_status_log: observed_at must be the newest evidence instant';
  end if;
  if new.reason = 'retired_absent_from_card'
     and cardinality(new.evidence_observed_at) < 2 then
    raise exception 'fight_booking_status_log: a retirement needs >= 2 absent observations';
  end if;
  foreach at in array new.evidence_observed_at loop
    if not exists (select 1 from public.fight_bout_order o
                   where o.event_id = new.event_id and o.source = new.source
                     and o.observed_at = at) then
      raise exception 'fight_booking_status_log: % is not an observation of event %',
        at, new.event_id;
    end if;
    if (exists (select 1 from public.fight_bout_order o
                where o.event_id = new.event_id and o.source = new.source
                  and o.observed_at = at and o.fight_id = new.fight_id))
       = (new.reason = 'retired_absent_from_card') then
      raise exception 'fight_booking_status_log: observation % does not support %',
        at, new.reason;
    end if;
  end loop;
  if new.reason = 'retired_absent_from_card' and exists (
       select 1 from public.fight_bout_order o
       where o.event_id = new.event_id and o.source = new.source
         and o.observed_at > new.observed_at) then
    raise exception 'fight_booking_status_log: a newer observation exists than the evidence';
  end if;
  return new;
end;
$$;
drop trigger if exists fight_booking_status_log_evidence on public.fight_booking_status_log;
create trigger fight_booking_status_log_evidence
  before insert on public.fight_booking_status_log
  for each row execute function public.fight_booking_status_log_check_evidence();

create or replace function public.fight_booking_status_log_no_rewrite()
returns trigger language plpgsql as $$
begin
  raise exception 'fight_booking_status_log is append-only: % rejected.', tg_op;
end;
$$;
drop trigger if exists fight_booking_status_log_block_update on public.fight_booking_status_log;
create trigger fight_booking_status_log_block_update
  before update on public.fight_booking_status_log
  for each row execute function public.fight_booking_status_log_no_rewrite();
drop trigger if exists fight_booking_status_log_block_delete on public.fight_booking_status_log;
create trigger fight_booking_status_log_block_delete
  before delete on public.fight_booking_status_log
  for each row execute function public.fight_booking_status_log_no_rewrite();
drop trigger if exists fight_booking_status_log_block_truncate on public.fight_booking_status_log;
create trigger fight_booking_status_log_block_truncate
  before truncate on public.fight_booking_status_log
  for each statement execute function public.fight_booking_status_log_no_rewrite();

alter table public.fight_booking_status_log enable row level security;
revoke all on public.fight_booking_status_log from anon, authenticated;

-- 3. The writer's privileges, stated rather than inherited ---------------------
-- The ingester runs as service_role (bypasses RLS). It needs to read and append
-- both tables and nothing else.
revoke update, delete, truncate on public.fight_bout_order from service_role;
revoke update, delete, truncate on public.fight_booking_status_log from service_role;
grant select, insert on public.fight_bout_order to service_role;
grant select, insert on public.fight_booking_status_log to service_role;
grant usage on sequence public.fight_bout_order_id_seq to service_role;
grant usage on sequence public.fight_booking_status_log_id_seq to service_role;
revoke all on sequence public.fight_bout_order_id_seq from anon, authenticated;
revoke all on sequence public.fight_booking_status_log_id_seq from anon, authenticated;

-- 4. The public read path (unchanged from proposed_2026-10-15) ------------------
-- The latest COMPLETE card observation per event: every row sharing that
-- card's newest observed_at (the ingester appends a whole card in one
-- statement, so one instant = one coherent card). Only active bookings. The
-- browser reads this view; the ledger itself stays revoked from both roles.
-- Owner-rights view (no security_invoker), the same pattern as the market views.
create or replace view public.v_card_running_order as
with latest as (
  select distinct on (event_id) event_id, source, observed_at
  from public.fight_bout_order
  where source = 'ufcstats_card'
  order by event_id, observed_at desc, id desc
)
select o.event_id, o.fight_id, o.bout_order, o.observed_at
from public.fight_bout_order o
join latest l
  on l.event_id = o.event_id and l.source = o.source and l.observed_at = o.observed_at
join public.fights f
  on f.id = o.fight_id and f.is_active;

comment on view public.v_card_running_order is
  'Latest complete running-order observation per card, active bookings only. '
  'bout_order 1 = first bout to walk out; the main event has the highest number. '
  'Read by card-research.js. A booking missing from it was added after the '
  'observation and must not be placed by guesswork.';

revoke all on public.v_card_running_order from public, anon, authenticated;
grant select on public.v_card_running_order to anon, authenticated;

-- 5. Verify before committing: any failure raises and rolls the whole file back.
do $$
declare
  bad text := '';
  r record;
  priv text;
begin
  -- objects
  if to_regclass('public.fight_bout_order') is null then bad := bad || ' ledger missing;'; end if;
  if to_regclass('public.fight_booking_status_log') is null then bad := bad || ' decision log missing;'; end if;
  if to_regclass('public.v_card_running_order') is null then bad := bad || ' view missing;'; end if;
  if to_regclass('public.fight_bout_order_unique_idx') is not null then
    bad := bad || ' fight_bout_order_unique_idx present;';
  end if;

  -- browser roles: nothing on either table or sequence; SELECT only on the view
  foreach priv in array array['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'] loop
    for r in select unnest(array['anon','authenticated']) as role loop
      if has_table_privilege(r.role, 'public.fight_bout_order', priv) then
        bad := bad || format(' %s holds %s on fight_bout_order;', r.role, priv); end if;
      if has_table_privilege(r.role, 'public.fight_booking_status_log', priv) then
        bad := bad || format(' %s holds %s on fight_booking_status_log;', r.role, priv); end if;
      if priv <> 'SELECT' and has_table_privilege(r.role, 'public.v_card_running_order', priv) then
        bad := bad || format(' %s holds %s on v_card_running_order;', r.role, priv); end if;
    end loop;
  end loop;
  for r in select unnest(array['anon','authenticated']) as role loop
    if not has_table_privilege(r.role, 'public.v_card_running_order', 'SELECT') then
      bad := bad || format(' %s cannot read v_card_running_order;', r.role); end if;
    if has_sequence_privilege(r.role, 'public.fight_bout_order_id_seq', 'USAGE,SELECT,UPDATE')
       or has_sequence_privilege(r.role, 'public.fight_booking_status_log_id_seq', 'USAGE,SELECT,UPDATE') then
      bad := bad || format(' %s holds a sequence privilege;', r.role); end if;
  end loop;

  -- the writer
  if not (has_table_privilege('service_role', 'public.fight_bout_order', 'SELECT,INSERT')
      and has_table_privilege('service_role', 'public.fight_booking_status_log', 'SELECT,INSERT')) then
    bad := bad || ' service_role cannot read+append;'; end if;
  if has_table_privilege('service_role', 'public.fight_bout_order', 'UPDATE,DELETE,TRUNCATE')
     or has_table_privilege('service_role', 'public.fight_booking_status_log', 'UPDATE,DELETE,TRUNCATE') then
    bad := bad || ' service_role can rewrite an append-only table;'; end if;

  -- RLS on, triggers present and enabled
  if exists (select 1 from pg_class where oid in ('public.fight_bout_order'::regclass,
             'public.fight_booking_status_log'::regclass) and not relrowsecurity) then
    bad := bad || ' RLS off;'; end if;
  if (select count(*) from pg_trigger
      where tgrelid = 'public.fight_bout_order'::regclass and not tgisinternal
        and tgenabled = 'O'
        and tgname in ('fight_bout_order_block_update', 'fight_bout_order_block_delete',
                       'fight_bout_order_block_truncate')) <> 3 then
    bad := bad || ' ledger guard triggers incomplete;'; end if;
  if (select count(*) from pg_trigger
      where tgrelid = 'public.fight_booking_status_log'::regclass and not tgisinternal
        and tgenabled = 'O'
        and tgname in ('fight_booking_status_log_block_update', 'fight_booking_status_log_block_delete',
                       'fight_booking_status_log_block_truncate', 'fight_booking_status_log_evidence')) <> 4 then
    bad := bad || ' decision-log triggers incomplete;'; end if;

  -- the exact index set on the ledger
  if (select string_agg(indexname, ',' order by indexname) from pg_indexes
      where schemaname = 'public' and tablename = 'fight_bout_order')
     <> 'fight_bout_order_card_idx,fight_bout_order_latest_idx,fight_bout_order_one_per_instant_idx,fight_bout_order_pkey' then
    bad := bad || ' ledger index set differs;'; end if;

  -- the view's shape is what card-research.js reads
  if (select string_agg(column_name, ',' order by ordinal_position)
      from information_schema.columns
      where table_schema = 'public' and table_name = 'v_card_running_order')
     <> 'event_id,fight_id,bout_order,observed_at' then
    bad := bad || ' v_card_running_order columns differ;'; end if;

  if bad <> '' then
    raise exception 'running-order migration verification failed:%', bad;
  end if;
end $$;

commit;
