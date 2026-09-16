# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-16 — CLV-001 v1.0.2: book list frozen, capture path written and verified, nothing applied

**From:** Claude
**To:** Reed
**Date:** 2026-09-16

### First, a correction to what I gave you an hour ago

**The dry run said the scheduled-start mechanism did not exist. It does, and I
missed it.** I checked `fights.bell_at` (0 of 8,994) and `events` (a DATE, no
time) and stopped. I did not check for a start-time ledger, and there is one:
**`fight_start_estimates` + `v_fight_start_best`**, shipped in
`dur001_migration.sql`, collecting provider commence times since 2026-09-14 and
already resolving 16 future fights.

The 47 rows still fail — every settled card resolves to the event-date fallback,
because the ledger started after them. But "the field does not exist" implies
building something, and "the ledger started collecting two days ago" implies
waiting one card. The second is true, and it is a materially better position than
I reported. Correction is at the top of `DRY_RUN_2026-09-16.md`.

The same sweep found `v_odds_books_sportsbooks`, also from DUR-001, which already
encodes the sportsbook / aggregate / prediction-market split — and it turned out
to be the right answer to the book-list question below.

### 1. The eligible book list is frozen — Amendment 2 (a)

Ten sportsbooks: FanDuel, DraftKings, BetMGM, Caesars, BetRivers, BetWay, Unibet,
BetOnline.ag, Bovada, BetUS. v1.0.1 → v1.0.2, chain `c2e3f5aa…` → `06fa587a…`.

**Where the list came from matters more than its contents.** It is the membership
of `v_odds_books_sportsbooks` — a view written for the **totals** market *before
CLV-001 existed*, defined as every book whose name does not contain "consensus"
and is not Polymarket or Kalshi. It was not assembled by looking at which books
would suit a CLV number; it was already in the repo, under a rule anyone can
read. That is better provenance than anything I could have composed today.

Two facts make `motivated_by_observed_results: false` checkable rather than
merely asserted here: no CLV figure has ever been computed, and the dry run
establishes none is computable on the present record.

**Coverage was deliberately not a criterion.** Caesars, BetWay and Unibet have not
appeared in the feed since 2026-05-31 and are on the list anyway. Dropping a book
for thin coverage is a judgement about which prices count, made now, and it is
exactly what freezing forecloses. A book that never quotes never enters a
consensus, which costs nothing.

### 2. A second amendment part you did not ask for, and I think you need

**Amendment 2 (b): only `bell_at` and `provider_commence` count as a scheduled
start. The event-date fallback does not.**

`v_fight_start_best` *always* answers — it falls back to the event date at 18:00
UTC. Reading `start_at` without reading `start_basis` therefore hands every fight
in the database, back to 1994, a plausible-looking schedule. That is the same
defect shape as R-13: a populated placeholder sailing through a presence check,
and it would have decided staleness by a constant nobody chose for this purpose.
A fight resting on the fallback is unscored, which is what it is.

### 3. Capture: written, verified offline, unapplied

The moneyline path was throwing away everything the totals path keeps — same
loop, same payload, same provider metadata. That asymmetry is the whole reason
CLV-001's capture requirements read as unmet: **the mechanism was already running
in the next table over.** So the column names are copied from `prop_odds`, not
invented.

| §4 | requirement | column |
|---|---|---|
| 9 | provider market IDs | `source_event_id` |
| 7 | scheduled bout-start timing | `source_commence_at` (+ `is_live`) |
| 11 | provider AND retrieval timestamps | `provider_last_update` + `retrieved_at` |
| 10 | opponent identity at quote time | `opponent_fighter_id` |
| 8 | market suspension / takedown | `market_status` |
| 6 | provider and feed version | `feed_version` |
| 12 | immutable link to the source quote | `raw` |

`research/clv/proposed_2026-09-16_fight_odds_capture.sql` — additive only, every
column NULLable with no default, so all 110,032 existing rows are untouched and
NULL honestly means "predates the column". **Unapplied.** `build/fetch-odds.js`
strips these keys when the columns are absent, so an un-migrated database keeps
capturing exactly what it captured before and logs that the quotes it is taking
can never be scored.

**Two-sided near-bell capture.** `odds.yml` now wakes every 15 minutes;
`shouldCaptureNow()` gates each wake — 30 minutes near a real bell, hourly on a
card day, once daily otherwise. ~33 credits on a card day, ~286/month, inside the
500 free tier.

The 30 minutes is forced, not chosen: the frozen 45-minute staleness limit was
derived from a measured 30-minute interval plus grace, and **hourly capture
cannot satisfy it** — a bell at :59 leaves the freshest quote 59 minutes old and
the row goes unscored on a stale price. At 30 minutes the worst case is 29.

### How "verified" was interpreted, since you said verify before applying

The only thing checkable before the migration exists is the code that will fill
it. So I pulled the row builders out of the main loop, made them pure, and wrote
`build/test-fetch-odds.js` — **25 checks, no API key, no Supabase key, no
network, no credit, nothing written.** It replays the saved Odds API fixture and
asserts every §4 field lands on every row; that sides map by fighter name and not
the provider's home/away order; that a Draw outcome is dropped rather than
guessed onto a corner; that `is_live` is *null* and not *false* when there is no
commence time; that stripping leaves the legacy shape untouched; and — walking
every possible bell minute — that the freshest pre-bell quote is always inside 45
minutes.

**What that does not verify**, and must not be read as verifying: that the
provider keeps sending these fields, that the columns accept them, or that a real
card yields three two-sided books inside 45 minutes of a bell. Those need the
migration applied and one card captured.

### Publication is untouched

Amendment 2 removes a blocker from the **write** path. It does not touch the
**publish** path, and there is now a test that says so by name:
`test_freezing_the_list_did_not_open_publication`. The gate is still 0 of 100
observations and 0 of 20 events, still fail-closed, still blocked on
`sample_floor_met` and `interval_excludes_zero`.

Tests: 86 CLV Python, 94 repo Python, 25 Node. All green.

## Next action

**Reed:** apply `research/clv/proposed_2026-09-16_fight_odds_capture.sql` — that
one only. Everything downstream waits on real captured rows, and every card that
passes before it lands is permanently unscorable.

Then the sequence runs itself: the next card captures under the new path →
`--clv001 --report` shows real per-row reasons instead of one blanket one → if
three named books quote both corners inside the window, apply
`proposed_2026-09-16_clv001_columns.sql` and turn on `--write`.

I have not applied either migration, called The Odds API, or written to Supabase.

---

## 2026-09-16 — CLV-001 v1.0.1; settle_clv reconciled; the first dry run scores nothing

**From:** Claude
**To:** Reed
**Date:** 2026-09-16

### What changed

Your four instructions, in the order you gave them.

**1. Amendment 1 landed.** The de-vig direction correction is in force. It landed
as **DUR-001 Amendment 2** — that is where the defective sentence actually lives,
not in the CLV protocol as I first told you — and CLV-001 inherits it as its
**Amendment 1**, v1.0.0 → v1.0.1. History was not rewritten: the v1.0.0 bytes,
freeze instant and hash are preserved in `protocol.json` beside the chain
`ef912fce…` → `c2e3f5aa…`. No de-vigged probability changed, because the two
conventions are exact reparametrisations.

**2. The migration is written and unapplied.**
[`research/clv/proposed_2026-09-16_clv001_columns.sql`](../research/clv/proposed_2026-09-16_clv001_columns.sql).
Additive only — every statement is `ADD COLUMN IF NOT EXISTS` or
`CREATE INDEX IF NOT EXISTS`, so it is idempotent; no DROP, no DELETE, no
back-filling UPDATE, no trigger created or weakened, no existing row
reinterpreted. Nine new columns: the measure, its inputs, and enough provenance
to reconstruct the calculation from the raw quotes (the exact `fight_odds.id`
array, the consensus artifact as computed, and its sha256). Five `NOT VALID`
check constraints, so historical rows are never touched. `clv_pp` and `clv_beat`
keep their meaning and get a comment marking them legacy.

**3. `settle_clv.py` has two explicit modes.** `--clv001 --report` computes the
frozen measure and writes nothing. `--clv001 --write` writes only if every
precondition holds. Neither is the default and `--clv001` alone is an error —
nothing should report or write because a flag was forgotten. The legacy path is
untouched and its cron invocation (`--execute`) is unchanged.

`preflight()` treats an unevaluable condition as failed. It checks: the CLV-001
columns exist; `protocol.json` says frozen; its version matches the one compiled
into `scoring.py` **exactly**; the protocol markdown still hashes to the recorded
sha256; Q-02's named book list is present; and the unbackfillable capture
requirements are met. Miss one and no value is written for any row. There is no
override flag — a gate with an override is not a gate.

**4. Tripwires.** 41 new tests in `cfl_engine/clv/test_scoring.py`, 74 across the
CLV modules, 94 in `tests/`. All green. They pin each thing you named, and
several are built so a sloppier implementation would still pass the naive
version: the de-vig-per-book test uses a set whose *median pair is synthetic*, so
median-then-de-vig lands on a different number and the test catches the
reordering. Two epoch tests cover the dangerous case — an epoch stamp is always
"before the fight", so it passes every ordering rule; two real books plus one
epoch book must not reach three, and an epoch quote id must never reach the
provenance array. One test scores a hundred rows and asserts `protocol.json` is
byte-identical afterwards.

### The dry run, and it is not good news

[`research/clv/DRY_RUN_2026-09-16.md`](../research/clv/DRY_RUN_2026-09-16.md).
Read-only via Supabase MCP — there is no service key in this container, so the
script could not authenticate and the counts were re-derived query by query in
its check order.

**0 scored, 47 unscored, all for the same reason.** Write mode refuses at
preflight on four conditions. Every row then stops at `no_scheduled_start`:
`fights.bell_at` is populated on **0 of 8,994** fights and `events` stores a date
with no time, so Q-01's reference instant does not exist. I did not substitute
one. Midnight, or the card's first bout, or "that evening" would each produce a
number under a definition chosen after the fact by whoever implemented it.

**Fixing `bell_at` alone would not help.** The freshest two-sided sportsbook
quote on any past card was captured **157.8 hours — 6.6 days — before it**,
against a 45-minute staleness limit set from measured cadence before any result
existed. All 47 rows would move from `no_scheduled_start` to `stale_close`.

`is_closer` is flagged on exactly two books and CLV-001 excludes both: BFO
Consensus (15,362 rows, an aggregate, and **every row epoch-stamped**) and
Polymarket (a prediction market, Q-03). The seven real sportsbooks in
`fight_odds` are never flagged at all.

### The thing I need you to rule on

**Q-02 froze the rule and not the list.** It says *"fixed **NAMED** sportsbook
list frozen at protocol freeze"*. `protocol.json` records the resolution and no
list. `settle_clv.py` refuses rather than deriving one from whichever books are
in the data — that derivation is the thing Q-02 exists to prevent.

Proposal, deliberately containing **no list**, is at
[`AMENDMENT_PROPOSAL_2026-09-16_eligible_books.md`](../research/clv/AMENDMENT_PROPOSAL_2026-09-16_eligible_books.md).
It sets out what is in `odds_books` and leaves the choice to you.

**Now is the safest moment this will ever be.** The hazard is picking books after
seeing which ones flatter the number. No CLV number exists, and the dry run
establishes none is computable on the current record — so a list named today
provably cannot be result-motivated. That stops being verifiable the moment
near-bell capture starts producing data.

### One place I departed from an approved plan

The approved proposal's step 4 said to delete the `devig.py` note and
`test_the_stated_direction_is_the_wrong_one`. I rewrote both instead. The note
now records the correction rather than the defect, and the test is
`test_the_sum_increases_in_k_as_amended`, asserting the property the amended text
now claims. Deleting a passing assertion about the direction would leave the
freshly-corrected claim resting on trust again — which is exactly how it went
wrong the first time. The departure is recorded at the top of the proposal file.

### What did not happen

No migration applied. No Supabase write of any kind. No CLV statistic computed,
and none would have printed if one were — the report prints counts, reasons and
provenance, never a headline. The publication gate is untouched at 0 of 100 and
0 of 20.

## Next action

**Reed:** two calls, in this order.

1. **Name the eligible sportsbooks**, or say you want the list deferred. Nothing
   scores until this exists, and this is the cleanest moment to fix it.
2. **Decide whether to change the capture path.** Two-sided near-bell quotes from
   named sportsbooks (§4 item 2), a scheduled bout-start instant (§4 item 7) and
   provider market IDs (§4 item 9). None can be backfilled, and without item 2 in
   particular the measure cannot produce an observation no matter what else is
   fixed. This is a product-priority call, not a methodological one — the honest
   framing is that CLV is currently unmeasurable and the fix is in the scraper,
   not the protocol.

The migration stays unapplied until there is something to write into it.

---

## 2026-09-16 — CLV-001 FROZEN v1.0.0; one amendment proposed before settle_clv

**From:** Claude
**To:** Reed
**Date:** 2026-09-16

### What changed

Your L3 approvals are recorded and **CLV-001 is frozen at v1.0.0**
(2026-09-16T10:30:00Z, sha256 `ef912fce…`). Q-14 recorded first, `CLAUDE.md`
amended with your exact replacement rule, then Q-05/06/07/08/11/13 resolved.

**Freezing did not open publication, and I had to restructure the gate to keep
it that way.** The freeze procedure literally said *"publication_gate.
publication_allowed becomes true"* — following it would have published on a
sample of zero, against your explicit instruction. The gate is now the AND of
three conditions:

| condition | state |
|---|---|
| `protocol_frozen` | **true** |
| `sample_floor_met` | **false** — 0 of 100 observations, 0 of 20 events |
| `interval_excludes_zero` | **false** — unevaluable, and fail-closed |

Three of the original gate tests *skip* once frozen — they policed the run-up to
a freeze. That meant freezing would silently remove every check on publication
at the exact moment publication becomes conceivable. Eight new tests cover the
frozen state; flipping `publication_allowed` to true now fails with
`CLV publication is ALLOWED at 0/100 observations and 0/20 events`.

### The thing I need you to rule on

**Implementing the power de-vig found a mathematical error in the protocol you
froze this morning.** §6 says *"the sum is strictly decreasing in k"*. For the
formula it specifies, `q^(1/k)`, the sum is strictly **increasing** in k. It
decreases only under the other convention, `q^k`.

**No number changes.** The two are exact reparametrisations — the `q^k` root is
the reciprocal — so the fair probabilities are bit-identical, and both roots sit
inside the stated `[0.5, 5.0]` bracket. Verified on three pairs.

It still matters: an implementer trusting the stated direction inverts their sign
test and fails to converge. And it is a false statement inside a document whose
value is that you do not have to re-derive its claims.

Proposal at
[`research/clv/AMENDMENT_PROPOSAL_2026-09-16_devig_direction.md`](../research/clv/AMENDMENT_PROPOSAL_2026-09-16_devig_direction.md).

**I did not quietly fix it.** The protocol was frozen hours earlier, and
correcting a frozen document silently — even for something numerically inert —
is the exact habit the freeze exists to prevent. Afterwards it would be
indistinguishable from quietly correcting something that *did* change a number.

The implementation does not depend on the claim either way: `_bisect` reads the
sign at both bracket ends. Two tests pin the equivalence, and one is written to
start **failing** if the protocol's claim ever becomes true, so the note cannot
outlive its cause.

### What shipped

`cfl_engine/clv/devig.py` — the frozen arithmetic as pure functions: power
de-vig (primary), proportional and Shin (frozen sensitivities), the ≥3-book
consensus with per-book de-vig *then* median, and `CLV_return`. 33 tests, no DB.

One test earned its place immediately: **de-vig-then-median and
median-then-de-vig can coincide**, when one book is median on both sides. My
first version of that test asserted they always differ and failed. They differ
only when the median pair is *synthetic* — a pair no book quoted — which is the
situation Q-02's ordering exists to rule out. Both directions are now pinned.

### What I did NOT do

**`settle_clv.py` is untouched.** Two reasons, and I want you to pick:

1. `model_edges` has **no column** for `clv_return`, the closing fair
   probability, the book count, or an unscored reason. Writing the frozen
   measure needs a migration, and I do not apply migrations.
2. I cannot run it — no service key here — and it is a live daily writer.
   Shipping an unverified rewrite of it blind is how the 1970-timestamp class of
   defect gets introduced rather than found.

### Next action

**Reed: approve or reject the de-vig amendment, and say how you want
`settle_clv.py` reconciled** — a proposed-unapplied migration plus a
column-detecting script that reports `CLV_return` until the columns exist, or
wait until you can run it yourself.

Publication stays shut either way. 0 of 100.

---

*Older entries (CLV-001 v0.3.0-draft, the revision against the review, the
original draft, and the coordination-layer setup) are in git history — the
convention at the top of this file is to keep the last three.*
