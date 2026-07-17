# CFL Engine — one probability brain, two product faces

Walk-forward XGBoost fight model with leak-proof feature construction, rolling
calibration, a market-blend layer, tiered picks (Face 1 / accuracy) and an
edge/Kelly table (Face 2 / ROI), plus a leak-audit suite that runs on every
pipeline execution.

## Run it

```bash
pip install -r requirements.txt
python run_pipeline.py --fights fights.csv --stats fight_stats.csv \
    --fighters fighters.csv --outdir out/
# harness self-test on synthetic data:
python run_pipeline.py --synthetic --outdir out_synth/
```

Outputs: `report.md` (metrics, audit, both faces), `oos_predictions.csv`,
`edge_bets.csv`, `feature_importance.csv`.

## Data contract (3 CSVs)

**fights.csv** — one row per fight
| column | type | notes |
|---|---|---|
| fight_id | str | unique |
| event_date | date | ISO `YYYY-MM-DD` |
| fighter_a_id / fighter_b_id | str | corner order does NOT matter — the pipeline randomizes it |
| result | str | `a`, `b`, `draw`, `nc` |
| weight_class | str | optional |
| n_rounds_sched | int | optional, 3/5 |
| method | str | optional; `KO/TKO…`, `SUB…`, `DEC…` prefixes used for finish features |
| odds_a / odds_b | int | optional, American closing odds; Face 2 disabled without them |

**fight_stats.csv** — one row per (fight, fighter): `fight_id, fighter_id,
sig_landed, sig_attempted, td_landed, td_attempted, sub_attempts, knockdowns,
control_seconds, fight_seconds`

**fighters.csv** — `fighter_id` required; `dob`, `name` optional (dob enables
age features — worth having).

## Exporting from Supabase

`fight_stats` is your `fight_rounds` table aggregated to fight level. Pattern
(adapt column names to your schema):

```sql
select fr.fight_id, fr.fighter_id,
       sum(fr.sig_strikes_landed)    as sig_landed,
       sum(fr.sig_strikes_attempted) as sig_attempted,
       sum(fr.td_landed)             as td_landed,
       sum(fr.td_attempted)          as td_attempted,
       sum(fr.sub_attempts)          as sub_attempts,
       sum(fr.knockdowns)            as knockdowns,
       sum(fr.control_seconds)       as control_seconds,
       sum(fr.round_seconds)         as fight_seconds
from fight_rounds fr
group by 1, 2;
```

`fights.csv` comes from your `fights` joined to `events` for the date; odds
join from your BestFightOdds capture keyed on fight_id.

## What the audit will tell you

- **Corner-symmetry residual**: how orientation-sensitive the raw model is.
  Inference averages both orderings so published P(A)+P(B)=1 exactly; the
  residual is reported so you can see what the averaging is correcting.
- **PIT structural check**: recomputes prior-fight counts from the raw fights
  table and compares to the feature matrix. Any mismatch = your features are
  not point-in-time. Must be 0.
- **Too-good red flags**: OOS accuracy > 70% or log-loss beating the vig-free
  close by > 0.015 both indicate leakage, not genius. If these fire on your
  real data, do not celebrate — investigate.
- **Segment Brier vs market**: divisions where `model_minus_market` is worst
  are your no-bet zones. Abstention is free accuracy.

## Design decisions (the why)

- **One model, two faces.** Face 1 tiers and Face 2 edges both read from the
  same calibrated probability. Two separate models would publicly disagree and
  the accuracy-optimized one would emit distorted probabilities useless for EV.
- **Corner randomization + symmetric inference.** Kills the ufcstats
  winner-listed-first leak twice over: once in training data, once
  structurally at prediction time.
- **All career stats rebuilt chronologically** from the stats table with a
  2-year half-life recency decay. Present-day career averages are never joined
  onto historical fights.
- **Tuning happens only on the base window** (data preceding every evaluation
  slice). Early stopping inside each fold uses the tail of that fold's own
  training window. No evaluation row ever influences a hyperparameter.
- **Rolling calibration/blend**: the calibrator and market-blend for fold k
  are fit only on out-of-sample predictions from folds < k. Platt scaling for
  small pools (<1500), isotonic once there's enough data.
- **Blend layer** (`logit(model) + logit(market)` logistic stack) is what Face
  2 bets on. Expect the blend ≈ market with your model nudging it; edges come
  from disagreements that survive the blend, and there will be few. That is
  what a real edge looks like. A model that "beats the close everywhere" is
  broken, not brilliant.
- **Kelly is quarter-Kelly capped at 2%** because full Kelly on estimated
  probabilities is how bankrolls die.

## Honest limitations

- With only closing odds stored, Face 2's "edge" is model-vs-close. True CLV
  needs the line captured at bet time — build that capture into the product;
  it is your fastest-converging proof metric.
- ROI over a few hundred bets is noise. Publish CLV beat rate and calibration,
  not monthly ROI.
- `n_reg_fights` here counts fights inside your dataset. Fighters with pre-UFC
  careers look like debutants; a `pre_dataset_fights` column in fighters.csv
  is a cheap future upgrade, as are reach/height/stance diffs.
