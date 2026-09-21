# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-21 (i) — The alert delivery test, and the email CFL has never sent

**From:** Claude
**To:** Owner
**Date:** 2026-09-21

PR #46 merged (`163f7e3`). The controlled delivery test ran against the real
database on `main`. **Nine of ten checks pass. The tenth cannot pass yet, and
the reason is bigger than this feature.**

### The blocker: the mailer has never been configured

**`RESEND_API_KEY` is not set on this repository.** The alert sender therefore
falls back to dry run and no email can leave. `RESEND_FROM` is unset too.

Checking `digest.yml` shows the same — `RESEND_API_KEY:` and `RESEND_FROM:`
both empty in its run environment. **No email has ever been sent from this
repo, the Cannon Card Brief included.** The Brief also reports
`0 active subscribers`, so it had nothing to send in any case, but the mailer
itself was never wired up and nothing ever said so out loud: `send-digest.js`
falls back to dry run silently by design.

The alert sender now prints which kind of dry run it is (`no RESEND_API_KEY —
the mailer is not configured` vs `ALERTS_DRY_RUN was set`) and whether
`RESEND_FROM` was set or defaulted. Presence only; no secret value is printed.
"Nothing was sent" had two very different causes and read identically.

### What did pass, against live data

| check | result |
|---|---|
| Dispatch connects to the real DB | **pass** — service key works |
| Candidate selection and refusals | **pass** — fired on a real 7.0-pt move over 3 matched books |
| Delivery row recorded | **pass** — `alert:5:seq:1`, payload snapshot matches the market exactly |
| Alert armed | **pass** — `fire_count=1`, `armed_value=7.002`, `fp=cd70918d88…` |
| `alert_fired` funnel event | **pass** — `srv:alerts`, `kind=market_move`, `seq=1` |
| Duplicate re-run does not resend | **pass** — `1 already_fired`, still 1 delivery / 1 event |
| **Re-arm across a cohort change** | **pass** — see below |
| Preference links resolve | **pass** — all three land on real pages; opt-out at `#prefs` |
| Cleanup | **pass** — alert and watchlist row gone, delivery row kept with `alert_id` NULL |
| **Exactly one email arrives** | **BLOCKED — no mailer** |

**The re-arm check is the one worth reading.** `armed_value` was forced to 0
against a live 7.0-point move — which clears the 3-point threshold twice over —
and only the cohort fingerprint was made not to match. The run reported
`0 fired · 1 re-baselined`, reason `cohort_changed_rebaselined`, and silently
restored the real fingerprint and value. The refusal that matters most is the
one that held under a condition designed to make it fire.

### A gap the test found

The alert email's primary call to action is *"Open this fight in Fight Lab"*,
and only `watchlist.html` handled `?src=alert`. **The click most likely to
happen was the one not counted**, so `alert_clicked` would have read as though
nobody engaged with alerts people were in fact opening. Fixed; the link now
carries `&kind` so the event can tell the two alert types apart. Still no
identifier of any kind in the URL.

### Still not settled, and not mine

**There is no one-click unsubscribe in the alert email.** It links to the
preferences panel, where `Alert emails: Off` is a working opt-out. For mail a
member explicitly configured, that is defensible as transactional — but whether
it needs a true one-click unsubscribe is a legal question, and it belongs with
T-048 rather than with me inventing a requirement.

## Next action

**Owner:** add `RESEND_API_KEY` and `RESEND_FROM` as repository secrets, with a
Resend-verified sender domain. Then say so and the exact sequence above re-runs
with `dry_run: false` for you to confirm receipt. **Until that passes the
schedule stays off (T-073) and the feature is not production-ready.**

Note the clock: the test fight sat at ~530 minutes against a 1440-minute
movement ceiling, so it stops being a valid candidate roughly 15 hours after
this entry. After that the re-test needs a fresh capture or a different fight.

**Nobody:** turns the cron back on before that test passes.

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
