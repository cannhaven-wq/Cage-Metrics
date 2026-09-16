# CLV-001 amendment proposal — the eligible-book list was never written down

**Status: PROPOSED — not in force. Needs Reed's approval.**
**Raised:** 2026-09-16, by the dry run ([`DRY_RUN_2026-09-16.md`](DRY_RUN_2026-09-16.md)).
**Severity:** blocking. No observation can score until this is resolved.
**Protocol version affected:** `1.0.1`.

---

## The defect

Q-02 resolved to:

> fixed **NAMED** sportsbook list frozen at protocol freeze; require ≥ 3 eligible
> books with valid TWO-SIDED closing markets.

**The rule was frozen. The list was not.** `protocol.json` records `resolution`
and no `eligible_books`. There is nothing for an implementation to read.

This is not a technicality. The reason Q-02 chose a named list over rule-based
eligibility was stated at the time: *"DUR-001 already forbids selecting
sportsbooks after results are visible; a fixed list makes that unbreakable rather
than merely prohibited."* A named list that does not exist is not unbreakable —
it is the rule-based option with an extra step, decided by whoever implements it
first.

`settle_clv.py` therefore refuses: `eligible_book_list_not_frozen` disqualifies
every row, and `--write` will not run. It does not derive a list from the books
present in the data, because that is the thing Q-02 exists to prevent.

## Why now is the safest possible moment to fix it

The hazard Q-02 guards against is choosing books after seeing which ones flatter
the number. **No CLV number exists**, none has been computed, and the dry run
establishes that none is computable on the current record at all — 0 of 47 rows
scorable, blocked upstream of the book count. A list named today cannot be
result-motivated, and that is verifiable rather than asserted.

That window closes the moment two-sided near-bell capture starts producing data.
This should be settled before then, not after.

## What is in `odds_books` today

Recorded as a fact about the schema, not as a recommendation. **No list is
proposed here** — the choice is Reed's, and a proposal that named books would be
the implementer making it.

| id | name | kind |
|---|---|---|
| 1 | FanDuel | sportsbook |
| 2 | Caesars | sportsbook |
| 3 | BetRivers | sportsbook |
| 4 | BetWay | sportsbook |
| 5 | Unibet | sportsbook |
| 9 | BetOnline.ag | sportsbook |
| 10 | Bovada | sportsbook |
| 11 | DraftKings | sportsbook |
| 12 | BetMGM | sportsbook |
| 13 | BetUS | sportsbook |
| 6 | BFO Consensus | **aggregate** — excluded by kind |
| 14 | CFL Consensus (Odds API) | **aggregate** — excluded by kind |
| 7 | Polymarket | **prediction market** — excluded by Q-03 |
| 8 | Kalshi | **prediction market** — excluded by Q-03 |

The four exclusions are already frozen (Q-03 for the markets; an aggregate is a
blend of other books' margins, so de-vigging it is a different operation and
counting it toward the ≥3 floor would double-count its constituents).
`is_eligible_book` in `cfl_engine/clv/scoring.py` enforces both by name, so they
cannot be admitted by a renumbering — but that is a *necessary* condition, not
the named list itself.

## Proposed amendment

1. Add `eligible_books` to `protocol.json` as an array of book **names** — names,
   not ids, because ids are a database detail that can be renumbered and the rule
   froze names.
2. Record the amendment with `sha256_before` / `sha256_after`, chaining from
   `c2e3f5aa19e9de371ba972705cd8df4b5feb1273dc5117f848959e76bcd1875e`, and bump
   to `1.0.2`.
3. State in the amendment that the list was fixed while **zero** CLV
   observations existed and none was computable, with the dry run as the record.
4. Additions after that require their own dated amendment, as Q-02 already says.

`settle_clv.py` needs no change: it already reads the list by name and refuses
without one.

`motivated_by_observed_results`: **false**, and unusually checkable — the dry run
shows the measure produces nothing to be motivated by.

## What stays blocked either way

Naming the books unblocks one of four preflight conditions. Two-sided near-bell
capture from those books (§4 item 2), a scheduled bout-start instant (§4 item 7)
and provider market IDs (§4 item 9) are all still missing, and none can be
backfilled. This amendment removes a paperwork blocker, not the real one.
