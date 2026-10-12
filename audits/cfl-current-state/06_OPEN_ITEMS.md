# 06 — Open items, defects and technical debt

Audit date: 2026-10-12. Consolidated from `coordination/TASK_QUEUE.md` (34 open rows, ids kept as `T-nnn`), the 2026-09-18 audit's unresolved rows, the live-system checks in this audit, and the code review. New items are `A-nnn`. Priority: P0 = contradicts the product's stated rules or is losing data now; P1 = blocks revenue or integrity; P2 = quality; P3 = hygiene. Effort is rough: S under half a day, M one to two days, L about a week, XL more. Tags: **VERIFIED** / **INFERRED** / **UNKNOWN**. Nothing is marked complete without evidence.

## A. Live defects (acting now, found by this audit)

| id | description | component | pri | effort | blocker | business impact | evidence | disposition |
|---|---|---|---|---|---|---|---|---|
| **A-001** | **Social poster publishes model percentages to X three times a week.** `social-engine.js` regenerates pieces from `model_picks.p_cal` and stamps them `positioning:'research'`; `social-post.js` posts the next stamped piece. Tweet id 2108670936010387493 on 2026-10-09: "BONFIM 50% over PRADO…". Reddit title hard-coded "our model's read". | `.github/workflows/social-post.yml`, `build/social-engine.js:127,204,373,473,513-523,551`, `build/social-post.js:339-371` | **P0** | S (disable cron) / M (rewrite templates) | none | Public contradiction of D-011 in CFL's own name; reputational | run 37993596942 job log; `.funnel-state/posted-pieces.json` | fix now: disable the schedule, then rewrite or retire the generator; review the X timeline for posts since 2026-09-21 |
| **A-002** | Fighter scraper on Railway has been dead since May: last successful deploy 2026-05-22, the 2026-07-01 deploy with the UFCStats proof-of-work fix FAILED. 4,495 of 4,554 fighters last updated May 2026; 2,222 have NULL division. | `cage-metrics-scrapper` (other repo), Railway project `radiant-caring` | P1 | S–M (fix the build) | UFCStats blocking; other repo | The most visited page serves five-month-old fighter profiles | Railway deployments; live `fighters.updated_at` histogram | fix |
| **A-003** | Odds scraper on Railway: every deploy since 2026-07-01 FAILED on both of its two services (last success 2026-05-26). A second service's start command was overridden to the retired `backfill_odds.py` (D-004: "should be removed"). Polymarket rows still arrive, so the May build runs. | `cage-metrics-odds-scrapper`, Railway projects `model` and `skillful-transformation` | P1 | S | other repo | Unknown code running against an append-only table; duplicate service | Railway deployments | investigate; remove the duplicate service; fix or retire |
| **A-004** | `export.yml` fails every day: `SUPABASE_URL is not set`; `data/exports/` has never been committed. Also, if fixed as written it would commit the full raw `fight_odds` and `prop_odds` tables to a public repository daily. | `.github/workflows/export.yml`, `build/export_tables.py` | P2 | S | decide intent | Red cron nobody reads; licensing exposure if it ever succeeds | job log run 38251503583 | decide: disable, or fix with a private destination |
| **A-005** | `build/send-digest.js:100,113` and `build/social-post.js:72-73` read `open_p_a` / `books_at_open`, removed from `v_fight_market_movement` on 2026-09-21. The Brief loses its movement line; the legacy social path builds empty posts. No test pins it. | `build/` | P2 | S | none | Email would ship wrong once a key is set | live view columns; file lines | fix; add to `card-brief.test.js` |
| **A-006** | 14 of 75 `preview/*.html` ship FAQ JSON-LD "Cannon Fight Lab's models pick X … beat the opening price"; all in the sitemap; regenerated every 6 h. | `build/preview-templates.js:162-172,202`, `build/prerender.js:213` | P1 | S | none | Structured data contradicts D-011 and uses a banned phrase | grep | fix; extend the no-model test to generated output |
| **A-007** | `fighter.html:906-928` renders "Model called X of N", "Beats/Trails expectations", "a fade candidate at a short price" from `v_fighter_model_record`; `:993-1004` shows prop projections without the archive banner. The most visited page. | `fighter.html` | P1 | S | none | D-011 breach on the main landing page | code | fix: remove or banner; add the view to `BANNED_READS` |
| **A-008** | `event.html:695-698` runtime `<title>` "… UFC Predictions" and description "model odds" for upcoming events (indexed). | `event.html` | P2 | S | none | SERP snippet says "Predictions" | code | fix |
| **A-009** | Supabase: RLS disabled on `odds_aliases` and `unmatched_odds` (anon can read and write); 8 security-definer functions executable by `anon`; leaked-password protection off; 7 functions with mutable `search_path`. | Supabase | P2 | S | none | small exposure; linter ERRORs | advisor output 2026-10-12 | fix |
| **A-010** | `public_read_odds.sql` at the repo root grants anon `SELECT` on `fight_odds` and `odds_books`; no "superseded" header. Live policy is admin-only (VERIFIED), so one accidental `psql -f` exposes every raw quote. | `public_read_odds.sql:18-25` | P1 | S | none | data exposure hazard | file; live `pg_policies` | remove or convert to a pointer file |
| **A-011** | 16 Supabase edge functions (`prop0002-*`, `prop0003-*`, `cfl-*-test`, `cfl-prop0001-*`, `cfl-cardio-fold-fit`, `cfl-exp-export-temp`) are deployed and ACTIVE with no source in any repo. | Supabase | P2 | S | none | untracked code with database access | `list_edge_functions` | inventory, export source, delete scratch |
| **A-012** | 10 live tables have no definition in any repo (`streak_effect_cache`, `cardio_style_snapshots`, `master_dataset`, `master_dataset_v2`, `fighter_snapshot_2025`, `prediction_indicators`, `fight_odds_consensus_snapshot`, `hub_visits`, `odds_aliases`, `unmatched_odds`); 7 of them are readable by anon. | Supabase | P3 | S | none | reproducibility; unknown contents exposed | `list_tables`, grants query | inventory; drop or document |
| **A-013** | Webhook `verify_jwt=false` is set live but recorded nowhere in the repo (no `supabase/config.toml`). | `supabase/functions/stripe-webhook` | P2 | S | none | a default redeploy silently drops Stripe events | management API | commit function config |

## B. Monetization blockers (all owner- or lawyer-gated except T-069)

| id | description | pri | effort | blocker | disposition |
|---|---|---|---|---|---|
| T-054 | `privacy.html` must name Plausible (and `funnel_events`). Draft in `legal-review/PROPOSED_WORDING.md`. | P0 for revenue | S + lawyer | owner, L3 #9 | complete (owner) |
| T-048 | No Terms of Service page. | P0 for revenue | M + lawyer | owner, L3 #9 | complete (owner) |
| T-067 | Set the price and periods. | P0 for revenue | S | owner, L3 #7 | decide |
| T-068 | Stripe account, product, three function secrets. | P0 for revenue | S | owner | complete |
| T-069 | Exercise checkout end to end in Stripe test mode. | P1 | M | T-068 | complete (Claude) |
| T-066 | Turn checkout live in one PR (blockers removed, button enabled, `verify-billing-refusal.yml` assertions updated). | P0 for revenue | S | all above, L3 | complete (owner) |
| T-061 | Apply the Free/Pro boundary (`enforced:true`, `current_user_is_pro()` in views/policies, `alert_quota()`). Deliberately behind payment (D-019). | P1 | M | T-066 chain | defer until T-069 |
| T-074 | Set `RESEND_API_KEY` / `RESEND_FROM`. Unblocks digest, alerts, dead-man email. | P1 | S | owner | complete |
| T-073 | Re-enable the alerts cron after a controlled delivery test (dry run, one real email, duplicate re-run, cleanup). | P1 | S | T-074 | complete after T-074 |
| T-049 | Sportsbook jurisdiction labelling; standing gate before any affiliate link. | P2 | M | owner | defer |
| T-050 | Decide whether `parlay.html` and `mybook.html` stay reachable ("retire My Book" decided 2026-08-19, not done). | P3 | S | owner | decide |
| T-041 | My Book "vs earliest price seen" column under Q-14. | P3 | S | owner | decide |
| T-035 | Email-capture modal branch, never approved. | P3 | S | owner | decide or delete |
| A-020 | Nothing Pro would sell is withheld: alerts, watchlists, charts and the book table are free; history, "since last visit" and advanced analytics are unbuilt. The boundary document is a proposal. | P1 (strategy) | L–XL to build Pro-only depth | owner | decide before building |

## C. Data pipeline and integrity

| id | description | pri | effort | blocker | evidence | disposition |
|---|---|---|---|---|---|---|
| A-030 | Three CLV-001 migrations plus the `fight_odds` immutability trigger (T-031) unapplied: `odds_api_usage`, `fight_bout_order`, `fight_bout_completions`, `v_clv_close_reference`, `model_edges.clv_*`, `pre_fight_snapshots.edge_model_edge_id`, `cfl_integrity_count` all absent live. Headers of the two applied files still say "NOT APPLIED"; `STATE.md` lines 304–335 contradict its own line 37. | P1 | S each, L3 for immutability | T-029 seed first; owner | live `list_tables`; `research/clv/*.sql` headers | fix headers now; apply in order |
| T-029 | Seed `odds_api_usage` from the provider's `x-requests-remaining` before applying event-flow; until then the governor runs at the coarsest 30-minute rung. | P1 | S | needs a capture run | `build/fetch-odds.js:537-593` | fix |
| T-030 | Event Flow activation needs a real UFCStats fetch from a non-datacenter IP; cron commented out; 0 runs ever. | P1 | S (owner machine) | UFCStats 403 | `event-flow.yml` | complete (owner-side) |
| T-031 | Apply `fight_odds` immutability between cards; today the table has no triggers and `is_closer` is UPDATEd in production. | P1 | S | owner L3 | live trigger query | complete (owner) |
| A-031 | Eight data-integrity findings from 2026-09-16 unresolved: 104 odds rows + 8 predictions on non-participants (L3), 1,578 corner-swapped odds rows misread by four views, 30,724 epoch-stamped rows (24% of `fight_odds`), 4 duplicate bouts, 36 settled fights with no result, 2 prediction-market closers (L3), 61 prices ≥100-to-1, `bell_at` on 0 fights. The integrity runner cannot run (needs the unapplied RPC). | P1 | L | two owner decisions | `research/integrity/DATA_INTEGRITY_AUDIT_2026-09-16.md` | decide + fix |
| A-032 | Odds-to-fight matching is by fighter-name pair despite 8 namesake fighters; an ambiguous match is dropped, a wrong one writes a permanent row. | P2 | M | none | `build/fetch-odds.js:946-998`; `checks.py:313` | investigate: add provider id mapping |
| T-077 | `cfl-snapshotter` cron is Friday-only, so non-Saturday cards never get `predictions`; `closing_odds_american` NULL in every row ever. PR #52 scopes the watchdog accordingly. | P1 | S/M | Railway config (owner) | PR #52; live `predictions` | merge #52; fix cron |
| T-076 | Dead man's handle cannot see its own silence; needs an observer outside GitHub. | P2 | M | external service (L3 if paid) | CLAUDE.md | fix |
| T-006 | Two-sided quote capture at the publish instant (cannot be backfilled). | P1 | M | none | TASK_QUEUE | fix |
| T-032 | Retire stale bookings from Event Flow observation rather than by hand. | P2 | M | T-030 | | fix after T-030 |
| T-011 / A-033 | `cfl_engine/requirements.txt` all `>=`; `build/package.json` supabase-js `^2.45.0` (the pattern that broke the snapshotter); `tests.yml` on Node 20 while the snapshotter needs 22. | P2 | S | none | files | pin |
| A-034 | `build/test-fetch-odds.js` (945 lines of capture tests) is not run by CI. | P2 | S | none | `tests.yml:146-160` | add |
| A-035 | ~15 env-var names read in code are absent from the documented secrets table; three names for one service key. | P3 | S | none | grep | document |
| T-058 | Card-wide movement charts need a materialised series (`v_fight_chart_series` 4.6 s for 12 fights). | P3 | M | demand | STATE.md | defer |
| T-055 | Read `v_funnel_daily` after a week of traffic — now overdue; this audit did it (see `05_`). | P3 | S | — | | complete (superseded by this audit) |

## D. Security

| id | description | pri | effort | evidence | disposition |
|---|---|---|---|---|---|
| T-059 | P0 `profiles` self-promotion — **fixed** in SQL and live (policy pins eight columns). | — | — | `billing_migration.sql:107-123`; live `pg_policies` | complete |
| T-072 | TRUNCATE inherited by `authenticated` — **fixed** (REVOKE ALL then GRANT). | — | — | `alerts_migration.sql` | complete |
| A-010 | `public_read_odds.sql` hazard (above). | P1 | S | | remove |
| A-009 | RLS off on two tables; anon-executable definer functions; password protection (above). | P2 | S | | fix |
| A-040 | Two unmarked destructive one-off scripts at root (`dead_booking_cleanup.sql` 8 DELETE/UPDATE/DROP; `cleanup_stale_live_picks.sql`). | P2 | S | | move to `migrations/` with an applied-date header or delete |
| A-041 | 211 `innerHTML` uses with manual escaping; sample of unescaped interpolations all go to safe sinks; no automated guard. | P3 | M | | add a lint test |
| T-062 | `email_subscribers` anon INSERT `WITH CHECK (true)`, unthrottled. | P3 | M | | defer |
| A-042 | `cfl_engine/dur001/test_dur001.py:263` writes probe rows to production if `SUPABASE_ACCESS_TOKEN` is ever added to CI. Documented hazard. | P3 | S | | keep documented |
| A-043 | Publishable key hardcoded in 10 files (intentional; rotation needs 10 edits). | P3 | S | | centralise |

## E. Product debt and copy

| id | description | pri | effort | disposition |
|---|---|---|---|---|
| A-050 | Stale copy contradicting shipped features: `market.html:150-157` and `pricing.html:121-131,176` say charts/alerts/watchlists are not built; `mybook.html` says "consensus picks", "simulated value flags", "beat the opener", dead Kelly controls; `fight.html:506` promises an email; nav badge "MARKET · LIVE". | P2 | S | fix |
| A-051 | `COPY_STYLE.md` and `coordination/STATE.md` "Site" section still describe a picks product while CLAUDE.md says COPY_STYLE governs every string. | P2 | S | rewrite |
| A-052 | `coordination/HANDOFF.md:5-48` preamble corrupted since 2026-10-05 (a section spliced mid-sentence); structure test does not catch it. | P2 | S | fix |
| A-053 | `edges.html:444-450` Record "60–72% · Active" vs FE-001's 50.2%; `edges.js` record and td_def still shipped to the snapshotter. T-024 in progress, T-025 owner-gated. | P2 | M | decide (owner): correction note or retire |
| A-054 | Three CTAs link to the `card-lab.html` redirect stub (`track-record.html:389`, `predictor.html:614`, `_shared.js:484`). | P3 | S | fix |
| A-055 | `social/` (80 files, 11 MB) with "our model 69%" batches and an un-noindexed dashboard served by Pages; `build/draft-post.js` still renders a pick table (T-039); `social/queue.json` stale (T-038). | P2 | S | remove from Pages; retire or rewrite |
| A-056 | `h2h.html` duplicates Fight Lab's stat block and receives ~39% of sessions with no market data on it. | P2 (product) | M | decide: make it the funnel into Fight Lab, or fold |
| A-057 | Orphan pages `props.html`, `predictor.html`; internal `lab.html` reads admin-only tables with the anon key. | P3 | S | decide |
| A-058 | Three URLs per event, two per fight, with conflicting canonicals. | P3 | M | pick one canonical |
| A-059 | `fighter_cardio` (2,681 rows, mixed-effects fade slope) is published and rendered nowhere. | P3 | M | decide |
| A-060 | CLAUDE.md stale in at least six places (picks.html two-hop; "no test suite"; 19 funnel events vs 24; `edges.js` "used by index.html"; stubs "120 ms JS redirect"; alerts cadence); `PROOF_CENTER.md`, `SEO_PER_PAGE.md`, `SOCIAL_SETUP.md` stale. | P3 | S | fix |
| A-061 | Test coverage gaps: no-model test scans only root pages and omits `v_fighter_model_record`; nothing tests stub/preview output, `social-engine.js`, or runtime meta strings. | P2 | S | extend |

## F. Research

| id | description | pri | disposition |
|---|---|---|---|
| T-002 | Nine DUR-001 amendment clauses need individual owner votes; backfill gate refuses everything meanwhile. | P2 | decide (owner) |
| T-003 / T-007 | Stale queue rows: the CLV protocol is frozen v1.0.10, yet these say "review before freeze" / "resolve then freeze"; no decision entry closes T-007. | P3 | record decision, close |
| A-070 | CLV-001 computes nothing (0 of 100 observations, 0 of 20 events) until A-030 lands and until cards pass with capture inside the 45-minute limit. | P1 | blocked on A-030 |
| A-071 | PR #53 SYM-002/SYM-003 (+2,460 lines) is outside the research register and unreviewed; results are git-ignored. | P2 | review, register or close |
| A-072 | PROP-0001's live isotonic step worsens out-of-sample log loss by 0.0148; the gate report's generator is not in the repo; `prop_odds` covers 24 fights. DUR-001/002 have no kill rule. | P2 | decide (owner) |
| A-073 | Cardio mixed-model validation numbers never committed; R-8/R-11 public claims unpreregistered. | P3 | preregister or drop |
| T-009 / A-074 | Owner naming resolved as D-021 on an unmerged branch (`claude/trusting-cori-sfllu9`). | P2 | merge or drop |

## G. Repository hygiene

| id | description | pri | disposition |
|---|---|---|---|
| A-080 | 38 fully merged remote branches; 13 unmerged, 5 of them pre-September and abandoned (`macau-event-v5-accuracy` 21 ahead, `automated-traffic-funnel` 8, `council/stats-accuracy-and-ui-fixes` 4, `council/props-output-layer` 13, `fight-week-v2` 7). | P3 | delete merged; triage the rest per their ids |
| A-081 | 34 root SQL files, 7 with an applied header; `migrations/` has one file; `research/clv/` five; applied state of ~26 root files knowable only from the live DB. | P3 | one directory, dated names, applied header; reconcile with `list_migrations` |
| A-082 | `out_real/` git-ignored yet two files tracked; `social/` images 11 MB and `docs/screenshots` 3.9 MB tracked; ~5,400 stubs make 61% of history bot commits. | P3 | clean |
| A-083 | Dead code: `distanceEdges.js`, `research/validate.js|subset-test.js|event-drill.js` (hindsight-biased, 2026-05-17), `cfl_engine/make_synthetic.py`, `build/make-posting-app.js`, `cflAuth.joinWaitlist`, `model-weights.json`. | P3 | remove or move to research/ |
| A-084 | Cache-bust tags inconsistent (`?v=rl3` vs `rl4`; `_auth.js` unversioned/`rl2`/`mybook1`). | P3 | normalise |
| A-085 | No single document lists the 19 workflows, their crons and which are switched off. | P3 | add a table to CLAUDE.md |

## H. Suggested order (if work continues at all — see `08_`)

1. **A-001** stop the social poster today; **A-006**, **A-007**, **A-008** scrub the remaining model leaks and extend the test. Half a day total.
2. **A-002**, **A-003** fix the two dead Railway services or retire them; **A-004** decide the export cron. One day.
3. **A-010**, **A-009**, **A-013** close the security hazards. Half a day.
4. **A-030 / T-029 / T-030 / T-031** apply the CLV and event-flow migrations in order — only if the CLV line is to continue.
5. **T-074 + T-073** make alerts and the Brief deliver — only if members are to be acquired.
6. **T-054 → T-048 → T-067 → T-068 → T-069 → T-066** the revenue chain — only after a Pro offer exists that withholds something (A-020).
7. Copy and documentation (A-050–A-061), hygiene (A-080–A-085) as time allows.

Counts: 34 open TASK_QUEUE rows carried; 2 of the prior audit's items confirmed fixed (T-059, T-072 plus the earlier `lab.html` noindex, single-hop `picks.html`, CI); 55 new `A-` items of which 13 are live defects found by this audit.
