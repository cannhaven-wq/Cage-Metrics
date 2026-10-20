/* ==========================================================================
   tests/data-view.test.js — the Charts / Numbers switch (T-104).

   Owner, 2026-10-20: "use graphs and tables when able — people can get lost
   in the numbers — at least a toggle." Card Lab, Market Lab and Factor Lab
   draw their figures as charts by default; the switch brings the plain
   figures back and is remembered per browser.

   Run:  node tests/data-view.test.js
   ========================================================================== */
'use strict';
const fs = require('fs');
const path = require('path');
const read = f => fs.readFileSync(path.join(__dirname, '..', f), 'utf8');
let passed = 0; const failures = [];
function t(name, fn) { try { fn(); passed += 1; } catch (err) { failures.push(name + '\n      ' + err.message); } }
function ok(c, what) { if (!c) throw new Error(what || 'expected truthy'); }

const SRC = read('data-view.js');
const DV = require('../data-view.js');

t('charts is the default, and a bad stored value falls back to it', () => {
  ok(DV.mode() === 'charts', 'default is ' + DV.mode());
  ok(/MODES\.indexOf\(v\) >= 0 \? v : 'charts'/.test(SRC), 'an unknown stored value is not rejected');
});

t('storage is wrapped: a blocked localStorage cannot break a page', () => {
  ok((SRC.match(/try \{[^}]*localStorage/g) || []).length >= 2, 'a localStorage read or write is not wrapped in try');
});

t('one attribute decides what shows, so switching never refetches', () => {
  ok(/html\[data-dv="numbers"\] \.dv-c \{ display: none/.test(SRC), 'charts are not hidden in numbers view');
  ok(/html:not\(\[data-dv="numbers"\]\) \.dv-n \{ display: none/.test(SRC), 'numbers are not hidden in charts view');
});

t('the helpers draw what they are given and nothing when data is missing', () => {
  ok(DV.split(null) === '', 'split draws with no probability');
  ok(DV.mirror(70, null) === '', 'mirror draws with one side missing');
  ok(DV.record(0, 0, 0) === '', 'record draws with no fights');
  const s = DV.split(0.6, 'Yan', 'Dvalishvili');
  ok(/60%/.test(s) && /40%/.test(s), 'split does not label both shares');
  ok(/aria-label="Yan 60%, Dvalishvili 40%"/.test(s), 'split has no readable label');
  ok(/aria-label="5 wins, 2 losses"/.test(DV.record(5, 2, 0)), 'record does not name losses');
});

t('the helpers escape what they print', () => {
  ok(!/<script>/.test(DV.split(0.5, '<script>', 'x')), 'a name reaches the markup unescaped');
});

// Analytics names are a closed list shared with a database CHECK; the switch
// must not invent one (tests/analytics-events.test.js).
t('the switch sends no analytics event', () => {
  ok(!/cfl\.track\(/.test(SRC), 'data-view.js emits an analytics event');
});

['index.html', 'market.html', 'stats.html'].forEach(f => t(f + ' loads data-view.js and draws the switch', () => {
  const src = read(f);
  ok(/<script src="data-view\.js(\?v=\d+)?"><\/script>/.test(src), 'data-view.js is not loaded');
  ok(/class="dv-toggle"/.test(src) && /data-dv="charts"/.test(src) && /data-dv="numbers"/.test(src), 'no Charts / Numbers switch');
  ok(/dv-c/.test(src) && /dv-n|cflDataView/.test(src), 'nothing on the page responds to the switch');
}));

t('Card Lab keeps the sportsbook table as the Numbers view', () => {
  const src = read('index.html');
  const fn = src.slice(src.indexOf('function booksTableHtml'), src.indexOf('function booksDetailHtml'));
  ok(/'dv-n'/.test(fn) && /<table class="fx-bt fx-bt-c">/.test(fn), 'the per-book table is not the numbers view');
  ok(/dv-c fx-bchart/.test(fn), 'the per-book chart is missing');
});

t('Factor Lab renders a table of the same stored values', () => {
  const src = read('stats.html');
  ok(/id="labTable"/.test(src) && /class="fl-table dv-n"/.test(src), 'no numbers table');
  ok(/class="fl-list dv-c" id="labBody"/.test(src), 'the cards are not the charts view');
});

if (failures.length) {
  console.error('data-view: ' + failures.length + ' failed, ' + passed + ' passed');
  failures.forEach(f => console.error('  ✗ ' + f)); process.exit(1);
}
console.log('data-view: ' + passed + ' passed');
