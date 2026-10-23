# DISC-001 — Factor Discovery Report

**2026-10-21. Internal research, development data only (fights before
2025-01-01).** Nothing here goes on a public page. Any public use of a result
is a published claim (L3 item 8, owner only). Preregistration:
[`PREREGISTRATION.md`](PREREGISTRATION.md), committed `d4aedbc6` before any
data was exported. Numbers: [`results.json`](results.json).

## Plain verdict

**None of the 20 factors, 3 interactions or 2 combinations we tested made the
closing odds any better at predicting winners.** Not one passed, and not one
even cleared the uncorrected p < 0.05 line, which usually throws up a fake
winner or two by chance alone.

**In one sentence:** by the time a fight closes, the betting market has
already priced knockout history, layoffs, activity, opponent quality, common
opponents and win streaks, at least to any degree this data can see.

That fits everything measured before it: the Factor Lab and FE-001 found that
Record and Takedown Defence look strong until you account for the odds, and
then don't.

## What was tested, plainly

For every UFC fight from 2012 to 2024 with a closing price (5,792 fights, 523
cards) we made two forecasts, using only what was known before fight night:

1. **The odds alone**, adjusted the way history says they should be adjusted.
2. **The odds plus one factor.**

If the factor knows something the odds don't, forecast 2 beats forecast 1 on
fights it has never seen. Each year was forecast using only earlier years, so
no fight is ever predicted using itself. Same-card results never count.

## Every factor, best to worst

"Gain" is how much better forecast 2 was than forecast 1, in thousandths of a
log-loss point per fight. Above zero means the factor helped. PRED-001's
smallest gain worth acting on is **+3.00**. "Leans" is the direction the data
leans: how often the fighter ahead on that factor wins at even odds. It is
fitted on all years at once, so it describes the data rather than predicting
anything. A lean near 50% means no lean.

| rank | factor | verdict | gain ×1000 | 95% range ×1000 | fights it applied to | leans | years leaning the same way |
|---|---|---|---|---|---|---|---|
| 1 | F13 Age *(contaminated — see below)* | Adds nothing measurable | +0.77 | −0.58 to +2.09 | 4,538 | 47.0% for the fighter ~5 years older | 13 of 13 |
| 2 | F14 UFC win rate *(contaminated)* | Adds nothing measurable | +0.25 | −0.32 to +0.80 | 4,087 | 48.4% | 13 of 13 |
| 3 | F03 Coming off a KO/TKO loss | Adds nothing measurable | +0.23 | −0.44 to +0.93 | 931 | 46.8% for the fighter coming off the KO | 13 of 13 |
| 4 | F18 Common opponents ("MMA math") | Adds nothing measurable | +0.18 | −0.43 to +0.79 | 695 | 46.2% | 11 of 13 |
| 5 | F02 KO/TKO loss in the last year | Adds nothing measurable | +0.12 | −0.27 to +0.51 | 1,103 | 47.6% | 10 of 13 |
| 6 | F17 Rematch: who won last time | Not enough fights | +0.04 | −0.51 to +0.54 | 116 | 57.0% for the previous winner | 11 of 13 |
| 7 | F12 Accumulated cage time | Adds nothing measurable | −0.03 | −0.40 to +0.34 | 4,486 | 50.5% | 13 of 13 |
| 8 | F15 Opponent quality | Adds nothing measurable | −0.05 | −0.63 to +0.53 | 4,426 | 48.6% | 8 of 13 |
| 9 | F05 Knockout damage, fading with time | Adds nothing measurable | −0.06 | −0.40 to +0.29 | 2,969 | 49.4% | 13 of 13 |
| 10 | F10 Recent activity (fights in 2 years) | Adds nothing measurable | −0.06 | −0.86 to +0.75 | 3,471 | 51.2% | 13 of 13 |
| 11 | F09 Quick turnaround (90 days or less) | Adds nothing measurable | −0.06 | −0.65 to +0.52 | 619 | 47.3% | 12 of 13 |
| 12 | F16 Momentum (win streak) | Adds nothing measurable | −0.07 | −0.19 to +0.05 | 3,093 | 50.4% | 5 of 13 |
| 13 | F06 Knockdowns absorbed | Adds nothing measurable | −0.14 | −0.49 to +0.19 | 2,994 | 50.1% | 1 of 13 |
| 14 | F11 UFC experience | Adds nothing measurable | −0.20 | −0.43 to +0.02 | 5,049 | 50.0% | 12 of 13 |
| 15 | F20 First main event | Not enough fights | −0.20 | −0.50 to +0.09 | 184 | 47.7% | 12 of 13 |
| 16 | F01 KO/TKO losses (count) | Adds nothing measurable | −0.21 | −0.62 to +0.20 | 2,594 | 50.1% | 1 of 13 |
| 17 | F19 First five-round fight | Not enough fights | −0.22 | −0.50 to +0.05 | 209 | 48.7% | 10 of 13 |
| 18 | F04 Repeat KO/TKO losses (2+) | Adds nothing measurable | −0.29 | −0.74 to +0.14 | 1,141 | 49.8% | 12 of 13 |
| 19 | F07 Layoff length | Adds nothing measurable | −0.45 | −1.00 to +0.07 | 4,341 | 50.4% | 11 of 13 |
| 20 | F08 Long layoff (a year or more) | Adds nothing measurable | −1.16 | −2.53 to +0.19 | 842 | 46.6% for the returning fighter | 13 of 13 |

**Interactions** (each judged against a model already holding its two parts):

| id | interaction | verdict | gain ×1000 | 95% range ×1000 | fights it applied to |
|---|---|---|---|---|---|
| I1 | Coming off a KO/TKO loss × back within 180 days | Adds nothing measurable | −0.07 | −0.91 to +0.71 | 422 |
| I2 | Rematch × first meeting ended in a finish | Not enough fights | −0.41 | −0.88 to +0.01 | 58 |
| I3 | First main event × opponent's main-event experience | Not enough fights | −0.07 | −0.37 to +0.22 | 184 |

**Combinations** (declared in advance, not built from the winners):

| model | gain ×1000 | 95% range ×1000 |
|---|---|---|
| C1 — all 20 factors together | −1.97 | −5.12 to +1.13 |
| C2 — the 18 clean factors (no age, no win rate) | −3.02 | −5.77 to −0.26 |

**Putting all the factors together made the forecast worse**, and for C2 the
whole range sits below zero. Twenty weak inputs add more noise than signal,
even with the shrinkage we fixed in advance.

## How sensitive the test was

A "nothing" only means something if the test could have found a real effect.
So we kept the real fights, odds and factor values, threw away the real
results, and simulated results in which a factor *does* matter, at a known
strength, 40 times per setting ([`positive_control.py`](positive_control.py),
[`positive_control.json`](positive_control.json)):

| planted effect (at even odds, the fighter ahead on the factor wins…) | found, on coming off a KO loss (applies to ~1 in 6 fights) | found, on long layoff (~1 in 7) | found, on age (nearly every fight) |
|---|---|---|---|
| 53% | 0% | 0% | 13% |
| 55% | 0% | 0% | 35% |
| 57% | 5% | 8% | **100%** |
| 60% | 38% | 30% | **100%** |

For age, "ahead" means about five years younger or older (one typical age gap). "Found" uses the corrected bar this report applies to the best-ranked factor.
At the uncorrected 5% bar, a 60% planted effect on the yes/no factors is found
about 9 times in 10.

**What that means:**

- **For factors that apply to most fights** (age, experience, cage time,
  opponent quality, activity), the test is sharp. A real effect of 57% at even
  odds would have shown up every time, and none did.
- **For factors that apply to a minority of fights** (KO losses, layoffs,
  quick turnarounds, rematches, first main events), the test is blunt. It can
  rule out a big effect but not a modest one. Using the 95% ranges above
  against the simulation, a "coming off a KO loss" effect of about 57% or more
  is unlikely, and a "long layoff" effect of about 55% or more is unlikely.
  Effects of 52–54% cannot be ruled out.
- **A factor that applies to 1 fight in 6 cannot reach PRED-001's +3.00
  useful-gain bar averaged over every fight, even with a large effect.** A
  planted 60% effect on "coming off a KO loss" averaged +2.66. Sparse factors
  have to be asked as their own question, on the fights where they apply.

## Three things that look like findings and are not

1. **"The market underrates favourites."** Adjusting the odds alone, before
   any factor, improved on the raw odds (+1.19, range +0.19 to +2.11). That
   is an artefact of how the bookmaker's margin was removed. Under PRED-001's
   other two methods the gain disappears: power method −0.05 (range −0.48 to
   +0.34), Shin method +0.27 (range −0.36 to +0.85)
   ([`devig_check.py`](devig_check.py), [`devig_check.json`](devig_check.json)).
   The proportional method leaves longshots slightly too likely, and the
   adjustment simply undid that. **There is no mispricing claim here.** That
   is also why every factor is judged against the adjusted odds: otherwise each
   one would get credit for the same fix.
2. **Long layoff leans the same way in all 13 years and still loses.** The
   early forecasts were fitted on few fights (about 1,000 for 2012) and put
   five times too much weight on it, which cost heavily in 2013–14. Once the
   data grew, the weight shrank and the net effect from 2015 on is about zero.
   That is the walk-forward doing its job.
3. **Age is closest to something, and it is still not a finding.** It leans
   the same way in all 13 years (the younger fighter does slightly better than
   the odds say: about 47% at even odds for a fighter five years older) and helped in 8 of 13 years, but its range crosses
   zero (p = 0.13). It is also contaminated: it was chosen because a Factor Lab
   verdict computed over 2025–26 looked good, so no historical test can count
   as evidence for it. Only a prospective test can.

## What this means for the plan

1. **Don't spend a sealed-set look on any of these.** Nothing qualifies as a
   candidate. The sealed set allows 10 looks ever, and this run gives no
   reason to use one.
2. **Don't add these factors to anything user-facing as "edges".** That was
   already the rule (D-011), and this is the evidence behind it for 20 more
   factors.
3. **If the sparse factors are worth more time, ask them as their own
   question.** That means "on fights where one fighter is coming off a KO
   loss, does the market get the price right?" It would be a new
   preregistration (DISC-002), still pre-2025 data only, and its power would
   be stated before the run: about 930 such fights can see an effect of about
   54% or larger, and nothing smaller.
4. **Set a high bar before building new data.** An injury, travel or altitude
   factor that applies to 1 fight in 20 would need an effect of roughly 57% or more at
   even odds to be visible in this history, even asked as its own question, and reconstructing it
   historically is expensive and biased (injuries are reported selectively).
   The evidence so far says the closing market is hard to beat on information
   that is public before the fight. Spend new-data money only where there is a
   specific reason to think the market *can't* know something, and where
   capture can start prospectively.
5. **The prospective odds capture (from 19 September 2026) stays the thing
   that can eventually answer the money question.** Nothing here changes that.

## Limits, stated once

- **UFC fights only.** A fighter's pre-UFC record isn't in the database, so a
  UFC debut looks like a blank, and those fights fall back to the odds alone.
- **The benchmark is BFO's closing consensus**, a historical closing price with
  no real timestamp that nobody could have bet at a known time (BT-001). This
  measures information, never a return.
- **"Knockout loss" means KO/TKO** as recorded by UFCStats. Doctor's stoppages
  are excluded, and knockdowns are counted separately (F06).
- **Ranking momentum** has no source table. F16 (win streak) stands in for
  it and should not be described as rankings.
- **Not tested, because the data doesn't exist:** venue altitude, camp
  altitude, travel, time zones, injuries, media attention, public betting.

<details>
<summary>The arithmetic</summary>

- Market probability m: BFO closer for each corner (by `fighter_id`),
  proportional de-vig (`pred_protocol.devig_proportional`), both prices within
  100-to-1.
- Baseline: p = σ(a · logit m). Factor model: p = σ(a · logit m + β · d),
  d = factor(A) − factor(B), standardised on the training window. There is no
  intercept and d is antisymmetric, so p(A) = 1 − p(B) exactly.
  `pred_protocol.symmetry_violations` returned no violations for any model.
- Maximum likelihood (Newton). Walk-forward: train on every eligible fight
  before year Y (from 2008), predict Y, Y = 2012…2024. C1 and C2 use a ridge
  penalty λ = 5 on the standardised coefficients, with the market slope
  unpenalised.
- Gain per fight = LL(baseline) − LL(model), in nats. Mean over 5,792 scored
  fights. Uncertainty: whole cards resampled 10,000 times, seed 20261012
  (`pred_protocol.cluster_bootstrap`). One-sided p = (resamples ≤ 0 + 1) /
  10,001.
- Holm step-down at family-wise α = 0.05, separately for the 20 primary
  factors (first bar p ≤ 0.0025) and the 3 interactions. The smallest primary
  p was 0.13 (age). The smallest interaction p was 0.56.
- "Not enough fights" = fewer than 300 scored fights where the factor
  differed between the two fighters.
- Point-in-time audit: for 200 randomly drawn scored fights (seed 20261021),
  every value was recomputed by a separate, naive implementation from a
  history cut off before the fight's date, and again with the corners
  swapped. There were zero differences and zero symmetry failures. The run
  refuses to finish otherwise.

</details>

## Reproduce

```
python3 research/experiments/DISC-001/discover.py          # results.json
python3 research/experiments/DISC-001/positive_control.py  # positive_control.json
python3 research/experiments/DISC-001/devig_check.py       # devig_check.json
```

The data in `data/` was produced by `build/disc001-export.js`, which implements
`research/factors/disc001_dev_export.sql`. The two agree byte for byte: md5 of
the fights export `886dff134655d8cad62b055c82dfd3a1` (7,974 rows, 6,953 with a
BFO closer) and of the fighters export `bed424a2de1324bb0a9330ae49b1c8c1`
(2,550 rows), computed both in the database and on the exported files. The
export ran once, in a one-off GitHub Actions job on the research branch that
was deleted before merge. No sealed fight's result or price was read: every
query was filtered to events before 2025-01-01, and the loader re-checks every
row with `pred_protocol.dev_only()`.
