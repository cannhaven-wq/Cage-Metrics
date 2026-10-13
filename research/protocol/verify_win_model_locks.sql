-- =============================================================================
-- verify_win_model_locks.sql — behavioural check of the proposed lock table.
--
-- Runs the proposed migration's body plus twelve checks inside one DO block
-- that ALWAYS ends by raising an exception, so every statement is rolled back
-- and nothing persists — the table, the triggers, the test rows. The outcome
-- is the text of that final exception: 'VERIFY-ROLLBACK 12 of 12 passed' or a
-- list of what failed. Safe to run against production for exactly that reason.
--
-- It inlines the migration body (everything between its begin; and commit;)
-- verbatim; tests/test_win_model_locks_sql.py fails if the two drift.
--
-- Run record, 2026-10-13: through the Supabase MCP tool a request this long
-- times out (60 s) with no statement left running and nothing persisted -
-- shorter requests of the same SQL finish in 0.3 s. So it was run as two
-- rolled-back halves, each re-creating the full table, guard and triggers:
-- A = checks 1-5 and 10 (5 of 5), B = 6-9, 11, 12 (6 of 6). Through psql the
-- whole file runs as one statement.
-- =============================================================================
do $verify$
declare
  up   record;   -- an unsettled fight on a card whose first bout is comfortably in the future
  done record;   -- a settled fight
  r    text := '';
  ok   int := 0;
  n    int := 0;
  lid  bigint;
  t    timestamptz;
  sha  text := repeat('a', 64);
begin
set local lock_timeout = '5s';

create table if not exists public.win_model_locks (
  id                    bigint generated always as identity primary key,

  -- what is being forecast
  fight_id              bigint not null references public.fights(id) on delete restrict,
  event_id              bigint not null references public.events(id) on delete restrict,
  event_date            date   not null,          -- overwritten by the guard from events
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
  actual_lock_at        timestamptz not null default clock_timestamp(),  -- overwritten by the guard

  -- what the market said at that moment (frozen; fight_odds is append-only too,
  -- but this makes the lock self-contained)
  market_p_a_vigfree    numeric not null,          -- median of per-book proportional de-vig, both sides required
  market_book_count     integer not null check (market_book_count >= 1),
  market_quotes         jsonb   not null,          -- [{book_id, book, american_a, american_b, captured_at}, ...]
  market_captured_at    timestamptz not null,      -- newest quote time in market_quotes
  market_source         text,                      -- e.g. 'fight_odds via v_fight_odds_latest_by_book'

  notes                 text,

  constraint win_model_locks_p_open   check (p_a > 0 and p_a < 1),
  constraint win_model_locks_mkt_open check (market_p_a_vigfree > 0 and market_p_a_vigfree < 1),
  constraint win_model_locks_corners  check (fighter_a_id <> fighter_b_id),
  constraint win_model_locks_sha      check (artifact_sha256 ~ '^[0-9a-f]{64}$'),
  constraint win_model_locks_commit   check (code_commit ~ '^[0-9a-f]{7,40}$'),
  constraint win_model_locks_exp      check (experiment_id ~ '^PRED-[0-9]{3}$'),
  constraint win_model_locks_quotes   check (jsonb_typeof(market_quotes) = 'array')
);

-- One forecast per fight per experiment. A re-run is refused by the index, so
-- the earliest lock wins, and neither a later opinion nor a sibling variant can
-- sit beside it.
create unique index if not exists win_model_locks_one_per_experiment
  on public.win_model_locks (fight_id, experiment_id);
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
  -- The wall clock at this insert, not the client's and not the transaction's.
  new.actual_lock_at := clock_timestamp();

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

  select event_date into new.event_date from public.events where id = f.event_id;

  select min(start_at) into v_start from public.v_fight_start_best where event_id = f.event_id;
  if v_start is null then
    raise exception 'lock rejected: no start time can be established for the card of fight %', new.fight_id;
  end if;
  if new.actual_lock_at >= v_start then
    raise exception 'lock rejected: the card of fight % starts % and the lock is %', new.fight_id, v_start, new.actual_lock_at;
  end if;

  if new.training_cutoff > new.event_date then
    raise exception 'lock rejected: training_cutoff % is after the event date %', new.training_cutoff, new.event_date;
  end if;
  if new.generated_at > new.actual_lock_at + interval '5 minutes' then
    raise exception 'lock rejected: generated_at % is in the future of the lock %', new.generated_at, new.actual_lock_at;
  end if;
  if new.market_captured_at > new.actual_lock_at then
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
   where f.winner_id is null and f.method is null and f.is_active is distinct from false
     and f.fighter_a_id is not null and f.fighter_b_id is not null
     and (select min(s.start_at) from public.v_fight_start_best s where s.event_id = f.event_id) > now() + interval '1 hour'
   order by e.event_date, f.id limit 1;
  select f.id, f.event_id, e.event_date, f.fighter_a_id, f.fighter_b_id into done
    from public.fights f join public.events e on e.id = f.event_id
   where f.winner_id is not null order by e.event_date desc limit 1;
  if up.id is null then raise exception 'VERIFY-ROLLBACK cannot run: no upcoming fight'; end if;

  -- 1. a valid lock is accepted; actual_lock_at is the wall clock even when the
  --    client back-dates it; event_date comes from events even when the client lies
  n := n + 1;
  insert into public.win_model_locks (fight_id, event_id, event_date, fighter_a_id, fighter_b_id, p_a,
     experiment_id, model_name, model_version, artifact_sha256, code_commit, training_cutoff,
     generated_at, actual_lock_at, market_p_a_vigfree, market_book_count, market_quotes, market_captured_at)
  values (up.id, up.event_id, date '1999-01-01', up.fighter_a_id, up.fighter_b_id, 0.55,
     'PRED-999', 'verify', 'v0', sha, 'abc1234', date '2024-12-31',
     now() - interval '1 minute', timestamptz '2000-01-01', 0.52, 3, '[]'::jsonb, now() - interval '5 minutes')
  returning id, actual_lock_at into lid, t;
  if t >= now() and t <= clock_timestamp()
     and (select event_date from public.win_model_locks where id = lid) = up.event_date
  then ok := ok + 1; r := r || ' 1:ok'; else r := r || ' 1:FAIL(lock time or event date taken from the client)'; end if;

  n := n + 1; begin
    insert into public.win_model_locks (fight_id, event_id, event_date, fighter_a_id, fighter_b_id, p_a, experiment_id, model_name, model_version, artifact_sha256, code_commit, training_cutoff, generated_at, market_p_a_vigfree, market_book_count, market_quotes, market_captured_at)
    values (up.id, up.event_id, up.event_date, up.fighter_a_id, up.fighter_b_id, 0.6, 'PRED-999', 'verify', 'v0', sha, 'abc1234', date '2024-12-31', now(), 0.52, 3, '[]'::jsonb, now() - interval '5 minutes');
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
    insert into public.win_model_locks (fight_id, event_id, event_date, fighter_a_id, fighter_b_id, p_a, experiment_id, model_name, model_version, artifact_sha256, code_commit, training_cutoff, generated_at, market_p_a_vigfree, market_book_count, market_quotes, market_captured_at)
    values (done.id, done.event_id, done.event_date, done.fighter_a_id, done.fighter_b_id, 0.6, 'PRED-999', 'verify', 'v1', sha, 'abc1234', date '2024-12-31', now(), 0.52, 3, '[]'::jsonb, now() - interval '5 minutes');
    r := r || ' 6:FAIL(settled fight accepted)';
  exception when others then
    if sqlerrm like 'lock rejected%' or sqlerrm like 'win_model_locks is append-only%' then ok := ok + 1; r := r || ' 6:ok';
    else r := r || ' 6:FAIL(wrong error: ' || sqlerrm || ')'; end if; end;
  n := n + 1; begin
    insert into public.win_model_locks (fight_id, event_id, event_date, fighter_a_id, fighter_b_id, p_a, experiment_id, model_name, model_version, artifact_sha256, code_commit, training_cutoff, generated_at, market_p_a_vigfree, market_book_count, market_quotes, market_captured_at)
    values (up.id, up.event_id, up.event_date, up.fighter_b_id, up.fighter_a_id, 0.6, 'PRED-998', 'verify', 'v2', sha, 'abc1234', date '2024-12-31', now(), 0.52, 3, '[]'::jsonb, now() - interval '5 minutes');
    r := r || ' 7:FAIL(swapped corners accepted)';
  exception when others then
    if sqlerrm like 'lock rejected%' or sqlerrm like 'win_model_locks is append-only%' then ok := ok + 1; r := r || ' 7:ok';
    else r := r || ' 7:FAIL(wrong error: ' || sqlerrm || ')'; end if; end;
  n := n + 1; begin
    insert into public.win_model_locks (fight_id, event_id, event_date, fighter_a_id, fighter_b_id, p_a, experiment_id, model_name, model_version, artifact_sha256, code_commit, training_cutoff, generated_at, market_p_a_vigfree, market_book_count, market_quotes, market_captured_at)
    values (up.id, up.event_id, up.event_date, up.fighter_a_id, up.fighter_b_id, 0.6, 'PRED-997', 'verify', 'v3', sha, 'abc1234', up.event_date + 1, now(), 0.52, 3, '[]'::jsonb, now() - interval '5 minutes');
    r := r || ' 8:FAIL(training cutoff after the event accepted)';
  exception when others then
    if sqlerrm like 'lock rejected%' or sqlerrm like 'win_model_locks is append-only%' then ok := ok + 1; r := r || ' 8:ok';
    else r := r || ' 8:FAIL(wrong error: ' || sqlerrm || ')'; end if; end;
  n := n + 1; begin
    insert into public.win_model_locks (fight_id, event_id, event_date, fighter_a_id, fighter_b_id, p_a, experiment_id, model_name, model_version, artifact_sha256, code_commit, training_cutoff, generated_at, market_p_a_vigfree, market_book_count, market_quotes, market_captured_at)
    values (up.id, up.event_id, up.event_date, up.fighter_a_id, up.fighter_b_id, 0.6, 'PRED-996', 'verify', 'v4', sha, 'abc1234', date '2024-12-31', now(), 0.52, 3, '[]'::jsonb, now() + interval '1 hour');
    r := r || ' 9:FAIL(future market snapshot accepted)';
  exception when others then
    if sqlerrm like 'lock rejected%' or sqlerrm like 'win_model_locks is append-only%' then ok := ok + 1; r := r || ' 9:ok';
    else r := r || ' 9:FAIL(wrong error: ' || sqlerrm || ')'; end if; end;
  n := n + 1; begin
    insert into public.win_model_locks (fight_id, event_id, event_date, fighter_a_id, fighter_b_id, p_a, experiment_id, model_name, model_version, artifact_sha256, code_commit, training_cutoff, generated_at, market_p_a_vigfree, market_book_count, market_quotes, market_captured_at)
    values (up.id, up.event_id, up.event_date, up.fighter_a_id, up.fighter_b_id, 0.6, 'PRED-999', 'verify', 'v5', sha, 'abc1234', date '2024-12-31', now(), 0.52, 3, '[]'::jsonb, now() - interval '5 minutes');
    r := r || ' 10:FAIL(second variant for the same fight and experiment accepted)';
  exception when unique_violation then ok := ok + 1; r := r || ' 10:ok'; end;

  -- 11. the training cutoff may equal the event date (the night-before run)
  n := n + 1; begin
    insert into public.win_model_locks (fight_id, event_id, event_date, fighter_a_id, fighter_b_id, p_a, experiment_id, model_name, model_version, artifact_sha256, code_commit, training_cutoff, generated_at, market_p_a_vigfree, market_book_count, market_quotes, market_captured_at)
    values (up.id, up.event_id, up.event_date, up.fighter_a_id, up.fighter_b_id, 0.6, 'PRED-995', 'verify', 'v6', sha, 'abc1234', up.event_date, now(), 0.52, 3, '[]'::jsonb, now() - interval '5 minutes');
    ok := ok + 1; r := r || ' 11:ok';
  exception when others then r := r || ' 11:FAIL(valid night-before lock rejected: ' || sqlerrm || ')'; end;

  n := n + 1;
  if not has_table_privilege('anon', 'public.win_model_locks', 'SELECT')
     and not has_table_privilege('anon', 'public.win_model_locks', 'INSERT')
     and not has_table_privilege('authenticated', 'public.win_model_locks', 'SELECT')
     and not has_table_privilege('authenticated', 'public.win_model_locks', 'INSERT')
     and not has_table_privilege('authenticated', 'public.win_model_locks', 'TRUNCATE')
     and not has_table_privilege('anon', 'public.win_model_locks', 'TRUNCATE')
     and not has_table_privilege('authenticated', 'public.v_win_model_locks_graded', 'SELECT')
     and not has_table_privilege('anon', 'public.v_win_model_locks_graded', 'SELECT')
  then ok := ok + 1; r := r || ' 12:ok';
  else r := r || ' 12:FAIL(browser role holds a privilege)'; end if;

  raise exception 'VERIFY-ROLLBACK % of % passed:%', ok, n, r;
end
$verify$;
