# PRED-002 — brief for the independent auditor: are the Stage 1 thresholds right?

**Requested by:** the owner's reviewer, 2026-10-12 (T-085). **Written by:**
Claude, the researcher on PRED-002. That is why this is a brief and not a
verdict: under PRED-001 §1 the person who wrote the preregistration may not
judge it.

**Who may answer it:** an auditor session or person who wrote none of
PRED-002's code or preregistration, the same independence rule PRED-001 §1
applies to sealed-data looks. The answer is a short written verdict in
`research/experiments/PRED-002/AUDITOR_REVIEW_THRESHOLDS.md`. It covers each
question below: keep, change (to what, and why), or cannot judge. It is
committed **before** Stage 1 runs.

**What the auditor may read:** the preregistration, PRED-001, this brief and
INFO-AUDIT-001. The auditor may also run arithmetic on development-years
(pre-2025) figures. It does not need sealed data and must not read any.

## What is being asked, plainly

Stage 1 is a filter on 2016–2024 fights. It decides whether opponent-adjusted
ratings are worth a prospective test. The thresholds in
`PREREGISTRATION.md` §6 were written by the researcher **before** any
training, as the owner required. The owner's reviewer asked that someone
independent confirm they are sensible **as a filter**. In the reviewer's
words, they must not be treated "as proof of commercial value".

## The thresholds under review

| # | condition |
|---|---|
| S1.1 | gain over price plus engine (Δ_B) ≥ 0.002 per fight |
| S1.2 | Δ_B's 95% event-resampled interval entirely above 0 |
| S1.3 | gain over price alone (Δ_M) ≥ 0.006, interval above 0 |
| S1.4 | Δ_B > 0 in at least 6 of the 9 years |
| S1.5 | calibration slope 0.8–1.25, \|intercept\| ≤ 0.1 |
| S1.6 | Δ_M ≤ 0.015 and accuracy ≤ 72%, else SUSPECT |

## Facts the auditor needs (development years only)

- **Sample.** 2016–2024 has **4,174** decided fights with a BestFightOdds
  close on both corners, on **372** cards: 425–497 a year. PRED-002 §7 also
  excludes fights where a fighter has no prior UFC fight with round splits, so
  the scored set will be smaller. That share is not yet measured; a guess is
  20–25%, giving roughly 3,100–3,300 fights.
- **What the engine already adds.** On 2020–2026 walk-forward fights, a
  market-plus-engine blend beat the market by 0.0035 per fight
  (INFO-AUDIT-001 §3b). The PRED-002 baseline B is that blend, **retrained on
  development data only**, so its own Δ_M on 2016–2024 is unknown until Stage
  1 runs.
- **Spread.** The SD of per-fight Δ for a market-plus-model blend against the
  market was 0.062–0.066 (PRED-001 §6; INFO-AUDIT-001). The SD of **Δ_B** (C
  against B, two nested blends differing by five features) has never been
  measured. It should be well below that, plausibly 0.02–0.04.

## Questions, with the researcher's own reading for the auditor to accept or reject

1. **Is S1.1's 0.002 the right size?** The researcher picked it as about
   two-thirds of what the whole engine adds (0.0035). *A concern the auditor
   should weigh:* S1.1 is a point-estimate floor. If the true gain is exactly
   0.002, Stage 1 passes only about half the time. Is that the intended
   behaviour of a filter, or should the floor sit below the effect worth
   chasing?
2. **Can S1.2 be met at all on this sample?** With roughly 3,200 fights and an
   SD of Δ_B between 0.02 and 0.04, a 95% interval has a half-width of about
   0.0007–0.0014 (before clustering by card). So a true 0.002 would usually
   clear zero. The auditor should check this arithmetic, and say whether
   card-level clustering changes the answer.
3. **Is S1.3 the condition that actually binds?** If B already beats the
   market by about 0.0035, then S1.3 (Δ_M ≥ 0.006) requires the ratings to add
   about 0.0025 or more, which is stricter than S1.1. Is having two
   overlapping gates intended? Would one gate on Δ_B with a separate,
   clearly-labelled report of Δ_M be cleaner?
4. **Does S1.4 (6 of 9 years) add anything?** Each year has about 460 fights.
   At a true gain of 0.002 and an SD of 0.03, each year's estimate has an SE of
   about 0.0014, so most years should come out positive anyway. Is S1.4 a real
   guard against a gain concentrated in a few years, or a formality?
5. **Is anything missing?** For example: a minimum share of fights scored, a
   check that the five ratings are not just re-encoding the engine's existing
   striking features, or a cap on how far C may move from B.
6. **Is the commercial caveat stated strongly enough?**
   `PREREGISTRATION.md` §10 says no verdict is a statement about
   profitability. Is that sufficient, or should Stage 1's output carry the
   prospective sizing (0.010) beside every Stage 1 number, so a pass is never
   read as "worth money"?

## What happens next

- **Thresholds accepted:** the preregistration is frozen as is and Stage 1 runs
  once.
- **Thresholds changed:** the change goes in as an amendment **before**
  freezing, citing this review. It is not "motivated by observed results",
  because there are none yet. Then freeze, then run.
- **The auditor cannot judge:** say why. The owner decides whether to proceed.

**Nothing in this brief is a result.** No Stage 1 number exists. The ratings
have not been built.
