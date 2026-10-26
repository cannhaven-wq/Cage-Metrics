# Discovery run `20261021T200151Z-phase1`

**Data: real-dev.** PRED-001 DEV partition only (6,824 priced fights with a result; latest event 2024-12-14). Fingerprints match the frozen manifest: True. Exploratory result: under PRED-001 section 9 it supports no statement outside the research folder.

## Plain verdict

Nothing held up. No idea passed the first screen after correcting for how many were tried.

- Tested: **660** ideas (44 single factors, 616 factor-by-situation interactions), every one recorded with its result in `results.json`.
- Passed the first screen (2010-2018, false-discovery rate held at 0.1, split evenly between singles and interactions): **0**.
- RESEARCH_LEAD: 0
- BELOW_USEFUL_EFFECT: 0
- UNSTABLE: 0
- FAILED_CONFIRMATION: 0
- REJECTED_SCREEN: 585
- INSUFFICIENT_SAMPLE: 75
- LEAK_SUSPECT: 0
- Noise controls (fake factors made of random numbers): 40 run; 0 looked 'significant' before correction, 0 would have passed the corrected screen.

## The market we are trying to beat

| period | fights | cards | market log loss | after recalibrating the market | recalibration gain | market picks right |
|---|---|---|---|---|---|---|
| screen 2010-2018 | 3,509 | 321 | 0.6117 | 0.6115 | +0.0002 | 65.7% |
| confirm 2019-2024 | 2,826 | 253 | 0.6061 | 0.6038 | +0.0023 | 67.0% |

Lower log loss is better. 'Recalibrating' only re-weights the market's own number; a factor gets credit only for what it adds beyond that.

## Research leads: 0

## Held up, but too small to matter: 0

## Unstable: 0

## Failed confirmation (2019-2024): 0

## Closest misses at the screen (of 585 rejected)

Shown so near-misses are visible, not to rescue them. Screening-period numbers (2010-2018).

| candidate | gain vs its reference | 95% range | p (one-sided) | FDR q-value (within its kind) | permutation family-wise p |
|---|---|---|---|---|---|
| `I:d_ctrl_pct*c_layoff_max` | +0.0007 | -0.0001 to +0.0015 | 0.0414 | 0.999 | 0.950 |
| `I:mu_grapple*c_layoff_max` | +0.0004 | -0.0001 to +0.0009 | 0.0741 | 0.999 | 1.000 |
| `I:d_td_per15*c_layoff_max` | +0.0003 | -0.0001 to +0.0006 | 0.0750 | 0.999 | 1.000 |
| `S:d_ufc_raw_rate` | +0.0004 | -0.0001 to +0.0010 | 0.0801 | 0.980 | 1.000 |
| `I:mk_cubic*c_any_debut` | +0.0008 | -0.0003 to +0.0018 | 0.0882 | 0.999 | 1.000 |
| `S:d_kd_per15` | +0.0007 | -0.0004 to +0.0017 | 0.0958 | 0.980 | 1.000 |
| `S:d_win_rate` | +0.0005 | -0.0003 to +0.0012 | 0.1183 | 0.980 | 1.000 |
| `I:d_sub_losses*c_any_debut` | +0.0003 | -0.0002 to +0.0008 | 0.1188 | 0.999 | 1.000 |
| `I:d_str_def*c_main_event` | +0.0005 | -0.0004 to +0.0014 | 0.1271 | 0.999 | 1.000 |
| `I:d_sub_losses*c_era` | +0.0006 | -0.0005 to +0.0018 | 0.1316 | 0.999 | 1.000 |
| `S:d_last3_win_rate` | +0.0005 | -0.0004 to +0.0013 | 0.1470 | 0.980 | 1.000 |
| `S:d_finish_rate` | +0.0007 | -0.0006 to +0.0020 | 0.1513 | 0.980 | 1.000 |

## Everything at once, and no market at all (context, not tested)

| model | screen gain vs market | confirm gain vs market | confirm 95% range |
|---|---|---|---|
| `M:engine_all` | +0.0002 | +0.0007 | -0.0043 to +0.0054 |
| `M:history_all` | -0.0040 | +0.0004 | -0.0029 to +0.0037 |
| `M:style_matchup_all` | +0.0000 | +0.0010 | -0.0028 to +0.0047 |
| `M:physical_all` | +0.0008 | +0.0015 | -0.0013 to +0.0044 |
| `M:market_all` | +0.0002 | +0.0022 | +0.0008 to +0.0035 |
| `M:all_base` | -0.0038 | -0.0007 | -0.0060 to +0.0045 |
| `X:standalone_engine_features` | -0.0565 | -0.0537 | -0.0634 to -0.0437 |

## Leakage and integrity checks

- Feature sources against PRED-001's forbidden list: clean.
- Corner-label readers: none.
- Point-in-time recompute (25 random cards, 295 fights, 58 features, card's own results scrambled): passed.
- Corner-swap rebuild: passed.
- Fitted-model symmetry (PRED-001 checker): passed.
- Leak detector self-check (a planted leak must trip it): works (planted leak scored +0.2012 vs market).
- Permutation null (100 shuffles): the best of 660 pure-chance ideas typically reaches z = 2.26 (95th percentile 3.06); the best real idea reached 1.73.

## What this run cannot tell you

- The market here is BestFightOdds' historical closing consensus. It has no time stamp and was never a price anyone could bet. No betting return is computed, and none should be inferred.
- Every year used is before 2025. The sealed 2025-26 holdout was not read and not spent.
- A research lead licenses a written PRED-001 preregistration and nothing else. It is not an approved model and must not appear on any public page (D-011).

