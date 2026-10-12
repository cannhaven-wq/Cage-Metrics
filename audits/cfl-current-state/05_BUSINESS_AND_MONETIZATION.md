# 05 — Business and monetization

Audit date: 2026-10-12. Business facts below were verified against the live Supabase database, GitHub Actions and Railway. Plausible, Stripe, X analytics, Supabase billing, Railway billing and The Odds API account were **not accessible** from this session; where a number lives only there it is marked UNKNOWN. Nothing is estimated.

## 1. Revenue

| item | state | evidence |
|---|---|---|
| Revenue to date | **$0** (VERIFIED as far as the system can show) | `billing_events` 0 rows; `profiles.subscription_status` NULL for all 8; no Stripe account connected (D-018); `STRIPE_*` secrets unset |
| Paid tier on sale | none | `pricing.html` Subscribe button ships `disabled`; edge function returns 503 `checkout_disabled` before authenticating |
| Price | not set; owner's stated preference ~$9.99–11.99/month, $79–99/year with a founding rate (D-019, "recorded as a preference, not set") | `coordination/STATE.md` |
| Affiliate income | none; T-049 (book jurisdiction labelling) is a standing gate before any affiliate link | `coordination/STATE.md` |

## 2. Payment integration

Built end to end and locked (D-018): `supabase/functions/stripe-checkout`, `supabase/functions/stripe-webhook`, `billing_migration.sql`, `billing-lifecycle.js` (46 tests), `v_my_billing`, `account.html`. Verified against the deployed endpoints once (2026-09-21, `verify-billing-refusal.yml`). The ordered path to switching it on is entirely owner- and lawyer-gated except one step:

| step | id | owner | state |
|---|---|---|---|
| Privacy page names Plausible | T-054 | owner + lawyer (L3) | blocked; draft wording in `legal-review/PROPOSED_WORDING.md` |
| Terms of Service page exists | T-048 | owner + lawyer (L3) | blocked; none exists |
| Set the price | T-067 | owner (L3) | not set |
| Stripe account, product, three function secrets | T-068 | owner | no account |
| Exercise checkout in Stripe test mode | T-069 | Claude | blocked on T-068 |
| Apply the Free/Pro boundary | T-061 | Claude | deliberately behind payment (D-019) |
| Turn checkout live in one PR | T-066 | owner (L3) | blocked on all above |

Also unrecorded anywhere in the repo: the webhook's `verify_jwt=false` setting (live, VERIFIED) — a redeploy from defaults would silently drop every Stripe event.

## 3. Subscription tiers and entitlement enforcement

`PRODUCT_BOUNDARY.md` (status: proposal) defines Free as the whole current product and Pro as depth, history, monitoring and personalisation: book-by-book table, movement history, historical lookback, watchlists, price and movement alerts, "since your last visit", advanced matchup analytics. Of those, watchlists, alerts and the book table are already built **and free**; historical lookback, "since last visit" and advanced analytics are not built. `entitlements.js::SURFACES` has 19 rows, all `enforced:false`; `current_user_is_pro()` exists in Postgres and nothing calls it. During beta every account is premium. **There is no enforced tier.**

## 4. Users

| metric | value (VERIFIED live, 2026-10-12) |
|---|---|
| Registered accounts | 8 (first 2026-05-02, last 2026-09-11) |
| Accounts signed in during the last 30 days | **0** (last sign-in 2026-09-11) |
| Admin accounts | 1 (the owner) |
| Email subscribers (Cannon Card Brief) | 0 |
| Premium waitlist | 0 |
| Watchlist rows / alerts | 0 / 0 |
| Bets logged in My Book | 3 (1 bankroll) |

Of the eight accounts, some are presumably the owner's own test accounts (INFERRED; not verified).

## 5. Traffic (in-house funnel table only; Plausible not accessible)

`funnel_events` has been collecting since 2026-09-21 (5,665 events). Sessions are random per-browser-session ids, never joined to an account.

| period | sessions per day |
|---|---|
| 2026-09-21 → 09-30 | 8 → 33, mostly 10–27 |
| 2026-10-01 → 10-05 | 25 → 171 |
| 2026-10-06 → 10-12 | 247, 339, 382, 465, 368, 414, 345 |

Growth over three weeks is real and steep (roughly 15× from late September). Where it lands, last 14 days:

| path | sessions | share |
|---|---|---|
| `/fighter.html` | 1,157 | ~37% |
| `/h2h.html` | 1,229 | ~39% (every session distinct; INFERRED inbound from preview stubs and search) |
| `/event.html` | 432 | ~14% |
| `/` (Card Lab) | 53 | ~2% |
| `/fight.html` | 55 | ~2% |
| `/fighters.html` | 20 | |
| `/market.html` | 7 | |
| `/stats.html` | 4 | |
| `/pricing.html` | 3 | |
| `/parlay.html` | 9; `/props.html` 3; `/track-record.html` 4; `/proof.html` 4; `/cardio.html` 1; `/signup.html` 1; `/login.html` 1 | |

Event counts for the whole period: `landing_view` 3,265 (3,125 sessions), `fighter_page_view` 1,628, `event_page_view` 451, `card_lab_view` 158 (98 sessions), `fight_opened` 88, `market_lab_view` 21, `return_visit` 14, `factor_lab_view` 11, `pricing_view` 6. No signup, login, checkout or alert events were emitted (the first three are declared but not wired; `alert_fired` once, a test).

**Reading.** Roughly 90% of visits are long-tail search traffic to fighter, head-to-head and event pages generated by the prerender pipeline. The market-intelligence product (Card Lab, Market Lab, Fight Lab, Factor Lab) that D-011 made the forward-facing offer received about 150 sessions in three weeks. The return-visit count is 14. Conversion to an account in that window is zero.

Source of the growth is UNKNOWN from this data (no referrer is stored); the timing coincides with the 6-hourly stub regeneration and the social poster's post-repositioning activity, but that is not established.

## 6. Conversion funnel

Designed (`TRAFFIC_FUNNEL.md`, `ANALYTICS_SCHEMA.md`): SEO previews, social posts, weekly email, RSS → `signup.html?src=` → account → (future) Pro. Actual: the email channel sends nothing (no `RESEND_API_KEY`, 0 subscribers), the social channel posts forbidden copy to X and nothing to Reddit, the preview pages link to `h2h.html` and `event.html` rather than to the product surfaces, and no signup has occurred since 2026-09-11. There is no measured conversion because there is nothing to convert to.

## 7. Marketing and SEO

- Prerendered stubs (5,452 sitemap URLs) are the only acquisition channel that demonstrably works.
- Social: X secrets are set and the poster runs three times a week; Reddit secrets are missing. The content it posts contradicts the positioning (see `03_` V1). `social/` batches from July–August are still served.
- Email: built, inert.
- Per-page SEO is documented (`SEO_PER_PAGE.md`) but stale against the repositioned titles; `event.html` runtime title still says "UFC Predictions".
- No paid acquisition, no partnerships, no press, no newsletter history found.

## 8. Customer feedback or validation

None found in the repository, the database, or the issue tracker (0 issues ever). `contact.html` posts to Formspree; submissions are not inspectable here. No user interviews, surveys, waitlist signups or testimonials are recorded. The product boundary and price are owner preferences, not tested with customers.

## 9. Costs

| item | state |
|---|---|
| Supabase | project `uftancejftcryfvbggll` ACTIVE_HEALTHY; plan and monthly cost UNKNOWN (billing not exposed through the access used). Database under 100 MB. |
| Railway | 6 projects, 6 services; plan and cost UNKNOWN. |
| The Odds API | code hard-caps at the 500-credit free tier; account standing UNKNOWN; the usage ledger table does not exist. |
| GitHub | Actions minutes on a personal account; 3,127 runs to date; public repo. Cost UNKNOWN, likely within free allowance (INFERRED). |
| Domain, Plausible, Resend, Formspree, X developer account | UNKNOWN. Plausible is a paid product; a subscription is implied by the live snippet (INFERRED). |
| Development time | ~7 months; 417 human commits plus the AI tooling behind the 117 Claude-authored commits. |

No expense is recorded anywhere in the repository.

## 10. What stops CFL taking payment for a useful product today

In order of what actually holds:

1. **Nothing is for sale.** No price, no Stripe account, no Pro feature that is withheld from free users. Everything Pro would sell is either already free (alerts, watchlists, book table, charts) or not built (history, "since last visit", advanced analytics).
2. **Two legal blockers** the code enforces: `privacy.html` must name the analytics processor; a Terms page must exist. Both are owner-and-lawyer work; draft wording exists.
3. **The features a paying member would be paying for do not deliver.** Alerts have no schedule and no mail key; the digest has no key, no subscribers, and reads a dead column.
4. **No demand signal.** 8 accounts, none active; 0 subscribers; ~150 product-surface sessions in three weeks against ~3,000 search landings on reference pages.
5. **Positioning is not yet true of the whole system.** The social channel publishes model percentages; one product page shows engine output; preview structured data names a pick. A paying customer or a journalist can find the contradiction in minutes.
6. **Data licensing is unexamined.** The product republishes scraped UFCStats data and The Odds API prices with no terms on file; the Odds API free tier is the only tier the code allows.

## 11. What is missing to complete this section of the audit

Plausible dashboard (true pageviews, referrers, bounce); Stripe (nothing to see yet); Supabase and Railway invoices; The Odds API account page (credits used, tier); X analytics for the posted tweets; Formspree inbox; the owner's own time and spend records.
