# PRED-002 — independent review of the Stage 1 thresholds (T-085)

**Reviewer:** ChatGPT, the project's specification and review role. It wrote
none of PRED-002's code or preregistration, so it is independent in the sense
PRED-001 §1 requires. **Reviewed:** [`AUDITOR_BRIEF_THRESHOLDS.md`](AUDITOR_BRIEF_THRESHOLDS.md),
[`PREREGISTRATION.md`](PREREGISTRATION.md) (draft) and PRED-001.
**Date:** 2026-10-12. **Relayed by:** the owner, verbatim below.
**Recorded by:** Claude, the researcher, who changed nothing in the verdict.

**Reviewed before any Stage 1 number existed.** Nothing had been trained or
scored when this review was given.

## Verdict

**RETAIN the proposed numerical thresholds S1.1–S1.6.**

| | threshold | verdict |
|---|---|---|
| S1.1 | Δ_B ≥ 0.002 | retained |
| S1.2 | Δ_B interval above 0 | retained |
| S1.3 | Δ_M ≥ 0.006, interval above 0 | retained |
| S1.4 | Δ_B > 0 in at least 6 of 9 years | retained |
| S1.5 | calibration slope 0.8–1.25, \|intercept\| ≤ 0.1 | retained |
| S1.6 | leak tripwires | retained |

## Pre-freeze amendments required

The two **conditions**:

1. **Minimum eligible-fight coverage**, defined from development data only and
   without examining experimental outcomes. → **Amendment A1**
2. **Disclosure of exclusions by year**, and of the population the findings
   apply to. → **Amendment A2**

And two further requirements:

3. **Pin the exact incumbent engine code commit and all benchmark
   dependencies.** → **Amendment A3**
4. **Every Stage 1 report must clearly separate** a historical research
   improvement from the prospective 0.010 target, and both from commercial
   profitability. → **Amendment A4**

## Instructions that came with the verdict

- Complete the normal verification, freeze the preregistration, and run
  Stage 1 **exactly once** under the established protocol.
- **Do not change thresholds in response to results. Report failure as
  failure.**

## How each was met

A1–A4 are written into `PREREGISTRATION.md` under *Pre-freeze amendments,
2026-10-12*, together with **A5**. A5 records implementation choices the draft
left open. The reviewer did not ask for it, and it is listed so that nothing
about the run is decided after the freeze. The thresholds in `stage1.py` are
checked against the preregistration by `tests/test_pred002_stage1.py`, and so
are A1's coverage floors and A4's report framing.
