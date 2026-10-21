"""T-090: the Card Brief double opt-in migration, run against a real Postgres.

    python -m unittest tests/test_card_brief_optin_sql.py -v

Builds a throwaway cluster that looks like production does today: the T-088
replica (research/security/t088_replica_bootstrap.sql + t088_replica_schema.sql,
production's schema, policies and grants), then the T-088 least-privilege
migration and the pre-fight TRUNCATE guard, which production has had since
2026-10-15 (D-028). On top of that it applies card_brief_double_optin_migration.sql
TWICE, and proves:

* a link confirms its address once; a second click is still TRUE and changes
  nothing;
* a wrong, malformed, expired or unsubscribed link is FALSE and confirms nothing;
* a visitor cannot read the table, the tokens or the hashes, and cannot write
  anything but (email, source) — and the Card Brief signup still works, with a
  repeat address still 23505;
* a browser insert can never arrive confirmed, even if a wider grant is handed
  back by mistake;
* the migration's own check aborts the transaction on a leaked read;
* a re-run is safe and raises no NOTICE (a NOTICE hangs the Supabase MCP tool).

**No production database is touched, ever** — same arrangement as
tests/test_t088_rehearsal.py: initdb into a temp directory, unix socket only,
`listen_addresses` empty, destroyed afterwards. Without initdb every test SKIPS.
"""
from __future__ import annotations

import hashlib
import os
import shlex
import shutil
import subprocess
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEC = os.path.join(REPO_ROOT, "research", "security")
MIGRATION = os.path.join(REPO_ROOT, "card_brief_double_optin_migration.sql")
PG_BIN_CANDIDATES = ("/usr/lib/postgresql/17/bin", "/usr/lib/postgresql/16/bin",
                     "/usr/lib/postgresql/15/bin", "/usr/local/pgsql/bin")
PORT = 55438

GOOD = "a" * 64              # a well-formed token; its sha256 is what is stored
EXPIRED = "b" * 64
UNSUB = "c" * 64
AUTH = "d" * 64
NEVER_ISSUED = "e" * 64
ADMIN = "00000000-0000-0000-0000-00000000a0a0"
MEMBER = "00000000-0000-0000-0000-00000000b0b0"
HASHED = "f" * 64


def sha(tok: str) -> str:
    return hashlib.sha256(tok.encode()).hexdigest()


def _bin_dir():
    for d in PG_BIN_CANDIDATES:
        if os.path.exists(os.path.join(d, "initdb")):
            return d
    which = shutil.which("initdb")
    return os.path.dirname(which) if which else None


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class CardBriefOptIn(unittest.TestCase):
    tmp = None

    @classmethod
    def setUpClass(cls):
        cls.bin_dir = _bin_dir()
        if not cls.bin_dir:
            raise unittest.SkipTest("no local Postgres (initdb not found)")
        cls.tmp = tempfile.mkdtemp(prefix="t090-pg-", dir="/var/tmp")
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

        # Production as it stands: the replica, then T-088 (applied 2026-10-15).
        for name in ("t088_replica_bootstrap.sql", "t088_replica_schema.sql",
                     "proposed_2026-10-13_t088_least_privilege.sql",
                     "proposed_2026-10-13_t088_pre_fight_truncate_guard.sql"):
            cls.sql(read(os.path.join(SEC, name)))
        # The one address already on the list before the migration, and one
        # admin and one ordinary member for the admin-read policy.
        cls.sql("insert into public.email_subscribers (email, source) "
                "values ('existing@example.invalid', 'footer');"
                f"insert into public.profiles (id, email, is_admin) values "
                f"('{ADMIN}', 'admin@example.invalid', true), ('{MEMBER}', 'member@example.invalid', false);")

        # The migration runs as postgres, the way psql "$SUPABASE_DB_URL" does.
        cls.first_run = cls.sql("set role postgres;\n" + read(MIGRATION))
        cls.second_run = cls.sql("set role postgres;\n" + read(MIGRATION))

        # Issue four links the way the sender does: hash only, expiry set.
        cls.sql(f"""
          set role service_role;
          insert into public.email_subscribers (email, source) values
            ('good@example.invalid', 't'), ('expired@example.invalid', 't'),
            ('unsub@example.invalid', 't'), ('auth@example.invalid', 't'),
            ('hash@example.invalid', 't');
          update public.email_subscribers set confirm_token_hash = '{sha(GOOD)}',
                 confirm_token_expires_at = now() + interval '7 days',
                 confirm_sent_at = now(), confirm_send_count = 1
           where email = 'good@example.invalid';
          update public.email_subscribers set confirm_token_hash = '{sha(EXPIRED)}',
                 confirm_token_expires_at = now() - interval '1 minute',
                 confirm_sent_at = now() - interval '8 days', confirm_send_count = 1
           where email = 'expired@example.invalid';
          update public.email_subscribers set confirm_token_hash = '{sha(UNSUB)}',
                 confirm_token_expires_at = now() + interval '7 days',
                 unsubscribed_at = now(), confirm_send_count = 1
           where email = 'unsub@example.invalid';
          update public.email_subscribers set confirm_token_hash = '{sha(AUTH)}',
                 confirm_token_expires_at = now() + interval '7 days', confirm_send_count = 1
           where email = 'auth@example.invalid';
          update public.email_subscribers set confirm_token_hash = '{sha(HASHED)}',
                 confirm_token_expires_at = now() + interval '7 days', confirm_send_count = 1
           where email = 'hash@example.invalid';
        """)

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
    def sql(cls, text, check=True):
        """Run a script; returns stdout + stderr (unaligned, tuples only)."""
        if cls.pg16:
            text = text.replace(", MAINTAIN", "")
        path = os.path.join(cls.tmp, "in.sql")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(path, 0o644)
        return cls._run([os.path.join(cls.bin_dir, "psql"), "-h", cls.tmp, "-p", str(PORT),
                         "-U", "pg", "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-q", "-At",
                         "-f", path], check)

    def one(self, text):
        return self.sql(text).strip().splitlines()[-1]

    def denied(self, role, stmt):
        out = self.sql(f"set role {role};\n{stmt};", check=False)
        self.assertIn("permission denied", out, f"{role} was allowed: {stmt}\n{out}")

    def confirm(self, token, role="anon"):
        return self.one(f"set role {role}; select public.confirm_email_subscription('{token}');")

    # -- re-run ----------------------------------------------------------------
    def test_applies_twice_without_a_notice(self):
        for label, out in (("first", self.first_run), ("second", self.second_run)):
            with self.subTest(run=label):
                self.assertNotIn("ERROR", out)
                self.assertNotIn("NOTICE", out)

    def test_existing_address_is_kept_unconfirmed(self):
        row = self.one("select confirmed_at is null, confirm_token_hash is null, confirm_send_count, "
                       "unsubscribe_token is not null from public.email_subscribers "
                       "where email = 'existing@example.invalid';")
        self.assertEqual(row, "t|t|0|t")

    # -- confirming ------------------------------------------------------------
    def test_link_confirms_once_and_a_second_click_changes_nothing(self):
        self.assertEqual(self.one("select confirmed_at is null from public.email_subscribers "
                                  "where email = 'good@example.invalid';"), "t")
        self.assertEqual(self.confirm(GOOD), "t")
        first = self.one("select confirmed_at from public.email_subscribers "
                         "where email = 'good@example.invalid';")
        self.assertTrue(first)
        self.assertEqual(self.confirm(GOOD), "t")
        self.assertEqual(self.one("select confirmed_at from public.email_subscribers "
                                  "where email = 'good@example.invalid';"), first)
        # it confirmed that address and no other (auth@ is confirmed by its own test)
        self.assertEqual(self.one("select string_agg(email, ',' order by email) from public.email_subscribers "
                                  "where confirmed_at is not null and email <> 'auth@example.invalid';"),
                         "good@example.invalid")

    def test_wrong_and_malformed_tokens_are_false(self):
        for tok in (NEVER_ISSUED, "A" * 64, "a" * 63, "", "' or 1=1 --", sha(GOOD)):
            with self.subTest(token=tok[:12]):
                tok_sql = tok.replace("'", "''")
                self.assertEqual(self.one(f"set role anon; select public.confirm_email_subscription('{tok_sql}');"), "f")
        self.assertEqual(self.one("set role anon; select public.confirm_email_subscription(null);"), "f")

    def test_the_stored_hash_is_not_a_working_link(self):
        # Someone who could read the table still could not confirm with it.
        self.assertEqual(self.confirm(sha(HASHED)), "f")
        self.assertEqual(self.one("select confirmed_at is null from public.email_subscribers "
                                  "where email = 'hash@example.invalid';"), "t")

    def test_expired_link_is_false_and_confirms_nothing(self):
        self.assertEqual(self.confirm(EXPIRED), "f")
        self.assertEqual(self.one("select confirmed_at is null from public.email_subscribers "
                                  "where email = 'expired@example.invalid';"), "t")

    def test_unsubscribed_address_is_never_confirmed(self):
        self.assertEqual(self.confirm(UNSUB), "f")
        self.assertEqual(self.one("select confirmed_at is null from public.email_subscribers "
                                  "where email = 'unsub@example.invalid';"), "t")

    def test_signed_in_member_can_confirm_too(self):
        self.assertEqual(self.confirm(AUTH, role="authenticated"), "t")

    # -- privileges ------------------------------------------------------------
    def test_visitors_cannot_read_the_list_or_any_token(self):
        self.denied("anon", "select count(*) from public.email_subscribers")
        self.denied("anon", "select confirm_token_hash from public.email_subscribers")
        self.denied("anon", "select unsubscribe_token from public.email_subscribers")
        self.denied("anon", "select email from public.email_subscribers")

    def as_member(self, uid, stmt, check=True):
        return self.sql(f"set request.jwt.claim.sub = '{uid}'; set role authenticated;\n{stmt};", check=check)

    def test_admin_read_is_unchanged_and_a_member_sees_nothing(self):
        # D-027: existing reads stay. The RLS policy decides the rows.
        cols = ("id, email, source, created_at, last_sent_at, unsubscribed_at, unsubscribe_token, "
                "confirmed_at, confirm_sent_at, confirm_send_count")
        admin = self.as_member(ADMIN, f"select count(*) from (select {cols} from public.email_subscribers) s")
        self.assertGreaterEqual(int(admin.strip().splitlines()[-1]), 5)
        member = self.as_member(MEMBER, f"select count(*) from (select {cols} from public.email_subscribers) s")
        self.assertEqual(member.strip().splitlines()[-1], "0")
        nobody = self.sql(f"set role authenticated; select count(email) from public.email_subscribers;")
        self.assertEqual(nobody.strip().splitlines()[-1], "0")

    def test_nobody_reads_the_token_columns_from_a_browser_role_not_even_an_admin(self):
        for uid in (ADMIN, MEMBER):
            for stmt in ("select confirm_token_hash from public.email_subscribers",
                         "select confirm_token_expires_at from public.email_subscribers",
                         "select * from public.email_subscribers"):
                with self.subTest(uid=uid, stmt=stmt):
                    out = self.as_member(uid, stmt, check=False)
                    self.assertIn("permission denied", out)

    def test_visitors_cannot_change_or_empty_the_list(self):
        for role in ("anon", "authenticated"):
            with self.subTest(role=role):
                self.denied(role, "update public.email_subscribers set confirmed_at = now()")
                self.denied(role, "delete from public.email_subscribers")
                self.denied(role, "truncate public.email_subscribers")
                self.denied(role, "insert into public.email_subscribers (email, source, confirmed_at) "
                                  "values ('forged@example.invalid', 'x', now())")
                self.denied(role, "insert into public.email_subscribers (email, source, confirm_token_hash, "
                                  f"confirm_token_expires_at) values ('forged2@example.invalid', 'x', '{sha(GOOD)}', now())")

    def test_card_brief_signup_still_works_and_a_repeat_is_23505(self):
        for role in ("anon", "authenticated"):
            with self.subTest(role=role):
                out = self.sql(f"set role {role}; insert into public.email_subscribers (email, source) "
                               f"values ('new-{role}@example.invalid', 'footer');")
                self.assertNotIn("ERROR", out)
                dup = self.sql(f"set role {role}; insert into public.email_subscribers (email, source) "
                               f"values ('new-{role}@example.invalid', 'footer');", check=False)
                self.assertIn("duplicate key value violates unique constraint", dup)
        self.assertEqual(self.one("select count(*) from public.email_subscribers "
                                  "where email like 'new-%' and confirmed_at is null;"), "2")

    def test_unsubscribe_link_still_works_for_visitors(self):
        tok = self.one("select unsubscribe_token from public.email_subscribers "
                       "where email = 'existing@example.invalid';")
        out = self.sql(f"begin; set local role anon; select public.unsubscribe_email('{tok}'); rollback;")
        self.assertEqual(out.strip().splitlines()[-1], "t")
        self.assertEqual(self.one("select unsubscribed_at is null from public.email_subscribers "
                                  "where email = 'existing@example.invalid';"), "t")

    def test_a_browser_insert_never_arrives_confirmed_even_with_a_wide_grant(self):
        out = self.sql(f"""
          begin;
          grant insert on public.email_subscribers to anon;
          set local role anon;
          insert into public.email_subscribers (email, source, confirmed_at, confirm_token_hash,
                 confirm_token_expires_at, confirm_send_count)
          values ('wide@example.invalid', 'x', now(), '{sha(NEVER_ISSUED)}', now() + interval '1 day', 5);
          reset role;
          select confirmed_at is null, confirm_token_hash is null, confirm_send_count
            from public.email_subscribers where email = 'wide@example.invalid';
          rollback;
        """)
        self.assertEqual(out.strip().splitlines()[-1], "t|t|0")
        self.assertEqual(self.one("select count(*) from public.email_subscribers "
                                  "where email = 'wide@example.invalid';"), "0")

    def test_constraints_refuse_a_bad_hash_and_a_link_without_expiry(self):
        bad = self.sql("update public.email_subscribers set confirm_token_hash = 'not-a-hash', "
                       "confirm_token_expires_at = now() where email = 'existing@example.invalid';", check=False)
        self.assertIn("email_subscribers_confirm_hash_format", bad)
        no_exp = self.sql(f"update public.email_subscribers set confirm_token_hash = '{sha('z' * 64)}' "
                          "where email = 'existing@example.invalid';", check=False)
        self.assertIn("email_subscribers_confirm_hash_has_expiry", no_exp)

    def test_function_shape(self):
        row = self.one("select prosecdef, proconfig::text from pg_proc "
                       "where oid = 'public.confirm_email_subscription(text)'::regprocedure;")
        self.assertEqual(row, 't|{"search_path=\\"\\""}')
        self.assertEqual(self.one("select has_function_privilege('public', "
                                  "'public.confirm_email_subscription(text)', 'EXECUTE');"), "f")

    def test_the_migration_check_aborts_on_a_leaked_read(self):
        mig = read(MIGRATION)
        anchor = "-- 6. Prove it before committing"
        self.assertIn(anchor, mig)
        leaked = mig.replace(anchor, "GRANT SELECT ON public.email_subscribers TO anon;\n" + anchor)
        out = self.sql("set role postgres;\n" + leaked, check=False)
        self.assertIn("T-090 double opt-in check failed", out)
        self.assertIn("anon holds SELECT", out)
        hash_leak = mig.replace(anchor, "GRANT SELECT (confirm_token_hash) ON public.email_subscribers "
                                        "TO authenticated;\n" + anchor)
        out = self.sql("set role postgres;\n" + hash_leak, check=False)
        self.assertIn("authenticated may SELECT confirm_token_hash", out)
        lost = mig.replace("              confirmed_at, confirm_sent_at, confirm_send_count)\n",
                           "              confirmed_at, confirm_sent_at)\n")
        self.assertNotEqual(lost, mig)
        out = self.sql("set role postgres;\n" + lost, check=False)
        self.assertIn("authenticated lost SELECT (confirm_send_count)", out)
        # and every transaction rolled back
        self.denied("anon", "select 1 from public.email_subscribers")
        self.assertIn("permission denied", self.as_member(
            ADMIN, "select confirm_token_hash from public.email_subscribers", check=False))


if __name__ == "__main__":
    unittest.main()
