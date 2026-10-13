# Human traffic baseline, 2026-10-12

**The short version: CFL currently gets roughly one to four human visits a day,
and the number has been falling.** The 350–465 daily "sessions" in
`funnel_events` are almost entirely crawlers that execute JavaScript.

## How accurately the pipeline separates people from crawlers today

It doesn't. `landing_view` fires on page load for anything that runs JavaScript,
and nothing in the table records an interaction that a crawler wouldn't produce.
No user agent or automation flag is stored (by design: nothing identifying is
sent), so after the fact the only way to separate them is by behaviour.

| signal in the last 14 days | sessions |
|---|---|
| all sessions | 3,033 |
| no referrer and no UTM source | 3,000 |
| opened a second page | 7 |
| lasted longer than 60 seconds | 4 |
| median session duration | 0 seconds |
| `return_visit` | 6 |
| arrived from Google / Bing / ChatGPT links | 9 / 3 / 7 |
| hour-of-day spread | flat across all 24 UTC hours |

A human audience has referrers, sometimes opens a second page, stays more than
zero seconds and sleeps. This one does none of those.

## The baseline, by week (proxy, from data already collected)

"Human signal" = the session did at least one thing a crawler does not: fired a
click-only event (changed a sort, expanded the per-book table, opened the
methodology, used the watchlist, started a Brief signup), arrived with a
referrer or UTM source, was a return visit, or opened a second page.

| week starting | all sessions | human signal | clicked | from search | any source | returning | 2+ pages | human, reached a product page |
|---|---|---|---|---|---|---|---|---|
| 2026-09-21 | 144 | **28** | 6 | 12 | 18 | 8 | 9 | 23 |
| 2026-09-28 | 286 | **20** | 4 | 9 | 18 | 3 | 4 | 14 |
| 2026-10-05 | 2,379 | **10** | 0 | 5 | 6 | 3 | 2 | 8 |
| 2026-10-12 (Mon only) | 395 | **0** | 0 | 0 | 0 | 0 | 0 | 0 |

Read it as an upper bound on people: some of those sessions are the owner and
anyone testing the site. Raw sessions grew roughly sixteen-fold over the period
while human-signal sessions halved twice.

Where people came from, all time (sessions): Google 18, ChatGPT 11 (8 tagged
with `utm_source=chatgpt.com`), Bing 4, DuckDuckGo 1, and single visits from
YouTube, TradingView, Prime Video and Google Drive.

What they reached: Market Lab and Fight Lab together drew fewer than 30
sessions in three weeks with any human signal at all.

## What this PR adds so the next baseline is measured, not inferred

- `engaged_session`, fired once per session on the first scroll past the first
  screen, click, tap or keypress, at least 2 s after load with the tab visible.
  Pinned by `tests/engagement.test.js`.
- `webdriver` and `ua_bot` flags on `landing_view` (booleans only).
- `v_traffic_daily`: per day, sessions, automation-flagged, engaged, engaged
  from search, engaged with any source, engaged and returning, engaged and
  reached a product page, engaged with 2+ pages. **This is the dashboard.**
  Query it in the Supabase SQL editor:

  ```sql
  select * from v_traffic_daily order by day desc limit 28;
  ```

## Apply order (production — needs approval)

1. Apply the updated `funnel_events_migration.sql` (adds `engaged_session` to the
   allowed names and creates `v_traffic_daily`). It is re-run safe.
2. Then merge the PR. If the page ships first, `engaged_session` inserts are
   rejected by the old constraint — harmless (the emitter swallows it) but those
   sessions are lost to the baseline. Plausible still receives the event name.

## Not reconciled: Plausible

Plausible was not reachable from this session. It filters known bots and is the
independent check. Please export, for 2026-09-21 → today: unique visitors per
day, top sources, top pages, bounce rate, and visit duration. If Plausible shows
hundreds of daily visitors, the conclusion above is wrong and should be revisited;
if it shows a handful, it is confirmed.
