# DUR-001 — does PROP-0001 beat the closing totals market?

One question: **after the vig-free closing UFC totals market is known, does the
frozen PROP-0001 fight-duration model still add predictive information?**

Everything here is prospective. No historical sportsbook totals exist in the
database (`prop_odds` had 0 rows on 2026-09-14), so the experiment starts from
the first captured card and accumulates. Nothing is back-filled, nothing is
re-priced after a result is known, and the decision rules below were written
before any result existed.

## What PROP-0001 is (and is not)

| | |
|---|---|
| Model | `cfl_engine/models/duration.py` — discrete-time logistic hazard, one finish hazard per round of a 3-round fight, isotonic-recalibrated. |
| Features | `cfl_engine/features/build_features.py` — 49 point-in-time covariates (round-profile rates, fight-history rates, age/reach/height, stance + style matchups). Frozen 2026-08-06; `covariate_columns()` is the list. |
| Gate evidence | `cfl_engine/harness/walkforward_report.json` — walk-forward log loss 0.5037 vs 0.5082 constant hazard, all gates pass. |
| Freeze tag | `PROP-0001@v1` (`lock_prop0001.py::MODEL_VERSION`). The spec is frozen; training data grows daily. A spec change is a new version and new lock rows. |
| **Not** PROP-0001 | `prop_projections.p_distance` (`props_v1`) — that is a league-average baseline, identical for every fight. It is never used here. |

### Threshold mapping (frozen)

The hazard model gives per-round finish probabilities `h1, h2, h3`. A sportsbook
total of `X.5` rounds settles at 2:30 of round `X+1`, so we also need `phi_r`,
the share of round-`r` finishes that land at or before 2:30 (estimated
point-in-time from the training data, ~0.45):

```
P(over X.5) = S_X * (1 - phi_{X+1} * h_{X+1})     S_0 = 1, S_1 = 1-h1, S_2 = (1-h1)(1-h2)
P(distance) = S_2 * (1 - h3)
```

Every lock row stores `haz_r1..3`, `phi_r1..3`, the round-end split and the
49-feature row, so the probability can be recomputed without the model
(`test_lock_row_reproduces_probability_from_stored_hazards`).

Corner order: the training panel randomises corners, so a served fight is scored
under both orderings and the hazards averaged.

Scope: **3-round fights only**. Upcoming fights are scraped with
`scheduled_rounds = 3` by default, so main events and title fights are excluded
on their flags. The analysis additionally filters on the *actual* scheduled
rounds once the result is in.

## Ledgers (all private, all append-only)

| Table / view | Role | Immutability |
|---|---|---|
| `prop_odds` | every sportsbook totals quote: fight, book, line, over/under price, `captured_at`, `source_commence_at`, `is_live`, raw provider metadata | triggers reject UPDATE / DELETE / TRUNCATE |
| `fight_start_estimates` | every start-time observation per fight and source (`odds_api_commence` today) | triggers reject UPDATE / DELETE |
| `v_fight_start_best` | **close hierarchy**: `fights.bell_at` (actual bell) → latest provider commence → `event_date` 18:00 UTC fallback. `start_basis` says which tier answered. | view |
| `v_prop_odds_lifecycle` | per-quote opener / closer flags. **Close = last non-live quote strictly before `start_at`.** Carries `start_basis`, `lead_time`. | view (recomputed, so closes update when real bell times arrive) |
| `v_prop_odds_closing_consensus` / `v_prop_odds_opening_consensus` | median vig-free P(over) across books per (fight, line) | view |
| `prop_model_locks` | PROP-0001 predictions locked pre-fight | triggers reject UPDATE / DELETE / TRUNCATE; insert guard rejects `training_cutoff > actual_lock_at`, a fight with a result, or a lock at/after the best-known start |
| `v_prop_fight_duration` | elapsed seconds from ufcstats `end_round`/`end_time`; void flag | view |

`fights.bell_at` is never written from a provider guess. The fallback tier is
deliberately early (18:00 UTC) so a fallback close can be stale but can never
contain an in-play price.

Schema: [`dur001_migration.sql`](../../dur001_migration.sql) (repo root).

## Pipeline

```
build/fetch-odds.js  (hourly CI, .github/workflows/odds.yml)
   ├─ h2h  -> fight_odds            (unchanged moneyline path)
   ├─ totals -> prop_odds           (append-only; wantTotals() decides when the
   │                                 extra credit is spent — hourly within 6h of
   │                                 a start, even hours in the card window,
   │                                 daily baseline for openers)
   └─ commence_time -> fight_start_estimates

cfl_engine/dur001/lock_prop0001.py   (daily CI, .github/workflows/prop-locks.yml)
   -> prop_model_locks  one row per (fight, threshold 0.5/1.5/2.5, over) + distance
      trained ONLY on completed fights with event_date < today; first lock wins

cfl_engine/dur001/dur001_analysis.py  (run by hand once cards have settled)
   -> out_real/dur001/dur001_report.json + dur001_rows.csv
```

Commands:

```bash
# dry-run / replay the totals capture without spending a credit or writing
cd build && ODDS_FIXTURE=../cfl_engine/dur001/fixtures/odds_api_totals_fixture.json FORCE=1 node fetch-odds.js

# lock the next 8 days of cards (dry-run, then write)
python cfl_engine/dur001/lock_prop0001.py
python cfl_engine/dur001/lock_prop0001.py --execute

# the analysis (10,000 event-cluster bootstrap draws)
python cfl_engine/dur001/dur001_analysis.py --draws 10000

# pipeline check on synthetic events (never stored)
python cfl_engine/dur001/dur001_analysis.py --synthetic 40
python cfl_engine/dur001/dur001_analysis.py --synthetic 40 --synthetic-signal 1.0

# tests (pure-Python + a rolled-back DB probe when SUPABASE_ACCESS_TOKEN is set)
python -m pytest cfl_engine/dur001/test_dur001.py -q
```

## The analysis

One row = one (fight, sportsbook threshold) with a closing consensus **and** a
PROP-0001 lock at that exact threshold.

* **Market probability**: American → raw implied (`|A|/(|A|+100)` or `100/(A+100)`),
  two-way de-vig `p_over = q_over/(q_over+q_under)`, median across books, last
  non-live quote before the best-known start.
* **Outcome**: Over `X.5` wins iff elapsed time > `X*300 + 150` s (past 2:30 of
  round X+1); ending exactly at 2:30 is Under. Whole-number lines push on the
  bell and are excluded; no-contests are void and excluded.
* **Phase 5** raw: log loss, Brier, calibration intercept/slope, fight / event /
  book counts, coverage by threshold. `G_LL = LL_market − LL_CFL`.
* **Phase 6** residual (the real test), walk-forward by event, coefficients fit
  on prior events only:
  `baseline: logit(P) = α + β·logit(P_close)`
  `challenger: logit(P) = α + β·logit(P_close) + γ·[logit(P_CFL) − logit(P_close)]`
  Primary metric `G_LL = LL_baseline − LL_challenger` on fully out-of-sample rows.
* **Phase 7** event-cluster bootstrap: whole events resampled 10,000 times on the
  fixed OOS predictions; CI for `G_LL`, ΔBrier, calibration slope. Mean CLV and
  ROI are reported as null — DUR-001 places no bets.
* **Phase 8** opener test, walk-forward: predict `logit(P_close)` from
  `logit(P_open)` with and without `logit(P_CFL)`; compare OOS squared error.
  (Not `(close−open) ~ (CFL−open)`, which shares opener noise on both sides.)

## Pre-registered decision (frozen 2026-09-14, before any data)

PROMOTE the duration branch only if **all** of:

1. residual `G_LL > 0` out of sample;
2. event-cluster 95% bootstrap CI for `G_LL` excludes zero (lower bound > 0);
3. `G_LL ≥ 0.003` log loss per fight-threshold;
4. challenger Brier is not materially worse (ΔBrier ≤ 0.001);
5. challenger OOS calibration slope in [0.8, 1.2] and |intercept| ≤ 0.10.

REJECT if the CI upper bound is below 0.003 — an economically meaningful effect
is unlikely and the answer is not "add features". Otherwise HOLD and keep
collecting. Sportsbooks and thresholds are never selected after results are
visible; every posted line at every captured book enters the consensus.

## Historical safety rule (hard)

DUR-001 has no historical rows and none may be manufactured from the model
trained today. If a historical backfill is ever attempted it must:

1. produce PROP-0001 predictions **walk-forward**, refitting on completed fights
   with `training_cutoff < fight_start` for every historical fight, using the
   same frozen spec (`PROP-0001@v1`), and label the rows as a distinct
   `model_version` (e.g. `PROP-0001@v1-wf`) so they never mix with live locks;
2. never write them into `prop_model_locks` — the insert guard rejects any lock
   on a fight that already has a result, and that guard is not to be relaxed;
3. pair them only with sportsbook quotes that were genuinely captured before
   the fight (`captured_at < start_at`, `is_live = false`) — there is no
   historical totals feed on file, so today there is nothing to pair with.

The September 2026 model (trained through 2026-09-14) must never be used to
create predictions for fights before that date.

### Primary close-quality rule (2026-09-15)

Only closes whose start time is known enter the primary analysis:
`start_basis in ('bell_at', 'provider_commence')`. Rows resting on the
`event_date_fallback` are excluded from the closing benchmark, the market log
loss, the residual test, CLV and the verdict. `--include-fallback` runs them for
diagnostics only and labels the report as such.

## Known limits

* The Odds API job failed on every scheduled run from 2026-07-31 to 2026-09-15
  (`is_opener` NOT NULL violation on mixed-key bulk inserts). Fixed 2026-09-15;
  first real totals quotes landed the same day.
* Credits: totals add one credit per call. With the hourly card-window cadence
  the gating keeps a 4–5 card month around 400–430 of the 500 free credits.
  `ODDS_MARKETS=h2h` switches totals off.
* Close provenance is `provider_commence` until real bell times exist. Every row
  says so (`start_basis`), and the views recompute when `fights.bell_at` is filled.
* PROP-0001 is 3-round only; 5-round totals are out of scope by design.
* Isotonic recalibration is piecewise-constant, so fights with similar raw
  hazards receive identical calibrated probabilities. That is the frozen recipe.
