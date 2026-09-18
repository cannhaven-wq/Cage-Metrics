// Tests for research/factors/measure_edges_bands.js — T-015.
//
// The script cannot be run in every environment: it needs a service key,
// because fight_odds has no SELECT policy for anon. That is exactly why its
// LOGIC needs testing separately. A measurement nobody can check is not
// evidence, and a rule that silently stops matching edges.js would produce a
// confident number about the wrong thing.
//
// So these tests pin two things:
//   1. the rules reproduce edges.js's triggers and bands on hand-worked cases;
//   2. the point-in-time walk really is point-in-time — a fighter's record at
//      fight N reflects fights 1..N-1 and nothing later.
//
// No framework, no dependencies, same shape as the other suites in tests/.
//   node tests/edges-bands.test.js

'use strict';

const M = require('../research/factors/measure_edges_bands.js');
const E = require('../edges.js');

let passed = 0;
const failures = [];

function t(name, fn) {
  try { fn(); passed += 1; } catch (err) { failures.push(`${name}\n      ${err.message}`); }
}
function eq(actual, expected, what) {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) throw new Error(`${what || 'value'}: expected ${e}, got ${a}`);
}
function ok(cond, what) { if (!cond) throw new Error(what || 'expected truthy'); }
function close(a, b, tol, what) {
  if (Math.abs(a - b) > (tol || 1e-9)) throw new Error(`${what || 'value'}: ${a} vs ${b}`);
}

// ---------------------------------------------------------------- constants
// If edges.js moves its thresholds and this script does not, the measurement
// silently describes a rule the site no longer runs. These two assertions are
// the tripwire for that.

t('the record trigger still matches edges.js', () => {
  // edges.js: `if (gap < 0.08) return null;`
  const src = require('fs').readFileSync(`${__dirname}/../edges.js`, 'utf8');
  ok(/gap\s*<\s*0\.08/.test(src), 'edges.js no longer triggers record at 0.08');
  eq(M.RECORD_TRIGGER, 0.08, 'RECORD_TRIGGER');
});

t('the record bands and their claimed rates still match edges.js', () => {
  const src = require('fs').readFileSync(`${__dirname}/../edges.js`, 'utf8');
  for (const [cut, pct] of [['0.40', '72.0'], ['0.25', '70.0'], ['0.15', '65.0']]) {
    ok(src.includes(`gap >= ${cut}`), `edges.js lost the ${cut} record cut`);
    ok(src.includes(`pct = ${pct}`), `edges.js lost the ${pct} record rate`);
  }
  eq(M.RECORD_BANDS.map((b) => b.claimed), [60, 65, 70, 72], 'claimed record rates');
});

t('the td_def trigger and bands still match edges.js', () => {
  const src = require('fs').readFileSync(`${__dirname}/../edges.js`, 'utf8');
  ok(/gap\s*<\s*10/.test(src), 'edges.js no longer triggers td_def at 10');
  for (const [cut, pct] of [['30', '56.0'], ['20', '54.0']]) {
    ok(src.includes(`gap >= ${cut}`), `edges.js lost the ${cut} td_def cut`);
    ok(src.includes(`pct = ${pct}`), `edges.js lost the ${pct} td_def rate`);
  }
  eq(M.TD_BANDS.map((b) => b.claimed), [52.5, 54, 56], 'claimed td_def rates');
  eq(M.TD_LOW, E.STYLE_THRESHOLDS.TD_LOW, 'wrestling gate threshold');
});

// ------------------------------------------------------------------- rules

t('record smoothing reproduces edges.js exactly', () => {
  // edges.js: (aw + 2) / (aTotal + 4)
  close(M.smoothed(9, 10), 11 / 14, 1e-12, '9-1');
  close(M.smoothed(5, 10), 7 / 14, 1e-12, '5-5');
});

t('record does not fire below three combined fights', () => {
  const m = {
    a: { id: 1 }, b: { id: 2 },
    sA: { fights: 1, wins: 1 }, sB: { fights: 1, wins: 0 },
  };
  eq(M.recordRule(m), null, 'two combined fights');
});

t('record does not fire below the 0.08 gap', () => {
  // 5-5 vs 6-4: 7/14 = .500 vs 8/14 = .571 -> gap .0714, under the trigger
  const m = {
    a: { id: 1 }, b: { id: 2 },
    sA: { fights: 10, wins: 5 }, sB: { fights: 10, wins: 6 },
  };
  eq(M.recordRule(m), null, 'gap 0.071');
});

t('record fires and picks the better record', () => {
  // 9-1 vs 5-5: 11/14 = .7857 vs 7/14 = .5 -> gap .2857, third band
  const m = {
    a: { id: 1 }, b: { id: 2 },
    sA: { fights: 10, wins: 9 }, sB: { fights: 10, wins: 5 },
  };
  const r = M.recordRule(m);
  close(r.gap, 11 / 14 - 7 / 14, 1e-12, 'gap');
  eq(r.pickId, 1, 'picks the better record');
  ok(r.gap >= 0.25 && r.gap < 0.40, 'lands in the 70% band');
});

t('takedown defence is point-in-time and needs five faced attempts', () => {
  eq(M.tdDefOf({ td_faced: 4, td_conceded: 0 }), null, 'under the attempt floor');
  close(M.tdDefOf({ td_faced: 10, td_conceded: 2 }), 80, 1e-9, '8 of 10 stuffed');
});

t('the wrestling gate is edges.js willHaveWrestling', () => {
  const grappler = { minutes: 15, td_landed: 1 };  // td_avg 1.0, exactly at TD_LOW
  const nobody = { minutes: 15, td_landed: 0 };
  ok(M.willHaveWrestling(grappler, nobody), 'one shooter is enough');
  ok(!M.willHaveWrestling(nobody, nobody), 'neither shoots');
});

t('td_def does not fire under a 10-point gap, and does at 10', () => {
  const mk = (fa, ca, fb, cb) => ({
    a: { id: 1 }, b: { id: 2 },
    sA: { td_faced: fa, td_conceded: ca, minutes: 15, td_landed: 5 },
    sB: { td_faced: fb, td_conceded: cb, minutes: 15, td_landed: 5 },
  });
  // 80% vs 75% -> 5 points
  eq(M.tdDefRule(mk(10, 2, 20, 5), false), null, 'five-point gap');
  // 90% vs 80% -> 10 points, exactly at the trigger
  const r = M.tdDefRule(mk(10, 1, 10, 2), false);
  ok(r, 'ten-point gap fires');
  close(r.gap, 10, 1e-9, 'gap');
  eq(r.pickId, 1, 'picks the better defence');
});

t('the wrestling gate can suppress a firing td_def edge', () => {
  const m = {
    a: { id: 1 }, b: { id: 2 },
    sA: { td_faced: 10, td_conceded: 1, minutes: 15, td_landed: 0 },
    sB: { td_faced: 10, td_conceded: 2, minutes: 15, td_landed: 0 },
  };
  ok(M.tdDefRule(m, false), 'fires ungated');
  eq(M.tdDefRule(m, true), null, 'gated off when neither fighter shoots');
});

t('age fires at a one-year gap and picks the younger fighter', () => {
  eq(M.ageRule({ a: { id: 1 }, b: { id: 2 }, ageA: 30, ageB: 30 }), null, 'no gap');
  const r = M.ageRule({ a: { id: 1 }, b: { id: 2 }, ageA: 28, ageB: 34 });
  eq(r.pickId, 1, 'younger');
  close(r.gap, 6, 1e-9, 'gap');
});

// ------------------------------------------------------------------ stats

t('Wilson intervals behave at small n and never straddle impossibly', () => {
  const r = M.rate(3, 4);
  ok(r.ci_lo > 0 && r.ci_hi < 100, 'bounded');
  ok(r.ci_lo < r.pct && r.pct < r.ci_hi, 'contains the point estimate');
  eq(M.rate(0, 0), null, 'no observations means no rate, not zero');
});

t('the verdict ladder matches build/factor-rates.js', () => {
  const big = (pct) => ({ n: 500, wins: Math.round(5 * pct), pct, ci_lo: pct - 2, ci_hi: pct + 2 });
  eq(M.verdictFor({ n: 50 }, { n: 50 }), 'insufficient', 'under the overall floor');
  eq(M.verdictFor(big(60), { n: 40 }), 'unproven', 'under the market-even floor');
  eq(M.verdictFor(big(60), big(60)), 'real', 'interval clears 50');
  eq(M.verdictFor(big(60), { n: 500, pct: 40, ci_lo: 38, ci_hi: 42 }), 'inverted', 'below 50');
  eq(M.verdictFor(big(60), { n: 500, pct: 56, ci_lo: 49, ci_hi: 63 }), 'lean', 'straddles, >= 55');
  eq(M.verdictFor(big(60), { n: 500, pct: 51, ci_lo: 46, ci_hi: 56 }), 'proxy', 'straddles, < 55');
});

t('a claimed rate is tested against the measured interval, not the point estimate', () => {
  const even = { n: 300, pct: 52, ci_lo: 47, ci_hi: 57 };
  eq(M.claimVerdict(70, even), 'claim_above_interval', '70% claim vs a 47-57 interval');
  eq(M.claimVerdict(55, even), 'claim_inside_interval', '55% claim');
  eq(M.claimVerdict(40, even), 'claim_below_interval', '40% claim');
  eq(M.claimVerdict(70, { n: 40 }), 'untested', 'too few market-even fights to judge');
});

// -------------------------------------------------------- point-in-time

t('the walk is point-in-time: state at fight N excludes fight N and later', () => {
  // Three fights. Fighter 1 wins the first two, then meets fighter 4.
  // At that third fight fighter 1 must read 2-0, never 3-0.
  const fighters = [1, 2, 3, 4].map((id) => ({ id, name: `F${id}`, dob: '1995-01-01' }));
  const events = [
    { id: 10, event_date: '2020-01-01' },
    { id: 11, event_date: '2020-06-01' },
    { id: 12, event_date: '2021-01-01' },
  ];
  const fights = [
    { id: 1, event_id: 10, fighter_a_id: 1, fighter_b_id: 2, winner_id: 1, end_round: 3, end_time: '5:00' },
    { id: 2, event_id: 11, fighter_a_id: 1, fighter_b_id: 3, winner_id: 1, end_round: 3, end_time: '5:00' },
    { id: 3, event_id: 12, fighter_a_id: 1, fighter_b_id: 4, winner_id: 4, end_round: 3, end_time: '5:00' },
  ];
  const odds = fights.flatMap((f) => ([
    { fight_id: f.id, fighter_id: f.fighter_a_id, american_odds: -110, is_closer: true },
    { fight_id: f.id, fighter_id: f.fighter_b_id, american_odds: -110, is_closer: true },
  ]));

  const ms = M.buildMatchups({ events, fights, fighters, odds });
  eq(ms.length, 3, 'three scored matchups');
  eq(ms[0].sA, { fights: 0, wins: 0, minutes: 0, td_landed: 0, td_faced: 0, td_conceded: 0 }, 'debut is blank');
  eq(ms[1].sA.fights, 1, 'one prior fight at the second bout');
  eq(ms[2].sA.fights, 2, 'two prior fights at the third bout');
  eq(ms[2].sA.wins, 2, 'two prior wins — the loss it is about to take is not counted');
});

t('a fight at even money lands in the market-even cohort; a big favourite does not', () => {
  const fighters = [1, 2].map((id) => ({ id, name: `F${id}`, dob: '1995-01-01' }));
  const events = [{ id: 10, event_date: '2020-01-01' }, { id: 11, event_date: '2020-02-01' }];
  const fights = [
    { id: 1, event_id: 10, fighter_a_id: 1, fighter_b_id: 2, winner_id: 1, end_round: 3, end_time: '5:00' },
    { id: 2, event_id: 11, fighter_a_id: 1, fighter_b_id: 2, winner_id: 1, end_round: 3, end_time: '5:00' },
  ];
  const odds = [
    { fight_id: 1, fighter_id: 1, american_odds: -120, is_closer: true },
    { fight_id: 1, fighter_id: 2, american_odds: +100, is_closer: true },
    { fight_id: 2, fighter_id: 1, american_odds: -400, is_closer: true },
    { fight_id: 2, fighter_id: 2, american_odds: +320, is_closer: true },
  ];
  const ms = M.buildMatchups({ events, fights, fighters, odds });
  eq(ms[0].even, true, 'pick-em is market-even');
  eq(ms[1].even, false, '-400 is outside the band');
});

t('scoreFactor separates the raw column from the market-controlled one', () => {
  // Eight fights. The rule is right on every lopsided one and wrong on every
  // even one — the exact shape of a factor that is only reading the favourite.
  const mk = (i, even, winner) => ({
    id: i, a: { id: 1 }, b: { id: 2 }, winner, even,
    sA: { fights: 10, wins: 9 }, sB: { fights: 10, wins: 2 },
  });
  const ms = [
    mk(1, false, 1), mk(2, false, 1), mk(3, false, 1), mk(4, false, 1),
    mk(5, true, 2), mk(6, true, 2), mk(7, true, 2), mk(8, true, 2),
  ];
  const r = M.scoreFactor(ms, M.recordRule, M.RECORD_BANDS);
  eq(r.headline.all.n, 8, 'fires on all eight');
  eq(r.headline.all.pct, 50, 'raw 50%');
  eq(r.headline.even.n, 4, 'four market-even');
  eq(r.headline.even.pct, 0, 'zero under market control');
});

// ------------------------------------------------------------------ report
if (failures.length) {
  console.log(`\n  ${passed} passed, ${failures.length} FAILED\n`);
  failures.forEach((f) => console.log(`  ✗ ${f}\n`));
  process.exit(1);
}
console.log(`\n  ${passed} passed — the measurement reproduces edges.js's own rules.\n`);
