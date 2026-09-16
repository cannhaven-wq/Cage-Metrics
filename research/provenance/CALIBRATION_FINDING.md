# The gate report measures the model without its calibration step

**Date:** 2026-09-16
**Status:** established, from two committed artifacts. Nothing was tuned.
**Tool:** `cfl_engine/dur001/diagnose_folds.py`

---

## Finding

> **`cfl_engine/harness/walkforward_report.json` reports the PROP-0001 hazards
> with the isotonic recalibration bypassed. The live locks apply it. The gate
> report is therefore not a validation of the recipe that writes the locks — it
> validates the same model without its final step.**
>
> **Separately: applying that isotonic step makes out-of-sample log loss worse,
> by 0.0148 pooled and on 13 of 18 folds.**

The first half is a labelling problem. The second is a question about the model,
and it is Reed's to decide, not one to fix by editing a frozen file.

## How it was established

A block walk-forward of the frozen recipe was compared fold by fold against the
gate report. The stages were separated so the earliest difference could be
isolated, since a difference at an early stage makes every later comparison
meaningless.

**Fold structure: identical.** 18 folds, same boundaries.

**Data selection: identical.** Every interior fold's `n_test` matches exactly,
all 17 of them. `n_train` for fold 0 is 6,724, exactly the reproduced panel's
rows minus its test rows, and in both reports `n_train` grows by precisely the
previous fold's `n_test`. The only row-count difference is the final partial
fold — 94 frozen against 193 here — because the two runs were generated on
different days (the gate is dated 2026-08-06; this run's data ends 2026-08-30).
9,030 + 99 = 9,129, exactly.

**Calibration: this is the difference.**

| | reproduced | frozen |
|---|---|---|
| pooled log loss, isotonic **applied** | 0.5180 | — |
| pooled log loss, isotonic **bypassed** | **0.5032** | — |
| frozen pooled log loss | — | **0.5037** |
| \|raw − frozen\| | **0.0005** | |
| \|calibrated − frozen\| | 0.0143 | |

Across the 17 folds scoring identical rows, mean |raw − frozen| is **0.00378**
and mean |calibrated − frozen| is **0.01329**. The raw series matches the frozen
report to 5e-4 on five folds; the calibrated series matches on none.

The two folds the gate report marks `calibrated: false` — 2018-01-01 and
2018-07-01 — are the ones where the reproduced **raw** log loss matches it to
four decimals (0.5552 vs 0.5553; 0.5002 vs 0.5002).

A 0.0005 pooled gap, fully accounted for by the final-fold data window, is not a
coincidence. The frozen report's `model_logloss` is the uncalibrated hazard.

## Why the isotonic step hurts

Offered as the most likely mechanism, not as an established claim.

`fit_prop0001` (in the frozen `lock_prop0001.py`) does this:

```python
cal_start = cutoff - 365d
pre, cal   = pp[pp.event_date <  cal_start], pp[pp.event_date >= cal_start]
base = DurationHazardModel().fit(pre, cov)   # fit WITHOUT the trailing year
base.fit_calibration(cal)                    # isotonic on that year, OOS to base
full = DurationHazardModel().fit(pp, cov)    # refit on ALL training rows
full.iso_ = base.iso_                        # carry base's map onto full
```

The isotonic map is honestly out-of-sample with respect to `base`. But it is
then applied to `full`, a model fit on strictly more data — including the very
year the calibrator was fit on. `full`'s raw hazards are not distributed like
`base`'s, so the map is being applied to inputs it was not estimated for. A
monotone correction fitted to one model's output scale, applied to another's,
can easily do net harm, which is what the per-fold `iso Δ` column shows:
negative on 13 of 18 folds, as far as −0.0505.

## What follows, and what does not

**Does follow:**

1. `walkforward_report.json` should be relabelled for what it measures. It is a
   valid gate result for the uncalibrated hazard model. It is not evidence about
   the calibrated recipe serving the locks.
2. Any CFL surface citing 0.5037 as validation of the live model is citing the
   wrong artifact.
3. The live-lock recipe has never been validated end to end on historical data.

**Does not follow:**

- That the 48 live locks are wrong. They are internally consistent, on record
  before the bell, and unchanged since — see `PROVENANCE_REPORT.md`. They were
  produced by the calibrated recipe, which is what they say they were.
- That the isotonic step should be removed. That is a model change: it needs a
  new `model_version`, a new preregistration, and locks written under the new
  version. **It is never an edit to the frozen recipe**, and it must not be
  decided by whichever variant scores better on this comparison — that would
  turn a provenance investigation into model selection, which is the specific
  failure this whole exercise exists to avoid.

## Reproducing

```
python cfl_engine/dur001/walkforward_prop0001.py --from-exports data/exports \
    --mode block --start 2018-01-01 --out out_real/prop0001_wf_block
python cfl_engine/dur001/diagnose_folds.py --run out_real/prop0001_wf_block
```

The diagnostic is read-only over two existing artifacts. It fits nothing and has
no option that could change either side.
