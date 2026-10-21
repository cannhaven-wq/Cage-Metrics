-- =============================================================================
-- T-076 — an observer OUTSIDE GitHub for the dead man's own liveness
-- =============================================================================
-- STATUS: PROPOSED, NOT APPLIED. Applying it is L3 (CRITICAL_GATES item 5: it
-- creates RLS-enabled tables and enables two extensions). The runbook is
-- research/ops/T076_DEAD_MAN_OBSERVER_RUNBOOK.md. Apply with psql, not the
-- Supabase MCP tool (see "NOTICE" below).
--
-- PLAIN ENGLISH: the dead man (dead-man.yml) shouts when the pre-fight record
-- is missing — but only when GitHub runs it. If GitHub stops running it, it
-- goes quiet, and quiet looks like healthy. This makes the dead man sign in to
-- the database every time it runs, and has the database itself (pg_cron, a
-- scheduler that is not GitHub's) check every hour that a sign-in has arrived
-- recently. If none has for 30 hours, the database opens a GitHub issue.
--
-- WHY THESE PIECES, measured 2026-10-21 against production (read-only):
--   pg_cron 1.6.4 and pg_net 0.20.0 are AVAILABLE and NOT enabled.
--   supabase_vault 0.3.1 is enabled and holds 0 secrets.
--   PostgreSQL 17.6.
-- Both extensions ship with every Supabase plan; enabling them is not a paid
-- add-on. Nothing here calls a paid service: the alarm is a GitHub issue, the
-- same channel dead-man.yml already uses.
--
-- WHAT THE OBSERVER DEPENDS ON, AND WHAT IT DOES NOT
--   Does not depend on: GitHub's scheduler, GitHub Actions, Railway, Resend.
--   Depends on: Supabase's database being up (if it is not, the dead man
--   itself fails loudly in GitHub — "I could not look" is a failure there — so
--   each of the two watches the other), and GitHub's REST API accepting an
--   issue (which works even when Actions schedules are throttled or disabled).
--
-- THE TWO LOOPS
--   1. dead man -> database: every run of build/check-pre-fight-coverage.js
--      inserts one row into watchdog_heartbeats (source 'dead-man').
--   2. database -> dead man: every hourly observer pass inserts a row too
--      (source 'observer'), and the dead man reads the latest one and says so
--      in its step summary when the observer has itself gone quiet.
--
-- ONLY SCHEDULED RUNS COUNT. A manual workflow_dispatch proves the script
-- works; it does not prove GitHub is still delivering the schedule, which is
-- the one thing being watched. Manual and local rows are kept for the record
-- and ignored by the verdict.
--
-- THE SERVER'S CLOCK, NEVER THE SENDER'S. ran_at is forced to
-- clock_timestamp() by trigger. COVERAGE_NOW lets a test run pretend to be in
-- the past or future; a heartbeat stamped by that clock would fake freshness.
--
-- ONE ISSUE PER STALL, NEVER ONE PER HOUR. A stall is identified by the last
-- heartbeat it is stuck behind; watchdog_liveness_alerts is UNIQUE on it and
-- the row is inserted BEFORE the request is sent — the same order
-- user_alert_deliveries uses, for the same reason: a crash between the two
-- costs one missing issue, never an unbounded stream. A new heartbeat starts a
-- new episode, so the next stall alerts again.
--
-- NO TOKEN, NO SILENCE. Until the owner stores the GitHub token in Vault, a
-- stall is still detected and recorded with delivery = 'not_configured', and
-- the dead man's step summary prints that the observer is not armed. It never
-- pretends to have sent anything.
--
-- NOTICE: `create table if not exists` on a table that already exists raises
-- a NOTICE, which hangs the Supabase MCP tool until its 60 s timeout. The
-- extensions are guarded by DO blocks for the same reason; re-applying the
-- whole file is still safest through psql.
-- =============================================================================

begin;
set local lock_timeout = '5s';

-- BEGIN EXTENSIONS (tests/test_t076_observer_sql.py strips this block and
-- stubs `cron`, `net` and `vault`, because a throwaway cluster has neither)
do $$
begin
  if not exists (select 1 from pg_extension where extname = 'pg_cron') then
    create extension pg_cron;
  end if;
  if not exists (select 1 from pg_extension where extname = 'pg_net') then
    create extension pg_net with schema extensions;
  end if;
end $$;
-- END EXTENSIONS

-- -----------------------------------------------------------------------------
-- 1. The heartbeat. Written by the dead man (service_role, via PostgREST) and
--    by the observer itself.
-- -----------------------------------------------------------------------------
create table if not exists public.watchdog_heartbeats (
  id         bigint generated always as identity primary key,
  source     text not null check (source in ('dead-man', 'observer')),
  outcome    text not null check (outcome in ('ok', 'breach', 'error', 'installed',
                                              'fresh', 'already_alerted',
                                              'sent', 'not_configured')),
  trigger    text not null check (trigger in ('schedule', 'workflow_dispatch', 'local',
                                              'migration', 'pg_cron')),
  ran_at     timestamptz not null default clock_timestamp(),
  -- observer rows only: is the GitHub token in Vault, i.e. could a stall
  -- actually be reported? NULL on dead-man rows.
  armed      boolean,
  run_url    text check (run_url is null or length(run_url) <= 300),
  detail     text check (detail is null or length(detail) <= 2000)
);

create index if not exists watchdog_heartbeats_source_ran_at
  on public.watchdog_heartbeats (source, trigger, ran_at desc);

create or replace function public.watchdog_heartbeats_server_clock()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.ran_at := clock_timestamp();
  return new;
end $$;

-- CREATE OR REPLACE, not DROP IF EXISTS: the latter raises a NOTICE on a first
-- apply, which hangs the Supabase MCP tool.
create or replace trigger watchdog_heartbeats_server_clock
  before insert on public.watchdog_heartbeats
  for each row execute function public.watchdog_heartbeats_server_clock();

-- -----------------------------------------------------------------------------
-- 2. One row per stall episode. The suppression memory for the alarm.
-- -----------------------------------------------------------------------------
create table if not exists public.watchdog_liveness_alerts (
  id                bigint generated always as identity primary key,
  source            text not null,
  last_heartbeat_at timestamptz not null,
  detected_at       timestamptz not null default clock_timestamp(),
  delivery          text not null default 'pending'
                    check (delivery in ('pending', 'sent', 'not_configured')),
  request_id        bigint,
  unique (source, last_heartbeat_at)
);

-- -----------------------------------------------------------------------------
-- 3. Private to both browser roles, written by service_role only.
--    Revoke from BOTH roles, then grant: revoking from anon alone once left
--    authenticated holding TRUNCATE, which ignores RLS (alerts_migration.sql).
-- -----------------------------------------------------------------------------
alter table public.watchdog_heartbeats enable row level security;
alter table public.watchdog_liveness_alerts enable row level security;

revoke all on public.watchdog_heartbeats from public, anon, authenticated;
revoke all on public.watchdog_liveness_alerts from public, anon, authenticated;
revoke all on sequence public.watchdog_heartbeats_id_seq from public, anon, authenticated;
revoke all on sequence public.watchdog_liveness_alerts_id_seq from public, anon, authenticated;

grant select, insert on public.watchdog_heartbeats to service_role;
grant select on public.watchdog_liveness_alerts to service_role;

-- Seed: start the clock at install time, so a freshly applied observer does not
-- alarm before the dead man has had a chance to run once.
insert into public.watchdog_heartbeats (source, outcome, trigger, detail)
select 'dead-man', 'installed', 'migration', 'T-076 observer installed'
where not exists (select 1 from public.watchdog_heartbeats where source = 'dead-man');

-- -----------------------------------------------------------------------------
-- 4. The verdict. Pure read: how old is the last SCHEDULED dead-man heartbeat?
--    30 hours matches .github/scripts/watchdog-cadence.js WORST_ACCEPTABLE_HOURS
--    and the dead-man.yml window in build/check-pipeline-health.js: three daily
--    positions put a healthy gap under ~13 h, and GitHub has delivered daily
--    schedules up to ~8 h late. tests/test_t076_observer_sql.py asserts they
--    agree.
-- -----------------------------------------------------------------------------
create or replace function public.dead_man_liveness(p_now timestamptz default clock_timestamp())
returns table (last_heartbeat_at timestamptz, age_hours numeric, stale boolean)
language sql
stable
set search_path = ''
as $$
  with last as (
    select max(h.ran_at) as at
      from public.watchdog_heartbeats h
     where h.source = 'dead-man'
       and h.trigger in ('schedule', 'migration')
  )
  select coalesce(last.at, '-infinity'::timestamptz),
         case when last.at is null then null
              else round((extract(epoch from (p_now - last.at)) / 3600)::numeric, 1) end,
         last.at is null or p_now - last.at > interval '30 hours'
    from last
$$;

-- -----------------------------------------------------------------------------
-- 5. The alarm. Called hourly by pg_cron. Returns what it did, and records it
--    as an 'observer' heartbeat so the dead man can see the observer is alive.
-- -----------------------------------------------------------------------------
create or replace function public.dead_man_liveness_alarm(p_now timestamptz default clock_timestamp())
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_last   timestamptz;
  v_age    numeric;
  v_stale  boolean;
  v_alert  bigint;
  v_token  text;
  v_req    bigint;
  v_result text;
begin
  select l.last_heartbeat_at, l.age_hours, l.stale
    into v_last, v_age, v_stale
    from public.dead_man_liveness(p_now) l;

  -- Read every pass, not only on a stall, so the observer's own heartbeat can
  -- say whether it is armed. Otherwise a missing token is discovered only at
  -- the moment it was needed.
  select s.decrypted_secret into v_token
    from vault.decrypted_secrets s
   where s.name = 'cfl_github_issue_token'
   limit 1;
  if v_token is not null and length(trim(v_token)) = 0 then v_token := null; end if;

  if not v_stale then
    v_result := 'fresh';
  else
    -- Insert BEFORE sending. A conflict means this stall was already reported.
    insert into public.watchdog_liveness_alerts (source, last_heartbeat_at)
    values ('dead-man', v_last)
    on conflict (source, last_heartbeat_at) do nothing
    returning id into v_alert;

    if v_alert is null then
      v_result := 'already_alerted';
    else
      if v_token is null then
        update public.watchdog_liveness_alerts
           set delivery = 'not_configured' where id = v_alert;
        v_result := 'not_configured';
      else
        select net.http_post(
          url     := 'https://api.github.com/repos/cannhaven-wq/Cage-Metrics/issues',
          body    := jsonb_build_object(
            'title',  'Dead man has not run on schedule for '
                      || coalesce(v_age::text, 'an unknown number of') || ' hours',
            'labels', jsonb_build_array('dead-man'),
            'body',   'The pre-fight record watchdog (`dead-man.yml`) has not checked in '
                      || 'from a scheduled run since `' || v_last::text || '`.' || E'\n\n'
                      || 'That usually means GitHub stopped delivering its schedule '
                      || '(throttling, or the 60-day inactivity disable). While it is '
                      || 'silent, a card can go off with no pre-fight record and nothing '
                      || 'will say so.' || E'\n\n'
                      || 'Check: Actions -> "Dead man — is the pre-fight record there?" -> '
                      || 'is it enabled, and when did it last run on a schedule? Re-enable '
                      || 'it and run it once by hand.' || E'\n\n'
                      || 'Opened by the Supabase pg_cron observer (T-076), which does not '
                      || 'depend on GitHub''s scheduler. One issue per stall; close it once '
                      || 'scheduled runs are back.' || E'\n\n'
                      || '<!-- cfl-deadman-liveness:' || v_last::text || ' -->'),
          headers := jsonb_build_object(
            'Authorization',        'Bearer ' || v_token,
            'Accept',               'application/vnd.github+json',
            'X-GitHub-Api-Version', '2022-11-28',
            'User-Agent',           'cfl-dead-man-observer',
            'Content-Type',         'application/json')
        ) into v_req;

        update public.watchdog_liveness_alerts
           set delivery = 'sent', request_id = v_req where id = v_alert;
        v_result := 'sent';
      end if;
    end if;
  end if;

  insert into public.watchdog_heartbeats (source, outcome, trigger, armed, detail)
  values ('observer', v_result, 'pg_cron', v_token is not null,
          'last scheduled dead-man heartbeat ' || coalesce(v_last::text, 'none')
          || coalesce(', ' || v_age::text || ' h ago', ''));

  -- The observer writes 24 rows a day. Keep a month of them; dead-man rows are
  -- kept, they are three a day and they are the record of the schedule.
  delete from public.watchdog_heartbeats
   where source = 'observer' and ran_at < p_now - interval '31 days';

  return v_result;
end $$;

-- Supabase's default privileges hand EXECUTE on every new function in public
-- to anon and authenticated (measured 2026-10-21). Neither may call these.
revoke all on function public.watchdog_heartbeats_server_clock() from public, anon, authenticated;
revoke all on function public.dead_man_liveness(timestamptz) from public, anon, authenticated;
revoke all on function public.dead_man_liveness_alarm(timestamptz) from public, anon, authenticated;
grant execute on function public.dead_man_liveness(timestamptz) to service_role;

-- -----------------------------------------------------------------------------
-- 6. The schedule. Minute 17, hourly. cron.schedule with an existing job name
--    replaces that job, so re-applying does not stack a second one.
-- -----------------------------------------------------------------------------
select cron.schedule('cfl-dead-man-liveness', '17 * * * *',
                     $job$select public.dead_man_liveness_alarm()$job$);

commit;
