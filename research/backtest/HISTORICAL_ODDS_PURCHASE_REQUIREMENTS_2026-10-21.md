# Historical odds purchase — requirements (owner decision E3)

**Status: budget approved (up to $30); nothing purchased.** The CFL Owner
decides when to spend it. Anything learned from this data is exploration. It
is never evidence of a prospective betting edge, and it never appears on a
public page as one.

## What to buy

- **Provider:** The Odds API, historical odds endpoint. It is the provider
  CFL's live capture already uses, so books and fields line up.
- **Market:** MMA, head-to-head (moneyline), US-region sportsbooks.
- **Window:** mid-2020 (the earliest available) through **2024-12-31 only**.
  Anything from 2025 on would buy sealed PRED-001 data, and must not be
  bought or read.
- **Sampling:** one snapshot per bout close to the scheduled start, plus one
  about 24 hours earlier, so price and movement can both be measured.
- **Size and cost (approximate, provider site unreachable from here):**
  - about 2,300 fights and 190 cards;
  - about 15,000 credits, with historical calls billed at 10× normal;
  - about $30 for one month of credits.
  - Confirm the price on the provider's page before buying.

## How it may be used

1. Pre-register first, as BT-001 did: plan committed before any result.
2. Read only cards dated before 2025-01-01.
3. Treat every result as exploratory. The pre-2025 years already helped
   choose the factors and calibrate v1–v3, so a positive result there can
   only suggest what to test prospectively.
4. At about 2,300 fights, this data can only detect a large edge (around
   +10% return). Detecting +5% needs about 5,400 bets
   (`research/backtest/power.py`).

## Recommendation

Wait. The honest sample is the prospective one CFL is already capturing.
Buy this only if a specific pre-registered question needs pre-2025 prices.
