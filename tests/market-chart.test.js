/* ==========================================================================
   tests/market-chart.test.js — the chart cannot draw a line it cannot defend.

   A chart is the easiest place in a product to hide a methodology problem: a
   shape looks authoritative whether or not the points behind it are
   comparable. These assertions exist because "the line went up" is the most
   persuasive claim CFL makes, and it has to be the most checkable.

   The four rules, each tested by behaviour rather than by reading source:

     1. ONE FIXED COHORT across the whole plotted window. Not trusted from
        SQL — asserted in JS, so a view change cannot silently produce a
        shifting-cohort line.
     2. NO INTERPOLATION. The path is a STEP (H/V only). A diagonal would
        claim the price passed through values no book ever posted.
     3. REFUSE RATHER THAN THIN. Below three matched books there is no
        consensus line, and the refusal says which refusal it is.
     4. THE COHORT SIZE IS ON SCREEN, not only in a tooltip.

   Run:  node tests/market-chart.test.js
   ========================================================================== */

'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = f => path.join(__dirname, '..', f);
const read = f => fs.readFileSync(root(f), 'utf8');

const CHART_JS = read('market-chart.js');
const CHART_SQL = read('market_chart_views.sql');
const FIGHT = read('fight.html');

const stripComments = src => src
  .replace(/\/\*[\s\S]*?\*\//g, ' ')
  .replace(/^\s*\/\/.*$/gm, ' ')
  .replace(/^\s*--.*$/gm, ' ');

// Load the module in a bare context — it must not need a DOM to be reasoned about.
function loadChart() {
  const ctx = { window: {}, console: { warn() {}, log() {} }, module: { exports: {} } };
  vm.createContext(ctx);
  ctx.globalThis = ctx.window;
  Object.assign(ctx, { Math, Date, JSON, isFinite, String, Number, Object, Array, RegExp, Error });
  vm.runInContext(CHART_JS, ctx);
  return ctx.window.cflChart || ctx.module.exports;
}
const CH = loadChart();

function fakeEl() {
  return { innerHTML: '', querySelector: () => null, querySelectorAll: () => [] };
}
function series(n, cohort, startPct, endPct) {
  const t0 = Date.parse('2026-09-19T00:00:00Z');
  const out = [];
  for (let i = 0; i < n; i++) {
    out.push({
      at: new Date(t0 + i * 3600000).toISOString(),
      market_p_a: (startPct + (endPct - startPct) * (i / Math.max(1, n - 1))) / 100,
      cohort_books: cohort
    });
  }
  return out;
}
const META_OK = { series_status: 'ok', cohort_books: 3, books_ever: 6 };

let passed = 0;
const failures = [];
function t(name, fn) {
  try { fn(); passed++; } catch (e) { failures.push(name + ' — ' + e.message); }
}
function ok(cond, msg) { if (!cond) throw new Error(msg); }
function eq(a, b, msg) {
  if (a !== b) throw new Error((msg || 'value') + ': expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a));
}

t('the module loads without a DOM', () => {
  ok(CH && typeof CH.render === 'function', 'no render()');
  ok(typeof CH.validateSeries === 'function', 'no validateSeries()');
  eq(CH.MIN_COHORT_BOOKS, 3, 'MIN_COHORT_BOOKS');
});

/* ------------------------------------------ 1. one fixed cohort, asserted */
t('a cohort that changes mid-series is REFUSED, not drawn', () => {
  const s = series(10, 3, 50, 57);
  s[6].cohort_books = 4;                      // a book joins halfway
  const v = CH.validateSeries(s, META_OK);
  eq(v.ok, false, 'a shifting cohort was accepted');
  eq(v.reason, 'cohort_changed_mid_series', 'reason');
  eq(v.points.length, 0, 'points were returned anyway');
});

t('the refusal for a shifting cohort names it as OUR bug, not a quiet market', () => {
  const s = series(10, 3, 50, 57); s[6].cohort_books = 4;
  const el = fakeEl();
  CH.render(el, { meta: META_OK, series: s, nameA: 'A', nameB: 'B' });
  const txt = el.innerHTML.replace(/<[^>]+>/g, ' ');
  ok(/bug on our side/i.test(txt), 'the copy blames the market instead of the code');
  ok(/refusing it|withheld/i.test(txt), 'it does not say the chart was withheld');
});

t('a constant cohort is accepted and reported', () => {
  const v = CH.validateSeries(series(20, 5, 50, 57), { series_status: 'ok', cohort_books: 5 });
  eq(v.ok, true, 'a valid series was refused');
  eq(v.cohortBooks, 5, 'cohortBooks');
  eq(v.points.length, 20, 'points');
});

t('the JS does not trust the SQL status alone', () => {
  // status says ok, the rows say otherwise. The rows win.
  const s = series(8, 1, 50, 57);
  const v = CH.validateSeries(s, { series_status: 'ok', cohort_books: 1 });
  eq(v.ok, false, 'a 1-book cohort was drawn because the status said ok');
  eq(v.reason, 'insufficient_matched_books', 'reason');
});

/* ------------------------------------------------- 2. no interpolation */
t('the consensus path is a STEP, with no diagonal segments', () => {
  const el = fakeEl();
  CH.render(el, { meta: META_OK, series: series(12, 3, 50, 57), nameA: 'A', nameB: 'B' });
  const m = el.innerHTML.match(/<path d="(M[^"]+)" fill="none" stroke="#2fdccb"/);
  ok(m, 'no consensus path was drawn');
  const d = m[1];
  ok(/^M[\d.\s]+( H[\d.]+ V[\d.]+)+$/.test(d),
     'the path is not made only of H/V steps: ' + d.slice(0, 80));
  ok(!/[LlCcQqSsTtAa]/.test(d.replace(/^M/, '')),
     'the path contains a line-to or curve command: ' + d.slice(0, 80));
});

t('per-book lines are stepped too', () => {
  const el = fakeEl();
  const books = [];
  [1, 2, 3].forEach(id => series(6, 3, 48, 55).forEach(r =>
    books.push({ book_id: id, book_name: 'Book ' + id, at: r.at, fair_a: r.market_p_a })));
  CH.render(el, { meta: META_OK, series: series(6, 3, 50, 57), books, showBooks: true, nameA: 'A', nameB: 'B' });
  const paths = el.innerHTML.match(/<path d="(M[^"]+)"[^>]*data-book/g) || [];
  ok(paths.length >= 1, 'no per-book paths were drawn');
  paths.forEach(p => {
    const d = p.match(/d="(M[^"]+)"/)[1];
    ok(!/[LlCcQqSsTtAa]/.test(d.replace(/^M/, '')), 'a per-book path is not stepped');
  });
});

t('nothing is smoothed or resampled', () => {
  const body = stripComments(CHART_JS).toLowerCase();
  ['interpolat', 'smooth', 'curve', 'resample', 'lerp', 'movingaverage', 'bezier']
    .forEach(w => ok(body.indexOf(w) === -1, 'market-chart.js mentions "' + w + '"'));
  const sql = stripComments(CHART_SQL).toLowerCase();
  ok(sql.indexOf('generate_series') === -1,
     'the SQL builds a synthetic time grid instead of using real captures');
});

t('every x is a real capture instant', () => {
  const s = series(5, 3, 50, 57);
  const v = CH.validateSeries(s, META_OK);
  const want = s.map(r => Date.parse(r.at)).sort((a, b) => a - b);
  eq(v.points.length, want.length, 'point count');
  v.points.forEach((p, i) => eq(p.t, want[i], 'point ' + i + ' moved off its capture instant'));
});

/* ---------------------------------------------- 3. refuse rather than thin */
t('below three matched books there is NO line', () => {
  [0, 1, 2].forEach(n => {
    const v = CH.validateSeries(series(10, n, 50, 57), { series_status: 'ok', cohort_books: n });
    eq(v.ok, false, n + ' books produced a line');
  });
  const v3 = CH.validateSeries(series(10, 3, 50, 57), { series_status: 'ok', cohort_books: 3 });
  eq(v3.ok, true, 'three books were refused');
});

t('each refusal explains itself, and they are distinguishable', () => {
  const cases = ['no_broad_capture', 'insufficient_matched_books', 'not_enough_history', 'cohort_changed_mid_series'];
  const seen = {};
  cases.forEach(r => {
    const c = CH.refusalCopy(r, 2, '3, 4');
    ok(c.head && c.head.length > 3, r + ' has no headline');
    ok(c.body && c.body.length > 40, r + ' has no explanation');
    ok(!/^—$|^-$/.test(c.head), r + ' renders a bare dash');
    ok(!seen[c.body], r + ' reuses another refusal\'s wording');
    seen[c.body] = true;
  });
});

t('a single point is not a history', () => {
  const v = CH.validateSeries(series(1, 3, 50, 50), META_OK);
  eq(v.ok, false, 'one point was drawn as a line');
  eq(v.reason, 'not_enough_history', 'reason');
});

t('a refused consensus still permits per-book lines (requirement 5)', () => {
  // The SQL is what guarantees this: meta gates the series, not the book view.
  const sql = CHART_SQL.replace(/\s+/g, ' ');
  ok(/v_fight_chart_series[\s\S]*?series_status = 'ok'/.test(sql),
     'the series view is not gated on series_status');
  ok(!/v_fight_chart_books[\s\S]{0,400}series_status/.test(sql),
     'the per-book view is gated on the consensus status, which it must not be');
});

/* ------------------------------------------- 4. the cohort size is on screen */
t('the cohort size is rendered outside the tooltip', () => {
  const el = fakeEl();
  CH.render(el, { meta: META_OK, series: series(10, 4, 50, 57), nameA: 'Vieira', nameB: 'Bryczek' });
  const foot = (el.innerHTML.match(/<div class="mc-foot">[\s\S]*?$/) || [''])[0].replace(/<[^>]+>/g, ' ');
  ok(/middle of 4 sportsbooks/.test(foot),
     'the cohort size is not in the chart footer: ' + foot.slice(0, 120));
  // and not ONLY in the tooltip
  const tip = (el.innerHTML.match(/class="mc-tip"[\s\S]*?<\/div>/) || [''])[0];
  ok(foot.indexOf('sportsbooks') !== -1, 'cohort size missing from the always-visible layer');
  ok(tip.indexOf('4 sportsbooks') === -1 || foot.indexOf('4 sportsbooks') !== -1,
     'the cohort size appears only on hover');
});

t('the chart is labelled for a screen reader and offers a table', () => {
  const el = fakeEl();
  CH.render(el, { meta: META_OK, series: series(10, 3, 50, 57), nameA: 'Vieira', nameB: 'Bryczek' });
  ok(/role="img"/.test(el.innerHTML), 'no role on the svg');
  ok(/aria-label="[^"]{20,}"/.test(el.innerHTML), 'no descriptive aria-label');
  const tbl = CH.tableHtml(series(4, 3, 50, 57), 'Vieira', 3);
  ok(/<table/.test(tbl) && /<caption/.test(tbl), 'no table view of the same numbers');
  ok(/Books<\/th>/.test(tbl), 'the table omits the cohort size column');
});

t('Fight Lab renders the chart and its methodology disclosure', () => {
  ok(/id="flChart"/.test(FIGHT), 'no chart container on Fight Lab');
  ok(/market-chart\.js\?v=/.test(FIGHT), 'Fight Lab does not load market-chart.js');
  ok(/How this line is calculated/.test(FIGHT), 'no methodology disclosure in the UI');
  ok(/mcTable/.test(FIGHT), 'no table toggle');
  ok(/CFL does not/.test(FIGHT) && /see sportsbook openers/.test(FIGHT),
     'the disclosure does not state that CFL never sees openers');
});

/* ------------------------------------------------ the shared rule, and perf */
t('the chart cohort IS the matched cohort, not a new definition', () => {
  const sql = CHART_SQL.replace(/\s+/g, ' ');
  ok(/v_fight_market_horizon_cohorts/.test(sql),
     'the chart defines its own cohort instead of reusing the matched one');
  ok(/horizon = 'broad_baseline'/.test(sql), 'it does not use the broad_baseline horizon');
});

t('the single-fight performance constraint is documented where it bites', () => {
  ok(/SINGLE-FIGHT VIEW/.test(CHART_SQL),
     'the SQL does not warn that the series view is single-fight only');
  ok(/4,607 ms|4607/.test(CHART_SQL), 'the measured multi-fight cost is not recorded');
  ok(/22 ms/.test(CHART_SQL), 'the measured single-fight cost is not recorded');
  ok(/Do not batch this/.test(CHART_JS), 'market-chart.js does not warn against batching');
});

t('the 14-day window is gone from the per-book view', () => {
  const sql = CHART_SQL.replace(/\s+/g, ' ');
  ok(/CREATE VIEW public\.v_fight_odds_latest_by_book|CREATE OR REPLACE VIEW public\.v_fight_odds_latest_by_book/.test(sql),
     'the per-book view is not redefined here');
  const def = sql.slice(sql.indexOf('v_fight_odds_latest_by_book AS'));
  ok(!/CURRENT_DATE - 14/.test(def),
     'v_fight_odds_latest_by_book still carries the 14-day event window');
});

t('no opener language anywhere in the chart layer', () => {
  [stripComments(CHART_JS), stripComments(CHART_SQL)].forEach((body, i) => {
    const lower = body.toLowerCase();
    ['opening line', 'opening price', 'opened at', 'since open'].forEach(p =>
      ok(lower.indexOf(p) === -1, ['market-chart.js', 'market_chart_views.sql'][i] + ' says "' + p + '"'));
  });
});

// ------------------------------------------------------------------ report
if (failures.length) {
  console.log(`\n  ${passed} passed, ${failures.length} FAILED\n`);
  failures.forEach(f => console.log(`  ✗ ${f}\n`));
  process.exit(1);
}
console.log(`\n  ${passed} passed — the chart cannot draw a line it cannot defend.\n`);
