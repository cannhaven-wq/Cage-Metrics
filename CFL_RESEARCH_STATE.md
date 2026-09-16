# CFL research state

The register of what Cannon Fight Lab is currently testing, what is frozen, and
what has been withdrawn. One entry per experiment. `research/registry.json` is
the machine-readable mirror of this file; `tests/test_research_state.py` checks
both against what is actually on disk.

**Rule:** a number does not appear on a CFL surface — site copy, a post, a
README, this file — unless it can be traced to an artifact named here. A figure
whose source cannot be produced is withdrawn, not footnoted.

Last updated: 2026-09-16.

---

## Register

| id | what it asks | status | verdict |
|---|---|---|---|
| **DUR-001** | after the vig-free totals market is known, does PROP-0001 still add information about whether a fight goes over a round total? | collecting | none yet |
| **PROP-0001** | the frozen fight-duration model DUR-001 tests. Not itself an experiment — the artifact under test | frozen, serving locks | n/a |

---

## DUR-001 — does the duration model beat the totals market?

| field | value |
|---|---|
| status | **collecting**. First card (UFC 331, 2026-09-15) locked; no analysis run |
| preregistration | [`cfl_engine/dur001/PREREGISTRATION.md`](cfl_engine/dur001/PREREGISTRATION.md), frozen 2026-09-15 UTC |
| preregistration sha256 | `69fecf1c84893d736d998fba5ee93583c64806f8eb439a51f42f24f04aee8d94` |
| challenger | PROP-0001@v1 (see below) |
| benchmark | vig-free consensus of sportsbook round totals at the exact locked threshold |
| primary endpoint | out-of-sample log-loss gain `G_LL = LL_baseline − LL_challenger` |
| minimum useful effect | 0.003 per observation |
| observation unit | one (fight, threshold) row — **proposed** to become one fight, see amendment (b) |
| cluster unit | the UFC event |
| kill rule | **none in force.** Proposed: 2027-09-15 or 500 valid prospective observations, whichever first, then HOLD-PASSIVE — amendment (f) |
| verdict | none |
| verdict timestamp | none |

### What is on record

| | |
|---|---|
| locks | 48 rows, `prop_model_locks` ids 5–52, 12 fights × (3 thresholds + goes_distance) |
| ledger hash | `df3ab0cca0757eb9c452e9bfb0cede38` — `md5(string_agg(row_to_json(l)::text, '\|' order by id))` over the whole table, as computed by [`cfl_engine/dur001/health.py`](cfl_engine/dur001/health.py). **Verified 2026-09-16: reproduces exactly.** |
| first sportsbook quote | `prop_odds` id 7, captured 2026-09-15 02:05:21 UTC |
| results artifact | none yet |

### Lock provenance

**code_version `322a5b09e739-dirty` on all 48 locks; audit in
[`research/provenance/`](research/provenance/); rule going forward: no `-dirty`
locks, or store the full diff hash with the lock.**

Detail, from the 2026-09-16 audit:

- `322a5b0` is a 6-line workflow edit dated 2026-09-02 and is the **direct
  parent** of `6be7198`, the commit the preregistration names as the freeze. The
  locks were written from a 13-day-stale checkout carrying, uncommitted, the
  work that became `6be7198`.
- The dirty state **did** include model-generating code: `lock_prop0001.py`
  itself had no git history at lock time. The one frozen model file involved,
  `build_features.py`, changed only by a behaviour-preserving refactor.
- All 48 rows reproduce `predicted_probability`, `p_ends_r1..r3` and
  `p_decision` from their own stored hazards and phi. 48/48 at 1e-5, max error
  7.95e-7.
- The ledger hash verifies, so the rows are byte-for-byte what was frozen.
- `prop_model_locks` rejects UPDATE, DELETE and TRUNCATE by trigger for every
  role including `service_role`.

### Amendments

**In force — Amendment 1, 2026-09-16, approved by Reed Cannon:**

| item | decision |
|---|---|
| **(h) de-vig** | **Power method** is primary. Proportional and Shin are frozen sensitivities, reported beside it. No fourth method may be introduced, and the primary may not be swapped for a sensitivity after a result is visible. |
| **(i) historical timing** | **Candidate 1** — T−10 before the earliest provider start ever observed; moved starts **flagged and retained**; no extra Odds API credits. Candidate 2 is rejected and **not** kept as a sensitivity. |

Binding text is in
[`PREREGISTRATION.md` §Amendments](cfl_engine/dur001/PREREGISTRATION.md).
The backfill gate enforces (i): `self_consistent_walkback` earns a dedicated
`TIMING_REJECTED` refusal that asserting approval cannot buy past.

**Held — not approved:** items (a), (b), (c), (d), (e), (f), (g), (j), (k) in
[`AMENDMENT_DRAFT_2026-09-15.md`](cfl_engine/dur001/AMENDMENT_DRAFT_2026-09-15.md)
remain **PROPOSED**. Nothing that changes calibration, scoring or the market
comparison is decided while the walk-forward fold discrepancy is open; the
governance and monitoring items can be voted on individually once it closes.

### Open: the walk-forward fold discrepancy

A block walk-forward of the frozen recipe reproduces the panel, the fold
boundaries and the training sets of
[`walkforward_report.json`](cfl_engine/harness/walkforward_report.json)
**exactly** — every fold's `n_test` matches, and `n_train` for fold 0 is the
panel minus the test rows to the row. Data selection is ruled out.

One structural difference survives: the frozen report records folds 0 and 1 as
`calibrated: false`. `fit_prop0001` fits isotonic on the trailing 365 days, a
window that is never empty here, so under that recipe every fold calibrates.
**The gate report therefore did not use the calibration recipe the live locks
use, and cannot be cited as validation of it.** Which recipe it did use is
unconfirmed — the generator is not in the repository.

This is the blocker for the held amendment items. Nothing was tuned on either
side.

### Forbidden changes

- Retraining, re-featuring, re-calibrating or re-mapping PROP-0001 while the
  sample accumulates. Daily refits on a growing training set under the same spec
  are part of the procedure, not a change.
- Widening a model's evaluation window past its `test_start_date`.
- Selecting sportsbooks, or selecting thresholds after results are visible.
- Writing any historical backfill into `prop_model_locks`.
- Deriving 3.5 or 4.5 probabilities for five-round fights.

---

## PROP-0001 — the frozen duration model

| field | value |
|---|---|
| status | **frozen**, serving locks |
| model_version | `PROP-0001@v1` |
| freeze commit | `6be7198ebe4d56b27366268318b757e99e3074c5` |
| freeze timestamp | 2026-09-15 (UTC) |
| form | discrete-time logistic hazard, one hazard per round, isotonic recalibration on the trailing 365 days |
| features | 49 covariates from `build_features.covariate_columns()` |
| population | UFC fights scheduled for 3 rounds, 2010 onward, clean finish or decision |
| gate report | [`cfl_engine/harness/walkforward_report.json`](cfl_engine/harness/walkforward_report.json) — block walk-forward from 2018-01-01, 6-month blocks |

### Numbers with no source

**The 0.483378 / 3,793 figure was WITHDRAWN by the statistics director on
2026-09-15 pending an artifact.** It is not to be cited, republished, or used
as a baseline until the run that produced it can be named and its output
committed. Nothing currently in the repository reproduces it.

The figures that **do** have an artifact are the ones in
`walkforward_report.json` — pooled model log-loss 0.5037 against a constant
hazard's 0.5082 over 9,030 test rows in 18 folds, and 0.5059 against the
market's 0.5073 on the 8,565-row odds subset. Those are the only duration-model
performance numbers with a committed source, and they are a *gate* result, not
a DUR-001 result: they are measured against the model's own historical panel,
not against a pre-fight market on fights locked in advance.

---

## Frozen files

Changing any of these silently invalidates the experiments that rest on them.
`tests/test_research_state.py` fails if the bytes on disk stop matching.

| path | sha256 | frozen at |
|---|---|---|
| `cfl_engine/dur001/PREREGISTRATION.md` | `7bb30ffc4be103ae7d89db492e826aaa2d7f22c80385a66147c9662cc8103fe0` | `1bc3fdd`, **amended 2026-09-16** |
| `cfl_engine/dur001/dur001_analysis.py` | `b45ae7065f6af58cff69549e03f92668ce710f66d7bcb1037c9a6389f0c4071c` | `788386e` |
| `dur001_migration.sql` | `c9218d43bc877b09867754128fd14e8d5a93ac5e1d9ef2ed35f2a66c6eabcafe` | `6be7198` |
| `cfl_engine/dur001/lock_prop0001.py` | `2c052b234bbbe177255121d3bdd3c2252009828e7a6e42e08a1373555756dd2d` | `6be7198` |
| `cfl_engine/features/build_features.py` | `60f2c1c12131afa92a862ef09ab7ae496d05312b2b94096350115231ca79032f` | `6be7198` |
| `cfl_engine/models/duration.py` | `b0aea1d004a952630ca6bed461a89454d803c09fe15d008b9432d47842eb4d0b` | `90571ff` |
| `cfl_engine/harness/walkforward_report.json` | `d162850465a7ca5dd9c2eed22aed3ee600cd40d62009e6401855f35e6d6a368c` | `90571ff` |

All seven were verified on 2026-09-16 to be byte-identical to their freeze
commits. The preregistration has since been **amended once**, under its own
documented amendment procedure:

| amendment | date | hash before | hash after |
|---|---|---|---|
| 1 — de-vig method (h) and historical timing rule (i) | 2026-09-16 | `69fecf1c84893d736d998fba5ee93583c64806f8eb439a51f42f24f04aee8d94` | `7bb30ffc4be103ae7d89db492e826aaa2d7f22c80385a66147c9662cc8103fe0` |

To change a frozen file there are exactly two legitimate routes, and nothing
else:

1. **A dated amendment**, for the preregistration only, recorded in its own
   `## Amendments` section with its approver, its date and its reason, and
   logged in the table above with both hashes. The original §-text is never
   rewritten — the amendment states what it replaces.
2. **A new model version**, for anything else: bump `model_version`, write a new
   preregistration, add a new entry here. Locks written under the old version
   stay under the old version.

Editing in place and quietly updating the hash is neither of those, and is the
one move this table exists to prevent. `tests/test_research_state.py` fails on
any hash change; an amendment is the case where you update the recorded hash
*and* the amendment log *and* the preregistration's own `## Amendments` section
in the same commit. A hash change with no amendment recorded is a red flag, and
there is a test for that too.
