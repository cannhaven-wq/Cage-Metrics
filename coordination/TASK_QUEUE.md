# Task queue

What is queued, who owns it, and what level it sits at. One row per task.

**Levels** are defined in [`CRITICAL_GATES.md`](CRITICAL_GATES.md): `L0`
execute, `L1` AI-to-AI, `L2` proceed and notify, `L3` owner only.
**Owners**: `Claude` (build), `ChatGPT` (spec / review), `Owner` (Michael Cannon).
**Status**: `proposed`, `queued`, `in-progress`, `blocked`, `done`, `dropped`.

An `L3` task cannot be marked `done` until [`DECISIONS.md`](DECISIONS.md)
records the decision against its id. `tests/test_coordination.py` enforces it.

Ids are never reused. A task that dies is `dropped`, not deleted — the reason
it died is usually worth more than the task was.

---

## Open

| id | task | level | owner | status |
|---|---|---|---|---|
| T-002 | Individual votes on the nine held amendment clauses — (a) (b) (c) (d) (e) (f) (g) (j) (k) | L3 | Owner | blocked |
| T-003 | Review the CLV measurement protocol draft before freeze | L1 | ChatGPT | in-progress |
| T-006 | Two-sided quote capture at the publish instant | L1 | Claude | queued |
| T-007 | Resolve the five L3 questions in the CLV protocol, then freeze it | L3 | Owner | blocked |
| T-009 | Confirm how the owner is named in the governance records — "Reed Cannon" or "Michael Cannon" | L3 | Owner | blocked |
| T-011 | Pin the CI Python dependency set — `cfl_engine/requirements.txt` is `>=` ranges, so the suite can redden on an upstream release | L1 | Claude | queued |
| T-024 | Remeasure the exact `edges.js` record / td_def bands, and age, under market control — **owned by FE-001** | L1 | Claude | in-progress |
| T-025 | Dated correction to the `edges.html` factor table, once T-024 lands — **FE-001 supplies the evidence** | L3 | Owner | blocked |
| T-029 | Seed `odds_api_usage` from the provider's own `x-requests-remaining` before applying the event-flow migration — an empty ledger reads as "0 spent, 500 left" | L1 | Claude | queued |
| T-030 | Event Flow activation: produce `REAL_PAGE_CHECK.json` from a real UFCStats fetch, then uncomment the schedule | L1 | Claude | blocked |
| T-031 | Apply `proposed_2026-09-16_fight_odds_immutability.sql` — **between cards**, never during one | L3 | Owner | queued |
| T-032 | Retire a stale booking from the Event Flow observation instead of by hand, per `STALE_BOOKING_LIFECYCLE.md` §1 | L1 | Claude | queued |
| T-033 | Bring the rest of `fight-week-v2` onto `main` — Event Hub pages, fight pages, Market Board, Fight Week Brief, pre/post-card digest, `hub_visits` prune, funnel events, sitemap ordering — rebased on the current tree and reconciled with D-007 | L2 | Claude | queued |
| T-034 | Reconcile `revenue/trust-funnel-v1` with D-007: retire or re-route its claims manifest through `proof-gates.js`; keep the "forecast" wording, the single signup component and the funnel events | L2 | Claude | queued |
| T-035 | `claude/email-capture-modal-gbkqri` — an email prompt after two minutes on every page. Never approved; the owner's call | L3 | Owner | proposed |
| T-038 | Regenerate `social/queue.json` through `npm run social-engine` — every queued piece predates the repositioning and quotes a model probability, so `social-post.js` now refuses all 21 of them | L1 | Claude | queued |
| T-039 | Rewrite `build/draft-post.js` for the research positioning — it still renders a "Model pick / Confidence" table. Manual-only (`workflow_dispatch`), so it publishes nothing unattended | L1 | Claude | queued |
| T-048 | **CHECKOUT BLOCKER.** No Terms of Service page exists. `privacy.html` and `disclaimer.html` do, and `disclaimer.html` already carries UFC non-affiliation, 21+, helplines and affiliate disclosure — **those helpline/jurisdiction claims are themselves unverified and flagged for checking.** Facts for a drafter and the five open questions: [`legal-review/PROPOSED_WORDING.md`](../legal-review/PROPOSED_WORDING.md) | L3 | Owner | proposed |
| T-050 | Decide whether `parlay.html` and `mybook.html` stay reachable at all. Both are out of the primary journey and neither carries a model any more; `parlay.html` is a neutral calculator and `mybook.html` a private utility. Keeping or retiring them is a product call, not a defect | L3 | Owner | proposed |
| T-054 | **CHECKOUT BLOCKER.** `privacy.html` does not name **Plausible**, a third-party processor loading on 25 of 30 root pages since before the repositioning. Draft clause and the four questions a lawyer must answer: [`legal-review/PROPOSED_WORDING.md`](../legal-review/PROPOSED_WORDING.md). Nothing drafted into production | L3 | Owner | proposed |
| T-058 | Card-wide movement sparklines, if ever wanted. `v_fight_chart_series` is **single-fight only** — 22 ms for one literal `fight_id`, 4.6 s for twelve, and a subquery predicate does not push down at all. It needs a materialized view refreshed on capture, or a set-returning function called once per fight. Do not batch the current view | L1 | Claude | proposed |
| T-061 | Apply the Free/Pro boundary — flip `enforced` per surface and add the matching Postgres gate. A surface may only flip once `current_user_is_pro()` guards it server-side. **Moved behind the payment gates 2026-09-21 ([D-019](DECISIONS.md)): a paywall in front of a product with no checkout is a dead end, and it destroys `paywall_hit` as a measurement.** Needs T-054, T-048, a price, a Stripe account and a test-mode checkout first | L2 | Claude | blocked |
| T-062 | `email_subscribers` accepts an INSERT from anon with `WITH CHECK (true)` — normal for a signup form, but it means anyone can enqueue arbitrary addresses. Rate limiting or a confirmation step, if subscription spam ever appears. Not a vulnerability, a nuisance | L1 | Claude | proposed |
| T-066 | **L3, owner only.** Turn checkout on: set a price, connect a Stripe account, set `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` / `STRIPE_PRICE_ID`, remove the blockers from `entitlements.js` and enable the button — in one pull request where all of it shows in the diff. Blocked on T-048 and T-054 | L3 | Owner | blocked |
| T-067 | **L3, owner.** Set the CFL Pro price and decide which periods are sold. Stated default 2026-09-21: ~$9.99–$11.99/month, $79–$99/year, founding rate for the first cohort — **a preference, not a set price.** Also undecided: whether the founding rate is for life or a term, and what happens to it on lapse. `CRITICAL_GATES.md` item 7 | L3 | Owner | blocked |
| T-068 | **Owner.** Connect a Stripe account, create the product and price, set `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` / `STRIPE_PRICE_ID` as Supabase **function** secrets. Needs T-067 first. Enabling paid infrastructure is L3 | L3 | Owner | blocked |
| T-069 | Exercise checkout end to end in Stripe **test mode**: a real session, a real webhook delivery with a real signature, entitlement activating and then expiring. Everything below this is already tested offline and against the DB; this is the one layer no test can reach without keys. Needs T-068 | L1 | Claude | blocked |
| T-055 | Read the funnel once there is a week of traffic: `v_funnel_daily` answers the nine questions in `ANALYTICS_SCHEMA.md`. Do not tune the product on the first day's rows | L1 | Claude | queued |
| T-049 | Sportsbook jurisdiction labelling — offshore and regulated books are visually identical in the Market Lab per-book table. Needs a neutral classification, and whether to make a jurisdiction claim at all is not ours | L3 | Owner | proposed |
| T-041 | Decide whether `mybook.html`'s "vs earliest price seen" column should exist at all under Q-14, or whether any per-bet closing-line figure waits on the frozen CLV protocol | L3 | Owner | proposed |

## Closed

| id | task | level | owner | status |
|---|---|---|---|---|
| T-001 | Automate DUR-002's `armed → collecting` transition, guard-gated, with provenance recorded | L1 | Claude | dropped |
| T-005 | Build the `coordination/` layer and wire it into `CLAUDE.md` | L1 | Claude | done |
| T-008 | Draft the CLV measurement protocol | L1 | Claude | done |
| T-010 | Run the existing Python and JS test suites in CI, on push and pull request | L0 | Claude | done |
| T-020 | Replacement copy for the four contradicted public claims on `index.html` | L3 | Owner | done |
| T-021 | A model-vs-market representation that makes no unsupported edge claim | L3 | Owner | done |
| T-022 | Proof Center into the nav and footer, with analytics | L2 | Claude | done |
| T-023 | Label the explanation layer as matchup context, not model internals | L2 | Claude | done |
| T-026 | Stop the homepage headline pooling the live and replay records | L3 | Owner | done |
| T-027 | Settle the unordered `.range()` paging in `build/factor-rates.js`, and publish the corrected cohort | L3 | Owner | done |
| T-028 | UFC 331 launch activation — apply the additive capture migrations, reconcile the card | L3 | Owner | done |
| T-036 | Reword the shared funnel CTA away from "every edge factor unlocked" and bump `_shared.js?v=` across every consumer | L1 | Claude | done |
| T-037 | The research repositioning: remove the forecast from every forward-facing surface, build Card Lab / Fight Lab / Market Lab, reframe the email as the Cannon Card Brief | L3 | Owner | done |
| T-004 | Collapse the `picks.html` → `card-lab.html` → `/` redirect to a single hop | L1 | Claude | done |
| T-043 | A defensible market-movement baseline: matched book cohort, three-book floor, no "opening line" anywhere | L2 | Claude | done |
| T-044 | Sitemap hygiene — stop listing a noindex redirect stub and three empty query-string shells | L0 | Claude | done |
| T-045 | `fighter.html`'s own `lastName` rendered "Raul Rosas Jr." as "Jr."; delegate to `fight-insights.js` | L0 | Claude | done |
| T-051 | The Prop Board was still a live public model surface after the repositioning — archive it, drop it from the nav, `noindex` | L2 | Claude | done |
| T-052 | The Cannon Card Brief's email subject still read "model picks before the card" | L2 | Claude | done |
| T-053 | `verify-live` checked the pre-repositioning card; one assertion failed and two had gone stale silently | L0 | Claude | done |
| T-047 | Instrument the funnel events: `funnel_events` table, `cfl.track` in `_shared.js`, fifteen events emitting, four declared | L1 | Claude | done |
| T-046 | Every market horizon on one matched-cohort rule — `v_fight_market_at_lock` rebuilt, the 24 h lookback fixed, one shared intersection | L1 | Claude | done |
| T-040 | Widen `v_fight_odds_latest_by_book` past the 14-day window | L1 | Claude | done |
| T-056 | Movement history charts on Fight Lab, fixed cohort, refusal below three books | L1 | Claude | done |
| T-059 | **P0, FIXED** — the `profiles` UPDATE policy did not pin `is_admin` or `beta_premium`, so any signed-in user could make themselves an admin and read every `email_subscribers` row and all of `fight_odds` | L0 | Claude | done |
| T-060 | Auth + Pro entitlement architecture: `current_user_is_pro()`, `v_my_entitlement`, `entitlements.js`, the checkout gate. Gates nothing yet, by design | L1 | Claude | done |
| T-057 | `v_fight_market_quotes` used a multiply-referenced CTE — an optimization fence that blocked predicate pushdown. One fight's series took 3.4 s; now 22 ms | L0 | Claude | done |
| T-063 | Stripe subscription lifecycle end to end: `billing_migration.sql`, `billing-lifecycle.js`, the `stripe-checkout` and `stripe-webhook` edge functions, 39 offline tests, verified against the real DB. Charges nobody | L1 | Claude | done |
| T-064 | `pricing.html` presents the plan with the Subscribe button disabled **in the served HTML** and the reason on the page, read from `entitlements.js` rather than hardcoded. Also fixed `<footer</div>`, broken markup live on `main` | L1 | Claude | done |
| T-065 | `account.html` showed every beta member as "Free" (read `profiles.tier` alone, ignoring `beta_premium`) and promised billing "launches soon". Now reads `v_my_billing` and describes state through the shared state machine | L1 | Claude | done |
| T-070 | Fight watchlists: `user_watchlist`, the star on Card Lab / Fight Lab / the watchlist page, `v_my_watchlist`. Owner-scoped, nothing gated | L1 | Claude | done |
| T-071 | Price-target and market-movement alerts: `user_alerts` / `user_alert_prefs` / `user_alert_deliveries`, `v_fight_alert_market`, `alerts.js`, `build/send-alerts.js`, `alerts.yml`. **An alert cannot fire from a comparison CFL would refuse to print**; the matched-cohort rule is preserved and a re-arm across a cohort change re-baselines silently | L1 | Claude | done |
| T-072 | **P0-class, FIXED** — `REVOKE ALL FROM anon` left `authenticated` holding **TRUNCATE** on three new tables via Supabase default privileges. TRUNCATE bypasses RLS, so any signed-in member could have emptied every other member's watchlist and alerts. Plus two faults in the pin trigger that made it inert. All three found by checking behaviour, not by reading | L0 | Claude | done |
| T-073 | Re-enable the `alerts.yml` schedule (`*/15`). **Blocked on the controlled delivery test**: one dry run, one real alert to one real address, a verified duplicate-rerun, cleanup. Merging a workflow that carries a cron is turning that cron on, so it ships manual-only and comes back as its own reviewed commit | L1 | Claude | blocked |

---

## Notes on the open rows

**T-037 is done and is recorded as [D-011](DECISIONS.md).** It is the largest
single product change in this repo's history and it is L3 on two counts: it
retires existing public claims and it is a major architectural change to the
forward-facing product. The owner's instruction is quoted verbatim in D-011
rather than summarised, because an L3 approval that is paraphrased is not an
approval.

**T-038 is small but it is the one unattended publisher still carrying the old
positioning.** `social-post.yml` fires Mon/Wed/Fri. It now refuses any queued
piece that is not stamped `positioning: "research"`, so nothing ships — but the
queue is dead until it is regenerated, and the fallback path (`buildPost`, which
posts line movement) is what runs in the meantime. That fallback is correct, so
this is a restoration of capability, not a leak.

**T-040 is what stops Fight Lab being a durable SEO surface.** The per-book and
movement views are both scoped to `event_date >= CURRENT_DATE - 14`, which is
right for the capture cost and wrong for a page meant to rank on
"[fighter] vs [fighter] odds" long after the card. A fight outside the window
renders its matchup panel and an honest "no sportsbook price captured" market
panel — correct, but thin.

**T-041 is a genuine question, not a formality.** `mybook.html` used to show a
column headed "CLV" comparing the user's own price to the earliest price we had
captured. Under this change the header reads "vs first" and the summary tile
reads "Avg vs earliest price seen"; the arithmetic is unchanged. The argument
for keeping it is that it describes the user's own bet, not a CFL performance
claim, so Q-14's publication gate is not engaged. The argument against is that
Q-14's wording is unconditional about a user-facing surface. Claude does not get
to pick.

**T-009** is attribution, which is the one thing an append-only log exists to
get right. The records name the owner two ways: `protocol.json` resolves Q-14 by
**"Reed Cannon"** and `CLAUDE.md` names the owner that way, while
[D-004](DECISIONS.md) records **"Michael Cannon (owner)"**; both appear across
`STATE.md`, `HANDOFF.md` and the protocol document.

Whether that is one person recorded two ways or a genuine mis-attribution is
**not** something Claude or ChatGPT may settle by inference — which is why
nothing has been normalised and every entry still reads exactly as it was
written. L3 and blocked on the owner. The fix is a new `DECISIONS.md` entry
stating which name is correct, never an edit to the existing ones.

**T-002** is the live bottleneck on DUR-001's specification. The clauses are not
approved en bloc and are split by risk in the register. Six of them change data
eligibility, scoring, model behaviour or interpretation; three are governance
only. The three low-risk ones could move first if the owner wants to clear the
backlog without touching anything that affects a result.

**T-003** is with ChatGPT now. The draft is
[`research/clv/CLV_MEASUREMENT_PROTOCOL.md`](../research/clv/CLV_MEASUREMENT_PROTOCOL.md);
the review checklist is §7. Twelve decided rules, eleven open questions. It is a
**measurement protocol, not an experiment** — no hypothesis, no challenger, no
verdict, so it stays out of the DUR register.

**T-004** is small and self-contained, and is named in `CLAUDE.md` as worth
doing. Good filler when a larger line is blocked.

**T-006** is urgent in a way its size hides. Q-05's de-vigged variant needs both
sides of the market captured at the publish instant, and that can never be
backfilled — every card that goes by without it is permanently unavailable to
that definition. It does not wait on the protocol freeze, because capturing more
than you end up needing costs nothing and capturing less is irreversible.

**T-011** is what T-010 left unpinned. `tests.yml` pins its runner exactly
(`pytest==9.1.1`) but installs `cfl_engine/requirements.txt` as written, and that
file carries `>=` ranges for pandas, numpy, scikit-learn, scipy, statsmodels,
pyarrow, xgboost and tabulate. So the suite can go red on somebody else's
release, with no change in this repo behind it — the exact failure the pytest pin
exists to prevent, left standing on the larger half of the dependency set.

It was not fixed inside T-010 because `requirements.txt` is the **engine's** own
manifest, shared with the jobs that actually run the model. Pinning it is a
change to the engine's runtime, not to CI, and it deserves a deliberate run
rather than a line slipped into a CI pull request. The likely shape is a
CI-only constraints file rather than narrowing the manifest, so the engine keeps
its ranges and the test job stops floating.

**T-007** is the freeze. Five questions need the owner: Q-05 (vigged or de-vigged),
Q-06 (published probability or wager price), Q-07 (aggregation and weighting),
Q-08 (minimum sample), Q-11 (how it may be described). Each changes what a
published number means. It is blocked behind T-003 — ChatGPT reviews the
methodology first, so the questions reaching the owner have been through a
statistician.


**T-010 to T-026 come out of the 2026-09-18 read-only audit**
([`AUDIT_2026-09-18.md`](AUDIT_2026-09-18.md)). Three are the owner's.

**T-010** is the one with the best ratio of value to risk in the whole audit.
Seven test files — 168 tests, 4,227 subtests and 71 JS assertions — guard the
frozen-file hashes, the CLV publication gate, the proof-gate record separation
and the coordination invariants. They all pass. Nothing runs them: only
`event-flow.yml` invokes a single unittest module. A frozen hash could drift on
`main` and no gate would notice.

**T-020 and T-021 are L3 because of gate #8**, not because the finding is
debatable. Four public claims on `index.html` contradict artifacts in this
repository — including "graded at real closing prices", which is exactly the
claim CLV-001 exists to withhold. Replacement copy is drafted and no public
claim has been edited. What needs the owner is the wording that ships, not
whether the current wording is wrong.

**T-021 carries a standing direction** from the owner, 2026-09-18: the
governance rule in `CLAUDE.md` is preserved, and `CLAUDE.md` is **not** to be
amended merely to keep the percentage UI. The replacement must express the
model-versus-market comparison without asserting an edge the evidence does not
support.

### T-021 — what the page actually does, found live on UFC 331 night

**Observed 2026-09-19, ~21:00 UTC, on the live card. Nothing was changed.** The
owner spotted a main-event card reading *"Market — no consensus line yet"* and
*"Edge — needs a market price"*. Both statements were false.

**The sportsbook data was fine.** Verified end to end **as the `anon` role**,
which is what the browser is: `v_fight_odds_consensus` returned all 13 fights,
Van −157 / Pantoja +134 across **8 bookmakers**, `fetched_at` 20:46:09 — twenty
minutes old. Grants correct, view is `security_invoker=false` so it reads
through `fight_odds`'s RLS, query runs in **235 ms** against `anon`'s 3-second
`statement_timeout`. No data problem, and nothing to do with that day's
migration.

**The cause is a suppression guard in `index.html`** (~line 1126):

```js
value = confidence - marketPct;
if (value > 15) {   // "almost always stale or mismatched odds"
  marketPct = null; // ...and a null renders as "no consensus line yet"
  value = 0;
}
```

Three separate defects stacked:

1. **It blames the odds.** The comment says a big gap means stale or mismatched
   odds. Measured: eight books, fresh, provenance-complete. The odds were right
   and **the model was overconfident** — the code treats a model problem as a
   data problem.
2. **It then misreports that to the user** as an absence of data. The site has
   the line and says it does not.
3. **It is one-sided.** It fires only when the model is *above* the market.
   Chikadze (−19.2) and Gandra (−13.6) displayed their lines normally, so the
   page hides exactly the fights where CFL disagrees most bullishly.

Blast radius that night — **3 of 12 bouts, including the main event**:

| bout | model | market | gap | cell |
|---|---|---|---|---|
| Tuivasa vs Despaigne | 54.7% | 21.0% | **+33.7** | suppressed |
| Van vs Pantoja (main) | 79.6% | 58.9% | **+20.7** | suppressed |
| Shahbazyan vs Ferreira | 79.6% | 62.1% | **+17.5** | suppressed |

**The worse half: edge percentages are live.** Gaps between `VALUE_EDGE` (4) and
15 render as a green figure captioned "model over market" —

```js
edgeCell = `…<div class="n green">+${value.toFixed(0)}%</div>
            <div class="s">model over market</div>`
```

On that card, **Menifield +10%, Pitbull +9%, Vera +7%**. That is an edge
percentage in the user interface, which `CLAUDE.md`'s first rule prohibits
outright, and Q-14 explicitly left that prohibition standing. The rule has no
size exemption: the large gaps are hidden and the mid-size ones ship.

**Why no edge figure is defensible at any size.** `benchmark_report.md` records
the engine losing to the close — **0.6511 log-loss against 0.5978**. A model
worse calibrated than the market cannot claim to have found 21 points of edge
in it, and FE-001 left the shipped record and takedown-defence factors
unsupported. The owner's framing, 2026-09-19: *"a giant model/market
disagreement should trigger scrutiny of the model, not excitement about the
bet… the market deserves the presumption of correctness until CFL demonstrates
otherwise."*

**Direction approved by the owner 2026-09-19**, to implement after the card:

- **always show the verified consensus line** — hiding a real price and
  inventing a reason is strictly worse than showing it;
- **remove edge percentages entirely**, every size, not just the suppressed
  ones;
- **replace them with neutral model-vs-market language** that states where the
  model sits without asserting the difference is money.

**Why this was not shipped the same night.** Not pipeline risk — capture is
fully isolated from `index.html`, and `odds.yml` runs on schedule/dispatch, not
on push. The blocker is that the change is **not** the two-line edit it looks
like. `value` also drives the `✦ Value alert` badge and the "Value" sort. Delete
the suppression on its own and Tuivasa's +33.7 stops being hidden and starts
rendering a **Value alert** — the single most tout-y thing the site could
publish, on a +502 underdog. The three pieces (percentage text, badge + sort,
suppression) are coupled and have to move together, which is T-021 proper.

**T-020 and T-021 shipped together, later the same night**, in
[#38](https://github.com/cannhaven-wq/Cage-Metrics/pull/38) under [D-010](DECISIONS.md), on the owner's instruction to make the approved
changes live during the card. The three coupled pieces moved as one: the
suppression is gone (from `event.html` too, which carried the same guard), the
badge and sort became a neutral "Far from the market" badge and a
"Disagreement" sort, and the percentage became "N pts · CFL higher / market
higher / mostly agree" — the approved `fight-week-v2` wording — with the
sub-label "a flag on the model, not the price" from ten points up. The market
cell now reads the sportsbooks-only vig-free view with its book count and
quote age, so "6 books" means six books and a stale line says so.
`tests/model-vs-market.test.js` stops any of it drifting back. The isolation
claim above was re-verified before shipping: nothing in the diff touches
`build/`, the workflows that capture, or the database.

### T-033 to T-035 — what this week's branches still hold

**T-033.** `fight-week-v2` is the owner's own branch (2026-09-15) and the
source of the approved event-first direction. D-010 carried its homepage
wording and its sportsbooks-only market view; the rest — 128 files, 125
commits behind `main` — was not merged during a live card. It also carries a
three-tile record block that would put a live figure on the homepage, which
D-007 decided against; that part needs reconciling, not rebasing.

**T-034.** `revenue/trust-funnel-v1` (also 2026-09-15) predates D-007 and
computes the homepage and Proof Center headline through its own claims
manifest. `proof-gates.js` is now the one place that arithmetic may live, so
the manifest either goes through the rulebook or goes. The wording work in it
("forecast" for "pick", "model forecasts and market analysis, not handicapper
picks" — already used by D-010), the single signup component and the funnel
events are still wanted.

**T-035.** `claude/email-capture-modal-gbkqri` (2026-09-17) asks for an email
after two minutes on every page. No decision records it. It is the kind of
launch-UX change COPY_STYLE.md's anti-tout rule is sensitive to, so it waits.

**T-022 and T-023 are L2** — reversible, publish no new number, and T-023 can
only narrow what the page asserts. Proceed and notify.

**Ids T-020 to T-026 were renumbered on 2026-09-18, and the reason matters.**
They were first allocated as T-011 to T-016. While this session was working, a
second session allocated **T-011 to a different task** on the
`claude/brave-cray-rssmll-ci` branch. Two live meanings for one id in an
append-only log is the failure this file's "ids are never reused" rule exists
to prevent, so this session's block moved up and out of the way rather than
contest it. The gap from T-017 to T-019 is deliberate slack against the same
race happening again. Nothing was deleted: T-011 as used here never reached
`main`.

**T-022 and T-023 shipped 2026-09-18** in
[#25](https://github.com/cannhaven-wq/Cage-Metrics/pull/25), merged to `main`
at `e91a7da`. They were briefly marked `done` while existing only on a branch,
which was wrong — branch-only work is not shipped work — and they stayed
`in-progress` until the merge. Recorded as [D-006](DECISIONS.md).

The merge carried one addition found during consolidation: `fight-insights.js`
was changed without bumping its `?v=6` cache-bust, so a returning visitor would
have received the new heading over a cached script with no `CONTEXT_NOTE` — the
new heading with its explanation silently missing, which asserts less than the
copy it replaced. Bumped to `?v=7` on all three consumers before merge.

**T-026 shipped 2026-09-18** in
[#23](https://github.com/cannhaven-wq/Cage-Metrics/pull/23), merged to `main` at
`b1bc881a`, under [D-007](DECISIONS.md). It was L3 because it changes a
published number, not because the defect was arguable: the headline was computed
over the live and replay records pooled together, the fix computes it over one,
and **the number moves**. The owner chose the replay record, matching the
`(simulated)` label already beside it.

It also carries a second fix found reviewing the first. `assertOneRecord`
ignores UNKNOWN, so a graded row whose `source` resolved to no record passed the
gate and was then counted anyway — the aggregate runs over the graded rows, not
over the rows the assertion approved. `headlineFromPicks` now fails closed via
`assertEveryRow`. `flatStakeLedger` and `straightRecord` still use the
permissive assertion; extending it to them is open and named in the handoff.

**T-024 and T-025 moved out of this line on 2026-09-18.** A dedicated
factor-evidence workstream (**FE-001**) now owns the exact market-controlled
measurement and has run it; this line's preliminary work is parked rather than
merged, so there is one authoritative factor artifact instead of two competing
ones. Nothing about the finding changed — `edges.js` publishes 60–72% for a
record gap and 52–56% for takedown defence, and neither range traces to an
artifact — only who establishes the replacement numbers.

**The distinction that must survive the handover**, because it is the one that
was got wrong once already: `factor-rates.json` matches `edges.js`'s 10/20/30
takedown-defence bands but applies **no `willHaveWrestling()` gate**, and it
bands the **raw** record gap where `edges.js` bands a **Laplace-smoothed** one.
So any figure taken from it is evidence about the generic factor, never a
measurement of the shipped rule. Age clearing 50% standalone is likewise not
authority to reinstate it: the engine already carries age among its 49
covariates, so incremental value is a separate question.

**T-025 stays the owner's** under gate #8 whoever supplies the evidence.

**T-027 is diagnosed and fixed in code; it became L3 on the way.** See
[`research/factors/T-027_PAGINATION.md`](../research/factors/T-027_PAGINATION.md).

`build/factor-rates.js` paged every read with `.range()` and no `.order()` —
separate statements whose row order Postgres does not fix, so pages overlapped
and skipped. The evidence localises the loss to the `fight_odds` read alone:
`fights_scored` is 8,739 in both the published artifact and FE-001's independent
SQL, so the other three reads came back complete, and the market-even flag has
no other input. Replaced with keyset paging (`build/paginate.js`), which also
survives the concurrent writes `fight_odds` takes every five minutes; ordering
alone would not.

**It is L3, and the owner's, because a corrected run moves published
verdicts.** It was briefly worse than that: `prerender.yml` regenerated and
committed `factor-rates.json` every six hours, so merging the reader fix would
have performed and published a corrected run unattended. That route is closed —
the Factor Lab is out of the cron, and regeneration is now a manual workflow
running under `contents: read` that commits nothing.

So the remaining decision is narrower and cleaner: run the validation workflow,
read the comparison, and decide whether to publish the candidate. Publishing is
a deliberate commit of `factor-rates.json` in a pull request where the moved
verdicts show in the diff. The procedure is in the document above.

**T-027 closed 2026-09-18** under [D-008](DECISIONS.md), PR #34 at `f40fd27c`.
869 → 1,220, matching FE-001 exactly; the `fights_scored` control held at 8,739;
seven verdicts moved, one downward. The artifact published is the byte-verified
candidate (sha256 `ba3c9077…`), alongside the copy that keeps it honest —
`ufc_record` clearing the bar is **not** evidence for `edges.js`'s record
factor, and the displayed name is now "UFC-only record" so the one-line summary
says which record it means without relying on a caveat above it.
`tests/record-factors-distinct.test.js` stops that drifting back.

**What T-027 did not settle, deliberately:** the shipped `edges.js` record and
takedown-defence heuristics are still unsupported and still shipped. That is the
next product question and it is not a consequence of this one.

Deliberately excluded from the 2026-09-18 consolidation, which was merging
finished work rather than opening new lines.

---

## Notes on the closed rows

**T-010 — done 2026-09-18.** The repo had seventeen test modules and no workflow
that ran them; the only test invoked anywhere in `.github/workflows/` was a
single `unittest` module inside `event-flow.yml`. `.github/workflows/tests.yml`
now runs the whole suite on every push and pull request — `pytest` from the repo
root, not `pytest tests/`, so `cfl_engine/` and `research/` are in it too. 624
Python tests and two Node files, against the 168 the first draft of the workflow
would have covered.

It is **L0**, not L1: it adds no feature, asserts nothing new, and changes no
product behaviour — it pulls tripwires that were already built. What it buys is
that the frozen-file hash check, the CLV publication gate, the L3 gate and
`test_lock_prop0002.py`'s conformance proof stop depending on somebody
remembering to run them. For a gate, that is the difference between a guard and
a note.

The audit that found it is
[`reviews/2026-09-18-claude-ci-audit.md`](reviews/2026-09-18-claude-ci-audit.md).
The one thing it did not settle is **T-011**, above.

---

## Why T-001 was dropped

**T-001 — dropped 2026-09-17, not built.** It asked for automation of DUR-002's
`armed → collecting` transition. That transition is a **one-shot**: DUR-002
crosses it exactly once, and it has now crossed it. It was performed manually
and is on `main` — first lock 2026-09-16T01:29:00Z, 48 rows across 12 fights,
`lock_prop0002.py` frozen into DUR-002's frozen files, full guards rerun green.

Automation for an event that has already happened and cannot recur has no
remaining value. The task is dropped rather than deleted because the reasoning
is worth more than the task was: the *shape* of the work — detect first row,
record provenance, freeze the script, rerun guards, and **stop if any guard
fails** — is the template for the next experiment that arms, and D-002's
classification of it as L1 execution rather than an L3 decision still stands.

---

## The UFC 331 launch block (T-028 to T-032)

**T-028 — done 2026-09-19** under [D-009](DECISIONS.md). It is L3 because it
applies production migrations (gate #5), not because any step was arguable.

The finding that made it urgent rather than routine: **the odds job had captured
nothing on a card day.** `.github/workflows/odds.yml` wakes on `*/5`, and every
cadence tier gated on the wall clock — `min % cadence < WAKE_INTERVAL_MIN`.
That is equivalent to a cadence only if the cron really fires every five
minutes. GitHub throttles a `*/5` schedule to a handful of deliveries a day at
arbitrary minutes: on 2026-09-19 they landed at :43, :30, :35 and :35, never
once inside minutes 0–4. So the gate never opened, and the only UFC 331
moneyline rows on file that morning came from another writer.

Fixed in `build/fetch-odds.js` by measuring **elapsed time since our own last
capture** instead of the clock's phase, falling back to the phase test whenever
the last capture is unreadable — so a missing ledger degrades to the old
behaviour and never to "capture every wake". Seven regression tests, two of them
mutation-checked, including a replay of the four real wakes. Simulated against
tonight's card the same throttled wakes yield **10 captures instead of 1**.

**T-029** is the reason the event-flow migration did not go with it. It creates
`odds_api_usage` empty, and `remainingCredits([], undefined)` returns the full
500 — so the governor would read "nothing spent this month", which is false, and
take the finest rung. Seed the ledger from the provider's own
`x-requests-remaining` on a capture first; then the migration is safe.

**T-030** is blocked on the environment, not on a decision. `--execute` refuses
until `cfl_engine/event_flow/REAL_PAGE_CHECK.json` exists, and it cannot be
produced from CI or from an agent session: UFCStats answers 403 to both.

**T-031** carries its own timing rule. It adds triggers to `fight_odds` while
another repository writes to it, so it lands **between cards**. D-004 already
records that it is the owner's to apply.

**T-032** is the principled version of what T-028 did by hand. 47328 was retired
from three independent observations, but `STALE_BOOKING_LIFECYCLE.md` §1 wants
the retirement to fall out of `plan_append`'s `stale_fights` automatically. That
needs T-030 first.
