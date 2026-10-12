"""The PRED-001 prospective lock ledger, tested against a real Postgres.

    python -m pytest tests/test_win_forecast_locks.py -v

`proposed_2026-10-12_win_forecast_locks.sql` is NOT applied to production;
applying it is L3 (T-084). These tests are the evidence offered for that
approval: they run the migration against a throwaway cluster (the same harness
as test_sql_behaviour.py — initdb into a temp dir, unix socket only, torn down
afterwards, SUPABASE_DB_URL never read) and try to break every guard the file's
header claims. They skip where initdb is absent; the static checks at the
bottom run everywhere.
"""
from __future__ import annotations

import os
import re
import unittest

from test_sql_behaviour import PostgresCase

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(REPO_ROOT, "proposed_2026-10-12_win_forecast_locks.sql")

ART = "a" * 64
PREREG = "b" * 64
FEAT = "c" * 64

# Only what the migration reads. service_role is BYPASSRLS on Supabase, so it is
# here too; without that the RLS-on, no-policy tables would read as empty to it.
STUBS = """
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then create role service_role; end if;
end $$;
alter role service_role bypassrls;
create table public.events (id bigint primary key, event_date date);
create table public.fights (
  id bigint primary key, event_id bigint not null references public.events(id),
  fighter_a_id bigint, fighter_b_id bigint, winner_id bigint, method text, bell_at timestamptz);
create table public.odds_books (id bigint primary key, name text, short_code text);
create view public.v_odds_books_sportsbooks as
  select id, name, short_code from public.odds_books
  where name !~~* '%consensus%' and lower(name) <> all (array['polymarket','kalshi']);
create table public.fight_odds (
  id bigint primary key, fight_id bigint not null, fighter_id bigint not null,
  book_id bigint not null, american_odds integer, implied_prob numeric,
  captured_at timestamptz not null, is_live boolean);
create table public.fight_start_estimates (
  fight_id bigint, source text, start_at timestamptz, observed_at timestamptz default now());
create view public.v_fight_start_best as
  select f.id as fight_id, f.event_id, e.event_date,
    coalesce(f.bell_at, pc.start_at, (e.event_date::timestamp + time '18:00') at time zone 'UTC') as start_at,
    case when f.bell_at is not null then 'bell_at' when pc.start_at is not null then 'provider_commence'
         when e.event_date is not null then 'event_date_fallback' end as start_basis
  from public.fights f left join public.events e on e.id = f.event_id
  left join lateral (select s.start_at from public.fight_start_estimates s
    where s.fight_id = f.id and s.source = 'odds_api_commence' order by s.observed_at desc limit 1) pc on true;
grant select on public.events, public.fights, public.odds_books, public.v_odds_books_sportsbooks,
  public.fight_odds, public.fight_start_estimates, public.v_fight_start_best to service_role;

-- fixtures: event 1 is in ten days; event 2 started yesterday
insert into public.events values (1, current_date + 10), (2, current_date - 1);
insert into public.fights values
  (100, 1, 11, 12, null, null, null),   -- upcoming
  (101, 1, 13, 14, null, null, null),   -- upcoming, gets a result below
  (200, 2, 21, 22, null, null, null);   -- started yesterday, no result yet
insert into public.odds_books values (1, 'DraftKings', 'dk'), (2, 'FanDuel', 'fd'),
  (3, 'Consensus', 'cons'), (4, 'Polymarket', 'poly');
insert into public.fight_odds values
  (1, 100, 11, 1, -150, 0.60, now() - interval '1 hour', false),
  (2, 100, 12, 1,  130, 0.43, now() - interval '1 hour', false),
  (3, 100, 11, 2, -145, 0.59, now() - interval '30 minutes', false),
  (4, 100, 12, 2,  125, 0.44, now() - interval '30 minutes', false),
  (5, 101, 13, 1, -200, 0.67, now() - interval '1 hour', false),     -- another fight
  (6, 100, 11, 3, -150, 0.60, now() - interval '1 hour', false),     -- consensus row
  (7, 100, 11, 4, -150, 0.60, now() - interval '1 hour', false),     -- prediction market
  (8, 100, 11, 1, -150, 0.60, now() - interval '3 days', false),     -- stale
  (9, 100, 11, 1, -150, 0.60, now() - interval '1 hour', true),      -- in-play
  (10, 100, 11, 1, -150, 0.60, now() + interval '1 hour', false),    -- from the future
  (11, 200, 21, 1, -150, 0.60, now() - interval '2 days', false),
  (12, 200, 22, 1,  130, 0.43, now() - interval '2 days', false);
"""

REGISTER = (f"insert into public.win_forecast_experiments (experiment_id, artifact_sha256, "
            f"preregistration_sha256, protocol_version, code_commit, frozen_at, benchmark) values "
            f"('PRED-002', '{ART}', '{PREREG}', '1.0.0', 'abc1234', now() - interval '1 day', "
            f"'same_timestamp_consensus');")


def lock_sql(**over) -> str:
    v = dict(experiment_id="'PRED-002'", artifact_sha256=f"'{ART}'", fight_id="100",
             event_id="1", fighter_a_id="11", fighter_b_id="12", p_a="0.62",
             p_market_a="0.58", market_quote_ids="array[1,2,3,4]::bigint[]",
             market_book_count="2", market_latest_quote_at="(select max(captured_at) from public.fight_odds where id in (1,2,3,4))",
             features="'{}'::jsonb", feature_sha256=f"'{FEAT}'",
             training_cutoff="now() - interval '2 days'", generated_at="now() - interval '5 minutes'")
    v.update(over)
    cols = ", ".join(v)
    vals = ", ".join(v.values())
    return f"insert into public.win_forecast_locks ({cols}) values ({vals});"


class TestWinForecastLocks(PostgresCase):

    def setUp(self):
        self.db = f"wfl_{self._testMethodName[:40].lower()}"
        self.psql(f'drop database if exists "{self.db}"')
        self.psql(f'create database "{self.db}"')
        self.psql(STUBS, db=self.db)
        self.psql_file(MIGRATION, db=self.db)
        self.psql(REGISTER, db=self.db)

    def ok(self, sql):
        return self.psql(sql, db=self.db)

    def rejected(self, sql, needle):
        err = self.psql(sql, db=self.db, expect_error=True)
        self.assertIn(needle, err)

    # ------------------------------------------------------------- happy path
    def test_a_valid_lock_is_accepted_and_the_clock_is_the_databases(self):
        self.ok(lock_sql(actual_lock_at="'2000-01-01'"))
        age = self.ok("select extract(epoch from now() - actual_lock_at) < 60, "
                      "start_basis_at_lock from public.win_forecast_locks")
        self.assertEqual(age, "t|event_date_fallback")

    def test_the_migration_is_idempotent(self):
        self.ok(lock_sql())
        self.psql_file(MIGRATION, db=self.db)
        self.assertEqual(self.ok("select count(*) from public.win_forecast_locks"), "1")

    # ------------------------------------------------------------- append-only
    def test_update_delete_truncate_are_refused_even_for_the_superuser(self):
        self.ok(lock_sql())
        self.rejected("update public.win_forecast_locks set p_a = 0.9", "append-only")
        self.rejected("delete from public.win_forecast_locks", "append-only")
        self.rejected("truncate public.win_forecast_locks cascade", "append-only")
        self.rejected("update public.win_forecast_experiments set frozen_at = now()", "append-only")
        self.rejected("delete from public.win_forecast_experiments", "append-only")

    def test_one_forecast_per_fight_per_artifact(self):
        self.ok(lock_sql())
        self.rejected(lock_sql(p_a="0.7"), "win_forecast_locks_one_per_artifact")

    # ------------------------------------------------------------- timing
    def test_a_fight_that_has_started_is_refused(self):
        self.rejected(lock_sql(fight_id="200", event_id="2", fighter_a_id="21", fighter_b_id="22",
                               market_quote_ids="array[11,12]::bigint[]",
                               market_latest_quote_at="(select max(captured_at) from public.fight_odds where id in (11,12))"),
                      "lock rejected")

    def test_a_provider_start_in_the_past_wins_over_the_event_date(self):
        self.ok("insert into public.fight_start_estimates values "
                "(100, 'odds_api_commence', now() - interval '1 minute', now())")
        self.rejected(lock_sql(), "starts at")

    def test_a_fight_with_a_result_is_refused(self):
        self.ok("update public.fights set winner_id = 11, method = 'KO/TKO' where id = 100")
        self.rejected(lock_sql(), "already has a result")

    def test_training_or_generation_after_the_lock_is_refused(self):
        self.rejected(lock_sql(training_cutoff="now() + interval '1 hour'"), "training_cutoff")
        self.rejected(lock_sql(generated_at="now() + interval '1 hour'"), "generated_at")

    def test_an_unregistered_or_future_frozen_artifact_is_refused(self):
        self.rejected(lock_sql(artifact_sha256=f"'{'d' * 64}'"), "is not registered")
        self.ok(f"insert into public.win_forecast_experiments (experiment_id, artifact_sha256, "
                f"preregistration_sha256, protocol_version, code_commit, frozen_at, benchmark) values "
                f"('PRED-003', '{ART}', '{PREREG}', '1.0.0', 'abc1234', now() + interval '1 day', "
                f"'same_timestamp_consensus')")
        self.rejected(lock_sql(experiment_id="'PRED-003'"), "frozen at")

    # ------------------------------------------------------------- identity
    def test_corners_must_be_the_fights_corners(self):
        self.rejected(lock_sql(fighter_a_id="12", fighter_b_id="11"), "are not fight")
        self.rejected(lock_sql(event_id="2"), "belongs to event")

    # ------------------------------------------------------------- benchmark provenance
    def test_benchmark_quotes_must_be_real_fresh_sportsbook_pre_lock_quotes(self):
        cases = {
            "array[1,2,999]::bigint[]": "do not exist",
            "array[1,2,5]::bigint[]": "cited quotes",      # another fight
            "array[2,6]::bigint[]": "cited quotes",        # consensus row
            "array[2,7]::bigint[]": "cited quotes",        # prediction market
            "array[2,8]::bigint[]": "cited quotes",        # 3 days old
            "array[2,9]::bigint[]": "cited quotes",        # in-play
            "array[2,10]::bigint[]": "cited quotes",       # captured after the lock
            "array[1,3]::bigint[]": "both corners",        # one corner only
        }
        for ids, needle in cases.items():
            with self.subTest(ids=ids):
                self.rejected(lock_sql(market_quote_ids=ids,
                                       market_latest_quote_at=f"(select max(captured_at) from public.fight_odds where id = any({ids}))"),
                              needle)

    def test_the_latest_quote_instant_must_be_true(self):
        self.rejected(lock_sql(market_latest_quote_at="now() - interval '2 hours'"), "not the latest")

    def test_probabilities_must_be_strictly_inside_zero_one(self):
        self.rejected(lock_sql(p_a="1"), "win_forecast_locks_p_chk")
        self.rejected(lock_sql(p_market_a="0"), "win_forecast_locks_p_chk")

    # ------------------------------------------------------------- grading
    def test_grading_scores_settled_fights_and_voids_a_changed_opponent(self):
        self.ok(lock_sql())
        # fight 100 is won by corner A; the model said 0.62, the market 0.58
        self.ok("update public.fights set winner_id = 11, method = 'Decision' where id = 100")
        row = self.ok("select grade_status, y_a, round(ll_model, 4), round(ll_market, 4) "
                      "from public.v_win_forecast_graded where fight_id = 100")
        self.assertEqual(row, "scored|1|0.4780|0.5447")
        # the opponent is replaced after the lock: the forecast is void, not scored
        self.ok("update public.fights set fighter_b_id = 99 where id = 100")
        row = self.ok("select grade_status, ll_model is null from public.v_win_forecast_graded where fight_id = 100")
        self.assertEqual(row, "void_corners_changed|t")

    # ------------------------------------------------------------- privileges
    def test_anon_and_authenticated_can_neither_read_nor_write(self):
        self.ok(lock_sql())
        for role in ("anon", "authenticated"):
            with self.subTest(role=role):
                for sql in ("select * from public.win_forecast_locks",
                            "select * from public.win_forecast_experiments",
                            "select * from public.v_win_forecast_graded",
                            "truncate public.win_forecast_locks"):
                    self.rejected(f"set role {role}; {sql}", "permission denied")
                self.rejected(f"set role {role}; " + lock_sql(), "permission denied")

    def test_service_role_may_read_and_insert_and_nothing_else(self):
        self.ok("set role service_role; " + lock_sql())
        self.assertEqual(self.ok("set role service_role; select count(*) from public.v_win_forecast_graded")
                         .splitlines()[-1], "1")
        self.rejected("set role service_role; update public.win_forecast_locks set p_a = 0.5", "permission denied")
        self.rejected("set role service_role; delete from public.win_forecast_locks", "permission denied")
        self.rejected("set role service_role; truncate public.win_forecast_locks", "permission denied")
        grants = self.ok("select string_agg(privilege_type, ',' order by privilege_type) "
                         "from information_schema.role_table_grants "
                         "where table_name = 'win_forecast_locks' and grantee = 'service_role'")
        self.assertEqual(grants, "INSERT,SELECT")


class TestWinForecastLocksStatic(unittest.TestCase):
    """Shape checks that run without Postgres."""

    @classmethod
    def setUpClass(cls):
        with open(MIGRATION, encoding="utf-8") as f:
            cls.sql = f.read()

    def test_it_says_it_is_not_applied(self):
        self.assertIn("STATUS: PROPOSED. NOT APPLIED.", self.sql)

    def test_the_lock_instant_cannot_come_from_the_client(self):
        self.assertIn("new.actual_lock_at := clock_timestamp();", self.sql)

    def test_no_security_definer(self):
        self.assertNotRegex(self.sql.lower(), r"security\s+definer")

    def test_both_public_roles_are_revoked_on_every_object(self):
        for obj in ("win_forecast_experiments", "win_forecast_locks", "v_win_forecast_graded"):
            self.assertRegex(self.sql, rf"revoke all on public\.{obj}\s+from public, anon, authenticated")

    def test_nothing_destructive(self):
        code = re.sub(r"--[^\n]*", "", self.sql).lower()
        self.assertNotRegex(code, r"\bdrop\s+(table|view|function|index)\b")
        self.assertNotRegex(code, r"\bdelete\s+from\b")


if __name__ == "__main__":
    unittest.main()
