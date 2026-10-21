# Discovery run `20261021T202341Z-demo-synthetic`

**Data: synthetic.** Clearly labelled SYNTHETIC fixture: no real fight is in it, and nothing here describes real UFC fights. Exploratory result: under PRED-001 section 9 it supports no statement outside the research folder.

## Plain verdict

2 of 660 tested ideas held up well enough to deserve a proper, preregistered test. None is a proven edge.

- Tested: **660** ideas (44 single factors, 616 factor-by-situation interactions), every one recorded with its result in `results.json`.
- Passed the first screen (2010-2018, false-discovery rate held at 0.1, split evenly between singles and interactions): **2**.
- RESEARCH_LEAD: 2
- BELOW_USEFUL_EFFECT: 0
- UNSTABLE: 0
- FAILED_CONFIRMATION: 0
- REJECTED_SCREEN: 583
- INSUFFICIENT_SAMPLE: 75
- LEAK_SUSPECT: 0
- Noise controls (fake factors made of random numbers): 40 run; 0 looked 'significant' before correction, 0 would have passed the corrected screen.

## The market we are trying to beat

| period | fights | cards | market log loss | after recalibrating the market | recalibration gain | market picks right |
|---|---|---|---|---|---|---|
| screen 2010-2018 | 2,376 | 216 | 0.5365 | 0.5370 | -0.0005 | 72.6% |
| confirm 2019-2024 | 1,584 | 144 | 0.5452 | 0.5451 | +0.0001 | 71.2% |

Lower log loss is better. 'Recalibrating' only re-weights the market's own number; a factor gets credit only for what it adds beyond that.

## Research leads: 2

Confirmation-period numbers (2019-2024), each fitted only on earlier years.

| candidate | fights where it says something | gain vs its reference | 95% range (by card) | gain vs market | years positive |
|---|---|---|---|---|---|
| `S:d_reach_in` | 1,436 | +0.0104 | +0.0027 to +0.0184 | +0.0105 | 100% |
| `S:d_height_in` | 1,450 | +0.0079 | +0.0004 to +0.0158 | +0.0080 | 83% |

- `S:d_reach_in`: Beyond the closing price, difference in reach in inches helps say who wins.
  - To confirm prospectively at its measured size: about 2,542 forecast-in-advance fights (~5.3 years). H1 could only detect 0.021.
- `S:d_height_in`: Beyond the closing price, difference in height in inches helps say who wins.
  - To confirm prospectively at its measured size: about 4,048 forecast-in-advance fights (~8.4 years). H1 could only detect 0.021.

## Held up, but too small to matter: 0

## Unstable: 0

## Failed confirmation (2019-2024): 0

## Closest misses at the screen (of 583 rejected)

Shown so near-misses are visible, not to rescue them. Screening-period numbers (2010-2018).

| candidate | gain vs its reference | 95% range | p (one-sided) | FDR q-value (within its kind) | permutation family-wise p |
|---|---|---|---|---|---|
| `I:mk_move*c_age_mean` | +0.0007 | -0.0001 to +0.0015 | 0.0429 | 1.000 | 0.571 |
| `I:d_td_per15*c_abs_move` | +0.0010 | -0.0003 to +0.0022 | 0.0595 | 1.000 | 0.762 |
| `I:mu_grapple*c_abs_move` | +0.0013 | -0.0004 to +0.0031 | 0.0700 | 1.000 | 0.762 |
| `S:mu_strike_eff` | +0.0004 | -0.0003 to +0.0010 | 0.1565 | 1.000 | 1.000 |
| `I:d_mean_minutes*c_overround` | +0.0004 | -0.0004 to +0.0013 | 0.1578 | 1.000 | 1.000 |
| `I:d_td_def*c_abs_move` | +0.0004 | -0.0004 to +0.0012 | 0.1590 | 1.000 | 1.000 |
| `S:d_str_def` | +0.0005 | -0.0005 to +0.0015 | 0.1671 | 1.000 | 1.000 |
| `I:mu_grapple*c_overround` | +0.0004 | -0.0005 to +0.0014 | 0.1979 | 1.000 | 1.000 |
| `S:d_mean_minutes` | +0.0001 | -0.0002 to +0.0004 | 0.2336 | 1.000 | 1.000 |
| `I:d_kd_per15*c_small` | +0.0004 | -0.0008 to +0.0017 | 0.2459 | 1.000 | 1.000 |
| `I:d_sub_per15*c_mkt_conf` | +0.0003 | -0.0005 to +0.0011 | 0.2473 | 1.000 | 1.000 |
| `S:d_td_def` | +0.0008 | -0.0015 to +0.0033 | 0.2490 | 1.000 | 1.000 |

## Everything at once, and no market at all (context, not tested)

| model | screen gain vs market | confirm gain vs market | confirm 95% range |
|---|---|---|---|
| `M:engine_all` | +0.0075 | +0.0064 | -0.0020 to +0.0150 |
| `M:history_all` | -0.0062 | +0.0001 | -0.0040 to +0.0042 |
| `M:style_matchup_all` | -0.0019 | -0.0029 | -0.0054 to -0.0003 |
| `M:physical_all` | +0.0121 | +0.0101 | +0.0024 to +0.0181 |
| `M:market_all` | -0.0016 | +0.0000 | -0.0006 to +0.0006 |
| `M:all_base` | +0.0041 | +0.0050 | -0.0044 to +0.0146 |
| `X:standalone_engine_features` | -0.0535 | -0.0343 | -0.0523 to -0.0158 |

## Leakage and integrity checks

- Feature sources against PRED-001's forbidden list: clean.
- Corner-label readers: none.
- Point-in-time recompute (25 random cards, 275 fights, 58 features, card's own results scrambled): passed.
- Corner-swap rebuild: passed.
- Fitted-model symmetry (PRED-001 checker): passed.
- Leak detector self-check (a planted leak must trip it): works (planted leak scored +0.1965 vs market).
- Permutation null (20 shuffles): the best of 660 pure-chance ideas typically reaches z = 1.74 (95th percentile 2.41); the best real idea reached 3.46.

## What this run cannot tell you

- The market here is BestFightOdds' historical closing consensus. It has no time stamp and was never a price anyone could bet. No betting return is computed, and none should be inferred.
- Every year used is before 2025. The sealed 2025-26 holdout was not read and not spent.
- A research lead licenses a written PRED-001 preregistration and nothing else. It is not an approved model and must not appear on any public page (D-011).

