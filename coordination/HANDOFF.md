# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-16 — CLV-001 v1.0.9: Amendment 6, provenance enforced per row

**From:** Claude
**To:** Reed → ChatGPT review
**Date:** 2026-09-16

**No migration applied. No production write. No paid API call. No publication.**
Four migrations now, all proposed and unapplied.

**Version bumped to v1.0.9**, hash `f8c6e68a…`, chained from `a009bb17…`. The
measurement did not change — same cutoffs, same de-vig, same 45-minute limit,
same books, same gate. What changed is that rules already written down are
enforced where they apply. It is recorded as an amendment anyway, because it
changes which rows can score and because §5 of a frozen document had to be
corrected. `motivated_by_observed_results: false`, and trivially so: nothing has
been scored.

### 1. Eligibility is a property of the ROW, not of the schema

The settler checked that the CLV-001 **columns existed** and then scored on
whatever `fight_odds` held. Those are different tests, and the gap opens the day
the capture migration lands: a June quote with a credible `captured_at` — R-13
passes it, live capture began 2026-05-22 — and NULL in every new column becomes
scorable.

A quote is now eligible only if **that quote** carries `source_event_id`,
`feed_version`, `opponent_fighter_id`, `provider_last_update`, `retrieved_at`,
`market_status` and `raw`. Present means populated: an empty string and an empty
jsonb record nothing and do not count. The settler selects all of them, and a
test pins the select list against the required set so the check can never pass on
what the query asked for rather than on what the row holds.

Pre-migration rows stay permanently unscorable — a coverage fact under R-05.

### 2. R-07 is applied per quote, as written

`forecast_locked_at < close_quoted_at`, strictly. The implementation checked
`published_at < cutoff`.

**A forecast locked at 9:28 could be scored against a 9:20 book quote, because
the cutoff was 9:30.** That price was on the screen before the forecast existed.
Reed's case is now a test, along with the assertion that the check it replaced
would have passed exactly this arrangement.

`closing_pairs` takes the lock as a required argument with **no default** — a
default of None would be a silent bypass of R-07, the same shape of hole
Amendment 5.1 closed in `score_row`. Passing None drops every quote.

### 3. The lock comes from an immutable record

R-07: "A forecast whose timestamp cannot be established from an immutable record
is not eligible." `model_edges` has no append-only trigger.

**No new ledger was needed.** `pre_fight_snapshots` already is one — unique on
`fight_id`, UPDATE and DELETE rejected by trigger for every role including
`service_role` — and it carries `edge_side`, `edge_bet_fighter_id` and
`edge_odds_at_publish`, so it matches **this edge** rather than merely its fight.
All three must agree. It predates CLV-001, which is what makes it good evidence.

The effective lock is the **later** of the immutable instant and `published_at`.
Later is strictly harder, so an edited `published_at` can only ever cost
observations — never admit a quote the immutable record would have excluded.
There is a test for that direction specifically.

### 4. The posted price must name and prove its source quote

§4 item 12. `clv_publish_quote_id` records the exact `fight_odds` row, and the
scorer **verifies** it: same American price, the bet fighter, the opponent
(Q-10), the provider market id (R-06), a credible instant (R-13), full §4
provenance. The closing quotes must name the same market and the same opponent —
a repost or a rematch is a different market, not a later quote on the same one.

Historical edges have no link and are not given one. Searching for "the row whose
price matches" manufactures the record the rule exists to require.

### 5. The cutoff is stored, and hashed

`clv_cutoff_at` is added and required on every scored row. For bouts 2..N the
cutoff coincides with `clv_window_opened_at` so it looked recoverable; for **bout
1** — the only bout this version can currently score — nothing held it.

The cutoff, the forecast lock and the publish quote id go **inside the hashed
artifact**. A consensus is a set of prices *selected by* a cutoff: hashing the
prices alone means the same books at the same median hash identically whether
they were selected against a 22:00 cutoff or a 23:00 one. There is a test that
constructs exactly that pair.

### 6. Bout 1's cutoff comes from bout 1's own schedule

`v_clv_close_reference` resolved the card's scheduled start from the latest
`odds_api_commence` observation belonging to **any** fight on the event. The
provider publishes a commence time per market and the tail of a card is
re-estimated as the night is rebuilt, so the newest observation usually belongs
to another fight.

**Measured on a real Postgres, not asserted:** with bout 1 at 22:00 and bout 12
at 04:30, the old view gave bout 1 a cutoff of **04:30** — six and a half hours
late, which would have made every in-play price on the card eligible as its
close. It now resolves the bout-1 fight's own latest observation within the
latest complete card snapshot, and the view reports `card_start_fight_id` so a
reader can check whose schedule it is.

I ran the regression against the pre-Amendment-6 view to confirm it fails there:
`'12' != '1'`.

### 7. The raw quote evidence is made durable

R-01 requires the raw quote store to reject UPDATE and DELETE by trigger for
every role including `service_role`. `fight_odds` did not — the legacy
`is_closer` promotion UPDATEs it after every card — so `clv_source_quote_ids`
pointed at rows whose price, timestamp, identity or provenance could be rewritten
afterwards, with the consensus hash still matching, because the hash covers the
artifact rather than the rows it names.

New migration, and **it is the one that is not additive-only**:
`proposed_2026-09-16_fight_odds_immutability.sql`. DELETE and TRUNCATE refused
outright; UPDATE refused for anything but `is_opener` / `is_closer`. Whitelist by
construction — it compares `to_jsonb(old)` and `to_jsonb(new)` minus those keys,
so a column added later is protected the moment it exists (there is a test that
adds one and checks).

The legacy promotion still works, verified against a live trigger. A Node test
pins that `fetch-odds.js` writes no other column, so a future edit fails the
suite rather than the cron at 23:00 UTC on a card night.

### 8. The staleness clock is named, and left alone

The frozen 45 minutes came from CFL's own observation cadence, so it stays
measured from `captured_at`. `provider_last_update` is required provenance and
explicitly **not** the clock. Recorded as `STALENESS_MEASURED_FROM`, documented
on both columns, and tested in both directions: a nine-hour-old book move does
not make a fresh capture stale, and a fresh book move does not rescue a stale
capture.

### 9. Stale live documentation

- **§5 no longer says freezing opens the gate.** It listed
  "`publication_allowed` becomes `true`" among the things that happen at freeze —
  the one sentence in the document that could be read as authorising a number to
  appear. Replaced with the actual rule, as a dated correction rather than a
  silent rewrite. (`protocol.json`'s `freeze_procedure` was already correct; the
  markdown was the stale one.)
- **Capture-column comments** now name v1.0.8-onward's two cutoff bases instead
  of the Amendment 2 (b) era "bell_at and provider_commence" rule.
- **Scorer text** no longer offers "or a confirmed bell" as a cutoff.
- Superseded amendment blocks are untouched. A test strips the blockquotes and
  asserts the **live** text only, so history stays auditable.

### New: behavioural SQL tests

`tests/test_sql_behaviour.py` runs the DDL against a throwaway Postgres cluster
(`initdb` into a temp dir, unix socket, `listen_addresses` empty, destroyed in
teardown). It **skips** where no local Postgres exists, so it costs nothing in CI
or on a laptop. `SUPABASE_DB_URL` is never read and no production database is
touched.

It proves what static analysis cannot: all four migrations apply in the
documented order, apply twice unchanged, the bout-1 schedule resolves correctly,
the immutability trigger allows exactly the right UPDATE and refuses the rest,
and the `model_edges` completeness constraint actually rejects a row missing its
cutoff.

### Files changed

| file | what |
|---|---|
| `cfl_engine/clv/scoring.py` | row-level provenance; per-quote R-07; `forecast_lock`; `verify_publish_quote`; cutoff stored and hashed; v1.0.9 |
| `cfl_engine/settle_clv.py` | provenance columns fetched; snapshots and publish quotes resolved; `clv_cutoff_at` written; new precondition |
| `cfl_engine/clv/test_scoring.py` | +39 tests across the six new rules |
| `research/clv/proposed_2026-09-16_fight_odds_immutability.sql` | **new** — R-01 triggers, not additive-only |
| `research/clv/proposed_2026-09-16_clv001_columns.sql` | `clv_cutoff_at`, `clv_publish_quote_id`, 4 reasons, 2 constraints |
| `research/clv/proposed_2026-09-16_event_flow.sql` | bout-1 schedule resolution; `card_start_fight_id` |
| `research/clv/proposed_2026-09-16_fight_odds_capture.sql` | comments corrected; staleness clock documented |
| `research/clv/CLV_MEASUREMENT_PROTOCOL.md` | Amendment 6; §5 corrected; v1.0.9 |
| `research/clv/protocol.json` | amendment 6 + hash chain; 5 new sections |
| `tests/test_sql_behaviour.py` | **new** — 17 behavioural tests |
| `tests/test_clv_protocol.py` | +8 documentation regressions |
| `tests/test_migrations_idempotent.py` | +12 tests; `__main__` block moved to the end |
| `build/test-fetch-odds.js` | +2 tests pinning the UPDATE whitelist |
| `coordination/STATE.md`, `coordination/HANDOFF.md` | this |

### Tests

| suite | result |
|---|---|
| `tests/` (repo) | **149 passed**, 3 skipped |
| `cfl_engine/clv/test_scoring.py` + `test_devig.py` | **161 passed** |
| `build/test-fetch-odds.js` (Node) | **66 passed** |

376 total, all green. The 3 skips are the frozen-protocol fixtures that skip by
design. Hash chain verified across 9 amendments; publication gate confirmed shut
at 0 of 100 / 0 of 20.

**One pre-existing defect found and fixed in passing.**
`tests/test_migrations_idempotent.py` had its `if __name__ == "__main__"` block
in the middle of the file, so running it directly collected only the first three
classes and silently skipped the rest. Moved to the end; direct invocation now
collects all 31.

### Preserved, as instructed

The closing-price proxy methodology and naming; the 45-minute freshness rule;
≥3 eligible two-sided books; power de-vig per book then median; the ten named
books; append-only provenance; the 500-credit ceiling; the fail-closed
publication gate; no paid services; no production migrations.

### Remaining blockers

1. **Exact bout completions have no source.** Unchanged and still binding.
2. **Running order is not captured.** Free to fix; nothing writes the ledger yet.
3. **Nothing publishes `clv_publish_quote_id`.** New, and it is a real one: the
   edge publisher lives outside this repo (`cfl-snapshotter` / the engine), and
   until it records which `fight_odds` row a posted price came from, **no future
   edge can score either**. This is not a migration — it is a change to whatever
   writes `model_edges`. Flagged rather than guessed at.
4. **Nothing is applied.**

### New L3 decisions required

**Two, both small and both stated rather than assumed:**

1. **The version bump itself.** Items 1–8 are conformance with rules already
   frozen, but they change which rows can score, and item 9 edits a frozen
   document. I recorded it as Amendment 6 / v1.0.9 rather than as a silent fix.
   If you would rather it were not a version bump, say so and it reverts to
   v1.0.8 with the §5 correction carried as an erratum.
2. **`proposed_2026-09-16_fight_odds_immutability.sql` is not additive.** It
   constrains an existing writer. Before it is applied, any writer to
   `fight_odds` outside this repo needs inventorying — inside this repo there is
   exactly one, and it is covered.

Still not required: no spend, no paid tier, no publication.

## Next action

**ChatGPT:** review Amendment 6 — in particular (c), whether
`pre_fight_snapshots` is the right immutable lock and whether matching on side +
bet fighter + price is a tight enough identification of the edge; and (g),
whether the `is_opener` / `is_closer` whitelist is the right cut.

**Reed:** the two L3 items above. Then apply in order —
`..._fight_odds_capture.sql`, `..._fight_odds_immutability.sql`,
`..._event_flow.sql`, `..._clv001_columns.sql`.

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

*Older entries are in git history — the convention at the top of this file is
to keep the last three.*
