# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-16 — D-004: the legacy BFO backfill is retired

**From:** Claude
**To:** Owner → ChatGPT review
**Date:** 2026-09-16

**No migration applied. No production write. No CLV published. No paid API call.**
No `fight_odds` row deleted or rewritten, here or anywhere.

Two repositories:

| repo | commit | branch |
|---|---|---|
| `cage-metrics-odds-scrapper` | `d8e1908` | `retire/backfill-odds-2026-09-16` (pushed, **not merged** — it is not my default branch to push to) |
| `Cage-Metrics` | see below | `research/clv-001-revision` |

### The retirement

`backfill_odds.py` now prints a retirement notice and **exits non-zero**. It
holds no `delete`, `insert`, `update` or `upsert` — verified by grep after the
change, and by running it.

Non-zero is the deliberate part. A scheduler that read a silent success would go
on calling it forever and nobody would learn it had been retired.

The docstring carries the full reasoning rather than a one-line "retired":
what it did, the R-01 clause it collides with, the fact that its
delete-before-insert was *the* mechanism of its idempotency, and — for whoever
wants the capability back — that the append-only replacement appends a second
observation and resolves by `(observed_at DESC, id DESC)`, the pattern
`fight_bout_completions` already uses. The implementation is preserved in git
history at `1ad1aa6`.

### No automation referenced it

Checked before changing anything:

- `.github/workflows/` — three workflows, running `polymarket/backfill_history.py`,
  `polymarket/probe_history.py`, and the nightly model-training loop. None
  mentions it.
- `nixpacks.toml` — `[start] cmd = "python odds_scraper.py"`.
- No `Procfile`, no `railway.json`/`railway.toml`.
- The only references anywhere were **documentation**: two in `README.md` and one
  comment in `backtest_queries.sql`. All three updated.

**One thing I cannot verify.** The README described a *second Railway service*
whose start command was overridden to `backfill_odds.py`. Railway configuration
is not in git. If that service still exists it will now exit non-zero with the
notice instead of deleting anything — loud and harmless — and it should be
removed. Flagged in the README and the inventory.

### Nothing scorable was lost

BFO publishes the price but not when it was observed, so the script stamped
`captured_at` as the Unix epoch *by design* — the source comment reads
"placeholder; opener time isn't precisely known". R-13 excludes every such row
from scoring permanently; they are the bulk of the 30,724 it names. The rows it
already wrote are untouched and still feed `model/v5`, `model/v6` and the rest,
which read opener/closer prices without needing a capture instant.

### Cage-Metrics side

- **`CLAUDE.md`** — `cage-metrics-odds-scrapper` added to the related-repos
  list, named as the main writer to `fight_odds`, linked to the inventory.
- **`FIGHT_ODDS_WRITER_INVENTORY.md`** — status block at the top: no known
  repository-based writer conflict remains. The blocker is left described in
  full rather than deleted; a retired conflict nobody can read the reasoning for
  is one somebody re-creates.
- **`DECISIONS.md`** — **D-004**, quoting the owner, recording that the repo
  change is revertible and the rule it protects is not: a ledger that has been
  append-only and then is not was never append-only.
- **`STATE.md`**, **`HANDOFF.md`** — this.

### Tests

| suite | result |
|---|---|
| `tests/` (repo, incl. static migration + Postgres behavioural) | **171 passed**, 3 skipped |
| `cfl_engine/clv/` | **200 passed** (`test_scoring` 167 + `test_devig` 33) |
| `build/test-fetch-odds.js` (Node) | **66 passed** |

**437 total, all green.** No CLV-001 code changed in this pass. Still locally
reported.

### Where this leaves the migration

`proposed_2026-09-16_fight_odds_immutability.sql` has **no known
repository-based writer conflict**. It remains unapplied, with the other four.

## Next action

**ChatGPT:** the migration application plan.

**Owner:** merge `retire/backfill-odds-2026-09-16` in the odds scrapper (pushed
as a branch, not to `main`), and check whether the second Railway service still
exists.

---

## 2026-09-16 — conformance cleanup: the machine mirror and the SQL pairing

**From:** Claude
**To:** Owner → ChatGPT review
**Date:** 2026-09-16

**No migration applied. No production write. No CLV published. No paid API call.**
Five migrations, all proposed and unapplied. Hash `8167dcf1…`, re-chained from
`df5ce2a5…`. No rule changed — this is a conformance correction to the
already-approved Amendment 7, recorded as such inside it.

### 1. The machine mirror still carried the superseded rule

`protocol.json` is the copy a program reads, and it had drifted — for the second
time, in the same direction: the markdown and the code were right and the mirror
was stale.

| key | was | now |
|---|---|---|
| `forecast_lock.instant_within_snapshot` | "engine_published_at, falling back to snapshot_at" | `edge_published_at`, `snapshot_at` fallback, **never** `engine_published_at` |
| `forecast_lock.immutable_record` | the tuple, as the matching rule | `edge_model_edge_id` primary; the unique tuple named as the **legacy fallback** |
| `forecast_lock.engine_published_at` | absent | says what it is — `model_picks.published_at`, pick provenance, not a lock |
| `publish_price_provenance` | price + identity only | `temporal_bound` explicit, and the timing check added to `verified_not_trusted` |

A stale docstring in `forecast_lock()` still said the pick instant was preferred,
under an implementation that did the opposite. Fixed with it.

**Six new tripwires** so this cannot happen a third time, and one of them pins
the mirror against the module's own constants (`NOT_AN_EDGE_LOCK_FIELDS`,
`SNAPSHOT_EDGE_PUBLISHED_FIELD`, `SNAPSHOT_EDGE_ID_FIELD`) rather than restating
the rule in prose — so the two copies cannot be corrected independently and
disagree again.

### 2. The pairing is enforced both ways

The migration checked that a timestamp had an id. It did not check the reverse,
so an id with a NULL instant was accepted. You are right that the runtime was
safe — it falls back to `snapshot_at` — and right that safe is not the same as
impossible, and the approved rule says *together*.

`pre_fight_snapshots_edge_id_needs_published_at` added. Behavioural regressions:
an INSERT with `edge_model_edge_id` set and `edge_published_at` NULL **fails**,
and a historical row with both NULL is still valid and untouched.

**One thing the reverse constraint exposed.** `model_edges.published_at` can be
NULL, so the snapshotter could have written an id with no instant and failed the
whole INSERT batch — taking the snapshot cron down on a card night. Added
`_pair_edge_identity()`: both halves are dropped unless both are present, with a
log line. That fight degrades to the legacy path, which costs precision and is
the right trade against losing the snapshot.

### Files changed

| file | what |
|---|---|
| `research/clv/protocol.json` | `forecast_lock` and `publish_price_provenance` synchronised; `db_pairing`; hash re-chained |
| `research/clv/CLV_MEASUREMENT_PROTOCOL.md` | conformance correction recorded inside Amendment 7 |
| `research/clv/proposed_2026-09-16_snapshot_edge_identity.sql` | the reverse constraint |
| `cfl_engine/clv/scoring.py` | stale `forecast_lock()` docstring rewritten |
| `cfl_engine/snapshot_predictions.py` | `_pair_edge_identity()` |
| `tests/test_clv_protocol.py` | +6 mirror-drift tripwires |
| `tests/test_sql_behaviour.py` | +2 pairing regressions |
| `cfl_engine/clv/test_scoring.py` | +1 producer-pairing test |
| `coordination/STATE.md`, `coordination/HANDOFF.md` | this |

### Tests

| suite | result |
|---|---|
| `tests/` (repo, incl. static migration + Postgres behavioural) | **171 passed**, 3 skipped |
| `cfl_engine/clv/` | **200 passed** (`test_scoring` 167 + `test_devig` 33) |
| `build/test-fetch-odds.js` (Node) | **66 passed** |

**437 total, all green.** Corrected 2026-09-16: this entry first read 199 / 436,
written before the last test in the pass was added. The commit message for
`49eca588` had it right and this table was the stale copy — the same
two-copies-drifting failure the mirror tripwires now guard against, one level up.
Still locally reported; no CI workflow exists and `CLAUDE.md` says not to add one
without asking.

### Operational item 1 is done: every `fight_odds` writer is inventoried

[`research/clv/FIGHT_ODDS_WRITER_INVENTORY.md`](../research/clv/FIGHT_ODDS_WRITER_INVENTORY.md).
Read-only: all five repositories on the account cloned shallow and grepped, every
hit classified by verb. No database queried, nothing modified.

**One blocker**, and it is in a repository `CLAUDE.md` does not list.

`cage-metrics-odds-scrapper` — `backfill_odds.py:457` **deletes**
opener/closer rows for a (fight, book) and re-inserts them. That is what makes
the backfill re-runnable, and an append-only table cannot offer it. Three ways
forward — retire it, make it append-only, or apply knowing it breaks — and the
choice is the owner's. Worth knowing while deciding: that function stamps
`captured_at` as the Unix epoch by design ("placeholder; opener time isn't
precisely known"), which is where R-13's 30,724 sentinel rows come from. Nothing
it writes can ever be scored, so this is about not breaking a tool, not about the
measurement.

**Everything else is compatible.** Seven other write sites across the odds
scrapper and this repo: four INSERTs, and four UPDATEs that touch `is_opener` /
`is_closer` **and nothing else**. That last part is the useful part — the
whitelist was chosen from first principles, and code written by somebody who had
never heard of this migration independently agrees with it. If the whitelist were
wrong, that is where it would have shown.

`cage-metrics-scrapper`, `cage-metrics-event-scrapper` and `cfl-snapshotter` do
not write to `fight_odds` at all.

**A finding that is not about this migration.** `cage-metrics-odds-scrapper` is
absent from `CLAUDE.md`'s "Related repos" list — and it is the repository that
does most of the writing to `fight_odds`. Every step in this project that started
from "the repos are X, Y and Z" was working from an incomplete list. Nothing
downstream turned out wrong, but that was luck rather than method. One-line edit,
left to the owner since that file is the project's canonical description.

What a grep cannot see is stated in the inventory: a SQL editor session, a manual
`psql`, a Railway console, an Edge Function. The migration is the backstop —
an unknown writer errors loudly instead of quietly rewriting evidence — but loud
on a Tuesday afternoon beats loud at 23:00 UTC on a card night, which argues for
landing it between cards.

### Remaining blockers — operational, not evidential

1. ~~Inventory every `fight_odds` writer.~~ **Done**, above — one decision falls
   out of it.
2. The real edge publisher must write `clv_publish_quote_id`.
3. Running order is not captured.
4. Exact bout completions have no source.
5. The five migrations must be deliberately applied.
6. A real event must run through the pipeline before CLV-001 collection is
   relied on.

## Next action

**Owner:** `backfill_odds.py` — retire it, make it append-only, or accept that
it breaks — and then the migration-application decision. Order:
`..._fight_odds_capture.sql`, `..._fight_odds_immutability.sql`,
`..._event_flow.sql`, `..._snapshot_edge_identity.sql`,
`..._clv001_columns.sql`. The second is the one that is not additive and needs
every external `fight_odds` writer inventoried first.

**ChatGPT:** nothing outstanding on the evidence chain by your last pass.

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

*Older entries are in git history — the convention at the top of this file is
to keep the last three.*
