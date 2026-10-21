> **DEFERRED by the CFL Owner, 2026-10-21 (decision packet C4).** Nothing here is
> applied or wired in. The heartbeat code was removed from the dead-man job;
> first evaluate the monitoring already in place. Kept as a reference only.

# T-076 — Turning on the dead man's outside observer

**Plain version.** The dead man checks that every card has its pre-fight record.
It only runs when GitHub runs it. If GitHub stops running it, it goes quiet, and
quiet looks the same as healthy. This adds a second clock that is not GitHub's:
the database checks every hour that the dead man has signed in during the last
30 hours, and opens a GitHub issue if it has not.

**Status on 2026-10-21: built, tested, not live.** The dead man's half is in
`build/check-pre-fight-coverage.js` and is harmless until the table exists. The
database half is
[`proposed_2026-10-21_t076_dead_man_observer.sql`](proposed_2026-10-21_t076_dead_man_observer.sql),
not applied.

## Cost

Nothing, as far as can be checked from the repo and the database:

- `pg_cron` 1.6.4 and `pg_net` 0.20.0 are already **available** on the project
  (they come with Supabase) and are simply not switched on. Measured read-only
  on 2026-10-21.
- Supabase Vault is already on (0 secrets stored).
- The alarm is a GitHub issue, the same channel `dead-man.yml` already uses. A
  fine-grained GitHub token is free.
- Load: one tiny query an hour, about 4 rows a day kept, plus 24 observer rows
  a day pruned after 31 days.

Not checked here: the Supabase plan's own terms. If the plan bills for anything
these use, that makes it L3 item 6 and it stops.

## The owner's steps

Applying the migration is L3 (CRITICAL_GATES item 5: new tables with RLS, two
extensions). Creating the token is something only the owner can do.

1. **Create a fine-grained GitHub token.** GitHub -> Settings -> Developer
   settings -> Fine-grained tokens -> Generate.
   - Resource owner: `cannhaven-wq`. Repository access: **only** `Cage-Metrics`.
   - Permissions: **Issues: Read and write**. Nothing else.
   - Expiry: the longest you are comfortable with, with a calendar reminder.
     An expired token makes the observer unable to speak. The dead man's step
     summary says "NOT ARMED" when the token is missing, but cannot see an
     expired one; the first failed alert shows in `net._http_response`
     (query below).
2. **Apply the migration with psql** (not the Supabase MCP tool; see the file
   header):
   ```
   psql "$SUPABASE_DB_URL" -f research/ops/proposed_2026-10-21_t076_dead_man_observer.sql
   ```
3. **Store the token in Vault** in the Supabase SQL editor. Never in the repo,
   never in chat:
   ```sql
   select vault.create_secret('<the token>', 'cfl_github_issue_token',
                              'T-076: opens dead-man issues from pg_cron');
   ```
4. **Check it** (step 5 below), then mark the file `STATUS: APPLIED <date>` and
   record the decision.

Without step 3 the observer still runs and still notices a stall, but records
it as `not_configured` instead of opening an issue. It never pretends to have
sent anything.

## 5. Checking it works

```sql
-- the job exists and runs hourly at :17
select jobname, schedule, active from cron.job where jobname = 'cfl-dead-man-liveness';
select status, start_time from cron.job_run_details
 where jobid = (select jobid from cron.job where jobname = 'cfl-dead-man-liveness')
 order by start_time desc limit 5;

-- the dead man has checked in from a scheduled run, and the observer is armed
select source, trigger, outcome, armed, ran_at from public.watchdog_heartbeats
 order by ran_at desc limit 10;
select * from public.dead_man_liveness();

-- a dry run of the verdict and dedupe WITHOUT waiting 30 hours. pg_net queues
-- the request in a table and sends it only after COMMIT, so the rollback
-- discards both the alert row and the request: nothing reaches GitHub. Expect
-- 'sent' with the token stored, 'not_configured' without it.
-- To prove the GitHub end for real, run the select alone (no begin/rollback):
-- that opens one real issue, which you then close.
begin;
select public.dead_man_liveness_alarm(clock_timestamp() + interval '31 hours');
rollback;

-- what GitHub answered to a real alert (201 = issue created)
select a.detected_at, a.delivery, r.status_code, left(r.content, 200)
  from public.watchdog_liveness_alerts a
  left join net._http_response r on r.id = a.request_id
 order by a.detected_at desc limit 5;
```

The dead man's own step summary gains a heading, **"Who watches the
watchdog"**, which says on every run one of: not installed, never ran, stale,
running but NOT ARMED, or running and armed.

## How the pieces fit

| piece | where | what it does |
|---|---|---|
| heartbeat write | `build/check-pre-fight-coverage.js::liveness` | every run inserts one row (`ok` / `breach` / `error`); never changes the exit code |
| server clock | trigger on `watchdog_heartbeats` | `ran_at` is the database's time, not the sender's, so a pretend-time run cannot fake freshness (and such runs write nothing anyway) |
| verdict | `public.dead_man_liveness()` | only **scheduled** heartbeats count; manual runs prove the script, not the schedule; stale past 30 h, same as `watchdog-cadence.js` and `check-pipeline-health.js` |
| alarm | `public.dead_man_liveness_alarm()` via pg_cron `17 * * * *` | one GitHub issue per stall, labelled `dead-man`; alert row inserted before the request, UNIQUE on the stalled heartbeat |
| watching the watcher | observer heartbeat + `observerVerdict` | each pass leaves its own row with `armed`; the dead man reads it back and says if the observer has stopped (3 h window) |

**Each watches the other.** If the database is down, the dead man fails loudly
inside GitHub ("I could not look" is a failure). If GitHub stops the schedule,
the database notices. If pg_cron stops, the dead man's summary says so on its
next run. What remains unwatched is both stopping at once.

## Closing the issue

The observer opens an issue and does not close it: a stall is something a
person should look at even after it ends. Close it by hand once scheduled runs
are back; the next stall opens a new one.

## Undo

```sql
select cron.unschedule('cfl-dead-man-liveness');
drop function public.dead_man_liveness_alarm(timestamptz);
drop function public.dead_man_liveness(timestamptz);
drop table public.watchdog_liveness_alerts;
drop table public.watchdog_heartbeats;
drop function public.watchdog_heartbeats_server_clock();
delete from vault.secrets where name = 'cfl_github_issue_token';
```

The dead man keeps working after this: its heartbeat write fails harmlessly and
its summary goes back to "NOT INSTALLED". Revoke the GitHub token too.
