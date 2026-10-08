# SYM-002 — broader symbolic win-probability search (private research)

**Frozen 2026-10-07, before any feature matrix was built or any model fitted.**
The machine-readable rules are [`config.json`](config.json). This file says the
same thing in words. A changed setting is a new experiment, not an edit.

## Plain version

We are asking one question: *can a short, written-down formula built from a
fighter's record before the fight predict the winner better than a plain
weighted average of the same numbers, or better than the betting market?*

We will search a large but fixed set of formulas, pick one using older fights
only, and then score it once on later fights it never saw. If it does not beat
the simple versions by more than luck would allow, we say so.

Nothing here touches the website, the database, or any published number.

## What v1 was, and what we can and cannot say about it

An earlier session reported a three-term formula, 61.5% accuracy on 226 eligible
2026 fights, and a market correction that did not beat the market. **Its code,
preprocessing and predictions are not available to this session** (no ZIP, no
`research/symbolic/` in any branch). We therefore cannot *reproduce* v1. We
re-implement its reported **structure** on our own point-in-time features and
refit it, and separately apply its reported coefficients to our standardised
differences as an approximate reference. Neither is a reproduction.

## Rules fixed in advance

- **Features**: 23 per-fighter numbers, each computed only from fights strictly
  before the event date (list in `config.json`). Career averages from the
  `fighters` table are **not** used as inputs; they are loaded only to measure
  how much they would leak.
- **Corner swap**: every term is `h(A,B) − h(B,A)` and there is no intercept, so
  swapping the fighters turns P(A) into exactly 1 − P(A). Tested on every row.
- **Search**: 3 configurations (depth 2/3/4, up to 4/6/8 terms) × 5 seeds, 120
  formulas × 26 generations per run. Bounded operators, protected division
  `x/(1+|y|)`, every node clipped to ±20, NaN/∞ → 0.
- **Selection**: lowest inner-validation log loss plus 0.0002 per node.
  Never accuracy.
- **Folds**: test years 2021–2026, trained on earlier events only; inner
  validation is the last two calendar years of each training window.
  Preprocessing is learned from the training rows of that fold only.
- **2026** has already been studied by CFL. It is scored and reported, but as
  historical research, not as an untouched confirmation.
- **Improvement** means: the 95% event-level bootstrap interval of the pooled
  2021–2025 log-loss difference excludes zero, and the model wins at least 4 of
  the 5 folds.
- **Odds**: archived odds carry placeholder timestamps (1970-01-01) and are
  labelled *unverified*. Timing-verified pre-start prices exist for 34 decided
  fights and are reported separately and descriptively. No ROI, no CLV.
- **Final model**: the same procedure once on everything through 2026-10-03,
  hashed, for scoring on events after 2026-10-07 only.
