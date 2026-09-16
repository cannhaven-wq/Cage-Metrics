# Coordination state

Where the project actually is, in one screen. Read this first; it is the
entry point to the rest of `coordination/`.

Last updated: 2026-09-16

**Live baton:** CLV-001 is **FROZEN at v1.0.1** (frozen 2026-09-16T10:30:00Z;
Amendment 1 same day). `settle_clv.py` is reconciled and the first dry run is
in. **It scores nothing, and the reason is structural**: 0 of 47 rows, all
`no_scheduled_start`, with two-sided sportsbook capture ~6.6 days stale behind a
45-minute limit. **Publication is still shut** — 0 of 100 observations, 0 of 20
events. Waiting on Reed for the eligible-book list Q-02 froze but never wrote
down, and for a call on the capture path.

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
47** eligible rows. Four preflight conditions fail, so write mode refuses
outright; every row then stops at `no_scheduled_start`, because `fights.bell_at`
is populated on 0 of 8,994 fights and `events` stores a date with no time. Even
with that fixed, nothing would score: the freshest two-sided sportsbook quote on
any past card was captured **157.8 hours** before it, against a frozen 45-minute
staleness limit. Near-card capture today is an aggregate (all epoch-stamped) and
a prediction market, and CLV-001 excludes both by kind.

No CLV statistic was computed, and none is computable on the current record.
Nothing renders CLV today; `track-record.html` carries a placeholder. Legacy
`clv_pp` settlement into `model_edges` continues on its cron, untouched —
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

**CLV-001 eligible books.** Q-02 froze *"a fixed **named** sportsbook list,
frozen at protocol freeze"* — and the list was never written down.
`settle_clv.py` refuses to derive one, because deriving it is the thing Q-02
exists to prevent. Proposal, with no list in it, is at
[`AMENDMENT_PROPOSAL_2026-09-16_eligible_books.md`](../research/clv/AMENDMENT_PROPOSAL_2026-09-16_eligible_books.md).
Worth settling now: zero CLV numbers exist and none is computable, so a list
named today provably cannot be result-motivated. That window closes when
near-bell capture starts working.

**CLV-001 capture path.** Naming the books unblocks one of four preflight
conditions. The other three — two-sided near-bell quotes from named sportsbooks,
a scheduled bout-start instant, provider market IDs — are capture changes, and
none can be backfilled. Whether to make them is a product-priority call, not a
methodological one.

**The proposed CLV-001 migration is unapplied.**
[`proposed_2026-09-16_clv001_columns.sql`](../research/clv/proposed_2026-09-16_clv001_columns.sql)
is additive-only (no DROP, no DELETE, no destructive UPDATE, no trigger change)
and filed outside the repo root so the "apply root `*.sql`" habit cannot pick it
up. It should go last — when there is something to write into it.

All five original CLV L3 questions (Q-05, Q-06, Q-07, Q-08, Q-11) are resolved
and recorded, along with Q-12, Q-13 and Q-14.

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
