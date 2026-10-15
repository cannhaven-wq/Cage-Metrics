/* ==========================================================================
   tests/non-ufc-event.test.js — T-086. A Contender Series / Road to UFC card
   keeps its URLs, says plainly what it was, and is never presented, indexed
   or listed as a UFC event.

   Run:  node tests/non-ufc-event.test.js
   ========================================================================== */
'use strict';
const fs = require('fs');
const path = require('path');
const { nonUfcEventStub, eventStub } = require('../build/templates.js');
const { isUfcEventName, nonUfcPromotion, PROMOTION_LABEL } = require('../build/promotion.js');

let passed = 0;
const failures = [];
function t(name, fn) {
  try { fn(); passed += 1; } catch (e) { failures.push(`${name}\n      ${e.message}`); }
}
function ok(c, what) { if (!c) throw new Error(what || 'expected truthy'); }
const read = f => fs.readFileSync(path.join(__dirname, '..', f), 'utf8');

const DWCS = { id: 4259, name: 'DWCS 10.3', event_date: '2026-08-25', location: 'Las Vegas, Nevada, USA', is_upcoming: false };

t('the classifier: DWCS and Road to UFC are not UFC; real UFC names are', () => {
  ok(!isUfcEventName('DWCS 10.3'));
  ok(!isUfcEventName('Road to UFC Season 4: Episode 6'));
  ok(isUfcEventName('UFC Fight Night: Buckley vs. Malott'));
  ok(isUfcEventName('Noche UFC: Silva vs. Delgado'));
  ok(nonUfcPromotion('DWCS 10.3') === 'DWCS');
  ok(nonUfcPromotion('Road to UFC 5.1') === 'RTU');
});

t('the non-UFC stub keeps the URL alive but is noindex and says what the card was', () => {
  const html = nonUfcEventStub(DWCS, PROMOTION_LABEL.DWCS);
  ok(/<meta name="robots" content="noindex, follow">/.test(html), 'stub is indexable');
  ok(html.includes('https://cannonfightlab.com/event.html?id=4259'), 'stub does not lead to the event page');
  ok(/not a UFC event/.test(html), 'stub does not say it is not a UFC event');
  ok(html.includes("Dana White&#39;s Contender Series") || html.includes("Dana White's Contender Series"),
    'stub does not name the promotion');
  ok(!/Ultimate Fighting Championship/.test(html), 'stub names the UFC as organiser');
  ok(!/SportsEvent/.test(html), 'stub carries UFC SportsEvent markup');
});

t('the UFC stub is unchanged in kind (still indexable, still a UFC event)', () => {
  const html = eventStub({ id: 1, name: 'UFC 300: Pereira vs. Hill', event_date: '2024-04-13' }, []);
  ok(/index, follow/.test(html));
  ok(/Ultimate Fighting Championship/.test(html));
});

t('the committed DWCS stub is the non-UFC one, and the sitemap does not list it', () => {
  const stub = read('e/dwcs-10-3-4259.html');
  ok(/noindex/.test(stub), 'e/dwcs-10-3-4259.html is still the indexable UFC stub');
  ok(!/\/e\/dwcs-/.test(read('sitemap.xml')), 'sitemap.xml lists a DWCS card');
});

t('every /e/ entry in the sitemap is a UFC card by name', () => {
  const locs = read('sitemap.xml').match(/\/e\/[^<]+\.html/g) || [];
  ok(locs.length > 500, 'expected the sitemap to list the event stubs');
  locs.forEach(l => ok(!/^\/e\/(dwcs|road-to-ufc|dana-white)/.test(l), `non-UFC card in sitemap: ${l}`));
});

t('prerender writes non-UFC cards with the non-UFC stub and keeps them out of the sitemap', () => {
  const src = read('build/prerender.js');
  ok(/require\('\.\/promotion'\)/.test(src), 'prerender does not use the shared rule');
  ok(/fetchNonUfcEvents\(\)/.test(src), 'prerender does not read events_non_ufc');
  ok(/isUfcEventName\(e\.name\)/.test(src), 'prerender does not catch a non-UFC card still in events');
  const loop = src.slice(src.indexOf('for (const e of nonUfc)'), src.indexOf('const nonUfcDone'));
  ok(/nonUfcEventStub\(/.test(loop), 'non-UFC loop does not use nonUfcEventStub');
  ok(!/urls\.push/.test(loop), 'non-UFC stubs are pushed into the sitemap');
  ok(/keep\.add\(filename\)/.test(loop), 'non-UFC stubs would be pruned (old links would 404)');
  // A missing table is tolerated only as "not migrated yet"; anything else throws.
  ok(/PGRST205/.test(src) && /throw new Error\('events_non_ufc read failed/.test(src));
});

t('event.html falls back to events_non_ufc and labels the card, never as a UFC event', () => {
  const src = read('event.html');
  ok(/renderNonUfcEvent\(sb, eventId\)/.test(src), 'event.html has no non-UFC fallback');
  const fn = src.slice(src.indexOf('async function renderNonUfcEvent'), src.indexOf('async function load()'));
  ok(/from\('events_non_ufc'\)/.test(fn) && /from\('fights_non_ufc'\)/.test(fn), 'fallback does not read the sibling tables');
  ok(/noindex/.test(fn), 'fallback page stays indexable');
  ok(/not a UFC event/.test(fn), 'fallback does not say it is not a UFC event');
  ok(/do not count toward anyone's UFC\s+record/.test(fn), 'fallback does not say the results are not counted');
  ok(/cfl\.escapeHtml\(/.test(fn), 'fallback does not escape database strings');
});

if (failures.length) {
  console.error(`non-ufc-event: ${failures.length} failed, ${passed} passed`);
  failures.forEach(f => console.error('  ✗ ' + f));
  process.exit(1);
}
console.log(`non-ufc-event: ${passed} passed`);
