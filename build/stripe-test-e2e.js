#!/usr/bin/env node
// =============================================================================
// stripe-test-e2e.js — T-069: the billing path, end to end, in Stripe TEST mode.
// =============================================================================
// PLAIN ENGLISH: once a Stripe account exists, this proves the whole loop on
// the deployed functions without anyone paying anything: a signed-in test
// member asks for a checkout, Stripe-signed messages arrive at the webhook, and
// the member's access switches on, survives a failed payment, and switches off
// when the subscription ends. It reads the member's access back the way the
// site does (v_my_billing), so "it worked" means what the account page shows.
//
// IT REFUSES TO RUN WITH A LIVE KEY. Not "warns": exits 2 before any request,
// unless STRIPE_SECRET_KEY starts with `sk_test_`. Any `sk_live_` / `rk_live_`
// value anywhere in its environment is also a refusal. A checkout URL that is
// not a test-mode session (`cs_test_`) aborts the run.
//
// WHAT IT NEEDS (environment; never commit any of these)
//   STRIPE_SECRET_KEY      sk_test_...   the TEST secret key
//   STRIPE_WEBHOOK_SECRET  whsec_...     the signing secret of the endpoint
//                                        that points at the deployed
//                                        stripe-webhook function — the SAME
//                                        value set as the function secret
//   STRIPE_PRICE_ID        price_...     optional: checked to be a test-mode,
//                                        recurring, active price
//   CFL_TEST_EMAIL / CFL_TEST_PASSWORD   a dedicated test member account with
//                                        beta_premium = false (see runbook)
//   SUPABASE_URL / SUPABASE_KEY          optional; default to the project URL
//                                        and publishable key in _shared.js
//   CFL_FUNCTIONS_URL                    optional; where the two functions
//                                        are served. Defaults to
//                                        $SUPABASE_URL/functions/v1. A
//                                        non-https value (a local
//                                        `supabase functions serve` stack,
//                                        with SUPABASE_URL/KEY pointed at the
//                                        same local stack) skips the endpoint
//                                        preflight, because `stripe listen`
//                                        forwards instead of an endpoint.
//                                        Not the runbook's route; untested.
//
// WHAT IT DOES, IN ORDER
//   0. preflight   key is sk_test_; webhook secret is whsec_; the price (if
//                  given) is test-mode, recurring and active; the Stripe
//                  webhook endpoint for this project exists, is enabled and
//                  sends the events the function handles, and its API version
//                  is reported (see the current_period_end note in the runbook)
//   1. sign in     the test member, through Supabase Auth, like the site does
//   2. checkout    POST stripe-checkout as that member. 200 + a cs_test_ URL
//                  passes. 503 checkout_disabled is reported as BLOCKED, which
//                  is the expected answer while T-054/T-048 stand; pass
//                  --require-checkout to make it a failure instead.
//   3. real wait   with --wait-for-real-checkout, print the URL, pay it with
//                  Stripe's test card, and poll v_my_billing until Stripe's own
//                  delivery (a real signature) switches access on.
//   4. replay      signed fixtures, posted to the deployed webhook, each
//                  followed by a read of v_my_billing:
//                    subscription.created  active             -> pro
//                    subscription.updated  past_due           -> still pro
//                    subscription.updated  cancel at period end -> pro, ending
//                    subscription.deleted  period over        -> free
//                    the first event again                    -> duplicate_ignored,
//                                                                still free
//                    a forged signature                       -> 400
//                    a stale timestamp                        -> 400
//
// It creates ONE Stripe test-mode customer per run so the profile it writes
// carries a real test customer id (a later checkout reuses it). It never
// creates a live object and never touches another member.
//
// Run:  node build/stripe-test-e2e.js [--require-checkout]
//                                     [--wait-for-real-checkout[=minutes]]
//                                     [--skip-replay]
// Exit: 0 all legs passed (BLOCKED checkout counts as passed unless
//       --require-checkout); 1 a leg failed; 2 refused to run.
// =============================================================================
'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const WEBHOOK_EVENTS = [
  'checkout.session.completed',
  'customer.subscription.created',
  'customer.subscription.updated',
  'customer.subscription.deleted',
];
// The Stripe API version that moved current_period_end off the Subscription
// object and onto its items. The webhook reads o.current_period_end.
const PERIOD_END_MOVED_IN = '2025-03-31';

// --------------------------------------------------------------- pure parts
// Exported so tests/stripe-webhook-offline.test.js can drive them with no
// network and no keys.

class Refusal extends Error {}

function assertTestMode(env) {
  const key = env.STRIPE_SECRET_KEY || '';
  for (const [name, value] of Object.entries(env)) {
    if (typeof value === 'string' && /^(sk|rk)_live_/.test(value)) {
      throw new Refusal(`${name} holds a LIVE Stripe key. This harness only ever runs in test mode.`);
    }
  }
  if (!key.startsWith('sk_test_')) {
    throw new Refusal('STRIPE_SECRET_KEY must be a TEST secret key (sk_test_...). Refusing to run.');
  }
  const whsec = env.STRIPE_WEBHOOK_SECRET || '';
  if (!whsec.startsWith('whsec_')) {
    throw new Refusal('STRIPE_WEBHOOK_SECRET must be the endpoint signing secret (whsec_...).');
  }
  if (env.STRIPE_PRICE_ID && !/^price_/.test(env.STRIPE_PRICE_ID)) {
    throw new Refusal('STRIPE_PRICE_ID does not look like a price id (price_...).');
  }
  if (!env.CFL_TEST_EMAIL || !env.CFL_TEST_PASSWORD) {
    throw new Refusal('CFL_TEST_EMAIL and CFL_TEST_PASSWORD (a dedicated test member) are required.');
  }
  return true;
}

// Stripe's documented scheme: v1 = hex HMAC-SHA256(secret, `${t}.${payload}`),
// header `t=<unix seconds>,v1=<hex>`.
function signPayload(payload, secret, t) {
  const v1 = crypto.createHmac('sha256', secret).update(`${t}.${payload}`, 'utf8').digest('hex');
  return `t=${t},v1=${v1}`;
}

function checkoutUrlIsTestMode(url) {
  return typeof url === 'string' && /^https:\/\/checkout\.stripe\.com\//.test(url) && /cs_test_/.test(url);
}

// API versions are dated strings, so they compare lexically.
function periodEndMovedOff(apiVersion) {
  return typeof apiVersion === 'string' && apiVersion.slice(0, 10) >= PERIOD_END_MOVED_IN;
}

function subscription({ subId, customerId, userId, status, periodEndSec, cancelAtPeriodEnd }) {
  return {
    id: subId, object: 'subscription', customer: customerId, status,
    current_period_end: periodEndSec, cancel_at_period_end: !!cancelAtPeriodEnd,
    livemode: false, metadata: { cfl_user_id: userId },
  };
}

// The replay script. Each step names the event, the expected HTTP answer and
// the v_my_billing state the member should then see. `expect.entitlement` is
// what current_user_entitlement() returns for a non-beta member.
function buildFixtures({ runId, userId, customerId, nowSec }) {
  const subId = `sub_cfl_e2e_${runId}`;
  const future = nowSec + 30 * 86400;
  const past = nowSec - 3600;
  const ev = (n, type, object) => ({
    id: `evt_cfl_e2e_${runId}_${n}`, object: 'event', type, livemode: false,
    api_version: null, created: nowSec, data: { object },
  });
  const created = ev(1, 'customer.subscription.created',
    subscription({ subId, customerId, userId, status: 'active', periodEndSec: future }));
  return [
    { name: 'subscription created (active) switches Pro on', event: created,
      http: 200, body: 'applied',
      expect: { entitlement: 'pro', subscription_status: 'active', cancel_at_period_end: false, period_end: future } },
    { name: 'one failed payment (past_due) keeps Pro to the period end',
      event: ev(2, 'customer.subscription.updated',
        subscription({ subId, customerId, userId, status: 'past_due', periodEndSec: future })),
      http: 200, body: 'applied',
      expect: { entitlement: 'pro', subscription_status: 'past_due', cancel_at_period_end: false, period_end: future } },
    { name: 'cancelling at period end keeps Pro and flags it as ending',
      event: ev(3, 'customer.subscription.updated',
        subscription({ subId, customerId, userId, status: 'active', periodEndSec: future, cancelAtPeriodEnd: true })),
      http: 200, body: 'applied',
      expect: { entitlement: 'pro', subscription_status: 'active', cancel_at_period_end: true, period_end: future } },
    { name: 'deletion after the period ends switches Pro off',
      event: ev(4, 'customer.subscription.deleted',
        subscription({ subId, customerId, userId, status: 'canceled', periodEndSec: past })),
      http: 200, body: 'applied',
      expect: { entitlement: 'free', subscription_status: 'canceled', cancel_at_period_end: false, period_end: null } },
    { name: 'a redelivered old event is ignored and does not switch Pro back on',
      event: created, http: 200, body: 'duplicate_ignored',
      expect: { entitlement: 'free', subscription_status: 'canceled', cancel_at_period_end: false, period_end: null } },
    { name: 'a forged signature is refused', event: ev(6, 'customer.subscription.created',
        subscription({ subId, customerId, userId, status: 'active', periodEndSec: future })),
      forge: 'signature', http: 400, body: 'signature_mismatch',
      expect: { entitlement: 'free', subscription_status: 'canceled', cancel_at_period_end: false, period_end: null } },
    { name: 'a stale timestamp is refused', event: ev(7, 'customer.subscription.created',
        subscription({ subId, customerId, userId, status: 'active', periodEndSec: future })),
      forge: 'stale', http: 400, body: 'timestamp_outside_tolerance',
      expect: { entitlement: 'free', subscription_status: 'canceled', cancel_at_period_end: false, period_end: null } },
  ];
}

// The header to send for one step: properly signed, or deliberately not.
function headerFor(step, payload, secret, nowSec) {
  if (step.forge === 'signature') return signPayload(payload, secret + '_wrong', nowSec);
  if (step.forge === 'stale') return signPayload(payload, secret, nowSec - 3600);
  return signPayload(payload, secret, nowSec);
}

// Compare a v_my_billing row against a step's expectation. Returns a list of
// mismatches (empty = pass). Times are compared to the second.
function billingMismatches(row, expect) {
  const out = [];
  if (!row) return ['v_my_billing returned no row'];
  if (row.entitlement !== expect.entitlement) out.push(`entitlement ${row.entitlement} != ${expect.entitlement}`);
  if (row.subscription_status !== expect.subscription_status) {
    out.push(`subscription_status ${row.subscription_status} != ${expect.subscription_status}`);
  }
  if (!!row.cancel_at_period_end !== expect.cancel_at_period_end) {
    out.push(`cancel_at_period_end ${row.cancel_at_period_end} != ${expect.cancel_at_period_end}`);
  }
  const got = row.current_period_end ? Math.round(Date.parse(row.current_period_end) / 1000) : null;
  if (got !== expect.period_end) out.push(`current_period_end ${row.current_period_end} != ${expect.period_end}`);
  return out;
}

function parseArgs(argv) {
  const a = { requireCheckout: false, waitMinutes: 0, skipReplay: false };
  for (const arg of argv) {
    if (arg === '--require-checkout') a.requireCheckout = true;
    else if (arg === '--skip-replay') a.skipReplay = true;
    else if (arg.startsWith('--wait-for-real-checkout')) {
      const m = arg.match(/=(\d+)$/);
      a.waitMinutes = m ? Number(m[1]) : 10;
    } else throw new Refusal('unknown argument ' + arg);
  }
  return a;
}

function projectFromShared() {
  try {
    const src = fs.readFileSync(path.join(__dirname, '..', '_shared.js'), 'utf8');
    return {
      url: (src.match(/SUPABASE_URL = '([^']+)'/) || [])[1],
      key: (src.match(/SUPABASE_KEY = '([^']+)'/) || [])[1],
    };
  } catch (e) { return {}; }
}

// ------------------------------------------------------------ network parts

async function stripeGet(key, pathname) {
  const res = await fetch('https://api.stripe.com/v1' + pathname, { headers: { Authorization: `Bearer ${key}` } });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`Stripe GET ${pathname} -> ${res.status} ${body.error && body.error.message}`);
  return body;
}

async function stripePost(key, pathname, form) {
  const res = await fetch('https://api.stripe.com/v1' + pathname, {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams(form).toString(),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`Stripe POST ${pathname} -> ${res.status} ${body.error && body.error.message}`);
  return body;
}

async function main() {
  const env = process.env;
  const results = [];
  const record = (leg, status, detail) => {
    results.push({ leg, status, detail });
    console.log(`  [${status}] ${leg}${detail ? ' — ' + detail : ''}`);
  };

  let args;
  try {
    args = parseArgs(process.argv.slice(2));
    assertTestMode(env);
  } catch (e) {
    if (e instanceof Refusal) { console.error('REFUSED: ' + e.message); process.exit(2); }
    throw e;
  }

  const shared = projectFromShared();
  const SUPA_URL = env.SUPABASE_URL || shared.url;
  const SUPA_KEY = env.SUPABASE_KEY || shared.key;
  if (!SUPA_URL || !SUPA_KEY) { console.error('REFUSED: no Supabase URL / publishable key'); process.exit(2); }
  const SK = env.STRIPE_SECRET_KEY;
  const WHSEC = env.STRIPE_WEBHOOK_SECRET;
  const FUNCTIONS = (env.CFL_FUNCTIONS_URL || `${SUPA_URL}/functions/v1`).replace(/\/+$/, '');
  const localFunctions = !/^https:\/\//.test(FUNCTIONS);
  const webhookUrl = `${FUNCTIONS}/stripe-webhook`;
  console.log(`\nT-069 Stripe test-mode end-to-end against ${SUPA_URL}\n`);

  // ---- 0. preflight ------------------------------------------------------
  if (env.STRIPE_PRICE_ID) {
    try {
      const p = await stripeGet(SK, `/prices/${encodeURIComponent(env.STRIPE_PRICE_ID)}`);
      const problems = [];
      if (p.livemode !== false) problems.push('price is not a test-mode price');
      if (!p.recurring) problems.push('price is not recurring');
      if (!p.active) problems.push('price is not active');
      record('preflight: price', problems.length ? 'FAIL' : 'PASS',
        problems.join('; ') || `${p.id} ${p.currency} ${p.unit_amount} / ${p.recurring.interval}`);
    } catch (e) { record('preflight: price', 'FAIL', e.message); }
  } else {
    record('preflight: price', 'SKIP', 'STRIPE_PRICE_ID not set');
  }
  if (localFunctions) {
    record('preflight: webhook endpoint', 'SKIP', `functions served locally at ${FUNCTIONS}; use \`stripe listen\``);
  } else try {
    const list = await stripeGet(SK, '/webhook_endpoints?limit=100');
    const ep = (list.data || []).find(e => e.url === webhookUrl);
    if (!ep) {
      record('preflight: webhook endpoint', 'FAIL', `no test-mode endpoint points at ${webhookUrl}`);
    } else {
      const events = ep.enabled_events || [];
      const missing = events.indexOf('*') !== -1 ? [] : WEBHOOK_EVENTS.filter(x => events.indexOf(x) === -1);
      const problems = [];
      if (ep.status !== 'enabled') problems.push('endpoint is ' + ep.status);
      if (missing.length) problems.push('not sending ' + missing.join(', '));
      record('preflight: webhook endpoint', problems.length ? 'FAIL' : 'PASS',
        problems.join('; ') || `${ep.id}, api_version ${ep.api_version || '(account default)'}`);
      if (periodEndMovedOff(ep.api_version)) {
        record('preflight: api version', 'FAIL',
          `${ep.api_version} puts current_period_end on subscription ITEMS; the webhook reads it off the ` +
          'subscription and would grant open-ended access. Recreate the endpoint on an earlier version ' +
          'or change the webhook first (runbook §current_period_end).');
      } else if (!ep.api_version) {
        record('preflight: api version', 'WARN', 'endpoint uses the account default version — check it in the dashboard');
      }
    }
  } catch (e) { record('preflight: webhook endpoint', 'FAIL', e.message); }

  // ---- 1. sign in --------------------------------------------------------
  const authRes = await fetch(`${SUPA_URL}/auth/v1/token?grant_type=password`, {
    method: 'POST',
    headers: { apikey: SUPA_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: env.CFL_TEST_EMAIL, password: env.CFL_TEST_PASSWORD }),
  });
  const auth = await authRes.json().catch(() => ({}));
  if (!authRes.ok || !auth.access_token) {
    record('sign in', 'FAIL', `HTTP ${authRes.status}`);
    return finish(results, args);
  }
  const userId = auth.user && auth.user.id;
  const asMember = { apikey: SUPA_KEY, Authorization: `Bearer ${auth.access_token}` };
  record('sign in', 'PASS', `member ${userId}`);

  const readBilling = async () => {
    const r = await fetch(`${SUPA_URL}/rest/v1/v_my_billing?select=*`, { headers: asMember });
    const rows = await r.json().catch(() => null);
    return Array.isArray(rows) ? rows[0] : null;
  };
  const before = await readBilling();
  if (!before) { record('read v_my_billing', 'FAIL', 'no row'); return finish(results, args); }
  if (before.is_beta) {
    record('test account', 'FAIL', 'beta_premium is true, so entitlement is pro whatever Stripe says and ' +
      'nothing can be observed. Set beta_premium = false for this TEST account only (runbook step 6).');
    return finish(results, args);
  }
  record('test account', 'PASS', `starts ${before.entitlement}, status ${before.subscription_status || 'none'}`);

  // ---- 2. checkout -------------------------------------------------------
  let checkoutUrl = null;
  const coRes = await fetch(`${FUNCTIONS}/stripe-checkout`, {
    method: 'POST', headers: { ...asMember, 'Content-Type': 'application/json' }, body: '{}',
  });
  const co = await coRes.json().catch(() => ({}));
  if (coRes.status === 503 && co.error === 'checkout_disabled') {
    record('checkout session', args.requireCheckout ? 'FAIL' : 'BLOCKED',
      'checkout_disabled: ' + (co.blockers || []).map(b => b.id).join(', ') + ' still stand');
  } else if (coRes.ok && co.url) {
    if (!checkoutUrlIsTestMode(co.url)) {
      record('checkout session', 'FAIL', 'the session is NOT a test-mode session. Aborting.');
      return finish(results, args);
    }
    checkoutUrl = co.url;
    record('checkout session', 'PASS', 'test-mode session created');
  } else {
    record('checkout session', 'FAIL', `HTTP ${coRes.status} ${co.error || ''}`);
  }

  // ---- 3. real delivery --------------------------------------------------
  if (args.waitMinutes && checkoutUrl) {
    console.log(`\n  Pay this with card 4242 4242 4242 4242, any future date, any CVC:\n  ${checkoutUrl}\n`);
    const deadline = Date.now() + args.waitMinutes * 60000;
    let seen = null;
    while (Date.now() < deadline) {
      await new Promise(r => setTimeout(r, 10000));
      const row = await readBilling();
      if (row && row.entitlement === 'pro' && ['active', 'trialing'].indexOf(row.subscription_status) !== -1) { seen = row; break; }
    }
    record('real Stripe delivery switches Pro on', seen ? 'PASS' : 'FAIL',
      seen ? `status ${seen.subscription_status}, ends ${seen.current_period_end}` : `nothing within ${args.waitMinutes} min`);
  } else if (args.waitMinutes) {
    record('real Stripe delivery switches Pro on', 'SKIP', 'no checkout session to pay');
  }

  // ---- 4. signed replay --------------------------------------------------
  if (!args.skipReplay) {
    let customerId;
    try {
      const c = await stripePost(SK, '/customers', {
        email: env.CFL_TEST_EMAIL, 'metadata[cfl_e2e]': '1', 'metadata[cfl_user_id]': userId,
      });
      if (c.livemode !== false) throw new Error('Stripe created a LIVE customer');
      customerId = c.id;
    } catch (e) {
      record('replay: test customer', 'FAIL', e.message);
      return finish(results, args);
    }
    const runId = Date.now().toString(36);
    const steps = buildFixtures({ runId, userId, customerId, nowSec: Math.floor(Date.now() / 1000) });
    for (const step of steps) {
      const payload = JSON.stringify(step.event);
      const nowSec = Math.floor(Date.now() / 1000);
      const res = await fetch(webhookUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Stripe-Signature': headerFor(step, payload, WHSEC, nowSec) },
        body: payload,
      });
      const text = await res.text();
      const problems = [];
      if (res.status !== step.http) problems.push(`HTTP ${res.status} != ${step.http}`);
      if (text.trim() !== step.body) problems.push(`body "${text.trim()}" != "${step.body}"`);
      problems.push(...billingMismatches(await readBilling(), step.expect));
      record('replay: ' + step.name, problems.length ? 'FAIL' : 'PASS', problems.join('; '));
    }
  }

  return finish(results, args);
}

function finish(results) {
  const failed = results.filter(r => r.status === 'FAIL');
  const blocked = results.filter(r => r.status === 'BLOCKED');
  console.log(`\n  ${results.length - failed.length} ok, ${failed.length} failed` +
    (blocked.length ? `, ${blocked.length} blocked (expected while CHECKOUT_BLOCKERS stand)` : '') + '\n');
  process.exit(failed.length ? 1 : 0);
}

module.exports = {
  Refusal, assertTestMode, signPayload, checkoutUrlIsTestMode, periodEndMovedOff,
  buildFixtures, headerFor, billingMismatches, parseArgs, WEBHOOK_EVENTS, PERIOD_END_MOVED_IN,
};

if (require.main === module) {
  main().catch(e => { console.error('stripe-test-e2e crashed:', e && e.message); process.exit(1); });
}
