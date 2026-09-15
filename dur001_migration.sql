-- =============================================================================
-- dur001_migration.sql — DUR-001: "does PROP-0001 add information after the
-- vig-free closing UFC totals market is known?"
--
-- Applied 2026-09-14 via the Supabase Management API (cfl_engine/run_sql_mgmt.py
-- or the MCP apply_migration path). Idempotent: safe to re-run.
--
-- What this changes (and only this):
--   1. prop_odds  — three new columns (provider commence time, live flag, raw
--                   payload) and APPEND-ONLY triggers. Existing columns untouched.
--   2. fight_start_estimates — append-only ledger of "when does this fight
--                   start" observations by source (Odds API commence_time today;
--                   real bell times later). fights.bell_at stays reserved for an
--                   ACTUAL bell time and is never written from a provider guess.
--   3. v_fight_start_best — the close hierarchy:
--                   bell_at  >  latest provider commence  >  event_date fallback.
--   4. v_prop_odds_lifecycle / v_prop_odds_closing_consensus — recreated so the
--                   computed close is "last NON-LIVE quote strictly before the best
--                   available start time", with the basis carried on every row so
--                   closes can be recomputed when real bell times arrive.
--                   Column order of the existing views is preserved; new columns
--                   are appended (v_prop_odds_devig / v_odds_capture_health /
--                   v_prop_odds_integrity_issues are untouched).
--   5. prop_model_locks — the immutable PROP-0001 prediction-lock ledger.
--
-- Nothing here touches fight_odds, the moneyline model, or any public table.
-- prop_odds, fight_start_estimates and prop_model_locks are PRIVATE
-- (RLS on, no anon/authenticated policy → service_role only).
-- =============================================================================


-- ----------------------------------------------------------------------------
-- 1. prop_odds: provenance columns + append-only
-- ----------------------------------------------------------------------------
alter table public.prop_odds
  add column if not exists source_commence_at timestamptz,   -- provider's fight start (Odds API commence_time)
  add column if not exists is_live            boolean not null default false,  -- captured_at >= provider commence
  add column if not exists raw                jsonb;         -- bookmaker/market last_update etc.

comment on column public.prop_odds.source_commence_at is
  'Provider commence/start timestamp as seen AT CAPTURE (Odds API commence_time). Immutable per row; the fight-level best start time is v_fight_start_best.';
comment on column public.prop_odds.is_live is
  'True when the quote was captured at/after the provider commence time — i.e. an in-play price. Never eligible as a pre-fight close.';
comment on column public.prop_odds.raw is
  'Verbatim provider metadata for the quote (bookmaker key, market/bookmaker last_update). Never used for modelling.';

create or replace function public.prop_odds_no_rewrite()
returns trigger language plpgsql as $$
begin
  raise exception
    'prop_odds is append-only: % on quote id % (fight %) rejected. A sportsbook quote is an observation; capture a new row instead.',
    tg_op, coalesce(old.id, new.id), coalesce(old.fight_id, new.fight_id);
end;
$$;

drop trigger if exists prop_odds_block_update on public.prop_odds;
create trigger prop_odds_block_update
  before update on public.prop_odds
  for each row execute function public.prop_odds_no_rewrite();

drop trigger if exists prop_odds_block_delete on public.prop_odds;
create trigger prop_odds_block_delete
  before delete on public.prop_odds
  for each row execute function public.prop_odds_no_rewrite();

-- Belt and braces: no truncate either (statement-level).
drop trigger if exists prop_odds_block_truncate on public.prop_odds;
create trigger prop_odds_block_truncate
  before truncate on public.prop_odds
  for each statement execute function public.prop_odds_no_rewrite();

create index if not exists prop_odds_fight_commence_idx
  on public.prop_odds (fight_id, source_commence_at desc);


-- ----------------------------------------------------------------------------
-- 2. fight_start_estimates: append-only ledger of start-time observations
-- ----------------------------------------------------------------------------
create table if not exists public.fight_start_estimates (
  id          bigint generated always as identity primary key,
  fight_id    bigint      not null references public.fights(id) on delete cascade,
  source      text        not null,                 -- 'odds_api_commence' | 'ufcstats_bell' | 'manual'
  start_at    timestamptz not null,
  observed_at timestamptz not null default now(),
  note        text
);
create index if not exists fight_start_estimates_fight_idx
  on public.fight_start_estimates (fight_id, source, observed_at desc);
-- one row per distinct observation; a re-run seeing the same start does nothing
create unique index if not exists fight_start_estimates_uniq
  on public.fight_start_estimates (fight_id, source, start_at);

comment on table public.fight_start_estimates is
  'Append-only. Every start-time observation per fight and source. fights.bell_at is reserved for a confirmed actual bell; provider guesses live here.';

create or replace function public.fight_start_estimates_no_rewrite()
returns trigger language plpgsql as $$
begin
  raise exception 'fight_start_estimates is append-only: % rejected.', tg_op;
end;
$$;
drop trigger if exists fight_start_estimates_block_update on public.fight_start_estimates;
create trigger fight_start_estimates_block_update
  before update on public.fight_start_estimates
  for each row execute function public.fight_start_estimates_no_rewrite();
drop trigger if exists fight_start_estimates_block_delete on public.fight_start_estimates;
create trigger fight_start_estimates_block_delete
  before delete on public.fight_start_estimates
  for each row execute function public.fight_start_estimates_no_rewrite();

alter table public.fight_start_estimates enable row level security;
revoke all on public.fight_start_estimates from anon, authenticated;


-- ----------------------------------------------------------------------------
-- 3. v_fight_start_best: the close hierarchy
--    1) fights.bell_at (actual bell) when present
--    2) most recently OBSERVED provider commence time (fight_start_estimates,
--       source 'odds_api_commence'), so a reschedule wins over an older guess
--    3) fallback: event_date 18:00 UTC. Deliberately EARLY: US cards start
--       prelims ~22:00 UTC and never before 18:00 UTC, so a fallback close can be
--       stale but can never include an in-play price. start_basis says which.
-- ----------------------------------------------------------------------------
create or replace view public.v_fight_start_best
  with (security_invoker = true) as
select
  f.id as fight_id,
  f.event_id,
  e.event_date,
  coalesce(f.bell_at, pc.start_at,
           (e.event_date::timestamp + time '18:00') at time zone 'UTC') as start_at,
  case when f.bell_at is not null then 'bell_at'
       when pc.start_at is not null then 'provider_commence'
       when e.event_date is not null then 'event_date_fallback'
       else null end as start_basis,
  pc.observed_at as provider_observed_at
from public.fights f
left join public.events e on e.id = f.event_id
left join lateral (
  select s.start_at, s.observed_at
  from public.fight_start_estimates s
  where s.fight_id = f.id and s.source = 'odds_api_commence'
  order by s.observed_at desc
  limit 1
) pc on true;

comment on view public.v_fight_start_best is
  'Best available fight start per fight: bell_at > latest provider commence > event_date 18:00 UTC. start_basis records which tier answered so closes can be recomputed later.';


-- ----------------------------------------------------------------------------
-- 4. lifecycle + closing consensus, recreated on the start hierarchy.
--    Existing columns/order preserved; new columns appended at the end.
-- ----------------------------------------------------------------------------
drop view if exists public.v_prop_odds_closing_consensus;
drop view if exists public.v_prop_odds_lifecycle;

create view public.v_prop_odds_lifecycle
  with (security_invoker = true) as
select
  d.id, d.fight_id, d.event_id, d.event_date, d.market_type, d.fighter_id, d.line,
  d.over_odds, d.under_odds, d.book_id, d.source, d.source_event_id, d.captured_at,
  d.is_opener, d.is_closer, d.over_prob_raw, d.under_prob_raw, d.overround,
  d.over_prob_vigfree, d.under_prob_vigfree,
  f.bell_at,
  -- opener: first quote ever seen for this (fight, market, fighter, line, book)
  d.captured_at = min(d.captured_at) over (
      partition by d.fight_id, d.market_type, coalesce(d.fighter_id, 0::bigint),
                   coalesce(d.line, '-1'::numeric), d.book_id) as is_opener_calc,
  -- closer: last NON-LIVE quote strictly before the best available start time
  (s.start_at is not null and not p.is_live and d.captured_at < s.start_at
   and d.captured_at = max(d.captured_at) filter (where not p.is_live and d.captured_at < s.start_at) over (
      partition by d.fight_id, d.market_type, coalesce(d.fighter_id, 0::bigint),
                   coalesce(d.line, '-1'::numeric), d.book_id)) as is_closer_calc,
  -- appended provenance
  s.start_at,
  s.start_basis,
  p.source_commence_at,
  p.is_live,
  (s.start_at - d.captured_at) as lead_time
from public.v_prop_odds_devig d
join public.prop_odds p on p.id = d.id
join public.fights f on f.id = d.fight_id
left join public.v_fight_start_best s on s.fight_id = d.fight_id;

comment on view public.v_prop_odds_lifecycle is
  'Per-quote opener/closer flags. is_closer_calc = last non-live quote strictly before v_fight_start_best.start_at; start_basis tells you whether that was an actual bell, a provider commence time, or the event-date fallback.';

create view public.v_prop_odds_closing_consensus
  with (security_invoker = true) as
select
  fight_id, event_id, event_date, market_type, fighter_id, line,
  count(*) as bookmaker_count,
  percentile_cont(0.5) within group (order by over_prob_vigfree::double precision)  as median_over_prob_vigfree,
  percentile_cont(0.5) within group (order by under_prob_vigfree::double precision) as median_under_prob_vigfree,
  min(captured_at) as earliest_book_close_at,
  max(captured_at) as latest_book_close_at,
  bell_at,
  -- appended
  start_at,
  start_basis,
  min(lead_time) as min_lead_time,
  max(lead_time) as max_lead_time,
  array_agg(book_id order by book_id) as book_ids
from public.v_prop_odds_lifecycle
where is_closer_calc and source <> 'synthetic'
group by fight_id, event_id, event_date, market_type, fighter_id, line, bell_at, start_at, start_basis;

comment on view public.v_prop_odds_closing_consensus is
  'Median vig-free closing probability per (fight, market, fighter, line) across books. Only non-live pre-start quotes qualify. start_basis is the provenance of the close.';

-- Opening consensus (same shape) for the Phase-8 opener test.
create or replace view public.v_prop_odds_opening_consensus
  with (security_invoker = true) as
select
  fight_id, event_id, event_date, market_type, fighter_id, line,
  count(*) as bookmaker_count,
  percentile_cont(0.5) within group (order by over_prob_vigfree::double precision)  as median_over_prob_vigfree,
  percentile_cont(0.5) within group (order by under_prob_vigfree::double precision) as median_under_prob_vigfree,
  min(captured_at) as earliest_book_open_at,
  max(captured_at) as latest_book_open_at,
  start_at, start_basis,
  array_agg(book_id order by book_id) as book_ids
from public.v_prop_odds_lifecycle
where is_opener_calc and not is_live and source <> 'synthetic'
group by fight_id, event_id, event_date, market_type, fighter_id, line, start_at, start_basis;


-- ----------------------------------------------------------------------------
-- 5. prop_model_locks — immutable PROP-0001 (and future) prediction locks
-- ----------------------------------------------------------------------------
create table if not exists public.prop_model_locks (
  id                    bigint generated always as identity primary key,
  fight_id              bigint  not null references public.fights(id) on delete restrict,
  event_id              bigint  not null references public.events(id) on delete restrict,
  event_date            date,
  market_type           text    not null check (market_type in ('total_rounds','goes_distance')),
  threshold             numeric,                -- e.g. 1.5 / 2.5 (null for goes_distance)
  side                  text    not null check (side in ('over','under','yes')),
  model_name            text    not null,       -- 'PROP-0001'
  model_version         text    not null,       -- e.g. 'PROP-0001@2026-09-14' (freeze tag)
  generated_at          timestamptz not null,   -- when the prediction was computed
  actual_lock_at        timestamptz not null default now(),  -- when the row hit the ledger
  training_cutoff       timestamptz not null,   -- only fights with event_date < this were used
  training_n_fights     integer,
  predicted_probability numeric not null check (predicted_probability > 0 and predicted_probability < 1),
  -- enough to reproduce predicted_probability without the model:
  haz_r1                numeric,                -- calibrated per-round finish hazards
  haz_r2                numeric,
  haz_r3                numeric,
  phi_r1                numeric,                -- PIT share of round-r finishes at/before 2:30
  phi_r2                numeric,
  phi_r3                numeric,
  p_ends_r1             numeric,
  p_ends_r2             numeric,
  p_ends_r3             numeric,
  p_decision            numeric,
  features              jsonb,                  -- the covariate row fed to the model
  code_version          text,                   -- git commit of the lock script
  feature_hash          text,                   -- sha256 of the covariate row
  notes                 text
);
create unique index if not exists prop_model_locks_one_per_version
  on public.prop_model_locks (fight_id, market_type, coalesce(threshold, '-1'::numeric), side, model_name, model_version);
create index if not exists prop_model_locks_fight_idx on public.prop_model_locks (fight_id);
create index if not exists prop_model_locks_event_idx on public.prop_model_locks (event_date, event_id);

comment on table public.prop_model_locks is
  'Append-only research prediction locks (PROP-0001 duration model). One row per (fight, market, threshold, side, model_version). Never updated; a new model version is a new row.';

create or replace function public.prop_model_locks_no_rewrite()
returns trigger language plpgsql as $$
begin
  raise exception
    'prop_model_locks is append-only: % on lock % rejected. Locks are never revised; publish a new model_version instead.',
    tg_op, coalesce(old.id, new.id);
end;
$$;
drop trigger if exists prop_model_locks_block_update on public.prop_model_locks;
create trigger prop_model_locks_block_update
  before update on public.prop_model_locks
  for each row execute function public.prop_model_locks_no_rewrite();
drop trigger if exists prop_model_locks_block_delete on public.prop_model_locks;
create trigger prop_model_locks_block_delete
  before delete on public.prop_model_locks
  for each row execute function public.prop_model_locks_no_rewrite();
drop trigger if exists prop_model_locks_block_truncate on public.prop_model_locks;
create trigger prop_model_locks_block_truncate
  before truncate on public.prop_model_locks
  for each statement execute function public.prop_model_locks_no_rewrite();

-- A lock must be made BEFORE the fight could have started and must only train on
-- fights strictly before the lock. Enforced at insert time so no post-hoc lock
-- can ever be written, even by service_role.
create or replace function public.prop_model_locks_guard()
returns trigger language plpgsql as $$
declare
  v_start timestamptz;
  v_settled boolean;
begin
  if new.training_cutoff > new.actual_lock_at then
    raise exception 'lock rejected: training_cutoff (%) is after actual_lock_at (%)', new.training_cutoff, new.actual_lock_at;
  end if;
  if new.generated_at > new.actual_lock_at + interval '5 minutes' then
    raise exception 'lock rejected: generated_at (%) is after actual_lock_at (%)', new.generated_at, new.actual_lock_at;
  end if;
  select (winner_id is not null or method is not null) into v_settled from public.fights where id = new.fight_id;
  if v_settled then
    raise exception 'lock rejected: fight % already has a result on file', new.fight_id;
  end if;
  select start_at into v_start from public.v_fight_start_best where fight_id = new.fight_id;
  if v_start is not null and new.actual_lock_at >= v_start then
    raise exception 'lock rejected: fight % start (%) is not after actual_lock_at (%)', new.fight_id, v_start, new.actual_lock_at;
  end if;
  return new;
end;
$$;
drop trigger if exists prop_model_locks_guard_insert on public.prop_model_locks;
create trigger prop_model_locks_guard_insert
  before insert on public.prop_model_locks
  for each row execute function public.prop_model_locks_guard();

alter table public.prop_model_locks enable row level security;
revoke all on public.prop_model_locks from anon, authenticated;


-- ----------------------------------------------------------------------------
-- 6. Graded join used by the DUR-001 analysis (read-side only)
-- ----------------------------------------------------------------------------
create or replace view public.v_prop_fight_duration
  with (security_invoker = true) as
select
  f.id as fight_id, f.event_id, e.event_date, f.scheduled_rounds, f.method, f.end_round, f.end_time,
  case
    when f.method is null then null
    when f.method ilike 'decision%' or f.method ilike '%draw%' then f.scheduled_rounds * 300
    when f.method ilike 'overturned%' or f.method ilike 'could not continue%' or f.method ilike 'no contest%' or f.method ilike 'other%' then null
    when f.end_round is null or f.end_time !~ '^\d+:\d\d$' then null
    else (f.end_round - 1) * 300 + split_part(f.end_time, ':', 1)::int * 60 + split_part(f.end_time, ':', 2)::int
  end as duration_seconds,
  (f.method ilike 'overturned%' or f.method ilike 'could not continue%' or f.method ilike 'no contest%' or f.method ilike 'other%') as is_void
from public.fights f
left join public.events e on e.id = f.event_id;

comment on view public.v_prop_fight_duration is
  'Elapsed fight time in seconds from ufcstats end_round/end_time (decision = full scheduled time). NULL = not graded or void.';
