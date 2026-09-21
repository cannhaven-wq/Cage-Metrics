# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-21 (e) — Entitlement moves into Postgres, and a P0 came with it

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-21

PR #42 merged (`ce2c55c`). Item 4 of the monetization sequence — auth + Pro
entitlements — is done. [D-017](DECISIONS.md), T-059 / T-060.

### Read this first: a live privilege escalation, now closed

The `profiles` UPDATE policy pinned `tier`, `tier_expires_at` and
`stripe_customer_id`. It did **not** pin `is_admin` or `beta_premium`.
`current_user_is_admin()` reads `is_admin`, and that function *is* the SELECT
policy on `fight_odds` and `odds_books`; `email_subscribers` checks it
directly. **Any signed-in user could make themselves an admin and read every
subscriber's email address.**

`_auth.js` strips those fields client-side and said "RLS will reject anyway".
It did not — and the publishable key is public by design, so the REST endpoint
never needed our JavaScript.

Fixed and **verified as the `authenticated` role in a rolled-back
transaction**: both escalations now fail 42501, ordinary profile edits still
work. A sweep of every other UPDATE/INSERT policy found **no second instance**.
Treated as L0 and executed rather than queued; the reasoning is in D-017.

Worth knowing: the first version of that verification was **confounded** —
`beta_premium` is `true` for everyone during beta, so setting it to `true` is a
no-op, not an escalation, and it read as a false failure until the test flipped
the value instead. The empirical check was right to be run and wrong on the
first pass.

### The entitlement layer

`current_user_entitlement()` (`free | pro`) and `current_user_is_pro()` —
`SECURITY DEFINER`, pinned `search_path`, safe in RLS. `v_my_entitlement` gives
the browser its own standing and no one else's. Verified across six cases
including **paid-but-expired → free**.

That last one is a second bug fixed: `tier_expires_at` was honoured nowhere, so
a lapsed subscription would have kept access indefinitely. Free today, because
nobody has paid; expensive on the first renewal failure.

### Nothing is gated, and checkout is blocked in code

Every surface is `enforced: false`. Applying the boundary is step 5, after
Stripe. When a gate lands it goes in a view or policy calling
`current_user_is_pro()`, never an `if (cflAuth.isPro())` around a fetch.

`entitlements.js::CHECKOUT_BLOCKERS` names **T-054** and **T-048**;
`checkoutMayBeEnabled()` is false while either stands and a test fails if a
checkout entry point ships. Auth, pricing and Stripe wiring can all be built
meanwhile — only taking money is blocked, which is what the owner asked for.
**Turning checkout on now means deleting a named legal blocker**, deliberately.

### Verified

13 Node suites, **315 assertions**; 168 Python tests, 4,369 subtests. All green.

### Next action

**Stripe + pricing** (item 5 in the owner's ordering of the remaining work),
built against `current_user_is_pro()` and behind the checkout gate. Then apply
the Free/Pro boundary (**T-061**), then watchlists and alerts.

**Owner:** T-054 and T-048 are now the literal blocker on revenue, not a note —
the code will not let checkout ship until they are resolved. Draft wording and
the open legal questions: [`legal-review/PROPOSED_WORDING.md`](../legal-review/PROPOSED_WORDING.md).

---

## 2026-09-21 (d) — The chart draws one cohort, or it draws nothing

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-21

PR #41 merged (`ac7d485`). Item 3 of the monetization sequence — movement
charts — is done. [D-016](DECISIONS.md), T-056 / T-040 / T-057.

### The chart

Fight Lab has a "How the market moved" section: a stepped line of the vig-free
consensus over time, on a **fixed cohort**, with the cohort size in the footer,
a methodology disclosure written from what actually happened on that fight, a
per-sportsbook overlay and a table of the same numbers.

Four rules, all enforced in `market-chart.js` rather than in the page:
one fixed cohort **asserted in JS rather than trusted from SQL**; no
interpolation (the path is `H`/`V` only, and a test parses the emitted `d`
attribute); refuse rather than thin below three books; the cohort size on
screen, not only on hover. A cohort that changes mid-series is refused with
copy saying it is **our bug**, not a quiet market.

The cohort is not a new definition — it is the `broad_baseline` matched cohort
from T-046, which fixes the window for free.

### A 155x fix found on the way, and what it does not buy

`v_fight_market_quotes` used a CTE referenced twice. A multiply-referenced CTE
is an **optimization fence**: `WHERE fight_id = X` never pushed into it, so
every reference re-scanned ~85k rows. One fight's series took **3,412 ms**; as
a direct self-join it takes **22 ms**, and every market surface gets that.

It does not make the view batchable. Twelve fights cost **4.6 s**; a subquery
predicate does not push down at all. **`v_fight_chart_series` is single-fight
only**, which is why the chart lives on Fight Lab and **Market Lab has no
sparkline**. Card-wide charts need a materialized view or a set-returning
function — **T-058**, queued rather than guessed at.

### T-040 closed

`v_fight_odds_latest_by_book` lost its 14-day window. **51 fights older than a
fortnight have their sportsbook detail back**; the oldest event covered is
2026-05-30. That was the last of the windowed views.

### Verified

12 Node suites, **298 assertions**; 168 Python tests, 4,357 subtests. 12 pages
at 1440, 768 and 390 px, zero horizontal overflow. The chart was rendered in
headless Chromium against the real UFC 331 series and inspected: 20 points,
step path with **no diagonal segments**, labels aligned to their grid rows,
cohort size in the footer. Tampered data (a cohort change injected mid-series)
is refused, confirmed by running the module against it.

Two rendering defects were found by looking at the screenshots rather than by
testing: SVG text scaled with the viewBox to ~19px, and the HTML labels were
misaligned from their grid rows by the letterboxing. Both fixed — labels are
HTML and the viewBox no longer preserves aspect ratio.

### Next action

**Auth + Pro entitlement architecture** (item 4), which the owner's sequence
gates behind this PR being merged. Do not start it before then.

**Owner:** T-054 (privacy must name Plausible) and T-048 (Terms) still gate
checkout, and checkout is two items away. Draft wording is in
[`legal-review/PROPOSED_WORDING.md`](../legal-review/PROPOSED_WORDING.md).

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
