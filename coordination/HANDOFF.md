# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-21 (g) — No paywall before there is a way to pay

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-21

PR #44 merged (`68a6a5a`). The Stripe backbone is on `main` and
`verify-billing-refusal.yml` is now dispatchable from its permanent home.

**The owner resequenced the remaining work** ([D-019](DECISIONS.md)).
Free-vs-Pro enforcement used to sit immediately after Stripe; it now sits
behind the gates that make paying possible.

| # | step | whose | state |
|---|---|---|---|
| 1 | Stripe backbone (#44) | Claude | **done** |
| 2 | **T-054** privacy names the analytics processor | Owner + lawyer | blocked on legal |
| 3 | **T-048** Terms of Service exists | Owner + lawyer | blocked on legal |
| 4 | **T-067** set the price | Owner (L3) | not set |
| 5 | **T-068** Stripe account, product, secrets | Owner | no account connected |
| 6 | **T-069** checkout in Stripe test mode | Claude | blocked on 4–5 |
| 7 | **T-061** apply the Free/Pro boundary | Claude | moved here |
| 8 | **T-066** turn checkout live | Owner (L3) | blocked on 2–7 |
| 9 | watchlists / movement alerts | Claude | **unblocked** |

**It is not only about courtesy to the member.** A paywall in front of a
product with no checkout is a dead end — the member meets a wall and the door
behind it does not exist. It also destroys the one measurement the funnel
instrumentation was built to take: `paywall_hit` means something when a
purchase is possible and nothing when it is not, and a month of unbuyable
paywall hits is a baseline nobody can read afterwards.

**Nothing about the blockers changed.** T-054 and T-048 are still checkout
blockers, `entitlements.js::CHECKOUT_BLOCKERS` is untouched, and
`stripe-checkout` still returns 503 before it authenticates anyone. Moving
step 7 later makes 7 and 8 independent, which they always should have been.

### The drafter's brief was out of date, and now is not

`legal-review/PROPOSED_WORDING.md` told a drafter that subscription terms were
"none of this is decided". That was true when it was written and false the
moment #44 merged: billing period, renewal, cancellation, failed payment and
expiry are now shipped, tested behaviour. The file carries a new **"How billing
actually behaves"** section so the Terms can describe the system rather than
guess at it — cancellation taking effect at period end, a failed payment not
cutting access off immediately, access ending automatically on expiry, an
unrecognised state ending access rather than continuing it.

Two things flagged so a drafter cannot over-promise: **no trial is
implemented**, and **nothing in the system issues a refund**. If the Terms
promise one, it is a manual process today.

Still outside production. `privacy.html` and `disclaimer.html` remain untouched.

### On the price

The owner's stated default is ~$9.99–$11.99 monthly, $79–$99 annually, with a
founding rate for the first cohort. **Recorded as a preference, not set**
(T-067). No number is configured and `STRIPE_PRICE_ID` is unset. Three things
it implies are also undecided and are now flagged for the drafter: whether both
periods are sold, whether the founding rate is for life or for a term, and what
happens to it on lapse and resubscription — which interacts with the undecided
question of what the beta grant obliges.

## Next action

**Owner:** steps 2–5 are yours and nothing downstream moves without them. The
cheapest one to clear first is **T-054** — it is a single disclosure clause and
the draft is already written; T-048 is the larger piece.

**Claude:** step 9 (watchlists / movement alerts) is the only unblocked build
work in the sequence. Do not start T-061 — it is deliberately behind the
payment gates now.

**Nobody:** removes a blocker to make something pass, or sets a price to unblock
themselves.

---

## 2026-09-21 (f) — The subscription is built, and the front door is bolted

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-21

PR #43 merged (`97ec5b4`). Item 5 of the monetization sequence — Stripe and
pricing — is done. [D-018](DECISIONS.md), T-063 / T-064 / T-065.

**CFL cannot take a penny, and that is a control rather than a note.**

### Read this first: what stops the money

Three locks, in the order of what actually holds:

1. **The deployed `stripe-checkout` function returns 503 `checkout_disabled`
   with T-054 and T-048 named — before it authenticates the caller and before
   it reads any configuration.** The browser is not a security boundary, so
   this is the one that matters.
2. **`pricing.html` ships the Subscribe button `disabled` in the served HTML**,
   not disabled by JavaScript afterwards. JS can fail to load; a button that is
   live for 200 ms is a button that can be clicked.
3. **The page reads that state from `entitlements.js::CHECKOUT_BLOCKERS`** and
   holds no opinion of its own, so removing a blocker moves the page and
   hardcoding "enabled" cannot happen quietly.

A fourth, by accident of having nothing: `STRIPE_SECRET_KEY`,
`STRIPE_WEBHOOK_SECRET` and `STRIPE_PRICE_ID` are unset and both functions fail
closed. **Not counted as a lock** — it disappears the moment a key is added for
testing.

**Verified, not asserted.** `.github/workflows/verify-billing-refusal.yml`
posts to both live endpoints and fails if either answers with anything but a
refusal, including a forged webhook signature that must never return 200. It
needs no secret (the project URL and publishable key are already committed) and
runs with `contents: read`. The agent environment's network policy blocks the
Supabase host, so this has to run in CI to run at all.

### The lifecycle

`billing-lifecycle.js` is a pure function — no network, no database, no Stripe
SDK — and `tests/billing-lifecycle.test.js` drives **signup → checkout →
activation → renewal → failed payment → cancellation → expiry → lapse →
resubscription** offline, 39 assertions. Then the same sequence was run against
the real database in a rolled-back transaction: `free, pro, pro, pro, pro, free,
free, pro`.

The four rules that are money-shaped:

- **`past_due` keeps access to the end of the period.** One failed card payment
  must not cut a paying member off while Stripe is still retrying.
- **`canceled` keeps access to the end of the period, then stops.** They paid
  for it. They do not get the next one.
- **`unpaid` / `incomplete` / `incomplete_expired` / `paused` end access now.**
- **An unrecognised status ends access.** "Probably fine" is how a lapsed
  member keeps a subscription forever.

**`checkout.session.completed` never grants entitlement** — it only links the
Stripe customer id. Entitlement comes from subscription events alone.

**Idempotency is a UNIQUE constraint on `stripe_event_id`, not a check**, and the
insert happens first: Stripe delivers at least once, and two concurrent
deliveries both pass a `SELECT`-then-`INSERT`. A `23505` returns 200
`duplicate_ignored`. Status codes are flow control — 400 for a bad signature,
500 for a real write failure so Stripe retries, 200 for understood-but-not-
appliable with the reason recorded in `billing_events`.

**The lifecycle rules are duplicated inside the webhook** because an edge
function cannot import from the repo root at deploy time. A test asserts the two
copies agree.

### Two defects found on the way

**`pricing.html` was serving broken markup.** `<footer</div>` — a stray unclosed
tag, live on `main`, which browsers recover from by opening a bogus `<footer>`
wrapping the rest of the page including the real one.

**`account.html` called every beta member "Free".** It derived the tier from
`profiles.tier` alone; during beta `tier` is `'free'` for everyone and
`beta_premium` is what makes them premium, so the account page contradicted the
rest of the site for **every account holder**. It now reads `v_my_billing` and
phrases the state through the shared state machine, and it stopped promising that
billing "launches soon", which is a date nobody has.

### What was deliberately not done

- **The Free/Pro boundary is not enforced.** Every `SURFACES` row still carries
  `enforced: false`. Nothing is behind a paywall. That is item 6.
- **No price is set.** `CRITICAL_GATES.md` item 7 makes pricing L3; the range on
  `pricing.html` is the owner's existing copy, unchanged.
- **`privacy.html` and `disclaimer.html` untouched.** Draft wording stays in
  `legal-review/PROPOSED_WORDING.md`, outside production.
- **T-058 (card-wide charts) not started**, per the owner.

### One thing to watch

The self-referential copy guard has now bitten **five times** in this repo: a
ban list containing the banned phrase, a `//` comment explaining a ban, a
shipped `COMMENT ON` string, `document.body.textContent` including inline
`<script>` text, and this sprint a comment explaining that
`cfl.EVENTS.checkout_started` is *not* emitted, which tripped the test asserting
it is not emitted. Every copy assertion in this repo should read **stripped,
visible text**. It is worth a written convention rather than a sixth discovery.

## Next action

**Owner:** decide whether to run item 6 — the Free/Pro boundary — next, or to
hold it until T-048 and T-054 clear. Enforcing a paywall before there is any way
to pay for it means a member can hit a wall with no door in it, which is a worse
first impression than a free board. The build order the owner locked puts
enforcement after Stripe, and Stripe is now done, so this is genuinely the next
item; the question is only whether it lands before or after the legal work.

**ChatGPT:** review `billing-lifecycle.js` against the Stripe status model
specifically for statuses CFL has not enumerated, and review whether
`past_due` keeping access to period end is the right call for CFL's price point.

**Nobody:** removes an entry from `CHECKOUT_BLOCKERS` to make something pass.
T-066 is the L3 that turns checkout on, and it is the owner's.

---

## 2026-09-21 (e) — Entitlement moves into Postgres, and a P0 came with it

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-21

PR #42 merged (`ce2c55c`). Item 4 of the monetization sequence — auth + Pro
entitlements — is done. [D-017](DECISIONS.md), T-059 / T-060.

### Read this first: a live privilege escalation, now closed

The `profiles` UPDATE policy pinned `tier`, `tier_expires_at` and
`stripe_customer_id`. It did **not** pin `is_admin` or `beta_premium`.
`current_user_is_admin()` reads `is_admin`, and that function *is* the SELECT
policy on `fight_odds` and `odds_books`; `email_subscribers` checks it
directly. **Any signed-in user could make themselves an admin and read every
subscriber's email address.**

`_auth.js` strips those fields client-side and said "RLS will reject anyway".
It did not — and the publishable key is public by design, so the REST endpoint
never needed our JavaScript.

Fixed and **verified as the `authenticated` role in a rolled-back
transaction**: both escalations now fail 42501, ordinary profile edits still
work. A sweep of every other UPDATE/INSERT policy found **no second instance**.
Treated as L0 and executed rather than queued; the reasoning is in D-017.

Worth knowing: the first version of that verification was **confounded** —
`beta_premium` is `true` for everyone during beta, so setting it to `true` is a
no-op, not an escalation, and it read as a false failure until the test flipped
the value instead. The empirical check was right to be run and wrong on the
first pass.

### The entitlement layer

`current_user_entitlement()` (`free | pro`) and `current_user_is_pro()` —
`SECURITY DEFINER`, pinned `search_path`, safe in RLS. `v_my_entitlement` gives
the browser its own standing and no one else's. Verified across six cases
including **paid-but-expired → free**.

That last one is a second bug fixed: `tier_expires_at` was honoured nowhere, so
a lapsed subscription would have kept access indefinitely. Free today, because
nobody has paid; expensive on the first renewal failure.

### Nothing is gated, and checkout is blocked in code

Every surface is `enforced: false`. Applying the boundary is step 5, after
Stripe. When a gate lands it goes in a view or policy calling
`current_user_is_pro()`, never an `if (cflAuth.isPro())` around a fetch.

`entitlements.js::CHECKOUT_BLOCKERS` names **T-054** and **T-048**;
`checkoutMayBeEnabled()` is false while either stands and a test fails if a
checkout entry point ships. Auth, pricing and Stripe wiring can all be built
meanwhile — only taking money is blocked, which is what the owner asked for.
**Turning checkout on now means deleting a named legal blocker**, deliberately.

### Verified

13 Node suites, **315 assertions**; 168 Python tests, 4,369 subtests. All green.

### Next action

**Stripe + pricing** (item 5 in the owner's ordering of the remaining work),
built against `current_user_is_pro()` and behind the checkout gate. Then apply
the Free/Pro boundary (**T-061**), then watchlists and alerts.

**Owner:** T-054 and T-048 are now the literal blocker on revenue, not a note —
the code will not let checkout ship until they are resolved. Draft wording and
the open legal questions: [`legal-review/PROPOSED_WORDING.md`](../legal-review/PROPOSED_WORDING.md).

---
