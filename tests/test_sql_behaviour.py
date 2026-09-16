"""Behavioural tests for the proposed CLV-001 SQL, run against a real Postgres.

    python -m unittest tests/test_sql_behaviour.py -v

`test_migrations_idempotent.py` reads the migration files as TEXT and checks
their shape. That catches a missing guard; it cannot catch a view that parses
perfectly and returns the wrong row. Two of Amendment 6's items are exactly that
kind of defect:

  * (f) `v_clv_close_reference` took the card's scheduled start from the latest
    commence observation belonging to ANY fight on the event. Every static check
    it had still passed.
  * (g) the `fight_odds` immutability trigger either lets the legacy `is_closer`
    promotion through while rejecting a price edit, or it does not. Nothing about
    its text tells you which.

So these run the DDL against a throwaway cluster, insert fixtures, and read the
answers back.

**No production database is touched, ever.** The cluster is created by `initdb`
into a temporary directory, listens on a unix socket in that directory with
`listen_addresses` empty, and is destroyed in `tearDownClass`. `SUPABASE_DB_URL`
is never read. If `initdb` is unavailable — the normal case on a dev laptop and
in CI — every test here SKIPS rather than failing, and the static suite still
covers the file's shape.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLV = os.path.join(REPO_ROOT, "research", "clv")

PG_BIN_CANDIDATES = ("/usr/lib/postgresql/16/bin", "/usr/lib/postgresql/15/bin",
                     "/usr/lib/postgresql/14/bin", "/usr/local/pgsql/bin")


def _pg_bin() -> str | None:
    for d in PG_BIN_CANDIDATES:
        if os.path.exists(os.path.join(d, "initdb")):
            return d
    which = shutil.which("initdb")
    return os.path.dirname(which) if which else None


# Minimal stand-ins for the production tables the proposed DDL references. Only
# the columns the migrations and the view actually read — a full schema copy
# would drift from production and start testing itself.
STUBS = """
-- Supabase's roles. Cluster-wide, so created idempotently: the migrations
-- revoke from them and a bare CREATE ROLE would fail on the second database.
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon')
    then create role anon; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated')
    then create role authenticated; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role')
    then create role service_role; end if;
end $$;

create table public.fights (
  id bigint primary key,
  event_id bigint not null,
  fighter_a_id bigint,
  fighter_b_id bigint,
  bell_at timestamptz
);
create table public.fight_start_estimates (
  id bigint generated always as identity primary key,
  fight_id bigint not null references public.fights(id) on delete cascade,
  source text not null,
  start_at timestamptz not null,
  observed_at timestamptz not null default now(),
  note text
);
create table public.pre_fight_snapshots (
  id bigint generated always as identity primary key,
  fight_id integer not null unique,
  snapshot_at timestamptz not null default now(),
  engine_published_at timestamptz,
  edge_side text,
  edge_bet_fighter_id integer,
  edge_odds_at_publish integer
);
create table public.fight_odds (
  id bigint generated always as identity primary key,
  fight_id bigint not null,
  fighter_id bigint not null,
  book_id bigint not null,
  american_odds integer,
  implied_prob numeric,
  captured_at timestamptz not null,
  is_opener boolean default false,
  is_closer boolean default false,
  source_event_id text,
  feed_version text,
  opponent_fighter_id bigint,
  provider_last_update timestamptz,
  retrieved_at timestamptz,
  market_status text,
  raw jsonb
);
"""


class PostgresCase(unittest.TestCase):
    """Brings up one throwaway cluster for the whole class."""

    tmp: str | None = None
    bin_dir: str | None = None

    @classmethod
    def setUpClass(cls):
        cls.bin_dir = _pg_bin()
        if not cls.bin_dir:
            raise unittest.SkipTest("no local Postgres (initdb not found)")
        cls.tmp = tempfile.mkdtemp(prefix="clv-pg-", dir="/var/tmp")
        os.chmod(cls.tmp, 0o777)
        data = os.path.join(cls.tmp, "data")
        # Postgres refuses to run as root, so when the suite is running as root
        # the cluster is owned by the system `postgres` account.
        cls.runas = "postgres" if os.geteuid() == 0 else None
        try:
            cls._run([os.path.join(cls.bin_dir, "initdb"), "-D", data,
                      "-U", "pg", "--auth=trust"])
            cls._run([os.path.join(cls.bin_dir, "pg_ctl"), "-D", data, "-w",
                      "-o", f"-k {cls.tmp} -p 55432 -c listen_addresses=",
                      "-l", os.path.join(cls.tmp, "log"), "start"])
        except Exception as e:                  # noqa: BLE001
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise unittest.SkipTest(f"could not start a throwaway Postgres: {e}")

    @classmethod
    def tearDownClass(cls):
        if not cls.tmp:
            return
        try:
            cls._run([os.path.join(cls.bin_dir, "pg_ctl"), "-D",
                      os.path.join(cls.tmp, "data"), "-m", "immediate", "stop"])
        except Exception:                       # noqa: BLE001 - teardown is best effort
            pass
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @staticmethod
    def _as(runas, argv):
        """Re-quote for `su -c`, which takes one shell string.

        shlex.quote, not hand-rolled quoting: the SQL below is full of single
        quotes and `$$`, and double-quoting it hands `$$` to the shell, which
        cheerfully substitutes its own PID into the middle of a DO block.
        """
        if not runas:
            return argv
        import shlex
        return ["su", runas, "-s", "/bin/bash", "-c",
                " ".join(shlex.quote(a) for a in argv)]

    @classmethod
    def _run(cls, argv):
        argv = cls._as(cls.runas, argv)
        out = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            raise RuntimeError(out.stderr.strip() or out.stdout.strip())
        return out.stdout

    def psql(self, sql: str, db: str = "postgres", expect_error: bool = False) -> str:
        argv = [os.path.join(self.bin_dir, "psql"), "-h", self.tmp, "-p", "55432",
                "-U", "pg", "-d", db, "-v", "ON_ERROR_STOP=1", "-At", "-c", sql]
        out = subprocess.run(self._as(self.runas, argv), capture_output=True,
                             text=True, timeout=120)
        if expect_error:
            self.assertNotEqual(out.returncode, 0,
                                f"expected this to be rejected, it succeeded: {sql}")
            return out.stderr
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout.strip()

    def psql_file(self, path: str, db: str = "postgres"):
        argv = [os.path.join(self.bin_dir, "psql"), "-h", self.tmp, "-p", "55432",
                "-U", "pg", "-d", db, "-v", "ON_ERROR_STOP=1", "-f", path]
        out = subprocess.run(self._as(self.runas, argv), capture_output=True,
                             text=True, timeout=180)
        self.assertEqual(out.returncode, 0, out.stderr)

    def fresh_db(self, name: str):
        self.psql(f'drop database if exists "{name}"')
        self.psql(f'create database "{name}"')
        self.psql(STUBS, db=name)
        return name


class TestBoutOneSchedule(PostgresCase):
    """Amendment 6 (f). The card's scheduled start is BOUT 1's own schedule.

    Reed's regression: bout 1 and bout 12 carry different provider commence
    values, and bout 1's cutoff must be bout 1's.
    """

    BOUT1 = "2026-10-03T22:00:00+00"      # what the provider says about bout 1
    BOUT12 = "2026-10-04T04:30:00+00"     # ... and about the main event

    def setUp(self):
        self.db = self.fresh_db("clv_sched")
        self.psql_file(os.path.join(CLV, "proposed_2026-09-16_event_flow.sql"),
                       db=self.db)
        self.psql("""
          insert into public.fights (id, event_id) values (1, 900), (12, 900);
          -- One complete card observation: fight 1 opens, fight 12 closes.
          insert into public.fight_bout_order (fight_id, event_id, bout_order,
                                               source, observed_at)
            values (1, 900, 1, 'ufcstats_card', '2026-10-01T12:00:00+00'),
                   (12, 900, 12, 'ufcstats_card', '2026-10-01T12:00:00+00');
          -- Bout 12's commence is observed LATER than bout 1's, which is the
          -- normal case: the tail of the card is re-estimated as the night is
          -- rebuilt. The old view took the newest observation on the event and
          -- therefore handed bout 1 this value.
          insert into public.fight_start_estimates (fight_id, source, start_at,
                                                    observed_at)
            values (1, 'odds_api_commence', '%s', '2026-10-01T09:00:00+00'),
                   (12, 'odds_api_commence', '%s', '2026-10-02T09:00:00+00');
        """ % (self.BOUT1, self.BOUT12), db=self.db)

    def test_bout_one_takes_its_own_scheduled_start(self):
        got = self.psql(
            "select reference_at, reference_basis, card_start_fight_id "
            "from public.v_clv_close_reference where fight_id = 1", db=self.db)
        reference_at, basis, start_fight = got.split("|")
        self.assertEqual(basis, "scheduled_first_bout")
        self.assertEqual(start_fight, "1",
                         "the schedule must come from the bout-1 fight itself")
        self.assertIn("22:00:00", reference_at)
        self.assertNotIn("04:30:00", reference_at,
                         "bout 1's cutoff was set from bout 12's commence time — "
                         "six and a half hours late, and every in-play price on "
                         "the card would have been eligible as its close")

    def test_a_later_bout_does_not_inherit_the_card_start_as_a_cutoff(self):
        got = self.psql(
            "select coalesce(reference_at::text, 'null'), reference_basis "
            "from public.v_clv_close_reference where fight_id = 12", db=self.db)
        reference_at, basis = got.split("|")
        self.assertEqual(reference_at, "null")
        self.assertEqual(basis, "card_scheduled_start",
                         "reported, never scored (Amendment 4.1)")

    def test_a_reschedule_of_bout_one_moves_the_cutoff_in_either_direction(self):
        self.psql("""
          insert into public.fight_start_estimates (fight_id, source, start_at,
                                                    observed_at)
            values (1, 'odds_api_commence', '2026-10-03T21:00:00+00',
                    '2026-10-02T18:00:00+00');
        """, db=self.db)
        got = self.psql("select reference_at from public.v_clv_close_reference "
                        "where fight_id = 1", db=self.db)
        self.assertIn("21:00:00", got,
                      "a card moved EARLIER must move the cutoff earlier; max() "
                      "would have kept the superseded 22:00")

    def test_a_scratched_opener_cannot_supply_the_schedule(self):
        # Fight 1 is dropped from the card; fight 12 becomes bout 1.
        self.psql("""
          insert into public.fight_bout_order (fight_id, event_id, bout_order,
                                               source, observed_at)
            values (12, 900, 1, 'ufcstats_card', '2026-10-02T12:00:00+00');
        """, db=self.db)
        got = self.psql(
            "select fight_id, coalesce(reference_at::text,'null'), "
            "coalesce(card_start_fight_id::text,'null') "
            "from public.v_clv_close_reference order by fight_id", db=self.db)
        rows = dict(line.split("|", 1) for line in got.splitlines())
        self.assertTrue(rows["12"].endswith("|12"),
                        f"bout 1 is now fight 12 and the schedule must be its "
                        f"own; got {rows['12']!r}")
        self.assertIn("04:30:00", rows["12"])
        self.assertTrue(rows["1"].startswith("null"),
                        "the scratched fight is off the card and has no cutoff")


class TestFightOddsImmutability(PostgresCase):
    """Amendment 6 (g). The raw quote evidence is actually durable (R-01)."""

    def setUp(self):
        self.db = self.fresh_db("clv_immutable")
        self.psql_file(
            os.path.join(CLV, "proposed_2026-09-16_fight_odds_immutability.sql"),
            db=self.db)
        self.psql("""
          insert into public.fight_odds (fight_id, fighter_id, book_id,
                american_odds, implied_prob, captured_at, source_event_id, raw)
            values (1, 101, 11, 150, 0.40, '2026-09-12T21:50:00+00',
                    'odds-api-evt-7f3', '{"bookmaker":"draftkings"}');
        """, db=self.db)

    def test_the_legacy_closer_promotion_still_works(self):
        """The one UPDATE path in the repo. If this broke, the migration would
        take the odds cron down on the next card night."""
        self.psql("update public.fight_odds set is_closer = true where id = 1",
                  db=self.db)
        self.assertEqual(self.psql("select is_closer from public.fight_odds "
                                   "where id = 1", db=self.db), "t")
        self.psql("update public.fight_odds set is_closer = false where id = 1",
                  db=self.db)
        self.assertEqual(self.psql("select is_closer from public.fight_odds "
                                   "where id = 1", db=self.db), "f")
        self.psql("update public.fight_odds set is_opener = true where id = 1",
                  db=self.db)

    def test_a_price_cannot_be_rewritten(self):
        err = self.psql("update public.fight_odds set american_odds = -200 "
                        "where id = 1", db=self.db, expect_error=True)
        self.assertIn("immutable", err)
        self.assertIn("american_odds", err, "the error names the offending field")
        self.assertEqual(self.psql("select american_odds from public.fight_odds "
                                   "where id = 1", db=self.db), "150")

    def test_the_capture_instant_cannot_be_rewritten(self):
        err = self.psql("update public.fight_odds set captured_at = "
                        "'2026-09-12T21:59:00+00' where id = 1",
                        db=self.db, expect_error=True)
        self.assertIn("captured_at", err)

    def test_provenance_cannot_be_rewritten(self):
        for col, val in (("source_event_id", "'some-other-market'"),
                         ("opponent_fighter_id", "999"),
                         ("raw", "'{}'::jsonb"),
                         ("book_id", "12"),
                         ("fighter_id", "202")):
            with self.subTest(column=col):
                err = self.psql(f"update public.fight_odds set {col} = {val} "
                                f"where id = 1", db=self.db, expect_error=True)
                self.assertIn(col, err)

    def test_a_column_added_after_the_trigger_is_protected_too(self):
        """Whitelist by construction. A blacklist would leave this unprotected
        until somebody remembered to add it."""
        self.psql("alter table public.fight_odds add column proxy_cutoff_at "
                  "timestamptz", db=self.db)
        self.psql("update public.fight_odds set is_closer = true where id = 1",
                  db=self.db)          # still fine
        err = self.psql("update public.fight_odds set proxy_cutoff_at = "
                        "'2026-09-12T22:00:00+00' where id = 1",
                        db=self.db, expect_error=True)
        self.assertIn("proxy_cutoff_at", err)

    def test_delete_is_rejected(self):
        err = self.psql("delete from public.fight_odds where id = 1",
                        db=self.db, expect_error=True)
        self.assertIn("append-only", err)
        self.assertEqual(self.psql("select count(*) from public.fight_odds",
                                   db=self.db), "1")

    def test_truncate_is_rejected(self):
        err = self.psql("truncate public.fight_odds", db=self.db,
                        expect_error=True)
        self.assertIn("append-only", err)
        self.assertEqual(self.psql("select count(*) from public.fight_odds",
                                   db=self.db), "1")

    def test_inserting_a_new_observation_is_still_free(self):
        """Append-only means append. A correction is a new row, never an edit."""
        self.psql("""
          insert into public.fight_odds (fight_id, fighter_id, book_id,
                american_odds, captured_at)
            values (1, 101, 11, -200, '2026-09-12T21:55:00+00');
        """, db=self.db)
        self.assertEqual(self.psql("select count(*) from public.fight_odds",
                                   db=self.db), "2")

    def test_the_migration_is_rerunnable(self):
        self.psql_file(
            os.path.join(CLV, "proposed_2026-09-16_fight_odds_immutability.sql"),
            db=self.db)
        err = self.psql("delete from public.fight_odds where id = 1",
                        db=self.db, expect_error=True)
        self.assertIn("append-only", err)


class TestProposedMigrationsApply(PostgresCase):
    """All four files, in the documented order, on one database.

    A migration that parses is not a migration that applies: a constraint naming
    a column another file adds later, or a view built on a table that does not
    exist yet, fails only here.
    """

    ORDER = ("proposed_2026-09-16_fight_odds_capture.sql",
             "proposed_2026-09-16_fight_odds_immutability.sql",
             "proposed_2026-09-16_event_flow.sql",
             "proposed_2026-09-16_snapshot_edge_identity.sql",
             "proposed_2026-09-16_clv001_columns.sql")

    def setUp(self):
        self.db = self.fresh_db("clv_all")
        # model_edges, enough of it for the result columns to land on.
        self.psql("""
          create table public.model_edges (
            id bigint generated always as identity primary key,
            fight_id bigint, event_date date, side text, bet_fighter_id bigint,
            odds_at_publish integer, published_at timestamptz, source text,
            clv_pp numeric, clv_beat boolean, settled_at timestamptz
          );
        """, db=self.db)

    def test_all_four_apply_in_order(self):
        for name in self.ORDER:
            with self.subTest(migration=name):
                self.psql_file(os.path.join(CLV, name), db=self.db)

    def test_applying_them_twice_changes_nothing(self):
        for name in self.ORDER:
            self.psql_file(os.path.join(CLV, name), db=self.db)
        for name in self.ORDER:
            with self.subTest(migration=name, run=2):
                self.psql_file(os.path.join(CLV, name), db=self.db)

    def test_the_compare_and_set_write_lets_exactly_one_settler_win(self):
        """Amendment 7 (a), the race half.

        `_partition_for_write` reads `clv_scored_at IS NULL` and the write
        happens later, so two settlers overlapping — a cron firing while someone
        runs it by hand, a retry on a slow run — can both classify the same row
        as fresh. The application logic is write-once; the DATABASE write has to
        be too, or "written once" holds only while nothing races it.

        This is the statement the settler issues, run twice against a real
        Postgres. The filter is evaluated as part of the UPDATE, so the second
        one matches no row and comes back empty — which is the settler's signal
        to go and verify what the winner wrote, never to write over it.
        """
        for name in self.ORDER:
            self.psql_file(os.path.join(CLV, name), db=self.db)
        self.psql("insert into public.model_edges (fight_id, side, "
                  "odds_at_publish, source) values (1, 'a', 150, 'live')",
                  db=self.db)
        # Wrapped in a CTE so psql returns the ROW COUNT alone; a bare
        # UPDATE ... RETURNING also prints its command tag, which is not data.
        claim = """
          with claimed as (
          update public.model_edges
             set clv_return = %s, closing_fair_probability = 0.51,
                 closing_book_count = 3, clv_protocol_version = 'CLV-001@1.0.10',
                 clv_scored_at = %s, clv_source_quote_ids = '{1,2}',
                 clv_closing_consensus = '{}'::jsonb, clv_consensus_sha256 = 'abc',
                 clv_close_basis = 'scheduled_first_bout',
                 clv_lead_time_minutes = 10, clv_lead_time_is_lower_bound = false,
                 clv_proxy_quoted_at = '2026-09-12T21:50:00+00',
                 clv_cutoff_at = '2026-09-12T22:00:00+00',
                 clv_publish_quote_id = %s
           where id = 1 and clv_scored_at is null
          returning id)
          select count(*) from claimed
        """
        first = self.psql(claim % ("0.02", "'2026-09-13T06:00:00+00'", "9001"),
                          db=self.db)
        self.assertEqual(first, "1", "the first settler must claim the row")

        second = self.psql(claim % ("0.99", "'2026-09-14T06:00:00+00'", "9999"),
                           db=self.db)
        self.assertEqual(second, "0", "the second settler must match NO row")

        kept = self.psql("select clv_return, clv_scored_at, clv_publish_quote_id "
                         "from public.model_edges where id = 1", db=self.db)
        value, scored_at, quote_id = kept.split("|")
        self.assertEqual(float(value), 0.02,
                         "the first settler's observation must survive")
        self.assertEqual(quote_id, "9001")
        self.assertIn("2026-09-13", scored_at,
                      "clv_scored_at records when the row was FIRST scored and "
                      "must not be refreshed by a later run")

    def test_an_unconditional_patch_by_id_would_have_overwritten_it(self):
        """The control. Without the filter the second write wins, silently, and
        `clv_scored_at` moves with it — which is exactly what was happening."""
        for name in self.ORDER:
            self.psql_file(os.path.join(CLV, name), db=self.db)
        # A complete scored row: the completeness constraint is NOT VALID but it
        # binds new rows, so a half-filled one is rejected before this test can
        # make its point.
        self.psql("""
          insert into public.model_edges (fight_id, side, odds_at_publish, source,
            clv_return, closing_fair_probability, closing_book_count,
            clv_protocol_version, clv_scored_at, clv_source_quote_ids,
            clv_closing_consensus, clv_consensus_sha256, clv_close_basis,
            clv_lead_time_minutes, clv_lead_time_is_lower_bound,
            clv_proxy_quoted_at, clv_cutoff_at, clv_publish_quote_id)
          values (1, 'a', 150, 'live', 0.02, 0.51, 3, 'CLV-001@1.0.10',
                  '2026-09-13T06:00:00+00', '{1,2}', '{}'::jsonb, 'abc',
                  'scheduled_first_bout', 10, false,
                  '2026-09-12T21:50:00+00', '2026-09-12T22:00:00+00', 9001)
        """, db=self.db)
        self.psql("update public.model_edges set clv_return = 0.99, "
                  "clv_scored_at = '2026-09-14T06:00:00+00' where id = 1",
                  db=self.db)
        self.assertEqual(
            float(self.psql("select clv_return from public.model_edges "
                            "where id = 1", db=self.db)), 0.99,
            "an unconditional PATCH by id overwrites a scored row — the reason "
            "the settler no longer issues one")

    def test_the_snapshot_edge_columns_land_nullable_and_paired(self):
        """Amendment 7 (e). `edge_published_at` is the EDGE's publication
        instant; `engine_published_at` is the model PICK's and is a different
        record. The two constraints keep the new column honest."""
        for name in self.ORDER:
            self.psql_file(os.path.join(CLV, name), db=self.db)

        # A pre-existing snapshot: NULL in both new columns, untouched.
        self.psql("insert into public.pre_fight_snapshots (fight_id, snapshot_at,"
                  " engine_published_at) values (1, '2026-09-09T12:00:00+00',"
                  " '2026-09-07T12:00:00+00')", db=self.db)
        self.assertEqual(
            self.psql("select coalesce(edge_model_edge_id::text,'null'), "
                      "coalesce(edge_published_at::text,'null') "
                      "from public.pre_fight_snapshots where fight_id = 1",
                      db=self.db), "null|null")

        # A modern one: both present, and consistent.
        self.psql("""
          insert into public.pre_fight_snapshots (fight_id, snapshot_at,
            engine_published_at, edge_model_edge_id, edge_published_at,
            edge_side, edge_bet_fighter_id, edge_odds_at_publish)
          values (2, '2026-09-09T12:00:00+00', '2026-09-07T12:00:00+00',
                  7, '2026-09-08T12:00:00+00', 'a', 101, 150)
        """, db=self.db)

    def test_an_edge_instant_without_an_edge_id_is_rejected(self):
        for name in self.ORDER:
            self.psql_file(os.path.join(CLV, name), db=self.db)
        err = self.psql("insert into public.pre_fight_snapshots (fight_id, "
                        "snapshot_at, edge_published_at) values "
                        "(3, '2026-09-09T12:00:00+00', '2026-09-08T12:00:00+00')",
                        db=self.db, expect_error=True)
        self.assertIn("pre_fight_snapshots_edge_published_needs_an_id", err)

    def test_an_edge_cannot_be_published_after_the_snapshot_that_froze_it(self):
        for name in self.ORDER:
            self.psql_file(os.path.join(CLV, name), db=self.db)
        err = self.psql("""
          insert into public.pre_fight_snapshots (fight_id, snapshot_at,
            edge_model_edge_id, edge_published_at, edge_side,
            edge_bet_fighter_id, edge_odds_at_publish)
          values (4, '2026-09-09T12:00:00+00', 7, '2026-09-10T12:00:00+00',
                  'a', 101, 150)
        """, db=self.db, expect_error=True)
        self.assertIn("pre_fight_snapshots_edge_published_before_snapshot", err)

    def test_the_append_only_triggers_on_snapshots_are_untouched(self):
        """The migration is additive on the pre-fight record. ADD COLUMN is DDL
        and the triggers do not block it — but they must still be there
        afterwards, doing their job."""
        for name in self.ORDER:
            self.psql_file(os.path.join(CLV, name), db=self.db)
        self.psql("insert into public.pre_fight_snapshots (fight_id, snapshot_at)"
                  " values (5, '2026-09-09T12:00:00+00')", db=self.db)
        # The stub table has no triggers of its own — production does — so this
        # asserts the migration added none and removed none.
        self.assertEqual(
            self.psql("select count(*) from pg_trigger t "
                      "join pg_class c on c.oid = t.tgrelid "
                      "where c.relname = 'pre_fight_snapshots' "
                      "and not t.tgisinternal", db=self.db), "0",
            "the migration must not create, alter or drop a trigger on the "
            "pre-fight record")

    def test_a_scored_row_cannot_omit_the_cutoff_it_was_scored_against(self):
        """Amendment 6 (e), enforced by the database rather than only by the
        writer. The completeness constraint is NOT VALID, so it binds new rows
        and leaves history alone — this checks that it binds."""
        for name in self.ORDER:
            self.psql_file(os.path.join(CLV, name), db=self.db)
        complete = """
          insert into public.model_edges (fight_id, side, odds_at_publish,
            clv_return, closing_fair_probability, closing_book_count,
            clv_protocol_version, clv_scored_at, clv_source_quote_ids,
            clv_closing_consensus, clv_consensus_sha256, clv_close_basis,
            clv_lead_time_minutes, clv_lead_time_is_lower_bound,
            clv_proxy_quoted_at, clv_cutoff_at, clv_publish_quote_id)
          values (1, 'a', 150, 0.02, 0.51, 3, 'CLV-001@1.0.9', now(),
                  '{1,2}', '{}'::jsonb, 'abc', 'scheduled_first_bout',
                  10, false, '2026-09-12T21:50:00+00',
                  '2026-09-12T22:00:00+00', 9001)
        """
        self.psql(complete, db=self.db)
        err = self.psql(complete.replace("'2026-09-12T22:00:00+00'", "null"),
                        db=self.db, expect_error=True)
        self.assertIn("model_edges_clv_scored_is_complete", err)
        err = self.psql(complete.replace(", 9001)", ", null)"),
                        db=self.db, expect_error=True)
        self.assertIn("model_edges_clv_scored_is_complete", err)

    def test_the_stored_cutoff_must_agree_with_the_stored_lead_time(self):
        for name in self.ORDER:
            self.psql_file(os.path.join(CLV, name), db=self.db)
        err = self.psql("""
          insert into public.model_edges (fight_id, side, odds_at_publish,
            clv_return, closing_fair_probability, closing_book_count,
            clv_protocol_version, clv_scored_at, clv_source_quote_ids,
            clv_closing_consensus, clv_consensus_sha256, clv_close_basis,
            clv_lead_time_minutes, clv_lead_time_is_lower_bound,
            clv_proxy_quoted_at, clv_cutoff_at, clv_publish_quote_id)
          values (1, 'a', 150, 0.02, 0.51, 3, 'CLV-001@1.0.9', now(),
                  '{1,2}', '{}'::jsonb, 'abc', 'scheduled_first_bout',
                  999, false, '2026-09-12T21:50:00+00',
                  '2026-09-12T22:00:00+00', 9001)
        """, db=self.db, expect_error=True)
        self.assertIn("model_edges_clv_cutoff_matches_lead_time", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
