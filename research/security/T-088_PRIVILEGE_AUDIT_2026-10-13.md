# T-088 — Who can write to the database from a browser? (audit and plan, 2026-10-13)

**Status:** audit done; plan revised to the owner's 2026-10-14 review; rehearsed on a
replica **and on production (rolled back)**; **nothing applied.** Applying it
is an L3 gate (`coordination/CRITICAL_GATES.md` item 5) and waits on the owner's
sign-off on the production rehearsal results below.

## In plain terms

- **Verdict.** Anyone visiting the site can write to more of the database than
  the site needs. Most of those writes are blocked by row-level rules. Three
  get through today. The worst, "erase a whole table", cannot be reached from a
  browser, but it is only one mistake away. The fix keeps every action the site
  actually offers and removes the rest. Reads do not change.
- **Found along the way, and worse for the business:** the **Cannon Card Brief
  signup has never worked.** Every visitor who submits an address gets a
  database error, which is why the list has zero people on it. That fix is in
  this change; it touches no database setting.
- **What a member sees differently:** nothing. Signup, My Book, watchlist,
  alerts, alert settings, unsubscribe and the Card Brief all behave the same.
  The Card Brief starts working.

## What was checked

Read-only, against production, 2026-10-13. Every table, view, sequence,
function and default privilege in `public`, plus each one's RLS flag, policies
and triggers, for `PUBLIC`, `anon` (a visitor) and `authenticated` (a member).
Every browser-side write in this repo's pages, and the database key used by
every backend writer (`build/`, `cfl_engine/`, `cage-metrics-scrapper`,
`cage-metrics-odds-scrapper`: **all of them use the service-role key**). The
signup and unsubscribe functions. `pg_graphql` is not installed, and storage
has no buckets, so REST is the only browser path.

## Findings

| # | finding | reachable from a browser today? | severity |
|---|---|---|---|
| F1 | **Card Brief signup fails for every visitor.** `subscribeEmail` used `upsert(..., ignoreDuplicates)`, which is `INSERT ... ON CONFLICT DO NOTHING`. Postgres requires an ON CONFLICT insert to pass a SELECT policy too, and visitors (correctly) have none on `email_subscribers`. Confirmed on production as `anon` and `authenticated` in a rolled-back transaction: `42501 new row violates row-level security policy`. A plain insert passes. The visitor is shown the raw database message. | yes — it is the visitor's only path | **high (commercial)** |
| F2 | A visitor can subscribe with an **unsubscribe token they choose** (whole-row INSERT on `email_subscribers`). It is harmless today because the list is empty. Once it is not, whoever knows a token can unsubscribe that row. | yes | medium |
| F3 | A member can **rewrite `profiles.email`** (whole-row UPDATE; the policy pins nine columns, not that one). Alert mail goes to the verified `auth.users` address (`build/send-alerts.js:319`), so this mislabels the member's own row and does not redirect mail. | yes | low |
| F4 | **`hub_visits` accepts anonymous inserts** (policy `WITH CHECK (true)`). Nothing in any repo writes or reads it; its 20 rows were written within six minutes on 2026-09-16. Dead surface. | yes | low |
| F5 | Browser roles hold **TRUNCATE on 26 tables** — among them `pre_fight_snapshots`, `fights`, `fighters`, `profiles`, `user_bets`, `email_subscribers`. TRUNCATE ignores RLS. PostgREST never issues it, so there is no browser path today; any future SQL path (an RPC, a GraphQL install, a definer function) inherits it. | no | high if reached |
| F6 | **`pre_fight_snapshots` refuses UPDATE and DELETE, not TRUNCATE**, for every role including `service_role`. `prop_odds`, `prop_model_locks` and `win_model_locks` already refuse it. CLAUDE.md describes the table as un-erasable; it is not. | no (needs a service key or owner) | high — it is the evidence table |
| F7 | INSERT / UPDATE / DELETE grants on every read-only public table (`events`, `fights`, `fighters`, `model_*`, `predictions`, ...). RLS has no write policy there, so writes return "denied" or touch zero rows. | refused by RLS | low (defence in depth) |
| F8 | **Default privileges** hand `anon` and `authenticated` ALL on every new table and sequence the `postgres` role creates in `public`. Every exposure above started this way; T-087's odds tables did too. | the next table | medium |
| F9 | UPDATE (`setval`) and SELECT on **every sequence**. Not exposed over REST. | no | low |
| F10 | `v_prop_projections_current` is an auto-updatable view with INSERT / UPDATE / DELETE grants. It is `security_invoker`, so the base table's RLS refuses the write. | refused by RLS | low |
| F11 | `fight_odds` and `model_picks` are described as append-only and **have no triggers enforcing it**. The `fight_odds` fix is already proposed (`research/clv/proposed_2026-09-16_fight_odds_immutability.sql`). | no (service key only) | tracked elsewhere |

**Accepted as designed:**
- **Definer functions callable by visitors** (Supabase advisor WARNs): `current_user_is_admin/is_pro/entitlement`, `is_premium`, `alert_quota`, `unsubscribe_email`, `handle_new_user`, `user_alerts_quota_check`. The first four are evaluated *inside RLS policies* as the caller, so revoking EXECUTE would break every policy that names them. The unsubscribe link needs anonymous EXECUTE and takes a 128-bit token. The trigger functions cannot be called over REST.
- **Anyone can add an address to the Card Brief, the waitlist or the analytics table.** That is what a signup form is.

## The plan

Two proposed files, each with an assertion block that rolls it back if the
result is not exactly right:

1. [`proposed_2026-10-13_t088_least_privilege.sql`](proposed_2026-10-13_t088_least_privilege.sql) — F2–F5, F7–F10.
2. [`proposed_2026-10-13_t088_pre_fight_truncate_guard.sql`](proposed_2026-10-13_t088_pre_fight_truncate_guard.sql) — F6.

Plus the F1 fix in `_auth.js` (no database change; it ships when the PR merges).

| what someone does on the site | what the database needs | after |
|---|---|---|
| Sign up / log in | nothing from the browser: `handle_new_user()` runs as `postgres` | unchanged |
| Get the Card Brief | `INSERT (email, source)` on `email_subscribers` + USAGE on its id sequence | **narrowed to two columns** |
| Join the waitlist | `INSERT (email, source)` on `premium_waitlist` | narrowed |
| Page analytics | `INSERT (event, session_id, path, props)` on `funnel_events` | narrowed |
| Unsubscribe link | `EXECUTE unsubscribe_email` | unchanged |
| Change display name | `UPDATE (display_name)` on `profiles` | **narrowed to one column** |
| My Book | INSERT / UPDATE / DELETE `user_bets`; INSERT / UPDATE `user_bankrolls` | unchanged |
| Watchlist | INSERT / DELETE `user_watchlist` | unchanged |
| Alerts + settings | INSERT / UPDATE / DELETE `user_alerts`; INSERT / UPDATE `user_alert_prefs` | unchanged |
| Read any public page | SELECT, as today | **unchanged — the migration proves it** |
| Backend writers | service role, which bypasses all of this | unchanged |

Everything else a browser role holds — every TRUNCATE, REFERENCES, TRIGGER,
MAINTAIN, every write on a read-only table, `hub_visits`, sequence UPDATE —
goes. **Every RLS policy stays exactly as it is.**

**New tables, views and sequences are private by default** (owner,
2026-10-14). Nothing created after this migration is readable or writable from
a browser until its own migration says
`GRANT SELECT ON public.<object> TO anon, authenticated`. Objects that exist
today keep every read they have, because default privileges only apply to
objects created later; the migration proves that before committing. What it
takes from future work:
- **Every new public table or view needs an explicit grant.**
  `tests/t088-least-privilege.test.js` fails if a page reads an object no repo
  SQL grants. 16 current reads were granted only in production, never in a
  file; they are frozen as a named legacy list, and the test refuses additions
  to it.
- **Drop-and-recreate loses grants.** `CREATE OR REPLACE VIEW` keeps them. Of
  the 15 drop-and-recreate views in repo SQL, 13 already re-grant, and the other
  2 (`dur001_migration.sql`) have no browser reader. No job creates tables or
  views at runtime.

## Rehearsal 1 — replica (2026-10-13, repeated 2026-10-14)

`tests/test_t088_rehearsal.py` builds a throwaway local Postgres from
[`t088_replica_bootstrap.sql`](t088_replica_bootstrap.sql) and
[`t088_replica_schema.sql`](t088_replica_schema.sql). Those files hold production's schema, policies, triggers,
identity columns and exact grants, captured read-only with no rows. They were
re-captured on 2026-10-14 after `main` merged D-025 and T-084/T-085, and came
out byte-identical for tables, policies and grants. Then
[`t088_probe.sql`](t088_probe.sql) runs 50 probes as the real roles with real
JWT subjects. Each probe runs in a savepoint and the whole run rolls back.

| | before | after |
|---|---|---|
| 31 legitimate actions: signup, Card Brief (new and repeat), waitlist, analytics, unsubscribe, public reads incl. an existing view, profile, My Book, watchlist, alerts, alert settings, deliveries, backend writers | all work | **all work** |
| TRUNCATE `pre_fight_snapshots` / `fights` / `profiles` / `user_bets` / `email_subscribers` | allowed | denied |
| forged unsubscribe token · rewrite `profiles.email` · `hub_visits` insert · `setval` | allowed | denied |
| update `events` · unsubscribe everyone | refused by RLS (zero rows) | denied |
| self-admin · bet as another user · forge an alert delivery · write through the invoker view | denied | denied |
| edit another member's bets | zero rows (RLS) | zero rows (RLS) — correct: members keep UPDATE on their own |
| a brand-new table: can a visitor write it? read it? | yes / yes | **no / no** |

Also proved on the replica:
- **Idempotent.** Both files apply twice cleanly.
- **The assertion block bites.** A leaked TRUNCATE plus a column UPDATE, a dropped watchlist grant, and a removed public read each abort the migration. Each one is rolled back.
- **The TRUNCATE guard holds.** It blocks `service_role` and the owner, and the snapshot writer's INSERT still works.

The expected after-state is pinned in
[`t088_expected_after.txt`](t088_expected_after.txt).

## Rehearsal 2 — production, rolled back (2026-10-14)

Run against the live database through the Supabase tool. Every run started
with `lock_timeout = 3s`, so nothing could queue behind live traffic. Each run
ended in an exception, so all of it rolled back. Raw results:
[`t088_production_rehearsal_2026-10-14.txt`](t088_production_rehearsal_2026-10-14.txt).

- **The migration and its assertion block pass on production in 0.1 s** with no
  violation. That includes every real view, which the replica does not carry.
- **All 50 probes ran under the migration.** 49 match the replica's expected
  matrix exactly:
  - every legitimate action works;
  - every attack is denied;
  - a new table is unreadable and unwritable.
- **The one difference was a broken probe, not a policy gap.** The `hub_visits`
  probe set `id` explicitly. Production's `id` is an identity column, which
  rejects that before any privilege check (`428C9`). Re-run correctly on
  production: anonymous insert is **allowed today** and **denied under the
  migration**. The probe is fixed, and the replica now reproduces all 13
  identity columns.
- **The TRUNCATE guard on production:** trigger creation takes 10 ms, and a TRUNCATE
  by the table owner is refused with the append-only message. The
  `service_role` half could not be run through the tool. See below.
- **Nothing persisted.** A fingerprint taken before and after the rehearsals
  matched exactly:
  - an md5 of every privilege on every object in `public`;
  - an md5 of the default privileges;
  - row counts of 12 tables;
  - no guard trigger, no probe rows, no probe table, and no open session.

**Two tooling limits found, and how the probe works around them.** Both make the
Supabase `execute_sql` tool hang until its 60-second timeout, with nothing
applied and nothing left running. That is the same failure mode CLAUDE.md
records for NOTICEs.
1. **A TRUNCATE run as `service_role`.** On production the probe answers
   TRUNCATE probes from the privilege system (`has_table_privilege`), which is
   exactly what the migration changes: set `t088.static_truncate = on`. The
   replica still executes them for real.
2. **An `EXECUTE` of a two-statement string.** Every probe is now one
   statement, with its other half seeded as a fixture.

## Applying it (owner-approved only)

1. **Apply** the least-privilege file. It sets `lock_timeout = 3s` itself, and
   aborts on its own if the result is not exactly the allowlist with reads
   unchanged.
2. **Apply** the TRUNCATE guard file (D-T088-3).
3. **Verify:**
   - Re-run the production probe (rolled back, static TRUNCATE). It must match
     `t088_expected_after.txt`.
   - Re-run the Security Advisor.
   - Submit the Card Brief form on the live site once and see "Subscribed".
4. **Rollback, if a page breaks:** the `GRANT` lines in `t088_replica_schema.sql`
   are production's pre-change grants, verbatim (add back `MAINTAIN`, which the
   PG16 copy omits). Re-running them restores the old state. The default
   privileges come back with `ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES / SEQUENCES TO anon, authenticated`.

## Decisions (owner review, 2026-10-14)

- **D-T088-1 — least-privilege migration:** approved in principle, pending
  sign-off on the production rehearsal results above.
- **D-T088-2 — default visibility of new tables:** **private by default**,
  explicit review for each grant. Done in the migration; existing reads
  unchanged.
- **D-T088-3 — pre-fight TRUNCATE protection:** approved. Applies with D-T088-1.
- **D-T088-4 — `hub_visits`:** revoke browser access (in the migration); **keep
  the table**.
- **D-T088-5 — Card Brief double opt-in:** required before any marketing email.
  Enforced in code now: `build/send-digest.js::MARKETING_SEND_BLOCKERS` holds
  T-090 and forces dry-run whatever secrets are set, and
  `tests/marketing-send-blocker.test.js` keeps it there. Building confirmation
  itself is T-090.
