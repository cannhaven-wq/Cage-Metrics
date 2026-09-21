# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-21 (f) — The matchup audit, and two ideas it killed

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-21

The owner's new product direction — CFL's moat is proprietary matchup analysis,
not predictions — came with an explicit instruction: **audit before building**,
because "I'd rather CFL have six genuinely useful proprietary analytics than 50
arbitrary scores." The audit is done. **Nothing was built.** Every query was a
`SELECT`; no migration applied, no table created, no page touched.

- [`MATCHUP_ANALYTICS_SPEC.md`](../MATCHUP_ANALYTICS_SPEC.md) — the A–E
  classification, the metric formulas, the Fight Lab redesign, the first build.
- [`research/matchup/AUDIT_2026-09-21.md`](../research/matchup/AUDIT_2026-09-21.md)
  — the measurements, with the SQL that produced each one.

### Read this first: the headline feature, as specified, is noise

The direction put round-by-round cardio high on the list. Split-half
reliability says the **percentage** form does not survive:

| metric | reliability (n≥6 fights) |
|---|---|
| R3/R1 decline **ratio** | **0.05** |
| decline as **absolute drop** (strikes/min) | 0.30 |
| round output **level** | 0.56 |

A fighter's "output drops 36% by round three" tells you almost nothing about
their next fight. The same drop in strikes per minute is modestly real. So the
feature lives — the parameterisation dies. Dividing by a small, noisy R1
denominator was the whole problem.

**This contradicts a live surface.** `v_fighter_consistency`'s
`tireless/steady/tapers/fades/collapses` tiers are computed from that exact
ratio and `fighter.html` renders them. `CLAUDE.md` already says cardio does not
predict winners; this is narrower — the tier does not reliably predict the
fighter's **own next cardio performance**. Published claim, unreproducible
measurement, so it is gate #8 and it is yours: **T-066, L3.** Nothing edited.

### The one that worked

Opponent-adjusted striking is real and it is the P0. Adjusting a fighter's
prior output by what their opponents normally give up predicts next-fight
output at **0.3779** vs **0.2926** raw, n=6,902 held-out fighter-fights, all
strictly point-in-time. It beats *both* its inputs, and it wins in all four
era × fight-length subgroups (best: 0.36 → 0.47 for long modern fights).

### The one that didn't

The identical method on wrestling made prediction **worse** (0.3493 raw →
0.3466 adjusted), in two separate formulations. Takedown-defence % alone is
weak (0.115). Recommendation: **no opponent-adjusted wrestling composite** —
show his volume and their concession rate as two numbers that never merge.

### Two constraints now on the record

**The median UFC fighter here has four fights.** Requiring 3+ prior fights on
both sides covers 48% of fights since 2010; on the next card, 10 of 22 fighter
slots won't support the round-level section. "Not enough fights to say" is a
designed state, not an error path.

**CFL's real market history is 231 fights deep**, since 2026-05-30. The other
7,681 fights carry single-book historical odds whose `captured_at` is the Unix
epoch — a sentinel, not a time, on 30,724 rows. Comparables filtered on market
*price* are feasible now; on market *movement*, not for a year.

### Sequencing

This does not jump the queue. The owner's locked order stands and the matchup
work sits **after Stripe**, as T-063 to T-068.

## Next action

**Owner:** T-066 is the only thing needing you — the cardio tiers are a
published claim resting on a 0.05-reliability measurement. The likely fix is
reparameterisation to the absolute drop with shrinkage and a visible `n`, plus
a dated correction rather than a silent rewrite; deletion is not required.

**ChatGPT:** review the CFL-OAS v1 formula and validation design in
`MATCHUP_ANALYTICS_SPEC.md` §4 and `research/matchup/AUDIT_2026-09-21.md` T-3
before T-063 is built — specifically the shrinkage constant (measured but not
yet fitted), division/era normalisation, and whether one round of opponent
adjustment is enough.

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
