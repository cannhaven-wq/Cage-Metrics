// =============================================================================
// stripe-checkout — creates a Stripe Checkout Session for CFL Pro.
// =============================================================================
// IT REFUSES TO RUN. That is its current, intended behaviour.
//
// Two compliance items must be resolved before CFL takes a payment:
//
//   T-054  privacy.html does not name Plausible, a third-party analytics
//          processor running on every page
//   T-048  there is no Terms of Service page at all
//
// The owner's instruction was that those must block enabling live checkout
// while NOT blocking this being built and tested. So the whole path exists,
// is deployed and is exercised by tests — and the first thing it does is
// return 503 with the blockers named.
//
// The gate is here, server-side, and not only in entitlements.js. A gate that
// lives in the browser is not a gate: the publishable key is public by design
// and this endpoint is reachable without loading any of our JavaScript.
//
// TO TURN CHECKOUT ON: resolve both items, then remove them from
// CHECKOUT_BLOCKERS below AND from entitlements.js. Two deliberate edits in
// two files, each with a reviewer attached. Not a default that slips through.
// =============================================================================

import 'jsr:@supabase/functions-js/edge-runtime.d.ts';
import { createClient } from 'jsr:@supabase/supabase-js@2';

const CHECKOUT_BLOCKERS = [
  { id: 'T-054', what: 'privacy.html does not disclose Plausible analytics' },
  { id: 'T-048', what: 'no Terms of Service page exists' },
];

const CORS = {
  'Access-Control-Allow-Origin': 'https://cannonfightlab.com',
  'Access-Control-Allow-Headers': 'authorization, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...CORS, 'Content-Type': 'application/json' },
  });
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: CORS });
  if (req.method !== 'POST') return json({ error: 'method_not_allowed' }, 405);

  // ---- GATE 1: the legal blockers. Before anything else, including auth. ---
  if (CHECKOUT_BLOCKERS.length > 0) {
    return json({
      error: 'checkout_disabled',
      message:
        'CFL is not taking payments yet. Checkout is blocked until two ' +
        'compliance items are resolved.',
      blockers: CHECKOUT_BLOCKERS,
    }, 503);
  }

  // ---- GATE 2: fail closed without configuration --------------------------
  // Everything below is unreachable today. It is written, and tested, so that
  // turning checkout on is a configuration change rather than a build.
  const STRIPE_SECRET_KEY = Deno.env.get('STRIPE_SECRET_KEY');
  const STRIPE_PRICE_ID = Deno.env.get('STRIPE_PRICE_ID');
  const SITE_URL = Deno.env.get('SITE_URL') ?? 'https://cannonfightlab.com';
  if (!STRIPE_SECRET_KEY || !STRIPE_PRICE_ID) {
    return json({ error: 'not_configured' }, 503);
  }

  // ---- the member must be signed in, proven by their own JWT --------------
  const authHeader = req.headers.get('Authorization') ?? '';
  if (!authHeader.startsWith('Bearer ')) return json({ error: 'unauthenticated' }, 401);

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL')!,
    Deno.env.get('SUPABASE_ANON_KEY')!,
    { global: { headers: { Authorization: authHeader } } },
  );
  const { data: userData, error: userErr } = await supabase.auth.getUser();
  if (userErr || !userData?.user) return json({ error: 'unauthenticated' }, 401);
  const user = userData.user;

  // Already entitled? Do not sell the same thing twice.
  const { data: ent } = await supabase.from('v_my_entitlement').select('*').maybeSingle();
  if (ent?.entitlement === 'pro' && !ent?.is_beta) {
    return json({ error: 'already_subscribed' }, 409);
  }

  // Reuse an existing Stripe customer so a member does not accumulate them.
  const admin = createClient(
    Deno.env.get('SUPABASE_URL')!,
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
  );
  const { data: profile } = await admin
    .from('profiles').select('stripe_customer_id').eq('id', user.id).maybeSingle();

  const form = new URLSearchParams();
  form.set('mode', 'subscription');
  form.set('line_items[0][price]', STRIPE_PRICE_ID);
  form.set('line_items[0][quantity]', '1');
  form.set('success_url', `${SITE_URL}/account.html?checkout=done`);
  form.set('cancel_url', `${SITE_URL}/pricing.html?checkout=cancelled`);
  // Both of these carry the member id back to us on the webhook, so the
  // subscription can be matched to an account without guessing from an email.
  form.set('client_reference_id', user.id);
  form.set('subscription_data[metadata][cfl_user_id]', user.id);
  form.set('metadata[cfl_user_id]', user.id);
  if (profile?.stripe_customer_id) form.set('customer', profile.stripe_customer_id);
  else if (user.email) form.set('customer_email', user.email);

  const res = await fetch('https://api.stripe.com/v1/checkout/sessions', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${STRIPE_SECRET_KEY}`,
      'Content-Type': 'application/x-www-form-urlencoded',
      // Stripe idempotency: a double-clicked button must not create two
      // sessions, and therefore cannot create two subscriptions.
      'Idempotency-Key': `cfl_checkout_${user.id}_${new Date().toISOString().slice(0, 13)}`,
    },
    body: form.toString(),
  });

  if (!res.ok) {
    console.error('[stripe-checkout] session creation failed', res.status);
    return json({ error: 'stripe_error' }, 502);
  }
  const session = await res.json();
  return json({ url: session.url });
});
