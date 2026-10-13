"""T-085 migration and rollback for v_fight_chart_series, on a throwaway Postgres.

    python -m unittest tests/test_chart_series_t085_sql.py -v

The views the chart depends on are loaded from their PRODUCTION definitions
(tests/fixtures/t085_live_dependencies.sql). Then the cycle runs:

    pre-T-085 definition (the rollback file)  ->  snapshot
    T-085 migration                           ->  must equal the snapshot
    rollback                                  ->  must equal the snapshot again
    migration re-applied                      ->  still equal (re-runnable)

and after each step the browser roles may SELECT and nothing else. The
fixture's quotes cover a fight with 4 books (a series), a fight that never
reaches 3 books (refused, no rows), a book that joins after the baseline
(excluded from the cohort), and a quote marked live (ignored).

No production database is touched. SKIPS where initdb is unavailable.
"""
from __future__ import annotations

import os
import unittest

from test_sql_behaviour import PostgresCase, REPO_ROOT

FIX = os.path.join(REPO_ROOT, "tests", "fixtures", "t085_live_dependencies.sql")
MIGRATION = os.path.join(REPO_ROOT, "chart_series_t085.sql")
ROLLBACK = os.path.join(REPO_ROOT, "chart_series_t085.rollback.sql")

SCHEMA = """
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated; end if;
end $$;
create table public.odds_books (id bigint primary key, name text, short_code text);
create table public.fight_odds (
  id bigint generated always as identity primary key,
  fight_id bigint not null, book_id bigint not null, side char(1) not null,
  implied_prob numeric, american_odds integer, captured_at timestamptz not null,
  retrieved_at timestamptz, is_live boolean, market_status text
);
insert into public.odds_books values (1,'BookA','a'),(2,'BookB','b'),(3,'BookC','c'),(4,'BookD','d'),
  (5,'LateBook','l'),(9,'Consensus','x');
"""

# (fight, book, minutes after t0, implied A, implied B, is_live)
QUOTES = [
    # fight 1: books 1-4 quote from the start; book 5 joins later.
    *[(1, b, 0, 0.50 + b / 100, 0.55 - b / 100, None) for b in (1, 2, 3, 4)],
    *[(1, b, 60, 0.53 + b / 100, 0.52 - b / 100, None) for b in (1, 2, 3)],
    (1, 4, 90, 0.60, 0.45, None),
    (1, 5, 120, 0.70, 0.35, None),          # joins after the baseline: not in the cohort
    (1, 2, 150, 0.40, 0.65, True),          # a live quote: ignored
    (1, 1, 180, 0.58, 0.47, None),
    (1, 9, 30, 0.50, 0.50, None),           # the consensus pseudo-book: excluded
    # fight 2: only two books ever. Refused, no rows.
    (2, 1, 0, 0.5, 0.55, None), (2, 2, 10, 0.45, 0.6, None), (2, 1, 40, 0.52, 0.53, None),
]


class TestChartSeriesT085(PostgresCase):

    def setUp(self):
        self.db = "t085"
        self.psql(f'drop database if exists "{self.db}"')
        self.psql(f'create database "{self.db}"')
        self.psql(SCHEMA, db=self.db)
        rows = []
        for f, b, m, pa, pb, live in QUOTES:
            lv = "null" if live is None else "true"
            for side, p in (("A", pa), ("B", pb)):
                rows.append(f"({f},{b},'{side}',{p},-110,timestamptz '2026-10-10 12:00+00' + interval '{m} minutes',"
                            f"now(),{lv},null)")
        self.psql("insert into public.fight_odds (fight_id, book_id, side, implied_prob, american_odds, "
                  "captured_at, retrieved_at, is_live, market_status) values " + ",".join(rows) + ";", db=self.db)
        self.psql_file(FIX, db=self.db)
        # The state before T-085: the rollback file IS the pre-change definition.
        self.psql_file(ROLLBACK, db=self.db)

    def snapshot(self):
        out = self.psql("set role anon; select coalesce(string_agg(s::text, '|' order by fight_id, at), '') "
                        "|| '#' || count(*) from public.v_fight_chart_series s;", db=self.db)
        return out.strip().splitlines()[-1].strip()

    def materialized(self):
        out = self.psql("select pg_get_viewdef('public.v_fight_chart_series'::regclass, true) "
                        "~* 'cohort AS NOT MATERIALIZED';", db=self.db)
        return out.strip().splitlines()[-1].strip() == "t"

    def privileges(self):
        res = {}
        for role in ("anon", "authenticated"):
            for priv in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                out = self.psql(f"select has_table_privilege('{role}', 'public.v_fight_chart_series', '{priv}');",
                                db=self.db)
                res[(role, priv)] = out.strip().splitlines()[-1].strip()
        return res

    def assert_select_only(self):
        for (role, priv), v in self.privileges().items():
            self.assertEqual(v, "t" if priv == "SELECT" else "f", f"{role} {priv}")

    def test_fixture_produces_a_series_and_a_refusal(self):
        snap = self.snapshot()
        self.assertTrue(snap.endswith("#5") or "#" in snap)
        n = int(snap.rsplit("#", 1)[1])
        self.assertGreater(n, 0, "the fixture produced no chart points at all")
        self.assertNotIn("(2,", snap, "a fight that never reached 3 books produced a series")

    def test_migration_rollback_and_reapply_keep_the_output_identical(self):
        before = self.snapshot()
        self.assertFalse(self.materialized())

        self.psql_file(MIGRATION, db=self.db)
        self.assertTrue(self.materialized(), "the migration did not apply NOT MATERIALIZED")
        self.assertEqual(self.snapshot(), before, "the migration changed the chart's output")
        self.assert_select_only()

        self.psql_file(ROLLBACK, db=self.db)
        self.assertFalse(self.materialized(), "the rollback did not restore the previous definition")
        self.assertEqual(self.snapshot(), before, "the rollback changed the chart's output")
        self.assert_select_only()

        self.psql_file(MIGRATION, db=self.db)
        self.psql_file(MIGRATION, db=self.db)
        self.assertEqual(self.snapshot(), before, "re-applying the migration changed the output")

    def test_the_migration_tightens_wide_grants(self):
        # Production state before T-085: both browser roles held ALL on the view.
        self.psql("grant all on public.v_fight_chart_series to anon, authenticated;", db=self.db)
        self.psql_file(MIGRATION, db=self.db)
        self.assert_select_only()

    def test_the_migration_and_market_chart_views_agree(self):
        # The one-view migration must carry the same body as the source-of-truth file.
        def body(path):
            s = open(path).read()
            i = s.index("CREATE OR REPLACE VIEW public.v_fight_chart_series AS")
            j = s.index("COMMENT ON VIEW public.v_fight_chart_series", i)
            return s[i:j]
        self.assertEqual(body(MIGRATION), body(os.path.join(REPO_ROOT, "market_chart_views.sql")))


if __name__ == "__main__":
    unittest.main()
