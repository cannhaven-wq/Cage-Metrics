# Proof Center — build notes and handoff

Branch: `product/proof-center`. **Not merged, not deployed, not indexed.**

---

## The plain-English version (per CLAUDE.md, this comes first)

**What changes.** A new page, `proof.html`, that lists every prediction we have
on record — when we posted it, what percentage we gave it, what the price was,
what happened, and what a flat $100 bet came to. It can be filtered and
searched. Picks we posted before a fight and fights we re-ran through history
afterwards sit in two separate boxes that are never added together.

**Why it matters.** `track-record.html` is a summary: it tells a reader what our
numbers are. It does not let a sceptic inspect the underlying rows. A bettor who
has been burned by touts does not want a summary, they want the receipts. This
is the receipts.

**What the user sees differently.** Seven questions answered at the top in one
line each, then the record, then a market-price test that says *"still
collecting, 46 of 100"* instead of a number, then the whole archive with losses
sitting in the same list as wins.

---

## 1. What was built

| Piece | File | What it does |
|---|---|---|
| The page | `proof.html` | The Proof Center surface. Standalone HTML at the repo root, same as every other page. |
| The rulebook | `proof-gates.js` | Single source of truth for record separation, publication gates and flat-stake money math. Browser `<script>` **and** `require()` in Node, same dual-export pattern as `edges.js`. |
| The tripwire | `tests/proof-gates.test.js` | 33 assertions that the two rules hold. `node tests/proof-gates.test.js`, no framework, no dependencies, not wired to CI. |
| One cross-link | `track-record.html` | One line under the pledge pointing at the new page. Nothing else on that page was touched. |

**No database change. No SQL migration. No new view.** The page reads the
existing `v_model_picks_graded`, `v_model_edges_graded`, `v_pre_fight_graded`
and `events` — all of which already grant `SELECT` to `anon, authenticated`.
Nothing needs applying before this can be looked at.

### Page sections, in order

1. **Header** — what the page is, and that losses are shown at the same size.
2. **Seven questions** — the brief's seven questions, each with a one-line
   answer computed from the data, each linking to the section that proves it.
3. **Two records. Never added together.** — live and replay side by side, each
   with *what it is / what it proves / what it can't tell you*, plus a note that
   the separation is enforced in code and has a test.
4. **The live record** — KPI strip (record, hit rate, flat-stake P&L, cards
   covered), every tile carrying a status chip. Below it, a panel on what the
   dollar figure is and, louder, what it is not.
5. **The price test** — gated. See §4.
6. **The archive** — every row, filterable by record / feed / result, searchable
   by fighter, card or date. Newest first, paged 50 at a time.
7. **How we measure ourselves, in plain English** — six steps, then a panel
   headed *"What this page will not tell you"*.
8. **Check it yourself** — seven claims, what backs each, and a verdict. Three
   verdicts are recomputed in the browser on every load, including a row-by-row
   crosscheck of every live pick against the append-only pre-fight snapshot.
9. **What the labels mean** — the five status chips defined.

---

## 2. Routes and components

- **Route:** `/proof.html` (`noindex, nofollow` — deliberately; see §6).
- **Global namespace:** `window.cflProof`, from `proof-gates.js`.
  - `RECORD` / `STATUS` / `GATES`
  - `recordKind(row)`, `splitByRecord(rows)`, `assertOneRecord(rows, expected)`
  - `evaluateGate(gateId, have)`, `statusCopy(status)`
  - `winProfit(odds, stake)`, `flatStakeLedger(rows, opts)`, `straightRecord(rows, opts)`
  - `clvPairCount(rows)`, `timestampAudit(rows)`, `crossCheckSnapshots(picks, snapshots)`
- **Not touched:** `edges.js`, `fight-insights.js`, `_shared.js`, `_auth.js`,
  `_shared.css`, `cfl_engine/**`, `research/**`, every frozen file in
  `CFL_RESEARCH_STATE.md`, every `*.sql` migration.

### Screenshots

Rendered headless at 1360×1000 and 390×844 against the real rows (see §3):

| File | What it shows |
|---|---|
| `/tmp/claude-0/proof-desktop.png` | Full page, desktop |
| `/tmp/claude-0/proof-mobile.png` | Full page, 390px |
| `/tmp/claude-0/top.png` | Header + seven questions + the two records |
| `/tmp/claude-0/darch2.png` | The archive, desktop |
| `/tmp/claude-0/losses.png` | Money feed filtered to losses only |
| `/tmp/claude-0/replay.png` | Replay tab with its simulated banner |
| `/tmp/claude-0/maudit.png` | The audit table stacked on a phone |

They live in the session scratchpad, not the repo — regenerate them by serving
the repo and pointing a browser at `proof.html`.

---

## 3. Real vs mocked

**Everything the page renders is real.** It reads the live database through the
same publishable anon key the rest of the site uses. There is no synthetic data
in `proof.html`, in `proof-gates.js`, or anywhere in the repo.

As of 2026-09-16 the live record reads:

| | |
|---|---|
| live calls on record | 151, across 11 cards, since 2026-07-18 |
| settled | 106 — 60 right, 46 wrong (57%) |
| live money bets | 61, of which 41 settled — 28 won, 13 lost |
| flat $100 running total | −$120 |
| price pairs for the market test | 46 |
| picks covered by the frozen snapshot | 67, all 67 still matching exactly |
| engine builds in the record | `engine_v1`, `engine_v2` |

Those numbers move with every card. They are **not** written into any file —
the page recomputes them on load, which is the point.

Two things are mocked, both outside the repo and both only to get a browser
picture in this environment (the egress policy blocks `cdn.jsdelivr.net` and
the Supabase REST host, so a real browser load is impossible here):

- `/tmp/claude-0/preview/fixture.js` — the 151 live picks, 61 live edges and 5
  backtest picks, **exported verbatim from the live database** by read-only
  `SELECT`. Real rows, just served from disk.
- `/tmp/claude-0/preview/stub.js` — a fake Supabase client that serves them.

Neither is committed. Neither is referenced by `proof.html`.

**The `published_at` trap, handled.** Every `backtest` row carries the same
`published_at` — `2026-08-18 22:42:57Z`, the moment the backfill ran. That is
not a prediction time. The archive therefore prints **"re-run, not posted"** for
replay rows and never renders their timestamp. This is the single most
load-bearing honesty decision in the build.

---

## 4. What stays hidden because a gate has not passed

### The market-price test — **shut**

Currently **46 of 100**. The page shows the rule, the progress bar and the
count. It shows **no number, no direction, no hint**, and there is a test
asserting the pending copy contains none of *beat / ahead / positive / negative
/ profit / edge / winning*.

The floor of 100 is not invented here. It is the stance already shipped on
`track-record.html`: *"these numbers go up here once 100+ locked picks have both
a posted price and a closing price on record."* `GATES.clv.source` cites it
verbatim so a reviewer can trace it, and `tests/proof-gates.test.js` pins the
threshold — move it and two tests fail.

**Even when the gate opens, this page still prints nothing.** It says the rule
has been met and that switching the measurement on is a separate reviewed
change. Wiring an actual CLV figure is not in this branch and should not be
done without the owner.

### The money figure — **shown, labelled "too early"**

41 settled bets against a floor of 100. The running total is a fact about the
record and answers one of the seven questions, so it is shown — but tagged
`TOO EARLY`, never described as a rate to expect, and never put above a bet CTA.
The page contains no CTA at all.

### Not built, because it would need a definition this branch may not touch

- Any late pre-fight price proxy. `model_edges` carries `closing_odds_pm` /
  `clv_pp_pm` and I did not guess at what they mean. Defining or surfacing them
  is a CLV-methodology decision, which is explicitly out of scope.
- Any per-tier, per-weight-class or per-engine-build breakout. Each is a slice,
  and slicing a 106-fight record produces cells small enough to mislead. Worth
  revisiting once the sample supports it.

---

## 5. Tests run

```
$ node tests/proof-gates.test.js
  33 passed — replay/live separation and publication gating hold.
```

Covering: unrecognised `source` never counts as live; `assertOneRecord` throws
on a mixed set; the ledger and the record summariser both refuse a mixed set;
`clvPairCount` ignores replay rows carrying both prices; the CLV gate opens at
exactly 100 and not at 99; the pending copy leaks no direction; an unknown gate
fails closed; `NaN` / `Infinity` / negative / `null` / a string all resolve to
zero rather than to a pass; every defined gate is live-only and carries a source
citation; pending is never counted as a loss; a settled row with no price is
reported rather than dropped; an empty ledger reports "no rate" instead of zero;
`timestampAudit` separates same-day posts from genuine day-before ones and flags
late and undated rows; `crossCheckSnapshots` catches a changed fighter and a
changed probability, tolerates float noise, treats an uncovered fight as
uncovered rather than as a pass, and ignores replay rows.

`tests/test_research_state.py` could not be run here — no `pytest` in this
container. It guards frozen-file hashes and **no frozen file was touched**;
`git diff --stat` against `main` confirms the only changed tracked file is
`track-record.html`, +1 line.

**The tests were verified to bite.** Lowering `GATES.clv.minObservations` from
100 to 1 fails 2 tests; restoring it passes 27. (Same check the repo already
does for `tests/test_research_state.py`.)

Also run, in a headless browser against the real rows: full render at 1360px and
390px, every filter combination, the search box, the replay tab, and a
horizontal-overflow check (`scrollWidth === innerWidth` at 390px). No page
errors. The only console errors are the blocked CDN and font requests, which are
this environment's egress policy, not the page.

**Not run:** nothing. There is no lint and no test suite in this repo, and per
`CLAUDE.md` I did not add one — `tests/proof-gates.test.js` is a bare `node`
script, not a framework, and nothing in CI invokes it.

---

## 5b. One claim I got wrong, and fixed

The first cut of the audit table said *"A posted pick can never be edited or
deleted — append-only, enforced by the database"*, citing
`pre_fight_snapshots_migration.sql`.

**That was false for the tables this page actually reads.** Checked against
`pg_trigger`: only `pre_fight_snapshots` and `prop_model_locks` carry
append-only triggers. `model_picks` and `model_edges` carry none — and
`model_edges` is *deliberately* updated after a card by `settle_clv.py` to fill
in the closing price.

An overstated trust claim on the trust page is the worst possible bug here, so
it is replaced by two rows that are both true and, together, stronger:

- **"The picks still match a copy nobody can edit"** — a real crosscheck,
  computed in the browser, of every live pick against `v_pre_fight_graded`
  (which *is* trigger-sealed). Currently **67 of 67 match exactly**, on both the
  fighter and the percentage. Picks from before the freeze started running in
  August 2026 are reported as uncovered, not as passing.
- **"The tables behind this page are not themselves locked"** — says the
  unflattering thing outright, explains that the closing-price update is
  settlement rather than revision, and points at the frozen copy as what makes
  it checkable.

Worth a reviewer's attention: this is the pattern the page is supposed to
enforce, and it only got caught because the claim was checked against the
database instead of against the migration file that sounded right.

---

## 6. Decisions for the owner

**No L3.** Nothing in this branch creates or increases a monetary cost. No paid
service is touched, no API is called, no new scheduled job exists, and the page
adds no query the site does not already make.

Four calls that are Reed's, not mine:

1. **Nav placement.** `proof.html` is reachable only from the one link added to
   `track-record.html`. Putting it in the nav changes every page on the site and
   is a publishing decision.
2. **`noindex`.** The page ships `noindex, nofollow` and is absent from
   `sitemap.xml`. That is deliberate for an unreviewed branch. Flip both when it
   is approved.
3. **Does this replace `track-record.html`, or sit beside it?** Right now they
   overlap: both show the live record. Beside it is defensible — one summarises,
   one lets you inspect — but two proof pages is a thing to decide, not drift
   into.
4. **The 100-pick floor for the money figure.** I reused the sample floor
   already written in the `track-record.html` honesty box rather than invent
   one. If you want a different floor for money than for the market test, say so
   **now**, while the number underneath is not yet interesting — changing it
   later is the move this whole setup exists to prevent.

---

## 7. Files changed

```
new    proof.html                    the page
new    proof-gates.js                separation + gate rules, browser & node
new    tests/proof-gates.test.js     33 assertions
new    PROOF_CENTER.md               this file
edit   track-record.html             +1 line, a link to proof.html
```

Nothing else. No frozen file, no migration, no engine file, no shared script, no
stylesheet.

---

## 8. Exact next action for ChatGPT review

Review in this order, because the later items only matter if the earlier ones
hold:

1. **`proof-gates.js` first, on its own.** It is 300 lines and it is where every
   claim on the page is enforced. Specifically: does `assertOneRecord` actually
   make a blended total impossible, or only unlikely? Does `evaluateGate` fail
   closed on every path? Is `flatStakeLedger` counting anything as a win that
   isn't one?
2. **`tests/proof-gates.test.js` against it.** Is there a way to publish a gated
   number that no test would catch?
3. **Then the copy in `proof.html`**, against `COPY_STYLE.md`. Flag any sentence
   that would embarrass us if the next card went 0–12, any un-translated stats
   term, and any number presented without its status chip.
4. **Then the honesty of the audit table**, and §5b in particular. Seven claims;
   three verdicts are computed live. Are the four static ones overstated? Apply
   the same test I had to apply to myself: for each row, what would have to be
   true in the database for it to be false, and has anyone actually looked?
5. **Do not merge, deploy, index, or add to the nav** as part of the review.

---

## Revision 2 — the four required corrections (2026-09-16)

Architecture approved; these are the trust-critical fixes applied on top. Still
not merged, not deployed, not indexed, not in the nav.

### 1. The market-price gate now defers to CLV-001

The previous cut counted legacy `closing_odds` pairs and rendered **"46 of
100"** as progress. That was Proof Center inventing its own CLV rule, which it
has no standing to do.

- `GATES.clv` is now a **deferred** gate: `deferred: true`, `authority:
  'CLV-001'`, **no `minObservations`, no `unit`, nothing countable**.
- `evaluateGate` ignores `have` entirely for a deferred gate. No number reaches
  it, and there is a test over `0 … Number.MAX_SAFE_INTEGER` and `Infinity`
  confirming none of them opens it.
- **`clvPairCount()` was deleted, not left unused.** A helper that computes the
  wrong thing is a helper someone re-wires.
- The panel renders **no figure, no count and no progress bar** — a test asserts
  no `.prog` element exists inside `#marketGate`.
- The shipped sentence is the agreed one, verbatim: *"Prospective market-price
  validation is collecting. No CLV figure is publication-approved yet."*
- **Integration path, without implementing any CLV rule.** `evaluateGate('clv',
  null, authority)` opens only when `authority.publication_approved === true`
  **and** `authority.authority === 'CLV-001'`. Ten malformed authority objects
  are tested and all fail closed. Even when approved, `showValue` stays `false`
  — surfacing a figure is a separate reviewed change, not something this branch
  can switch on.

CLV-001 does not exist in this repository yet (`grep` finds nothing, and
`research/registry.json` holds only DUR-001, DUR-002 and PROP-0001), so today the
gate is simply shut with no authority available.

### 2. False immutability claims removed

Every absolute claim is gone — *"rows are locked"*, *"can never be edited
afterwards"*, *"the row is never edited again"*, *"once written, a pick cannot be
changed or deleted"*. The page now tells the true version:

- the working tables are ordinary tables and we could edit them;
- for covered cards a copy is frozen into `pre_fight_snapshots`, which **is**
  trigger-sealed against UPDATE and DELETE for every role;
- this page re-compares the working row to that sealed copy in front of the
  reader — **67 of 67 still match** on fighter and percentage;
- the **84 live calls with no sealed copy are reported as uncovered**, never as
  passing. The audit verdict reads `67 of 67 still match · 84 not covered`.

The existing disclosure row was not weakened; the rest of the page was brought
into line with it.

### 3. Timing is graded, not asserted

`timestampAudit()` is replaced by `timingEvidence()`, which sorts every live call
into exactly one of four levels and never rounds upward:

| Grade | Count | What it means |
|---|---|---|
| Sealed before the card | **54** | Sealed copy exists, still matches, and was taken on an **earlier calendar day** than the card |
| Dated before the card | **70** | Posted on an earlier day, on our own timestamp |
| Same-day timestamp | **27** | Timestamped on the card's own day — cannot place it before the first bell |
| Timing unverified | **0** | No usable timestamp, or one dated after the card |

Verified against SQL: `54 / 70 / 27 / 0`, summing to 151.

The old answer *"Yes — all 151 timestamped, none after its card"* is gone. The
page now reads *"54 sealed, 70 dated ahead — 27 only same-day"*, there is a
dedicated `#timing` section, and **every archive row carries its own grade**.

**On reviewing `pre_fight_snapshots` itself, as instructed:** a snapshot is
*not* automatically timing evidence. Checked against the table — **13 of its 67
rows were taken on the card's own day.** Those are graded down to `same-day`
like any other row rather than riding the sealed label, and an audit row states
outright that *"a sealed copy is not by itself proof of timing"*. Two tests pin
this: a same-day seal must never produce the sealed grade, and a same-day
timestamp must never produce a verified verdict at any hour of the day.

If an authoritative per-fight cutoff ever arrives, `timingEvidence` is where
same-day rows get upgraded. Nothing invents one now.

### 4. "CFL cannot change the rules" replaced

The seven-questions answer now reads **"Rules can change — but only versioned
and dated, never backwards"**, with a matching step in the method section and an
audit row: changes are versioned and dated, results stay tied to the rules they
were scored under, nothing already graded is re-graded under a friendlier rule,
and a threshold is never moved after anyone has seen what it gates.

### 5. Scope tightened

*"every prediction in our database"* is gone. The page is now *"the main
engine's fight calls"*, with a scope panel in the header naming the four things
it reads and stating that the fight-duration and prop models run under their own
protocols with their own records, none of which appear here or are counted in
anything above. An audit row repeats it: *"This page does not speak for the rest
of the lab."*

### Preserved, as required

Live/replay separation, losses at equal prominence, replay rows never receiving a
publication timestamp, flat-$100 P&L, fail-closed load, no CTA, `noindex`,
read-only access, no model/research/CLV/ingestion/odds-capture change, no paid
services. All still covered by tests.

---

## Revision 2 — tests

```
$ node tests/proof-gates.test.js
  36 passed — replay/live separation and publication gating hold.

$ node tests/proof-copy.test.js
  17 passed — shipped copy matches what the data actually supports.
```

`tests/proof-copy.test.js` is new. It reads the shipped strings from
`proof.html` **and** `proof-gates.js` (both hold user-facing copy), strips the
stylesheet and all code comments so a comment explaining a forbidden claim
cannot trip its own test, and strips markup before substring checks.

The five required regressions, and where they live:

| # | Requirement | Test |
|---|---|---|
| 1 | Same-day timestamp can never produce a "verified pre-fight" verdict | `proof-gates`: *a same-day timestamp can NEVER produce a verified pre-fight verdict*, *a same-day SEALED copy is still graded same-day* |
| 2 | Legacy `closing_odds` count can never open the CLV-001 gate | `proof-gates`: *no count, however large, can open the CLV gate*, *the legacy closing-odds counter is gone, not merely unused*, *only the owning protocol can open a deferred gate* |
| 3 | No rendered copy claims `model_picks`/`model_edges` are immutable | `proof-copy`: *no copy claims a posted row can never be edited*, *the page states outright that the source tables are not locked* |
| 4 | Methodology described as versioned, not impossible | `proof-copy`: *the rules question is not answered "No"*, *methodology change is described as versioned and dated* |
| 5 | Scope claims only what it queries | `proof-copy`: *the page does not claim to hold every prediction CFL has made*, *the page names its scope and what it excludes* |

**Both suites verified to bite.** Re-introducing `"No — rows are locked"` fails 2
copy tests; restoring the old `"every prediction in our database"` claim fails
the scope test; lowering a gate floor fails the gate tests. The markup-stripping
step was added *because* the first version of the scope test could be evaded by
splitting the phrase with an inline `<strong>`.

Re-rendered headless against the real rows at 1360px and 390px: no page errors,
no horizontal overflow, per-row grades spot-checked (a Sep 12 call with a
day-before snapshot renders **Sealed**; a Sep 26 call with no snapshot yet
renders **Dated**; UFC 330 calls, whose snapshots were taken on card day, render
**Dated** rather than Sealed).

---

## Revision 2 — files changed

```
edit   proof.html                    scope, timing section, deferred gate, audit rows, per-row grades
edit   proof-gates.js                clv deferred to CLV-001; clvPairCount deleted;
                                     timestampAudit -> timingEvidence/timingLevel/timingCopy
edit   tests/proof-gates.test.js     36 assertions (was 33)
new    tests/proof-copy.test.js      17 assertions on shipped copy
edit   PROOF_CENTER.md               this section
```

`track-record.html` is unchanged from revision 1 (+1 link line). No frozen file,
no migration, no engine file, no shared script, no stylesheet.

---

## Revision 2 — one thing outside this branch that Reed should see

`track-record.html` — a **live, shipped page** — currently says of live picks:
*"added once, never revised"*, and its pledge box says picks are *"added once,
never revised"* again. By the same check that caught the Proof Center claim,
that is not enforced by the database on `model_picks`.

I did not edit it. It is outside this branch's stated scope, it is live to real
users, and quietly rewording a shipped trust claim is exactly the kind of change
that should be a decision rather than a drive-by. **It should be corrected, and
I can do it in a follow-up on your word.**

---

## Revision 2 — next action for ChatGPT

1. **`proof-gates.js` `GATES.clv` and `evaluateGate`.** Is there any argument
   shape that opens the deferred gate other than a genuine CLV-001 approval? Is
   `showValue` reachable as `true` for it?
2. **`timingEvidence`.** Do the four grades partition every live row exactly
   once, under every combination of missing snapshot, missing timestamp,
   non-matching snapshot and same-day snapshot? Can any path grade a row *up*?
3. **`tests/proof-copy.test.js`.** It asserts on strings, which is brittle by
   nature — is there a rewording that would restore a false claim while keeping
   all 17 green?
4. **The audit table's nine rows** against the database, not against the
   migration files. That distinction is what caught the immutability bug.
5. **Do not merge, deploy, index, or add to the nav.**

---

## Revision 3 — final trust-copy / semantics fixes (2026-09-16)

Passed major review. No redesign; three fixes only. Still not merged, not
deployed, not indexed, not in the nav.

### 1. `source='live'` no longer reads as proof of pre-fight timing

It identifies the prospective dataset. It says nothing about whether any given
row beat the first bell — that is what the per-row grades are for. Every label
now agrees:

| Was | Now |
|---|---|
| Filter: *"Posted before the fight"* | *"Live / prospective"* |
| Record card: *"Posted before the fight"* | *"Live / prospective record"* |
| Archive note: *"Every call posted before its card"* | *"Calls from the live feed, newest first, each tagged with what its timing can actually be shown to support"* |
| Live section: *"Only picks written to the database before the card started"* | *"The prospective feed only — calls published as the card approached… what each row can prove about **when** it was written is a separate question, graded below"* |
| Record card: *"A row written to the database ahead of the card"* | *"Calls from the live feed: rows written as a card approached"* + *"It does **not**, on its own, prove any given call beat the first bell"* |
| `STATUS_COPY.live` blurb: *"Measured only on picks posted before the fight"* | *"Measured only on the prospective feed… graded separately, row by row"* |

The lede now states it outright: *"being in the live feed is not by itself proof
that a call beat the first bell."*

One stale trailing code comment in `proof-gates.js` still said "rows posted
before the fight" and was corrected too — the copy scan caught it, because it
only strips full-line comments. That false positive is the safe direction, so
the stripper stays naive on purpose.

### 2. Snapshot presence, match and timing are three counters, not one

`sealedCovered` conflated "a sealed copy exists" with "it still matches", so a
future mismatch would have silently read as *uncovered* — hiding the exact
failure the crosscheck exists to catch. Replaced by four explicit fields:

| Field | Today |
|---|---|
| `snapshotPresent` | 67 |
| `snapshotMatched` | 67 |
| `snapshotMismatched` | 0 |
| `snapshotAbsent` | 84 |

Invariants now hold by construction and are tested: `present + absent === total`,
`matched + mismatched === present`. The timing grade is computed downstream of
all three and still requires **all** of: a copy exists, it matches, and it was
taken on an earlier calendar day than the card.

The UI follows. The totals card reads *"67 have a sealed copy at all"* from
`snapshotPresent`, and appends a red *"N of those no longer match it"* if that
ever becomes non-zero. The audit verdict reads *"67 of 67 sealed copies still
match · 84 calls have no sealed copy"*, and on a mismatch flips to *"N of M are
**covered by a sealed copy but no longer match it**"* — never "uncovered". The
audit row spells the three facts out and says a copy that stops matching is
*"never quietly folded back into 'no copy'."*

### 3. CLV freeze wording narrowed

*"frozen before any result can be seen"* → **"frozen before any CLV-001 result
was computed or reviewed"**, in all three places. UFC outcomes and the legacy
price fields predate CLV-001, so the broad claim was more than is true.

The sentence now lives once, as `GATES.clv.freezeNote`, and the page renders it
from there — so the wording cannot drift between the gate panel and the audit
row, and the copy test asserts on a real literal rather than a template.

### Revision 3 — tests

```
$ node tests/proof-gates.test.js
  40 passed — replay/live separation and publication gating hold.

$ node tests/proof-copy.test.js
  20 passed — shipped copy matches what the data actually supports.
```

New this revision:

- **`proof-gates`** — *a snapshot that exists but does not match: present, not
  sealed, still a mismatch* (the required test: asserts `snapshotPresent`, no
  sealed grade, and an independent `crossCheckSnapshots` mismatch);
  *a mismatch on probability alone is still present-and-mismatched*;
  *the three snapshot facts stay consistent with each other*;
  *snapshot presence never implies a timing grade on its own*;
  *the live status blurb does not claim the whole bucket is proven pre-fight*.
- **`proof-copy`** — *no label describes the whole live bucket as proven
  pre-fight* (the required regression, eight banned phrasings);
  *the live record is labelled as a feed, and points at the per-row grading*;
  *the CLV freeze claim is narrowed to CLV-001 results*.

**All three verified to bite:** restoring *"Posted before the fight"* on the
record card fails the live-bucket test; broadening `freezeNote` back to *"frozen
before any result can be seen"* fails the freeze test; folding a mismatched
snapshot into `snapshotAbsent` fails three gate tests including the
`present + absent === total` invariant.

Re-rendered headless against the real rows at 1360px and 390px: no page errors,
no horizontal overflow, timing grades unchanged at **54 / 70 / 27 / 0**.

### Revision 3 — files changed

```
edit   proof.html                    live-bucket labels, snapshot counters in UI, freeze wording
edit   proof-gates.js                snapshotPresent/Matched/Mismatched/Absent replace sealedCovered;
                                     live status blurb; GATES.clv.freezeNote; stale comment
edit   tests/proof-gates.test.js     40 assertions (was 36)
edit   tests/proof-copy.test.js      20 assertions (was 17)
edit   PROOF_CENTER.md               this section
```

`track-record.html` unchanged since revision 1 (+1 link line). No frozen file,
no migration, no engine file, no shared script, no stylesheet, no database
change.

### Revision 3 — preserved

Deferred CLV gate with no local threshold; no legacy 46/100 progress; live/replay
firewall; equal visibility for losses; the four timing grades; the immutable
snapshot crosscheck; versioned-methodology language; main-engine-only scope;
flat-$100 P&L; no CTA; `noindex`; read-only database access; no paid services.
All still covered by tests.

**Still outstanding and outside this branch:** `track-record.html` is live and
says of live picks *"added once, never revised"*, which the same check shows is
not enforced on `model_picks`. Awaiting your word to fix it in a follow-up.

---

## Revision 4 — `track-record.html` brought in line (2026-09-16)

Proof Center approved. This revision fixes the adjacent page so it stops
contradicting the evidence model. **Copy consistency only** — no calculation,
query, model, styling, methodology or CLV behaviour was touched. Verified: the
diff contains no changed line matching `const|let|=>|function|filter(|map(|
reduce(|.from(|select(|querySelector`. 25 insertions, 21 deletions, all strings
plus one explanatory comment.

### What was claimed, and what it is now

| Was | Now |
|---|---|
| *"added once, never revised"* (pledge, ×2 in JS) | *"recorded with a timestamp… never re-run or re-priced"* |
| *"added once, never edited"* (archive banner) | *"recorded with a timestamp dated on or before the card"* |
| *"Locked before the bell — our real pre-fight record"* (h2) | *"The live record — our prospective calls, graded"* |
| *"Every pick below was saved with a timestamp before the card started"* | *"Every call below was recorded with a timestamp as its card approached… how strongly each row's timing can be proved varies"* |
| *"Live · locked before fight night"* (banner) | *"Live · prospective record"* |
| *"picks were locked live: written to the database before fight night"* | *"come from the live feed: recorded with a timestamp as each card approached"* |
| *"bets were locked live before fight night and added once, never re-priced"* | *"come from the live feed, priced as each card approached and never re-priced"* |
| *"models with locked-before-the-fight picks"* | *"models with calls on the live feed"* |
| *"The one genuinely locked-before-the-bell record…"* | *"The one genuinely prospective record…"* |
| *"not picks locked before fights"* | *"not calls published as a card approached"* |
| *"Complete pre-fight record"*, *"the pre-fight record is being rebuilt"* | *"Complete live record"*, *"the live record is being rebuilt"* |

Every rewritten passage now uses the Proof Center framing — live/prospective
record, calls recorded with timestamps, timing evidence varies by row, sealed
copies exist for part of the record — and points at `proof.html` for the
row-level grades. Three links to the Proof Center now exist on the page.

### One thing found while doing it, and NOT changed

The legacy archive banner splits live from simulated with:

```js
const liveRows = picks.filter(r => r.created_at && r.created_at.slice(0, 10) <= r.event_date);
```

That is a comparison against the card's **date**, so it includes same-day rows —
the exact conflation Proof Center corrected. Calculations were explicitly out of
scope, so **the filter is untouched**. Instead:

- the copy beside it now says so outright: *"That date includes same-day rows,
  so it is not by itself proof a given call beat the first bell"*, with a link
  to the Proof Center;
- a comment above the filter records what it does and does not establish;
- a test asserts that disclosure cannot be removed.

**This is worth a decision separately from this branch.** The honest options are
to leave it (a dataset split, now labelled as one) or to grade it the way
`timingEvidence` does. I have not assumed either.

### Revision 4 — tests

```
$ node tests/proof-gates.test.js
  40 passed — replay/live separation and publication gating hold.

$ node tests/proof-copy.test.js
  24 passed — shipped copy matches what the data actually supports.
```

Four new tests in `proof-copy`, scanning `track-record.html`:

- *track-record.html does not claim rows are written once and never revised* —
  five banned phrasings;
- *track-record.html makes no wholesale pre-bell claim* — nine banned phrasings
  including *"locked before the bell"*, *"locked live"*, *"our real pre-fight
  record"*;
- *track-record.html uses the same framing and points at the row-level grades*;
- *the same-day banner split on track-record.html is described honestly*.

**A hole in my own test, found and fixed.** The presence checks originally ran
against the raw file, so a **code comment satisfied them** — dropping the
same-day disclosure from the visible copy still passed. The scanner now keeps
three views of the file: markup (for `href` checks), text (tags stripped — where
prose must be proved), and lowercased text (for banned phrases). That is the
same failure mode these tests exist to catch, so it is worth naming.

All four verified to bite: reinstating *"added once, never revised"*, reinstating
the *"Locked before the bell"* heading, deleting the same-day disclosure, and
removing the Proof Center link each fail their test.

Re-rendered `track-record.html` headless: no page errors, all sections render,
counts unchanged (the numbers come from untouched code).

### Revision 4 — files changed

```
edit   track-record.html             copy only + one explanatory comment (25 ins, 21 del)
edit   tests/proof-copy.test.js      24 assertions (was 20); three-view scanner
edit   PROOF_CENTER.md               this section
```

`proof.html` and `proof-gates.js` unchanged this revision.

### Revision 4 — next action for ChatGPT

1. Read the rewritten `track-record.html` strings against the data: does any
   surviving sentence claim more than a timestamp plus a partial sealed copy
   supports?
2. Decide on the `created_at <= event_date` banner filter — leave it as a
   labelled dataset split, or grade it like `timingEvidence`. Out of scope here.
3. Do not deploy.

---

## Revision 5 — `track-record.html` site-consistency pass (2026-09-16)

Three stale claims removed. **Copy only** — verified: no changed line touches a
calculation, query, selector or model output. 16 insertions, 14 deletions on
`track-record.html`.

### 1. The CLV section defers entirely to CLV-001

Deleted the local methodology — the 100-pick threshold *and* the benchmark
definition. Both belong to CLV-001. The section (now `id="clvStatus"`, added so
tests can scope to it) reads:

> **Prospective market-price validation is collecting.** CFL measures this under
> the separately frozen **CLV-001** protocol, which owns every condition — how
> many scored observations it takes, across how many separate UFC events, and
> how tight the range must be. **No CLV figure is publication-approved yet.**
> This page holds no threshold of its own and computes nothing here. The Proof
> Center will display it only when CLV-001's own publication gate is satisfied.

The heading changed too: *"Did we beat the closing price?"* → *"Did we get a
better price than the market ended up at?"*, matching `proof.html`.

**Also renamed, and worth a veto if you disagree.** Four other places described
the replay's grading price as *"the closing price"* / *"the real closing
price"*. Those describe `edgeOdds()` grading simulated bets off the stored
`closing_odds` field — a different thing from CLV-001's benchmark, so strictly
outside instruction 1. But it is the *same stored field* CLV-001 would draw on,
and calling it a verified close overstates it. They now read **"our
closing-price proxy"**. The calculation is untouched. Say the word and I'll
revert the wording.

Left alone deliberately: the v5 audit note *"they leaned on the closing betting
line"*. That describes a model's training input, not a CLV benchmark, and it is
accurate. The benchmark test is scoped to the `#clvStatus` block so this cannot
be confused with it.

### 2. "live locked record" gone

*"The live locked record starts July 2026"* → *"The live / prospective record
starts July 2026."*

### 3. Scope narrowed to the main engine

| Was | Now |
|---|---|
| h1: *"Every pick we've made. Wins and losses."* | *"The main engine's fight calls — wins and losses."* |
| Archive summary: *"Every model we've run — archived simulations"* | *"Every main-engine model represented in this archive — simulations"* |
| Archive note: *"Every model we've ever run, oldest to newest."* | *"Every main-engine model represented in this archive, oldest to newest. Fight-duration and prop research run under their own protocols and appear nowhere on this page."* |
| meta description: *"Every CFL pick graded in public"* | *"Every main-engine fight call graded in public"* |

### Revision 5 — tests

```
$ node tests/proof-gates.test.js
  40 passed — replay/live separation and publication gating hold.

$ node tests/proof-copy.test.js
  29 passed — shipped copy matches what the data actually supports.
```

Five new, covering all four required regressions:

- *track-record.html has a market-price section that defers to CLV-001*;
- *track-record.html states no CLV threshold of its own* — five banned phrasings
  plus a regex that rejects **any** `NN picks/bets/observations` threshold
  appearing in the CLV block, so a different number is caught too;
- *track-record.html does not call the CLV benchmark the literal closing price*
  — scoped to the `#clvStatus` block, plus a page-wide check that no stored
  field is presented as *"the real closing price"*;
- *track-record.html contains no "live locked record" wording*;
- *track-record.html does not claim to hold every CFL prediction or model*.

**All five verified to bite**, by re-introducing each original claim in turn:
the 100-pick gate fails 2 tests, the old heading fails 1, *"live locked
record"* fails 1, the every-model claim fails 1, and presenting the proxy as a
real closing price fails 1.

Re-rendered headless: no page errors, every section renders, all counts
unchanged.

### Revision 5 — files changed

```
edit   track-record.html             copy only (16 ins, 14 del) + id="clvStatus" hook for tests
edit   tests/proof-copy.test.js      29 assertions (was 24)
edit   PROOF_CENTER.md               this section
```

`proof.html` and `proof-gates.js` unchanged since revision 3.

### Revision 5 — preserved

Every calculation, query, model output, timing grade, Proof Center gate, style
rule and pre-existing test behaviour. The only structural edit to
`track-record.html` is the `id="clvStatus"` attribute, added purely so the
benchmark test can scope to that section instead of matching the whole page.

### Still open for you

1. The *"closing-price proxy"* rename above — keep or revert.
2. The `created_at <= event_date` banner filter (revision 4): leave it as a
   labelled dataset split, or grade it like `timingEvidence`.
