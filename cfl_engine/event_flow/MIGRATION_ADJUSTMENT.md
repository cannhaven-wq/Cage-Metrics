# `fight_bout_order` needs one index change before it is applied

**For: the CLV session, which owns
[`research/clv/proposed_2026-09-16_event_flow.sql`](../../research/clv/proposed_2026-09-16_event_flow.sql).
This session did not edit that file.**

The migration is unapplied, so this costs nothing to change now and would cost a
corrupted ledger to change later.

---

## The defect, in one example

A bout is observed at position 5. The card is reshuffled and it moves to 6. The
card is reshuffled again and it moves **back to 5**.

The migration currently declares:

```sql
create unique index if not exists fight_bout_order_unique_idx
  on public.fight_bout_order (fight_id, source, bout_order);
```

with the comment "re-observing the same order is a no-op, a changed order
appends". That is true for the second observation and false for the third. The
third insert says `(fight, ufcstats_card, 5)` — a row that already exists, from
two reshuffles ago — so the unique index rejects it.

What is left on record is 5 and 6, with **6 carrying the later `observed_at`**.
And `v_clv_close_reference` resolves running order by:

```sql
select distinct on (o.fight_id) ...
order by o.fight_id, o.observed_at desc, o.id desc   -- latest observation wins
```

so it concludes the fight is bout 6. It is bout 5. The card moved back and the
ledger had no way to say so.

Everything downstream inherits that: `prev_completed_at` looks at the wrong
neighbouring bout, `is_first_bout` can be wrong, and a close reference gets
attached to the wrong fight. Silently — nothing raises, nothing looks odd, and
the reshuffle that caused it is exactly the situation where the order matters
most.

**The general rule this violates:** a ledger of observations must never let
history constrain what can be observed next. A position the card held before is
a position the card can hold again.

### It is worse than the 5 → 6 → 5 case

That example is the minimal one. In practice the index bites on the **first**
reshuffle of any card, because the ingester appends the **whole card** as one
observation — see "Why the whole card" in `bout_order.py`. When two prelims swap,
two bouts move and the other eleven do not, and those eleven are re-appended at
the positions they already hold. Every one of them collides.

So under the index as written, the ledger records a card's first observation and
then nothing, ever again, for that card. This is covered end to end by
`test_the_still_unique_ledger_halts_at_the_very_first_reshuffle`, with
`test_without_the_index_the_same_reshuffle_records_cleanly` as the control —
the only difference between the two is the index.

The index and complete-snapshot appends are simply incompatible. Appending only
the bouts that moved would dodge the collision for movers but not for a returning
bout, and it would give up the property that each observation reads back as one
coherent card. Dropping the index is the fix; appending partial cards is not.

---

## The change

Replace the unique index with a non-unique one, and (optionally) move the
uniqueness to a key that cannot recur.

```sql
-- WAS: forbids a bout from ever returning to a position it held before.
-- create unique index if not exists fight_bout_order_unique_idx
--   on public.fight_bout_order (fight_id, source, bout_order);

-- The lookup this index was really serving: "what is the latest observation
-- for this fight?" — which wants fight, source and time, not the position.
create index if not exists fight_bout_order_latest_idx
  on public.fight_bout_order (fight_id, source, observed_at desc, id desc);

-- Optional, and it is genuinely unique: one statement about a fight per
-- instant. `observed_at` defaults to now(), which is the TRANSACTION's start
-- time, so a whole card appended in one statement shares one timestamp and this
-- holds trivially. It stops the same batch being inserted twice inside one
-- transaction. It does NOT stop a doubled write from two separate calls —
-- nothing at the storage layer can, and that is the ingester's job, which it
-- does by reading the ledger before appending.
create unique index if not exists fight_bout_order_one_per_instant_idx
  on public.fight_bout_order (fight_id, source, observed_at);
```

The comment on the table should change with it. Suggested wording:

> Append-only record of where a fight sat in its card's running order.
> `bout_order` 1 is the first bout to walk out — the only one whose start is the
> card's scheduled start. Append-only, and **deliberately not unique on
> (fight_id, source, bout_order)**: a reshuffled card can return a bout to a
> position it held before, and a unique index there would reject that
> observation and leave the ledger asserting the intermediate position forever.
> The latest observation wins; the ones before it stay readable.

Nothing else in the migration needs to move. The append-only triggers, the RLS
grants, and `v_clv_close_reference` are all unaffected — the view's
`distinct on ... order by observed_at desc, id desc` is already the correct rule
and becomes correct *in practice* once the ledger can record the move back.

---

## What the ingester does about it meanwhile

`ingest_bout_order.py` no longer relies on the database to deduplicate:

* it **reads the latest observation per fight** before writing, compares it to
  the page, and appends the **whole card as one observation** only if something
  differs. An unchanged card writes nothing;
* the insert sends **no conflict resolution at all** — no
  `resolution=ignore-duplicates`, no `merge-duplicates`. A test asserts the
  `Prefer` header is exactly `return=representation`;
* if the unique index is still there, the append fails with a `23505`, and the
  ingester recognises it and exits **5** (`EXIT_LEDGER_SHAPE`) with a message
  naming this file. It does not retry, does not fall back, and does not write a
  partial card.

So applying the migration unchanged is safe in the sense that nothing corrupts —
the ingester stops instead of recording a wrong order. But it stops at the first
reshuffle of any card, so ingestion is effectively one-observation-per-card until
the index is dropped.

---

## Test coverage

`cfl_engine/event_flow/test_event_flow.py`, class
`TestReturnToAPreviousPosition`:

| test | what it proves |
|---|---|
| `test_the_move_back_is_appended_and_downstream_resolves_to_5` | 5 → 6 → 5: all three observations land, and the consumer's own rule resolves to **5** |
| `test_the_old_ignore_duplicates_behaviour_would_have_failed_this` | replays the old rule and shows it resolves to **6** — so the test above is testing something |
| `test_a_tie_on_observed_at_is_broken_by_id_not_by_luck` | two observations sharing a timestamp resolve deterministically, and not by arrival order |
| `test_out_of_order_arrival_still_resolves_to_the_newest` | resolution does not depend on the order PostgREST returns rows |
| `test_an_unchanged_card_appends_nothing` | the no-op is still a no-op |
| `test_one_bout_moving_appends_the_whole_card` | one mover appends a complete, self-consistent snapshot |
| `test_a_fight_that_left_the_card_is_reported_not_erased` | a dropped booking's last observation stands and is surfaced, not overwritten |

And in `TestIngestEventEndToEnd`, driving the runner itself against a fake
append-only ledger rather than the planner in isolation:

| test | what it proves |
|---|---|
| `test_five_six_five_through_the_runner` | three pages through `ingest_event`; a bout goes 2 → 1 → 2 and the ledger resolves to 2, with all twelve rows on record |
| `test_the_still_unique_ledger_halts_at_the_very_first_reshuffle` | with the index reinstated, the run exits 5 naming this file and writes **no partial card** |
| `test_without_the_index_the_same_reshuffle_records_cleanly` | the control — same reshuffle, index gone, both observations land |
| `test_re_running_an_unchanged_card_writes_nothing` | four runs of an identical card leave four rows |
| `test_the_whole_card_shares_one_observed_at` | an observation is one snapshot, not thirteen timestamps |
| `test_a_dry_run_writes_nothing_even_when_the_card_changed` | the dry run is genuinely dry |

The downstream check reimplements `distinct on (fight_id) order by observed_at
desc, id desc` in the test rather than importing `latest_state`, so a matching
bug in our own helper cannot hide.

---

## One thing this does not solve

When a booking falls off a card, its last observation stays on record and
`v_clv_close_reference` will still resolve a running order for it. The ledger
has no way to record "this bout left the card", and inventing one would mean
writing a fact nobody observed.

The ingester reports it — `N fight(s) were ordered before and are not on the
page now` — and the view could exclude such a fight by joining to whatever
retirement flag `fights` eventually carries (`add_bout_order_migration.sql`
proposes `is_active`, also unapplied). Raised here because it is the CLV
session's call, not this one's, and it is not urgent: a dead booking has no
result and no bell, so nothing scores it.
