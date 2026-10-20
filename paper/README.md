# Paper-trading system (private research; DRAFT; not running)

**Status, plainly:** this is a draft implementation with tests. Nothing is
scheduled, nothing writes to the database, no forecast is locked, no paper
bet has been recorded against a real card, and no edge has been shown. The
investigation that precedes it (2026-10-20) found none.

The question it is built to answer: does MMA-001's probability, applied to the
best *executable* price across seven sportsbooks and Polymarket, pick
profitable selective bets — compared with the same price rule and no model?

## What is here

| file | what it does | network / db |
|---|---|---|
| `config/strategy_draft.json` | every rule, as data: venues, reference cohort, freshness, price band, M1/S1 thresholds, staking, caps, stop, lock lead | none |
| `pricing.py` | normalises a sportsbook price and a Polymarket purchase to "risk 1 unit, net if win"; walks the ask ladder with the market's fee; rejects hypothetical fills | none |
| `reference.py` | the margin-free consensus of ≥3 *other* eligible sportsbooks, both timestamps fresh; never the BFO placeholder, the synthetic consensus, Polymarket or Kalshi | none |
| `strategy.py` | M1 / S1 decisions per fight: bet / pass / abstain with the reason; ranking; card cap; bankroll stop | none |
| `ledger.py` | append-only, hash-chained JSONL ledger; one lock per card per strategy version; reruns refused | file only |
| `settle.py` | settlement (win / loss / push / cancel on corner change), per-strategy metrics over the same cards, CLV reported `unavailable` unless CLV-001's prerequisites are met | none |
| `data.py` | snapshot loader; read-only Supabase pull; the lock instant | read-only REST, optional |
| `run_card.py` | the CLI: dry run by default; `--write` appends the ledger; `--execute-locks` is refused without `PAPER_ALLOW_LOCK_WRITE=1` | as above |
| `mma001/model.js` | the Doc's MMA-001 source, transcribed verbatim; `test.js` is the Doc's own checks | none |
| `mma001/forecast.js` | prospective inference only: replays all history (any date), no fitting, no scoring, corner symmetry asserted | none |
| `private/` | **git-ignored**: the artifact (`mma001_artifact.json`), history exports, snapshots, ledgers, dry-run output | — |
| `../tests/paper/` | 19 tests: swapped corners, stale quotes (both timestamps), missing fees, insufficient depth, settlement rules, changed opponent, duplicate run, card cap, late lock, bankroll stop, band, reference exclusions, forecast symmetry, end-to-end | — |

In `cage-metrics-odds-scrapper`: `polymarket/capture_book.py` (executable
order books, fee rate per market, status, resolution text; writes a private
table or a JSONL file, never `fight_odds`), `polymarket/polymarket_books_migration.sql`
(proposed, not applied), `polymarket/test_capture_book.py` (5 tests on
recorded fixtures), and a minimal change to `scrape.py` so it can be
imported without credentials (the client is created on first use; behaviour
of a normal run is unchanged).

## The model

MMA-001 is used exactly as the Doc saved it. `private/mma001_artifact.json`
is the Doc's `artifact.json` verbatim (sha256
`fb271929eb5326d3f306e4b90715741c05ae924ff8ea84b84d93086b5df7cfbf`). An
independent refit from the DEV export reproduces every coefficient to
8e-16, so the artifact is the model the Doc describes. It is **not frozen
under PRED-001** (no registration, no author provenance, no independent
point-in-time audit) — all three are listed in the approval bundle.

`forecast.js` reads post-2024 results to build features for upcoming bouts.
That is the one place sealed-period outcomes are read, it is inherent to a
prospective forecast, and it never evaluates or fits anything. The DEV
history in `private/history_all.json` is the fingerprint-matched export plus
970 settled 2025–26 bouts pulled with the Doc's own export recipe.

## Fees and the Polymarket platform — what is verified and what is not

- The feed is **Polymarket's global exchange** (`gamma-api.polymarket.com`,
  `clob.polymarket.com` — polymarket.com, not polymarket.us).
- Fee form applied: the published taker fee `fee = C × rate × p × (1 − p)`
  with C the shares traded, makers 0. **On a BUY the fee is collected in the
  outcome shares received** (Polymarket Help Center, "Trading fees"; the
  owner confirmed this reading on 2026-10-20), so `polymarket_fill` spends
  the cash at the ask, receives gross shares, and withholds
  `gross × rate × p × (1 − p)` shares; the payout is the net shares. The
  first draft added the fee to the cash cost instead, which is a different
  instrument. The **rate is read per market from the exchange** (`/fee-rate`,
  then the market's own fee field) and never hard-coded. A book whose rate
  could not be read is stored with `fee_rule_verified = false` and the
  evaluator rejects it; `fee_rule_must_be_verified: true` in the draft
  config keeps that guard on.
- **Not verified from this environment:** polymarket.com, docs.polymarket.com
  and help.polymarket.com are unreachable here (proxy 403 / DNS). The
  `/book` and `/fee-rate` endpoint shapes come from the official
  documentation as indexed by search and from the API's documented response
  fields. The per-category rate for UFC markets is whatever the exchange
  reports for the market at capture time.
- Settlement: only markets whose resolution text reads as a plain
  fight-winner market with no draw/NC-to-one-side clause are `settlement_ok`.
  A 50-50 resolution on a draw is *not* comparable with a sportsbook push and
  is rejected.

## The lock

One predetermined lock per card: `earliest verified start − 360 min`, where
verified means `bell_at` or the provider's commence time. If any active bout
on the card only has an `event_date_fallback` start, `win_model_locks`'
deadline (00:00 UTC of the event date) is earlier and wins. A run before the
instant reports `before_lock`; a run more than 60 minutes after it reports
`late` and the card is recorded as missed, never locked late. For UFC 333
(all prelims commence 14:00 UTC) the lock is **2026-10-24 08:00 UTC**.

Quote freshness is judged at the lock instant on both `captured_at` and the
provider's `last_update`, 60 minutes. **The sportsbook capture is hourly on
card day and daily otherwise, and GitHub throttles it; on the last card the
measured gaps were 2–4 hours.** A lock that lands in a gap abstains on every
fight. That is correct behaviour and it is also a real constraint: see the
dry run.

## Dry run, 2026-10-20 (read-only snapshot of UFC 333, 15 bouts, 80 quotes, 6 books)

Evaluated at the snapshot's capture instant (18:36 UTC) every fight
**abstained**: the newest quotes were 75 minutes old. Evaluated at the quote
instant (17:22 UTC) — a demonstration of the evaluator, not a lock — see
`private/dryrun_ufc333_at_quotes.json`; the summary is in the handoff. No
Polymarket books were available (the exchange is unreachable from here), so
no Polymarket offer was considered.

## Commands

```bash
# tests
python3 -m pytest -q tests/paper
(cd ../cage-metrics-odds-scrapper && python3 -m pytest -q polymarket/test_capture_book.py)
node paper/mma001/test.js

# dry run on a saved snapshot (prints decisions and the would-be lock rows; writes nothing)
PAPER_MODEL_ARTIFACT=paper/private/mma001_artifact.json \
python3 paper/run_card.py --snapshot paper/private/snapshot_ufc333_2026-10-20.json --now 2026-10-24T08:05:00+00:00

# read-only look at the captured market before the lock (never recorded)
python3 paper/run_card.py --snapshot ... --evaluate-at-capture --now <quote instant>

# live read-only pull (needs SUPABASE_URL and a service key in the environment)
python3 paper/run_card.py --live

# record a lock and its decisions to the private ledger (file only)
python3 paper/run_card.py --live --write

# settle open selections once results are in
python3 paper/run_card.py --settle --live --write

# Polymarket order books to a private file (needs the exchange reachable)
(cd ../cage-metrics-odds-scrapper && python3 polymarket/capture_book.py --out /private/books.jsonl)
```

Writing `win_model_locks` rows (`--execute-locks`) additionally needs
`PAPER_ALLOW_LOCK_WRITE=1`: that is the owner's switch, because the first
lock starts prospective collection under PRED-001.

## Thresholds (starting assumptions, not findings)

- **M1 ≥ 2%:** the sportsbook consensus's own spread across books is about
  2–3 points a side; below that a "better price" is inside the measurement
  noise of the reference.
- **S1 ≥ 3% on the model:** MMA-001's mean disagreement with the market is 3.6
  points; 3% selects fights where it actually disagrees.
- **−400…+400:** outside that band one result dominates a season of paper.
- **1 unit, 4 per card, stop at 70:** flat, so no result is weighted by
  confidence; the stop forces a review rather than a resize.
- **60 minutes:** a price older than that is a historical fact, not an offer.

None of these was tuned on observed results, and this README is where a
change must be justified before it is made.

## Approval bundle (the smallest set that starts paper trading)

1. **Freeze MMA-001** under PRED-001: registry entry, `pred-registration`
   block, author provenance, independent point-in-time audit. Until then the
   locks it writes are not an experiment.
2. **Allow the lock writer:** set `PAPER_ALLOW_LOCK_WRITE=1` and the service
   key in the environment that runs `run_card.py --live --write --execute-locks`
   at each card's lock instant (a scheduled job is not created by this work).
3. **Polymarket:** apply `polymarket_books_migration.sql` (L3, new
   append-only table) and schedule `capture_book.py` at the lock instant;
   confirm the fee rule against the live documentation and flip nothing else.
4. **Ledger location:** the private JSONL file is enough for a start; a
   database table is not required and is not prepared.

What stays unavailable until separately approved: CLV (the `clv001_columns`
and `event_flow` migrations), and any public mention of any of this (D-011).
