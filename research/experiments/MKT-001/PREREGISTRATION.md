# MKT-001 — How should the bookmaker's margin be taken out of the historical closing odds?

**Internal research, DEV only (fights before 2025-01-01).** Written and
committed **before** `run.py` exists or anything below is computed under this
specification. Nothing here goes on a public page. A change after the commit
that freezes this file is a dated amendment below, with the reason.

## Plain version

A sportsbook's prices add up to more than 100% — that extra is its margin.
To turn prices into fair chances, the margin has to be taken out, and there
are three standard ways to do it. They give slightly different answers,
mostly for long shots. Yesterday's audit found that one of CFL's "findings"
was really just the choice of method. This study settles, on the historical
closing odds, which method gives the most accurate chances and how much
"re-weighting" each one can still gain. Every later test then knows how big
the free head start is that it must not take credit for.

## Disclosure — this is not a blind study

- Partial results are already known. The consolidation audit
  (`research/consolidation/AUDIT_2026-10-21.md` §4.1, script
  `research/consolidation/checks/reconcile.py`) computed the re-weighting gain
  under all three methods on three windows (2012–24, 2010–18, 2019–24) and the
  in-window calibration slopes. The power method looked best there.
- Author: Claude session `session_01TZy7rXSd57dkscoSB1MNiN`, which also wrote
  that audit.
- Variants tried before this file: those three windows, one model form
  (market slope only). Nothing else.
- So MKT-001 is **descriptive and consolidating**: a complete, fixed,
  by-era table on the whole DEV set, not a test that could surprise anyone.
  Its decision rule is fixed below anyway, so the reading cannot drift.

## What it does not do

- It does **not** change PRED-001. PRED-001's primary benchmark stays the
  proportional de-vig, with power and Shin as sensitivities (§4), and it may
  not be re-chosen after the fact. MKT-001 informs only (a) the "re-weighted
  market only" baseline every later win-probability study reports beside its
  result (D-034), and (b) which method the Discovery Engine's sensitivity
  checks should read first.
- It measures a consensus price nobody could bet (BT-001). No return, edge or
  profit is computed or implied.
- It reads nothing on or after 2025-01-01.

## Data

- The Discovery Engine's DEV export, `research/discovery/data/dev/fights.csv`,
  sha256 `5a5f1838d7585e68bb9041f93314a1caad7ec367e1408db866d93fe62924c2ee`
  (not committed, D-034; `research/discovery/WITHHELD.json` says how to obtain
  it). `run.py` refuses a file with any other hash, and passes every row
  through `pred_protocol.dev_only()`.
- Scored set: decided (winner is one corner), both BFO closers present,
  `is_active` not false — PRED-001's DEV set, **6,824 fights**; the run
  checks the count and PRED-001's DEV id and outcome fingerprints.
- Opener: the BFO opener for the same fights where both sides exist
  (ordered before the closer, not timed). Secondary and descriptive only.

## Methods compared

1. **Proportional:** `pred_protocol.devig_proportional`.
2. **Power:** find k with p_A^k + p_B^k = 1 (implied probabilities), fair
   p = p^k.
3. **Shin:** the standard Shin (1993) insider-proportion solution, normalised.

Power and Shin are implemented without CLV-001's 3%–97% market band (which
exists for bettable quotes, and would drop 7 historical fights). On every
fight inside the band they must equal `cfl_engine/clv/devig.py` to 1e-9; the
run fails otherwise.

## Measures

For each method, on all 6,824 fights and by era — **2007–2012, 2013–2016,
2017–2020, 2021–2024** (event year):

- mean log loss (natural log, clipped to [1e-4, 1 − 1e-4]); Brier score;
- calibration intercept and slope (`pred_protocol.calibration_fit`);
- a 10-bin reliability table (counts and observed rates, aggregate only);
- **walk-forward re-weighting gain:** for each test year 2010–2024, fit
  `logit p = a · logit q` on every scored fight from earlier years (no
  penalty), predict the test year; gain = mean[LL(q) − LL(re-weighted)] over
  2010–2024 and by era; 95% range from 10,000 card resamples, seed 20261012
  (`pred_protocol.cluster_bootstrap`).
- Descriptive: median overround (margin) of the closer and the opener, by era.

## Primary comparison and decision rule (fixed)

The paired per-fight log-loss difference for each pair of methods —
power vs proportional, Shin vs proportional, power vs Shin — over all 6,824
fights, with the card bootstrap. Two-sided p = 2 × min(share of resamples ≤ 0,
share ≥ 0), floored at 1/10,001; Holm at family-wise 0.05 over the three.

- If one method's log loss is lower than **both** others and both of its
  comparisons survive Holm: it is the **recommended reporting baseline** for
  the "re-weighted market only" figure.
- Otherwise: **no method is distinguishable**; later studies report all three.

Reported beside it, never changing it: the same comparisons by era, and how
often the eras agree on the ordering.

## What would change the plan

- If the recommended method's own walk-forward re-weighting gain has a 95%
  range that includes zero, later studies may treat "the market re-weighted"
  and "the market" as the same baseline under that method, and say so.
- If the eras disagree on the ordering, that is reported as instability and
  the recommendation carries that caveat.

## Amendments

none
