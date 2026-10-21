# Phase 2 research design — sportsbook pricing and fighter analytics

**2026-10-21. A plan, not a run.** Nothing here has been executed. Each
experiment below starts only with its own preregistration committed first,
and the ones marked *owner* wait for the owner. Companion to
[`AUDIT_2026-10-21.md`](AUDIT_2026-10-21.md).

## Plain version

Two broad searches found that public fight statistics add nothing measurable
to the closing odds. Running a third would mostly find noise. So Phase 2 asks
fewer, sharper questions:

- **Prices:** do individual sportsbooks get prices wrong in ways the rest of
  the market then corrects? That can be measured from prices alone, as they
  are captured, without waiting for fight results — and it is the only route
  to something a bettor could actually use.
- **Fighters:** two narrow ideas the searches did not test — wrestling and
  striking measured against the quality of past opponents — each asked once,
  with the answer "probably no" written down in advance.

**Three things stay separate throughout:** forecasting better than the odds
(information), finding prices the market later corrects (a pricing error),
and making money after the bookmaker's margin (profit). Evidence for the first
is not evidence for the other two.

---

## 0. Ground rules that shape everything

- **DEV is explored.** Every pre-2025 year has now been searched twice. A DEV
  result can rank an idea; it cannot confirm one.
- **Confirmation is expensive.** The sealed set (710 priced fights, 10 looks
  ever) can see a gain of about 0.008; realistic gains are 0.003 or less.
  Prospective confirmation of a 0.004 gain takes about 2,900 fights (~6 years).
- **Any "edge" needs a price someone could bet.** BFO's historical consensus is
  not one (BT-001). Only timestamped single-book quotes are, and they start on
  2026-09-19.
- **Report the free gain.** Re-weighting the proportionally de-vigged market
  gains +0.001 to +0.002 on its own (audit §4.1). Every model reports a
  "re-weighted market only" baseline beside its own result.

## A. Sportsbook pricing research

### A.0 What data exists, and what it can support

| source | span | timestamps | bettable | supports |
|---|---|---|---|---|
| **W0 BFO consensus** (opener + closer per fighter) | 2007-07 → 2026-07-11 (6,953 fights before 2025) | none (1970 placeholder; opener and closer are *ordered*, not timed) | **no** — an aggregate; its closer carries a 7.7% median margin in 2020–24 vs 4.1% at open | consensus calibration; favourite/long-shot shape by era; opener→closer *direction* |
| W1 BFO per-book scrape | 2 cards, May–June 2026 | not verifiable (rows after the card) | no | nothing |
| W2 Odds API legacy | Jul → mid-Sep 2026, sparse | yes, but days before the bell | at capture time only | nothing systematic |
| **W3 Odds API v4 with provenance** | from 2026-09-16 (first card 2026-09-19) | `retrieved_at`, `source_commence_at`, `market_status`, raw payload | **yes** (7 books) | book disagreement, outlier prices, movement and correction, per-book favourite/underdog margin, CLV |
| Polymarket / Kalshi | prospective | yes | prediction markets, not sportsbooks | cross-market comparison only (CLV-001 Q-03) |

### A.1 Reuse, not rebuild

All of this exists and is enough: `fight_odds` and the definer views
`v_odds_books_sportsbooks`, `v_fight_odds_latest_by_book`,
`v_fight_market_vigfree`, `v_fight_market_at_lock`, `v_fight_market_movement`
(matched-book cohort, refuses below three books), `v_fight_start_best`;
`cfl_engine/clv/devig.py` and `settle_clv.py`; the CLV-001 definitions
(`CLV_return`, eligible books, R-01–R-13); BT-001's coverage queries
(`research/backtest/coverage_queries.sql`); the capture cadence in
`build/fetch-odds.js`. **No migration and no scraper change is needed.** One
prerequisite is not research: the prepared `fight_odds` lock (C2) should be
applied before any prospective price study starts its clock, so the rows it
reads cannot change underneath it.

### A.2 Experiments, in priority order

**MKT-001 — Which de-vig describes the historical consensus?** (DEV, W0)
Question: across eras, which of proportional, power and Shin gives the
best-calibrated BFO close, and how large is the re-weighting gain under each?
Mostly computed already (audit §4.1); preregister, run once, publish
internally. *Information value: high per hour* — it sets the honest baseline
every later win-probability test must beat. *Limit:* describes an aggregate
nobody could bet; says nothing about profit.

**MKT-002 — Do outlier sportsbooks get corrected?** (prospective, W3,
**owner**: needs approval to read post-2026-10-12 prices before outcomes exist)
Question: when one book's price for a fighter sits away from the other books'
de-vigged consensus at capture time *t*, does the consensus at the close move
toward that book (the book was early and right) or away (the book was stale
and wrong)? Measured as CLV-001's `CLV_return` of that quote against the
eligible-book close. Prices only; no fight outcome is read. *Information value:
the highest available* — it is the one test of a systematic pricing error
that is also a price someone could have taken. *Limits:* the sample grows only
with new cards (about 12 bouts × 6–7 books per card); the per-quote spread of
`CLV_return` has not been measured yet, so the first step is a dated pilot
that measures it and states the required number of cards before any result is
read. Positive CLV is evidence of beating the close, not of profit after the
margin; a profit claim still needs PRED-001 §9.

**MKT-003 — Does movement continue or reverse?** (prospective, W3, same
approval) Question: is the move over the last *k* hours before the bell
followed by further move in the same direction, or by reversal? Price-only,
same data as MKT-002, separate preregistration. *Value:* moderate. *Limit:*
GitHub delivers the capture schedule irregularly (4 wakes on one measured
day); horizons must be defined on elapsed time between real captures.

**MKT-004 — Opener→closer on the historical consensus.** (DEV, W0) The engine
already tested opener-to-closer movement as a factor (`mk_move`, rejected).
Only worth running as a calibration question ("is the closer better than the
opener, by how much, by era?"). *Value:* low. *Limit:* ordered, not timed.

**Per-book favourite/underdog margin** (descriptive, W3) — how each book
spreads its margin between favourite and underdog. No hypothesis test; feeds
MKT-002's definition of an outlier.

## B. Advanced fighter analytics

### B.0 Data

- **`fight_rounds`**: one row per round, 37 columns, per corner — significant
  strikes landed/attempted, takedowns landed/attempted, knockdowns, control
  seconds, submission attempts, reversals and the strike breakdowns
  (`cfl_engine/export_rounds.py`, T-086 plan). 25 completed fights have no
  rounds: 21 from 1994–98, 3 duplicates excluded by PRED-001, 1 scraper loss
  (T-093). **Neither existing export contains it**; the engine's export holds
  per-fight totals, including head/body/leg and distance/clinch/ground.
- A DEV-only round export is a read-only `SELECT` with `event_date <
  2025-01-01` in SQL, like the two existing exports — no migration. The agent
  environment cannot reach the database, so it runs as a one-off job or by the
  owner, and its output follows whatever the owner decides about committed
  exports (audit §6).
- Reusable: `cfl_engine/engine.py` (point-in-time career features),
  `cfl_engine/cardio/` (fade-slope model; `fighter_cardio.csv` is fitted on
  today's data and **may not be used as a feature** — refit point in time),
  `v_fighter_consistency` v7 and `v_fighter_style` (both compute from all
  history: rebuild point in time before use), the engine's audits and ledger.

### B.1 What the searches already ruled out (DEV, linear, against the close)

Raw striking and grappling rates (`d_slpm`, `d_sapm`, `d_str_def`,
`d_td_per15`, `d_td_def`, `d_ctrl_pct`, `d_kd_per15`), simple matchup terms
(`mu_grapple`, `mu_net_strike`, `mu_strike_eff`), knockout history and
knockdowns absorbed (DISC-001 F01–F06), and cardio as a winner predictor
(50.2% on market-even fights, already retired). New work must be *different
in kind*, not a re-cut of these.

### B.2 Experiments

**PRED-002 — opponent-adjusted grappling** (draft PR #62, owner-approved as
the first PRED-001 experiment, D-024). Finish and freeze it rather than start
a rival. **Before freezing it must disclose** that the engine's Phase 1 looked
at takedown defence, takedown rate, control share and `mu_grapple` on all DEV
years. *Value:* moderate — the one adjustment never tested. *Limit:* its own
draft expects "probably no", and its 0.006 target is below what the sealed set
can see.

**FA-001 — opponent-adjusted striking.** Each fighter's significant strikes
landed and absorbed per minute relative to what each past opponent typically
allowed and threw, with empirical-Bayes shrinkage for short records, one
antisymmetric difference, run through the engine. Uses per-fight totals that
are already exported. *Value:* moderate; `d_sapm` was the strongest raw style
term in both engine periods (+0.0010, +0.0012, neither significant).
*Limit:* one family of two features, single look on DEV, non-confirmatory.

**FA-002 — accumulated head damage.** Time-decayed significant head strikes
absorbed plus knockdowns absorbed. *Value:* low — DISC-001's knockdown and
knockout-damage factors were null and "chin" stories are widely priced. Run
only if FA-001 is run anyway (same export, same machinery).

**Not proposed:** cardio decline as a winner factor (measured null), and style
labels × anything (the engine's matchup terms were null and the labels are not
point in time). A round-level cardio study belongs to fight *length*, which
DUR-001/DUR-002 govern and which is read-only until their evaluation points.

### B.3 Sample-size limits, stated before any run

- All priced DEV fights: 6,824. That is plenty to *rank* a common feature
  (DISC-001's positive control found a 57% age-sized effect every time), but
  every year of it has been searched, so a DEV result is exploratory only.
- Sparse subgroups (DISC-001's proposed DISC-002): about 930 fights for
  "coming off a KO loss"; its own positive control says only effects of about
  57–60% at even odds are visible. **Low value; not recommended.**
- Whatever DEV suggests, the sealed set sees ~0.008 and prospective
  confirmation takes years. Plan for most of these to end "not detected".

## C. Proposed next sprint

| # | task | level | expected information value | limits |
|---|---|---|---|---|
| 1 | Engine v1.1: fix E1 (de-vig gate) and E3 (contamination flags); E2 per the owner's choice; new `config_id`; commit config before running | L1 (E2 owner) | makes any future lead trustworthy | no new result |
| 2 | MKT-001 preregistration and single run | L1 | high per hour: fixes the honest baseline | aggregate, not bettable |
| 3 | MKT-002 pilot: measure the spread of `CLV_return` for outlier quotes, then fix n | **owner** (read post-freeze prices); after C2 | highest available | needs months of cards |
| 4 | Freeze PRED-002 with the engine disclosure | L1 (draft already owner-approved) | moderate | expected null |
| 5 | FA-001 through engine v1.1 | L1 | moderate | DEV-only, exploratory |

**Not in the sprint:** another broad hypothesis search, DISC-002, buying
historical odds, any new scraper, any sealed-set look, anything on the site.
