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
--        * the market benchmark is RECOMPUTED by the database at the lock
--          instant (win_forecast_benchmark) and must match what was stored:
--          the same quotes, book count, latest-quote time and probability
--          (to 1e-9). The benchmark is every real sportsbook's latest
--          non-live price on both corners from the 36 hours before the lock,
--          proportionally de-vigged, median across books. The caller cannot
--          pick the books, pick an older quote, or do its own arithmetic.
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
  'fight_odds.id of every quote behind p_market_a, sorted. The guard recomputes the benchmark from fight_odds at the lock instant and requires these to be exactly its quotes.';


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
-- The benchmark, defined once, in the database. PRED-001 §4: the market
-- probability AT THE SAME TIMESTAMP as the forecast, proportional de-vig.
--
-- Eligible quote: on this fight and one of its two corners; from a real
-- sportsbook (v_odds_books_sportsbooks — no consensus row, no prediction
-- market); not in-play; captured strictly before `at` and no more than 36
-- hours before it; a valid American price (|odds| >= 100).
-- Per book: its LATEST eligible quote on each corner. A book counts only if it
-- quotes both corners. Its vig-free P(A) = imp(A) / (imp(A) + imp(B)), with
-- implied probability from the American price. The benchmark is the MEDIAN of
-- the per-book values (the mean of the middle two when the count is even).
--
-- The lock script calls this to fill the lock row; the insert guard calls it
-- again at the database's own lock instant and refuses any disagreement. So the
-- stored benchmark is never the caller's arithmetic. If a new quote lands
-- between the two calls, the insert is refused and the script retries.
-- ----------------------------------------------------------------------------
create or replace function public.win_forecast_benchmark(
  p_fight_id bigint, p_fighter_a_id bigint, p_fighter_b_id bigint, p_at timestamptz)
returns table (quote_ids bigint[], book_count integer,
               latest_quote_at timestamptz, p_market_a numeric)
language sql
stable
set search_path = public, pg_temp
as $$
  with eligible as (
    select o.id, o.book_id, o.fighter_id, o.captured_at,
           case when o.american_odds > 0 then 100.0 / (o.american_odds + 100.0)
                else (-o.american_odds)::numeric / ((-o.american_odds) + 100.0) end as imp
      from public.fight_odds o
     where o.fight_id = p_fight_id
       and o.fighter_id in (p_fighter_a_id, p_fighter_b_id)
       and o.captured_at <  p_at
       and o.captured_at >= p_at - interval '36 hours'
       and not coalesce(o.is_live, false)
       and o.american_odds is not null
       and abs(o.american_odds) >= 100
       and exists (select 1 from public.v_odds_books_sportsbooks b where b.id = o.book_id)
  ),
  latest as (
    select distinct on (book_id, fighter_id) *
      from eligible
     order by book_id, fighter_id, captured_at desc, id desc
  ),
  per_book as (
    select a.book_id,
           a.imp / (a.imp + b.imp) as p_a,
           a.id as id_a, b.id as id_b,
           greatest(a.captured_at, b.captured_at) as latest_at
      from latest a
      join latest b on b.book_id = a.book_id and b.fighter_id = p_fighter_b_id
     where a.fighter_id = p_fighter_a_id
  )
  select (select array_agg(x order by x)
            from (select id_a as x from per_book union all select id_b from per_book) q),
         count(*)::integer,
         max(latest_at),
         (percentile_cont(0.5) within group (order by p_a::double precision))::numeric
    from per_book;
$$;

comment on function public.win_forecast_benchmark(bigint, bigint, bigint, timestamptz) is
  'PRED-001 same-timestamp benchmark: median across sportsbooks of each book''s latest pre-`at` proportional vig-free P(A), quotes no older than 36h, no in-play, no consensus or prediction-market rows. The lock guard recomputes it and refuses any disagreement.';

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
  v_bench     record;
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

  -- 6. the benchmark is RECOMPUTED here from fight_odds, at the lock instant,
  --    and must equal what the caller stored: the same quotes, the same book
  --    count, the same latest-quote instant and the same probability. The
  --    caller chooses nothing about the benchmark; it can only agree with it.
  select b.quote_ids, b.book_count, b.latest_quote_at, b.p_market_a
    into v_bench
    from public.win_forecast_benchmark(new.fight_id, new.fighter_a_id,
                                       new.fighter_b_id, new.actual_lock_at) b;
  if coalesce(v_bench.book_count, 0) = 0 then
    raise exception 'lock rejected: no sportsbook priced both corners of fight % in the 36 hours before the lock', new.fight_id;
  end if;
  if (select array_agg(x order by x) from unnest(new.market_quote_ids) x)
       is distinct from v_bench.quote_ids then
    raise exception 'lock rejected: market_quote_ids % are not the benchmark quotes % (each eligible book''s latest pre-lock price on each corner)',
      new.market_quote_ids, v_bench.quote_ids;
  end if;
  if new.market_book_count is distinct from v_bench.book_count then
    raise exception 'lock rejected: market_book_count % is not the % books the benchmark uses',
      new.market_book_count, v_bench.book_count;
  end if;
  if new.market_latest_quote_at is distinct from v_bench.latest_quote_at then
    raise exception 'lock rejected: market_latest_quote_at % is not the latest benchmark quote (%)',
      new.market_latest_quote_at, v_bench.latest_quote_at;
  end if;
  if abs(new.p_market_a - v_bench.p_market_a) > 1e-9 then
    raise exception 'lock rejected: p_market_a % does not match the probability recomputed from the cited quotes (%)',
      new.p_market_a, v_bench.p_market_a;
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
revoke all on function public.win_forecast_benchmark(bigint, bigint, bigint, timestamptz) from public, anon, authenticated;
grant execute on function public.win_forecast_benchmark(bigint, bigint, bigint, timestamptz) to service_role;
