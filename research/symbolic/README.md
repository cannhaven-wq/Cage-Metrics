# research/symbolic — SYM-002 symbolic win-probability search (private research)

**Plain version:** this folder tests whether a short, written-down formula built
from each fighter's record *before* a fight can predict the winner better than a
plain weighted average of the same numbers, or better than the betting market.
It is private research. Nothing here feeds the website, writes to the database,
or produces a number for any public page — and under
[D-011](../../coordination/DECISIONS.md) nothing from it may appear on one.

**Results are not in this repository.** Raw exports, fitted models, candidate
logs and the written report live in `private/`, which is git-ignored in full.
This folder holds only the code and the rules that were frozen before anything
was fitted.

| file | what it is |
|---|---|
| [`PREREGISTRATION.md`](PREREGISTRATION.md) / [`config.json`](config.json) | the rules, frozen 2026-10-07 before any fitting (commit `f65e1a1d`) |
| `features.py` | point-in-time features: every number for a fight on date D comes from bouts strictly before D |
| `audit.py` | brute-force leakage checks, a truncation test, corner-order bias, odds-timestamp audit |
| `symreg.py` | the bounded symbolic-search engine |
| `run_experiment.py` | outer chronological folds 2021–2026 plus the final frozen fit |
| `report.py` | metrics, event-level bootstrap, calibration, seed stability, saved-model re-prediction check |

## Design guarantees

- **Corner swap is exact.** Every term is `h(A,B) − h(B,A)` and there is no
  intercept, so swapping the fighters turns P(A) into exactly 1 − P(A). The run
  checks this on every test row (max error is at machine precision).
- **No career averages as inputs.** The `fighters` table's `slpm`, `sapm`,
  `str_def`, `td_avg` and current `age` include the fight being predicted. They
  are loaded only under a `leaky_` prefix so the audit can measure the leak.
- **Corners are randomised** (seeded). In the raw table the listed fighter A
  wins far more often than half the time; any model with an intercept would learn that.
- **Bounded maths.** Protected division `x / (1 + |y|)`, every node clipped to
  ±20, NaN/∞ → 0, identically-zero terms rejected, L2-penalised weights.
- **Preprocessing is fold-local.** Scaling and the reach-from-height imputation
  are learned from the training rows of each fold (and of the inner split for
  selection), never from test rows.
- **Archived odds are labelled unverified.** Their timestamps are placeholders
  (1970-01-01). Timing-verified pre-start prices are kept in a separate column
  and never pooled with the archived ones. No ROI, no CLV.

## Running it

Data access: the container's network policy blocks the Supabase host, so the
exports were pulled through the Supabase connector with read-only `SELECT`s and
unwrapped by `private/data/ingest_connector_exports.py`. With direct database
access, any export producing the same five CSVs works (column lists in that
script).

```bash
pip install numpy pandas pyarrow
python features.py         # -> private/data/features.parquet
python audit.py            # -> private/results/audit.json
python run_experiment.py   # -> private/results, private/logs, private/models
python report.py           # -> private/results/metrics.json
```

The final models in `private/models/` are frozen by SHA-256 in
`private/models/FROZEN.json`. They may be scored only on events after
2026-10-07. The 2026 fights before that date have already been studied by CFL
and count as historical research, not as a confirmation set.
