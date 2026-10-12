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

## The run — the one look

- **Run:** GitHub Actions [38306859194](https://github.com/cannhaven-wq/Cage-Metrics/actions/runs/38306859194),
  2026-10-12 20:51:45–20:54:07 UTC, commit `bf1f2483147451b3b9d56a8c1334e8b0bbe89224`.
  The run commit is the freeze commit plus the workflow file. Its first step
  re-checked every frozen file against its recorded hash and passed.
- **Code:** `stage1.py` sha256 `2307e776…a3a535`, which is the frozen bytes.
- **Export:** manifest sha256 `35af166d…364eb0`. The data files are
  byte-identical to the preflight: fights.csv `cdb37e14…`, rounds.csv
  `79b482a7…`, fight_stats.csv `c9de8b49…`, fighters.csv `9796b9b6…`.
- **η = 0.10.** The point-in-time recheck found 0 mismatches in 200 fights,
  and the preflight had no failures.
- **Measured SD of Δ_M: 0.0929**; SD of Δ_B 0.0797. These would have sized the
  prospective test, which will not happen.
- **B and C coefficients:** per year in the run log. The B weight on the engine
  ran 0.14–0.27. In C, the engine's weight shrank to 0.03–0.18, and the
  ratings took on non-zero weights that did not improve the forecast.
- **Verdict: STOP_STAGE1.** S1.1, S1.2, S1.3 and S1.4 failed; S1.5 held. See
  [`STAGE1_REPORT.md`](STAGE1_REPORT.md) and
  [`stage1_result.json`](stage1_result.json).
