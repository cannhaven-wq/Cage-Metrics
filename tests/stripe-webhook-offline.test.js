/* ==========================================================================
   tests/stripe-webhook-offline.test.js — the DEPLOYED webhook's own code, run.

   tests/billing-lifecycle.test.js drives billing-lifecycle.js exhaustively and
   reads the webhook's source for the right shapes. What nothing did until now
   is EXECUTE the webhook's code: its signature check and its private copy of
   the lifecycle rules had only ever been read with regular expressions. A
   regex cannot tell a correct HMAC from one over the wrong bytes, or a copied
   rule that drifted by one branch.

   So this lifts the pure part of supabase/functions/stripe-webhook/index.ts
   (everything above `Deno.serve`), strips its TypeScript types, and runs it in
   Node with Web Crypto — the same API Deno uses. Signatures are generated
   locally with Stripe's documented scheme (HMAC-SHA256 of `${t}.${payload}`,
   header `t=...,v1=...`) by build/stripe-test-e2e.js, the T-069 harness, so
   the harness and the webhook are proven to speak the same scheme before
   anyone has a key.

   No network. No keys. No Deno.

   Run:  node tests/stripe-webhook-offline.test.js
   ========================================================================== */
'use strict';
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const root = f => path.join(__dirname, '..', f);
const B = require('../billing-lifecycle.js');
const H = require('../build/stripe-test-e2e.js');
const SRC = fs.readFileSync(root('supabase/functions/stripe-webhook/index.ts'), 'utf8');

// ------------------------------------------------------------ load the TS
function stripTypes(ts) {
  const mod = require('node:module');
  if (typeof mod.stripTypeScriptTypes === 'function') {
    const emit = process.emitWarning;
    process.emitWarning = () => {};               // "experimental" is noise here
    try { return mod.stripTypeScriptTypes(ts); } finally { process.emitWarning = emit; }
  }
  // Fallback for a Node without the built-in stripper: the annotations this
  // file actually uses, and nothing cleverer.
  return ts
    .replace(/\)\s*:\s*(string|number|boolean|unknown)(\s*\|\s*null)?\s*\{/g, ') {')
    .replace(/(\w+)\s*:\s*(string|number|boolean|unknown|any)(\s*\|\s*null)?(?=\s*[,)=])/g, '$1')
    .replace(/\s+as\s+Record<string,\s*string>/g, '')
    .replace(/\s+as\s+any/g, '');
}

const start = SRC.indexOf('const PRO_TIER');
const end = SRC.indexOf('Deno.serve(');
if (start < 0 || end < 0 || end < start) throw new Error('could not find the pure section of the webhook');
const pure = stripTypes(SRC.slice(start, end));
const W = new Function('crypto', 'TextEncoder',
  pure + '\nreturn { PRO_TIER, FREE_TIER, STATUS_KEEPS_PERIOD, STATUS_ENDS_NOW, HANDLED, iso, idOf, ' +
  'entitlementFor, userIdFrom, periodEndOf, TOLERANCE_SECONDS, timingSafeEqual, verifyStripeSignature };'
)(globalThis.crypto, TextEncoder);

// ------------------------------------------------------------ harness
let passed = 0;
const failures = [];
const queue = [];
const t = (name, fn) => queue.push([name, fn]);
function ok(c, m) { if (!c) throw new Error(m); }
function eq(a, b, m) {
  const A = JSON.stringify(a), Bv = JSON.stringify(b);
  if (A !== Bv) throw new Error((m || 'value') + ': expected ' + Bv + ', got ' + A);
}

const SECRET = 'whsec_offline_test_secret_not_real';
const NOW_SEC = Math.floor(Date.parse('2026-10-01T12:00:00Z') / 1000);
const NOW_MS = NOW_SEC * 1000;
const body = JSON.stringify({ id: 'evt_1', type: 'customer.subscription.updated',
  data: { object: { id: 'sub_1', status: 'active', current_period_end: NOW_SEC + 86400 } } });
const verify = (raw, header, secret, now) => W.verifyStripeSignature(raw, header, secret || SECRET, now || NOW_SEC);

/* ======================================================================
   1. SIGNATURE VERIFICATION — the webhook's authentication
   ====================================================================== */

t('a payload signed with Stripe\'s scheme verifies', async () => {
  const r = await verify(body, H.signPayload(body, SECRET, NOW_SEC));
  eq(r, { ok: true, reason: 'verified' }, 'verdict');
});

t('the signature is over the exact raw bytes: one changed character fails', async () => {
  const header = H.signPayload(body, SECRET, NOW_SEC);
  const r = await verify(body.replace('"active"', '"Active"'), header);
  eq(r.reason, 'signature_mismatch', 'a tampered body verified');
  const r2 = await verify(body + ' ', header);
  eq(r2.reason, 'signature_mismatch', 'trailing whitespace verified — the body was re-serialised, not read raw');
});

t('a different secret fails', async () => {
  const r = await verify(body, H.signPayload(body, SECRET + 'x', NOW_SEC));
  eq(r.reason, 'signature_mismatch', 'reason');
});

t('the timestamp is inside the signed bytes, so it cannot be swapped', async () => {
  const good = H.signPayload(body, SECRET, NOW_SEC);
  const v1 = good.split('v1=')[1];
  const r = await verify(body, `t=${NOW_SEC - 10},v1=${v1}`);
  eq(r.reason, 'signature_mismatch', 'a re-timestamped signature verified');
});

t('a replay outside five minutes is refused, either side of now', async () => {
  eq(W.TOLERANCE_SECONDS, 300, 'tolerance');
  const old = NOW_SEC - 301, future = NOW_SEC + 301;
  eq((await verify(body, H.signPayload(body, SECRET, old))).reason, 'timestamp_outside_tolerance', 'old');
  eq((await verify(body, H.signPayload(body, SECRET, future))).reason, 'timestamp_outside_tolerance', 'future');
  eq((await verify(body, H.signPayload(body, SECRET, NOW_SEC - 300))).ok, true, 'exactly at the edge');
});

t('a missing or malformed header is refused, never treated as signed', async () => {
  eq((await verify(body, '')).reason, 'missing_signature', 'empty');
  eq((await verify(body, 'garbage')).reason, 'malformed_signature', 'garbage');
  eq((await verify(body, `t=${NOW_SEC}`)).reason, 'malformed_signature', 'no v1');
  eq((await verify(body, 't=abc,v1=00')).reason, 'malformed_signature', 'non-numeric t');
  eq((await verify(body, `t=${NOW_SEC},v1=`)).reason, 'malformed_signature', 'empty v1');
});

t('Stripe\'s extra v0 test-mode signature does not get in the way', async () => {
  const h = H.signPayload(body, SECRET, NOW_SEC) + ',v0=6ffbb59b2300aae63f272406069a9788598b792a944a07aba816edb039989a39';
  eq((await verify(body, h)).ok, true, 'a v0 element broke verification');
});

t('KNOWN LIMIT, pinned: with several v1 values only the LAST is checked', async () => {
  // Stripe sends one v1 per active signing secret while a secret is being
  // rolled with an overlap. This function keeps the last one it parses, so a
  // valid signature that is not last is refused. Harmless while there is one
  // secret; the runbook says to roll the secret WITHOUT an overlap until the
  // function accepts any matching v1. If this test starts failing because the
  // function now accepts either order, delete it and the runbook caveat.
  const good = H.signPayload(body, SECRET, NOW_SEC).split('v1=')[1];
  const other = H.signPayload(body, 'whsec_other', NOW_SEC).split('v1=')[1];
  eq((await verify(body, `t=${NOW_SEC},v1=${other},v1=${good}`)).ok, true, 'good-last');
  eq((await verify(body, `t=${NOW_SEC},v1=${good},v1=${other}`)).ok, false, 'good-first');
});

t('the comparison is constant-time shaped and length-checked', () => {
  eq(W.timingSafeEqual('abcd', 'abcd'), true, 'equal');
  eq(W.timingSafeEqual('abcd', 'abce'), false, 'differs');
  eq(W.timingSafeEqual('abcd', 'abc'), false, 'length');
});

/* ======================================================================
   2. THE WEBHOOK'S COPY OF THE RULES, EXECUTED AGAINST THE MODULE'S
   ====================================================================== */

t('entitlementFor agrees with billing-lifecycle.js on every status and period', () => {
  const statuses = B.STATUS_KEEPS_PERIOD.concat(B.STATUS_ENDS_NOW,
    ['canceled', '', 'weird', 'ACTIVE', 'active ']);
  const ends = [null, new Date(NOW_MS - 86400000).toISOString(), new Date(NOW_MS + 86400000).toISOString(),
                new Date(NOW_MS).toISOString()];
  let n = 0;
  statuses.forEach(s => ends.forEach(e => {
    eq(W.entitlementFor(s, e, NOW_MS), B.entitlementFor(s, e, NOW_MS), `status ${JSON.stringify(s)} end ${e}`);
    n++;
  }));
  ok(n >= 40, 'too few combinations exercised: ' + n);
});

t('the constants are the same values, not just the same names', () => {
  eq(W.PRO_TIER, B.PRO_TIER, 'PRO_TIER');
  eq(W.FREE_TIER, B.FREE_TIER, 'FREE_TIER');
  eq(W.STATUS_KEEPS_PERIOD, B.STATUS_KEEPS_PERIOD, 'STATUS_KEEPS_PERIOD');
  eq(W.STATUS_ENDS_NOW, B.STATUS_ENDS_NOW, 'STATUS_ENDS_NOW');
  eq(W.HANDLED, B.HANDLED, 'HANDLED');
});

t('the member is found the same way, and never from an email', () => {
  [
    { client_reference_id: 'u1' },
    { metadata: { cfl_user_id: 'u2' } },
    { subscription_details: { metadata: { cfl_user_id: 'u3' } } },
    { customer_email: 'a@b.com' },
    {}, null,
  ].forEach(o => eq(W.userIdFrom(o), B.userIdFrom(o), JSON.stringify(o)));
  eq(W.userIdFrom({ customer_email: 'a@b.com' }), null, 'an email resolved to a member');
});

t('the period end is found the same way in both copies, for both Stripe shapes', () => {
  const F = NOW_SEC + 86400, L = NOW_SEC + 2 * 86400;
  const shapes = [
    { current_period_end: F },                                                  // legacy
    { items: { data: [{ current_period_end: F }] } },                           // basil
    { items: { data: [{ current_period_end: F }, { current_period_end: L }] } },// basil, several items
    { current_period_end: F, items: { data: [{ current_period_end: L }] } },    // both: top level wins
    { items: { data: [{ current_period_end: null }, { current_period_end: 'x' }] } },
    { items: { data: [] } }, { items: null }, { current_period_end: 0 }, { current_period_end: '' }, {}, null,
  ];
  const want = [F, F, L, F, null, null, null, null, null, null, null];
  shapes.forEach((o, i) => {
    eq(W.periodEndOf(o), B.periodEndOf(o), 'copies disagree on ' + JSON.stringify(o));
    eq(W.periodEndOf(o), want[i], 'periodEndOf(' + JSON.stringify(o) + ')');
  });
});

t('a basil payload through the webhook path grants to the item period end; no end fails closed', () => {
  const F = NOW_SEC + 86400;
  const basilEv = { type: 'customer.subscription.updated',
    data: { object: { id: 'sub_b', status: 'active', items: { data: [{ current_period_end: F }] } } } };
  const w = webhookWrites(basilEv, NOW_MS);
  eq(w.entitlement, 'pro', 'basil active');
  eq(w.ent.expiresAt, new Date(F * 1000).toISOString(), 'basil expiry');
  ['active', 'trialing', 'past_due'].forEach(status => {
    const none = { type: 'customer.subscription.updated', data: { object: { id: 'sub_n', status } } };
    const r = webhookWrites(none, NOW_MS);
    eq(r.entitlement, 'free', status + ' with no period end granted access');
    eq(r.ent.reason, 'status_' + status + '_no_period_end_fails_closed', status + ' reason');
    eq(r.ent.reason, B.decide(none, NOW_MS).reason, status + ' reason vs decide()');
  });
});

t('Stripe timestamps convert the same way', () => {
  [NOW_SEC, 0, -1, null, undefined, 'x'].forEach(v => {
    const w = W.iso(v);
    const b = (v === null || v === undefined) ? null : (isFinite(Number(v)) && Number(v) > 0 ? new Date(Number(v) * 1000).toISOString() : null);
    eq(w, b, 'iso(' + JSON.stringify(v) + ')');
  });
});

/* ======================================================================
   3. THE T-069 FIXTURES, THROUGH THE WEBHOOK'S OWN PATH
   ====================================================================== */

// What the webhook would write for a verified subscription event, following
// its handler step by step, and what current_user_entitlement() then reads.
function webhookWrites(event, nowMs) {
  const o = event.data.object;
  const status = event.type === 'customer.subscription.deleted' ? 'canceled' : String(o.status || '');
  const ent = W.entitlementFor(status, W.iso(W.periodEndOf(o)), nowMs);
  const pro = (ent.tier === 'premium' || ent.tier === 'pro') &&
              (ent.expiresAt === null || Date.parse(ent.expiresAt) > nowMs);
  return { ent, status, entitlement: pro ? 'pro' : 'free', cancel: !!o.cancel_at_period_end };
}

for (const shape of ['legacy', 'items']) t('every replay step (' + shape + ' payload) signs, verifies, and maps to the state the harness expects', async () => {
  const steps = H.buildFixtures({ runId: 'offline', userId: 'user-1', customerId: 'cus_offline', nowSec: NOW_SEC, shape });
  const sample = steps[0].event.data.object;
  ok(shape === 'items' ? (!('current_period_end' in sample) && sample.items.data.length === 1)
                       : ('current_period_end' in sample && !sample.items), 'fixture is not the ' + shape + ' shape');
  ok(steps.length >= 7, 'the replay lost a step');
  let lastApplied = null;
  const seen = new Set();
  for (const step of steps) {
    const raw = JSON.stringify(step.event);
    const v = await verify(raw, H.headerFor(step, raw, SECRET, NOW_SEC));
    if (step.forge) {
      eq(v.ok, false, step.name + ' verified');
      eq(v.reason, step.body, step.name + ' refusal reason');
      eq(step.http, 400, step.name + ' status');
      continue;
    }
    eq(v.ok, true, step.name + ' did not verify');
    ok(W.userIdFrom(step.event.data.object) === 'user-1', step.name + ': no member id in metadata');
    if (seen.has(step.event.id)) {
      eq(step.body, 'duplicate_ignored', step.name + ' re-applies a seen event');
    } else {
      seen.add(step.event.id);
      eq(step.body, 'applied', step.name);
      lastApplied = webhookWrites(step.event, NOW_MS);
      // and the pure module agrees with the webhook path
      const d = B.decide(step.event, NOW_MS);
      eq(d.tier, lastApplied.ent.tier, step.name + ' tier vs decide()');
      eq(d.expiresAt, lastApplied.ent.expiresAt, step.name + ' expiry vs decide()');
    }
    // the state the member reads after this step is the last APPLIED event's
    eq(lastApplied.entitlement, step.expect.entitlement, step.name + ' entitlement');
    eq(lastApplied.status, step.expect.subscription_status, step.name + ' status');
    eq(lastApplied.cancel, step.expect.cancel_at_period_end, step.name + ' cancel flag');
    const end = lastApplied.ent.expiresAt ? Math.round(Date.parse(lastApplied.ent.expiresAt) / 1000) : null;
    eq(end, step.expect.period_end, step.name + ' period end');
  }
});

t('billingMismatches reads a v_my_billing row the way the harness asserts it', () => {
  const exp = { entitlement: 'pro', subscription_status: 'past_due', cancel_at_period_end: false, period_end: NOW_SEC };
  eq(H.billingMismatches({ entitlement: 'pro', subscription_status: 'past_due', cancel_at_period_end: false,
    current_period_end: new Date(NOW_MS).toISOString() }, exp), [], 'a matching row');
  ok(H.billingMismatches({ entitlement: 'free', subscription_status: 'past_due', cancel_at_period_end: false,
    current_period_end: new Date(NOW_MS).toISOString() }, exp).length === 1, 'a wrong entitlement passed');
  ok(H.billingMismatches(null, exp).length === 1, 'a missing row passed');
});

/* ======================================================================
   4. THE HARNESS REFUSES TO RUN OUTSIDE TEST MODE
   ====================================================================== */

const goodEnv = {
  STRIPE_SECRET_KEY: 'sk_test_x', STRIPE_WEBHOOK_SECRET: 'whsec_x',
  CFL_TEST_EMAIL: 'e2e@example.invalid', CFL_TEST_PASSWORD: 'x',
};

t('assertTestMode accepts only a test key, and refuses any live key in the environment', () => {
  eq(H.assertTestMode(goodEnv), true, 'a complete test-mode env');
  const refuses = (env, why) => {
    let refused = false;
    try { H.assertTestMode(env); } catch (e) { refused = e instanceof H.Refusal; }
    ok(refused, 'not refused: ' + why);
  };
  refuses(Object.assign({}, goodEnv, { STRIPE_SECRET_KEY: 'sk_live_x' }), 'live secret key');
  refuses(Object.assign({}, goodEnv, { STRIPE_SECRET_KEY: 'rk_test_x' }), 'restricted key');
  refuses(Object.assign({}, goodEnv, { STRIPE_SECRET_KEY: '' }), 'no key');
  refuses(Object.assign({}, goodEnv, { SOMETHING_ELSE: 'rk_live_x' }), 'a live key anywhere in env');
  refuses(Object.assign({}, goodEnv, { STRIPE_WEBHOOK_SECRET: 'not_whsec' }), 'bad webhook secret');
  refuses(Object.assign({}, goodEnv, { STRIPE_PRICE_ID: 'prod_x' }), 'a product id where a price id goes');
  refuses(Object.assign({}, goodEnv, { CFL_TEST_PASSWORD: '' }), 'no test member');
});

t('only a test-mode checkout session is accepted', () => {
  eq(H.checkoutUrlIsTestMode('https://checkout.stripe.com/c/pay/cs_test_a1b2#x'), true, 'test');
  eq(H.checkoutUrlIsTestMode('https://checkout.stripe.com/c/pay/cs_live_a1b2#x'), false, 'live');
  eq(H.checkoutUrlIsTestMode('https://evil.example/cs_test_'), false, 'wrong host');
});

t('the API version that moved current_period_end is flagged', () => {
  eq(H.periodEndMovedOff('2025-03-31.basil'), true, 'basil');
  eq(H.periodEndMovedOff('2025-09-30.clover'), true, 'later');
  eq(H.periodEndMovedOff('2024-06-20'), false, 'earlier');
  eq(H.periodEndMovedOff(null), false, 'unknown is reported separately, not as moved');
});

t('run as a program with no key, or a live key, it exits 2 before any request', () => {
  const script = root('build/stripe-test-e2e.js');
  const base = { PATH: process.env.PATH, HOME: process.env.HOME };
  // HTTPS_PROXY pointed at a closed port: if the script reached the network
  // it would fail differently, not exit 2 with REFUSED.
  const cases = [
    {},
    { STRIPE_SECRET_KEY: 'sk_live_abc', STRIPE_WEBHOOK_SECRET: 'whsec_x', CFL_TEST_EMAIL: 'a', CFL_TEST_PASSWORD: 'b' },
  ];
  cases.forEach(extra => {
    const r = spawnSync(process.execPath, [script], {
      env: Object.assign({}, base, extra, { HTTPS_PROXY: 'http://127.0.0.1:9' }), encoding: 'utf8', timeout: 20000,
    });
    eq(r.status, 2, 'exit status for ' + JSON.stringify(Object.keys(extra)) + ' (stderr: ' + r.stderr + ')');
    ok(/REFUSED/.test(r.stderr), 'no REFUSED line');
  });
});

t('the harness posts to the function this repo deploys, and checks its events', () => {
  const src = fs.readFileSync(root('build/stripe-test-e2e.js'), 'utf8');
  ok(/\/functions\/v1`/.test(src), 'the default functions base is not the project\'s /functions/v1');
  ok(/\/stripe-webhook`/.test(src) && /\/stripe-checkout`/.test(src), 'function paths');
  ok(/rest\/v1\/v_my_billing/.test(src), 'it does not read entitlement back through v_my_billing');
  H.WEBHOOK_EVENTS.forEach(e => ok(B.HANDLED.indexOf(e) !== -1, e + ' is not handled by the lifecycle'));
});

// ------------------------------------------------------------------ run
(async () => {
  for (const [name, fn] of queue) {
    try { await fn(); passed++; } catch (e) { failures.push(name + ' — ' + e.message); }
  }
  if (failures.length) {
    console.log(`\n  ${passed} passed, ${failures.length} FAILED\n`);
    failures.forEach(f => console.log(`  ✗ ${f}\n`));
    process.exit(1);
  }
  console.log(`\n  ${passed} passed — the deployed webhook's own code verifies Stripe's scheme and agrees with the lifecycle.\n`);
})();
