# WIN-001 — DEV walk-forward results (exploratory; no claim outside this folder)

Produced by `dev_walkforward.py` on 2026-10-20 from the DEV export in `data/`
(`DATA.md`). PRED-001 §9: an exploratory DEV result supports **no statement
anywhere else**. Machine-readable copy: `DEV_RESULTS.json`.

**Design.** For each test year 2019–2024 the variant is fitted on priced,
decided DEV fights dated before 1 January of that year and scored on that
year; 2,826 fights scored in all. Δ is mean per-fight (LL_market − LL_model),
positive = model better. The 95% range is a 2,000-draw bootstrap over events
(seed 20261012).

| variant | Δ | SD of Δᵢ | 95% range | acc model / market | cal. intercept / slope |
|---|---|---|---|---|---|
| market_only (re-scaled market, no stats) | +0.0022 | 0.033 | +0.0012 … +0.0033 | 67.0 / 67.0 | +0.08 / 1.11 |
| elo | +0.0023 | 0.034 | +0.0011 … +0.0034 | 67.0 / 67.0 | +0.08 / 1.11 |
| elo_age_record | +0.0022 | 0.070 | −0.0006 … +0.0049 | 67.5 / 67.0 | +0.11 / 1.06 |
| **full_c1 (chosen)** | **+0.0046** | **0.119** | **+0.0000 … +0.0093** | 67.8 / 67.0 | +0.12 / 1.03 |
| full_c01 | +0.0045 | 0.116 | −0.0000 … +0.0091 | 67.8 / 67.0 | +0.12 / 1.05 |
| full_c001 | +0.0019 | 0.104 | −0.0022 … +0.0059 | 67.7 / 67.0 | +0.12 / 1.17 |
| standalone full (no market input) | −0.0464 | 0.265 | — | 61.0 / 67.0 | — |

Market's own calibration on the same 2,826 fights: intercept +0.078, slope
1.23. The model's intercept is within PRED-001's relative margin of the
market's (both carry the corner-A bias — corner A won 57.5% of these fights
and neither has an intercept to absorb it); the model's slope is nearer 1.

Per-year Δ for the chosen variant: 2019 +0.0011, 2020 +0.0067, 2021 +0.0040,
2022 +0.0011, 2023 +0.0035, 2024 +0.0114. `market_only`: +0.0004, +0.0013,
+0.0020, +0.0024, +0.0026, +0.0045.

**What this says, plainly.**

1. The formula beats the closing line on 2019–2024 by about 0.0046 per
   fight, and the lower end of its range touches zero. That is above the
   0.003 minimum useful effect but not confidently so.
2. **About half of it is not the stats.** Re-scaling the market's own logit
   by 1.1 with no fighter information at all gains 0.0022: proportional
   de-vig overstates underdogs, and a fitted weight corrects it. The stats
   add roughly 0.0024 on top — below the minimum useful effect on their own.
3. The spread of the per-fight gain (SD 0.119) is nearly twice the protocol's
   0.064 floor, because a fitted blend disagrees with the market more than a
   fixed 80/20 one. That spread, not the gain, is what sets the sample size:
   **5,685 prospective fights, about twelve years**, to confirm a true 0.005.
4. A standalone version (no market input) loses to the market by 0.046 per
   fight and 6 points of accuracy. The market is the opponent, and it is a
   strong one.
5. Elo alone adds nothing to the market (+0.0023 vs +0.0022 for the re-scaled
   market). The rating is already priced in.

Weights of the frozen artifact (per DEV standard deviation of each A − B
difference): market logit +1.105; sa_pm −0.183 (absorbing more strikes is bad);
age −0.136 (older is bad); win_rate −0.109 and kd_p15 −0.070 (negative *after*
the market and Elo have spoken — the market overrates a gaudy win rate and
knockdown count); sl_pm +0.077; td_p15 +0.050; finish_rate +0.045;
n_fights +0.037; reach +0.025; the rest under 0.02 in magnitude. These are
descriptive and were not used to select features.
