# T-093 — Completed UFC fights with no round records (audit, 2026-10-15)

Feeds **T-091**, the fix that writes a fight's rounds in one database
transaction (Cage-Metrics branch `claude/pensive-fermi-d6pbi0-rounds-rpc`,
event-scraper PR #3).

## Plain version

25 finished UFC fights have no round-by-round stats. They are three different
problems:

- **1 lost its stats to a scraper failure** (fight 7349). The stats exist on
  UFCStats and can be fetched again.
- **3 are the same bout entered twice** (fights 43, 46 and 8780). The real
  copies, 27872, 27877 and 27879, already have full stats. The duplicates add
  an extra bout to six fighters' public UFC records. The fix is to remove them.
  They do not need filling in.
- **21 are from 1994–98.** UFCStats seems never to have published stats for
  them. We do not fill those in.

Every page and model already skips a fight with no rounds; none counts it as
zero.

## How the 25 were found

```sql
select f.id from fights f join events e on e.id = f.event_id
where (f.method is not null or f.winner_id is not null)
  and e.event_date < current_date
  and not exists (select 1 from fight_rounds r where r.fight_id = f.id);
```

Production, 2026-10-15. Control group: 8,915 other completed fights have both
fight totals and rounds, including 246 from before 2001.

## Classification

| fights | what the row holds | classification | evidence |
|---|---|---|---|
| **7349** McSweeney vs. Browne, TUF 11 Finale, 2010-06-19 | fight totals (6 vs 19 sig. strikes), finish time, method detail; **no rounds** | **Scraper failure, recoverable** | The totals can only have come from a page that had stats. The 2026-10-14 full rescan deleted the rounds and lost its connection before re-inserting them (T-091). |
| **43, 46, 8780**, UFC Fight Night: Song vs. Figueiredo, 2026-05-30 | result and method; no finish time, no totals, no rounds | **Duplicate bookings, NOT missing data** | Each has the same event and the same two fighters as **27872, 27877 and 27879**, which have full rounds under different UFCStats ids. The current UFCStats event page lists 13 fights, the database 16. The duplicates inflate six public UFC records: Rodrigo Vera reads 2-0 and Zhu Kangjie 0-2 from one bout, and the same goes for Matthews, Harris, Tsuruya and Gurule. **Fix: retire the three rows (a production delete, L3; precedent D-024).** |
| **21 fights, 1994-12-16 → 1998-10-16**: 8558, 8566, 8574, 8575, 8615, 8616, 8624, 8625, 8626, 8633, 8634, 8642, 8659, 8667, 8668, 8678, 8679, 8688, 8689, 8708, 8709 | result, method, round, time; no totals at any level, no rounds | **Probable source limitation, not yet confirmed** | No statistic of any kind was ever stored for them, while the same scraper stored full stats for 246 other fights on the same early cards. That is how a UFCStats page with empty stat tables looks. |

One more same-card pair turned up in the duplicate check: **8577 / 8580**
(event 873, 1998). Both have rounds. It may be a genuine same-night tournament
rematch. Not investigated.

**Not confirmed from this session.** UFCStats is unreachable from the agent
environment: DNS fails, including through WebFetch.

## What changed in the event scraper

- **PR #2, merged `b977434`.**
  - `upsert_rounds` (both scrapers) upserts on `(fight_id, round_number)`, then
    deletes only rounds past the new last round. A failed write no longer
    empties a fight.
  - Fetches retry 3 times; a 404 is final.
  - A finished fight with no round tables is logged.
  - **Phase 5** re-scrapes completed fights that have no rounds, and logs each
    one as `REPAIRED`, `SOURCE_EMPTY` or `FETCH_FAILED`.
- **Phase 5 is OFF in production** (`REPAIR_MAX_FIGHTS=0` on *Weekly Scraper*,
  since 2026-10-15 14:53 UTC). Two reasons: the owner holds full rescans until
  T-091 is reviewed, and phase 5 must not fill the three duplicates.
- **PR #4 (open, not merged)** makes phase 5 skip a duplicate booking.
- **Side effect to know about:** merging PR #2 redeployed the
  `cage-metrics-event-scrapper` service, which runs a full `events_scraper.py`
  rescan on every deploy. One started at 14:34 UTC on 2026-10-15, with the
  upsert-first code.
  - Baseline taken during it, at 14:52 UTC: 20,976 round rows over 8,915
    fights, and 25 completed fights without rounds.
  - Railway's tools cannot stop a single deployment; only the dashboard can.
  - T-091's PR #3 conflicts with PR #2 in `upsert_rounds` and needs rebasing
    onto `main`.

## Downstream

Every view that reads `fight_rounds` (`fighter_round_stats`,
`v_fighter_cardio`, `v_fighter_cardio_curve`, `v_fighter_consistency`,
`v_fighter_style`) inner-joins it. A fight with no rounds is left out, never
counted as a zero-output fight. Pages show a NULL fight-level field as a dash.
No frozen model input was edited. The duplicate bookings do reach
`v_fighter_ufc_record`, which counts from `fights`.

## To close T-093

1. **Owner (L3):** retire fights 43, 46 and 8780. They duplicate 27872, 27877
   and 27879.
2. When the full rescan finishes, compare against the 14:52 baseline. Round
   rows and fights-with-rounds must not have dropped.
3. **7349:** restore it through T-091's RPC once it is applied, or through
   phase 5 once PR #4 lands and phase 5 is switched back on.
4. **The 21:** with phase 5 on, each should log `SOURCE_EMPTY`. Record any that
   does not.
5. **Never fill in numbers.**
