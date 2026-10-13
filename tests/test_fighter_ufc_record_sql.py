"""v_fighter_ufc_record (T-084) against a real, throwaway Postgres.

    python -m unittest tests/test_fighter_ufc_record_sql.py -v

What it proves, without touching any production database:

  * ACCURACY. The record is counted from completed, active bookings only. A
    retired booking (D-024) never counts, even with a result written to it, and
    neither does tonight's card, a future card or a blank method. W / L / draw /
    no contest are told apart.
  * THE SAME RULE AS FIGHT LAB. The fixture is also fed to
    fight-lab.js::ufcRecord through Node, and every fighter's record must agree.
    Fight Lab counts on the client while this view counts in SQL, so they are
    two implementations that must not drift.
  * PERMISSIONS. anon and authenticated may SELECT and nothing else (no
    INSERT / UPDATE / DELETE / TRUNCATE). The view is security_invoker.
  * RE-RUNNABLE. Applying the file twice changes nothing.

Reuses the throwaway-cluster harness from tests/test_sql_behaviour.py. It SKIPS
where initdb is unavailable.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest

from test_sql_behaviour import PostgresCase, REPO_ROOT

VIEW_SQL = os.path.join(REPO_ROOT, "fighter_ufc_record_view.sql")
ROLLBACK_SQL = os.path.join(REPO_ROOT, "fighter_ufc_record_view.rollback.sql")

SCHEMA = """
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated; end if;
end $$;
create table public.events (
  id bigint primary key, name text, event_date date, is_upcoming boolean
);
create table public.fights (
  id bigint primary key, event_id bigint not null,
  fighter_a_id bigint, fighter_b_id bigint, winner_id bigint,
  method text, is_active boolean
);
-- Production: both tables are public-read for both roles.
grant select on public.events, public.fights to anon, authenticated;
"""

# Fixture. Dates are relative to the database's CURRENT_DATE, so the test does
# not rot. Fighter 1 is the subject; 2 is the Sutherland regression shape.
EVENTS = [
    (1, "Past A", -400, False), (2, "Past B", -300, False), (3, "Past C", -200, False),
    (4, "Tonight", 0, False), (5, "Next week", 7, True),
    (6, "Flagged upcoming but past", -30, True), (7, "Past D", -100, False),
]
FIGHTS = [
    # id, event, a, b, winner, method, is_active
    (101, 1, 1, 51, 1, "KO/TKO", None),                    # win, NULL is_active = active
    (102, 2, 52, 1, 52, "Submission", True),               # loss
    (103, 3, 1, 53, None, "Decision - Split", True),       # draw
    (104, 3, 1, 54, None, "Overturned", True),             # no contest
    (105, 3, 1, 55, 1, "Decision - Unanimous", False),     # RETIRED, result written: must not count
    (106, 4, 1, 56, None, None, True),                     # tonight, no result
    (107, 5, 1, 57, None, None, True),                     # booked
    (108, 6, 1, 58, 1, "KO/TKO", True),                    # event still flagged upcoming
    (109, 7, 1, 59, 1, "   ", True),                       # blank method
    (110, 4, 1, 60, 1, "KO/TKO", True),                    # result already on TODAY's card: not yet history
    # Fighter 2: the shape that read 0-2 in fighters.ufc_* while fights held 1-3.
    (201, 1, 275, 2, 275, "Submission", True),
    (202, 2, 2, 3673, 3673, "KO/TKO", True),
    (203, 3, 4548, 2, 2, "Decision - Unanimous", True),
    (204, 7, 2, 428, 428, "Submission", True),
]


class TestFighterUfcRecord(PostgresCase):

    def setUp(self):
        self.db = "ufc_record"
        self.psql(f'drop database if exists "{self.db}"')
        self.psql(f'create database "{self.db}"')
        self.psql(SCHEMA, db=self.db)
        ev = ",".join(f"({i}, '{n}', current_date + {d}, {str(u).lower()})" for i, n, d, u in EVENTS)
        def lit(v):
            if v is None:
                return "null"
            if isinstance(v, bool):
                return str(v).lower()
            if isinstance(v, str):
                return "'" + v.replace("'", "''") + "'"
            return str(v)
        fi = ",".join("(" + ",".join(lit(v) for v in row) + ")" for row in FIGHTS)
        self.psql(f"insert into public.events values {ev}; insert into public.fights values {fi};", db=self.db)
        self.psql_file(VIEW_SQL, db=self.db)

    def record(self, fighter_id, role="anon"):
        out = self.psql(
            f"set role {role}; select coalesce((select ufc_wins||','||ufc_losses||','||ufc_draws||','||"
            f"ufc_no_contests||','||ufc_fights from public.v_fighter_ufc_record where fighter_id = {fighter_id}), 'none');",
            db=self.db)
        return out.strip().splitlines()[-1].strip()

    # ---------------------------------------------------------------- accuracy
    def test_counts_only_completed_active_bookings(self):
        # 101 W, 102 L, 103 D, 104 NC. Excluded: 105 retired, 106/110 today,
        # 107 future, 108 flagged upcoming, 109 blank method.
        self.assertEqual(self.record(1), "1,1,1,1,4")

    def test_a_retired_booking_with_a_result_never_counts(self):
        self.psql("update public.fights set is_active = true where id = 105", db=self.db)
        self.assertEqual(self.record(1), "2,1,1,1,5", "the fixture's retired win should count once reactivated")
        self.psql("update public.fights set is_active = false where id = 105", db=self.db)
        self.assertEqual(self.record(1), "1,1,1,1,4")

    def test_stale_fighter_totals_cannot_reach_the_record(self):
        # Regression: fighters.ufc_* read 0-2 for this shape; the fights are 1-3.
        self.assertEqual(self.record(2), "1,3,0,0,4")

    def test_a_fighter_with_no_completed_fight_has_no_row(self):
        self.assertEqual(self.record(57), "none")      # only a booked fight
        self.assertEqual(self.record(999), "none")

    def test_last_fight_date_is_the_latest_completed_card(self):
        out = self.psql("select last_ufc_fight_date = current_date - 100 from public.v_fighter_ufc_record "
                        "where fighter_id = 2;", db=self.db)
        self.assertIn("t", out.split())

    # ---------------------------------------------------- same rule as Fight Lab
    def test_agrees_with_fight_lab_for_every_fighter(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not available")
        rows = self.psql(
            "select json_agg(json_build_object('fighter_id', fighter_id, 'w', ufc_wins, 'l', ufc_losses, "
            "'d', ufc_draws, 'nc', ufc_no_contests)) from public.v_fighter_ufc_record;", db=self.db)
        sql_rows = {r["fighter_id"]: r for r in json.loads(rows.strip().splitlines()[-1])}
        today = self.psql("select current_date;", db=self.db).strip().splitlines()[-1].strip()
        ev = [{"id": i, "name": n, "event_date": self.psql(f"select current_date + {d};", db=self.db)
               .strip().splitlines()[-1].strip(), "is_upcoming": u} for i, n, d, u in EVENTS]
        cols = ["id", "event_id", "fighter_a_id", "fighter_b_id", "winner_id", "method", "is_active"]
        fights = [dict(zip(cols, r)) for r in FIGHTS]
        ids = sorted({f["fighter_a_id"] for f in fights} | {f["fighter_b_id"] for f in fights})
        script = (
            "const FL=require(%s);const d=JSON.parse(require('fs').readFileSync(0,'utf8'));"
            "const out={};for(const id of d.ids){const r=FL.ufcRecord(d.fights,d.events,id,d.today);"
            "if(r.total)out[id]={w:r.w,l:r.l,d:r.d,nc:r.nc};}console.log(JSON.stringify(out));"
        ) % json.dumps(os.path.join(REPO_ROOT, "fight-lab.js"))
        res = subprocess.run([node, "-e", script], input=json.dumps(
            {"ids": ids, "fights": fights, "events": ev, "today": today}), capture_output=True, text=True, check=True)
        js_rows = {int(k): v for k, v in json.loads(res.stdout).items()}
        self.assertEqual(set(js_rows), set(sql_rows), "the two rules count different fighters")
        for fid, js in js_rows.items():
            s = sql_rows[fid]
            self.assertEqual((js["w"], js["l"], js["d"], js["nc"]), (s["w"], s["l"], s["d"], s["nc"]),
                             f"fighter {fid}: Fight Lab and the view disagree")

    # ------------------------------------------------------------- permissions
    def test_both_browser_roles_can_read_and_nothing_else(self):
        for role in ("anon", "authenticated"):
            for priv, want in (("SELECT", "t"), ("INSERT", "f"), ("UPDATE", "f"),
                               ("DELETE", "f"), ("TRUNCATE", "f")):
                out = self.psql(f"select has_table_privilege('{role}', 'public.v_fighter_ufc_record', '{priv}');",
                                db=self.db)
                self.assertEqual(out.strip().splitlines()[-1].strip(), want, f"{role} {priv}")

    def test_the_view_runs_with_the_callers_rights(self):
        out = self.psql("select reloptions::text from pg_class where relname = 'v_fighter_ufc_record';", db=self.db)
        self.assertIn("security_invoker=on", out)

    def test_a_role_without_access_to_fights_cannot_read_through_it(self):
        self.psql("revoke select on public.fights from anon;", db=self.db)
        out = self.psql("set role anon; select count(*) from public.v_fighter_ufc_record;",
                        db=self.db, expect_error=True)
        self.assertIn("permission denied", out)

    # ---------------------------------------------------------------- rollback
    def test_rollback_removes_only_the_view_and_can_be_reapplied(self):
        counts = lambda: self.psql("select (select count(*) from public.fights) || ',' || "
                                   "(select count(*) from public.events);", db=self.db).strip().splitlines()[-1].strip()
        before = counts()
        self.psql_file(ROLLBACK_SQL, db=self.db)
        gone = self.psql("select to_regclass('public.v_fighter_ufc_record') is null;", db=self.db)
        self.assertEqual(gone.strip().splitlines()[-1].strip(), "t", "the rollback left the view behind")
        self.assertEqual(counts(), before, "the rollback touched fights or events")
        self.psql_file(ROLLBACK_SQL, db=self.db)          # re-runnable
        self.psql_file(VIEW_SQL, db=self.db)
        self.assertEqual(self.record(1), "1,1,1,1,4")

    # ------------------------------------------------------------ re-runnable
    def test_applying_the_file_twice_changes_nothing(self):
        before = self.record(1)
        self.psql_file(VIEW_SQL, db=self.db)
        self.assertEqual(self.record(1), before)


if __name__ == "__main__":
    unittest.main()
