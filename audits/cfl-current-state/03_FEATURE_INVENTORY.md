# 03 — User-facing feature inventory

Audit date: 2026-10-12. Every root page and cross-page feature was read in code; live data was checked through read-only SQL; the rendered site could not be fetched from the audit container (the repo's `verify-live.yml` last passed 2026-09-21). Tags: **VERIFIED**, **INFERRED**, **UNKNOWN**. Classification: PRODUCTION READY / FUNCTIONAL BUT INCOMPLETE / PROTOTYPE / BROKEN / PLANNED ONLY / UNKNOWN. A deployed page is not counted as a completed feature unless its data path is populated and running.

## 1. Product surfaces

| feature | what the user can do today | data path | populated live? | public? | class | what blocks / remains |
|---|---|---|---|---|---|---|
| **Card Lab** (`index.html`) | See the next or live card; per fight the vig-free consensus, fair price, market move since first broad capture with book count, best price and book; sort by card order, biggest move, books disagree; open Fight Lab; star a fight (account wall); email signup | `events`, `fights`, `fighters`, `v_fight_market_movement`, `v_fight_market_horizons`, stat views | Yes — next card (Buckley vs Malott, 10-17) has 14 of 16 fights priced across 8 books, captured 2026-10-12 | yes, nav | **PRODUCTION READY** (VERIFIED code; data running) | Only 98 sessions reached it in three weeks (see `05_`). "Free during beta" banner. |
| **Market Lab** (`market.html`) | Whole card as a board: consensus, best price each side, move since baseline and over 24 h, book spread, capture age; expand per-book table; "what changed in 24 h" | same views plus `v_fight_odds_latest_by_book` | yes | yes, nav | **PRODUCTION READY** | Copy at `market.html:150-157` says charts, alerts and watchlists are "not built yet" — they are. No card-wide sparkline (T-058). 19 sessions in three weeks. |
| **Fight Lab** (`fight.html`) | One matchup: both corners' consensus, best and fair price, two movement horizons, stepped movement chart, per-book table, measured matchup differences, career stats; star; set a price-target or movement alert | market views, `v_fight_chart_*`, `v_fight_alert_market`, `v_my_alerts` | yes | yes, linked from every card row | **PRODUCTION READY** as a page | Alert form promises "We will email you when it happens" (`fight.html:506`); nothing can send that email today (§3). |
| **Factor Lab** (`stats.html`) | Read eight factor cards with raw and market-even win rates, intervals and plain verdicts; stat-finder insights | static `factor-rates.json` + six stat-finder views | artifact dated 2026-09-18 (24 days old, by design); live views populated | yes, nav | **PRODUCTION READY** | Refresh is a manual reviewed PR. Meta tags still say "UFC betting insights". 10 sessions in three weeks. |
| **Event page** (`event.html`) | Full card or past results, per-fight market band, matchup notes, tape | fight data + market views | yes | yes, linked from stubs and feed | **PRODUCTION READY** | Runtime `<title>` for upcoming events still reads "… UFC Predictions" and description "model odds" (`event.html:695-698`), outside the no-model test's reach. 431 sessions in three weeks. |
| **Fighter page** (`fighter.html`) | Profile, record, cardio tier, style, finish profile, Elo opponent quality, next-fight market and notes, prop projection | fighter data, `fighter_ratings`, `v_fighter_*`, **`v_fighter_model_record`**, **`v_prop_projections_current`** | yes, but the fighter table is 4,495/4,554 stale since May 2026 and 2,222 fighters lack a division | yes; **the most visited page** (1,157 sessions in 14 days) | **FUNCTIONAL BUT RULE-VIOLATING** | `fighter.html:906-928` renders "Model called X of N", "Beats/Trails expectations" and "a fade candidate at a short price" from the engine's graded record; `:993-1004` shows prop-model projections without the archive banner `props.html` carries. `v_fighter_model_record` is not in the test's banned reads. |
| **Fighters index** (`fighters.html`) | Search and filter 4,554 fighters | `fighters` | yes (stale profiles) | yes, More menu | PRODUCTION READY | |
| **Head-to-head** (`h2h.html`) | Pick two fighters and compare stats | fighter data | yes | yes, More menu; sitemap 0.8 | PRODUCTION READY but **DUPLICATIVE** of Fight Lab's stat block | 1,229 sessions in 14 days — the second most visited page, every session a distinct visitor (INFERRED: inbound links from the 75 preview stubs and search). No market data on it. |
| **Cardio Scores** (`cardio.html`) | Leaderboards and per-fighter cardio curves | `v_fighter_consistency` v7, `v_fighter_cardio_curve` | yes | yes, More menu | PRODUCTION READY | 1 session in 14 days. |
| **Parlay Calculator** (`parlay.html`) | Build legs from upcoming cards, edit price, see combined odds and payout; prefilled from best tracked price | `v_fight_odds_latest_by_book` | yes (fixed from the months-long zero-rows bug) | yes, More menu; not in sitemap | FUNCTIONAL | Whether it should exist is an open owner question (T-050). 9 sessions. |

## 2. Archive and explainer surfaces

| page | status | notes |
|---|---|---|
| **Proof Center** (`proof.html`) | PRODUCTION READY as an evidence page; archive banner | Live record vs replay never summed; CLV box deferred (correct: 0 observations). 4 sessions in 14 days. |
| **Model Archive** (`track-record.html`) | archive, functional | Computes accuracy/calibration/ROI live from `model_predictions`; CTA at `:389` goes to the `card-lab.html` redirect stub; uses "opening line" wording seven times (archive-exempt). |
| `predictor.html` | archive, **orphan**, noindex | No inbound link; still runs a Kelly bankroll calculator (`:729-746`). |
| `edges.html` | archive | Factor table still marks Record "60–72% · Active" while FE-001 measured ~50.2% on market-even fights (T-025, owner-gated). |
| `methodology.html` | archive/explainer | fine |
| `props.html` Prop Board | archive, **orphan**, noindex | No inbound link; the same projections appear unbannered on `fighter.html`; the daily `props-refresh.yml` keeps writing to it. |
| `lab.html` | internal, noindex | Reads admin-only `fight_odds`/`odds_books` with the anon key → its comparisons are silently empty. **BROKEN** (INFERRED), internal only. |
| `about.html`, `disclaimer.html`, `privacy.html`, `contact.html` | static | `privacy.html` does not name Plausible (checkout blocker T-054); no Terms page exists (T-048); `about.html:194` says features are "still rolling out". |

## 3. Member features

| feature | built | runs end to end? | live usage | class |
|---|---|---|---|---|
| **Accounts** (signup, login, reset, account page, display name, password) | yes (`_auth.js`, four pages) | INFERRED yes (email-confirmation setting UNKNOWN) | 8 accounts, last sign-up 2026-09-11, **0 sign-ins in the last 30 days** | PRODUCTION READY, unused |
| **Beta premium** | every account gets `beta_premium=true`; `account.html` shows billing state through `v_my_billing` | yes | 8/8 | PRODUCTION READY |
| **Watchlist** (`watchlist.html`, star buttons) | yes; owner-scoped tables, 53 alert tests | database writes work (INFERRED) | **0 rows** in `user_watchlist` | PRODUCTION READY UI, unused |
| **Price-target and movement alerts** | yes: `alerts.js` pure rules, `v_fight_alert_market` refusals, `build/send-alerts.js` sender with dedupe-before-send | **No.** `alerts.yml` cron is commented out pending a controlled delivery test (T-073); `RESEND_API_KEY` unset (T-074); 4 manual runs on 2026-09-21 only | 0 alerts; 1 test delivery row | **PLANNED ONLY in production** — UI promises an email the system cannot send |
| **Cannon Card Brief** weekly email | yes (`build/send-digest.js`, pick-free, 7 tests); signup widget on four pages | Runs every Wednesday in dry-run; sends nothing; **also reads a column (`open_p_a`) that no longer exists**, so the movement line would be empty even with a key | **0 subscribers** | PLANNED ONLY in production |
| **My Book** (`mybook.html`) | bankroll, bet log, auto-settle, P&L | yes (INFERRED) | 1 bankroll, 3 bets | FUNCTIONAL BUT INCOMPLETE: copy still says "consensus picks", "simulated value flags", "beat the opener"; dead Kelly controls; "retire My Book" was decided 2026-08-19 and not done (T-050) |
| **Free vs Pro** | `PRODUCT_BOUNDARY.md` written; `entitlements.js::SURFACES` has 19 rows all `enforced:false`; `current_user_is_pro()` exists | nothing gated, by decision (D-019) | — | PLANNED ONLY |
| **Pricing and Stripe** (`pricing.html`, two edge functions, `billing-lifecycle.js`, 46 tests) | yes, end to end | **Cannot take money**: Subscribe button disabled in HTML; checkout 503 naming two legal blockers; no Stripe account, no price, no secrets | `pricing_view` 5 sessions; Pro column says "Not for sale" and "the features listed above are not built" (they are built and free) | FUNCTIONAL BUT INCOMPLETE, locked by design |
| **Premium waitlist** (`cflAuth.joinWaitlist`) | function exists | no page calls it | 0 rows | dead code |

## 4. Outbound channels

| channel | built | live behaviour (VERIFIED) | class |
|---|---|---|---|
| **Social auto-poster** (X, Reddit) | `build/social-engine.js` regenerates a queue from `model_picks.p_cal`, templates "our model reads A NN% over B", stamps every piece `positioning:'research'`; `build/social-post.js` posts the next stamped piece Mon/Wed/Fri | **Posting model percentages to X.** Run 37993596942 (2026-10-09) tweeted "BONFIM 50% over PRADO, and they finish at an elite clip…" with image, tweet id 2108670936010387493. Reddit skipped (client id/secret unset). 41 pieces marked posted; markers 10-05, 10-07, 10-09. | **BROKEN against D-011** — the one channel still publishing a forecast in CFL's name |
| **SEO stubs and previews** | prerender every 6 h | 14 of 75 `preview/*.html` carry "Cannon Fight Lab's models pick X … beat the opening price" in FAQ JSON-LD; all in the sitemap | BROKEN against D-011 (structured data only, invisible on the page) |
| **RSS feed** (`feed.xml`) | yes | market-framed; fine | OK |
| **GitHub issues** from the dead man | yes | never triggered | OK |
| **Discord** DUR-001 alert | code exists | not wired | PLANNED ONLY |

## 5. Rule violations and contradictions found (beyond what the test suite catches)

| # | where | what | severity |
|---|---|---|---|
| V1 | `social-post.yml`, `build/social-engine.js:513,373,473,551`, `build/social-post.js:339-365` | Scheduled job publishes model-percentage tweets; verified live post on 2026-10-09 | **P0** |
| V2 | `build/preview-templates.js:162-172`, 14 `preview/*.html` | "models pick X … beat the opening price" in public JSON-LD; forbidden phrase "opening price" too | P1 |
| V3 | `fighter.html:906-928` | Engine record and "fade candidate at a short price" on the most visited product page | P1 |
| V4 | `fighter.html:993-1004` vs `props.html` | Same prop projections archived on one page, product-styled on the other | P2 |
| V5 | `event.html:695-698` | Runtime title "UFC Predictions", description "model odds" on an indexed page | P2 |
| V6 | `market.html:150-157`, `pricing.html:121-131,176` | Say charts, alerts, watchlists are not built | P2 copy |
| V7 | `mybook.html:199-202,552,854,860,233-240` | "consensus picks", "simulated value flags", "beat the opener", dead Kelly controls | P2 (gated, noindex) |
| V8 | `fight.html:506` | Promises an email that cannot be sent | P2 |
| V9 | `edges.html:444-450` | Record factor "60–72% · Active" contradicts the published measurement | P2 (owner-gated T-025) |
| V10 | `track-record.html:389`, `predictor.html:614`, `_shared.js:484` | Links to the `card-lab.html` redirect stub | P3 |
| V11 | `_shared.js:551` | Nav badge "MARKET · LIVE" while every page says prices are not live | P3 |
| V12 | `COPY_STYLE.md`, `coordination/STATE.md` "Site" section | Style guide and state still describe a picks product | P2 governance |
| V13 | `tests/no-model-on-public-surfaces.test.js` | Scans only root pages; `BANNED_READS` omits `v_fighter_model_record`; no scan of `social-engine.js`, stubs, or runtime meta strings | coverage gap |
| V14 | `social/` (80 tracked files, 11 MB) | Pre-repositioning batches with "our model 69%" copy and a dashboard are served by Pages with no noindex | P2 |

## 6. Unfinished, abandoned, duplicated or disconnected

- Orphan pages: `props.html`, `predictor.html` (no inbound link). Internal broken page: `lab.html`.
- Dead code on product: `edges.js` (kept for the snapshotter), `distanceEdges.js`, `model-weights.json`, `cflAuth.joinWaitlist`, My Book Kelly controls.
- Duplicates: `h2h.html` vs `fight.html`; three URLs per event (`event.html?id`, `/e/`, `/card/`), two per fight; `proof.html` vs `track-record.html`; three social generators.
- Switched off: `alerts.yml`, `event-flow.yml`; `export.yml` failing; Reddit posting.
- Unmerged: `fight-week-v2` (7 commits), `revenue/trust-funnel-v1`, email-capture modal, SYM-002/003 (PR #53), watchdog scope (PR #52), D-021 owner naming.

## 7. Is there a coherent, functioning MVP?

**Yes, for one audience, and it is free.** A logged-out UFC bettor who wants market context rather than picks gets a complete, internally consistent product: Card Lab → Fight Lab → Market Lab → Factor Lab, plus the fighter database, event pages, cardio and the Proof Center. Every price carries its book count and age, refusals are named, no opener is claimed, and the odds capture feeding it is running on the current card. That journey is shippable today.

**Traffic does not use it that way.** In the last 14 days visitors landed overwhelmingly on fighter, head-to-head and event pages from search (3,000+ sessions) and the four product surfaces drew under 150 sessions combined. The product that was built is not the product that is being found.

**It is not an MVP for a paying member.** Nothing can be bought, nothing is gated, and the two member features beyond a free account (watchlist, alerts) stop at the database. The eight accounts that exist have not signed in for a month.

**It contradicts itself in one channel.** Every HTML surface was scrubbed of the forecast on 2026-09-21; the Monday/Wednesday/Friday social job still tweets model percentages, verified on 2026-10-09.
