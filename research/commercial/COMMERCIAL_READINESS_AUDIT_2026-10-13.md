# Commercial-readiness audit — what stands between CFL and its first paying customer

Written 2026-10-13, after the stabilization merges (#54–#57), PRED-001 (#58)
and D-024. It answers the owner's step 6: *what prevents Cannon Fight Lab from
attracting paying subscribers, independently of whether the prediction model
succeeds.* It builds on
[`COMMERCIAL_VALIDATION_2026-10-12.md`](COMMERCIAL_VALIDATION_2026-10-12.md)
(the offer and the demand test), which is not repeated here. Nothing below is
built, priced or charged for.

## The plain verdict

**CFL cannot take its first $100 today, and the model is not the reason.**
Four things stand in the way, in this order:

1. Almost nobody is there to buy.
2. The one feature worth paying for cannot send an email.
3. There is no lawful way to take money yet.
4. Nobody has checked whether the data may be resold.

The first is the hardest and the cheapest to test. The fastest honest $100
probably comes from **one business customer**, not from ten subscribers.

**Correction, later on 2026-10-13 (T-088).** The "0 email subscribers" below
was not only an audience problem. **The Card Brief signup form had never
worked:** every submission failed with a database error shown to the visitor,
because the browser asked for an upsert that row security refuses. Fixed in
`_auth.js` (a plain insert; an address already on the list counts as success),
proven against production in a rolled-back transaction, and shipping with the
T-088 pull request. No subscriber is known to have been lost: the funnel table
records no signup attempt. Until that merges, blocker 2's "a real Brief" has
nobody to send to. See
[`../security/T-088_PRIVILEGE_AUDIT_2026-10-13.md`](../security/T-088_PRIVILEGE_AUDIT_2026-10-13.md), finding F1.

## 1. The audience, measured today

| measure | value | source |
|---|---|---|
| raw sessions today | 355 | `v_traffic_daily`, 2026-10-13 |
| sessions that declare automation | 27 in the first hour of the new flag | same |
| **engaged people, first hour after launch** | **1** | same, after today's correction |
| human-signal sessions, last three full weeks | 28, 20, 10 | `HUMAN_TRAFFIC_BASELINE_2026-10-12.md` |
| accounts / active in 30 days | 8 / 0 (last sign-in 2026-09-11) | `profiles`, `auth.users` |
| email subscribers / Pro waitlist / watchlist rows | 0 / 0 / 0 | live tables |

**New today, and it matters:** crawlers that run JavaScript also *scroll*. In
its first hour the "engaged visitor" signal counted 27 people; 24 were
self-declared bots and 2 were headless browsers. Corrected in
[cannhaven-wq/Cage-Metrics#61](https://github.com/cannhaven-wq/Cage-Metrics/pull/61).
The human audience is, if anything, **smaller** than the baseline said. Every
plan that starts with "convert our visitors" starts from about one person an
hour, on a good hour.

## 2. What blocks a paying customer, ranked

Each item was checked against the code or the database today.

| # | blocker | evidence | who can move it | size |
|---|---|---|---|---|
| 1 | **No audience to sell to** | §1. About 90% of sessions land on fighter, h2h and event stub pages from search and AI crawlers. Market Lab, the product, had 21 views in three weeks. | owner (distribution) | the long pole |
| 2 | **The paid feature does not deliver** | Alerts: `alerts.yml` has no schedule (dispatch only) and `RESEND_API_KEY` is unset. The weekly digest runs every Wednesday and sends nothing: dry-run, 0 subscribers. | owner: create a Resend key (free tier) and set two secrets; Claude: delivery test (T-073/T-074) | about an hour |
| 3 | **Nothing is withheld from free users** | Every built Pro item (book table, charts, watchlists, alerts) is free; `pricing.html` says Pro is "not built yet". | product decision | small |
| 4 | **No way to take money** | No Stripe account; `checkoutMayBeEnabled()` is false while T-054 (privacy must name Plausible) and T-048 (no Terms) stand. The privacy page also wrongly describes a cookie banner and affiliate cookies. | owner + lawyer | days to weeks |
| 5 | **Data rights unchecked** | Prices come from The Odds API, free tier, terms unread. Stats are scraped from UFCStats, unlicensed. A paid product built on either needs an answer first. | owner (read two sets of terms) | an afternoon |
| 6 | **Gambling-adjacent rules** | Alerts that prompt a bet may fall under state tout or advertising rules. T-049 must be done before any affiliate link. | owner + lawyer | unknown |

What does **not** block revenue: the prediction model, PRED-001 and the lock
table. They stay a research track. D-011 already keeps them off every public
surface, and none of the routes below depends on them.

## 3. The arithmetic of $100

| route | what $100 takes | realistic at today's audience? |
|---|---|---|
| Pro subscription at about $10/month | 10 paying members, or 4 annual members at about $25 | **No.** At 1–4 people a day, even a strong 5% sign-up rate gives about one waitlist entry a week, before anyone pays. Needs distribution first. |
| Founding-member presale (pay now, delivered when built) | 4–10 people from the demand test's conversations | possible, after Terms, privacy and payment exist; a refund promise is required |
| **One business customer** — a betting newsletter, podcast or Discord that pays for a weekly card-market brief, or an embeddable movement table | 1 invoice, $100–250 | **the most plausible.** One conversation, no paywall, no audience needed. It is a services or data deal, so the data-rights check (blocker 5) comes first. |
| Affiliate links | tens of referred sign-ups | **No.** T-049 is open, the audience is tiny, and it contradicts the anti-tout positioning. |
| Ads or sponsorship | thousands of human visits | **No.** |

## 4. What to do, in order (the next phase: first $100)

**Week 1 — make the thing work and make it lawful to sell (no new code needed).**

1. Owner: create a Resend key and set `RESEND_API_KEY` and `RESEND_FROM`.
   Claude: run the controlled alert delivery test and turn on the alerts
   schedule. Afterwards CFL can send one real price alert and one real Brief.
2. Owner: read The Odds API terms on redistribution and commercial use, and
   note the answer in `DECISIONS.md`. If paid use needs a paid tier, that is
   an L3 cost decision. Keep UFCStats-derived stats out of anything sold.
3. Owner and lawyer: fix the privacy page's false statements now, whatever
   happens next. Start Terms (T-048) only if week 2 finds a buyer.

**Week 2 — find one buyer before building anything (the demand test, aimed at
businesses as well as people).**

4. Ten conversations, five of them with people who *publish* about UFC
   betting: newsletters, podcasts, Discord admins. Show them the Card Lab and
   one real alert. Ask what they would pay for weekly, and record the answers
   privately.
5. Put up `/pro.html` as specified in the 2026-10-12 review: "not available
   yet", a price, and a waitlist that writes to the existing
   `premium_waitlist`. Distribute it during one fight week.

**Week 3 — take money only if weeks 1–2 earned it.**

6. If a business says yes, invoice them for the weekly brief. That is the
   first $100, with no subscription system involved.
7. If at least 30 people join the waitlist and at least 3 of 10 conversations
   would pay: set the price (L3), open Stripe (T-068), test-mode run (T-069),
   gate alerts through `public.alert_quota()`, turn checkout on (T-066).
8. If fewer than 10 people join from at least 300 engaged visitors: stop Pro,
   keep CFL free and cheap, and record why, the same way the model's failure
   was recorded.

**Kill rule, fixed now.** If no buyer, business or person, has said yes by the
end of week 3, the owner decides between keeping CFL as a free reference and
shutting down the paid track. More engineering is not one of the options.

## 5. What Claude can do without the owner, and what it cannot

| Claude can, now | needs the owner |
|---|---|
| Build `/pro.html` as an honest, non-transacting offer page (static, noindex) | The price to show (L3) |
| Run the alert delivery test and turn on the schedule once the key exists | The Resend key; any spending |
| Draft the weekly business brief from Market Lab data, as a sample to show prospects | Every conversation with a prospect |
| Fix any copy the lawyer approves | Privacy and Terms wording (L3) |
| Measure everything with `v_traffic_daily` and `premium_waitlist` | Reading and answering the data-rights question |
