# PRED-001 — Prediction research protocol

**Status: frozen 2026-10-12, on the owner's instruction; Amendment 1
2026-10-13, before any look.** Changing anything below is an L3 amendment
(`coordination/CRITICAL_GATES.md` item 1): dated, appended to the
`## Amendments` section, with `motivated_by_observed_results` recorded, and a
new entry in [`FREEZE.json`](FREEZE.json), which hashes every governed file —
this text, the code, the thresholds, the manifest, its SQL recipe, the H1 id
list and the test file. The executable rules are in
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
  if it is large (0.01 log loss), about 1,650 fights (roughly 3.4 years) if it
  is 0.005, and about 2,900 (six years) if it is 0.004. §6 has the arithmetic. There is no shortcut that is also
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
| **Independent Auditor** | a session or person **that wrote none of the model's code or preregistration** (checked by git authorship and session id) | run the point-in-time audit; run `pred_protocol.run_look` — the only sanctioned way to look, which evaluates and appends the hash-chained ledger entry in one step — at a pinned commit | change a model, a threshold, or the eligible fight set; evaluate an artifact twice on H1 |
| **Owner** | Reed | record the verdict (L3 item 3); approve amendments; approve any public claim (L3 item 8) | — |

The auditor computes the verdict **mechanically**. `evaluate()` returns it.
Recording it as the experiment's verdict is the owner's step, and the owner
records what the code returned, not an interpretation of it.

## 2. Data partitions and the holdout

| partition | dates | decided fights | with BFO close | use |
|---|---|---|---|---|
| **DEV** | through 2024-12-31 | 7,830 | 6,824 (623 events) | everything: fitting, tuning, feature selection, walk-forward |
| **H1** (sealed) | 2025-01-01 → 2026-07-11 | 789 | **710 (63 events)** | auditor only, one look per experiment, 10 looks ever |
| **RESERVE** (sealed) | 2026-07-12 → 2026-10-11 | 169 | 0 | nobody; no consistent benchmark exists for it |
| **PROSPECTIVE** | forecasts locked after freeze, before the fight starts | — | — | the confirmatory test |

Counts and sha256 fingerprints of the fight ids, the benchmark prices and the
outcomes are in [`holdout_manifest.json`](holdout_manifest.json); the exact
statement that produces them is [`holdout_manifest.sql`](holdout_manifest.sql)
and the ids themselves (no outcomes) are [`h1_fight_ids.txt`](h1_fight_ids.txt).
The outcomes were hashed inside the database and never displayed. Fights 43,
46 and 8780 are excluded: they were rebooked in place, so their stored prices
may belong to a different matchup.

**How access is controlled — conventions with tripwires, not a sandbox.**

1. Development code is expected to read fights through
   `pred_protocol.dev_only()`, which **raises** on any sealed date rather than
   silently dropping it. Nothing forces a researcher to call it.
2. Experiment code lives in `research/experiments/<ID>/`. A test fails if any
   non-Markdown file there names a database route (`supabase`, `psql`, a
   `postgres://` URL, `SUPABASE_`, `DATABASE_URL`, `create_client`,
   `psycopg`, the export or capture scripts), and if any committed data file
   there contains a date on or after 2025-01-01. Data reaches an experiment as
   a DEV export, never as a live query.
3. A look happens through `run_look`, which refuses a second look by the same
   experiment, a spent budget, or an auditor who is one of the authors, then
   evaluates and appends a hash-chained ledger entry in one step. A test
   verifies the chain and that no entry present on `main` disappears.
4. **The limit, stated plainly:** any agent holding database credentials *can*
   read `fights.winner_id` for 2025, and can import a helper from outside the
   experiment folder. Controls 1–3 make a sealed read visible and deliberate;
   they do not make it impossible. That is why **no claim rests
   on H1** (§9). Prospective outcomes do not exist when the forecast is locked,
   so no credential can leak them.

**H1 is not virgin, and this protocol says so** (manifest,
`known_contamination`). Published results for v4–v6 and the engine cover
2025–26. The Factor Lab computes its verdicts over all years, including H1.
An experiment whose features were chosen because a Factor Lab verdict looked
good has therefore selected on H1. It must declare that, and its H1 result is
recorded as **non-confirmatory**: it may proceed to a prospective test, but it
counts as no historical evidence. The engine was trained on data through
2026-07, and its walk-forward folds and market blend already span the sealed
window, so it is ineligible for H1: it cannot be first-opened on data it has
already seen.

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
  it consumed. **Confirmatory looks score the incremental form only.** A
  standalone model's result is reported beside it, never decides: its paired
  spread against the market is about five times larger (§6), so on H1 it
  could only clear the bar with a gain above the 0.015 leak tripwire.
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

**Fights needed** for an 80% chance of PASS when the true gain is as stated
(`pred_protocol.required_n(..., mue=0.003)`). PASS needs two things — the
lower bound above 0 **and** the estimate at least 0.003 — so the sample must
satisfy both. v1.0 sized for the first alone, which gives about 50% power at a
true gain of 0.003 (Amendment 1).

| true gain | blend, H1 (α = 0.005) | blend, prospective (α = 0.01) | ≈ years at 480 priced fights a year |
|---|---|---|---|
| 0.020 | 120 | 103 | 0.2 |
| 0.010 | 479 | 412 | 0.9 |
| 0.006 | 1,329 | 1,142 | 2.4 |
| 0.005 | 1,914 | 1,645 | 3.4 |
| 0.004 | 2,990 | 2,902 | 6.0 |
| 0.003 | not reachable: a target equal to the minimum useful effect can never be powered | | |

**What this means, without softening.** H1's 710 fights can only detect a gain
of about **0.008** for a blend, and about **0.041** for a standalone model.
The best gain anyone has measured in this repo, 0.0034, is below what H1 can
see. A model with a real advantage that small will most likely come back
INCONCLUSIVE on H1. Confirming it prospectively would take most of a decade.
The protocol does not lower the bar to make this faster.

**Each prospective preregistration fixes, before its first lock:**

- a target gain δ ≥ 0.004;
- an SD of max(0.064, the SD the experiment measured on DEV);
- n_required ≥ `required_n(SD, δ, 0.01, 0.8, mue=0.003)`;
- the analysis date.

These live in the experiment's `research/registry.json` entry, and
`load_registration` reads them from there and checks them against the frozen
preregistration on disk: the auditor cannot supply a different n.

There is one confirmatory analysis, on exactly the first n_required eligible
locks in lock order. Earlier looks are `PROSPECTIVE_INTERIM`: logged in the
ledger, never a pass, not counted against the budget, and before half of
n_required no rule applies. From half onward, the only early stop is
futility.

## 7. Decision rules

Implemented in `pred_protocol.evaluate`, and checked in this order:

| verdict | rule |
|---|---|
| **INVALID** | an outcome not 0/1, a market probability missing or outside (0,1), a model probability outside [0,1]; a duplicate fight; artifact not the one registered; point-in-time audit failed; corner symmetry failed; fewer than 20 events or under two fights per event; coverage under 95%; **an H1 fight set that is not exactly the manifest's**; a confirmatory prospective look not on exactly n_required fights. **The ledger slot is still spent.** |
| **SUSPECT** | Δ > 0.015, or the model's accuracy beats the market's on the same fights by more than 5 points. Frozen until the auditor writes a leak audit. A found leak turns it INVALID. No leak found means the owner decides (L3 item 10). |
| **REJECT** — no meaningful incremental information | Δ ≤ 0; **or** the upper end of the 95% range is below 0.003; **or**, at an interim look at half of n_required or later, that same upper end is below 0.003 (futility). |
| **UNDERPOWERED** | an interim look that is not futile. Never a pass. |
| **FAIL_CALIBRATION** | would otherwise pass, but \|slope − 1\| > max(0.2, \|market slope − 1\| + 0.1) or \|intercept\| > max(0.1, \|market intercept\| + 0.05). Judged against the market's own calibration on the same fights, so a blend is not failed for a bias it inherited. |
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

1. **One experiment, one look.** H1 scores an experiment's frozen artifact
   exactly once. Changing a byte of the artifact does not buy a second look:
   it is a new experiment, with its own preregistration and its own slot.
   Because PASS_H1 licenses nothing but a prospective test, successors and
   `variants_tried_on_dev` cannot turn repeated tries into a claim.
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
6. **Every look is recorded before it is discussed.** `run_look` writes the
   entry, hash-chained to the one before it, in the same step that computes
   the verdict. Failures, INVALIDs and REJECTs stay in the ledger; a test
   fails if an entry is edited, or if one present on `main` disappears.
7. **No subgroup rescue, and no subgroup H1.** H1 is scored on the whole
   sealed set or not at all. Results for subgroups (division, favourite or
   underdog, title fights) are descriptive.
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

### Amendment 1 — 2026-10-13

**Motivation:** an independent review commissioned by the owner the day after
the freeze, run twice before merge ([D-023](../../coordination/DECISIONS.md)). `motivated_by_observed_results: false` — the ledger was empty, no
look at H1 or at prospective data had been taken, and no model exists under
this protocol. The review showed that v1.0 could be bypassed with every test
green. Changes:

1. **Hash protection for everything governed** (review B1). `FREEZE.json` holds
   a hash history of the protocol text, the code, `protocol.json`, the manifest,
   its SQL, the H1 id list and the test file. The test pins the v1.0 entry and
   requires one dated `### Amendment` here per later entry.
2. **H1 inputs are facts checked against fingerprints, not numbers the caller
   supplies** (B2, rounds 2–3). Every fact must be a plain integer, and the
   same integers that are hashed are the ones scored — round 3 showed that
   hashing `int(x)` while scoring `x` let `1000.1`/`1000.2` split a card and a
   ±0.99 nudge on a price move the result. An export of a `numeric` column
   must cast to int (`-150.0` is refused). An H1 row carries the fight id, the card, the
   outcome, the two BFO closing American prices and the model probability;
   `evaluate` checks ids, outcomes, prices and card assignment against the
   manifest and de-vigs the prices itself. Round 1 checked only the ids, and
   flipping 5% of outcomes turned REJECT into PASS_H1. Subgroup H1 looks are
   removed (§8.7).
3. **Frozen values live inside the frozen file** (B3, round 2). The
   preregistration carries a ```` ```pred-registration ```` block —
   artifact hash, model class, target, SD, n_required, author sessions — and
   the registry must repeat it exactly. `load_registration` reads the block
   and checks it against the sample-size rule; a target above the 0.015 leak
   tripwire is refused. A test fails if a merged experiment's entry changes.
4. **Looks go through `run_look`, hash-chained, and only main counts** (B4).
   Budgets, one look per experiment, and an auditor who is a Claude session
   that is not an author are enforced before computing. Authors are read from
   the `Claude-Session` trailers of every commit that touched the experiment
   folder and every `code_paths` entry in the frozen block, as well as from
   the block's own list. On a push to `main` the
   anti-rewrite checks compare against the commit before the push, not main
   with itself. A crash is recorded as
   INVALID. Tests fail if a ledger entry, a FREEZE.json entry or a registered
   experiment present on `main` changes; CI fetches main and **fails, rather
   than skips,** when it cannot.
4a. **Prospective inputs are derived from the lock rows** (rounds 2–5). The
   unit is the **card**: cards are taken whole, in start order, from the
   experiment's first locked card, until the graded locks with unchanged
   corners reach n_required — so a confirmatory look scores at least
   n_required fights and never cuts a card in half. The model probability is
   the locked `p_a`; the market is the one frozen on the lock. **Every priced
   card in that run must be covered (round 5): every priced bout carries a
   lock row** — a forecast, or an **abstention lock** (`p_a` NULL, written
   before the bell like any other) that is scored at the market's probability
   and so adds nothing; abstentions above 5% make the look INVALID, as on H1.
   A bout first priced after the card's last lock is not owed one. Any other
   gap is INVALID: the round-4 allowance of one missing bout per card let a
   writer roll back the worst-scoring bout after the fight and gain more than
   the minimum useful effect. A card left out — skipped, or rolled back — fails
   the look. Locks on the next card, not yet in the population and not yet
   graded, are set aside; a graded lock on an unlisted card is INVALID. The
   population comes from the committed recipe
   [`card_population.sql`](card_population.sql) and its hash is recorded with
   the look; **the auditor re-runs the recipe and must get the same hash**,
   which is what catches a population trimmed at the front. Timestamps are
   parsed, never compared as text.
5. **Interim prospective looks are a separate, logged stage** (B5).
6. **Sample size covers both halves of the PASS rule** (S1). Minimum target
   raised from 0.003 to 0.004; the §6 table is recomputed.
7. **Bad inputs are INVALID**, not silently clipped (S2). Cluster ids compare
   as strings (N1).
8. **The accuracy tripwire is relative to the market** (S3), and
   **calibration is judged against the market's own** (S5).
9. **Confirmatory looks score the incremental form only** (S4).
10. **The manifest is reproducible** (S6): exact SQL, the H1 id list, a
    benchmark-prices fingerprint, and the exclusion of fights 43, 46 and 8780
    (rebooked in place). H1 is 710 fights, not 713.
11. **Access controls are described as conventions with tripwires** (S7). The
    experiment lint widens and committed data is scanned for sealed dates.
12. **The engine cannot be first-opened on H1** (INFO-AUDIT-001), now stated
    in §2 and the manifest.

13. **The lock table** (round 2): the lock time is `clock_timestamp()` — the
    wall clock at the insert, not the transaction's start, which a writer
    could open before the bell; the deadline is the card's earliest start,
    and a bout with only the event-date fallback counts from 00:00 UTC — in
    practice, locks are due by midnight UTC on fight day, the same schedule
    the pre-fight snapshot already keeps. A card in Australia, whose local
    date runs ahead of UTC, can still start before that fallback when no
    provider commence time is on file - a known gap, flagged for the auditor,
    not enforced by the guard; the quotes list must match the book
    count;
    one forecast per fight per experiment; the market snapshot is required;
    `event_date` comes from `events`; valid night-before locks are no longer
    refused.

**The trust model, said once.** Code in this repository cannot stop a person
with database credentials from computing a log loss on the sealed fights by
hand. What it can do is make the official record impossible to bend quietly:
only a ledger entry on `main` counts, every governed file and entry is frozen
against `main`, and every input to a look is checked or derived. That is why
**no claim rests on H1**: prospective outcomes do not exist when a lock is
written, and no credential can leak them.

Not changed: the partitions, the 0.003 minimum useful effect, the budgets and
their α, the leak tripwire on Δ, the benchmark, the claim ladder.
