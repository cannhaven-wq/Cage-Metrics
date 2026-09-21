// Regression test — the homepage headline can never pool the live and replay
// records. T-026.
//
// THE DEFECT THIS PINS
//
// index.html's loadHeroProof() called cfl.fetchEnginePicks() with no `source`
// filter. v_model_picks_graded carries both the prospective live feed and the
// walk-forward history replay, so the homepage's headline accuracy, its
// graded-fight count, its Lock-tier rate and its "Why trust it?" tiles were
// averages over the two records pooled together — the exact operation
// proof-gates.js::assertOneRecord exists to refuse, on the most prominent
// number on the site.
//
// Two halves, and both are needed:
//
//   1. FUNCTIONAL — headlineFromPicks refuses a mixed set, and refuses a
//      caller who has not said which record they are summarising. This is the
//      guarantee.
//   2. STATIC — index.html actually routes through it, with a source filter,
//      having loaded the rulebook. A perfect guarantee in a module the page
//      does not call protects nothing, and re-introducing the bug means
//      deleting one of these lines, which fails here.
//
//   node tests/hero-record.test.js

'use strict';

const fs = require('fs');
const path = require('path');
const P = require('../proof-gates.js');

const INDEX = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const PROOF = fs.readFileSync(path.join(__dirname, '..', 'proof.html'), 'utf8');
const TRACK = fs.readFileSync(path.join(__dirname, '..', 'track-record.html'), 'utf8');

let passed = 0;
const failures = [];
function t(name, fn) {
  try { fn(); passed += 1; } catch (err) { failures.push(`${name}\n      ${err.message}`); }
}
function ok(cond, what) { if (!cond) throw new Error(what || 'expected truthy'); }
function eq(a, b, what) {
  if (JSON.stringify(a) !== JSON.stringify(b)) {
    throw new Error(`${what || 'value'}: expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`);
  }
}
function throws(fn, what) {
  let threw = false;
  try { fn(); } catch (e) { threw = true; }
  if (!threw) throw new Error(`${what || 'call'} should have thrown but did not`);
}

const live = (hit, tier) => ({ source: 'live', hit, tier: tier || 'Lean' });
const replay = (hit, tier) => ({ source: 'backtest', hit, tier: tier || 'Lean' });

// ------------------------------------------------------------- functional

t('a mixed set throws rather than producing a headline', () => {
  throws(() => P.headlineFromPicks([live(true), replay(true)], P.RECORD.REPLAY),
    'live + replay pooled');
});

t('the exact shape of the old bug throws', () => {
  // 100 replay rows at 60% and 20 live rows at 30% — the old code would have
  // quietly published the blend. There is no argument to headlineFromPicks
  // that returns a number for this input.
  const rows = [];
  for (let i = 0; i < 100; i++) rows.push(replay(i < 60));
  for (let i = 0; i < 20; i++) rows.push(live(i < 6));
  throws(() => P.headlineFromPicks(rows, P.RECORD.REPLAY), 'the original defect');
  throws(() => P.headlineFromPicks(rows, P.RECORD.LIVE), 'and the other way round');
});

t('a caller that does not name its record is refused', () => {
  throws(() => P.headlineFromPicks([replay(true)]), 'no expected record');
});

t('asking for one record and being handed the other throws', () => {
  throws(() => P.headlineFromPicks([replay(true), replay(false)], P.RECORD.LIVE),
    'replay rows asked to be live');
});

// --------------------------------------- unknown sources, and failing closed
//
// THE SECOND DEFECT, found in review after the first fix.
//
// assertOneRecord deletes UNKNOWN from the set of record kinds it inspects, so
// a graded row whose `source` is neither 'live' nor 'backtest' passed the gate.
// It was then counted anyway: headlineFromPicks aggregates over `graded`, not
// over the rows the assertion approved. So an unclassifiable row contributed to
// n, to hits and to the published accuracy, having been explicitly waved past
// the check meant to protect that number.
//
// An earlier version of this very file asserted that behaviour was correct
// (`eq(h.n, 3, 'unknown rows are still graded rows')`), which is how it
// survived. For a published trust statistic the rule is the other way round:
// every row that reaches the arithmetic must resolve to the record being
// claimed, and a row that does not stops the number rather than joining it.

t('an unrecognised source throws rather than contributing to the number', () => {
  const rows = [replay(true), replay(false), { source: 'something-new', hit: true }];
  throws(() => P.headlineFromPicks(rows, P.RECORD.REPLAY),
    'a graded row with an unresolvable source');
});

t('the error names the offending source, so it can be diagnosed', () => {
  let msg = '';
  try {
    P.headlineFromPicks([replay(true), { source: 'shadow-feed', hit: true }], P.RECORD.REPLAY);
  } catch (e) { msg = e.message; }
  ok(msg.includes('shadow-feed'), `the message should name the source, got: ${msg}`);
});

t('a missing or non-string source throws too', () => {
  throws(() => P.headlineFromPicks([replay(true), { hit: true }], P.RECORD.REPLAY),
    'a graded row with no source at all');
  throws(() => P.headlineFromPicks([replay(true), { source: null, hit: false }], P.RECORD.REPLAY),
    'a graded row with a null source');
});

t('the harm is arithmetic, and it is what the throw prevents', () => {
  // 2 replay rows, both hits, plus one unknown-source miss. Under the old
  // behaviour this published 2/3 = 66.7% "replay accuracy" while the replay
  // record it claimed to describe was 2/2 = 100%. The number on screen was
  // moved by a row nobody could account for.
  const rows = [replay(true), replay(true), { source: 'something-new', hit: false }];
  throws(() => P.headlineFromPicks(rows, P.RECORD.REPLAY), 'an unknown row skewing the rate');

  // And the clean subset still summarises, so the throw is about provenance
  // and not about the arithmetic being broken.
  const clean = P.headlineFromPicks(rows.slice(0, 2), P.RECORD.REPLAY, { minPicks: 1, minLocks: 1 });
  eq(clean.n, 2, 'clean n');
  eq(clean.accuracy, 100, 'clean accuracy');
});

t('an UNGRADED unknown-source row does not throw — it never reaches the number', () => {
  // Only graded rows are aggregated, so a pending row of unknown provenance is
  // filtered out before the assertion and is not an error. Failing closed means
  // refusing what would be counted, not refusing everything.
  const h = P.headlineFromPicks(
    [replay(true), replay(false), { source: 'something-new', hit: null }],
    P.RECORD.REPLAY, { minPicks: 1, minLocks: 1 });
  eq(h.n, 2, 'pending unknown rows are excluded, not fatal');
});

t('unknown is still never relabelled as live', () => {
  // The original property, kept: a row we cannot classify must not be treated
  // as live by default. This guards recordKind itself.
  eq(P.recordKind({ source: 'something-new', hit: true }), P.RECORD.UNKNOWN, 'unknown stays unknown');
  eq(P.recordKind({ hit: true }), P.RECORD.UNKNOWN, 'missing source is unknown');
});

t('assertEveryRow is the strict form, and assertOneRecord keeps the loose one', () => {
  // Two different questions, deliberately. assertOneRecord asks "is this all
  // one record?" and tolerates an unknown row; assertEveryRow asks "does every
  // row resolve?" and does not. Aggregates that publish must use the second.
  // Pinned so the two cannot be quietly collapsed into one.
  const rows = [replay(true), { source: 'something-new', hit: true }];
  ok(P.assertOneRecord(rows, P.RECORD.REPLAY), 'assertOneRecord tolerates an unknown row');
  throws(() => P.assertEveryRow(rows, P.RECORD.REPLAY), 'assertEveryRow must not');
  throws(() => P.assertEveryRow(rows), 'assertEveryRow with no expected record');
});

t('the headline routes through the strict assertion, not the loose one', () => {
  // Static check on the module's own source: swapping assertEveryRow back to
  // assertOneRecord inside headlineFromPicks would restore the defect while
  // every functional test above still had something to call. This is the line
  // that stops that.
  const SRC = fs.readFileSync(path.join(__dirname, '..', 'proof-gates.js'), 'utf8');
  const body = SRC.slice(SRC.indexOf('function headlineFromPicks'));
  const fn = body.slice(0, body.indexOf('\n  }'));
  ok(/assertEveryRow\(graded, expected\)/.test(fn),
    'headlineFromPicks must call assertEveryRow on the graded rows');
  ok(!/assertOneRecord\(graded/.test(fn),
    'headlineFromPicks must not fall back to the permissive assertion');
});

t('a clean single-record set summarises correctly', () => {
  const rows = [replay(true, 'Lock'), replay(false, 'Lock'), replay(true), replay(true)];
  const h = P.headlineFromPicks(rows, P.RECORD.REPLAY, { minPicks: 1, minLocks: 1 });
  eq(h.record, P.RECORD.REPLAY, 'record');
  eq(h.n, 4, 'n');
  eq(h.hits, 3, 'hits');
  eq(h.accuracy, 75, 'accuracy');
  eq(h.lockN, 2, 'locks');
  eq(h.lockAccuracy, 50, 'lock accuracy');
});

t('pending rows are excluded, never counted as losses', () => {
  const rows = [replay(true), replay(false), { source: 'backtest', hit: null }];
  const h = P.headlineFromPicks(rows, P.RECORD.REPLAY, { minPicks: 1 });
  eq(h.n, 2, 'only settled rows');
  eq(h.accuracy, 50, 'accuracy over settled rows only');
});

t('small samples are not publishable', () => {
  const rows = [];
  for (let i = 0; i < 99; i++) rows.push(replay(true));
  eq(P.headlineFromPicks(rows, P.RECORD.REPLAY).publishable, false, '99 picks');
  rows.push(replay(true));
  eq(P.headlineFromPicks(rows, P.RECORD.REPLAY).publishable, true, '100 picks');
});

t('the Lock floor is separate from the headline floor', () => {
  const rows = [];
  for (let i = 0; i < 100; i++) rows.push(replay(true));
  for (let i = 0; i < 49; i++) rows.push(replay(true, 'Lock'));
  eq(P.headlineFromPicks(rows, P.RECORD.REPLAY).locksPublishable, false, '49 locks');
  rows.push(replay(true, 'Lock'));
  eq(P.headlineFromPicks(rows, P.RECORD.REPLAY).locksPublishable, true, '50 locks');
});

t('an empty set produces no rate rather than zero', () => {
  const h = P.headlineFromPicks([], P.RECORD.REPLAY);
  eq(h.accuracy, null, 'no accuracy');
  eq(h.publishable, false, 'not publishable');
});

// ----------------------------------------------------------------- static
// The guarantee above is only worth anything where a record is published.
//
// UPDATED 2026-09-21 (the research repositioning). The homepage used to carry
// the engine's replay headline — "61.5% straight-up across 3,235 never-seen
// fights · Locks hit 74.5% (simulated)" — and the four static checks here
// pinned it to the rulebook so it could not silently pool the live and replay
// records. The homepage no longer publishes that record, or any model record,
// at all. A page with no engine accuracy on it cannot pool two of them, which
// is strictly stronger than what these lines used to enforce, so the checks
// move: index.html is now asserted to publish nothing, and the routing checks
// follow the record to the pages that still carry one.
//
// The functional half above is untouched. The rulebook is what actually holds.

t('the homepage publishes no engine record at all', () => {
  ok(!/headlineFromPicks/.test(INDEX),
    'index.html is computing an engine headline again — the homepage does not publish a model record');
  ok(!/HERO_RECORD_SOURCE/.test(INDEX),
    'the hero record source constant is back in index.html');
  ok(!/v_model_picks_graded|fetchEnginePicks/.test(INDEX),
    'index.html is reading the graded picks feed again');
});

t('the homepage quotes no model accuracy figure', () => {
  // Strip comments and <style> first: a comment explaining why a number is
  // forbidden must not itself trip the check for that number.
  const visible = INDEX
    .replace(/<style>[\s\S]*?<\/style>/g, ' ')
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/^\s*\/\/.*$/gm, ' ');
  ok(!/\b6[0-9]\.[0-9]%\s*(straight-up|of its picks)/.test(visible),
    'a hardcoded engine accuracy is back on the homepage');
  ok(!/Locks?\s+hit\b/i.test(visible),
    'the Lock-tier accuracy is back on the homepage');
});

t('the Proof Center still routes its record through the rulebook', () => {
  ok(/<script src="proof-gates\.js"><\/script>/.test(PROOF),
    'proof.html does not load proof-gates.js');
  const rulebook = PROOF.indexOf('src="proof-gates.js"');
  const usage = PROOF.search(/P\.(straightRecord|headlineFromPicks|assertOneRecord|flatStakeLedger)/);
  ok(rulebook > -1 && usage > -1, 'both present');
  ok(rulebook < usage, 'proof-gates.js must load before it is called');
});

t('every published record summary names which record it is', () => {
  // straightRecord / flatStakeLedger must always be told which record they are
  // summarising; an un-named call is how two records get pooled.
  const calls = PROOF.match(/P\.(straightRecord|flatStakeLedger)\([^)]*\)/g) || [];
  ok(calls.length > 0, 'proof.html no longer summarises a record at all');
  calls.forEach(c => { ok(/expectRecord/.test(c), 'un-named record summary — ' + c); });
});

t('the model archive keeps the two records apart by source', () => {
  // track-record.html does not use the rulebook module; it splits by the
  // `source` column directly. Either route is fine, but it must split.
  ok(/r\.source === 'backtest'/.test(TRACK) && /r\.source === 'live'/.test(TRACK),
    'track-record.html no longer separates the replay and live records');
});

// ----------------------------------------------------------------- report
if (failures.length) {
  console.log(`\n  ${passed} passed, ${failures.length} FAILED\n`);
  failures.forEach((f) => console.log(`  ✗ ${f}\n`));
  process.exit(1);
}
console.log(`\n  ${passed} passed — no record is published without naming which record it is.\n`);
