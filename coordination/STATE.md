# Coordination state

Where the project actually is, in one screen. Read this first; it is the
entry point to the rest of `coordination/`.

Last updated: 2026-09-16

**Live baton:** CLV-001 is **FROZEN at v1.0.6** (frozen 2026-09-16T10:30:00Z;
Amendments 1–4.2 same day). The benchmark is the **late pre-fight price proxy**,
never "the closing line". **Amendment 4.2 fixed a methodological bug**: the
previous bout's completion OPENS a fight's window and never closes it, so it is
no longer a scoring cutoff. Capture stays at **5 minutes through a live card
under a hard credit ceiling** — now hard-coded so no environment variable or
provider quota can widen it. **Three migrations written and none applied.
Publication is still shut** — 0 of 100 observations, 0 of 20 events.

**This file does not own research truth.**
[`CFL_RESEARCH_STATE.md`](../CFL_RESEARCH_STATE.md) is authoritative for every
experiment, freeze, hash and verdict, and `tests/test_research_state.py` checks
it against the bytes on disk. This file summarises and links. Where the two
disagree, the research register wins and this file is the one that is wrong.

---

## The loop

```
Claude builds  →  writes HANDOFF.md  →  ChatGPT reviews  →  writes the next spec
      ↑                                                              │
      └──────────────────────────────────────────────────────────────┘
                        Reed appears only at an L3 gate
```

| file | what it is for |
|---|---|
| [`STATE.md`](STATE.md) | this file — current position, refreshed at every handoff |
| [`TASK_QUEUE.md`](TASK_QUEUE.md) | what is queued, who owns it, what level it is |
| [`DECISIONS.md`](DECISIONS.md) | append-only log of decisions and who made them |
| [`HANDOFF.md`](HANDOFF.md) | the live baton — newest entry at the top |
| [`CRITICAL_GATES.md`](CRITICAL_GATES.md) | the L0–L3 ladder and the closed L3 list |

Git history is the audit trail. These files are the working surface.

---

## Where the project is

### Research

| line | state | see |
|---|---|---|
| DUR-001 — does PROP-0001@v1 beat the totals market? | collecting | [register](../CFL_RESEARCH_STATE.md) |
| DUR-002 — the same question for the uncalibrated hazard | **armed**, zero observations | [register](../CFL_RESEARCH_STATE.md) |
| PROP-0001 | frozen, serving locks | [register](../CFL_RESEARCH_STATE.md) |

**The duration model is read-only.** Development on it is finished; both
experiments run untouched until their evaluation points.

### CLV — the active line

[`research/clv/CLV_MEASUREMENT_PROTOCOL.md`](../research/clv/CLV_MEASUREMENT_PROTOCOL.md)
is **frozen at v1.0.6**. It is a measurement protocol, not a model experiment —
no hypothesis, no challenger, no verdict — so it lives outside the DUR register.

Three gates, deliberately separate:

| | state |
|---|---|
| capturing raw market quotes | **running** — does not wait for anything |
| computing a CLV statistic | **open** since the freeze — and it computes nothing, see below |
| putting a CLV number on a surface | **shut** — 0 of 100 observations, 0 of 20 events |

**The first dry run**
([`DRY_RUN_2026-09-16.md`](../research/clv/DRY_RUN_2026-09-16.md)) scored **0 of
47** eligible rows, every one at `no_scheduled_start`. Nothing on a settled card
can ever score: the freshest two-sided sportsbook quote on any past card was
captured **157.8 hours** before it, against a frozen 45-minute limit, and
near-card capture was an aggregate (all epoch-stamped) plus a prediction market,
both excluded by kind.

**That report carried an error, corrected at the top of it.** It said the
scheduled-start mechanism did not exist. It does — `fight_start_estimates` and
`v_fight_start_best`, from `dur001_migration.sql`, collecting since 2026-09-14
and already resolving `provider_commence` for 16 future fights. The 47 rows fail
because the ledger started after those cards, not because the field is missing.
One card of waiting, not a build.

**What shipped 2026-09-16, and what it needs:**

| | state |
|---|---|
| Q-02 eligible book list, ten sportsbooks | **frozen**, Amendment 2 (a) |
| the event-flow close reference, per fight | **frozen**, Amendment 3 |
| trigger ≠ close, stated so it cannot be collapsed | **frozen**, Amendment 3 (b) |
| the late pre-fight price proxy + lead-time reporting | **frozen**, Amendment 4 |
| a pre-card price is recognised, never scored | **frozen**, Amendment 4.1 |
| an opener is never a cutoff | **frozen**, Amendment 4.2 |
| the free allowance is hard-coded, env cannot widen it | **frozen**, Amendment 4.2 |
| 5-minute live capture under a hard credit governor | **written**, verified offline |
| the three ledgers are append-only, trigger-enforced | **written, UNAPPLIED** |
| `fight_odds` capture columns, mirroring `prop_odds` | **written, UNAPPLIED** |
| event-flow cadence in `build/fetch-odds.js` | **written**, verified offline, degrades if un-migrated |
| `fight_bout_order` + `fight_bout_completions` + `v_clv_close_reference` | **written, UNAPPLIED** |
| `model_edges` CLV-001 result columns | **written, UNAPPLIED** — last of the three |

**Amendment 3 in one line:** the card's published start belongs to bout 1 and
nobody else — applying it to all thirteen would have marked every quote after
the first bell as in-play for twelve of them.

**Amendment 4 in one line:** the benchmark is a late pre-fight price *proxy*,
captured every 5 minutes through a live card under a hard credit ceiling, with
its lead time recorded on every row.

**Amendment 4.1 in one line:** and "pre-card" does not count as "late" — a quote
before the card began is safely pre-fight and hours early on a late bout, so it
is recognised (`only_pre_card_price`) and never scored.

**Amendment 4.2 in one line:** a window has two ends and only one is the close —
the previous bout finishing *opens* the next fight's window, so using it as the
cutoff would pick a price quoted while the previous bout was still being fought,
and would make the 5-minute capture self-defeating.

**Scoring cutoffs** are now `bell_at` (any bout) and `scheduled_first_bout`
(bout 1 only). **Window openers** — `previous_bout_completion` and
`card_scheduled_start` — are capture triggers, reported, never cutoffs. Three
unscorable states are told apart: `fight_start_unverified` (one confirmed bell
away), `only_pre_card_price`, `no_scheduled_start`.

**Capture coverage is unaffected and every snapshot is kept.** `window_opens_at`
is stored so the snapshots inside a window become scorable **retrospectively**
once a confirmed bell arrives — including on cards already captured.

**What the proxy may be called:** the *late pre-fight price proxy* (long form,
*scheduled/late closing-price proxy*). **Never "the closing line."** Every row
carries its lead time and a flag saying whether that lead time is exact or a
lower bound.

No CLV statistic was computed, and none is computable until a card is captured
under the new path. Nothing renders CLV today; `track-record.html` carries a
placeholder. Legacy `clv_pp` settlement continues on its cron, untouched —
bookkeeping under the old convention, never labelled CLV.

### Where the work moves next

Stated in the research register, in priority order:

1. **Market / closing-price capture and CLV** — the biggest statistical
   dependency for showing CFL has an economically meaningful edge. *Active.*
2. Customer monetisation.
3. The win-probability engine.

### Open owner decisions

**DUR-001 amendments.** Nine held clauses — (a) (b) (c) (d) (e) (f) (g) (j) (k)
— remain PROPOSED and each needs an individual vote on its actual clause text.
They are explicitly *not* approved en bloc. Split by risk in the register: six
change data eligibility, scoring, model behaviour or interpretation and get
higher scrutiny; three are governance and monitoring only.

**The bout-completions L3 is resolved as a blocker and open as an improvement.**
[`L3_ESCALATION_2026-09-16_bout_completions.md`](../research/clv/L3_ESCALATION_2026-09-16_bout_completions.md).
Amendment 4's tier 4 removed the dependency; completions now buy **lead-time
precision**, not the metric. Doing nothing costs precision, not coverage.
Nothing has been bought, priced or enabled.

**Three CLV-001 migrations are written and unapplied, and the order matters.**
All additive-only — no DROP, no DELETE, no destructive UPDATE, no existing
trigger changed — and all filed outside the repo root so the "apply root `*.sql`"
habit cannot pick them up. None touches `v_fight_start_best`, which lives in a
frozen file and serves DUR-001.

1. [`proposed_2026-09-16_fight_odds_capture.sql`](../research/clv/proposed_2026-09-16_fight_odds_capture.sql)
   — **first.** Ten capture columns on `fight_odds`, copied name-for-name from
   `prop_odds`, which has carried them since DUR-001. Every quote captured before
   this lands is permanently unscorable, so the cost of waiting is measured in
   cards.
2. [`proposed_2026-09-16_event_flow.sql`](../research/clv/proposed_2026-09-16_event_flow.sql)
   — **second.** The running-order and bout-completion ledgers, plus CLV-001's
   own `v_clv_close_reference`. Both tables land empty; nothing backfills them.
3. [`proposed_2026-09-16_clv001_columns.sql`](../research/clv/proposed_2026-09-16_clv001_columns.sql)
   — **last, and only when there is something to write into it.** Nothing is
   computable until a card has been captured under (1) and (2).

**The odds cadence changed with them.** `odds.yml` now wakes every **5 minutes**
and `shouldCaptureNow()` gates each wake: 5 minutes while a card is **in flow**
(budget permitting), hourly on a card day, once daily otherwise.

**Five minutes is a target; the ceiling is a governor.** A card at 5-minute
cadence costs ~123 credits and the measured rate is 3.7 events a month, 6 in the
busiest — enough to break a 500-credit allowance outright. So before each call
the job reads the provider's own `x-requests-remaining` header (persisted in
`odds_api_usage`), counts the cards still to come, reserves each one's floor
cost, and takes the finest rung of 5 → 10 → 15 → 30 that fits. Below a hard floor
it stops. `FORCE` overrides the cadence, never the ceiling.
`build/test-fetch-odds.js` walks months of 1 to 8 cards and asserts none exceeds
the allowance. Degrading to 30 minutes still clears the frozen 45-minute
staleness limit, so the governor costs **lead time, never correctness**.
**No paid tier without an L3.**

All five original CLV L3 questions (Q-05, Q-06, Q-07, Q-08, Q-11) are resolved
and recorded, along with Q-12, Q-13 and Q-14, and Q-02's list is frozen.

### Site

Plain static HTML/CSS/JS on GitHub Pages; `main` deploys on push. No bundler.
One Node build step (prerender + factor rates) runs on a 6-hour cron. Nothing
on the card is gated in the frontend during beta.

---

## Refreshing this file

Whoever writes a handoff updates this file in the same commit, and moves the
date. A `STATE.md` that lags the handoff is worse than no `STATE.md`, because
the next reader trusts it.

Keep it to one screen. Detail belongs in the register, the queue, or the
handoff — not here.
