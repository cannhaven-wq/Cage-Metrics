# DUR-002 Preregistration — PROP-0001@v2 (uncalibrated hazard)

> ## STATUS: DRAFT — NOT IN FORCE
>
> This document is **not frozen**. It takes effect only when Reed dates and
> signs §0, and not before. Until then no `PROP-0001@v2` lock may be written and
> no DUR-002 number may be computed.
>
> Freezing is a two-line edit — set the date in §0 and change this banner — plus
> a registry entry. It is deliberately left undone so the freeze date is the day
> Reed actually approves, not the day this was drafted.

---

## 0. Signature

| | |
|---|---|
| drafted | 2026-09-16 |
| **frozen** | **— not yet —** |
| approved by | — |
| first eligible card | the first card whose locks are written after the freeze |

---

## 1. Why this experiment exists

DUR-001 tests `PROP-0001@v1`, whose specification ends with an isotonic
recalibration step. During the 2026-09-16 provenance audit it emerged that the
historical gate report,
[`cfl_engine/harness/walkforward_report.json`](../harness/walkforward_report.json),
does **not** measure that pipeline: it measures the same hazard model with the
isotonic step bypassed (see
[`research/provenance/CALIBRATION_FINDING.md`](../../research/provenance/CALIBRATION_FINDING.md)).

So the specification the historical artifact actually evaluated has never been
run prospectively, and the specification running prospectively has never been
evaluated historically. DUR-002 closes that gap from the prospective side.

## 2. Full disclosure — what was seen before this was drafted

**This is the part a sceptical reader should check hardest, so it goes near the
top rather than in a footnote.**

Before this document was drafted, a walk-forward comparison of the two variants
on historical data was run and inspected. It showed the uncalibrated variant
scoring better: pooled log loss 0.5032 against 0.5180, on 13 of 18 folds.

**Those numbers are not the reason for this specification, and they may not be
cited as evidence for it.** They are recorded here so that nobody later
discovers them and concludes they were the hidden motive.

Selecting a model because it won a comparison you have already seen is model
selection on observed history. The reasons in §3 are the ones that count, and
each is checkable without reference to any score.

Consequently:

- No historical performance figure for `PROP-0001@v2` may appear in any DUR-002
  result, summary, or CFL surface.
- DUR-002's verdict rests only on fights locked **after** the freeze in §0.
- If the prospective result contradicts the historical comparison, the
  prospective result stands. That is the whole point of freezing first.

## 3. The specification, and why

### The rule

> **Model probability is the raw hazard-derived probability. No isotonic or
> other post-hoc calibration is applied. This specification was fixed before
> evaluation on subsequent locked fights.**

Concretely: identical to `PROP-0001@v1` in every respect — same 49 covariates
from `build_features.covariate_columns()`, same discrete-time logistic hazard in
`models/duration.py`, same point-in-time training rule, same threshold
mapping — except that `predict_hazard` is called with `calibrated=False` and no
`iso_` map is ever fitted or attached.

### Why this specification, on grounds independent of any score

1. **It is the simpler specification.** It removes a stage rather than adding
   one. Between two variants with no prospective evidence separating them, the
   one with fewer estimated components is the better default, and it is the
   easier one to reason about when something goes wrong.
2. **It is the specification the existing historical artifact evaluated.**
   Adopting it aligns the prospective pipeline with the only historical
   walk-forward evidence CFL actually holds for this model, instead of leaving
   the two permanently describing different objects.
3. **The calibration step's construction is questionable on inspection, not on
   results.** `fit_prop0001` fits the isotonic map on `base` — a model trained
   *without* the trailing year — and then applies it to `full`, refit on all
   rows *including* that year. A monotone correction estimated on one model's
   output scale is applied to another model's outputs. That is a defect visible
   by reading the code, and it would be a reason for concern even if the
   calibrated variant had scored better.

Reason 3 is the substantive one. Reasons 1 and 2 would justify the choice on
their own.

### What is NOT a reason

That the uncalibrated variant scored better on history. See §2.

## 4. Relationship to DUR-001 and PROP-0001@v1

DUR-001 continues **unchanged**. In particular:

- `PROP-0001@v1` is not modified, re-specified, or retired.
- Its 48 existing locks are **not** reinterpreted, regraded, or annotated with
  anything implying they were produced by a different recipe. They were produced
  by the calibrated recipe and they record it correctly.
- DUR-001's preregistration, endpoints and verdict rules are untouched.

The two run **in parallel**, each writing its own locks under its own
`model_version`. Neither reads the other's results before its own verdict.

A head-to-head comparison of v1 against v2 is **not** part of DUR-002 and is not
preregistered here. If it is ever wanted it needs its own preregistration, its
own endpoint and its own decision rule, written before either experiment
reports.

## 5. Frozen model

| item | value |
|---|---|
| model_name | `PROP-0001` |
| model_version | `PROP-0001@v2` |
| model code | `cfl_engine/models/duration.py`, unchanged |
| feature code | `cfl_engine/features/build_features.py`, unchanged, 49 covariates |
| calibration | **none.** `calibrated=False`; no `iso_` is fitted or attached |
| threshold mapping | unchanged from v1 (§3 of the DUR-001 preregistration) |
| lock table | `prop_model_locks`, `model_version = 'PROP-0001@v2'` |

v2 locks are written alongside v1 locks for the same fights. The lock table's
unique index is keyed on `model_version`, so both coexist without collision, and
its append-only triggers apply to both.

## 6. Inherited from DUR-001, unchanged

To keep the two comparable and to avoid smuggling in unrelated changes, DUR-002
adopts the following from `cfl_engine/dur001/PREREGISTRATION.md` **as amended by
Amendment 1**, by reference:

- §4 eligible fights;
- §5 eligible market rows;
- §6 market probability, **including Amendment 1.1's power de-vig** as primary
  with proportional and Shin as frozen sensitivities;
- §8 uncertainty (event-cluster bootstrap, descriptive until the sample
  supports otherwise);
- §10 outcome and settlement;
- §12 analysis timing;
- §13 what is not part of the experiment, **including Amendment 1.2's frozen
  historical timing rule**.

Any DUR-001 amendment adopted after this document is frozen does **not**
propagate to DUR-002 automatically. Propagation requires its own dated amendment
here.

## 7. Primary endpoint

As DUR-001 §7: walk-forward by event, coefficients fit on prior events only.

```
baseline:   logit(P) = α + β·logit(P_close)
challenger: logit(P) = α + β·logit(P_close) + γ·[logit(P_CFL_v2) − logit(P_close)]
G_LL = LL_baseline − LL_challenger
```

Minimum useful effect: **0.003** per observation, as DUR-001.

## 8. Decision rules

As DUR-001 §11, evaluated only on fights locked after the freeze in §0.

No verdict may be taken until the sample reaches the thresholds DUR-001's
decision rules require. One card is descriptive only.

## 9. Kill / checkpoint

Mandatory checkpoint at the earlier of **2027-09-16** or **500 valid prospective
observations**. If the verdict at the checkpoint is not PROMOTE, DUR-002 moves
to HOLD-PASSIVE: locks continue, no further analyst time is committed until the
sample doubles or the specification changes.

(DUR-001 has no kill rule in force — its equivalent is amendment item (f),
still held. DUR-002 carries one from the start because there is no reason to
repeat that gap.)

## 10. Forbidden

- Reintroducing isotonic or any other post-hoc calibration to `PROP-0001@v2`.
  That would be a third model version with its own preregistration.
- Citing any historical performance figure for v2 as evidence for or against it.
- Modifying `PROP-0001@v1`, its locks, or DUR-001's preregistration.
- Writing a v2 backfill into `prop_model_locks` under any circumstances.
- Comparing v1 and v2 head-to-head without a separate preregistration.
- Any amendment motivated by an observed result.

## Amendments

_None._
