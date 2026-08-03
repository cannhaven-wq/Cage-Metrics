# cfl_engine integration — progress checkpoint

Working through `CLAUDE_CODE_HANDOFF.md` (from Downloads/files.zip, extracted to
Claude scratchpad). Update this file after every milestone so a fresh session can
resume without re-deriving anything.

## 2026-07-19 — engine_v2 + full front-end rebuild ("one engine, three faces")

- [x] **engine_v2 shipped in code**: STATIC_FEATS (height_in, reach_in,
  is_southpaw, is_switch) added to engine.py as PIT-safe static lookups (NaN
  when unknown — a missing stance never reads as Orthodox); export_data.py /
  predict_upcoming.py fetch the columns; version string centralized in
  version.py (`ENGINE_VERSION = "engine_v2"`), imported by both publishers.
- [x] **Retrain passed the gate**: synthetic self-test clean; real run on the
  2026-07-19 export (8,779 fights) — PIT sampled 0/200 AND exhaustive
  pit_diagnose 17,558/0; no too-good flags; calibrated OOS 61.5% acc /
  0.6537 LL vs engine_v1's 61.4% / 0.6511 (noise-level). `d_reach_in` is the
  #3 feature by gain. Locks 74.5% (n=707). Face 2: 658 bets, 519-139,
  flat +0.3% / Kelly +10.0%.
- [x] **publish_backtest dry-run clean** (3,235 picks / 658 edges, no anomalies).
  `--execute` NOT yet run (blocked in-session) — Reed runs it, see runbook below.
- [x] **Front-end rebuilt around the engine** (all pages cache-busted to
  `?v=rd6`): `_shared.js` gains `cfl.ENGINE` + `fetchEnginePicks/EngineEdges`
  (graded-view loaders); track-record.html is engine-first (two face tabs,
  source-keyed Simulated/Live banner, v3/v6 in a collapsed archive with the old
  code path intact); card-lab.html defaults to the engine with published tiers;
  picks.html runs entirely on live model_picks/model_edges; index.html hero,
  model select, explanations, past-event rows repointed. Copy updated on
  about/pricing/methodology/edges (dated 7/19 update post)/predictor (archive
  framing). All build/ scripts (digest, social-post, social-engine, draft-post,
  prerender) now read model_picks (live-preferred) instead of v3/v6.
- [x] Front-end verified against production DB via local server: engine section
  degrades gracefully while the graded views are missing; card-lab/index/picks
  render engine rows end-to-end from the existing engine_v1 rows.

### Runbook for Reed (in order)
1. Supabase SQL Editor: run `cleanup_stale_live_picks.sql` (71 stale live picks
   from the buggy first publish — the 7/18 card becomes a clean gap).
2. SQL Editor: run `model_graded_views.sql` (front-end reads these views).
3. `PYTHONPATH=cfl_engine python cfl_engine/publish_backtest.py --execute`
   (replaces the engine_v1 backtest with engine_v2's 3,235 picks / 658 edges).
4. Re-add the Railway Weekly Scraper cron (`0 6 * * 0,1,3,5`) so the 7/18
   results land; then re-run export_data.py before the next predict_upcoming.
5. Next fight week: `predict_upcoming.py` dry-run → `--execute` (publishes as
   engine_v2), and `settle_clv.py --execute` the day after the card.

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

## DEPLOYED 2026-07-17

Tables created (SQL Editor) and both publishers executed against production:
- `model_picks`: 3,232 backtest + **71 live** (21 Lock / 29 Pick / 21 Lean).
- `model_edges`: 638 backtest + **10 live**, all with `odds_at_publish` captured,
  `closing_odds`/`clv_beat` null (pre-event). CLV clock running for the
  Du Plessis–Usman card (2026-07-18).
- DDL shipped via `cfl_engine/run_sql_mgmt.py` (Management API). NOTE: that host
  is behind Cloudflare, which 403s (error 1010) on urllib's default UA — the
  script now sends a browser User-Agent. (Migration itself was ultimately pasted
  into the SQL Editor; publishers use the PostgREST host, no CF block.)

## Hardening pass 2026-07-17 (adversarial review of the unattended-run scripts)

Fixed in code (committed, not pushed):
- **settle_clv.py — 2 blockers**: it fell back to the STALE
  fight_odds_consensus_snapshot table and compared its DEVIGGED prob against the
  RAW vigged publish prob — either would silently corrupt clv on the headline
  metric and lock it in (settled_at gate). Removed the fallback entirely: a
  missing close now leaves the row unsettled. Also stores the real median-book
  American close, not a reconstructed one. Sign convention was verified correct.
- **predict_upcoming.py — important**: publishing ALL upcoming cards at once +
  insert-only locking permanently locked far-future picks onto stale history.
  Now gated to events within ~12 days (`--within-days`, default 12) + a staleness
  warning if the completed-history export is old. Added dead-booking dedupe
  (drops phantom double-bookings, keeps the market-priced real fight) and a final
  model refit on ALL completed fights (was holding out the recent 10%).
  Dry-run confirms: 71→27 picks (2 imminent cards), 3 phantoms dropped.

## MUST DO to correct the live data (the first publish was the buggy version)

1. SQL Editor: run `cleanup_stale_live_picks.sql` (clears the 71 stale live rows).
2. `PYTHONPATH=cfl_engine python cfl_engine/predict_upcoming.py --execute`
   — republishes just the imminent card(s), deduped, on current history.

## Front-end wiring (staged, needs browser preview before ship)

- `model_graded_views.sql` (repo root) — run in SQL Editor. Creates
  v_model_picks_graded / v_model_edges_graded (server-side fights join, since the
  tables have no outcome column and a 3k-id client join would 414). Pure additive
  DB objects, safe to ship now.
- HTML not yet edited (no browser this session to verify). Plan per review:
  (a) track-record.html — add an ISOLATED `loadEngine()` in its own try/catch +
  DOM block reading v_model_picks_graded (source='backtest' for the record); must
  NOT run inside loadProof().catch (that replaces the whole page on any throw).
  (b) card-lab.html — add engine_v1 to the model dropdown reading the live picks;
  stage-for-preview (rewires interactive pickForFight/buildRows). Copy guardrail:
  present engine_v1 as honest ~61% / calibrated, NEVER as beating the market; do
  not render CLV yet (backtest clv null, live edges unsettled).

## Recurring / upstream (unchanged)

- Per event week: `predict_upcoming.py --execute` after odds land;
  `settle_clv.py --execute` the day after each card (fills closing_odds + CLV).
- Optional: `dead_booking_cleanup.sql` (past stale fight rows 43/46/8780).
- Upstream: (a) fight_odds_consensus_snapshot table not refreshed since May — fix
  its writer or drop it (serving + settle use v_fight_odds_consensus / is_closer);
  (b) event scraper should kill dead future double-bookings at the source;
  (c) Railway Weekly Scraper cron still needs re-adding (separate incident doc).

## Key facts for whoever resumes

- Live schema: fights 8859 / events 788 / fighters 4509 / fight_rounds 20615 /
  fight_odds 105894 (15542 closer rows). Upcoming events through 2026-09.
- Existing prod tables for benchmark: `model_predictions` (model_version, fight_id,
  side, model_p, opener_implied_p, edge, would_bet, won...), `model_versions`
  (test_start_date etc.) — respect each model's own OOS window (CLAUDE.md rule).
- Guardrails: quarter-Kelly / 2% cap / 4% min edge fixed; publish CLV + calibration,
  not ROI; fold 0 never user-facing; no new ufcstats scraping.
- Report to Reed in plain English: accuracy %, win rates, dollars — not log-loss jargon.
