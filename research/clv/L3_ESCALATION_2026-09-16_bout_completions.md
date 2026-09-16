# L3 escalation — where exact bout completion times come from

**Raised:** 2026-09-16, implementing CLV-001 Amendment 3.
**Escalated because:** every option that works costs money or standing human
time, and Reed's instruction is that no paid infrastructure or API spend is
assumed without an L3 call.
**Nothing has been bought, signed up for, or enabled.**

---

## Plain version

We now measure a fight's closing price against the moment that fight actually
started. For the first fight of a card we know that — it is the advertised start
time. For the other twelve we do not, because nobody records when each fight
ends, and the next one starts right after.

So today we can score about **one fight per card**. We need a hundred, across
twenty cards. At one per card that is a hundred cards — roughly two years.

Getting the other twelve means knowing when each bout finishes, live. There is no
free way to do that. This is the decision.

---

## What is already solved, and free

**Running order.** Which fight is first, second, twelfth. `fights` has no order
column — only `is_main_event`, which names the last bout — but ufcstats publishes
a card in order, and the existing event scraper can write `fight_bout_order` on
the same pass it already makes. No new service, no cost, no L3.

That alone unlocks tier 3: the card's first bout becomes scorable. It does not
unlock the rest.

## What is not solved

**Exact bout completions.** Nothing records when a bout ended.

The obvious candidate does not work, and it is worth being precise about why,
because it looks like it should. The result scraper runs after the card and tells
us *a winner exists by time T*. That is **completion plus unknown lag** — an
upper bound, sometimes hours wide. Used as the *next* bout's start it sits too
late, and every quote taken between the real start and T would be admitted as a
pre-start quote. Those are in-play prices. Scoring a closing line against them is
precisely the failure Amendment 3 exists to prevent, and it would be invisible in
the output: the numbers would look fine.

`fight_bout_completions.is_exact` exists to make that refusal structural rather
than remembered. `v_clv_close_reference` reads only `is_exact = true` rows.

---

## The options

| | what it is | cost | quality |
|---|---|---|---|
| **A** | **Do nothing.** Score bout 1 only | none | ~1 observation per card. 100 observations ≈ 100 cards ≈ 2 years |
| **B** | **Manual entry** — someone notes each bout's end time during the card | ~13 timestamps per card, live, on ~46 cards a year | exact if done attentively; a missed card is simply unscored, never wrong |
| **C** | **Paid live-data feed** with bout-level timing | a new monthly subscription, price unknown until quoted | exact and unattended; a new standing bill and a new dependency |
| **D** | **Derive from market disappearance** — a book pulls a fight's market when it goes in-play, so the last capture that still showed it brackets the start | none, once the 30-minute capture is running | approximate, bracketed to 30 minutes, and **it is a new definitional choice that would need its own L3 freeze** |

### Notes on each

**A is the honest default and it is not embarrassing.** One scorable observation
per card, accumulating. Nothing is wrong with the number; there is just less of
it. If the answer is "not worth spending on yet", A is what happens, and the
protocol already behaves correctly under it.

**B is the cheapest thing that fully works.** It is also the one that quietly
stops happening. If it is chosen, it needs to be somebody's named job with a
place to type the times, not an intention.

**C is the only unattended option.** I have not priced it, contacted a provider,
or enabled anything — that would be the spend this escalation exists to avoid
pre-empting. If this is the direction, the next step is a quote, brought back
here before anything is signed.

**D is the interesting one and I am deliberately not implementing it.** It uses
data the new capture already produces, costs nothing, and is genuinely
informative. But "the market disappeared" is not "the fight started" — a market
can be pulled for other reasons — and turning an observation about our own
polling into a bout-start instant is a new measurement definition. Adding it
myself, to a protocol frozen this morning, to relieve a coverage problem I
reported this afternoon, is exactly the move the freeze exists to stop. If you
want it, it is a fresh L3 with its own amendment, and the bracket width should be
stated in the rule.

---

## What I recommend

**Take the free half now, decide the paid half later.** Have the event scraper
populate `fight_bout_order` — no cost, no L3, and it makes the first bout of
every card scorable from the next card onward. Then let real coverage accumulate
for a few cards before deciding whether B, C or D is worth it, because the
decision is easier with a real count of scorable observations in front of you
than with my estimate of one.

Nothing degrades while you decide. Unscored fights are counted and reported under
R-05; they are never scored on a substitute.

---

## What this does not change

The publication gate is untouched and stays fail-closed: 100 scored observations
across 20 distinct events with a cluster interval excluding zero, currently 0 and
0. None of the options above moves it — they change how fast observations
accumulate, never whether a number may be shown.
