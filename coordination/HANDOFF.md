# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-21 (c) — The funnel counts, and the monetization sprint has started

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-21

PR #39 and #40 are **merged and live**. Production was verified serving the
merged commit (served-bytes MATCH on every file) and the card matched the
ground-truth table fight for fight. The monetization sprint has begun, in the
owner's locked order. **T-047 is done**; item 2 is T-046.

### T-047 — funnel analytics, actually emitting

[D-014](DECISIONS.md). Nineteen names, fifteen emitting, two sinks:
`funnel_events` (ours — `INSERT` only, no `SELECT` for anyone, aggregates via
`v_funnel_daily`) and the Plausible that was already installed. Names live in
`cfl.EVENTS`, the DB CHECK constraint and `ANALYTICS_SCHEMA.md`, and
`tests/analytics-events.test.js` (25 assertions) fails if they drift.

### Three things worth carrying forward

1. **Plausible was already on 25 of 30 root pages.** `ANALYTICS_SCHEMA.md`,
   written earlier the same day, said no vendor existed. It was wrong and is
   corrected. Plausible gets the event **name only** — custom properties are
   paid, and that would be an L3 spend taken by accident.
2. **`anon` held `UPDATE`/`DELETE` on the new table after applying**, inherited
   from Supabase's default `public` grants. RLS denied them, so nothing was
   exploitable, but one layer was doing the work of two. Revoked. **The
   verification query is what found it — the migration's own prose claimed the
   right outcome and the database disagreed.** Check grants after every apply.
3. **`privacy.html` does not name Plausible.** A third-party processor on every
   page, undisclosed. Gate 9, so it is **T-054** with draft wording in D-014
   rather than a quiet edit. **This one needs the owner before checkout, not
   after.**

`CLAUDE.md` also still described `open_p_a` and `openCaveat` as live, which
D-012 retired hours earlier. Corrected — that file is what a fresh session reads
first, and a stale entry there is how a retired column comes back.

### Verified

11 Node suites, **270 assertions**; 168 Python tests, 4,339 subtests. All green.
11 pages rendered at 1440, 768 and 390 px with zero horizontal overflow. The
database was exercised directly: a well-formed event inserts, an unknown event
name is rejected by the CHECK constraint, a short `session_id` is rejected, and
`v_funnel_daily` aggregates. The test row was deleted; the table is empty and
waiting for real traffic.

### T-046 — every horizon on one rule (added after the entry above)

[D-015](DECISIONS.md). The matched-cohort intersection now lives in exactly one
place, `v_fight_market_horizon_cohorts`, and three horizons aggregate it:
`broad_baseline`, `h24`, `lock`. Adding a fourth means adding a row to one CTE.

Two were still on the old footing and **one of them was mine**: the 24-hour
lookback D-012 itself shipped had exactly the defect D-012 removed from the
baseline. `v_fight_market_at_lock` was the other — worst disagreement **5.2
points**, one fight resting on a single book at lock.

**Did values move?** The 24 h horizon: no — worst disagreement 0.5 pts, under the
display threshold, so nothing rendered changed. Small because a day is short
enough that yesterday's books are still quoting; **not** small in the case that
matters, a book pulling a market during fight week. The lock horizon: yes, 5.2
points, though nothing public renders it. The baseline horizon is unchanged,
verified fight by fight against the ground-truth table.

`market.js` no longer subtracts one median from another to get the 24 h move —
it reads `movement_pts_a_24h` from SQL, because subtracting a matched median from
an all-books median re-mixes cohorts inside the formatter.

### The two checkout blockers, and what was deliberately not done

**T-054** (privacy must name Plausible) and **T-048** (no Terms page) are both
**checkout blockers**. Draft wording, the facts a drafter needs, and the open
questions are in [`legal-review/PROPOSED_WORDING.md`](../legal-review/PROPOSED_WORDING.md)
— **outside production. No legal language was written into any live page, and no
helpline, regulator or jurisdiction claim was invented.** `disclaimer.html`'s
existing helpline and Tennessee reference are flagged there for verification
rather than reused as though verified.

Two things a lawyer must decide that we explicitly did not: whether "anonymous"
or "pseudonymised" is correct for the funnel rows given a per-session id exists,
and whether a retention period must be stated — no prune job exists, so a stated
period needs one built to match.

### Next action

**Movement history charts**, once the PR carrying T-047 + T-046 is merged — the
owner's instruction is not to start them before that. They now have a clean
foundation: every horizon reads `v_fight_market_horizons`, so a chart that plots
a series across horizons cannot mix cohorts unless it goes around the view.

**Owner:** T-054 and T-048 are yours and they gate checkout, not launch. T-049
still gates affiliate links.

---

## 2026-09-21 (b) — The repositioning is on one branch, and its movement number is now defensible

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-21

The owner's direction, given today: **the model goes private, historical proof
stays.** The repositioning on `claude/focused-maxwell-qw232x` is the desired
product state, not `main`. This branch is that work plus today's trust sprint
on top of it, in one history.

### The branch reconciliation

`claude/focused-maxwell-qw232x` was verified before anything was built on it:
one commit (`24819e0`) on top of `main` at `2244b41`, no rebase needed, and it
does contain what was reported — Card Lab, Market Lab, Fight Lab, the Cannon
Card Brief, the archive banners, and `tests/no-model-on-public-surfaces.test.js`.
Nothing it built was rebuilt. It is merged here, not reimplemented.

Two id collisions were resolved in its favour, because it was written first:
its **D-011** and **T-037** stand; today's decision became **D-012** and its
task **T-043**.

### What today's sprint changed on top of it

`market_lab_views.sql` defined `v_fight_market_movement` with `open_p_a` from
`min(captured_at)`. It was scrupulous about disclosing that — "our first
capture", never "the opening line", always beside `books_at_open` — and it was
still wrong. On the live table, 22 of 79 fights had **one** sportsbook at that
instant; against a matched cohort the figure overstated movement by up to
**12.7 points** and reported **three markets as moving 3+ points when they had
not moved at all**.

[D-012](DECISIONS.md) replaces it: the baseline is the **first broad CFL
capture** (three distinct books priced), movement is medianed over the books
quoting at **both** ends, and below three such books there is no number — the
surface says which refusal it is instead. Market Lab's `<th>Since open</th>` is
gone. Every dash now carries its reason.

Also: the 14-day window is off the movement view (half of T-040), the sitemap
no longer lists a noindex stub or three query-string shells, `picks.html` is
one hop, and `fighter.html` no longer calls Raul Rosas Jr. "Jr.".

### Verified

11 Node suites — **245 assertions** — and 168 Python tests with 4,327 subtests,
all green. Every page rendered in headless Chromium at 1440, 768 and 390 px
with **zero horizontal overflow** on all of them. The Supabase CDN is blocked
by this environment's egress policy, so the browser could not load live data;
the number path was verified instead by running the real
`v_fight_market_movement` rows for UFC Fight Night: Rosas Jr. vs. Barcelos
through `market.js` directly, including a fabricated one-book fight to confirm
the refusal renders as a reason rather than a dash.

### Two model surfaces that survived the repositioning

[D-013](DECISIONS.md). `props.html` was in the no-model test's PRODUCT list and
passed anyway — it sells model output but says *projection*, and the ban list
was built from the fight forecast's vocabulary. It is archived now, out of the
nav, `noindex`. And the Cannon Card Brief's **subject line** still read
"<Event> — model picks before the card" while its body and its own footer said
the opposite; `build/send-digest.js` is on a weekly cron. Both now have guards:
`tests/card-brief.test.js` reads subject lines specifically, and the no-model
test checks that an archived surface is `noindex`, banner-carrying and unlinked.

`ANALYTICS_SCHEMA.md` and `PRODUCT_BOUNDARY.md` are the sprint's two written
deliverables — nineteen funnel events with the nine questions they answer, and
the Free/Pro line. Neither ships code; T-047 implements the first.

### Next action

**ChatGPT reviews [D-012](DECISIONS.md)**, specifically the three-book floor —
it is the one judgement in the change, and moving it is one constant in three
places. Then the sprint's unfinished phases, in this order: **T-047** (funnel
analytics — inventory what `_shared.js` already emits before adding a vendor),
**T-046** (`v_fight_market_at_lock`, the last incomparable-cohort baseline in
the repo), **T-038/T-039** (the social queue and `draft-post.js`, both still
pre-repositioning). **T-048** (Terms of Service) and **T-049** (sportsbook
jurisdiction labelling) are the owner's and need a lawyer, not a model.

---

## 2026-09-21 — The model is off the product; CFL is a research tool

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-21

The repositioning, on the owner's instruction, recorded as
[D-011](DECISIONS.md); T-036 and T-037 are done. Branch
`claude/focused-maxwell-qw232x`.

### What is now live

| | |
|---|---|
| positioning | "Research the UFC market." The forecast is gone from every forward-facing surface; what the site sells is the market, the movement and the matchup |
| Card Lab (`index.html`) | per fight: vig-free consensus, the fair price behind it, movement since our first capture, best price and the book posting it. Sorts are Card order / Biggest move / Books disagree. No pick, no confidence tier, no CFL-vs-market difference |
| Fight Lab (`fight.html`, new) | one matchup: both corners' consensus and best price, movement over two horizons, book spread, freshness, a per-sportsbook table, and the measured differences between the two fighters. Rewrites its own `<title>` and share description from the fighters' names |
| Market Lab (`market.html`, new) | the whole card as a board — consensus, best price each side, since-open, 24 h, book spread, capture age — with a per-fight book breakdown that expands on demand, and a "what changed in the last 24 hours" list above it |
| Factor Lab | unchanged and promoted into the nav |
| data layer | one additive view, `v_fight_market_movement` (`market_lab_views.sql`), **applied**. Same shape and grants as the existing market views; nothing replaced, nothing dropped |
| shared module | `market.js` — every market number on every surface is formatted here, so "never without its book count and its age" and "our first capture is not the opening line" are enforced in one file |
| matchup layer | `fight-insights.js` gains `buildMatchupNotes` / `buildMatchupCaveats`: the same comparisons with no pick to hang them on. `buildEdgeBullets` / `buildRedFlags` are retained and no longer rendered anywhere public |
| email | **The Cannon Card Brief.** `build/send-digest.js` now reports the biggest line moves, the book spread and the freshness instead of a "Model pick / Confidence" table |
| social | `build/social-post.js` posts line movement, not picks, and refuses any queued piece not stamped `positioning: "research"` |
| SEO assets | 4,549 fighter stubs, 799 event stubs, 62 preview pages and 8 card pages rewritten in place, plus the generators behind them (`build/templates.js`, `build/prerender.js`, `build/preview-templates.js`, `build/event-preview-templates.js`) — these were the unattended publishers |
| archive | `proof.html`, `track-record.html`, `predictor.html`, `edges.html` and `methodology.html` keep every number and gain a dated banner saying the model they document is no longer in the product |

### Three defects found on the way, all pre-existing

1. **`parlay.html` had been showing no prices at all.** It queried `fight_odds`
   and `odds_books` directly; both carry `private_lockdown_admin_only` for
   `anon` *and* `authenticated`, so every leg rendered "—" with HTTP 200 and no
   error. It now reads `v_fight_odds_latest_by_book`.
2. **`mybook.html` settled bets off `model_predictions`.** A fight the model
   never scored could never settle a user's bet. It now reads `fights` directly.
3. **Two mobile overflows and one shared-footer overflow**, the footer one on
   every page of the site. All three fixed.

### Verified

All 7 Node suites and 168 Python tests (4,296 subtests) green, including the new
`tests/no-model-on-public-surfaces.test.js` (60 assertions) which replaces
`tests/model-vs-market.test.js`. Every page rendered in headless Chromium at
1440 and 390 against real UFC Fight Night: Rosas Jr. vs. Barcelos rows: no page
errors, no horizontal overflow anywhere. The new view was checked against the
live database — 9 of 11 fights priced, 26 captures on the main event, one line
6.3 points off where we first saw it.

### Held to scope

No model, threshold, schedule, snapshot, ledger or frozen specification was
changed. The engine still runs and still writes its locked pre-fight record. The
CLV publication gate is untouched and still shut. No paid tier was created.

## Next action

**Owner:** one call, **T-041**. `mybook.html` had a column headed "CLV"
comparing a user's own price to the earliest price we captured. It now reads
"vs first" / "Avg vs earliest price seen" — same arithmetic, different words.
Q-14's wording is unconditional about a user-facing surface; the counter-argument
is that this describes the user's bet, not a CFL claim. That is a judgement call
and it is yours.

**ChatGPT:** the claim worth attacking is `open_p_a`. It is the median across
whichever sportsbooks happened to be in our *first capture* of a fight, which on
most cards is one offshore book, and every surface that shows it also shows
`books_at_open` and calls it "our first capture" rather than the opening line.
The question is whether a reader who is told "1 book, Sep 18 01:55 UTC" still
reads a six-point move as six points of market movement rather than partly as a
change in which books we were reading. If not, the honest fix is to define the
baseline as the first capture at which N books were quoting, and to publish
nothing before that.

---
