-- =============================================================================
-- proposed_2026-10-15_card_running_order.sql — PROPOSED. NOT APPLIED.
-- Needs the owner's approval (EVENT_CARD_PLAN_2026-10-15.md, step 1).
-- =============================================================================
-- What it does, in plain English: creates the running-order ledger that the
-- existing event-flow ingester (cfl_engine/event_flow/) already writes to, and
-- a read-only view so Card Lab and the event page can show a card in the order
-- it will actually be fought.
--
-- WHY A SEPARATE FILE, NOT research/clv/proposed_2026-09-16_event_flow.sql:
-- that migration also creates odds_api_usage EMPTY, and an empty ledger reads
-- as "0 credits spent" to the odds credit governor (T-029, CLAUDE.md), plus
-- fight_bout_completions and the CLV close-reference view, which belong to the
-- CLV research. This file carries ONLY section 1 of it — the fight_bout_order
-- DDL, copied verbatim (same column list, same index names, same triggers) —
-- so applying the CLV migration later is a no-op for this table.
--
-- Cost: none. No API, no credits, no paid service.
--
-- APPLY IN THE SUPABASE SQL EDITOR OR WITH psql, NOT THE MCP TOOL: the
-- `drop trigger if exists` lines raise a NOTICE on first apply, which hangs
-- execute_sql until its timeout (CLAUDE.md, "Supabase MCP gotcha").
-- =============================================================================

begin;

-- 1. The ledger — verbatim from proposed_2026-09-16_event_flow.sql §1 -------
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

-- 2. The public read path ----------------------------------------------------
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

commit;

-- Verify after applying (each should hold):
--   select has_table_privilege('anon', 'public.fight_bout_order', 'select');        -- false
--   select has_table_privilege('anon', 'public.v_card_running_order', 'select');    -- true
--   select has_table_privilege('anon', 'public.v_card_running_order', 'insert');    -- false
