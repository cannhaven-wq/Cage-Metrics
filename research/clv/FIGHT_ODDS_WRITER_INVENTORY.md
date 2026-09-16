# Every writer to `fight_odds`, 2026-09-16

**Why this exists.** `research/clv/proposed_2026-09-16_fight_odds_immutability.sql`
is the one CLV-001 migration that is **not additive**: it adds triggers to a
table that is already being written to, and it changes what an existing writer
is allowed to do. The migration's own header says this inventory has to happen
first, and ChatGPT's review made it the precondition for applying it.

The consequence of missing a writer is operational, not statistical: that writer
starts failing the moment the migration lands — and the ones here run on crons.

**Method.** Read-only. Every repository on the account was cloned shallow and
grepped for `fight_odds`, then every hit was classified by verb. No database was
queried; no repository was modified. A grep can only find writers that live in a
repository, which is the limit stated at the bottom.

**Result: one blocker.** Everything else either appends or touches only the two
derived flags the trigger whitelists.

---

## The blocker

### `cage-metrics-odds-scrapper` — `backfill_odds.py:457`

```python
supabase.table("fight_odds").delete()\
    .eq("fight_id", fight_id).eq("book_id", book_id)\
    .or_("is_opener.eq.true,is_closer.eq.true").execute()
```

`upsert_opener_closer()` **deletes** the existing opener/closer rows for a
(fight, book) and re-inserts them, and its docstring says why: *"Deletes existing
opener/closer rows ... then inserts fresh ones. Idempotent."*

Under the migration this raises, and the function fails on its first call.

**This is a genuine design conflict, not an oversight to route around.** The
delete-before-insert is what makes the backfill re-runnable, and an append-only
table cannot offer that. R-01 is explicit — *"A quote that turns out to be
garbage is excluded at scoring time by a written rule, never deleted"* — so the
append-only version of this function appends a second observation and lets the
reader resolve which is current, exactly as `fight_bout_completions` does.

Three ways forward, and the choice is the owner's:

1. **Retire it.** It is a historical backfill of BestFightOdds opener/closer
   pairs, not a cron. If it has done its job, it can stop being runnable.
2. **Make it append-only.** Drop the delete; insert the new pair; readers take
   the latest observation. Costs nothing at read time and matches the ledger
   pattern already used elsewhere.
3. **Apply the migration knowing it breaks.** Defensible only if (1) is true in
   practice, and it should be a decision rather than a discovery.

**Worth knowing while deciding:** this function writes `captured_at` as
`1970-01-01T00:00:00Z` and `…:01Z` — commented in the source as *"placeholder;
opener time isn't precisely known"*. That is the origin of the 30,724 epoch-
stamped rows R-13 excludes. Nothing it writes can ever be scored by CLV-001, in
either direction, so the blocker is about not breaking a tool — it has no
bearing on the measurement.

---

## Everything else, and why it is fine

### `Cage-Metrics` (this repo)

| where | verb | verdict |
|---|---|---|
| `build/fetch-odds.js:1443` | `INSERT` (chunked) | append — unaffected |
| `build/fetch-odds.js:974,980` | `UPDATE {is_closer}` | **whitelisted** |
| `build/fetch-odds.js:~1418` | sets `is_opener` on rows *before* insert | part of the INSERT, not an UPDATE |
| `build/factor-rates.js:316` | `SELECT` | unaffected |
| `cfl_engine/*` | `SELECT` | unaffected |

No DELETE anywhere in this repo. `build/test-fetch-odds.js` pins both facts, so
a future edit that starts writing another column fails the suite rather than the
cron.

### `cage-metrics-odds-scrapper` — the rest of it

| where | verb | verdict |
|---|---|---|
| `odds_scraper.py:517` | `INSERT` | append — unaffected |
| `backfill_odds.py:499` | `INSERT` | append (epoch-stamped, permanently unscorable) |
| `polymarket/scrape.py:321` | `INSERT` | append |
| `polymarket/scrape.py:355` | `UPDATE {is_opener}` | **whitelisted** |
| `polymarket/scrape.py:360,361` | `UPDATE {is_closer}` | **whitelisted** |
| `polymarket/backfill_history.py:451` | `INSERT` | append |
| `polymarket/backfill_history.py:464` | `UPDATE {is_opener}` | **whitelisted** |
| `web/app.py:231`, `model/**`, `diagnose_unmatched.py` | `SELECT` | unaffected |

**This is the useful corroboration.** Four independent update sites, written by
somebody who had never heard of this migration, touch `is_opener` and `is_closer`
and nothing else. The whitelist was chosen from first principles — derived flags,
recomputable, carrying no observation — and the code that already exists agrees
with it. If the whitelist were wrong, this is where it would have shown.

Polymarket rows are excluded from CLV-001 by kind anyway (Q-03, exchanges and
prediction markets), so these writers and the measurement never meet.

### `cage-metrics-scrapper`

No writes to `fight_odds`. Fighter-level scraping only.

### `cage-metrics-event-scrapper`

No reference to `fight_odds` at all.

### `cfl-snapshotter`

No reference to `fight_odds` at all. It reads `model_predictions` and writes the
legacy `predictions` table; its cron has been dead since 2026-05-29.

---

## A finding that is not about this migration

**`cage-metrics-odds-scrapper` is not in `CLAUDE.md`'s "Related repos" list.** That
list names Cage-Metrics, `cage-metrics-scrapper`, `cage-metrics-event-scrapper`
and `cfl-snapshotter` — and the repository that does most of the writing to
`fight_odds` is absent from it.

Every reasoning step in this project that started from "the repos are X, Y and Z"
was working from an incomplete list. Nothing downstream turned out to be wrong,
but that was luck rather than method: it is exactly the shape of the mistake that
would have made this inventory come back clean and be wrong.

Adding it to `CLAUDE.md` is a one-line edit and is left to the owner, since that
file is the project's canonical description rather than working notes.

---

## What this inventory cannot see

- A writer that is not in a repository on this account: a Supabase SQL editor
  session, a manual `psql`, a Railway console, an Edge Function, a scheduled job
  defined outside git. Only the owner can rule those out.
- A repository the account cannot list.
- Anything added after 2026-09-16.

The migration itself is the backstop for all three: a writer nobody knew about
starts erroring loudly instead of quietly rewriting evidence, which is the
behaviour R-01 asks for. **Loud is the intended failure mode — but it is better
to be loud on a Tuesday afternoon than at 23:00 UTC on a card night**, which is
the argument for landing it between cards.
