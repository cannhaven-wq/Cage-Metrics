# A fight that leaves the card

**Written 2026-09-18, from a live instance.** Design and investigation only —
**no production record has been modified**, and nothing here is applied.

## What happened

Tier 1 validation parsed the real UFCStats page for **UFC 331** (CFL event
`4433`). The page carried **twelve** bouts. `fights` carried **thirteen**.

The extra row was `cfl_fight_id 47328` — **Renato Moicano vs Brian Ortega**.
Ortega withdrew injured, so the bout was cancelled and UFCStats dropped it from
the card. Confirmed by the owner.

**This is not a parser defect and not a scrape anomaly.** It is the normal
lifecycle of a booking, which the data model has no way to express:

```
announced  ->  stored in `fights`  ->  fighter withdraws
           ->  disappears from the live card  ->  ...and then what?
```

There is no "and then what". The row stays, looking exactly like a live booking.

## Why it matters more than a cosmetic count

`bout_order = n_bouts - page_index`. If a cancelled booking is ever allowed to
inflate `n_bouts`, **every bout on the card is numbered one too high** — the main
event lands at 13 on a 12-bout card — and nothing raises. Everything downstream
inherits it: `prev_completed_at` reads the wrong neighbouring bout, `is_first_bout`
is wrong, and a CLV close reference attaches to the wrong fight.

The current code is already correct here: the running order is computed over the
**page's** bouts, never the database's. Two regression tests now pin that
(see below), and a mutation check confirms they fail if the count is ever taken
from `fights` instead.

So the arithmetic is safe. What is not handled is everything *else* that reads
`fights` and cannot tell a cancelled booking from a live one.

---

## 1. How a removed booking should be detected

**The detector already exists and is already computed.** `plan_append` in
`bout_order.py` returns `stale_fights`: fights that have a bout-order observation
on record and are absent from the current page. `ingest_bout_order.py` reports it
(*"N fight(s) were ordered before and are not on the page now"*) and then does
nothing with it.

That is the right signal, and it should be the only one, because it is the only
one grounded in an observation. Three weaker alternatives, and why not:

| candidate | why not |
|---|---|
| past event + `winner_id is null` | conflates cancellations with genuinely ungraded history — **192 such rows exist, the earliest from 1995-04-07**. It cannot tell the two apart |
| fighter appears twice on one card | a good *corroborating* signal, and how the existing `add_bout_order_migration.sql` cleanup works, but it only catches opponent-swaps, not a bout that vanishes outright |
| absent from a single page fetch | a fetch failure is not a cancellation. Requires a complete, parsed card — which is exactly what `stale_fights` is derived from |

**The rule to implement:** a booking is a candidate for retirement when it has at
least one bout-order observation and is absent from the **latest complete card
observation** for its event. Retirement is then a decision recorded against that
observation, never a silent side effect of one page load.

**A caution that is not hypothetical.** A card is not fully announced at once;
early-announced bouts appear over weeks. A fight with **no** prior observation
that is absent from the page has not been removed — it was never seen. Only a
fight that was observed and then vanished is a candidate. `stale_fights` already
encodes exactly that distinction.

## 2. Preserving the history

Nothing is deleted, and the retirement is not a rewrite of the booking:

- **`fight_bout_order` is append-only.** Every observation stands, including the
  last one that placed the withdrawn fight on the card. That is how "this fight
  was booked at position 7 on the 14th" stays answerable.
- **The `fights` row stays.** Locked picks, `pre_fight_snapshots` rows and
  captured odds all reference it by id. Deleting it would orphan evidence that is
  append-only by design and cannot be rewritten to point elsewhere.
- **`model_picks`, `pre_fight_snapshots` and `fight_odds` are untouched.** A
  prediction published against a bout that was later cancelled *was* published.
  Retracting it retroactively is exactly the revision the pre-fight record exists
  to prevent.

What changes is one flag on the booking plus the reason and the instant — not the
booking itself.

## 3. What must exclude inactive fights

`add_bout_order_migration.sql` already proposes the column, and it is **unapplied**
(verified: `is_active` is not on `fights` today):

```sql
ALTER TABLE fights ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;
```

Its comment already states the intent: *"False when the booking fell off the
UFCStats event page... Rows are never deleted — locked picks reference them."*

**The frontend is already defending.** `_shared.js` filters `f.is_active !== false`
and its comment notes the column may not exist. So the site is written against a
column that was never added — which is the shape of a defence that silently does
nothing.

Consumers to audit, in the order they matter:

| consumer | today | wanted |
|---|---|---|
| bout count / running order | already page-derived — **safe** | keep, and pin with tests |
| `_shared.js` card rendering | filters `is_active !== false`, column absent so no-op | works once applied |
| predictions / `model_picks` | no filter | do not publish a pick for a retired booking |
| odds capture (`fetch-odds.js`) | no filter | stop spending credits on a cancelled bout |
| `v_clv_close_reference` | resolves the latest **complete card**, so a fight absent from it already drops out — **safe** | confirm, no change expected |
| Prop Board / snapshots | no filter | exclude from the next card's projections |

**Retired means "not on the current card", never "did not happen".** A retired
booking must stay fully visible in history and in any record that already
referenced it.

## 4. Are the other stale bookings the same class?

Read-only inspection of recent cards. The pattern is consistent, and it is the
same normal class — an opponent change, leaving the superseded booking behind:

| event | superseded booking (unsettled) | what actually happened (settled) |
|---|---|---|
| 2626 | Kody Steele vs Gauge Young | Gauge Young vs Stan Dorsainvil |
| 4224 | Liu Ce vs Junior Tafa | Liu Ce vs Levi Rodrigues Jr. |
| 4225 | Nathaniel Wood vs Mairon Santos | Nathaniel Wood vs Pavel Andrusca |
| 4282 | Kelvin Gastelum vs Yousri Belgaroui | Yousri Belgaroui vs Djorden Santos |
| 4282 | Yair Rodriguez vs Jean Silva | Jean Silva vs Jose Delgado |

Every superseded row carries **no winner**; every replacement is settled. One
fighter is common to both. This is a withdrawal or opponent swap in each case,
and **no second defect class appears** in this sample.

Event 4282 also shows the knock-on the existing migration's cleanup addresses:
**two rows on one card both flagged `is_main_event`**, because the superseded
main event kept its flag when the replacement arrived.

**Scale, measured read-only:**

| | |
|---|---|
| past-event fights with no winner | **192**, across 157 events |
| earliest | **1995-04-07** — so this population is *not* purely cancellations |
| predictions attached to them | 894 |
| odds rows attached to them | 10,478 |
| fights on future cards | 63 |

**The 1995 date is the important one.** It shows why "past and unsettled" cannot
be the detector: the population mixes real cancellations with ungraded history
from before results were captured. Retiring on that signal would mark thirty
years of legitimate fights inactive. The observation-based detector in §1 does not
have this problem, because it only ever considers fights that were observed on a
card and then left it.

## 5. Regression tests — added

In `test_event_flow.py::TestIngestEventEndToEnd`:

- **`test_a_cancelled_booking_does_not_inflate_the_running_order`** — five
  bookings in the database, four bouts on the page. Asserts four rows written,
  contiguous orders `[1,2,3,4]`, the main event at 4 and not 5, and that the
  cancelled booking never receives a `bout_order`. This is UFC 331 in miniature.
- **`test_a_booking_that_disappears_between_refreshes_is_reported_not_erased`** —
  announced and observed, then gone on the next refresh. Asserts its last
  observation still resolves, that the remaining bouts renumber over the shorter
  card, and that it does not join the current card.

Both were **mutation-checked**: with `n` taken from the database count instead of
the page, both fail. They are guards, not decoration.

---

## What is NOT proposed here

- No production record is modified. Nothing is retired.
- No migration is applied, including `add_bout_order_migration.sql`.
- The one-time cleanup in that migration retires superseded bookings by
  `UPDATE`. It should be read on its own terms before it runs — it is the same
  class of change as the CLV immutability trigger, in that it alters the meaning
  of existing rows, and 894 predictions and 10,478 odds rows point at the
  population it touches.
- Whether a retired booking should be *visible* anywhere in the UI, and in what
  words, is a copy decision under `COPY_STYLE.md`, not a schema decision.
