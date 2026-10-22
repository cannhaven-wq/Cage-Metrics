# MKT-002 — Do outlier sportsbook prices get corrected? (DRAFT, not frozen)

**Status: draft, NOT frozen.** The 2026-10-22 pilot ([`PILOT_RESULTS.md`](PILOT_RESULTS.md)) found that a fresh closing price exists for about 1 bout in 4 at the current capture timing, so this design cannot reach its sample size; it stays unfrozen until the owner decides on fight-day capture timing (T-120). No observation has been evaluated.
Every value below may change until the freeze commit; after it, a change is a
new experiment. Governed by the price-only rules in
[`PHASE2_RESEARCH_DESIGN_2026-10-21.md`](../../consolidation/PHASE2_RESEARCH_DESIGN_2026-10-21.md)
§A.2 (D-034, owner condition 5) and by CLV-001's frozen definitions. It reads
**no fight result**.

## Plain version

Sometimes one sportsbook's price for a fighter sits noticeably away from the
other books. Either that book knows something early (and the others will
follow), or it is slow (and it will be pulled back). We take each such price
at a fixed time before the fight and ask, using the closing prices only:
would a bettor who took it have beaten the market's fair closing price? If
outlier prices beat the close on average, some books misprice systematically
in a way a bettor could have used. If not, they don't.

## Hypothesis

- **Population of quotes.** For every bout on a UFC card whose first W3
  capture is after this file's freeze commit, at each anchor time *t*, each
  eligible sportsbook's two-sided quote for each corner.
- **Outlier.** A quote is an *outlier toward the fighter* when the book's
  vig-free probability for that fighter is at least **δ = 3 percentage
  points lower** than the leave-one-out median vig-free probability of the
  other eligible books at the same anchor (the book offers that fighter at a
  longer price than the rest). δ is fixed at freeze from the pilot's
  distribution; 3 points is the working value.
- **H0:** the mean `CLV_return` of outlier quotes is ≤ 0.
  **H1:** it is > 0 (the outlier price beat the fair close).
- A secondary, descriptive split: outliers from each book separately.

## Anchor times (fixed)

Measured from the bout's best-known start (`v_fight_start_best.start_at`;
where only the event-date fallback exists, from 00:00 UTC on the event date):

- **T−24h** and **T−3h**: the latest two-sided capture **at or before** each
  anchor, from each book, provided it is no older than **120 minutes** at the
  anchor (CFL's actionable-price staleness rule). A book with no such capture
  is absent at that anchor, never imputed.
- **Close:** the last two-sided capture of each eligible book before the
  start, no older than **45 minutes** at the start (CLV-001's frozen limit).

## Quote-quality rules (fixed)

1. Eligible books: `v_odds_books_sportsbooks` (excludes BFO consensus, the CFL
   consensus row, Polymarket, Kalshi). `feed_version` must be the W3 provenance
   feed; `retrieved_at` and `source_commence_at` present.
2. Both sides quoted by the same book in the same capture; `is_live` false;
   `market_status` open; American prices within 100-to-1.
3. At least **4** eligible books at the anchor (so the leave-one-out median
   has at least 3), and at least **3** at the close.
4. A bout rebooked or cancelled after the anchor is dropped; a bout whose
   corners changed is dropped (CLV-001 R-08, Q-10).
5. One observation per book per bout per side per anchor; duplicates and
   reposts collapse to the latest at or before the anchor (R-06).

## Scoring (fixed)

- `CLV_return = closing_fair_probability × decimal_odds_of_the_outlier_quote − 1`
  (CLV-001 §1.1): publish side = the outlier quote as posted (vigged), close =
  the median across eligible books of the **power**-de-vigged closing
  probability (CLV-001's primary; proportional and Shin as frozen
  sensitivities, reported, never chosen).
- Unit of resampling: the **card**. 10,000 card-bootstrap resamples, seed
  20261012. One-sided test at α = 0.01.
- Reported beside it, never deciding: the same for non-outlier quotes (the
  control), by book, by anchor, by favourite/underdog.

## Sample size

Fixed at freeze from the pilot: n = the number of outlier quotes needed for
80% power at a true mean `CLV_return` of **+0.01**, using the pilot's SD and
its within-card correlation, with the design effect floored at 1. Analysis on
exactly the first n eligible outlier quotes in capture order, whole cards
only. One interim look at n/2, futility only.

## Pilot (allowed before freeze, outcome-free and hypothesis-free)

On existing W3 captures for cards from 2026-10-12 to the freeze: count books
per anchor, staleness, how often each quality rule drops a quote, the
distribution of book-versus-consensus gaps (to fix δ), and the SD of
`CLV_return` **across all quotes pooled, never split by outlier status**. The
pilot may not compute the outlier-versus-control comparison. Its numbers are
committed with the freeze.

## What a result would and would not mean

- **Pass:** some books post prices the market later corrects, by enough to
  beat the fair close after paying the posted price. Not proof of profit
  after all costs; any public use is L3 (item 8).
- **Fail:** outlier prices are, on average, correctly pulled back. Recorded
  as a negative result.

## Data handling

Read-only exports of the columns listed in §A.2 rule 1; kept out of the
repository (D-034); each export's row count and sha256 committed. No write to
any table.
