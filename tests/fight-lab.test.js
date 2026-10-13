/* ==========================================================================
   tests/fight-lab.test.js — the rules behind Fight Lab's matchup research:
   style and late-round reads prefer this bout's division and fall back to
   career, recent form counts only fights that actually happened (newest
   first, five at most), and late-round output is never worded as fatigue.

   Run:  node tests/fight-lab.test.js
   ========================================================================== */

'use strict';
const fs = require('fs');
const path = require('path');
const FL = require('../fight-lab.js');

let passed = 0;
const failures = [];
function t(name, fn) {
  try { fn(); passed += 1; } catch (err) { failures.push(`${name}\n      ${err.message}`); }
}
function eq(a, b, what) {
  if (JSON.stringify(a) !== JSON.stringify(b)) {
    throw new Error(`${what || 'not equal'}: got ${JSON.stringify(a)}, want ${JSON.stringify(b)}`);
  }
}
function ok(c, what) { if (!c) throw new Error(what || 'expected truthy'); }

// ------------------------------------------------------------------ style

const STYLE_ROWS = [
  { fighter_id: 1, weight_class: 'CAREER',       style: 'grappler', sample_fights: 5, confidence: 'high' },
  { fighter_id: 1, weight_class: 'Middleweight', style: 'striker',  sample_fights: 5, confidence: 'high' },
  { fighter_id: 1, weight_class: 'Welterweight', style: 'hybrid',   sample_fights: 3, confidence: 'medium' },
  { fighter_id: 2, weight_class: 'CAREER',       style: 'striker',  sample_fights: 5, confidence: 'high' },
];

t('style reads the division of this bout first', () => {
  const r = FL.styleRead(STYLE_ROWS, 1, 'Middleweight');
  eq([r.key, r.scope, r.weightClass], ['striker', 'division', 'Middleweight']);
});

t('style falls back to career when the division has no row', () => {
  const r = FL.styleRead(STYLE_ROWS, 2, 'Lightweight');
  eq([r.key, r.scope], ['striker', 'career']);
});

t('a style read off a smaller sample says so', () => {
  ok(FL.styleRead(STYLE_ROWS, 1, 'Welterweight').thin, 'medium sample not flagged');
  ok(!FL.styleRead(STYLE_ROWS, 1, 'Middleweight').thin, 'high sample flagged');
});

t('no rows means no label, not a guess', () => {
  eq(FL.styleRead(STYLE_ROWS, 99, 'Lightweight'), null);
  eq(FL.styleRead([], 1, null), null);
});

t('hybrid is said in plain English', () => {
  eq(FL.STYLE.hybrid.label, 'Mixes both');
});

// ------------------------------------------------------------ recent form

const TODAY = '2026-10-13';
const EVENTS = [
  { id: 10, name: 'Old card',      event_date: '2024-01-01', is_upcoming: false },
  { id: 11, name: 'Mid card',      event_date: '2025-01-01', is_upcoming: false },
  { id: 12, name: 'Recent card',   event_date: '2026-05-01', is_upcoming: false },
  { id: 13, name: 'Today card',    event_date: '2026-10-13', is_upcoming: false },
  { id: 14, name: 'Next card',     event_date: '2026-10-17', is_upcoming: true  },
  { id: 15, name: 'Stale flag',    event_date: '2026-09-01', is_upcoming: true  },
  { id: 16, name: 'Earlier',       event_date: '2023-01-01', is_upcoming: false },
  { id: 17, name: 'Earliest',      event_date: '2022-01-01', is_upcoming: false },
  { id: 18, name: 'Way back',      event_date: '2021-01-01', is_upcoming: false },
];
const F = (id, ev, a, b, winner, method, extra) => Object.assign({
  id, event_id: ev, fighter_a_id: a, fighter_b_id: b,
  fighter_a_name: 'F' + a, fighter_b_name: 'F' + b, winner_id: winner, method,
  end_round: 3, end_time: '5:00', weight_class: 'Welterweight',
}, extra || {});
const FIGHTS = [
  F(100, 10, 1, 7, 1, 'KO/TKO'),
  F(101, 11, 8, 1, 8, 'Decision - Unanimous'),
  F(102, 12, 1, 9, null, 'Decision - Split'),           // a draw
  F(103, 13, 1, 6, null, null),                         // tonight: no result yet
  F(104, 14, 1, 2, null, null),                         // this bout, upcoming
  F(105, 15, 1, 5, 1, 'Submission'),                    // flagged upcoming: excluded
  F(106, 16, 1, 4, null, 'Overturned'),                 // a no contest
  F(107, 17, 3, 1, 1, 'Submission'),
  F(108, 18, 1, 3, 3, 'KO/TKO'),
  F(109, 11, 2, 9, 2, 'KO/TKO'),                        // someone else's fight
  F(110, 10, 1, 7, null, null),                         // past, never got a method (cancelled)
];

const form = FL.recentForm(FIGHTS, EVENTS, 1, TODAY, { excludeFightId: 104 });

t('recent form is newest first and five at most', () => {
  eq(form.map(r => r.fightId), [102, 101, 100, 106, 107]);
});

t('recent form never counts tonight, a booked fight, or a fight with no result', () => {
  const ids = form.map(r => r.fightId);
  [103, 104, 105, 110].forEach(id => ok(ids.indexOf(id) === -1, `fight ${id} counted as form`));
});

t('recent form names the opponent from either corner', () => {
  eq(form.find(r => r.fightId === 101).opponentName, 'F8');
  eq(form.find(r => r.fightId === 100).opponentName, 'F7');
  eq(form.find(r => r.fightId === 101).opponentId, 8);
});

t('results read W, L, D and NC', () => {
  const by = Object.fromEntries(form.map(r => [r.fightId, r.result]));
  eq([by[100], by[101], by[102], by[106], by[107]], ['W', 'L', 'D', 'NC', 'W']);
});

t('a debutant has an empty form list', () => {
  eq(FL.recentForm(FIGHTS, EVENTS, 42, TODAY), []);
});

t('methods are shortened, not invented', () => {
  eq(FL.shortMethod('Decision - Unanimous'), 'Decision (unanimous)');
  eq(FL.shortMethod("TKO - Doctor's Stoppage"), 'KO/TKO');
  eq(FL.shortMethod('Submission'), 'Submission');
  eq(FL.shortMethod(''), '');
});

// ------------------------------------------------------- late-round output

const LATE_ROWS = [
  { fighter_id: 1, weight_class: 'CAREER', recent_fights: 5, r3p_minutes: '25.0',
    consistency_score: '126.9', cardio_tier: 'tireless', confidence_tier: 'high', r1_sig_str_per_min: '12.5' },
  { fighter_id: 1, weight_class: 'Bantamweight', recent_fights: 1, r3p_minutes: '5.0',
    consistency_score: null, cardio_tier: null, confidence_tier: 'limited', r1_sig_str_per_min: '5.8' },
  { fighter_id: 2, weight_class: 'Welterweight', recent_fights: 3, r3p_minutes: '12.4',
    consistency_score: '72.0', cardio_tier: 'tapers', confidence_tier: 'limited', r1_sig_str_per_min: '3.1' },
];

t('a division row with no score falls back to career', () => {
  const r = FL.lateRoundRead(LATE_ROWS, 1, 'Bantamweight');
  eq([r.scope, r.keptPct, r.fights, r.lateMinutes], ['career', 127, 5, 25]);
  ok(!r.thin, 'a high-sample read flagged thin');
});

t('a thin late-round read says so, with how much fighting it rests on', () => {
  const r = FL.lateRoundRead(LATE_ROWS, 2, 'Welterweight');
  eq([r.scope, r.thin, r.fights, r.lateMinutes], ['division', true, 3, 12.4]);
  ok(r.lowPace, 'a 3.1 a minute round-one pace not flagged as low');
});

t('no late-round data means no read', () => {
  eq(FL.lateRoundRead(LATE_ROWS, 3, 'Welterweight'), null);
});

t('late-round output is never worded as fatigue or cardio', () => {
  const words = /cardio|fatigu|tired(?!ness)|gas(?:sed| tank)|tireless|collapse|stamina/i;
  Object.values(FL.LATE).forEach(v => {
    ok(!words.test(v.label), `label "${v.label}" reads as a fatigue claim`);
    ok(!words.test(v.line), `line "${v.line}" reads as a fatigue claim`);
  });
  ok(/not tiredness/i.test(FL.LATE_ROUND_NOTE), 'the note no longer says output is not tiredness');
  ok(/nothing useful about who wins/i.test(FL.LATE_ROUND_NOTE), 'the note no longer says it does not pick winners');
});

t('every tier the view can emit has a plain-English label', () => {
  ['tireless', 'steady', 'tapers', 'fades', 'collapses'].forEach(k => ok(FL.LATE[k], `no label for ${k}`));
});

// ------------------------------------------------------- the page itself

const PAGE = fs.readFileSync(path.join(__dirname, '..', 'fight.html'), 'utf8');

t('Fight Lab loads fight-lab.js', () => {
  ok(/<script src="fight-lab\.js\?v=\d+"><\/script>/.test(PAGE), 'fight.html does not load fight-lab.js');
});

t('Fight Lab answers who, then how they compare, then the market', () => {
  const at = id => PAGE.indexOf('id="' + id + '"');
  const order = ['secWho', 'secCompare', 'secStats', 'secLate', 'secForm', 'secMarket', 'secChart', 'secBooks'];
  order.forEach(id => ok(at(id) > 0, `fight.html lost section ${id}`));
  for (let i = 1; i < order.length; i++) {
    ok(at(order[i - 1]) < at(order[i]), `${order[i - 1]} no longer comes before ${order[i]}`);
  }
});

t('the late-round panel shows its sample and its caveat', () => {
  ok(/Sample: /.test(PAGE), 'no sample label on the late-round cards');
  ok(/reached round 3/.test(PAGE), 'no count of fights that reached round three');
  ok(/LATE_ROUND_NOTE/.test(PAGE), 'the late-round caveat is not rendered');
});

// -------------------------------------------------------------- report
if (failures.length) {
  console.error(`fight-lab: ${failures.length} failed, ${passed} passed`);
  failures.forEach(f => console.error('  ✗ ' + f));
  process.exit(1);
}
console.log(`fight-lab: ${passed} passed`);
