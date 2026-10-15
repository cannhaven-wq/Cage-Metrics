"""T-092: the per-fight v_fight_market_movement gives the same answers, faster.

    python -m pytest -q tests/test_t092_market_movement_sql.py

Builds the market view chain on a throwaway Postgres with production's
definitions (the old v_fight_market_movement is the rollback file), loads a
synthetic odds history designed to hit every branch, then:

  * applies market_movement_t092.sql — its own assertion block must pass;
  * checks the new output against the old, row by row and column by column;
  * proves the guard bites: a deliberately wrong candidate is refused and the
    old view is left in place;
  * rolls back and checks the old answers come back.

Skips without initdb, like the rest of the SQL suites.
"""
from __future__ import annotations

import os
import random
import re
import tempfile
import unittest

from test_sql_behaviour import PostgresCase, REPO_ROOT

MIGRATION = os.path.join(REPO_ROOT, "market_movement_t092.sql")
ROLLBACK = os.path.join(REPO_ROOT, "market_movement_t092.rollback.sql")

# The views beneath v_fight_market_movement, as production defines them
# (pg_get_viewdef, 2026-10-15). v_fight_locked_forecast is stubbed empty: only
# its 'lock' horizon reads it and v_fight_market_movement uses 'h24' alone.
SCHEMA = """
create table public.odds_books (id bigint primary key, name text not null, short_code text);
create table public.fights (id bigint primary key, event_id bigint);
create table public.fight_odds (
  id bigserial primary key, fight_id bigint not null, book_id bigint not null,
  side char(1) not null, captured_at timestamptz not null, implied_prob numeric,
  american_odds integer, is_live boolean, market_status text, retrieved_at timestamptz);
create index on public.fight_odds (fight_id, book_id, captured_at);
create index on public.fight_odds (fight_id, captured_at);

create view public.v_odds_books_sportsbooks as
 select id, name, short_code from odds_books
  where name !~~* '%consensus%' and lower(name) <> all (array['polymarket','kalshi']);

create view public.v_fight_market_quotes as
 select a.fight_id, a.book_id, a.captured_at as quoted_at,
    (a.implied_prob / (a.implied_prob + b.implied_prob)) as fair_a,
    (b.implied_prob / (a.implied_prob + b.implied_prob)) as fair_b,
    a.american_odds as american_odds_a, b.american_odds as american_odds_b, a.retrieved_at
   from fight_odds a
   join fight_odds b on b.fight_id = a.fight_id and b.book_id = a.book_id
                    and b.captured_at = a.captured_at and b.side = 'B'
   join v_odds_books_sportsbooks sb on sb.id = a.book_id
  where a.side = 'A' and a.captured_at > '2010-01-01 00:00:00+00'
    and a.implied_prob is not null and a.implied_prob > 0
    and b.implied_prob is not null and b.implied_prob > 0
    and a.is_live is not true and b.is_live is not true
    and (a.market_status is null or a.market_status = 'open')
    and (b.market_status is null or b.market_status = 'open');

create view public.v_fight_market_broad_baseline as
 with first_seen as (
   select fight_id, book_id, min(quoted_at) as first_quoted_at
     from v_fight_market_quotes group by fight_id, book_id),
 ranked as (
   select fight_id, book_id, first_quoted_at,
          row_number() over (partition by fight_id order by first_quoted_at, book_id) as book_rank
     from first_seen)
 select fight_id, first_quoted_at as baseline_at, 3 as min_books from ranked where book_rank = 3;

create view public.v_fight_locked_forecast as
 select null::bigint as fight_id, null::timestamptz as locked_at where false;

create view public.v_fight_market_horizon_cohorts as
 with fights_seen as (select distinct fight_id from v_fight_market_quotes),
 h as (
   select fight_id, 'broad_baseline'::text as horizon, baseline_at as as_of from v_fight_market_broad_baseline
   union all select fight_id, 'h24', now() - interval '24 hours' from fights_seen
   union all select fight_id, 'lock', locked_at from v_fight_locked_forecast where locked_at is not null),
 then_cohort as (
   select distinct on (h.fight_id, h.horizon, q.book_id) h.fight_id, h.horizon, h.as_of, q.book_id,
          q.fair_a as then_fair_a, q.quoted_at as then_quoted_at
     from h join v_fight_market_quotes q on q.fight_id = h.fight_id and q.quoted_at <= h.as_of
    order by h.fight_id, h.horizon, q.book_id, q.quoted_at desc),
 now_cohort as (
   select distinct on (fight_id, book_id) fight_id, book_id, fair_a as now_fair_a, quoted_at as now_quoted_at
     from v_fight_market_quotes order by fight_id, book_id, quoted_at desc)
 select t.fight_id, t.horizon, t.as_of, t.book_id, t.then_fair_a, t.then_quoted_at, n.now_fair_a, n.now_quoted_at
   from then_cohort t join now_cohort n on n.fight_id = t.fight_id and n.book_id = t.book_id;

create view public.v_fight_market_horizons as
 with agg as (
   select fight_id, horizon, min(as_of) as as_of, count(*)::integer as matched_book_count,
     (percentile_cont(0.5::double precision) within group (order by then_fair_a::double precision))::numeric as then_p_a,
     (percentile_cont(0.5::double precision) within group (order by now_fair_a::double precision))::numeric as now_p_a,
     max(then_quoted_at) as then_quoted_at, max(now_quoted_at) as now_quoted_at
   from v_fight_market_horizon_cohorts group by fight_id, horizon)
 select fight_id, horizon, as_of, 3 as min_books, matched_book_count, then_quoted_at, now_quoted_at,
   case when matched_book_count >= 3 then then_p_a end as then_p_a,
   case when matched_book_count >= 3 then now_p_a end as now_p_a,
   case when matched_book_count >= 3 then (now_p_a - then_p_a) * 100::numeric end as movement_pts_a,
   case when matched_book_count >= 3 then 'ok' else 'insufficient_matched_books' end as movement_status,
   'matched_cohort_median_vigfree_v1'::text as movement_method
 from agg a;

do $r$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated; end if;
end $r$;
"""

BOOKS = [(1, "DraftKings"), (2, "FanDuel"), (3, "BetMGM"), (4, "Bovada"), (5, "BetUS"),
         (6, "BetOnline.ag"), (7, "Caesars"), (8, "Consensus (CFL)"), (9, "Polymarket")]


def american_to_prob(o: int) -> float:
    return 100 / (o + 100) if o > 0 else -o / (-o + 100)


def synthetic_odds(seed: int = 92) -> str:
    """Deterministic odds history. Prices sit on a coarse grid so books tie
    often (the tie-break case); fights get 1..9 books, so some never reach a
    broad capture; captures span ten days, so the 24 h horizon is exercised;
    some rows are live or closed and must be ignored; one fight id has odds but
    no fights row and must not appear."""
    rnd = random.Random(seed)
    rows = []
    fights = []
    for fid in range(1, 41):
        event = 100 + fid // 8
        fights.append(f"({fid},{event})")
        if fid % 13 == 0:
            continue  # a booked fight with no odds at all
        books = rnd.sample([b for b, _ in BOOKS], rnd.randint(1, len(BOOKS)))
        for b in books:
            first = rnd.uniform(0.5, 240)  # hours ago
            n = rnd.randint(1, 6)
            for k in range(n):
                hours_ago = first * (1 - k / max(n, 1))
                fav = rnd.choice([-300, -250, -200, -150, -120, -110])
                dog = rnd.choice([110, 120, 150, 180, 220, 250])
                if rnd.random() < 0.5:
                    fav, dog = dog, fav
                live = "true" if rnd.random() < 0.05 else "null"
                status = "'closed'" if rnd.random() < 0.05 else ("'open'" if rnd.random() < 0.5 else "null")
                ts = f"now() - interval '{hours_ago:.4f} hours'"
                for side, odds in (("A", fav), ("B", dog)):
                    rows.append(f"({fid},{b},'{side}',{ts},{american_to_prob(odds):.6f},{odds},{live},{status})")
    # odds for a fight that is not in `fights`
    for b in (1, 2, 3):
        for side, odds in (("A", -150), ("B", 130)):
            rows.append(f"(999,{b},'{side}',now() - interval '5 hours',{american_to_prob(odds):.6f},{odds},null,null)")
    return ("insert into public.odds_books (id, name) values "
            + ",".join(f"({i},'{n}')" for i, n in BOOKS) + ";\n"
            + "insert into public.fights (id, event_id) values " + ",".join(fights) + ";\n"
            + "insert into public.fight_odds (fight_id, book_id, side, captured_at, implied_prob, "
              "american_odds, is_live, market_status) values " + ",\n".join(rows) + ";")


# Every column except the two book names, which may differ only between books
# tied on the best price (checked separately).
CMP = """
select count(*) from (
  (select fight_id, to_jsonb(x) - 'best_book_a' - 'best_book_b' from {a} x
   except select fight_id, to_jsonb(y) - 'best_book_a' - 'best_book_b' from {b} y)
  union all
  (select fight_id, to_jsonb(y) - 'best_book_a' - 'best_book_b' from {b} y
   except select fight_id, to_jsonb(x) - 'best_book_a' - 'best_book_b' from {a} x)) d
"""


class TestT092MarketMovement(PostgresCase):

    def setUp(self):
        self.db = "t092"
        self.psql(f'drop database if exists "{self.db}"')
        self.psql(f'create database "{self.db}"')
        self.psql(SCHEMA, db=self.db)
        self.psql(synthetic_odds(), db=self.db)
        self.psql_file(ROLLBACK, db=self.db)  # the OLD view, as production has it
        self.psql("create table old_out as select * from public.v_fight_market_movement", db=self.db)

    def q(self, sql):
        return self.psql(sql, db=self.db).splitlines()[-1].strip()

    def view_is_new(self):
        return "LATERAL" in self.psql(
            "select pg_get_viewdef('public.v_fight_market_movement'::regclass)", db=self.db).upper()

    def test_helper_tells_old_from_new(self):
        self.assertFalse(self.view_is_new())
        self.psql_file(MIGRATION, db=self.db)
        self.assertTrue(self.view_is_new())

    def test_fixture_covers_every_branch(self):
        self.assertGreater(int(self.q("select count(*) from old_out where movement_status = 'ok'")), 0)
        self.assertGreater(int(self.q("select count(*) from old_out where movement_status = 'no_broad_capture'")), 0)
        self.assertGreater(int(self.q("select count(*) from old_out where movement_status_24h = 'ok'")), 0)
        self.assertGreater(int(self.q("select count(*) from old_out where movement_status_24h <> 'ok'")), 0)
        self.assertEqual(self.q("select count(*) from old_out where fight_id = 999"), "0")

    def test_migration_applies_and_answers_are_identical(self):
        self.psql_file(MIGRATION, db=self.db)
        self.assertTrue(self.view_is_new(), "the migration did not replace the view")
        self.assertEqual(self.q("select count(*) from old_out"),
                         self.q("select count(*) from public.v_fight_market_movement"))
        self.assertEqual(self.q(CMP.format(a="old_out", b="public.v_fight_market_movement")), "0")
        # Book names: any difference must be between books posting the same best price.
        self.assertEqual(self.q("""
          with latest as (select distinct on (fight_id, book_id) fight_id, book_id, american_odds_a, american_odds_b
                            from public.v_fight_market_quotes order by fight_id, book_id, quoted_at desc),
          named as (select l.*, b.name from latest l join public.odds_books b on b.id = l.book_id)
          select count(*) from old_out o join public.v_fight_market_movement n using (fight_id)
           where (o.best_book_a is distinct from n.best_book_a and not exists (
                   select 1 from named x, named y where x.fight_id = o.fight_id and y.fight_id = o.fight_id
                      and x.name = o.best_book_a and y.name = n.best_book_a
                      and x.american_odds_a = o.best_american_a and y.american_odds_a = n.best_american_a))
              or (o.best_book_b is distinct from n.best_book_b and not exists (
                   select 1 from named x, named y where x.fight_id = o.fight_id and y.fight_id = o.fight_id
                      and x.name = o.best_book_b and y.name = n.best_book_b
                      and x.american_odds_b = o.best_american_b and y.american_odds_b = n.best_american_b))"""), "0")
        # Columns: same names, types and order, so dependents and grants survive.
        self.assertEqual(
            self.q("select string_agg(a.attname||':'||format_type(a.atttypid,a.atttypmod), ',' order by a.attnum) "
                   "from pg_attribute a where a.attrelid = 'old_out'::regclass and a.attnum > 0"),
            self.q("select string_agg(a.attname||':'||format_type(a.atttypid,a.atttypmod), ',' order by a.attnum) "
                   "from pg_attribute a where a.attrelid = 'public.v_fight_market_movement'::regclass and a.attnum > 0"))
        self.assertEqual(self.q("select has_table_privilege('anon','public.v_fight_market_movement','SELECT')"), "t")

    def test_a_filtered_read_matches_the_same_rows(self):
        self.psql_file(MIGRATION, db=self.db)
        for event in (100, 101, 102, 104):
            self.assertEqual(self.q(CMP.format(
                a=f"(select * from old_out where event_id = {event})",
                b=f"(select * from public.v_fight_market_movement where event_id = {event})")), "0")
        self.assertEqual(self.q(CMP.format(
            a="(select * from old_out where fight_id = 7)",
            b="(select * from public.v_fight_market_movement where fight_id = 7)")), "0")

    def test_the_guard_refuses_a_wrong_candidate_and_changes_nothing(self):
        sql = open(MIGRATION).read()
        broken = sql.replace("OFFSET 2 LIMIT 1", "OFFSET 1 LIMIT 1")  # second book instead of third
        self.assertNotEqual(sql, broken)
        with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, dir=self.tmp) as f:
            f.write(broken)
        os.chmod(f.name, 0o644)
        argv = [os.path.join(self.bin_dir, "psql"), "-h", self.tmp, "-p", "55432", "-U", "pg",
                "-d", self.db, "-v", "ON_ERROR_STOP=1", "-f", f.name]
        import subprocess
        out = subprocess.run(self._as(self.runas, argv), capture_output=True, text=True, timeout=120)
        self.assertNotEqual(out.returncode, 0, "a wrong candidate must be refused")
        self.assertIn("T-092 aborted", out.stderr)
        self.assertFalse(self.view_is_new(), "a refused candidate must leave the old view in place")

    def test_rollback_restores_the_old_answers(self):
        self.psql_file(MIGRATION, db=self.db)
        self.psql_file(ROLLBACK, db=self.db)
        self.assertFalse(self.view_is_new())
        self.assertEqual(self.q(CMP.format(a="old_out", b="public.v_fight_market_movement")), "0")


if __name__ == "__main__":
    unittest.main()
