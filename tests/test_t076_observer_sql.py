"""T-076 — the outside observer for the dead man, run against a real Postgres.

    python -m unittest tests/test_t076_observer_sql.py -v

The migration is PROPOSED, NOT APPLIED. These run it against a throwaway
cluster (initdb into a temp dir, unix socket only, destroyed afterwards) with
`cron`, `net` and `vault` stubbed, because a local cluster has neither pg_cron
nor pg_net. The stubs record what would have been scheduled and sent, so the
tests read back the request the observer would make to GitHub.

`SUPABASE_DB_URL` is never read. Skips where initdb is absent.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIG = os.path.join(REPO_ROOT, "research", "ops",
                   "proposed_2026-10-21_t076_dead_man_observer.sql")
PG_BIN_CANDIDATES = ("/usr/lib/postgresql/17/bin", "/usr/lib/postgresql/16/bin",
                     "/usr/lib/postgresql/15/bin", "/usr/local/pgsql/bin")
PORT = "55476"


def _pg_bin() -> str | None:
    for d in PG_BIN_CANDIDATES:
        if os.path.exists(os.path.join(d, "initdb")):
            return d
    which = shutil.which("initdb")
    return os.path.dirname(which) if which else None


# Supabase's roles, plus stand-ins for the three extensions the migration uses.
STUBS = """
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then create role service_role bypassrls; end if;
end $$;
create schema extensions;
create schema cron;
create table cron.jobs (jobname text primary key, schedule text, command text);
create function cron.schedule(p_name text, p_schedule text, p_command text) returns bigint
language sql as $$
  insert into cron.jobs values (p_name, p_schedule, p_command)
  on conflict (jobname) do update set schedule = excluded.schedule, command = excluded.command;
  select 1::bigint;
$$;
create schema net;
create table net.calls (id bigint generated always as identity, url text, body jsonb, headers jsonb);
create function net.http_post(url text, body jsonb default '{}', params jsonb default '{}',
                              headers jsonb default '{}', timeout_milliseconds int default 5000)
returns bigint language sql as $$
  insert into net.calls (url, body, headers) values (url, body, headers) returning id;
$$;
create schema vault;
create table vault.secrets_stub (name text primary key, decrypted_secret text);
create view vault.decrypted_secrets as select name, decrypted_secret from vault.secrets_stub;
"""


def migration_without_extensions() -> str:
    sql = open(MIG, encoding="utf-8").read()
    start, end = sql.index("-- BEGIN EXTENSIONS"), sql.index("-- END EXTENSIONS")
    return sql[:start] + sql[end + len("-- END EXTENSIONS"):]


class ObserverCase(unittest.TestCase):
    tmp = None

    @classmethod
    def setUpClass(cls):
        cls.bin_dir = _pg_bin()
        if not cls.bin_dir:
            raise unittest.SkipTest("no local Postgres (initdb not found)")
        cls.tmp = tempfile.mkdtemp(prefix="t076-pg-", dir="/var/tmp")
        os.chmod(cls.tmp, 0o777)
        data = os.path.join(cls.tmp, "data")
        cls.runas = "postgres" if os.geteuid() == 0 else None
        try:
            cls._run([os.path.join(cls.bin_dir, "initdb"), "-D", data, "-U", "pg", "--auth=trust"])
            cls._run([os.path.join(cls.bin_dir, "pg_ctl"), "-D", data, "-w",
                      "-o", f"-k {cls.tmp} -p {PORT} -c listen_addresses=",
                      "-l", os.path.join(cls.tmp, "log"), "start"])
        except Exception as e:                  # noqa: BLE001
            shutil.rmtree(cls.tmp, ignore_errors=True)
            cls.tmp = None
            raise unittest.SkipTest(f"could not start a throwaway Postgres: {e}")
        cls.mig_path = os.path.join(cls.tmp, "t076.sql")
        with open(cls.mig_path, "w", encoding="utf-8") as fh:
            fh.write(migration_without_extensions())
        os.chmod(cls.mig_path, 0o644)

    @classmethod
    def tearDownClass(cls):
        if not cls.tmp:
            return
        try:
            cls._run([os.path.join(cls.bin_dir, "pg_ctl"), "-D",
                      os.path.join(cls.tmp, "data"), "-m", "immediate", "stop"])
        except Exception:                       # noqa: BLE001
            pass
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @staticmethod
    def _as(runas, argv):
        if not runas:
            return argv
        import shlex
        return ["su", runas, "-s", "/bin/bash", "-c", " ".join(shlex.quote(a) for a in argv)]

    @classmethod
    def _run(cls, argv):
        out = subprocess.run(cls._as(cls.runas, argv), capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            raise RuntimeError(out.stderr.strip() or out.stdout.strip())
        return out.stdout

    def psql(self, sql, expect_error=False):
        argv = [os.path.join(self.bin_dir, "psql"), "-h", self.tmp, "-p", PORT, "-U", "pg",
                "-d", self.db, "-v", "ON_ERROR_STOP=1", "-At", "-c", sql]
        out = subprocess.run(self._as(self.runas, argv), capture_output=True, text=True, timeout=120)
        if expect_error:
            self.assertNotEqual(out.returncode, 0, f"expected rejection, it succeeded: {sql}")
            return out.stderr
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout.strip()

    def apply(self):
        argv = [os.path.join(self.bin_dir, "psql"), "-h", self.tmp, "-p", PORT, "-U", "pg",
                "-d", self.db, "-v", "ON_ERROR_STOP=1", "-q", "-f", self.mig_path]
        out = subprocess.run(self._as(self.runas, argv), capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr)

    def setUp(self):
        self.db = "t076_" + re.sub(r"\W", "_", self._testMethodName)[-40:]
        argv = [os.path.join(self.bin_dir, "psql"), "-h", self.tmp, "-p", PORT, "-U", "pg",
                "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-c"]
        self._run(argv + [f'drop database if exists "{self.db}"'])
        self._run(argv + [f'create database "{self.db}"'])
        self.psql(STUBS)
        self.apply()

    # -- helpers -------------------------------------------------------------
    def alarm(self, hours_ahead: float) -> str:
        return self.psql("select public.dead_man_liveness_alarm(clock_timestamp() + "
                         f"interval '{hours_ahead} hours')")

    def scheduled_heartbeat(self, trigger="schedule"):
        self.psql("insert into public.watchdog_heartbeats (source, outcome, trigger) "
                  f"values ('dead-man', 'ok', '{trigger}')")

    def store_token(self):
        self.psql("insert into vault.secrets_stub values ('cfl_github_issue_token', 'tok_test')")


class TestInstall(ObserverCase):
    def test_install_seeds_one_heartbeat_and_schedules_hourly(self):
        self.assertEqual(self.psql("select count(*) from public.watchdog_heartbeats "
                                   "where source='dead-man' and trigger='migration'"), "1")
        self.assertEqual(self.psql("select schedule || ' ' || command from cron.jobs"),
                         "17 * * * * select public.dead_man_liveness_alarm()")

    def test_reapplying_is_safe(self):
        self.apply()
        self.assertEqual(self.psql("select count(*) from public.watchdog_heartbeats"), "1")
        self.assertEqual(self.psql("select count(*) from cron.jobs"), "1")

    def test_a_fresh_install_does_not_alarm(self):
        self.assertEqual(self.alarm(1), "fresh")
        self.assertEqual(self.psql("select count(*) from public.watchdog_liveness_alerts"), "0")


class TestVerdict(ObserverCase):
    def test_stale_only_past_thirty_hours(self):
        self.assertEqual(self.alarm(29.5), "fresh")
        self.assertNotEqual(self.alarm(30.5), "fresh")

    def test_a_manual_run_does_not_reset_the_clock(self):
        self.psql("update public.watchdog_heartbeats set ran_at = ran_at - interval '40 hours'")
        self.scheduled_heartbeat(trigger="workflow_dispatch")
        self.scheduled_heartbeat(trigger="local")
        self.assertEqual(self.psql("select stale from public.dead_man_liveness()"), "t")

    def test_a_scheduled_run_does_reset_it(self):
        self.psql("update public.watchdog_heartbeats set ran_at = ran_at - interval '40 hours'")
        self.scheduled_heartbeat()
        self.assertEqual(self.psql("select stale from public.dead_man_liveness()"), "f")

    def test_the_sender_cannot_choose_its_own_timestamp(self):
        self.psql("insert into public.watchdog_heartbeats (source, outcome, trigger, ran_at) "
                  "values ('dead-man', 'ok', 'schedule', '2099-01-01')")
        self.assertEqual(self.psql("select count(*) from public.watchdog_heartbeats "
                                   "where ran_at > clock_timestamp() + interval '1 minute'"), "0")


class TestAlarm(ObserverCase):
    def test_no_token_is_recorded_not_sent(self):
        self.assertEqual(self.alarm(31), "not_configured")
        self.assertEqual(self.psql("select delivery from public.watchdog_liveness_alerts"),
                         "not_configured")
        self.assertEqual(self.psql("select count(*) from net.calls"), "0")
        self.assertEqual(self.psql("select armed from public.watchdog_heartbeats "
                                   "where source='observer'"), "f")

    def test_one_issue_per_stall_not_one_per_hour(self):
        self.store_token()
        self.assertEqual(self.alarm(31), "sent")
        self.assertEqual(self.alarm(32), "already_alerted")
        self.assertEqual(self.alarm(33), "already_alerted")
        self.assertEqual(self.psql("select count(*) from net.calls"), "1")
        self.assertEqual(self.psql("select count(*) from public.watchdog_liveness_alerts"), "1")

    def test_a_new_stall_after_recovery_alerts_again(self):
        self.store_token()
        self.assertEqual(self.alarm(31), "sent")
        self.scheduled_heartbeat()
        self.assertEqual(self.alarm(1), "fresh")
        self.assertEqual(self.alarm(31), "sent")
        self.assertEqual(self.psql("select count(*) from net.calls"), "2")

    def test_the_request_is_a_github_issue_with_the_token_from_vault(self):
        self.store_token()
        self.alarm(31)
        self.assertEqual(self.psql("select url from net.calls"),
                         "https://api.github.com/repos/cannhaven-wq/Cage-Metrics/issues")
        self.assertEqual(self.psql("select headers->>'Authorization' from net.calls"), "Bearer tok_test")
        self.assertEqual(self.psql("select body->'labels'->>0 from net.calls"), "dead-man")
        body = self.psql("select body->>'body' from net.calls")
        self.assertIn("dead-man.yml", body)
        self.assertIn("cfl-deadman-liveness:", body)
        self.assertEqual(self.psql("select delivery || ':' || (request_id is not null) "
                                   "from public.watchdog_liveness_alerts"), "sent:true")

    def test_every_pass_leaves_an_observer_heartbeat_saying_if_armed(self):
        self.alarm(1)
        self.store_token()
        self.alarm(2)
        self.assertEqual(self.psql("select string_agg(outcome || ':' || armed, ',' order by id) "
                                   "from public.watchdog_heartbeats where source='observer'"),
                         "fresh:false,fresh:true")

    def test_old_observer_rows_are_pruned_and_dead_man_rows_are_kept(self):
        self.alarm(1)
        self.psql("update public.watchdog_heartbeats set ran_at = ran_at - interval '40 days'")
        self.scheduled_heartbeat()
        self.alarm(1)
        self.assertEqual(self.psql("select count(*) from public.watchdog_heartbeats where source='observer'"), "1")
        self.assertEqual(self.psql("select count(*) from public.watchdog_heartbeats where source='dead-man'"), "2")


class TestPrivileges(ObserverCase):
    def test_browser_roles_cannot_read_write_truncate_or_call(self):
        for role in ("anon", "authenticated"):
            with self.subTest(role=role):
                for stmt in ("select * from public.watchdog_heartbeats",
                             "insert into public.watchdog_heartbeats (source, outcome, trigger) "
                             "values ('dead-man','ok','schedule')",
                             "truncate public.watchdog_heartbeats",
                             "select * from public.watchdog_liveness_alerts",
                             "truncate public.watchdog_liveness_alerts",
                             "select public.dead_man_liveness_alarm()",
                             "select * from public.dead_man_liveness()"):
                    err = self.psql(f"set role {role}; {stmt}", expect_error=True)
                    self.assertIn("permission denied", err)

    def test_service_role_can_write_a_heartbeat_and_read_the_observer(self):
        self.psql("set role service_role; insert into public.watchdog_heartbeats "
                  "(source, outcome, trigger) values ('dead-man','ok','schedule')")
        got = self.psql("set role service_role; select count(*) from public.watchdog_heartbeats")
        self.assertEqual(got.splitlines()[-1], "2")

    def test_service_role_cannot_forge_an_alert(self):
        err = self.psql("set role service_role; insert into public.watchdog_liveness_alerts "
                        "(source, last_heartbeat_at) values ('dead-man', now())", expect_error=True)
        self.assertIn("permission denied", err)


if __name__ == "__main__":
    unittest.main()
