# PRED-001 — Prediction research protocol

**Status: frozen 2026-10-12, on the owner's instruction.** Changing anything
below is an L3 amendment (`coordination/CRITICAL_GATES.md` item 1): dated,
appended to the `## Amendments` section, with `motivated_by_observed_results`
recorded, and the new sha256 in `protocol.json`. The executable rules are in
[`pred_protocol.py`](pred_protocol.py) and the thresholds in
[`protocol.json`](protocol.json). If the prose and the code disagree, the code
is what ran. Fix the prose by amendment.

## Plain version

Bookmakers' closing prices already predict UFC fights well. Every model CFL
has built does worse than them. This protocol is how any new attempt gets
judged, written down **before** anyone tries, so nobody can move the goalposts
after seeing a result.

- **The market is the opponent, not a coin flip.** A model counts only if it
  makes better probability forecasts than the betting market, on the same
  fights.
- **The score is log loss.** It measures how surprised the forecast was by what
  actually happened. Lower is better. Accuracy, calibration, Brier and betting
  simulations are reported, but none of them decides anything.
- **Recent fights are locked away.** Fights from 1 January 2025 onward may not
  be used to build or tune anything. One independent check per model is
  allowed on 2025 to mid-2026, and there are ten such checks in total, ever.
- **Passing the locked-away check is not proof.** It only earns the right to a
  real test: forecasts written down before fights happen, then scored after.
  That is the only data on which nobody could have peeked at the answer.
- **The bar is set in advance, and so is "no".** A model is rejected if it does
  not beat the market on average, or if even its best case is too small to
  matter. A result that is too good is treated as a bug until shown otherwise.
- **This takes a long time, and that is a finding, not a delay.** A real but
  small advantage needs about 400 fights (roughly 10 months of UFC) to confirm
  if it is large (0.01 log loss), and about 1,650 fights (roughly 3.4 years)
  if it is 0.005. §6 has the arithmetic. There is no shortcut that is also
  honest.

---

## 0. Scope

This governs every experiment that produces a **win probability** for a UFC
fight and asks whether it carries information the betting market does not.
Fight-duration work is governed by DUR-001/DUR-002 and is untouched. Closing
line value is measured under CLV-001 and is untouched; this protocol **uses**
CLV-001 as the gate for any betting claim (§9). This protocol builds no model,
trains nothing, and starts no computer-vision work.

**Prior state, not recomputed here.** What has already been measured (v1–v6,
the engine, the market blend, the factor inventory) is inventoried by the
prediction-benchmarks session and in `cfl_engine/benchmark_report.md`. The
summary that matters: the engine's log loss is 0.054 worse than the BFO
closing consensus on 3,068 fights. The best market-plus-model blend gained
0.0034 over the market on about 3,070 fights. That gain was never tested for
significance, and it was fitted on years that are now sealed.

## 1. Roles

| role | who | may | may not |
|---|---|---|---|
| **Researcher** | any agent or person building a model | read and fit DEV data; run walk-forward inside DEV; write a preregistration; freeze an artifact | read H1, RESERVE, or any outcome on or after 2025-01-01; evaluate on sealed data; record a verdict |
| **Independent Auditor** | a session or person **that wrote none of the model's code or preregistration** (checked by git authorship and session id) | run the point-in-time audit; run `pred_protocol.evaluate` on sealed or prospective data at a pinned commit; append to `holdout_ledger.json` | change a model, a threshold, or the eligible fight set; evaluate an artifact twice on H1 |
| **Owner** | Reed | record the verdict (L3 item 3); approve amendments; approve any public claim (L3 item 8) | — |

The auditor computes the verdict **mechanically**. `evaluate()` returns it.
Recording it as the experiment's verdict is the owner's step, and the owner
records what the code returned, not an interpretation of it.

## 2. Data partitions and the holdout

| partition | dates | decided fights | with BFO close | use |
|---|---|---|---|---|
| **DEV** | through 2024-12-31 | 7,830 | 6,824 (623 events) | everything: fitting, tuning, feature selection, walk-forward |
| **H1** (sealed) | 2025-01-01 → 2026-07-11 | 789 | **713 (63 events)** | auditor only, one look per artifact, 10 looks ever |
| **RESERVE** (sealed) | 2026-07-12 → 2026-10-11 | 169 | 0 | nobody; no consistent benchmark exists for it |
| **PROSPECTIVE** | forecasts locked after freeze, before the fight starts | — | — | the confirmatory test |

Counts and sha256 fingerprints of the fight ids and the outcomes are in
[`holdout_manifest.json`](holdout_manifest.json). The outcomes were hashed
inside the database and never displayed.

**How access is prevented, and the limit of that.**

1. Development code reads fights only through `pred_protocol.dev_only()`, which
   **raises** on any sealed date rather than silently dropping it.
2. Experiment code lives in `research/experiments/<ID>/`. A test fails if any
   file there contains a direct database path (`supabase`, `psql`,
   `SUPABASE_`, `DATABASE_URL`, `create_client`). Data reaches an experiment as
   a DEV export, never as a live query.
3. Every look at sealed data is an entry in `holdout_ledger.json`, appended in
   the same commit as the result. The test enforces the budgets.
4. **The limit, stated plainly:** any agent holding database credentials *can*
   read `fights.winner_id` for 2025. Controls 1–3 make a sealed read visible
   and deliberate; they do not make it impossible. That is why **no claim rests
   on H1** (§9). Prospective outcomes do not exist when the forecast is locked,
   so no credential can leak them.

**H1 is not virgin, and this protocol says so** (manifest,
`known_contamination`). Published results for v4–v6 and the engine cover
2025–26. The Factor Lab computes its verdicts over all years, including H1.
An experiment whose features were chosen because a Factor Lab verdict looked
good has therefore selected on H1. It must declare that, and its H1 result is
recorded as **non-confirmatory**: it may proceed to a prospective test, but it
counts as no historical evidence. The engine was trained on data through
2026-07 and is ineligible for H1.

## 3. Point-in-time inputs

Every feature must have been knowable before the fight. "Knowable" means it
can be computed from rows dated strictly before the fight's `event_date`.
Same-card results are excluded: that was the 1990s tournament leak the engine
once had.

**Required in every preregistration: a feature manifest.** For each feature,
list the source table and columns, the time rule, and whether it is static.

**Forbidden sources**, because they hold today's value rather than the value
before the fight:

- `fighters`: `wins`, `losses`, `draws`, `ufc_wins`/`ufc_losses`/`ufc_draws`,
  `slpm`, `str_acc`, `sapm`, `str_def`, `td_avg`, `td_acc`, `td_def`,
  `sub_avg`, `age`, `division`, `last_fight_date`. Rebuild these from fight
  history as of the fight date, the way the engine does.
- The fight's own result columns: `winner_id`, `method`, `end_round`,
  `end_time`, and its own stat totals and `fight_rounds`.
- Any other model's outputs (`model_predictions`, `model_picks`,
  `model_edges`, `prop_projections`, `pre_fight_snapshots`). Their training
  windows overlap the holdout.
- Prediction-market prices at or after settlement, and any price beyond
  100-to-1.
- The corner label itself (see corner symmetry below).

**Allowed with a declared caveat:** `height_in`, `reach_in`, `stance` and
`dob`. These are present-day profile values, treated as fixed over time. Age
must be computed from `dob` and the fight date.

**The auditor's point-in-time audit** is a precondition. If it fails, the
verdict is INVALID.

1. Recompute every feature for at least 200 randomly drawn DEV fights, plus
   every scored fight, from a copy of the data cut off at each fight's
   `event_date` (strictly before it). Any difference from the submitted value
   is a failure.
2. Check the manifest against the forbidden list.
3. **Corner symmetry.** Corner A wins about 64% of UFC fights, because the
   A/B label is not random. A model must satisfy p(A beats B) = 1 − p(B beats
   A) to within 1e-6 on every scored fight
   (`pred_protocol.symmetry_violations`). Averaging both orderings is the
   accepted fix.

## 4. Benchmarks

| model type | primary benchmark | also reported |
|---|---|---|
| **no odds input** (standalone) | vig-free BFO closing consensus (proportional de-vig, both sides required) | the same comparison through a blend (below) |
| **odds as input** (a blend, or any model that reads a price) | the market probability **at the same timestamp** as the price the model read, de-vigged the same way | the closing benchmark |

- **The primary question is incremental information.** "Does the model know
  something the market doesn't" is tested as a combination of market and
  model, with its weights frozen on DEV. It is scored against the market quote
  it consumed. A standalone model may be submitted as is, but its paired
  spread against the market is about five times larger (§6), so it needs
  roughly 25 times more fights.
- **Historically, the only consistent close is BFO's closing consensus.** It
  carries a 1970 placeholder timestamp, so it is a closing *price* with an
  unknown time. It is fine as a probability benchmark and is never used for
  timing claims (CLV-001 R-13).
- **Prospectively,** the closing benchmark is CLV-001's closing-price proxy,
  and the same-timestamp benchmark is the eligible-book consensus at the
  instant the forecast was locked.
- De-vig sensitivity (power and Shin) is reported beside the primary result.
  It is never chosen after the fact.

## 5. Metrics

**Primary:** Δ = mean over scored fights of (log loss of market − log loss of
model). Positive means the model was better. Fights are scored once, from
corner A's side.

**Reported, never decisive:**

- Brier score for both.
- Accuracy for both.
- Calibration intercept and slope, from a logistic refit of the result on
  logit(p). These gate a pass (§7) but cannot create one.
- A reliability table in 10 bins.
- **Simulated betting**, under one fixed rule: flat 1 unit whenever model_p ×
  decimal_odds − 1 > 0 at the benchmark price. Report n, ROI and an
  event-bootstrap 95% range. Historical BFO consensus is **not a price anyone
  could bet**, and the write-up must say so next to the number.

**Abstention cannot help.** A fight the model declines is scored at the
market's probability, which adds zero. Coverage below 95% of eligible fights
is INVALID.

## 6. Uncertainty and sample size

**Uncertainty.** Whole cards are resampled: 10,000 times, seed 20261012,
percentile intervals. A card is the unit because its fights share a night and
a news cycle.

**What sets the sample size** is the spread of the per-fight difference
Δᵢ. It was measured on DEV only (2023–24, 643 fights, 85 events):

| comparison | SD of Δᵢ | floor used |
|---|---|---|
| standalone stats model vs close (v1–v3) | 0.311–0.317 | **0.32** |
| fixed 80/20 market-plus-model blend vs close | 0.062–0.063 | **0.064** |

Clustering by card measured 0.72–0.85. That is floored at 1, because a lucky
measurement is not a licence to need fewer fights.

**Fights needed**, one-sided test at 80% power
(`pred_protocol.required_n`):

| true gain | blend, H1 (α = 0.005) | blend, prospective (α = 0.01) | ≈ years at 480 priced fights a year | standalone, prospective |
|---|---|---|---|---|
| 0.020 | 120 | 103 | 0.2 | 2,570 |
| 0.010 | 479 | 412 | 0.9 | 10,277 |
| 0.005 | 1,914 | 1,645 | 3.4 | 41,108 |
| 0.003 | 5,316 | 4,568 | 9.5 | 114,188 |

**What this means, without softening.** H1's 713 fights can only detect a gain
of about **0.008** for a blend, and about **0.041** for a standalone model.
The best gain anyone has measured in this repo, 0.0034, is below what H1 can
see. A model with a real advantage that small will most likely come back
INCONCLUSIVE on H1. Confirming it prospectively would take most of a decade.
The protocol does not lower the bar to make this faster.

**Each prospective preregistration fixes, before its first lock:**

- a target gain δ ≥ 0.003;
- an SD of max(the class floor above, the SD the experiment measured on DEV);
- n_required = `required_n(SD, δ, 0.01, 0.8)`;
- the analysis date.

There is one analysis, at n_required. Before half of n_required, no rule
applies. From half onward, the only early stop is futility.

## 7. Decision rules

Implemented in `pred_protocol.evaluate`, and checked in this order:

| verdict | rule |
|---|---|
| **INVALID** | preregistration or artifact hash mismatch; point-in-time audit failed; corner symmetry failed; fewer than 20 events; coverage under 95%. **The ledger slot is still spent.** |
| **SUSPECT** | Δ > 0.015, or accuracy > 72%. Frozen until the auditor writes a leak audit. A found leak turns it INVALID. No leak found means the owner decides (L3 item 10). |
| **REJECT** — no meaningful incremental information | Δ ≤ 0; **or** the upper end of the 95% range is below 0.003; **or**, prospectively at half of n_required or later, that same upper end is below 0.003 (futility). |
| **UNDERPOWERED** | prospective, before n_required, and not futile. Never a pass. |
| **FAIL_CALIBRATION** | would otherwise pass, but the calibration slope is outside 0.8–1.25 or \|intercept\| > 0.1. |
| **PASS_H1** | the one-sided lower bound at α = 0.005 is above 0 **and** Δ ≥ 0.003. This licenses a prospective test, and nothing else. |
| **PASS_PROSPECTIVE** | the same rule at n_required, with α = 0.01 one-sided. |
| **INCONCLUSIVE** | anything else. Treated as a failure for every claim. |

**Independent verification.** A third party needs only:

- the commit hash;
- the frozen artifact;
- the ledger entry, which records the inputs' sha256 and the outputs;
- the eligible rows, re-derived from the manifest recipe.

From those, `evaluate()` reproduces the verdict exactly: the bootstrap is
seeded and nothing else is random.

## 8. Rules against leakage, cherry-picking and holdout optimisation

1. **One artifact, one look.** H1 scores a frozen artifact (model file sha256
   plus code commit) exactly once. A changed artifact is a new look and spends
   a new slot.
2. **Ten looks at H1, ever.** Each look runs at α = 0.005, so the chance that
   any of the ten passes by luck is held at 5% (Bonferroni). When the budget
   is spent, H1 retires and only prospective evidence counts.
3. **Five prospective confirmatory slots** at α = 0.01 each, for the same
   reason.
4. **Variants are chosen on DEV.** Picking the best of N variants on H1 is N
   looks. Each preregistration records `variants_tried_on_dev`: the honest
   count of configurations compared during development.
5. **No refit after a look.** An artifact that has been evaluated cannot be
   retrained, re-featured or recalibrated and resubmitted as the same
   experiment. A successor is a new experiment that names its predecessor.
   This is the DUR-001 `forbidden_changes` rule applied to win models.
6. **Every look is recorded before it is discussed.** The ledger entry and the
   verdict are committed together. Failures, INVALIDs and REJECTs stay in the
   ledger, and a test fails if an entry disappears.
7. **No subgroup rescue.** Results for subgroups (division, favourite or
   underdog, title fights) are descriptive. Only a subgroup named as the
   primary population in the preregistration can pass.
8. **Prospective locks are append-only and are written before the start.**
   This uses the same pattern as `prop_model_locks` and `pre_fight_snapshots`:
   the database rejects UPDATE and DELETE, and refuses a lock after the start
   time. Creating that table is a production migration (L3 item 5) and a
   prerequisite of any prospective experiment.

## 9. What may be claimed

| evidence | allowed statement |
|---|---|
| exploratory DEV result | none outside the experiment folder |
| PASS_H1 | internal only: "historical signal on sealed data; prospective test registered" |
| PASS_PROSPECTIVE | "added information beyond the market on N fights forecast in advance". **Public use still needs the owner (L3 item 8) and does not lift D-011 by itself.** |
| **betting advantage or profit** | requires all of: PASS_PROSPECTIVE; CLV-001's publication gate open (at least 100 scored observations across 20 events); and a positive lower bound on CLV_return for the same model's locked forecasts. Simulated ROI never qualifies. |

## 10. Preregistration requirements

Each experiment gets `research/experiments/<ID>/PREREGISTRATION.md`, copied
from [`EXPERIMENT_TEMPLATE.md`](EXPERIMENT_TEMPLATE.md), and an entry in
`research/registry.json` that follows the existing schema, with
`protocol: "PRED-001"`. Both are frozen, with their sha256 recorded, **before**
any request to the auditor.

## Amendments

None.
