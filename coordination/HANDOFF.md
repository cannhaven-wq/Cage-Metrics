# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-16 — Event Flow's ledger design integrated into CLV-001

**From:** Claude
**To:** Reed → ChatGPT review
**Date:** 2026-09-16

**No migration applied.** All three remain proposed and unapplied. **No protocol
version bump** — v1.0.8 is unchanged, hash `a009bb17…` intact. Everything below
makes the implementation match the rule that was already frozen.

Integrates the sibling Event Flow session's `MIGRATION_ADJUSTMENT.md`, which
passed its own review, plus four consistency items.

### 1. History must never constrain what can be observed next

`UNIQUE (fight_id, source, bout_order)` is gone from `fight_bout_order`. A card
reordered and then reordered back is a truthful second observation, and Event
Flow re-appends the whole card on every change — under a value-unique index every
one of those rows would be rejected and an append-only ledger would quietly
refuse to record reality.

The same principle now applies to `fight_bout_completions`: nothing is unique on
the completed_at **value**, because a correction may return to an instant already
observed.

| index | shape | why |
|---|---|---|
| `*_latest_idx` | `(fight_id, source, observed_at desc, id desc)` | non-unique; serves every read |
| `*_one_per_instant_idx` | `UNIQUE (fight_id, source, observed_at)` | genuinely non-recurring: one statement per source per instant |
| `fight_bout_order_card_idx` | `(event_id, source, observed_at desc, id desc)` | resolving a whole card |

### 2. The running order resolves as a COMPLETE CARD, not per fight

This was a real bug, not a tidy-up. Event Flow appends the whole UFCStats card as
one observation sharing one `observed_at`. Resolving the latest row per **fight**
leaves a scratched booking's old position alive beside the current card: two
current bout 1s, a wrong `is_first_bout`, and a previous-bout lookup that walks
into a dead booking — silently.

Both consumers now resolve the latest complete card as a unit, scoped to
`source = 'ufcstats_card'`:

- `v_clv_close_reference` — new `latest_card` CTE (`distinct on (event_id)`,
  `order by event_id, observed_at desc, id desc`); `ord` joins to it on the
  instant.
- `build/fetch-odds.js` — new exported `resolveCurrentCard()`; `attachEventFlow`
  queries by `event_id` rather than by fight id, because resolving the card needs
  rows for bouts outside our candidate set. `card_complete` counts only fights on
  the current card, so a dead booking can no longer keep a finished night looking
  unfinished and burning credits.

**Reed's regression scenario, now a test.** Initial card A=1, B=2, C=3; latest
card B=1, C=2. Result: **B=1, C=2**; A absent from the current card; position 1
resolves to B and never to A; C's previous bout is B and never A; exactly one
fight is bout 1. Older rows stay in the ledger, readable as history — nothing is
erased.

### 3. The last `bell_at` remnants in the scoring schema

- `proposed_2026-09-16_clv001_columns.sql` — `clv_close_basis` is now exactly
  `'scheduled_first_bout'` / `'previous_bout_completion'`; stale comments
  rewritten.
- `cfl_engine/settle_clv.py` — `_fights_by_id`'s docstring still described the
  three-tier "actual bell → previous completion → scheduled start" resolution.
  Rewritten to the two cases, with the bell named as audit-only.
- Leftover Tier-era wording ("which tier answered", "a fourth tier") replaced.

Remaining bell-as-cutoff text sits inside the superseded Amendment 3/4/4.1/4.2
blockquotes, which stay as filed — audit trail, not live rule text.

### 4. The 20-event floor counts EVENTS, by `event_id`

The UFC runs two cards on one date regularly. Counting `event_date` would let the
gate open on 19 real events. `event_id` is now selected in `_fights_by_id`,
carried onto every scored row by `score_row`, and counted in `_report_clv001`;
rows with no `event_id` are reported as a warning and never counted.

This is not a rule change — Q-13 already said "20 distinct completed UFC events".
It is the implementation finally counting what the rule says.

### 5. A direct call cannot score against a bell

`admissible_reference` was the only gate, but `score_row` takes the instant and
the basis as separate arguments — a caller that resolved the reference itself
would hand in a real instant labelled `bell_at` and get a valid-looking score
back. The refusal now lives inside `score_row`, and its message names the
version and the two bases it permits. `scheduled_first_bout` on a non-first bout
is refused the same way.

### Files changed

| file | what |
|---|---|
| `research/clv/proposed_2026-09-16_event_flow.sql` | value-unique indexes removed; `latest_card` CTE; complete-card `ord` |
| `research/clv/proposed_2026-09-16_clv001_columns.sql` | `clv_close_basis` vocabulary reduced to two |
| `build/fetch-odds.js` | `resolveCurrentCard()` exported; `attachEventFlow` queries by event |
| `build/test-fetch-odds.js` | +6 tests — Reed's A/B/C scenario and its corollaries |
| `cfl_engine/clv/scoring.py` | basis guard in `score_row`; `event_id` on every row |
| `cfl_engine/clv/test_scoring.py` | +10 tests — the basis guard and the event count |
| `cfl_engine/settle_clv.py` | `event_id` plumbed through; distinct events by id; docstring |
| `tests/test_migrations_idempotent.py` | +8 tests — ledger index shape, complete-card rule |
| `coordination/STATE.md`, `coordination/HANDOFF.md` | this |

### Tests

| suite | result |
|---|---|
| `tests/` (repo) | **115 passed**, 3 skipped |
| `cfl_engine/clv/test_scoring.py` | **89 passed** |
| `cfl_engine/clv/test_devig.py` | **33 passed** |
| `build/test-fetch-odds.js` (Node) | **64 passed** |

All green, 301 tests. Three fixtures in `tests/` skip by design once the protocol
is frozen. Hash chain verified across 8 amendments; publication gate confirmed
shut at 0 of 100 / 0 of 20.

**One test was wrong and is fixed, not worked around.** A regex in
`test_migrations_idempotent.py` matched the view statement only up to the first
`;` — and a semicolon inside a SQL comment ended it early, so three assertions
were passing on text they had never read. They now run against comment-stripped
SQL.

### Preserved, as instructed

The approved closing-price proxy methodology and naming; the 45-minute freshness
rule; ≥3 eligible two-sided books; power de-vig per book then median; the ten
named books; append-only provenance; the 500-credit ceiling with its STOP
condition and non-raisable cap; the fail-closed publication gate; no paid
services; no production migrations.

### Remaining blockers

1. **Exact bout completions have no source.** Unchanged and still the binding
   one: required for bouts 2..N, the difference between ~1 and ~12.5 scorable
   observations per card.
2. **Running order is not captured.** Free to fix. Event Flow's ledger is the
   destination; nothing writes to it yet.
3. **Nothing is applied.**

### New L3 decisions required

**None.** No rule changed, no version bumped, no spend enabled.

One **optional** editorial amendment for Reed to consider, deliberately not made:
Amendments 3, 4 and 4.1 carry no "superseded" stamp the way 4.2 does, so their
bell-as-cutoff tables read as current to someone who starts in the middle of the
file. Stamping them would edit a frozen document and therefore needs its own
amendment and hash. Flagged rather than done.

## Next action

**ChatGPT:** the final pre-migration review — items 1–5 above, and specifically
whether the complete-card resolution in `v_clv_close_reference` and
`attachEventFlow` agree with Event Flow's ledger semantics.

**Reed, after that:** apply in order — `..._fight_odds_capture.sql`,
`..._event_flow.sql`, `..._clv001_columns.sql`.

---

## 2026-09-16 — CLV-001 v1.0.8: Amendment 5.1, four consistency fixes

**From:** Claude
**To:** Reed → ChatGPT review
**Date:** 2026-09-16

**No migration applied.** All three remain proposed and unapplied.

The v1.0.7 methodology is unchanged. These make the code, schema, view, tests and
documents agree with it.

### 1. No bell override inside this version

Amendment 5 admitted a confirmed bell "wherever one exists". Withdrawn. The
cutoff is **exactly two cases, always**: card scheduled start for bout 1, exact
previous-bout completion for bouts 2..N.

The reason it mattered: a bell override would silently make one version behave as
**two** — fights with a bell scored one way, fights without scored another,
inside the same summary statistic. A rule that depends on which optional field
happens to be populated is not frozen.

`bell_at` is retained as an audit field (`v_clv_close_reference.actual_bell_at`,
`fights.bell_at`) and never substituted for the cutoff. Scoring against real
bells is a **new protocol version**. `scoring.py`, `protocol.json`, the markdown,
the view, the tests and the comments all agree.

### 2. The cutoff is no longer dressed up as a start

`bout_started_at` was falling back to the previous bout's completion — asserting
that fight N+1 began the instant fight N ended. It did not; the walkout sits
between them, and that column's only job is to hold facts.

| field | now filled by |
|---|---|
| `fight_odds.bout_started_at` | a **confirmed bell**, nothing else |
| `fight_odds.is_live` | keyed to `bout_started_at`; `NULL` when unknown |
| `fight_odds.proxy_cutoff_at` | **new** — the frozen cutoff, under its own name |

CLV scoring excludes quotes at or after the cutoff **directly**, against the
cutoff. It never reads `is_live`, so no liveness fact is manufactured to achieve
an exclusion it can perform honestly.

### 3. Corrections resolve by observation, not by clock

`prev_done` used `max(completed_at)`. The ledger is append-only, so a correction
is a new row — and a correction usually moves the instant **earlier** (9:31
misheard, 9:30 confirmed). `max()` would keep returning the superseded 9:31
forever, leaving a minute of in-window quotes wrongly eligible.

Now `ORDER BY observed_at DESC, id DESC LIMIT 1`. **A correction from 9:31 to
9:30 resolves to 9:30.** The capture job uses the same ordering; the running-order
and card-schedule CTEs already did, and there are now tests for all three.

### 4. Tier-4 language gone

`protocol.json`'s `missing_inputs_for_tier_2` block — which still called exact
bout completions "an IMPROVEMENT rather than a prerequisite" and carried obsolete
Tier 4 coverage arithmetic — is replaced by `required_inputs`. Under Amendment 5
the previous bout's exact completion **is** the cutoff for bouts 2..N, so without
it those fights cannot be scored at all.

The remaining Tier-4 mentions are inside the superseded Amendment 4/4.1/4.2
records, which stay as filed — that is the audit trail, not live rule text.

### Files changed

| file | what |
|---|---|
| `cfl_engine/clv/scoring.py` | `bell_at` → `AUDIT_ONLY_BASES`; two-case cutoff; v1.0.8 |
| `cfl_engine/clv/test_scoring.py` | bell-override and lead-time tests rewritten |
| `cfl_engine/settle_clv.py` | `proxy_cutoff_at` in the capture probe; comments |
| `build/fetch-odds.js` | `proxyCutoffAt()` split out; `boutStartedAt()` bell-only; corrections by `observed_at` |
| `build/test-fetch-odds.js` | 10 tests for the cutoff/start split |
| `research/clv/CLV_MEASUREMENT_PROTOCOL.md` | Amendment 5.1; v1.0.8 |
| `research/clv/protocol.json` | `required_inputs` replaces the Tier-4 block; `bell_at_is_audit_only`; amendment 5.1 |
| `research/clv/proposed_2026-09-16_event_flow.sql` | no bell in `reference_at`; `observed_at DESC, id DESC` |
| `research/clv/proposed_2026-09-16_fight_odds_capture.sql` | `proxy_cutoff_at` column; corrected `bout_started_at` / `is_live` semantics |
| `tests/test_migrations_idempotent.py` | +7 tests: correction ordering, no bell override |
| `coordination/STATE.md`, `coordination/HANDOFF.md` | this |

### Tests

| suite | result |
|---|---|
| `tests/` (repo) | **109 passed**, 3 skipped |
| `cfl_engine/clv/` | **112 passed** |
| `build/test-fetch-odds.js` (Node) | **58 passed** |

All green. Hash chain verified across 8 amendments; publication gate confirmed
shut at 0 of 100 / 0 of 20.

### Preserved, as instructed

CFL closing-price proxy naming; full per-row provenance; the 500-credit governor
with its STOP condition and non-raisable ceiling; migration idempotency (15 tests);
append-only ledgers on all three tables; fail-closed publication.

### Remaining blockers

1. **Exact bout completions have no source** — now formally *required* for bouts
   2..N, not an improvement. The difference between ~1 and ~12.5 observations per
   card.
2. **Running order is not captured** — free to fix; without it nothing scores.
3. **Nothing is applied.**

### New L3 decisions required

**None new.** The bout-completions L3 is unchanged in substance and sharper in
framing: it is now a requirement rather than an accuracy improvement. The Odds
API allowance is untouched at the free 500.

## Next action

**ChatGPT:** review Amendment 5.1.

**Reed, after that:** apply in order — `..._fight_odds_capture.sql`,
`..._event_flow.sql`, `..._clv001_columns.sql`.

---

## 2026-09-16 — CLV-001 v1.0.7: the operational cutoff frozen, plus four implementation fixes

**From:** Claude
**To:** Reed → ChatGPT review
**Date:** 2026-09-16

**No migration applied.** All three remain proposed and unapplied.

### Amendment 5 — the operational cutoff, frozen

| | cutoff |
|---|---|
| bout 1 | the card's **scheduled start time** |
| bouts 2..N | the **exact completion of the immediately previous bout** |
| any bout with a confirmed bell | the **bell**, which outranks both |

Scored price = the latest eligible sportsbook snapshot **strictly before** that
cutoff.

This **supersedes Amendment 4.2**, which refused this cutoff because it precedes
the bell — and in doing so refused to score anything at all. Previous-bout
completion now has both its roles: this version's **scoring cutoff** and the
**capture trigger**. All "opener only, never a cutoff" language is gone from the
code, the view, the migrations and the protocol.

Named the **CFL closing-price proxy** (long form *late pre-fight closing-price
proxy*), never the exact sportsbook closing line. For later bouts it sits several
minutes before the bell; `clv_lead_time_is_lower_bound` marks exactly those rows
rather than hiding the gap.

Every scored observation preserves cutoff timestamp, cutoff basis, selected quote
timestamp, lead time to cutoff, source quote IDs and consensus provenance, and
protocol version — and the storage constraint requires all of them, so a figure
missing any is not writable. Reliable bell timestamps would be a **new protocol
version**; rows scored under this one are never reinterpreted.

### Fix 1 — the budget now actually declines

The real bug, and it was worse than cosmetic: clamping a 19,500-credit provider
balance to 500 on **every run** made the budget read 500 every time. It never
declined, the governor never degraded, and the ceiling was decorative.

Month-to-date spend is now the **sum of `odds_api_usage.credits_charged`** for
the current month — our own count, which nothing upstream can reset. The
provider's header is a cross-check and is believed only when **smaller** (it
catches calls we made but failed to log). The clamp stays as the second half.

A regression test pushes 40 calls through a 19,500-credit balance and asserts the
balance falls on every single one; another asserts a spent-out month reaches STOP
through our own count alone.

The 500 free allowance stays the ceiling. No paid tier assumed or enabled.

### Fix 2 — the migrations are genuinely re-runnable

Three files claimed idempotency while containing **13 bare `ADD CONSTRAINT`
statements**, each of which errors on a second run — so a routine re-apply would
have half-applied. All 13 are now wrapped in `DO` blocks that check
`pg_constraint` first. `tests/test_migrations_idempotent.py` (8 tests) enforces
it, including a check that a file *claiming* idempotency actually is, so the
claim and the reality cannot drift apart again.

One constraint was removed rather than guarded:
`model_edges_clv_window_opens_before_it_closes` asserted an ordering that
Amendment 5 inverts. `clv_lead_time_positive` already encodes the ordering that
matters.

### Fixes 3–5 — preserved

Append-only protections on all three ledgers are intact and now have their own
tests. Publication stays fail-closed at 0 of 100 / 0 of 20. Naming is the CFL
closing-price proxy throughout.

### Files changed

| file | what |
|---|---|
| `cfl_engine/clv/scoring.py` | Amendment 5 cutoff set, `PRECEDES_BELL_BASES`, new unscored reason, v1.0.7 |
| `cfl_engine/clv/test_scoring.py` | cutoff/lead-time/provenance tests rewritten |
| `cfl_engine/settle_clv.py` | `is_first_bout` threaded through; preflight text; `prev_bout_completed_at` |
| `build/fetch-odds.js` | `spentThisMonth`, `remainingCredits`, `credits_charged` recording |
| `build/test-fetch-odds.js` | 6 credit-accounting regression tests |
| `research/clv/CLV_MEASUREMENT_PROTOCOL.md` | Amendment 5; v1.0.7 |
| `research/clv/protocol.json` | amendment chain, benchmark naming, accounting note |
| `research/clv/proposed_2026-09-16_event_flow.sql` | view cutoff, `credits_charged`, DO blocks |
| `research/clv/proposed_2026-09-16_clv001_columns.sql` | basis vocabulary, constraints, DO blocks |
| `research/clv/proposed_2026-09-16_fight_odds_capture.sql` | DO blocks |
| `tests/test_migrations_idempotent.py` | **new** — 8 tests |
| `coordination/STATE.md`, `coordination/HANDOFF.md` | this |

### Tests

| suite | result |
|---|---|
| `tests/` (repo, incl. new migration tests) | **102 passed**, 3 skipped |
| `cfl_engine/clv/` (scoring + devig) | **111 passed** |
| `build/test-fetch-odds.js` (Node) | **60 passed** |

All green. Protocol hash chain verified across 7 amendments; publication gate
confirmed shut.

### Remaining blockers

1. **Exact bout completions have no source.** Under Amendment 5 these are the
   *scoring cutoff* for bouts 2..N, not just a trigger — so they are now the
   difference between ~1 and ~12.5 observations per card. This is the single
   highest-leverage open item.
2. **Running order is not captured.** Free to fix (ufcstats lists cards in
   order); without it no fight is identifiable as bout 1 and no bout has a
   "previous" one, so nothing scores at all.
3. **Nothing is applied.** Migrations wait on Reed. The 5-minute cadence starts
   when the event-flow migration lands, since `odds_api_usage` lives there.

### New L3 decisions required

**One, and it is the same one, now sharper:** where exact bout completion times
come from. Under Amendment 5 they are load-bearing for the metric rather than an
accuracy improvement. Options and costs are in
`research/clv/L3_ESCALATION_2026-09-16_bout_completions.md` — nothing has been
bought, priced or enabled. No other L3 is raised by this change; the Odds API
allowance is unchanged at the free 500.

## Next action

**ChatGPT:** review Amendment 5 and the four fixes.

**Reed, after that:** apply in order — `..._fight_odds_capture.sql`,
`..._event_flow.sql`, `..._clv001_columns.sql`.

---

*Older entries are in git history — the convention at the top of this file is
to keep the last three.*
