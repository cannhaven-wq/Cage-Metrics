# 04 — Data infrastructure and predictive models

Audit date: 2026-10-12. Live figures come from read-only SQL against the production Supabase project (`uftancejftcryfvbggll`, Postgres 17.6, ACTIVE_HEALTHY) run during this audit; repository figures cite path and line. Tags: **VERIFIED** (read from the live DB, a committed artifact, or a test), **INFERRED**, **UNKNOWN**.

---

## Part A — Data infrastructure

### A1. Verified live record counts (2026-10-12)

| table | rows | span / freshness | notes |
|---|---|---|---|
| `events` | 801 | 1994-03-11 → 2026-12-12 | 7 future cards booked |
| `fights` | 9,059 | `updated_at` max 2026-10-11 | 8,984 past; 196 past fights with no winner; 63 with no stats; 8,788 with a result |
| `fighters` | 4,554 | **4,495 last updated May 2026**; 6 in the last 30 days, 53 in 90 days | 2,222 have NULL `division` |
| `fight_rounds` | 20,982 | — | the table "nothing else can reconstruct" |
| `fight_odds` | 126,488 | real timestamps 2026-05-22 → 2026-10-12 | **30,724 rows (24%) stamped 1970-01-01** by the retired BestFightOdds backfill; 11,794 rows carry full CLV-001 provenance (all since 2026-09-19) |
| `odds_books` | 14 | — | 10 real US books, plus BFO Consensus, CFL Consensus (synthetic), Polymarket, Kalshi |
| `prop_odds` | 791 | 2026-09-15 → 2026-10-02 | totals quotes on 24 fights |
| `fight_start_estimates` | 151 | 2026-09-15 → 2026-10-11 | |
| `pre_fight_snapshots` | 106 | 2026-08-15 → 2026-10-09 | 9 cards; **UFC FN Rosas Jr. vs Barcelos (09-26) has 0 rows, permanently** |
| `predictions` (cfl-snapshotter) | 77 | 2026-05-02 → 2026-10-09 | wrote twice in the last five months (Gamrot 08-08, Allen vs Duncan 10-09) |
| `model_picks` | 3,429 | backtest 3,235 (2020-01 → 2026-07-18); live 194 (07-18 → 10-17) | |
| `model_edges` | 737 | backtest 658; live 79 | |
| `model_predictions` (legacy v1–v6) | 19,074 | v1/v2/v3 2,936 each, v4 1,590, v5 5,840, v6 2,836 | 28 v5 rows flagged `reconstructed` |
| `model_versions` | 6 | v1–v4 `last_trained_at` **2026-10-12** (nightly retrain in another repo); v5 05-30; v6 07-01 | |
| `prop_projections` | 26 | next card only | full-table replaced daily |
| `prop_model_locks` | 488 | 2026-09-15 → 2026-10-09 | 244 per model version, 61 fights |
| `fighter_cardio` | 2,681 | — | nothing renders it |
| `fighter_ratings` | 2,777 | — | Elo, read by `fighter.html` |
| `funnel_events` | 5,665 | 2026-09-21 → 2026-10-12 | see `05_BUSINESS_AND_MONETIZATION.md` |
| `profiles` / `auth.users` | 8 / 8 | last sign-up 2026-09-11; **0 sign-ins in the last 30 days** | all `beta_premium`, 1 admin |
| `email_subscribers`, `premium_waitlist`, `billing_events`, `user_watchlist`, `user_alerts`, `user_alert_prefs` | 0 each | — | `user_alert_deliveries` 1 (test); `user_bets` 3; `user_bankrolls` 1 |
| Orphan tables not defined anywhere in this repo | `streak_effect_cache` 14,421; `cardio_style_snapshots` 15,632; `master_dataset` 4,204; `master_dataset_v2` 4,204; `fighter_snapshot_2025` 2,629; `prediction_indicators` 3,119; `fight_odds_consensus_snapshot` 29; `hub_visits` 20; `odds_aliases` 0; `unmatched_odds` 11 | — | written by other repos or by hand; `odds_aliases` and `unmatched_odds` have **RLS disabled** |

Whole database is under 100 MB (`fight_odds` 40 MB is the largest table). Objects documented in the repo but absent live: `odds_api_usage`, `fight_bout_order`, `fight_bout_completions`, `v_clv_close_reference`, `cfl_integrity_count`, the `model_edges.clv_*` columns, `pre_fight_snapshots.edge_model_edge_id` (the three unapplied CLV migrations). `fight_odds` has **no triggers** (the immutability migration is unapplied), and the live `v_fight_odds_latest_by_book` is the `market_chart_views.sql` definition (no 14-day window).

### A2. Odds capture, by month and by book (VERIFIED live)

| month | rows | distinct fights | books | with provenance |
|---|---|---|---|---|
| epoch (1970) | 30,724 | 7,681 | 1 (BFO Consensus) | 0 |
| 2026-05 | 71,594 | 42 | 7 | 0 |
| 2026-06 | 1,076 | 49 | 1 | 0 |
| 2026-07 | 3,126 | 71 | 8 | 0 |
| 2026-08 | 1,928 | 95 | 9 | 0 |
| 2026-09 | 10,666 | 72 | 9 | 6,214 |
| 2026-10 (to 12th) | 7,374 | 55 | 9 | 5,580 |

Books: Caesars, BetWay, Unibet and Kalshi stopped 2026-05-31 (the BestFightOdds scraper era). FanDuel, BetRivers, BetOnline, DraftKings, Bovada, BetMGM, BetUS and the synthetic CFL Consensus are written by `build/fetch-odds.js` through 2026-10-11. Polymarket (16,100 rows, through 2026-10-12) is written by the Railway odds-scraper's `polymarket/` capture. The usable multi-book time series is therefore **about three weeks old** (since UFC 331, 2026-09-19) and covers four cards.

Recent cards (VERIFIED live): UFC 331 13/13 snapshots, 13 fights with odds, 8 books; Rosas Jr. vs Barcelos 0/13 snapshots, 12 with odds; UFC 332 14/15 snapshots, 15 with odds; Allen vs Duncan 12/12, 12 with odds, 9 books. Upcoming: Buckley vs Malott 14/16 fights priced, UFC 333 9/10, UFC 334 2/12, UFC 335 3/4; Moicano vs Nolan, Bonfim vs Brady and Prochazka vs Stirling have no prices yet (not posted by books, INFERRED).

### A3. Ingestion: who writes what, and whether it is running

| table | writer | schedule | live status |
|---|---|---|---|
| `fights`, `events` (results, upcoming cards) | `cage-metrics-event-scrapper` "Weekly Scraper" on Railway (not in this repo) | nightly | **RUNNING** — Railway log 2026-10-12 00:05 UTC: 9 events, 97 fights upserted, 53 recently-fought fighters refreshed, 0 errors |
| `fighters` (full profile refresh) | `cage-metrics-scrapper` on Railway | nightly | **DEAD since May** — last successful deploy 2026-05-22; the 2026-07-01 deploy carrying the UFCStats proof-of-work fix FAILED; 4,495 of 4,554 fighters last touched May 2026; only recent fighters are refreshed by the event scraper's phase 4 |
| `fight_odds` (sportsbooks) | `build/fetch-odds.js` via `odds.yml` (The Odds API, free tier, 500 credits/month hard cap) | asks `*/5`, delivered ~4–6×/day by GitHub | **RUNNING**, last run 2026-10-12 06:53 UTC success. Governor stuck at the coarsest 30-minute rung because `odds_api_usage` does not exist |
| `fight_odds` (BestFightOdds, Polymarket) | `cage-metrics-odds-scrapper` on Railway, two services in two projects | unknown | **every deploy since 2026-07-01 FAILED** on both services (last success 2026-05-26); Polymarket rows still arrive through 2026-10-12, so the May build is presumably still running (INFERRED). A second service whose start command was overridden to the retired `backfill_odds.py` is noted in D-004 as "should be removed" |
| `pre_fight_snapshots` | `cfl_engine/snapshot_predictions.py` via `snapshot.yml` | 23:00 + 10:30 UTC | RUNNING, last success 2026-10-12 |
| `model_picks`, `model_edges` (live) | `cfl_engine/predict_upcoming.py` via `engine-serve.yml` | daily 09:00 UTC | RUNNING |
| `model_edges.clv_*` (legacy settle) | `cfl_engine/settle_clv.py` via `settle-clv.yml` | daily 12:00 UTC | RUNNING in legacy mode; CLV-001 write mode gated shut |
| `prop_projections` | `predict_props_upcoming.py` via `props-refresh.yml` | daily 10:00 UTC | RUNNING (feeds an archived page) |
| `prop_model_locks` | `lock_prop0001.py`, `lock_prop0002.py` via `prop-locks.yml` | daily 11:00 UTC | RUNNING |
| `predictions` | `cfl-snapshotter` on Railway | Fridays 18:00 UTC since 2026-10-05 | RUNNING; wrote 12 rows 2026-10-09 |
| `fight_bout_order` | `cfl_engine/event_flow/ingest_bout_order.py` via `event-flow.yml` | **cron commented out**; 0 runs ever | BLOCKED: UFCStats returns 403 to datacenter IPs and the table does not exist |
| `data/exports/*.jsonl` | `build/export_tables.py` via `export.yml` | daily 05:00 UTC | **FAILING every day**: `SUPABASE_URL is not set` (GitHub secret missing); `data/` has never been committed |
| `fighter_cardio` | `cfl_engine/cardio/publish.py` | manual | not scheduled; nothing renders it |
| `model_predictions`, `model_versions` | v1–v6 training in the odds-scraper repo | nightly (v1–v4 retrained 2026-10-12) | RUNNING somewhere outside this repo (UNKNOWN where; Railway deploys of that repo fail, so likely a GitHub Action in that repo — INFERRED) |

### A4. Fight and event matching

- **Odds API → `fights` is matched by normalised fighter-name pair** (`build/fetch-odds.js:88-97, 946-998`): four tiers down to surname pair; ambiguous pairs are discarded rather than resolved. The surname tier was added 2026-10-02 after "Mick/Michael Parkin" and "Alex/Alexander Volkanovski" cost UFC 332 two fights and UFC 333 its main event. `cfl_engine/integrity/checks.py:313-327` records 8 namesake fighters as "the reason nothing in this codebase is allowed to match a fighter by name" — the odds path does exactly that. INFERRED risk: a wrong pair match writes a permanent price onto the wrong fight.
- **UFCStats → fights** is matched by `ufc_fight_id` in the event scraper (not in this repo) and in Event Flow (`cfl_engine/event_flow/`, never run in production).
- Known identity failures: event 113 (2026-05-30) had three fight ids reassigned by UFCStats, producing the 1,578 corner-swapped odds rows (`dead_booking_cleanup.sql`); the first live publish locked 71 picks on dead double-bookings (`cleanup_stale_live_picks.sql`); UFC 331's Moicano–Ortega booking was retired by hand (D-009); 192 past fights have no winner, so "past and no winner" cannot be used as a cancellation signal (`cfl_engine/event_flow/STALE_BOOKING_LIFECYCLE.md`).

### A5. Data quality and integrity

`cfl_engine/integrity/checks.py` defines 21 checks with 2026-09-16 baselines; the runner needs an unapplied RPC, so it cannot run against production. The eight findings in `research/integrity/DATA_INTEGRITY_AUDIT_2026-09-16.md` are all still open (VERIFIED by the Phase 6 review): 104 odds rows and 8 predictions naming a non-participant (owner decision), 1,578 corner-letter contradictions on 8 fights (misread by four views), 30,724 placeholder timestamps, 4 duplicate bouts, 36 settled fights without a result, 2 prediction-market prices flagged as closers, 61 prices at or beyond 100-to-1, and `bell_at` populated on **0 fights** (no confirmed bell source exists anywhere).

Documented irreversible losses: the Rosas Jr. vs Barcelos card (13 fights, no pre-fight record, trigger-protected so it cannot be backfilled); `predictions` unwritten August → October because the Railway cron was never set; 110,980 odds rows captured before 2026-09-19 carry NULL provenance forever; the v6 "record" was in-sample until restated (2,602 → 412 fights); the Factor Lab scored 869 of 1,220 market-even fights for weeks because of unordered paging.

Live writers still reading a removed column: `build/send-digest.js:100,113` and `build/social-post.js:72-73` read `open_p_a` / `books_at_open`, which D-012 removed from `v_fight_market_movement` on 2026-09-21 (VERIFIED live: the view has no such column). The social poster therefore skips every fight and the Brief loses its movement line. No test pins it.

### A6. Indexing and performance

`fight_odds` carries 8 indexes live (`idx_fight_odds_fight`, `idx_fight_odds_fight_book_time`, `idx_fight_odds_captured`, `fight_odds_source_event_idx`, `fight_odds_pre_start_idx`, two partial uniques on opener/closer, pk) — adequate for a 126k-row table. Every market view does `DISTINCT ON` plus an exact-timestamp self-join over the whole table; the documented cost is `v_fight_chart_series` at 22 ms for one fight and 4.6 s for twelve (T-058), which is why Market Lab has no sparklines. Market Lab as anon measured 235 ms. No performance problem at current scale; the view design will not scale to card-wide charts without a materialised series.

### A7. Security posture of the data layer (VERIFIED, Supabase advisors 2026-10-12)

- **ERROR**: RLS disabled on `odds_aliases` and `unmatched_odds` (small, but fully writable with the public anon key).
- **ERROR**: 38 `SECURITY DEFINER` views — by design (the browser reads odds only through definer views), but each one is a place where a future column addition leaks without a policy.
- **WARN**: 8 security-definer functions executable by `anon` (`current_user_is_admin`, `current_user_is_pro`, `is_premium`, `alert_quota`, `handle_new_user`, `unsubscribe_email`, `user_alerts_quota_check`, `current_user_entitlement`); 7 functions with mutable `search_path`; leaked-password protection off.
- `fight_odds` and `odds_books` are correctly `private_lockdown_admin_only` live; however `public_read_odds.sql` at the repo root still grants `SELECT` to anon and would expose every raw quote if applied by mistake.
- Overlapping duplicate SELECT policies on `events`, `fighters`, `fights` (five each) — harmless, untidy.
- The two P0s from September (self-promotion to admin; `TRUNCATE` inherited by `authenticated`) are fixed in the SQL and the live policies match.

### A8. Provenance and licensing (INFERRED risk; no terms on file)

No UFCStats, The Odds API or BestFightOdds terms are referenced anywhere in the repository. UFCStats actively blocks datacenter IPs (403 to Railway and CI), which the project works around; the entire stats product is a UFCStats derivative. Odds are republished on every public page, in prerendered stubs, the RSS feed, social posts, the Brief, and — by design of `export.yml` — would be committed daily as raw JSONL to a public GitHub repository if the workflow's missing secret were ever set. Whether The Odds API's free tier permits redistribution is UNKNOWN. `disclaimer.html` states CFL is not a licensed sportsbook. These are the licensing questions a buyer or a lawyer would ask first.

### A9. Which datasets are commercially useful as they stand

1. **Multi-book moneyline time series since 2026-09-19** — provenance-complete, 10 named US books, 5–30 minute cadence in card flow; matched-cohort movement and best-price views already built and tested. Clean but tiny (four cards), the governor is pinned at its coarsest rung, the table is not yet trigger-immutable, and redistribution terms are unverified.
2. **`pre_fight_snapshots`** — an append-only, publicly readable "what was shown before the bell" ledger. 106 rows, one card missing.
3. **Fighter, fight and round statistics with derived views** (consistency v7, finisher rates, division percentiles, Elo, cardio slopes) — the real research value and the thing visitors actually come for (see traffic in `05_`), but a scraped derivative with a stale fighter table (May 2026) and no licence.
4. **`prop_odds` totals ledger** — append-only, clean, 24 fights. Too small to sell.
5. **Pre-2026-09-19 odds history** — research-grade only (24% undated, synthetic rows, corner swaps).

---

## Part B — Predictive modeling

### B1. Inventory

| # | model / experiment | type | status |
|---|---|---|---|
| 1 | `edges.js` verdict heuristic (record, td_def; cardio retired) | hand-tuned Bayesian combiner | archived; no production consumer except `cfl-snapshotter` |
| 2 | `distanceEdges.js` go-the-distance heuristic | heuristic | dead code |
| 3–8 | Legacy v1 (LR), v2 (Elo+GB), v3 (advanced), v4 (stacker), v5 (XGBoost with closer and opener), v6 (XGBoost "value" with opener) | trained in the odds-scraper repo | archive pages only; v1–v4 still retrained nightly |
| 9 | `cfl_engine` win model engine_v1/engine_v2 | walk-forward XGBoost, rolling calibration, market blend, quarter-Kelly | runs daily, writes picks/edges, removed from every public surface (D-011) |
| 10–11 | PROP-0001@v1 (hazard + isotonic) and @v2 (raw hazard) duration models | discrete-time logistic hazard, 49 point-in-time covariates | frozen, serving locks daily |
| 12 | DUR-001 / DUR-002 prospective experiments | residual-on-market test with event bootstrap | collecting; no verdict; 24 fights with market quotes |
| 13 | Count models (sig-strike NB2, takedown hurdle) and simulator (Prop Board) | GLMs | archived surface; cron still runs |
| 14–15 | Cardio fade-slope mixed model; `v_fighter_consistency` tiers | descriptive | published; not rendered / shown as description |
| 16–17 | FE-001 factor evidence; Factor Lab (`factor-rates.json`, 2026-09-18) | market-controlled univariate tests | published |
| 18 | CLV-001 protocol | measurement protocol, not a model | frozen v1.0.10; 0 of 100 observations |
| 19–20 | SYM-002 symbolic search; SYM-003 matchup features | preregistered GP / L2 LR ablation | PR #53, unmerged; results git-ignored |
| 21 | "v1 symbolic" 3-term formula | — | not in any branch; irreproducible |

### B2. Head-to-head against the closing market (VERIFIED artifacts)

| model | window | n | accuracy | log loss | market log loss on the same fights |
|---|---|---|---|---|---|
| engine (calibrated) | 2020-01 → 2026-07 | 3,232 | 61.4% | 0.6511 | 0.5978 (68.0%) — `cfl_engine/benchmark_report.md:14-17` |
| engine, recomputed by this audit from `out_real/oos_predictions.csv` | same | 3,235 | 61.6% | 0.6537 | 0.5979 |
| engine market blend | priced rows | 3,071 | 68.5% | 0.5945 | 0.5979 (+0.003, inside the repo's own 0.015 leak band) |
| v1 / v2 / v3 | 2023+ | 1,205 | 62.8 / 62.7 / 63.7% | 0.641 / 0.638 / 0.638 | market better by 0.041–0.044 |
| v4 stacker (uses opener) | 2025+ | 515 | 62.7% | 0.6254 | market better by 0.014 |
| v5 (uses **closer**) | 2025+ | 400 | 70.8% | 0.5952 | ≈ market — it ingests the market |
| v6 (uses opener) | 2025+ restated | 412 | 70.9% | 0.5956 | scored against the opener, which is an input |
| PROP-0001 raw hazard | 2018+ walk-forward, 9,030 rows | — | — | 0.5037 vs constant hazard 0.5082; vs archived totals market 0.5059 vs 0.5073 on an **irreproducible** subset | isotonic step in the live v1 recipe **worsens** log loss by 0.0148 |

Every honest win-probability model loses to the closing market by 0.014–0.044 log loss. The two models at or above the market use the market price as an input. The engine's blend matches the market only because it contains the market, and requires the closing price, which is not available at bet time.

### B3. The "edge" backtest and the live record

- `out_real/edge_bets.csv` (658 bets, 2021-06 → 2026-07): 519-139, **flat ROI +0.34%**; stake-weighted Kelly +10.0% is the figure that was on the homepage. Year-by-year flat ROI flips sign (2023 −4.1%, 2026 −1.4%). Bets are blend-vs-close favourites.
- Live engine picks (VERIFIED live DB): 155 graded, 91 hits = **58.7%**, no market control. `v_pre_fight_graded`: engine_v2 40 won / 39 lost; engine_v1 13 / 10.
- Live edges: 65 settled, 46 won, +$356 on $6,500 flat (+5.5%); legacy `clv_pp` mean +2.2 points, 44 of 64 positive. This CLV is the vigged single-side construction the frozen CLV-001 protocol declines to publish; the sample is 65, below every floor the project set (100 picks; 100 observations across 20 events).
- CLV-001 protocol-grade observations: **0**. The dry run scored 0 of 47 eligible rows because no settled card had a sportsbook quote inside the 45-minute limit.

### B4. Factor evidence (VERIFIED `factor-rates.json`, generated 2026-09-18T18:32Z; 8,739 fights scored, 1,220 market-even)

| factor | raw win % | market-even n / win % (95% CI) | verdict |
|---|---|---|---|
| age (younger wins) | 57.1 (n 8,612) | 1,219 / 56.5 (53.7–59.3) | real |
| raw UFC record gap (5+ prior UFC fights each) | 62.7 (1,347) | 185 / 58.4 (51.2–65.2) | real, every band individually unproven |
| takedown defence | 54.8 | 430 / 50.2 | proxy for the line |
| reach, height, southpaw-reach, strike volume, finish rate | 50–57 | 48–52 | proxy |

FE-001 adds the exact `edges.js` definitions: record 50.2% and td_def 50.5% on market-even fights — coin flips. Age is already an engine feature and the engine still loses to the close; a univariate 56.5% on 14% of fights is a descriptive finding, not a tradable edge.

### B5. Leakage and overfitting concerns, by model

- `edges.js` backtest used current career totals that contain the predicted result; published tier percentages trace to no artifact.
- v5 trains on the closing line; v6's test window overlapped training until 2026-08-19; v1–v4 cutoffs "not verified" so the archive page floors them at 2025.
- Engine: point-in-time features audited (0/17,544 structural leaks claimed in `INTEGRATION_STATUS.md`, narrative), but the "closing" price it is scored against comes from `fight_odds` rows of which 24% carry a 1970 timestamp and 1,578 are corner-swapped — "closing" is unverified for the historical window.
- PROP-0001: the gate report's generator is not in the repo; the market subset is irreproducible; a prior headline (0.483378 / 3,793) was withdrawn; the first 48 locks were written from a dirty tree.
- SYM-002/003: results are git-ignored; the report generator hard-codes the conclusion that no formula beat a plain regularised LR and that the archived market beat every fighter-only model (`make_report.py:140-157`).

### B6. Deployment status

Nothing predictive is shown to the public (enforced by `tests/no-model-on-public-surfaces.test.js`, 58 assertions, passing). The engine, legacy retrains, duration locks, prop projections, snapshots and legacy CLV settlement all still run daily, writing an auditable private record. The Proof Center and Model Archive pages show the graded record behind archive banners.

### B7. Outstanding research (from the project's own registers)

DUR-001/002 need a decision point and nine owner votes on amendments (T-002); `prop_odds` coverage is 24 fights. CLV-001 cannot score until three migrations land (A-010) and cannot publish until 100 observations across 20 events exist. FE-001's correction to `edges.html` (T-025) is L3. The cardio mixed model's validation numbers were never committed. SYM-002/003 sit in an unreviewed PR outside the research register. The dead man's handle cannot observe its own silence (T-076).

### B8. Verdict on commercial deployment or trading

**Not supported by the evidence.** No CFL model beats the closing market; the only constructs that match it contain it; prospective evidence is 65 bets and zero protocol-grade CLV observations; the duration model's market result is irreproducible and its live calibration is unvalidated. D-011 — keep the engine running privately, publish nothing until prospective evidence exists — is the conclusion the artifacts support. The research governance is unusually strong for a one-person project; the predictive evidence is not.
