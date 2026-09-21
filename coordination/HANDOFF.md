# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-21 — Movement compares like with like, or says it cannot

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-21

A production-readiness sprint was requested. **Its premise did not match the
repo, and that is the most important thing in this entry** — read "Where the
brief and the repo disagree" below before acting on anything from it.

### Shipped

Recorded as [D-011](DECISIONS.md); T-004, T-037 and T-042 are done.

| | |
|---|---|
| `market_movement_views.sql` | applied. Four read-only views. `v_fight_market_quotes` (de-vigged per-book quote history), `v_fight_market_broad_baseline` (the first broad CFL capture), `v_fight_market_movement` (movement over the matched cohort, with provenance), `v_fight_market_movement_books` (the show-your-working rows) |
| dropped | the live `v_fight_market_movement` from the unmerged `fight-week-v2` branch — `open_p_a`, `open_p_b`, `books_at_open`, where "open" was `min(captured_at)`. It was in **no repo file**. No dependent view, no repo consumer, no rendered surface; checked before the drop. Every defensible column it had is kept; its 14-day event window is not |
| `market-movement.js` | the only place a movement number becomes words. Plain → number → detail, and an honest refusal below three matched books |
| tests | `tests/market-movement.test.js` (25), `tests/sitemap-hygiene.test.js` (11) |
| SEO | `card-lab.html` (noindex meta-refresh stub) and the bare `fighter.html` / `event.html` shells removed from `sitemap.xml` and from `build/prerender.js`; `methodology.html` and `privacy.html` added; `picks.html` now redirects straight to `/` instead of through `card-lab.html` |
| access | `v_fight_market_quotes` granted to no public role — full tick history is the Pro asset |
| docs | `PRODUCT_BOUNDARY.md` — Free vs Pro, a proposal, nothing priced |

The numbers behind it, measured live: 22 of 79 fights had exactly one
sportsbook at CFL's earliest capture; the retired method overstated a move by
up to 12.7 points and reported three phantom moves on markets that had not
moved. Worked examples are in D-011.

### Where the brief and the repo disagree

The sprint brief asserted, as settled fact, that public model surfaces had been
removed and that a Market Lab, a Fight Lab and a Cannon Card Brief exist. On
`main`, on 2026-09-21:

- **Market Lab, Fight Lab, Cannon Card Brief**: do not exist. Zero occurrences
  outside the brand name "Cannon Fight Lab". They are [T-033](TASK_QUEUE.md),
  queued, on an unmerged branch.
- **The public model is not gone.** `track-record.html` is in the primary nav
  and publishes ROI, profit/loss and an edge-banded bet table;
  `predictor.html`, `parlay.html`, `props.html` and `mybook.html` all ship.
  D-010, approved two days earlier, deliberately kept "Model vs Market" on the
  homepage.

So the brief's instruction "do not regress that work" and its acceptance
criterion "the public model remains gone" cannot both be honoured and be true.
Nothing was removed on the strength of a premise the repo contradicts.
**[T-039](TASK_QUEUE.md) is the owner's call** and it is the live baton.

### Next action

**Owner decides T-039**: does CFL stay a model-and-market product with the
Proof Center carrying the record (the D-010 position, two days old), or does it
reposition to research-and-market-intelligence with the model private? Every
other queued item downstream — T-040's analytics event names, T-041's "opening
line" relabelling, T-033's Market Lab and Fight Lab, the Cannon Card Brief —
depends on that answer, and none of them should start before it.

---

## 2026-09-19 (b) — The homepage is the card, and it claims no edge

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-19

Frontend release on UFC 331 night, on the owner's instruction to make the
approved website changes live during the card. [PR #38](https://github.com/cannhaven-wq/Cage-Metrics/pull/38),
recorded as [D-010](DECISIONS.md); T-020 and T-021 are done.

### What is now live

| | |
|---|---|
| hero | the current card — "*UFC 331: Van vs. Pantoja 2* — Model vs Market" — with a rail of counts (fights, forecasts locked since Sep 7, sportsbook lines with book range and quote age, big disagreements) and the three widest gaps |
| market cell | always shown; sportsbooks-only vig-free median (`v_fight_market_vigfree`), "6 books, vig removed · N min ago", **stale** past 3 h on a fight day / 36 h otherwise, "no sportsbook line captured yet" when there is none |
| third cell | "Difference · N pts · CFL higher / market higher / mostly agree"; from 10 points a neutral "Far from the market" badge and "a flag on the model, not the price" |
| removed | `+N% model over market`, `✦ Value alert`, the Value sort, the parlay strip, "Top edge · next card", and `event.html`'s "Edge +Npp" / "⚡ Value" |
| claims | "graded at real closing prices" and the hardcoded 61% / 75% out of every meta/OG/Twitter string; "find where the betting line is wrong" out of the hero; `519-139`, `+10.0%`, `12-5`, `down $61`, "as of Aug 18" out of the prose; the how-to steps no longer name retired drivers |
| records | replay headline unchanged, via `proof-gates.js`, "(simulated)" on the phone strip too; the live record described and linked, not numbered (D-007) |
| shared copy | `fight-insights.js?v=8`: "books lean the other way" now fires only when the books favour the opponent (it used to fire only when they were *more* sure of our pick); a new flag for the model ten or more points above the market; "Jr." is no longer a surname |

### The reconciliation, in one paragraph

`main` at `194e1e9` was live and no PR was open. The week's unmerged work was
three branches: the owner's `fight-week-v2` and `revenue/trust-funnel-v1`
(both 2026-09-15, both >120 commits behind `main`) and an unapproved email
modal. D-010 carried the approved *direction* and the approved *wording* from
`fight-week-v2` — event-first hero, "model vs market", the sportsbooks-only
market view it added to the database on the 15th, its 5/10-point bands — into
the current `index.html` rather than merging 128 files during a live card. The
rest is T-033 to T-035, each with its reason. No Codex changes were found on
any branch or in the working tree.

### Verified

Every Node suite and all 624 Python tests green, including the new
`tests/model-vs-market.test.js` (14 assertions). Rendered in headless Chromium
against the real UFC 331 rows: 12 active fights, the retired Moicano–Ortega
booking dropped, every market cell present, Tuivasa's 34-point gap first under
Disagreement, no overflow at 390 px, no console errors. The agent environment
cannot reach cannonfightlab.com or Supabase directly, so the served bytes and
the rendered live page are checked by the new `Verify live site` workflow.

### Held to scope

No model, threshold, schedule, snapshot, ledger or schema change. `build/` is
untouched. The `odds.yml` capture and the immutability plan (T-031) are exactly
where the previous entry left them.

## Next action

**Owner:** two calls. (1) **T-035** — the email modal, yes or no. (2) The
order of **T-033** and **T-034**: the Event Hub / Market Board work is the
larger product step and the claims manifest is the thing it must not
reintroduce.

**ChatGPT:** the claim worth attacking is that "N pts · CFL higher" is a
disagreement and not an edge percentage under `CLAUDE.md` line 1. The defence
is that it is the arithmetic between two numbers already on screen, neutral in
colour and sign, never called an edge, and carrying a flag against the model
from ten points up. If a reader would still take "34 pts · CFL higher" as a
reason to bet, the third cell should lose the number, as the 2026-09-18 draft
proposed, and only the label should stay.

---

## 2026-09-19 — UFC 331: the first card captured under the CLV capture path

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-19

Launch-day activation for UFC 331 (event 4433, first bout 21:00 UTC). Recorded
as [D-009](DECISIONS.md), which is the approval — see the correction below.

### The finding, and it is the whole entry

**On a card day, the odds job had captured nothing.** Every cadence tier in
`build/fetch-odds.js` gated on where the wall clock sat —
`min % cadence < WAKE_INTERVAL_MIN`. That is a cadence only if the `*/5` cron
fires every five minutes; GitHub throttles it to a handful of deliveries a day
at arbitrary minutes. The four real wakes on the 19th were **:43, :30, :35,
:35** — not one inside minutes 0–4, so the gate never opened. The only UFC 331
moneyline rows on file that morning came from the Polymarket writer, which
CLV-001 excludes by kind, and the freshest *sportsbook* line was **28 hours**
old against a frozen 45-minute staleness limit.

The gate now measures **elapsed time since our own last capture**, scoped to
rows carrying `feed_version` so the other two writers cannot suppress our
cadence, and falls back to the phase test whenever that is unreadable — so a
missing ledger degrades to the old behaviour, never to "capture every wake".
Seven tests, two mutation-checked, one replaying the four real wakes. Same
throttled wakes against tonight's card: **10 captures, against 1**.

### What is now live

| | |
|---|---|
| `fight_odds` capture columns | **applied** — all 110,980 existing rows NULL, nothing backfilled |
| `fights.is_active` / `bout_order` | **applied** — `_shared.js` had been reading both for months |
| first CLV-eligible capture | 15:49 UTC, 142 rows, 6 books, **118 with the full §4 set** |
| UFC 331 card | 12 active, 1 retired, evidence preserved |

No CLV figure computed, none published, publication gate untouched at 0/100 and
0/20.

### The premise that was wrong

The instruction said *"the approved migrations"*. **None of the five had an
approval on record** — `DECISIONS.md` ended at D-008, and D-004 says the
immutability migration is still the owner's to apply. D-009 is therefore not a
citation of an earlier approval, it *is* the approval, and it is scoped to the
two additive files rather than to all five.

### Held back, against the instruction, and why

Three migrations and two activations. The reasons are engineering, not process:

1. **Immutability** — adds triggers to `fight_odds` while another repository
   writes to it, during a live card. Its own filing says apply it between cards.
2. **Event flow** — creates `odds_api_usage` **empty**, which reads as *"0 spent,
   500 remaining"*. That is false, and the governor would take its finest rung on
   it. Overspending the free allowance is paid usage, L3 under gate #6. **T-029.**
3. **`clv001_columns`** — stores a result nothing can compute yet. Its header
   says apply last.
4. **The Event Flow schedule** — `REAL_PAGE_CHECK.json` does not exist and
   `--execute` refuses without it. UFCStats returns **403** to this environment,
   so it cannot be produced from here. **T-030.**
5. **CLV write mode** — changes nothing tonight. The gate is a sample floor and
   it is at 0.

## Next action

**Owner:** two calls, neither urgent tonight.

1. **T-031** — the immutability migration, once the card is over. It is the last
   structural piece and D-004 already assigns it to you.
2. Whether holding items 1–5 above was the right read. If you want the Event
   Flow schedule on, **T-030** needs somebody on a residential connection to
   fetch one UFCStats page; it is not a decision, it is an IP block.

**ChatGPT:** the claim worth attacking is the cadence fix. It changes when
credits are spent, and the argument that it cannot spend faster than the ladder
already permits rests on `dueSinceLastCapture` returning `null` — not `false` —
on every unreadable path. If there is a path where an unreadable last capture
reads as "due", the credit ceiling has a hole in it and the test asserting
elapsed ≤ phase + 1 is measuring the wrong thing.

---
