# Factor evidence — what edges.js claims, and what the data says

**T-024. Read-only. 2026-09-18.**

This is the artifact that has to exist before any factor claim moves. It is
**partial, and says exactly where it stops.**

---

## The plain-English version

`edges.js` tells the site how strong each of its factors is. Two of those
strengths were typed in by hand and never checked. We checked what we could
check today.

- **Takedown defence.** The site says a big gap is worth 56%. Measured on
  fights the betting market priced even, fighters with a big takedown-defence
  edge win **44.6%** — outside the range the claim needs, and slightly worse
  than a coin flip. **But this is not yet a test of the exact rule the site
  runs.** The site only applies takedown defence when someone in the fight
  actually wrestles; the measurement we have includes every fight. So this is
  strong evidence against takedown defence in general, and the shipped rule
  has still to be tested on its own terms.
- **Pro record.** The site says a wide record gap is worth up to 72%. Measured
  the same way, the whole factor is **55.1%**, with a range that still includes
  50. 65%, 70% and 72% are all outside that range.
- **Age.** The site **retired** this factor in May. It is the only one of the
  three with a range that clears a coin flip: **56.7%** on 868 market-even
  fights.

So the engine dropped the factor that works and kept two that have not been
shown to.

---

## What was measured, and what was not

| | status |
|---|---|
| Takedown defence, at edges.js's band edges, **without its wrestling gate** | **measured** — see §1 |
| Takedown defence, at edges.js's band edges, **with** `willHaveWrestling()` | **not yet** — needs the live run |
| Pro record, at edges.js's own smoothed bands | **not yet** — needs the live run |
| Pro record, headline (does the rule beat a coin flip at all) | **measured**, generic form |
| Age, at the Factor Lab's bands | **measured** |

**Nothing here is an exact test of a rule as shipped.** Two of the four lines
above are pending, and both pending lines are the ones that would license a
change. That is deliberate: this document exists to be the evidence, not to
stand in for it.

**Why the record bands are not done.** `build/factor-rates.js` bands the
**raw** win-rate gap at 10 / 15 / 22 / 30 points and requires five prior UFC
fights a side. `edges.js` bands the **Laplace-smoothed** gap at 8 / 15 / 25 /
40 and requires three combined. Those are different cuts of a different
quantity, so the per-band numbers are not comparable and are not reported.

**Why the takedown-defence bands are close but still not exact.** Both files
cut at the same edges — 10, 20 and 30 points — so the band structure needs no
translation. Two differences remain, and the first is **material**:

1. **`factor-rates.js` applies no `willHaveWrestling()` gate.** `edges.js`
   fires its takedown-defence factor only when at least one fighter has a
   career `td_avg >= 1.0` — i.e. only when somebody in the fight actually
   shoots. The Factor Lab measurement includes every fight with a takedown-
   defence gap, wrestler or not. Those are **different cohorts**, and the
   excluded one is exactly the population where takedown defence is least
   likely to matter. Gating could plausibly move the number in either
   direction: it removes fights where the metric is irrelevant (which should
   help) but also shrinks the sample (which widens the interval).
2. It rebuilds takedown defence point-in-time where `edges.js` reads the
   present-day career figure.

So the 49.3% is **evidence against takedown defence as a general signal**. It
is not a verdict on the gated rule the site actually runs, and this document
does not treat it as one.

`research/factors/measure_edges_bands.js` closes the remaining gap by scoring
`edges.js`'s own triggers and bands. **It could not be run in the session that
wrote it**: the environment's network policy blocks `*.supabase.co`, and
`fight_odds` has no `SELECT` policy for `anon`, so the market-control column
needs a service key. The script refuses to write a result without one rather
than publish a confidently empty market column. Its logic is covered by
`tests/edges-bands.test.js` (18 assertions, verified to fail when tampered
with), so the rules are proven correct even though the run is pending.

---

## Method

Identical to `build/factor-rates.js`, deliberately, so the two artifacts can be
read side by side:

- **Point-in-time.** Each result is folded into both fighters' state only after
  that fight has been scored. Career totals off the `fighters` table are never
  used — they contain the result being predicted, and that bug was live once
  and inflated the record factor to 75.5%.
- **Market control.** A fight joins the `even` cohort only when neither side
  closed outside ±140. A factor strong raw and weak market-even was reading the
  favourite, not the fight.
- **Wilson 95% intervals**, which behave at small n.
- **A claim is judged against the interval, not the point estimate.** A claim
  inside the interval is *not refuted*; it is not thereby supported either.

Source for every measured number below: `factor-rates.json`, generated
2026-09-18T12:44:17Z from 8,739 scored fights with a 869-fight market-even
cohort.

---

## 1. Takedown defence — strong evidence against, exact test still pending

`edges.js` fires at a 10-point gap **when wrestling is in play** and claims
52.5 / 54 / 56%.

**The table below omits the wrestling gate.** It is the ungated cohort: every
fight with a takedown-defence gap. Read it as evidence about the metric, not as
a measurement of the shipped rule.

| Band | edges.js claims | Measured, market-even | 95% interval | n | Verdict on the claim |
|---|---|---|---|---|---|
| Any gap | — | **49.3%** | 43.7 – 55.0 | 298 | the factor is a coin flip |
| 10–20 points | 52.5% | 52.2% | 43.1 – 61.2 | 113 | inside the interval — not refuted, not supported |
| 20–30 points | 54.0% | 51.2% | 40.7 – 61.6 | 84 | **untested** — below the 100-fight floor |
| 30+ points | **56.0%** | **44.6%** | 35.2 – 54.3 | 101 | **claim is above the interval** |

Three things worth separating.

**Ungated, the claim fails where it is boldest.** The 30+ band is where
`edges.js` is most confident, and it is the band that measures *below* a coin
flip. The interval's upper bound is 54.3; the claim is 56.0.

**Ungated, the factor does not survive market control.** 49.3% on 298
market-even fights, with an interval centred almost exactly on 50. Raw it reads
54.8% on 2,601 fights — which is what reading the favourite looks like. This is
the same shape, and the same test, that retired cardio in August 2026.

**And none of that is yet a measurement of the rule on the site.** The shipped
factor fires only when someone in the fight wrestles. Restricting to that
cohort is what `measure_edges_bands.js` does and what has not been run. Until
it has, the honest statement is: *takedown defence looks like a market proxy,
and we have not yet tested the gated form.* Anything stronger is borrowing
confidence from a cohort we did not measure.

## 2. Pro record — the headline does not support the top three bands

`edges.js` fires at a 0.08 smoothed gap and claims 60 / 65 / 70 / 72%.

| | Measured, market-even | 95% interval | n |
|---|---|---|---|
| UFC record, any gap the rule fires on | **55.1%** | 46.8 – 63.3 | 136 |

| edges.js claim | Against that interval |
|---|---|
| 60% | inside — not refuted |
| **65%** | **above the interval** |
| **70%** | **above the interval** |
| **72%** | **above the interval** |

Raw, the factor reads 62.7% on 1,347 fights. Under market control it is 55.1%
with a range that still includes 50, which is why `factor-rates.json` grades it
`lean` — "can't tell yet" — rather than `real`.

**The band-level question is still open** and is what the pending run answers.
What is already established is that a factor whose own confidence interval
includes a coin flip cannot support a published 72%.

## 3. Age — the retired factor is the only one with evidence

| Band | Measured, market-even | 95% interval | n | Verdict |
|---|---|---|---|---|
| Any gap | **56.7%** | 53.4 – 59.9 | 868 | **real** |
| 1–2 years younger | 53.1% | 47.0 – 59.1 | 260 | proxy |
| 3–4 years younger | 58.0% | 51.6 – 64.1 | 238 | **real** |
| 5–6 years younger | 58.6% | 50.8 – 66.0 | 157 | **real** |
| 7–9 years younger | 58.9% | 51.0 – 66.5 | 151 | **real** |
| 10+ years younger | 56.5% | 44.1 – 68.1 | 62 | unproven — small sample |

Age is the only factor on the board whose market-even interval clears 50, and
it does so on the largest sample of the three by a wide margin. `edges.js`
retired it on 2026-05-17.

**This is not a recommendation to reinstate it.** Reinstating a factor is a
model change, it would need its own preregistration, and the May retirement had
a stated rationale that this document has not examined. What the numbers
establish is narrower and sufficient: the retirement cannot be justified by the
evidence that retired cardio, because age passes that test and the two factors
that were kept do not.

---

## 4. A second defect, found while doing this

`edges.js`'s `recordEdge` reads `a.wins` / `a.losses`, and `tdDefEdge` reads
`a.td_def` — **present-day career figures off the `fighters` table.**

For a live pick that is legitimate: the fight has not happened, so today's
totals are genuinely pre-fight. For any *backtest* it is leakage — the totals
include the result being predicted.

`research/results.md`, produced by `research/validate.js`, reports 68.4%
accuracy for the `edges.js` verdict across 6,655 historical fights. That figure
was measured this way. `edges.html` already carries a
*"Superseded July 2026 — measured with hindsight"* note against it, so this was
caught; it is recorded here because it is the reason the pending run substitutes
point-in-time UFC record for present-day pro record, and a reader needs to know
that substitution is not a convenience.

---

## 5. What this does and does not license

**Licensed by this artifact:**

- Recording that two published factor ranges have **no supporting artifact** —
  which is a statement about provenance, not about the factors' merit, and is
  true independent of any pending run.
- Prioritising the gated run. The ungated result is suggestive enough that
  finishing the exact measurement is clearly worth the credits.

**NOT licensed, corrected 2026-09-18 after review:**

- **Shipping the `edges.html` correction.** An earlier version of this section
  licensed it on the evidence in hand. That was wrong: the correction's central
  sentence is about the shipped takedown-defence rule, and the shipped rule is
  gated where the measurement is not. The draft at
  [`DRAFT_edges_correction_2026-09-18.md`](DRAFT_edges_correction_2026-09-18.md)
  is marked do-not-ship until T-024 runs. **T-025 stays blocked.**

**Not licensed:**

- Changing `edges.js`'s constants. That is a model change and needs its own
  specification. It is also not urgent: `computeEdges` has **no production
  consumer** — `index.html` no longer loads `edges.js`, `event.html` loads it
  only for `cardioFor`, and the `cfl-snapshotter` cron has been dead since
  2026-05-29. The claim ships on `edges.html`; the code does not run.
- **Reinstating age.** See §3. Clearing 50% under market control in isolation
  is not the same as adding value on top of what the engine already knows —
  the engine carries age among its 49 covariates, so a standalone base rate
  says nothing about incremental contribution. That needs its own test.
- Any statement about record's individual bands. See §2. The headline cohort
  is not a test of the Laplace-smoothed 8 / 15 / 25 / 40 bands; those bands sit
  on a different quantity and have not been scored.

---

## Reproducing this

The measured numbers come from `factor-rates.json`, which the 6-hour
`prerender.yml` cron regenerates and commits. The claim-against-interval
verdicts:

```bash
node -e "
const M = require('./research/factors/measure_edges_bands.js');
const fr = require('./factor-rates.json');
const td = fr.factors.find(f => f.id === 'td_def');
td.buckets.forEach(b => console.log(b.label, b.even.pct, b.even.ci_lo, b.even.ci_hi, b.even.n));
"
```

The pending run, from an environment with egress and a service key:

```bash
SUPABASE_SECRET_KEY=... node research/factors/measure_edges_bands.js
# writes research/factors/edges_bands_measured.json
```

Its logic, offline:

```bash
node tests/edges-bands.test.js
```
