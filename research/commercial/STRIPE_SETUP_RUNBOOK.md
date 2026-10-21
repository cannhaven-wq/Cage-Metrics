# Stripe setup runbook — from no account to the first real subscription

Written 2026-10-21. For **Reed (owner)**. Every step that spends money, sets a
price, sets a secret or turns payments on is **L3** (`coordination/CRITICAL_GATES.md`
items 6 and 7) and is marked **[owner]**. Nothing in this file has been done yet.

**Plain version.** The subscription system is already built and tested. What
it is missing is a Stripe account, a price, and three passwords. This runbook
does those in **test mode first**, proves the whole loop works with fake money
(T-069), and only then does one pull request switch on real payments. That pull
request is the only place payments can be turned on, and everything it changes
is visible in its diff.

## The three locks, and the order they come off

From `CLAUDE.md` §Billing. They hold in this order, and they come off in the
**go-live pull request only** (step 9), never piecemeal:

1. **The checkout function refuses first.** `supabase/functions/stripe-checkout`
   returns `503 checkout_disabled` naming T-054 and T-048 before it reads a
   secret or checks who is asking.
2. **The Subscribe button is `disabled` in the served HTML** of `pricing.html`.
3. **The page reads `entitlements.js::CHECKOUT_BLOCKERS`** and has no opinion
   of its own.

Unset secrets make both functions fail closed. That is **not** a fourth lock:
it disappears the moment step 5 is done, which is why step 5 is safe only
because lock 1 still holds.

## Before you start — what must already be true

| needed | task | who |
|---|---|---|
| `privacy.html` names Plausible | T-054 | owner + lawyer |
| a Terms of Service page exists (period, renewal, cancellation, refunds) | T-048 | owner + lawyer |
| the price, and which periods are sold (monthly only? yearly too? founding rate?) | T-067 | owner |

Steps 1–7 can run **before** T-054/T-048 are done. Step 9 cannot.

---

## 1. Create the Stripe account **[owner]**

1. Sign up at stripe.com with the business email. Fill in the business profile
   (legal name, address, bank account for payouts, tax details).
2. Turn on **Test mode** (the toggle in the dashboard). Steps 2–7 are all in
   test mode. Test mode and live mode have **separate** keys, prices, webhook
   endpoints and signing secrets — nothing created in one exists in the other.

## 2. Create the product and price — test mode **[owner]**

1. *Product catalogue → Add product.* Name: **CFL Pro**. No description that
   promises a feature that is not built (`entitlements.js::NEVER_SOLD`).
2. Add a **recurring** price, **monthly**, in USD, at the T-067 amount.
3. Copy the price id (`price_...`). This becomes `STRIPE_PRICE_ID`.

The checkout function sells **one** price today (`STRIPE_PRICE_ID`). If T-067
decides to sell a yearly plan too, the function needs a small code change to
accept a plan id and map it to a second secret — that goes in the go-live PR,
not in a dashboard setting. `entitlements.js::PLANS` already lists `pro_yearly`
with `stripe_price_secret: null` for exactly this reason.

## 3. Create the webhook endpoint — test mode **[owner]**

*Developers → Webhooks → Add endpoint.*

- **URL:** `https://uftancejftcryfvbggll.supabase.co/functions/v1/stripe-webhook`
- **Events to send** (these are the ones `billing-lifecycle.js::HANDLED` acts on):
  - `checkout.session.completed`
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
  - `invoice.paid`
  - `invoice.payment_succeeded`
  - `invoice.payment_failed`
- **API version: read §current_period_end below before choosing.**
- After saving, **reveal the signing secret** (`whsec_...`). This becomes
  `STRIPE_WEBHOOK_SECRET`.

### §current_period_end — the one setting that can break access silently

The webhook reads `current_period_end` **off the subscription object**. Stripe
API version **2025-03-31 ("basil") and later** moved that field onto the
subscription's *items*. On such a version the webhook would see no period end,
and `billing-lifecycle.js` grants an `active` or `past_due` subscription with
no period end **open-ended access**. A member could keep Pro after their card
stopped working, until Stripe finally marks the subscription `unpaid`.

So, either:

- create the endpoint on an API version **before 2025-03-31**, or
- before go-live, change `billing-lifecycle.js` **and** the webhook's copy
  (the test fails if only one changes) to fall back to
  `items.data[0].current_period_end`.

The T-069 harness checks the endpoint's version and **fails** on a version at
or after 2025-03-31, so this cannot pass unnoticed. *Unverified here:* the
exact field move is from Stripe's changelog as known to the author, not from a
live account — confirm it in the dashboard's API version notes.

### §Rolling the signing secret

Stripe can roll a webhook secret with an overlap, sending one `v1` signature
per live secret. The webhook only checks the **last** `v1` in the header
(`tests/stripe-webhook-offline.test.js` pins this). Until that is changed,
roll the secret **without** an overlap ("expire now") and update the function
secret immediately.

## 4. Keys — test mode **[owner]**

*Developers → API keys.* Copy the **secret key** (`sk_test_...`). This becomes
`STRIPE_SECRET_KEY`. Never paste any of these into chat, a commit, an issue or
a GitHub secret. They live in Supabase only.

## 5. Set the three Supabase **function** secrets — test values **[owner, L3: T-068]**

Supabase dashboard → *Edge Functions → Secrets* (or the CLI):

```
supabase secrets set --project-ref uftancejftcryfvbggll \
  STRIPE_SECRET_KEY=sk_test_... \
  STRIPE_WEBHOOK_SECRET=whsec_... \
  STRIPE_PRICE_ID=price_...
```

`SUPABASE_URL`, `SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_ROLE_KEY` are
provided to functions automatically. `SITE_URL` is optional and defaults to
`https://cannonfightlab.com`.

What changes the moment this is done:

- **Checkout still refuses** (`503 checkout_disabled`) — lock 1 runs before the
  function reads any secret.
- **The webhook starts working**: a correctly signed **test-mode** event is
  processed and written to `profiles`. An unsigned one now gets `400` instead
  of `503 not_configured`. `.github/workflows/verify-billing-refusal.yml`
  already accepts either, so it stays green.

The functions are already deployed. If either is ever redeployed, the webhook
**must** keep JWT verification off — Stripe sends no Supabase JWT, and the
signature check is the authentication:

```
supabase functions deploy stripe-webhook --no-verify-jwt --project-ref uftancejftcryfvbggll
```

## 6. Make a test member

1. Sign up on the site with an address used only for this (e.g. a `+cfl-e2e`
   alias). Confirm the email.
2. During beta every account has `beta_premium = true`, which makes it Pro
   whatever Stripe says, so nothing could be observed. **For this one test
   account only**, in the Supabase SQL editor:

   ```sql
   update public.profiles set beta_premium = false
   where id = (select id from auth.users where email = '<the test address>');
   ```

   A member cannot do this to their own row — the profiles policy pins it — so
   it has to be done as the database owner. Do not run it for anyone else.

## 7. T-069 phase 1 — prove the webhook, on test keys

From a checkout of this repo, on any machine with Node 22:

```
STRIPE_SECRET_KEY=sk_test_... \
STRIPE_WEBHOOK_SECRET=whsec_... \
STRIPE_PRICE_ID=price_... \
CFL_TEST_EMAIL=<test address> CFL_TEST_PASSWORD=<its password> \
node build/stripe-test-e2e.js
```

It refuses (exit 2) unless the key starts with `sk_test_`, and if any live key
is anywhere in its environment. Then it checks the price is a test-mode
recurring price, checks the endpoint from step 3 exists and sends the right
events on a safe API version, signs in as the test member, asks for a
checkout, and replays signed subscription events against the **deployed**
webhook, reading `v_my_billing` after each:

| step | expected |
|---|---|
| checkout | **BLOCKED** — `checkout_disabled`, T-054/T-048. Correct while the locks hold |
| subscription created, active | Pro, renews at period end |
| updated to `past_due` (one failed card) | **still Pro** to the period end |
| updated, cancel at period end | Pro, flagged as ending |
| deleted, period over | Free |
| the first event delivered again | `duplicate_ignored`, still Free |
| forged signature | `400`, nothing changes |
| stale timestamp | `400`, nothing changes |

Exit 0 means every leg passed. It creates one Stripe **test** customer per run
and touches only the test member's row. Everything the harness does without a
network is already run on every push by `tests/stripe-webhook-offline.test.js`.

## 8. What phase 1 cannot prove

A real checkout session and a delivery signed **by Stripe** rather than by the
harness. The checkout function refuses until lock 1 comes off, so this is
phase 2, inside step 9, **still on test keys**.

## 9. The single go-live pull request **[owner approves and merges, L3: T-066]**

Only once T-054 and T-048 are resolved and recorded in `DECISIONS.md` with the
owner's own words. One pull request, and all of it in the diff:

1. `entitlements.js` — `CHECKOUT_BLOCKERS` emptied, each removal citing its
   resolved task; `PLANS[].amount_cents` set to the T-067 amount in cents.
2. `supabase/functions/stripe-checkout/index.ts` — its `CHECKOUT_BLOCKERS`
   emptied to match (`tests/billing-lifecycle.test.js` fails if the two
   disagree).
3. `pricing.html` — `#proCheckout` no longer `disabled` in the markup; the
   click handler posts to `stripe-checkout` with the member's session and
   follows the returned URL; `checkout_started` is emitted there and nowhere
   else. The Pro column stops saying "Not for sale".
4. The tests that pin "nothing can take money" are changed **in the same PR**,
   deliberately: the checkout-gate tests in `tests/entitlements.test.js` and
   `tests/billing-lifecycle.test.js`, and the null-amount test in
   `tests/pricing-config.test.js`.
5. `.github/workflows/verify-billing-refusal.yml` — the checkout assertions
   change from "503 `checkout_disabled`" to what an enabled function must
   still refuse: no `Authorization` header → `401 unauthenticated`, a bogus
   bearer token → `401`, `GET` → `405`. The webhook assertions tighten to
   unsigned → `400` and forged → `400` (no more `503`). Renaming it to
   "Verify billing gates" is part of the same diff.
6. If yearly is sold: the function change from step 2.
7. If the endpoint is on API version 2025-03-31 or later: the
   `current_period_end` fallback, in both copies.

Then, in order:

1. Merge with the **test** secrets from step 5 still set, and redeploy
   `stripe-checkout` (and `stripe-webhook --no-verify-jwt` if it changed).
   For this window the site sells only test mode: Stripe shows a TEST banner
   and only test cards work. Keep it short.
2. **T-069 phase 2:**
   `node build/stripe-test-e2e.js --require-checkout --wait-for-real-checkout`
   — it prints a `cs_test_` checkout URL; pay it with card
   `4242 4242 4242 4242`, any future expiry, any CVC. It passes when Stripe's
   own delivery switches the test member to Pro. Then cancel that test
   subscription in the dashboard.
3. Run *Actions → Verify billing refusal* (now "gates") by hand.
4. **Switch to live [owner]:** in live mode, repeat steps 2–4 (product, price,
   endpoint on the same URL, keys), then set the three secrets again with the
   `sk_live_` / live `whsec_` / live `price_` values. Run the verify workflow
   again.
5. First real purchase by the owner, on the owner's own card; check
   `account.html` shows it; refund it from the dashboard.

## 10. Turning it back off

- **Stop new checkouts:** put a blocker back in both `CHECKOUT_BLOCKERS` lists
  and redeploy `stripe-checkout`. It returns `503` again. Existing subscribers
  keep the access they paid for: the webhook keeps running.
- **Stop everything:** unset `STRIPE_SECRET_KEY` (checkout → `503
  not_configured`). Leave `STRIPE_WEBHOOK_SECRET` set while anyone holds a
  paid period, or cancellations and failed payments stop reaching their
  profiles.

## Not decided here

The price, the periods, a founding rate and what happens to it on lapse
(T-067); whether the beta grant ends when Pro launches; whether a lapsed
member's existing alerts keep emailing; and the T-061 boundary itself, drafted
in [`t061_pro_gates.DRAFT.sql`](t061_pro_gates.DRAFT.sql) and not applied
(D-019: no paywall before there is a way to pay).
