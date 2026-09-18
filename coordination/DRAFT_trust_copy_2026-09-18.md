# Draft — replacement copy for the contradicted public claims

**Status: DRAFT FOR REVIEW. Nothing in here has been applied.**
`index.html` is untouched. Every "after" string below is a proposal.

Covers T-020 (the four contradicted claims) and T-021 (the `Edge`
representation). Both are **L3 under gate #8** — a change to how an existing
public performance claim is described.

Raised by [`AUDIT_2026-09-18.md`](AUDIT_2026-09-18.md) §1.

---

## The rule every replacement below obeys

> A claim ships only if an artifact in this repository supports it, and no
> claim may imply CFL beats the closing market, because that has not been
> established and CLV-001 exists precisely to decide when it may be said.

What the artifacts actually support, and what they refuse:

| Supported | Artifact |
|---|---|
| The engine picks ~61% out-of-sample on fights it never trained on | `benchmark_report.md` 61.4%; homepage figure is live-computed |
| Backing the closing favourite gets ~68% | `benchmark_report.md`, same 3,068 priced fights |
| **The engine does NOT beat the closing line** | `benchmark_report.md`: LL 0.6511 vs 0.5978; Brier 0.2299 vs 0.2055 |
| Picks are written before the card and frozen where nobody can edit them | `pre_fight_snapshots`, trigger-enforced |
| Age is the only factor surviving market control | `factor-rates.json`, verdict `real` |

| Refused | Why |
|---|---|
| Any closing-line-value claim | CLV-001 gate shut, 0 of 100 observations |
| "graded at real closing prices" | asserts the above by implication; and the integrity audit found a settled prediction-market price flagged as a closing price, plus 30,724 rows with 1970 capture times |
| A bare "edge" percentage | `CLAUDE.md` line 1, `COPY_STYLE.md` swap table |
| "the betting line is wrong" / "the market is underpricing this" | asserts a mispricing the evidence does not support |

---

## T-A — title, meta description, Open Graph, Twitter card

These ship in every share, so they travel further than the page.

### A1 · `<meta name="description">` (line 9) and `og:description` (line 19)

**Before**

> A tape-only UFC engine graded in public — 61% straight-up on 3,200+ fights it never trained on, Locks at 75% — plus value flags graded at real closing prices and the Factor Lab: which stats actually predict fights. Every miss shown.

**After**

> A tape-only UFC engine graded in public: it picks every fight without ever seeing the odds, and we post the misses next to the hits. Backing the closing favourite still beats us — we publish that too. Plus the Factor Lab: which fight stats actually predict winners, and which just repeat the betting line.

Three changes. "graded at real closing prices" is gone — it is the CLV claim in
other words. The hardcoded `61%` / `75%` are gone, because a description in the
`<head>` cannot be refreshed by the page's own JavaScript and will drift. And
the fact that the market beats us is stated rather than omitted, which is both
true and the strongest anti-tout signal we have.

### A2 · `<meta name="twitter:description">` (line 30)

**Before**

> A tape-only UFC engine graded in public — 61% on 3,200+ never-seen fights, every pick locked, every miss shown — plus the Factor Lab: which stats actually predict fights.

**After**

> A tape-only UFC engine graded in public. Every pick frozen before the card, every miss shown, and the one test we have not passed named on the page. Plus the Factor Lab: which fight stats actually predict winners.

### A3 · `<title>` (line 8) — no change proposed

> Cannon Fight Lab — UFC Models That Show Their Work

Accurate and carries no number. Leave it.

---

## T-B — the hero headline

### B1 · `<h1>` (line 403)

**Before**

> Find where the betting line is **wrong.**

**After**

> See the number behind every **pick.**

The current headline asserts we can identify mispriced lines. `benchmark_report.md`
says the opposite on the only test that has been run: the engine's log-loss is
0.6511 against the closing line's 0.5978. It is not a close call and it is our
own measurement.

Two alternates, if the direction is wrong:

- *"A UFC model that shows its losses."*
- *"Every pick, every miss, on the record before the bell."*

All three describe something already true and already provable on `proof.html`.

### B2 · the lede (line 404)

**Before**

> UFC picks with the math shown and the losses posted. One model calls every fight without ever seeing the odds; a second flags the fights where the price looks off.

**After**

> UFC picks with the math shown and the losses posted. The model calls every fight without ever seeing the odds, then we put its number next to the book's so you can see where the two disagree.

"flags the fights where the price looks off" is the same mispricing claim in
softer words. "where the two disagree" is exactly what the product does.

---

## T-C — the hardcoded figures

### What is actually hardcoded, and what is not

This distinction matters and the audit's first pass under-stated it.

**Live-refreshed on every load** by `loadHeroProof()` — the static values in
the HTML are fallbacks, not claims:
`hpProof`, `mProof`, `hpN2`, `hpAcc2`, `hpLockAcc2`, `hpLockN2`, `tileGraded`,
`tileLock`, `tileFights`. **No change needed.**

**Never refreshed — genuinely hardcoded**, all inside the `track-note`
paragraph (line 452): `658 simulated bets`, `519-139`, `+10.0%`, `12-5`,
`down $61`, and the `Aug 18, 2026` snapshot date.

### C1 · the Value sentences in `track-note`

**Before**

> **Value** — the money face — flags a bet only when the engine's number beats the vig-free market price by 4+ points: its 658 simulated bets, graded at real closing prices, went **519-139** (+10.0% when bets are sized to the edge; roughly break-even at flat $100 — short-priced favorites pay small). Those results are the walk-forward replay, simulated point-in-time and labeled as such; the replay's first, uncalibrated year is excluded from everything we publish. The live record started July 2026 and is still tiny — **12-5** on settled flags, down $61 at flat $100 so far.

**After**

> **Value** — the money face — flags a fight only when the engine's number and the vig-free market price disagree by 4 points or more. Those flags were tested by replaying the engine through past cards, which is a sanity check and not evidence: the model is being clever about a world that already happened. The live record started in July 2026 and is still far too small to read. Both records, and the exact counts, are on the [Proof Center](proof.html) — recomputed on every load, never typed into this page.

The replay results are not deleted, they are **moved to where they can stay
true**. `proof.html` already renders both records, separately, with a
`TOO EARLY` chip on the money figure and a hard refusal to total them together.
A number that lives on a page that recomputes it cannot go stale; a number
typed into a paragraph can, and this one did.

This also removes the `+10.0%` — a simulated return figure sitting above an
"Analyze next card →" CTA, which `COPY_STYLE.md` rule 5 names as the single
move that reads as a tout.

### C2 · the closing-favourite sentence — keep, and source it

**Before**

> Just backing the closing favorite gets about 68% — we publish a number that loses to Vegas because a model within seven points of the market without ever looking at the market is a model you can actually trust to be independent of it.

**After** — unchanged in substance, one clause added:

> Just backing the closing favourite gets about 68% — measured on the same fights, in our own benchmark. We publish a number that loses to Vegas because a model that lands within seven points of the market without ever looking at it is a model you can trust to be independent of it.

This is the one number on the page that argues against us, it is backed by
`benchmark_report.md`, and it should stay. Adding "in our own benchmark" makes
it checkable.

### C3 · a defect the copy cannot fix — `loadHeroProof` pools two records

**This is a code change, not a wording change, and it is the most serious item
in this document.**

`loadHeroProof()` (line 533) calls:

```js
const rows = await cfl.fetchEnginePicks(q => q.not('hit', 'is', null));
```

`cfl.fetchEnginePicks` applies **no `source` filter**. So the headline
accuracy, the graded-fight count, the Lock-tier rate and the "Why trust it?"
tiles are all computed over live **and** replay rows pooled together, then
labelled `(simulated)`.

That is the exact operation `proof-gates.js::assertOneRecord` throws an
exception rather than perform, on the most prominent statistic on the site. The
`(simulated)` label is the conservative direction — it under-claims rather than
over-claims — but "3,288 never-seen fights" is still a mixed-record total, and
the page presents one number where there are two records.

Proposed fix, for review with T-020 because it changes what a published number
means:

```js
const rows = await cfl.fetchEnginePicks(q =>
  q.not('hit', 'is', null).eq('source', 'backtest'));
```

…with the label kept as `(simulated)` and the live record quoted separately, at
its real size, linking to `proof.html`. The alternative — split both and show
them side by side — is better but is a layout change, not a one-line fix.

**Recommendation: fix this before the wording.** A mixed total is a stronger
objection than a stale one.

---

## T-D — the `Edge` representation

### The owner's direction, 2026-09-18

> Preserve the current governance rule. Do not amend `CLAUDE.md` merely to keep
> the percentage UI. Propose a clearer user-facing representation that does not
> make an unsupported "edge" claim.

So: `CLAUDE.md` line 1 stands as written, and the UI moves.

### What has to go, and what can stay

The underlying quantity — model probability minus vig-free market probability —
is **fine to compute**. It sorts the card, it decides which fight leads the
hero, and it is an honest description of a disagreement. What is not fine is
printing it as a percentage called "Edge", because in sportsbook English an
edge is a claimed advantage, and we have not established one.

So the number stays internal. The label and the display change.

### D1 · the fight-row strip (lines 1123–1140)

**Before** — three cells, the third a signed percentage:

| Model | Market | Edge |
|---|---|---|
| 62% | 55% | **+7%** |
| Nurmagomedov wins | implied by the line | model over market |

**After** — same two numbers, the third cell replaced by a gap description
carrying no number and no claim:

| Our number | The book's number | |
|---|---|---|
| 62% | 55% | **We're higher** |
| Nurmagomedov wins | implied by the line | a disagreement, not an edge |

Bands, mapping to the existing `value` variable:

| Condition | Label | Sub-label |
|---|---|---|
| `value >= VALUE_EDGE` (4) | **We're higher** | biggest disagreements on this card |
| `0 < value < 4` | **Close to the line** | we and the book roughly agree |
| `value <= 0` | **The book's higher** | the market likes this more than we do |
| no market price | **No line yet** | needs a market price |

### D2 · the badge

**Before:** `✦ Value alert`
**After:** `✦ Biggest gaps on this card`

"Value alert" asserts a bet is worth taking. "Gap" asserts two numbers differ,
which is all we can show.

### D3 · the sort control (line 434)

**Before:** `Value` → **After:** `Biggest gap`

### D4 · the hero panel

**Before** (line 416): `Top edge · next card`
**After**: `Biggest gap · next card`

**Before** (line 418, the footnote): *"Edge is how much higher our number is than what today's odds say."*

**After**:

> We show our number and the book's side by side. Where they disagree, we say so — a disagreement is not proof the book is wrong, and we have not yet shown that ours is the better number.

**Before** (lines 627–630, the three note strings):

> The model thinks the market is underpricing this pick — the biggest gap on the card.
> A modest gap over the market price — the best value the model sees on this card.
> No real gap vs the market on this card yet — the line is fair. Bet value, not picks.

**After**:

> The widest gap between our number and the book's on this card. That is a disagreement, not a verdict on the price.
> A narrow gap — we and the book are close on every fight on this card.
> We and the book agree across this card. Nothing here looks mispriced to us.

### D5 · the value-play summary (line 966)

**Before**

> **N picks** on this card clear our 4% value bar — the model's number beats the book's by at least that much. That's the raw material for a parlay, not a green light…

**After**

> On **N fights** our number and the book's are at least 4 points apart. That is where we disagree with the market most — not a list of good bets. Whether disagreeing with the market pays is the one thing our record cannot yet tell you; see the [Proof Center](proof.html).

### What this costs

Nothing functional. `value` still sorts, still ranks the hero, still drives the
badge. A user loses one number and gains an honest sentence, and the site stops
publishing a figure its own governance file prohibits.

---

## Suggested order, if these are approved

1. **C3** — the pooled-record fix. A wrong number is worse than a stale one.
2. **A1 / A2** — the meta and OG strings. They travel furthest.
3. **B1 / B2** — the hero.
4. **D1–D5** — the Edge representation. Largest diff, lowest risk.
5. **C1 / C2** — the `track-note` paragraph.

Each is independent; none depends on another landing first.

## What is NOT proposed here

- No change to `CLAUDE.md`. The rule stands.
- No change to `proof.html` or `track-record.html` copy. Both already defer
  correctly on CLV.
- No new number anywhere. Every replacement removes a claim or moves it to a
  surface that recomputes it.
