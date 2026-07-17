# cfl_engine integration — progress checkpoint

Working through `CLAUDE_CODE_HANDOFF.md` (from Downloads/files.zip, extracted to
Claude scratchpad). Update this file after every milestone so a fresh session can
resume without re-deriving anything.

## Done

- [x] **Task 1 — synthetic smoke test PASSED** (2026-07-16). `out_synth/report.md`:
  PIT structural check 0/200 mismatches, no red flags, ECE 0.017.
  Engine source extracted from `cfl_engine_full_source.md` into `cfl_engine/` (8 files).
  Deps installed (pandas/numpy/sklearn/xgboost/tabulate on system Python 3.11).
- [x] Live Supabase schema introspected via PostgREST OpenAPI root (service key works,
  legacy JWT format, env vars `SUPABASE_URL` + `SUPABASE_SECRET_KEY`).
- [x] `cfl_engine/export_data.py` written. Design notes:
  - `fights` table carries per-fight stat totals (wide `a_/b_` cols) → primary source
    for fight_stats.csv; `fight_rounds` aggregation used as cross-check + coverage report.
  - result mapping: `winner_id`→a/b; winnerless `Decision - *`→draw;
    Overturned/Could Not Continue/Other→nc; method null or event `is_upcoming`→excluded.
  - closing odds: `fight_odds` `is_closer=true`, side `'A'/'B'` (UPPERCASE), median
    implied prob across books per side → back to American; both sides required.
  - `fight_seconds` = (end_round−1)*300 + m:ss; decisions fall back to sched*300.
  - PostgREST caps at 1000 rows/request → Range-header pagination everywhere.

- [x] Opus adversarial review of export_data.py done; all findings fixed:
  odds now keyed by (fight_id, fighter_id) not side convention; fight_rounds
  backfill implemented + zero-fill partner corner (engine self-join hazard);
  NC-family method overrides stale winner_id; winnerless finishes excluded not
  nc-bucketed; null event_date excluded (PIT anchor).
- [x] **Task 2 — export ran clean** (2026-07-16): 8775 fights (a=5528/b=3091 —
  corner bias visible as expected, engine randomizes), draws 62, nc 94;
  17502 stat rows; odds coverage 87.8% both-sides; 0 odds rows unmatched by
  fighter_id; cross-check fights-totals vs fight_rounds agg: 17500 compared,
  0 mismatched. Excluded: 71 upcoming, 13 no_result, 0 anomalies.
  CSVs in `cfl_engine/data/`.

- [x] **Task 3 first run + AUDIT GATE findings** (2026-07-16): no too-good red
  flags (OOS acc 61.3%; model log-loss 0.653 vs market 0.598 — model does NOT
  beat the close). But PIT check = 1/200 mismatch → root-caused exhaustively
  (95 corner-mismatches over all 17.5k rows), two causes, both fixed:
  1. **Dead-booking duplicate rows** in `fights` for event 113 (2026-05-30):
     stale ids 43/46/8780 vs canonical 27872/27877/27879; stats on new rows,
     odds attached to OLD rows. Export now merges (evidence-based dedupe: a
     dead booking is a stats-empty ghost; same-pair rows BOTH with stats are
     real same-night rematches — Sakuraba–Silveira 1997 kept). Upstream
     cleanup SQL for Reed: `dead_booking_cleanup.sql` (repo root, SQL Editor).
  2. **1990s tournament same-night fights**: engine's history loop + Elo
     counted same-day earlier bouts as prior. Fixed in engine.py to enforce
     its own strictly-before-date iron rule: history filter + per-date Elo
     update batching. Both changes make the model see LESS, never more.

- [x] **Tasks 3+4 final: AUDIT GATE PASSED** (2026-07-16). PIT = 0/200 sampled AND
  0/17,544 exhaustive (`pit_diagnose.py`). No too-good flags. OOS 61.4% acc /
  0.651 LL; market 68.0% / 0.598; blend 68.4% / 0.594 (beats market by 0.004 —
  under the 0.015 leak line). ECE 0.019. Synthetic re-passed after engine fixes.
  No-bet segments (worst model-vs-market Brier): Catch Weight, debut_involved,
  Light Heavyweight, Strawweight. Committed as 939d0a3.
- [x] **Task 5: benchmark** — `cfl_engine/benchmark_prod.py` + `benchmark_report.md`.
  v1/v2/v3 recomputed = site claims (validates scorer). v5 = 70.8% acc → RED FLAG
  confirmed (it trains on the closing line; that's the market's number, can't run
  live). v6 67.7% (test window overlaps training). Every prod model loses to the
  close on log-loss on shared fights. Engine is the honest yardstick.
- [x] **Task 6: wiring** — `model_picks_edges_migration.sql` (repo root; Reed runs
  in SQL Editor) + `cfl_engine/publish_backtest.py` (dry-run validated: 3232 picks,
  638 edges, corner back-mapping proven on flipped cases, fold 0 excluded by
  construction). `--execute` deletes+reloads source='backtest' only; never touches
  source='live' (insert-only pick locking).
- [x] **Task 7: serving + CLV** — `cfl_engine/predict_upcoming.py` (71 picks / 8
  upcoming events, 9 edges in dry-run; consensus read from v_fight_odds_consensus
  VIEW — the snapshot TABLE is stale since May, do not use) +
  `cfl_engine/settle_clv.py` (fills closing_odds, clv_pp, clv_beat post-event;
  positive clv_pp = beat the close). Publish clip [0.05, 0.95] applied UPSTREAM of
  the blend (isotonic tail artifact was flagging a fake 21-point edge).

## For Reed (the only human steps left)

1. Supabase SQL Editor: run `model_picks_edges_migration.sql`, then
   `dead_booking_cleanup.sql`.
2. `PYTHONPATH=cfl_engine python cfl_engine/publish_backtest.py --execute` (once).
3. Per event week: `predict_upcoming.py --execute` after odds land;
   `settle_clv.py --execute` the day after each card.
4. Upstream hygiene flagged: (a) fight_odds_consensus_snapshot table not being
   refreshed since May — either fix its writer or drop it (serving now uses the
   view); (b) upcoming cards contain stale double-bookings (e.g. Ankalaev booked
   vs both Rountree and Guskov; Umar Nurmagomedov on two cards) — event scraper
   should kill dead future bookings; (c) Railway Weekly Scraper cron still needs
   re-adding (separate incident doc).

## Key facts for whoever resumes

- Live schema: fights 8859 / events 788 / fighters 4509 / fight_rounds 20615 /
  fight_odds 105894 (15542 closer rows). Upcoming events through 2026-09.
- Existing prod tables for benchmark: `model_predictions` (model_version, fight_id,
  side, model_p, opener_implied_p, edge, would_bet, won...), `model_versions`
  (test_start_date etc.) — respect each model's own OOS window (CLAUDE.md rule).
- Guardrails: quarter-Kelly / 2% cap / 4% min edge fixed; publish CLV + calibration,
  not ROI; fold 0 never user-facing; no new ufcstats scraping.
- Report to Reed in plain English: accuracy %, win rates, dollars — not log-loss jargon.
