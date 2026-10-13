"""The v_odds_books_sportsbooks write hole, reproduced and closed on a throwaway Postgres.

    python -m unittest tests/test_security_odds_books_view.py -v

Production (2026-10-13): the view is SECURITY DEFINER, owned by a role that
bypasses RLS, auto-updatable, and anon held INSERT/UPDATE/DELETE on it.
odds_books is admin-only (RLS on, no browser policy), and fight_odds.book_id
is ON DELETE CASCADE. This test builds exactly that shape, shows that anon can
delete a sportsbook and its whole odds history through the view, then applies
security_odds_books_view_readonly.sql and shows that anon can still read the
view but no longer write through it.

No production database is touched. SKIPS where initdb is unavailable.
"""
from __future__ import annotations

import os
import unittest

from test_sql_behaviour import PostgresCase, REPO_ROOT

FIX = os.path.join(REPO_ROOT, "security_odds_books_view_readonly.sql")

SHAPE = """
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated; end if;
end $$;
create table public.odds_books (id bigint primary key, name text, short_code text);
alter table public.odds_books enable row level security;          -- admin-only: no browser policy
create table public.fight_odds (
  id bigint generated always as identity primary key,
  fight_id bigint not null,
  book_id bigint not null references public.odds_books(id) on delete cascade
);
alter table public.fight_odds enable row level security;
-- The production definition (pg_get_viewdef, 2026-10-13), owned by the bootstrap superuser.
create view public.v_odds_books_sportsbooks as
 SELECT id, name, short_code FROM odds_books
  WHERE name !~~* '%consensus%'::text AND (lower(name) <> ALL (ARRAY['polymarket'::text, 'kalshi'::text]));
-- Production grants: Supabase defaults give the browser roles everything.
grant all on public.v_odds_books_sportsbooks to anon, authenticated;
insert into public.odds_books values (1, 'FanDuel', 'fd'), (2, 'DraftKings', 'dk');
insert into public.fight_odds (fight_id, book_id) values (10, 1), (11, 1), (12, 2);
"""


class TestOddsBooksViewHole(PostgresCase):

    def setUp(self):
        self.db = "odds_books_hole"
        self.psql(f'drop database if exists "{self.db}"')
        self.psql(f'create database "{self.db}"')
        self.psql(SHAPE, db=self.db)

    def one(self, sql, **kw):
        return self.psql(sql, db=self.db, **kw).strip().splitlines()[-1].strip()

    def test_before_the_fix_anon_can_delete_a_book_and_its_odds_history(self):
        self.psql("set role anon; delete from public.v_odds_books_sportsbooks where id = 1;", db=self.db)
        self.assertEqual(self.one("select count(*) from public.odds_books;"), "1", "the delete did not reach odds_books")
        self.assertEqual(self.one("select count(*) from public.fight_odds;"), "1",
                         "the cascade did not erase the deleted book's odds history")

    def test_before_the_fix_anon_can_rename_a_book(self):
        self.psql("set role anon; update public.v_odds_books_sportsbooks set name = 'pwned' where id = 2;",
                  db=self.db)
        self.assertEqual(self.one("select name from public.odds_books where id = 2;"), "pwned")

    def test_after_the_fix_anon_can_read_but_not_write(self):
        self.psql_file(FIX, db=self.db)
        self.assertEqual(self.one("set role anon; select count(*) from public.v_odds_books_sportsbooks;"), "2")
        for stmt in ("delete from public.v_odds_books_sportsbooks where id = 1",
                     "update public.v_odds_books_sportsbooks set name = 'x' where id = 2",
                     "insert into public.v_odds_books_sportsbooks values (3, 'Fake', 'fk')"):
            for role in ("anon", "authenticated"):
                out = self.psql(f"set role {role}; {stmt};", db=self.db, expect_error=True)
                self.assertIn("permission denied", out, f"{role} could still run: {stmt}")
        self.assertEqual(self.one("select count(*) from public.odds_books;"), "2")
        self.assertEqual(self.one("select count(*) from public.fight_odds;"), "3")

    def test_the_fix_is_rerunnable(self):
        self.psql_file(FIX, db=self.db)
        self.psql_file(FIX, db=self.db)
        self.assertEqual(self.one("set role anon; select count(*) from public.v_odds_books_sportsbooks;"), "2")


if __name__ == "__main__":
    unittest.main()
