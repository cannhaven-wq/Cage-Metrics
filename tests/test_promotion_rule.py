"""T-086: every copy of the "is this a UFC card?" rule gives the same answer.

    cd tests && python -m unittest test_promotion_rule -v

The rule lives in five places, in three languages:
  * t086_dwcs_non_ufc.sql             events_ufc_name_only CHECK (Postgres regex)
  * cfl_engine/integrity/checks.py    non_ufc_card_in_events (Postgres regex)
  * research/data-integrity/reconcile_ufc_records.py  UFC_EVENT_RE (Python)
  * build/promotion.js                isUfcEventName (JavaScript)
  * cage-metrics-event-scrapper/promotion.py  (tested in that repository
    against the same NAMES list)

NAMES covers every naming pattern in production's 801 events on 2026-10-13
(numbered cards, Fight Night with and without a colon, on FOX / FX / FUEL TV,
UFC Live, UFC Macao, "UFC - Ultimate Japan", TUF finales, Noche UFC, Ortiz vs
Shamrock 3, UFC Freedom 250, "UFC - Road to UFC 4.6") plus the non-UFC forms.
Run against production the same day, the SQL rule flagged exactly one of the
801: 4259 "DWCS 10.3".
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import unittest

from test_sql_behaviour import PostgresCase, REPO_ROOT

sys.path.insert(0, os.path.join(REPO_ROOT, "cfl_engine", "integrity"))
sys.path.insert(0, os.path.join(REPO_ROOT, "research", "data-integrity"))

# (name, is a UFC card)
NAMES = [
    ("UFC 300: Pereira vs. Hill", True),
    ("UFC 100", True),
    ("UFC 37.5: As Real As It Gets", True),
    ("UFC Fight Night: Buckley vs. Malott", True),
    ("UFC Fight Night 56: Shogun vs Saint Preux", True),
    ("UFC Fight Night 1", True),
    ("UFC Fight Night - Fight for the Troops", True),
    ("UFC on FOX: Johnson vs. Reis", True),
    ("UFC on FX: Belfort vs. Rockhold", True),
    ("UFC on FUEL TV: Nogueira vs. Werdum", True),
    ("UFC Live: Cruz vs Johnson", True),
    ("UFC Macao: Franklin vs Le", True),
    ("UFC: Silva vs Irvin", True),
    ("UFC - Ultimate Japan", True),
    ("UFC - Ultimate Ultimate '96", True),
    ("UFC 306: Riyadh Season Noche UFC", True),
    ("Noche UFC: Silva vs. Delgado", True),
    ("UFC Freedom 250", True),
    ("The Ultimate Fighter: Heavy Hitters Finale", True),
    ("The Ultimate Fighter: Team Joanna vs. Team Cláudia Finale", True),
    ("Ortiz vs Shamrock 3: The Final Chapter", True),
    ("UFC - Road to UFC 4.6", True),   # in production and in the sealed H1 set; see the T-086 plan
    ("DWCS 10.3", False),
    ("DWCS 11.1", False),
    ("Dana White's Contender Series 2026: Week 5", False),
    ("Dana White’s Contender Series 2024: Week 1", False),
    ("Road to UFC Season 4: Episode 6", False),
    ("road to ufc 5.1", False),
    ("Bellator 300", False),
    ("PFL World Championship", False),
    ("", False),
]


def js_answers(names):
    node = shutil.which("node")
    if not node:
        return None
    code = ("const {isUfcEventName}=require(process.argv[1]);"
            "const names=JSON.parse(require('fs').readFileSync(0,'utf8'));"
            "process.stdout.write(JSON.stringify(names.map(isUfcEventName)));")
    out = subprocess.run([node, "-e", code, os.path.join(REPO_ROOT, "build", "promotion.js")],
                         input=json.dumps(names), capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def t083_ufc_event_re() -> "re.Pattern[str]":
    """UFC_EVENT_RE exactly as reconcile_ufc_records.py compiles it."""
    import ast
    path = os.path.join(REPO_ROOT, "research", "data-integrity", "reconcile_ufc_records.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in tree.body:
        if (isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "UFC_EVENT_RE" for t in node.targets)
                and isinstance(node.value, ast.Call)):
            args = node.value.args
            pattern = ast.literal_eval(args[0])
            flags = 0
            for a in args[1:]:
                for name in ast.unparse(a).replace("re.", "").split("|"):
                    flags |= getattr(re, name.strip())
            return re.compile(pattern, flags)
    raise AssertionError("UFC_EVENT_RE not found in reconcile_ufc_records.py")


def sql_check_expression() -> str:
    sql = open(os.path.join(REPO_ROOT, "t086_dwcs_non_ufc.sql")).read()
    m = re.search(r"ADD CONSTRAINT events_ufc_name_only CHECK \((.*?)\);", sql, re.S)
    assert m, "events_ufc_name_only CHECK not found in the migration"
    return " ".join(m.group(1).split())


class TestRuleWithoutDatabase(unittest.TestCase):

    def test_javascript(self):
        names = [n for n, _ in NAMES]
        got = js_answers(names)
        if got is None:
            self.skipTest("node not installed")
        self.assertEqual(dict(zip(names, got)), dict(NAMES))

    def test_t083_reconciliation_regex(self):
        # Read UFC_EVENT_RE out of the source rather than importing the script:
        # it imports `requests` at the top, which the test runner does not have.
        rx = t083_ufc_event_re()
        for name, want in NAMES:
            with self.subTest(name=name):
                self.assertEqual(bool(rx.search(name)) if name else False, want)

    def test_integrity_check_uses_the_migration_rule(self):
        import checks
        literals = lambda sql: re.findall(r"'([^']*)'", sql)
        self.assertEqual(literals(checks.by_key("non_ufc_card_in_events").sql),
                         literals(sql_check_expression()),
                         "the integrity check's rule differs from the migration's CHECK")


class TestRuleInPostgres(PostgresCase):

    def test_sql_check_expression(self):
        db = "promo"
        self.psql(f'drop database if exists "{db}"')
        self.psql(f'create database "{db}"')
        self.psql("create table n (name text, want boolean);", db=db)
        values = ",".join("($q$" + n + "$q$," + ("true" if w else "false") + ")" for n, w in NAMES)
        self.psql(f"insert into n values {values};", db=db)
        expr = sql_check_expression()
        bad = self.psql(f"select coalesce(string_agg(name, ' | '), '') from n "
                        f"where ({expr}) is distinct from want", db=db)
        self.assertEqual(bad, "", "the SQL CHECK disagrees on these names")


if __name__ == "__main__":
    unittest.main()
