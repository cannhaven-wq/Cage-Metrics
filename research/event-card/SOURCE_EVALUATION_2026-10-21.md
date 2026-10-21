# Running order — which source can CFL actually read? (T-030)

Written 2026-10-21. Every finding below is from a real request made by a
GitHub Actions runner (the agent sandbox reaches none of these hosts); the run
is linked beside it. Nothing here is applied, scheduled or paid for.

## The short version

UFCStats, the source the ingester was built for, **does not serve GitHub's
runners** — it answers with an anti-bot page. ESPN's public scoreboard JSON
**does**, lists every bout in walkout order with the start time of each card
section, and on both cards tested agreed with Wikipedia bout for bout. The code
can now read either. **Which one CFL uses on a schedule is the owner's call**,
because ESPN's terms of use have not been reviewed (see "Terms" below).

## What each source returned

| source | from a GitHub runner | evidence |
|---|---|---|
| UFCStats event and listing pages (`www.ufcstats.com`) | **HTTP 200 with a 2,998-byte `<title>Loading…</title>` anti-bot page**, no fight rows. A 200 is not a page. | page-check runs [39620237572](https://github.com/cannhaven-wq/Cage-Metrics/actions/runs/39620237572), [39620364912](https://github.com/cannhaven-wq/Cage-Metrics/actions/runs/39620364912) |
| ESPN `site.api.espn.com/.../mma/ufc/scoreboard` | **HTTP 403 Access Denied** | probe run [39621346144](https://github.com/cannhaven-wq/Cage-Metrics/actions/runs/39621346144) |
| ESPN `site.web.api.espn.com/.../mma/ufc/scoreboard` | **HTTP 200 JSON** (37,580 bytes current week; 43,390 for `dates=20261017`) | probe runs [39622101981](https://github.com/cannhaven-wq/Cage-Metrics/actions/runs/39622101981), [39623017331](https://github.com/cannhaven-wq/Cage-Metrics/actions/runs/39623017331) |
| ESPN `.../summary?event=<id>` | HTTP 404 | 39622101981 |
| ESPN `sports.core.api.espn.com/v2/.../events` | HTTP 200, an index of links only | 39622101981 |
| Wikipedia MediaWiki API (`en.wikipedia.org/w/api.php`) | **HTTP 200**, the event article's wikitext with a results table | 39621346144, 39623017331 |
| UFC.com | **not probed**: its Terms of Use prohibit automated access (PR #81 finding) | `EVENT_CARD_PLAN_2026-10-15.md` |

## What ESPN's scoreboard carries

Real samples, cut to the fields the adapter reads with no value changed, are in
`cfl_engine/event_flow/fixtures/` (`SOURCES.json` holds each one's run, raw
sha256 and content hash; they were recovered byte-exact from the job log).

- **Bout order, first walkout first.** On UFC Fight Night: Buckley vs. Malott
  (2026-10-17, 13 bouts) the first competition is You vs. Chovancek and the
  last is Buckley vs. Malott — the bout the card is named after. On UFC 333
  (2026-10-24, 14 bouts) the last is Volkanovski vs. Evloev.
- **Card sections with start times.** Each bout carries its section's start:
  Buckley vs. Malott 21:00 and 00:00 UTC (prelims, main card); UFC 333
  14:00 / 16:00 / 18:00 UTC (early prelims, prelims, main card). This is the
  "sections and start times" T-096 decision 2 said no source had. **Not wired
  into anything** — showing them is a separate decision.
- **No UFCStats id.** Bouts link to CFL's `fights` by both fighters' names.

## How it was checked

The ESPN path of `real_page_check.py` passed on runs
[39623845331](https://github.com/cannhaven-wq/Cage-Metrics/actions/runs/39623845331) and
[39623974340](https://github.com/cannhaven-wq/Cage-Metrics/actions/runs/39623974340). The
second one's output is committed as `cfl_engine/event_flow/REAL_PAGE_CHECK.json`,
byte for byte (its sha256 `2614e60e…1b1b`, printed by the run, matches the file):

1. **Direction, from the card's own name.** ESPN lists the titled main event
   last (bout 13 of 13; bout 14 of 14) and not first, on both cards.
2. **An independent second source.** Wikipedia's results table matched ESPN
   **13 of 13** on the completed card and **14 of 14** on the upcoming one,
   every bout at the same position, despite four different spellings
   ("You Su-young" / "SuYoung You", "Abusupiyan" / "Abus" Magomedov,
   "Cameron" / "Cam" Rowston, "Nicole" / "Nicolle" Caliari).
3. **Section times never go backwards** along the order (a card where they did
   is refused — the list would not be a running order).
4. **Linking against CFL's real rows** (read-only query, 2026-10-21): 13 of 13
   bouts on event 4368 and 14 of 14 on event 4542 link to exactly one fight
   each, and none of the four retired bookings on those cards (47881, 48644,
   50990, 48648) is ever linked — including Julien Leblanc and Javad Mahjoub,
   who each have a retired twin on the same card.

## The linking rule, because it relaxes an old one

The UFCStats path links by UFCStats fight id and **never** by name ("eight
pairs of fighters share a name"). ESPN has no such id, so its path links by
name under the narrowest rule that is still safe (`sources.link_by_pair`):
only fights already on **this** event; **both** corners must match after
folding case, accents, spaces and punctuation (no nicknames, no surname-only,
no fuzzy distance); **exactly one** row may match; and **every** bout must link
or the whole card is refused. Name collisions across the database cannot reach
it; a collision within one card refuses rather than guesses.

## Terms (the open question)

- **UFC.com** prohibits automated access — not used.
- **ESPN**: the site.web API is undocumented and public. ESPN/Disney's terms of
  use were **not** reviewed in this session. Running it twice a day is light,
  but light is not the same as permitted. **Owner decision** before ESPN is put
  on a schedule; the code defaults to UFCStats so nothing changes without it.
- **Wikipedia**: the MediaWiki API is documented for this; content is CC BY-SA.
  It is community-edited, so it is used to cross-check, never as the source.

## What changes if the owner picks ESPN

1. Apply `apply_2026-10-21_running_order.sql` (it already accepts
   `espn_scoreboard` rows in the view and the decision log).
2. `REAL_PAGE_CHECK.json` is already committed from run 39623974340
   (source `espn_scoreboard`); `--execute` accepts it for ESPN only and still
   refuses UFCStats-sourced writes.
3. Dispatch `event-flow.yml` with `source=espn`, dry run, then execute.
4. Flip `RUNNING_ORDER_LIVE`, then the schedule (two lines, in the workflow
   header).

If the owner says no, T-030 stays blocked on UFCStats: the options are a
non-datacenter runner, a page saved from a browser (`--from-file`), or the
event scraper's challenge handling (PR #81 step 0) — the last not written here,
because this session does not write code to get past a site's bot protection.
