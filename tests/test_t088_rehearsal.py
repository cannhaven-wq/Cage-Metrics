"""T-088: rehearse the least-privilege migration against a replica of production.

    python -m unittest tests/test_t088_rehearsal.py -v

Builds a throwaway cluster from research/security/t088_replica_bootstrap.sql and
t088_replica_schema.sql (production's schema, policies, triggers and grants as of
2026-10-13), then:

1. runs research/security/t088_probe.sql on the CURRENT grants — every
   legitimate browser action must already work, or the probe is wrong;
2. applies proposed_2026-10-13_t088_least_privilege.sql TWICE (idempotency) and
   the pre-fight TRUNCATE guard twice;
3. runs the probe again and compares it, line for line, with
   research/security/t088_expected_after.txt;
4. proves the migration's own assertion block aborts on a leaked write, a
   missing grant and a changed read.

**No production database is touched, ever** — same arrangement as
tests/test_sql_behaviour.py: initdb into a temp directory, unix socket only,
`listen_addresses` empty, destroyed afterwards. Without initdb every test SKIPS.
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEC = os.path.join(REPO_ROOT, "research", "security")
MIGRATION = "proposed_2026-10-13_t088_least_privilege.sql"
GUARD = "proposed_2026-10-13_t088_pre_fight_truncate_guard.sql"
PG_BIN_CANDIDATES = ("/usr/lib/postgresql/17/bin", "/usr/lib/postgresql/16/bin",
                     "/usr/lib/postgresql/15/bin", "/usr/local/pgsql/bin")
PORT = 55434


def _bin_dir():
    for d in PG_BIN_CANDIDATES:
        if os.path.exists(os.path.join(d, "initdb")):
            return d
    which = shutil.which("initdb")
    return os.path.dirname(which) if which else None


def read(name):
    with open(os.path.join(SEC, name), encoding="utf-8") as fh:
        return fh.read()


def probe_lines(text):
    """`role|probe|outcome` lines out of the probe's T088_RESULT exception."""
    out = []
    for ln in text.splitlines():
        ln = ln.split("T088_RESULT")[-1].strip()
        if ln.count("|") == 2 and not ln.startswith("CONTEXT"):
            out.append(ln)
    return out


class T088Rehearsal(unittest.TestCase):
    tmp = None

    @classmethod
    def setUpClass(cls):
        cls.bin_dir = _bin_dir()
        if not cls.bin_dir:
            raise unittest.SkipTest("no local Postgres (initdb not found)")
        cls.tmp = tempfile.mkdtemp(prefix="t088-pg-", dir="/var/tmp")
        os.chmod(cls.tmp, 0o777)
        cls.runas = "postgres" if os.geteuid() == 0 else None
        cls.pg16 = "/16/" in cls.bin_dir or "/15/" in cls.bin_dir
        data = os.path.join(cls.tmp, "data")
        try:
            cls._run([os.path.join(cls.bin_dir, "initdb"), "-D", data, "-U", "pg", "--auth=trust"])
            cls._run([os.path.join(cls.bin_dir, "pg_ctl"), "-D", data, "-w",
                      "-o", f"-k {cls.tmp} -p {PORT} -c listen_addresses=",
                      "-l", os.path.join(cls.tmp, "log"), "start"])
        except Exception as e:                  # noqa: BLE001
            shutil.rmtree(cls.tmp, ignore_errors=True)
            cls.tmp = None
            raise unittest.SkipTest(f"could not start a throwaway Postgres: {e}")
        cls.psql_file("t088_replica_bootstrap.sql")
        cls.psql_file("t088_replica_schema.sql")
        cls.before = probe_lines(cls.psql_file("t088_probe.sql", check=False))
        for _ in range(2):
            cls.psql_file(MIGRATION)
            cls.psql_file(GUARD)
        cls.after = probe_lines(cls.psql_file("t088_probe.sql", check=False))
        cls.guard = cls.psql_file("t088_guard_probe.sql", check=False)

    @classmethod
    def tearDownClass(cls):
        if not cls.tmp:
            return
        try:
            cls._run([os.path.join(cls.bin_dir, "pg_ctl"), "-D",
                      os.path.join(cls.tmp, "data"), "-m", "immediate", "stop"])
        except Exception:                       # noqa: BLE001
            pass
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def _run(cls, argv, check=True):
        if cls.runas:
            argv = ["su", cls.runas, "-s", "/bin/bash", "-c", " ".join(shlex.quote(a) for a in argv)]
        res = subprocess.run(argv, capture_output=True, text=True, timeout=180)
        if check and res.returncode != 0:
            raise RuntimeError(res.stdout + res.stderr)
        return res.stdout + res.stderr

    @classmethod
    def psql_text(cls, sql, check=True):
        if cls.pg16:
            sql = sql.replace(", MAINTAIN", "")
        path = os.path.join(cls.tmp, "in.sql")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(sql)
        os.chmod(path, 0o644)
        return cls._run([os.path.join(cls.bin_dir, "psql"), "-h", cls.tmp, "-p", str(PORT),
                         "-U", "pg", "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-q", "-f", path], check)

    @classmethod
    def psql_file(cls, name, check=True):
        return cls.psql_text(read(name), check)

    def test_probe_saw_every_case(self):
        self.assertEqual(len(self.before), len(self.after))
        self.assertGreaterEqual(len(self.after), 45)

    def test_every_legitimate_action_works_before_and_after(self):
        for label, lines in (("before", self.before), ("after", self.after)):
            for ln in lines:
                role, probe, outcome = ln.split("|")
                if not probe.startswith("L_"):
                    continue
                want = "err:23505" if probe == "L_card_brief_resubscribe_is_23505" else "allowed"
                with self.subTest(state=label, role=role, probe=probe):
                    self.assertEqual(outcome, want)

    def test_after_matches_the_reviewed_matrix(self):
        expected = [ln for ln in read("t088_expected_after.txt").splitlines() if ln.count("|") == 2]
        self.assertEqual(self.after, expected)

    def test_no_attack_is_allowed_after(self):
        for ln in self.after:
            role, probe, outcome = ln.split("|")
            if probe.startswith("A_") or probe == "D_new_table_anon_can_write":
                with self.subTest(role=role, probe=probe):
                    self.assertIn(outcome, ("denied", "zero_rows"))

    def test_truncate_guard_binds_service_role_and_owner_but_not_inserts(self):
        self.assertIn("service_insert=allowed", self.guard)
        self.assertIn("service_truncate=blocked", self.guard)
        self.assertIn("owner_truncate=blocked", self.guard)

    def test_assertion_block_catches_a_leak_a_missing_grant_and_a_changed_read(self):
        mig = read(MIGRATION)
        anchor = "-- 5. Prove it before committing"
        watch = "GRANT INSERT, DELETE            ON public.user_watchlist   TO authenticated;"
        self.assertIn(anchor, mig)
        self.assertIn(watch, mig)
        cases = {
            "leak": mig.replace(anchor, "GRANT TRUNCATE ON public.user_bets TO authenticated;\n" + anchor),
            "missing": mig.replace(watch, "REVOKE ALL ON public.user_watchlist FROM authenticated; "
                                          "GRANT SELECT ON public.user_watchlist TO authenticated;"),
            "read": mig.replace(anchor, "REVOKE SELECT ON public.fighters FROM anon;\n" + anchor),
        }
        for name, sql in cases.items():
            with self.subTest(mutation=name):
                self.assertIn("T-088 least-privilege check failed", self.psql_text(sql, check=False))
        # and each mutation rolled back
        self.assertEqual(probe_lines(self.psql_file("t088_probe.sql", check=False)), self.after)


if __name__ == "__main__":
    unittest.main()
