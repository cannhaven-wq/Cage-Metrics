/* ==========================================================================
   tests/market-movement.test.js — a market move must be a move, not a change
   in which sportsbooks were asked.

   The defect this pins was found in the LIVE DATABASE on 2026-09-21. A view
   named v_fight_market_movement, applied from the unmerged fight-week-v2
   branch and present in no repo file, exposed open_p_a / open_p_b /
   books_at_open, where "open" meant min(captured_at) — CFL's single earliest
   capture instant. Measured against the real table that day:

     * 79 fights had real sportsbook quotes
     * 22 of them (28%) had exactly ONE sportsbook at that instant
     * against the matched-cohort method the retired one differed by 3+ points
       on 7 fights, and on 3 fights reported a 3+ point "move" for a market
       that had in fact moved less than 1 point
     * worst single overstatement: 12.7 points

   Two separate things were wrong and both are pinned here:
     1. calling CFL's first sighting an "open" — CFL has never observed a
        sportsbook opening line, and may not imply it;
     2. comparing a one-book baseline against a six-book present and
        describing the whole difference as market movement.

   Run:  node tests/market-movement.test.js
   ========================================================================== */

'use strict';
const fs = require('fs');
const path = require('path');

const root = f => path.join(__dirname, '..', f);
const read = f => fs.readFileSync(root(f), 'utf8');
const exists = f => fs.existsSync(root(f));

const MV = require('../market-movement.js');
const SQL = read('market_movement_views.sql');
const MODULE_SRC = read('market-movement.js');

const stripComments = src => src
  .replace(/\/\*[\s\S]*?\*\//g, ' ')
  .replace(/^\s*\/\/.*$/gm, ' ')
  .replace(/^\s*--.*$/gm, ' ');

let passed = 0;
const failures = [];
function t(name, fn) {
  try { fn(); passed++; }
  catch (e) { failures.push(name + ' — ' + e.message); }
}
function ok(cond, msg) { if (!cond) throw new Error(msg); }
function eq(a, b, msg) {
  if (a !== b) throw new Error((msg || 'value') + ': expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a));
}

const NOW = Date.parse('2026-09-21T13:00:00Z');
const base = over => Object.assign({
  movement_status: 'ok',
  movement_pts_a: 7.0,
  baseline_p_a: 0.50,
  matched_current_p_a: 0.57,
  baseline_at: '2026-09-14T08:00:00Z',
  baseline_quote_at: '2026-09-14T08:00:00Z',
  last_updated: '2026-09-21T12:40:00Z',
  oldest_current_quote_at: '2026-09-21T12:10:00Z',
  baseline_book_count: 3,
  book_count: 6,
  matched_book_count: 3,
  movement_method: 'matched_cohort_median_vigfree_v1'
}, over || {});

/* -------------------------------------------------- 1. no opening-line claim */
const FORBIDDEN = [
  'opening line', 'opening price', 'opening market', 'opened at',
  'market open', 'the open '
];

t('the module never says CFL saw an opening line', () => {
  // The FORBIDDEN_BASELINE_WORDS list names the banned phrases in order to ban
  // them; it must not itself trip the ban.
  const copy = stripComments(MODULE_SRC)
    .replace(/const FORBIDDEN_BASELINE_WORDS = \[[\s\S]*?\];/, ' ')
    .toLowerCase();
  FORBIDDEN.forEach(p =>
    ok(copy.indexOf(p) === -1, 'market-movement.js still emits "' + p + '"'));
});

t('every describeMovement string avoids opening-line wording', () => {
  const rows = [
    base(),
    base({ movement_pts_a: -4.2 }),
    base({ movement_status: 'insufficient_matched_books', matched_book_count: 2 }),
    base({ movement_status: 'no_broad_capture', matched_book_count: 0, baseline_at: null, baseline_quote_at: null })
  ];
  rows.forEach(r => {
    const d = MV.describeMovement(r, { fighterA: 'Vieira', fighterB: 'Bryczek', now: NOW });
    const all = [d.plain, d.detail, d.value && d.value.label, d.value && d.value.longLabel]
      .filter(Boolean).join(' ').toLowerCase();
    FORBIDDEN.forEach(p => ok(all.indexOf(p) === -1, 'rendered copy says "' + p + '"'));
  });
});

t('the SQL exposes no open_p_a / books_at_open column', () => {
  const body = stripComments(SQL).toLowerCase();
  ['open_p_a', 'open_p_b', 'books_at_open'].forEach(c =>
    ok(body.indexOf(c) === -1, 'market_movement_views.sql still defines ' + c));
});

t('the baseline is named as a CFL capture, not a market event', () => {
  ok(/first broad capture/i.test(MV.SHORT_BASELINE), 'SHORT_BASELINE does not name the capture');
  ok(/CFL first saw/i.test(MV.PLAIN_BASELINE), 'PLAIN_BASELINE does not attribute the sighting to CFL');
});

/* ------------------------------------------- 2. the matched-cohort threshold */
t('MIN_MATCHED_BOOKS is 3 and the SQL agrees', () => {
  eq(MV.MIN_MATCHED_BOOKS, 3, 'MIN_MATCHED_BOOKS');
  ok(/book_rank\s*=\s*3/.test(SQL), 'the SQL baseline does not rank to the 3rd book');
  ok(/matched_book_count,\s*0\)\s*>=\s*3/.test(SQL.replace(/\s+/g, ' ')),
     'the SQL does not gate movement on 3 matched books');
});

t('two matched books produce a refusal, not a number', () => {
  const d = MV.describeMovement(base({
    movement_status: 'insufficient_matched_books',
    matched_book_count: 2, movement_pts_a: null,
    baseline_p_a: null, matched_current_p_a: null
  }), { now: NOW });
  eq(d.ok, false, 'ok');
  eq(d.value, null, 'value');
  eq(d.plain, 'Movement unavailable', 'plain');
  ok(/not enough comparable sportsbooks/i.test(d.detail), 'detail does not explain why');
});

t('no broad capture produces a refusal that says what is missing', () => {
  const d = MV.describeMovement(base({
    movement_status: 'no_broad_capture', matched_book_count: 0,
    baseline_book_count: 0, book_count: 1,
    baseline_at: null, baseline_quote_at: null, movement_pts_a: null
  }), { now: NOW });
  eq(d.ok, false, 'ok');
  eq(d.value, null, 'value');
  ok(/3 different sportsbooks/i.test(d.detail), 'detail does not name the threshold');
});

t('a status of ok with too few matched books is still refused', () => {
  // defence in depth: the module does not trust the status column alone
  const d = MV.describeMovement(base({ matched_book_count: 1 }), { now: NOW });
  eq(d.ok, false, 'a 1-book cohort was accepted');
  eq(d.value, null, 'value');
});

t('a missing movement figure is never inferred from the medians', () => {
  const d = MV.describeMovement(base({ movement_pts_a: null }), { now: NOW });
  eq(d.ok, false, 'ok');
  eq(d.value, null, 'a number was manufactured from baseline_p_a/current_p_a');
});

/* --------------------------------- 3. structurally incomparable cohorts */
t('the SQL medians both ends over the SAME matched book set', () => {
  const body = SQL.replace(/\s+/g, ' ');
  ok(/matched AS \( SELECT b\.fight_id, b\.book_id/.test(body),
     'no matched CTE intersecting baseline and current cohorts');
  ok(/ORDER BY m\.baseline_fair_a/.test(body) && /ORDER BY m\.current_fair_a/.test(body),
     'the two medians are not both taken from the matched CTE');
});

t('a book quoting only now cannot enter the comparison', () => {
  // 6 books quote now, 3 were there at the baseline. The detail must say so.
  const d = MV.describeMovement(base(), { fighterA: 'Vieira', fighterB: 'Bryczek', now: NOW });
  ok(d.ok, 'a defensible row was refused');
  ok(/3 sportsbooks present both/i.test(d.detail), 'detail does not state the matched count');
  ok(/6 quote now in total/i.test(d.detail), 'detail does not disclose the wider current cohort');
  ok(/left out of the comparison/i.test(d.detail), 'detail does not say the extras are excluded');
});

/* ------------------------------ 4. synthetic consensus is never a sportsbook */
t('the quote view draws books from v_odds_books_sportsbooks only', () => {
  ok(/JOIN public\.v_odds_books_sportsbooks/.test(SQL),
     'quotes are not restricted to real sportsbooks');
  ok(!/FROM public\.odds_books\b/.test(SQL),
     'a view reads odds_books directly, so the synthetic consensus row can enter');
});

t('live and non-open markets are excluded from every quote', () => {
  ok(/is_live IS NOT TRUE/.test(SQL), 'in-fight quotes are not excluded');
  ok(/market_status IS NULL OR o\.market_status = 'open'/.test(SQL),
     'suspended or settled markets are not excluded');
});

/* ------------------------------------------- 5. best price and its provenance */
t('a best price always names its sportsbook and its age', () => {
  const p = MV.describeBestPrice(base({ best_american_a: 145, best_book_a: 'Pinnacle' }), 'a', { now: NOW });
  ok(p.ok, 'a real price was refused');
  eq(p.price, '+145', 'price');
  eq(p.book, 'Pinnacle', 'book');
  ok(p.age, 'no freshness on a best price');
  ok(/best observed/i.test(p.plain), 'it claims availability rather than observation');
});

t('best price states that no sportsbook can buy the position', () => {
  const p = MV.describeBestPrice(base({ best_american_a: -110, best_book_a: 'DraftKings' }), 'a', { now: NOW });
  ok(/no payment from any sportsbook/i.test(p.note) || /cannot buy|can buy/i.test(p.note),
     'the ranking does not disclaim commercial influence');
  ok(!/affiliate|partner|sponsor/i.test(stripComments(MODULE_SRC).replace(/commercial relationship/g, '')),
     'commercial wording leaked into price ranking');
});

t('a missing price is an honest empty state', () => {
  const p = MV.describeBestPrice(base({ best_american_a: null, best_book_a: null }), 'a', { now: NOW });
  eq(p.ok, false, 'ok');
  eq(p.price, null, 'price');
  ok(/no sportsbook price captured/i.test(p.plain), 'empty state does not explain itself');
});

/* --------------------------------------------- 6. book spread is a definition */
t('"books disagree" carries its measurement', () => {
  const s = MV.describeBookSpread(base({ book_spread_pts: 3.8 }));
  ok(s.ok, 'a real spread was refused');
  eq(s.value, '3.8 pts', 'value');
  ok(/widest gap between the 6 sportsbooks/i.test(s.detail), 'no definition given');
  ok(/removing each book/i.test(s.detail), 'does not say the margin is removed');
});

t('one book quoting is not a disagreement', () => {
  const s = MV.describeBookSpread(base({ book_count: 1, book_spread_pts: 0 }));
  eq(s.ok, false, 'ok');
  ok(/at least two books/i.test(s.detail), 'does not explain the empty state');
});

/* ------------------------------------------------- 7. plain-English framing */
t('a sub-1-point move reads as steady, not as news', () => {
  const d = MV.describeMovement(base({ movement_pts_a: 0.4 }), { fighterA: 'Vieira', now: NOW });
  eq(d.plain, 'Books have held steady', 'plain');
  ok(d.ok, 'a small move should still be defensible');
});

t('direction is named by fighter, in plain words', () => {
  const up = MV.describeMovement(base({ movement_pts_a: 4.1 }), { fighterA: 'Vieira', fighterB: 'Bryczek', now: NOW });
  const dn = MV.describeMovement(base({ movement_pts_a: -4.1 }), { fighterA: 'Vieira', fighterB: 'Bryczek', now: NOW });
  eq(up.plain, 'Books moved toward Vieira', 'plain up');
  eq(dn.plain, 'Books moved toward Bryczek', 'plain down');
  eq(up.value.text, '+4.1 pts', 'up text');
});

t('the three disclosure layers are all present on an ok row', () => {
  const d = MV.describeMovement(base(), { fighterA: 'Vieira', fighterB: 'Bryczek', now: NOW });
  ok(d.plain && d.plain.length > 0, 'no plain layer');
  ok(d.value && d.value.text, 'no number layer');
  ok(d.detail && d.detail.length > 40, 'no detail layer');
  ok(d.method, 'no reproducible method name');
});

t('every surface can reach the full provenance set', () => {
  const d = MV.describeMovement(base(), { now: NOW });
  ['baseline', 'current', 'matched', 'minimum'].forEach(k =>
    ok(typeof d.books[k] === 'number', 'books.' + k + ' missing'));
  ok(d.at.baseline && d.at.current, 'baseline/current timestamps missing');
  ok('oldestCurrent' in d.at, 'oldest current quote missing');
  eq(d.method, 'matched_cohort_median_vigfree_v1', 'method');
});

/* -------------------------------------------- 8. the file contract holds */
t('the SQL documents how captures are grouped', () => {
  ok(/§Grouping/.test(SQL), 'the grouping rule is not documented');
  ok(/captured_at` is the grouping key/.test(SQL), 'the grouping key is not named');
});

t('the module is loadable in the browser and in Node', () => {
  ok(/window\.cflMovement/.test(MODULE_SRC), 'no browser global');
  ok(/module\.exports/.test(MODULE_SRC), 'no CommonJS export');
});

t('the SQL file is real and applied alongside the module', () => {
  ok(exists('market_movement_views.sql'), 'market_movement_views.sql missing');
  ok(exists('market-movement.js'), 'market-movement.js missing');
});

/* ---------------------------------- 9. the surfaces obey the same rule */
const SURFACES = ['index.html', 'market.html', 'fight.html', 'event.html', 'fighter.html'];
const MARKET_JS = read('market.js');

t('market.js is the only place a surface reads the movement view', () => {
  SURFACES.forEach(f => {
    const src = read(f);
    ok(!/from\(['"]v_fight_market_movement['"]\)/.test(src),
       f + ' queries the movement view directly instead of through market.js');
  });
  ok(/from\('v_fight_market_movement'\)/.test(MARKET_JS),
     'market.js does not read the movement view');
});

t('no surface reads the retired single-instant open columns', () => {
  SURFACES.concat(['market.js']).forEach(f => {
    const src = read(f);
    ['open_p_a', 'open_p_b', 'books_at_open'].forEach(c =>
      ok(src.indexOf(c) === -1, f + ' still reads ' + c));
    ['moveSinceOpen', 'openProb', 'booksAtOpen', 'openCaveat'].forEach(c =>
      ok(src.indexOf(c) === -1, f + ' still uses the retired field ' + c));
  });
});

t('market.js refuses movement below the matched-book floor', () => {
  ok(/MIN_MATCHED_BOOKS\s*=\s*3/.test(MARKET_JS), 'market.js does not pin the floor at 3');
  ok(/matched\s*>=\s*M\.MIN_MATCHED_BOOKS/.test(MARKET_JS),
     'market.js does not gate on the matched book count');
  ok(/usable \? num\(isA \? row\.baseline_p_a/.test(MARKET_JS),
     'market.js reads the baseline without checking it is usable');
});

t('side B moves the opposite way to side A', () => {
  ok(/isA \? movePtsA : -movePtsA/.test(MARKET_JS),
     'market.js does not flip the sign of the move for the other corner');
});

t('the superseded SQL file defines nothing', () => {
  const legacy = read('market_lab_views.sql');
  ok(!/CREATE\s+OR\s+REPLACE\s+VIEW/i.test(legacy),
     'market_lab_views.sql still defines a view — two files, one view, is how they drift');
  ok(/SUPERSEDED/.test(legacy), 'market_lab_views.sql does not say it is superseded');
});

t('every surface explains a dash instead of printing a bare one', () => {
  ok(/not enough comparable books/i.test(read('fight.html')),
     'fight.html prints a bare dash for a missing move');
  ok(/under 3 books|not comparable/i.test(read('market.html')),
     'market.html prints a bare dash for a missing move');
  ok(/not enough comparable books|not yet priced by/i.test(read('index.html')),
     'index.html prints a bare dash for a missing move');
});

// ------------------------------------------------------------------ report
if (failures.length) {
  console.log(`\n  ${passed} passed, ${failures.length} FAILED\n`);
  failures.forEach(f => console.log(`  ✗ ${f}\n`));
  process.exit(1);
}
console.log(`\n  ${passed} passed — movement compares like with like, or says it cannot.\n`);
