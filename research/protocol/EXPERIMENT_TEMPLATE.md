# <ID> — <one-line question>

Governed by PRED-001 (`research/protocol/PREDICTION_RESEARCH_PROTOCOL.md`).
Copy this file to `research/experiments/<ID>/PREREGISTRATION.md`, fill in
every field, record its sha256 in `research/registry.json`, and freeze it
**before** asking the auditor for anything. A field you cannot fill is
written `none`. It is never left blank and never guessed.

## Plain version

<Two sentences a bettor could repeat to a friend. What is being tested, and
what result would mean "no".>

## Hypothesis

- H0: the challenger adds no information to <benchmark>. Δ ≤ 0.
- H1: Δ > 0 on <population>.
- Target gain δ (≥ 0.004): <value>, and why that size is plausible.

## Challenger

- Type: standalone | incremental (market + model, weights frozen on DEV)
- Model artifact sha256: <hash>, code commit: <hash>
- Training window: DEV only, <dates>
- Variants tried on DEV (an honest count of configurations compared): <n>
- Features chosen using any all-years result (Factor Lab, a published
  benchmark)? yes/no. If yes, the H1 result is non-confirmatory (PRED-001 §2).

## Feature manifest

| feature | source table.column | time rule | static? |
|---|---|---|---|

## Benchmark

- Primary: <BFO close | same-timestamp quote at lock>
- De-vig: proportional (primary); power and Shin reported

## Population and eligibility

<division, rounds, and any exclusions beyond PRED-001's.>

## Sample size

- SD used: max(0.064, DEV-measured SD = <value>)
- n_required (prospective): <≥ required_n(SD, δ, 0.01, 0.8, mue=0.003)>
- Analysis trigger: the first n_required eligible locks, in lock order

## Registry entry (research/registry.json)

These are what `load_registration` reads. The auditor cannot supply them.

    "protocol": "PRED-001", "model_class": "incremental",
    "model_artifact_sha256": "<64 hex>", "target_effect": <δ>, "sd_used": <SD>,
    "n_required": <n>, "preregistration_path": "research/experiments/<ID>/PREREGISTRATION.md",
    "preregistration_sha256": "<64 hex>", "author_sessions": ["<session ids that built it>"]

## Stages requested

- [ ] H1 evaluation (spends 1 of 10 slots; whole sealed set only)
- [ ] Prospective test (spends 1 of 5 slots; needs the lock table, L3)

## Pre-stated interpretation

What we will say for each verdict, written now:

- REJECT: <...>
- INCONCLUSIVE: <...>
- PASS_H1: <...>

## Amendments

None.
