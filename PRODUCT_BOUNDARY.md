# Free vs Pro — the product boundary

Status: **proposal**, written 2026-09-21. Nothing here is built, priced or
charged for. Pricing and payments are **L3** ([`coordination/CRITICAL_GATES.md`](coordination/CRITICAL_GATES.md)
item 7); this document exists so the next sprint starts from a written boundary
instead of inventing one under deadline.

## The principle

Pro sells **depth, history, monitoring, convenience and personalisation**.
Pro does not sell facts.

If a number answers *"what is the market saying about this fight right now"*,
it is free. If it answers *"show me every book, every hour, and tell me when it
changes"*, that is Pro. A reader who never pays should still leave with a true
and useful picture of the card — that is the product, not the teaser.

Pro explicitly does **not** sell an opinion about who wins or what to bet. CFL
does not publish one, at any price.

## Free

| surface | what a free reader gets |
|---|---|
| the current card | every fight, in card order |
| market consensus | the vig-free market probability, the book count, the age of the quote |
| movement | the headline move since the first broad CFL capture, with its matched-book count and its method |
| best observed price | the best American price CFL captured, the book that posted it, its age |
| book disagreement | the current spread between books, in points, with its definition |
| matchup comparison | the basic stat comparison between the two corners |
| fighter pages | all ~4,500 of them |
| event pages | all ~800 of them |
| Factor Lab | every finding, every sample size, every verdict |
| Proof Center + methodology | in full, including the failures |
| Cannon Card Brief | signup and delivery |

## Pro

| surface | what paying adds |
|---|---|
| book-by-book table | every sportsbook's current price side by side, not just the best and the spread |
| movement history | the full line chart, every capture, not just baseline → now |
| historical lookback | past cards' market history beyond the current window |
| watchlists | fights and fighters a reader chooses to follow |
| price-target alerts | "tell me if anyone posts +150 on this fighter" |
| movement alerts | "tell me if this market moves 3+ points" |
| since your last visit | what changed on this card since the reader was last here |
| advanced matchup analytics | the deeper per-fight breakdowns |
| prop research | when and if the prop surface is rebuilt for it |
| fight-week monitoring | the personalised version of the Brief |

## Explicitly NOT included, at any tier

- Picks, plays, best bets, leans, locks, or a recommended side.
- A CFL win probability presented as something to bet into.
- An edge percentage, an expected-value figure, or a staking suggestion.
- Any claim that CFL beats the market or that a reader will profit.
- Affiliate placement dressed as a recommendation. Best-price ordering is the
  American number and nothing else, on every tier, forever.

## What the architecture already supports

- `profiles.tier` and `profiles.beta_premium` exist; `cflAuth.getTier()` /
  `getPaidTier()` already distinguish a beta grant from a paid one.
- Tier checks in the frontend are **presentation only**. Real enforcement is
  Postgres RLS — see the data-layer notes in `CLAUDE.md`. Any Pro surface must
  be gated in the database, not in JavaScript.
- The first piece of that gating landed 2026-09-21: `v_fight_market_quotes`
  (the full per-book tick history, i.e. the Pro asset) is **not** granted to
  `anon` or `authenticated`. The aggregate views above it are owner-rights
  views and keep reading it, so the free surfaces are unaffected.

## What is NOT decided here

Price, billing period, trial length, whether beta grantees are grandfathered,
and whether Pro launches at all. All L3.
