/* ==========================================================================
   tests/billing-lifecycle.test.js — the whole subscription lifecycle, driven.

   Signup, checkout, webhook, activation, renewal, cancellation, expiry,
   failed renewal and reinstatement — every one of them, with no Stripe
   account in existence. That is the reason the lifecycle lives in a pure
   function: the part of a payment system that is hardest to test is the part
   that costs the most when it is wrong, so it is the part that must be
   testable offline.

   The money-shaped failures this is written to catch:

     - a cancelled member losing access they have already paid for
     - a lapsed member keeping access forever
     - one failed card payment cutting someone off instantly
     - a retried webhook applying the same event twice
     - an unknown Stripe status being treated as "probably fine"

   Run:  node tests/billing-lifecycle.test.js
   ========================================================================== */

'use strict';
const fs = require('fs');
const path = require('path');

const root = f => path.join(__dirname, '..', f);
const read = f => fs.readFileSync(root(f), 'utf8');

const B = require('../billing-lifecycle.js');
const E = require('../entitlements.js');
const WEBHOOK = read('supabase/functions/stripe-webhook/index.ts');
const CHECKOUT = read('supabase/functions/stripe-checkout/index.ts');
const MIGRATION = read('billing_migration.sql');
const PRICING = read('pricing.html');
const ACCOUNT = read('account.html');
const WORKFLOW = read('.github/workflows/verify-billing-refusal.yml');

// Visible page text only: an HTML comment or an inline script explaining a ban
// must not read as the page committing the thing it bans. This has bitten four
// times in this repo, so the copy assertions below read stripped text.
const visible = html => html
  .replace(/<!--[\s\S]*?-->/g, ' ')
  .replace(/<script[\s\S]*?<\/script>/gi, ' ')
  .replace(/<style[\s\S]*?<\/style>/gi, ' ')
  .replace(/<[^>]+>/g, ' ');

let passed = 0;
const failures = [];
function t(name, fn) {
  try { fn(); passed++; } catch (e) { failures.push(name + ' — ' + e.message); }
}
function ok(cond, msg) { if (!cond) throw new Error(msg); }
function eq(a, b, msg) {
  if (a !== b) throw new Error((msg || 'value') + ': expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a));
}

// A fixed clock, so "expired" and "still running" mean something exact.
const NOW = Date.parse('2026-10-01T12:00:00Z');
const unix = isoStr => Math.floor(Date.parse(isoStr) / 1000);
const FUTURE = unix('2026-11-01T12:00:00Z');   // a month of paid period left
const PAST = unix('2026-09-01T12:00:00Z');     // a month expired

const ev = (type, object, id) => ({ id: id || 'evt_test', type, data: { object } });
const sub = over => Object.assign({
  id: 'sub_1', customer: 'cus_1', status: 'active',
  current_period_end: FUTURE, cancel_at_period_end: false,
  metadata: { cfl_user_id: 'user-uuid-1' }
}, over || {});

/* ======================================================================
   1. SIGNUP AND ACTIVATION
   ====================================================================== */

t('checkout completion links the customer but does NOT grant access', () => {
  // The session may arrive before or after the subscription object, and only
  // the subscription carries the period dates. Entitling here would mean
  // guessing an expiry.
  const d = B.decide(ev('checkout.session.completed', {
    mode: 'subscription', customer: 'cus_1', subscription: 'sub_1',
    client_reference_id: 'user-uuid-1'
  }), NOW);
  eq(d.action, 'link', 'action');
  eq(d.tier, null, 'checkout granted a tier without knowing the period');
  eq(d.userId, 'user-uuid-1', 'userId');
  eq(d.customerId, 'cus_1', 'customerId');
});

t('a one-off payment checkout is not mistaken for a subscription', () => {
  const d = B.decide(ev('checkout.session.completed', { mode: 'payment', customer: 'cus_1' }), NOW);
  eq(d.action, 'ignore', 'a non-subscription checkout was acted on');
});

t('the subscription becoming active grants Pro to the period end', () => {
  const d = B.decide(ev('customer.subscription.created', sub()), NOW);
  eq(d.action, 'apply', 'action');
  eq(d.tier, 'premium', 'tier');
  eq(d.expiresAt, new Date(FUTURE * 1000).toISOString(), 'expiry is not the period end');
  eq(d.subscriptionStatus, 'active', 'status');
});

t('a trial grants Pro', () => {
  const d = B.decide(ev('customer.subscription.updated', sub({ status: 'trialing' })), NOW);
  eq(d.tier, 'premium', 'a trialing member was not given access');
});

/* ======================================================================
   2. RENEWAL
   ====================================================================== */

t('renewal extends the expiry to the new period end', () => {
  const later = unix('2026-12-01T12:00:00Z');
  const d = B.decide(ev('customer.subscription.updated', sub({ current_period_end: later })), NOW);
  eq(d.expiresAt, new Date(later * 1000).toISOString(), 'the expiry did not move to the new period');
  eq(d.tier, 'premium', 'tier');
});

t('invoice events never set entitlement themselves', () => {
  // They accompany a subscription.updated carrying the authoritative dates.
  // Acting on both is two writes racing to say the same thing.
  ['invoice.paid', 'invoice.payment_succeeded', 'invoice.payment_failed'].forEach(type => {
    const d = B.decide(ev(type, { subscription: 'sub_1', customer: 'cus_1' }), NOW);
    eq(d.action, 'note', type + ' action');
    eq(d.tier, null, type + ' set a tier');
  });
});

/* ======================================================================
   3. FAILED RENEWAL — the one most likely to be got wrong
   ====================================================================== */

t('ONE failed payment does not cut a member off', () => {
  // Stripe moves to past_due and keeps retrying. Cutting access at the first
  // failed charge punishes an expired card.
  const d = B.decide(ev('customer.subscription.updated', sub({ status: 'past_due' })), NOW);
  eq(d.tier, 'premium', 'a past_due member lost access immediately');
  eq(d.expiresAt, new Date(FUTURE * 1000).toISOString(), 'past_due did not keep the paid period');
});

t('past_due stops mattering once the paid period ends', () => {
  // No separate grace timer: the expiry does the work.
  const d = B.decide(ev('customer.subscription.updated', sub({ status: 'past_due', current_period_end: PAST })), NOW);
  eq(d.expiresAt, new Date(PAST * 1000).toISOString(), 'expiry');
  // The tier is still premium, but the expiry is in the past — and
  // current_user_entitlement() reads free from that. Asserted below.
  ok(Date.parse(d.expiresAt) < NOW, 'the expiry is not actually in the past');
});

t('Stripe giving up (unpaid) ends access immediately', () => {
  const d = B.decide(ev('customer.subscription.updated', sub({ status: 'unpaid' })), NOW);
  eq(d.tier, 'free', 'an unpaid subscription kept access');
  eq(d.expiresAt, null, 'an unpaid subscription kept an expiry');
});

t('a first payment that never succeeded grants nothing', () => {
  ['incomplete', 'incomplete_expired'].forEach(status => {
    const d = B.decide(ev('customer.subscription.updated', sub({ status })), NOW);
    eq(d.tier, 'free', status + ' granted access');
  });
});

/* ======================================================================
   4. CANCELLATION AND EXPIRY
   ====================================================================== */

t('cancelling keeps the access already paid for', () => {
  // The member has paid through a date. They are owed it.
  const d = B.decide(ev('customer.subscription.deleted', sub({ status: 'canceled' })), NOW);
  eq(d.tier, 'premium', 'a cancelled member lost access they had paid for');
  eq(d.expiresAt, new Date(FUTURE * 1000).toISOString(), 'expiry');
  eq(d.reason, 'canceled_but_period_paid', 'reason');
});

t('cancel-at-period-end is still active access, and is flagged as ending', () => {
  const d = B.decide(ev('customer.subscription.updated', sub({ cancel_at_period_end: true })), NOW);
  eq(d.tier, 'premium', 'tier');
  eq(d.cancelAtPeriodEnd, true, 'the ending flag was lost, so the UI would say "renews"');
});

t('once the period has ended, cancellation means free', () => {
  const d = B.decide(ev('customer.subscription.deleted', sub({ current_period_end: PAST })), NOW);
  eq(d.tier, 'free', 'an expired cancelled member kept access');
  eq(d.reason, 'canceled_period_over', 'reason');
});

t('deletion means cancelled whatever the payload status says', () => {
  const d = B.decide(ev('customer.subscription.deleted', sub({ status: 'active', current_period_end: PAST })), NOW);
  eq(d.tier, 'free', 'a deleted subscription was read as active and kept access');
});

/* ======================================================================
   5. REINSTATEMENT
   ====================================================================== */

t('resubscribing after cancelling restores access', () => {
  const after = unix('2027-01-01T12:00:00Z');
  const d = B.decide(ev('customer.subscription.created', sub({ id: 'sub_2', status: 'active', current_period_end: after })), NOW);
  eq(d.tier, 'premium', 'tier');
  eq(d.subscriptionId, 'sub_2', 'the new subscription id was not picked up');
});

/* ======================================================================
   6. THINGS THAT MUST NOT HAPPEN
   ====================================================================== */

t('an unknown status never grants access', () => {
  ['', 'weird', 'ACTIVE', 'active ', null, undefined].forEach(status => {
    const d = B.decide(ev('customer.subscription.updated', sub({ status })), NOW);
    eq(d.tier, 'free', 'status ' + JSON.stringify(status) + ' granted access');
  });
});

t('an unhandled event type is acknowledged and does nothing', () => {
  // A webhook that throws on an unexpected type makes Stripe retry forever.
  const d = B.decide(ev('customer.source.expiring', { customer: 'cus_1' }), NOW);
  eq(d.action, 'ignore', 'action');
  eq(d.tier, null, 'tier');
});

t('decide() never throws, on anything', () => {
  [null, undefined, {}, { type: 'x' }, { type: 'customer.subscription.updated' },
   { type: 'customer.subscription.updated', data: {} },
   { type: 'customer.subscription.updated', data: { object: null } }]
    .forEach(bad => {
      let threw = false;
      try { B.decide(bad, NOW); } catch (e) { threw = true; }
      ok(!threw, 'decide() threw on ' + JSON.stringify(bad));
    });
});

t('a member id is never guessed from an email', () => {
  const d = B.decide(ev('customer.subscription.updated', sub({ metadata: {}, customer_email: 'a@b.com' })), NOW);
  eq(d.userId, null, 'a user id was inferred from something other than our own metadata');
});

/* ======================================================================
   7. THE WEBHOOK WRAPPER'S OWN GUARANTEES
   ====================================================================== */

t('the webhook verifies the Stripe signature before anything else', () => {
  ok(/verifyStripeSignature/.test(WEBHOOK), 'no signature verification');
  ok(/TOLERANCE_SECONDS/.test(WEBHOOK), 'no replay window — a captured request would work forever');
  ok(/timingSafeEqual/.test(WEBHOOK), 'the signature is compared with ===, which leaks timing');
  ok(/crypto\.subtle\.importKey/.test(WEBHOOK), 'the HMAC is not computed with Web Crypto');
  const sigIdx = WEBHOOK.indexOf('verifyStripeSignature(raw');
  const writeIdx = WEBHOOK.indexOf("from('profiles')");
  ok(sigIdx > 0 && writeIdx > sigIdx, 'a profile write happens before the signature check');
});

t('the webhook fails CLOSED when unconfigured', () => {
  ok(/if \(!WEBHOOK_SECRET \|\| !SERVICE_KEY \|\| !SUPA_URL\)/.test(WEBHOOK),
     'the webhook does not check its own configuration');
  ok(/not_configured', \{ status: 503 \}/.test(WEBHOOK),
     'an unconfigured webhook does not refuse — it would tell Stripe events were handled');
});

t('the webhook dedupes on the Stripe event id before applying', () => {
  ok(/stripe_event_id/.test(WEBHOOK), 'no event id recorded');
  ok(/23505/.test(WEBHOOK), 'the unique-violation path is not handled, so retries double-apply');
  ok(/duplicate_ignored', \{ status: 200 \}/.test(WEBHOOK), 'a duplicate is not acknowledged');
  ok(/stripe_event_id text\s+NOT NULL UNIQUE/.test(MIGRATION),
     'billing_events.stripe_event_id is not UNIQUE, so dedupe cannot work');
});

t('the webhook asks Stripe to retry only when WE failed', () => {
  ok(/record_failed', \{ status: 500 \}/.test(WEBHOOK), 'a failed record does not ask for a retry');
  ok(/write_failed', \{ status: 500 \}/.test(WEBHOOK), 'a failed write does not ask for a retry');
  ok(/deferred', 'no_member_matched_yet'/.test(WEBHOOK),
     'an unmatched member is not deferred — retrying will not make them appear');
});

t('the webhook and the pure module agree on the rules', () => {
  // The edge function cannot import from the repo root, so the rules are
  // duplicated. If they drift, the tested behaviour is not the deployed one.
  B.STATUS_KEEPS_PERIOD.forEach(s => ok(WEBHOOK.indexOf("'" + s + "'") !== -1,
    'the webhook does not list keep-period status ' + s));
  B.STATUS_ENDS_NOW.forEach(s => ok(WEBHOOK.indexOf("'" + s + "'") !== -1,
    'the webhook does not list ends-now status ' + s));
  B.HANDLED.forEach(e => ok(WEBHOOK.indexOf("'" + e + "'") !== -1,
    'the webhook does not handle ' + e));
  ok(/canceled_but_period_paid/.test(WEBHOOK), 'the webhook lost the paid-period rule');
  ok(/const PRO_TIER = 'premium'/.test(WEBHOOK), 'the webhook writes a different tier value');
});

/* ======================================================================
   8. CHECKOUT IS BLOCKED, SERVER-SIDE
   ====================================================================== */

t('the checkout function refuses before it does anything else', () => {
  const gateIdx = CHECKOUT.indexOf('CHECKOUT_BLOCKERS.length > 0');
  const stripeIdx = CHECKOUT.indexOf('api.stripe.com');
  ok(gateIdx > 0, 'there is no blocker gate in the checkout function');
  ok(stripeIdx > gateIdx, 'Stripe is called before the blocker gate');
  // json() takes the status positionally, so the gate reads `}, 503);`
  ok(/\}, 503\);/.test(CHECKOUT.slice(gateIdx, gateIdx + 400)),
     'the gate does not return 503 — it must refuse, not fall through');
  ok(/checkout_disabled/.test(CHECKOUT.slice(gateIdx, gateIdx + 400)),
     'the refusal does not name itself');
  ['T-054', 'T-048'].forEach(id =>
    ok(CHECKOUT.indexOf(id) !== -1, 'the gate does not name ' + id));
});

t('the server-side gate matches the client-side one', () => {
  E.CHECKOUT_BLOCKERS.forEach(b =>
    ok(CHECKOUT.indexOf(b.id) !== -1,
       'entitlements.js blocks on ' + b.id + ' but the edge function does not'));
  eq(E.checkoutMayBeEnabled(), false, 'the client gate is open while the server gate is shut');
});

t('checkout fails closed without configuration, and never sells twice', () => {
  ok(/!STRIPE_SECRET_KEY \|\| !STRIPE_PRICE_ID/.test(CHECKOUT), 'no configuration check');
  ok(/already_subscribed/.test(CHECKOUT), 'an existing subscriber can be sold a second subscription');
  ok(/Idempotency-Key/.test(CHECKOUT), 'a double-clicked button can create two sessions');
  ok(/unauthenticated/.test(CHECKOUT), 'checkout does not require a signed-in member');
});

/* ======================================================================
   9. THE WRITE PATH IS CLOSED TO MEMBERS
   ====================================================================== */

t('billing_events is service_role only', () => {
  ok(/ENABLE ROW LEVEL SECURITY/.test(MIGRATION), 'RLS is not enabled on billing_events');
  ok(/REVOKE ALL ON public\.billing_events FROM anon, authenticated/.test(MIGRATION),
     'members are not revoked from billing_events');
  ok(!/CREATE POLICY[^;]*ON public\.billing_events/.test(MIGRATION),
     'a policy on billing_events would open it to a member role');
});

t('the new subscription columns are pinned in the profiles policy', () => {
  // T-059's lesson: a WITH CHECK protects exactly the columns it names, so
  // columns are pinned in the same migration that creates them.
  ['stripe_subscription_id', 'subscription_status', 'cancel_at_period_end'].forEach(col => {
    ok(new RegExp('ADD COLUMN IF NOT EXISTS ' + col).test(MIGRATION), col + ' is not added here');
    ok(new RegExp(col + '\\s+IS NOT DISTINCT FROM').test(MIGRATION),
       col + ' is created but NOT pinned — a member could set their own subscription state');
  });
});

t('entitlement still comes from one place', () => {
  ok(/current_user_entitlement/.test(MIGRATION),
     'the billing layer does not defer to the existing entitlement function');
  ok(!/CREATE OR REPLACE FUNCTION public\.current_user_entitlement/.test(MIGRATION),
     'the billing migration redefines the entitlement rule — there must be only one');
});

/* ==========================================================================
   WHAT THE MEMBER IS TOLD. describe() is the only sentence a member ever reads
   about their own money, and it had no test at all. Each case below is a thing
   it would be unfair, or wrong, to say.
   ========================================================================== */

t('a billing date is readable and pinned to UTC', () => {
  // Stripe periods land on midnight UTC. Formatted in local time, a member
  // west of Greenwich is shown the day BEFORE their access ends.
  eq(B.formatDay('2026-10-21T00:00:00Z'), 'October 21, 2026', 'period end');
  eq(B.formatDay(null), null, 'a missing date must not become today');
  eq(B.formatDay('not a date'), null, 'an unparseable date must not become a day');
});

t('a beta member is never told they are paying', () => {
  const d = B.describe({ is_beta: true, entitlement: 'pro' });
  ok(/beta/i.test(d.head + d.body), 'beta is not named');
  ok(/nothing is charged|no card/i.test(d.body), 'it does not say nothing is charged');
  ok(!/renew|payment|invoice/i.test(d.body), 'it implies a payment: ' + d.body);
});

t('a failed payment does not read as a cancellation', () => {
  const d = B.describe({ subscription_status: 'past_due', current_period_end: '2026-10-05T00:00:00Z' });
  ok(/October 5, 2026/.test(d.body), 'the date a member keeps access to is not shown');
  ok(/keep access|retry/i.test(d.body), 'it does not say access continues while Stripe retries');
  ok(!/ended|cancelled|canceled/i.test(d.head + d.body),
     'a retrying payment is described as an ending: ' + d.head);
});

t('a cancelling member is told they keep what they paid for', () => {
  const d = B.describe({ subscription_status: 'active', cancel_at_period_end: true,
                         current_period_end: '2026-10-21T00:00:00Z' });
  ok(/October 21, 2026/.test(d.head + d.body), 'the end date is missing');
  ok(/paid for it|continues until/i.test(d.body), 'it does not say access continues: ' + d.body);
});

t('a lapsed member is not told they still have access', () => {
  const past = { subscription_status: 'canceled', current_period_end: '2026-01-01T00:00:00Z' };
  const d = B.describe(past, Date.parse('2026-09-21T00:00:00Z'));
  eq(d.head, 'Free account', 'a lapsed member is not on the free plan');
  ok(!/continues|until/i.test(d.body), 'it still promises access: ' + d.body);

  const future = { subscription_status: 'canceled', current_period_end: '2026-12-01T00:00:00Z' };
  const d2 = B.describe(future, Date.parse('2026-09-21T00:00:00Z'));
  ok(/December 1, 2026/.test(d2.head + d2.body),
     'a cancelled member inside a paid period is cut off early: ' + JSON.stringify(d2));
});

t('an unknown status says free rather than guessing', () => {
  const d = B.describe({ subscription_status: 'some_status_stripe_added_later' });
  eq(d.head, 'Free account', 'an unrecognised status was described as paid');
});

t('no billing sentence sells anything', () => {
  const all = ['active', 'trialing', 'past_due', 'canceled', 'unpaid', 'incomplete', null]
    .map(st => B.describe({ subscription_status: st, current_period_end: '2026-10-21T00:00:00Z' }))
    .concat([B.describe({ is_beta: true })]);
  all.forEach(d => {
    const txt = (d.head + ' ' + d.body).toLowerCase();
    ['upgrade now', 'don\'t miss', 'act fast', 'limited time', 'best value']
      .forEach(phrase => ok(txt.indexOf(phrase) === -1, 'billing copy touts: ' + phrase));
    ok(d.head && d.body, 'a billing state has no sentence');
  });
});

/* ==========================================================================
   THE SURFACES. A passing state machine is worth nothing if a page can put an
   enabled button in front of it. These assert the two member-facing billing
   surfaces cannot ask for money, and cannot lie about why.
   ========================================================================== */

t('the pricing page reads the checkout gate instead of hardcoding it', () => {
  ok(/<script src="entitlements\.js"><\/script>/.test(PRICING),
     'pricing.html does not load entitlements.js, so its button state is its own opinion');
  ok(/checkoutMayBeEnabled\s*\(/.test(PRICING),
     'pricing.html does not consult checkoutMayBeEnabled()');
});

t('the pricing page ships the Subscribe button disabled in the markup', () => {
  // Disabled by JS is not enough: JS can fail to run, and a button that is
  // live for the first 200ms is a button that can be clicked.
  const btn = PRICING.match(/<button[^>]*id="proCheckout"[^>]*>/);
  ok(btn, 'no #proCheckout button on pricing.html');
  ok(/\bdisabled\b/.test(btn[0]),
     'the Subscribe button is not disabled in the served HTML: ' + btn[0]);
});

t('the pricing page never claims to sell what is not for sale', () => {
  const txt = visible(PRICING).replace(/\s+/g, ' ');
  ok(/Not for sale/i.test(txt), 'the Pro column no longer says it is not for sale');
  ok(/Checkout is switched off/i.test(txt),
     'the page does not state on its face that checkout is off');
  [/launch(es|ing)? (soon|shortly)/i, /coming soon/i, /start your (free )?trial/i,
   /enter your card/i, /billed (monthly|today)/i]
    .forEach(re => ok(!re.test(txt),
      'pricing.html makes a payment-shaped promise: ' + re));
});

t('clicking the inert button cannot emit a checkout event', () => {
  // cfl.EVENTS.checkout_started is declared and deliberately not emitted. If
  // the disabled button fired it, the funnel would count checkouts that never
  // could have happened, and the first real number would be unreadable.
  // Comments stripped: a comment explaining why the event is NOT emitted must
  // not read as the emission. Fifth time this pattern has bitten in this repo.
  const code = (PRICING.match(/<script>[\s\S]*?<\/script>/g) || []).join('\n')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/^\s*\/\/.*$/gm, ' ');
  ok(!/checkout_started/.test(code),
     'pricing.html emits checkout_started while checkout is disabled');
});

t('the account page describes billing through the shared state machine', () => {
  ok(/<script src="billing-lifecycle\.js"><\/script>/.test(ACCOUNT),
     'account.html does not load billing-lifecycle.js');
  ok(/cflBilling\.describe\(/.test(ACCOUNT),
     'account.html phrases billing state itself instead of using describe()');
  ok(/v_my_billing/.test(ACCOUNT),
     'account.html does not read v_my_billing');
});

t('the account page cannot call a beta member Free', () => {
  // profiles.tier is 'free' for everyone during beta; beta_premium is what
  // makes them Pro. A page reading only `tier` contradicts the whole site.
  const js = (ACCOUNT.match(/<script>[\s\S]*?<\/script>/g) || []).join('\n');
  ok(!/profile\??\.tier\s*\|\|\s*'free'/.test(js),
     'account.html derives the tier from profiles.tier alone, ignoring beta_premium');
  ok(/entitlement\s*===\s*'pro'/.test(js) || /getTier\(\)/.test(js),
     'account.html does not use the entitlement rule');
});

t('the account page only claims "no card on file" when that is true', () => {
  ok(/has_billing_account/.test(ACCOUNT),
     'account.html states no card is on file without checking whether one is');
});

t('the account page makes no promise about when billing starts', () => {
  const txt = visible(ACCOUNT).replace(/\s+/g, ' ');
  [/launch(es|ing)? (soon|shortly)/i, /coming soon/i]
    .forEach(re => ok(!re.test(txt),
      'account.html promises a launch date it does not have: ' + re));
});

t('the refusal is verified against the deployed functions, not just asserted', () => {
  ok(/workflow_dispatch/.test(WORKFLOW), 'the refusal check is not manually runnable');
  ok(/contents:\s*read/.test(WORKFLOW),
     'the refusal check is handed a writable token — it is a check, not a gate');
  ok(/stripe-checkout/.test(WORKFLOW) && /stripe-webhook/.test(WORKFLOW),
     'the refusal check does not hit both functions');
  ok(/checkout_disabled/.test(WORKFLOW), 'it does not assert the checkout refusal');
  ok(/T-054/.test(WORKFLOW) && /T-048/.test(WORKFLOW),
     'it does not assert that the blockers are named in the refusal');
  ok(/not_configured/.test(WORKFLOW), 'it does not assert the webhook refusal');
  ok(!/secrets\./.test(WORKFLOW),
     'the refusal check uses a secret — it must need none');
});

// ------------------------------------------------------------------ report
if (failures.length) {
  console.log(`\n  ${passed} passed, ${failures.length} FAILED\n`);
  failures.forEach(f => console.log(`  ✗ ${f}\n`));
  process.exit(1);
}
console.log(`\n  ${passed} passed — the lifecycle is driven end to end, and nothing can take money.\n`);
