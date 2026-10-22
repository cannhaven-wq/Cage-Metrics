# CFL Discovery Engine — Phase 1

**Plain version.** This tries hundreds of fight factors, one at a time and in
combination with the situation (five-rounder, title fight, heavyweight, how
lopsided the odds are, …), and asks one question of each: *does knowing this
make a better forecast than the betting market's closing price, on fights it
was not fitted on?* Every idea tried is written down with its result,
including every failure, so nobody can show only the winners.

It is a research tool. It produces no pick, no edge, and nothing for the
website. A "research lead" from this engine licenses exactly one thing: writing
a proper PRED-001 preregistration. See
[`REPORT_PHASE1.md`](REPORT_PHASE1.md) for what the first real run found.

## Run it

From `research/discovery/`:

```bash
pip install -r ../../cfl_engine/requirements.txt -c ../../cfl_engine/ci-constraints.txt
python -m cfl_discovery --data dev                 # the DEV export (obtain it first: WITHHELD.json; ~15-35 min, 100 permutations)
python -m cfl_discovery --data dev --permutations 0 --pit-dates 5   # quick look (~3 min) - still recorded
python -m cfl_discovery --data synthetic           # labelled synthetic world, planted reach effect
python -m cfl_discovery --data synthetic --planted-reach 0           # null world: should find nothing
```

Tests (from the repo root): `python -m pytest tests/test_discovery.py -q`
(about 3 minutes; runs three synthetic worlds end to end).

**Every run appends a line to [`ledger.jsonl`](ledger.jsonl) and writes
`runs/<run_id>/`. Commit both.** A run that is not committed did not leave the
machine, and a committed run cannot be removed without the test failing.

## The rules it obeys

| rule | where it is enforced |
|---|---|
| PRED-001 DEV only: no fight on or after 2025-01-01 is read | `export_dev.sql` filters in SQL; `data.load_dev` passes every row through `pred_protocol.dev_only()`, which raises; a test scans every committed data file for sealed dates |
| The data is the data PRED-001 froze | the loader recomputes the manifest's DEV id and outcome fingerprints and refuses on any difference |
| No database or network route in the code | `tests/test_discovery.py::ResearchFolderLint` (same patterns as PRED-001's experiment lint) |
| Thresholds cannot be loosened | `run.load_config` refuses a config whose minimum useful effect (0.003) or leak tripwires (0.015 log loss, 5 accuracy points) differ from `research/protocol/protocol.json` |
| The market is the opponent, log loss is the score | every candidate is `logit p = (1+g)·logit(q_close) + Σ b·x` — PRED-001's incremental form — scored by log loss against the de-vigged BFO close |
| Corner symmetry | every feature is A-minus-B (or a symmetric context that only multiplies one); no intercept; checked three ways (corner-swap rebuild of every feature, PRED-001's `symmetry_violations` on fitted models, a corner-reader detector) |
| Point-in-time | a random 25 cards are rebuilt from data cut off before the card, with the card's own results scrambled; every feature must match exactly |
| No selective reporting | the catalog is hashed before scoring; the shortlist is hashed before confirmation; every candidate's numbers in both periods are kept; the ledger is hash-chained and checked against `main` |
| No promotion | there is no tier above `RESEARCH_LEAD`, nothing writes to a database, the registry or a page |

## How a candidate is judged

1. **Screen (2010–2018, walk-forward by year).** Each year's model is fitted
   only on earlier years. A *single* factor is compared with the market after
   the market's own bias is corrected (so the factor gets no credit for the
   favourite–longshot shape). An *interaction* is compared with its own
   single factor, so it cannot borrow its parent's credit. Card-clustered
   standard errors; Benjamini–Hochberg at q = 0.10, split evenly between
   singles and interactions; Holm and a 100-shuffle permutation max-statistic
   are reported beside it.
2. **Shortlist** (at most 25), fixed and hashed before step 3 runs.
3. **Confirm (2019–2024, walk-forward).** Holm over the shortlist at 0.05,
   one-sided, and a card-bootstrap 95% range (10,000 resamples, PRED-001's
   seed) that must clear zero.
4. **Stability.** Positive in ≥ 60% of the fifteen years, the coefficient the
   same sign in ≥ 80% of folds and in both periods, and still positive under
   the power and Shin de-vigs.
5. **Size.** At least 0.003 log loss better than the market (PRED-001's minimum
   useful effect). Anything better than 0.015, or more than 5 accuracy points
   better, is quarantined as a probable leak.

Tiers, best first: `RESEARCH_LEAD`, `BELOW_USEFUL_EFFECT`, `UNSTABLE`,
`FAILED_CONFIRMATION`, `REJECTED_SCREEN`, `INSUFFICIENT_SAMPLE`,
`LEAK_SUSPECT`. Not tested, reported for context: `CONTEXT_MODEL` (many
features at once, and one model with no market input) and `CONTROL` (noise).

## Layout

```
research/discovery/
  README.md                this file
  REPORT_PHASE1.md         what the first real run found, failed, and needs next
  export_dev.sql           the read-only, DEV-only recipe behind data/dev/
  data/dev/                fights.csv, fighters.csv, DATA_MANIFEST.json (hashes)
  config/phase1.json       DISC-P1-v1, the configuration of ledger entries 1-2 (engine 1.0.0);
                           committed 33 s AFTER entry 1's run started (E4, below)
  config/v1_1.json         DISC-P1-v1.1, engine 1.1.0; used by every later run
  WITHHELD.json            files kept out of the repository, pinned by sha256 (D-034)
  cfl_discovery/           the engine (stdlib + numpy + pandas)
    data.py                load, PRED-001 guard, fingerprints, de-vig (proportional, power, Shin)
    features.py            point-in-time features + manifest (reuses cfl_engine/engine.py)
    candidates.py          the hypothesis catalog
    model.py               the market-offset logistic model
    evaluate.py            walk-forward, clustered statistics, BH / Holm / permutations
    leakage.py             manifest, corner-reader, point-in-time and corner-swap audits
    ledger.py              append-only hash-chained run ledger
    report.py              SUMMARY.md, per-fight predictions, symmetry check
    synthetic.py           labelled synthetic worlds with a planted effect
    run.py                 the pipeline
  ledger.jsonl             one line per run, hash-chained
  runs/<run_id>/           config, catalog, feature manifest, shortlist, results.json,
                           oos_predictions.csv, SUMMARY.md
```

Reused, not rebuilt: `research/protocol/pred_protocol.py` (de-vig, log loss,
card bootstrap, calibration, sample size, symmetry checker, DEV guard),
`cfl_engine/engine.py` (point-in-time career features and Elo),
`cfl_engine/clv/devig.py` (power and Shin de-vig). None of them is modified.

## Status after the 2026-10-21 consolidation (D-034)

This engine is CFL's one research framework; DISC-001
(`research/experiments/DISC-001/`) is kept as its independent cross-check.
An audit by a session that wrote neither project reproduced ledger entry 1
exactly ([`../consolidation/AUDIT_2026-10-21.md`](../consolidation/AUDIT_2026-10-21.md)).
Engine **1.1.0** fixes what it found; ledger entries 1-2 stay the record of
engine 1.0.0 and are not rerun.

- **E1 fixed.** The power/Shin stability check is evaluated on the fights
  where each method is defined (7 DEV fights for power and 3 for Shin are beyond the frozen helpers'
  97% band), the number left out is recorded in `devig_sensitivity`, and a
  method that was not evaluated fails the check. In 1.0.0 it was skipped and
  an empty check counted as passed.
- **E2 fixed (owner decision).** The 0.003 minimum useful effect is measured
  against the **re-weighted market**, so a factor gets no credit for the
  de-vig's own bias (worth up to +0.0023 in 2019-24 under the proportional
  method). The raw-market gain is still computed and shown beside it.
  PRED-001 itself is unchanged.
- **E3 fixed.** Features that measure a factor whose all-years verdict CFL has
  already seen (the Factor Lab's eight factors and `edges.js`'s record and
  takedown defence) carry `h1_contaminated`, as do features built on or standing
  in for one (`mu_grapple`, `mu_net_strike`, `d_dec_rate`, `d_last3_win_rate`);
  so does every candidate built on any of them. Such a candidate is non-confirmatory whatever its tier.
- **E4 recorded.** `config/phase1.json` and the catalog code were committed
  (`c112794d`, 20:02:24 UTC) 33 seconds *after* ledger entry 1's run began
  (`20261021T200151Z`). The ledger's config and code hashes match the
  committed files, but **that run cannot be shown to have been preregistered
  before it started**, and must not be described that way. Within the run,
  the catalog and shortlist were written before the stages that use them;
  nothing outside the run timestamps that. From v1.1 on: commit the config
  before the first real run that uses it.
- **Data stays out of the repository.** The DEV export and real per-fight
  predictions are git-ignored; `WITHHELD.json` pins each by sha256 and says
  how to obtain it. The ledger accepts an absent file only if it is withheld
  with the recorded hash. Tests that need the export skip, with the reason,
  when it is not on disk.
