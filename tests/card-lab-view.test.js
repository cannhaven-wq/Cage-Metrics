/* ==========================================================================
   tests/card-lab-view.test.js — Card Lab's compact list.

   The compact list is a second view of the SAME card: it must go through the
   same order, sort and search as the full cards, show both corners' prices,
   carry the book count and capture age, and link every row to Fight Lab.

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
const build = PAGE.slice(PAGE.indexOf('function buildFightCard'), PAGE.indexOf('function fighterSideHtml'));

t('the view toggle exists beside the sort, and the existing controls are kept', () => {
  ['id="viewSeg"', 'data-view="list"', 'id="sortSeg"', 'id="dirSeg"', 'id="cardSearch"'].forEach(s => ok(PAGE.includes(s), 'missing ' + s));
});

t('both views are drawn from the one sorted, searched list', () => {
  ok(/cards\.sort\(/.test(render) && render.indexOf('cards.sort(') < render.indexOf("_hpView === 'list'"), 'list view bypasses the sort');
  ok(/c => c\.row/.test(render) && /c => c\.html/.test(render), 'views are not both read off the same cards array');
  ok(/fightMatches/.test(render), 'search no longer applies');
});

t('each compact row shows both prices, the division, the move, and links to Fight Lab', () => {
  ok(/odds\(a, readA\) \+ odds\(b, readB\)/.test(build), 'both corners are not priced');
  ok(/fight\.weight_class/.test(build) && /class="clist-row" href="fight\.html\?id=/.test(build), 'division or Fight Lab link missing');
  ok(/moveSinceBaseline/.test(build.slice(build.indexOf('compact-list row'))), 'move missing from the row');
  ok(/bookCount/.test(build.slice(build.indexOf('compact-list row'))) && /fresh\.when/.test(build.slice(build.indexOf('compact-list row'))), 'book count or age missing');
});

t('a remembered view never throws when storage is blocked', () => {
  ok(/try \{ return localStorage\.getItem\('cfl\.cardView'\)/.test(PAGE), 'read is not guarded');
  ok(/try \{ localStorage\.setItem\('cfl\.cardView'/.test(PAGE), 'write is not guarded');
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
