# Running order — the migration, ready to apply (T-096 1a, T-032)

Written 2026-10-21. **Nothing here has been applied.** Applying it is L3
(`coordination/CRITICAL_GATES.md` item 5: it creates append-only tables, which a
`git revert` cannot undo once they hold rows). The owner's act is: **approve,
then run one file.**

## In plain English

It creates the place CFL writes down what order a card runs in, a read-only
view the site can use to say "Bout 7 of 13", and a log that records **why** a
booking was taken off a card before the flag on it ever changes. It changes no
existing table, deletes nothing, and costs nothing.

Applying it does **not** make the running order appear by itself. The pages stay
switched off (`RUNNING_ORDER_LIVE = false`) until a real card is in the ledger,
and the ingester's source still has to be chosen: UFCStats does not serve
GitHub's runners; ESPN's public scoreboard does, and passed the real-page check
(see "The source" below) — using it on a schedule is a second owner decision.

## The file

[`apply_2026-10-21_running_order.sql`](apply_2026-10-21_running_order.sql) — one
transaction. It replaces `proposed_2026-10-15_card_running_order.sql` (now a
pointer that defines nothing).

| object | what | who can reach it |
|---|---|---|
| `fight_bout_order` | the running-order ledger, **verbatim** from the CLV migration §1 (same columns, index names, triggers), so applying `research/clv/proposed_2026-09-16_event_flow.sql` later is a no-op for it | `service_role`: SELECT, INSERT. Browser roles: nothing |
| `fight_booking_status_log` | **new (T-032).** One row per `fights.is_active` change Event Flow makes, appended before the flag moves, naming the card observations it rests on. A trigger refuses evidence the ledger does not support (fewer than two absences, an instant that is not an observation of that event, an observation that still holds the fight, a newer observation than the evidence) | `service_role`: SELECT, INSERT. Browser roles: nothing |
| `v_card_running_order` | latest complete card per event, active bookings only — unchanged from 2026-10-15 | `anon`, `authenticated`: SELECT only |

Both tables reject UPDATE, DELETE **and TRUNCATE** for every role (row triggers
do not fire on TRUNCATE, so it gets its own statement-level trigger).

**Preconditions it checks and refuses on:** `fights` exists and has `is_active`
(applied 2026-09-19); the old `fight_bout_order_unique_idx` is absent.

**Verification inside the transaction:** before `commit`, a block checks every
privilege, the exact index set, RLS, every trigger, and the view's columns. If
any check fails it raises and **the whole file rolls back** — nothing is left
half-applied (`tests/test_running_order_migration.py` proves the rollback).

**Re-running is safe:** applied twice to a throwaway Postgres 16, the second run
changes nothing (schema fingerprint identical, data kept). It is also compatible
with the CLV event-flow migration applied before or after it.

## Apply procedure

Between cards is preferred (not inside 48 hours of one) only because the
`lock_timeout` is 3 s; the file touches no table the odds job writes.

1. Open the Supabase SQL editor for project `uftancejftcryfvbggll` (or use
   `psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f research/event-card/apply_2026-10-21_running_order.sql`).
   **Not** the Supabase MCP tool: the `if not exists` / `drop trigger if exists`
   lines raise NOTICEs, which hang it (CLAUDE.md, "Supabase MCP gotcha").
2. Paste the whole file and run it once. Success ends in `COMMIT`. Any
   `ERROR: running-order migration verification failed: …` or
   `precondition: …` means nothing was applied; send the message back.
3. Run the checklist below. Every line must match.

## Verification checklist (run after applying)

```sql
select to_regclass('public.fight_bout_order')         is not null as ledger,       -- t
       to_regclass('public.fight_booking_status_log') is not null as decision_log, -- t
       to_regclass('public.v_card_running_order')     is not null as view,         -- t
       to_regclass('public.fight_bout_order_unique_idx') is null   as no_old_idx,   -- t
       has_table_privilege('anon', 'public.fight_bout_order', 'select')                  as anon_ledger,  -- f
       has_table_privilege('authenticated', 'public.fight_bout_order', 'select')         as auth_ledger,  -- f
       has_table_privilege('anon', 'public.fight_booking_status_log', 'select')          as anon_log,     -- f
       has_table_privilege('anon', 'public.v_card_running_order', 'select')              as anon_view,    -- t
       has_table_privilege('authenticated', 'public.v_card_running_order', 'select')     as auth_view,    -- t
       has_table_privilege('anon', 'public.v_card_running_order', 'insert')              as anon_write,   -- f
       has_table_privilege('service_role', 'public.fight_bout_order', 'insert')          as writer,       -- t
       has_table_privilege('service_role', 'public.fight_bout_order', 'truncate')        as writer_trunc, -- f
       (select count(*) from public.fight_bout_order)                                    as ledger_rows,  -- 0
       (select count(*) from public.fight_booking_status_log)                            as log_rows;     -- 0

select indexname from pg_indexes where tablename = 'fight_bout_order' order by 1;
-- fight_bout_order_card_idx, fight_bout_order_latest_idx,
-- fight_bout_order_one_per_instant_idx, fight_bout_order_pkey

select tgrelid::regclass, tgname from pg_trigger
where tgrelid in ('public.fight_bout_order'::regclass, 'public.fight_booking_status_log'::regclass)
  and not tgisinternal order by 1, 2;
-- fight_bout_order: block_delete, block_truncate, block_update
-- fight_booking_status_log: block_delete, block_truncate, block_update, evidence

-- Nothing that existed before moved:
select count(*) filter (where is_active = false) as inactive_bookings from public.fights;
-- the same number as before applying (8 on 2026-10-15)
```

Then, from a browser or `curl` with the publishable key, `GET
/rest/v1/v_card_running_order?limit=1` returns `[]` with HTTP 200 (empty, not
404) and `GET /rest/v1/fight_bout_order` returns `401`/`403` or `[]`.

## Rollback and forward-fix

- **Before the first ingester write** (both tables empty): rollback is
  ```sql
  begin;
  drop view public.v_card_running_order;
  drop table public.fight_booking_status_log;
  drop table public.fight_bout_order;
  drop function public.fight_bout_order_no_rewrite();
  drop function public.fight_booking_status_log_no_rewrite();
  drop function public.fight_booking_status_log_check_evidence();
  commit;
  ```
  Nothing else depends on them: `card-research.js` is off, and `fetch-odds.js`
  only reads `fight_bout_order` to detect a card in flow, degrading to "unknown"
  when it is absent.
- **After rows exist:** do not drop. They are observations and decisions,
  append-only by design; a dropped ledger is lost evidence (the same reason
  `pre_fight_snapshots` is never rewritten). Fix forward with a new migration
  (`create or replace view`, an added index, a new trigger) and leave the rows.
- A wrong `is_active` set by the ingester is undone by the ingester itself when
  the bout reappears on the card (reactivation, recorded in the log), or by hand
  with `update fights set is_active = true where id = …` plus a `manual` row in
  `fight_booking_status_log` saying why.

## After applying — the rest, in order

| step | what | status |
|---|---|---|
| 1 | Real-page check → `cfl_engine/event_flow/REAL_PAGE_CHECK.json` | **done for ESPN** (run [39623974340](https://github.com/cannhaven-wq/Cage-Metrics/actions/runs/39623974340), committed byte-exact); **blocked for UFCStats** |
| 2 | Owner: choose the source (ESPN, or stay on UFCStats and accept it cannot run from Actions) | `SOURCE_EVALUATION_2026-10-21.md` |
| 3 | Dry run: Actions → *Event flow — bout order* → `event_id` = next card (4542 = UFC 333), `source` = `espn`, `execute` unchecked. Expect `14 bouts from ESPN event … [confirmed …]`, no `REFUSED`, and `note: 1 fight row(s) … not on the page` (48648, retired) | after 1 and 2 |
| 4 | One `execute` run, then PR #81's runbook step 6 checks (`source = 'espn_scoreboard'`) | 3 |
| 5 | `RUNNING_ORDER_LIVE = true` in `card-research.js` (+ its test), verify-live | 4 |
| 6 | Schedule: in `.github/workflows/event-flow.yml` replace `# schedule:` / `#   - cron: "20 7,19 * * *"` with `schedule:` / `  - cron: "20 7,19 * * *"`, and set the `SOURCE` default to `espn` | 5 and one unchanged manual run writing nothing |

## The source, with evidence (2026-10-21)

- **UFCStats does not serve GitHub's runners.** Runs
  [39620237572](https://github.com/cannhaven-wq/Cage-Metrics/actions/runs/39620237572) and
  [39620364912](https://github.com/cannhaven-wq/Cage-Metrics/actions/runs/39620364912):
  both listings and the event page for UFC Fight Night: Buckley vs. Malott
  (`55e94a9b525dcf45`) answered **HTTP 200 with a 2,998-byte
  `<title>Loading…</title>` anti-bot page**, no fight rows. The check records
  that as `source_blocked` and fails; no record was or may be produced from it.
- **ESPN `site.api.espn.com`: HTTP 403.** **ESPN `site.web.api.espn.com`: HTTP 200**,
  every bout in walkout order with section start times.
- **Wikipedia (MediaWiki API): HTTP 200** — used as the independent cross-check.
- **UFC.com: not probed** — its Terms of Use prohibit automated access.
- The ESPN check passed: the titled main event is last on both cards (13/13,
  14/14) and Wikipedia agrees bout for bout on both.

Full write-up: [`SOURCE_EVALUATION_2026-10-21.md`](SOURCE_EVALUATION_2026-10-21.md).
