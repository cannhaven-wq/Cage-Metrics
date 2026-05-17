# edges.js validation — phase 1 baseline

Generated: 2026-05-17T13:49:35.731Z

**CAVEATS** (see header of `research/validate.js`):

- Uses CURRENT fighter career stats / cardio for all fights, including past ones (hindsight bias).
- Streak-based edges (streak / loss_streak / post_loss) are disabled to avoid the worst leakage.
- Numbers should be read as an **upper bound**, not the true accuracy of a fair-replay model.

## Headline

- Decided fights in DB: **8546**
- Skipped (missing fighter or event row): 0
- Skipped (no edges fired): 1891
- Predictions made: **6655**
- Predictions correct: **4552 (68.4%)**

Sanity: fighter A wins in **64.2%** of decided fights — should be near 50% if A/B labelling is random.

## Calibration: accuracy by confidence band

Does a 65% verdict actually win 65% of the time? If yes, model is calibrated.

| Band     | n      | accuracy | expected |
|----------|--------|----------|----------|
| 50-55%   | 1952   | 55.9%    | 50%+     |
| 55-60%   | 1614   | 64.7%    | 55%+     |
| 60-65%   | 1676   | 72.7%    | 60%+     |
| 65-70%   | 1008   | 81.6%    | 65%+     |
| 70-75%   | 399    | 92.7%    | 70%+     |
| 75%+     | 6      | 100.0%   | 75+%+    |

## Accuracy by year

Hindsight-bias proxy: if recent years score much higher than old years,
the current-stats-on-old-fights problem is significant.

| Year | n     | accuracy |
|------|-------|----------|
| 1994 | 20    | 95.0% |
| 1995 | 31    | 90.3% |
| 1996 | 31    | 90.3% |
| 1997 | 31    | 83.9% |
| 1998 | 23    | 78.3% |
| 1999 | 39    | 69.2% |
| 2000 | 38    | 71.1% |
| 2001 | 38    | 68.4% |
| 2002 | 43    | 65.1% |
| 2003 | 32    | 71.9% |
| 2004 | 28    | 78.6% |
| 2005 | 75    | 73.3% |
| 2006 | 130   | 63.1% |
| 2007 | 136   | 65.4% |
| 2008 | 165   | 64.8% |
| 2009 | 165   | 70.3% |
| 2010 | 201   | 64.2% |
| 2011 | 230   | 61.7% |
| 2012 | 269   | 63.6% |
| 2013 | 299   | 67.6% |
| 2014 | 369   | 65.9% |
| 2015 | 368   | 63.6% |
| 2016 | 354   | 63.6% |
| 2017 | 345   | 66.7% |
| 2018 | 350   | 66.0% |
| 2019 | 389   | 63.2% |
| 2020 | 330   | 66.1% |
| 2021 | 371   | 69.0% |
| 2022 | 378   | 68.0% |
| 2023 | 386   | 73.8% |
| 2024 | 406   | 76.1% |
| 2025 | 417   | 78.4% |
| 2026 | 168   | 75.0% |

## Accuracy by division

| Division              | n     | accuracy |
|-----------------------|-------|----------|
| Lightweight           | 1112  | 67.5% |
| Welterweight          | 1041  | 64.7% |
| Middleweight          | 888   | 66.6% |
| Bantamweight          | 766   | 71.7% |
| Featherweight         | 667   | 67.6% |
| Heavyweight           | 601   | 67.6% |
| Light Heavyweight     | 556   | 71.6% |
| Flyweight             | 534   | 70.6% |
| Strawweight           | 285   | 70.2% |
| Open Weight           | 74    | 90.5% |
| Catch Weight          | 63    | 66.7% |

## Per-factor accuracy

When this edge fires (alongside others), did its favored side win? `pct_avg` is the average
confidence the model assigned this factor — a well-calibrated factor has accuracy ≈ pct_avg.

| Factor        | n      | accuracy | pct_avg |
|---------------|--------|----------|---------|
| td_def        | 4905   | 60.7%    | 54.2%   |
| record        | 3767   | 75.5%    | 62.1%   |
| cardio        | 524    | 60.1%    | 54.8%   |

## Per-factor accuracy — SOLO edge fights only

Same metric but filtered to fights where this was the ONLY factor firing. Cleaner signal.

| Factor        | n      | accuracy | pct_avg |
|---------------|--------|----------|---------|
| td_def        | 2570   | 59.0%    | 54.2%   |
| record        | 1510   | 75.8%    | 62.1%   |
| cardio        | 149    | 58.4%    | 54.7%   |

## Distance predictor (distanceEdges.js)

Predicts whether a fight goes to a decision. Grading uses `fight.method`:
"Decision..." → went distance, KO/TKO/Submission/DQ → ended early, NC/Other skipped.
Same hindsight caveat as the winner verdict: cardio data is current, not point-in-time.

The `fighter_history` factor uses `v_fighter_finish_rate` with the CURRENT fight
subtracted from each fighter's totals (`rateExcludingFight`). So a fighter's
decision_rate when predicting fight X reflects all their other fights but not X.
No leakage. Production naturally has no leakage either — when predicting an
upcoming fight, that fight isn't in the view yet.

- Predictions made: **6655**
- Skipped (NC / unclear method): 0
- Correct: **3859 (58.0%)**
- Baseline (always pick "goes distance"): 46.2%
- Baseline (always pick "ends early"):    53.8%

### Calibration by predicted-distance band

When model says distance probability is X%, what % of fights actually went distance?
Well-calibrated → "actual %" lands inside the band.

| Band   | n      | actual went distance | predict accuracy |
|--------|--------|----------------------|------------------|
| <30%   | 424    | 22.2%                | 77.8% |
| 30-40% | 1268   | 37.1%                | 62.9% |
| 40-50% | 2408   | 45.4%                | 54.6% |
| 50-60% | 1987   | 52.9%                | 52.9% |
| 60-70% | 474    | 62.7%                | 62.7% |
| 70-80% | 94     | 73.4%                | 73.4% |

### Per-division accuracy + actual base rate

Compare the "actual distance rate" column to distanceEdges.js DIVISION_DISTANCE_RATE to
see if the hardcoded base rates need tuning.

| Division              | n     | actual distance | predict accuracy |
|-----------------------|-------|-----------------|------------------|
| Lightweight           | 1112  | 48.6%           | 54.0% |
| Welterweight          | 1041  | 47.0%           | 54.9% |
| Middleweight          | 888   | 39.9%           | 60.1% |
| Bantamweight          | 766   | 55.1%           | 55.1% |
| Featherweight         | 667   | 52.6%           | 52.3% |
| Heavyweight           | 601   | 30.9%           | 69.1% |
| Light Heavyweight     | 556   | 36.0%           | 64.0% |
| Flyweight             | 534   | 55.2%           | 55.6% |
| Strawweight           | 285   | 62.5%           | 62.5% |
| Open Weight           | 74    | 6.8%            | 93.2% |
| Catch Weight          | 63    | 50.8%           | 57.1% |

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
| 1       | 1265  | 53.0% |
| 2       | 1209  | 52.0% |
| 3       | 1092  | 56.8% |
| 4       | 904   | 57.1% |
| 5       | 836   | 55.7% |
| 6       | 652   | 59.8% |
| 7       | 498   | 59.4% |
| 8       | 410   | 62.7% |
| 9       | 295   | 66.1% |
| 10      | 199   | 66.8% |
| 11      | 140   | 64.3% |
| 12+     | 271   | 70.1% |

### Veterans only (both fighters have 5+ UFC fights)

Cleaner signal — strips out the newcomer cohort where younger isn't reliably better.

| Age gap | n     | younger wins |
|---------|-------|--------------|
| 1       | 826   | 53.4% |
| 2       | 821   | 51.8% |
| 3       | 744   | 58.2% |
| 4       | 596   | 59.2% |
| 5       | 552   | 54.7% |
| 6       | 450   | 59.1% |
| 7       | 326   | 62.3% |
| 8       | 284   | 64.8% |
| 9       | 206   | 65.0% |
| 10      | 137   | 64.2% |
| 11      | 94    | 60.6% |
| 12+     | 182   | 70.3% |

### Newcomer cohort (at least one fighter has <5 UFC fights)

| Age gap | n     | younger wins |
|---------|-------|--------------|
| 1       | 439   | 52.2% |
| 2       | 388   | 52.6% |
| 3       | 348   | 53.7% |
| 4       | 308   | 52.9% |
| 5       | 284   | 57.7% |
| 6       | 202   | 61.4% |
| 7       | 172   | 54.1% |
| 8       | 126   | 57.9% |
| 9       | 89    | 68.5% |
| 10      | 62    | 72.6% |
| 11      | 46    | 71.7% |
| 12+     | 89    | 69.7% |

## Edge-count distribution

How many edges fired per fight?

| Edges per fight | count |
|-----------------|-------|
| 0               | 1879 |
| 1               | 4229 |
| 2               | 2319 |
| 3               | 119 |

