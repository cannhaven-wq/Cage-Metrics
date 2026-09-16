# DUR-001 Preregistration

**Frozen:** 2026-09-15 (UTC), before any UFC 331 fight had settled and before any
sportsbook total had been compared with a PROP-0001 lock.
**Status:** binding. Any deviation from this document must be recorded as a
dated amendment below, with its reason, before the affected data is analysed.
Amendments may never be motivated by observed results.

## 1. Question

After the vig-free closing UFC fight-totals market is known, does the frozen
PROP-0001 fight-duration model still add predictive information about whether
a fight goes over a posted round total?

## 2. Hypotheses

- **H0:** conditional on the closing market probability, PROP-0001 carries no
  additional information. In the residual model of §7, γ = 0 and the
  out-of-sample log-loss gain G_LL = 0.
- **H1:** PROP-0001 carries additional information: G_LL > 0 out of sample.

Secondary (non-decision) question: does PROP-0001 carry information before the
market fully incorporates it (opener test, §9).

## 3. Frozen model

| item | value |
|---|---|
| model_name | `PROP-0001` |
| model_version | `PROP-0001@v1` |
| model code | `cfl_engine/models/duration.py` (discrete-time logistic hazard, one hazard per round, isotonic recalibration on the trailing 365 days) |
| feature code | `cfl_engine/features/build_features.py`, 49 covariates from `covariate_columns()` |
| lock script | `cfl_engine/dur001/lock_prop0001.py` |
| freeze commit (model + features + lock script) | `6be7198ebe4d56b27366268318b757e99e3074c5` |
| analysis commit | `788386e46db5c03a207b93d00a5ea13f915c01da` |
| main at preregistration | `3ce2bf1b802d016ed9a4d46506815277d90811e1` |
| first 48 locks (UFC 331, 12 fights) | `prop_model_locks` ids 5–52, ledger hash `df3ab0cca0757eb9c452e9bfb0cede38` (md5 of row_to_json ordered by id) |
| first real sportsbook quote | `prop_odds` id 7, captured 2026-09-15 02:05:21 UTC |

PROP-0001 is not retrained by hand, re-featured, re-calibrated, or re-mapped
while the sample accumulates. Daily refits on a growing training set under the
same spec are part of the frozen procedure, not a change. Any spec change is a
new `model_version` with new lock rows and its own preregistration.

## 4. Eligible fights

A fight enters the sample only if all hold:

1. UFC event, scheduled for **3 rounds**, not flagged main event or title fight
   at lock time, and the *actual* scheduled rounds are 3 once the result is in;
2. a PROP-0001 lock exists in `prop_model_locks` with `model_version = PROP-0001@v1`,
   written before the fight's best-known start (enforced by the insert guard);
3. the fight settles with a finish or decision. No-contests, overturned results,
   and "could not continue" are void and excluded;
4. the fight was not a dead or duplicate booking.

Five-round fights are excluded permanently. No 3.5 or 4.5 probabilities are ever
derived for them.

## 5. Eligible market rows

One analysis row is one (fight, threshold). It enters only if all hold:

1. the sportsbook threshold **exactly equals** a locked PROP-0001 threshold
   (0.5, 1.5, 2.5). No interpolation, extrapolation, or nearest-line mapping;
2. at least one non-synthetic, non-live quote (`is_live = false`,
   `source <> 'synthetic'`) captured strictly before the fight's start;
3. the fight's start basis is `bell_at` or `provider_commence`.
   `event_date_fallback` rows are diagnostics only and never enter the primary
   analysis;
4. the lock's `actual_lock_at` is not after the latest closing quote.

Sportsbooks are never selected. Every book that posts the exact threshold is in
the consensus. Thresholds are never selected after results are visible.

## 6. Market probability

- American → raw implied: negative `q = |A| / (|A| + 100)`, positive `q = 100 / (A + 100)`.
- Two-way de-vig per book: `p_over = q_over / (q_over + q_under)`.
- **Close** per book = last non-live quote strictly before `v_fight_start_best.start_at`.
- **Closing consensus** = median of per-book vig-free `p_over` across eligible
  books at the identical threshold (`v_prop_odds_closing_consensus`).
- **Opening consensus** = the same median over each book's first quote
  (`v_prop_odds_opening_consensus`).

## 7. Primary test (residual model)

Walk-forward by event, chronological. For each scored event, coefficients are
fit on prior events only (minimum 8 prior events and 40 prior rows):

```
baseline:   logit(P) = α + β·logit(P_close)
challenger: logit(P) = α + β·logit(P_close) + γ·[logit(P_CFL) − logit(P_close)]
```

Newton logistic regression with ridge 1e-3 on slopes only. Both models score
the held-out event. Pooled out-of-sample log loss:

```
G_LL = LL_baseline − LL_challenger      (positive = CFL adds information)
```

Also reported: Brier, calibration intercept and slope of the challenger, and
the raw comparison `LL_market − LL_CFL` (informational only).

## 8. Uncertainty

Event-cluster bootstrap: resample whole UFC events with replacement, 10,000
draws, on the fixed out-of-sample predictions (no refitting inside the
bootstrap). Report 95% percentile intervals for G_LL, ΔBrier, and calibration
slope. Individual fights are never resampled.

## 9. Secondary test (opener)

Walk-forward OLS predicting `logit(P_close)` from `logit(P_open)` with and
without `logit(P_CFL)`; compare out-of-sample squared error. Not a decision
input.

## 10. Outcome and settlement

Over `X.5` wins iff elapsed fight time > `X·300 + 150` seconds (past 2:30 of
round X+1). Ending exactly at 2:30 settles Under. Elapsed time comes from
ufcstats `end_round` and `end_time`; a decision is the full scheduled time.
Whole-number lines that end exactly on a round bell push and are excluded.

## 11. Decision rules

PROMOTE the duration branch only if **all** of:

1. G_LL > 0 out of sample;
2. the 95% event-bootstrap interval for G_LL has lower bound > 0;
3. G_LL ≥ 0.003 per fight-threshold row;
4. challenger Brier − baseline Brier ≤ 0.001;
5. challenger calibration slope in [0.8, 1.2] and |intercept| ≤ 0.10.

REJECT if the interval's upper bound is below 0.003. Otherwise HOLD and keep
collecting. No ROI thresholds are optimised. No bets are placed by this
experiment; CLV and ROI are reported as null.

## 12. Analysis timing

No performance number is computed for a card until every eligible fight on it
has settled. The first card (UFC 331) produces a descriptive table only
(`P_CFL`, `P_open`, `P_close`, `Y` per row); no decision is taken from one card.
The decision rules are evaluated only on the full accumulated sample.

## 13. What is not part of DUR-001

Significant strikes, takedowns, moneylines, cardio, new duration features, and
any historical backfill from the current model. A historical backfill, if ever
attempted, must be walk-forward with `training_cutoff < fight_start`, carry a
distinct `model_version`, and never be written to `prop_model_locks`.

## Amendments

### Amendment 1 — 2026-09-16 — de-vig method and historical timing rule

**Approved by:** Reed Cannon, 2026-09-16.
**Status:** in force.
**Motivation:** both items fix a *definitional* choice that must be settled
before more data accumulates. Neither was motivated by an observed result: no
UFC 331 outcome had been inspected when they were drafted or approved, no
DUR-001 performance number has been computed, and the verdict machinery in §11
is untouched by this amendment.

Recorded here rather than by rewriting §6 and §13, so the original text stays
legible and the change is dated.

---

#### 1.1 — De-vig method (amends §6)

§6 currently reads:

> - Two-way de-vig per book: `p_over = q_over / (q_over + q_under)`.

**Amended to:**

> - **Primary de-vig: the power method.** Per book, solve for the single
>   exponent `k > 0` satisfying
>
>   ```
>   q_over^(1/k) + q_under^(1/k) = 1
>   ```
>
>   and take `p_over = q_over^(1/k)`. Solved by bisection on `k` over
>   `[0.5, 5.0]` to a tolerance of 1e-10; the sum is strictly decreasing in `k`,
>   so the root is unique. A book whose two-way overround is non-positive, or
>   for which no root exists in that bracket, is dropped from the consensus for
>   that (fight, threshold) and the drop is logged.
>
> - **Frozen sensitivity: proportional de-vig**, `p_over = q_over / (q_over + q_under)`,
>   reported beside the primary and never in place of it.
>
> - **Frozen sensitivity: Shin (1993)**, reported beside the primary.
>
> No further de-vig method may be introduced. The three named here are the
> complete set for the life of DUR-001, and the primary may not be swapped for a
> sensitivity after any result is visible.

**Reasoning.** The power method carries a cleaner assumption set for a two-sided
market: it is transparent, monotonic, and makes no claim about *why* the margin
is distributed as it is. Proportional de-vig is known to under-price favourites
and over-price longshots. Shin is retained as a sensitivity rather than promoted
because using it as the primary leans on its insider-trading interpretation,
which is a substantive claim about UFC round-totals markets that CFL has no
evidence for.

Naming all three now, with one fixed as primary, is the point: the choice of
de-vig cannot become a free parameter searched after the fact.

---

#### 1.2 — Historical timing rule (amends §13)

§13 requires a historical backfill to be walk-forward but does not say which
historical quote is the benchmark. That gap is closed:

> **Historical pre-fight benchmark (the "T-10 historical pre-fight benchmark").**
> For each fight, the benchmark quote is the last snapshot at or before
> **T − 10 minutes**, where T is the **earliest provider start time ever
> observed** for that fight across all stored snapshots.
>
> A fight whose observed provider start moved after capture is **flagged** in
> the output and **retained**. No fight is excluded on the basis of a capture
> property.
>
> This rule spends **no additional Odds API credits**: it reads only snapshots
> already stored.

**Reasoning.** The rejected alternative walked back through 5-minute snapshots
to find the latest one that still believed the fight had not started, and
excluded fights where none qualified. Excluding a fight because its card became
chaotic conditions the dataset on events that occur *after* the sampling
decision was made — the cohort stops being defined prospectively. Flagging
preserves the cohort and still allows a chaos split as a zero-cost sensitivity.

The rejected candidate is **not** retained as a sensitivity. Keeping both would
reintroduce exactly the choice this amendment exists to remove.

---

#### 1.3 — What this amendment does not do

Explicitly unchanged, and still **PROPOSED** only, in
[`AMENDMENT_DRAFT_2026-09-15.md`](AMENDMENT_DRAFT_2026-09-15.md): items (a)
consensus book minimum, (b) one line per fight, (c) the two-questions split,
(d) the verdict rule, (e) cluster-CI gating, (f) the checkpoint, (g)
terminology, (j) `market_last_update`, (k) the dirty-tree guard.

Nothing touching calibration, scoring, or the market comparison is approved
while the walk-forward fold discrepancy is open. The backfill gate in
`research/dur001_backfill/` stays shut on every axis other than the timing rule
frozen above.
