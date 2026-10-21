/* ==========================================================================
   tests/h2h-redirect.test.js — the retired Head-to-Head URL only redirects.

   Head-to-Head left the public site on 2026-10-16 (owner, T-103) and must not
   come back through its own stub. But it was the largest real-visitor entry
   point (T-055), and its old links name two fighters (h2h.html?a=<id>&b=<id>).
   So the stub sends a two-fighter link to that bout's Fight Lab page, and
   everything else to the card at /, as before.

   Pinned here:
     - no Head-to-Head UI: no picker, no comparison table, no stats, no nav,
       no Supabase client, no _shared.js;
     - noindex, canonical to /, a no-script refresh to /, and a backstop;
     - the redirect logic, executed with a fake location and fetch:
         two ids + a booking  -> fight.html?id=<that fight>
         rematch              -> the next upcoming booking, else the latest
         dead booking only    -> /
         no ids, one id, bad ids, same id twice, no rows, HTTP error,
         network error        -> /

   Run:  node tests/h2h-redirect.test.js
   ========================================================================== */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = f => path.join(__dirname, '..', f);
const HTML = fs.readFileSync(root('h2h.html'), 'utf8');
const SHARED = fs.readFileSync(root('_shared.js'), 'utf8');
const noComments = s => s.replace(/<!--[\s\S]*?-->/g, ' ');
const SCRIPT = (HTML.match(/<script>([\s\S]*?)<\/script>/) || [])[1];

let passed = 0;
const failures = [];
const queue = [];
const t = (name, fn) => queue.push([name, fn]);
function ok(c, m) { if (!c) throw new Error(m); }
function eq(a, b, m) { if (a !== b) throw new Error((m || 'value') + ': expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a)); }

// Run the stub's script with a fake browser. Resolves with where it went and
// what it asked for. Timers run instantly in order of delay, so the
// "slow lookup" backstop is exercised by a fetch that never settles.
function run(search, respond, today) {
  return new Promise(resolve => {
    const replaced = [];
    const requests = [];
    const timers = [];
    const RealDate = Date;
    const ctx = {
      URLSearchParams,
      location: { search, replace: u => replaced.push(u) },
      setTimeout: (fn, ms) => { timers.push([ms, fn]); },
      fetch: respond === undefined ? undefined : (url, opts) => { requests.push({ url, opts }); return respond(url); },
      Date: class extends RealDate { constructor(...a) { super(...(a.length ? a : [today || '2026-10-21T12:00:00Z'])); } },
    };
    vm.runInNewContext(SCRIPT, ctx);
    // let promise chains settle, then fire any timers in delay order
    setImmediate(() => setImmediate(() => setImmediate(() => {
      timers.sort((x, y) => x[0] - y[0]).forEach(([, fn]) => fn());
      resolve({ to: replaced[0], all: replaced, requests, timers: timers.map(x => x[0]) });
    })));
  });
}
const json = rows => () => Promise.resolve({ ok: true, json: () => Promise.resolve(rows) });

/* ----------------------------------------------------------- no H2H UI */

t('the stub renders no Head-to-Head product', () => {
  const body = noComments(HTML).replace(/^\s*\/\/.*$/gm, ' ');
  ['compareArea', 'renderCompare', 'renderPicker', 'compare-section', 'cfl-nav', 'cfl-footer',
   'Strikes landed', 'Takedown', 'Reach', 'Select two fighters', 'Clear matchup', '<input', '<form',
   '<table', 'supabase-js', '_shared.js', '_auth.js', 'cfl.render']
    .forEach(s => ok(body.indexOf(s) === -1, 'h2h.html carries Head-to-Head UI or app chrome: ' + s));
  ok(body.length < 6000, 'h2h.html has grown to ' + body.length + ' bytes — it is a stub, not a page');
  eq((HTML.match(/<script\b/g) || []).length, 1, 'number of scripts');
  ok(!/innerHTML|document\.write|appendChild|createElement/.test(SCRIPT), 'the script draws something');
  ok(!/<h1|<h2|<button/i.test(body), 'the stub has headings or buttons');
});

t('it reads only the fights it needs, through the public REST path, and writes nothing', () => {
  ok(/\/rest\/v1\/fights\?select=id,is_active,events\(event_date\)/.test(SCRIPT), 'the lookup is not the narrow fights read');
  ok(!/method\s*:/.test(SCRIPT), 'the lookup is not a plain GET');
  const url = (SHARED.match(/SUPABASE_URL = '([^']+)'/) || [])[1];
  const key = (SHARED.match(/SUPABASE_KEY = '([^']+)'/) || [])[1];
  ok(url && SCRIPT.indexOf("'" + url + "'") !== -1, 'the stub\'s project URL differs from _shared.js');
  ok(key && SCRIPT.indexOf("'" + key + "'") !== -1, 'the stub\'s publishable key differs from _shared.js');
  ok(!/service_role|sb_secret_/.test(HTML), 'a privileged key is in a public page');
});

t('noindex, canonical to the homepage, and a no-script fallback to /', () => {
  ok(/<meta name="robots" content="noindex, follow">/.test(HTML), 'not noindex');
  ok(/<link rel="canonical" href="https:\/\/cannonfightlab\.com\/">/.test(HTML), 'canonical is not the homepage');
  ok(/<noscript><meta http-equiv="refresh" content="0; url=\/"><\/noscript>/.test(HTML),
     'a reader without scripts is not sent to /');
  const refreshes = [...HTML.matchAll(/http-equiv="refresh" content="(\d+); url=([^"]+)"/g)];
  refreshes.forEach(m => eq(m[2], '/', 'every meta refresh goes to /'));
  const unconditional = noComments(HTML).replace(/<noscript>[\s\S]*?<\/noscript>/g, '')
    .match(/http-equiv="refresh" content="(\d+);/);
  ok(unconditional && Number(unconditional[1]) >= 3,
     'an immediate unconditional refresh would beat the lookup to it');
  ok(/href="\/">homepage<\/a>/.test(HTML), 'no visible link to the homepage');
});

t('the stub is not in the sitemap', () => {
  ok(!/h2h\.html/.test(fs.readFileSync(root('sitemap.xml'), 'utf8')), 'sitemap lists h2h.html');
});

/* ------------------------------------------------------- the redirect */

t('two fighters with one booking land on that fight', async () => {
  const r = await run('?a=3346&b=23821', json([{ id: 50565, is_active: true, events: { event_date: '2026-10-03' } }]));
  eq(r.to, 'fight.html?id=50565', 'destination');
  eq(r.all.length, 1, 'redirected more than once');
  ok(/fighter_a_id\.eq\.3346,fighter_b_id\.eq\.23821/.test(r.requests[0].url) &&
     /fighter_a_id\.eq\.23821,fighter_b_id\.eq\.3346/.test(r.requests[0].url), 'both corner orders are not asked for');
  eq(r.requests[0].opts.headers.apikey.indexOf('sb_publishable_'), 0, 'apikey header');
});

t('a rematch prefers the next upcoming booking', async () => {
  const r = await run('?a=1&b=2', json([
    { id: 10, is_active: true, events: { event_date: '2024-03-01' } },
    { id: 30, is_active: true, events: { event_date: '2026-12-12' } },
    { id: 20, is_active: true, events: { event_date: '2026-11-01' } },
  ]));
  eq(r.to, 'fight.html?id=20', 'not the nearest upcoming');
});

t('with nothing upcoming, the most recent bout', async () => {
  const r = await run('?b=2&a=1', json([
    { id: 10, is_active: true, events: { event_date: '2024-03-01' } },
    { id: 11, is_active: true, events: { event_date: '2025-08-09' } },
  ]));
  eq(r.to, 'fight.html?id=11', 'not the latest past bout');
});

t('a card on today\'s date counts as upcoming', async () => {
  const r = await run('?a=1&b=2', json([
    { id: 10, is_active: true, events: { event_date: '2026-10-21' } },
    { id: 11, is_active: true, events: { event_date: '2026-10-20' } },
  ]), '2026-10-21T23:00:00Z');
  eq(r.to, 'fight.html?id=10', 'today\'s card');
});

t('a dead booking is never a destination', async () => {
  eq((await run('?a=1&b=2', json([{ id: 9, is_active: false, events: { event_date: '2026-11-01' } }]))).to, '/', 'dead only');
  eq((await run('?a=1&b=2', json([
    { id: 9, is_active: false, events: { event_date: '2026-11-01' } },
    { id: 8, is_active: true, events: { event_date: '2025-01-01' } },
  ]))).to, 'fight.html?id=8', 'dead upcoming vs live past');
});

t('everything else lands on the card, and never asks the database', async () => {
  const cases = ['', '?a=1', '?b=2', '?a=1&b=1', '?a=abc&b=2', '?a=0&b=2', '?a=-1&b=2',
                 '?a=1)&b=2', '?a=1,fighter_b_id.eq.2&b=3', '?a=1234567890&b=2', '?x=1&y=2'];
  for (const q of cases) {
    const r = await run(q, () => { throw new Error('fetched for ' + q); });
    eq(r.to, '/', 'destination for ' + JSON.stringify(q));
    eq(r.requests.length, 0, 'a query was sent for ' + JSON.stringify(q));
  }
});

t('no rows, an HTTP error, a network error or a missing fetch all land on the card', async () => {
  eq((await run('?a=1&b=2', json([]))).to, '/', 'no rows');
  eq((await run('?a=1&b=2', () => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) }))).to, '/', 'HTTP 500');
  eq((await run('?a=1&b=2', () => Promise.reject(new Error('offline')))).to, '/', 'network');
  eq((await run('?a=1&b=2', undefined)).to, '/', 'no fetch');
  eq((await run('?a=1&b=2', json({ message: 'odd' }))).to, '/', 'a non-array body');
});

t('a lookup that never answers still lands on the card', async () => {
  const r = await run('?a=1&b=2', () => new Promise(() => {}));
  eq(r.to, '/', 'a hung lookup strands the reader');
  ok(r.timers.some(ms => ms <= 3000), 'no backstop timer of 3 s or less');
});

(async () => {
  for (const [name, fn] of queue) {
    try { await fn(); passed++; } catch (e) { failures.push(name + ' — ' + e.message); }
  }
  if (failures.length) {
    console.log(`\n  ${passed} passed, ${failures.length} FAILED\n`);
    failures.forEach(f => console.log(`  ✗ ${f}\n`));
    process.exit(1);
  }
  console.log(`\n  ${passed} passed — the retired Head-to-Head URL redirects and renders nothing.\n`);
})();
