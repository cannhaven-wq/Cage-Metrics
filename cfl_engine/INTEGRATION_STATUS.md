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

## In flight

- [ ] Re-run chain (background): synthetic smoke + real pipeline + exhaustive
  PIT diagnose. Expect PIT = 0 everywhere now.
- [ ] Explore agent mapping repo (model_predictions/model_versions usage, odds
  pipeline, picks publishing, benchmark files for handoff task 5).

## Next (in order, per handoff)

3. **AUDIT GATE** — read `out_real/report.md`. RED FLAG = OOS acc >70% or model beats
   vig-free close by >0.015 log-loss → find leak in data path, fix, rerun. Never weaken checks.
4. Benchmark existing prod model (`model_predictions`/`model_versions` in Supabase)
   with `audit.metric_block` on same fights; if old numbers beat red-flag thresholds,
   call it out as old-backtest leakage.
5. Create `model_picks` + `model_edges` tables (check `SUPABASE_DB_URL` for direct psql
   DDL; else SQL Editor file for Reed). Load calibrated folds only; fold 0 never exposed.
6. CLV capture: odds_at_publish snapshot + post-event closing fill + clv_beat. No new
   ufcstats scraping surface.

## Key facts for whoever resumes

- Live schema: fights 8859 / events 788 / fighters 4509 / fight_rounds 20615 /
  fight_odds 105894 (15542 closer rows). Upcoming events through 2026-09.
- Existing prod tables for benchmark: `model_predictions` (model_version, fight_id,
  side, model_p, opener_implied_p, edge, would_bet, won...), `model_versions`
  (test_start_date etc.) — respect each model's own OOS window (CLAUDE.md rule).
- Guardrails: quarter-Kelly / 2% cap / 4% min edge fixed; publish CLV + calibration,
  not ROI; fold 0 never user-facing; no new ufcstats scraping.
- Report to Reed in plain English: accuracy %, win rates, dollars — not log-loss jargon.
