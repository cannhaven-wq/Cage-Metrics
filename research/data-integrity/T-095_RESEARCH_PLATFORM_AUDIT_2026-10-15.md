# T-095 — Research platform audit: what the data supports, what it does not

Date: 2026-10-15. Scope: the 7 upcoming UFC cards in the database (150
fighters, 75 bookings) and the surfaces that render them: Card Lab
(`index.html`), the event page (`event.html`) and Fight Lab (`fight.html`).
All counts below come from queries against production on that date. Nothing
was written to production.

## 1. Data reliability findings

| # | Finding | Measured | Cause | Fixed in this change? |
|---|---|---|---|---|
| R1 | **Card running order is not in the data.** `fights.bout_order` is NULL on every booking ever stored, past and upcoming. | 0 of all bookings | The running-order pipeline (`event-flow.yml`, `cfl_engine/event_flow/`) is built but switched off until `proposed_2026-09-16_event_flow.sql` is applied and a real UFCStats page check is recorded (T-029). Below the main event, `cfl.orderCard` sorts by insert id — **the order bouts were announced**, not the order they are fought. Card Lab's hint said "top of the card down", which overstated it. | **Disclosed, not fixed.** Card Lab and the event page now say what the order is ("main event first, then in the order the bouts were announced") and that the running order, main card / prelims split and start times are not held. The fix needs the event-flow migration — owner approval. |
| R2 | **No start time and no main card / prelims split.** | `events` has no time column; `fights.bell_at` is NULL on all 75 upcoming bookings | Never captured. UFCStats does not publish the split. | **Disclosed, not fixed.** Needs a new source. |
| R3 | **Stored ages are stale.** `fighters.age` is not recomputed as birthdays pass. | 45 of 150 upcoming fighters read a year young; 149 of 150 have a date of birth | The profile scraper writes `age` once per scrape (see R4). | **Fixed on the pages:** Card Lab, the event page and Fight Lab compute age from `dob` (`card-research.js::ageOn`). The stored column is untouched. Age matters most here: it is one of the two factors that survive market control. |
| R4 | **Fighter profiles are stale.** The UFCStats career rates (`slpm`, `str_def`, ...), pro record and `last_fight_date` on `fighters` lag the fight history. | 141 of 150 not refreshed in 60+ days; 68 of 150 have fought since their profile was refreshed; `last_fight_date` wrong for 91 | The profile scraper (`cage-metrics-scrapper`, Railway project `radiant-caring`) has had **no working deploy since 2026-07-01**: the 1 July deploy that ports the UFCStats proof-of-work solver **failed to build**, and the 22 May deploy still running cannot get past the PoW wall UFCStats added around 28 June. | **Worked around on Fight Lab:** every career rate is now rebuilt from `fights` (complete per-fight totals for every UFC bout since 2015, including 2026), and the scraped figure is shown only for reference, with its refresh date and the number of UFC fights it misses. **The scraper itself is not fixed** — redeploying it is an outward production action and needs approval. |
| R5 | **Pro record (all promotions) can be behind the UFC record.** | 4 of 150 | Same as R4. | Already handled: Fight Lab shows "not up to date" instead of an impossible record (T-083/T-084). |
| R6 | **Market coverage on upcoming cards is partial.** | 12/13, 6/11, 0/11, 0/13, 2/12, 0/9, 1/6 bookings priced, nearest card first | Expected: books post lines a week or two out. | Nothing to fix. Every page already says "No line yet". |
| R7 | **Historical odds are mostly unreadable from the browser.** | 99 of 966 completed fights since 2025-01-01 have a row in `v_fight_market_vigfree`; 16 in `v_fight_market_at_lock` | The full history lives in `fight_odds`, which is admin-only by design (T-087). | **Not built.** A per-fighter "favourite or underdog in past fights" panel needs a new read-only definer view of closing consensus per completed fight — a migration, so owner approval. |
| R8 | **Round data gaps.** | 25 completed fights without round records | Tracked as T-093 (1 scraper loss, 21 probable source gaps from 1994–98, 3 duplicates now retired). | Already tracked. Fight Lab names any fight it leaves out of a figure and why. |
| R9 | **Duplicate fighters.** | 8 duplicated names across all fighters; **0** on upcoming cards | Same-name fighters (likely distinct people). | Nothing to fix for upcoming cards. |
| R10 | **Double bookings.** | 0 fighters booked twice on an upcoming card; 4 retired bookings on upcoming cards | The scraper retires a booking that leaves the UFCStats page (`is_active = false`). | **Now used:** the retired bookings are real opponent changes, and Card Lab, the event page and Fight Lab show them ("Opponent change"). |
| R11 | **Weight-class labels do not distinguish men's and women's divisions.** | "Flyweight", "Bantamweight", "Featherweight" carry both; `fighters.sex` is almost empty | Scraper (May 2026 division / sex bug, noted in its deploy history). | **Handled for division rank:** the comparison pool is cut to fighters linked to the two on the page by actual bouts, so men and women are never compared. |
| R12 | **No news, injury, weigh-in or short-notice source.** | — | Never built. | **Not built, and not faked.** Fight Lab's context panel states plainly that these are not covered. |

## 2. Requested features against what exists

Legend: ✅ works (before or after this change) · 🟡 partial · ⛔ blocked on data or approval.

**Event page / Card Lab.** Next event prominently ✅ (Card Lab hero) · complete card ✅ · correct bout order ⛔ R1 · ascending/descending toggle ✅ *new* (honestly labelled "main event first / last") · main card vs prelims ⛔ R2 · names and records ✅ · weight classes ✅ · current odds ✅ · links to matchup analysis ✅ · date and location ✅ · start time ⛔ R2 · desktop and mobile ✅.

**Fight Lab — tale of the tape.** Age ✅ *fixed* (R3) · height, reach, stance ✅ · weight 🟡 division limit *new*; weigh-in weight ⛔ R12 · pro record ✅ (stale-guarded) · UFC record ✅ · physical differences ✅ with Factor Lab evidence.

**Fighting style.** Primary style ✅ (existing classifier, round one of the last five fights) · striking tendencies ✅ *new* (where strikes land: head/body/legs, distance/clinch/ground) · wrestling ✅ takedowns landed and attempted per 15 *new*, control time · submission threats ✅ attempts per 15, submission wins and losses *new* · striking and takedown defence ✅ · style matchup analysis 🟡 framed as questions in Key points, not as verdicts.

**Recent form.** Last five, opponents, results, methods ✅ · KO/submission history ✅ how they win and how they lose *new* · finishing trends ✅ · quality of competition ✅ *new* (each opponent's UFC record going into the fight) · time since last fight ✅.

**Advanced analytics.** Landed/absorbed per minute, accuracy, defence, takedown accuracy/defence, submissions, control time, knockdowns ✅ — now from every UFC fight (fresh, R4) and the last five · division rank ✅ *new* · finishing percentages ✅ · round-by-round ✅ *new* · cardio indicators ✅ (late-round score) · historical trends 🟡 fight-by-fight rows under each metric; no chart.

**Betting intelligence.** Current moneyline, every book, implied probability (vig-free), line movement ✅ · "opening odds" — CFL has never observed a sportsbook opener; it shows the first broad capture and says so (D-012) · historical odds trends ⛔ R7.

**News and context.** UFC debut ✅ *new* · opponent changes / cancellations 🟡 *new*, once the UFCStats card changes · short-notice timing, missed weight, injuries, news ⛔ R12.

**Interpretation.** ✅ *new*: Fight Lab's Key points tab separates **verified facts**, **numbers CFL calculated** and **interpretation**, and interpretation is written as questions. Nothing names a winner.

## 3. Blocked items and what unblocks them

1. **Running order (R1)** — apply `proposed_2026-09-16_event_flow.sql` with the index change in `cfl_engine/event_flow/MIGRATION_ADJUSTMENT.md`, record one real-page check, then enable `event-flow.yml`. The pages switch wording automatically once every bout has `bout_order` (`card-research.js::orderInfo`). Owner approval (production schema).
2. **Profile scraper (R4)** — find why the 2026-07-01 build of `cage-metrics-scrapper` failed and redeploy. That also fixes `fighters.age` and `last_fight_date` at the source. Owner approval (production deploy).
3. **Historical odds (R7)** — a read-only definer view exposing one closing consensus per completed fight, granted SELECT to both browser roles. Owner approval (migration).
4. **Start time, main/prelims split, news, injuries, weigh-ins (R2, R12)** — need a new source. Not something to infer.
