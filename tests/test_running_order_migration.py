"""research/event-card/apply_2026-10-21_running_order.sql against a real Postgres.

    python -m pytest -q tests/test_running_order_migration.py

Same throwaway-cluster harness as test_sql_behaviour.py: initdb into a temp
directory, unix socket only, destroyed afterwards, SKIPPED when initdb is not
installed. No production database is touched; SUPABASE_DB_URL is never read.

What it proves: the file applies, re-applies with no change, is compatible with
the CLV event-flow migration in either order, refuses a wrong starting state
and rolls back completely when its own verification fails, and that the
objects it creates behave — the view returns the latest complete card of
active bookings, both tables are append-only including TRUNCATE, the browser
roles reach only the view, and the decision log refuses evidence the ledger
does not support.
"""
from __future__ import annotations

import os
import subprocess
import unittest

from test_sql_behaviour import CLV, REPO_ROOT, PostgresCase  # noqa: E402

MIGRATION = os.path.join(REPO_ROOT, "research", "event-card",
                         "apply_2026-10-21_running_order.sql")
CLV_EVENT_FLOW = os.path.join(CLV, "proposed_2026-09-16_event_flow.sql")

# fights as production has it for this purpose: is_active exists (applied
# 2026-09-19, add_bout_order_migration.sql).
ACTIVE = "alter table public.fights add column is_active boolean not null default true;"

FINGERPRINT = """
select string_agg(x, E'\\n' order by x) from (
  select 'idx ' || tablename || ' ' || indexdef as x from pg_indexes
   where schemaname = 'public' and tablename in ('fight_bout_order', 'fight_booking_status_log')
  union all
  select 'trg ' || tgrelid::regclass || ' ' || tgname || ' ' || tgenabled::text from pg_trigger
   where not tgisinternal and tgrelid in ('public.fight_bout_order'::regclass,
                                          'public.fight_booking_status_log'::regclass)
  union all
  select 'acl ' || c.relname || ' ' || coalesce(c.relacl::text, '') from pg_class c
   join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public' and c.relname in ('fight_bout_order', 'fight_booking_status_log',
     'v_card_running_order', 'fight_bout_order_id_seq', 'fight_booking_status_log_id_seq')
  union all
  select 'con ' || conrelid::regclass || ' ' || conname || ' ' || pg_get_constraintdef(oid)
   from pg_constraint where conrelid in ('public.fight_bout_order'::regclass,
                                         'public.fight_booking_status_log'::regclass)
  union all
  select 'view ' || pg_get_viewdef('public.v_card_running_order'::regclass)
) s
"""


class RunningOrderCase(PostgresCase):
    def apply(self, db: str, path: str = MIGRATION, expect_error: bool = False) -> str:
        argv = [os.path.join(self.bin_dir, "psql"), "-h", self.tmp, "-p", "55432",
                "-U", "pg", "-d", db, "-v", "ON_ERROR_STOP=1", "-f", path]
        out = subprocess.run(self._as(self.runas, argv), capture_output=True,
                             text=True, timeout=180)
        if expect_error:
            self.assertNotEqual(out.returncode, 0, "expected the migration to be refused")
            return out.stderr
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout

    def db_with_fights(self, name: str) -> str:
        db = self.fresh_db(name)
        self.psql(ACTIVE, db=db)
        self.psql("insert into public.fights (id, event_id) values "
                  "(1, 77), (2, 77), (3, 77), (4, 77), (9, 88)", db=db)
        return db


class TestApplyAndReapply(RunningOrderCase):
    def test_applies_then_reapplies_with_no_change(self):
        db = self.db_with_fights("ro_twice")
        self.apply(db)
        first = self.psql(FINGERPRINT, db=db)
        self.assertIn("fight_booking_status_log_once_idx", first)
        self.apply(db)
        self.assertEqual(self.psql(FINGERPRINT, db=db), first,
                         "a second apply changed the schema")

    def test_reapply_after_data_keeps_the_data(self):
        db = self.db_with_fights("ro_twice_data")
        self.apply(db)
        self.psql("insert into public.fight_bout_order (fight_id, event_id, bout_order, source) "
                  "values (1, 77, 2, 'ufcstats_card'), (2, 77, 1, 'ufcstats_card')", db=db)
        self.apply(db)
        self.assertEqual(self.psql("select count(*) from public.fight_bout_order", db=db), "2")

    def test_compatible_with_the_clv_migration_in_either_order(self):
        for name, order in (("ro_then_clv", [MIGRATION, CLV_EVENT_FLOW]),
                            ("clv_then_ro", [CLV_EVENT_FLOW, MIGRATION])):
            with self.subTest(order=name):
                db = self.db_with_fights(name)
                for path in order:
                    self.apply(db, path)
                self.assertEqual(self.psql(
                    "select string_agg(indexname, ',' order by indexname) from pg_indexes "
                    "where tablename = 'fight_bout_order'", db=db),
                    "fight_bout_order_card_idx,fight_bout_order_latest_idx,"
                    "fight_bout_order_one_per_instant_idx,fight_bout_order_pkey")


class TestRefusals(RunningOrderCase):
    def test_refuses_without_fights_is_active_and_leaves_nothing(self):
        db = self.fresh_db("ro_no_active")
        err = self.apply(db, expect_error=True)
        self.assertIn("fights.is_active", err)
        self.assertEqual(self.psql("select to_regclass('public.fight_bout_order') is null", db=db), "t")

    def test_refuses_the_old_unique_index(self):
        db = self.db_with_fights("ro_unique")
        self.psql("create table public.fight_bout_order (id bigserial primary key, fight_id bigint, "
                  "event_id bigint, bout_order int, source text, observed_at timestamptz); "
                  "create unique index fight_bout_order_unique_idx on public.fight_bout_order "
                  "(fight_id, source, bout_order)", db=db)
        self.assertIn("fight_bout_order_unique_idx", self.apply(db, expect_error=True))

    def test_a_failed_verification_rolls_the_whole_file_back(self):
        """A pre-existing ledger with a stray index: everything else would
        apply, the verification block notices, and nothing at all is left."""
        db = self.db_with_fights("ro_verify")
        self.psql("create table public.fight_bout_order (id bigserial primary key, "
                  "fight_id bigint not null references public.fights(id), event_id bigint not null, "
                  "bout_order int not null, source text not null, "
                  "observed_at timestamptz not null default now()); "
                  "create index stray_idx on public.fight_bout_order (source)", db=db)
        self.assertIn("ledger index set differs", self.apply(db, expect_error=True))
        self.assertEqual(self.psql(
            "select (to_regclass('public.fight_booking_status_log') is null)::text || ',' || "
            "(to_regclass('public.v_card_running_order') is null)::text", db=db), "true,true")


class TestBehaviour(RunningOrderCase):
    def setUp(self):
        self.db = self.db_with_fights("ro_behaviour")
        # Supabase's service_role has BYPASSRLS; the stub role must too, or the
        # test would be about the stub rather than the migration.
        self.psql("alter role service_role bypassrls")
        self.apply(self.db)
        # Three observations of event 77: fight 3 present in the first only.
        self.psql("""
          begin;
          insert into public.fight_bout_order (fight_id, event_id, bout_order, source, observed_at)
          values (1, 77, 3, 'ufcstats_card', '2026-10-14 07:20+00'),
                 (2, 77, 1, 'ufcstats_card', '2026-10-14 07:20+00'),
                 (3, 77, 2, 'ufcstats_card', '2026-10-14 07:20+00'),
                 (1, 77, 2, 'ufcstats_card', '2026-10-15 07:20+00'),
                 (2, 77, 1, 'ufcstats_card', '2026-10-15 07:20+00'),
                 (1, 77, 2, 'ufcstats_card', '2026-10-15 19:20+00'),
                 (2, 77, 1, 'ufcstats_card', '2026-10-15 19:20+00');
          commit;""", db=self.db)

    def q(self, sql, **kw):
        out = self.psql(sql, db=self.db, **kw)
        # `set role x; select ...` prints SET first; keep the answer.
        return out if kw.get("expect_error") else (out.splitlines() or [""])[-1]

    def test_view_returns_the_latest_complete_card(self):
        self.assertEqual(self.q("select string_agg(fight_id || ':' || bout_order, ',' "
                                "order by bout_order) from public.v_card_running_order "
                                "where event_id = 77"), "2:1,1:2")

    def test_view_ignores_manual_rows_and_follows_a_newer_espn_card(self):
        self.q("insert into public.fight_bout_order (fight_id, event_id, bout_order, source, observed_at) "
               "values (1, 77, 1, 'manual', '2026-10-16 07:20+00')")
        self.assertEqual(self.q("select string_agg(fight_id || ':' || bout_order, ',' "
                                "order by bout_order) from public.v_card_running_order "
                                "where event_id = 77"), "2:1,1:2")
        self.q("insert into public.fight_bout_order (fight_id, event_id, bout_order, source, observed_at) "
               "values (1, 77, 1, 'espn_scoreboard', '2026-10-16 08:00+00'), "
               "(2, 77, 2, 'espn_scoreboard', '2026-10-16 08:00+00')")
        self.assertEqual(self.q("select string_agg(fight_id || ':' || bout_order, ',' "
                                "order by bout_order) from public.v_card_running_order "
                                "where event_id = 77"), "1:1,2:2")

    def test_the_log_checks_evidence_within_its_own_source(self):
        self.q("insert into public.fight_bout_order (fight_id, event_id, bout_order, source, observed_at) "
               "values (1, 77, 1, 'espn_scoreboard', '2026-10-16 08:00+00')")
        # Evidence from the UFCStats ledger cannot be claimed under the ESPN source.
        self.q(self.RETIRE.format(fid=3, at="2026-10-15 19:20+00", n=2,
                                  ev="'2026-10-15 19:20+00','2026-10-15 07:20+00'")
               .replace("'ufcstats_card')", "'espn_scoreboard')"), expect_error=True)
        self.q(self.RETIRE.format(fid=3, at="2026-10-15 19:20+00", n=2,
                                  ev="'2026-10-15 19:20+00','2026-10-15 07:20+00'")
               .replace("'ufcstats_card')", "'provider')"), expect_error=True)

    def test_view_drops_a_retired_booking(self):
        self.q("update public.fights set is_active = false where id = 2")
        self.assertEqual(self.q("select string_agg(fight_id::text, ',') from "
                                "public.v_card_running_order where event_id = 77"), "1")

    def test_ledger_is_append_only_including_truncate(self):
        for sql in ("update public.fight_bout_order set bout_order = 9",
                    "delete from public.fight_bout_order",
                    "truncate public.fight_bout_order"):
            with self.subTest(sql=sql):
                self.assertIn("append-only", self.q(sql, expect_error=True))

    def test_browser_roles_reach_only_the_view(self):
        self.assertIn("permission denied",
                      self.q("set role anon; select count(*) from public.fight_bout_order",
                             expect_error=True))
        self.assertIn("permission denied",
                      self.q("set role authenticated; select count(*) from public.fight_booking_status_log",
                             expect_error=True))
        self.assertEqual(self.q("set role anon; select count(*) from public.v_card_running_order"), "2")
        self.assertEqual(self.q(
            "select bool_or(has_table_privilege(r, 'public.v_card_running_order', p)) "
            "from unnest(array['anon','authenticated']) r, "
            "unnest(array['INSERT','UPDATE','DELETE','TRUNCATE']) p"), "f")

    def test_service_role_appends_and_cannot_rewrite(self):
        self.q("set role service_role; insert into public.fight_bout_order "
               "(fight_id, event_id, bout_order, source) values (1, 77, 1, 'ufcstats_card')")
        self.assertIn("permission denied",
                      self.q("set role service_role; truncate public.fight_booking_status_log",
                             expect_error=True))

    RETIRE = ("insert into public.fight_booking_status_log (fight_id, event_id, is_active, reason, "
              "observed_at, evidence_observed_at, confirmations, source) values "
              "({fid}, 77, false, 'retired_absent_from_card', '{at}', array[{ev}]::timestamptz[], "
              "{n}, 'ufcstats_card')")

    def test_a_supported_retirement_is_recorded_once(self):
        ok = self.RETIRE.format(fid=3, at="2026-10-15 19:20+00", n=2,
                                ev="'2026-10-15 19:20+00','2026-10-15 07:20+00'")
        self.q(ok)
        self.assertIn("duplicate key", self.q(ok, expect_error=True))
        for sql in ("update public.fight_booking_status_log set reason = 'manual'",
                    "delete from public.fight_booking_status_log",
                    "truncate public.fight_booking_status_log"):
            with self.subTest(sql=sql):
                self.assertIn("append-only", self.q(sql, expect_error=True))

    def test_the_log_refuses_evidence_the_ledger_does_not_support(self):
        cases = {
            "one absence only": self.RETIRE.format(
                fid=3, at="2026-10-15 19:20+00", n=1, ev="'2026-10-15 19:20+00'"),
            "the fight is on that card": self.RETIRE.format(
                fid=1, at="2026-10-15 19:20+00", n=2,
                ev="'2026-10-15 19:20+00','2026-10-15 07:20+00'"),
            "not an observation": self.RETIRE.format(
                fid=3, at="2026-10-16 07:20+00", n=2,
                ev="'2026-10-16 07:20+00','2026-10-15 07:20+00'"),
            "observed_at is not the newest evidence": self.RETIRE.format(
                fid=3, at="2026-10-15 07:20+00", n=2,
                ev="'2026-10-15 19:20+00','2026-10-15 07:20+00'"),
            "a newer observation exists": self.RETIRE.format(
                fid=3, at="2026-10-15 07:20+00", n=1, ev="'2026-10-15 07:20+00'")
                .replace(", 1, 'ufcstats", ", 2, 'ufcstats"),
            "direction contradicts reason": self.RETIRE.format(
                fid=3, at="2026-10-15 19:20+00", n=2,
                ev="'2026-10-15 19:20+00','2026-10-15 07:20+00'").replace("false", "true"),
        }
        for why, sql in cases.items():
            with self.subTest(why=why):
                self.q(sql, expect_error=True)
        self.assertEqual(self.q("select count(*) from public.fight_booking_status_log"), "0")

    def test_a_reactivation_must_be_on_the_latest_card(self):
        base = ("insert into public.fight_booking_status_log (fight_id, event_id, is_active, reason, "
                "observed_at, evidence_observed_at, source) values ({fid}, 77, true, "
                "'reactivated_back_on_card', '2026-10-15 19:20+00', "
                "array['2026-10-15 19:20+00']::timestamptz[], 'ufcstats_card')")
        self.q(base.format(fid=1))
        self.q(base.format(fid=3), expect_error=True)


if __name__ == "__main__":
    unittest.main()
