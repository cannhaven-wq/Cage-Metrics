# Phase 2 research design — sportsbook pricing and genuinely new fight variables

**2026-10-21, revised after the owner's decision D-034. A plan, not a run.**
Nothing here has been executed. Each experiment starts only after its own
preregistration is committed; items marked **owner** wait for the owner.
Companion to [`AUDIT_2026-10-21.md`](AUDIT_2026-10-21.md).

## Plain version

Two broad searches found that the fight statistics CFL already has add
nothing measurable to the closing odds. Running a third search over the same
statistics would mostly find noise. So the next program has two halves:

- **Prices.** Do individual sportsbooks post prices that the rest of the
  market then corrects? That can be measured from prices alone, as they are
  captured, without reading a single fight result — and it is the only route
  to something a bettor could actually use.
- **New information.** Before any modelling, a small, cheap pilot checks
  whether information the market may weigh poorly can be collected reliably
  and dated honestly: records from other promotions, amateur backgrounds,
  gyms, travel, and venue conditions like altitude.

**Three things stay separate throughout:** forecasting better than the odds
(information), finding prices the market later corrects (a pricing error),
and making money after the bookmaker's margin (profit). Evidence for one is
not evidence for the others.

---

## 0. Ground rules

- **No broad search.** Every experiment is one preregistered question.
- **DEV is explored.** Every pre-2025 year has been searched twice. A DEV
  result can rank an idea; it cannot confirm one.
- **No sealed outcome is read**, by anything in this plan.
- **Confirmation is expensive.** The sealed set (710 priced fights, 10 looks
  ever) can see a gain of about 0.008; prospective confirmation of 0.004 takes
  about 2,900 fights (~6 years). Plan for most tests to end "not detected".
- **Report the free gain.** Re-weighting the proportionally de-vigged market
  gains +0.001 to +0.002 on its own (audit §4.1). Every win-probability model
  reports a "re-weighted market only" baseline beside its result, and the
  engine's 0.003 size test is now measured against it (D-034).
- **No data exports or per-fight rows in the repository** (D-034). Results
  are committed as aggregates; inputs are pinned by sha256.
- **No production change, no append-only write, no paid service, no new
  scraper** without the owner.

## A. Sportsbook pricing

### A.0 What data exists and what it can support

| source | span | timestamps | bettable | supports |
|---|---|---|---|---|
| **W0 BFO consensus** (opener + closer per fighter) | 2007-07 → 2026-07-11 (6,953 fights before 2025) | none (1970 placeholder; opener and closer are *ordered*, not timed) | **no**: an aggregate; its closer's median margin is 7.7% in 2020–24 vs 4.1% at open (BT-001) | consensus calibration; favourite/long-shot shape by era; opener→closer *direction* |
| W1 BFO per-book scrape | 2 cards, May–June 2026 | not verifiable (rows after the card) | no | nothing |
| W2 Odds API legacy | Jul → mid-Sep 2026, sparse | yes, days before the bell | at capture only | nothing systematic |
| **W3 Odds API v4 with provenance** | from 2026-09-16 (first card 2026-09-19) | `retrieved_at`, `source_commence_at`, `market_status`, raw payload | **yes** (7 books) | book disagreement, outliers, movement and correction, per-book margins, CLV |
| Polymarket / Kalshi | prospective | yes | prediction markets | cross-market comparison only (CLV-001 Q-03) |

**Which W3 data the price-only studies may use.** Captures for cards on or
after **2026-10-12** (after PRED-001's RESERVE window). W3 captures for cards
before that date fall in RESERVE and stay unread.

### A.1 Reuse, not rebuild

`fight_odds` and the definer views `v_odds_books_sportsbooks`,
`v_fight_odds_latest_by_book`, `v_fight_market_vigfree`,
`v_fight_market_at_lock`, `v_fight_market_movement` (matched-book cohort,
refuses below three books) and `v_fight_start_best`; `cfl_engine/clv/devig.py`;
CLV-001's definitions (`CLV_return`, R-01–R-13); BT-001's coverage queries; the
capture cadence in `build/fetch-odds.js`. **No migration, no scraper change.**

### A.2 Rules for price-only research (owner condition 5)

1. **Prices only.** Reads are limited to `fight_odds`, `odds_books`, the
   market views above, and `fights` / `events` *booking* columns (ids, date,
   corners, scheduled rounds, start time). No query, export or script in a
   price-only study may name `winner_id`, `method`, `end_round`, `end_time`,
   any stat column, `fight_rounds`, or any table holding results. The
   preregistration lists the exact columns and a test enforces it on the
   study's folder, as PRED-001's experiment lint does.
2. **Fixed before evaluation.** Hypothesis, anchor times, quote-quality rules,
   scoring rule, sample size and analysis date are frozen in the
   preregistration and committed **before** any observation used for
   evaluation is read.
3. **Evaluation set = new observations only.** It is the cards whose first W3
   capture comes *after* the preregistration commit. Captures that already
   exist (cards from 2026-10-12 to the freeze) may be used **only** for a
   declared pilot that measures quote quality and the spread of the outcome
   variable, and never computes the hypothesis statistic.
4. **C2 first.** The prepared `fight_odds` lock (C2) should be in force
   before the evaluation clock starts, so the rows a study reads cannot
   change underneath it. Until then, each read records the row count and a
   hash of what it read.
5. **No writes.** Studies read through read-only exports kept out of the
   repository (D-034). Nothing is written to an append-only table or any
   production table without separate authorization.
6. **No profit language.** A positive `CLV_return` is evidence of beating the
   close, not of profit after the margin. A profit claim needs PRED-001 §9.

### A.3 Experiments, in priority order

**MKT-001 — Which de-vig describes the historical consensus?** (DEV, W0)
Which of proportional, power and Shin gives the best-calibrated BFO close,
by era, and how large is the re-weighting gain under each? Mostly computed
(audit §4.1); preregister, run once. *Value: high per hour* — it sets the
honest baseline every later win-probability test reports. *Limit:* an
aggregate nobody could bet.

**MKT-002 — Do outlier sportsbooks get corrected?** (prospective, W3;
preregistration draft: [`MKT-002_PREREGISTRATION_DRAFT.md`](MKT-002_PREREGISTRATION_DRAFT.md))
When one book's price sits away from the other books' consensus at a fixed
anchor time, does the close move toward that book (it was early and right) or
away (it was stale)? Scored by `CLV_return` of the outlier quote against the
eligible-book close. *Value: the highest available* — the one test of a
systematic pricing error that is also a price someone could have taken.
*Limit:* the sample grows only with new cards; the pilot fixes n.

**MKT-003 — Does late movement continue or reverse?** (prospective, W3) Is a
move between two anchor times followed by more move the same way before the
close? Same data, separate preregistration. *Value: moderate.* *Limit:* the
capture schedule is irregular; anchors are defined on elapsed time between
real captures.

**MKT-004 — Opener→closer on the historical consensus** (DEV, W0) only as a
calibration question. *Value: low* (the engine's `mk_move` was rejected).

**Per-book margin split** (descriptive, W3): how each book spreads its margin
between favourite and underdog. Feeds MKT-002's outlier definition.

## B. Fighter analytics from data CFL already has

Already ruled out on DEV (linear, against the close): raw striking and
grappling rates, simple matchup terms, knockout history, knockdowns absorbed,
experience, layoff, activity, streaks, cardio as a winner predictor. New work
here must be different in kind.

**PRED-002 — opponent-adjusted grappling** (draft PR #62; approved under
D-024, retained under D-034). Finish and freeze it rather than start a rival.
Before freezing it must carry the disclosures in
[`PRED-002_PRIOR_EXPLORATION.md`](PRED-002_PRIOR_EXPLORATION.md), including
that SYM-003 evaluated the same idea on the sealed years. *Value:* moderate.
*Limit:* expected null; target below what H1 can see.

**FA-001 — opponent-adjusted striking** through engine 1.1, using per-fight
totals the DEV export already holds. One family of two features. *Value:*
moderate (`d_sapm` was the strongest raw style term in both engine periods,
neither significant). *Limit:* DEV-only, exploratory; SYM-003 also tested
striking residuals on H1, so disclose it the same way.

`fight_rounds` (per round: strikes by target and position, takedowns,
knockdowns, control, submission attempts, reversals) is needed only for
round-level questions; a round-level cardio study belongs to fight *length*,
which DUR-001/002 govern and keep read-only.

## C. New fight variables — feasibility pilot (owner condition 8)

**Why.** Everything tested so far comes from UFCStats, which every
bookmaker also reads. Information that is harder to collect, or that the
market might weigh poorly, is where an edge could plausibly exist. The pilot
answers "can we get it, honestly dated, at useful coverage?" **before** any
model sees an outcome.

### C.1 Candidates

| variable | what CFL has today | candidate sources (terms unchecked) | point-in-time problem | informative fights (to be measured) |
|---|---|---|---|---|
| **Record in other promotions before the UFC** | nothing dated. `fighters.wins/losses` is today's career total, forbidden by PRED-001 §3; one Contender Series card in `fights_non_ufc` | Wikipedia fighter pages, Sherdog, Tapology, regional promotion sites | needs every bout dated, so only fights before each UFC bout count | every debut (both corners often), every fighter who left and returned |
| **Strength of those promotions** | nothing | as above; promotion-level results of UFC entrants | promotion strength must be computed from earlier entrants only | as above |
| **Amateur background** (amateur record, wrestling/BJJ/kickboxing credentials) | nothing | Tapology amateur records, Wikipedia, national-federation records | mostly static before debut; coverage likely patchy and biased toward well-known fighters | likely small; the pilot measures it |
| **Gym / camp and coach** | nothing | UFC.com bios (current), Wikipedia, Tapology | changes over time; current-day values leak. Dated history is the hard part | camp changes are rare events |
| **Travel** (distance, time-zone shift, home-country fight) | `events.location` (text); `fighters.country` (the country a fighter *represents*, hand-corrected, present-day) | event venue geocoding; residence/camp location from the gym source | country represented ≠ where a fighter lives and trains | time-zone shifts > 5 h are common on international cards; measured in the pilot |
| **Environmental** (venue altitude, fight-night local time, indoor climate is constant) | `events.location` | public elevation data for venue cities; event start times (`fight_start_estimates`, `bell_at`) | static and pre-known: no leakage risk | altitude cards are few (Mexico City, Denver, Salt Lake City): likely too few to detect anything but a large effect |
| **Late-breaking information** (short-notice replacement, missed weight) | nothing | official weigh-in results, news timestamps | must be timestamped *relative to the price* to matter | links to A: the question is whether prices move enough when it breaks |

### C.2 The pilot, in four steps, no outcomes read

1. **Sources and terms (desk).** For each source: terms of use, API or
   licence, robots rules, cost. **Any automated collection, new scraper or
   paid source needs the owner** (data rights are L3 item 9; spending is
   item 6). Output: a source table with a go/no-go per source.
2. **Hand-collected sample.** For 100 fighters on cards from 2026-10-12 on
   (prospective, no results needed) and 100 DEV-era debuts: collect each
   variable by hand from the approved sources. Measure coverage, how precisely
   each fact can be dated, agreement between two sources, and minutes per
   fighter. Stored as aggregates; the raw sheet stays out of the repository.
3. **Power before outcomes.** From booking data only (no results), count the
   DEV fights where each variable would differ between the corners, and
   compute the smallest effect each could detect (as DISC-001's positive
   control did). A variable that applies to 1 fight in 20 needs roughly a
   57% effect at even odds to be visible.
4. **Gate.** A variable goes to a DEV experiment only if: its source is
   cleared; coverage is at least 80% of informative fights; each fact can be
   dated before the bout; and step 3 shows a plausible effect is detectable.
   Otherwise it becomes a **prospective-capture** candidate: recorded before
   each future card. That needs storage, which is a production change for the
   owner.

*Value:* this is the only part of the program that can add information the
market does not already read from UFCStats. *Limits:* collection is slow,
coverage is likely biased toward famous fighters, and the market already uses
much of this (debut prices are set from pre-UFC records). The pilot exists so
that "no" is cheap.

## D. Proposed next sprint

| # | task | level | value | limits |
|---|---|---|---|---|
| 1 | Engine 1.1 (done in this PR): E1, E2, E3 fixed; E4 recorded | — | trustworthy future leads | no new result |
| 2 | MKT-001 preregistration and single run | L1 | high per hour: the honest baseline | aggregate, not bettable |
| 3 | MKT-002: freeze the draft, run the quote-quality pilot on existing post-10-12 captures, then evaluate only new cards | L1 under D-034's conditions; C2 first | highest available | months of cards |
| 4 | New-variable pilot, steps 1–3 | L1; any collection beyond hand sampling or any spend is **owner** | the only route to genuinely new information | slow; patchy coverage |
| 5 | Freeze PRED-002 with the disclosures | L1 (approved direction) | moderate | expected null |
| 6 | FA-001 through engine 1.1 | L1 | moderate | DEV-only, exploratory |

**Not in the sprint:** another broad hypothesis search, DISC-002, buying
historical odds, any new scraper, any sealed-set look, anything on the site.
