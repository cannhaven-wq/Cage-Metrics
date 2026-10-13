
-- =============================================================================
-- verify_win_model_locks.sql — behavioural check of the proposed lock table.
--
-- Runs the WHOLE proposed migration plus ten checks inside one DO block that
-- ALWAYS ends by raising an exception, so every statement is rolled back and
-- nothing persists — the table, the triggers, the test rows. The outcome is the
-- text of that final exception: 'VERIFY-ROLLBACK ... 10/10 passed' or a list of
-- what failed. Safe to run against production for exactly that reason.
--
-- It inlines the migration verbatim; tests/test_prediction_protocol.py fails if
-- the two drift, so edit both together.
-- =============================================================================
do $verify$
declare
  up   record;   -- an unsettled fight whose start is comfortably in the future
  done record;   -- a settled fight
  r    text := '';
  ok   int := 0;
  n    int := 0;
  lid  bigint;
  t    timestamptz;
  sha  text := repeat('a', 64);
begin
-- =============================================================================
-- proposed_2026-10-13_win_model_locks.sql — PRED-001 §8.8: the forecast lock
--
-- STATUS: PROPOSED. NOT APPLIED. Applying it is a production migration
-- (CRITICAL_GATES L3 item 5) and needs the owner's explicit go after review.
--
-- Plain version: one row per forecast, written before the fight, that nobody
-- can change or delete afterwards — not us, not the service key, not a
-- migration that forgets. Each row freezes the probability, which model and
-- which exact build made it, what it was trained on, and every sportsbook price
-- we could see at that moment. That row is the only evidence PRED-001 accepts.
--
-- What it creates, and nothing else:
--   1. public.win_model_locks           the ledger (private: service_role only)
--   2. win_model_locks_guard()          insert-time rules (below)
--   3. append-only triggers             UPDATE / DELETE / TRUNCATE all raise
--   4. public.v_win_model_locks_graded  read-side join to results, private
-- It touches no existing table, view, policy or row. Idempotent.
--
-- Insert-time rules (the guard). A lock is REJECTED when:
--   a. the fight already has a result on file;
--   b. the server clock is at or after the fight's best-known start
--      (v_fight_start_best: bell_at > provider commence > event_date 18:00 UTC);
--   b2. the booking has been retired (is_active = false);
--   c. the corners do not match the fights row as it stands at lock time
--      (rebooked-in-place rows exist: fights 43, 46, 8780);
--   d. training_cutoff is after the lock, or after the event date;
--   e. the market snapshot is dated after the lock;
--   f. the probability is not strictly inside (0, 1);
--   g. a required provenance field (artifact hash, code commit, experiment id)
--      is missing or malformed.
-- actual_lock_at is ALWAYS the database's now(): a client-supplied value is
-- overwritten, so a late lock cannot be back-dated. (prop_model_locks trusts
-- the client here; this table does not.)
--
-- Rollback: this creates only new objects. Before the first lock:
--   drop view if exists public.v_win_model_locks_graded;
--   drop table if exists public.win_model_locks;   -- (append-only triggers go with it)
--   drop function if exists public.win_model_locks_guard();
--   drop function if exists public.win_model_locks_no_rewrite();
-- AFTER the first lock the table is evidence and is not dropped; a defect is
-- fixed by a new table version, never by editing rows.
-- =============================================================================

-- Adding the foreign keys takes a SHARE ROW EXCLUSIVE lock on fights and events,
-- which waits behind any open writer (the odds job, the scrapers). Fail fast
-- instead of queueing every later writer behind this migration.
set local lock_timeout = '5s';

create table if not exists public.win_model_locks (
  id                    bigint generated always as identity primary key,

  -- what is being forecast
  fight_id              bigint not null references public.fights(id) on delete restrict,
  event_id              bigint not null references public.events(id) on delete restrict,
  event_date            date   not null,
  fighter_a_id          bigint not null,
  fighter_b_id          bigint not null,
  p_a                   numeric not null,          -- P(fighter_a_id wins); decided fights only are graded

  -- who made it (PRED-001 provenance)
  experiment_id         text   not null,           -- e.g. 'PRED-002'
  model_name            text   not null,
  model_version         text   not null,
  artifact_sha256       text   not null,           -- the frozen model file
  code_commit           text   not null,           -- git commit of the lock script
  training_cutoff       date   not null,           -- trained only on events strictly before this date
  training_n_fights     integer,
  features              jsonb,                     -- the exact input row
  feature_hash          text,                      -- sha256 of features, as the script computed it

  -- when
  generated_at          timestamptz not null,      -- when the script computed p_a
  actual_lock_at        timestamptz not null default now(),  -- overwritten by the guard with now()

  -- what the market said at that moment (frozen; fight_odds is append-only too,
  -- but this makes the lock self-contained)
  market_p_a_vigfree    numeric,                   -- median of per-book proportional de-vig, both sides required
  market_book_count     integer,
  market_quotes         jsonb,                     -- [{book_id, book, american_a, american_b, captured_at}, ...]
  market_captured_at    timestamptz,               -- newest quote time in market_quotes
  market_source         text,                      -- e.g. 'fight_odds via v_fight_odds_latest_by_book'

  notes                 text,

  constraint win_model_locks_p_open   check (p_a > 0 and p_a < 1),
  constraint win_model_locks_mkt_open check (market_p_a_vigfree is null or (market_p_a_vigfree > 0 and market_p_a_vigfree < 1)),
  constraint win_model_locks_corners  check (fighter_a_id <> fighter_b_id),
  constraint win_model_locks_sha      check (artifact_sha256 ~ '^[0-9a-f]{64}$'),
  constraint win_model_locks_commit   check (code_commit ~ '^[0-9a-f]{7,40}$'),
  constraint win_model_locks_exp      check (experiment_id ~ '^PRED-[0-9]{3}$'),
  constraint win_model_locks_quotes   check (market_quotes is null or jsonb_typeof(market_quotes) = 'array')
);

-- One forecast per fight per model build. A re-run is refused by the index, so
-- the earliest lock wins and a second, later opinion can never replace it.
create unique index if not exists win_model_locks_one_per_build
  on public.win_model_locks (fight_id, experiment_id, model_version, artifact_sha256);
create index if not exists win_model_locks_event_idx on public.win_model_locks (event_date, event_id);
create index if not exists win_model_locks_exp_idx   on public.win_model_locks (experiment_id, model_version);

comment on table public.win_model_locks is
  'PRED-001 forecast ledger. Append-only: UPDATE, DELETE and TRUNCATE raise for every role. Insert-time guard rejects locks after the start, on settled fights, on rebooked corners, or with a training cutoff after the lock. actual_lock_at is always the database clock.';

-- ---------------------------------------------------------------------------
-- Append-only
-- ---------------------------------------------------------------------------
create or replace function public.win_model_locks_no_rewrite()
returns trigger language plpgsql as $$
begin
  raise exception
    'win_model_locks is append-only: % rejected. A forecast on record is evidence; a new model build writes a new row.',
    tg_op;
end;
$$;

drop trigger if exists win_model_locks_block_update on public.win_model_locks;
create trigger win_model_locks_block_update
  before update on public.win_model_locks
  for each row execute function public.win_model_locks_no_rewrite();
drop trigger if exists win_model_locks_block_delete on public.win_model_locks;
create trigger win_model_locks_block_delete
  before delete on public.win_model_locks
  for each row execute function public.win_model_locks_no_rewrite();
drop trigger if exists win_model_locks_block_truncate on public.win_model_locks;
create trigger win_model_locks_block_truncate
  before truncate on public.win_model_locks
  for each statement execute function public.win_model_locks_no_rewrite();

-- ---------------------------------------------------------------------------
-- Insert guard. SECURITY INVOKER (the default): it only reads fights /
-- v_fight_start_best, which the inserting service_role can read.
-- ---------------------------------------------------------------------------
create or replace function public.win_model_locks_guard()
returns trigger language plpgsql as $$
declare
  f        record;
  v_start  timestamptz;
begin
  -- The database clock, not the client's.
  new.actual_lock_at := now();

  select fighter_a_id, fighter_b_id, winner_id, method, event_id, is_active
    into f from public.fights where id = new.fight_id;
  if not found then
    raise exception 'lock rejected: fight % does not exist', new.fight_id;
  end if;
  if f.is_active is false then
    raise exception 'lock rejected: fight % is a retired booking', new.fight_id;
  end if;
  if f.winner_id is not null or f.method is not null then
    raise exception 'lock rejected: fight % already has a result on file', new.fight_id;
  end if;
  if f.event_id is distinct from new.event_id then
    raise exception 'lock rejected: fight % belongs to event %, not %', new.fight_id, f.event_id, new.event_id;
  end if;
  if f.fighter_a_id is distinct from new.fighter_a_id or f.fighter_b_id is distinct from new.fighter_b_id then
    raise exception 'lock rejected: corners (%, %) do not match fight % as booked (%, %)',
      new.fighter_a_id, new.fighter_b_id, new.fight_id, f.fighter_a_id, f.fighter_b_id;
  end if;

  select start_at into v_start from public.v_fight_start_best where fight_id = new.fight_id;
  if v_start is null then
    raise exception 'lock rejected: no start time can be established for fight %', new.fight_id;
  end if;
  if new.actual_lock_at >= v_start then
    raise exception 'lock rejected: fight % starts % and the lock is %', new.fight_id, v_start, new.actual_lock_at;
  end if;

  if new.training_cutoff > new.actual_lock_at::date or new.training_cutoff > new.event_date then
    raise exception 'lock rejected: training_cutoff % is after the lock or the event', new.training_cutoff;
  end if;
  if new.generated_at > new.actual_lock_at then
    raise exception 'lock rejected: generated_at % is in the future of the lock %', new.generated_at, new.actual_lock_at;
  end if;
  if new.market_captured_at is not null and new.market_captured_at > new.actual_lock_at then
    raise exception 'lock rejected: market snapshot % is dated after the lock %', new.market_captured_at, new.actual_lock_at;
  end if;
  return new;
end;
$$;

drop trigger if exists win_model_locks_guard_insert on public.win_model_locks;
create trigger win_model_locks_guard_insert
  before insert on public.win_model_locks
  for each row execute function public.win_model_locks_guard();

-- ---------------------------------------------------------------------------
-- Private. RLS on with no policy, and every privilege revoked from BOTH
-- browser roles — revoking from anon alone once left authenticated holding
-- TRUNCATE from Supabase defaults (see alerts_migration.sql).
-- ---------------------------------------------------------------------------
alter table public.win_model_locks enable row level security;
revoke all on public.win_model_locks from anon, authenticated;
revoke all on sequence public.win_model_locks_id_seq from anon, authenticated;
revoke all on function public.win_model_locks_guard() from anon, authenticated, public;
revoke all on function public.win_model_locks_no_rewrite() from anon, authenticated, public;

-- ---------------------------------------------------------------------------
-- Read side: locks joined to results. security_invoker, so it is exactly as
-- private as the table under it.
-- ---------------------------------------------------------------------------
create or replace view public.v_win_model_locks_graded
  with (security_invoker = true) as
select
  l.id as lock_id, l.experiment_id, l.model_name, l.model_version, l.artifact_sha256,
  l.fight_id, l.event_id, l.event_date, l.actual_lock_at,
  l.p_a, l.market_p_a_vigfree, l.market_book_count, l.market_captured_at,
  f.winner_id,
  case when f.winner_id = l.fighter_a_id then 1
       when f.winner_id = l.fighter_b_id then 0 end as y_a,
  -- graded only when the bout still has the corners the lock named
  (f.fighter_a_id = l.fighter_a_id and f.fighter_b_id = l.fighter_b_id) as corners_unchanged
from public.win_model_locks l
join public.fights f on f.id = l.fight_id;

revoke all on public.v_win_model_locks_graded from anon, authenticated;

comment on view public.v_win_model_locks_graded is
  'PRED-001 grading join. y_a is null for draws, no-contests and unsettled fights. corners_unchanged=false marks a bout rebooked in place after the lock: excluded from scoring, never re-attributed.';

  select f.id, f.event_id, e.event_date, f.fighter_a_id, f.fighter_b_id into up
    from public.fights f join public.events e on e.id = f.event_id
    join public.v_fight_start_best s on s.fight_id = f.id
   where f.winner_id is null and f.method is null and s.start_at > now() + interval '1 hour'
     and f.fighter_a_id is not null and f.fighter_b_id is not null
   order by s.start_at limit 1;
  select f.id, f.event_id, e.event_date, f.fighter_a_id, f.fighter_b_id into done
    from public.fights f join public.events e on e.id = f.event_id
   where f.winner_id is not null order by e.event_date desc limit 1;
  if up.id is null then raise exception 'VERIFY-ROLLBACK cannot run: no upcoming fight'; end if;

  -- 1. a valid lock is accepted, and actual_lock_at is the DB clock even when the client back-dates it
  n := n + 1;
  insert into public.win_model_locks (fight_id, event_id, event_date, fighter_a_id, fighter_b_id, p_a,
     experiment_id, model_name, model_version, artifact_sha256, code_commit, training_cutoff,
     generated_at, actual_lock_at, market_p_a_vigfree, market_captured_at, market_quotes)
  values (up.id, up.event_id, up.event_date, up.fighter_a_id, up.fighter_b_id, 0.55,
     'PRED-999', 'verify', 'v0', sha, 'abc1234', date '2024-12-31',
     now() - interval '1 minute', timestamptz '2000-01-01', 0.52, now() - interval '5 minutes', '[]'::jsonb)
  returning id, actual_lock_at into lid, t;
  if t = now() then ok := ok + 1; r := r || ' 1:ok'; else r := r || ' 1:FAIL(actual_lock_at=' || t || ')'; end if;

  -- helper pattern: each rejection check expects an exception
  n := n + 1; begin
    insert into public.win_model_locks (fight_id, event_id, event_date, fighter_a_id, fighter_b_id, p_a, experiment_id, model_name, model_version, artifact_sha256, code_commit, training_cutoff, generated_at)
    values (up.id, up.event_id, up.event_date, up.fighter_a_id, up.fighter_b_id, 0.6, 'PRED-999', 'verify', 'v0', sha, 'abc1234', date '2024-12-31', now());
    r := r || ' 2:FAIL(duplicate accepted)';
  exception when unique_violation then ok := ok + 1; r := r || ' 2:ok'; end;

  n := n + 1; begin
    update public.win_model_locks set p_a = 0.9 where id = lid;
    r := r || ' 3:FAIL(update accepted)';
  exception when others then
    if sqlerrm like 'lock rejected%' or sqlerrm like 'win_model_locks is append-only%' then ok := ok + 1; r := r || ' 3:ok';
    else r := r || ' 3:FAIL(wrong error: ' || sqlerrm || ')'; end if; end;

  n := n + 1; begin
    delete from public.win_model_locks where id = lid;
    r := r || ' 4:FAIL(delete accepted)';
  exception when others then
    if sqlerrm like 'lock rejected%' or sqlerrm like 'win_model_locks is append-only%' then ok := ok + 1; r := r || ' 4:ok';
    else r := r || ' 4:FAIL(wrong error: ' || sqlerrm || ')'; end if; end;

  n := n + 1; begin
    truncate public.win_model_locks;
    r := r || ' 5:FAIL(truncate accepted)';
  exception when others then
    if sqlerrm like 'lock rejected%' or sqlerrm like 'win_model_locks is append-only%' then ok := ok + 1; r := r || ' 5:ok';
    else r := r || ' 5:FAIL(wrong error: ' || sqlerrm || ')'; end if; end;

  n := n + 1; begin
    insert into public.win_model_locks (fight_id, event_id, event_date, fighter_a_id, fighter_b_id, p_a, experiment_id, model_name, model_version, artifact_sha256, code_commit, training_cutoff, generated_at)
    values (done.id, done.event_id, done.event_date, done.fighter_a_id, done.fighter_b_id, 0.6, 'PRED-999', 'verify', 'v1', sha, 'abc1234', date '2024-12-31', now());
    r := r || ' 6:FAIL(settled fight accepted)';
  exception when others then
    if sqlerrm like 'lock rejected%' or sqlerrm like 'win_model_locks is append-only%' then ok := ok + 1; r := r || ' 6:ok';
    else r := r || ' 6:FAIL(wrong error: ' || sqlerrm || ')'; end if; end;

  n := n + 1; begin
    insert into public.win_model_locks (fight_id, event_id, event_date, fighter_a_id, fighter_b_id, p_a, experiment_id, model_name, model_version, artifact_sha256, code_commit, training_cutoff, generated_at)
    values (up.id, up.event_id, up.event_date, up.fighter_b_id, up.fighter_a_id, 0.6, 'PRED-999', 'verify', 'v2', sha, 'abc1234', date '2024-12-31', now());
    r := r || ' 7:FAIL(swapped corners accepted)';
  exception when others then
    if sqlerrm like 'lock rejected%' or sqlerrm like 'win_model_locks is append-only%' then ok := ok + 1; r := r || ' 7:ok';
    else r := r || ' 7:FAIL(wrong error: ' || sqlerrm || ')'; end if; end;

  n := n + 1; begin
    insert into public.win_model_locks (fight_id, event_id, event_date, fighter_a_id, fighter_b_id, p_a, experiment_id, model_name, model_version, artifact_sha256, code_commit, training_cutoff, generated_at)
    values (up.id, up.event_id, up.event_date, up.fighter_a_id, up.fighter_b_id, 0.6, 'PRED-999', 'verify', 'v3', sha, 'abc1234', up.event_date + 1, now());
    r := r || ' 8:FAIL(future training cutoff accepted)';
  exception when others then
    if sqlerrm like 'lock rejected%' or sqlerrm like 'win_model_locks is append-only%' then ok := ok + 1; r := r || ' 8:ok';
    else r := r || ' 8:FAIL(wrong error: ' || sqlerrm || ')'; end if; end;

  n := n + 1; begin
    insert into public.win_model_locks (fight_id, event_id, event_date, fighter_a_id, fighter_b_id, p_a, experiment_id, model_name, model_version, artifact_sha256, code_commit, training_cutoff, generated_at, market_captured_at)
    values (up.id, up.event_id, up.event_date, up.fighter_a_id, up.fighter_b_id, 0.6, 'PRED-999', 'verify', 'v4', sha, 'abc1234', date '2024-12-31', now(), now() + interval '1 hour');
    r := r || ' 9:FAIL(future market snapshot accepted)';
  exception when others then
    if sqlerrm like 'lock rejected%' or sqlerrm like 'win_model_locks is append-only%' then ok := ok + 1; r := r || ' 9:ok';
    else r := r || ' 9:FAIL(wrong error: ' || sqlerrm || ')'; end if; end;

  n := n + 1;
  if not has_table_privilege('anon', 'public.win_model_locks', 'SELECT')
     and not has_table_privilege('anon', 'public.win_model_locks', 'INSERT')
     and not has_table_privilege('authenticated', 'public.win_model_locks', 'SELECT')
     and not has_table_privilege('authenticated', 'public.win_model_locks', 'INSERT')
     and not has_table_privilege('authenticated', 'public.win_model_locks', 'TRUNCATE')
     and not has_table_privilege('anon', 'public.win_model_locks', 'TRUNCATE')
     and not has_table_privilege('authenticated', 'public.v_win_model_locks_graded', 'SELECT')
     and not has_table_privilege('anon', 'public.v_win_model_locks_graded', 'SELECT')
  then ok := ok + 1; r := r || ' 10:ok';
  else r := r || ' 10:FAIL(browser role holds a privilege)'; end if;

  raise exception 'VERIFY-ROLLBACK % of % passed:%', ok, n, r;
end
$verify$;
