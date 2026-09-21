// =============================================================================
// stripe-webhook — hears back from Stripe and keeps entitlement true.
// =============================================================================
// Thin on purpose. The decision of what an event MEANS lives in
// billing-lifecycle.js, which is a pure function and is tested exhaustively in
// Node without a Stripe account. This file does four things:
//
//   1. verify the signature          (reject anything unsigned or stale)
//   2. dedupe on the Stripe event id (Stripe delivers at least once)
//   3. ask billing-lifecycle what it means
//   4. write profiles.tier / tier_expires_at
//
// WHY IT ALWAYS RETURNS 200 ON A HANDLED-BUT-UNAPPLIABLE EVENT
// A non-2xx makes Stripe retry, with backoff, for days. That is right for "I
// am broken" and wrong for "I do not know this member yet". So: a bad
// signature is 400, a genuine failure to write is 500 (retry me), and anything
// we understood but could not apply is 200 with the reason recorded in
// billing_events. The row is the audit trail; the status code is flow control.
//
// verify_jwt MUST be false: Stripe does not send a Supabase JWT. The signature
// check below is the authentication, which is why it runs before anything else
// and why the function refuses outright when the secret is missing.
// =============================================================================

import 'jsr:@supabase/functions-js/edge-runtime.d.ts';
import { createClient } from 'jsr:@supabase/supabase-js@2';

// ---------------------------------------------------------------------------
// The lifecycle rules, kept byte-identical to billing-lifecycle.js.
// tests/billing-lifecycle.test.js asserts the two copies agree, because an
// edge function cannot import from the repo root at deploy time.
// ---------------------------------------------------------------------------
const PRO_TIER = 'premium';
const FREE_TIER = 'free';
const STATUS_KEEPS_PERIOD = ['active', 'trialing', 'past_due'];
const STATUS_ENDS_NOW = ['unpaid', 'incomplete', 'incomplete_expired', 'paused'];
const HANDLED = [
  'checkout.session.completed',
  'customer.subscription.created',
  'customer.subscription.updated',
  'customer.subscription.deleted',
  'invoice.paid',
  'invoice.payment_succeeded',
  'invoice.payment_failed',
];

function iso(unix: unknown): string | null {
  const n = Number(unix);
  if (!isFinite(n) || n <= 0) return null;
  return new Date(n * 1000).toISOString();
}
function idOf(v: unknown): string | null {
  if (!v) return null;
  return typeof v === 'string' ? v : ((v as any).id ? String((v as any).id) : null);
}
function entitlementFor(status: string, endIso: string | null, now: number) {
  const endMs = endIso ? Date.parse(endIso) : NaN;
  const running = isFinite(endMs) && endMs > now;
  if (STATUS_ENDS_NOW.includes(status)) return { tier: FREE_TIER, expiresAt: null, reason: 'status_' + status + '_ends_access' };
  if (STATUS_KEEPS_PERIOD.includes(status)) {
    if (!endIso) return { tier: PRO_TIER, expiresAt: null, reason: 'status_' + status + '_no_period_end' };
    return { tier: PRO_TIER, expiresAt: endIso, reason: 'status_' + status };
  }
  if (status === 'canceled') {
    return running
      ? { tier: PRO_TIER, expiresAt: endIso, reason: 'canceled_but_period_paid' }
      : { tier: FREE_TIER, expiresAt: null, reason: 'canceled_period_over' };
  }
  return { tier: FREE_TIER, expiresAt: null, reason: 'unknown_status_' + status };
}
function userIdFrom(o: any): string | null {
  if (!o) return null;
  if (o.client_reference_id) return String(o.client_reference_id);
  if (o.metadata?.cfl_user_id) return String(o.metadata.cfl_user_id);
  if (o.subscription_details?.metadata?.cfl_user_id) return String(o.subscription_details.metadata.cfl_user_id);
  return null;
}

// ---------------------------------------------------------------------------
// Stripe signature verification, in Web Crypto. v1 HMAC-SHA256 over
// "<timestamp>.<raw body>", compared in constant time, with a tolerance so a
// captured request cannot be replayed indefinitely.
// ---------------------------------------------------------------------------
const TOLERANCE_SECONDS = 300;

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function verifyStripeSignature(raw: string, header: string, secret: string, nowSec: number) {
  if (!header) return { ok: false, reason: 'missing_signature' };
  const parts = Object.fromEntries(
    header.split(',').map((kv) => { const i = kv.indexOf('='); return [kv.slice(0, i).trim(), kv.slice(i + 1).trim()]; }),
  ) as Record<string, string>;
  const t = Number(parts['t']);
  const given = parts['v1'];
  if (!isFinite(t) || !given) return { ok: false, reason: 'malformed_signature' };
  if (Math.abs(nowSec - t) > TOLERANCE_SECONDS) return { ok: false, reason: 'timestamp_outside_tolerance' };

  const key = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'],
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(`${t}.${raw}`));
  const expected = Array.from(new Uint8Array(sig)).map((b) => b.toString(16).padStart(2, '0')).join('');
  return timingSafeEqual(expected, given) ? { ok: true, reason: 'verified' } : { ok: false, reason: 'signature_mismatch' };
}

Deno.serve(async (req: Request) => {
  if (req.method !== 'POST') return new Response('method_not_allowed', { status: 405 });

  const WEBHOOK_SECRET = Deno.env.get('STRIPE_WEBHOOK_SECRET');
  const SERVICE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');
  const SUPA_URL = Deno.env.get('SUPABASE_URL');
  // Fail CLOSED. An unconfigured webhook that returns 200 would tell Stripe
  // its events were handled when nothing was recorded at all.
  if (!WEBHOOK_SECRET || !SERVICE_KEY || !SUPA_URL) {
    console.error('[stripe-webhook] not configured — refusing');
    return new Response('not_configured', { status: 503 });
  }

  const raw = await req.text();
  const nowSec = Math.floor(Date.now() / 1000);
  const verdict = await verifyStripeSignature(raw, req.headers.get('stripe-signature') ?? '', WEBHOOK_SECRET, nowSec);
  if (!verdict.ok) {
    console.warn('[stripe-webhook] rejected:', verdict.reason);
    return new Response(verdict.reason, { status: 400 });
  }

  let event: any;
  try { event = JSON.parse(raw); } catch { return new Response('bad_json', { status: 400 }); }

  const admin = createClient(SUPA_URL, SERVICE_KEY);
  const o = event?.data?.object ?? {};
  const customerId = idOf(o.customer);
  const now = Date.now();

  // ---- 2. DEDUPE FIRST. The unique index is the lock. -----------------------
  const { error: dupeErr } = await admin.from('billing_events').insert({
    stripe_event_id: event.id,
    event_type: event.type,
    stripe_customer_id: customerId,
    outcome: 'received',
  });
  if (dupeErr) {
    // 23505 = already processed. Acknowledge; do not apply twice.
    if ((dupeErr as any).code === '23505') return new Response('duplicate_ignored', { status: 200 });
    console.error('[stripe-webhook] could not record event', dupeErr);
    return new Response('record_failed', { status: 500 });   // ask Stripe to retry
  }

  const finish = async (outcome: string, detail: string, extra: Record<string, unknown> = {}) => {
    await admin.from('billing_events')
      .update({ outcome, detail, ...extra })
      .eq('stripe_event_id', event.id);
    return new Response(outcome, { status: 200 });
  };

  if (!HANDLED.includes(event.type)) return await finish('ignored', 'unhandled_event_type');

  // ---- §resolving a member ------------------------------------------------
  // Stripe's metadata first; the stored customer id second. If neither
  // resolves, record and acknowledge — a later checkout.session.completed
  // links the customer and the next subscription event applies. Retrying
  // would not make the member appear.
  let userId = userIdFrom(o);
  if (!userId && customerId) {
    const { data: p } = await admin.from('profiles').select('id').eq('stripe_customer_id', customerId).maybeSingle();
    userId = p?.id ?? null;
  }
  if (!userId) return await finish('deferred', 'no_member_matched_yet', { stripe_customer_id: customerId });

  // ---- checkout completed: link only, never entitle -----------------------
  if (event.type === 'checkout.session.completed') {
    if (o.mode && o.mode !== 'subscription') return await finish('ignored', 'not_a_subscription_checkout');
    const { error } = await admin.from('profiles')
      .update({ stripe_customer_id: customerId, stripe_subscription_id: idOf(o.subscription) })
      .eq('id', userId);
    if (error) { console.error(error); return new Response('write_failed', { status: 500 }); }
    return await finish('linked', 'customer_linked_awaiting_subscription',
      { user_id: userId, subscription_id: idOf(o.subscription) });
  }

  // ---- invoices: note only. The subscription event carries the dates. -----
  if (event.type.startsWith('invoice.')) {
    return await finish('noted', event.type, { user_id: userId, subscription_id: idOf(o.subscription) });
  }

  // ---- the subscription: the only thing that sets entitlement ------------
  const status = event.type === 'customer.subscription.deleted' ? 'canceled' : String(o.status ?? '');
  const periodEnd = iso(o.current_period_end);
  const ent = entitlementFor(status, periodEnd, now);

  const { error: writeErr } = await admin.from('profiles').update({
    tier: ent.tier,
    tier_expires_at: ent.expiresAt,
    subscription_status: status,
    cancel_at_period_end: !!o.cancel_at_period_end,
    stripe_customer_id: customerId,
    stripe_subscription_id: idOf(o.id),
  }).eq('id', userId);

  if (writeErr) { console.error('[stripe-webhook] write failed', writeErr); return new Response('write_failed', { status: 500 }); }

  return await finish('applied', ent.reason, {
    user_id: userId,
    subscription_id: idOf(o.id),
    applied_tier: ent.tier,
    applied_expires_at: ent.expiresAt,
  });
});
