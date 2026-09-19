# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-19 — UFC 331: the first card captured under the CLV capture path

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-19

Launch-day activation for UFC 331 (event 4433, first bout 21:00 UTC). Recorded
as [D-009](DECISIONS.md), which is the approval — see the correction below.

### The finding, and it is the whole entry

**On a card day, the odds job had captured nothing.** Every cadence tier in
`build/fetch-odds.js` gated on where the wall clock sat —
`min % cadence < WAKE_INTERVAL_MIN`. That is a cadence only if the `*/5` cron
fires every five minutes; GitHub throttles it to a handful of deliveries a day
at arbitrary minutes. The four real wakes on the 19th were **:43, :30, :35,
:35** — not one inside minutes 0–4, so the gate never opened. The only UFC 331
moneyline rows on file that morning came from the Polymarket writer, which
CLV-001 excludes by kind, and the freshest *sportsbook* line was **28 hours**
old against a frozen 45-minute staleness limit.

The gate now measures **elapsed time since our own last capture**, scoped to
rows carrying `feed_version` so the other two writers cannot suppress our
cadence, and falls back to the phase test whenever that is unreadable — so a
missing ledger degrades to the old behaviour, never to "capture every wake".
Seven tests, two mutation-checked, one replaying the four real wakes. Same
throttled wakes against tonight's card: **10 captures, against 1**.

### What is now live

| | |
|---|---|
| `fight_odds` capture columns | **applied** — all 110,980 existing rows NULL, nothing backfilled |
| `fights.is_active` / `bout_order` | **applied** — `_shared.js` had been reading both for months |
| first CLV-eligible capture | 15:49 UTC, 142 rows, 6 books, **118 with the full §4 set** |
| UFC 331 card | 12 active, 1 retired, evidence preserved |

No CLV figure computed, none published, publication gate untouched at 0/100 and
0/20.

### The premise that was wrong

The instruction said *"the approved migrations"*. **None of the five had an
approval on record** — `DECISIONS.md` ended at D-008, and D-004 says the
immutability migration is still the owner's to apply. D-009 is therefore not a
citation of an earlier approval, it *is* the approval, and it is scoped to the
two additive files rather than to all five.

### Held back, against the instruction, and why

Three migrations and two activations. The reasons are engineering, not process:

1. **Immutability** — adds triggers to `fight_odds` while another repository
   writes to it, during a live card. Its own filing says apply it between cards.
2. **Event flow** — creates `odds_api_usage` **empty**, which reads as *"0 spent,
   500 remaining"*. That is false, and the governor would take its finest rung on
   it. Overspending the free allowance is paid usage, L3 under gate #6. **T-029.**
3. **`clv001_columns`** — stores a result nothing can compute yet. Its header
   says apply last.
4. **The Event Flow schedule** — `REAL_PAGE_CHECK.json` does not exist and
   `--execute` refuses without it. UFCStats returns **403** to this environment,
   so it cannot be produced from here. **T-030.**
5. **CLV write mode** — changes nothing tonight. The gate is a sample floor and
   it is at 0.

## Next action

**Owner:** two calls, neither urgent tonight.

1. **T-031** — the immutability migration, once the card is over. It is the last
   structural piece and D-004 already assigns it to you.
2. Whether holding items 1–5 above was the right read. If you want the Event
   Flow schedule on, **T-030** needs somebody on a residential connection to
   fetch one UFCStats page; it is not a decision, it is an IP block.

**ChatGPT:** the claim worth attacking is the cadence fix. It changes when
credits are spent, and the argument that it cannot spend faster than the ladder
already permits rests on `dueSinceLastCapture` returning `null` — not `false` —
on every unreadable path. If there is a path where an unreadable last capture
reads as "due", the credit ceiling has a hole in it and the test asserting
elapsed ≤ phase + 1 is measuring the wrong thing.

---

## 2026-09-18 (f) — Factor Lab correction published; T-027 closed

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-18

**T-027 is done.** PR #34 merged at `f40fd27c` under [D-008](DECISIONS.md), the
L3 that permits it — verified by removing the entry and watching
`test_a_done_L3_task_has_a_recorded_decision` go red.

### What is now live

`market_even_cohort` 869 → **1,220**, `fights_scored` held at 8,739, seven
verdicts moved. The artifact is byte-verified: sha256 `ba3c9077…`, reconstructed
from the validation run's own checksummed log because the artifact download
redirects to blob storage the build network refuses.

The Factor Lab's summary now reads **"Age, UFC-only record"**. That name is a
page-side override, so `factor-rates.json` stays byte-identical to what the run
produced and a future regeneration cannot silently revert the wording.

Also corrected: three freshness claims the publish gate had quietly falsified
(`stats.html`, `edges.html`, `CLAUDE.md` all said the Lab rebuilt on a timer),
and a pre-existing error that printed 8,739 into a sentence describing the
1,220-fight market-even cohort.

### The episode in one line

A reader defect in a build script had been publishing itself every six hours.
The fix required separating measurement from publication first, then correcting
the numbers, then correcting the words — in that order, because merging the fix
on its own would have published its effects unreviewed.

### What this deliberately did NOT settle

`edges.js`'s **record** and **takedown-defence** heuristics are still shipped and
still unsupported. FE-001 put record at ~50.2% market-even and takedown defence
on the line. `ufc_record` clearing the bar is a different measurement and is not
evidence for either. Nothing about them changed, and nothing should be inferred
from the Factor Lab's green light.

## Next action

**Owner:** the measurement-integrity line is closed. The open product question is
what to do with the two unsupported shipped heuristics — retire them the way
cardio was retired in August, restate their published ranges honestly, or leave
them with a caveat. That is a copy-and-product decision, not a measurement one;
the evidence for it already exists in FE-001.

**ChatGPT:** worth a skeptical read of whether the `stats.html` caveat plus the
"UFC-only record" label are together enough that a casual reader cannot come away
believing the pick engine's record factor was validated. That was the failure
mode this whole publication was shaped around, and it is a judgement about
wording rather than data.

---

## 2026-09-18 (e) — the corrected Factor Lab, prepared for publication

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-18

Measurement integrity only. Prepared, **not merged**.

### What is in the publication PR

The corrected artifact, byte-verified rather than retyped: the candidate was
reconstructed from the validation run's own log (gzip+base64) and its sha256
matches what that run printed — `ba3c9077…`, 16,800 bytes. Its comparison
against the published file reproduces run 35377644563 exactly: same seven
verdicts, same 28 resized buckets, `fights_scored` control unmoved at 8,739.

The artifact download could not be used: it redirects to blob storage the
network refuses. So the validation workflow now also emits the candidate to its
log, checksummed — a reviewer who cannot fetch the artifact should not be
reduced to retyping numbers out of a table.

### The problem the copy exists to prevent

`ufc_record` clearing the bar is **not** evidence for `edges.js`'s record
factor. Two measurements, one everyday word:

| | Factor Lab `ufc_record` | `edges.js` recordEdge |
|---|---|---|
| record | **UFC-only** | **whole-career professional** |
| quantity | raw win-rate gap | Laplace-smoothed |
| market-even | **58.4%, `real`** | **~50.2%, a coin flip** (FE-001) |

Left alone, the site would publish a green light on one and a reader would take
it for the other — the one that actually picks fights. So `stats.html` carries a
standing caveat, and `edges.html` and `methodology.html` carry **dated**
corrections that report the new result and keep the shipped factor unsupported
in the same breath. `tests/record-factors-distinct.test.js` (14 assertions)
stops that drifting back.

### A pre-existing error found on the way

`stats.html` printed `fights_scored` into a sentence describing the market-even
cohort — *"tested each one on the 8,739 fights where the odds were even"*, when
8,739 is every scored fight and the even-money cohort is a seventh of that. Both
numbers are named now. It was wrong before this work and is not caused by it.

### Held to scope

`edges.js`, thresholds, engine behaviour, Event Flow, migrations and
monetisation are untouched — checked, not assumed. The scheduled publication
gate stays shut: this is one reviewed commit of `factor-rates.json`, not a
return to unattended refreshes. **Age stays retired.**

## Next action

**Owner:** final review of the publication PR. It is the only thing standing
between the corrected numbers and `stats.html`.

**ChatGPT:** the claim worth attacking is the copy, not the arithmetic. The
arithmetic has two independent routes to 1,220. The question is whether a reader
of `stats.html` could still come away believing the pick engine's record factor
has been validated — because that is the failure this PR is shaped to prevent,
and it is a judgement about wording rather than about data.

---
