# Matchup analytics — specification

**Status:** audit complete, **nothing built**. This is the gap audit the owner
asked for before implementation, not a design that has been approved.
**Date:** 2026-09-21
**Evidence:** [`research/matchup/AUDIT_2026-09-21.md`](research/matchup/AUDIT_2026-09-21.md)
— every measurement cited here is reproducible from the SQL in that file.

> **Plain English first, per `CLAUDE.md`.**
> *What changes:* Fight Lab stops showing career averages and starts showing
> what a fighter did against the specific quality of opposition they faced, and
> what they did in each round.
> *Why it matters:* "He lands 5.2 a minute" is a UFCStats fact anyone can get
> free. "He lands 5.2 a minute against opponents who normally give up 3.4" is
> ours, and it is a different sentence.
> *What the user sees:* three to five plain statements at the top of a fight
> page, each of which opens into the numbers, the sample and the limits.
> *No pick, no winner, no confidence score, no matchup score.*

---

## 1. The three findings that shaped this spec

The audit tested the owner's proposals rather than assuming them. Three
results changed the plan, and two of them say **don't build it**.

**Opponent-adjusted striking works.** Adjusting a fighter's prior output for the
opponents who produced it predicts their next fight's output materially better
than the raw number — correlation 0.2926 → **0.3779** across 6,902 held-out
fighter-fights, and it wins in every era and fight-length subgroup tested. It
beats both of its own inputs, so it is genuinely combining information. This is
the strongest result in the audit and it should be built first.

**Opponent-adjusted wrestling does not work.** The identical method applied to
takedowns made prediction slightly *worse* (0.3493 raw → 0.3466 adjusted), and a
second formulation also lost. A fighter's own takedown volume is already the
dominant signal, and opponent takedown-defence percentage is weak on its own
(0.115). **Recommendation: reject the composite**, and show the two numbers side
by side instead.

**"Output declines 36% by round three" is not a fighter trait.** Split-half
reliability of the R3/R1 **ratio** is **0.05** — indistinguishable from noise. A
fighter's measured decline percentage says almost nothing about their next
fight. The same decline expressed as an **absolute drop in strikes per minute**
reaches 0.30, which is modest but real; round output **level** reaches 0.56.
So round-by-round survives as a differentiator, but only after the percentage is
thrown away.

That last finding reaches a shipped surface: `v_fighter_consistency`'s
`tireless / steady / tapers / fades / collapses` tiers are built on the R3+/R1
ratio, and `fighter.html` renders them. See §7.

---

## 2. The constraint that governs every metric

**The median UFC fighter in this database has four fights.**

| fights per fighter | share |
|---|---|
| 1 | 439 of 2,771 |
| 2–4 | 1,053 |
| 5–9 | 644 |
| 10+ | 635 |

Requiring three prior fights **on both sides** is satisfiable for 48.1% of
fights since 2010; five on both sides, 31.8%. On the next real card
(2026-09-26), 16 of 22 fighter slots clear three prior fights and 12 of 22 clear
four fights reaching round three.

Three rules follow, and they are not negotiable:

1. **Every per-fighter number is shrunk toward its division mean**, with the
   weight set by the measured reliability of that metric — not chosen by feel.
2. **Every number ships with its sample size** in the same visual unit. A figure
   without an `n` beside it is a bug.
3. **"Not enough fights to say" is a designed state**, shown at least as often
   as a number, and it explains *why* rather than rendering a dash.

---

## 3. Metric classification

Per the owner's scheme: **A** ready now · **B** small engineering ·
**C** needs point-in-time reconstruction · **D** needs new data · **E** reject.

### A — ready now, from data already in the database

| metric | source | notes |
|---|---|---|
| Significant strikes landed / absorbed per minute | `fight_rounds` + real round clock | Must be recomputed from rounds, **not** read from `fighters.slpm` (§6) |
| Strike attempt rate (pace) | `a_sig_str_attempted` | 0% null after 2005 |
| Striking accuracy, defensive avoidance | landed ÷ attempted, both corners | |
| Head / body / leg distribution | `*_head_landed` etc. | Landed only; attempts not broken out |
| Distance / clinch / ground distribution | `*_distance_landed` etc. | 0% null |
| Takedown attempts and landed per 15 | `*_td_attempted`, `*_td_landed` | |
| Control seconds per round | `*_ctrl_seconds` | Populated from 2000; zeros are genuine |
| Submission attempts, reversals | `*_sub_attempts`, `*_rev` | Low base rates — sparse, label as such |
| Knockdowns per 15 | `*_kd` | Very low base rate; see E |
| Round-by-round output **level** | `fight_rounds` × round clock | Reliability **0.56** |
| Age, reach, height, stance, layoff, UFC experience | `fighters`, `events` | Already used by Factor Lab |
| Market consensus, best price, movement, book spread | `v_fight_market_movement` et al. | Already shipped; unchanged by this work |

### B — ready with small engineering

| metric | what is needed |
|---|---|
| **CFL Opponent-Adjusted Striking (OAS)** | One point-in-time view; formula in §4. **The P0.** |
| Round-by-round **absolute** decline (R1 − R3 strikes/min) | Same view, plus shrinkage constants (reliability 0.30) |
| Absorption by round | Mirror of the above on the opponent's landed column |
| Recent trajectory (last 3 vs prior) | Ordering already exists; needs a stated window and a noise floor |
| Wrestling **pairing** — his volume vs their concession, shown separately | Deliberately *not* a composite (§1) |
| Opponent-quality-faced disclosure ("his opponents normally allow 3.4/min") | Falls out of the OAS view; valuable on its own |

### C — needs point-in-time reconstruction before it can be validated

| metric | why |
|---|---|
| Division- and era-normalised versions of everything in A | League pace drifted 24 → 37 significant strikes per round, 2010 → 2023. Comparing a 2011 fighter to a 2025 one without normalisation is a bug waiting to be published |
| Second-order opponent adjustment | The opponent's allowance is itself unadjusted for who *they* faced |
| Historical comparable matchups | Needs a **frozen** matching definition, declared before any outcome is looked at (§5) |
| Style-interaction claims | `v_fighter_style` exists; the *interaction* between two styles has never been tested |

### D — needs data CFL does not have

| wanted | reality |
|---|---|
| Short-notice / full-camp status | Not in any table. Would need a new source |
| Weight-cut, missed weight, rehydration | Not captured |
| Injury and layoff *reason* | Only the layoff gap is derivable |
| Round-by-round head/body/leg **attempts** | Only landed is broken out per round |
| Position/control detail beyond seconds | UFCStats does not expose it |
| Judges' scorecards | Not captured |
| **Historical market movement** | Only 231 fights have real multi-book capture (since 2026-05-30). Historical odds exist for 7,681 fights but as a **single book with no timestamp** |

### E — reject

| rejected | reason |
|---|---|
| **Any single "matchup score"** | Explicitly excluded by the owner, and nothing in the audit supports collapsing these into one number |
| **Cardio / decline as a percentage or ratio** | Split-half reliability **0.05**. Measured noise |
| **Opponent-adjusted wrestling composite** | Made prediction worse than raw in two formulations |
| **Takedown-defence % as a headline** | 0.115 correlation alone. Keep it as context, never as a claim |
| Knockdown *rate* as a fighter trait | Base rate far too low at n=4; will be noise. Not separately tested — reject pending a reliability test |
| Nearest-neighbour "similar fighters win 68%" | Fake precision. §5 |
| Any "X has the edge / favours Y" phrasing | `CLAUDE.md` and `COPY_STYLE.md` forbid it |
| Elo-style composite rating | The owner ruled it out and the audit found no need for it |
| Anything sourced from `fighters` career aggregates for historical validation | Contains the outcome being predicted (§6) |

---

## 4. Proposed proprietary CFL metrics

### CFL-OAS v1 — Opponent-Adjusted Striking **(the P0)**

**Plain English:** how much a fighter lands, measured against how much the
people they fought normally give up.

```
league_apm      = Σ(absorbed) / Σ(minutes)          -- division- and era-scoped
opp_allow(o,t)  = Σ(o absorbed) / Σ(o minutes)      -- o's fights strictly before t
raw(f,t)        = Σ(f landed)  / Σ(f minutes)       -- f's fights strictly before t
OAS(f,t)        = raw(f,t) × ( opp_allow_faced(f,t) / league_apm )
```

where `opp_allow_faced` is the minute-weighted mean of `opp_allow` across the
opponents `f` has already fought. Every term uses only fights **before** `t`.

- **Shrinkage:** `OAS_shrunk = w·OAS + (1−w)·division_mean`, `w = n/(n+k)`,
  `k` fitted from the measured reliability. Not yet fitted — see §9.
- **Validation:** correlation with next-fight output **0.3779** vs **0.2926**
  raw, n=6,902, holds in all four era × length subgroups.
- **Floor:** 3 prior fights for the fighter and 3 for each opponent contributing
  to the baseline. Below that the metric is not shown.
- **Versioned** as `oas_v1` with a calculation date and source lineage.

### CFL-LRD v1 — Late-Round Drop

**Plain English:** how many fewer strikes per minute a fighter lands in round
three than in round one.

```
LRD(f) = mean over eligible fights of ( r1_sig_per_min − r3_sig_per_min )
```

Eligible = fight reached round 3, both rounds ≥ 1 minute.

- **Expressed in strikes per minute, never as a percentage.** Reliability 0.30
  as a difference, 0.05 as a ratio.
- **Heavy shrinkage**, and a minimum of 4 eligible fights — which only 12 of 22
  slots on the next card clear.
- Shown beside the R1 and R3 **levels**, which are the more reliable figures.

### CFL-OQF v1 — Opponent Quality Faced

**Plain English:** whether a fighter's numbers came against people who give up a
lot, or people who give up very little.

A by-product of OAS, and useful alone — it is the honest answer to "his record
looks great, against whom?". Ships as a plain statement plus the underlying list
of opponents, not as a rating.

### Wrestling: a **pair**, not a metric

Deliberately two numbers that never merge:

> "Fighter A attempts 4.1 takedowns per 15 minutes (11 fights).
> Fighter B's opponents have landed 1.8 per 15 against him (7 fights)."

The audit says combining these predicts worse than either used plainly.

### Governance for all CFL metrics

Per the owner's §12, each carries a documented formula, a version, a calculation
date, source lineage, and a test. They live in one module so a source swap
touches one layer.

---

## 5. Historical comparables — buildable, with one hard rule

7,681 fights carry historical odds, so comparables filtered on **market
probability, age gap, pace difference, experience, stance and reach** are
feasible now. Comparables filtered on **market movement** are not — 231 fights.

**The matching definition is frozen before any outcome is examined**, recorded
with a date, and never tuned after seeing results. Tuning filters until the
outcome looks interesting is how a research tool becomes a tout.

Output is neutral and countable:

> "23 historical fights matched these filters." → the fights, their context,
> their outcomes. **Never** "fighters like A win 68% of these."

---

## 6. Leakage rules (mandatory)

1. **Never use `fighters` career aggregates** (`slpm`, `sapm`, `td_avg`,
   `td_acc`, `td_def`, `str_def`, `wins`, `losses`, `last_5`) **in historical
   validation.** They are current-state snapshots containing the outcome being
   predicted. This exact defect once inflated the Factor Lab record factor to
   75.5%.
2. **Every historical figure uses a strictly-prior window frame**
   (`rows between unbounded preceding and 1 preceding`), for the fighter *and*
   the opponent's baseline.
3. **A metric that cannot be reconstructed point-in-time is labelled
   `NOT READY FOR HISTORICAL VALIDATION`** and is never quietly validated with
   current data.
4. **A 1970 `captured_at` is a sentinel, not a time.** 30,724 rows carry it. It
   must never be rendered, differenced, or treated as a capture instant.
5. Round clock comes from `end_round` + `end_time`, never assumed to be 5:00.

---

## 7. A shipped surface this audit contradicts

`v_fighter_consistency` derives its `tireless / steady / tapers / fades /
collapses` tiers from the R3+/R1 **ratio**, and `fighter.html` renders them.
That ratio has split-half reliability **0.05**.

`CLAUDE.md` already records that cardio does not predict winners and that it is
shown as description rather than as a pick. This finding is narrower and harder:
**the tier does not reliably predict the fighter's own next cardio
performance.** Two fighters given different tiers are, at n=4, mostly being
separated by noise.

This is a published claim resting on a measurement that does not reproduce, so
changing it is an owner call under gate #8 — queued as **T-066, L3**. Nothing
has been edited. The likely fix is reparameterisation to the absolute drop
(reliability 0.30) with shrinkage and a visible `n`, not deletion — and per
`CLAUDE.md`, a dated correction rather than a silent rewrite.

---

## 8. Fight Lab redesign

`fight.html` already has the right skeleton — market, chart, books, matchup
notes, stats. The change is **progressive disclosure** and one new section.

```
Fighter A vs Fighter B
[ market: consensus · best price · movement · books · freshness ]   ← unchanged

WHAT STANDS OUT                                    ← new, 3–5 items, never more
  "Big difference in pace"                    [+]
  "A's output drops late; B's holds"          [+]
  "A shoots takedowns; B has faced few"       [+]
     └ expands to: exact numbers · sample size · the fights ·
                   methodology · limitations

STRIKING · WRESTLING & GRAPPLING · PACE BY ROUND ·
RECENT PERFORMANCE · PHYSICAL / EXPERIENCE ·
MARKET HISTORY · FACTOR LAB CONTEXT                ← all collapsed by default
```

Rules the redesign inherits:

- **Ceiling of five items**, and fewer when the data is thin. A page that always
  finds five interesting things is not measuring anything.
- **Every headline statement is generated from a threshold with a documented
  definition** — "big difference in pace" means a stated gap, not a writer's
  judgement.
- **Thin data is a first-class state.** On the next card, 10 of 22 slots will
  not support the round-level section.
- All copy goes through `fight-insights.js`, never inlined — `event.html`,
  `fighter.html` and Card Lab share it.
- All market numbers keep going through `market.js`.
- No pick, no winner, no confidence, no CFL-vs-market difference.
  `tests/no-model-on-public-surfaces.test.js` must stay green.

---

## 9. Recommended first build

**Build CFL-OAS v1 and nothing else in the first pass.**

It is the only proposal with a measured out-of-sample gain, it is the clearest
answer to "why not just use UFCStats", and it produces CFL-OQF for free. The
smallest shippable slice:

1. A point-in-time view (`v_fighter_striking_pit`) — per fighter per fight,
   prior landed/absorbed/minutes, strictly-prior frames. No UI.
2. Fit the shrinkage constant `k` from measured reliability. Record it.
3. Validation committed to `research/matchup/` as a dated result, including the
   subgroup table. Published as evidence **before** the number appears anywhere.
4. One Fight Lab statement, expandable to numbers, sample and method.

Explicitly **not** in the first pass: wrestling composites (rejected), round
decline (needs shrinkage work, T-065), comparables (needs a frozen definition),
any paywall change (T-061 owns that, after Stripe).

**Sequencing note:** the owner placed this after the Stripe/payment work. This
audit does not change that, and nothing here should start before it.

---

## 10. Why this beats a stats site or an odds screen

A UFCStats page shows what happened. An odds screen shows what the market
thinks. Neither tells you **whether the numbers were earned against anyone
good** — and that is the one question this audit shows CFL can answer with
measured support.

The moat is not the metric. It is the paired capability:

- CFL owns a **capture schedule and provenance** for the market, and a
  **point-in-time reconstruction** of the fighters, in one place.
- CFL **publishes what failed** — the ratio-based cardio tier, the wrestling
  composite, the retired forecast — which is the part no competitor will copy.
- Third-party statistics stay an input. The transformation, the adjustment, the
  round-level reconstruction and the honest refusals are the product.
