# Coordination state

Where the project actually is, in one screen. Read this first; it is the
entry point to the rest of `coordination/`.

Last updated: 2026-09-21

**Live baton:** CLV-001 is **FROZEN at v1.0.10** (frozen 2026-09-16T10:30:00Z;
Amendments 1–7 ratified same day; **Amendment 7 approved by Michael Cannon,
owner, 2026-09-16**). **CLV write mode is held shut while any amendment is
unratified** — a preflight condition, not a note. It no longer fires, and it
stays, because a gate deleted the moment it first goes green was never a gate. **Amendment 5 freezes the operational cutoff**: bout
1 takes the card's scheduled start, bouts 2..N take the exact completion of the
immediately previous bout — **those two cases, always**, with `bell_at` retained
as an audit field and never overriding them (5.1). The scored price is the
latest eligible sportsbook snapshot strictly before the cutoff. This is the **CFL closing-price proxy**,
never the exact sportsbook closing line — for later bouts it sits several
minutes before the bell, which is accepted and recorded per row. Capture stays
at **5 minutes through a live card under a hard credit ceiling**.
**Amendment 6 enforces the provenance rules per ROW**: a quote is usable because
that quote carries the §4 fields, never because the columns exist on the table;
R-07 is applied per quote against an immutable lock from `pre_fight_snapshots`;
the posted price must name and prove its source quote; the cutoff is stored and
hashed. **Amendment 7 makes settlement write-once**: an observation is written
once and every later run verifies it and writes nothing, aborting loudly on
drift. **Two of the five migrations are now APPLIED** (2026-09-19,
[D-009](DECISIONS.md)) — the `fight_odds` capture columns and
`add_bout_order_migration.sql`. **Publication is still shut** — 0 of 100
observations, 0 of 20 events.

**UFC 331 is the first card captured under the capture path.** At 15:49 UTC on
2026-09-19, 142 rows across 6 books landed with **118 carrying the full §4
provenance set** — the first CLV-eligible quotes CFL has recorded. Nothing is
scored and nothing is published; the capture gate and the publication gate stay
as separate as D-003 made them.

**It nearly did not happen, and the reason is worth keeping.** Every cadence
tier in `build/fetch-odds.js` gated on the wall clock (`min % cadence <
WAKE_INTERVAL_MIN`), which equals a cadence only if the `*/5` cron really fires
every five minutes. GitHub throttles it to a handful of deliveries a day at
arbitrary minutes — on the 19th they were :43, :30, :35 and :35, never inside
minutes 0–4 — so on a **card day** the job captured nothing at all. The gate now
measures elapsed time since our own last capture and falls back to the phase
test when that is unreadable. Same throttled wakes, **10 captures instead of 1**.

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
                       the owner appears only at an L3 gate
```

| file | what it is for |
|---|---|
| [`STATE.md`](STATE.md) | this file — current position, refreshed at every handoff |
| [`TASK_QUEUE.md`](TASK_QUEUE.md) | what is queued, who owns it, what level it is |
| [`DECISIONS.md`](DECISIONS.md) | append-only log of decisions and who made them — newest is **D-004**, retiring `backfill_odds.py` |
| [`HANDOFF.md`](HANDOFF.md) | the live baton — newest entry at the top |
| [`CRITICAL_GATES.md`](CRITICAL_GATES.md) | the L0–L3 ladder and the closed L3 list |
| [`AUDIT_2026-09-18.md`](AUDIT_2026-09-18.md) | the read-only product audit — where the five workstreams actually stand |

Git history is the audit trail. These files are the working surface.

---

## Where the project is

### The open question, and it is the owner's — T-039

A production-readiness sprint was briefed on 2026-09-21 on the premise that the
public model had been removed and that a **Market Lab**, a **Fight Lab** and a
**Cannon Card Brief** exist. Checked against `main` that day, none of it holds:
those three surfaces have zero occurrences in the tree outside the brand name,
and `track-record.html` (ROI, profit/loss, an edge-banded bet table) is in the
primary nav beside `predictor.html`, `parlay.html`, `props.html` and
`mybook.html`. [D-010](DECISIONS.md), approved 2026-09-19, deliberately kept
"Model vs Market" on the homepage.

Nothing was removed on the strength of that premise. **[T-039](TASK_QUEUE.md)
is the live baton**: model-and-market with the Proof Center carrying the record,
or research-and-market-intelligence with the model private. T-033, T-040 and
T-041 all wait on the answer.

### Market movement — settled 2026-09-21

Movement is measured over the **matched book cohort** and refused below three
such books; the baseline is the **first broad CFL capture** and is never called
an opening line. [D-011](DECISIONS.md), `market_movement_views.sql`,
`market-movement.js`. The live `v_fight_market_movement` that called
`min(captured_at)` an "open" — present in no repo file, inherited from the
unmerged `fight-week-v2` — is gone. On the real table it overstated moves by up
to 12.7 points and reported three markets as moving 3+ points when they had not
moved at all. No surface renders any of this yet.

### Research

| line | state | see |
|---|---|---|
| DUR-001 — does PROP-0001@v1 beat the totals market? | collecting | [register](../CFL_RESEARCH_STATE.md) |
| DUR-002 — the same question for the uncalibrated hazard | **collecting** since 2026-09-16 — 48 rows on 12 fights | [register](../CFL_RESEARCH_STATE.md) |
| PROP-0001 | frozen, serving locks | [register](../CFL_RESEARCH_STATE.md) |

**The duration model is read-only.** Development on it is finished; both
experiments run untouched until their evaluation points.

### CLV — the active line

[`research/clv/CLV_MEASUREMENT_PROTOCOL.md`](../research/clv/CLV_MEASUREMENT_PROTOCOL.md)
is **frozen at v1.0.10**. It is a measurement protocol, not a model experiment —
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
| the late pre-fight closing-price proxy + lead-time reporting | **frozen**, Amendment 4 |
| a pre-card price is recognised, never scored | **frozen**, Amendment 4.1 |
| the operational cutoff (scheduled start / previous-bout completion) | **frozen**, Amendment 5 |
| no bell override; cutoff ≠ start; corrections by `observed_at` | **frozen**, Amendment 5.1 |
| the free allowance is hard-coded, env cannot widen it | **frozen**, Amendment 4.2 |
| month-to-date spend counted from our own ledger, not the provider's balance | **fixed** |
| all four migrations genuinely re-runnable (DO-block guards) | **fixed**, 8 static + 2 live-SQL tests |
| 5-minute live capture under a hard credit governor | **written**, verified offline |
| the three ledgers are append-only, trigger-enforced | **written, UNAPPLIED** |
| `fight_odds` capture columns, mirroring `prop_odds` | **written, UNAPPLIED** |
| event-flow cadence in `build/fetch-odds.js` | **written**, verified offline, degrades if un-migrated |
| `fight_bout_order` + `fight_bout_completions` + `v_clv_close_reference` | **written, UNAPPLIED** |
| both ledgers unconstrained by history — nothing unique on the *value* | **fixed**, 3 tests |
| the running order resolves as a **complete card**, not per fight | **fixed**, 9 tests |
| the 20-event floor counts `event_id`, never `event_date` | **fixed**, 5 tests |
| `score_row` refuses a cutoff basis this version does not permit | **fixed**, 4 tests |
| eligibility is a property of the ROW, not of the schema | **fixed**, 7 tests |
| R-07 applied per quote, against an immutable lock | **fixed**, 14 tests |
| the posted price names and proves its source quote | **fixed**, 9 tests |
| the cutoff is stored on the row and inside the hash | **fixed**, 6 tests |
| bout 1's cutoff comes from bout 1's own schedule | **fixed**, 4 live-SQL tests |
| `fight_odds` observation fields immutable by trigger | **written, UNAPPLIED**, 9 live-SQL tests |
| settlement is write-once; re-runs verify and write nothing | **fixed**, 13 tests |
| the first write is an atomic compare-and-set, not a PATCH by id | **fixed**, 2 live-SQL tests |
| the linked publish quote must predate publication | **fixed**, 4 tests |
| an unratified amendment holds write mode shut | **fixed**, 9 tests |
| the lock is the EDGE's publication, never the model pick's | **fixed**, 11 tests + 4 live-SQL |
| the machine mirror cannot drift back to the superseded rule | **fixed**, 6 tests |
| `edge_model_edge_id` + `edge_published_at` required BOTH ways in SQL | **fixed**, 3 live-SQL tests |
| a snapshot names WHICH edge it froze (`edge_model_edge_id`) | **written, UNAPPLIED**, 9 tests |
| ambiguous edge identity scores nothing | **fixed**, included above |
| `model_edges` CLV-001 result columns | **written, UNAPPLIED** — last to apply |

**Amendment 3 in one line:** the card's published start belongs to bout 1 and
nobody else — applying it to all thirteen would have marked every quote after
the first bell as in-play for twelve of them.

**Amendment 4 in one line:** the benchmark is a *proxy*, captured every 5
minutes through a live card under a hard credit ceiling, with its lead time
recorded on every row.

**Amendment 4.1 in one line:** and "pre-card" does not count as "late" — a quote
before the card began is safely pre-fight and hours early on a late bout, so it
is recognised (`only_pre_card_price`) and never scored.

**Amendment 7 in one line:** an observation is written once and thereafter only
checked — and a snapshot has to say which publication it froze, not merely one
that looks like it.

**Amendment 6 in one line:** every provenance rule already written down is now
enforced on the ROW rather than assumed from the shape of the table — and §5 no
longer says freezing opens the publication gate.

**Amendment 5 in one line, and it supersedes 4.2:** the previous bout's
completion is *both* the next fight's scoring cutoff and its capture trigger. It
precedes the bell by the walkout interval — accepted, because it is the most
consistent, observable and reproducible cutoff available, and because waiting
for a confirmed bell means scoring nothing.

**Scoring cutoffs:** `scheduled_first_bout` (bout 1) and
`previous_bout_completion` (bouts 2..N) — exactly those.
`card_scheduled_start` stays reported and never scored; `bell_at` is an audit
field, and scoring against real bells would be a **new protocol version**.

**The cutoff is not a claim about when a fight started.**
`fight_odds.bout_started_at` and `is_live` are filled only by a confirmed bell;
the frozen cutoff lives in its own column, `proxy_cutoff_at`. Scoring excludes
quotes at or after the cutoff directly rather than manufacturing a liveness
fact.

**History must never constrain what can be observed next.** Both event-flow
ledgers are observation ledgers: nothing is unique on the *value* (a bout order,
a completion instant), only one statement per source per instant. A card
reordered back to a position it held before, or a completion corrected to an
instant already seen, is a truthful new observation and has to be recordable.

**The running order is a COMPLETE CARD observation.** Event Flow appends the
whole UFCStats card at one `observed_at`, so both `v_clv_close_reference` and
`build/fetch-odds.js` resolve the latest observation **as a unit**. Resolving the
latest row per *fight* would leave a scratched booking's old position alive —
two current bout 1s, a wrong `is_first_bout`, and a previous-bout lookup into a
dead booking. Older rows stay in the ledger as history; nothing is erased.

**The 20-event floor counts `event_id`.** The UFC runs two cards on one date
regularly, so counting `event_date` would open the gate on 19 real events. A
scored row with no `event_id` is warned about and never counted.

**Eligibility is a property of the ROW.** The capture migration makes the §4
fields *recordable*; it does not make any row carry them, and the 110,032 rows
captured before it will carry NULL forever — correctly. A quote scores only if
that quote holds `source_event_id`, `feed_version`, `opponent_fighter_id`,
`provider_last_update`, `retrieved_at`, `market_status` and `raw`. Present means
populated: an empty string and an empty jsonb record nothing.

**R-07 is `forecast_locked_at < close_quoted_at`, per quote.** A forecast locked
at 9:28 cannot be scored against a 9:20 book quote even though the cutoff is
9:30 — that price was on the screen before the forecast existed. The lock comes
from `pre_fight_snapshots`, matched to *this edge* by side + bet fighter + price,
because `model_edges.published_at` is mutable. The effective lock is the **later**
of the two, so an edited `published_at` can only cost observations.

**The posted price must name its source quote.** `clv_publish_quote_id` points at
the exact `fight_odds` row, and the scorer verifies rather than trusts it — same
price, same corners, same provider market, credible instant, full provenance.
Historical edges have no link and are never given a fabricated one.

**The cutoff is stored and hashed.** `clv_cutoff_at`, plus the cutoff, the lock
and the publish quote id inside the hashed artifact: a consensus is a set of
prices *selected by* a cutoff, so hashing the prices alone leaves the selection
rule outside the integrity check.

**An amendment written is not an amendment approved.** Amendment 7 is
implemented on the branch and marked PROPOSED in both copies —
`approved_by: null`, `last_ratified_version: 1.0.9`, and a ⚠ block at the top of
its markdown. `preflight` refuses write mode while any amendment is in that
state. Reporting is unaffected: a dry run against a proposed amendment is how
the owner sees what they are being asked to approve.

**The lock is the EDGE's publication instant, never the model pick's.**
`pre_fight_snapshots.engine_published_at` is `model_picks.published_at` — a
different record, published earlier: the engine posts a pick, and the edge
derived from it appears later, once the price has moved far enough to flag one.
Reading the pick's instant as the edge's placed the lock early and admitted
quotes from before the edge existed. `edge_published_at` is added beside
`edge_model_edge_id` (both required together) and written by the snapshotter.
Historical snapshots fall back to `snapshot_at` only — later than publication,
therefore conservative, and labelled as a fallback on the row — and never to
`engine_published_at`, which stays as provenance for the main model prediction.

**The machine mirror is the copy a program reads.** `protocol.json` twice kept
a superseded rule after the markdown and the code had moved on — most recently
`forecast_lock.instant_within_snapshot` still saying *"engine_published_at,
falling back to snapshot_at"*. Corrected, and `tests/test_clv_protocol.py` now
pins the mirror against the module's own constants so the two cannot be fixed
independently and disagree again.

**Amendment 7 is ratified.** Approved substance: *a scored CLV-001 observation is
permanent; later runs may verify it but never overwrite it, and a genuine
correction is a new auditable superseding record rather than a mutation of the
original.* The superseding **mechanism** is deliberately not designed yet —
nothing has been scored, so there is nothing to correct, and the half that
cannot wait is guaranteed: nothing overwrites an observation, so whatever the
correction ledger turns out to be, it inherits an intact record.

**Settlement is write-once.** A scored observation is written once and never
again: a later run re-scores it only to CHECK it, field by field, and PATCHes
nothing either way. `clv_scored_at` is never refreshed. Drift — the stored row
no longer reproducing — aborts the whole run loudly rather than being quietly
overwritten, because a PATCH at that moment is the one thing that would make the
disagreement disappear. A row scored under a different protocol version is never
touched. The first write is an atomic compare-and-set —
`id = X AND clv_scored_at IS NULL`, exactly one row expected — because the
freshness read and the write are separate round trips and two overlapping
settlers could otherwise both call a row fresh. Zero rows back means somebody
else won: the settler verifies what they wrote and never writes over it.

**The publish quote must predate publication.** A row can carry the right price,
corners, market and a credible instant and still have been captured *after* the
edge was published — a later quote that agrees with the posted price, not its
source. A book that has not moved for an hour leaves several such rows.

**A snapshot must name WHICH publication it froze.** Side + bet fighter + price
is a cross-check, not an identity — one fight can be republished with all three
the same, and `snapshot_predictions.py` keeps only the latest of several live
edges per fight. `pre_fight_snapshots.edge_model_edge_id` fixes that and the
snapshotter now writes it (probing for the column, so the migration needs no
matching deploy). Where it is absent the tuple must be unique among the fight's
live edges; two matches, or a cohort never established, is
`ambiguous_edge_identity` and scores nothing.

**Corrections resolve by observation.** `fight_bout_completions` is append-only,
so a correction is a new row — and it usually moves the instant *earlier*. The
view takes `observed_at DESC, id DESC`, so a correction from 9:31 to 9:30
resolves to 9:30. Unscorable states are told apart: `no_previous_bout_completion`
(record one completion and the captured snapshots become scorable),
`only_pre_card_price`, `no_scheduled_start`.

**Every scored row preserves** its cutoff timestamp, cutoff basis, selected quote
timestamp, lead time to the cutoff (plus a flag saying the cutoff precedes the
bell), source quote IDs and consensus provenance, and its protocol version. The
storage constraint requires all of them.

**If reliable bell timestamps arrive that is a NEW protocol version** — rows
scored under this one are never retroactively reinterpreted.

**What the proxy may be called:** the *CFL closing-price proxy* (long form,
*late pre-fight closing-price proxy*). **Never the exact sportsbook closing
line.**

No CLV statistic was computed, and none is computable until a card is captured
under the new path. Nothing renders CLV today; `track-record.html` carries a
placeholder. Legacy `clv_pp` settlement continues on its cron, untouched —
bookkeeping under the old convention, never labelled CLV.

### Product — audited 2026-09-18

A read-only audit of the five active workstreams is at
[`AUDIT_2026-09-18.md`](AUDIT_2026-09-18.md). Nothing was changed to produce
it. Three findings are load-bearing:

1. **Four public claims on `index.html` contradict artifacts in this
   repository** — most seriously "value flags graded at real closing prices",
   which is the claim CLV-001 exists to withhold, and which ships in every
   social unfurl. **Resolved 2026-09-19** under [D-010](DECISIONS.md): all four
   are off the page (T-020, done).
2. **The test suite ran nowhere — fixed.** 624 tests, 4,567 subtests and the
   Node suites guard the frozen hashes, the CLV gate, the proof-gate separation
   and DUR-002's conformance guarantee. All passed, and nothing pulled them.
   **T-010 is merged** (`4f9d4a8`), so every PR is now checked. `cfl_engine/
   requirements.txt` is still unpinned — T-011.
3. **`edges.js` publishes factor strengths with no artifact.** Record claims
   60–72% and measures 55.1% market-even (CI 46.8–63.3); takedown defence
   claims 52–56% and measures 49.3% (CI 43.7–55.0); age, retired in May, is the
   only `real` verdict. **Neither of the first two is yet an exact test of the
   shipped rule** — `factor-rates.json` applies no `willHaveWrestling()` gate
   and bands the raw rather than the smoothed record gap. **The exact
   measurement is owned by the factor-evidence workstream (FE-001), not by this
   line**; T-024 and T-025 sit with it. `computeEdges` has no production
   consumer, but `edges.html` still publishes the ranges as **Active**, so the
   correction is still owed — just not from here.

The trust pages keep their split by owner direction of 2026-09-18:
`track-record.html` is results and history, `proof.html` is evidence, method,
provenance and the publication gates.

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

**Owner attribution (T-009).** The governance records name the owner two ways —
"Reed Cannon" and "Michael Cannon". Nothing has been normalised: [D-005](DECISIONS.md)
records Q-14's ratifier exactly as `protocol.json` has it, and D-004 still reads as
written. L3, blocked on the owner; the fix is a new decision entry, never an edit.

**The bout-completions L3 is resolved as a blocker and open as an improvement.**
[`L3_ESCALATION_2026-09-16_bout_completions.md`](../research/clv/L3_ESCALATION_2026-09-16_bout_completions.md).
Amendment 4's tier 4 removed the dependency; completions now buy **lead-time
precision**, not the metric. Doing nothing costs precision, not coverage.
Nothing has been bought, priced or enabled.

**Migration status, corrected 2026-09-19.** (1) below is **APPLIED**, as is
`add_bout_order_migration.sql`, which adds `fights.is_active` and `bout_order` —
two columns `cfl.orderCard` in `_shared.js` had been reading for months against
a schema that did not have them. (2) and (3) are **still unapplied**, and (2)
was deliberately held on the 19th: it creates `odds_api_usage` **empty**, and an
empty ledger reads as *"0 spent, 500 remaining"*, which is false and would send
the credit governor to its finest rung on a wrong premise. Seed it first —
**T-029**.

**Three CLV-001 migrations are written, and the order matters.**
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

**A fifth migration adds one column**,
[`proposed_2026-09-16_snapshot_edge_identity.sql`](../research/clv/proposed_2026-09-16_snapshot_edge_identity.sql)
— `pre_fight_snapshots.edge_model_edge_id`, so a snapshot names the edge it
froze. Additive, order-independent, and it cannot be backfilled, so the sooner
it lands the sooner snapshots stop being ambiguous.

**Every `fight_odds` writer is inventoried, and the one conflict is retired** —
[`FIGHT_ODDS_WRITER_INVENTORY.md`](../research/clv/FIGHT_ODDS_WRITER_INVENTORY.md),
read-only across all five repositories on the account.
`cage-metrics-odds-scrapper`'s `backfill_odds.py` deleted opener/closer rows
before re-inserting them, which an append-only table cannot allow. **Retired by
owner decision (D-004)** and **merged to `cage-metrics-odds-scrapper@af54180`
on 2026-09-17** (PR #1): it prints a notice and exits non-zero, holds
no write verb, deleted nothing, and nothing automated ever invoked it. Seven
other write sites are compatible, and the four UPDATE sites touch only
`is_opener` / `is_closer` — independent confirmation that the trigger's
whitelist is the right cut. **The immutability migration now has no known
repository-based writer conflict**; what a grep cannot see (a SQL editor
session, a Railway console) is why its loud failure still matters, and why it
should land between cards. `cage-metrics-odds-scrapper` has been added to
`CLAUDE.md`'s related-repos list, where it had been missing.

**A fourth migration is written, and it is the one that is NOT additive.**
[`proposed_2026-09-16_fight_odds_immutability.sql`](../research/clv/proposed_2026-09-16_fight_odds_immutability.sql)
makes `fight_odds` observation fields immutable by trigger (R-01) — DELETE and
TRUNCATE refused outright, UPDATE refused for anything but the derived
`is_opener` / `is_closer` flags the legacy closer promotion maintains. It adds
triggers to a table already being written to, so it changes what an existing
writer may do, and is filed separately to be read on its own terms. Apply it
**second**, after the capture columns. Any writer to `fight_odds` outside this
repo must be inventoried first.

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

### Measurement integrity

**T-027 — closed 2026-09-18, corrected numbers published.**
`build/factor-rates.js` paged with `.range()` and no `.order()`, so pages
overlapped and skipped and the Factor Lab scored 869 market-even fights where
the real cohort is 1,220 — on an identical 8,739-fight denominator. Fixed with
keyset paging, re-run manually, compared, and published under
[D-008](DECISIONS.md) at `f40fd27c`. Seven verdicts moved, one downward. The
artifact shipped is byte-verified against the validation run
([`research/factors/T-027_PAGINATION.md`](../research/factors/T-027_PAGINATION.md)).

**The corrected run is in, and it confirms the diagnosis.** Run manually
2026-09-18: `market_even_cohort` 869 → **1,220**, which is exactly FE-001's
independent figure, while the `fights_scored` control held at 8,739. **7
verdicts moved** (one of them down), 28 buckets gained 30–40% sample. Nothing
was published. Full table in the document above.

**Two factors now survive market control, and they are not interchangeable.**
Age, and the Factor Lab's `ufc_record` — the **raw UFC** win-loss gap, ~58% on
the corrected cohort. `edges.js`'s record factor is a *different* measurement
(Laplace-smoothed, whole-career professional) that FE-001 put at ~50.2%, and it
**remains unsupported**. The publication PR states that distinction on
`stats.html`, `edges.html` and `methodology.html`, corrects `CLAUDE.md`'s "only
age" line, and adds `tests/record-factors-distinct.test.js` to stop the two
collapsing back into one generic "Record" claim.

**Age stays retired.** A standalone base rate says nothing about incremental
value over the engine's 49 covariates, and nothing here reinstates it.

**Open, and the next product question:** `edges.js`'s record and takedown-defence
heuristics are still shipped and still unsupported. FE-001 put the record factor
at ~50.2% market-even and takedown defence on the line. Nothing in T-027
validates either — what to do about them (retire, restate, or leave with the
caveat) has not been decided.

**The publication gate stays shut, and that is what made the correction
reviewable.**
`prerender.yml` used to regenerate and commit `factor-rates.json` every six
hours, so merging the fix would have republished every affected verdict
unattended. It no longer does: regeneration moved to a manual workflow that runs
under `contents: read` and commits nothing. So `factor-rates.json` now goes
stale until someone refreshes it on purpose, and publishing a corrected run is a
deliberate commit — gate #8, still the owner's, but no longer something a merge
can do by accident.

### Site

Plain static HTML/CSS/JS on GitHub Pages; `main` deploys on push. No bundler.
One Node build step (prerender: stubs, sitemap, feed) runs on a 6-hour cron;
the Factor Lab is no longer part of it. Nothing
on the card is gated in the frontend during beta.

**The homepage is the card, and it claims no edge — shipped 2026-09-19 on
UFC 331 night** (T-020 + T-021, [D-010](DECISIONS.md)). The hero names the
current event ("*UFC 331: Van vs. Pantoja 2* — Model vs Market"), the rail
counts what the backend holds (fights, forecasts locked and since when,
sportsbook lines with book range and quote age, big disagreements) and lists
the three widest gaps. Every fight row shows the model's number and the
**sportsbooks-only vig-free** market number (`v_fight_market_vigfree`, book
count and age on the cell, "stale" past three hours on a fight day) — the
15-point suppression that hid real lines is gone from `index.html` and
`event.html` — and the third cell is "Difference: N pts · CFL higher /
market higher / mostly agree", never "Edge". The Value badge, the Value sort,
the parlay strip and the "+N% model over market" figure are gone; the four
contradicted claims from the audit are gone from the meta, hero, track note
and how-to steps; the live record is described and linked, never numbered
beside the simulation (D-007). `tests/model-vs-market.test.js` guards it.
`Verify live site` (`.github/workflows/verify-live.yml`, manual, read-only)
compares served bytes with the checkout and loads the live page in a browser.
**Not shipped:** the rest of `fight-week-v2`, `revenue/trust-funnel-v1`, the
email modal — T-033 to T-035.

**The homepage headline is one record as of 2026-09-18** (T-026,
[D-007](DECISIONS.md), PR #23 at `b1bc881a`). It was computed over the live feed
and the history replay pooled together; it is now the **replay** record only,
matching the `(simulated)` label beside it, and **the published figure moved as
a result**. The live record stays on the Proof Center at its real size under its
own `TOO EARLY` chip until it can stand alone. The arithmetic lives in
`proof-gates.js::headlineFromPicks`, behind the assertion, so the page cannot go
back to computing its own headline — and that assertion now fails closed: a
graded row whose `source` resolves to no record stops the number rather than
being waved past the gate and counted anyway.

**The UFC 331 card is reconciled, 2026-09-19.** UFC removed Moicano–Ortega
(fight 47328); `fights` still carried it, so the card read 13 where the real one
is 12. It is now `is_active = false` — the **only** retired row in the database —
and `cfl.orderCard` drops it with no frontend change. Nothing was deleted: its
snapshot, its model pick and all 40 captured quotes stand, because a prediction
published against a bout later cancelled *was* published. Retired means "not on
the current card", never "did not happen". Doing it by hand is the stopgap;
`STALE_BOOKING_LIFECYCLE.md` §1 wants it falling out of Event Flow's own
`stale_fights` — **T-032**, behind **T-030**.

**T-021 has a concrete, measured case as of 2026-09-19** — found on the live UFC
331 card, documented in [`TASK_QUEUE.md`](TASK_QUEUE.md). `index.html` blanks the
market cell whenever the model sits more than 15 points above the market, then
reports that to the user as *"no consensus line yet"*. The data was verified
healthy **as `anon`**: 8 bookmakers, 235 ms, fresh. So the page hid a real price
and gave a false reason, on 3 of 12 bouts including the main event — and only
ever in the direction that flatters the model. Meanwhile gaps of 4 to 15 points
**ship as green edge percentages** ("+10% model over market"), which is the thing
`CLAUDE.md`'s first rule prohibits and Q-14 explicitly did not touch. Direction
approved: always show the line, remove every edge percentage, replace with
neutral language. Not shipped in the first pass because `value` also drives the
`Value alert` badge and the Value sort — removing the suppression alone would
start touting a +502 underdog at +33.7. **Shipped later the same night with all
three pieces moved together** — see "Site" below and [D-010](DECISIONS.md).

**Trust UX shipped 2026-09-18** (T-022 / T-023, [D-006](DECISIONS.md), PR #25 at
`e91a7da`). The Proof Center is reachable from the nav and footer rather than
from one line inside `track-record.html`. The per-fight bullets are headed
*"What stands out in this matchup"* and carry a line saying they are matchup
context, not the model's reasoning — they come from `fight-insights.js`, an
independent heuristic, and nothing in that file feeds the engine that produces
the percentage.

### CI — the tripwires are now pulled automatically

**`.github/workflows/tests.yml` runs the whole suite on every push and pull
request** (T-010, 2026-09-18). Before it, seventeen test modules existed and no
workflow ran any of them — the only test invoked anywhere was one `unittest`
module inside `event-flow.yml`. Everything passed; nothing was checking. For the
frozen-file hash check, the CLV publication gate, the L3 gate and
`test_lock_prop0002.py`'s conformance proof, that is the difference between a
guard and a note.

`pytest` runs from the **repo root**, not `tests/`: 624 Python tests, not the 168
under `tests/` alone. The other 456 are `cfl_engine/` and `research/` — the
frozen model path, the CLV-001 scorer, the integrity checks. Two jobs, Python and
Node, so a failure names its suite.

No secret is passed and none is needed, which is what lets it run as
`contents: read` and stay safe on fork pull requests. Two suites are worth
knowing precisely: `test_sql_behaviour.py` builds its own throwaway Postgres with
`initdb` and tears it down, and one test in `cfl_engine/dur001/test_dur001.py`
talks to the **production** Supabase management API, gated on
`SUPABASE_ACCESS_TOKEN`. It skips here and **must keep skipping** — adding a
secret to this workflow would make every fork pull request a production write.

**Residual gap: the engine dependencies are not pinned.** `pytest` is pinned
exactly; `cfl_engine/requirements.txt` is `>=` ranges, so the job can still
redden on an upstream release. Pinning it is a change to the engine's manifest,
not to CI. Queued as **T-011**. Audit:
[`reviews/2026-09-18-claude-ci-audit.md`](reviews/2026-09-18-claude-ci-audit.md).

---

## Refreshing this file

Whoever writes a handoff updates this file in the same commit, and moves the
date. A `STATE.md` that lags the handoff is worse than no `STATE.md`, because
the next reader trusts it.

Keep it to one screen. Detail belongs in the register, the queue, or the
handoff — not here.
