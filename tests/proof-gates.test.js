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

// ----------------------------------------------- gates: CLV deferred to CLV-001
// REGRESSION (correction 1). The CLV publication rule belongs to the CLV-001
// protocol. Proof Center must hold no threshold of its own, must derive no
// progress from the legacy closing_odds fields, and must have no reachable count
// that opens the gate.

t('the CLV gate holds no local threshold at all', function () {
  const g = P.GATES.clv;
  eq(g.deferred, true, 'deferred');
  eq(g.authority, 'CLV-001', 'authority');
  eq(g.minObservations, undefined, 'clv must not carry a local threshold');
  eq(g.unit, undefined, 'clv must not carry a local unit to count');
});

t('no count, however large, can open the CLV gate', function () {
  [0, 1, 46, 99, 100, 101, 1e6, Number.MAX_SAFE_INTEGER, Infinity].forEach(function (n) {
    const g = P.evaluateGate('clv', n);
    eq(g.publishable, false, 'publishable at have=' + n);
    eq(g.showValue, false, 'showValue at have=' + n);
    eq(g.status, P.STATUS.COLLECTING, 'status at have=' + n);
  });
});

t('the legacy closing-odds counter is gone, not merely unused', function () {
  eq(typeof P.clvPairCount, 'undefined', 'clvPairCount must not exist');
});

t('a deferred gate reports no progress a page could render', function () {
  const g = P.evaluateGate('clv', 46);
  eq(g.have, null, 'have'); eq(g.need, null, 'need');
  eq(g.remaining, null, 'remaining'); eq(g.pct, null, 'pct');
});

t('only the owning protocol can open a deferred gate', function () {
  eq(P.evaluateGate('clv', 0, { publication_approved: true, authority: 'CLV-001' }).publishable, true, 'real authority');
  [
    { publication_approved: true, authority: 'proof-center' },
    { publication_approved: true },
    { publication_approved: 'true', authority: 'CLV-001' },
    { publication_approved: 1, authority: 'CLV-001' },
    { authority: 'CLV-001' },
    {}, null, undefined, 'yes', true,
  ].forEach(function (a, i) {
    eq(P.evaluateGate('clv', 1e9, a).publishable, false, 'bogus authority #' + i);
  });
});

t('even an approved deferred gate renders no figure from this page', function () {
  const g = P.evaluateGate('clv', 0, { publication_approved: true, authority: 'CLV-001' });
  eq(g.publishable, true, 'publishable');
  eq(g.showValue, false, 'showValue must stay false — surfacing it is a separate change');
});

t('the CLV pending copy is the agreed fail-closed wording', function () {
  const m = P.evaluateGate('clv', 46).message;
  ok(/prospective market-price validation is collecting/i.test(m), 'collecting sentence');
  ok(/no clv figure is publication-approved yet/i.test(m), 'not-approved sentence');
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

// ------------------------------------------------------------ timing evidence
// REGRESSION (correction 3). A same-day timestamp is evidence that a row exists,
// not evidence that it preceded the fight. It must never reach the strong grade,
// and a sealed copy must not carry a row past the timing question either.

const SEAL = f => ({ fight_id: f, snapshot_at: '2026-07-30T05:00:00Z', engine_pick_fighter_id: 7, engine_p_cal: 0.61 });
const call = (f, posted, card) => ({ source: 'live', fight_id: f, published_at: posted, event_date: card, pick_fighter_id: 7, p_cal: 0.61 });

t('a same-day timestamp can NEVER produce a verified pre-fight verdict', function () {
  const e = P.timingEvidence([call(1, '2026-08-02T23:59:00Z', '2026-08-02')], []);
  eq(e.sameDay, 1, 'sameDay');
  eq(e.sealed, 0, 'must not reach the sealed grade');
  eq(e.dated, 0, 'must not reach the dated grade');
  eq(P.timingLevel(call(1, '2026-08-02T00:00:01Z', '2026-08-02'), null), 'sameDay', 'earliest possible same-day moment');
});

t('a same-day SEALED copy is still graded same-day, not sealed', function () {
  // Immutability and timing are separate claims: sealing stops a rewrite, it
  // does not move the clock. A snapshot taken on the card's own day inherits
  // the same-day problem.
  const sameDaySeal = { fight_id: 2, snapshot_at: '2026-08-02T06:00:00Z', engine_pick_fighter_id: 7, engine_p_cal: 0.61 };
  const e = P.timingEvidence([call(2, '2026-08-02T07:00:00Z', '2026-08-02')], [sameDaySeal]);
  eq(e.sealed, 0, 'sealed');
  eq(e.sameDay, 1, 'sameDay');
  eq(e.snapshotPresent, 1, 'still counted as covered by a sealed copy');
  eq(e.snapshotMatched, 1, 'the copy still matches — only the clock falls short');
});

t('a sealed copy taken on an earlier day reaches the strong grade', function () {
  const e = P.timingEvidence([call(3, '2026-07-30T06:00:00Z', '2026-08-02')], [SEAL(3)]);
  eq(e.sealed, 1, 'sealed'); eq(e.dated, 0, 'dated'); eq(e.sameDay, 0, 'sameDay');
});

t('a sealed copy that no longer matches does not confer the sealed grade', function () {
  const wrong = { fight_id: 4, snapshot_at: '2026-07-30T05:00:00Z', engine_pick_fighter_id: 99, engine_p_cal: 0.61 };
  const e = P.timingEvidence([call(4, '2026-07-31T06:00:00Z', '2026-08-02')], [wrong]);
  eq(e.sealed, 0, 'sealed'); eq(e.dated, 1, 'falls back to its own timestamp');
});

// ---------------------------- snapshot: presence vs match vs timing ---------
// REGRESSION. Three separate facts. A sealed copy that exists but has stopped
// matching must be reported as a MISMATCH, never rolled into "no sealed copy" —
// an absence is a gap in coverage, a mismatch is a red flag, and collapsing the
// second into the first would hide exactly the failure the crosscheck is for.

t('a snapshot that exists but does not match: present, not sealed, still a mismatch', function () {
  const row = call(4, '2026-07-31T06:00:00Z', '2026-08-02');
  const wrong = { fight_id: 4, snapshot_at: '2026-07-30T05:00:00Z', engine_pick_fighter_id: 99, engine_p_cal: 0.61 };
  const e = P.timingEvidence([row], [wrong]);

  eq(e.snapshotPresent, 1, 'counts as snapshot-present');
  eq(e.snapshotAbsent, 0, 'must NOT be counted as having no sealed copy');
  eq(e.snapshotMatched, 0, 'matched');
  eq(e.snapshotMismatched, 1, 'reported as a mismatch');
  eq(e.sealed, 0, 'must not receive the sealed timing grade');

  // …and the crosscheck agrees, independently.
  const c = P.crossCheckSnapshots([row], [wrong]);
  eq(c.covered, 1, 'crosscheck covered'); eq(c.mismatched, 1, 'crosscheck mismatched'); eq(c.clean, false, 'crosscheck clean');
});

t('a mismatch on probability alone is still present-and-mismatched', function () {
  const row = call(5, '2026-07-31T06:00:00Z', '2026-08-02');
  const drifted = { fight_id: 5, snapshot_at: '2026-07-30T05:00:00Z', engine_pick_fighter_id: 7, engine_p_cal: 0.88 };
  const e = P.timingEvidence([row], [drifted]);
  eq(e.snapshotPresent, 1, 'present'); eq(e.snapshotMismatched, 1, 'mismatched'); eq(e.sealed, 0, 'sealed');
});

t('the three snapshot facts stay consistent with each other', function () {
  const rows = [
    call(1, '2026-07-31T06:00:00Z', '2026-08-02'),   // sealed copy, matches
    call(2, '2026-07-31T06:00:00Z', '2026-08-02'),   // sealed copy, mismatched
    call(3, '2026-07-31T06:00:00Z', '2026-08-02'),   // no sealed copy
  ];
  const e = P.timingEvidence(rows, [
    SEAL(1),
    { fight_id: 2, snapshot_at: '2026-07-30T05:00:00Z', engine_pick_fighter_id: 99, engine_p_cal: 0.61 },
  ]);
  eq(e.snapshotPresent + e.snapshotAbsent, e.total, 'present + absent must cover every row');
  eq(e.snapshotMatched + e.snapshotMismatched, e.snapshotPresent, 'matched + mismatched must equal present');
  eq(e.snapshotPresent, 2, 'present'); eq(e.snapshotAbsent, 1, 'absent');
  eq(e.snapshotMatched, 1, 'matched'); eq(e.snapshotMismatched, 1, 'mismatched');
  eq(e.sealed, 1, 'only the matching, earlier-day copy earns the sealed grade');
});

t('snapshot presence never implies a timing grade on its own', function () {
  // Present, matching, but taken on the card's own day: covered, not sealed.
  const row = call(6, '2026-08-02T07:00:00Z', '2026-08-02');
  const sameDaySeal = { fight_id: 6, snapshot_at: '2026-08-02T06:00:00Z', engine_pick_fighter_id: 7, engine_p_cal: 0.61 };
  const e = P.timingEvidence([row], [sameDaySeal]);
  eq(e.snapshotPresent, 1, 'present'); eq(e.snapshotMatched, 1, 'matched');
  eq(e.sealed, 0, 'sealed'); eq(e.sameDay, 1, 'sameDay');
});

t('a row posted after its card is unverified, never dated', function () {
  const e = P.timingEvidence([call(5, '2026-08-03T06:00:00Z', '2026-08-02')], []);
  eq(e.unverified, 1, 'unverified'); eq(e.dated, 0, 'dated'); eq(e.sameDay, 0, 'sameDay');
  eq(e.unverifiedRows.length, 1, 'reported, not dropped');
});

t('a row missing either timestamp is unverified', function () {
  eq(P.timingEvidence([call(6, null, '2026-08-02')], []).unverified, 1, 'no published_at');
  eq(P.timingEvidence([call(7, '2026-08-01T06:00:00Z', null)], []).unverified, 1, 'no event_date');
});

t('the four grades always account for every live row exactly once', function () {
  const rows = [
    call(1, '2026-07-30T06:00:00Z', '2026-08-02'),   // sealed
    call(2, '2026-07-31T06:00:00Z', '2026-08-02'),   // dated
    call(3, '2026-08-02T20:00:00Z', '2026-08-02'),   // same day
    call(4, null, '2026-08-02'),                     // unverified
    call(5, '2026-08-09T06:00:00Z', '2026-08-02'),   // unverified (late)
  ];
  const e = P.timingEvidence(rows, [SEAL(1)]);
  eq(e.total, 5, 'total');
  eq(e.sealed + e.dated + e.sameDay + e.unverified, e.total, 'grades must partition the rows');
});

t('timingEvidence ignores replay rows entirely', function () {
  eq(P.timingEvidence([replayWin, replayWin], []).total, 0, 'replay rows graded');
});

t('timingCopy fails closed to "unverified" for anything unrecognised', function () {
  eq(P.timingCopy('made-up').label, P.timingCopy('unverified').label, 'fallback');
  eq(P.timingCopy(undefined).label, P.timingCopy('unverified').label, 'undefined');
});

t('no timing grade describes itself as proof of pre-bell timing', function () {
  // The same-day and unverified blurbs must not read as confirmation.
  ['sameDay', 'unverified'].forEach(function (k) {
    const b = P.timingCopy(k).blurb.toLowerCase();
    ok(b.indexOf('proves') === -1 && b.indexOf('verified before') === -1 && b.indexOf('confirmed') === -1,
       k + ' blurb must not read as proof: ' + b);
  });
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
