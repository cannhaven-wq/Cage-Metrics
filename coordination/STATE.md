# Coordination state

Where the project actually is, in one screen. Read this first; it is the
entry point to the rest of `coordination/`.

Last updated: 2026-09-16

**Live baton:** CLV-001 is **FROZEN at v1.0.3** (frozen 2026-09-16T10:30:00Z;
Amendments 1–3 same day). Amendment 3 is the **event-flow rule**: a card is one
scheduled start and then a queue, so the close reference is per fight — actual
bell, else the previous bout's completion, else (first bout only) the card's
scheduled start. Book list frozen, capture path written and verified offline,
**three migrations written and none applied**. **Publication is still shut** — 0
of 100 observations, 0 of 20 events. Waiting on Reed for one L3 (where bout
completions come from) and to apply the first migration.

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
is **frozen at v1.0.1**. It is a measurement protocol, not a model experiment —
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
| `fight_odds` capture columns, mirroring `prop_odds` | **written, UNAPPLIED** |
| event-flow cadence in `build/fetch-odds.js` | **written**, verified offline, degrades if un-migrated |
| `fight_bout_order` + `fight_bout_completions` + `v_clv_close_reference` | **written, UNAPPLIED** |
| `model_edges` CLV-001 result columns | **written, UNAPPLIED** — last of the three |

**Amendment 3 in one line:** the card's published start belongs to bout 1 and
nobody else. Amendment 2 (b) applied it to all thirteen fights, which would have
marked every quote after the first bell as in-play for twelve of them — caught
before any such quote exists.

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

**An L3 is open: where exact bout completion times come from.**
[`L3_ESCALATION_2026-09-16_bout_completions.md`](../research/clv/L3_ESCALATION_2026-09-16_bout_completions.md).
Until they exist, only the **first bout of each card** is scorable — about one
observation per event, against a floor of 100 across 20. The running order is
free (ufcstats lists a card in order; the event scraper can write it). Exact
completions are not: manual entry, a paid live feed, or a new definitional rule.
Nothing has been bought or enabled. Recommendation in the doc: take the free half
now, decide the paid half after a few cards of real coverage.

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

**The odds cadence changed with them.** `odds.yml` now wakes every 15 minutes and
`shouldCaptureNow()` gates each wake: 30 minutes while a card is **in flow**,
hourly on a card day, once daily otherwise. "In flow" opens 3h before the
scheduled start and closes when every bout has an exact completion, or after 7h.
~33 credits on a card day, ~286/month, inside the 500 free tier — **unchanged by
Amendment 3**, so no spend escalation was needed for the cadence itself. The
30-minute figure is not a preference: the frozen 45-minute staleness limit was
derived from a measured 30-minute interval, and hourly capture cannot satisfy it.

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
