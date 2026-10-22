# MKT-002 pilot — results

**2026-10-22. Prices only; no fight result read; the hypothesis was not
tested.** Plan: [`PILOT_PLAN.md`](PILOT_PLAN.md) (committed `6d876a1b`,
amended `8e0dcdd4` before any read). Numbers:
[`pilot/pilot_results.json`](pilot/pilot_results.json). The two reads'
outputs are kept outside the repository (D-034); read 2's local copy matched
the md5 the database computed (`5981cc52…`).

## Plain verdict

**The data cannot support the outlier test yet, and the reason is when prices
are captured, not how many books there are.** In the last day before a fight,
CFL's capture job ran about every 3.4 hours (median), not hourly as designed,
so a fresh closing price — the yardstick the test needs — existed for only
**3 of the 12 bouts** on the one card that has finished since 12 October.

**Second finding: the books mostly agree.** Three hours out, a typical book
sat half a point from the others; only 1 quote in 113 was 3 or more points out
of line. Out-of-line prices big enough to matter are rare, so the test needs
many cards even with perfect capture.

**Recommendation:** do not freeze MKT-002 yet. Freezing a test that cannot
reach its sample size spends nothing useful. Fix the capture timing first
(an owner decision, below), then re-run this pilot on two or three new cards
and freeze.

## What the reads found

**Scope.** Cards dated 2026-10-12 onward: 4 cards, 32 bouts with any
sportsbook quote, 3,602 capture rows (one per book per capture). Only the
**17 October card** (12 bouts) has finished, so it is the only one whose
anchor times have passed; the other three cards' bouts count as "0 fresh
books" below because their anchors are still in the future.

**Quality** (a row is dropped by the first rule it fails):

| rule | rows |
|---|---|
| kept | 3,096 |
| one side missing | 489 |
| captured after the start | 13 |
| not the provenance feed | 4 |
| live, market not open, beyond 100-to-1, inactive bout | 0 |

Every start time came from the provider's commence time (no date fallback).

**Fresh prices on the 17 October card (12 bouts, 7 books):**

| anchor | bouts with ≥ 4 fresh books | typical age of the price |
|---|---|---|
| T−24h (≤ 120 min old) | 8 of 12 (all with 6) | 66 min |
| T−3h (≤ 120 min old) | 11 of 12 (10 with 6, 1 with 5) | 46 min |
| close (≤ 45 min old, CLV-001's frozen limit) | **3 of 12** | 39 min |

**Capture timing in the final 24 hours** (minutes between consecutive clean
captures of the same book and bout, all cards): p10 **127**, median **204**,
p90 **263**. `odds.yml` asks GitHub for a wake every 5 minutes and the
cadence gate asks for hourly captures on card day; GitHub's throttling of
frequent schedules (documented in CLAUDE.md since 2026-09-19) is the likely
reason the realised interval is three to four times longer.

**How far each book sits from the others** (power de-vig, distance from the
median of the other books, bouts with ≥ 4 fresh books):

| anchor | quotes | median | 90th pct | 95th pct | ≥ 2 pts | ≥ 3 pts |
|---|---|---|---|---|---|---|
| T−24h | 48 | 0.6 pts | 1.6 pts | 2.0 pts | 3 | 1 |
| T−3h | 65 | 0.5 pts | 1.4 pts | 2.0 pts | 4 | 0 |

**Spread of `CLV_return`, all quotes pooled** (never split by outlier status;
its mean was not computed): T−3h SD 0.012 over 22 quote-sides; T−24h SD 0.117
over 24, inflated by one long-shot bout. Both rest on one card and only three
closing prices, so neither can fix a sample size.

## What this means for the design

1. **The closing yardstick is the binding constraint.** Under the frozen
   45-minute limit, about 1 bout in 4 gets a close. Loosening it to the
   realised capture interval (3–4 hours) would let a stale price stand in for
   the close and weaken what "beat the close" means; that is a change to how
   CLV is measured, not a tuning choice.
2. **Outliers are rare at δ = 3 points.** At about 1 qualifying quote per
   card, and with closes for a quarter of bouts, a test powered for a +0.01
   mean `CLV_return` would need hundreds of cards — years. At δ = 2 points,
   roughly 3–4 quotes per card qualify, which is still slow.
3. **What would make it feasible:** captures every 15–30 minutes in the last
   three hours before each bout, so most bouts get a fresh close and a T−30m
   anchor. That is a change to how the existing odds job is triggered — no
   new scraper, but possibly more Odds API credits — so it is the owner's
   decision (CRITICAL_GATES items 5–6). It also matters beyond MKT-002:
   CLV-001's own scoring needs a fresh close.

## Owner decisions this raises

- **Capture timing on fight day.** Options, without a new scraper:
  (a) trigger the existing odds job from a scheduler GitHub does not throttle
  (the outside-observer idea, T-076, deferred under D-033);
  (b) accept the current cadence and redesign MKT-002 around T−24h and T−3h
  only, measuring movement between them rather than against the close
  (weaker, and closer to MKT-003);
  (c) wait: keep collecting and re-run this pilot after more cards.
- **Credits.** Any denser schedule must first be priced against the
  provider's remaining credits; spending more is item 6.

Until one of these is decided, MKT-002 stays a draft and no observation is
evaluated.
