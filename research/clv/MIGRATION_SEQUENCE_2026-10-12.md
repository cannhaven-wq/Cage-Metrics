# CLV-001 and odds immutability — the order to apply what is left

Written 2026-10-12 for the stabilization sprint. **Nothing here has been applied.**
Every step that writes to production waits for the owner (CRITICAL_GATES.md L3
item 5). This page only puts the files in order and says what each depends on.

## Where things stand (verified against the live database, 2026-10-12)

| file | state | evidence |
|---|---|---|
| `research/clv/proposed_2026-09-16_fight_odds_capture.sql` | **applied** 2026-09-19 (D-009) | the 11 capture columns exist on `fight_odds`; the 2026-10-12 odds run logs "all CLV-001 capture columns present". The file's own header still says "draft" — stale. |
| `add_bout_order_migration.sql` | **applied** 2026-09-19 (D-009) | `fights.bout_order`, `fights.is_active` exist |
| `research/clv/proposed_2026-09-16_event_flow.sql` | not applied | `fight_bout_order`, `fight_bout_completions`, `odds_api_usage`, `v_clv_close_reference` absent |
| `research/clv/proposed_2026-09-16_fight_odds_immutability.sql` | not applied (T-031) | `fight_odds` has **no triggers** |
| `research/clv/proposed_2026-09-16_clv001_columns.sql` | not applied | no `model_edges.clv_*` columns |
| `research/clv/proposed_2026-09-16_snapshot_edge_identity.sql` | not applied | no `pre_fight_snapshots.edge_model_edge_id` |
| `cfl_engine/integrity/count_rpc.sql` | not applied | no `cfl_integrity_count` function — the integrity runner cannot run |
| `cfl_engine/dur001/proposed_2026-09-15_market_last_update.sql` | not applied, **blocked** on DUR-001 amendment (j) (T-002) | — |

## The order, with why

**Step 0 — between cards only.** Every step below changes tables the odds job
writes to. Apply Monday–Wednesday, never inside 48 hours of a card. Take a
note of the current `fight_odds` row count before and after each step.

**Step 1 — `cfl_engine/integrity/count_rpc.sql`.** Read-only helper function;
nothing depends on it and it depends on nothing. Apply first so the integrity
runner (`cfl_engine/integrity/run_audit.py`) can measure the before-state of
every later step. Lowest risk of the set.

**Step 2 — seed, then apply `proposed_2026-09-16_event_flow.sql` (T-029).**
It creates `odds_api_usage` **empty**, and an empty ledger reads as "0 spent,
500 left" — which would move the credit governor from its current safe 30-minute
rung to its finest 5-minute rung on a false premise. So in the same session as
applying it, insert one seed row from the provider's own count. The latest
figure in the odds job log (run 38277445027, 2026-10-12 16:27 UTC):
`used=33, remaining=467`. Re-read it from the most recent run on the day,
because it moves.
- Unblocks: `build/fetch-odds.js` budget reading; the in-flow capture tier;
  `v_clv_close_reference`. `fight_bout_order` stays empty until Event Flow can
  fetch UFCStats from a non-datacenter IP (T-030) — applying the tables does
  not make that happen.
- Its own header: apply after the capture migration (done) and before
  `clv001_columns`.

**Step 3 — `proposed_2026-09-16_fight_odds_immutability.sql` (T-031).**
Blocks DELETE and TRUNCATE on `fight_odds` for every role, and allows UPDATE of
`is_opener` / `is_closer` only. Check the writers first — verified 2026-10-12:
- `build/fetch-odds.js` inserts and toggles `is_opener`/`is_closer` only — allowed.
- The odds repo's `train_models.yml` Polymarket step inserts and toggles the same
  two flags — allowed.
- `backfill_odds.py` (the one writer that deleted rows) was retired (D-004);
  its Railway service has no schedule and has not built since July.
- `dead_booking_cleanup.sql` at the repo root **repoints** `fight_odds.fight_id`
  — it would now be refused. That is the intended effect; it is a one-off from
  May that must not be re-run.
After applying: run one odds capture by hand (`odds.yml`, workflow_dispatch)
and confirm it still inserts and promotes closers.

**Step 4 — `proposed_2026-09-16_clv001_columns.sql`.** Adds the CLV-001
result columns and checks to `model_edges`. Depends on Step 2 (the close
reference view). `settle_clv.py --clv001 --write` stays gated shut by its own
preflight until every amendment is ratified; applying the columns does not
start writing.

**Step 5 — `proposed_2026-09-16_snapshot_edge_identity.sql`.** Order-independent;
`snapshot_predictions.py` already probes for the column and starts filling it
the first run after it exists.

**Not in this sequence:** `proposed_2026-09-15_market_last_update.sql` (waits on
the DUR-001 amendment vote, T-002).

## Rollback per step

| step | rollback |
|---|---|
| 1 | `drop function public.cfl_integrity_count(text);` |
| 2 | drop the three tables and the view; `fetch-odds.js` already degrades to "budget unknown" when they are absent |
| 3 | `drop trigger` for the three triggers the file creates (names in the file) — the only step whose purpose is to be hard to undo, so read the file before applying |
| 4 | the columns are additive and nullable; drop them |
| 5 | additive; drop the column |

## Does this sprint need it?

Honestly: not for the commercial question. CLV-001 publication needs 100 scored
observations across 20 events, and Step 2 alone cannot produce them while Event
Flow is blocked by UFCStats. Steps 1 and 3 are worth doing anyway — Step 1 so
data integrity can be measured, Step 3 because `fight_odds` is the one asset that
gains value with time and nothing currently stops a writer deleting from it.
