# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-16 — Amendment 7 RATIFIED; the edge publication instant fixed

**From:** Claude
**To:** Owner → ChatGPT review
**Date:** 2026-09-16

**No migration applied. No production write. No CLV published. No paid API call.**
Five migrations, all proposed and unapplied.

**v1.0.10 is ratified.** Approved by **Michael Cannon (owner, L3), 2026-09-16**.
Hash `df5ce2a5…`, chained from `f8c6e68a…`. The chain verifies across ten
amendments and every one now records an approver, a date and
`motivated_by_observed_results: false`.

### The defect: the lock was the model pick's timestamp, not the edge's

ChatGPT was right, and it was a live lookahead hole.

`pre_fight_snapshots.engine_published_at` is `model_picks.published_at` —
`snapshot_predictions.py` fills it from the **pick** row, and separately reads
the **edge** row for side, fighter and price without ever storing the edge's own
`published_at`. `forecast_lock` then read the pick's instant as the edge's.

A pick and a value edge are different records published at different times: the
engine posts a pick, and the edge derived from it appears later, once the price
has moved far enough to flag one. So the lock sat early, and quotes from before
the edge existed were eligible. A lookahead violation wearing an immutable
record's clothes — the worst kind, because everything about it looks audited.

| | now |
|---|---|
| modern snapshot | `edge_published_at`, required together with `edge_model_edge_id` |
| historical snapshot | `snapshot_at` — later than publication, therefore conservative, and flagged `immutable_is_conservative_fallback` on the row |
| `engine_published_at` | **never a lock, in any branch.** Carried as provenance for the main model prediction, which is what it is |

The publish-quote bound follows the same instant, tightened by
`model_edges.published_at` when that is earlier. A mutable timestamp may narrow
the window; it may never widen it.

Two database constraints keep the column honest: an edge instant requires an
edge id beside it (an instant with no id cannot be attached to a publication,
and would be indistinguishable from the pick's), and an edge cannot have been
published after the snapshot that froze it.

**ChatGPT's scenario, run:** pick Monday, edge Tuesday, snapshot Wednesday,
`published_at` later edited back to **Sunday**, matching quote Monday evening.

- Monday quote **refused** — `forecast_not_before_close`, all six books.
- Immutable lock stays **Tuesday** (modern) or **Wednesday** (legacy fallback).
- **Never Monday.**
- The backdated Sunday *tightens* the publish-quote bound rather than widening
  it, so the Monday quote is refused on that side too.

I reverted the lock resolution to the old behaviour to confirm the regression
has teeth: **7 of its 10 tests fail** against the pre-fix code.

### Amendment 7 ratification

Recorded in both copies, with the approved substance rather than just a yes:

> Once a CLV-001 result is officially scored, it is permanent and may never be
> overwritten. If a genuine error is later discovered, the correction must be
> appended/superseded with an audit trail rather than silently replacing the
> original record.

**The superseding mechanism is deliberately not designed here**, per the owner's
instruction, and `protocol.json` records that deferral as part of what was
approved. Zero observations have been scored, so there is nothing to correct;
the half that cannot wait is guaranteed — nothing overwrites an observation — so
whatever the correction ledger turns out to be, it inherits an intact record.

The `all_amendments_approved` preflight condition **stays**. It no longer fires,
and it governs the next unratified amendment. A gate deleted the moment it first
goes green was never a gate, and there is a test saying so.

### Owner naming

`TASK_QUEUE.md` now names **Michael Cannon** as the Owner; the rest of live
coordination text uses the role. Historical records — `DECISIONS.md`, earlier
handoffs, Amendments 1–6 — keep their original attribution.

**One inconsistency I did not silently resolve:** `CLAUDE.md` still records the
owner as Reed Cannon. That is the repo's canonical config, not coordination
text, and renaming a person there on my own initiative seemed like the wrong
call. Say the word and it is a one-line edit.

### Everything preserved

Re-verified by the suites, not by assertion: atomic compare-and-set first write,
lost-race re-read and verification, post-score drift abort, `clv_scored_at` never
refreshed, exact `edge_model_edge_id`, ambiguous historical identity fails
closed, no fabricated `clv_publish_quote_id`, row-level quote provenance,
`forecast_locked_at < quote_at < cutoff`, stored and hashed cutoff, bout-1
schedule resolution, whole-card event-flow resolution, raw quote immutability,
`captured_at` 45-minute staleness, event-ID publication counting, bell audit-only,
publication gate shut.

### Files changed

| file | what |
|---|---|
| `cfl_engine/clv/scoring.py` | `SNAPSHOT_EDGE_PUBLISHED_FIELD`, `NOT_AN_EDGE_LOCK_FIELDS`; lock resolution rewritten; publish bound follows it |
| `cfl_engine/snapshot_predictions.py` | writes `edge_published_at` from the EDGE row, behind the same column probe |
| `cfl_engine/settle_clv.py` | fetches and normalises the new column, with a fallback |
| `research/clv/proposed_2026-09-16_snapshot_edge_identity.sql` | `edge_published_at` + 2 constraints |
| `research/clv/CLV_MEASUREMENT_PROTOCOL.md`, `protocol.json` | Amendment 7 (e); ratification; `edge_publication_instant`; hash re-chained |
| `cfl_engine/clv/test_scoring.py` | `legacy_snapshot()` fixture; +10 tests for the calendar scenario; ~20 rewired |
| `tests/test_sql_behaviour.py` | +4 behavioural tests on the new column and constraints |
| `tests/test_clv_protocol.py` | +3 ratification-discipline tests |
| `coordination/STATE.md`, `coordination/TASK_QUEUE.md`, `coordination/HANDOFF.md` | this |

### Tests

| suite | result |
|---|---|
| `tests/` (repo, incl. static migration + Postgres behavioural) | **163 passed**, 3 skipped |
| `cfl_engine/clv/` | **199 passed** |
| `build/test-fetch-odds.js` (Node) | **66 passed** |

**428 total, all green.** The 3 skips are frozen-protocol fixtures that skip by
design. Still locally reported — no CI workflow exists and `CLAUDE.md` says not
to add one without asking; the offer stands.

### Remaining blockers

1. **Nothing writes `clv_publish_quote_id`.** Still the binding one: until the
   edge publisher records it contemporaneously, no edge scores.
2. **Exact bout completions have no source.**
3. **Running order is not captured.**
4. **Nothing is applied.**

### L3 decisions waiting

1. Apply the five migrations, in order.
2. Inventory every external `fight_odds` writer before
   `..._fight_odds_immutability.sql` — it is the one that is not additive.
3. `..._snapshot_edge_identity.sql` touches `pre_fight_snapshots`: two nullable
   columns and two NOT VALID checks, no trigger created or altered (there is a
   behavioural test asserting the trigger count on that table is unchanged).
4. Optional, raised by ChatGPT: a DB guard making CLV result columns immutable
   once `clv_scored_at` is set — stronger than the compare-and-set, non-additive,
   its own decision.
5. Whether to add the CI workflow.

## Next action

**ChatGPT:** confirm the edge-publication fix, and in particular that
`snapshot_at` is the right conservative fallback for historical snapshots rather
than refusing them outright.

**Owner:** the L3 list above.

---

## 2026-09-16 — Amendment 7 hardened, and marked PROPOSED

**From:** Claude
**To:** Owner → ChatGPT review
**Date:** 2026-09-16

**No migration applied. No write enabled. No CLV published. No spend.**
Hash `6a009c49…`, re-chained from `f8c6e68a…`.

### 1. The first write is now atomic

You were right: `_partition_for_write` read `clv_scored_at IS NULL` and the write
happened a round trip later, so two overlapping settlers could both call a row
fresh and the second would overwrite the first, `clv_scored_at` included. The
application logic was write-once; the database write was not.

`claim_and_write_clv001()` issues

```
PATCH /model_edges?id=eq.<X>&clv_scored_at=is.null
Prefer: return=representation
```

and requires **exactly one** row back. The filter is evaluated by Postgres as
part of the UPDATE, under the row lock, so exactly one of two racing writers
matches and the other matches none.

Zero rows back is not an error to retry — it means somebody else got there
first. The settler then **re-reads those rows and verifies them** exactly as a
re-run would: agreement means the race was harmless, disagreement is reported
loudly with nothing written over. More than one row back exits rather than
guessing.

Both regressions run against a real Postgres: the same claim issued twice
returns `1` then `0`, and the first settler's `clv_return` and `clv_scored_at`
survive. There is a control test showing the unconditional PATCH by id **does**
overwrite, so the pair documents the bug as well as the fix.

The DB-guard version you mention — CLV result columns immutable once
`clv_scored_at` is set — is stronger and I have not written it: it is
non-additive, it would collide with the legacy settlement path on the same
table, and it is a separate L3. Flagged, not done.

### 2. Amendment 7 is PROPOSED, not approved

You are right, and the contradiction was mine. Fixed in both copies and enforced:

- `protocol.json`: `approved_by: null`, `approval_status: "PROPOSED — not
  owner-approved"`, `last_ratified_version: "1.0.9"`, and a `version_status`
  saying 1.0.10 is proposed.
- The markdown carries a **⚠ PROPOSED — NOT APPROVED** block at the top of
  Amendment 7 and a line in the status banner. The approval line is gone.
- **`preflight` now refuses write mode while any amendment lacks an approver**
  (`all_amendments_approved`). Not a note in a handoff — a condition, and
  `blockers` forces `write_allowed` false. Reporting is untouched, which is how
  you see what you are being asked to approve.

Six tests pin the discipline: an amendment either names an approver or says
PROPOSED; a pending one cannot be recorded as the ratified version; the markdown
must mark it near its heading and must not carry an approval line there; and a
pending amendment must hold write mode shut.

v1.0.10 stays as the version number, per your read — the bump is reasonable, the
false approval was the problem.

### 3. The publish quote must predate publication

`verify_publish_quote` proved price, corners, market, provenance and a credible
instant — and would accept a quote captured *after* the edge was published. That
is the routine case, not the exotic one: a book that has not moved for an hour
leaves several rows at the same price and only one of them precedes publication.

Now `captured_at <= published_at`, where the bound is the **earlier** of the
edge's `published_at` and the immutable snapshot instant. That is the opposite
choice from the effective lock, deliberately: the lock takes the later of the
two because a later lock only shrinks the closing window, but here the
comparison runs the other way, so the later instant is the permissive one and a
`published_at` edited forwards would admit a quote captured after the real
publication. There is a test for that specific direction.

Consequence, also tested: the publish side can never be drawn from inside the
window the closing side is measured over.

### Files changed

| file | what |
|---|---|
| `cfl_engine/settle_clv.py` | `claim_and_write_clv001` compare-and-set; lost-race verification; `all_amendments_approved` preflight |
| `cfl_engine/clv/scoring.py` | `verify_publish_quote` temporal bound, anchored to the earlier instant |
| `cfl_engine/clv/test_scoring.py` | +4 tests on the temporal bound |
| `tests/test_sql_behaviour.py` | +2 live-Postgres race tests, fix and control |
| `tests/test_clv_protocol.py` | +6 approval-discipline tests |
| `research/clv/CLV_MEASUREMENT_PROTOCOL.md`, `protocol.json` | Amendment 7 marked PROPOSED; hash re-chained |
| `coordination/STATE.md`, `coordination/HANDOFF.md` | this |

### Tests

| suite | result |
|---|---|
| `tests/` (repo) | **156 passed**, 3 skipped |
| `cfl_engine/clv/` | **187 passed** |
| `build/test-fetch-odds.js` (Node) | **66 passed** |

409 total, all green — still locally reported; the CI offer from the last
handoff stands.

### Remaining blockers

Unchanged: nothing writes `clv_publish_quote_id`; exact bout completions have no
source; running order is not captured; nothing is applied. And now one more, by
construction: **Amendment 7 is unratified, so write mode is shut** — which is
the intended state, not a defect.

### L3 decisions waiting

1. **Ratify or withdraw Amendment 7 / v1.0.10.** Until then the code runs in
   report mode only.
2. Amendments 1–6 and the v1.0.9 bump — ChatGPT recommends keeping it, I agree.
3. Every external `fight_odds` writer inventoried before
   `..._fight_odds_immutability.sql` is applied.
4. `..._snapshot_edge_identity.sql` touches `pre_fight_snapshots`. One nullable
   column, no trigger changed, no row read or written — but it is that table.
5. Optional, mentioned by ChatGPT: a DB guard making CLV result columns immutable
   after `clv_scored_at` is set. Stronger than the compare-and-set, non-additive,
   and its own decision.

## Next action

**ChatGPT:** confirm the three fixes, in particular whether anchoring the
publish-quote bound to the *earlier* of the two publication instants is right —
I went stricter than the literal `captured_at <= published_at` you specified,
and stricter is not automatically correct.

**Owner:** the L3 list above, starting with whether Amendment 7 is ratified.

---

## 2026-09-16 — CLV-001 v1.0.10: Amendment 7, write-once settlement

**From:** Claude
**To:** Owner → ChatGPT review
**Date:** 2026-09-16

**No migration applied. No write enabled. No CLV published. No spend.**
Five migrations now, all proposed and unapplied. **v1.0.10**, hash `b8a1f0aa…`,
chained from `f8c6e68a…`.

ChatGPT found a blocker the last handoff missed, and it was a real one.

### 1. Settlement was not write-once. It is now.

`clv001_main()` re-scored every historical live edge on every run and re-`PATCH`ed
every scored result — no check for an existing `clv_protocol_version`,
`clv_consensus_sha256`, `clv_scored_at` or stored cutoff. So a second run could
reinterpret an earlier observation against **later database state** — a quote
inserted since, a corrected completion, a reschedule — and refresh
`clv_scored_at` to the moment it did. Nothing on the row would have shown it
moved. That is the exact thing the protocol says never happens.

| state of the row | what a run does now |
|---|---|
| no CLV-001 score | score it, write **once** |
| scored under this version, reproduces | verify, **zero writes**, `clv_scored_at` untouched |
| scored under this version, does **not** reproduce | **abort the whole run**, loudly |
| scored under another version | left exactly as it is |

Verification covers every persisted field — protocol version, return, fair
probability, book count, source quote ids, consensus hash, close basis, lead time
and its flag, proxy instant, cutoff, publish quote id — plus the stored artifact
**re-hashed against its own recorded `clv_consensus_sha256`**, which is what
catches a jsonb edited in place. A test asserts that every persisted column is
either verified or explicitly exempted, so a future column cannot be added and
then never checked again.

Drift aborts *before* any PATCH, including the rows that would have been scored
for the first time — there is a source-level test that the `sys.exit` precedes
the write loop. A PATCH at that moment is the one thing that would make the
disagreement disappear.

Regressions, both asked for: a second identical settlement writes nothing, and
changed evidence after scoring is a hard failure rather than a rewrite.

### 2. `clv_publish_quote_id` stays fail-closed

Unchanged and now written down as deliberate, in the protocol and in
`protocol.json` (`publish_price_provenance.producer_status`). No producer
exists, so **no edge scores, historical or future**, and nothing backfills the
link by matching prices. A fail-closed rule with no producer looks like a bug
until somebody records that it is not.

### 3. Edge identity — you were right, and it is worse than "in principle"

`snapshot_predictions.py` reads *every* live edge on a fight and keeps the one
with the latest `published_at`:

```python
cur = edges.get(e["fight_id"])
if cur is None or (e["published_at"] or "") > (cur["published_at"] or ""):
    edges[e["fight_id"]] = e
```

So the architecture does **not** guarantee one live edge per fight. The snapshot
records one particular publication chosen from several, and the tuple cannot say
which. Both fixes are in:

1. **`pre_fight_snapshots.edge_model_edge_id`** — the id of the `model_edges` row
   the snapshot froze. A fifth migration adds it, and `snapshot_predictions.py`
   now selects `id` and writes it. It **probes for the column and omits it when
   absent**, so the migration and the deploy need no ordering between them and
   an unapplied migration can never take the snapshot cron down.
2. **Uniqueness, for every snapshot taken before that column existed.** Exactly
   one live edge on the fight may match the snapshot's tuple. Two matches →
   `ambiguous_edge_identity`, unscored. A cohort that was never established is
   refused the same way: not established is not the same as established.

The scored row records which applied (`forecast_lock.edge_identity` =
`shared_edge_id` or `tuple_unique_in_cohort`), because they are not the same
strength of evidence. No snapshot is backfilled with an inferred id.

### 4. Owner naming

Live coordination text — `STATE.md`, `TASK_QUEUE.md`, `CRITICAL_GATES.md`, and
`tests/test_coordination.py`'s owner enforcement — now says **Owner** as a role
rather than a personal name, so a change of who holds it is not a repo-wide
rename. `DECISIONS.md`, earlier handoff entries and every amendment block keep
the name they were written with: rewriting those would falsify who decided what.

I used the role word rather than substituting a different personal name.
`CLAUDE.md` still records the owner as Reed Cannon, and I have not changed it —
if the name itself has changed, say so and it is a one-line edit.

### On your L3 recommendation

Agreed and taken: **v1.0.9 is kept**, and this pass is v1.0.10 on the same
reasoning — the estimator did not move, the admissible observation set did.

### Files changed

| file | what |
|---|---|
| `cfl_engine/settle_clv.py` | `_partition_for_write`; verification-only re-runs; drift abort; cohort; stored columns read back |
| `cfl_engine/clv/scoring.py` | `verify_against_stored`, `has_clv001_score`, `VERIFIED_FIELDS`; `forecast_lock` raises and takes a cohort; v1.0.10 |
| `cfl_engine/snapshot_predictions.py` | selects and writes `edge_model_edge_id`, behind a column probe |
| `research/clv/proposed_2026-09-16_snapshot_edge_identity.sql` | **new** — one column on `pre_fight_snapshots` |
| `research/clv/proposed_2026-09-16_clv001_columns.sql` | `ambiguous_edge_identity` in the closed vocabulary |
| `research/clv/CLV_MEASUREMENT_PROTOCOL.md`, `protocol.json` | Amendment 7; v1.0.10; hash chain |
| `cfl_engine/clv/test_scoring.py` | +22 tests (write-once, edge identity) |
| `tests/test_sql_behaviour.py`, `tests/test_migrations_idempotent.py` | the fifth migration added to both |
| `coordination/*`, `tests/test_coordination.py` | Owner as a role |

### Tests

| suite | result |
|---|---|
| `tests/` (repo) | **149 passed**, 3 skipped |
| `cfl_engine/clv/` | **183 passed** |
| `build/test-fetch-odds.js` (Node) | **66 passed** |

398 total, all green — and still **locally reported**. See below.

### On CI

You are right that there are no status checks on the commit. The repo has no
workflow that runs these suites; `.github/workflows/` covers prerender, snapshot
and the digest. `CLAUDE.md` says not to add a test runner without asking, so I
have not. **Say the word and it is a short workflow** — `python -m unittest
discover -s tests` plus the two module suites plus `node --test`, on push and PR.
The Postgres suite skips where no cluster exists, so it costs nothing until a
service container is worth adding.

### Remaining blockers

1. **Nothing writes `clv_publish_quote_id`.** Still the binding one. Until the
   edge publisher records it contemporaneously, no edge scores.
2. **Exact bout completions have no source.**
3. **Running order is not captured.**
4. **Nothing is applied.**

### L3 decisions

1. **The two from last time stand**: v1.0.9 kept (ChatGPT recommends it, I agree,
   the call is yours), and the immutability migration needs every external
   `fight_odds` writer inventoried before it is applied.
2. **New, small:** applying `..._snapshot_edge_identity.sql` touches
   `pre_fight_snapshots`, which is the pre-fight record. It is one nullable
   column, no trigger changed, no row read or written — but it is that table, so
   it is named rather than slipped in.

## Next action

**ChatGPT:** confirm the write-once semantics — in particular whether aborting
the entire run on any drift is the behaviour you want, versus scoring the fresh
rows and reporting the drift separately. I chose the stricter one.

**Owner:** the L3 items above, and whether to add the CI workflow. Then apply in
order — `..._fight_odds_capture.sql`, `..._fight_odds_immutability.sql`,
`..._event_flow.sql`, `..._snapshot_edge_identity.sql`, `..._clv001_columns.sql`.

---

*Older entries are in git history — the convention at the top of this file is
to keep the last three.*
