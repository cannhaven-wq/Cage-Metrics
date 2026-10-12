# 07 — Project history and fragmentation

Audit date: 2026-10-12. Evidence: full git history of `origin/main` (1,063 commits, 2026-04-26 → 2026-10-12, unshallowed for this audit), the 52 remote branches, `coordination/DECISIONS.md` (D-001…D-020), `coordination/HANDOFF.md`, `coordination/AUDIT_2026-09-18.md`, `BRANCH_NOTES.md`, the merged-PR list from the GitHub API (51 PRs). Tags: **VERIFIED** (git or document evidence), **INFERRED** (my reading), **UNKNOWN**.

## 1. Headline numbers (VERIFIED)

| | |
|---|---|
| Commits on `origin/main` | 1,063 — Apr 37 · May 185 · Jun 130 · Jul 172 · Aug 195 · Sep 285 · Oct 59 |
| Authors | `github-actions[bot]` 646 (61%) · Reed Cannon 163 · cannhaven-wq 137 (same person, two git identities) · Claude 117. No other contributor. ChatGPT appears only as a reviewer in prose. |
| Bot commits | 597 "regenerate prerendered stubs [skip ci]" (6-hourly cron), 43 social-post markers, 6 validation regenerations |
| Human commits | 417, of which ~83 are April/May web-upload and rename noise and 52 are merge commits |
| Pull requests | 51 numbered; 48 merged; #3 and #26 closed unmerged ("PARKED"); #52 and #53 open |
| Remote branches | 52 including `main`; 13 carry unmerged commits (table in §5) |
| Repo shape today | 31 root HTML pages, 34 root `*.sql` files, 19 workflows + Pages, 23 test files, ~5,400 generated stub pages in `f/`, `e/`, `card/`, `preview/` |
| `CLAUDE.md` | 26 commits; 104 lines (2026-05-06) → 566 lines today |
| Last human commit on `main` | 2026-10-05. Everything since is the stub cron. |

## 2. Timeline by month (VERIFIED unless marked)

**April 2026 — "CageMetrics — UFC Stats for Bettors".** First `index.html` (`0ea6f1be`, 04-26) carries that title; by `5e12d6b0` (04-29) the uploaded page already says "Cannon Fight Lab". The rename happened in GitHub-web uploads with no commit recording it. The whole month is 37 "Add files via upload / Rename index_N.html" commits. First appearance 04-30 of `parlay.html`, `stats.html`, `h2h.html`, `event.html`, `fighter.html`, `about.html`. Original objective (INFERRED from title and page set): a stats and odds reference site for UFC bettors.

**May 2026 — a picks product built in a fortnight.** `cardio.html`, `edges.js`, `pricing.html`, `login.html`, `account.html` (05-01/02). `CLAUDE.md` and the prerender pipeline born 05-06 (`d2c378af`, `ed1eb5c1`). 05-15: sixteen commits in a day produce the rules-based verdict model, `edges.html`, and the first market-odds pull with a model-vs-market edge per fight (`435b39ac`, `build/fetch-odds.js`, `odds.yml`). 05-22: `predictor.html`, `lab.html`, `picks.html`, Kelly sizing, SRI-pinned Supabase CDN. 05-23: first CLV indicator (`eb01b170`) and "reframe as research, not advice" the same day. 05-24: `mybook.html`, `methodology.html`, disclaimer, privacy. 05-28: first Claude-authored PRs (#1, #2): traffic funnel, `social-post.js`, `send-digest.js`; homepage rewired to trained models v1–v4. **05-30 `d8eb18c1` "lead with 70% accuracy claim from v5"** — later flagged as a model trained on the closing line.

**June 2026 — silence, then an outage.** No human commit from 05-30 to 06-28. 06-28 `b48e36cb` fixes a site-wide perpetual load screen caused by a stale Supabase SRI hash (duration of the outage UNKNOWN). 06-30: The Odds API replaces the stalled BestFightOdds cron; redesign phase 1.

**July 2026 — Proof Center, Card Lab, content engine, cfl_engine.** 07-01: "first-capture openers" and a synthetic consensus row written into `fight_odds` (`48471f9a`, origin of the later-retired `open_p_a`); "Trust + conversion overhaul" creates `card-lab.html`, `track-record.html`, `fight-insights.js`. 07-04: social content engine, approval dashboard, X/Reddit auto-post, Metricool CSV, a desktop posting-app generator. 07-16: "three honest products" restructure (`factor-rates.json` born) and `cfl_engine/` integrated (Python walk-forward model). `INTEGRATION_STATUS.md` records engine_v2 at 61.5% out-of-sample and a simulated "519-139, Kelly +10.0%" that was still on the homepage on 2026-09-18.

**August 2026 — engine-first cutover, pre-fight record, council branches.** 08-02 engine-first cutover (41 files). 08-07 all six legacy models unretired, then hidden behind a Compare toggle the same day. 08-08 Prop Board. 08-13 `council/*` PRs #4–#7: `COPY_STYLE.md` (first "CLV is the north star" wording), `picks.html` retired to a redirect, Card Lab merged into the homepage. 08-15 pre-fight snapshot rule (`snapshot_predictions.py`, `pre_fight_snapshots`). 08-18 "fix every claim the Aug 18 audit flagged" (that audit is not in the repo). 08-19: cardio retired as a pick factor, mixed-effects fade-slope model, duration and count gate reports (the future PROP-0001), "retire My Book" (page still present), v6 restated on an honest window, `settle-clv.yml`.

**September 2026 — governance explosion, repositioning, monetization.** 09-01 the May rules model retired from every visible surface. 09-14 DUR-001 and PROP-0001 locks. 09-15/16 eight `research/*` branches: registry and sha256 tripwire, provenance audit (locks written from a dirty tree), DUR-002 frozen. **09-16 `8c30f7e8` the `coordination/` layer is born** (D-001, "proposed by ChatGPT"), plus `proof.html`, Event Flow, and CLV-001 taken from v0.2 draft to v1.0.10 in 18 commits in one day. 09-18 (≈50 commits): CI runs the test suite for the first time, `AUDIT_2026-09-18.md`, FE-001, the Factor Lab paging bug (869 → 1,220 market-even fights, seven verdicts moved). 09-19 UFC 331: capture columns applied, the cadence gate that lost a card day, D-010 "no edge claimed". **09-21 `24819e06` D-011: the model comes off the product** (`market.html`, `fight.html`, `market.js` born), followed the same day by D-012…D-020: matched-cohort movement, funnel analytics, entitlements and the `is_admin` P0, Stripe built and locked, no-paywall-before-payment, watchlists and alerts. Fifteen of twenty decisions were written in six days; ten on one day.

**October 2026 — ops hardening, then quiet.** 10-01/02 inert snapshot guard fixed (a card had already been lost); odds name-matching for diminutives. 10-05 dead man's handle (`check-pre-fight-coverage.js`, `dead-man.yml`), `cfl-snapshotter` cron finally set on Railway. 10-07 SYM-002/SYM-003 symbolic-regression research opened as PR #53. 10-05 → 10-12 no human commits on `main`.

### First-appearance table (VERIFIED, `git log --diff-filter=A`)

| path | first commit |
|---|---|
| `index.html` | 2026-04-26 `0ea6f1be` |
| `parlay.html`, `stats.html`, `h2h.html`, `event.html`, `fighter.html` | 04-30 `48c9c8c0` |
| `edges.js` | 05-02 `2aa94031` |
| `pricing.html`, `login.html`, `account.html` | 05-02 `02dffa63` |
| `CLAUDE.md`, `build/prerender.js`, `research/` | 05-06 |
| `edges.html`, `build/fetch-odds.js`, `odds.yml` | 05-15 |
| `predictor.html`, `lab.html`, `picks.html` | 05-22 |
| `mybook.html`, `methodology.html` | 05-24 |
| `build/social-post.js`, `build/send-digest.js` | 05-28 |
| `card-lab.html`, `track-record.html`, `fight-insights.js` | 07-01 `08c0a734` |
| `build/social-engine.js` | 07-04 |
| `factor-rates.json`, `cfl_engine/` | 07-16 |
| `props.html` | 08-08 |
| `COPY_STYLE.md` | 08-13 |
| `snapshot_predictions.py`, `pre_fight_snapshots_migration.sql`, `snapshot.yml` | 08-15 `e197f361` |
| `cfl_engine/dur001` | 09-14 |
| `tests/`, `research/registry.json`, `coordination/`, `research/clv`, `proof.html` | 09-16 |
| `fight_week_views.sql` | 09-19 |
| `market.html`, `fight.html`, `market.js` | 09-21 `24819e06` |
| `entitlements.js`, `billing_migration.sql`, `billing-lifecycle.js`, `alerts_migration.sql`, `alerts.js`, `watchlist.html` | 09-21 |
| `build/check-pre-fight-coverage.js`, `dead-man.yml` | 10-05 `34aa9224` |

## 3. Pivots (VERIFIED)

| pivot | when | evidence |
|---|---|---|
| Cage Metrics → Cannon Fight Lab | between 04-26 and 04-29 | titles in `0ea6f1be` vs `5e12d6b0`; no commit message records it |
| Stats reference → rules-based picks | 05-15 | `435b39ac` first model-vs-market edge |
| Rules → six trained models (v1–v6, in the odds-scraper repo) | 05-28 → 05-30 | `1b536709`, `d8eb18c1` |
| v1–v6 → `cfl_engine` Python walk-forward | 07-16 → 08-02 | `f3ca4c07`, `8a184567` |
| Picks page retired; Card Lab merged into the homepage | 08-13 | PRs #5, #7 |
| Pre-fight record becomes a hard rule | 08-15 | `e197f361` |
| CLV as north star → frozen measurement protocol | 08-13 wording; 09-16 protocol | D-003, D-005 |
| Duration model (PROP-0001), DUR-001, DUR-002 | 08-19 gate reports; frozen 09-15/16 | `research/registry.json` |
| `coordination/` and the ChatGPT review loop | 09-16 | D-001 |
| **Engine removed from the product (D-010, D-011)** | 09-19 / 09-21 | engine 61.4% vs close 68.0% in `cfl_engine/benchmark_report.md` |
| Monetization and retention sprint | 09-21 | D-017…D-020 |
| Ops hardening (snapshot guard, dead man) | 10-01 → 10-05 | PRs #47, #49, #50 |

The sequence is: build a picks product (May), discover it cannot beat the market (July–September), build a governance apparatus around that discovery (September), remove the picks and reposition as market intelligence (09-21), then build the subscription and alert machinery for the repositioned product (09-21) — none of which is switched on.

## 4. Features built and then abandoned or archived (VERIFIED dates)

| feature | built | archived / removed | why |
|---|---|---|---|
| Rules-based `edges.js` verdict (age, streak, cardio, record, td_def) | 05-15 | cardio retired 08-19; whole May model off every surface 09-01; `computeEdges` has no production consumer | coin-flip under market control (FE-001) |
| `distanceEdges.js` distance predictor | 05-15 | superseded by PROP-0001 | file still at root, dead |
| v1–v6 trained models and the "70%" v5 claim | 05-28/30 | hidden 08-07; archive only after D-011 | v5 trains on the closing line; v6 window overlapped training |
| `picks.html` | 05-22 | redirect stub 08-13 | merged into Card Lab |
| `card-lab.html` | 07-01 | redirect stub 08-13 | merged into homepage |
| `predictor.html`, `edges.html`, `methodology.html`, `track-record.html`, `proof.html` | 05-22 … 09-16 | all archive pages after D-011 | model off product |
| Prop Board (`props.html`, `prop_projections` cron) | 08-08 | archived, noindex 09-21 (D-013) | still a model surface; cron still runs daily |
| `mybook.html` Kelly verdicts | 05-24 | "retire My Book" 08-19; page still live, fate open (T-050) | |
| Value edge %, Value alert, parlay strip | 05-15 / 08-13 | removed 09-19 (D-010) | unsupported claim |
| `open_p_a` / first-capture "opener" baseline | 07-01 | removed 09-21 (D-012) | overstated moves by up to 12.7 points; still read by `send-digest.js` and `social-post.js` |
| Social content engine, Metricool CSV, posting desktop app, `social/` batches | 07-04 | manual-only; batches stale since July; copy quotes the retired model | T-038/T-039 open |
| `fight-week-v2` Event Hub / Market Board / Brief | 09-15 branch | never merged; D-011 built Fight Lab and Market Lab instead | |
| `lab.html` private backtest | 05-22 | unlinked, now noindex | includes training data |
| CLV indicators on picks page, My Book "vs earliest price" column | 05-23/24 | forbidden until CLV-001 thresholds are met (T-041) | |

## 5. Branches (VERIFIED)

52 remote branches including `main`. 38 are fully merged. 13 carry unmerged commits:

| ahead | last commit | branch | content | status (INFERRED) |
|---|---|---|---|---|
| 21 | 2026-05-30 | `claude/macau-event-v5-accuracy-kWvZe` | Macau backfill, UFCStats probing | abandoned |
| 8 | 05-28 | `claude/automated-traffic-funnel-9IFf4` | duplicates of merged funnel work | abandoned |
| 4 | 07-04 | `council/stats-accuracy-and-ui-fixes` | duplicates of merged content-engine work | abandoned |
| 13 | 08-09 | `council/props-output-layer` | sig-strike/takedown models, simulator, reverted paper-picks migration | abandoned |
| 7 | 09-15 | `fight-week-v2` | Event Hub, Market Board, Fight Week Brief, `hub_visits` | superseded by D-011 (T-033) |
| 2 | 09-15 | `revenue/trust-funnel-v1` | claim manifest, forecast wording | superseded (T-034) |
| 1 | 09-17 | `claude/email-capture-modal-gbkqri` | email prompt after 2 minutes | never approved (T-035) |
| 4 + 1 | 09-18 | `claude/brave-cray-rssmll`, `-factors` | earlier audit/FE-001 drafts | parked (PR #26 closed) |
| 1 | 09-21 | `claude/cool-gates-tbdy00` | matchup-analytics gap audit and spec | never merged |
| 1 | 10-05 | `claude/trusting-cori-sfllu9` | D-021 owner naming (closes T-009) | pending |
| 1 | 10-05 | `claude/watchdog-scope` | PR #52, Friday-only watchdog scope (T-077) | open PR |
| 4 | 10-07 | `claude/cool-sagan-osv7iq` | PR #53, SYM-002/SYM-003 symbolic regression | open PR, outside the research register |

Naming families: `claude/<adjective-scientist-id>` (Claude Code sessions, 32), `council/*` (7, Aug 8 → Sep 14, INFERRED the pre-`coordination/` review era), `research/*` (8, all 09-15/16, all merged).

## 6. Repeated and duplicated engineering (VERIFIED)

- **Four generations of prediction model**, each with its own harness: rules `edges.js` (`research/validate.js`, `lab.html`) → v1–v6 in the odds-scraper repo → `cfl_engine` engine_v1/v2 (`cfl_engine/harness`) → PROP-0001/0002 duration and count models (`walkforward_prop0001.py`); plus SYM-002/003 on an unmerged branch.
- **Three movement baselines**: BestFightOdds opener (05-25), CFL first-capture opener `open_p_a` (07-01), matched-cohort first broad capture (09-21, D-012).
- **Three generations of market view files**: `fight_week_views.sql` → `market_lab_views.sql` (now a pointer) → `market_movement_views.sql`, plus `market_horizon_views.sql` and `market_chart_views.sql`. `v_fight_odds_latest_by_book` is defined in two files with different windows.
- **Three social generators** reading one table: `draft-post.js` (05-26), `social-post.js` (05-28), `social-engine.js` (07-04), plus Metricool CSV and a desktop app.
- **Three audits in two months**: the "Aug 18 audit" (not in the repo), `council/frontend-audit` (08-13), `AUDIT_2026-09-18.md`; plus a data-integrity audit, a provenance report and `verify-live.yml`. This document is the fourth.
- **Card page merges**: picks → card-lab → index (05-22, 07-01, 08-13), then the homepage rebuilt again at D-010 (09-19) and D-011 (09-21).
- **Two trust pages** (`proof.html`, `track-record.html`), **three URLs per event** (`/card/`, `/e/`, `event.html?id=`), two handoff files, two state registers.
- CLV-001 went through eleven version bumps of a "frozen" document in one day.

## 7. Architectural fragmentation (VERIFIED)

- 31 standalone HTML pages each with inline JS; shared chrome rendered by `_shared.js`; script load order is load-bearing; SRI hashes must be replaced by hand across every page, which once took the whole site down.
- 34 SQL files at the repo root with no runner and no ordering; applied state lives only in prose. The Supabase migration log has 24 entries, all from 2026-09-14 onward; everything earlier was applied through the SQL editor. Core table DDL (`events`, `fighters`, `fights`, `fight_rounds`, `fight_odds`, `odds_books`, `profiles`, `model_predictions`, `predictions`) is not in this repo at all.
- Engine in Python (`cfl_engine/`, 18 workflows) while verdict, market, alert and billing logic is in browser-shared JS; the Stripe lifecycle rules are duplicated inside a Deno edge function with a test asserting the copies agree.
- **Five repositories**: this one plus `cage-metrics-scrapper`, `cage-metrics-odds-scrapper` (main `fight_odds` writer, v1–v6 training, Polymarket capture), `cage-metrics-event-scrapper`, `cfl-snapshotter`. Writers to one append-only table live in three repos.
- Scheduling split across GitHub Actions (throttled, several crons commented out), Railway crons (two odds-scraper services whose every deploy since 2026-07-01 has failed), and 18 Supabase edge functions of which 16 are research scratch not in the repo.
- ~5,400 generated stub files in git; 61% of commit history is the stub cron.

## 8. Decisions that created maintenance burden (INFERRED, evidence cited)

- Committing prerendered stubs (05-06) → 597 bot commits, 25 MB, and a history where human work is hard to find.
- Shipping the 70% v5 claim (05-30) and simulated Kelly figures (07-19) → four contradicted public claims and the D-007/D-010 cleanup.
- Writing a synthetic consensus row and "openers" into `fight_odds` (07-01) → `bookmaker_count` is not a book count; `open_p_a` had to be removed; immutability triggers must whitelist `is_opener`/`is_closer`.
- Per-page inline JS with hand-synced SRI and `?v=` cache-busters → the 06-28 outage and repeated cache-bust commits.
- Root-level SQL with no runner → "verify grants after applying" written three times in CLAUDE.md after three grant defects.
- Freezing CLV-001 before any eligible data existed → a v1.0.10 protocol that has scored nothing; five migrations, two applied.
- The coordination layer itself: `STATE.md` 853 lines, `DECISIONS.md` 1,563 lines, `CLAUDE.md` 566 lines, all prose; `HANDOFF.md` needed two same-day corrections and its preamble is currently corrupted.

## 9. Work that generated little practical value (INFERRED)

- The May–August picks and edge product line: rules, v1–v6, Kelly sizing, My Book verdicts, Value alerts, parlay strip. Removed by D-010/D-011; its residue is five archive pages and a test forbidding it.
- Social engine, Metricool, desktop posting app: manual-only, stale since July, copy uses the retired framing; the Mon/Wed/Fri poster now builds empty posts because it reads a column that no longer exists.
- `fight-week-v2`, `revenue/trust-funnel-v1`, `council/props-output-layer`: ~22 unmerged commits superseded within days or weeks.
- Stripe, entitlements and alerts (09-21): fully built and tested, none of it runs — no Stripe account, no `RESEND_API_KEY`, alerts cron off, nothing gated.
- DUR-001 backfill gate refusing everything pending nine owner votes since 09-16.
- `export.yml` daily table export: fails every day on a missing secret; no `data/` commit has ever landed.

## 10. Infrastructure worth reusing (VERIFIED existence)

- Append-only `pre_fight_snapshots` with trigger enforcement, `snapshot_predictions.py`, and the dead man's handle with 42 tests.
- `build/fetch-odds.js` cadence governor with credit ceiling, provenance columns and name-matching tiers.
- The matched-cohort market views and `market.js` wording rules, with `market-chart.js` cohort assertion.
- Pure, clock-injected, tested modules: `alerts.js`, `billing-lifecycle.js`, `entitlements.js`, `proof-gates.js`.
- Policy-as-tests: `no-model-on-public-surfaces`, `publish-gate`, `record-factors-distinct`, `sitemap-hygiene`.
- Research register and sha256 tripwire; the preregistration pattern (DUR, CLV, SYM).
- Event Flow ingestion and read-only reconciliation (unused in production because UFCStats blocks datacenter IPs).
- Prerender, sitemap and feed pipeline; `build/factor-rates.js` point-in-time scorer with Wilson intervals and market control.

## 11. Commit share by theme (ROUGH)

Over the 417 human commits: upload/rename noise ~20%, merges ~12%, research/governance/audits/protocols ~30%, ops/infra/data ~12%, product UI ~17–22%, social/SEO ~5%, copy ~4%. Over all 1,063 commits bots are 61%. Categorisation is keyword-based and overlapping; treat as ±5 points.

## 12. What could not be reconstructed (UNKNOWN)

- The exact rename commit (web uploads).
- The "Aug 18 audit" and the `council/frontend-audit` content.
- The script that produced `cfl_engine/harness/walkforward_report.json`.
- The original working tree behind the PROP-0001 dirty locks.
- Why no commits landed 05-30 → 06-28, and how long the SRI outage lasted.
- The four external repositories beyond `FIGHT_ODDS_WRITER_INVENTORY.md` and Railway deployment metadata (see `02_SYSTEM_ARCHITECTURE.md` for what Railway shows).
