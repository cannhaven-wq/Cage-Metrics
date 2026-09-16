-- =============================================================================
-- hub_visits — first-party, anonymous visit ledger for the retention question
-- "what share of the people who looked at card N came back for card N+1?"
-- =============================================================================
-- Plausible cannot answer that (its Stats API has no returning-visitor or
-- cohort dimension), so the pages write one row per (browser, card, day) here.
--
-- What is stored, and what is not:
--   visitor_key  a random UUID the browser makes up and keeps in localStorage
--                for 60 days, then replaces. Not an IP, not a user agent, not
--                a fingerprint, not linked to an account or an email. It says
--                "the same browser" and nothing else.
--   event_id     which card's hub / fight page / market board was viewed
--   page         'event_hub' | 'fight_preview' | 'market_board'
--   seen_on      the UTC date
-- Nothing else. No SELECT policy for anon or authenticated: the table is
-- write-only from the browser and only ever read by the retention query
-- (sql/retention_return_rate.sql) with the service role.
--
-- Safe to re-run.
-- =============================================================================

create table if not exists public.hub_visits (
  id           bigint generated always as identity primary key,
  visitor_key  uuid not null,
  event_id     integer not null,
  page         text not null check (page in ('event_hub', 'fight_preview', 'market_board', 'home')),
  seen_on      date not null default (now() at time zone 'utc')::date,
  created_at   timestamptz not null default now()
);

-- One row per browser per card per day per page; repeats are no-ops.
create unique index if not exists hub_visits_dedupe
  on public.hub_visits (visitor_key, event_id, page, seen_on);
create index if not exists hub_visits_event_idx on public.hub_visits (event_id, seen_on);

alter table public.hub_visits enable row level security;

-- Browser may INSERT its own anonymous row. No SELECT / UPDATE / DELETE for
-- anon or authenticated — reads happen only with the service role.
drop policy if exists hub_visits_insert_anon on public.hub_visits;
create policy hub_visits_insert_anon
  on public.hub_visits for insert
  to anon, authenticated
  with check (true);

grant insert on public.hub_visits to anon, authenticated;

-- ---------------------------------------------------------------- retention
-- Rows live 120 days, then go. That covers the card-N → card-N+1 comparison
-- (a week apart) with a quarter of history for trend, and no longer. The
-- visitor key itself rotates every 60 days in the browser, so nothing in this
-- table can be tied together past that window anyway.
--
-- pg_cron is not enabled on this project, so the prune is a function the
-- weekly workflow (.github/workflows/hub-visits-prune.yml) calls with the
-- service role. Nobody else can execute it.
create or replace function public.hub_visits_prune(p_keep_days integer default 120)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  n integer;
begin
  delete from public.hub_visits
   where seen_on < (now() at time zone 'utc')::date - greatest(p_keep_days, 30);
  get diagnostics n = row_count;
  return n;
end;
$$;

revoke all on function public.hub_visits_prune(integer) from public, anon, authenticated;
grant execute on function public.hub_visits_prune(integer) to service_role;
