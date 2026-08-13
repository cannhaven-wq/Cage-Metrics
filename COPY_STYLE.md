# COPY_STYLE.md

The voice rules for every word a user reads on Cannon Fight Lab — page copy,
button labels, model explanations, red flags, and generated text like
`prop_cards.why_text`. If you're writing a string that ships to a human, it
follows this file.

These rules are already lived in `track-record.html` and `fight-insights.js`.
When in doubt, copy their phrasing before you invent your own.

## Who we're writing for

A bettor, 21–30, who already speaks sportsbook English — moneyline, dog,
juice, closing line, units — but is **not** stats-literate. They know what a
+180 dog is. They do not know what log-loss, Brier, or a calibration curve is,
and they don't want to.

Give them enough to understand the pick and move. The target is an **8-second
read per fight**: what does the model like, how much, and why might it be wrong.

## The one rule everything else serves

**We are not a tout.** We don't sell picks, we don't hype, and we show our
losses at exactly the same size as our wins. Every sentence should be something
you'd be comfortable reading back after the pick lost. If a line only sounds
good when the bet wins, cut it.

## Voice: nine rules

1. **Plain English over stats jargon — always translate.** Never ship the
   metric name. Ship what it means.
   - "log-loss / Brier" → "how close our percentages land to reality" or
     "score vs a coin flip"
   - "calibration" → "when we say 60%, does it hit 60% of the time?"
   - "percentage-point gap / edge" → "the model's number vs the book's number"
   - "expected value / +EV" → "the price is better than the real odds"
   - "variance" → "swings", "how bumpy the ride is"

2. **Talk money and win rates, not scores.** People feel dollars. Prefer
   "Profit per $100 bet" over "ROI", "wins 58% of the time" over "0.58 hit
   rate", "$100 grew to $114" over "+14% return".

3. **CLV is the north star, not win rate.** When we talk about whether we're
   good, the honest answer is closing-line value — did we get a better price
   than the market closed at — not a hot streak. Say so. Never imply a win
   streak is proof.

4. **Losses get equal billing. Non-negotiable.** Misses are shown at the same
   prominence as wins, never tucked away. The shipped line for this is the
   standard: *"A model that only shows winners is selling something."* Keep
   that energy.

5. **Never show a simulation as if it were live.** Backtested / replayed
   numbers are always labeled "simulated". Live numbers are always labeled
   live. If a figure came from replaying history, the word "simulated" sits
   next to it. Never put a simulated ROI figure above a "place the bet" CTA —
   that's the one move that reads as a tout.

6. **Respect the market.** The book's price is right more often than any model.
   When the model disagrees with the market, that's a flag to state plainly,
   not to paper over: *"the market's price is right more often than any
   model."* We beat the market at the margins, we don't dunk on it.

7. **Concrete over abstract. Last names, real numbers, short clauses.** Not
   "the selection demonstrates superior takedown defense metrics" but
   *"Holloway stops more takedowns — 82% to 61%."* Use the fighter's last name.
   Put the two numbers side by side. One idea per clause.

8. **Confidence is honest, not inflated.** A thin edge is called a thin edge:
   *"This is a lean, not a strong pick — the model barely separates these
   two."* A read from a small sample is called a guess: *"treat it as a guess,
   not a fact."* Punchy truths over hedges: *"age catches up fast, not
   slowly."*

9. **No internal vocabulary on screen.** Words we use to build the model are
   not words the user should see. "Input weights", "rules-based read", "tier-2",
   "feature", "consensus model", "v4/v6" — all internal. Translate to what the
   user cares about: what's pushing the pick, and how sure we are.

## Word swaps (internal → shipped)

| Don't ship | Ship |
|---|---|
| Input weights | What's driving this pick |
| Rules-based read / tier-2 | (name the actual signal, e.g. "quick read" — see item E) |
| Edge (as a bare noun) | The gap between our number and the book's |
| ROI | Profit per $100 |
| Log-loss / Brier score | Score vs a coin flip |
| Calibration | Do our percentages hold up? |
| Model consensus | Where our models agree |
| Expected value / +EV | Better price than the real odds |
| Variance | Swings |

## Numbers & formatting

- Percentages as whole numbers for lay reading (58%, not 0.5814) unless
  precision is the point.
- Money through the `_shared.js` helpers (`cfl.formatRecord`, etc.). Currency
  in dollars, "$100 bet" as the unit.
- One number per comparison, both sides shown: "82% to 61%", not "82% (vs.
  league avg)".
- A raw stat with no anchor is decoration. If you show "4.2 strikes a minute",
  give the read too — high or low for the division, or a percentile.

## Quick self-check before shipping a string

1. Would this line embarrass us if the pick lost? → rewrite.
2. Did I ship a metric name instead of what it means? → translate.
3. Is there a simulated number sitting above a bet CTA? → move it.
4. Did I bury the loss or shrink it? → equal billing.
5. Would a 24-year-old who's never read a stats textbook get it in one pass? →
   if not, simplify.

## Reference implementations

- `track-record.html` — headings, the two-records framing, the misses section.
- `fight-insights.js` — `buildEdgeBullets` (why we like it) and `buildRedFlags`
  (why it might be wrong). This is the canonical "why" voice.
