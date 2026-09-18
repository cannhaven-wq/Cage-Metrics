# Draft — dated correction to the edges.html factor table

> ## ⛔ DO NOT SHIP YET
>
> **Corrected 2026-09-18 after review.** An earlier version of this draft said
> it could ship on the evidence already in hand. That was wrong.
>
> Its central claim is about the **shipped** takedown-defence rule, which fires
> only when `willHaveWrestling()` is true. The measurement behind it,
> `factor-rates.json`, applies **no such gate** — it scores every fight with a
> takedown-defence gap. Same bands, different cohort. The 49.3% is evidence
> against takedown defence as a general signal; it is not a measurement of the
> rule this page describes.
>
> **This draft ships only after `measure_edges_bands.js` has run with the gate
> applied (T-024).** The wording below is kept so the shape of the correction
> is reviewable now, and every sentence that overstated the evidence has been
> weakened to match what is actually established.

**Status: DRAFT FOR REVIEW. Nothing has been applied.** `edges.html` is
untouched.

**T-025. L3 under gate #8** — a change to how an existing public performance
claim is described.

Evidence: [`FACTOR_EVIDENCE_2026-09-18.md`](FACTOR_EVIDENCE_2026-09-18.md).

---

## Why a correction and not an edit

`edges.html` is an open-methodology page carrying dated audit narratives, and
the house rule for those is already written down in `CLAUDE.md`:

> when a measurement changes, add a dated correction rather than silently
> rewriting the history

The page already does this — it carries *"Superseded July 2026 — measured with
hindsight"* against its own headline accuracy figure, and *"Retired Aug 19"*
against cardio with the reason attached. This proposal follows that pattern
exactly. Nothing already on the page is deleted.

---

## Change 1 — a dated note above the factor table

Inserted directly under the heading **"The factors we measure"**, before the
existing paragraph.

> **Updated September 2026 — two of these ranges are not supported.**
> The percentages below were written when the factors were built and were
> never re-tested against the betting market. We have now tested them the same
> way we tested cardio: on fights the market priced even, where a factor can no
> longer score by quietly re-reading the favourite.
>
> **Takedown defence does not look like it survives that test.** Across
> evenly-priced fights where one fighter holds a clear takedown-defence edge,
> that fighter wins 49.3% of the time — a coin flip. In the band where this
> page claims the most, a 30-point gap, it is 44.6%. We are re-running the
> measurement restricted to fights where somebody actually wrestles, which is
> the narrower situation this factor is supposed to apply to, and we will post
> that number when it lands. What we can already say is that the 52–56% range
> below was never measured against the market at all.
>
> **The record range is not supported above 60%.** The factor as a whole wins
> 55.1% of evenly-priced fights, on a range that still includes 50. The 65%,
> 70% and 72% figures below all sit above that range. Whether any individual
> band holds up is still being measured, and we will post that when it is done.
>
> **Age, which this page lists as retired, is the one factor that passes.**
> The younger fighter wins 56.7% of evenly-priced fights across 868 of them,
> and the range clears a coin flip. We are not reinstating it on the strength
> of one measurement — that is a model change and it needs its own written
> plan — but leaving the retirement here unexplained would be the more
> misleading option.
>
> The factor code these ranges describe no longer drives anything on the site:
> the homepage and the card run on the engine, which is a different model with
> its own graded record. The working is in
> `research/factors/FACTOR_EVIDENCE_2026-09-18.md`.

## Change 2 — the Status column

Two rows change status. No row is deleted and no range is rewritten.

| Factor | Status today | Proposed status |
|---|---|---|
| Record | `Active` | `Range unsupported — Sept 2026` |
| TD defense | `Active` | `Range unsupported — under review Sept 2026` |
| Age | `Retired May 17` | `Retired May 17 — but see the September 2026 note` |
| Cardio | `Retired Aug 19` | unchanged |
| everything else | `Retired May 17` | unchanged |

The ranges in the Range column stay exactly as published. They are what was
claimed; striking them out would erase the thing the correction is about.

## Change 3 — one sentence in the intro paragraph

**Before**

> Every factor below is implemented in the public edges.js file. Active factors drive the current verdict.

**After**

> Every factor below is implemented in the public edges.js file. These factors drove the verdict this page describes; the site's current picks come from the engine, which is a separate model with its own graded record on the [Proof Center](proof.html).

This is true today and is not currently said anywhere. `index.html` stopped
loading `edges.js` some time ago, `event.html` loads it only for a cardio
lookup, and the snapshotter that used it has not run since 2026-05-29. A reader
on this page has no way to know that.

---

## What is deliberately not proposed

- **No change to `edges.js`.** The constants are wrong, but changing them is a
  model change needing its own specification, and the code has no production
  consumer, so the urgency is on the page rather than the file.
- **No reinstatement of age.**
- **No claim about record's individual bands** until the pending run lands.
- **No claim about the gated takedown-defence rule** until the same run lands.
- **No deletion of anything already published**, including the superseded
  68.4% figure and its existing hindsight note.

## Sequencing — corrected

**This does not ship before T-024.** The reasoning that said otherwise confused
two cohorts: `edges.js`'s takedown-defence factor is gated on
`willHaveWrestling()` and the measurement in hand is not, so a correction
asserting something about "this factor" would be asserting it from a different
population.

One part of the correction *is* independent of any pending run and stays true
whatever T-024 returns: **these ranges were never measured against the market
in the first place.** That is a provenance fact, not a performance claim. If
the owner wants to say something now rather than wait, that is the sentence
that can be said — and Change 3, which simply states that these factors no
longer drive the site's picks, is likewise true today.

The full correction, with numbers, waits for the gated run.
