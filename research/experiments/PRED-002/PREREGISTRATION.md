# PRED-002 — Do opponent-adjusted striking and grappling ratings know something the betting market and our current engine do not?

Governed by PRED-001 (`research/protocol/PREDICTION_RESEARCH_PROTOCOL.md`,
frozen v1.0.0). Approved as the next experiment by the owner on 2026-10-12
(T-080, [D-023](../../../coordination/DECISIONS.md)), with three conditions that
this document exists to meet:

1. **What counts as a meaningful improvement is written down here, before
   anything is trained.** §6.
2. **The bar is the market plus the existing model**, not the market alone and
   not a coin. §4.
3. **It starts on pre-2025 development data.** §5.

T-082 (does the live engine compute what its backtest computed?) ran first
and found no pipeline defect ([report](../../t082/T082_REPORT_2026-10-12.md)).
Nothing in this experiment reads the live engine or its locked picks either: the
"existing model" here is the engine's code retrained on development data only,
so a fault in the live serving path cannot leak into either side of the
comparison.

## Plain version

We build a rating for each fighter's striking (split by range: at distance, in
the clinch, on the ground) and wrestling that gives more credit for doing it
against good opponents and less for doing it against weak ones. Then we ask one
question: once you already know the betting price **and** what our current
engine says, do these ratings make the forecast better?

**"No" looks like this:** on the development years the ratings improve the
forecast by less than 0.002 per fight over price-plus-engine, or the range
around that improvement includes zero. Then we stop, write it down, and do not
try variations until one sticks.

## 1. Hypothesis

- **H0:** adding opponent-adjusted ratings to the market-plus-engine blend
  does not reduce log loss. Δ_B ≤ 0.
- **H1:** Δ_B > 0 on the eligible population (§7).
- Δ_B is the per-fight mean of (log loss of baseline B − log loss of challenger
  C); positive means the challenger was better. Δ_M is the same against the
  market alone.
- **Why a gain is plausible at all, and why it may well not exist.** No model
  CFL has built reads the position or target splits (8,920 fights fully
  populated) and none adjusts a fighter's output for who it was produced
  against; Elo adjusts wins only. Twelve of fourteen factors collapse to a coin
  flip once the market is controlled for, and the sportsbooks read the same
  UFCStats tables. INFO-AUDIT-001 rates the chance of success **low to
  moderate**. This document is written to make a "no" cheap and final.

## 2. The three forecasts

| | name | what it is |
|---|---|---|
| **M** | market | vig-free BestFightOdds closing consensus, proportional de-vig, both sides required |
| **B** | baseline: market + existing engine | logistic regression on `[logit(q_M), logit(p_engine)]`, weights fit on prior years only |
| **C** | challenger | the same logistic regression plus the K = 5 rating differentials of §3 |

`p_engine` is the incumbent engine (`cfl_engine/engine.py`, `train.py`,
unchanged code at the frozen commit) **retrained walk-forward on development
data only** — expanding annual folds, its own tuning on its own base window,
its own rolling calibration. The deployed engine_v1/v2 artifacts are ineligible
(trained through 2026-07, PRED-001 §2) and are not used.

B and C differ in **exactly one respect**: C's regression also sees the five
rating differentials. Same rows, same years, same fitting procedure, same
regularisation. Whatever Δ_B measures is the ratings and nothing else.

## 3. The ratings (fixed now; not tuned against the outcome)

Five stat categories, each computed per fighter per fight from `fight_rounds`
summed over rounds, as a rate per minute of fight time:

| k | category | per-fight quantity for fighter i vs opponent j |
|---|---|---|
| 1 | distance striking | `distance_landed` |
| 2 | clinch striking | `clinch_landed` |
| 3 | ground striking | `ground_landed` |
| 4 | takedowns | `td_landed` (per 15 minutes) |
| 5 | control | `ctrl_seconds` share of fight time |

**Model per category** (a two-sided online rating, the same idea Elo applies to
wins, applied to output): each fighter carries an offence rating o_i and a
defence rating d_i. The expected log-rate of i against j is
`μ + o_i − d_j`. After each fight, with residual r = log(rate + ε) − (μ + o_i − d_j):

```
o_i ← o_i + η·r        d_j ← d_j − η·r
```

and symmetrically for j against i. A fighter with no history starts at 0. μ and
ε are the pooled log-rate and a fixed floor (ε = 0.05 per minute) computed on
fights before 2010-01-01. Updates are batched per event date, so a result is
never visible to another bout on the same night (the engine's iron rule).

**The single tuning choice, made without looking at who won.** η is chosen from
{0.05, 0.10, 0.20} by the error in predicting the **next fight's stat rates**
(mean squared error of log-rate) on fights dated 2005-01-01 → 2012-12-31.
Win/loss outcomes and odds are not read to make this choice. η is recorded in
the artifact record and is then fixed.

**Features fed to C:** for each category k, the expected net margin
`(o_A − d_B) − (o_B − d_A)`. Five numbers per fight. They are antisymmetric by
construction (swapping corners negates them), so C satisfies PRED-001's corner
symmetry exactly; the test is still run.

## 4. Benchmarks and comparisons

- **Primary comparison: C vs B** (the owner's condition 2).
- **Secondary, also gated: C vs M.** A challenger that beats price-plus-engine
  but not the price alone has learned to repair the engine, not to beat the
  market.
- **Reported, never decisive:** B vs M (how much the engine adds on its own),
  accuracy, Brier, calibration slope and intercept, a 10-bin reliability table,
  and simulated flat betting under PRED-001 §5's one fixed rule, with the
  sentence "BestFightOdds consensus is not a price anyone could bet" printed
  beside it.
- De-vig: proportional primary; power and Shin reported beside it, never
  chosen after the fact.

## 5. Stages

### Stage 1 — development years (a filter, not evidence)

- **Runs only after:** the auditor's threshold review is committed (T-085)
  and this document is frozen with its sha256 in `research/registry.json`.
- **Data:** fights dated before 2025-01-01 only, read through
  `pred_protocol.dev_only()`, from a DEV export whose sha256 is recorded.
  Experiment code contains no database access (PRED-001 §2 rule 2).
- **Evaluation years:** 2016-01-01 → 2024-12-31 (expanding annual folds). For
  fold Y, the engine is trained on fights before Y, the ratings are the online
  state on the eve of each fight, and the B and C regressions are fit on the
  out-of-fold predictions of years 2013 → Y−1. Years before 2013 are burn-in
  and are never scored.
- **One run.** The configuration in this document is run once. There is no
  second run with different features, categories, η grid, folds or
  regularisation. A bug fix that changes the numbers is reported as a bug fix,
  with both outputs, and is an amendment.

### Stage 2 — one look at the sealed 2025 → 2026-07-11 window (auditor only)

Only if Stage 1 passes. The independent auditor (PRED-001 §1) scores the frozen
C and B artifacts on the 713 priced H1 fights, once, spending 1 of the 10 H1
slots, through `pred_protocol.evaluate()`.

### Stage 3 — prospective (the only stage that can earn a claim)

Only if Stage 2 does not REJECT. Both frozen artifacts (B and C) lock a
forecast for every eligible fight into `win_forecast_locks` before the start,
against the same-timestamp sportsbook consensus the database itself computes
(`win_forecast_benchmark`). **Needs the lock table, which is not yet applied
(T-084, L3), and reproducible forecasts (T-083): every lock must cite a saved,
hashed artifact that re-derives its number exactly.**

## 6. What counts as a meaningful improvement — fixed before training

Log loss, natural log, probabilities clipped to [1e-4, 1−1e-4], intervals by
resampling whole events (10,000 resamples, seed 20261012), as PRED-001 §5–6.

**These thresholds are a filter, not a measure of commercial value.** Passing
Stage 1 means "worth a prospective test" and nothing more. Every Stage 1
number is reported beside the prospective target (0.010), so a pass is never
read as "worth money". Before Stage 1 runs, an independent auditor reviews
these numbers ([brief](AUDITOR_BRIEF_THRESHOLDS.md), T-085). Any change goes in
as a pre-freeze amendment citing that review.

### Stage 1 passes only if ALL of these hold

| # | condition | why this number |
|---|---|---|
| S1.1 | **Δ_B ≥ 0.002** per fight | about two-thirds of everything the current engine adds to the price (0.0035). Smaller than that and the ratings would be a footnote to a model that is itself too small to bet |
| S1.2 | the 95% event-resampled interval for Δ_B lies **entirely above 0** | the improvement must be distinguishable from luck across the nine development years |
| S1.3 | **Δ_M ≥ 0.006** per fight, interval above 0 | the combined forecast must clear the price by a margin twice PRED-001's minimum useful effect; repairing the engine is not enough |
| S1.4 | Δ_B > 0 in **at least 6 of the 9** evaluation years | a gain that lives in two lucky years is not a property of the ratings |
| S1.5 | C's calibration slope within 0.8–1.25 and \|intercept\| ≤ 0.1 | PRED-001 §7 |
| S1.6 | Δ_M ≤ 0.015 and accuracy ≤ 72% | otherwise SUSPECT: a leak audit comes before anything else (PRED-001 §7) |

**Any condition failing ends PRED-002 at Stage 1** with the verdict
`STOP_STAGE1`, recorded with the numbers. No rescue by subgroup, division,
favourite/underdog split or alternative category set.

### Stage 2 (H1) passes only if

`pred_protocol.evaluate()` returns **PASS_H1** for C against the market, **and**
Δ_B on H1 is ≥ 0.002. The protocol's own arithmetic says H1 can only detect
about 0.008 for a blend, so a real but smaller gain will most likely return
INCONCLUSIVE. **INCONCLUSIVE on H1 does not stop Stage 3** — PRED-001 §9 rests
no claim on H1 — but it is recorded, and the owner decides whether the
prospective slot is worth spending.

### Stage 3 (prospective) — sized for a gain worth money

- **Target gain δ = 0.010** per fight against the same-timestamp market. This is
  the smallest gain INFO-AUDIT-001 judged plausibly worth money after a
  sportsbook's margin. Testing for anything smaller is a promise that resolves
  in years, not months (INFO-AUDIT-001 §5).
- **SD** = max(0.064, the SD of per-fight Δ_M measured in Stage 1).
- **n_required** = `required_n(SD, 0.010, 0.01, 0.8)` = **412** at the floor SD;
  recomputed from Stage 1's SD and fixed before the first lock. At ~480 priced
  fights a year, about **10 months**.
- **Analysis:** one, at n_required. From half of n_required, futility only
  (PRED-001 §6–7).
- **Kill date:** 18 months after the first lock, whatever n has reached. Then
  HOLD-PASSIVE: locks stop, the verdict is whatever `evaluate()` returns on the
  locks that exist, and no extension without a new preregistration.
- **Also reported prospectively:** C vs B on the same locks, with the same
  interval. A prospective pass against the market that does not also beat B is
  reported as "the engine-plus-market blend, not the ratings, carried it".

## 7. Population and eligibility

PRED-001's eligible set: both fighters set, a decisive result (draws and no
contests excluded), not a dead booking, a BestFightOdds close on both sides
(historical stages) or a same-timestamp sportsbook consensus on both sides
(prospective). **Additionally excluded:** a fight in which either fighter has
no prior UFC fight with round splits — the ratings are 0 by construction there
and the comparison would measure the engine, not the ratings. The share
excluded is reported. Coverage below 95% of the remaining eligible fights is
INVALID (PRED-001 §5).

## 8. Feature manifest

| feature | source | time rule | static? |
|---|---|---|---|
| q_M | `fight_odds` BFO closer (both sides), proportional de-vig | closing price; capture time unknown (1970 placeholder) | no |
| p_engine | engine walk-forward output | engine's own rule: rows strictly before `event_date` | no |
| rating differential, k = 1..5 | `fight_rounds.{a,b}_{distance,clinch,ground}_landed`, `{a,b}_td_landed`, `{a,b}_ctrl_seconds`; minutes from `fights.end_round`, `fights.end_time`, `scheduled_rounds` | online state updated only by fights on event dates strictly before the fight | no |

Forbidden-source check (PRED-001 §3): none of `fighters.*` career columns, no
fight's own result or stats, no other model's stored output.

## 9. Disclosures

- **Variants tried on development data:** 0 at freeze. The η grid (3 values)
  is selected on a stat-prediction error that never reads a win or a price, on
  years before any evaluation fold. Reported as 3 configurations considered.
- **Features chosen using an all-years result?** **No** Factor Lab verdict or
  published benchmark selected these categories; they were chosen because no
  model has ever read them (INFO-AUDIT-001 §4). **But H1 is not virgin**:
  INFO-AUDIT-001 re-scored the engine's blend gain by year including 2025–26
  (+0.0046 in 2025), and that figure informed the decision to keep the engine
  in the baseline. Stage 2 is therefore labelled **non-confirmatory for
  B vs M**; it remains eligible as a check of C vs B, which no one has ever
  measured.
- **Who may run what:** Claude (this session) is the Researcher for Stage 1 and
  may not run Stage 2. Stage 2 is an independent auditor session that wrote
  none of this code.

## 10. Pre-stated interpretation

- **STOP_STAGE1:** "Opponent-adjusted range and wrestling ratings did not add
  enough to the price plus our engine on 2016–2024 fights to be worth a
  prospective test." The hypothesis is closed; it is not re-run with tweaks.
- **Stage 1 pass, H1 REJECT:** "It looked useful on older fights and did not
  survive the sealed window." Closed.
- **Stage 1 pass, H1 INCONCLUSIVE:** "Too small to see on 713 fights, as the
  protocol predicted for gains under ~0.008." Owner decides whether to spend a
  prospective slot.
- **PASS_H1:** internal only — "showed a historical signal on sealed data;
  prospective test registered". Nothing public.
- **PASS_PROSPECTIVE:** "added information beyond the market on N fights
  forecast in advance". **Still not a betting claim**: that needs CLV-001's
  publication gate and a positive CLV lower bound on the same locks (PRED-001
  §9), and any public use is a separate L3 decision that does not lift D-011 by
  itself.
- **Whatever the verdict, it is not a statement about profitability.** A
  log-loss gain is a statement about forecasts. Whether it survives a
  sportsbook's margin is a separate measurement this experiment does not make.

## 11. Artifact record

This file is hash-frozen, so what Stage 1 produces is recorded **outside** it,
in [`ARTIFACT_RECORD.md`](ARTIFACT_RECORD.md) and in `research/registry.json`:
the development export's sha256, the commit the run used, η, the B and C
coefficients, and Stage 1's measured SD of Δ_M. Recording those is not an
amendment. Changing any section of this file is.

## Amendments

### Pre-freeze amendments, 2026-10-12 — written before any run, motivated by review, not by results

The independent review in [`AUDITOR_REVIEW_THRESHOLDS.md`](AUDITOR_REVIEW_THRESHOLDS.md)
retained S1.1–S1.6 unchanged. It set two conditions (A1, A2) and two further
requirements (A3, A4) before freezing. A5 records implementation choices the
text above left open. **None of them was motivated by an observed result: no
Stage 1 number existed when they were written.**

**A1 — coverage floor, fixed from development data without reading a result.**
Stage 1 is INVALID, and scores nothing, unless the scored population is
**at least 75%** of the priced, decided fights of 2016–2024 overall, **and at
least 70%** in every one of the nine years. These floors were set from a count
of which fights the §7 rule keeps. Who won was never read: of 4,174 priced,
decided fights, 3,333 qualify (79.9%), with every year between 75.7% and 84.8%.
That count was taken on 2026-10-12, read-only, from fights dated before
2025-01-01 only. The floors sit about 5 points under the measured values, so a
broken export fails loudly while the true population passes. This sits on top
of PRED-001's own rule (≥95% of the eligible fights forecast).

**A2 — exclusions disclosed by year.** Every Stage 1 report carries, per
year: priced decided fights; exclusions because corner A, corner B or both had
no earlier fight with round splits; any fight without an engine forecast; the
number scored; and coverage. It closes with this sentence on the population the
finding applies to: priced, decided UFC fights from 2016 to 2024 in which both
fighters had at least one earlier UFC fight with round splits, and nothing
about debuts.

**A3 — everything the result depends on is pinned.** The run uses one commit,
recorded in the report and in `ARTIFACT_RECORD.md`. Pinned at that commit:

- the experiment, `research/experiments/PRED-002/stage1.py`;
- the development export, `research/pred002_data/export_dev.py`;
- the incumbent engine code it retrains, `cfl_engine/engine.py` and
  `cfl_engine/train.py`;
- the benchmark and metric code, `research/protocol/pred_protocol.py` (de-vig,
  log loss, the card-resampled bootstrap, the calibration fit) and
  `research/protocol/protocol.json`;
- every library version, `cfl_engine/requirements.txt` (exact pins, T-083).

The registry freezes this file, `stage1.py` and `export_dev.py` by sha256. The
engine and protocol files are pinned by the run's commit, whose hashes the
artifact record lists. The engine stays editable for live work, so the record
says exactly which bytes Stage 1 used.

**A4 — every Stage 1 report separates three things.** Before any number, the
report states:

1. this is a historical research result that decides only whether a
   prospective test is earned;
2. the prospective test, sized for 0.010 against the price at the moment of
   the forecast, is the only stage that can support a claim;
3. it is not a statement about money: BestFightOdds consensus is not a price
   anyone could bet.

The prospective 0.010 sits in the results table beside Δ_B and Δ_M.
`tests/test_pred002_stage1.py` fails if any verdict's report omits these.

**A5 — implementation choices left open above, fixed now.**

- ε = 0.05 is applied in each category's own unit: strikes per minute,
  takedowns per 15 minutes, control as a share of fight time. A fight with no
  usable duration updates no rating. η is a single value for all five
  categories, chosen by mean squared error pooled across them. Only updates
  where both fighters already had a rating are counted, and a tie goes to the
  smaller η.
- **Engine:** annual folds from 2010. The 2010–2012 forecasts only seed the
  calibration and are never scored. Each fold tunes with `train.tune` on the
  first 55% of its training rows and early-stops on the last 10%, the
  engine's own procedure. Calibration is rolling, fitted on earlier years
  only: isotonic from 1,500 prior rows, Platt below that. It is fitted on both
  corner orientations and applied as ½(g(p) + 1 − g(1 − p)), so the engine's
  probability stays corner-symmetric.
- **Blends:** logistic regression with no intercept, fitted on both corner
  orientations, regularisation C = 100 (the engine's own blend setting), with
  no feature standardisation. No intercept, because an intercept is a corner
  term.
- **Market:** for each fighter, the median implied probability across
  BestFightOdds closing rows, then proportional de-vig. Simulated betting uses
  those medians as American prices; when both sides show value, the side with
  the larger edge is bet.
- **Cards** are clustered by `event_id`.
- **What counts as the one look.** A run that ends before any forecast is
  scored against a result is **not** a look: a preflight INVALID, an export
  failure, or a crash before scoring. Its log is kept. A run that has begun
  scoring **is** the look, whatever happens next, and is reported as such.
- **Preflight, before any scoring:** the A1 floors, at least 20 cards, a
  point-in-time recheck (the ratings for 200 randomly drawn scored fights,
  rebuilt from rounds dated strictly before each fight, must match exactly),
  and antisymmetry of every model input.
