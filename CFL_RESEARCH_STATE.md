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
| **DUR-001** | after the vig-free totals market is known, does PROP-0001@v1 still add information about whether a fight goes over a round total? | collecting | none yet |
| **DUR-002** | the same question for `PROP-0001@v2` — the uncalibrated hazard | **DRAFT, not frozen** | none |
| **PROP-0001** | the frozen fight-duration model. Not itself an experiment — the artifact under test | frozen, serving locks | n/a |

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
remain **PROPOSED**.

The calibration blocker is now closed, and that does **not** make the remaining
clauses automatically sound. They are not approved en bloc. Each gets an
individual vote on its actual clause text:

- **Higher scrutiny** — anything changing data eligibility, scoring, model
  behaviour or how a claim is interpreted: (a) book minimum, (b) one line per
  fight, (c) the two-questions split, (d) the verdict rule, (e) cluster-CI
  gating, (g) terminology.
- **Lower risk** — governance and monitoring only: (f) the checkpoint,
  (j) `market_last_update` exposure, (k) the dirty-tree guard.

### Closed: what the historical gate report actually validates

**Resolved 2026-09-16.**
[`research/provenance/CALIBRATION_FINDING.md`](research/provenance/CALIBRATION_FINDING.md).

A block walk-forward of the frozen recipe reproduces
[`walkforward_report.json`](cfl_engine/harness/walkforward_report.json)'s panel,
fold boundaries and training sets **exactly**. Data selection was ruled out. The
difference is the isotonic step:

| | pooled log loss |
|---|---|
| reproduced, isotonic **applied** (the live-lock path) | 0.5180 |
| reproduced, isotonic **bypassed** | **0.5032** |
| the gate report | **0.5037** |

**The gate report measures the raw hazard model.** The accurate sentence, to be
used wherever historical testing is described:

> Historical walk-forward testing supports the underlying raw hazard model. The
> calibration layer used in live PROP-0001 forecasts was not validated by that
> historical artifact.

PROP-0001 is **not** to be described as "historically validated" end to end.

Two consequences, kept separate on purpose:

1. **Labelling.** The artifact is relabelled, not altered — see
   [`cfl_engine/harness/README.md`](cfl_engine/harness/README.md). The frozen
   file is untouched.
2. **A model question, deferred to a new version.** The isotonic step costs
   0.0148 log loss pooled across 13 of 18 folds. PROP-0001@v1 is **not**
   changed and its locks are **not** reinterpreted. Any calibration change is a
   new `model_version` with its own preregistration, judged prospectively — see
   DUR-002 below.

This did not find PROP-0001 to be a bad model. It found that the artifact
everyone took as validating the live pipeline was validating a different stage
of it — caught before monetisation, which is what this register is for.

### Forbidden changes

- Retraining, re-featuring, re-calibrating or re-mapping PROP-0001 while the
  sample accumulates. Daily refits on a growing training set under the same spec
  are part of the procedure, not a change.
- Widening a model's evaluation window past its `test_start_date`.
- Selecting sportsbooks, or selecting thresholds after results are visible.
- Writing any historical backfill into `prop_model_locks`.
- Deriving 3.5 or 4.5 probabilities for five-round fights.

---

## DUR-002 — the same question for the uncalibrated hazard

| field | value |
|---|---|
| status | **DRAFT — not frozen, not in force** |
| preregistration | [`cfl_engine/dur002/PREREGISTRATION.md`](cfl_engine/dur002/PREREGISTRATION.md) |
| challenger | `PROP-0001@v2` — identical to v1 except no isotonic or other post-hoc calibration |
| freeze timestamp | none. Takes effect only when Reed dates and signs §0 |
| verdict | none |

Until §0 is signed, **no `PROP-0001@v2` lock may be written and no DUR-002
number computed.**

### Why v2 is specified this way

Three reasons, none of which is a score:

1. it is the **simpler specification** — it removes a stage rather than adding one;
2. it is the specification the **existing historical artifact actually
   evaluated**, so adopting it stops the prospective pipeline and the historical
   evidence describing different objects;
3. the v1 calibration step is **questionable on inspection**: the isotonic map is
   fit on a model trained without the trailing year, then applied to a model
   refit including it — a correction estimated on one output scale applied to
   another's.

### Disclosure

A historical comparison of the two variants was run and seen before this was
drafted, and it favoured the uncalibrated variant. **That is not the reason for
the specification and may not be cited as evidence for it.** It is recorded in
§2 of the preregistration so nobody later finds it and assumes it was the hidden
motive. DUR-002's verdict rests only on fights locked after the freeze.

### What DUR-002 does not do

It does not modify `PROP-0001@v1`, reinterpret its 48 existing locks, or change
DUR-001. The two run in parallel under separate `model_version`s. A head-to-head
comparison of v1 against v2 is **not** preregistered and would need its own
document.

---

## PROP-0001 — the frozen duration model

| field | value |
|---|---|
| status | **frozen**, serving locks |
| model_version | `PROP-0001@v1` |
| freeze commit | `6be7198ebe4d56b27366268318b757e99e3074c5` |
| freeze timestamp | 2026-09-15 (UTC) |
| form | discrete-time logistic hazard, one hazard per round, isotonic recalibration on the trailing 365 days |
| historical validation | **raw hazard model only** — the gate report bypasses the isotonic step. The live calibration layer is unvalidated historically. |
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
hazard's 0.5082 over 9,030 test rows in 18 folds. Two limits on how far they
reach, both load-bearing:

1. They are a *gate* result, not a DUR-001 result: measured against the model's
   own historical panel, not against a pre-fight market on fights locked in
   advance.
2. **They measure the raw hazard model, with the isotonic step bypassed** — not
   the complete PROP-0001 locking pipeline. See
   [`cfl_engine/harness/README.md`](cfl_engine/harness/README.md).

So: historical walk-forward testing supports the underlying raw hazard model.
The calibration layer used in live PROP-0001 forecasts was not validated by that
historical artifact.

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
