"""T-093: three duplicate bookings are retired with is_active = false, nothing
else moves, and the guard refuses anything but the audited rows.

    python -m pytest -q tests/test_t093_dead_bookings_sql.py

Skips without initdb, like the rest of the SQL suites.
"""
from __future__ import annotations

import os
import unittest

from test_sql_behaviour import PostgresCase, REPO_ROOT

MIGRATION = os.path.join(REPO_ROOT, "dead_bookings_t093.sql")
ROLLBACK = os.path.join(REPO_ROOT, "dead_bookings_t093.rollback.sql")

SCHEMA = """
create table public.fights (id bigint primary key, event_id bigint, ufc_fight_id text,
  fighter_a_id bigint, fighter_b_id bigint, winner_id bigint, is_active boolean default true);
create table public.fight_rounds (id bigserial primary key,
  fight_id bigint references public.fights(id) on delete cascade, round_number int);
create table public.fight_odds (id bigserial primary key,
  fight_id bigint references public.fights(id) on delete cascade, side char(1));
insert into public.fights values
  (43,   113, 'b007aa53eadea847', 2694, 2938, 2938, true),
  (27872,113, 'c1c9dfd0c0952f18', 2938, 2694, 2938, true),
  (46,   113, 'a3d176f12b1f0b86', 2353, 823, 2353, true),
  (27877,113, '224dce2c0b03e7eb', 2353, 823, 2353, true),
  (8780, 113, 'b6829142f42a75dc', 729, 10976, 10976, true),
  (27879,113, '34d5ec676fb5bce3', 729, 10976, 10976, true),
  (500,  113, 'unrelated', 1, 2, 1, true);
insert into public.fight_rounds (fight_id, round_number) values
  (27872,1),(27872,2),(27872,3),(27877,1),(27879,1),(500,1);
insert into public.fight_odds (fight_id, side)
  select (array[43,46,8780])[1 + g % 3], 'A' from generate_series(1, 10514) g;
"""


class TestT093DeadBookings(PostgresCase):

    def setUp(self):
        self.db = "t093"
        self.psql(f'drop database if exists "{self.db}"')
        self.psql(f'create database "{self.db}"')
        self.psql(SCHEMA, db=self.db)

    def q(self, sql):
        return self.psql(sql, db=self.db).splitlines()[-1].strip()

    def state(self):
        return self.q("select string_agg(id||':'||is_active, ',' order by id) from public.fights")

    def test_retires_exactly_the_three_and_moves_nothing(self):
        self.psql_file(MIGRATION, db=self.db)
        self.assertEqual(self.state(),
                         "43:false,46:false,500:true,8780:false,27872:true,27877:true,27879:true")
        self.assertEqual(self.q("select count(*) from public.fight_odds where fight_id in (43,46,8780)"), "10514")
        self.assertEqual(self.q("select count(*) from public.fight_rounds"), "6")
        self.assertEqual(self.q("select count(*) from public.fights"), "7", "nothing is deleted")

    def test_rerun_is_harmless(self):
        self.psql_file(MIGRATION, db=self.db)
        before = self.state()
        self.psql_file(MIGRATION, db=self.db)
        self.assertEqual(self.state(), before)

    def test_refuses_rows_that_are_not_the_audited_ones(self):
        self.psql("update public.fights set winner_id = 2694 where id = 27872", db=self.db)
        err = self.psql(f"\\i {MIGRATION}", db=self.db, expect_error=True)
        self.assertIn("T-093 aborted", err)
        self.assertEqual(self.q("select count(*) from public.fights where is_active = false"), "0")

    def test_refuses_when_the_canonical_twin_has_no_rounds(self):
        self.psql("delete from public.fight_rounds where fight_id = 27879", db=self.db)
        err = self.psql(f"\\i {MIGRATION}", db=self.db, expect_error=True)
        self.assertIn("T-093 aborted", err)
        self.assertEqual(self.q("select count(*) from public.fights where is_active = false"), "0")

    def test_rollback_restores_the_previous_state(self):
        before = self.state()
        self.psql_file(MIGRATION, db=self.db)
        self.psql_file(ROLLBACK, db=self.db)
        self.assertEqual(self.state(), before)


if __name__ == "__main__":
    unittest.main()
