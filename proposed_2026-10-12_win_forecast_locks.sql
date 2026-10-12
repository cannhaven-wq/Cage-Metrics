-- =============================================================================
-- proposed_2026-10-12_win_forecast_locks.sql — PRED-001 §8.8: the prospective
-- lock ledger for win-probability forecasts.
--
-- STATUS: PROPOSED. NOT APPLIED. Applying it is a production migration
-- (coordination/CRITICAL_GATES.md L3 item 5) and waits for the owner's written
-- approval, recorded as a decision against T-084. Idempotent: safe to re-run.
--
-- Plain version. Before a fight, a frozen research model writes down its
-- forecast here. The database itself refuses any forecast written after the
-- fight could have started, refuses any change or deletion afterwards, and
-- records the market price it was up against at that same moment, with the
-- exact sportsbook quotes that price came from. After the fight, a read-only
-- view scores both. Nothing here is public.
--
-- What it creates (and nothing else):
--   1. win_forecast_experiments — one row per frozen experiment artifact:
--      the preregistration hash, the model artifact hash, the code commit and
--      the freeze instant. Append-only.
--   2. win_forecast_locks — one row per (artifact, fight). Append-only. An
--      insert guard enforces, for every role including service_role:
--        * the lock instant is the database clock, never a client value;
--        * the artifact was frozen before the lock;
--        * the training cutoff and the generation time are not after the lock;
--        * the fight has no result on file;
--        * the lock is strictly before the fight's best known start
--          (v_fight_start_best), and a fight with no known start is refused;
--        * the corners named in the lock are the fight's corners right now;
--        * every market quote the benchmark cites exists, belongs to this
--          fight and one of its two corners, comes from a real sportsbook
--          (v_odds_books_sportsbooks: no consensus row, no prediction market),
--          is not in-play, and was captured before the lock and no more than
--          36 hours before it; both corners must be quoted. A benchmark
--          without quotes is refused. The preregistration may set a tighter
--          freshness limit; 36 hours is the floor the database holds.
--   3. v_win_forecast_graded — the read side: model and market log loss per
--      settled fight. A lock whose corners no longer match the fight that
--      happened (a replaced opponent) is VOID, never scored.
--
-- Reuses, does not change: fights, events, fight_odds, v_odds_books_sportsbooks
-- (fight_week_views.sql), v_fight_start_best (dur001_migration.sql). Does
-- not touch model_picks, pre_fight_snapshots,
-- prop_model_locks, or any public surface.
--
-- Security shape. RLS on, no policy for anon or authenticated, and every
-- privilege revoked from PUBLIC, anon and authenticated (TRUNCATE included —
-- TRUNCATE bypasses RLS, see the alerts_migration lesson). service_role keeps
-- SELECT and INSERT only. Verify the grants after applying: the migration's
-- text is not the result (funnel_events lesson).
--
-- The limit, stated plainly: the table OWNER (the `postgres` role) can drop a
-- trigger. Append-only here means "no application role and no API key can
-- rewrite history", not "physically impossible". Git history of this file and
-- the ledger's own ids are the tamper evidence for the rest.
-- =============================================================================


-- ----------------------------------------------------------------------------
-- 1. win_forecast_experiments: the frozen artifacts a lock may cite
-- ----------------------------------------------------------------------------
create table if not exists public.win_forecast_experiments (
  experiment_id          text        not null,
  artifact_sha256        text        not null,
  preregistration_sha256 text        not null,
  protocol               text        not null default 'PRED-001',
  protocol_version       text        not null,
  code_commit            text        not null,
  frozen_at              timestamptz not null,
  registered_at          timestamptz not null default now(),
  benchmark              text        not null,
  n_required             integer,
  analysis_date          date,
  kill_date              date,
  notes                  text,
  primary key (experiment_id, artifact_sha256)
);

do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'win_forecast_experiments_hashes_chk') then
    alter table public.win_forecast_experiments add constraint win_forecast_experiments_hashes_chk
      check (artifact_sha256 ~ '^[0-9a-f]{64}$' and preregistration_sha256 ~ '^[0-9a-f]{64}$');
  end if;
  if not exists (select 1 from pg_constraint where conname = 'win_forecast_experiments_commit_chk') then
    alter table public.win_forecast_experiments add constraint win_forecast_experiments_commit_chk
      check (code_commit ~ '^[0-9a-f]{7,40}$');
  end if;
  if not exists (select 1 from pg_constraint where conname = 'win_forecast_experiments_id_chk') then
    alter table public.win_forecast_experiments add constraint win_forecast_experiments_id_chk
      check (experiment_id ~ '^[A-Z]+-[0-9]{3}$');
  end if;
  if not exists (select 1 from pg_constraint where conname = 'win_forecast_experiments_benchmark_chk') then
    alter table public.win_forecast_experiments add constraint win_forecast_experiments_benchmark_chk
      check (benchmark in ('same_timestamp_consensus'));
  end if;
end $$;

comment on table public.win_forecast_experiments is
  'Append-only. One row per frozen PRED-001 experiment artifact. A forecast lock may only cite an artifact registered here, and only after its frozen_at.';


-- ----------------------------------------------------------------------------
-- 2. win_forecast_locks: the prospective forecasts
-- ----------------------------------------------------------------------------
create table if not exists public.win_forecast_locks (
  id                     bigint generated always as identity primary key,
  experiment_id          text        not null,
  artifact_sha256        text        not null,
  fight_id               bigint      not null references public.fights(id) on delete restrict,
  event_id               bigint      not null references public.events(id) on delete restrict,
  fighter_a_id           bigint      not null,
  fighter_b_id           bigint      not null,
  -- the forecast: probability that fighter_a_id wins (draws/NCs are void)
  p_a                    numeric     not null,
  -- the same-timestamp benchmark (PRED-001 §4): de-vigged consensus P(A)
  p_market_a             numeric     not null,
  market_quote_ids       bigint[]    not null,
  market_book_count      integer     not null,
  market_latest_quote_at timestamptz not null,
  devig_method           text        not null default 'proportional',
  -- reproducibility
  features               jsonb       not null,
  feature_sha256         text        not null,
  training_cutoff        timestamptz not null,
  generated_at           timestamptz not null,
  -- set by the guard from the database clock; any client value is overwritten
  actual_lock_at         timestamptz not null default clock_timestamp(),
  start_at_at_lock       timestamptz,
  start_basis_at_lock    text,
  notes                  text,
  foreign key (experiment_id, artifact_sha256)
    references public.win_forecast_experiments (experiment_id, artifact_sha256) on delete restrict
);

do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'win_forecast_locks_p_chk') then
    alter table public.win_forecast_locks add constraint win_forecast_locks_p_chk
      check (p_a > 0 and p_a < 1 and p_market_a > 0 and p_market_a < 1);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'win_forecast_locks_corners_chk') then
    alter table public.win_forecast_locks add constraint win_forecast_locks_corners_chk
      check (fighter_a_id <> fighter_b_id);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'win_forecast_locks_quotes_chk') then
    alter table public.win_forecast_locks add constraint win_forecast_locks_quotes_chk
      check (cardinality(market_quote_ids) >= 2 and market_book_count >= 1);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'win_forecast_locks_hash_chk') then
    alter table public.win_forecast_locks add constraint win_forecast_locks_hash_chk
      check (feature_sha256 ~ '^[0-9a-f]{64}$');
  end if;
  if not exists (select 1 from pg_constraint where conname = 'win_forecast_locks_devig_chk') then
    alter table public.win_forecast_locks add constraint win_forecast_locks_devig_chk
      check (devig_method in ('proportional'));
  end if;
end $$;

-- One forecast per fight per artifact. A changed model is a new artifact.
create unique index if not exists win_forecast_locks_one_per_artifact
  on public.win_forecast_locks (experiment_id, artifact_sha256, fight_id);
create index if not exists win_forecast_locks_fight_idx
  on public.win_forecast_locks (fight_id);

comment on table public.win_forecast_locks is
  'Append-only PRED-001 prospective win-probability locks. Written before the fight by a frozen artifact; refused after the start, never updated, never deleted. p_a is P(fighter_a_id wins).';
comment on column public.win_forecast_locks.actual_lock_at is
  'Database clock at insert (clock_timestamp()). The guard overwrites any client-supplied value, so a lock cannot be backdated.';
comment on column public.win_forecast_locks.market_quote_ids is
  'fight_odds.id of every quote behind p_market_a. The guard proves each one exists, belongs to this fight and corner pair, and predates the lock.';


-- ----------------------------------------------------------------------------
-- Append-only: both tables reject UPDATE, DELETE and TRUNCATE for every role.
-- ----------------------------------------------------------------------------
create or replace function public.win_forecast_no_rewrite()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
  raise exception
    '% is append-only: % rejected. A forecast that can be revised after the fact is not evidence; register a new artifact instead.',
    tg_table_name, tg_op;
end;
$$;

drop trigger if exists win_forecast_experiments_block_update on public.win_forecast_experiments;
create trigger win_forecast_experiments_block_update
  before update on public.win_forecast_experiments
  for each row execute function public.win_forecast_no_rewrite();
drop trigger if exists win_forecast_experiments_block_delete on public.win_forecast_experiments;
create trigger win_forecast_experiments_block_delete
  before delete on public.win_forecast_experiments
  for each row execute function public.win_forecast_no_rewrite();
drop trigger if exists win_forecast_experiments_block_truncate on public.win_forecast_experiments;
create trigger win_forecast_experiments_block_truncate
  before truncate on public.win_forecast_experiments
  for each statement execute function public.win_forecast_no_rewrite();

drop trigger if exists win_forecast_locks_block_update on public.win_forecast_locks;
create trigger win_forecast_locks_block_update
  before update on public.win_forecast_locks
  for each row execute function public.win_forecast_no_rewrite();
drop trigger if exists win_forecast_locks_block_delete on public.win_forecast_locks;
create trigger win_forecast_locks_block_delete
  before delete on public.win_forecast_locks
  for each row execute function public.win_forecast_no_rewrite();
drop trigger if exists win_forecast_locks_block_truncate on public.win_forecast_locks;
create trigger win_forecast_locks_block_truncate
  before truncate on public.win_forecast_locks
  for each statement execute function public.win_forecast_no_rewrite();


-- ----------------------------------------------------------------------------
-- The insert guard. SECURITY INVOKER (the default) on purpose: it reads only
-- tables the inserting role can already read, and a definer function would
-- hide which role did the insert (alerts_migration lesson).
-- ----------------------------------------------------------------------------
create or replace function public.win_forecast_locks_guard()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
declare
  v_frozen    timestamptz;
  v_fight     record;
  v_start     record;
  v_quotes    integer;
  v_bad       integer;
  v_latest    timestamptz;
begin
  -- 1. the lock instant is the database's, not the caller's
  new.actual_lock_at := clock_timestamp();

  -- 2. the artifact was frozen before this lock
  select frozen_at into v_frozen
    from public.win_forecast_experiments
   where experiment_id = new.experiment_id and artifact_sha256 = new.artifact_sha256;
  if v_frozen is null then
    raise exception 'lock rejected: artifact %/% is not registered', new.experiment_id, new.artifact_sha256;
  end if;
  if v_frozen > new.actual_lock_at then
    raise exception 'lock rejected: artifact frozen at % is after the lock at %', v_frozen, new.actual_lock_at;
  end if;

  -- 3. nothing the forecast used postdates the lock
  if new.training_cutoff > new.actual_lock_at then
    raise exception 'lock rejected: training_cutoff % is after the lock at %', new.training_cutoff, new.actual_lock_at;
  end if;
  if new.generated_at > new.actual_lock_at then
    raise exception 'lock rejected: generated_at % is after the lock at %', new.generated_at, new.actual_lock_at;
  end if;

  -- 4. the fight exists, has no result, and the corners are the fight's corners
  select id, event_id, fighter_a_id, fighter_b_id, winner_id, method
    into v_fight from public.fights where id = new.fight_id;
  if v_fight.id is null then
    raise exception 'lock rejected: fight % does not exist', new.fight_id;
  end if;
  if v_fight.winner_id is not null or v_fight.method is not null then
    raise exception 'lock rejected: fight % already has a result on file', new.fight_id;
  end if;
  if v_fight.event_id is distinct from new.event_id then
    raise exception 'lock rejected: fight % belongs to event %, not %', new.fight_id, v_fight.event_id, new.event_id;
  end if;
  if v_fight.fighter_a_id is distinct from new.fighter_a_id
     or v_fight.fighter_b_id is distinct from new.fighter_b_id then
    raise exception 'lock rejected: corners (%, %) are not fight %''s corners (%, %)',
      new.fighter_a_id, new.fighter_b_id, new.fight_id, v_fight.fighter_a_id, v_fight.fighter_b_id;
  end if;

  -- 5. strictly before the best known start; an unknown start fails closed
  select start_at, start_basis into v_start
    from public.v_fight_start_best where fight_id = new.fight_id;
  if v_start.start_at is null then
    raise exception 'lock rejected: fight % has no known start time, so "before the start" cannot be proved', new.fight_id;
  end if;
  if new.actual_lock_at >= v_start.start_at then
    raise exception 'lock rejected: fight % starts at % (%), not after the lock at %',
      new.fight_id, v_start.start_at, v_start.start_basis, new.actual_lock_at;
  end if;
  new.start_at_at_lock    := v_start.start_at;
  new.start_basis_at_lock := v_start.start_basis;

  -- 6. the benchmark names real, pre-lock quotes on this fight's two corners,
  --    and the stored latest-quote instant is the true latest
  select count(*),
         count(*) filter (where o.fight_id <> new.fight_id
                             or o.fighter_id not in (new.fighter_a_id, new.fighter_b_id)
                             or o.captured_at >= new.actual_lock_at
                             or o.captured_at <  new.actual_lock_at - interval '36 hours'
                             or coalesce(o.is_live, false)
                             or not exists (select 1 from public.v_odds_books_sportsbooks b
                                             where b.id = o.book_id)),
         max(o.captured_at)
    into v_quotes, v_bad, v_latest
    from public.fight_odds o
   where o.id = any (new.market_quote_ids);
  if v_quotes <> cardinality(new.market_quote_ids) then
    raise exception 'lock rejected: % of % cited market quotes do not exist',
      cardinality(new.market_quote_ids) - v_quotes, cardinality(new.market_quote_ids);
  end if;
  if v_bad > 0 then
    raise exception 'lock rejected: % cited quotes are for another fight or fighter, captured at/after the lock or more than 36 hours before it, in-play, or not from a sportsbook', v_bad;
  end if;
  if v_latest is distinct from new.market_latest_quote_at then
    raise exception 'lock rejected: market_latest_quote_at % is not the latest cited quote (%)',
      new.market_latest_quote_at, v_latest;
  end if;
  if not exists (select 1 from public.fight_odds o
                  where o.id = any (new.market_quote_ids) and o.fighter_id = new.fighter_a_id)
     or not exists (select 1 from public.fight_odds o
                  where o.id = any (new.market_quote_ids) and o.fighter_id = new.fighter_b_id) then
    raise exception 'lock rejected: the benchmark must cite quotes on both corners';
  end if;

  return new;
end;
$$;

drop trigger if exists win_forecast_locks_guard_insert on public.win_forecast_locks;
create trigger win_forecast_locks_guard_insert
  before insert on public.win_forecast_locks
  for each row execute function public.win_forecast_locks_guard();


-- ----------------------------------------------------------------------------
-- 3. v_win_forecast_graded: the read side
-- ----------------------------------------------------------------------------
create or replace view public.v_win_forecast_graded
  with (security_invoker = true) as
select
  l.id as lock_id,
  l.experiment_id,
  l.artifact_sha256,
  l.fight_id,
  l.event_id,
  l.actual_lock_at,
  l.start_at_at_lock,
  l.p_a,
  l.p_market_a,
  f.winner_id,
  case
    when f.fighter_a_id is distinct from l.fighter_a_id
      or f.fighter_b_id is distinct from l.fighter_b_id then 'void_corners_changed'
    when f.winner_id is null then 'pending_or_no_decision'
    when f.winner_id not in (l.fighter_a_id, l.fighter_b_id) then 'void_winner_not_in_corners'
    else 'scored'
  end as grade_status,
  case when f.winner_id = l.fighter_a_id then 1
       when f.winner_id = l.fighter_b_id then 0 end as y_a,
  -- natural-log loss, probabilities clipped to [1e-4, 1-1e-4] (PRED-001 protocol.json)
  case when f.winner_id in (l.fighter_a_id, l.fighter_b_id)
        and f.fighter_a_id = l.fighter_a_id and f.fighter_b_id = l.fighter_b_id then
    -ln(case when f.winner_id = l.fighter_a_id then least(greatest(l.p_a, 0.0001), 0.9999)
             else 1 - least(greatest(l.p_a, 0.0001), 0.9999) end) end as ll_model,
  case when f.winner_id in (l.fighter_a_id, l.fighter_b_id)
        and f.fighter_a_id = l.fighter_a_id and f.fighter_b_id = l.fighter_b_id then
    -ln(case when f.winner_id = l.fighter_a_id then least(greatest(l.p_market_a, 0.0001), 0.9999)
             else 1 - least(greatest(l.p_market_a, 0.0001), 0.9999) end) end as ll_market
from public.win_forecast_locks l
join public.fights f on f.id = l.fight_id;

comment on view public.v_win_forecast_graded is
  'Model vs same-timestamp market log loss per locked fight. Positive (ll_market - ll_model) means the model was better. A lock whose corners no longer match the fight is void, never scored.';


-- ----------------------------------------------------------------------------
-- Privileges: private to service_role, read and insert only.
-- ----------------------------------------------------------------------------
alter table public.win_forecast_experiments enable row level security;
alter table public.win_forecast_locks enable row level security;

revoke all on public.win_forecast_experiments from public, anon, authenticated, service_role;
revoke all on public.win_forecast_locks       from public, anon, authenticated, service_role;
revoke all on public.v_win_forecast_graded    from public, anon, authenticated, service_role;

grant select, insert on public.win_forecast_experiments to service_role;
grant select, insert on public.win_forecast_locks       to service_role;
grant select         on public.v_win_forecast_graded    to service_role;

revoke all on function public.win_forecast_no_rewrite()   from public, anon, authenticated;
revoke all on function public.win_forecast_locks_guard()  from public, anon, authenticated;
