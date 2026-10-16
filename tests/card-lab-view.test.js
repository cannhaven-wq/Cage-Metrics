/* ==========================================================================
   tests/card-lab-view.test.js — Card Lab's compact list.

   Since the Compact List redesign (2026-10-16) the list is the ONLY layout
   of the card: one row per fight, in card position, with the controls the
   approved design asks for — card order / reverse order, a section filter
   that is honest about what we do not hold, a sort and a search.

   Run:  node tests/card-lab-view.test.js
   ========================================================================== */
'use strict';
const fs = require('fs');
const path = require('path');
const PAGE = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
let passed = 0; const failures = [];
function t(name, fn) { try { fn(); passed += 1; } catch (err) { failures.push(name + '\n      ' + err.message); } }
function ok(c, what) { if (!c) throw new Error(what || 'expected truthy'); }

const render = PAGE.slice(PAGE.indexOf('function renderCards'), PAGE.indexOf('function renderSearchStatus'));
const wire = PAGE.slice(PAGE.indexOf('function wireControls'), PAGE.indexOf('function cardMarketRows'));

t('the controls exist: card order / reverse, section filter, sort, search', () => {
  ['id="dirSeg"', 'data-dir="down"', 'data-dir="up"', '>Card order<', '>Reverse order<',
   'id="sectionSeg"', 'id="sortSel"', 'value="move"', 'value="spread"', 'id="cardSearch"'].forEach(x => ok(PAGE.includes(x), 'missing ' + x));
});

t('the list is drawn from the one ordered, searched, sorted list', () => {
  ok(/sortCard\(fights, ro, 'down'\)/.test(render), 'card position does not come from sortCard');
  ok(/fightMatches/.test(render), 'search no longer applies');
  ok(/cards\.sort\(/.test(render) && render.indexOf('cards.sort(') < render.indexOf('cards.reverse()'), 'reverse is not applied after the sort');
  ok(/_hpSortKey === 'order' && _hpDir === 'up'/.test(render), 'reverse applies outside card position');
  ok(/c => c\.html/.test(render), 'rows are not read off the cards array');
  ok(!/_hpView|viewSeg/.test(PAGE), 'a second card layout is back');
});

t('reverse order always means card position', () => {
  ok(/if \(_hpSortKey !== 'order'\) \{ _hpSortKey = 'order'/.test(wire), 'reverse does not return to card position');
});

t('the card comes before the at-a-glance panel, and is the page heading', () => {
  ok(PAGE.indexOf('id="next"') < PAGE.indexOf('id="hero"'), 'the card is not first');
  ok((PAGE.match(/<h1[ >]/g) || []).length === 2, 'expected the card h1 in the markup and the one renderCardHead writes');
  ok(/<h1>\$\{cfl\.escapeHtml\(event\.name\)\}<\/h1>/.test(PAGE), 'the event name is not the h1');
});

// A duplicate declaration inside an inline script kills the whole card with no
// visible error to a test that only greps. Parse every inline block.
['index.html', 'fight.html'].forEach(f => t(f + ' inline scripts parse', () => {
  const src = fs.readFileSync(path.join(__dirname, '..', f), 'utf8');
  const blocks = src.match(/<script>([\s\S]*?)<\/script>/g) || [];
  ok(blocks.length > 0, 'no inline script found');
  blocks.forEach((b, i) => {
    try { new Function(b.replace(/^<script>|<\/script>$/g, '')); }
    catch (e) { throw new Error('inline script ' + i + ': ' + e.message); }
  });
}));

if (failures.length) {
  console.error('card-lab-view: ' + failures.length + ' failed, ' + passed + ' passed');
  failures.forEach(f => console.error('  ✗ ' + f)); process.exit(1);
}
console.log('card-lab-view: ' + passed + ' passed');
