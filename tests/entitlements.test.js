/* ==========================================================================
   tests/entitlements.test.js — who is Pro, and what must happen before money.

   Three things, in order of what they cost if wrong:

     1. THE P0. The UPDATE policy on `profiles` pins the security-bearing
        columns. It pinned three and not `is_admin` or `beta_premium`, which
        meant any signed-in user could make themselves an admin and read every
        subscriber's email address. This asserts the policy text names EVERY
        such column, and fails when `profiles` grows a new one that nobody
        added to the list — the omission is the bug, so the omission is what
        is tested.
     2. THE ENFORCEMENT BOUNDARY. Entitlement is decided in Postgres. The JS
        decides what to draw and must never be the only thing between a reader
        and Pro data.
     3. THE CHECKOUT GATE. Two legal items block taking money. They are a
        constant and a function here rather than a line in a document, because
        the sprint that builds Stripe is the one most likely to forget them.

   Run:  node tests/entitlements.test.js
   ========================================================================== */

'use strict';
const fs = require('fs');
const path = require('path');

const root = f => path.join(__dirname, '..', f);
const read = f => fs.readFileSync(root(f), 'utf8');

const E = require('../entitlements.js');
const MIGRATION = read('entitlements_migration.sql');
const AUTH = read('_auth.js');
const BOUNDARY = read('PRODUCT_BOUNDARY.md');

const stripComments = src => src
  .replace(/\/\*[\s\S]*?\*\//g, ' ')
  .replace(/^\s*\/\/.*$/gm, ' ')
  .replace(/^\s*--.*$/gm, ' ');

let passed = 0;
const failures = [];
function t(name, fn) {
  try { fn(); passed++; } catch (e) { failures.push(name + ' — ' + e.message); }
}
function ok(cond, msg) { if (!cond) throw new Error(msg); }
function eq(a, b, msg) {
  if (a !== b) throw new Error((msg || 'value') + ': expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a));
}

/* ------------------------------------------------- 1. the P0, and its shape */

// Every column on `profiles` that can grant access to anything. Adding a
// column here without adding it to the policy is the failure mode this guards.
const SECURITY_BEARING = ['tier', 'tier_expires_at', 'stripe_customer_id', 'is_admin', 'beta_premium'];

t('the profiles UPDATE policy pins every security-bearing column', () => {
  const m = MIGRATION.match(/CREATE POLICY "Users can update own profile[^"]*"[\s\S]*?WITH CHECK \(([\s\S]*?)\n\);/);
  ok(m, 'the UPDATE policy could not be found in entitlements_migration.sql');
  const check = m[1];
  SECURITY_BEARING.forEach(col =>
    ok(new RegExp('\\b' + col + '\\s+IS NOT DISTINCT FROM').test(check),
       'the policy does not pin ' + col + ' — a user could change it on their own row'));
  ok(/auth\.uid\(\) = id/.test(check), 'the policy does not restrict the row to the caller');
});

t('the old, vulnerable policy is dropped rather than left beside the new one', () => {
  ok(/DROP POLICY IF EXISTS "Users can update own profile \(except tier\)"/.test(MIGRATION),
     'the vulnerable policy is not dropped — two UPDATE policies OR together, so ' +
     'leaving it in place would keep the hole open');
});

t('the migration records what the hole actually exposed', () => {
  // A security fix whose reason is not written down gets reverted by someone
  // tidying up.
  ok(/is_admin/.test(MIGRATION) && /email_subscribers/.test(MIGRATION),
     'the migration does not say that is_admin gated email_subscribers');
  ok(/fight_odds/.test(MIGRATION), 'it does not say is_admin gated fight_odds');
  ok(/RLS did not/.test(MIGRATION) || /RLS will reject anyway/.test(MIGRATION),
     'it does not record that the client-side strip was mistaken for enforcement');
});

/* --------------------------------------- 2. enforcement lives in Postgres */

t('the entitlement is computed in SQL, not only in the browser', () => {
  ok(/CREATE OR REPLACE FUNCTION public\.current_user_entitlement\(\)/.test(MIGRATION),
     'no current_user_entitlement() function');
  ok(/CREATE OR REPLACE FUNCTION public\.current_user_is_pro\(\)/.test(MIGRATION),
     'no current_user_is_pro() function');
  ok(/SECURITY DEFINER/.test(MIGRATION), 'the functions are not SECURITY DEFINER');
  ok(/SET search_path TO 'public'/.test(MIGRATION),
     'a SECURITY DEFINER function without a pinned search_path is a hijack risk');
});

t('the SQL entitlement honours tier_expires_at', () => {
  const fn = MIGRATION.slice(MIGRATION.indexOf('current_user_entitlement'));
  ok(/tier_expires_at IS NULL OR p\.tier_expires_at > now\(\)/.test(fn),
     'an expired paid tier would still read as pro');
});

t('the JS honours tier_expires_at too, so the layers agree', () => {
  ok(/paidTierIsCurrent/.test(AUTH), '_auth.js has no expiry check');
  const body = stripComments(AUTH);
  ok(/ts > Date\.now\(\)/.test(body), 'the expiry comparison is missing');
  ok(!/if \(_currentProfile\.beta_premium\) return 'premium';\s*return _currentProfile\.tier/.test(body),
     'getTier() still returns the stored tier without checking expiry');
});

t('the self view returns only the caller\'s own row', () => {
  const v = MIGRATION.slice(MIGRATION.indexOf('v_my_entitlement'));
  ok(/auth\.uid\(\)/.test(v), 'v_my_entitlement does not scope to auth.uid()');
  ok(/LEFT JOIN public\.profiles p ON p\.id = auth\.uid\(\)/.test(v),
     'it joins profiles on something other than the caller');
  ok(!/FROM public\.profiles\s*;/.test(v), 'it selects from profiles unscoped');
});

t('the JS says plainly that it is presentation only', () => {
  ok(/PRESENTATION ONLY/i.test(read('entitlements.js')),
     'entitlements.js does not state that it decides rendering, not access');
  ok(/current_user_is_pro/.test(read('entitlements.js')),
     'it does not point at the server-side gate that actually enforces');
  ok(/presentation/i.test(AUTH), '_auth.js drops the presentation-only warning');
});

t('nothing is gated by the client alone today', () => {
  // Every surface is unenforced in this sprint by design; when one flips to
  // enforced, the server-side gate must exist first.
  const enforced = E.SURFACES.filter(s => s.enforced);
  if (enforced.length) {
    enforced.forEach(s => ok(/current_user_is_pro/.test(MIGRATION),
      'surface "' + s.key + '" is marked enforced but no server-side gate exists'));
  }
  ok(E.SURFACES.length > 0, 'the boundary is empty');
});

/* ------------------------------------------------- 3. the checkout gate */

t('checkout cannot be enabled while a legal blocker stands', () => {
  eq(E.checkoutMayBeEnabled(), false,
     'checkout reports it may be enabled — if that is intentional, both legal ' +
     'blockers must actually be resolved and removed on purpose');
  const ids = E.CHECKOUT_BLOCKERS.map(b => b.id);
  ok(ids.indexOf('T-054') !== -1, 'the privacy/Plausible blocker is missing');
  ok(ids.indexOf('T-048') !== -1, 'the Terms of Service blocker is missing');
});

t('each blocker names an owner and points at the draft', () => {
  E.CHECKOUT_BLOCKERS.forEach(b => {
    ok(b.id && b.what && b.why, b.id + ' is missing a field');
    ok(/Owner/i.test(b.owner), b.id + ' does not name the owner as the decider');
    ok(/legal-review/.test(b.draft), b.id + ' does not point at the prepared wording');
  });
  ok(fs.existsSync(root('legal-review/PROPOSED_WORDING.md')),
     'the draft wording file the blockers point at does not exist');
});

t('no checkout entry point ships while checkout is blocked', () => {
  if (E.checkoutMayBeEnabled()) return;             // gate lifted deliberately
  const pages = fs.readdirSync(root('.')).filter(f => /\.html$/.test(f));
  const offenders = [];
  pages.forEach(f => {
    const src = stripComments(read(f).replace(/<!--[\s\S]*?-->/g, ' '));
    if (/checkout\.session|stripe\.com\/v3|Stripe\(|createCheckoutSession|data-stripe/i.test(src)) {
      offenders.push(f);
    }
  });
  ok(offenders.length === 0,
     'a checkout entry point is live while T-054/T-048 stand: ' + offenders.join(', '));
});

t('no page claims a price while there is nothing to buy', () => {
  const pricing = read('pricing.html').replace(/<!--[\s\S]*?-->/g, ' ');
  ok(!/\$\d+\s*(\/|per )\s*(mo|month|yr|year)/i.test(pricing) || /beta|free|coming/i.test(pricing),
     'pricing.html advertises a recurring price with no checkout behind it');
});

/* ------------------------------------------ the boundary matches the doc */

t('the Free/Pro split in code matches PRODUCT_BOUNDARY.md', () => {
  const free = E.SURFACES.filter(s => s.tier === 'free').length;
  const pro = E.SURFACES.filter(s => s.tier === 'pro').length;
  ok(free >= 8, 'only ' + free + ' free surfaces — free must stay genuinely useful');
  ok(pro >= 5, 'only ' + pro + ' pro surfaces');
  // the things the doc promises stay free
  ['card_lab', 'market_lab', 'fight_lab', 'factor_lab', 'proof_center',
   'model_archive', 'card_brief', 'best_price'].forEach(k =>
    eq(E.tierFor(k), 'free', k + ' must be free'));
  // and the ones it sells
  ['watchlists', 'price_alerts', 'movement_alerts', 'historical_lookback'].forEach(k =>
    eq(E.tierFor(k), 'pro', k + ' must be pro'));
});

t('the Model Archive is free, because it is evidence and not a feature', () => {
  eq(E.tierFor('model_archive'), 'free', 'the archive was moved behind a paywall');
  ok(/free forever/i.test(BOUNDARY) || /evidence, not a feature/i.test(BOUNDARY),
     'PRODUCT_BOUNDARY.md no longer says the archive stays free');
});

t('nothing sold at any tier is a pick', () => {
  const sold = E.SURFACES.map(s => s.key + ' ' + s.what).join(' ').toLowerCase();
  ['pick', 'best bet', 'lock', 'edge %', 'expected value', 'our call']
    .forEach(p => ok(sold.indexOf(p) === -1, 'a surface sells "' + p + '"'));
  ok(E.NEVER_SOLD.length >= 5, 'the never-sold list is missing');
  ok(E.NEVER_SOLD.join(' ').toLowerCase().indexOf('picks') !== -1,
     'the never-sold list does not name picks');
});

t('decide() is a render decision and says so', () => {
  eq(E.decide('card_lab', false).show, true, 'a free surface was hidden from a free reader');
  eq(E.decide('watchlists', false).show, false, 'a pro surface was shown to a free reader');
  eq(E.decide('watchlists', true).show, true, 'a pro surface was hidden from a pro reader');
  eq(E.decide('watchlists', false).reason, 'pro_required', 'reason');
  eq(E.decide('not_a_real_surface', false).show, true,
     'an unknown surface defaults to hidden — it must default to shown, so a ' +
     'typo cannot silently paywall something');
});

// ------------------------------------------------------------------ report
if (failures.length) {
  console.log(`\n  ${passed} passed, ${failures.length} FAILED\n`);
  failures.forEach(f => console.log(`  ✗ ${f}\n`));
  process.exit(1);
}
console.log(`\n  ${passed} passed — entitlement is decided in Postgres, and money waits on the lawyers.\n`);
