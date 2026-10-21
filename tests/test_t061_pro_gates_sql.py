"""The T-061 Pro gates, DRAFTED and run against a throwaway Postgres.

    /tmp/claude-0/v311/bin/python -m pytest -q tests/test_t061_pro_gates_sql.py

`research/commercial/t061_pro_gates.DRAFT.sql` is not applied anywhere and must
not be until the owner approves T-061 (L3). These tests exist so that, on the
day it is, the file has already been shown to:

  * refuse to run unless the session says on purpose that it means to;
  * hide Pro data from a free reader, a lapsed member and a logged-out visitor,
    and show it to a paying member and a beta grantee;
  * leave every free surface exactly as readable as before;
  * let a lapsed member still see and delete what they made;
  * keep the alert allowance in its one documented place.

Real files, real Postgres: `entitlements_migration.sql` supplies the actual
`current_user_is_pro()`, and the watchlist/alerts sections are sliced out of
`alerts_migration.sql` rather than retyped, so the test cannot drift into
testing a copy of itself. The views the draft wraps are stubs: the gate is
the subject here, not the market maths underneath it.

Same throwaway-cluster rules as test_sql_behaviour.py: initdb into a temp dir,
unix socket only, destroyed afterwards, SUPABASE_DB_URL never read. Skips when
no local Postgres exists.
"""
from __future__ import annotations

import os
import re
import tempfile
import unittest

from test_sql_behaviour import PostgresCase, REPO_ROOT

DRAFT = os.path.join(REPO_ROOT, "research", "commercial", "t061_pro_gates.DRAFT.sql")
ENTITLEMENTS = os.path.join(REPO_ROOT, "entitlements_migration.sql")
ALERTS = os.path.join(REPO_ROOT, "alerts_migration.sql")

FREE = "00000000-0000-0000-0000-00000000000f"
PRO = "00000000-0000-0000-0000-0000000000a1"
LAPSED = "00000000-0000-0000-0000-0000000000a2"
BETA = "00000000-0000-0000-0000-0000000000b1"

STUBS = """
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then create role service_role; end if;
end $$;

create schema auth;
create table auth.users (id uuid primary key);
-- Supabase's auth.uid(): the JWT subject, read from a request GUC.
create function auth.uid() returns uuid language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;
grant usage on schema auth to anon, authenticated;
grant execute on function auth.uid() to anon, authenticated;
grant usage on schema public to anon, authenticated;

create table public.profiles (
  id uuid primary key references auth.users(id),
  tier text not null default 'free',
  tier_expires_at timestamptz,
  stripe_customer_id text,
  is_admin boolean not null default false,
  beta_premium boolean not null default true
);
alter table public.profiles enable row level security;

create table public.events (id bigint primary key, event_date date);
create table public.fights (id bigint primary key, event_id bigint references public.events(id));

-- Stand-ins for the views the draft wraps. Same names and grants as
-- market_chart_views.sql / market_movement_views.sql; trivial bodies.
create table public._series (fight_id bigint, at timestamptz, market_p_a numeric);
create view public.v_fight_chart_series as select fight_id, at, market_p_a from public._series;
create view public.v_fight_chart_books as select fight_id, 'BK'::text as book_code, at from public._series;
create view public.v_fight_chart_meta as select distinct fight_id from public._series;
create view public.v_fight_market_movement as select id as fight_id, 1.5::numeric as movement_pts_a from public.fights;
create view public.v_fight_odds_latest_by_book as select fight_id, 'BK'::text as book_code from public._series;
grant select on public.v_fight_chart_series, public.v_fight_chart_books, public.v_fight_chart_meta,
  public.v_fight_market_movement, public.v_fight_odds_latest_by_book to anon, authenticated;
"""

FIXTURES = f"""
insert into auth.users (id) values ('{FREE}'), ('{PRO}'), ('{LAPSED}'), ('{BETA}');
insert into public.profiles (id, tier, tier_expires_at, beta_premium) values
  ('{FREE}',   'free',    null,                       false),
  ('{PRO}',    'premium', now() + interval '20 days', false),
  ('{LAPSED}', 'premium', now() - interval '1 day',   false),
  ('{BETA}',   'free',    null,                       true);
insert into public.events (id, event_date) values
  (1, (now() at time zone 'utc')::date + 3),     -- the next card
  (2, (now() at time zone 'utc')::date - 400),   -- a card from last year
  (3, null);                                     -- a card with no date yet
insert into public.fights (id, event_id) values (10, 1), (20, 2), (30, 3), (11, 1), (12, 1), (13, 1);
insert into public._series values (10, now(), 0.55), (10, now() - interval '1 hour', 0.52), (20, now() - interval '400 days', 0.6);
"""


def _section(src: str, start: str, end: str) -> str:
    a = src.index(start)
    b = src.index(end, a)
    return src[a:b]


class TestT061ProGatesDraft(PostgresCase):

    def setUp(self):
        # Not fresh_db(): its CLV stubs define a different `fights`.
        self.db = "t061_gates"
        self.psql(f'drop database if exists "{self.db}"')
        self.psql(f'create database "{self.db}"')
        self.psql(STUBS, db=self.db)
        self.psql_file(ENTITLEMENTS, db=self.db)
        alerts = open(ALERTS, encoding="utf8").read()
        sliced = _section(alerts, "CREATE OR REPLACE FUNCTION public.alert_quota()",
                          "-- 3. user_alert_prefs")
        with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False,
                                         dir=self.tmp) as fh:
            fh.write(sliced)
            self.alerts_slice = fh.name
        os.chmod(self.alerts_slice, 0o644)
        self.psql_file(self.alerts_slice, db=self.db)
        self.psql(FIXTURES, db=self.db)

    def tearDown(self):
        try:
            os.unlink(self.alerts_slice)
        except OSError:
            pass

    # -- helpers ------------------------------------------------------------
    def apply_draft(self):
        sql = open(DRAFT, encoding="utf8").read()
        with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, dir=self.tmp) as fh:
            fh.write("SET cfl.t061_apply = 'yes';\n" + sql)
            path = fh.name
        os.chmod(path, 0o644)
        try:
            self.psql_file(path, db=self.db)
        finally:
            os.unlink(path)

    def as_user(self, uid: str | None, sql: str, expect_error: bool = False) -> str:
        """Run `sql` as Supabase would for this caller: the browser role, and
        the JWT subject that auth.uid() reads. None means logged out (anon)."""
        role = "authenticated" if uid else "anon"
        wrapped = f"set role {role}; set request.jwt.claim.sub = '{uid or ''}'; {sql}"
        return self.psql(wrapped, db=self.db, expect_error=expect_error)

    def count(self, uid, rel) -> int:
        out = self.as_user(uid, f"select count(*) from public.{rel}")
        return int(out.splitlines()[-1])

    # -- the draft refuses to run by accident ---------------------------------
    def test_the_draft_refuses_without_the_session_flag(self):
        err = self.psql(open(DRAFT, encoding="utf8").read(), db=self.db, expect_error=True)
        self.assertIn("is a draft", err)
        # and nothing was created
        got = self.psql("select to_regclass('public.v_pro_fight_chart_series') is null", db=self.db)
        self.assertEqual(got, "t", "the refusal ran after something had already been created")

    def test_the_draft_applies_twice(self):
        self.apply_draft()
        self.apply_draft()

    # -- the sanity check: before the draft, nothing is gated -----------------
    def test_before_the_draft_everyone_reads_the_chart(self):
        for uid in (None, FREE, PRO):
            self.assertEqual(self.count(uid, "v_fight_chart_series"), 3)

    # -- pro surfaces ---------------------------------------------------------
    def test_chart_history_is_pro_only(self):
        self.apply_draft()
        self.assertEqual(self.count(PRO, "v_pro_fight_chart_series"), 3)
        self.assertEqual(self.count(BETA, "v_pro_fight_chart_series"), 3,
                         "a beta grantee is Pro by current_user_entitlement()")
        for uid, who in ((FREE, "free"), (LAPSED, "lapsed"), (None, "logged out")):
            self.assertEqual(self.count(uid, "v_pro_fight_chart_series"), 0,
                             f"a {who} reader saw the Pro chart series")

    def test_the_ungated_series_is_no_longer_reachable_from_the_browser(self):
        self.apply_draft()
        for uid in (FREE, PRO, None):
            err = self.as_user(uid, "select count(*) from public.v_fight_chart_series",
                               expect_error=True)
            self.assertIn("permission denied", err)
            err = self.as_user(uid, "select count(*) from public.v_fight_chart_books",
                               expect_error=True)
            self.assertIn("permission denied", err)

    def test_book_history_is_pro_only(self):
        self.apply_draft()
        self.assertEqual(self.count(PRO, "v_pro_fight_chart_books"), 3)
        self.assertEqual(self.count(FREE, "v_pro_fight_chart_books"), 0)
        self.assertEqual(self.count(None, "v_pro_fight_chart_books"), 0)

    def test_lookback_shows_free_readers_the_current_window_only(self):
        self.apply_draft()
        free_ids = self.as_user(FREE, "select string_agg(fight_id::text, ',' order by fight_id) "
                                      "from public.v_fight_market_movement_lookback").splitlines()[-1]
        self.assertEqual(free_ids, "10,11,12,13,30",
                         "a free reader must see the next card and an undated card, not last year's")
        pro_ids = self.as_user(PRO, "select string_agg(fight_id::text, ',' order by fight_id) "
                                    "from public.v_fight_market_movement_lookback").splitlines()[-1]
        self.assertEqual(pro_ids, "10,11,12,13,20,30")

    def test_adding_to_a_watchlist_is_pro_and_a_lapsed_member_keeps_their_rows(self):
        # The lapsed member watched a fight while they were paying.
        self.psql(f"insert into public.user_watchlist (user_id, fight_id) values ('{LAPSED}', 10)",
                  db=self.db)
        self.apply_draft()
        self.as_user(PRO, f"insert into public.user_watchlist (user_id, fight_id) values ('{PRO}', 10)")
        err = self.as_user(FREE, f"insert into public.user_watchlist (user_id, fight_id) "
                                 f"values ('{FREE}', 10)", expect_error=True)
        self.assertIn("row-level security", err)
        self.as_user(LAPSED, f"insert into public.user_watchlist (user_id, fight_id) "
                             f"values ('{LAPSED}', 11)", expect_error=True)
        self.assertEqual(self.count(LAPSED, "user_watchlist"), 1,
                         "a lapsed member can no longer see what they made")
        self.as_user(LAPSED, "delete from public.user_watchlist where fight_id = 10")
        self.assertEqual(self.count(LAPSED, "user_watchlist"), 0,
                         "a lapsed member could not delete their own row")

    def test_the_alert_allowance_is_split_in_its_one_place(self):
        self.apply_draft()
        mk = "insert into public.user_alerts (user_id, fight_id, kind, threshold_pts, direction) " \
             "values ('{u}', {f}, 'market_move', 3, 'either')"
        for f in (10, 11, 12):
            self.as_user(FREE, mk.format(u=FREE, f=f))
        err = self.as_user(FREE, mk.format(u=FREE, f=13), expect_error=True)
        self.assertIn("alert quota reached (3", err)
        for f in (10, 11, 12, 13):
            self.as_user(PRO, mk.format(u=PRO, f=f))
        self.assertEqual(self.as_user(PRO, "select public.alert_quota()").splitlines()[-1], "50")

    # -- free surfaces are untouched -----------------------------------------
    def test_free_surfaces_read_exactly_as_before(self):
        before = {rel: [self.count(u, rel) for u in (None, FREE, PRO)]
                  for rel in ("v_fight_market_movement", "v_fight_odds_latest_by_book",
                              "v_fight_chart_meta")}
        self.apply_draft()
        after = {rel: [self.count(u, rel) for u in (None, FREE, PRO)] for rel in before}
        self.assertEqual(before, after)

    def test_every_gate_in_the_draft_calls_current_user_is_pro(self):
        sql = open(DRAFT, encoding="utf8").read()
        body = re.sub(r"--[^\n]*", "", sql)
        for view in ("v_pro_fight_chart_series", "v_pro_fight_chart_books",
                     "v_fight_market_movement_lookback"):
            m = re.search(r"CREATE OR REPLACE VIEW public\." + view + r" AS(.*?);", body, re.S)
            self.assertIsNotNone(m, view)
            self.assertIn("current_user_is_pro()", m.group(1), view)


if __name__ == "__main__":
    unittest.main()
