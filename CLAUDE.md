# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Product / naming

- **Product name is Cannon Fight Lab (CFL).** Never refer to it as "Cage Metrics" in user-facing copy. The repo on GitHub is still named `Cage-Metrics` for historical reasons — **do not rename the repo**.
- Wordmark: "Cannon Fight Lab" full / "CFL" short. Domain: `cannonfightlab.com`.
- Owner: Reed Cannon. GitHub: `cannhaven-wq`. Remote: `https://github.com/cannhaven-wq/Cage-Metrics.git`.

## Related repos (live on GitHub under `cannhaven-wq`, not in this folder)

- **Cage-Metrics** — this repo. The website. Plain HTML/CSS/JS, hosted on GitHub Pages.
- **cage-metrics-scrapper** — Python fighter scraper, runs on Railway.
- **cage-metrics-event-scrapper** — Python event scraper, in-progress on Railway.
- **cfl-snapshotter** — Node predictions snapshotter. Shares verdict logic with the frontend via `edges.js` (loaded with `<script>` in browser, `require('./edges')` in Node).

## Build / run / deploy

The site itself is plain static HTML/CSS/JS — no bundler, no test suite. There is one Node build step (prerender) that runs in CI on a schedule; you don't need it locally.

- **Local preview**: open `index.html` directly, or `python -m http.server` from the repo root.
- **Deploy**: pushing to `main` deploys to GitHub Pages automatically. `.nojekyll` is present so Pages serves files as-is. `CNAME` pins the custom domain.
- **Prerender**: `cd build && npm install && npm run prerender` regenerates the static stubs (see "Prerendered stubs" below). You almost never need to run this locally — the GitHub Action handles it on a 6-hour cron.
- No lint, no test suite. Don't add either without asking.

## Architecture

### Page model

Every page is its own standalone HTML file at the repo root (`index.html`, `fighter.html`, `h2h.html`, `parlay.html`, `stats.html`, `cardio.html`, `event.html`, `fighters.html`, `pricing.html`, `account.html`, `login.html`, `signup.html`, `reset.html`, `about.html`, `contact.html`, `disclaimer.html`). Shared chrome (nav, footer) is rendered by JS into `<nav class="cfl-nav">` and `<footer class="cfl-footer">` placeholders.

### Script load order (load-bearing)

Every page that has a nav must load **both** of these in order, before calling `cfl.renderNav()`:

```html
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.106.1/dist/umd/supabase.min.js" integrity="sha384-dzQgxMPp/h+N0t5qDf6Bp516wKZr3pXgGMpA7/ZM6tiWkqYo90N060L03dxnZ8Tf" crossorigin="anonymous"></script>
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

### Data layer (Supabase)

- Tables: `events`, `fighters`, `fights`, `fight_rounds`, `profiles`, `premium_waitlist` (and analytics views prefixed `v_*`).
- **RLS policies on public-data tables (`events`, `fighters`, `fights`, `fight_rounds`, every `v_*` view) must grant `SELECT TO anon, authenticated`.** An anon-only policy causes signed-in users to see empty results with HTTP 200 and no error — extremely hard to debug. When adding a new public view or table, always grant to both roles.
- The Supabase publishable key is committed in `_shared.js`. That's intentional — it's a public anon key, all access is enforced by RLS.

### Verdict / edge logic

`edges.js` is the single source of truth for fight verdicts and edge factors. It's used by both this site (homepage `index.html`) and the cfl-snapshotter Node service. Any change here affects both. The `ctx` shape and edge-object shape are documented at the top of the file.

### Cardio / consistency view (`v_fighter_consistency`)

- Live DB is on **v6**. The `v_fighter_consistency.sql` file in this repo is the older **v5** definition — the live view in production includes the v6 renames (`td_ratio_pct` → `grapp_ratio_pct`, `td_active` → `grapp_active`) and the broader wrestler trigger (`td_landed/round >= 0.5 OR ctrl_seconds/round >= 45`). The grappling cardio metric is the R3+/R1 ratio of `(td_landed × 60 + ctrl_seconds)` per round, capped by `dim_cap`.
- Per fighter the view emits one row per weight class plus a `'CAREER'` row. Frontend reads weight-class data first (when present and tier-tagged) and falls back to `CAREER`. See `loadCardioMap` / `cardioFor` in `index.html`.
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
- `.github/workflows/prerender.yml` — runs on `schedule` (every 6 hours), `workflow_dispatch` (manual), and `push` to `build/**` or the workflow file. Commits as `github-actions[bot]` with `[skip ci]` so the auto-commit doesn't re-trigger the workflow.

**Internal links** still go to `fighter.html?id=N` / `event.html?id=N` (via `cfl.fighterUrl` and `cfl.eventUrl`). Stubs are reachable via the sitemap and via direct sharing of slug URLs. If you ever want canonical to flip to the slug URL, change `cfl.fighterUrl` / `cfl.eventUrl` to emit slug paths and update the `<link rel="canonical">` in both the stub template and `fighter.html` / `event.html`.

**Repo size**: ~5,000 stubs × ~5KB = ~25MB on disk. Git diffs stay small because most stubs are stable run-to-run; only changed fighters' files are rewritten.

### Stat Finder views

`06_stat_finder_views.sql` defines the analytics views consumed by `stats.html`: `v_younger_fighter_winrate`, `v_southpaw_vs_orthodox`, `v_reach_advantage_winrate`, `v_title_finish_rate`, `v_finish_rate_by_division`, `v_main_event_finish_rate`. Views are non-materialized — cheap to compute and stay always-fresh against the source tables.

## Caching gotcha

GitHub Pages caches `_shared.js` and `_auth.js` aggressively. After shipping a change to either, returning users may see stale versions until they hard-reload. Cache-busting via `?v=N` query string on the `<script src>` is the recommended fix when shipping breaking changes to those files.

## Conventions

- All currency / numbers go through helpers in `_shared.js` (`cfl.formatRecord`, `cfl.formatHeight`, `cfl.formatReach`, `cfl.formatDate`, `cfl.formatDateShort`, `cfl.daysUntil`).
- For Supabase reads that may exceed the 1000-row per-call cap, use `cfl.fetchAll(() => sb.from(...).select(...))` — it pages through with `.range()`.
- HTML escaping: every interpolated string from the DB goes through `cfl.escapeHtml`. There is no template framework — XSS protection is manual.
- Per-page SEO meta is documented in `SEO_PER_PAGE.md`.
