# Running order — staged activation runbook (T-096)

Approved 2026-10-15 for **staged** activation: nothing is scheduled until the
migration, the real-page check and the booking-safety checks have all passed,
and a single controlled run comes before the twice-daily schedule.

Order matters. Step 1 must come before step 2: the ingester calls
`require_ledger()` on **every** run, dry runs included, and stops with exit 2
when `fight_bout_order` does not exist.

## Step 0 — the bot wall (decision needed)

UFCStats fronts every page with a proof-of-work interstitial ("Checking your
browser…"). The event scraper on Railway passes it with
`cage-metrics-event-scrapper/challenge.py` (pure Python, honest
identifying User-Agent, the work the site's own JavaScript does). The
ingester's `fetch_page` is a plain GET and has no solver, so a live dry run
today returns the challenge page, `parse_event_page` finds no bout rows, and the
run ends `PAGE UNREADABLE` / exit 4 before printing any order.

Writing the equivalent solver into the ingester was refused by this session's
safety controls. Two ways forward, both the owner's call:

- **A. Port it** (≈60 lines mirroring `challenge.py`, stdlib `hashlib` +
  cookie jar, injectable for tests) — by the owner, or by Claude with an
  explicit permission rule for it.
- **B. Reuse it** — in `event-flow.yml`, check out the scraper repo, fetch the
  page with its `challenge.get()`, and hand the saved HTML to the ingester with
  `--from-file`. No new solver code; one more repo in the workflow.

`--from-file` runs are unaffected either way, which is how the real-page check
can also be done by hand (save the page from a browser, run the dry run on it).

## Step 1 — migration (manual, Supabase SQL editor)

File: `research/event-card/proposed_2026-10-15_card_running_order.sql`.

1. Open the Supabase SQL editor for project `uftancejftcryfvbggll`.
2. Paste the whole file and run it once. Expect NOTICEs from the two
   `drop trigger if exists` lines on first apply; that is why it is not run
   through the MCP tool.
3. Verify — every line must return exactly this:

```sql
select to_regclass('public.fight_bout_order') is not null                       as ledger_exists,      -- true
       to_regclass('public.v_card_running_order') is not null                   as view_exists,        -- true
       has_table_privilege('anon', 'public.fight_bout_order', 'select')         as anon_reads_ledger,  -- false
       has_table_privilege('authenticated', 'public.fight_bout_order', 'select') as auth_reads_ledger,  -- false
       has_table_privilege('anon', 'public.v_card_running_order', 'select')     as anon_reads_view,    -- true
       has_table_privilege('anon', 'public.v_card_running_order', 'insert')     as anon_writes_view,   -- false
       (select count(*) from public.fight_bout_order)                           as rows_now;           -- 0
select indexname from pg_indexes where tablename = 'fight_bout_order' order by 1;
-- fight_bout_order_card_idx, fight_bout_order_latest_idx,
-- fight_bout_order_one_per_instant_idx, fight_bout_order_pkey — and NO fight_bout_order_unique_idx
select tgname from pg_trigger where tgrelid = 'public.fight_bout_order'::regclass and not tgisinternal order by 1;
-- fight_bout_order_block_delete, fight_bout_order_block_update
```

4. Re-running the file is safe (verified twice-applied on a throwaway
   Postgres). Rollback, if ever needed, is `drop view
   public.v_card_running_order; drop table public.fight_bout_order;` — the
   ledger is append-only by trigger, so nothing else depends on it yet.

The CLV migration (`research/clv/proposed_2026-09-16_event_flow.sql`) creates
the same table with `create table if not exists` and the same index names, so
applying it later is a no-op for this table.

## Step 2 — dry run against a real card (GitHub Actions)

The workflow reads the `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` repo
secrets — the same two `dead-man.yml` and `alerts.yml` use on their successful
runs, so they exist. (This session cannot list secrets; the proxy refuses that
path.)

1. Actions → **Event flow — bout order** → Run workflow:
   `event_id` = `4368` (UFC Fight Night: Buckley vs. Malott, 2026-10-17, or
   the next upcoming card), `execute` **unchecked**.
2. The log prints, for the card: `N bouts, first walkout first:` then one line
   per bout, then the ledger comparison, then any retirement lines, then
   `DRY RUN — would append N row(s)`.

## Step 3 — independent verification of the order (a person)

Open `http://www.ufcstats.com/event-details/<ufc_event_id>` in a browser
(event 4368 is `55e94a9b525dcf45`) and, ideally, the UFC's own event page.

- **Direction:** the dry run's **bout 1 must be the first prelim** and its
  **last line the main event**. If it is the other way round, stop: the flip in
  `bout_order.walkout_order` is backwards and every card would be inverted.
- **Completeness:** the bout count must equal the number of bouts on the page.
  Event 4368 has 13 active bookings and 3 retired ones (`47881`, `48644`,
  `50990`); expect `note: 3 fight row(s) on this event are not on the page
  (dead bookings)` and nothing else unlisted.
- **Linkage:** no `REFUSED` line. A refusal means a bout on the page has no
  `fights` row yet (run the event scraper first) — the ingester never writes a
  partial card.

## Step 4 — record the check

Commit `cfl_engine/event_flow/REAL_PAGE_CHECK.json`:

```json
{
  "ufc_event_id": "55e94a9b525dcf45",
  "cfl_event_id": 4368,
  "checked_by": "<name>",
  "checked_at": "2026-10-16",
  "main_event_bout_order": 13,
  "first_walkout_matchup": "<first prelim as printed>",
  "notes": "matched the card as listed on ufcstats.com"
}
```

All five named fields are required; `--execute` refuses without them.

## Step 5 — booking safety (what the dry run must and must not say)

Reviewed 2026-10-15 against `retirement.py`, `ingest_bout_order.py` and their
tests. Today **nothing automated writes `fights.is_active`**: no scraper code
sets it, no trigger, no function (production checked). The 8 inactive rows were
set by hand. So the ingester would become the only writer, and these are the
rules it applies — each covered by a test in `test_retirement.py` /
`test_event_flow.py`:

| Rule | Why it cannot retire a live booking |
|---|---|
| A booking is retired only when **absent from the latest two complete card observations in a row**, and only if it appeared in an earlier one. | One bad read, truncated page or half-built card cannot trip it. |
| A failed or refused scrape produces **no observation**. | Absence has to be observed twice, on cards actually read. |
| A booking **never seen on any observation is not a candidate**. | A newly announced bout that is not yet on the page is left alone. |
| A retired booking that reappears on the page is **reactivated**. | Retiring is not one-way; nobody has to notice by hand. |
| The only write is `PATCH {is_active}` on that one row. **Nothing is deleted, no other column is touched**, and it runs only after a persisted append under `--execute`. | A dry run prints `would set is_active=…` and writes nothing. |

On the **first** run of any card there is one observation, so no retirement can
be confirmed: the dry run must print no `stale CONFIRMED` line. The three
retired bookings on 4368 are already `is_active = false` and absent from the
page, so they can never be "reactivated" by mistake, and they are not on the
page so they will not be ordered.

**Do not proceed if** the dry run proposes `is_active=false` for any fight that
is on the page, or `is_active=true` for a fight that is not.

## Step 6 — controlled single-event execution

With steps 1–5 passed: Run workflow with `event_id` = `4368`, `execute`
**checked**. Then verify:

```sql
select count(*), count(distinct observed_at), min(bout_order), max(bout_order)
from public.fight_bout_order where event_id = 4368;
-- 13, 1, 1, 13
select bout_order, fight_id from public.v_card_running_order where event_id = 4368 order by 1;
-- 13 rows, 1..13, fight 46774 (the main event) at 13
select id, is_active from public.fights where event_id = 4368 order by id;
-- is_active unchanged from before the run
```

## Step 7 — switch the pages on

Claude: set `RUNNING_ORDER_LIVE = true` in `card-research.js` (one line; the
test that pins it off is updated in the same commit), add
`v_card_running_order` to the T-088 grant list via the migration file (already
there) and to `verify-live`, merge, run `verify-live`. Card Lab and the event
page then show "Bout 7 of 13", true walkout order, and "Official running order,
read from the UFCStats card on <date>".

## Step 8 — schedule

Only after step 7 is live and one more manual run has written nothing for an
unchanged card: uncomment the `schedule:` block in `.github/workflows/event-flow.yml`
(`20 7,19 * * *`). Cost: GitHub Actions minutes; no API credits.
