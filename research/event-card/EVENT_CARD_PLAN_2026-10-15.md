# T-096 — Event card: running order, sections, start times, search

Date: 2026-10-15. Status: the customer-facing code is in the PR; **three
owner decisions** gate the parts that need data. Nothing in this sprint has
been applied to production, scheduled or paid for.

## What a visitor gets now (in the PR, no approval needed)

- **Search within the card** on Card Lab and the event page: type any part of
  a fighter's name, nickname or the weight class ("jas", "welter",
  "blanch fly"). Case- and accent-insensitive; shows "3 of 13 fights match";
  Escape or the clear button resets it. Works with every sort and with the
  direction toggle.
- **The order says what it is.** With no verified running order (every card
  today), the card reads main event first, then in announcement order, and the
  note says so — plus that start times and the main card / prelims split are
  not held. Unchanged in substance from T-095; reworded per card.
- **A ready reader for the real running order.** `card-research.js` reads the
  event-flow ledger through a public view, puts every bout in walkout order,
  labels each "Bout 7 of 13", and turns the reverse toggle into
  "Main event first / First bout first". It is switched off
  (`RUNNING_ORDER_LIVE = false`) until the view exists, because a request for
  a missing view would 404 on every page load.
- Everything already on the card — odds, movement, best price, matchup notes,
  Fight Lab and Compare links, badges, the watchlist star — is unchanged.

## What the investigation found

| Question | Finding |
|---|---|
| Is there an existing running-order pipeline? | **Yes, complete and unused.** `cfl_engine/event_flow/` reads the UFCStats card page (which lists bouts in running order), links bouts by UFCStats fight id only, refuses partial cards and truncated pages, and appends whole-card observations to `fight_bout_order`. 47 tests. `event-flow.yml` runs it, manual-only, schedule commented out. |
| Why has it never run? | The ledger table does not exist: it is in `research/clv/proposed_2026-09-16_event_flow.sql`, unapplied, because that file also creates `odds_api_usage` empty, which would mislead the odds credit governor (T-029). And `--execute` is refused until a person records one real-page check (`REAL_PAGE_CHECK.json`). |
| Can the browser read it? | Not as designed: the ledger is revoked from both browser roles. A read-only view is needed. |
| What about `fights.bout_order`? | A different column with the **opposite** numbering (1 = main event). Nothing writes it; the site no longer reads it as an order. |
| Main card / prelims / early prelims? | **No source.** UFCStats does not publish card sections. |
| Start times? | **No reliable source.** `v_fight_start_best` holds per-fight times from the odds provider (`provider_commence`) — on 2026-10-17 they step through the evening (21:00 … 02:45 UTC) and look like a schedule, but they are the provider's guesses, and the repo records them as such (`dur001_migration.sql`). Three bouts on that card fall back to `event_date_fallback` (18:00 UTC), which is not a time at all. Showing them would be presenting an estimate as the start time. |

## Decisions for the owner

### 1. Running order — recommended

| Step | What | Who | Cost |
|---|---|---|---|
| 1a | Apply [`proposed_2026-10-15_card_running_order.sql`](proposed_2026-10-15_card_running_order.sql) in the SQL editor (not the MCP tool: its `drop trigger if exists` lines raise a NOTICE). It creates **only** the ledger (verbatim from the CLV migration §1, so that file stays compatible) and `v_card_running_order` (select-only to both browser roles). Verified on a throwaway Postgres: applies twice cleanly; the view returns the latest complete card, follows a reshuffle including a bout returning to an old position, drops retired bookings, ignores non-UFCStats rows; `anon` can read the view and not the ledger; the ledger rejects UPDATE. | Owner | none |
| 1b | The one-time real-page check the ingester demands: dispatch `event-flow.yml` as a **dry run** for the next card (GitHub's runners can reach UFCStats; this container cannot), read the printed order against the real card — **bout 1 must be the first prelim, the last line the main event** — and commit `cfl_engine/event_flow/REAL_PAGE_CHECK.json` naming who checked and when. | Owner (a person must look) | none |
| 1c | Run once with `execute`, then uncomment the schedule in `event-flow.yml` (`20 7,19 * * *`, twice a day; an unchanged card writes nothing). | Owner approves; Claude can do the edits | GitHub Actions minutes, negligible; UFCStats is free public HTML; no API credits |
| 1d | Flip `RUNNING_ORDER_LIVE` to `true` in `card-research.js` (one line) and add `v_card_running_order` to the live checks. | Claude, after 1a | none |

Risk: the ingester's assumption that UFCStats lists the main event first has
only been tested against a hand-built page (1b exists for exactly that). If it
were backwards every card would be inverted — which is why 1b is a person, not a
script.

### 2. Card sections (early prelims / prelims / main card) and start times — needs a new source

No source in the stack has them. Options, none started:

- **A. UFC.com event pages.** They list the sections and their start times.
  Would need an addition to the event scraper on Railway plus columns or a
  ledger for section and start time, and a check of UFC.com's terms of use for
  automated access. Cost: no money; one migration; scraper work; ongoing
  maintenance when the page markup changes. Section boundaries change during
  fight week, so it must be re-read like the running order.
- **B. A paid MMA data provider** with structured schedules. Costs money (L3).
- **C. Keep showing nothing.** The current behaviour, which states that they are
  not held.

Not an option: inferring sections from bout counts, or presenting the odds
provider's per-fight times as start times.

### 3. Odds-provider times — not recommended

They could be shown as "Sportsbooks list this bout around 21:00 UTC —
an estimate, not a broadcast time", but that reads like a schedule to anyone
skimming, and the fallback rows would need hiding. Recommendation: no.
