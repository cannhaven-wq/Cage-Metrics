# BT-001 — Historical UFC betting evaluation: pre-registered plan

**Written 2026-10-21, committed before any outcome was extracted or any
strategy was scored.** Internal research. Nothing here goes on a public page,
and no edge percentage from it may appear on the site (CLAUDE.md, D-011).

## Plain version

We want to know whether any simple, pre-chosen way of betting UFC fights would
have made money after paying what a bettor really pays: the bookmaker's cut,
the price you could actually get, and when that price was available. We write
the rules, the strategies and the bar for "yes" down first, then run them
once, and report every one, winners and losers.

## 0. What was looked at before this was written

Outcome-free only. Disclosed so nobody has to guess:

- Row counts of `fight_odds` by book and by date (no outcomes joined).
- The shape of the BestFightOdds (BFO) consensus rows before 2025: one opener
  row and one closer row per fighter, both sides, 6,953 fights, a 1970
  placeholder timestamp, vig included (e.g. +100 / -130).
- `model_versions` windows, and the row shape of `model_predictions` for
  v1–v3 in 2023–2024 (690 fights, one row per side). The `won` and `pnl_usd`
  columns were **not** selected.
- Price counts for cards dated on or after 2026-10-12 (no outcomes joined).
- Published prior results that anyone in this repo has seen: v1–v3 lose to the
  closing line on log loss (`cfl_engine/benchmark_report.md`); FE-001 and the
  Factor Lab (age and raw UFC record survive market control, computed over all
  years).

## 1. The sealed data, and what is excluded

PRED-001 (`research/protocol/`) seals everything from **2025-01-01**: H1
(2025-01-01 → 2026-07-11), RESERVE (2026-07-12 → 2026-10-11) and the
prospective window after it. Its Researcher role "may not read … any outcome
on or after 2025-01-01". This evaluation follows the strictest reading:

1. **No outcome dated on or after 2025-01-01 is read**, in any query, for any
   purpose. Every extraction query carries `event_date < '2025-01-01'`, and the
   analysis code passes every row through `pred_protocol.dev_only()`, which
   raises on a sealed date.
2. Every fight id in `research/protocol/h1_fight_ids.txt` is excluded again by
   id (belt and braces), and so are fights 43, 46 and 8780 (rebooked in place,
   PRED-001 Amendment 1).
3. **`win_model_locks` is never queried.** PRED-002 is collecting prospective
   locks; nothing here touches them.
4. Models whose honest out-of-sample window lies in sealed data are excluded:
   v4 and v5 (test windows start 2025-01-01), v6 (declared window starts
   2021-01-01 but it was trained through 2024-12-31, so its only honest window
   would be 2025+, which is sealed), and the engine (trained through 2026-07;
   PRED-001 says it cannot be first-opened on sealed data).
5. **Prices only, never outcomes, are read for cards on or after 2026-10-12**,
   and only to measure the cost of line-shopping and the timing of captures
   (§4). No sealed-window price (2025-01-01 → 2026-10-11) is read.

Consequence, stated up front: every outcome-bearing number in this study comes
from **1994–2024 (DEV)**, where the only price CFL holds is BFO's consensus
opener and closer. Per-book, timestamped, executable prices exist only from
2026-05-22, all inside sealed windows except the post-freeze cards.

## 2. Data

- Fights: `fights` joined to `events`, `event_date < 2025-01-01`, both fighters
  set, `winner_id` equal to one of them (draws and no-contests excluded),
  `is_active IS DISTINCT FROM false`, BFO consensus (`odds_books.id = 6`)
  opener **and** closer present on **both** sides.
- Ages: computed in SQL from `fighters.dob` at the event date, exported as
  years only (no dates of birth leave the database). Valid if 15 < age < 60
  (the Factor Lab rule).
- UFC record state: rebuilt in Python by walking every `fights` row before
  2025-01-01 in (event_date, id) order, folding each fight into both fighters'
  counts **after** scoring it, exactly as `build/factor-rates.js` does.
- Model predictions: `model_predictions` for v1, v2, v3 with
  `2023-01-01 ≤ event_date < 2025-01-01` (their `test_start_date` is
  2023-01-01; the window is never widened earlier).
- Snapshots saved to `research/backtest/data/` as CSV: ids, dates, prices,
  outcomes, ages, model probabilities. No names, no dates of birth, nothing
  personal. The SQL is saved beside them.

## 3. Strategies (fixed; no others will be scored)

Flat 1 unit per bet. At most one bet per fight per strategy.

| id | rule |
|---|---|
| **a FAV** | bet the side with the higher implied probability at the execution price. Skip exact pick'ems. |
| **b DOG** | bet the other side. |
| **c1 / c2 / c3** | v1 / v2 / v3. Normalise the two sides' `model_p` to sum to 1; bet the side with `p × decimal − 1 > 0` at the execution price (PRED-001 §5's betting rule). 2023–2024 only. |
| **d1 AGE-EVEN** | market-even fights only (both sides inside ±140 American at the execution price, `EVEN_BAND`); both ages valid and different; bet the younger fighter. |
| **d2 UFCREC-EVEN** | market-even fights only; both fighters with ≥ 5 prior UFC fights; raw UFC win-rate gap > 0.10; bet the better record (`build/factor-rates.js` definitions). |
| **e MOVE** | close only: bet the side whose de-vigged probability rose by **≥ 0.02** from BFO opener to BFO closer; bet at the close. |

**Execution times.**
- **CLOSE (primary family):** all eight strategies, priced at the BFO
  closing consensus, with the decision taken on closing information.
- **OPEN (secondary family):** a, b, c1–c3, d1, d2 priced at the BFO opening
  consensus, decision on opening information only. This is the only DEV
  setting in which closing line value is measurable.

That is **15** strategy × time tests.

## 4. Cost model

| scenario | price | role |
|---|---|---|
| **A — consensus, vig in** | BFO consensus American as stored, converted to decimal | **primary**; the bar is judged here |
| **B — best available** | A's decimal × `m_best`, where `m_best` is the median, over (fight, side), of best-book decimal ÷ median-book decimal | sensitivity: what perfect line-shopping across US books would add |
| **C — fair, no vig** | proportional de-vig of the two sides | **not executable**; descriptive only, to separate picking ability from cost |

`m_best` is measured, without outcomes, on cards dated ≥ 2026-10-12: for each
fight and real sportsbook (`v_odds_books_sportsbooks`), the last non-live
quote captured before the provider's commence time; a fight counts only with
≥ 3 books quoting both sides. The same rows report the sportsbooks' overround
and the gap between last capture and start, beside DEV BFO consensus's
overround. Measured on ~1–2 cards; it is a rough number and is labelled so.

**Timing.** BFO consensus is not a price anyone could bet: it is an aggregate,
and its opener/closer have no timestamp. "Close" means "approximately the last
pre-fight market"; "open" means "approximately the first posted". Both are
said next to every number.

## 5. Metrics

- n bets, events, hit rate, mean vig-inclusive breakeven (1/decimal), mean
  de-vigged implied probability of the side bet.
- **ROI** = Σ pnl ÷ Σ stake, under A (and B, C).
- **95% interval** by resampling whole events (10,000 resamples, seed
  20261012, percentile), and a **Bonferroni interval** at 1 − 0.05/15.
- **CLV** (OPEN family only): `CLV_return = p_close_fair × decimal_open − 1`
  (CLV-001 §1.1 form; proportional de-vig), mean and event-bootstrap 95%.
- Per-year ROI, descriptive only, no inference.

## 6. Pass bar (fixed now)

A strategy **beats the market after costs** only if, under scenario **A**:

1. n bets ≥ 100, and
2. the Bonferroni (K = 15) event-bootstrap lower bound of ROI is above 0.

Clearing it only under **B** is reported as *"conditional on perfect line
shopping; not demonstrated"*. Clearing the nominal 95% bound but not the
Bonferroni one is reported as *"not demonstrated; consistent with chance across
15 tests"*. Scenario C never passes anything.

**What a pass would and would not mean.** Even a pass is non-confirmatory:
DEV data has been looked at many times, the d-strategies' factors were chosen
on data that includes these years, and v1–v3's 2023–24 results are already
published. PRED-001 §9: simulated ROI never supports a betting claim. A pass
would license only a prospective, locked test. A fail is a fail.

## 7. Things that will not be done

No threshold, band, strategy, price or date range changes after results are
seen. No subgroup is promoted to a headline. If a bug is found after results
are seen, the fix and its effect are reported as a dated correction beside the
original number, not in place of it.
