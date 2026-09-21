# CLAUDE.md

> Every feature, every explanation, and every task must be understandable by a UFC bettor with no stats background. Plain verdict first, plain reason second, math only in a collapsed block if at all. No edge percentages and no unsupported market claims anywhere in the user interface. If Reed can't explain it to a friend in one sentence, it does not ship.

> **CLV, amended 2026-09-16 (Q-14).** This line used to read "no closing line value ... anywhere in the user interface". That absolute prohibition is lifted, and replaced by a narrower rule that is harder to misuse:
>
> **No CLV figure may appear on a user-facing surface unless it was produced under the currently frozen CLV measurement protocol and every publication threshold in that protocol is satisfied.**
>
> The protocol is [`research/clv/CLV_MEASUREMENT_PROTOCOL.md`](research/clv/CLV_MEASUREMENT_PROTOCOL.md), frozen 2026-09-16, and `tests/test_clv_protocol.py` enforces the gate. The prohibition on vague **edge percentages** and unsupported market claims above is untouched — this authorises **one** narrowly defined, auditable metric, not sportsbook-style marketing.
>
> **Frozen is not publishable.** As of the freeze the gate is still shut: the sample floor is 100 scored observations across 20 distinct events, and it stands at 0. Freezing settled *how* the number is measured; it did not create a number worth showing.

> Before writing any code, state the task in plain English: what changes, why it matters, and what the user sees differently. Reed approves the plain version first. No task starts from jargon.

> **POSITIONING, amended 2026-09-21 ([D-011](coordination/DECISIONS.md)).**
> Cannon Fight Lab is a **UFC research and market-intelligence tool**, not a
> picks product. The forecasting engine was removed from every forward-facing
> surface after testing failed to show its disagreement with the market was
> worth acting on.
>
> **Nothing on a public page may show a CFL win probability, a pick, a
> confidence tier, a predicted winner, or a difference between CFL's number and
> the market's.** `tests/no-model-on-public-surfaces.test.js` enforces it and
> names the exempt archive pages. The prohibition on edge percentages and
> unsupported market claims in the first rule above is untouched and now
> stronger.
>
> **The engine is not retired.** It runs on the same schedule, writes the same
> immutable pre-fight record, and is graded in the open on the Proof Center. It
> returns to the product only on prospective evidence, and the evidence is
> published before the number is. Do not delete model infrastructure to "tidy
> up" — see D-011 for what is explicitly not decided.
>
> **Third-party data is an input, never the product.** UFCStats and The Odds API
> feed CFL's research; what CFL sells is the capture schedule, the provenance,
> the vig-free consensus, the movement history, the matchup comparisons and the
> factor testing. Architect so a raw source can be swapped.
>
> **Best price means the best price in the data.** `market.js` orders it by the
> American number and by nothing else. If affiliate money ever enters this
> product, it does not enter there.

Wording reference: [`COPY_STYLE.md`](COPY_STYLE.md) governs every user-facing string.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Start here: `coordination/`

**Read [`coordination/STATE.md`](coordination/STATE.md) at the start of every session.** It is one screen and it says where the project actually is.

The repo is the communication layer between Claude (build) and ChatGPT (spec and review). Claude ships work and writes a handoff; ChatGPT reviews it and writes the next specification; Reed is pulled in only at an L3 gate.

| file | read it when |
|---|---|
| [`coordination/STATE.md`](coordination/STATE.md) | always, first |
| [`coordination/HANDOFF.md`](coordination/HANDOFF.md) | picking up work — the top entry names the next action |
| [`coordination/TASK_QUEUE.md`](coordination/TASK_QUEUE.md) | choosing what to do next |
| [`coordination/CRITICAL_GATES.md`](coordination/CRITICAL_GATES.md) | before anything that might need Reed |
| [`coordination/DECISIONS.md`](coordination/DECISIONS.md) | when a decision feels already-settled — it probably is |

**Default: proceed.** If a change is revertible, testable and already inside a written specification, do not ask. `CRITICAL_GATES.md` defines the L0–L3 ladder and the closed list of things that stop and wait — and defines "reversible" precisely, because append-only tables and published claims are not undone by `git revert`.

Finishing a piece of work means updating `STATE.md` and `HANDOFF.md` in the same commit. `tests/test_coordination.py` checks the structure; an L3 task cannot reach `done` without a decision recorded against its id.

## Product / naming

- **Product name is Cannon Fight Lab (CFL).** Never refer to it as "Cage Metrics" in user-facing copy. The repo on GitHub is still named `Cage-Metrics` for historical reasons — **do not rename the repo**.
- Wordmark: "Cannon Fight Lab" full / "CFL" short. Domain: `cannonfightlab.com`.
- Owner: Reed Cannon. GitHub: `cannhaven-wq`. Remote: `https://github.com/cannhaven-wq/Cage-Metrics.git`.
- **Copy voice is governed by [`COPY_STYLE.md`](COPY_STYLE.md).** Every user-facing string — page copy, buttons, model explanations, red flags, generated text like `prop_cards.why_text` — follows it. Anti-tout, plain English (no stats jargon), losses at equal prominence to wins, CLV as the north star. Read it before writing UI copy; the shipped reference implementations are `track-record.html` and `fight-insights.js`.

## Related repos (live on GitHub under `cannhaven-wq`, not in this folder)

- **Cage-Metrics** — this repo. The website. Plain HTML/CSS/JS, hosted on GitHub Pages.
- **cage-metrics-scrapper** — Python fighter scraper, runs on Railway.
- **cage-metrics-odds-scrapper** — Python odds scraper, runs on Railway (`odds_scraper.py`). **The main writer to `fight_odds`**, plus the Polymarket capture under `polymarket/` and the v1–v6 model training that reads it. Added to this list 2026-09-16: it had been missing, and it is the repo that writes most to `fight_odds` — see [`research/clv/FIGHT_ODDS_WRITER_INVENTORY.md`](research/clv/FIGHT_ODDS_WRITER_INVENTORY.md). Its `backfill_odds.py` is **retired**; `fight_odds` is append-only and that script deleted rows.
- **cage-metrics-event-scrapper** — Python event scraper, in-progress on Railway.
- **cfl-snapshotter** — Node predictions snapshotter. Shares verdict logic with the frontend via `edges.js` (loaded with `<script>` in browser, `require('./edges')` in Node).

## Build / run / deploy

The site itself is plain static HTML/CSS/JS — no bundler, no test suite. There is one Node build step (prerender) that runs in CI on a schedule; you don't need it locally.

- **Local preview**: open `index.html` directly, or `python -m http.server` from the repo root.
- **Deploy**: pushing to `main` deploys to GitHub Pages automatically. `.nojekyll` is present so Pages serves files as-is. `CNAME` pins the custom domain.
- **Prerender**: `cd build && npm install && npm run prerender` regenerates the static stubs (see "Prerendered stubs" below). You almost never need to run this locally — the GitHub Action handles it on a 6-hour cron.
- No lint, no test suite. Don't add either without asking.

## The pre-fight record (hard rule)

**No fight goes off without our prediction already on record.** Before every card, every fight on it gets exactly one immutable row in `pre_fight_snapshots` freezing what CFL was publicly showing at that moment: the engine's pick and calibrated probability, which engine version produced it, the market price we could see, any flagged value edge, the Prop Board projections for both corners, and the legacy v1–v6 model cards.

- Owned by [`cfl_engine/snapshot_predictions.py`](cfl_engine/snapshot_predictions.py), scheduled by [`.github/workflows/snapshot.yml`](.github/workflows/snapshot.yml) (23:00 UTC the night before + 10:30 UTC day-of). Schema in [`pre_fight_snapshots_migration.sql`](pre_fight_snapshots_migration.sql).
- **Append-only, enforced by database triggers that reject UPDATE and DELETE for every role including `service_role`.** Do not add a "fix up the snapshot" path. A record that can be revised after the bell is not evidence, and that is the only thing this table is for.
- The script **collects, it never computes.** It reads what we already published. Re-running the model at snapshot time could disagree with what the site actually showed, which defeats the purpose.
- Re-runs are always safe: fights already on record are skipped, never overwritten. Earliest snapshot wins; the second daily pass only adds late-booked fights.
- It refuses to snapshot a settled card, so a snapshot can never be backfilled after a result is known.

Why it can't just be the tables we already have: `model_picks` is insert-only but carries no price and no props; `prop_projections` is **full-table replaced** on every refresh, so it holds only the next card; `v_fight_odds_consensus` is overwritten as the line moves. The snapshot is the only place all three are frozen together ahead of the bell.

Grade it through `v_pre_fight_graded`, which joins snapshots to results — it can only ever contain picks that were on record before the fight.

Not to be confused with the legacy `predictions` table (the retired rules-model snapshotter, `cfl-snapshotter` on Railway, cron dead since 2026-05-29).

## Architecture

### Page model

Every page is its own standalone HTML file at the repo root. Shared chrome (nav, footer) is rendered by JS into `<nav class="cfl-nav">` and `<footer class="cfl-footer">` placeholders.

**Product surfaces**: `index.html` (**Card Lab**), `market.html` (**Market Lab**), `fight.html` (**Fight Lab**), `stats.html` (**Factor Lab**), `props.html`, `parlay.html`, `cardio.html`, `event.html`, `fighter.html`, `fighters.html`, `h2h.html`, `mybook.html`.
**Archive** (documents the retired forecast; each carries `.cfl-archive-note`): `track-record.html`, `proof.html`, `predictor.html`, `edges.html`, `methodology.html`.
**Explainers**: `about.html`.
**Account / legal / misc**: `pricing.html`, `account.html`, `login.html`, `signup.html`, `reset.html`, `contact.html`, `disclaimer.html`, `privacy.html`, `unsubscribe.html`.
**Internal**: `lab.html` — an unlinked backtest sandbox that says so at the top; its numbers include training data by construction. Don't cite it anywhere user-facing.
**Redirect stubs** (kept so old links, shares and bookmarks don't 404; `noindex`, meta-refresh): `card-lab.html` → `/`, `picks.html` → `card-lab.html`. Both are ~23 lines and carry no nav. `picks.html` currently redirects through `card-lab.html` rather than straight to `/` — a two-hop chain worth collapsing.

- **`index.html` — Card Lab** is the primary product surface. The hero is the current card ("*[Event]* — the whole market, one screen", D-011). The full card lives in the `#next` section, which is what the nav's "Card Lab" pill points at (`index.html#next`). Each fight shows four market cells — **Consensus** (vig-free median, `v_fight_market_movement`), **Fair price** (that probability as an American number, labelled not-bettable), **Market move** (matched-cohort, D-012), **Best price** + the book posting it — then the neutral matchup notes from `fight-insights.js::buildMatchupNotes`. Sorts are card order / biggest move / books disagree. **There is no pick, no confidence tier and no CFL-vs-market difference on this page**, and `tests/no-model-on-public-surfaces.test.js` keeps it that way. Card Lab used to be its own page; it was merged into the homepage so there is one card page rather than two, and `card-lab.html` is now only a redirect stub. **If you are looking for the card rendering, it is in `index.html`.**
  - Nothing on the card is gated in the frontend. During beta every account holder gets premium (`profiles.beta_premium`) and logged-out visitors see a "Free during beta" banner instead.
- **`market.html` — Market Lab** is the whole card as a board: consensus, best price each side, movement since first capture and over 24 h, book spread, capture age, with a per-fight book breakdown that expands on demand and a "what changed in the last 24 hours" list. Takes `?event=<id>`; defaults to the live or next card.
- **`fight.html` — Fight Lab** is one matchup, `?id=<fight_id>`: both corners' consensus and best price, the two movement horizons, the book spread, the per-sportsbook table, then the measured matchup differences and a full career-stat comparison. It rewrites its own `<title>` and share description from the fighters' names, because it is entered from search far more often than from the site.
- **`props.html`** ("Prop Board") — projected significant strikes and takedowns per fighter for the next card, read from `v_prop_projections_current`. Note `prop_projections` is **full-table replaced** on every refresh, so it only ever holds the next card; nothing historical survives there (see the pre-fight record section — this is one of the reasons snapshots exist).
- **`mybook.html`** ("My Book") — the only genuinely account-gated page (`cflAuth.requireAuth`). Reads and writes `user_bets` / `user_bankrolls`; schema in `bet_tracking_migration.sql`.
- **`parlay.html`** (Parlay **Calculator**) and **`cardio.html`** (Cardio Scores) are both in the nav. Parlay pre-fills the best number from `v_fight_odds_latest_by_book` on each leg and shows the combined payout beside the combined chance; it shows no model number and sizes no stake. It used to query `fight_odds`/`odds_books` directly and returned zero rows for every visitor — **those two tables are `private_lockdown_admin_only` for `anon` AND `authenticated`, so the browser can only reach odds through a definer view.** Cardio reads `v_fighter_consistency` and `v_fighter_cardio_curve`.
- **`edges.html`**, **`methodology.html`**, **`predictor.html`** are the open-methodology pages and are now **archive**: they document the retired forecast and each carries the `.cfl-archive-note` banner. They keep their dated audit narratives — when a measurement changes, add a dated correction rather than silently rewriting the history (see `edges.html`'s "Updated August 2026" note). **Do not delete a failed result from these pages.**
- **`track-record.html`** ("Model Archive" in the nav) computes accuracy / calibration / ROI / fav-dog splits live from `model_predictions`, gating each model to its own `model_versions.test_start_date` out-of-sample window. **Never widen a model's window past its `test_start_date`** — that re-leaks training data (same rule as predictor.html's shared 2025+ window).

### Script load order (load-bearing)

Every page that has a nav must load **both** of these in order, before calling `cfl.renderNav()`:

```html
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.106.1/dist/umd/supabase.min.js" integrity="sha384-9dsYHX1/12VQI+gHRtPXSM3YFsgJ+iIPjTy4WCtY7XbKG/q7MTdZxZhMd4cL9Gif" crossorigin="anonymous"></script>
<script src="_shared.js"></script>
<script src="_auth.js"></script>
```

The Supabase CDN URL is **version-pinned + SRI-hashed** (sha384). This blocks supply-chain tampering — if the CDN ever serves a different file at that path, the browser refuses to execute it. When you bump the version, regenerate the hash with:

```powershell
$tmp=[IO.Path]::GetTempFileName(); Invoke-WebRequest -Uri 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@<NEW>/dist/umd/supabase.min.js' -OutFile $tmp -UseBasicParsing; "sha384-" + [Convert]::ToBase64String([Security.Cryptography.SHA384]::Create().ComputeHash([IO.File]::ReadAllBytes($tmp))); Remove-Item $tmp
```

…then grep+replace the URL and `integrity=` across every HTML file in the repo (they must all stay in sync, or hash mismatches will break specific pages silently).

- `_shared.js` creates `window.cflSupabase` and the `window.cfl` helper namespace (incl. `cfl.renderNav`, `cfl.renderFooter`, `cfl.fetchAll` for >1000-row queries).
- `_auth.js` creates `window.cflAuth` and is what populates the auth slot inside the nav. **If `_auth.js` is missing, the nav renders but never reflects logged-in state** — this is the most common nav bug.

### Supabase client config (do not change)

In `_shared.js`, the client is constructed with an explicit `auth.lock` set to a no-op passthrough:

```js
lock: async (name, acquireTimeout, fn) => fn()
```

This is a workaround for a Supabase auth-lock hang bug (see `supabase/auth-js#762`) where, after sign-in, all subsequent DB queries hang on a pending Promise. **Never remove this.** If you replace the Supabase client, you must preserve the no-op lock.

### Auth model

- All auth UI flows through `window.cflAuth` (see `_auth.js`). Bootstraps the session on load and exposes `getUser`, `getProfile`, `getTier`, `isPremium`, `signIn`, `signOut`, `signUp`, `resetPassword`, `updateProfile`, `requireAuth`, `joinWaitlist`, `onAuthChange`, `ready`.
- During beta, `profiles.beta_premium = true` for every account holder. `getTier()` returns `'premium'` when either `tier='premium'` OR `beta_premium=true`. `getPaidTier()` returns the underlying paid tier only. See `beta_premium_migration.sql`.
- The frontend tier check is **presentation only** — real enforcement is in Postgres RLS. Don't gate sensitive data on `auth.isPremium()` alone.

### Entitlements (`entitlements_migration.sql`, 2026-09-21)

**`public.current_user_is_pro()` is the only thing that may gate a Pro
surface.** It is `SECURITY DEFINER` with a pinned `search_path`, safe in RLS
policies and definer views. `current_user_entitlement()` returns `free | pro`
and is the single source of truth. `v_my_entitlement` lets the browser read its
**own** standing, one row, for rendering only. `entitlements.js` holds the
Free/Pro boundary and is **presentation only** — it decides what to draw, never
what may be sent.

- **Both layers honour `tier_expires_at`.** Neither did before: a lapsed
  subscription read as premium indefinitely, because `getTier()` looked at
  `tier` alone. That costs nothing until the first renewal failure.
- **P0 fixed the same day.** The `profiles` UPDATE policy pinned `tier`,
  `tier_expires_at` and `stripe_customer_id` — and **not `is_admin` or
  `beta_premium`**. `current_user_is_admin()` reads `is_admin`, and that
  function *is* the SELECT policy on `fight_odds`/`odds_books` while
  `email_subscribers` checks it directly. Any signed-in user could
  `update profiles set is_admin = true where id = auth.uid()` and read every
  subscriber's address. `_auth.js` stripped those fields client-side and its
  comment said "RLS will reject anyway"; **it did not**, and the publishable key
  is public by design, so the REST endpoint never needed our JavaScript.
- **A `WITH CHECK` protects exactly the columns it names.** Every column added
  to `profiles` is unprotected until someone adds it to that list.
  `tests/entitlements.test.js` fails when a security-bearing column is missing
  from the policy — so prefer pinning by exception and check the test when you
  add a column.
- **Nothing is gated yet, deliberately.** Applying the Free/Pro boundary is a
  later step. When a gate lands it belongs in a view or policy calling
  `current_user_is_pro()`, never in an `if (cflAuth.isPro())` around a fetch.
- **Checkout is blocked in code, not in a note.**
  `entitlements.js::CHECKOUT_BLOCKERS` lists T-054 (privacy must name Plausible)
  and T-048 (no Terms page); `checkoutMayBeEnabled()` returns false while either
  stands, and a test fails if a checkout entry point ships anyway. Turning
  checkout on requires deleting a named legal blocker — a deliberate act with a
  reviewer attached.

### Data layer (Supabase)

- Tables: `events`, `fighters`, `fights`, `fight_rounds`, `profiles`, `premium_waitlist`, `email_subscribers` (and analytics views prefixed `v_*`).
- **Market views.** `v_fight_odds_consensus` averages *every* row in `fight_odds`, including the prediction-market rows and the synthetic consensus row, so its `bookmaker_count` is not a count of sportsbooks. `fight_week_views.sql` (applied 2026-09-15) adds `v_fight_market_vigfree`, `v_fight_market_at_lock`, `v_fight_odds_latest_by_book` and `v_odds_books_sportsbooks`. **`market_movement_views.sql` (applied 2026-09-21, [D-012](coordination/DECISIONS.md))** defines **`v_fight_market_movement`**, which is what Card Lab, Fight Lab, Market Lab, the Cannon Card Brief and the social poster all read. `market_lab_views.sql` defined it first and is now only a pointer to that file — **two files defining one view is how the two drift.**
  - **Movement is measured over the MATCHED BOOK COHORT and refused below three of them.** The baseline is the **first broad CFL capture** — the instant CFL first held two-sided prices from three distinct real sportsbooks — and movement is the median across only the books quoting at *both* ends. Below three such books `movement_pts_a` is NULL and `movement_status` says which refusal it is; nothing widens the cohort to produce a number.
  - **There is no `open_p_a`, and there must not be again.** The retired column took `min(captured_at)` — CFL's single earliest capture. It was disclosed honestly ("our first capture", never "the opening line", always beside `books_at_open`) and it was still wrong: 22 of 79 fights had **one** sportsbook at that instant, the figure overstated real movement by up to **12.7 points**, and three markets that had not moved were reported as moving 3+. A caveat beside a wrong number does not make it right.
  - **CFL has never observed a sportsbook opener.** No surface, column, label or comment may say "opening line", "open", "opened at" or "since open". `market.js::baselineCaveat` prints the working — including *why* there is no number when there isn't one — so no page can show the figure bare.
  - **`fight_odds` and `odds_books` are `private_lockdown_admin_only` for `anon` AND `authenticated`.** A browser query against either returns zero rows with HTTP 200 and no error. All market reads go through the definer views above. This cost `parlay.html` every price on every leg for months before it was caught.
- **RLS policies on public-data tables (`events`, `fighters`, `fights`, `fight_rounds`, every `v_*` view) must grant `SELECT TO anon, authenticated`.** An anon-only policy causes signed-in users to see empty results with HTTP 200 and no error — extremely hard to debug. When adding a new public view or table, always grant to both roles.
- The Supabase publishable key is committed in `_shared.js`. That's intentional — it's a public anon key, all access is enforced by RLS.

### Secrets (env vars, NEVER paste in chat)

Recurring secrets live as environment variables on the Claude Code environment (configured once via the web UI → Environment settings) and as GitHub Actions secrets (same names). **Read them from `process.env.<NAME>` directly — do not ask the user for the value, and do not commit them.** If a secret is unset, scripts must fall back gracefully (e.g. dry-run mode) rather than fail loudly.

| Env var | Used by | Purpose |
|---|---|---|
| `SUPABASE_DB_URL` | Claude Code sessions applying SQL migrations via `psql` | Direct Postgres connection string (port 5432, not pooler — pooler doesn't allow DDL). Format: `postgresql://postgres:[password]@db.[ref].supabase.co:5432/postgres`. Get from Supabase dashboard → Project Settings → Database → Connection string → URI (Direct connection). When set, Claude applies migrations (`*.sql` files in repo root) directly with `psql "$SUPABASE_DB_URL" -f path/to/migration.sql` instead of asking the user to paste SQL into the Supabase SQL Editor. |
| `SUPABASE_SERVICE_ROLE_KEY` | `build/send-digest.js`, future admin scripts | Bypass RLS to read `email_subscribers` and other private tables. Get from Supabase dashboard → Project Settings → API → `service_role` key. |
| `RESEND_API_KEY` | `build/send-digest.js` | Send the weekly digest. Missing → script auto-falls-back to dry-run. |
| `RESEND_FROM` | `build/send-digest.js` | Verified sender, e.g. `Cannon Fight Lab <hello@cannonfightlab.com>`. |
| `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET` | `build/social-post.js` | OAuth 1.0a creds for posting to X. Missing → that platform is skipped. |
| `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USERNAME`, `REDDIT_PASSWORD`, `REDDIT_SUBREDDIT` | `build/social-post.js` | Script-app creds for posting to Reddit. Missing → that platform is skipped. |
| `ODDS_API_KEY` | `build/fetch-odds.js` (**active** workflow — see below) | The Odds API. |

#### `odds.yml` is active, and its cron is not its capture rate

This file used to describe the odds workflow as **disabled**. It is not, and was
not — `Fetch UFC odds` (`.github/workflows/odds.yml`) is an **active** workflow.
Anything reasoning from "that one's off" was reasoning from a wrong premise.

Its cron *asks* to wake **every 5 minutes** (`*/5`). That is a request, not a
schedule, and not a capture rate either. **GitHub throttles high-frequency
schedules**: measured 2026-09-19 this workflow was delivered four times in a
day, at :43, :30, :35 and :35. Never reason as though `*/5` means every five
minutes — it does not, and a tier that needs a wake at a particular *minute*
will simply never fire (that defect cost a whole card day of capture; see
`coordination/STATE.md`). The cadence gate therefore measures **elapsed time
since our own last capture**, which is robust to whenever a wake happens to
arrive.

The three tiers are:

- `build/fetch-odds.js::shouldCaptureNow()` decides **before any API call**
  whether the wake is worth a credit. A quiet wake queries Supabase and exits,
  spending no credit.
- Three tiers: a card **in flow** captures every 5 minutes, budget permitting; a
  card **today or tomorrow** captures hourly; otherwise **one baseline capture a
  day** at 08:00 UTC.
- A hard ceiling reads the provider's own `x-requests-remaining` (persisted in
  `odds_api_usage`), reserves the floor cost of each card still to come this
  month, and degrades 5 → 10 → 15 → 30 minutes to fit. **An unreadable ledger
  reads as tight, never as unlimited.** No paid tier without an L3.

**Migration status (updated 2026-09-19).**
`proposed_2026-09-16_fight_odds_capture.sql` is **applied** — quotes now carry
the CLV-001 §4 provenance fields, and the first card captured under it was UFC
331. `proposed_2026-09-16_event_flow.sql` is **not**, deliberately: it creates
`odds_api_usage` **empty**, and an empty ledger reads as *"0 spent, 500
remaining"*, which is false and would send the credit governor to its finest
rung on a wrong premise. Seed it from the provider's own
`x-requests-remaining` first (T-029). Until it lands, `fight_bout_order` and
`fight_bout_completions` are absent, so no card can be identified as **in
flow** by running order and the budget reads as unknown — which the governor
treats as tight, giving the 30-minute rung. That still clears the frozen
45-minute staleness limit, so it costs **lead time, never correctness**.

Per-channel funnel docs: `TRAFFIC_FUNNEL.md`.

### Funnel analytics (`cfl.track`)

**One emitter, two sinks, nineteen event names, and the names live in three
places that must agree** — `cfl.EVENTS` in `_shared.js`, the
`funnel_events_known_event` CHECK constraint in `funnel_events_migration.sql`,
and the table in [`ANALYTICS_SCHEMA.md`](ANALYTICS_SCHEMA.md). A typo becomes a
rejected insert rather than a funnel step that silently reads zero forever, and
`tests/analytics-events.test.js` fails if the three drift.

- **`funnel_events`** is ours: `INSERT` for `anon`/`authenticated`, **no
  `SELECT` for either**, everything else revoked. Counts come from
  `v_funnel_daily`. A new table in `public` inherits broad grants from Supabase
  defaults — `anon` held `UPDATE`/`DELETE` on first apply — so **verify grants
  after applying a migration; the migration's own text is not the result.**
- **Plausible was already installed** on 25 of 30 root pages before any of this.
  It receives the **event name only**: custom properties are a paid feature, and
  spending money is L3. Do not add a second vendor.
- **Nothing that identifies a person is ever sent.** `cfl.track` strips prop
  keys matching email / name / user id / token / IP / phone / stake / amount /
  wager / bankroll rather than trusting each call site. `session_id` is random,
  per-session, in `sessionStorage`, never joined to an account.
- **It never throws and never blocks a render.** Analytics is the least
  important thing on any page. Four events (`best_price_clicked`,
  `fight_shared`, `checkout_started`, `checkout_completed`) are **declared and
  not emitted** because nothing exists to fire them yet — that is deliberate, so
  a later sprint does not invent new names.
- **`privacy.html` does not yet name Plausible.** Queued as **T-054**; the
  wording is an owner-and-lawyer call, not ours.

### Verdict / edge logic

`edges.js` is the single source of truth for fight verdicts and edge factors. It's used by both this site (homepage `index.html`) and the cfl-snapshotter Node service. Any change here affects both. The `ctx` shape and edge-object shape are documented at the top of the file.

`fight-insights.js` is the companion single source of truth for the human-readable matchup layer. **Public:** `buildMatchupNotes` + `buildMatchupCaveats` — neutral measured differences between two fighters with no pick attached, plus `MATCHUP_NOTE`. Card Lab, Fight Lab, `event.html` and `fighter.html` all read these. **Retained but never rendered publicly:** `buildEdgeBullets` + `buildRedFlags`, which phrase the same comparisons around a model pick. Edit this file rather than inlining the copy into a page, so a second consumer can't drift from the first.

### `market.js` — every market number on every surface

**All market formatting goes through `market.js`, and this is not a style preference.** The rules it holds are wording rules: a price is never shown without its book count and its age; the movement baseline is the first *broad* capture and is never called an opener; a dash always carries its reason; best price is ordered by the American number and by nothing else. A page that formats its own market numbers is a page that can quietly drop one. `tests/no-model-on-public-surfaces.test.js` asserts that every market surface loads it, and `tests/market-movement.test.js` asserts the cohort rules.

### Cardio / consistency view (`v_fighter_consistency`)

- Live DB and the repo file are both on **v7** (August 2026) — they now match; keep them that way. v7 fixed two things v4–v6 got wrong: every round was hardcoded to five minutes regardless of when the fight actually ended (`fights.end_round` + `fights.end_time` give the real clock), and round-one pace was averaged over every fight including ninety-second blowouts while late-round pace could only come from long fights. v7 counts **only fights that reached round three, on both sides of the ratio**, and drops rounds under a minute. It carries the v6 renames (`grapp_ratio_pct`, `grapp_active`) and the grappling trigger (`td_landed/round >= 0.5 OR ctrl_seconds/round >= 45`). The grappling metric is the R3+/R1 ratio of `(td_landed × 60 + ctrl_seconds)` per round, capped by `dim_cap`.
- The score is a **ratio**, so it says whether a fighter held his own pace — not whether that pace was worth holding. A famously passive fighter who stays passive scores "tireless". `r1_sig_str_per_min` (added in v7) exists so the UI can flag that; `fighter.html` shows a "Low volume" tag off it.
- **Cardio does not predict winners** (50.2% on market-even fights, measured point-in-time). It was retired as an `edges.js` pick factor in August 2026 — do not reinstate it. It predicts fight LENGTH, and is shown as description, not as a pick.
- A separate, more rigorous rating lives in `cfl_engine/cardio/` — a mixed-effects fade slope written to the `fighter_cardio` table. Nothing renders it yet. When something does, it must show `min_past_10` or `n_fights_reaching_r3` beside the slope: low-exposure slopes are heavily shrunk toward the population mean.
- Per fighter the view emits one row per weight class plus a `'CAREER'` row. Frontend reads weight-class data first (when present and tier-tagged) and falls back to `CAREER`. See `loadCardioMap` in `index.html` and `cardioFor` in `fight-insights.js`.
- Tiers: `tireless` / `steady` / `tapers` / `fades` / `collapses`. Confidence: `high` / `limited`.
- **Before shipping any rename in a SQL view, grep the entire repo for the old column names.** `grapp_ratio_pct` is referenced in `index.html`; column-not-found errors silently break `loadFights`, which cascades into broken nav rendering.

### Style classifier (`v_fighter_style`)

Three buckets only: **grappler / striker / hybrid**. Per-weight-class rows + a `CAREER` fallback row. Requires `r1_minutes >= 10`.

- Use `"grappler"` not `"wrestler"` — the bucket includes shoot-takedown wrestlers AND submission grapplers (e.g. Oliveira).
- Dominance-ratio logic (NOT independent fixed thresholds). R1 output rates feed it:
  - `grapp_score = (td_landed × 60 + ctrl_seconds)` per round, normalized as `grapp_norm = grapp_score / 90`.
  - `strk_score = sig strikes landed` per round, normalized as `strk_norm = strk_score / 16`.
  - **hybrid** if both norms ≥ 1.0 and neither dominates 2:1.
  - **grappler** if `grapp_norm ≥ 1.0 AND grapp_norm ≥ 2 × strk_norm`.
  - **striker** is the mirror of grappler.
- The browser-side `classifyStyle` in `edges.js` is a less-accurate fallback that uses career-aggregate fields on the `fighters` table (`td_avg`, `slpm`). The SQL view is preferred when available.

### Prerendered stubs (`/f/` and `/e/`)

For SEO and social unfurls, every fighter and event has a static HTML stub:

- `f/<slug>-<id>.html` — fighter stub (e.g. `f/jon-jones-123.html`)
- `e/<slug>-<id>.html` — event stub

These stubs are **not** the canonical URL — each one carries `<link rel="canonical" href="...fighter.html?id=N">` (or `event.html?id=N`) pointing back to the dynamic page. Their job is purely to give crawlers and social unfurlers (Twitter, Facebook, Discord, iMessage — none of which run JS) a fully-populated `<head>` with the fighter's/event's real name, description, OG tags, and Athlete/SportsEvent JSON-LD. Humans who land on a stub URL get JS-redirected to the canonical page after ~120ms.

**Build pipeline** (`build/` folder):

- `build/prerender.js` — pulls all fighters and events from Supabase via the same publishable anon key as the frontend, writes stubs to `f/` and `e/`, regenerates `sitemap.xml`. Uses `writeIfChanged` so unchanged stubs don't churn git diffs, and prunes stale stubs whose underlying row was deleted.
- `build/templates.js` — `fighterStub(f)` and `eventStub(e, fighters)` HTML builders. **If you edit the static fallback meta in `fighter.html` / `event.html`, mirror the change here** or the stubs drift from the canonical pages.
- `build/slug.js` — `slugify(s)` lowercases, drops apostrophes, replaces non-alphanum runs with `-`. Falls back to `'item'` for empty strings.
- `.github/workflows/prerender.yml` — runs on `schedule` (every 6 hours), `workflow_dispatch` (manual), and `push` to `build/**` or the workflow file. It runs `npm run prerender` (stubs + sitemap + feed) and commits the result as `github-actions[bot]` with `[skip ci]` so the auto-commit doesn't re-trigger the workflow. **It does NOT run `npm run factor-rates` and does not stage `factor-rates.json`** — see the Factor Lab section. It used to do both; that is what made a reader defect publish itself unattended (T-027).

**Internal links** still go to `fighter.html?id=N` / `event.html?id=N` (via `cfl.fighterUrl` and `cfl.eventUrl`). Stubs are reachable via the sitemap and via direct sharing of slug URLs. If you ever want canonical to flip to the slug URL, change `cfl.fighterUrl` / `cfl.eventUrl` to emit slug paths and update the `<link rel="canonical">` in both the stub template and `fighter.html` / `event.html`.

**Repo size**: ~5,000 stubs × ~5KB = ~25MB on disk. Git diffs stay small because most stubs are stable run-to-run; only changed fighters' files are rewritten.

### Factor Lab (`stats.html` + `factor-rates.json`)

The free surface that tests which fight stats actually predict winners and which only repeat the betting line. `stats.html` renders it; it computes nothing — it fetches `factor-rates.json` and places stored values.

- **Built by [`build/factor-rates.js`](build/factor-rates.js), and published only on purpose.** It is **not** on any cron. Regeneration runs through [`.github/workflows/factor-rates-validate.yml`](.github/workflows/factor-rates-validate.yml) — manual (`workflow_dispatch`), `permissions: contents: read`, so the token it is handed **cannot write to the repository**. It produces a candidate artifact plus a before/after comparison (`build/compare-factor-rates.js`, non-zero exit if any verdict moved) and commits nothing. Publishing is then a deliberate commit of `factor-rates.json` in a PR where the moved verdicts show in the diff. `tests/publish-gate.test.js` keeps that shut. **Consequence: `factor-rates.json` goes stale until someone refreshes it on purpose** — a stale number that was reviewed beats a fresh one that was not. To regenerate locally you need `SUPABASE_SECRET_KEY` (or `SUPABASE_SERVICE_ROLE_KEY`): **`fight_odds` has no `SELECT` policy for `anon`**, so the publishable key returns zero rows with no error. The script hard-fails on an empty odds pull rather than shipping a confidently empty market column — do not "fix" that by removing the guard.
- **The whole point is market control.** Every factor gets two numbers: its raw win rate, and the same rate across only the fights the market priced as even (both fighters inside `EVEN_BAND` = ±140 at close). A factor that looks strong raw and collapses under market control was reading the favourite, not the fight.
- **Scored point-in-time.** The script walks fights chronologically and folds each result into a fighter's state only *after* scoring it. Never use career totals off the `fighters` table for this — they contain the result being predicted. That bug was live once and inflated the record factor to 75.5%.
- **Verdicts are computed in the build script, never in the page**: `real` (95% interval clears 50), `inverted` (interval below 50), `lean` (straddles 50 but still at or above `LEAN_PCT` = 55 — "can't tell yet"), `proxy` (straddles 50 below that), `unproven` (fewer than `MIN_SAMPLE` = 100 market-even fights), `insufficient` (under the floor overall). Intervals are Wilson, which behaves at small n.
- **Thresholds live at the top of the script**: `MIN_SAMPLE`, `EVEN_BAND`, `LEAN_PCT`, `MIN_PRIOR_FIGHTS` (3, shared by striking volume and finishing rate) and `MIN_RECORD_FIGHTS` (5, UFC record only — its bands sit on the raw win rate, which is noisy enough at three fights that 3-0 reads as a flawless 100%).
- **Bucket edges must match the range the metric actually reaches.** The UFC record bands were once cut at 8/15/25/40 points while sitting on a Laplace-smoothed rate that tops out near 0.3 — two of four bands held 98 fights and 4, and half the breakout published as "insufficient". If you add or re-cut a factor's bands, check the real distribution first.
- **Two factors currently survive market control, and they are not interchangeable.** Age, and the Factor Lab's `ufc_record` — the **raw UFC** win-loss gap, ~58% on the market-even cohort. Corrected 2026-09-18: this line used to read *"Only age currently survives market control"*, which was true of the figures then published and false of the data. The builder paged its odds rows without a stable order and was scoring 869 market-even fights where the real cohort is 1,220 (T-027).
- **`ufc_record` surviving is NOT evidence for `edges.js`'s record factor.** The Factor Lab tests a raw UFC-only gap; `edges.js` ships a Laplace-smoothed **whole-career professional** gap, which FE-001 measured at ~50.2% market-even — a coin flip. Two measurements, one everyday word. Any copy that merges them into a generic "Record" claim is wrong, whichever direction it leans, and `tests/record-factors-distinct.test.js` exists to stop it.
- Anything on the site claiming otherwise is stale copy — fix the copy, don't widen the test.

### Stat Finder views

`06_stat_finder_views.sql` defines the analytics views consumed by `stats.html`: `v_younger_fighter_winrate`, `v_southpaw_vs_orthodox`, `v_reach_advantage_winrate`, `v_title_finish_rate`, `v_finish_rate_by_division`, `v_main_event_finish_rate`. Views are non-materialized — cheap to compute and stay always-fresh against the source tables.

## Caching gotcha

GitHub Pages caches `_shared.js` and `_auth.js` aggressively. After shipping a change to either, returning users may see stale versions until they hard-reload. Cache-busting via `?v=N` query string on the `<script src>` is the recommended fix when shipping breaking changes to those files.

## Conventions

- All currency / numbers go through helpers in `_shared.js` (`cfl.formatRecord`, `cfl.formatHeight`, `cfl.formatReach`, `cfl.formatDate`, `cfl.formatDateShort`, `cfl.daysUntil`).
- For Supabase reads that may exceed the 1000-row per-call cap, use `cfl.fetchAll(() => sb.from(...).select(...))` — it pages through with `.range()`.
- HTML escaping: every interpolated string from the DB goes through `cfl.escapeHtml`. There is no template framework — XSS protection is manual.
- **Don't hardcode a live figure into prose.** The data behind `factor-rates.json` and the graded views is regenerated every few hours, so a sentence that says "57.0% on 128 fights" is wrong by the next cron run — this has already happened. Prose carries the *claim* ("the range still crosses a coin flip"); the live surface carries the *measurement*. Where a specific number genuinely has to appear in copy, label it as a dated snapshot the way `index.html` does ("Numbers on this panel are a snapshot as of ...").
- Per-page SEO meta is documented in `SEO_PER_PAGE.md`.
- User-facing copy follows `COPY_STYLE.md` (voice, plain-language translations of stats terms, anti-tout rules). See the note under "Product / naming".
