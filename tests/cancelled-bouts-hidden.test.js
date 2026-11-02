/* ==========================================================================
   tests/cancelled-bouts-hidden.test.js — a cancelled bout is not on the card.

   A cancelled or replaced bout is retired with fights.is_active = false
   (D-024 / T-093; the event scraper now does it automatically when a bout
   drops off the UFCStats card page). Sean Brady vs. Gabriel Bonfim stayed on
   the site after it was pulled because nothing set the flag.

   Pinned here:
     - cfl.orderCard drops is_active = false rows and keeps true / missing;
     - every page that lists an upcoming card either runs it through
       cfl.orderCard or filters is_active in its query. parlay.html did
       neither, so a cancelled bout stayed selectable as a parlay leg.

   Run:  node tests/cancelled-bouts-hidden.test.js
   ========================================================================== */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const root = f => path.join(__dirname, '..', f);
let n = 0;
const ok = (cond, msg) => { assert.ok(cond, msg); n++; };

// --- cfl.orderCard, executed ------------------------------------------------
const sandbox = { window: {}, console,
  // Timers are no-ops: _shared.js schedules DOM work this test does not need.
  setTimeout() { return 0; }, clearTimeout() {}, setInterval() { return 0; }, clearInterval() {},
  document: { addEventListener() {} },
  supabase: { createClient: () => ({ auth: {} }) }, localStorage: { getItem() { return null; } } };
sandbox.window = sandbox;
let cfl = null;
try {
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(root('_shared.js'), 'utf8'), sandbox);
  cfl = sandbox.cfl || sandbox.window.cfl;
} catch (e) { console.log('note: _shared.js did not load in a sandbox (' + e.message + '); checking its source instead'); }

if (cfl && typeof cfl.orderCard === 'function') {
  const card = [
    { id: 52655, fighter_a_id: 1, fighter_b_id: 2, fighter_a_name: 'Waldo Cortes Acosta', fighter_b_name: 'Johnny Walker', is_active: true },
    { id: 49281, fighter_a_id: 3, fighter_b_id: 4, fighter_a_name: 'Gabriel Bonfim', fighter_b_name: 'Sean Brady', is_active: false },
    { id: 52657, fighter_a_id: 5, fighter_b_id: 6, fighter_a_name: 'Billy Elekana', fighter_b_name: 'Lucas Fernando' },
  ];
  const ids = cfl.orderCard(card, 'UFC Fight Night: Cortes Acosta vs. Walker').map(f => f.id);
  ok(!ids.includes(49281), 'orderCard must drop a retired (is_active = false) bout');
  ok(ids.includes(52655) && ids.includes(52657), 'orderCard must keep active and unflagged bouts');
} else {
  ok(/filter\(f => f\.is_active !== false\)/.test(fs.readFileSync(root('_shared.js'), 'utf8')),
    'cfl.orderCard must drop is_active = false rows');
}

// --- every upcoming-card surface honours the flag ---------------------------
for (const page of ['index.html', 'market.html', 'event.html', 'parlay.html']) {
  const src = fs.readFileSync(root(page), 'utf8');
  const viaOrderCard = /cfl\.orderCard\(/.test(src);
  const viaQuery = /\.not\(\s*'is_active'\s*,\s*'is'\s*,\s*false\s*\)/.test(src);
  ok(viaOrderCard || viaQuery, page + ' lists a card but never drops retired (is_active = false) bouts');
}

console.log('cancelled-bouts-hidden: ' + n + ' passed');
