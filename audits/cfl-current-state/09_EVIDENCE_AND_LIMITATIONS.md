# 09 — Evidence and limitations

Audit date: 2026-10-12. Conducted read-only from a cloud container with the repository checked out at `origin/main` `5aed9e42` (branch `claude/nice-bell-ussmhp`), plus read-only API access to the Supabase project, the Railway workspace and the GitHub repository. The only repository writes are the nine files in `audits/cfl-current-state/`.

## 1. Systems inspected

| system | access used | what was read |
|---|---|---|
| Git repository | local clone, unshallowed to the full 1,063 commits; `origin/*` branches fetched | all tracked files; `git log`, `shortlog`, `diff-filter=A`, `rev-list` per branch; read-only `git show` on the two open PR branches |
| GitHub (API) | `list_issues`, `list_pull_requests`, `list_branches`, `actions_list` (workflows, runs, jobs), `get_job_logs` | 0 open and 0 closed issues; 51 PRs; 52 branches; 22 workflows and their latest runs; job logs for the failing export run 38251503583 and the social-post run 37993596942 |
| Supabase project `uftancejftcryfvbggll` | `list_tables`, `list_migrations`, `list_edge_functions`, `get_advisors`, `get_project`, and read-only `SELECT`/`information_schema`/`pg_policies`/`pg_trigger`/`pg_indexes` queries | row counts, date ranges and freshness for every table named in `04_`; per-event snapshot/odds coverage; book-level odds breakdown; funnel events by day, name and path; `auth.users` counts and last sign-in; `profiles` tiers; view column lists; live policies and anon grants; triggers and indexes on `fight_odds`; security advisor output; edge function list with `verify_jwt` |
| Railway workspace | `list-projects`, `list-services`, `list-deployments`, `get-logs` | 6 projects, 7 services, last deployments and statuses, deploy logs for the event scraper (2026-10-12) and the snapshotter (2026-10-09) |
| Tests | run locally | `node tests/*.test.js` (17 files, all pass); `pytest -q -rs` from the repo root (629 passed, 4 skipped, 4,755 subtests) |

## 2. Repository files read (principal)

`CLAUDE.md`, `COPY_STYLE.md`, `PRODUCT_BOUNDARY.md`, `CFL_RESEARCH_STATE.md`, `PROOF_CENTER.md`, `BRANCH_NOTES.md`, `TRAFFIC_FUNNEL.md`, `ANALYTICS_SCHEMA.md`, `SEO_PER_PAGE.md`, `SOCIAL_SETUP.md`; `coordination/` (STATE, HANDOFF, TASK_QUEUE, DECISIONS, CRITICAL_GATES, AUDIT_2026-09-18); `legal-review/PROPOSED_WORDING.md`; all 31 root HTML pages; all 13 root JS modules; all 34 root SQL files, `migrations/`, `research/clv/*.sql`; `supabase/functions/*`; all 19 workflow files and `.github/scripts/`; every `build/*.js` and `build/export_tables.py`; `cfl_engine/` (engine, serving, snapshot, settle, clv, dur001, dur002, event_flow, features, models, cardio, integrity, harness reports, `benchmark_report.md`, `INTEGRATION_STATUS.md`); `research/` (protocol, dry run, writer inventory, FE-001, integrity audit, provenance, registry, 2026-05 validator results); `factor-rates.json`, `model-weights.json`, `out_real/*.csv`, `.funnel-state/*`, `social/queue.json`, samples of `preview/`, `card/`, `f/`, `e/`; `tests/*`. The PR #53 branch `claude/cool-sagan-osv7iq` was read via `git show` for `research/symbolic/*`.

## 3. Key live queries (reproducible)

- Table counts and freshness: `select count(*), min(..), max(..) from <table>` for every table in `04_` §A1.
- Odds by month and provenance: `group by date_trunc('month', captured_at)` with `source_event_id is not null`.
- Odds by book: `odds_books` left join `fight_odds` grouped by book with epoch-row count.
- Per-event coverage: events since 2026-08-01 joined to fight counts, `pre_fight_snapshots`, distinct priced fights, `predictions`, `model_picks`.
- Policies and grants: `pg_policies` and `information_schema.table_privileges` for `anon`.
- Fighters freshness: `date_trunc('month', updated_at)` histogram; `division is null` count.
- Funnel: `funnel_events` grouped by day, by `event`, by `path` (last 14 days).
- Users: `auth.users` count, `last_sign_in_at > now() - 30 days`.
- Model records: `v_pre_fight_graded` by `engine_model_version`; `model_edges` by source/version with `clv_beat`; `model_predictions` by `model_version`.
- Schema checks: columns of `v_fight_market_movement` (no `open_p_a`); `pg_get_viewdef('v_fight_odds_latest_by_book')` has no 14-day window; `pg_trigger` on `fight_odds` is empty; `pg_indexes` on `fight_odds`.

## 4. Systems that could not be accessed

| system | consequence |
|---|---|
| The live site `cannonfightlab.com` | Blocked by the container's egress policy (CONNECT 403). Rendered behaviour judged from code; the repo's own `verify-live.yml` last passed 2026-09-21. |
| Plausible | True pageviews, referrers and bounce unknown; only the in-house `funnel_events` table was used. |
| The four related repositories (`cage-metrics-scrapper`, `cage-metrics-odds-scrapper`, `cage-metrics-event-scrapper`, `cfl-snapshotter`) | Schemas, crons and code not inspected; only Railway deployment metadata and logs, plus `research/clv/FIGHT_ODDS_WRITER_INVENTORY.md`. |
| Supabase and Railway billing, The Odds API account, X analytics, Resend, Formspree, Stripe | Costs, API tier and credits, tweet engagement, contact-form submissions unknown. |
| Supabase Auth settings (email confirmation), function secrets | Not read; `verify_jwt` was read, secret presence inferred from workflow logs (`RESEND_*` absent per `TASK_QUEUE.md` and dry-run behaviour; `X_*` present per the 2026-10-09 job log). |
| The owner | No interview; intent, hours and spend are not on record. |

## 5. Important unverified or inferred claims

| claim | status |
|---|---|
| The May 2026 build of the odds scraper is still running on Railway | INFERRED from Polymarket rows arriving through 2026-10-12 while every deploy since July failed |
| Where v1–v4 are retrained nightly (their `last_trained_at` is 2026-10-12) | UNKNOWN; not in this repo, Railway deploys of the odds repo fail |
| The traffic growth is human and where it comes from | UNKNOWN; no referrer stored |
| Some of the 8 accounts are the owner's test accounts | INFERRED, not verified |
| The 14 "models pick" preview pages are being indexed | UNKNOWN; they are in the sitemap |
| The Odds API free tier permits redistribution; UFCStats scraping is tolerated | UNKNOWN; no terms on file |
| Cost figures of any kind | not available |
| PROP-0001 gate report, SYM-002/003 results, cardio validation numbers, `edges.js` tier percentages, v6 ROI descriptions | narrative only, no reproducible artifact in the repo (see `04_` §B5) |
| The dead man's handle, snapshot and odds crons will keep firing | GitHub throttles schedules and can disable them after inactivity; no external observer exists (T-076) |

## 6. Known gaps in this audit

- Row-level inspection of the 10 orphan tables was not done beyond counts and grants.
- `innerHTML` XSS review was sampled, not exhaustive.
- The X timeline was not reviewed for the full set of posts since 2026-09-21; one post was verified from a job log.
- Supabase performance advisors were not pulled (security advisors were).
- Commit-theme shares in `07_` are keyword counts, ±5 points.
- Effort estimates in `06_` and `08_` are rough sizes, not plans.

## 7. Information required to complete the picture

1. Plausible export for September–October (referrers, pages, bounce).
2. Access to the four external repositories and their Railway variables.
3. Supabase, Railway, Odds API, Plausible and domain invoices.
4. The Odds API terms for the free tier; any correspondence with UFCStats.
5. The X account's post history since 2026-09-21.
6. The owner's statement of which of the eight accounts are real.
7. A decision on which of the options in `08_` §2 is being pursued, because the open-items order in `06_` §H depends on it.
