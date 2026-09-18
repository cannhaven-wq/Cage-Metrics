# FE-001 — Do Record, Takedown Defence and Age survive market control?

**Dated 2026-09-18. Read-only investigation. Nothing in production changed.**

This is a research artifact, not a user-facing surface. It changes no copy, no
page, no threshold and no engine. It answers one question about three factors
and reports the answer as it came out.

---

## Plain verdict first

We took the three factor claims that are currently published — Record, Takedown
Defence and the retired Age heuristic — and tested each one against the fights
where the betting market called it a coin flip. That is the only test that
separates "this factor knows something" from "this factor is repeating the
favourite".

| Factor | Supported after market control? | One sentence |
|---|---|---|
| **Record** | **No.** | On evenly-priced fights the better-recorded fighter wins **50.2%** of the time — a coin flip — even though the published 60% and 65% tiers reproduce almost exactly when you *don't* control for the market. |
| **Takedown Defence** | **No.** | Every band lands between 48.6% and 52.2% on evenly-priced fights and no interval clears 50; the top band, the one claiming 56%, has the *lowest* point estimate of the three. |
| **Age** | **Yes, partly.** | The younger fighter wins **56.8%** of evenly-priced fights (1,018 of them) and the interval clears 50; the 3–4 year and 7–9 year bands clear it individually, and the 10+ year tier claiming 65.2% has too few evenly-priced fights to test at all. |

The sharpest single result: **Record's published tiers are almost exactly right
on uncontrolled data and almost exactly worthless on controlled data.** The
60.0% tier measures 59.8% raw and 49.9% market-even. The 65.0% tier measures
64.9% raw and 47.6% market-even. A factor whose calibration is that good raw and
that dead controlled is a factor that was fit to the betting line.

---

## What was tested, exactly

### Record — `edges.js :: recordEdge` (edges.js:164)

```
aTotal = a.wins + a.losses           (PROFESSIONAL record, not UFC-only)
bTotal = b.wins + b.losses
fires only if aTotal + bTotal >= 3
aRate  = (a.wins + 2) / (aTotal + 4) (Laplace smoothing)
bRate  = (b.wins + 2) / (bTotal + 4)
gap    = |aRate - bRate|
fires only if gap >= 0.08
gap >= 0.40 -> 72.0%    gap >= 0.25 -> 70.0%
gap >= 0.15 -> 65.0%    otherwise   -> 60.0%
favours the higher aRate/bRate
```

Published as "60–72%" in the `edges.html` factor table, triggered on an
"adjusted win-rate gap of at least 8 percentage points".

### Takedown Defence — `edges.js :: tdDefEdge` (edges.js:191)

```
fires only if a.td_def and b.td_def are both non-null
fires only if willHaveWrestling(a, b):
    a.td_avg >= 1.0 OR b.td_avg >= 1.0   (STYLE_THRESHOLDS.TD_LOW)
gap = |a.td_def - b.td_def|              (percentage points)
fires only if gap >= 10
gap >= 30 -> 56.0%    gap >= 20 -> 54.0%    otherwise -> 52.5%
favours the higher td_def
```

Published as "52–56%" in the `edges.html` factor table, triggered on a "10+
percentage-point gap in takedown defense, when grappling is in play".

### Age — retired, reconstructed (see the mismatch section)

The `ageEdge` function is **not in `edges.js` today and is not recoverable from
this clone's history** — the clone is shallow and `git log -S ageEdge` across
all refs returns nothing. The definition tested here was reconstructed from two
surviving artifacts:

* [`research/results.md`](../results.md) — the bands, the assigned percentages
  and the newcomer discounts;
* [`edges.html`](../../edges.html) — the trigger ("1+ year age gap.
  Newcomer-discounted at gap < 9 when either fighter has <5 UFC fights"), the
  published range ("52–70%") and the recalibration narrative.

```
gap = |age_a - age_b| in years, at the date of the fight
fires only if gap >= 1
1-2 yrs -> 52.0%   3-4 yrs -> 55.9%   5-6 yrs -> 58.2%
7-9 yrs -> 63.3%   10+ yrs -> 65.2%
newcomer discount (gap < 9, either fighter under 5 UFC fights):
1-2 -> 51.0%   3-4 -> 53.0%   5-6 -> 54.1%   7-9 -> 56.7%
favours the younger fighter
```

The 10+ tier is reported both as one band and split into 10–11 / 12+, because
the recalibration narrative in `edges.html` implies a six-band shipped version.
See the mismatch section — the shipped percentages are genuinely ambiguous.

---

## Method

Reused, not reinvented. The benchmark, the point-in-time discipline, the Wilson
intervals and the verdict ladder are all
[`build/factor-rates.js`](../../build/factor-rates.js) as it stands today. What
this artifact adds is a second set of *factor definitions* — the ones the
product actually ships — scored through that same machinery.

* **Point-in-time.** Every per-fighter statistic is a window aggregate over that
  fighter's strictly prior fights, ordered by event date then fight id. No
  career-aggregate column that contains the fight being scored is read, with one
  labelled exception (variant C below, which exists to show what production's
  capability gate does).
* **Market control.** A fight is "market-even" when both fighters closed inside
  ±140 American (`EVEN_BAND = 140`), taking the median closing price across
  books per fighter.
* **Intervals.** Wilson score, z = 1.96 — the same function, same constant.
* **Verdicts.** The same ladder: `real` (even interval clears 50), `inverted`
  (below 50), `lean` (straddles 50 but the rate is ≥ `LEAN_PCT` = 55), `proxy`
  (straddles 50 below that), `unproven` (fewer than `MIN_SAMPLE` = 100
  market-even fights), `insufficient` (under the floor overall).
* **"Claim supported?"** is a separate, stricter column: does the market-even
  95% interval *contain* the percentage `edges.js` assigns? A claim above the
  interval's upper bound is contradicted. A band with fewer than 100 market-even
  fights is reported as untestable rather than contradicted, however far the
  point estimate sits — a 13-fight cohort refutes nothing.
* **No threshold was moved after seeing a result.** Every band edge in this
  report is copied from the shipped code or the surviving artifact. Where a
  band fails, it is reported as failing.

Query: [`factor_evidence_2026-09-18.sql`](factor_evidence_2026-09-18.sql). It
SELECTs only.

**Dataset.** 8,739 scored fights, 1994-03-11 to 2026-09-12. **1,220** of them
market-even (14.0%).

### Harness validation

Before believing any of the above, the harness reproduces the three published
Factor Lab factors. The raw cohort matches
[`factor-rates.json`](../../factor-rates.json) (generated 2026-09-18T15:30:30Z)
exactly on age — 2,546 / 2,212 / 1,649 / 1,432 / 773, headline 8,612, every win
rate identical to the published tenth — and to within three fights on takedown
defence and thirteen on UFC record. Those small gaps are floating-point at band
edges: a raw win-rate gap of exactly 0.10 is `0.10000000000000009` in JavaScript
and exactly `0.1` in Postgres `numeric`, and the band test is a strict
inequality. They move individual fights between adjacent bands and change no
conclusion.

The **market-even** cohort does not match, and that is a finding in its own
right — see the discrepancy section at the end.

---

## Results

`all` = every fight the factor fires on. `even` = the market-even subset.
Claim = the percentage `edges.js` assigns to that band.

### Record — `edges.js` recordEdge, point-in-time professional record

| Band | edges.js claim | n (all) | win% (all) | 95% CI (all) | n (even) | win% (even) | 95% CI (even) | clears 50%? | Factor Lab verdict | claim supported? |
|---|---|---|---|---|---|---|---|---|---|---|
| gap 0.08-0.15 | 60.0 | 2557 | 59.8% | [57.9, 61.7] | 339 | 49.9% | [44.6, 55.1] | no | proxy | **CONTRADICTED** (claim above interval) |
| gap 0.15-0.25 | 65.0 | 1087 | 64.9% | [62.0, 67.6] | 105 | 47.6% | [38.3, 57.1] | no | proxy | **CONTRADICTED** (claim above interval) |
| gap 0.25-0.40 | 70.0 | 177 | 74.0% | [67.1, 79.9] | 20 | 70.0% | [48.1, 85.5] | no | unproven | untestable (even n<100) |
| gap >= 0.40 | 72.0 | 9 | 100.0% | [70.1, 100.0] | 0 | — | — | n/a | insufficient | untestable (no market-even fights) |
| ANY (fires) | — | 3830 | 62.0% | [60.4, 63.5] | 464 | 50.2% | [45.7, 54.7] | no | proxy | — |

### Takedown Defence — `edges.js` tdDefEdge, three gate variants

**B — point-in-time wrestling gate** (the honest analogue of `willHaveWrestling`)

| Band | edges.js claim | n (all) | win% (all) | 95% CI (all) | n (even) | win% (even) | 95% CI (even) | clears 50%? | Factor Lab verdict | claim supported? |
|---|---|---|---|---|---|---|---|---|---|---|
| gap 10-20 | 52.5 | 1004 | 52.9% | [49.8, 56.0] | 164 | 50.6% | [43.0, 58.2] | no | proxy | not contradicted (interval contains claim) |
| gap 20-30 | 54.0 | 706 | 55.4% | [51.7, 59.0] | 115 | 52.2% | [43.1, 61.1] | no | proxy | not contradicted (interval contains claim) |
| gap >= 30 | 56.0 | 823 | 55.7% | [52.2, 59.0] | 139 | 48.9% | [40.8, 57.1] | no | proxy | not contradicted (interval contains claim) |
| ANY (fires) | — | 2533 | 54.5% | [52.5, 56.4] | 418 | 50.5% | [45.7, 55.2] | no | proxy | — |

**C — career `td_avg` gate** (what production literally reads)

| Band | edges.js claim | n (all) | win% (all) | 95% CI (all) | n (even) | win% (even) | 95% CI (even) | clears 50%? | Factor Lab verdict | claim supported? |
|---|---|---|---|---|---|---|---|---|---|---|
| gap 10-20 | 52.5 | 856 | 52.7% | [49.3, 56.0] | 136 | 50.7% | [42.4, 59.0] | no | proxy | not contradicted (interval contains claim) |
| gap 20-30 | 54.0 | 609 | 55.2% | [51.2, 59.1] | 100 | 50.0% | [40.4, 59.6] | no | proxy | not contradicted (interval contains claim) |
| gap >= 30 | 56.0 | 713 | 55.1% | [51.5, 58.7] | 118 | 50.8% | [41.9, 59.7] | no | proxy | not contradicted (interval contains claim) |
| ANY (fires) | — | 2178 | 54.2% | [52.1, 56.3] | 354 | 50.6% | [45.4, 55.7] | no | proxy | — |

**D — no gate at all** (isolates what the gate is worth)

| Band | edges.js claim | n (all) | win% (all) | 95% CI (all) | n (even) | win% (even) | 95% CI (even) | clears 50%? | Factor Lab verdict | claim supported? |
|---|---|---|---|---|---|---|---|---|---|---|
| gap 10-20 | 52.5 | 1034 | 53.1% | [50.0, 56.1] | 167 | 50.9% | [43.4, 58.4] | no | proxy | not contradicted (interval contains claim) |
| gap 20-30 | 54.0 | 734 | 55.9% | [52.2, 59.4] | 120 | 50.8% | [42.0, 59.6] | no | proxy | not contradicted (interval contains claim) |
| gap >= 30 | 56.0 | 854 | 56.0% | [52.6, 59.3] | 144 | 48.6% | [40.6, 56.7] | no | proxy | not contradicted (interval contains claim) |
| ANY (fires) | — | 2622 | 54.8% | [52.9, 56.7] | 431 | 50.1% | [45.4, 54.8] | no | proxy | — |

The wrestling gate is worth nothing measurable. It removes about 3% of firings
and moves every market-even rate by less than a point. Whatever else is true of
this factor, gating it on "does anybody here shoot?" is not what is holding it
up.

### Age — retired heuristic's bands, whole population

| Band | edges.js claim | n (all) | win% (all) | 95% CI (all) | n (even) | win% (even) | 95% CI (even) | clears 50%? | Factor Lab verdict | claim supported? |
|---|---|---|---|---|---|---|---|---|---|---|
| 1-2 yrs | 52.0 | 2475 | 53.6% | [51.6, 55.6] | 357 | 55.2% | [50.0, 60.3] | no | lean | not contradicted (interval contains claim) |
| 3-4 yrs | 55.9 | 1863 | 56.5% | [54.3, 58.8] | 275 | 57.5% | [51.5, 63.2] | **yes** | **real** | not contradicted (interval contains claim) |
| 5-6 yrs | 58.2 | 1383 | 58.9% | [56.3, 61.5] | 197 | 56.3% | [49.4, 63.1] | no | lean | not contradicted (interval contains claim) |
| 7-9 yrs | 63.3 | 1084 | 63.7% | [60.8, 66.6] | 142 | 60.6% | [52.3, 68.2] | **yes** | **real** | not contradicted (interval contains claim) |
| 10-11 yrs | 65.2 | 291 | 67.7% | [62.1, 72.8] | 31 | 54.8% | [37.8, 70.8] | no | unproven | untestable (even n<100) |
| 12+ yrs | 65.2 | 212 | 71.7% | [65.3, 77.3] | 16 | 56.2% | [33.2, 76.9] | no | unproven | untestable (even n<100) |
| 10+ yrs (single band) | 65.2 | 503 | 69.4% | [65.2, 73.3] | 47 | 55.3% | [41.2, 68.6] | no | unproven | untestable (even n<100) |
| ANY (fires) | — | 7308 | 58.0% | [56.8, 59.1] | 1018 | 56.8% | [53.7, 59.8] | **yes** | **real** | — |

### Age — veterans only (both fighters with 5+ prior UFC fights)

| Band | edges.js claim | n (all) | win% (all) | 95% CI (all) | n (even) | win% (even) | 95% CI (even) | clears 50%? | Factor Lab verdict | claim supported? |
|---|---|---|---|---|---|---|---|---|---|---|
| 1-2 yrs | 52.0 | 731 | 52.8% | [49.2, 56.4] | 120 | 55.8% | [46.9, 64.4] | no | lean | not contradicted (interval contains claim) |
| 3-4 yrs | 55.9 | 539 | 56.8% | [52.6, 60.9] | 84 | 59.5% | [48.8, 69.4] | no | unproven | untestable (even n<100) |
| 5-6 yrs | 58.2 | 427 | 62.5% | [57.8, 67.0] | 62 | 58.1% | [45.7, 69.5] | no | unproven | untestable (even n<100) |
| 7-9 yrs | 63.3 | 314 | 68.8% | [63.5, 73.7] | 40 | 70.0% | [54.6, 81.9] | yes | unproven | untestable (even n<100) |
| 10-11 yrs | 65.2 | 83 | 68.7% | [58.1, 77.6] | 9 | 33.3% | [12.1, 64.6] | no | insufficient | untestable (even n<100) |
| 12+ yrs | 65.2 | 52 | 76.9% | [63.9, 86.3] | 4 | 50.0% | [15.0, 85.0] | no | insufficient | untestable (even n<100) |
| 10+ yrs (single band) | 65.2 | 135 | 71.9% | [63.7, 78.8] | 13 | 38.5% | [17.7, 64.5] | no | unproven | untestable (even n<100) |
| ANY (fires) | — | 2146 | 59.3% | [57.2, 61.3] | 319 | 58.3% | [52.8, 63.6] | **yes** | **real** | — |

The "veterans are the cleaner signal" claim in `edges.html` holds only on the
headline: 58.3% market-even for veterans against 56.1% for newcomers, with
overlapping intervals. Splitting the cohort costs so much sample that no
individual veteran band is testable under market control.

### Age — newcomer cohort (at least one fighter under 5 prior UFC fights)

Claims here are the **discounted** ones.

| Band | edges.js claim | n (all) | win% (all) | 95% CI (all) | n (even) | win% (even) | 95% CI (even) | clears 50%? | Factor Lab verdict | claim supported? |
|---|---|---|---|---|---|---|---|---|---|---|
| 1-2 yrs | 51.0 | 1744 | 54.0% | [51.6, 56.3] | 237 | 54.9% | [48.5, 61.1] | no | proxy | not contradicted (interval contains claim) |
| 3-4 yrs | 53.0 | 1324 | 56.4% | [53.7, 59.1] | 191 | 56.5% | [49.5, 63.4] | no | lean | not contradicted (interval contains claim) |
| 5-6 yrs | 54.1 | 956 | 57.3% | [54.2, 60.4] | 135 | 55.6% | [47.1, 63.7] | no | lean | not contradicted (interval contains claim) |
| 7-9 yrs | 56.7 | 770 | 61.7% | [58.2, 65.1] | 102 | 56.9% | [47.2, 66.1] | no | lean | not contradicted (interval contains claim) |
| 10-11 yrs | 65.2 | 208 | 67.3% | [60.7, 73.3] | 22 | 63.6% | [43.0, 80.3] | no | unproven | untestable (even n<100) |
| 12+ yrs | 65.2 | 160 | 70.0% | [62.5, 76.6] | 12 | 58.3% | [32.0, 80.7] | no | unproven | untestable (even n<100) |
| 10+ yrs (single band) | 65.2 | 368 | 68.5% | [63.6, 73.0] | 34 | 61.8% | [45.0, 76.1] | no | unproven | untestable (even n<100) |
| ANY (fires) | — | 5162 | 57.4% | [56.0, 58.7] | 699 | 56.1% | [52.4, 59.7] | **yes** | **real** | — |

Every newcomer band comes in **above** its discounted assignment on market-even
fights (54.9 vs 51.0, 56.5 vs 53.0, 55.6 vs 54.1, 56.9 vs 56.7). None is
contradicted — the intervals are wide enough to contain both the discounted and
the undiscounted number — but nothing in this data argues *for* the discount
either. It was fit to raw rates, and the raw newcomer/veteran split is smaller
than the discount it produced.

### Factor Lab replications (harness validation)

| Factor | Band | n (all) | win% (all) | n (even) | win% (even) | 95% CI (even) | verdict |
|---|---|---|---|---|---|---|---|
| UFC record | 10-15 pts | 434 | 58.8% | 73 | 56.2% | [44.8, 67.0] | unproven |
| UFC record | 15-22 pts | 422 | 62.8% | 60 | 66.7% | [54.1, 77.3] | unproven |
| UFC record | 22-30 pts | 291 | 62.9% | 32 | 50.0% | [33.6, 66.4] | unproven |
| UFC record | 30+ pts | 187 | 70.6% | 19 | 52.6% | [31.7, 72.7] | unproven |
| UFC record | ANY | 1334 | 62.6% | 184 | 58.2% | [50.9, 65.0] | real |
| TD defence | 10-20 pts | 1041 | 53.5% | 168 | 50.6% | [43.1, 58.1] | proxy |
| TD defence | 20-30 pts | 722 | 55.4% | 121 | 51.2% | [42.4, 60.0] | proxy |
| TD defence | 30+ pts | 838 | 56.0% | 141 | 48.9% | [40.8, 57.1] | proxy |
| TD defence | ANY | 2601 | 54.8% | 430 | 50.2% | [45.5, 54.9] | proxy |
| Age | 1-2 yrs | 2546 | 52.2% | 369 | 52.3% | [47.2, 57.3] | proxy |
| Age | 3-4 yrs | 2212 | 56.6% | 331 | 58.9% | [53.5, 64.1] | real |
| Age | 5-6 yrs | 1649 | 56.2% | 229 | 59.4% | [52.9, 65.5] | real |
| Age | 7-9 yrs | 1432 | 61.7% | 201 | 56.7% | [49.8, 63.4] | lean |
| Age | 10+ yrs | 773 | 67.8% | 89 | 57.3% | [46.9, 67.1] | unproven |
| Age | ANY | 8612 | 57.1% | 1219 | 56.5% | [53.7, 59.3] | real |

---

## Where the machinery cannot reproduce the product's definition

Reported rather than silently approximated, per the brief.

### 1. Record is professional, the Factor Lab's is UFC-only — neither is the other

`recordEdge` reads `fighters.wins` and `fighters.losses`, which are **full
professional** records including regional fights. The Factor Lab's `ufc_record`
factor is **UFC-only**, raw, with a five-prior-fight floor per side. They are
different factors that happen to share a name in conversation, and the Factor
Lab has never tested the one the product ships.

The reconstruction used here is: *professional record before a fight = the
career total as scraped today, minus the UFC results in our database that came
after that fight*. At a fighter's UFC debut this leaves their pre-UFC regional
record, which is what we want. It cannot see:

* **non-UFC bouts fought between UFC appearances.** Those are folded into the
  pre-UFC baseline, so a fighter's reconstructed record is slightly too good
  early in their UFC run and exactly right by the end. Rare in the modern era,
  common in the 1990s and 2000s.
* **imperfect UFC coverage.** `fighters.ufc_wins` disagrees with the count of
  that fighter's UFC wins in our `fights` table for 1,648 of 2,761 fighters
  (662 by two or more). The reconstruction does not read `ufc_wins`, so the
  disagreement does not enter the arithmetic directly — but it means some real
  post-fight results are not being subtracted, in the same direction as above.
* **scrape-time drift.** `fighters.wins` is a snapshot; a fighter whose row is
  stale carries a stale anchor.
* 11 fighters have a career loss count lower than their database loss count.
  Those are clamped to zero rather than allowed to go negative.

**This is a limitation of the backtest, not of production.** In production
`recordEdge` reads the `fighters` row as it stands *before* the card, which is
genuinely point-in-time. The published percentages are what is being tested
here, not the factor's leakage.

### 2. Takedown defence has no minimum-exposure floor in production

`tdDefEdge` fires on any non-null `a.td_def` / `b.td_def`. The UFC's own
`td_def` figure is a career aggregate, integer-rounded, over an unknown
denominator — a fighter who has faced one takedown attempt and stuffed it reads
100%, and a 10-point gap against them fires the factor. This backtest imposes
the Factor Lab's `MIN_TD_ATTEMPTS = 5` floor because the point-in-time
reconstruction needs one to mean anything.

**So the cohort tested here is cleaner than the cohort production fires on.**
The real production population includes low-exposure fighters this test excludes,
and there is no reason to expect them to do better.

Two further gaps: the reconstruction computes takedown defence from
`fights.a_td_attempted` / `b_td_landed`, which is UFC-only and will not match
the UFC's published percentage fighter-for-fighter; and `willHaveWrestling` is
gated on career `td_avg`, so variant B substitutes a point-in-time attempts-per-
15-minutes twin while variant C uses the career field as shipped. Both are
reported; they agree.

### 3. The age function's shipped percentages are genuinely ambiguous

`ageEdge` is gone from the code and unrecoverable from this clone. The two
surviving records **disagree about which tiers shipped**:

* [`research/results.md`](../results.md) lists the assignments as
  52.0 / 55.9 / 58.2 / 63.3 / 65.2, with newcomer discounts to
  51.0 / 53.0 / 54.1 / 56.7.
* [`edges.html`](../../edges.html) presents those same five numbers as what the
  model "said" *before* a recalibration, then states that "we shipped new tiers
  that match the measured rates" — implying roughly
  52 / 59 / 57 / 64 / 62 / 70 across six bands, and its published range of
  "52–70%" matches the recalibrated set, not the original one.

**This report tests the `results.md` set** and reports the 10+ tier both whole
and split 10–11 / 12+ so the recalibrated shape can be read off the same table.
Where a conclusion would differ between the two sets it is flagged; in practice
none does, because every band where they differ materially is untestable for
sample-size reasons.

One further deviation: the newcomer split uses **point-in-time** prior UFC
fights. `research/validate.js` used the career `ufc_wins + ufc_losses` columns,
which contain the fight being scored. The point-in-time version is the faithful
analogue of what production would do on an upcoming card.

### 4. Band-edge convention

`edges.js` bands are half-open upward (`gap >= 10` puts an exact 10 in the
bottom band); `build/factor-rates.js` bands are `(lo, hi]` (an exact 10 is
excluded entirely). Each is scored with its own convention. The difference moves
single-digit numbers of fights and no verdict.

---

## Sample-size limitations

These bound every conclusion above and are the reason three of the four
"unsupported" answers are *not proven wrong* so much as *not testable*.

1. **The market-even cohort is 1,220 fights out of 8,739 — 14.0%.** Market
   control costs seven eighths of the data. Everything downstream inherits that.
2. **Record's two strongest tiers are effectively untestable.** The 70% tier
   fires on 177 fights and only 20 are market-even. The 72% tier fires on **9
   fights in the entire 32-year history** and **zero** are market-even. A tier
   that fires on 0.1% of fights and has never once fired on an evenly-priced
   fight cannot be validated and barely matters to the verdict.
3. **Age's 10+ tier is untestable.** 47 market-even fights whole, 13 for
   veterans, 34 for newcomers. Its raw rate (69.4%) is the highest number in the
   report and its market-even rate (55.3%) is fifteen points lower, which is
   suggestive of a market-reading tier — but suggestive is all it is at n=47.
4. **Every veteran/newcomer band is below the 100-fight floor** except newcomer
   1–2, 3–4, 5–6 and 7–9. The cohort split is not affordable at this sample.
5. **Takedown defence's bands straddle 50 with intervals 15–18 points wide.**
   "Not contradicted" there means the interval is too wide to contradict
   anything, not that the claim is holding up. All three claims sit inside their
   intervals *and* all three point estimates sit at or below 51.
6. **Odds coverage is one book per side for 99.2% of fights.** The "median
   across books" is a median of one. `EVEN_BAND` is therefore sensitive to which
   book happened to be captured.
7. **The market-even flag uses `is_closer`, not the CLV-001 closing-price
   proxy.** The two are not the same benchmark and this report does not claim
   they are; nothing here is a CLV figure and nothing here is publishable under
   [`research/clv/CLV_MEASUREMENT_PROTOCOL.md`](../clv/CLV_MEASUREMENT_PROTOCOL.md).

---

## A discrepancy found on the way: the published market-even cohort is ~30% short

`factor-rates.json`, generated 2026-09-18T15:30:30Z, records
`market_even_cohort: 869`. Querying the same database directly, with the same
±140 band and the same median-of-books rule, gives **1,220**. The raw (non-even)
cohort matches the published figures exactly, so the gap is confined to the odds
join.

It is not staleness: restricting to events on or before 2026-09-12 (the
generated file's own `last_event`) still gives 1,220, so the rows were present
when the build ran.

**Most likely cause, stated as a hypothesis and not as a finding:**
`build/factor-rates.js::fetchAll` pages with `.range()` and **no `ORDER BY`**.
For `events`, `fights` and `fighters` that is harmless — small tables, few
pages, and the published numbers match exactly. For `fight_odds` it is sixteen
separate HTTP requests of `LIMIT 1000 OFFSET n` against a 110,936-row table
filtered to 15,786, and Postgres guarantees no stable row order across separate
statements. Under a parallel scan that silently drops and duplicates rows.

This could not be tested from this session — the network policy blocks the
Supabase REST endpoint, and `fight_odds` has no `anon` SELECT policy in any
case, so `build/factor-rates.js` cannot be run here. Paging is consistent
*within* a single statement, which does not settle the multi-request case.

**Consequence if the hypothesis is right:** every market-even figure currently on
`stats.html` is computed on about 70% of the fights that qualify, and published
verdicts move in both directions on the full cohort. Replicating the three live
Factor Lab factors on 1,220 market-even fights instead of 869: the UFC-record
headline goes from `lean` to **`real`** (58.2% on 184 fights, against 55.1% on
136 published); the age 7–9 band goes from `real` to **`lean`** (56.7% on 201,
against 58.9% on 151); the takedown-defence 20–30 band goes from `unproven` to
`proxy` (121 fights, against 84). Every band gains roughly 30–40% more sample —
age 5–6 reads 229 market-even fights here against 157 published. The numbers in
this report use the full 1,220 and therefore will not line up with the live page
until this is settled.

---

## Answers

**Is Record supported after controlling for the market?** No. Market-even, the
factor is 50.2% across all firings [45.7, 54.7]. The 60% tier measures 49.9%
and the 65% tier 47.6%; both claims sit above their intervals and are
contradicted. The 70% and 72% tiers cannot be tested. That the raw rates
(59.8%, 64.9%) reproduce the published tiers to within a point is the tell: the
tiers describe the market, not the fight.

**Is Takedown Defence supported?** No. Every band sits between 48.6% and 52.2%
market-even and no interval clears 50; the 56% tier has the lowest point
estimate of the three. No claim is statistically contradicted, because the
intervals are 15–18 points wide, but nothing supports one either. The wrestling
gate changes nothing measurable. The Factor Lab's existing `proxy` verdict is
confirmed on the product's own definition.

**Is Age supported?** Partly, and it is the only one of the three that is. The
younger fighter wins 56.8% of 1,018 market-even fights, interval [53.7, 59.8],
clearing 50. The 3–4 year band (57.5%) and the 7–9 year band (60.6%) clear it
individually and their assigned percentages sit inside their intervals. The 1–2
and 5–6 bands are above 55 but straddle 50 — `lean`, not proven. The 10+ tier
claiming 65.2% is untestable at 47 market-even fights, and its raw-to-even drop
of fifteen points is the shape of a market-reading tier. The veteran/newcomer
split does not survive market control at this sample, and the newcomer discount
is not supported by anything measured here.

---

## Recommended next action — not implemented in this session

In priority order. None of this was done here; this session wrote two files
under `research/factors/` and touched nothing else.

1. **Settle the odds-paging discrepancy before acting on anything else.** Add
   `.order('id')` to `fetchAll` (or page by keyset) in
   `build/factor-rates.js`, re-run with a service key, and compare
   `market_even_cohort` against 1,220. Every verdict on `stats.html` rests on
   that number, and several would move. This is a one-line change with a
   measurable before/after, and it is the cheapest item on this list.
2. **Decide what to do about Record's published 60–72% range.** The evidence
   says the tiers are market echo. That is a copy and product decision, not a
   code decision, and `edges.html` already carries a dated correction pattern
   for exactly this. Two obvious shapes: retire the factor the way cardio was
   retired in August 2026, or keep it and restate the range honestly. **Do not
   re-cut the bands to make them pass** — that is fitting thresholds to a test
   result, which is what produced this situation.
3. **Add the product's own definitions to the Factor Lab.** The Factor Lab tests
   a UFC-only record factor that the product does not ship, and a takedown
   defence factor with an exposure floor the product does not apply. Two new
   entries in `FACTORS` — `record_pro_smoothed` and `td_def_edges` — would put
   the shipped definitions on the live page where they can be watched, instead
   of in a dated artifact that goes stale.
4. **Recover or formally retire `ageEdge`.** Either find the deleted source (a
   full-history clone, or the `cfl-snapshotter` repo which vendors `edges.js`)
   and record the shipped tiers, or write down in `edges.html` that the retired
   age tiers are not recoverable. The current state — two repo artifacts giving
   different numbers for the same shipped function — is worse than either.
5. **Only then consider whether age earns a place back in the verdict.** It is
   the one factor here with a market-even interval clearing 50, and it was
   dropped in May 2026 on the strength of a backtest later found to be
   hindsight-biased. That is a real question, it is an L2/L3 product decision,
   and it needs its own preregistration rather than a paragraph at the end of
   an evidence artifact.

---

*Produced 2026-09-18. Read-only: no production surface, no threshold, no
coordination file and no migration was touched.*
