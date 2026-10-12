# PRED-002 — artifact record

What Stage 1 used and produced. Kept outside the hash-frozen preregistration
(§11), so it can be filled in without an amendment. Nothing here may change a
decision the preregistration fixed.

## Before the freeze: verification (no real data)

- **Synthetic end-to-end run.** `stage1.py` ran on the engine's own synthetic
  generator (`cfl_engine/make_synthetic.py`), with dates mapped onto 2004–2024
  and round splits derived from its strike totals. The run completed in about
  2 minutes. The point-in-time recheck found 0 of 200 mismatches, C was
  corner-symmetric to 2e-16, and η was chosen by stat error alone. Its
  synthetic market is unrealistically sharp (73% accuracy), and S1.6 tripped
  SUSPECT, as it should.
- **Sign check.** The same data with the market's prices deliberately blunted
  gave Δ_M = +0.062, which S1.6 flagged as SUSPECT. A sign error anywhere in
  the scoring would have shown here.
- `tests/test_pred002_stage1.py`: ratings never see their own fight or a
  same-night result, features are antisymmetric, a cut history reproduces the
  eve-of-fight state, the blend has no corner term, and every report opens with
  A4's framing.

## The run

Filled in after the run: commit, export sha256, η, coefficients, SD of Δ_M,
verdict.
