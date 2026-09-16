# What the harness reports actually measure

Read this before citing a number from `walkforward_report.json`.

Both reports in this folder are **frozen artifacts**. Neither may be edited —
this file exists so they can be relabelled without altering them.

---

## `walkforward_report.json` — the raw hazard model, not the PROP-0001 pipeline

**Relabelled 2026-09-16.** Established by
[`research/provenance/CALIBRATION_FINDING.md`](../../research/provenance/CALIBRATION_FINDING.md).

> **This report validates the underlying raw hazard model. It does NOT validate
> the calibration layer used in live PROP-0001 forecasts.**

### The accurate sentence

When describing what historical testing supports, use this:

> Historical walk-forward testing supports the underlying raw hazard model. The
> calibration layer used in live PROP-0001 forecasts was not validated by that
> historical artifact.

Do **not** write that PROP-0001 was "historically validated" end to end. It was
not, and saying so cites this file for a claim it does not make.

### The evidence

A faithful re-run of the frozen recipe reproduces this report's panel, fold
boundaries and training sets exactly — every interior fold's `n_test` matches,
and `n_train` for fold 0 equals the panel rows minus the test rows. What does
not match is the metric:

| | pooled log loss |
|---|---|
| reproduced, isotonic **applied** (the live-lock path) | 0.5180 |
| reproduced, isotonic **bypassed** | **0.5032** |
| **this report** | **0.5037** |

The 0.0005 gap against the bypassed series is fully accounted for by the final
partial fold's data window. Against the applied series the gap is 0.0143. The
two folds this report marks `calibrated: false` are the ones where the
reproduced raw series matches it to four decimals.

### What that means in practice

| claim | supported by this file? |
|---|---|
| the discrete-time hazard model beats a constant hazard out of sample | **yes** |
| the 49-covariate feature set carries duration signal | **yes** |
| the PROP-0001 *locking pipeline*, isotonic step included, performs as reported | **no** |
| `model_logloss` 0.5037 describes what the live locks produce | **no** |

The 48 live locks are unaffected. They are internally consistent, were on record
before the bell, and are unchanged since — see
[`research/provenance/PROVENANCE_REPORT.md`](../../research/provenance/PROVENANCE_REPORT.md).
They were produced by the calibrated recipe, which is exactly what they record.

### Reproducing

```
python cfl_engine/dur001/walkforward_prop0001.py --from-exports data/exports \
    --mode block --start 2018-01-01 --out out_real/prop0001_wf_block
python cfl_engine/dur001/diagnose_folds.py --run out_real/prop0001_wf_block
```

`diagnose_folds.py` is read-only over two existing artifacts. It fits nothing.

---

## `walkforward_counts_report.json`

The counts model's harness report. **Not audited.** No claim in this file
extends to it; if you are about to cite it, check first whether the same
raw-versus-calibrated question applies there too.

---

## The generator is not in this repository

Neither report has committed code that produces it. That is the underlying
defect behind the mislabelling: an artifact whose generator is absent cannot be
re-derived, so what it measures has to be established by forensics rather than
read off the source.

Any future harness report must be produced by committed code, and must record
in its own body which model variant it scored.
