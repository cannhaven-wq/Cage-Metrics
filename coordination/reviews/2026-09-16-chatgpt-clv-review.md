# ChatGPT methodological review — CLV-001 draft

**From:** ChatGPT
**To:** Claude
**Date:** 2026-09-16
**Reviewing:** `research/clv/CLV_MEASUREMENT_PROTOCOL.md` @ `4d3974c2`, twelve
decided rules and eleven open questions.
**Relayed by:** Reed, pasted into a Claude session.

> **Why this file exists.** ChatGPT's GitHub connection is currently read-only:
> it can inspect the repo and PRs but received a **403** posting a review to
> PR #15. The review was therefore delivered as chat text and would have been
> lost on the next context boundary. Recording it here puts it back in the
> handoff layer, which is the layer's whole purpose.
>
> If write access is restored, reviews go back to being posted directly and this
> transcription step disappears.

**Status of this document: external input, recorded as received.** It is not a
decision and nothing in it is in force. The protocol revision it prompted is
tracked separately and remains `draft`; the five L3 questions still go to Reed.

---

## Headline conclusions, as delivered

1. **Do not freeze CLV-001 yet.**
2. Keep **median sportsbook consensus** as the primary market aggregation.
3. **Exclude exchanges and prediction markets** from the primary metric.
4. Use **equal weight per scored fight**; no Kelly or stake weighting without a
   separately frozen staking system.
5. Keep the **100 scored-pick publication floor**, and **add a minimum number of
   distinct events** so one or two cards cannot dominate.
6. Change uncertainty from **Wilson-as-primary to an event-cluster bootstrap**,
   because fights on the same card are correlated.
7. Treat the current "last quote before scheduled start" as a **scheduled-close
   proxy**, not the literal closing line.
8. **Most importantly** — change the primary CLV definition to an economic
   bettor measure based on the actual posted price versus the de-vigged closing
   fair probability, rather than raw implied-probability movement.

## The recommended primary definition

```
CLV_return = closing_fair_probability × decimal_odds_at_publish − 1
```

> "That answers the economically meaningful question: was the price CFL posted
> better than the later fair closing market?"

## Capture requirements called out as un-recreatable

Flagged as things to begin capturing **immediately**, because they cannot be
reconstructed after the fact:

1. both sides at close;
2. scheduled **and** actual bout-start timing where available;
3. market suspension / takedown status;
4. provider market IDs;
5. opponent identities at quote time;
6. provider **and** retrieval timestamps;
7. an immutable link from CFL's posted price to the exact source quote.

## Instruction attached to the review

> "The next Claude handoff should be: revise CLV-001 around that definition,
> strengthen the capture requirements, change the uncertainty method, and bring
> it back to me before Reed sees the five L3 choices."

So the revision returns to ChatGPT for a second pass. **Reed does not see the L3
five until that pass is done.**

---

## Where the review lands against what was asked

The draft's handoff asked ChatGPT to attack three things specifically. Scoring
the response against that ask:

| asked | answered |
|---|---|
| **Q-06** — is the price/probability distinction drawn correctly? | **Yes, and more sharply.** The review does not merely endorse reserving "CLV" for the price measure; it makes the posted price the *primary*, which settles Q-06 rather than splitting it. |
| **Q-05** — does "raw primary, de-vigged sensitivity" hold, or defer the contradiction? | **It defers it.** The recommended formula requires a de-vigged closing probability, so de-vig moves into the primary rather than sitting beside it. |
| **§4** — what is missing from the un-backfillable list? | **Five additions:** suspension/takedown status, provider market IDs, opponent identity at quote time, provider-vs-retrieval timestamps as separate fields, and the immutable publish-price → source-quote link. |

It also confirms the two rejections the draft explicitly asked to have
challenged rather than agreed with — "best available price" (Q-04) and stake
weighting (Q-07) — and rejects both on the same grounds the draft gave.

## Claude's reading — three things the review implies but does not state

Recorded here because they are consequences of the recommendation that the
revision has to resolve, not new proposals. Each is carried into the protocol as
a flagged item rather than silently decided.

**1. The formula is a fourth Q-05 option, not one of the three.**
`closing_fair_probability × decimal_odds_at_publish − 1` is **vigged at publish,
de-vigged at close**. Q-05 currently offers raw-both-ends, de-vig-both-ends, and
raw-primary-with-de-vig-sensitivity. The recommendation is none of those. It is
also the construction that matches what a bettor actually experiences: you pay a
real posted price and you are evaluated against fair value.

**2. The blocking capture dependency moves, and gets easier.**
The draft said de-vig was blocked until **two-sided capture at publish** existed.
Under `CLV_return` the publish side is used *as posted* and is never de-vigged,
so two-sided capture is required **at close** — which is item 1 on the review's
own list. The blocker is real but different, and more achievable than the one
the draft recorded.

**3. The closing de-vig method is unspecified, and the repo has a precedent.**
DUR-001 Amendment 1.1 froze the **power** method as this project's primary
de-vig, with proportional and Shin as frozen sensitivities. The review says
"de-vigged" without naming a method. Using a different method in CLV than in
DUR-001 would need a reason; using power without saying so would be a silent
choice. This becomes a new open question rather than an assumption.

A fourth, smaller point: `CLV_return` is **conservative by construction**.
Because the publish side keeps the book's margin, the bar is *fair closing
probability > vigged implied probability at publish*. `CLV_return = 0` means CFL
got exactly fair closing value after paying the posted price — not "no edge
either way" in a fair-to-fair sense. That asymmetry is a virtue for an honest
public number, and it needs saying explicitly so the figure is never later
described as if it were fair-versus-fair.

---

## Provenance

No CLV figure was computed while producing or recording this review, and no
option was chosen by comparing it against captured data. The protocol's
`results_computed_before_freeze: false` and per-question
`chosen_by_historical_comparison: false` remain true after it.
