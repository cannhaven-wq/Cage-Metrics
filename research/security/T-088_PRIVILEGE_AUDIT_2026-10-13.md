# T-088 — Who can write to the database from a browser? (audit and plan, 2026-10-13)

**Status:** audit done; plan rehearsed; **nothing applied.** Applying the
migration is an L3 gate (`coordination/CRITICAL_GATES.md` item 5). The owner
decides; the decisions are listed at the end.

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
goes. New tables stop being born writable. **Every RLS policy stays exactly as
it is.**

## Rehearsal (done — on a replica, never on production)

`tests/test_t088_rehearsal.py` builds a throwaway local Postgres from
[`t088_replica_bootstrap.sql`](t088_replica_bootstrap.sql) and
[`t088_replica_schema.sql`](t088_replica_schema.sql) — production's schema,
policies, triggers and exact grants, captured read-only on 2026-10-13, no rows.
Then [`t088_probe.sql`](t088_probe.sql) runs 47 probes as the real roles with
real JWT subjects. Each probe runs in a savepoint and the whole run rolls back.

| | before | after |
|---|---|---|
| 28 legitimate actions: signup, Card Brief (new and repeat), waitlist, analytics, unsubscribe, public reads, profile, My Book, watchlist, alerts, alert settings, deliveries, backend writers | all work | **all work** |
| TRUNCATE `pre_fight_snapshots` / `fights` / `profiles` / `user_bets` / `email_subscribers` | allowed | denied |
| forged unsubscribe token · rewrite `profiles.email` · `hub_visits` insert · `setval` | allowed | denied |
| update `events` · unsubscribe everyone | refused by RLS (zero rows) | denied |
| self-admin · bet as another user · forge an alert delivery · write through the invoker view | denied | denied |
| edit another member's bets | zero rows (RLS) | zero rows (RLS) — correct: members keep UPDATE on their own |
| a brand-new table: can a visitor write it? | yes | **no** (still readable, D-T088-2) |

Also proved on the replica:
- **Idempotent.** Both files apply twice cleanly.
- **The assertion block bites.** A leaked TRUNCATE plus a column UPDATE, a dropped watchlist grant, and a removed public read each abort the migration. Each one is rolled back.
- **The TRUNCATE guard holds.** It blocks `service_role` and the owner, and the snapshot writer's INSERT still works.

The expected after-state is pinned in
[`t088_expected_after.txt`](t088_expected_after.txt).
`tests/t088-least-privilege.test.js` keeps the grants and the site in step: a
new browser write without a grant fails CI.

## Applying it (owner-approved only)

1. **Production rehearsal (optional; nothing persists).** In one `execute_sql` call, send:
   - the body of the least-privilege file without `BEGIN;`/`COMMIT;`;
   - then the body of `t088_probe.sql`.

   The probe ends by raising `T088_RESULT`, which rolls the migration back with it. Compare the lines to `t088_expected_after.txt`.
2. **Apply** the least-privilege file. It aborts on its own if anything is off.
3. **Apply** the TRUNCATE guard file (separate decision, D-T088-3).
4. **Verify:**
   - Re-run the probe on its own. It rolls back, and must still match `t088_expected_after.txt`.
   - Re-run the Security Advisor.
   - Submit the Card Brief form on the live site once and see "Subscribed".
5. **Rollback, if a page breaks:** the `GRANT` lines in `t088_replica_schema.sql`
   are production's pre-change grants, verbatim (add back `MAINTAIN`, which the
   PG16 copy omits). Re-running them restores the old state. The default
   privileges come back with `ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES / SEQUENCES TO anon, authenticated`.

## Decisions for the owner

- **D-T088-1 — apply the least-privilege migration?** Recommended: **yes.** It
  removes three live browser write paths and one latent one. The 28-action
  rehearsal shows it keeps everything the site does.
- **D-T088-2 — should new tables also stop being *readable* by default?**
  Recommended: **not yet.** This plan keeps today's convention, where a new
  table is readable but RLS decides which rows. Making reads explicit too is
  stricter. It also means every future public view needs a GRANT, and forgetting
  one breaks a page with "permission denied". Decide this once, then write it
  into CLAUDE.md.
- **D-T088-3 — add the TRUNCATE guard to `pre_fight_snapshots`?** Recommended:
  **yes.** It is the evidence table, and its sister tables already refuse
  TRUNCATE.
- **D-T088-4 — `hub_visits`.** Recommended: revoke now (in the migration), then
  drop the table and its policy later once it is confirmed dead. Dropping it
  removes data, so it is L3 on its own.
- **D-T088-5 — confirm Card Brief addresses before the first send.** Anyone can
  type anyone's address. That is how signup forms work, but sending mail to an
  address nobody confirmed is a deliverability and legal risk. Recommended:
  ask the address to confirm itself (double opt-in) before the first Brief goes
  out. That is a product and legal call, and it belongs with T-054.
