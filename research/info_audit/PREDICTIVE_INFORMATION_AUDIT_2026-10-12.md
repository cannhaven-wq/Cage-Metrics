# Predictive information audit — INFO-AUDIT-001

**Date:** 2026-10-12 · **Author:** Claude · **Status:** done, read-only, internal.
Nothing here is on a public surface and nothing here may be put on one (D-011).

**The question asked:** is CFL's biggest limit the models or the information we
feed them? What have we never tested, can we get it, and which single experiment
has a credible chance of improving on what we already have?

Every number below traces to an artifact in this folder:
[`queries.sql`](queries.sql) → [`live_results_2026-10-12.json`](live_results_2026-10-12.json)
(live database, read-only), [`blend_gain.py`](blend_gain.py) →
[`blend_gain_output.txt`](blend_gain_output.txt) (the engine's own walk-forward
file), and the existing reports cited inline.

**Pre-seal.** A parallel protocol workstream (branch `claude/nice-bell-ussmhp`,
`research/protocol/`) proposes sealing fights on or after **2025-01-01** as the
historical holdout. Every figure here that touches 2025–2026 fights is a
**descriptive re-scoring of output that already existed** (the engine's
walk-forward file, the locked snapshots, published reports). Nothing in this
audit was fit, tuned or blended anew on those fights. If that seal is adopted,
§7's Stage 1 runs on pre-2025 folds only and the sealed years are opened once,
under the protocol's rules.

---

## The plain-English version

1. **The market is the bar, and it is high.** In our own data, backing the
   closing favourite picked the winner **66.7% of the time across 7,537 fights**
   (2007–2026). That matches the outside 67.8% figure.
2. **Every model we have built lands in the same place, about 61–64%.** That
   covers a logistic model, Elo with boosting, a stacker and the XGBoost engine.
   Different machinery gives the same answer, so the machinery is not what holds
   us back.
3. **What our model adds on top of the betting price is real but tiny.**
   Historically, blending the engine with the closing price improved on the
   price alone in six of seven years. The gain is about half a percentage point
   of accuracy. You cannot bet on that: a sportsbook's margin is roughly ten
   times bigger.
4. **The live record is worse than the backtest.** On the 98 fights the engine
   put on record before the bell, it scored **no better than a coin flip** as a
   probability. The market scored clearly better on the same fights. The sample
   is small, but the gap from the backtest should be checked as a pipeline
   question.
5. **So, on the evidence: the limit is the information, not the model.** More
   modelling of the same columns is the lowest-value thing we could do next.
6. **We hold data we have never tested.** We have strikes by position
   (distance, clinch, ground) and by target (head, body, legs), plus reversals,
   for **8,920 fights**. No model or factor has ever read them. Nothing we have
   built adjusts a fighter's numbers for the quality of the opponents they were
   earned against.
7. **The honest time cost.** An improvement the size of the one we already have
   would take **about 3,800 unseen fights to confirm, roughly seven to eight
   years of UFC.** An improvement big enough to matter for money could be
   confirmed in about a year. So the test should look only for an effect big
   enough to matter. Anything smaller is "not worth it" either way.
8. **Recommendation:** test one thing. Do **opponent-adjusted fighter ratings**,
   built from the position and target data we already hold, add information
   beyond the betting price? Gate it on history first. If it passes, judge it
   only on fights locked before the bell. The chance of success is **low to
   moderate**, not high: the sportsbooks read the same UFCStats numbers we do.

---

## 1. The benchmark

| what | fights | picks the winner | log loss (lower is better) | source |
|---|---|---|---|---|
| Closing favourite, all priced history | 7,537 (2007-07 → 2026-07) | **66.7%** | 0.607 | Q1 |
| Closing line, on the engine's test fights | 3,071 (2020-01 → 2026-07) | 68.0% | 0.598 | `blend_gain.py`; `cfl_engine/benchmark_report.md` |
| A coin | — | 50% | 0.693 | — |

Caveat: the historical closing price is the **BestFightOdds consensus**, one
row per side. Its capture time was never recorded (every row carries a
1970-01-01 placeholder, Q6). CFL's own timestamped, per-book capture covers
only **272 fights**, from 2026-05-22.

## 2. What has been tried

### Models (winner)

| model | kind | tested on | picks winner | log loss | vs closing price (log loss; + means market better) |
|---|---|---|---|---|---|
| v1 | logistic, fight stats | 1,205 fights, 2023+ | 62.8% | 0.641 | +0.044 |
| v2 | logistic + Elo | 1,205, 2023+ | 62.7% | 0.638 | +0.041 |
| v3 | logistic, more features | 1,205, 2023+ | 63.7% | 0.638 | +0.041 |
| v4 | stacker of v1–v3 **plus the opening line** | 515, 2025+ | 62.7% | 0.625 | +0.014 |
| v5 | XGBoost **trained on the closing line** | 400, 2025+ | 70.8% | 0.595 | −0.003 — leak flag: it copies the market |
| v6 | XGBoost incl. betting line | 1,309, 2021+ | 67.7% | 0.622 | +0.020 — test overlaps training |
| **engine** (v1/v2) | XGBoost walk-forward, point-in-time, Elo, Platt/isotonic | 3,235, 2020-01 → 2026-07 | **61.4%** | 0.654 | +0.054 |
| **engine + market blend** | logistic stack, fit on earlier folds only | 3,071 | 68.5% | 0.595 | **−0.0035** (blend better) |

Sources: `cfl_engine/benchmark_report.md`, `cfl_engine/INTEGRATION_STATUS.md`,
`blend_gain_output.txt`. Correction to the brief: there is no documented "62%".
The engine's backtest is **61.4%**. Its live picks since 2026-07-18 are 34 of 54
(engine_v1) and **57 of 101 (56%, engine_v2)** (Q4).

**The engine's inputs:** fights, win rate, streak, layoff, age, Elo, strikes
landed and absorbed per minute, striking accuracy and defence, takedown rate,
accuracy and defence, submission and knockdown rates, control share, finish
rate, last-fight KO loss, height, reach, stance, scheduled rounds and weight
class. All are point-in-time career averages with a two-year half-life.
**None is adjusted for who the opponent was, and none uses the position or
target splits.**

### Factors (winner), measured on fights the market priced as even

Only two of the fourteen factors tested survive market control:

| survives | does not |
|---|---|
| **Age**: younger fighter, 56.5% (n=1,219) | Reach 52.4%, height 51.3%, takedown defence 50.2%, striking volume 48.4%, finish rate 52.3%, southpaw+reach 49.5% |
| **UFC-only record gap**: 58.4% (n=185, CI 51–65) | Whole-career record, the `edges.js` version, 50.2%; cardio 50.2% (retired) |

Source: `factor-rates.json`, `research/factors/FACTOR_EVIDENCE_2026-09-18.md`.
Never tested properly: win and loss streaks, layoff after a loss, takedown
accuracy point-in-time, short notice.

### Duration

PROP-0001 beats a constant baseline historically (0.5037 vs 0.5082) and is
under two preregistered prospective tests against the totals market (DUR-001,
DUR-002). Both are still collecting. **This audit does not touch them.**

## 3. Model or information? The evidence

**(a) Different machinery converges.** Logistic, Elo, boosting, stacking and
the engine all land at 61–64% and 0.64–0.65 log loss when they cannot see the
betting line. When five model families fed the same kind of inputs agree, the
inputs are the ceiling.

**(b) What the model adds beyond the price is small and fairly steady.**

| | value |
|---|---|
| blend gain over the market | **+0.0035** log loss per fight |
| event-clustered 95% interval (276 events) | **[+0.0012, +0.0057]**, which excludes zero |
| gain by year, 2020 → 2026 | −0.0004, +0.0043, +0.0024, +0.0035, +0.0065, +0.0046, +0.0019 |
| accuracy | 67.96% → 68.48% |

So the engine carries a sliver of information the closing price lacks. A
sliver is all it carries. Two limits on that conclusion: this is a historical
walk-forward, and the closing price it is compared against has no recorded
capture time.

**(c) Most of what we measure is already in the price.** Twelve of fourteen
factors fall to a coin flip once the market is controlled for. That is the same
finding as (b), seen one factor at a time.

**(d) The live record is worse than the backtest.** Q2–Q3, the first locked
pre-fight row per settled fight, 2026-08-15 → 2026-10-10, 8 events:

| | fights | picks winner | log loss |
|---|---|---|---|
| engine (engine_v2), locked before the bell | 98–102 | 53 of 102 (52%) | **0.717** |
| market at the same instant | 98 | 65 of 98 (66%) | **0.645** |
| coin | — | — | 0.693 |

- Engine minus market: +0.072 ± 0.034 standard error. The market is clearly
  better.
- Engine minus coin: +0.024 ± 0.040. Not distinguishable from a coin.
- When the engine disagreed with the market favourite (26 fights), it was right
  6 times.
- The backtest predicts about 0.654. Live is 0.717, roughly 1.5 standard errors
  worse.

That can be noise at this sample size. It can also be a live path that is not
the path the backtest measured, which is the same class of finding as the
PROP-0001 isotonic step. It is cheap to check, so it is queued (§8). It does
not change the conclusion: even the backtest engine adds only 0.0035.

**Conclusion.** Given the information CFL has used so far, the limit is the
information, not the modelling. A new architecture on the same columns is not
a credible route.

## 4. Information inventory

"Market sees it?" asks whether the sportsbooks plausibly already price this
information. That is the main reason a new input fails.

| information | held? | used by any model? | cost to get | leakage risk | market sees it? |
|---|---|---|---|---|---|
| Per-round strikes by **position** (distance / clinch / ground) and **target** (head / body / leg), reversals, total strikes | **Yes**: 20,982 round rows, 8,920 fights, fully populated (Q5) | **No** | none | low, point-in-time is mechanical | the raw numbers, yes; opponent-adjusted versions, less obviously |
| **Opponent-adjusted** ratings (stats measured against opponent quality) | derivable from the above | **No**. Elo adjusts wins only, not performance | build only | moderate: needs strict walk-forward | partly |
| Age, UFC-only record | yes | age yes; UFC-only record no | none | low | evidently not fully: both survive market control |
| Round lengths, finish timing | yes (`end_round`, `end_time`) | duration model only | none | low | yes |
| Short notice / replacement, missed weight | **no** | — | scrape + manual reconciliation; dates must be pre-fight | **high**: easy to backfill with hindsight | yes, by the close |
| Judges' scorecards, referee | no | — | moderate scrape | low | partly |
| Time spent in each position (not just strikes landed there) | no; only control seconds | — | not on UFCStats; needs a paid feed or video | — | unknown |
| Video-derived attributes (fatigue, defensive reactions) | no | — | very high: manual coding or vision pipeline, years of backfill | moderate | unknown |
| Camp, injuries, weight cut | no | — | unreliable public sources | high | yes, through news |
| Sportsbook openers, timestamped history before 2026-05 | no | — | not recoverable | — | — |
| Method and round prices (historical) | no; totals only since 2026-09-14 | — | forward capture only | — | — |

**Fight simulation** (the Markov chain approach) needs, at minimum,
time-in-position and transition counts. We hold strikes landed per position and
control time, not time spent standing, in the clinch or on the ground. We also
have no historical method or round prices to judge it against. So it is a
multi-month build with no available benchmark. Not first. This audit has not
verified the cited paper's data requirements or results, and neither paper
should be quoted on any CFL surface.

## 5. The statistical budget — the fact that sets every timeline

UFC produces about **500 decided fights a year** (497–515 each year 2021–2025, Q7). Using the
spread of the blend's per-fight gain (sd 0.066), here is how many fights a
prospective test needs to confirm a given gain (80% power, iid):

| gain to confirm (log loss) | what it means | fights | about |
|---|---|---|---|
| 0.003 | what we already have | 3,800 | 7–8 years |
| 0.005 | | 1,370 | 2.7 years |
| **0.010** | the smallest gain plausibly worth money after the book's margin | **340** | **8 months** |
| 0.020 | | 90 | 2 months |

These are floors. A model that moves further from the market has a larger
per-fight spread, and clustering by event widens the interval. The
preregistration must recompute power from its own historical-stage spread.

**Consequence:** a prospective winner test is affordable only when it is sized
for an effect worth having. A design that tries to confirm a 0.003 gain is a
promise that resolves around 2033. That is the "six months away" pattern the
brief rules out.

## 6. Candidate experiments, scored

| | hypothesis | data | build | test time | credible chance | verdict |
|---|---|---|---|---|---|---|
| **A** | Opponent-adjusted ratings from position / target splits add information beyond the price | held | weeks | history: days; prospective: ~1 year | low–moderate | **recommend** |
| B | The market under-prices the age gap (and the UFC-only record gap) | held | days | ~1–2 years (single factor, small effect) | low–moderate; already seen in history, so only prospective counts | runner-up; cheap to run alongside A as its own preregistration |
| C | Short notice / missed weight | must be scraped | weeks + reconciliation | ~1+ year | low: the close prices it | not now |
| D | Fight simulation | partly held | months | no benchmark yet | unknown | not now; revisit when method / round price capture has a season |
| E | Video-derived attributes | none | very high | years | unknown | drop for now |
| F | Re-tune the engine or try a new architecture | held | — | — | very low (§3a) | **do not** |

## 7. Proposed design for A (to preregister after approval)

**Plain version:** we build a rating for each fighter's striking and wrestling
that gives more credit for doing it against good opponents. We check on past
fights whether those ratings know something the betting price did not. If they
do, by a margin set in advance, we freeze everything and grade it on fights
locked before the bell for about a year. If not, we stop and say so.

**Stage 1 — historical gate.** A filter, not evidence.

- Ratings are fit walk-forward, point-in-time, on the engine's existing folds — **pre-2025 only if the protocol's holdout seal is adopted**, with 2025+ opened once as the confirmatory historical check.
- The challenger is the market plus the ratings. There are two comparators:
  the market alone, and the market plus the current engine. The second
  question is whether this beats what we already have.
- Thresholds are fixed in the preregistration **before** the first run.
  Suggested: a gain over the market of at least 0.006, and over market plus
  engine of at least 0.002, with the event-clustered interval excluding zero on
  both. Otherwise **stop**.
- One run. No feature hunting after the result is visible.

**Stage 2 — prospective.** Only the prospective stage can earn a verdict.

- Locks go into an append-only table at the existing snapshot instant.
- The comparator is the vig-free market price **at that same instant**, not the
  close.
- Minimum useful effect: 0.010.
- Sample: recomputed from the Stage 1 spread, expected to be about 350–500
  fights.
- A kill date and a HOLD-PASSIVE rule, in the DUR-001 pattern.

**No public number at any point** without a separate L3 decision, per D-011.

## 8. What this changes, and what it does not

- **Nothing user-facing changes.** No site, email or post carries any number
  from this audit.
- The engine, the snapshotter, DUR-001/002 and CLV are untouched.
- No timeline is promised beyond the arithmetic in §5.

**Queued from this audit:**

1. Owner picks the hypothesis (A recommended, B optional alongside).
2. Draft and freeze its preregistration.
3. Check why the engine's live record differs from its backtest. This is a
   pipeline audit, not tuning: does the live path compute what the backtest
   computed?
