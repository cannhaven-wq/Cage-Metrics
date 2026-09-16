# Handoff — event flow and data integrity

**From:** Claude (event-flow / integrity session, branch `claude/cfl-event-flow-integrity-29rl4c`)
**To:** ChatGPT for review, then Reed for the L3s
**Date:** 2026-09-16

> **A note on where this file lives.** The CLV session owns
> [`STATE.md`](STATE.md) and [`HANDOFF.md`](HANDOFF.md) and was editing both
> while this ran. This is a separate file on a separate branch so the two
> sessions cannot collide; it is a handoff entry, not a second baton. **When the
> branches merge, fold the summary below into `HANDOFF.md` and refresh
> `STATE.md` in the same commit**, per the rule at the bottom of `STATE.md`.
>
> This session **modified no existing file**. Everything below is new paths. The
> working tree touched nothing under `research/clv/`, nothing frozen, and
> nothing the close-price implementation is changing.

---

## 1. What changed

Four new things, all additive.

### `cfl_engine/event_flow/` — the running-order ingester

Reads a UFCStats event page and writes one row per bout into the append-only
`fight_bout_order` ledger. **First walkout is 1.**

| file | what |
|---|---|
| `ufcstats_card.py` | parses the event page; stdlib only, no bs4 |
| `bout_order.py` | links page bouts to fight rows and does the page-order flip |
| `ingest_bout_order.py` | the runner — dry run by default |
| `test_event_flow.py` | 26 tests |
| `fixtures/ufcstats_event_page.html` | hand-built to the markup contract, labelled as such |
| `README.md` | including the outstanding real-page verification step |

The direction is the thing worth reviewing hardest. UFCStats prints **main event
first**; the ledger stores **first walkout first**; so the page is read
bottom-up. There is also a second, opposite convention in the repo —
`fights.bout_order` in the unapplied `add_bout_order_migration.sql` counts
`1 = main event`. Same word, opposite meaning.
`test_the_two_conventions_are_opposites` exists so a future join notices.

Refusals, all tested: a truncated page raises rather than yielding a shorter
card; a card links **completely or not at all** (one unlinkable
bout renumbers every bout below it); linkage is by UFCStats fight id only, never
by name; a fight sitting on another event refuses; a duplicate id on either side
refuses; the ledger is never created by this script; inserts use
`resolution=ignore-duplicates`, never an upsert, so a re-run is a no-op and a
reshuffle appends; nothing is backfilled for past cards; `--execute` is required
to write. Exit codes distinguish setup failure (2) from a card that would not
link (3) from a page that could not be read (4).

### `.github/workflows/event-flow.yml`

Manual dispatch only. **No `schedule:` block** — `fight_bout_order` does not
exist until `research/clv/proposed_2026-09-16_event_flow.sql` is applied, and a
cron that is red every run is a cron people stop reading. The schedule is
written out, commented, ready to uncomment. Zero scheduled runs means zero cost
delta.

### `cfl_engine/integrity/` — standing data-integrity checks

21 read-only checks, each carrying the SQL that counts it, a plain-English
reason it matters, its classification, and the count measured today.
`run_audit.py` runs them and reports what moved. `test_integrity.py` — 17 tests —
enforces that every check is SELECT-only, explains itself without jargon, and
**that no defect whose repair would delete or invent an observation can ever be
classified "safe to fix automatically"**. Verified to bite: reclassifying one L3
check as AUTO fails two tests.

`count_rpc.sql` is **proposed and unapplied**, filed under `cfl_engine/integrity/`
rather than the repo root. It is `security invoker`, sets the transaction read
only, refuses anything that is not a single `SELECT`, and grants execute to
`service_role` only.

### `research/integrity/DATA_INTEGRITY_AUDIT_2026-09-16.md`

The full audit, plain-English summary first.

---

## 2. What was found

All 21 checks ran against production today and every one matched the baseline
recorded in the catalogue. Three findings can contaminate prospective validation
or CLV research.

### The three that matter

**a. Three fight rows were rebooked in place — L3.** Fights 43, 46 and 8780 on
event 113 (Song vs. Figueiredo, 2026-05-30) now hold different matchups than
they did when we published picks and captured prices for them. **8 predictions**
name Muslim Salikhov or Jesus Aguilar, who are not in those fights; **104 odds
rows** name Ramon Taveras. `unmatched_odds` row 1031 records the replacement
being detected and instructs "Update fights.fighter_*_id/name to clear" — still
`resolved = false`. Grading those picks scores our call on a fight we never
called. Deleting them loses evidence; repointing them invents a call. What is
needed is a rule, not a script.

**b. 1,578 odds rows have their corner letter contradicting their fighter — needs
review.** 746 fully-swapped quote pairs plus 86 half-swapped, across **8 fights**,
2026 only. All four odds views — `v_fight_odds_consensus`,
`v_fight_odds_latest_by_book`, `v_fight_market_vigfree`, `v_fight_market_at_lock` —
resolve corners by the **letter**, so those fights come out with the two
corners' prices swapped. Fight 46239 already carries a published `model_edges`
row computed that way. The odds rows are faithful; the letters went stale when
`fights` reordered its corners underneath them. `export_data.py` already keys on
`(fight_id, fighter_id)` for exactly this reason — the views have not followed.
**Not applied here**: `v_fight_market_at_lock` feeds DUR-001, which is
collecting, and changing a running experiment's inputs is not this session's
call.

**c. 30,724 odds rows carry a 1970 placeholder capture time — needs review.**
27.9% of the table, every one of them `BFO Consensus` and no other book's,
covering 7,681 fights from 2007 to 2026. The exact values are
`1970-01-01T00:00:00Z` on the 15,362 openers and `…:00:01Z` on the 15,362
closers — the timestamp is an **encoding of opener-versus-closer**, one second
apart so they sort, not a failed capture. Anything ordering on `captured_at`
puts the entire historical archive before every live quote on every fight. Not
fixable: the only repair is a time nobody observed.

### The rest, quantified

| finding | affected | class |
|---|---|---|
| same bout stored twice on one card | 4 matchups (1 is a genuine 1997 rematch); 44 prediction rows on 2 real bouts | review |
| bookings that fell off a card, never retired | 36 fights, all 2026; 31 modern fighter-double-bookings; 3 cards with two main events | review |
| a settled prediction market (±199900) flagged as a closing price | 2 rows, Polymarket, fight 27648, captured after the card | **L3** |
| prices past 100-to-1 | 61 rows, 4 fights (Kalshi 45, BetMGM 12, Polymarket 4) | review |
| no fight has a confirmed start time | 0 of 8,990 | review — this is what event flow is for |
| two fighter records sharing a name | 8 names | not a defect; the reason nothing matches by name |
| pre-2001 clock/round anomalies | 48 + 29 + 184 fights, all pre-2001 | not a defect; era artifact |

**Clean, and worth not re-deriving:** no duplicate `ufc_fight_id` or
`ufc_event_id`; no orphan rows in any of `fight_odds`, `model_predictions`,
`model_picks`, `model_edges`; **no duplicate market identity at all** — not one
`(fight, book, side, captured_at)` repeats across 110,032 rows, and no
fight-book-side has two openers or two closers; every row's `implied_prob`
agrees with its own price to 0.005, 110,032 for 110,032; no future timestamps;
no prediction dated differently from its event; no stale `is_upcoming`; all
8,994 fight ids and 798 event ids are well-formed 16-hex UFCStats tokens.

---

## 3. Tests run, and results

| suite | result |
|---|---|
| `cfl_engine.event_flow.test_event_flow` | **26 passed** |
| `cfl_engine.integrity.test_integrity` | **17 passed** |
| `tests.test_research_state` | 28 passed (unchanged by this session) |
| `research.dur001_backfill.tests.test_gate` | 32 passed (unchanged) |
| `cfl_engine.dur001.test_alert` | 25 passed (unchanged) |
| `cfl_engine.dur001.test_diagnose_folds` | 20 passed (unchanged) |
| `cfl_engine.dur001.test_dur001`, `dur002.test_lock_prop0002`, `dur001.test_walkforward_prop0001` | **import error — `numpy` is not installed in this container.** Pre-existing and environmental; nothing in this session imports numpy or touches those modules. |

**148 passing, 3 modules unrunnable here for a missing dependency.**

Two verifications beyond the unit tests:

* **Every one of the 21 checks was executed against production and matched its
  recorded baseline** — 21 for 21. The baselines are measurements, not guesses.
* **The linkage half of the ingester was run against real production data**: a
  page built from UFC 331's thirteen real `ufc_fight_id` values links 13/13,
  numbers the main event 13 and the opener 1, and is unaffected by an extra dead
  booking added to the fight list. Note that UFC 331's fight ids happen to
  ascend down the card, which is exactly why an id sort is dangerous — it looks
  right until event 113, where the same three bouts exist under ids 43/46/8780
  and again under 27872/27877/27879.
* **The governance tests were verified to bite**: reclassifying an L3 check as
  "safe to fix automatically" fails two tests.

---

## 4. Data defects still open

Nothing was repaired. Every finding above is open, and each is now a standing
check so it cannot get worse unnoticed.

Two things about the ingester are also open:

1. **The parser has never seen a real UFCStats page.** `ufcstats.com` is not on
   this container's network egress allowlist — `curl` returns
   `Host not in allowlist` and the fetch tool returns `EGRESS_BLOCKED`. The
   fixture is hand-built to the markup contract and labelled as such. The
   linkage half is verified against production data; the parsing half is not.
   The one-command check is in the README and is a dry run.
2. **The ledger does not exist.** `fight_bout_order` is created by
   `research/clv/proposed_2026-09-16_event_flow.sql`, which is written and
   unapplied. Until it lands the ingester exits 2 and names the migration. It
   will not create the table.

---

## 5. L3 decisions required

| | question | why it is Reed's |
|---|---|---|
| **L3-EF-1** | **May a fight row's participants ever be rewritten in place?** Recommended: no — a replacement is a new row and the old one is retired. | It changes what the event scraper is allowed to do, and it decides whether 8 published predictions are void or mis-attached. Neither answer can be reached from the data. |
| **L3-EF-2** | **What happens to the 8 predictions and 104 odds rows already stranded by (a)?** Options: leave and exclude by rule; or retire the row and re-key. Not: delete, and not: silently regrade. | Both honest options lose something. Deleting loses evidence of a real published call. |
| **L3-EF-3** | **Do prediction markets count as a book for CLV, and what stops a resolved market being read as a quote?** 2 rows at ±199900 are currently flagged as closing prices. | Protocol, and the CLV protocol is frozen. |
| **L3-EF-4** | **Apply `add_bout_order_migration.sql`?** It adds `fights.is_active` and retires dead bookings. | Schema change to the central table, and its cleanup rule (newest booking wins) is right for upcoming cards and arguable for settled ones. |
| **L3-EF-5** | **Apply `cfl_engine/integrity/count_rpc.sql`?** One read-only function so the audit can ask for a count. | Any migration. Costs nothing; the script is unusable without it. |

Sequenced after the CLV session's own migration order — `fight_odds_capture`,
then `event_flow`, then `clv001_columns` — the event-flow ingester becomes
runnable at step 2.

**Nothing here costs money.** UFCStats is public HTML on the host the scraper
already polls: no API key, no credits, no tier change. The workflow is manual
dispatch only, so it adds no scheduled runs. No paid service was enabled,
priced, or configured.

---

## 6. Next action for ChatGPT review

**Review `cfl_engine/event_flow/bout_order.py` and `ufcstats_card.py` against
one question: can this ingester ever write a running order that is wrong rather
than absent?**

That is the whole risk surface. A missing order costs coverage and is visible; a
wrong order is invisible and poisons every close reference derived from it. The
specific things to attack:

1. **The flip.** `walkout_order(page_index, n_bouts) = n_bouts - page_index`.
   Is "UFCStats lists main event first" actually true for *upcoming* cards, not
   just completed ones? If an upcoming page ever lists bouts in announcement
   order rather than card order, the flip produces a confident wrong answer and
   nothing in the code would notice. If that is a real risk, the fix is a
   refusal condition, not a heuristic.
2. **All-or-nothing linkage.** `build_rows` refuses the card if any page bout is
   unlinkable. Confirm there is no path where a bout is silently skipped and the
   remaining ones still get numbered — the `orders != range(1, n+1)` assertion is
   the backstop, check it cannot be reached with a hole.
3. **Append-on-reshuffle.** The unique index is
   `(fight_id, source, bout_order)`. A bout that moves from 5 to 6 appends. A
   bout that moves from 5 to 6 and back to 5 appends nothing the second time,
   so the ledger says 5 and 6 with the later `observed_at` on 6. Is
   "latest observation wins" in `v_clv_close_reference` still correct in that
   case? This is a question about the CLV view, not about this code, and it is
   the one interaction between the two sessions.
4. **The audit's classifications**, specifically whether finding (b) — the
   corner-letter contradiction — is correctly held at "needs review" rather than
   fixed. It has an obvious fix (key the views on `fighter_id`) and one blocker
   (`v_fight_market_at_lock` feeds a collecting experiment). Confirm that
   blocker is real; if it is not, this is the highest-value cheap fix on the list.

Then: the parsing half needs one real page. Anyone with UFCStats access can run
the dry run in `cfl_engine/event_flow/README.md` under
"Verifying against a real page" and paste the printed order. It writes nothing.
