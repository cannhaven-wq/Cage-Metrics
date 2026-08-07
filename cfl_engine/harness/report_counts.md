# Props output layer — counts + simulator report

_Significant-strike and takedown count models, and the Monte-Carlo simulator that turns them (with the gated duration hazard model) into full outcome distributions and betting-line probabilities. Every number is out-of-sample: each fold trains only on fights before the test year._

## Plain-English summary

- **Do the models beat a dumb average?** Significant strikes: yes — held-out error 9.1 strikes/round vs 9.9 for a no-covariates baseline. Takedowns: yes — it calls whether a round has a takedown far better (0.542 vs 0.611 log-loss, lower is better) and predicts the count to 0.53 vs 0.61 average error.

- **Are the distributions honest?** On the most recent window (2026, 257 fights) the simulator's 80% range for total significant strikes contained the real result 77% of the time (target 80%) and its 90% range 86% (target 90%). Fight length lands on target too (84% / 91%).

- **Known caveats:** takedown intervals run a touch narrow (80% covers 73%), and significant strikes carried a train-to-recent drift that a rolling recalibration pulls down to +3.3% average bias. Neither breaks the line probabilities; both are honest before sizing real money.


## Counts vs baseline (pooled out-of-sample)

| Metric | Model | Baseline |
|---|---|---|
| Sig log-likelihood (higher=better) | -3.7662 | -3.8201 |
| Sig mean abs error (strikes/round) | 9.076 | 9.852 |
| Sig NB dispersion (want ~1.0) | 1.311 | — |
| Sig mean bias (after recalibration) | +3.3% | — |
| Takedown any-TD log-loss (lower=better) | 0.5421 | 0.6108 |
| Takedown mean abs error | 0.528 | 0.610 |

## Simulator PIT coverage (integrated distributional check)

Most recent window (2026, 257 fights, 4000 sims each). Ending round is drawn from the gated duration model; a well-calibrated simulator gives PIT ~ Uniform(0,1), so an X% central interval should contain the actual outcome X% of the time.

| Metric | mean PIT (~0.50) | 50% | 80% | 90% |
|---|---|---|---|---|
| a_sig | 0.519 | 47.5% | 79.0% | 89.1% |
| b_sig | 0.492 | 45.5% | 75.9% | 86.4% |
| total_sig | 0.505 | 46.7% | 77.0% | 86.4% |
| a_td | 0.484 | 45.1% | 72.4% | 85.2% |
| total_td | 0.492 | 49.0% | 73.2% | 89.1% |
| end_round | 0.480 | 49.8% | 83.7% | 90.7% |

## Gates

| Gate | Result |
|---|---|
| sig_beats_baseline | PASS |
| td_beats_baseline | PASS |
| sig_dispersion_ok | PASS |
| sig_mean_bias_ok | PASS |
| sim_total_sig_coverage_ok | PASS |
| sim_duration_coverage_ok | PASS |

**ALL GATES PASS** — ship rule: passes every gate AND beats `baseline_counts.json`.


## Method notes / honest limitations

- **Covariate discipline:** opponent 'defense' is strikes/takedowns ALLOWED per minute, rebuilt point-in-time from fight_rounds with shrinkage. Career `str_def`/`td_def` fields are never used.

- **Recency weighting + rolling recalibration** correct strike-volume drift (2-year half-life; level factor fit on a recent training tail, strictly before the test window).

- **Duration** is the existing gated 3-round hazard model; the simulator is scoped to 3-round fights to match it. 5-round support is future work.

- **Takedown tails** are slightly thin — widen before sizing TD props hard.

- ROI is not claimed. This validates the *distributions*; edge vs posted prop lines is the next step once a prop-line feed is captured.

