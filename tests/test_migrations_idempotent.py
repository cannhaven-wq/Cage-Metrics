"""The proposed CLV-001 migrations claim to be idempotent. This checks it.

    python -m unittest tests/test_migrations_idempotent.py -v

A bare `ALTER TABLE ... ADD CONSTRAINT` is NOT idempotent — it errors on the
second run with "constraint already exists". Three files claimed re-runnability
while containing thirteen of them, which would have turned a routine re-apply
into a half-applied migration.

Static analysis, not execution: these files are deliberately unapplied, and the
property is a property of the text.
"""
from __future__ import annotations

import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLV_DIR = os.path.join(REPO_ROOT, "research", "clv")
MIGRATIONS = [
    "proposed_2026-09-16_fight_odds_capture.sql",
    "proposed_2026-09-16_event_flow.sql",
    "proposed_2026-09-16_clv001_columns.sql",
]


def read(name: str) -> str:
    with open(os.path.join(CLV_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def code_only(sql: str) -> str:
    """Drop `--` comment lines. The prose deliberately discusses ADD CONSTRAINT
    and DROP, so scanning the raw text finds the documentation rather than the
    statements."""
    return "\n".join(ln for ln in sql.split("\n")
                      if not ln.strip().startswith("--"))


class TestIdempotency(unittest.TestCase):
    def test_no_bare_add_constraint_at_statement_level(self):
        """Every ADD CONSTRAINT must sit inside a guard, never at top level."""
        bare = re.compile(r"^alter table\s+\S+\s*\n\s*add constraint", re.M | re.I)
        for name in MIGRATIONS:
            with self.subTest(migration=name):
                found = bare.findall(code_only(read(name)))
                self.assertEqual(
                    found, [],
                    f"{name} has {len(found)} unguarded ADD CONSTRAINT — it would "
                    f"error on a re-run, so the idempotency claim is false")

    def test_every_named_constraint_is_existence_checked(self):
        """The guard has to name the same constraint it is about to add."""
        for name in MIGRATIONS:
            sql = code_only(read(name))
            added = re.findall(r"add constraint (\w+)", sql, re.I)
            checked = re.findall(r"conname = '(\w+)'", sql)
            for constraint in added:
                with self.subTest(migration=name, constraint=constraint):
                    self.assertIn(
                        constraint, checked,
                        f"{constraint} is added without a pg_constraint check, so "
                        f"a second run would fail on it")

    def test_column_and_index_creation_is_conditional(self):
        for name in MIGRATIONS:
            sql = code_only(read(name))
            for stmt in re.findall(r"add column(?! if not exists)", sql, re.I):
                self.fail(f"{name}: ADD COLUMN without IF NOT EXISTS")
            for stmt in re.findall(r"create index(?! if not exists)", sql, re.I):
                self.fail(f"{name}: CREATE INDEX without IF NOT EXISTS")
            for stmt in re.findall(r"create table(?! if not exists)", sql, re.I):
                self.fail(f"{name}: CREATE TABLE without IF NOT EXISTS")

    def test_a_file_claiming_idempotency_actually_is(self):
        """If the claim is in the header it has to be earned — otherwise the
        claim itself has to go. This is the check that keeps those two in step."""
        claim = re.compile(r"idempotent|re-runnable|rerunnable", re.I)
        bare = re.compile(r"^alter table\s+\S+\s*\n\s*add constraint", re.M | re.I)
        for name in MIGRATIONS:
            sql = read(name)
            if claim.search(sql):
                with self.subTest(migration=name):
                    self.assertEqual(
                        bare.findall(code_only(sql)), [],
                        f"{name} claims idempotency and is not")


class TestStillAdditiveOnly(unittest.TestCase):
    """The DO-block rewrite must not have smuggled in anything destructive."""

    FORBIDDEN = [
        (r"\bdrop\s+table\b", "DROP TABLE"),
        (r"\bdrop\s+column\b", "DROP COLUMN"),
        (r"\bdrop\s+constraint\b", "DROP CONSTRAINT"),
        (r"\bdrop\s+view\b", "DROP VIEW"),
        (r"\bdelete\s+from\b", "DELETE"),
        (r"\btruncate\b", "TRUNCATE"),
        (r"^\s*update\s+public\.", "UPDATE"),
    ]

    def test_nothing_destructive(self):
        for name in MIGRATIONS:
            # Comments carry the words on purpose ("no DROP of any kind").
            code = code_only(read(name))
            for pattern, label in self.FORBIDDEN:
                with self.subTest(migration=name, statement=label):
                    self.assertIsNone(
                        re.search(pattern, code, re.I | re.M),
                        f"{name} contains a {label} — these migrations are "
                        f"additive-only")

    def test_drop_trigger_is_only_the_recreate_idiom(self):
        """`drop trigger if exists` immediately before `create trigger` is how
        the repo's existing ledgers are written and is itself idempotent. Any
        other DROP TRIGGER would be removing protection."""
        for name in MIGRATIONS:
            sql = code_only(read(name))
            for m in re.finditer(r"drop trigger(?! if exists)", sql, re.I):
                self.fail(f"{name}: unconditional DROP TRIGGER at {m.start()}")


class TestAppendOnlyPreserved(unittest.TestCase):
    """Reed asked for the append-only protections to be preserved. They are
    load-bearing for provenance, so they get their own check."""

    LEDGERS = ["fight_bout_order", "fight_bout_completions", "odds_api_usage"]

    def test_each_ledger_blocks_update_and_delete(self):
        sql = read("proposed_2026-09-16_event_flow.sql")
        for table in self.LEDGERS:
            with self.subTest(table=table):
                self.assertRegex(sql, rf"before update on public\.{table}")
                self.assertRegex(sql, rf"before delete on public\.{table}")
                self.assertRegex(sql, rf"{table}_no_rewrite")

    def test_each_ledger_enables_rls_and_revokes_public_roles(self):
        sql = read("proposed_2026-09-16_event_flow.sql")
        for table in self.LEDGERS:
            with self.subTest(table=table):
                self.assertRegex(
                    sql, rf"alter table public\.{table} enable row level security")
                self.assertRegex(
                    sql, rf"revoke all on public\.{table} from anon, authenticated")


if __name__ == "__main__":
    unittest.main(verbosity=2)
