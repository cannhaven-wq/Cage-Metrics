# MKT-001 — Report: removing the bookmaker's margin from the historical closing odds

**2026-10-22. Internal research, DEV only (fights before 2025-01-01).**
Preregistration: [`PREREGISTRATION.md`](PREREGISTRATION.md), frozen in
`1082cdc7` before `run.py` existed. Numbers: [`results.json`](results.json).
Not blind: the consolidation audit had already computed part of this (the
preregistration says so). Nothing here is a betting result: BFO's historical
consensus is not a price anyone could bet (BT-001).

## Plain verdict

**The way CFL has been removing the bookmaker's margin is the least accurate
of the three standard ways, and it got worse in recent years.** The other two
(power and Shin) are about equally good, and the data cannot separate them.

**Why it matters:** with the usual method, simply re-weighting the market's
own prices "beats the market" by +0.003 per fight in 2021–24 — which is the
whole of PRED-001's minimum useful gain. With the power method that free gain
is about zero. So any model judged against the usual method could look useful
while having learned nothing about fights. Yesterday's rule (D-034: the engine
measures its size test against the re-weighted market) already protects the
engine; this tells every other study what to report beside its result.

**One sentence a bettor can use:** the closing consensus is close to
correctly priced, and most of the apparent "the market underrates favourites"
pattern is an artefact of how its margin is removed.

## What was measured

All 6,824 decided DEV fights with both BFO closing prices (623 cards,
2007–2024), the same set PRED-001 froze (its id and outcome fingerprints are
checked on every run). Three methods turned each pair of prices into fair
chances; each was scored on how surprised it was by the results (log loss,
lower is better).

| method | log loss | calibration slope (1 = right) | re-weighting gain 2010–24 (95% range) | re-weighting gain 2021–24 |
|---|---|---|---|---|
| proportional (CFL's usual) | 0.6087 | 1.07 | **+0.0011** (+0.0002 to +0.0020) | **+0.0029** (+0.0015 to +0.0043) |
| power | **0.6074** | 0.96 | −0.0001 (−0.0005 to +0.0003) | +0.0003 (−0.0000 to +0.0006) |
| Shin | 0.6076 | 1.00 | +0.0002 (−0.0003 to +0.0008) | +0.0011 (+0.0003 to +0.0018) |

**Primary comparison** (per fight, all 6,824, whole-card resampling):

| comparison | advantage | 95% range | survives Holm |
|---|---|---|---|
| power better than proportional | +0.0013 | +0.0004 to +0.0022 | **yes** |
| Shin better than proportional | +0.0012 | +0.0006 to +0.0017 | **yes** |
| power better than Shin | +0.0001 | −0.0003 to +0.0006 | no |

**Decision, by the rule fixed in advance:** power has the lowest log loss but
does not beat Shin significantly, so **no single method is recommended**. Later
studies report all three. Proportional is clearly the worst of the three.

## By era

| era | fights | best → worst | proportional slope | closer margin (median) | opener margin (median) |
|---|---|---|---|---|---|
| 2007–2012 | 1,361 | power, Shin, proportional | 0.81 | 3.3% | 5.6% |
| 2013–2016 | 1,758 | power, Shin, proportional | 1.00 | 4.3% | 6.6% |
| 2017–2020 | 1,786 | power, Shin, proportional | 1.12 | 5.3% | 6.2% |
| 2021–2024 | 1,919 | Shin, power, proportional | **1.29** | **7.9%** | 4.1% |

- **Proportional is last in every era**, and the gap widens as the margin in
  BFO's closing consensus grows: +0.0006 (2007–12) to +0.0026 (2021–24) for
  power. The bigger the margin, the more proportional removal leaves long shots
  looking too likely — which then reads as "favourites win more than priced".
- **Power and Shin swap places only in 2021–24**, by 0.00006: the eras do not
  agree on a winner between them, which is why neither is recommended.
- **2007–2012 runs the other way** (all slopes below 1: the early consensus
  was slightly *too* confident). The 2021–24 "under-confidence" is not a
  stable property of the market.
- **The closing consensus's margin is larger than the opener's from 2021**
  (7.9% vs 4.1%), the reverse of every earlier era. It is an aggregate across
  books, so this describes how BFO's consensus was built, not what any one
  book charged.

## The opener (secondary, descriptive)

On the same fights the opening consensus is clearly less accurate than the
close (log loss 0.624 vs 0.607 under power), as expected: the market learns
between open and close. BFO's opener and closer are ordered, not timed, so
nothing here says *when* that learning happened.

## What this changes, and what it does not

- **For every later win-probability study:** report a "re-weighted market
  only" baseline under all three methods beside the result. Under
  proportional, expect it to show up to +0.003 for free in recent years.
- **For the Discovery Engine:** its size test is already against the
  re-weighted market (D-034), which removes this head start whichever method
  is primary.
- **PRED-001 is unchanged.** Its primary benchmark stays proportional; power
  and Shin stay sensitivities, never chosen after the fact. Whether that
  choice should change for future preregistrations is an owner decision, and
  this report is evidence for it, not the decision.
- **No claim about profit.** A consensus nobody could bet says nothing about
  returns. The price study that can (MKT-002) uses timestamped single-book
  quotes.

## Limits

- One historical source (BFO's consensus), one market type (fight winner),
  pre-2025 only.
- Not blind (see the preregistration's disclosure).
- The power and Shin implementations here have no 3%–97% band; on the 6,817
  fights inside the band they equal CFL's frozen helpers to within 6e-11.

<details>
<summary>The arithmetic</summary>

- Log loss: natural log, probabilities clipped to [1e-4, 1 − 1e-4]
  (`pred_protocol.log_loss_each`). Calibration: logistic refit of the result
  on logit(p) (`pred_protocol.calibration_fit`).
- Re-weighting: for each test year 2010–2024, `logit p = a · logit q` fitted
  by maximum likelihood on all earlier scored fights; gain =
  mean[LL(q) − LL(p)] on the test years.
- Uncertainty: 10,000 resamples of whole cards, seed 20261012
  (`pred_protocol.cluster_bootstrap`). Two-sided p = 2 × the smaller tail
  share, floored at 1/10,001; Holm at family-wise 0.05 over the three
  pairwise comparisons.
- Reproduce: `python3 -I research/experiments/MKT-001/run.py` with the DEV
  export in place (`research/discovery/WITHHELD.json`). Runs in about 10
  seconds; the bootstrap is seeded, so `results.json` is identical on rerun.

</details>
