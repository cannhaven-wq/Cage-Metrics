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

- **Preflight on the real data, nothing scored** (GitHub Actions run
  38306307794, commit `36b3d72`). `--preflight-only` stops before any forecast
  is compared with a result, so under A5 it is not a look. Results:
  - the export holds 7,974 development-year fights, the last card dated
    2024-12-14, 6,953 of them priced; the `dev_only()` gate held;
  - coverage matches the count A1 was set from, fight for fight: 3,333 scored
    of 4,174, and every year between 76.9% and 84.4%;
  - η = 0.10, the smallest stat-prediction MSE (1.963, against 2.026 at 0.05
    and 2.006 at 0.20), chosen without reading a result;
  - the point-in-time recheck and the antisymmetry checks passed;
  - the engine's 15 walk-forward folds (2010–2024) trained.

  Export sha256 at preflight: fights.csv `cdb37e14…`, rounds.csv `79b482a7…`.
  The Stage 1 run re-exports; any difference is recorded below.

## The run

Filled in after the run: commit, export sha256, η, coefficients, SD of Δ_M,
verdict.
