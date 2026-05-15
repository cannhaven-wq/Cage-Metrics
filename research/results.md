# edges.js validation — phase 1 baseline

Generated: 2026-05-15T19:20:02.462Z

**CAVEATS** (see header of `research/validate.js`):

- Uses CURRENT fighter career stats / cardio for all fights, including past ones (hindsight bias).
- Streak-based edges (streak / loss_streak / post_loss) are disabled to avoid the worst leakage.
- Numbers should be read as an **upper bound**, not the true accuracy of a fair-replay model.

## Headline

- Decided fights in DB: **8533**
- Skipped (missing fighter or event row): 0
- Skipped (no edges fired): 166
- Predictions made: **8367**
- Predictions correct: **5508 (65.8%)**

Sanity: fighter A wins in **64.2%** of decided fights — should be near 50% if A/B labelling is random.

## Calibration: accuracy by confidence band

Does a 65% verdict actually win 65% of the time? If yes, model is calibrated.

| Band     | n      | accuracy | expected |
|----------|--------|----------|----------|
| 50-55%   | 2116   | 53.2%    | 50%+     |
| 55-60%   | 1908   | 59.9%    | 55%+     |
| 60-65%   | 1852   | 68.1%    | 60%+     |
| 65-70%   | 1281   | 75.3%    | 65%+     |
| 70-75%   | 967    | 82.9%    | 70%+     |
| 75%+     | 243    | 87.7%    | 75+%+    |

## Accuracy by year

Hindsight-bias proxy: if recent years score much higher than old years,
the current-stats-on-old-fights problem is significant.

| Year | n     | accuracy |
|------|-------|----------|
| 1994 | 22    | 86.4% |
| 1995 | 34    | 79.4% |
| 1996 | 38    | 81.6% |
| 1997 | 37    | 86.5% |
| 1998 | 25    | 76.0% |
| 1999 | 40    | 72.5% |
| 2000 | 41    | 70.7% |
| 2001 | 39    | 69.2% |
| 2002 | 52    | 65.4% |
| 2003 | 39    | 69.2% |
| 2004 | 37    | 62.2% |
| 2005 | 78    | 76.9% |
| 2006 | 155   | 57.4% |
| 2007 | 168   | 70.8% |
| 2008 | 198   | 67.7% |
| 2009 | 210   | 63.3% |
| 2010 | 246   | 60.6% |
| 2011 | 292   | 58.9% |
| 2012 | 330   | 62.7% |
| 2013 | 365   | 64.7% |
| 2014 | 486   | 59.9% |
| 2015 | 456   | 62.3% |
| 2016 | 476   | 64.7% |
| 2017 | 437   | 65.2% |
| 2018 | 460   | 63.5% |
| 2019 | 495   | 64.6% |
| 2020 | 436   | 66.1% |
| 2021 | 487   | 63.7% |
| 2022 | 491   | 65.6% |
| 2023 | 494   | 71.5% |
| 2024 | 507   | 68.6% |
| 2025 | 509   | 73.7% |
| 2026 | 187   | 72.7% |

## Accuracy by division

| Division              | n     | accuracy |
|-----------------------|-------|----------|
| Lightweight           | 1396  | 66.7% |
| Welterweight          | 1332  | 65.0% |
| Middleweight          | 1096  | 62.3% |
| Bantamweight          | 971   | 66.2% |
| Featherweight         | 845   | 67.0% |
| Heavyweight           | 740   | 67.8% |
| Light Heavyweight     | 716   | 64.5% |
| Flyweight             | 664   | 65.2% |
| Strawweight           | 357   | 66.7% |
| Open Weight           | 84    | 84.5% |
| Catch Weight          | 76    | 68.4% |

## Per-factor accuracy

When this edge fires (alongside others), did its favored side win? `pct_avg` is the average
confidence the model assigned this factor — a well-calibrated factor has accuracy ≈ pct_avg.

| Factor        | n      | accuracy | pct_avg |
|---------------|--------|----------|---------|
| age           | 7650   | 57.4%    | 56.7%   |
| stance_reach  | 5550   | 53.4%    | 52.5%   |
| td_def        | 4869   | 60.7%    | 54.2%   |
| slpm          | 4253   | 64.8%    | 52.7%   |
| record        | 3763   | 75.5%    | 62.1%   |
| td_acc        | 3569   | 58.8%    | 53.6%   |
| cardio        | 521    | 60.5%    | 54.8%   |

## Per-factor accuracy — SOLO edge fights only

Same metric but filtered to fights where this was the ONLY factor firing. Cleaner signal.

| Factor        | n      | accuracy | pct_avg |
|---------------|--------|----------|---------|
| age           | 224    | 46.4%    | 57.2%   |
| record        | 62     | 91.9%    | 64.9%   |
| stance_reach  | 45     | 64.4%    | 52.8%   |
| slpm          | 16     | 43.8%    | 52.2%   |
| td_def        | 15     | 60.0%    | 55.1%   |
| td_acc        | 8      | 50.0%    | 53.5%   |

## Distance predictor (distanceEdges.js)

Predicts whether a fight goes to a decision. Grading uses `fight.method`:
"Decision..." → went distance, KO/TKO/Submission/DQ → ended early, NC/Other skipped.
Same hindsight caveat as the winner verdict: cardio data is current, not point-in-time.

**Additional caveat for the `fighter_history` factor**: `v_fighter_finish_rate`
aggregates over every fight a fighter has had, including the one being predicted.
So a fighter's decision_rate for fight X knows whether fight X went to decision
(diluted by N — for a fighter with 30 UFC fights, this is ~3% of their signal).
Bayesian shrinkage further dampens it. Real-world deployment accuracy will be
slightly lower than this number — exclude-current-fight rates are a follow-up.

- Predictions made: **8367**
- Skipped (NC / unclear method): 0
- Correct: **5176 (61.9%)**
- Baseline (always pick "goes distance"): 46.9%
- Baseline (always pick "ends early"):    53.1%

### Calibration by predicted-distance band

When model says distance probability is X%, what % of fights actually went distance?
Well-calibrated → "actual %" lands inside the band.

| Band   | n      | actual went distance | predict accuracy |
|--------|--------|----------------------|------------------|
| <30%   | 587    | 17.0%                | 83.0% |
| 30-40% | 1566   | 35.6%                | 64.4% |
| 40-50% | 2926   | 42.9%                | 57.1% |
| 50-60% | 2516   | 56.8%                | 56.8% |
| 60-70% | 615    | 72.4%                | 72.4% |
| 70-80% | 157    | 87.3%                | 87.3% |

### Per-division accuracy + actual base rate

Compare the "actual distance rate" column to distanceEdges.js DIVISION_DISTANCE_RATE to
see if the hardcoded base rates need tuning.

| Division              | n     | actual distance | predict accuracy |
|-----------------------|-------|-----------------|------------------|
| Lightweight           | 1396  | 47.8%           | 64.0% |
| Welterweight          | 1332  | 47.1%           | 61.8% |
| Middleweight          | 1096  | 40.1%           | 59.9% |
| Bantamweight          | 971   | 55.5%           | 56.8% |
| Featherweight         | 845   | 53.7%           | 57.6% |
| Heavyweight           | 740   | 32.2%           | 67.8% |
| Light Heavyweight     | 716   | 36.3%           | 63.7% |
| Flyweight             | 664   | 57.8%           | 58.6% |
| Strawweight           | 357   | 66.4%           | 66.4% |
| Open Weight           | 84    | 7.1%            | 92.9% |
| Catch Weight          | 76    | 48.7%           | 67.1% |

## Age gap → younger-fighter win rate

Independent of edges.js. For each integer year of age gap, what fraction of
historical fights did the younger fighter win? The gap is preserved across time
(both fighters age at the same rate) so this is NOT subject to hindsight bias.

Compare each row to the model's assigned `pct`:
- 1–2 yrs: 52.0% (newcomer-discounted to 51.0%)
- 3–4 yrs: 55.9% (newcomer-discounted to 53.0%)
- 5–6 yrs: 58.2% (newcomer-discounted to 54.1%)
- 7–9 yrs: 63.3% (newcomer-discounted to 56.7%)
- 10+ yrs: 65.2% (newcomer-discounted to 57.6%)

### All fights with known ages on both sides

| Age gap | n     | younger wins |
|---------|-------|--------------|
| 1       | 1264  | 53.0% |
| 2       | 1204  | 51.9% |
| 3       | 1089  | 56.8% |
| 4       | 902   | 57.1% |
| 5       | 834   | 55.6% |
| 6       | 650   | 59.8% |
| 7       | 499   | 59.5% |
| 8       | 410   | 62.7% |
| 9       | 295   | 66.1% |
| 10      | 199   | 66.8% |
| 11      | 139   | 64.7% |
| 12+     | 271   | 70.1% |

### Veterans only (both fighters have 5+ UFC fights)

Cleaner signal — strips out the newcomer cohort where younger isn't reliably better.

| Age gap | n     | younger wins |
|---------|-------|--------------|
| 1       | 828   | 53.5% |
| 2       | 817   | 51.7% |
| 3       | 742   | 58.2% |
| 4       | 594   | 59.4% |
| 5       | 553   | 54.6% |
| 6       | 448   | 59.2% |
| 7       | 327   | 62.4% |
| 8       | 284   | 64.8% |
| 9       | 206   | 65.0% |
| 10      | 137   | 64.2% |
| 11      | 94    | 60.6% |
| 12+     | 182   | 70.3% |

### Newcomer cohort (at least one fighter has <5 UFC fights)

| Age gap | n     | younger wins |
|---------|-------|--------------|
| 1       | 436   | 52.1% |
| 2       | 387   | 52.5% |
| 3       | 347   | 53.9% |
| 4       | 308   | 52.6% |
| 5       | 281   | 57.7% |
| 6       | 202   | 61.4% |
| 7       | 172   | 54.1% |
| 8       | 126   | 57.9% |
| 9       | 89    | 68.5% |
| 10      | 62    | 72.6% |
| 11      | 45    | 73.3% |
| 12+     | 89    | 69.7% |

## Edge-count distribution

How many edges fired per fight?

| Edges per fight | count |
|-----------------|-------|
| 0               | 41 |
| 1               | 370 |
| 2               | 1250 |
| 3               | 2329 |
| 4               | 2546 |
| 5               | 1523 |
| 6               | 456 |
| 7               | 18 |

