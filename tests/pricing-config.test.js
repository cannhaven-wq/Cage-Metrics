/* ==========================================================================
   tests/pricing-config.test.js — the page can only say what is true about price.

   The CFL Pro price is T-067, an owner decision (CRITICAL_GATES item 7), and it
   is not set. So the one config that would hold it — entitlements.js::PLANS —
   holds null, and pricing.html renders from it. These assertions make three
   failures impossible to ship by accident:

     - a page that states a price nobody decided (pricing.html used to say
       "around $10–15 a month" while T-067's own stated preference was a
       different range, and neither was a decision);
     - a price typed into HTML instead of into the config, so the page and the
       Stripe price can disagree;
     - a "price not set" state that renders as a blank, a $0 or a "from".

   Run:  node tests/pricing-config.test.js
   ========================================================================== */
'use strict';
const fs = require('fs');
const path = require('path');

const root = f => path.join(__dirname, '..', f);
const read = f => fs.readFileSync(root(f), 'utf8');
const fresh = () => { delete require.cache[require.resolve('../entitlements.js')]; return require('../entitlements.js'); };

const E = fresh();
const PRICING = read('pricing.html');

let passed = 0;
const failures = [];
function t(name, fn) { try { fn(); passed++; } catch (e) { failures.push(name + ' — ' + e.message); } }
function ok(c, m) { if (!c) throw new Error(m); }
function eq(a, b, m) { if (a !== b) throw new Error((m || 'value') + ': expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a)); }

const noHtmlComments = s => s.replace(/<!--[\s\S]*?-->/g, ' ');
// Any dollar amount that is not zero: $9, $9.99, $10–15, $ 79.
const NONZERO_DOLLARS = /\$\s*(?!0(?:\.0+)?\b)\d/;

/* ----------------------------------------------------------- the config */

t('every plan has an id, a label, an interval and a null amount', () => {
  ok(Array.isArray(E.PLANS) && E.PLANS.length >= 1, 'no PLANS in entitlements.js');
  const ids = new Set();
  E.PLANS.forEach(p => {
    ok(p.id && !ids.has(p.id), 'missing or duplicate plan id ' + p.id);
    ids.add(p.id);
    ok(p.label, p.id + ' has no label');
    ok(['month', 'year'].indexOf(p.interval) !== -1, p.id + ' has interval ' + p.interval);
    eq(p.amount_cents, null,
       p.id + ' carries an amount. The price is ' + E.PRICE_DECISION + ', an owner decision; ' +
       'if it has genuinely been decided, update this test in the same PR that creates the Stripe price');
  });
});

t('the price decision is named, so nobody mistakes null for an oversight', () => {
  eq(E.PRICE_DECISION, 'T-067', 'PRICE_DECISION');
});

t('an unset price reads "Price not set", never blank, zero or a range', () => {
  E.PLANS.forEach(p => {
    eq(E.priceIsSet(p), false, p.id + ' reads as set');
    eq(E.priceLabel(p), 'Price not set', p.id + ' label');
  });
  [{ amount_cents: 0 }, { amount_cents: -100 }, { amount_cents: 9.99 }, { amount_cents: '999' },
   { amount_cents: undefined }, null, undefined].forEach(p =>
    eq(E.priceLabel(p), 'Price not set', 'a malformed amount ' + JSON.stringify(p) + ' was rendered as a price'));
});

t('a set price renders exactly, so the day it is set the page is right', () => {
  // Exercised on a COPY: the shipped config stays null.
  eq(E.priceLabel({ amount_cents: 999, currency: 'usd', interval: 'month' }), '$9.99 / month', 'monthly');
  eq(E.priceLabel({ amount_cents: 7900, currency: 'usd', interval: 'year' }), '$79.00 / year', 'yearly');
  const rows = E.planRows();
  eq(rows.length, E.PLANS.length, 'planRows length');
  rows.forEach(r => { eq(r.price, 'Price not set', r.id); eq(r.set, false, r.id + ' set'); });
});

t('the monthly plan is the one the checkout function can sell', () => {
  const monthly = E.PLANS.filter(p => p.interval === 'month')[0];
  ok(monthly, 'no monthly plan');
  eq(monthly.stripe_price_secret, 'STRIPE_PRICE_ID', 'monthly plan secret');
  ok(/Deno\.env\.get\('STRIPE_PRICE_ID'\)/.test(read('supabase/functions/stripe-checkout/index.ts')),
     'the checkout function no longer reads STRIPE_PRICE_ID');
});

/* ------------------------------------------------------------ the page */

t('pricing.html renders the price lines from the config', () => {
  ok(/cflEntitlements\.planRows\(\)/.test(PRICING), 'pricing.html does not render from planRows()');
  ok(/id="planPrices"/.test(PRICING), 'no #planPrices list on pricing.html');
  E.PLANS.forEach(p =>
    ok(new RegExp('data-plan="' + p.id + '"[^>]*>[\\s\\S]*?Price not set').test(PRICING),
       'the served (no-JS) line for ' + p.id + ' does not say "Price not set"'));
});

t('pricing.html says "price not set" in its own words while amounts are null', () => {
  const txt = noHtmlComments(PRICING).replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
  ok(/Price not set/.test(txt), 'the visible page never says the price is not set');
  ok(/no price has been set/i.test(txt), 'the FAQ does not say no price has been set');
  [/expected (starting )?price/i, /around \$/i, /starting at/i, /from \$/i, /founding (rate|price)/i]
    .forEach(re => ok(!re.test(txt), 'pricing.html anticipates a price: ' + re));
});

t('no amount is hardcoded anywhere in pricing.html (markup, attributes or script)', () => {
  // $0 for the free tier is the only dollar figure the page may carry. Meta
  // tags, JSON-LD and inline scripts count: a crawler reads them too.
  const src = noHtmlComments(PRICING);
  const hits = (src.match(/\$\s*\d[\d.,]*(?:\s*[–-]\s*\$?\d+)?/g) || [])
    .filter(m => NONZERO_DOLLARS.test(m));
  ok(hits.length === 0, 'pricing.html hardcodes an amount: ' + hits.join(', '));
  ok(!/\b\d+(\.\d{2})?\s*(USD|dollars)\b/i.test(src), 'pricing.html hardcodes an amount in words');
});

t('no member-facing billing page hardcodes a CFL price', () => {
  ['account.html', 'signup.html', 'watchlist.html', 'login.html'].forEach(f => {
    const src = noHtmlComments(read(f));
    ok(!NONZERO_DOLLARS.test(src), f + ' carries a dollar amount');
  });
  // Elsewhere a dollar figure may describe someone else (about.html describes
  // touts charging one). It must never sit next to CFL Pro.
  fs.readdirSync(root('.')).filter(f => /\.html$/.test(f)).forEach(f => {
    const txt = noHtmlComments(read(f)).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
    const near = /(CFL Pro|Pro plan|Pro tier|subscription)[^.]{0,80}\$\s*[1-9]|\$\s*[1-9][^.]{0,80}(CFL Pro|Pro plan|Pro tier)/i;
    ok(!near.test(txt), f + ' states a price for CFL Pro');
  });
});

if (failures.length) {
  console.log(`\n  ${passed} passed, ${failures.length} FAILED\n`);
  failures.forEach(f => console.log(`  ✗ ${f}\n`));
  process.exit(1);
}
console.log(`\n  ${passed} passed — no price is shown that nobody decided.\n`);
