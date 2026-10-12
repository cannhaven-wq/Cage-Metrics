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
- Target gain δ (≥ 0.003): <value>, and why that size is plausible.

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

- SD used: max(class floor, DEV-measured SD = <value>)
- n_required (prospective): <required_n(...)>
- Analysis date or trigger: <date or n>

## Stages requested

- [ ] H1 evaluation (spends 1 of 10 slots)
- [ ] Prospective test (spends 1 of 5 slots; needs the lock table, L3)

## Pre-stated interpretation

What we will say for each verdict, written now:

- REJECT: <...>
- INCONCLUSIVE: <...>
- PASS_H1: <...>

## Amendments

None.
