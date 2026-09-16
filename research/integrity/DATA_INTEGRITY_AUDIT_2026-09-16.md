# Data-integrity audit — 2026-09-16

**Read-only.** Every number here came from a `SELECT` against the production
database. Nothing was written, nothing was migrated, nothing was deleted, and no
statistical definition was touched.

Scope: `fights`, `fighters`, `events`, `fight_odds`, `odds_books`,
`model_predictions`, `model_picks`, `model_edges`, and the four views that read
`fight_odds`. 8,990 fights, 4,548 fighters, 798 events, 110,032 odds rows,
18,622 predictions.

The checks are in [`cfl_engine/integrity/checks.py`](../../cfl_engine/integrity/checks.py)
and re-run with [`run_audit.py`](../../cfl_engine/integrity/run_audit.py). All 21
were executed against production on 2026-09-16 and every one matched the
baseline recorded in the catalogue.

---

## The short version

Three things are wrong in a way that can contaminate prospective validation and
CLV research. Everything else is either clean, or an artifact of 1990s UFC that
should be excluded by era rather than "fixed".

1. **Three fight rows were rebooked in place.** The row now holds a different
   matchup than it did when we published a pick on it and captured prices for
   it. 8 predictions and 104 odds rows name a fighter who is not in the fight
   they are attached to.
2. **1,578 odds rows have their corner label and their fighter disagreeing**, on
   8 fights — and all four odds views resolve corners by the label, not the
   fighter. Those fights come out of the views with the two corners' prices
   swapped.
3. **30,724 odds rows — 28% of the table — carry a placeholder capture time of
   1 January 1970.** The prices are fine; nothing can say when we saw them.

None of the three is fixable by a script without someone first deciding what the
right answer is. All three are recorded as standing checks so they cannot get
worse unnoticed.

---

## Classification, in one table

| # | finding | affected | class |
|---|---|---|---|
| 1 | Fight rows rebooked in place (recycled identity) | 3 fights; 8 predictions; 104 odds rows | **L3 / owner** |
| 2 | Corner label contradicts the fighter named | 1,578 rows, 8 fights, 4 views | **needs review** |
| 3 | Placeholder 1970 capture times | 30,724 rows, 7,681 fights | **needs review** |
| 4 | Same bout stored twice on one card | 4 matchups (3 real, 1 genuine 1997 rematch); 44 prediction rows on 2 bouts | **needs review** |
| 5 | Bookings that fell off a card and were never retired | 36 fights; 31 fighter-double-bookings; 3 cards with two main events | **needs review** |
| 6 | A settled prediction-market price flagged as a closing price | 2 rows | **L3 / owner** |
| 7 | Prices past 100-to-1 | 61 rows, 4 fights | **needs review** |
| 8 | No fight anywhere has a confirmed start time | 0 of 8,990 | **needs review** (it is what the event-flow work is for) |
| 9 | Two fighter records sharing a name | 8 names | not a defect — recorded |
| 10 | Pre-2001 clock and round anomalies | 48 + 29 + 184 fights | not a defect — era artifact |
| — | Everything else checked | 0 | clean |

---

## 1. Three fight rows were rebooked in place — L3

**In plain English:** a row in the `fights` table is supposed to be one bout. On
three of them, the fighters were swapped out afterwards, so the row now
describes a different fight from the one it described when we made a prediction
about it. Grading those predictions scores our call on a fight we never called.

The evidence is unambiguous, because the old names are still attached:

| fight row | now holds | but predictions on it name | rows |
|---|---|---|---|
| 43 | Carlston Harris vs Jake Matthews | **Muslim Salikhov** | 4 (v1, v2, v3, v4) |
| 46 | Rei Tsuruya vs Luis Gurule | **Jesus Aguilar** | 4 (v1, v2, v3, v4) |
| 8780 | Zhu Kangjie vs Rodrigo Vera | **Ramon Taveras** (in odds) | 104 odds rows across 43/46/8780 |

All three are on event 113, `UFC Fight Night: Song vs. Figueiredo`, 2026-05-30.

The database already noticed. `unmatched_odds` row 1031 reads, verbatim:

> `REPLACEMENT: 'Jesus Aguilar' replaced 'Luis Gurule' on fight 46 (kept: 'Rei Tsuruya'). Update fights.fighter_*_id/name to clear.`

— and it is still `resolved = false`. So the replacement was detected, the
instruction was to edit the fight row in place, and the edit happened without
the predictions and prices that pointed at the old matchup being reconciled.

**Why it is L3 and not a cleanup.** Both readings are defensible and they
disagree about what happened:

* the prediction was a real, published call on Salikhov and should keep pointing
  at a Salikhov bout — which means the fight row should never have been
  rewritten, and the honest repair is a new row plus a retired old one;
* or the prediction is void because that bout never took place, in which case it
  should be excluded from grading and not silently regraded against a different
  fight.

Deleting the predictions loses evidence. Repointing them invents a call we never
made. Neither is a script's decision. What is needed first is a **rule**: a fight
row's participants are immutable, and a replacement is a new row. That rule is
owner-level because it changes what the event scraper is allowed to do.

## 2. Corner label contradicts the fighter named — needs review

**In plain English:** each odds row says both "this is corner A" and "this is
the price on fighter X". On 1,578 rows those two disagree — the row says corner
A and names the fighter in corner B. Every view that reads odds resolves corners
by the letter, so on those fights the favourite's price comes out on the
underdog and vice versa.

| | |
|---|---|
| rows where the letter contradicts the fighter | **1,578** |
| of which complete pairs — both sides swapped together | 746 quote pairs |
| of which half-swapped — one row names a non-participant | 86 quote pairs (the 104 rows of finding 1) |
| distinct fights | **8** |
| era | 2026 only; zero among the epoch-stamped historical rows |
| books | BetWay 299, Unibet 195, BetRivers 195, Kalshi 91, Caesars 18, FanDuel 18, Polymarket 16 |

The views that key on the letter and not the fighter:
`v_fight_odds_consensus`, `v_fight_odds_latest_by_book`, `v_fight_market_vigfree`,
`v_fight_market_at_lock`. All 8 fights appear in `v_fight_odds_consensus`.

One of the 8 — fight 46239, Billy Ray Goff vs Ty Miller, 2026-08-08 — carries a
published `model_edges` row, so an edge and a CLV figure on that fight were
computed against the other corner's price.

**The cause is not the odds.** A fully swapped pair means the *fight* row's two
corners were reordered after the prices were captured: fight 43 is stored as
"Carlston Harris vs Jake Matthews" and its duplicate 27872 as "Jake Matthews vs
Carlston Harris". The odds rows are a faithful record of what was quoted; the
corner letters became stale when `fights` moved underneath them.

**Recommended direction, not applied:** the read path should resolve corners by
`fighter_id`, which is stable, rather than by `side`, which is a position in a
row that can be rewritten. `cfl_engine/export_data.py` already does exactly
this — the July 2026 review moved it to `(fight_id, fighter_id)` keying for this
reason — so the fix is to bring the four views in line with the exporter.

It is filed as **needs methodological review** rather than safe-to-fix for one
reason: changing those views changes which price every consumer sees, including
`v_fight_market_at_lock`, which DUR-001 reads. That is a change to a running
experiment's inputs and it is not mine to make while it is collecting. The odds
rows themselves need no edit at all.

## 3. Placeholder 1970 capture times — needs review

**In plain English:** 28% of the odds table says it was captured at midnight on
1 January 1970. That is not a time; it is the zero value a program writes when
it has nothing to put there. The prices are real and usable for what they are —
we simply cannot say when we saw them.

| | |
|---|---|
| rows | **30,724** of 110,032 (27.9%) |
| source | `BFO Consensus` (book 6) — every one of its rows, and no other book's |
| fights | 7,681 |
| event dates spanned | 2007-07-07 to 2026-07-11 |
| exact values | `1970-01-01T00:00:00Z` on 15,362 rows flagged opener, `…:00:01Z` on 15,362 flagged closer |

The one-second gap is the giveaway: the timestamp is not a failed capture time,
it is an **encoding of opener-versus-closer**, one second apart so they sort.

**Why it matters.** Anything that asks "what was the last price before this
fight" by ordering on `captured_at` places all 30,724 of these in 1970 — before
every live quote, on every fight. They can never be the most recent quote, and a
live book's week-old price will out-rank a genuine closing consensus. The
CLV-001 dry run already hit this from the other side: it scored 0 of 47 rows,
and the near-card capture it rejected was "an aggregate, all epoch-stamped".

**Why it is not fixable.** The only honest repair is a timestamp we never
observed. Rewriting them as "the event date" or "an hour before the bell" would
be inventing an observation, which is precisely what the append-only ledgers in
this project exist to prevent. The historical archive is what it is.

**What can be decided:** whether these rows are *excluded by rule* from anything
time-ordered, and whether `is_closer` on a BFO row is allowed to mean "this was
the closing consensus" despite carrying no time. That is a definition, so it is
review-level, and it belongs to whoever owns the CLV protocol rather than to
this session.

## 4. The same bout stored twice on one card — needs review

Four matchups appear twice within one event.

| matchup | event | rows | verdict |
|---|---|---|---|
| Zhu Kangjie vs Rodrigo Vera | Song vs. Figueiredo, 2026-05-30 | 8780, 27879 | duplicate |
| Rei Tsuruya vs Luis Gurule | same | 46, 27877 | duplicate |
| Carlston Harris vs Jake Matthews | same | 43, 27872 | duplicate |
| Kazushi Sakuraba vs Marcus Silveira | UFC Ultimate Japan, 1997-12-21 | 8577, 8580 | **genuine** — they really did fight twice that night |

The three modern pairs each carry a **different `ufc_fight_id`**, so the upsert
that keys on that id could not have caught them. The older row holds all the odds
(3,426–3,590 rows each); the newer row holds none.

Prediction rows are double-counted on two of them:

| bout | old row | new row | total prediction rows for one real fight |
|---|---|---|---|
| Harris vs Matthews | 43 → 16 | 27872 → 8 | **24** |
| Tsuruya vs Gurule | 46 → 12 | 27877 → 8 | **20** |

Anything that counts fights, or averages a metric over fights, counts these
twice. That includes track-record accuracy.

**Needs review** because picking which row survives is a judgement with
consequences: the old row carries the price history, the new row carries the
correct identity, and merging them means choosing which record of what happened
is authoritative. The 1997 pair must survive any rule that is written — a rule
that says "one matchup per card" is wrong about history.

## 5. Bookings that fell off a card and were never retired — needs review

| | |
|---|---|
| fights on a finished card with no winner and no method | **36**, every one in 2026 |
| fighters booked twice on one card, 2000 onwards | **31** |
| fighters booked twice on one card, pre-2000 | 67 — genuine, the tournament format |
| cards claiming two main events | **3** (Ankalaev vs Guskov, Du Plessis vs Usman, Noche UFC) |

**In plain English:** when a fight is scrapped or an opponent changes, the old
booking stays in the database forever, because the scraper updates rows by id and
a row that vanished from the source page is never visited again. So a settled
card can show a fight that never happened, a fighter appearing twice, and two
fights both flying the main-event flag.

The fix was written a while ago and never applied:
[`add_bout_order_migration.sql`](../../add_bout_order_migration.sql) adds
`fights.is_active` for exactly this, with a one-time cleanup scoped to upcoming
events. It is **unapplied** — `fights` has neither `is_active` nor `bout_order`
today, confirmed against the live schema.

It is review-level rather than automatic because it is a schema change to the
central table, and because the cleanup it carries makes a judgement (newest
booking wins) that is right for upcoming cards and arguable for settled ones.

Worth noting for the event-flow work: **the new running-order ingester does not
need this fixed.** A dead booking is simply not on the UFCStats page, so it gets
no order row. The page is the authority and the stale row is ignored.

## 6. A settled prediction-market price flagged as a closing price — L3

Two rows, both Polymarket, both on fight 27648 (UFC 330, 2026-08-15), captured
`2026-08-16T04:31:21Z` — after the card — at `+199900` and `-199900`. That is a
market quoting 99.95% / 0.05%: it has already resolved.

**In plain English:** this is not a price anyone could have bet. It is the
scoreboard. Counted as a closing price it would make our forecasting look
perfect on that fight, in the exact direction that flatters us.

**L3** because the question underneath it is a policy one: whether prediction
markets count as a book for CLV purposes at all, and if so, what cutoff stops a
resolved market being read as a quote. That is protocol, and the CLV protocol is
frozen and owned elsewhere. Flagged, not touched.

## 7. Prices past 100-to-1 — needs review

61 rows at `|american_odds| >= 10000`, across 4 fights: Kalshi 45, BetMGM 12,
Polymarket 4. Four of them exceed 50,000. Real sportsbooks do not price a UFC
fight at 100-to-1; these come from prediction markets at or near settlement,
where the number stops being a forecast and starts being an outcome.

Whether they are excluded, capped or kept is a protocol question, not a cleanup.

## 8. Nothing records when a fight started

`bell_at` is populated on **0 of 8,990 fights**. `fight_start_estimates` holds 18
rows, all from `odds_api_commence`, all observed on 2026-09-15 — the ledger began
after every past card.

This is not new and it is not a defect in the usual sense; it is the gap the
event-flow work exists to close, and the reason the running-order ingester built
alongside this audit matters. It is tracked as a standing check whose count we
want to see **go up**.

## 9–10. Recorded so they are not rediscovered as defects

**Eight pairs of fighters share a name** — Bruno Silva, Jean Silva, Joey Gomez,
Jose Montanha, Michael McDonald, Mike Davis, Tony Johnson, Victor Valenzuela.
These are real, distinct people. It is the reason nothing in this codebase is
permitted to match a fighter by name, and the running-order ingester refuses to
do so even when a name match would resolve a bout.

**The pre-2001 anomalies are history, not errors.** 48 fights record an end time
past 5:00 (up to 18:00), 29 ended in a round later than they were scheduled for,
170 were scheduled for one round and 14 for two. Every single one is pre-2001,
when rounds ran long and the tournament format was normal. Three exceptions sit
in 2001–2009, all `scheduled_rounds = 2`. The integrity checks start at 2001 for
this reason, and both currently stand at zero.

One consequence worth stating: `v_fighter_consistency` v7 derives a real round
clock from `fights.end_round` and `fights.end_time`. On a pre-2001 fight that
arithmetic yields an 18-minute round. The view is not obviously era-filtered;
whether it needs to be is a question for whoever owns it, and it is not urgent —
those fighters have no `fight_rounds` detail anyway.

---

## What came back clean

Checked and found at zero, so they are worth not re-deriving:

* no duplicate `ufc_fight_id`, no duplicate `ufc_event_id`, no duplicate event
  name-and-date;
* no fight with a null event, a null fighter, the same fighter in both corners,
  or a winner who was not in it;
* no orphan rows anywhere — `fight_odds`, `model_predictions`, `model_picks`,
  `model_edges` all resolve to live fights, fighters, events and books;
* no duplicate market identity: not one `(fight, book, side, captured_at)`
  repeats across 110,032 rows, and no fight-book-side has two openers or two
  closers;
* every row's `implied_prob` agrees with its own `american_odds` to within
  0.005 — 110,032 for 110,032;
* no odds row captured in the future; no `american_odds` of 0 or inside the
  impossible ±99 band; both sides present on every quote;
* `model_picks`, `model_predictions` and `model_edges` carry no duplicate
  identities and no `event_date` that disagrees with the event's own;
* no card still marked upcoming after its date, and no future card marked
  finished;
* 8,994 fight ids and 798 event ids are all well-formed 16-character UFCStats
  tokens — which is what lets the running-order ingester link on them and refuse
  everything else.

`fights.updated_at` is present, never null, never in the future, never at epoch.
The 1970 sentinel is confined entirely to `fight_odds.captured_at`.

---

## What was deliberately not done

* **No row was edited, deleted or backfilled.** Several findings have a tempting
  one-line `UPDATE`. Each of those would either delete a historical observation
  or write a fact nobody observed.
* **No migration was applied.** The one new SQL file here,
  [`cfl_engine/integrity/count_rpc.sql`](../../cfl_engine/integrity/count_rpc.sql),
  is proposed and unapplied, and filed outside the repo root so the
  "apply root `*.sql`" habit cannot pick it up.
* **No frozen definition was touched.** DUR-001 and DUR-002 are running;
  `v_fight_start_best`, `PREREGISTRATION.md`, the duration model and the CLV
  protocol were read and not modified.
* **No CLV or performance number is published or implied by this document.** The
  odds findings describe data quality, not results.
* **Nothing was enabled that costs money.** Every query ran through the existing
  read-only connection.
