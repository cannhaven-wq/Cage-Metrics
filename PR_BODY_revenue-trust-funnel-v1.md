Revenue track, PR 1. No model, threshold or prediction changed. Nothing under `cfl_engine/` or `research/` touched (tripwire hash identical before and after). No paywall, checkout or premium tier built. The peer session's PR 2 (fight-week-v2) will rebase on this.

## What changed, per task

**1. Public claim manifest.** `build/claims-manifest.js` (`npm run claims`, now in `prerender.yml`) queries the graded views and writes `data/claims.json`. Every headline number on the homepage, Proof Center, About, Methodology and edges.html is now a `data-claim` placeholder filled by `cfl.renderClaims()`, with "Last updated: <date>" beside it. Historical replay and live results are separate claims and separate blocks — nothing adds them. The Proof Center's engine KPI strip used to combine backtest + live rows into one number (the "3,288" was 3,235 replay + 53 live); it now has a replay / live toggle.

**2. Factor Lab contradiction.** The one recorded result is `factor-rates.json` (built by `build/factor-rates.js`, regenerated 2026-09-15). It says age = `real` (survives), UFC record = `lean` ("Maybe — close, but not enough fights yet to be sure"). About and Methodology now read the survivor list and the record verdict from that file via `cfl.renderFactorVerdicts()`; the verdict words (`cfl.FACTOR_ANSWER` / `cfl.FACTOR_BECAUSE`) moved to `_shared.js` so stats.html and the prose pages can't drift. Methodology's hardcoded age sample sizes (3,831 / 1,642 / 1,423 / 766) were stale and now come from the file too.

**3. Messaging.** Visible "pick" labels are "forecast" (Model forecast, Why this forecast?, Our forecast, every forecast graded…); "tape-only" → "odds-blind"; the line **"CFL publishes model forecasts and market analysis. It does not sell handicapper picks."** is on the homepage hero, About (twice, replacing "doesn't sell picks" / "We don't issue picks"), Proof Center lede (h1 now "Every forecast we've published. Wins and losses."), Methodology, preview/card footers and the email footer. "Pick" survives only as a technical name: `model_picks`, graded-row columns, the `Pick` confidence tier (Lock/Pick/Lean), and users' own parlay/My Book picks. Social post copy: "model picks, locked in" → "model forecasts, locked in". `COPY_STYLE.md` and `CLAUDE.md` updated.

**4. One email signup.** `cfl.renderEmailCaptures` in `_shared.js` is the single component ("Get the Fight Week Market Brief", one field, one button), placed on the homepage, Proof Center, `fighter.html`, `event.html`, every `/preview/` page and every `/card/` page. **Why the table had 0 rows:** `cflAuth.subscribeEmail` used `upsert(..., {ignoreDuplicates:true})`; that `ON CONFLICT DO NOTHING` path is rejected by RLS with 42501 even for a brand-new address, while a plain `INSERT` passes the existing anon policy (verified with curl: upsert → 401, insert → 201, duplicate → 409/23505). Fixed client-side: plain insert, 23505 reported as "already on the list". Tested end to end in the local build: invalid email → error, new email → row written (then deleted), same email in different case → duplicate message. No DB change needed. Digest subject is now "Fight Week Market Brief: <event>".

The `/f/` and `/e/` stubs redirect to `fighter.html` / `event.html` in 0 s and load no JS, so the signup went on the pages humans actually see rather than the stubs.

**5. Funnel tracking.** `cfl.track(name, props)` → `plausible(name, {props})`, queued if Plausible hasn't loaded, silent if blocked. Wired: `preview_view` (preview + card pages), `fight_expand` (opening "Why this forecast?" on event.html), `proof_center_view`, `methodology_view`, `email_form_view` (when the form scrolls into view), `email_submit` / `email_submit_success` / `email_submit_error`, `signup_start` (first focus on the signup form), `signup_complete`, `premium_interest` (either pricing CTA), `odds_book_click` (delegated on any `<a data-track="odds_book_click">` — there are no sportsbook links yet, so nothing fires today).

**6. SEO templates.** Titles are `<A> vs <B> Prediction & Odds | Cannon Fight Lab` and `<Event> Predictions & Odds | Cannon Fight Lab`; descriptions are unique per page (event, date, locked forecast, records). Preview pages gained a tale-of-the-tape table and the signup. Forecasts come from `pre_fight_snapshots` first, then the insert-only `model_picks` **live** row; backtest rows are no longer used and nothing is recomputed at render. Each page says when the forecast was locked. Sitemap static list: dropped the `card-lab.html` redirect stub, added methodology + props. `sitemap.xml` itself is left for the prerender Action to regenerate on merge (5,434 URLs / ~1 MB — well under the 50k / 50 MB limits); its 5.5k-line lastmod churn was excluded from this PR on purpose.

**7. RLS review.** `migrations/2026-09-15_odds_aliases_unmatched_odds_rls.sql` — **not applied**. Audit: both tables are touched only by the retired BFO scraper scripts (`cage-metrics-odds-scrapper/odds_scraper.py`, `backfill_odds.py`, `diagnose_unmatched.py`), all authenticating with `SUPABASE_SECRET_KEY` = service_role. Nothing in this repo, `build/fetch-odds.js`, `cfl_engine/`, the snapshotter or any GitHub Action reads them. Today anon holds SELECT/INSERT/UPDATE/DELETE/TRUNCATE on both. The migration enables RLS with no anon/authenticated policies and revokes those grants; service_role keeps working unchanged.

## Every number removed or relabeled

| Was on the page | Now | Source |
|---|---|---|
| "3,288 never-seen fights / 61.6%" (homepage hero, track note, tile, About, edges.html) — backtest + live summed | **3,235 / 61.5%**, labeled *Engine v2 historical replay* | `v_model_picks_graded WHERE source='backtest' AND hit IS NOT NULL` |
| "722 Locks / 74.7%" — summed | **707 / 74.5%**, historical replay | same view, `tier='Lock'` |
| "658 simulated bets 519-139" | **519-139 on 658**, historical replay, +$226 flat $100 at close, +10.0% edge-sized | `v_model_edges_graded WHERE source='backtest'` |
| "12-5 live Value, down $61" (stale) | **28-13** (20 pending), −$120 flat $100 at the price posted, *Live record* | `v_model_edges_graded WHERE source='live'` |
| live Fight IQ (not shown before) | **56.6% on 106** settled (45 pending); Locks 71.4% on 35 | `v_model_picks_graded WHERE source='live'` |
| "about 68%" closing favorite (untraceable prose) | **68.0% on 3,064** replay fights with a closing line | `fight_odds WHERE is_closer` joined to the replay rows, pick-em lines excluded |
| "8,937 fights in the database" (hardcoded) | **8,992** | `COUNT(*) FROM fights` |
| "live record since July 2026" (hardcoded) | July 2026 | `MIN(event_date)` of live rows |
| Methodology age sample "3,831 fights (5–6 yr: 56.2% of 1,642 · 7–9: 61.6% of 1,423 · 10+: 67.9% of 766)" | 8,612 / 56.2% of 1,649 / 61.7% of 1,432 / 67.8% of 773 | `factor-rates.json` |
| "Value numbers are a snapshot as of Aug 18, 2026" | removed; every block shows "Last updated" from the manifest | — |
| meta descriptions "61% on 3,200+ fights, Locks at 75%" (index.html) | numbers removed (meta can't be JS-filled) | — |

Nothing else was removed for being untraceable. "roughly 8,700 historical fights" on edges.html and "8,000+" in a few meta tags are approximate, dated narrative and were left.

## Stopped on / left out

- Nothing blocked. Task 2 did not need a new data file — `factor-rates.json` already was the single source and the copy already agreed with it; the change is structural (all three pages now read the file instead of restating it).
- The `/f/` and `/e/` redirect stubs did not get a form (see task 4).
- `build/social-engine.js` still renders an "N of M models agree" line; `consensusPick` keeps `agree: 1, total: 1` so it doesn't break. Its copy wasn't otherwise touched.

## Manual steps for Reed

1. **Plausible → Goals → add a custom-event goal for each:** `preview_view`, `fight_expand`, `proof_center_view`, `methodology_view`, `email_form_view`, `email_submit`, `email_submit_success`, `email_submit_error`, `signup_start`, `signup_complete`, `odds_book_click`, `premium_interest`. (Prop keys in use: `source`, `page`, `fight`, `card`, `event`, `cta`, `src`, `reason`, `duplicate`, `confirmed`.)
2. **Apply the RLS migration** after reading it: `python cfl_engine/run_sql_mgmt.py migrations/2026-09-15_odds_aliases_unmatched_odds_rls.sql`, then the verify queries at the bottom of the file.
3. **Search Console:** resubmit `https://cannonfightlab.com/sitemap.xml` after the first post-merge prerender run (it fires on push because `build/**` changed).
4. The prerender Action needs `SUPABASE_SERVICE_ROLE_KEY` (it already has it for factor-rates); without it the closing-favorite claim is carried forward as `STALE`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
