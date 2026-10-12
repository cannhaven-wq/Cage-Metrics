# PRED-002 Stage 1 — result

> **What this is:** a historical research result on 2016–2024 fights. It decides only whether PRED-002 earns a prospective test.
> **What it is not:** it is not the prospective test. That test is sized for a gain of 0.010 per fight against the price at the moment of the forecast, and only it can support a claim.
> **And it is not a statement about money.** BestFightOdds consensus is not a price anyone could bet, and a log-loss gain says nothing by itself about beating a sportsbook's margin.

**Verdict: STOP_STAGE1**

- S1.1: gain over price plus engine -0.0002 (needs >= 0.002)
- S1.2: its 95% range -0.0028 to +0.0024 (needs to sit above 0)
- S1.3: gain over price alone +0.0015, range -0.0016 to +0.0045 (needs >= 0.006 and above 0)
- S1.4: positive over price plus engine in 5 of 9 years (needs 6)

## The numbers

| | per fight | 95% range (cards resampled) |
|---|---|---|
| gain over price plus engine (Δ_B) | -0.0002 | -0.0028 to +0.0024 |
| gain over price alone (Δ_M) | +0.0015 | -0.0016 to +0.0045 |
| price plus engine over price alone | +0.0017 | -0.0007 to +0.0039 |
| **for comparison: the prospective target** | **+0.0100** | — |

3333 fights on 372 cards. Log loss: market 0.6198, B 0.6181, C 0.6183.

## Conditions

| | held? | detail |
|---|---|---|
| S1.1 | **no** | gain over price plus engine -0.0002 (needs >= 0.002) |
| S1.2 | **no** | its 95% range -0.0028 to +0.0024 (needs to sit above 0) |
| S1.3 | **no** | gain over price alone +0.0015, range -0.0016 to +0.0045 (needs >= 0.006 and above 0) |
| S1.4 | **no** | positive over price plus engine in 5 of 9 years (needs 6) |
| S1.5 | yes | calibration slope 1.055, intercept +0.083 |

## By year

| year | fights | Δ_B | Δ_M |
|---|---|---|---|
| 2016 | 373 | -0.0070 | -0.0095 |
| 2017 | 332 | +0.0015 | +0.0058 |
| 2018 | 353 | +0.0034 | +0.0044 |
| 2019 | 372 | -0.0023 | -0.0008 |
| 2020 | 327 | +0.0023 | +0.0049 |
| 2021 | 395 | -0.0007 | +0.0015 |
| 2022 | 399 | +0.0027 | +0.0033 |
| 2023 | 363 | -0.0037 | -0.0005 |
| 2024 | 419 | +0.0023 | +0.0051 |

## Reported, never decisive

- Accuracy: market 65.0%, B 66.0%, C 65.8%.
- Calibration of C: slope 1.055, intercept +0.083.
- Δ_M under other de-vig methods: power -0.0001, Shin +0.0003.
- Simulated flat betting: 1331 bets, ROI -0.2% (range -6.2% to +5.8%). BestFightOdds consensus is not a price anyone could bet.

## Population (A2)

| year | priced, decided | excluded: no prior split fight (A / B / both) | scored | coverage |
|---|---|---|---|---|
| 2016 | 469 | 19 / 89 / 12 | 373 | 79.5% |
| 2017 | 430 | 35 / 78 / 15 | 332 | 77.2% |
| 2018 | 449 | 34 / 80 / 18 | 353 | 78.6% |
| 2019 | 482 | 45 / 79 / 14 | 372 | 77.2% |
| 2020 | 425 | 28 / 87 / 17 | 327 | 76.9% |
| 2021 | 468 | 21 / 59 / 7 | 395 | 84.4% |
| 2022 | 482 | 31 / 62 / 10 | 399 | 82.8% |
| 2023 | 472 | 40 / 78 / 9 | 363 | 76.9% |
| 2024 | 497 | 35 / 58 / 15 | 419 | 84.3% |

Findings apply to priced, decided UFC fights from 2016 to 2024 in which **both** fighters had at least one earlier UFC fight with round-by-round splits. They say nothing about debuts.

_Rendered by the frozen `stage1.render()` from `stage1_result.json`, which is copied verbatim from the job log of [run 38306859194](https://github.com/cannhaven-wq/Cage-Metrics/actions/runs/38306859194) at commit `bf1f248`._
