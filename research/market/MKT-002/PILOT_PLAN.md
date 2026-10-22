# MKT-002 pilot — plan, committed before the read

**2026-10-22.** Under D-034 (owner condition 5) and the owner's 2026-10-22
instruction: "begin with read-only analysis of price quality and data
coverage, then freeze the experiment before evaluating future observations."
The preregistration is [`PREREGISTRATION_DRAFT.md`](PREREGISTRATION_DRAFT.md);
it is not frozen yet.

## Plain version

Before testing whether out-of-line sportsbook prices beat the market, check
whether the data can support the test at all: how many books quote each
fight, how fresh the prices are a day and three hours before the bell, how
often prices are out of line, and how noisy the measure is. None of this
looks at who won, and none of it looks at whether out-of-line prices did well.

## The one read

[`pilot/export_quotes.sql`](pilot/export_quotes.sql), run once, read-only,
through the database connector: every real-sportsbook quote for UFC cards
dated on or after 2026-10-12, with the bout's start time. It names no result,
method, round, finish-time or statistics column and no results table
(`tests/test_market_research.py` checks every query and script in
`research/market/`). The export is saved outside the repository; its sha256
and row count go in the pilot results. Until the C2 lock is in force, that hash
is the record of what was read.

## What the pilot computes — [`pilot/analyze.py`](pilot/analyze.py)

1. How often each quote-quality rule drops a quote (inactive bout, not the
   provenance feed, no retrieval time, live, market not open, one-sided,
   beyond 100-to-1, captured after the start), and which `market_status`
   values occur.
2. Per card: bouts with clean quotes, books, start-time basis.
3. Per bout, at T−24h, T−3h and the close: how many books have a fresh
   two-sided price (≤ 120 min old at an anchor, ≤ 45 min at the close).
4. The distribution of each book's distance from the other books' median
   (power de-vig) at each anchor, and how many quotes sit 2, 3, 4 and 5 points
   out — to fix the outlier threshold δ.
5. The spread (SD) of `CLV_return` over **all** anchor quotes pooled, and its
   within-card correlation — to fix the sample size.

## What it does not compute

The mean of `CLV_return`, or `CLV_return` split by distance, outlier status or
book. That is the hypothesis. It is evaluated only after the preregistration
is frozen, and only on cards whose first capture comes after the freeze.

## After the pilot

Fix δ, the quality rules and n in the preregistration from these numbers,
freeze it (commit, record its sha256), and from then on evaluate only new
cards. Cards read by the pilot are never part of the evaluation set.
