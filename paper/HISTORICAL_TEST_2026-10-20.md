# Does UFC price shopping work? Historical test of M1, 2026-10-20

**Finding, plainly.** The data CFL holds cannot answer it. M1 has never been
tested on a single settled bet. Of the 14 past cards with per-sportsbook
prices, 9 cannot be replayed at all (no start time was recorded before the
decision instant), and on 4 of the remaining 5 every price was more than the
60-minute limit old at the decision instant. The one card where the rules
could actually run is in a sealed window, so its result is not read. There is
**no ROI**, no profit, and no evidence for or against an edge. The missing
data is identified below; the only source that has it is paid.

Status: exploratory. Nothing here is a validated finding.

## What was pinned before anything was computed

- `paper/config/strategy_draft.json` sha256
  `4eaf5c3eab3cfd987bb9fab8c56a307e0218a75f1c4184ad52be4c35f1368555`
  (last changed in `8549c9c`), pinned at `f82fb91` and enforced by
  `--expect-config-sha256`. M1 as written: ≥ 2% expected return against the
  margin-free median of ≥ 3 *other* eligible sportsbooks, seven configured
  books, −400…+400, 60 minutes on both capture and provider timestamps, rank
  by reference return then fight id then venue id, 1 unit, ≤ 4 units and 1
  selection per fight per card, 100-unit bankroll, stop at 70, lock =
  earliest verified start − 360 min. Nothing was changed.
- Only M1 was replayed. S1 (the model filter) was not: the question was
  whether price shopping works before the predictor is added.

## Which tests the data supports

| source | dates | venues | price type | timestamps | size / limits | supports the M1 replay? |
|---|---|---|---|---|---|---|
| CFL `fight_odds`, BFO consensus (book 6) | 2007 → 2026-07 | one consensus | closing consensus | placeholder 1970 | none | **No** — one consensus cannot show price shopping |
| CFL `fight_odds`, per-book rows | 2026-05-30 → now (14 settled cards) | 7 configured books (+3 unconfigured) | posted sportsbook prices | capture time; provider time from 2026-09-16 only | none | **Partly** — see eligibility below; all but one settled card is sealed |
| CFL `fight_odds`, Polymarket (book 7) | 2026-05 → now | 1 | displayed price; both sides sum to 1.00 | capture time | none | **No** — a displayed price is not a fill |
| CFL `polymarket_books` captures (private file) | 2026-10-20 only | 1 | executable ask ladder + market fee | retrieval + book time | yes | Only for an unsettled card |
| The Odds API historical (paid) | 2020-06-06 → now, 10-min snapshots, 5-min from 2022-09 | each US/UK/EU/AU book | posted sportsbook prices | snapshot time + bookmaker/market last_update | none | **Yes, as posted prices** (limits stay unknown) |
| BestFightOdds | 2007 → now | many books | posted prices; summaries | no per-change timestamps verified | none | No (no API; timestamps unverified; terms unchecked) |
| Polymarket data API / prices-history | 2022-11 → now; per-bout UFC books mainly 2024+ | 1 | trades (fills of others) / midpoint | yes | trade size only | No historical order book: "No orderbook exists for the requested token id" |

The external rows come from official documentation (The Odds API pages were
read through search-indexed copies; that host is blocked here) and free
requests to Polymarket's public APIs.

## Eligibility, every card

All 14 past cards with configured-book rows, chronological. A card is
**missed** when the pinned lock cannot be formed: no provider start time had
been observed for any active bout before the decision instant.

| card | partition | evidence class | outcome | decision instant | bouts | bet | pass | abstain |
|---|---|---|---|---|---:|---:|---:|---:|
| 2026-05-30 | H1 (sealed) | — | missed: no start time | — | 13 | | | |
| 2026-06-06 | H1 | — | missed: no start time | — | 16 | | | |
| 2026-07-11 | H1 | — | missed: no start time | — | 16 | | | |
| 2026-07-18 | RESERVE (sealed) | — | missed: no start time | — | 16 | | | |
| 2026-07-25 | RESERVE | — | missed: no start time | — | 17 | | | |
| 2026-08-15 | RESERVE | — | missed: no start time | — | 15 | | | |
| 2026-08-22 | RESERVE | — | missed: no start time | — | 14 | | | |
| 2026-08-29 | RESERVE | — | missed: no start time | — | 14 | | | |
| 2026-09-12 | RESERVE | — | missed: no start time | — | 16 | | | |
| 2026-09-19 | RESERVE | decision-only | all stale (newest quote 1,667 min old) | 09-19 15:45 | 12 | 0 | 0 | 12 |
| 2026-09-26 | RESERVE | decision-only | all stale (191 min) | 09-25 18:00 | 13 | 0 | 0 | 13 |
| 2026-10-03 | RESERVE | decision-only | all stale (284 min) | 10-02 18:00 | 15 | 0 | 0 | 15 |
| 2026-10-10 | RESERVE | decision-only | **eligible** (53 min) | 10-09 18:00 | 12 | 1 | 9 | 2 |
| 2026-10-17 | unsealed | **settled** | all stale (164 min) | 10-17 15:10 | 13 | 0 | 0 | 13 |

Decision instants on the 09-26, 10-03 and 10-10 cards fall on the previous
evening because at least one active bout had no provider start yet, so the
pinned date-only fallback (00:00 UTC − 6 h) applied. The next sportsbook
capture after each instant came 5–220 minutes later.

**Eligible opportunities with zero qualifying bets** (a valid "no bets"
result): none. **Zero eligible opportunities because data is missing:** the
settled card and 3 sealed cards (stale quotes), plus 9 missed cards. The
only eligible card (2026-10-10, 10 priced bouts with a fresh reference) gave
1 selection at +3.1% expected return against the reference; it is sealed,
so it is not settled and has no profit figure.

## Results by strategy, year and card

| strategy | year | settled cards | bets | turnover | profit | ROI | max drawdown | coverage |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| M1 | 2026 | 1 (2026-10-17) | 0 | 0.0 | 0.0 | n/a | 0.0 | 13 of 13 bouts decided (all abstain) |

Bankroll: one continuous ledger from 100.0, settled after each card; it ended
at 100.0 because nothing was staked. The stop at 70 was never approached. On
the decision-only sealed cards the stop cannot be evaluated (nothing is
settled); those decisions assume it had not triggered.

**Uncertainty:** with no settled bet there is nothing to resample; a
card-level bootstrap is not estimable. Concentration in individual fights:
not applicable. For scale, the per-bet profit spread measured on 2023–24
(about 1.07 units) means a +3% true ROI needs roughly 7,800 bets to
distinguish from zero.

**Contamination.** The 2026-10-17 card's results were seen during the
investigation earlier the same day, before these thresholds were written, so
even a non-empty result there would have been exploratory only.

## Arbitrage, same history (outcome-free)

Opposite sides at two venues, $100 combined, split to equalise the two
winner payoffs, stakes in whole cents. Only instants **before the earliest
start ever recorded for the bout** count: the widest "arbitrages" in the raw
scan (e.g. +600 against −115) were in-fight prices captured after the bout
had started, and `is_live` cannot flag them because `bell_at` is never filled.

| class | count | meaning |
|---|---:|---|
| sportsbook pairs, mathematically favourable at quoted prices | **8 episodes, 5 bouts** | margins 0.988–0.997: $0.28–$1.20 on $100 at the quoted prices; each seen at 1–2 captures; 7 of 8 involve BetOnline; all on sealed-window cards |
| sportsbook pairs on bouts with no recorded start | 4 | cannot be shown to be pre-fight; not counted |
| simulated executions | **0** | not reachable: sportsbook limits are unknown |
| Polymarket + sportsbook, 2026-10-20 executable books | 150 combinations, **0 favourable** | best worst-case winner payoff −$1.91 on $100 |
| second leg unfilled | 0 | |

For every sportsbook pair the draw / no-contest / cancellation / changed-
opponent payoff rests on an **assumed** refund at both books; no book's rule
is in the data, so none of the 8 establishes an arbitrage. A Polymarket leg
pays $0.50 a share on a void (its resolution text says "resolve 50-50") while
a sportsbook refunds: the void state of a Polymarket favourite against a
sportsbook underdog loses money even when both winner states profit.

## Polymarket economics

- **Fee fields.** Gamma `feeSchedule {rate 0.05, exponent 1, takerOnly,
  rebateRate 0.15}`, `feeType sports_fees_v3`; CLOB `/fee-rate base_fee 1000`
  and market `taker_base_fee 1000`; market `version "v1"`. **The schedule
  governs.** docs.polymarket.com/trading/fees: fee = C × feeRate × p × (1 − p),
  "See Market Details to read the fee parameters", Sports taker rate 0.05,
  "you don't include fee information in your orders". The `1000` is the
  legacy rate signed into each v1 order: the CTF exchange charges it as a
  ceiling (`CalculatorHelper.sol`), and the FeeModule "refunds orders' fees if
  they are charged more than the operator's intent" (exchange-fee-module
  README). Both raw values are kept on every capture; the ceiling is a
  sensitivity formula the evaluator refuses to use for a decision.
- **Collected in shares on a buy.** Help Center (Maker Rebates): "fees are
  collected in shares on buy orders and USDC on sell orders". Contract:
  a BUY's fee is "charged on Token Proceeds … (outcomeTokens/price)", so
  fee_shares = fee_collateral / execution_price.
- **Checked values** (100 shares, Sports rate): 0.25 → $0.9375 = 3.75 shares;
  0.50 → $1.25 = 2.5 shares; 0.75 → $0.9375 = 1.25 shares. These reproduce
  the documented table ($0.94 / $1.25 / $0.94 in cents). Fees are rounded to
  5 decimals per match, as documented (rounding mode not documented;
  half-up used).
- **Verified means matched, not present.** A capture marks the fee rule
  verified only when fees are enabled, the schedule is taker-only with
  exponent 1, its category is documented, and its rate equals the documented
  rate. Not verified against an observed on-chain fill.
- **Expected returns assume a decided fight.** Every offer now says so and
  states its void payoff (sportsbook: refund, assumed; Polymarket: 0.50 a
  share). No draw or cancellation probability is invented.
- Missing Polymarket history did not block the sportsbook replay; historical
  Polymarket offers simply do not exist in it.

## Exclusions and data handling

- Sealed partitions (H1 2025-01-01 → 2026-07-11, RESERVE → 2026-10-11): their
  **prices** were read for the decision-only replay and the arbitrage scan;
  **no outcome was read in this task**, and the replay refuses an outcome
  file containing a sealed fight. Earlier the same day, before this task, the
  investigation did read RESERVE outcomes (realised results on 2026-09-19 →
  10-10 cards) and the MMA-001 feature history contains 2025–26 results; both
  are disclosed in the handoff.
- Quote rows dropped by rule are counted per card in `replay_report.json`
  (opponent mismatch, fighter not on the card, live, non-open, provider time
  after the instant). Unconfigured books (Caesars, BetWay, Unibet, Kalshi)
  never enter M1. One assumption: which bookings were on a card is today's
  `is_active`; no retired booking had a fresh quote at its card's instant.
- Raw prices, the review sample and the worked trace are in the git-ignored
  `paper/private/replay/` and were sent to the owner directly.

## Reproduce

Branch `claude/focused-maxwell-yru5a1` of `cannhaven-wq/Cage-Metrics`
(commit in the handoff). Inputs (sha256 of canonical JSON, recorded by the
replay): quote rows `a9192084…0d1abc`, card metadata `b959f1e9…d3bd1795`,
unsealed outcomes `32afd972…f6a67edd`; UFC 333 window rows `2d5b7965…8373226`;
Polymarket books file sha256 `6a5f6daa…7fce14`. The extraction statements are
in `paper/replay_extract.sql`.

```bash
python3 -m pytest -q tests/paper
python3 paper/review_sample.py --data paper/private/replay --out paper/private/replay/out
python3 paper/replay.py --data paper/private/replay --out paper/private/replay/out \
  --expect-config-sha256 4eaf5c3eab3cfd987bb9fab8c56a307e0218a75f1c4184ad52be4c35f1368555
python3 paper/arbitrage.py --data paper/private/replay --out paper/private/replay/out
```

## What is missing, exactly

1. **Per-book, timestamped sportsbook prices for unsealed settled cards.**
   The Odds API historical endpoint has them from 2020-06-06. Product: a paid
   usage plan (the indexed pricing page lists 20K credits at $30/month;
   confirm on the live page). Cost per card at one decision instant: one
   historical events call plus one odds snapshot, 10 credits per region per
   market; `us` only ≈ 11 credits/card, ≈ 2,200 for ~200 cards from 2020-06
   to 2024-12 (all DEV, outcomes usable). It answers: does M1 qualify bets,
   and do they win, on ~2,000 fights the protocol lets us score. It cannot
   answer what stake a book would have accepted. **Not purchased** — spending
   money is the owner's decision.
2. **A capture schedule that lands inside 60 minutes of each lock.** Going
   forward this is the binding constraint: on 4 of 5 lockable cards every
   quote was 53–1,667 minutes old at the instant.
3. **Sportsbook limits and void rules** — not in any source examined.

**Next action:** owner decides whether to buy one month of The Odds API's
historical access for a DEV-period (2020-06 → 2024-12) M1 replay; the code
above runs on it unchanged once the snapshots are exported into the same
three files.
