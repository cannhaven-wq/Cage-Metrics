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
