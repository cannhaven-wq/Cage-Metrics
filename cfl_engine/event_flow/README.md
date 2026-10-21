# Event flow — what order a card runs in

## The one-sentence version

UFCStats prints every card in running order; this reads that page and writes the
order down, so CFL can say which fight is first, second, third — instead of
guessing from database ids.

## Why it matters

A UFC card has one published start time and then a queue. The first bout starts
when the schedule says. Every bout after it starts when the one before it ends.

Without a running order, a price captured at 9pm cannot be placed: was it before
the third fight or during it? That question is the difference between a
pre-fight price and an in-play one, and no amount of care downstream can answer
it from data that was never recorded.

`fights` has no running-order column. It has `is_main_event` — which names the
**last** bout — and nothing else.

## Why not just sort by id

Because the id is an insertion order, not a card order, and it is wrong exactly
when it matters most. On UFC 331 the ids happen to ascend down the card. On
event 113 (`UFC Fight Night: Song vs. Figueiredo`) the same three bouts exist
twice, once under ids 43/46/8780 and again under 27872/27877/27879, written
weeks apart. An id sort puts those in an order that has nothing to do with the
card, and does so silently.

A rebooked bout, a reshuffled card, a late addition — each breaks the id sort,
and each is the case where the order is worth having.

## What gets written

One row per bout in `fight_bout_order`:

| column | meaning |
|---|---|
| `fight_id` | the CFL fight |
| `event_id` | its card |
| `bout_order` | **1 = the first bout to walk out** |
| `source` | `ufcstats_card` |
| `observed_at` | stamped by the database, not by this script |

### The direction, because it is the easy thing to get backwards

UFCStats prints **main event first**. The ledger stores **first walkout first**.
So the page is read bottom-up:

```
page row 0   (main event)     ->  bout_order 13
page row 12  (first prelim)   ->  bout_order 1
```

There is a second, opposite convention in this repo: `fights.bout_order`, in the
unapplied `add_bout_order_migration.sql`, counts `1 = main event`. Same word,
opposite meaning. Nothing here writes that column. `test_the_two_conventions_are_opposites`
exists so a future join notices.

## What it refuses to do

* **Refuses a partial card.** If one bout on the page has no fight row, every
  bout below it would still get a number — a wrong one. So the card links
  completely or nothing is written for it.
* **Refuses a truncated page.** A row cut off mid-response would be dropped
  silently, and a dropped row does not look like a missing bout — it looks like
  a shorter card, which renumbers every bout on it.
* **Links by UFCStats fight id only.** Never by fighter name: eight pairs of
  fighters in this database share a name, and a near-miss here attaches a price
  to the wrong bout.
* **Never creates the table.** If `fight_bout_order` is missing, the run stops
  and names the migration.
* **Never rewrites.** It reads the latest observation for every bout, compares
  it to the page, and appends the **whole card** as one observation only if
  something differs. An unchanged card writes nothing. The insert carries no
  conflict resolution at all — see "A bout can return to a position it held
  before" below, which is the reason.
* **Never backfills.** A running order reconstructed today is not what we
  observed on the night. Past cards get no rows.
* **Dry run unless told otherwise.** `--execute` is required to write.

Dead bookings are the case this handles best by doing nothing: a booking that
fell off the card is still in `fights` — 36 such rows sit on settled 2026 cards —
and the page not listing it is the signal. It gets no order row.

## A bout can return to a position it held before

This is the one piece of the design worth reading twice.

A card is reshuffled and a bout moves from 5 to 6. It is reshuffled again and
moves **back to 5**. All three are real observations and all three have to be on
record, because the last one is the current answer.

An earlier version of this leaned on the ledger's unique index —
`(fight_id, source, bout_order)` — plus `resolution=ignore-duplicates`, on the
reasoning that re-observing the same order should be a no-op. It is a no-op when
the order has not changed. It is **data loss** when the order changed twice and
came back: the third insert collides with the row from two reshuffles ago, gets
dropped, and the ledger is left holding 5 and 6 with 6 carrying the later
timestamp. Every consumer that takes the latest observation then says 6. The
fight is at 5.

So:

* there is **no uniqueness on (fight_id, source, bout_order)** — the CLV
  session's migration still declares it and needs one index change, written up
  in [`MIGRATION_ADJUSTMENT.md`](MIGRATION_ADJUSTMENT.md);
* the insert sends **no conflict resolution**, only `return=representation`;
* "has this changed?" is answered by **reading the ledger** — the latest
  observation per fight — never by catching a constraint violation;
* if the unique index is still in place, the append fails, the ingester
  recognises the error and exits **5** naming the fix, and nothing is written —
  not even a partial card.

Worth knowing: because the append is a **complete card**, the index as written
bites on the *first* reshuffle of any card, not only on a returning bout. When
two prelims swap, the eleven bouts that did not move are re-appended at the
positions they already hold, and every one of them collides. The index and
complete-snapshot appends are incompatible; dropping it is the fix.

The general rule: **history constrains nothing about the future.** A position
the card held before is a position the card can hold again.

## Running it

```bash
python cfl_engine/event_flow/ingest_bout_order.py                   # dry run, upcoming cards
python cfl_engine/event_flow/ingest_bout_order.py --execute
python cfl_engine/event_flow/ingest_bout_order.py --event-id 4433 --execute
python cfl_engine/event_flow/ingest_bout_order.py --event-id 4433 --from-file page.html
```

`--execute` additionally requires the real-page check below. Dry runs never do.

Needs `SUPABASE_URL` and a service key (`SUPABASE_SECRET_KEY`,
`SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_SERVICE_KEY`). The ledger is revoked
from `anon`, so a publishable key would read zero rows with HTTP 200 and look
like a clean run — hence the hard exit.

Exit codes: `0` fine, `2` setup problem (including the real-page check not
done), `3` a card would not link completely, `4` the page could not be fetched
or read, `5` the ledger still carries the unique index that blocks a returning
bout.

**Cost: none.** UFCStats is public HTML on the host the event scraper already
polls. No API key, no credits, no paid tier.

## Tests

```bash
python -m unittest cfl_engine.event_flow.test_event_flow -v
```

47 tests, no network, no database. `TestReturnToAPreviousPosition` is the one to
read: it walks 5 → 6 → 5 and asserts the consumer's own resolution rule lands on
5, and a companion test replays the old behaviour to show it lands on 6.

## Verifying against a real page — required before the first write

**`--execute` is refused until this has been done.** It is not a note in a
README; it is a gate in the code, and the gate is currently shut.

The parser is tested against `fixtures/ufcstats_event_page.html`, which is
**hand-built to the UFCStats markup contract, not a captured page**: this
container cannot reach `ufcstats.com` (the host is not on the network egress
allowlist; `curl` returns `Host not in allowlist` and the fetch tool returns
`EGRESS_BLOCKED`). A fixture written from an assumption cannot test that
assumption — and the assumption in question is the one that matters most and is
invisible when wrong: **that UFCStats lists the main event first**, which is why
`bout_order` counts up from the bottom of the page. If that is backwards, every
card in the ledger is inverted, every close reference derived from it lands on
the wrong fight, and nothing fails.

The linkage half *is* verified against production: a page built from UFC 331's
thirteen real `ufc_fight_id` values links 13/13 and numbers the main event 13
and the opener 1.

Do this once, somewhere with UFCStats access — the event scraper's Railway
environment qualifies — against an **upcoming** card:

```bash
curl -s http://www.ufcstats.com/event-details/8a0a35e7c74bebcc > /tmp/ufc331.html
python cfl_engine/event_flow/ingest_bout_order.py --event-id 4433 --from-file /tmp/ufc331.html
```

It is a dry run and writes nothing. Read the printed order against the real
card. **Bout 1 must be the first prelim and the last line must be the main
event.** If it is the other way round, the flip in `bout_order.walkout_order` is
backwards and must be corrected before anything is written.

Then record what you saw, in `cfl_engine/event_flow/REAL_PAGE_CHECK.json`:

```json
{
  "ufc_event_id": "8a0a35e7c74bebcc",
  "cfl_event_id": 4433,
  "checked_by": "Reed Cannon",
  "checked_at": "2026-09-17",
  "main_event_bout_order": 13,
  "first_walkout_matchup": "Michael Aswell Jr. vs JooSang Yoo",
  "notes": "matched the card as listed on ufcstats.com"
}
```

All of `ufc_event_id`, `checked_by`, `checked_at`, `main_event_bout_order` and
`first_walkout_matchup` are required — a record that does not say which page was
read, by whom, when, and how the direction came out asserts nothing.

If the parser raises instead of printing an order, the markup contract has moved
and the fixture should be replaced with the real page, which is the better
fixture anyway.

## Where this sits

`fight_bout_order` is created by `research/clv/proposed_2026-09-16_event_flow.sql`,
which is **written and unapplied**. This ingester is the free half of what that
migration's closing note asks for:

> Running order is obtainable free: ufcstats lists a card in order, and the
> existing event scraper can write `fight_bout_order` on the same pass. It makes
> bout 1 scorable on every card.

The other half — exact bout completions, which is what makes bouts 2..N scorable —
is not free and is an open owner decision. Nothing here touches it.
