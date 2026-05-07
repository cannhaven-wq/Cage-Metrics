# edges.js validation — phase 1 baseline

Generated: 2026-05-07T02:47:38.906Z

**CAVEATS** (see header of `research/validate.js`):

- Uses CURRENT fighter career stats / cardio for all fights, including past ones (hindsight bias).
- Streak-based edges (streak / loss_streak / post_loss) are disabled to avoid the worst leakage.
- Numbers should be read as an **upper bound**, not the true accuracy of a fair-replay model.

## Headline

- Decided fights in DB: **8520**
- Skipped (missing fighter or event row): 0
- Skipped (no edges fired): 177
- Predictions made: **8343**
- Predictions correct: **5521 (66.2%)**

Sanity: fighter A wins in **64.2%** of decided fights — should be near 50% if A/B labelling is random.

## Calibration: accuracy by confidence band

Does a 65% verdict actually win 65% of the time? If yes, model is calibrated.

| Band     | n      | accuracy | expected |
|----------|--------|----------|----------|
| 50-55%   | 2178   | 53.4%    | 50%+     |
| 55-60%   | 2028   | 60.8%    | 55%+     |
| 60-65%   | 1779   | 69.4%    | 60%+     |
| 65-70%   | 1491   | 76.0%    | 65%+     |
| 70-75%   | 755    | 85.8%    | 70%+     |
| 75%+     | 112    | 96.4%    | 75+%+    |

## Accuracy by year

Hindsight-bias proxy: if recent years score much higher than old years,
the current-stats-on-old-fights problem is significant.

| Year | n     | accuracy |
|------|-------|----------|
| 1994 | 23    | 87.0% |
| 1995 | 34    | 79.4% |
| 1996 | 38    | 84.2% |
| 1997 | 37    | 86.5% |
| 1998 | 25    | 76.0% |
| 1999 | 40    | 75.0% |
| 2000 | 41    | 70.7% |
| 2001 | 39    | 69.2% |
| 2002 | 52    | 67.3% |
| 2003 | 39    | 71.8% |
| 2004 | 38    | 63.2% |
| 2005 | 77    | 76.6% |
| 2006 | 155   | 58.7% |
| 2007 | 167   | 67.7% |
| 2008 | 198   | 68.2% |
| 2009 | 208   | 64.4% |
| 2010 | 244   | 62.3% |
| 2011 | 294   | 57.8% |
| 2012 | 330   | 62.1% |
| 2013 | 363   | 64.7% |
| 2014 | 486   | 60.7% |
| 2015 | 456   | 62.9% |
| 2016 | 476   | 65.5% |
| 2017 | 440   | 65.5% |
| 2018 | 457   | 65.0% |
| 2019 | 493   | 64.5% |
| 2020 | 433   | 67.0% |
| 2021 | 486   | 63.8% |
| 2022 | 488   | 66.2% |
| 2023 | 494   | 71.1% |
| 2024 | 508   | 68.7% |
| 2025 | 510   | 74.1% |
| 2026 | 174   | 72.4% |

## Accuracy by division

| Division              | n     | accuracy |
|-----------------------|-------|----------|
| Lightweight           | 1390  | 66.3% |
| Welterweight          | 1333  | 65.2% |
| Middleweight          | 1087  | 62.8% |
| Bantamweight          | 971   | 66.9% |
| Featherweight         | 841   | 66.5% |
| Heavyweight           | 739   | 69.4% |
| Light Heavyweight     | 713   | 66.3% |
| Flyweight             | 663   | 65.0% |
| Strawweight           | 356   | 66.3% |
| Open Weight           | 85    | 85.9% |
| Catch Weight          | 75    | 68.0% |

## Per-factor accuracy

When this edge fires (alongside others), did its favored side win? `pct_avg` is the average
confidence the model assigned this factor — a well-calibrated factor has accuracy ≈ pct_avg.

| Factor        | n      | accuracy | pct_avg |
|---------------|--------|----------|---------|
| age           | 7627   | 57.4%    | 55.9%   |
| stance_reach  | 5537   | 53.5%    | 52.5%   |
| td_def        | 4851   | 60.7%    | 54.2%   |
| slpm          | 4236   | 64.9%    | 52.7%   |
| record        | 3750   | 75.6%    | 62.1%   |
| td_acc        | 3566   | 58.9%    | 53.6%   |
| cardio        | 517    | 60.7%    | 54.8%   |

## Per-factor accuracy — SOLO edge fights only

Same metric but filtered to fights where this was the ONLY factor firing. Cleaner signal.

| Factor        | n      | accuracy | pct_avg |
|---------------|--------|----------|---------|
| age           | 223    | 46.2%    | 56.2%   |
| record        | 62     | 91.9%    | 64.9%   |
| stance_reach  | 45     | 64.4%    | 52.8%   |
| slpm          | 16     | 43.8%    | 52.2%   |
| td_def        | 15     | 60.0%    | 55.1%   |
| td_acc        | 8      | 50.0%    | 53.5%   |

## Edge-count distribution

How many edges fired per fight?

| Edges per fight | count |
|-----------------|-------|
| 0               | 41 |
| 1               | 369 |
| 2               | 1248 |
| 3               | 2331 |
| 4               | 2534 |
| 5               | 1523 |
| 6               | 457 |
| 7               | 17 |

