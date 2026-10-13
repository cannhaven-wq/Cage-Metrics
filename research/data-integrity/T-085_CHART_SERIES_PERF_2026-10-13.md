# T-085 — Why the line-movement chart takes seconds (2026-10-13)

**Short answer:** `v_fight_chart_series` works out the matched-sportsbook set
for **every fight with odds history** before it filters to the one fight being
asked for. One keyword in the view fixes it:

- **Time for one fight:** 5.8 s → 0.26 s.
- **Output:** identical, and every matched-book rule is unchanged.

## What changed since the 22 ms figure

The view's comment and D-012's write-up record *"one fight, literal fight_id
… 22 ms"* (2026-09-21/24). That was the figure after the T-057 fix to
`v_fight_market_quotes`, measured when the data covered **79 fights**. It is
not reproducible today:

- **The view itself:** the `cohort` CTE has been referenced twice since the
  view was first written, so it has always been materialised.
- **The data:**
  - fights with a broad baseline grew from 78 to **113**;
  - `fight_odds` grew from 116,004 to 126,972 rows.
- **The underlying quotes view** still takes **4.7 ms** for one fight.

So the slowness comes from the materialised `cohort` step. It builds a cohort
for every fight with odds history before it filters, so it grows with the
history held, not with the one fight a page asks for. The plan below spends its
time in nested loops over every fight's quotes (34,725 iterations).

How the original 22 ms was obtained cannot be reconstructed now: a 45% growth
in fights does not explain a 260× slowdown. The comment is corrected with a
dated note, and the old figure is kept and labelled rather than deleted. The
fix does not depend on that history: it removes the fence, so the cost no
longer grows with other fights at all.

## Query-plan evidence

`EXPLAIN (ANALYZE, BUFFERS)` of
`SELECT at, market_p_a, cohort_books FROM v_fight_chart_series WHERE fight_id = 46774`,
production, 2026-10-13:

- **Total:** execution 5,848 ms, planning 102 ms.
- **The most expensive node:** a `CTE Scan` on `cohort`, filtered by
  `fight_id = 46774`. It took 5,700 ms, returned 3 rows and **removed 466**:
  the (fight, sportsbook) cohort rows of the other 112 fights with a broad
  baseline.
- **Inside that CTE:**
  - `fight_odds` is scanned with only `captured_at > '2010-01-01'` as the
    index condition, with **no `fight_id`**. That is 48,024 side-A rows.
  - Those rows are then joined to side B through 34,725 loops, repeated for
    each nested view.

**Why.** `cohort` is a CTE referenced twice: once in `ticks` and once in
`standing`. From PostgreSQL 12 on, a CTE referenced more than once is
materialised by default. A materialised CTE is an optimisation fence, so the
outer `WHERE fight_id = X` cannot reach the index inside it.

## The fix

```sql
WITH cohort AS NOT MATERIALIZED (   -- was: WITH cohort AS (
```

`NOT MATERIALIZED` lets the planner inline `cohort` into both references and
push the fight filter into each one. Nothing else in the view changes, so the
matched-cohort rules (D-012), the fixed-cohort series, the carry-forward
and the ≥3-book refusal are untouched.

**Measured with a temporary copy of the view on production (never replacing the
live one):**

- **Speed:** 5,848 ms → **257 ms** for fight 46774. Every `fight_odds` scan now
  carries `fight_id = 46774` in its index condition.
- **Identical output:** for all 8 fights tested, the md5 of the full ordered
  output matched the live view.

| fight | points | old = new |
|---|---|---|
| 26712 (busiest on record) | 891 | yes |
| 8780 | 269 | yes |
| 48439 | 83 | yes |
| 51877 | 52 | yes |
| 51876 | 52 | yes |
| 53243 | 17 | yes |
| 46774 | 6 | yes |
| 53620 (under 3 books) | 0 rows | yes |

## Regression test

`tests/market-chart.test.js` asserts that every CTE referenced more than once in
`market_chart_views.sql` is declared `NOT MATERIALIZED` (verified to fail on a revert). The view's
§Performance comment is corrected with a dated note: the earlier figure is kept
and labelled, not deleted.

**Applying it:** `CREATE OR REPLACE VIEW` with the same columns. Grants and
dependants are unchanged. Not applied yet (T-085 was approved for
investigation).
