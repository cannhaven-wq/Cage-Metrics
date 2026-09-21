# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-21 (h) — Watchlists and alerts, and an alert that would rather say nothing

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-21

PR #45 merged (`7edd4e3`). Step 9 of the resequenced order — watchlists and
alerts — is done. [D-020](DECISIONS.md), T-070 / T-071 / T-072.

**There is now no unblocked build work left in the sequence.** Steps 2–5 are
yours and a lawyer's, step 6 needs your Stripe keys, and step 7 is gated behind
all of them.

### Read this first: a P0-class grant defect, and two inert protections

`REVOKE ALL ... FROM anon` left **`authenticated` holding TRUNCATE** on three of
the four new tables, inherited from Supabase's default privileges. **TRUNCATE
bypasses row level security entirely** — any signed-in member could have emptied
every other member's watchlist and alerts, with RLS never consulted. Same shape
as the `funnel_events` finding, and found the same way: by querying
`role_table_grants` after applying rather than by reading the migration.

Two further faults, both in the trigger pinning the suppression memory, both
found by testing behaviour rather than reading code:

1. It keyed on `auth.role()`, the JWT claim. A migration or psql session has no
   JWT, so it reverted **the sender's own writes** — alerts would never arm.
2. The fix used `current_user` but was `SECURITY DEFINER`, where `current_user`
   is the function's **owner**. The guard was always true: the protection read
   as though it worked and **did nothing at all**.

All three closed and verified as the `authenticated` role in a rolled-back
transaction.

### The rule the feature is built around

**An alert must never fire from a comparison CFL would refuse to print.** An
email is a stronger claim than a number on a page: the member did not go looking
for it, and it may send them to a sportsbook to act.

**The matched-cohort methodology is preserved and extended.** A movement alert
stores the **fingerprint** of the cohort it fired over — an md5 of the sorted
matched book ids, *not the count*, because one book leaving as another joins
holds the count still and moves the median. If the fingerprint or the baseline
changes, the alert **re-baselines and stays silent**. Subtracting two medians
over different book sets is the D-012 error, measured at up to 12.7 points.

### The finding that changed the design

The first version applied **one 45-minute staleness ceiling** to both kinds of
alert, borrowed from the frozen CLV limit. Against CFL's real capture cadence —
5 min only in flow, hourly on card day, otherwise **once a day** — that makes
**0 of 79 fights alertable**. Measured on the live table. The feature would have
shipped permanently silent, and a silent alert system is indistinguishable from
a broken one.

A price and a move are different claims and cannot share a rule: **a price is an
offer** (120 min, inside the hourly fight-week tier) and **a move is a
historical fact** (24 h). Alerts are inherently a fight-week feature; outside it
they correctly say nothing.

### Suppression

A **UNIQUE dedupe key claimed before the email is sent** — send-then-record
loses the record on a crash and re-sends forever; this way a crash costs one
email a member should have had rather than an unbounded number they should not.
The key is the alert plus its occurrence number, never the value, because keying
on the value mints a fresh key every tick. Then **one email per member per run**
rather than per alert, a cooldown, a daily cap, and quiet hours that stay
**off** until a time zone is collected rather than guessed.

### Verified

52 new assertions in `tests/alerts.test.js`, 20 suites green. The evaluator was
run against **live rows** from `v_fight_alert_market`: the biggest real move
(7.0 pts over 3 matched books) fires at a 3-point threshold, refuses to re-arm
after a cohort change, and every price alert is correctly refused as
`stale_for_price` at 8.6 hours old.

**Not verified, and it cannot be from here:** `build/send-alerts.js` has never
actually sent an email. This environment has no secrets and its network policy
blocks the Supabase host, so the sender can only run in CI. `alerts.yml` is
manually dispatchable with `dry_run` defaulting to **true**.

## Next action

**Owner:** dispatch **Send market alerts** with `dry_run: true` once this
merges, and read the log — it prints every refusal and its count. Then steps 2–5
of [D-019](DECISIONS.md), which nothing else moves without. Cheapest first is
**T-054**: one disclosure clause, draft already written.

**ChatGPT:** review the re-arm rule in `alerts.js::evaluate` specifically for a
case where re-baselining silently is the wrong call, and the two staleness
ceilings against what the odds cadence actually delivers in a fight week.

**Nobody:** relaxes a refusal to make an alert fire, or turns the quota into a
Pro gate before step 7.

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
