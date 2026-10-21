# Funnel read, 2026-10-21 (T-055)

**The short version: very few real people are using the site yet, and the one
page they did arrive on, Head-to-Head, was taken off the site on 2026-10-16.**
The funnel can't tell us what to tune yet, because there are too few real
visitors to read. Nothing in the product was changed on the strength of these
numbers.

Source: `funnel_events`, 2026-09-21 → 2026-10-21, read with the service role
through the Supabase tool. `engaged_session` (a scroll, click, tap or keypress
after 2 seconds) is the human-traffic signal, and it only exists from
2026-10-13. Before that date, people and crawlers can't be told apart. See
[`HUMAN_TRAFFIC_BASELINE_2026-10-12.md`](HUMAN_TRAFFIC_BASELINE_2026-10-12.md).

## The nine questions

| # | question | answer from the data |
|---|---|---|
| 1 | Where did the visitor land? | 6,646 landings; 2,802 flagged as automated by the browser itself. Of the 49 engaged sessions: **Head-to-Head 20**, Card Lab (`/` + `/index.html`) 18, fighter page 4, Fight Lab 2, others 5 |
| 2 | Did they reach Card Lab? | 309 `card_lab_view` events in 199 sessions over the month (crawler-inclusive) |
| 3 | Did they open a fight? | 221 `fight_opened` in 183 sessions (crawler-inclusive) |
| 4 | Did they use Market Lab? | 43 board views, 94 re-sorts (42 sessions), 31 per-book expands (7 sessions) |
| 5 | Did they subscribe to the Card Brief? | 2 sign-up starts, 1 address on the list (2026-10-15). `card_brief_signup_completed` has never been recorded; see below |
| 6 | Did they come back in the same fight week? | 41 return visits, 38 of them in the same fight week |
| 7 | Did they view pricing? | 7 views in 6 sessions; none since 2026-10-18 |
| 8 | Did they begin checkout? | not measurable: no checkout exists (`checkout_started` is declared, never emitted) |
| 9 | Did they pay? | not measurable, for the same reason |

Weekly (crawler-inclusive except the `engaged` column):

| week of | landings | engaged | Card Lab | fight opened | Market Lab | returns | pricing | Head-to-Head landings |
|---|---|---|---|---|---|---|---|---|
| 2026-09-21 | 187 | n/a | 64 | 23 | 24 | 8 | 2 | 22 |
| 2026-09-28 | 323 | n/a | 44 | 39 | 16 | 3 | 3 | 36 |
| 2026-10-05 | 2,413 | n/a | 49 | 24 | 3 | 3 | 1 | 992 |
| 2026-10-12 | 3,482 | 42 | 129 | 124 | 104 | 19 | 1 | 2,201 |
| 2026-10-19 (partial) | 241 | 7 | 23 | 11 | 21 | 8 | 0 | 7 |

## What it says

1. **Head-to-Head was where people arrived.** In the one full week we can
   measure people, 20 of the 49 engaged sessions started on `h2h.html`, more
   than on any other page. Head-to-Head landings were 2,201 that week and 7
   the next, after T-103 made the page a redirect to `/`. Retiring it was the
   owner's decision (2026-10-16) and is **not reopened here**. The owner
   should know that the page being retired was the site's main search entry
   point. If search arrivals matter, the redirect could point each old
   matchup to that fight's Fight Lab page rather than to the homepage. That is
   a product call.
2. **Real traffic is a few people a day.** 49 engaged sessions in nine days
   matches the 2026-10-12 baseline of one to four humans a day.
3. **The pricing page gets almost no visits,** which is consistent with nothing
   being for sale.
4. **The one Card Brief signup didn't record a "completed" event.** The address
   was saved (2026-10-15 14:41:08 UTC). The "started" event fired 120 ms
   before the insert, which is faster than a person types, so it was very
   likely a scripted test. A test that closes the page as soon as the insert
   returns would also explain the missing "completed" event. The database
   accepts that event name; this was checked as the `anon` role in a
   rolled-back transaction. Watch for it on the next real signup. It is not
   a known defect.

## What not to do with it

Don't tune the product on these numbers. There are too few people to read
any conversion rate, and every rate above the "engaged" column still
includes crawlers.
