# Commercial validation — the smallest paid offer, and a test of whether anyone wants it

Written 2026-10-12 for the stabilization sprint. **Nothing here is built, priced
or charged for.** Stripe stays off. Showing any price to the public is an owner
decision (CRITICAL_GATES.md L3 item 7).

## 1. The Free/Pro boundary as it stands

`PRODUCT_BOUNDARY.md` (status: proposal) and `entitlements.js::SURFACES` (19
rows, all `enforced: false`) say Pro sells depth, history, monitoring and
personalisation, never a pick. Checked against the code:

| proposed Pro item | state today | withheld from free users? |
|---|---|---|
| book-by-book table | built (Market Lab, Fight Lab) | no — free |
| movement chart per fight | built (Fight Lab) | no — free |
| watchlists | built | no — free (account required) |
| price-target and movement alerts | built, **cannot deliver** (no mail key, cron off) | no |
| historical lookback of past cards' markets | data exists since 2026-09-19; no page | not built |
| "what changed since you last looked" | not built | — |
| advanced matchup / prop research | not built; prop surface archived | — |

**The boundary withholds nothing that exists.** Every built Pro item is free,
and `pricing.html` still says alerts, watchlists and charts are "not built yet".
A paywall applied today would take away features people already have — a bad
first impression for a test with a handful of visitors a day.

## 2. The smallest differentiated paid offer

Criteria: already built or nearly, differentiated from free odds sites, and
cheap to deliver reliably.

**Recommended: "Fight-week alerts" — email when a fight's price reaches your
number, or its market moves past your threshold, measured over the books
quoting at both ends.**

- It is the only built feature a free odds-comparison site does not already
  give away, and the matched-cohort rule (D-012/D-020) is a real methodological
  difference: it refuses to alert on a "move" that is only a change of books.
- Remaining work is operational, not development: set `RESEND_API_KEY` /
  `RESEND_FROM` (T-074), run the controlled delivery test, re-enable the cron
  (T-073). Then the boundary would gate alert *creation* through
  `public.alert_quota()` — its single designed home.
- Bundle with it, for little extra: a "past cards" market history page (the
  provenance-tagged series since 2026-09-19), so Pro also holds something that
  is not available free elsewhere and grows with time.

What it is not: a forecast, an edge, a pick, or a claim the subscriber will
profit. All remain banned at every tier.

**Honest caveat:** there is no evidence anyone wants this. The test below exists
to find out before anything is built.

## 3. A demand test that measures genuine interest without selling anything

### Why the test must bring its own visitors

Human traffic is roughly one to four people a day
(`research/traffic/HUMAN_TRAFFIC_BASELINE_2026-10-12.md`). An on-site "join the
waitlist" box would collect close to nothing in a month and prove nothing either
way. The test therefore has two halves: an honest offer page, and deliberate
distribution to UFC bettors.

### The offer page (one static page, no backend work)

`/pro.html`, noindex until the test ends:

- What it is, in two sentences, with one screenshot of a real alert.
- **"Not available yet."** in the first line, not the footer.
- The intended price, shown plainly (owner sets it; the stated range is
  ~$10–12/month).
- One button: **"Tell me when it opens"** → email. This uses the existing
  `premium_waitlist` table and the existing `cflAuth.joinWaitlist`, which today
  has no caller. No new table, no billing, no card details.
- A second, optional one-click question after signup: "Would you have paid
  that price today? Yes / No / At a lower price". Stored as a funnel prop, no
  free text.

Measured with what already exists: `pro_cta_clicked` (already declared and
wired), `engaged_session` and `v_traffic_daily` (PR 3), and `premium_waitlist`
row count. Nothing personal goes into the funnel; the email lives only in
`premium_waitlist`.

### Distribution (where the visitors come from)

Two fight weeks, about three hours of the owner's time per week:

1. Post the free Card Lab for the upcoming card in UFC betting communities
   (r/MMAbetting, two or three MMA betting Discords), as a free resource, with
   one line pointing to the alerts page. No paid ads.
2. Reply to five people per week who ask "where's the best line on X" with the
   Fight Lab link.
3. Ten direct conversations with bettors: what they use today, whether a
   move or price alert would change what they do, what they would pay. Notes in
   a private file.

### Decide the thresholds before starting

Fixed in advance so the result cannot be argued with afterwards:

| outcome over two fight weeks | decision |
|---|---|
| ≥ 300 engaged visitors to the offer page **and** ≥ 30 waitlist signups **and** ≥ 3 of 10 conversations say they would pay | proceed: clear T-054 and T-048, set the price, build T-069 → T-066, gate alerts |
| 10–29 signups, or interest only at a much lower price | one more iteration on the offer; do not build |
| < 10 signups from ≥ 300 engaged visitors | stop Pro; keep CFL free and cheap to run, or reposition around what visitors actually use (fighter and matchup stats) |
| < 300 engaged visitors in total | the test did not run — distribution failed, not the offer. Fix distribution before reading anything into signups. |

Rules for honesty: never say or imply Pro is available; never take a card number
or a deposit; delete the waitlist on request; if the test says stop, publish the
result in `coordination/DECISIONS.md` the same way the model's failure was.

## 4. What blocks charging, besides demand

| blocker | state | owner | notes |
|---|---|---|---|
| T-054 privacy policy | open | owner + lawyer | Must name Plausible and the in-house funnel table. **Also wrong today in two places:** it describes a cookie banner the site does not have, and affiliate-tracking cookies, while `disclaimer.html` says there are no affiliate links. Draft wording: `legal-review/PROPOSED_WORDING.md`. |
| Disclaimer wording | stale | owner + lawyer | Section 2 of `disclaimer.html` illustrates variance with "a 62% favorite under our model" — CFL no longer publishes a model number. Share descriptions were corrected 2026-10-12; the legal body was left for the lawyer. |
| T-048 Terms of Service | does not exist | owner + lawyer | Facts for drafting, including billing behaviour, already in `legal-review/PROPOSED_WORDING.md`. |
| Data licensing — The Odds API | unexamined | owner | Alerts and the market pages are built on it. The code is capped at the free tier (500 credits/month; 33 used this month). Whether the free tier, or any tier, permits redistributing prices inside a paid product must be read in their terms before charging. |
| Data licensing — UFCStats | unexamined | owner | All fighter and fight statistics are scraped from UFCStats, which actively blocks datacenter IPs. Charging for the stats would be charging for a scraped derivative with no licence. The recommended offer is market-based, which keeps stats out of what is sold. |
| Gambling-adjacent rules | partial | owner + lawyer | `disclaimer.html` has 21+, helplines and a Tennessee LLC statement. Selling alerts that prompt a bet may trigger advertising or tout rules in some states; a lawyer should say which. T-049 (book jurisdiction labelling) before any affiliate link. |
| Price | not set | owner (L3) | — |
| Stripe account and secrets | none | owner | T-068 |
| Email delivery | key unset | owner | T-074 — needed for the test's confirmation email and for the product itself |

## 5. Recommendation

Run the demand test before any further build. It needs one static page, one
owner decision (the price to show), and two fight weeks of the owner's time in
communities where bettors already are. Fix T-074 first, because the alerts
feature has to be demonstrable with a real email. Do not start the legal work
(T-054, T-048) until the test clears its threshold — except the privacy
policy's false statements about cookies, which should be corrected now whatever
happens.
