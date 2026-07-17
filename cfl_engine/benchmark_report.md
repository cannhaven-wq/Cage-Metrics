# Production-model benchmark (v1-v6) vs the honest engine

_Generated 2026-07-17 by `cfl_engine/benchmark_prod.py`. Source: Supabase `model_versions` + `model_predictions` (deduped to one row per model per fight), scored with the same `audit.metric_block` the engine audits itself with._

Every model is scored **only inside its own declared out-of-sample window** (`test_start_date`). Widening a window would re-feed a model its own training data, so we never do it. Accuracy = share of fights the model called correctly; log-loss and Brier reward calibrated confidence (lower is better).

## The honest yardstick (the engine)

The clean walk-forward engine, scored on its calibrated out-of-sample fights (2020-01-25 to 2026-07-11, 3,232 fights):

| | accuracy | log-loss | brier |
|---|---|---|---|
| Engine (calibrated) | 61.4% | 0.6511 | 0.2299 |
| Vegas closing line (same 3,068 priced fights) | 68.0% | 0.5978 | 0.2055 |

The market wins. A clean MMA model that only sees the past lands ~61-67% and does **not** beat the closing line standalone. Any 'model' that does is almost always reading the answer off a leaked feature. That is the bar the shipped models are held to below.

## 1. Each model on its own out-of-sample window

| model | window from | fights scored | accuracy | log-loss | brier | site's claimed acc | claimed n | flag |
|---|---|---|---|---|---|---|---|---|
| **v1** Logistic Regression | 2023-01-01 | 1,205 | 62.8% | 0.6407 | 0.2249 | 62.7% | 1205 |  |
| **v2** Elo + Gradient Boosting | 2023-01-01 | 1,205 | 62.7% | 0.6376 | 0.2236 | 62.7% | 1205 |  |
| **v3** Advanced | 2023-01-01 | 1,205 | 63.7% | 0.6381 | 0.2237 | 63.7% | 1205 |  |
| **v4** Stacker | 2025-01-01 | 515 | 62.7% | 0.6254 | 0.2175 | 65.3% | 954 |  |
| **v5** Accuracy v5 | 2025-01-01 | 400 | 70.8% | 0.5952 | 0.2034 | 70.0% | 736 | RED: acc > 70% |
| **v6** v6 | 2021-01-01 | 1,309 | 67.7% | 0.6219 | 0.2158 | 67.5% | 2602 |  |

## 2. Same-fight comparison: each model vs the engine vs the market

For each model we take the fights it scored **inside its own window** that the engine also scored, and put all three on the identical fight set. `market` is the vig-free closing line. This is the apples-to-apples test.

### v1 - 1,203 shared fights (1,146 with a closing line)

| | fights | accuracy | log-loss | brier |
|---|---|---|---|---|
| v1 (prod) | 1,203 | 62.8% | 0.6410 | 0.2250 |
| engine p_cal | 1,203 | 63.8% | 0.6358 | 0.2230 |
| market (close) | 1,146 | 69.3% | 0.5958 | 0.2044 |

- On the 1,146 priced fights, v1 does not beat the closing line (its log-loss is +0.0436 vs the market; positive = market better).

### v2 - 1,203 shared fights (1,146 with a closing line)

| | fights | accuracy | log-loss | brier |
|---|---|---|---|---|
| v2 (prod) | 1,203 | 62.7% | 0.6380 | 0.2238 |
| engine p_cal | 1,203 | 63.8% | 0.6358 | 0.2230 |
| market (close) | 1,146 | 69.3% | 0.5958 | 0.2044 |

- On the 1,146 priced fights, v2 does not beat the closing line (its log-loss is +0.0406 vs the market; positive = market better).

### v3 - 1,203 shared fights (1,146 with a closing line)

| | fights | accuracy | log-loss | brier |
|---|---|---|---|---|
| v3 (prod) | 1,203 | 63.7% | 0.6385 | 0.2239 |
| engine p_cal | 1,203 | 63.8% | 0.6358 | 0.2230 |
| market (close) | 1,146 | 69.3% | 0.5958 | 0.2044 |

- On the 1,146 priced fights, v3 does not beat the closing line (its log-loss is +0.0413 vs the market; positive = market better).

### v4 - 513 shared fights (492 with a closing line)

| | fights | accuracy | log-loss | brier |
|---|---|---|---|---|
| v4 (prod) | 513 | 62.6% | 0.6269 | 0.2182 |
| engine p_cal | 513 | 64.1% | 0.6241 | 0.2182 |
| market (close) | 492 | 67.9% | 0.6005 | 0.2068 |

- On the 492 priced fights, v4 does not beat the closing line (its log-loss is +0.0140 vs the market; positive = market better).

### v5 - 399 shared fights (399 with a closing line)

| | fights | accuracy | log-loss | brier |
|---|---|---|---|---|
| v5 (prod) | 399 | 70.7% | 0.5961 | 0.2038 |
| engine p_cal | 399 | 64.2% | 0.6274 | 0.2195 |
| market (close) | 399 | 68.2% | 0.5988 | 0.2056 |

- On the 399 priced fights, v5 does not beat the closing line (its log-loss is -0.0028 vs the market; positive = market better).

### v6 - 1,308 shared fights (1,308 with a closing line)

| | fights | accuracy | log-loss | brier |
|---|---|---|---|---|
| v6 (prod) | 1,308 | 67.7% | 0.6221 | 0.2159 |
| engine p_cal | 1,308 | 62.8% | 0.6451 | 0.2270 |
| market (close) | 1,308 | 68.3% | 0.6020 | 0.2072 |

- On the 1,308 priced fights, v6 does not beat the closing line (its log-loss is +0.0202 vs the market; positive = market better).

## 3. Verdict (plain English)

**Leak flags fired: v5.** These models clear the too-good line (better than 70% accuracy, or beating the closing line by more than 1.5 points of log-loss). Nobody honest does that against the close standalone. Read those numbers as evidence the backtest was leaking, not as a reason to trust the model live.

**Known, already-diagnosed reasons (July 2026 audit) - state these plainly:**

- **v5 (the 70% headline) trains on the closing line itself.** Its ~70% accuracy is the market's own number handed back to us. The tell is in the same-fight table: on the 399 shared fights v5's log-loss (0.596) sits right on top of the market's (0.599) while the clean engine is well behind at 0.627 - v5 isn't out-predicting Vegas, it's copying Vegas. It cannot run live, because at pick time the closing line does not exist yet. Treat v5's 70% as 'we can reprint Vegas', not 'we beat Vegas'.
- **v6's public test window overlaps its training window.** v6 is scored from 2021 forward but was trained on data through the end of 2024 - so most of its 'out-of-sample' backtest (2021-2024) is data it already saw. The +13.6% ROI / 70% headline is a point-in-time simulation on seen fights; the *live* record only starts July 2026. Do not present the backtest ROI as a realized track record.
- **v1-v3 are honest and unremarkable:** low-60s accuracy, right in the clean-model band, and they lose to the closing line - exactly as an honest model should.
- **v4 (the stacker)** sits in the mid-60s on a small 2025+ sample; better than its base models but still short of the market. No leak flag, but the sample is thin.

**Bottom line for Reed:** the only models that look like they 'beat the market' are the two we already know are contaminated (v5 reads the closing line; v6 was tested on fights it trained on). Scored honestly - only inside a window the model never trained on, against the closing line - our clean engine calls about 61 of every 100 fights right and the closing line calls about 68. The market is still the thing to beat, and the way we beat it is finding spots where our price disagrees with the *opening* line and betting a quarter-Kelly slice - not by claiming a bigger accuracy number than Vegas.
