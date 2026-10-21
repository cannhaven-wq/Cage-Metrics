# T-093: source check for the 21 early fights with no round records (2026-10-21)

Follows [`T-093_MISSING_ROUND_RECORDS_2026-10-15.md`](T-093_MISSING_ROUND_RECORDS_2026-10-15.md).
The raw result is in [`T-093_SOURCE_CHECK_2026-10-21.json`](T-093_SOURCE_CHECK_2026-10-21.json).

## Plain version

**Still unverified.** We tried to check all 21 fights against UFCStats, and
UFCStats would not let the automated check in. Wikipedia confirms that all 21
fights happened and mostly agrees with our results, but Wikipedia has no
strike or takedown numbers. So we still don't know whether UFCStats has
round-by-round stats for these fights. The 2026-10-15 label, "probable source
limitation, not yet confirmed", stays as it was.

Two things are new:

- **"Alternate bout" doesn't fully explain the gap.** 20 of the 21 were
  alternate bouts (reserve fights, usually left off the pay-per-view
  broadcast). But two other alternate bouts on the same cards *do* have full
  stats in our database: Mezger vs. Fairn (UFC 4, fight 8707) and Kalman vs.
  Berto (UFC 10, fight 8643). So being an alternate makes missing stats
  likely, but it doesn't prove it.
- **3 of our result rows disagree with Wikipedia** (listed below). One of them,
  fight 8566, disagrees on how the fight ended.

Nothing was written to the production database.

## What was run

Workflow `.github/workflows/t093-source-check.yml`. It reads data only, uses no
secrets and has `contents: read`.

| run | what | result |
|---|---|---|
| 39620094556 | UFCStats, 21 fights + 2 control fights (stdlib urllib) | every URL returned **HTTP 200 with a "Checking your browser…" page** |
| 39620705070 | the same, with a cookie jar and the response logged | same page: ~2,994 bytes, `nginx/1.10.1`, title `Loading…`, a JavaScript proof-of-work script, no fight markup |
| 39621345502 | first Wikipedia run | **discarded**: the parser matched each fight against the whole page |
| 39621710731 | Wikipedia, `{{MMAevent bout}}` parser | superseded by the next run |
| **39623283850** | **Wikipedia, final** (sha `646b566`) | 21 of 21 bouts found. This is the run in the JSON |

**What happened at UFCStats.** The two controls (8559 and 8560 on UFC 17) have
rounds in our database, and they got the same challenge page as the 21
targets. So the page tells us nothing about any fight. **It is not a "no
rounds" result.** The checker now:

- marks a page like that `source_unreachable`, using the challenge text, the
  missing fight markup and the small page size;
- stops at the first such page instead of retrying;
- runs the UFCStats step only on manual dispatch.

We did not try to get past the challenge.

**This probably affects the production scrapers too.** If
`cage-metrics-event-scrapper` gets the same page, its phase 5 would log
`SOURCE_EMPTY` (a "the source has no rounds" result) or `FETCH_FAILED` for
every fight. Neither can be trusted until someone shows the scraper still gets
real pages. This has not been checked from here.

## Per fight

The "Wikipedia section" column is the card section the bout is listed under.
In the "matches CFL" column, "time" means the finish time and "method" means
how the fight ended (KO/TKO, submission or decision).

| CFL id | bout | event | UFCStats has rounds? | Wikipedia section | matches CFL? |
|---|---|---|---|---|---|
| 8708 | Bossett vs. Dias | UFC 4 | unreachable | Alternate bouts | time and method yes |
| 8709 | Charles vs. Rosier | UFC 4 | unreachable | Alternate bouts | yes |
| 8688 | Macias vs. Gipson | UFC 6 | unreachable | Alternate bouts | yes |
| 8689 | Sutton vs. McGlaughlin (Wikipedia spells it McLaughlin) | UFC 6 | unreachable | Alternate bouts | yes |
| 8678 | Parungao vs. Maturi | UFC 7 | unreachable | Alternate bouts | yes |
| 8679 | Sutton vs. Kalman | UFC 7 | unreachable | Alternate bouts | yes |
| 8667 | Hall vs. Jenkins | Ultimate Ultimate '95 | unreachable | Alternate bouts | yes |
| 8668 | Charles vs. Bessac | Ultimate Ultimate '95 | unreachable | Alternate bouts | yes |
| 8659 | Adkins vs. Mielke | UFC 8 | unreachable | Alternate bouts | yes |
| 8642 | Adkins vs. Mitchell | UFC 10 | unreachable | Alternate bouts | method yes. Wikipedia gives no time; CFL has round 2, 3:00 |
| 8633 | Traven vs. Berry | UFC 11 | unreachable | Alternate bouts | **time differs: CFL 1:33, Wikipedia 1:23** |
| 8634 | Ferrozzo vs. Fulton | UFC 11 | unreachable | Alternate bouts | time yes. Method is labelled differently: CFL "Submission", Wikipedia "TKO (submission to strikes)" |
| 8624 | Bowden vs. Nilson | Ultimate Ultimate '96 | unreachable | Alternate bouts | time yes. Method is labelled differently: CFL "KO/TKO", Wikipedia "Submission (headbutts)" |
| 8625 | Nelmark vs. Bossett | Ultimate Ultimate '96 | unreachable | Alternate bouts | yes |
| 8626 | Hall vs. Mitchell | Ultimate Ultimate '96 | unreachable | Alternate bouts | yes |
| 8615 | J. Martin vs. E. Martin | UFC 12 | unreachable | Heavyweight Alternate bout | yes |
| 8616 | Sanzo vs. Lee | UFC 12 | unreachable | Lightweight Alternate bout | yes |
| 8574 | Brennan vs. Turner | UFC 16 | unreachable | Welterweight Tournament Alternate bouts | yes |
| 8575 | Clark vs. Stuart | UFC 16 | unreachable | Welterweight Tournament Alternate bouts | yes |
| 8566 | Roberts vs. Moskowitz | UFC 17 | unreachable | Heavyweight bouts (**not** an alternate) | **disagrees: CFL "Decision, unanimous", round 2, 3:00; Wikipedia "KO (elbow)", 3:15** |
| 8558 | Marscucci vs. Santos | Ultimate Brazil | unreachable | Alternate Bouts | yes |

On these 12 Wikipedia pages **every** bout has an empty round cell, the main
cards included (`bouts_with_blank_round_cell` equals `bouts_on_page` on every
page). An empty cell is just how these pages are written, so it shows nothing
about whether these bouts had rounds.

## Did per-round statistics ever exist for these bouts?

**The rules on the night.** The Wikipedia pages describe the rules, and those
descriptions are quoted in the JSON under `rules_text`:

- **UFC 4, 6, 7 and Ultimate Ultimate '95:** "no rounds" (UFC 4 also had no
  time limit).
- **UFC 8:** a 10-minute limit for each match.
- **UFC 12–17:** we did not establish from these pages how rounds or
  overtime worked.

So for 1994–95 there was no round 2 for anyone to count. A fight's whole
record would be a single period. "No round records" would then mean "no
statistics at all", not "rounds 2+ missing".

**Where these stats come from.** Fight statistics for this era are worked out
afterwards from video. Alternate bouts were usually not on the pay-per-view
broadcast, which would explain why they have no stats.

**The two exceptions.** Fights 8707 and 8643 are alternate bouts with stats in
our database, which shows that video exists for at least some alternates.
**So we can't conclude from this that UFCStats has nothing for the 21.**

## What it would take to close this

1. Read each of the 21 UFCStats pages (or their totals) from somewhere that
   gets real pages. The control fights 8559/8560 must parse as "yes" in the
   same run, or the result doesn't count. `t093_source_check.py` already
   enforces that.
2. If any page does have round tables, our scraper missed it. The fix is to
   re-run phase 5 (`REPAIR_MAX_FIGHTS`) for that fight id once T-091/PR #4 are
   in. Do not insert numbers by hand. No such case is known today.
3. Check fight 8566's result against a third source. If CFL's
   decision/round-2 row is wrong, that is a results correction (a production
   write) and needs its own decision.
4. Separately, find out whether the production scrapers now get the challenge
   page.
