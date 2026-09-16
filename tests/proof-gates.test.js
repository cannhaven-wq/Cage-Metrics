/* ==========================================================================
   tests/proof-gates.test.js — the two things the Proof Center must never do.

     1. Blend the live record with the replay record.
     2. Publish a number whose publication gate has not passed.

   Run:  node tests/proof-gates.test.js
   No framework, no dependencies, no CI wiring — `node` is the whole runner.
   Exit code 0 = pass, 1 = fail.
   ========================================================================== */

'use strict';
const P = require('../proof-gates.js');

let passed = 0;
const failures = [];

function t(name, fn) {
  try { fn(); passed++; }
  catch (e) { failures.push(name + '\n      ' + e.message); }
}
function eq(actual, expected, what) {
  if (actual !== expected) {
    throw new Error((what || 'value') + ': expected ' + JSON.stringify(expected) + ', got ' + JSON.stringify(actual));
  }
}
function ok(cond, what) { if (!cond) throw new Error(what || 'expected truthy'); }
function throws(fn, what) {
  let threw = false;
  try { fn(); } catch (e) { threw = true; }
  if (!threw) throw new Error((what || 'call') + ' should have thrown but did not');
}

// Fixtures. Synthetic on purpose — these test the rules, not the data.
const liveWin  = { source: 'live',     won: true,  hit: true,  odds_at_publish: 150, closing_odds: 120, published_at: '2026-08-01T12:00:00Z', event_date: '2026-08-02' };
const liveLoss = { source: 'live',     won: false, hit: false, odds_at_publish: -200, closing_odds: -180, published_at: '2026-08-01T12:00:00Z', event_date: '2026-08-02' };
const livePend = { source: 'live',     won: null,  hit: null,  odds_at_publish: 110, closing_odds: null, published_at: '2026-09-20T12:00:00Z', event_date: '2026-09-26' };
const replayWin= { source: 'backtest', won: true,  hit: true,  odds_at_publish: 150, closing_odds: 140, published_at: '2026-08-18T22:42:57Z', event_date: '2022-05-01' };
const weird    = { source: 'paper',    won: true,  hit: true,  odds_at_publish: 150, closing_odds: 140 };

// ---------------------------------------------------------------- separation

t('splitByRecord keeps live, replay and unrecognised rows apart', function () {
  const s = P.splitByRecord([liveWin, replayWin, weird, liveLoss]);
  eq(s.live.length, 2, 'live');
  eq(s.replay.length, 1, 'replay');
  eq(s.unknown.length, 1, 'unknown');
});

t('an unrecognised source is never counted as live', function () {
  eq(P.recordKind(weird), P.RECORD.UNKNOWN, 'kind of source=paper');
  eq(P.splitByRecord([weird]).live.length, 0, 'live bucket');
});

t('a missing or malformed row is unknown, not live', function () {
  eq(P.recordKind(null), P.RECORD.UNKNOWN, 'null row');
  eq(P.recordKind({}), P.RECORD.UNKNOWN, 'row with no source');
  eq(P.recordKind({ source: 42 }), P.RECORD.UNKNOWN, 'non-string source');
});

t('assertOneRecord throws on a mixed set', function () {
  throws(function () { P.assertOneRecord([liveWin, replayWin]); }, 'mixed live+replay');
});

t('assertOneRecord throws when the set is the wrong record', function () {
  throws(function () { P.assertOneRecord([replayWin], P.RECORD.LIVE); }, 'replay rows asked to be live');
});

t('assertOneRecord accepts a single-record set and an empty set', function () {
  ok(P.assertOneRecord([liveWin, liveLoss], P.RECORD.LIVE), 'live only');
  ok(P.assertOneRecord([], P.RECORD.LIVE), 'empty');
});

t('flatStakeLedger refuses to total a mixed record', function () {
  throws(function () {
    P.flatStakeLedger([liveWin, replayWin], { expectRecord: P.RECORD.LIVE });
  }, 'mixed ledger');
});

t('straightRecord refuses to total a mixed record', function () {
  throws(function () {
    P.straightRecord([liveWin, replayWin], { expectRecord: P.RECORD.LIVE });
  }, 'mixed record');
});

t('clvPairCount ignores replay rows even when they carry both prices', function () {
  eq(P.clvPairCount([replayWin, replayWin, replayWin]), 0, 'replay pairs');
  eq(P.clvPairCount([liveWin, liveLoss, livePend, replayWin]), 2, 'live pairs only');
});

// --------------------------------------------------------------------- gates

t('the CLV gate stays shut below its floor and shows no value', function () {
  const g = P.evaluateGate('clv', 46);
  eq(g.publishable, false, 'publishable');
  eq(g.showValue, false, 'showValue');
  eq(g.status, P.STATUS.COLLECTING, 'status');
  eq(g.remaining, 54, 'remaining');
});

t('the CLV gate opens exactly at its floor, not before', function () {
  eq(P.evaluateGate('clv', 99).publishable, false, 'at 99');
  eq(P.evaluateGate('clv', 100).publishable, true, 'at 100');
  eq(P.evaluateGate('clv', 100).status, P.STATUS.APPROVED, 'status at 100');
});

t('the pending message never hints at the unpublished number', function () {
  const msg = P.evaluateGate('clv', 46).message.toLowerCase();
  ['beat', 'ahead', 'positive', 'negative', 'profit', 'edge', 'winning'].forEach(function (w) {
    ok(msg.indexOf(w) === -1, 'pending message must not contain "' + w + '"');
  });
});

t('an unknown gate fails closed', function () {
  const g = P.evaluateGate('nope', 1e9);
  eq(g.publishable, false, 'publishable');
  eq(g.showValue, false, 'showValue');
  eq(g.status, P.STATUS.COLLECTING, 'status');
});

t('rubbish counts are treated as zero, never as a pass', function () {
  [NaN, Infinity, -5, null, undefined, 'lots'].forEach(function (v) {
    const g = P.evaluateGate('clv', v);
    eq(g.have, 0, 'have for ' + String(v));
    eq(g.publishable, false, 'publishable for ' + String(v));
  });
});

t('every defined gate is live-record only and has a written source', function () {
  Object.keys(P.GATES).forEach(function (id) {
    const g = P.GATES[id];
    eq(g.record, P.RECORD.LIVE, id + '.record');
    ok(typeof g.source === 'string' && g.source.length > 10, id + ' needs a source citation');
    ok(typeof g.pending === 'string' && g.pending.length > 10, id + ' needs pending copy');
    ok(g.minObservations >= 1, id + '.minObservations');
  });
});

t('below-floor gates that do show a value are labelled provisional', function () {
  const g = P.evaluateGate('liveRecord', 12);
  eq(g.showValue, true, 'showValue');
  eq(g.publishable, false, 'publishable');
  eq(g.status, P.STATUS.PROVISIONAL, 'status');
});

t('statusCopy falls back to "still collecting" for anything unrecognised', function () {
  eq(P.statusCopy('made-up').label, P.statusCopy(P.STATUS.COLLECTING).label, 'fallback');
});

// --------------------------------------------------------------------- money

t('winProfit matches the sportsbook on both signs', function () {
  eq(Math.round(P.winProfit(150, 100)), 150, '+150');
  eq(Math.round(P.winProfit(-200, 100) * 100) / 100, 50, '-200');
  eq(P.winProfit(0, 100), null, 'zero odds');
  eq(P.winProfit(null, 100), null, 'missing odds');
  eq(P.winProfit('abc', 100), null, 'junk odds');
});

t('the ledger counts pending as pending, not as a loss', function () {
  const L = P.flatStakeLedger([liveWin, liveLoss, livePend], { expectRecord: P.RECORD.LIVE });
  eq(L.wins, 1, 'wins'); eq(L.losses, 1, 'losses');
  eq(L.settled, 2, 'settled'); eq(L.pending, 1, 'pending');
  eq(Math.round(L.pnl), 50, 'pnl');           // +150 on the win, -100 on the loss
});

t('a settled row with no price is reported as unpriced, not counted as a win', function () {
  const L = P.flatStakeLedger([{ source: 'live', won: true, odds_at_publish: null }], { expectRecord: P.RECORD.LIVE });
  eq(L.unpriced, 1, 'unpriced'); eq(L.wins, 0, 'wins'); eq(L.settled, 0, 'settled'); eq(L.pnl, 0, 'pnl');
});

t('an empty ledger reports no rate rather than zero', function () {
  const L = P.flatStakeLedger([], { expectRecord: P.RECORD.LIVE });
  eq(L.perBet, null, 'perBet'); eq(L.hitRate, null, 'hitRate');
});

t('straightRecord counts misses at full weight', function () {
  const r = P.straightRecord([liveWin, liveLoss, liveLoss, livePend], { expectRecord: P.RECORD.LIVE });
  eq(r.hits, 1, 'hits'); eq(r.misses, 2, 'misses'); eq(r.pending, 1, 'pending');
  eq(Math.round(r.hitRate * 100), 33, 'hitRate');
});

// ----------------------------------------------------------------- timestamps

t('timestampAudit counts a same-day post separately from a genuine day-before', function () {
  const sameDay = { source: 'live', published_at: '2026-08-02T23:00:00Z', event_date: '2026-08-02' };
  const a = P.timestampAudit([liveWin, sameDay]);
  eq(a.inOrder, 2, 'inOrder');
  eq(a.sameDay, 1, 'sameDay');
  eq(a.dayBefore, 1, 'dayBefore');
});

t('timestampAudit flags a pick posted after its card', function () {
  const late = { source: 'live', published_at: '2026-08-03T01:00:00Z', event_date: '2026-08-02' };
  const a = P.timestampAudit([liveWin, late]);
  eq(a.total, 2, 'total'); eq(a.inOrder, 1, 'inOrder'); eq(a.late, 1, 'late'); eq(a.clean, false, 'clean');
});

t('timestampAudit does not count an undated row as in order', function () {
  const a = P.timestampAudit([{ source: 'live', published_at: null, event_date: '2026-08-02' }]);
  eq(a.inOrder, 0, 'inOrder'); eq(a.undated, 1, 'undated'); eq(a.clean, false, 'clean');
});

t('timestampAudit ignores replay rows entirely', function () {
  eq(P.timestampAudit([replayWin, replayWin]).total, 0, 'replay rows audited');
});

t('an empty live record is not "clean"', function () {
  eq(P.timestampAudit([]).clean, false, 'clean on empty');
});

// ------------------------------------------------- immutable-copy crosscheck

const snapPick = { source: 'live', fight_id: 10, pick_fighter_id: 7, p_cal: 0.6123, published_at: '2026-08-01T00:00:00Z', event_date: '2026-08-02' };
const snapRow  = { fight_id: 10, engine_pick_fighter_id: 7, engine_p_cal: 0.6123 };

t('a pick matching its frozen copy counts as matched', function () {
  const c = P.crossCheckSnapshots([snapPick], [snapRow]);
  eq(c.covered, 1, 'covered'); eq(c.matched, 1, 'matched'); eq(c.mismatched, 0, 'mismatched'); eq(c.clean, true, 'clean');
});

t('a pick whose frozen copy names a different fighter is a mismatch', function () {
  const c = P.crossCheckSnapshots([snapPick], [{ fight_id: 10, engine_pick_fighter_id: 99, engine_p_cal: 0.6123 }]);
  eq(c.matched, 0, 'matched'); eq(c.mismatched, 1, 'mismatched'); eq(c.clean, false, 'clean');
});

t('a pick whose frozen copy carries a different probability is a mismatch', function () {
  const c = P.crossCheckSnapshots([snapPick], [{ fight_id: 10, engine_pick_fighter_id: 7, engine_p_cal: 0.71 }]);
  eq(c.mismatched, 1, 'mismatched'); eq(c.clean, false, 'clean');
});

t('a fight with no frozen copy is uncovered, not a mismatch', function () {
  const c = P.crossCheckSnapshots([snapPick], []);
  eq(c.covered, 0, 'covered'); eq(c.mismatched, 0, 'mismatched'); eq(c.clean, false, 'clean');
});

t('the crosscheck ignores replay rows', function () {
  const c = P.crossCheckSnapshots([replayWin], [{ fight_id: replayWin.fight_id, engine_pick_fighter_id: 1, engine_p_cal: 0.5 }]);
  eq(c.covered, 0, 'covered');
});

t('a probability equal within float noise still matches', function () {
  const c = P.crossCheckSnapshots([snapPick], [{ fight_id: 10, engine_pick_fighter_id: '7', engine_p_cal: 0.6123000000001 }]);
  eq(c.matched, 1, 'matched');
});

// ------------------------------------------------------------------- report

if (failures.length) {
  console.error('\n  ' + failures.length + ' FAILED, ' + passed + ' passed\n');
  failures.forEach(function (f) { console.error('  ✗ ' + f); });
  console.error('');
  process.exit(1);
}
console.log('\n  ' + passed + ' passed — replay/live separation and publication gating hold.\n');
