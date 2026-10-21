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
  eq([r.scope, r.score, r.fights, r.lateMinutes], ['career', 127, 5, 25]);
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
  ok(/not a measurement of tiredness/i.test(FL.LATE_ROUND_NOTE), 'the note no longer says the score is not tiredness');
  ok(/nothing useful about who wins/i.test(FL.LATE_ROUND_NOTE), 'the note no longer says it does not pick winners');
});

t('every tier the view can emit has a plain-English label', () => {
  ['tireless', 'steady', 'tapers', 'fades', 'collapses'].forEach(k => ok(FL.LATE[k], `no label for ${k}`));
});

// ------------------------------------------------------- the page itself

const PAGE = fs.readFileSync(path.join(__dirname, '..', 'fight.html'), 'utf8');

// ------------------------------------------- retired and cancelled bookings
// A booking retired under D-024 has is_active = false. None carries a method
// today, but the rule must not depend on that: a method written to a retired
// row must still never make it "completed".

const EV2 = [
  { id: 1, name: 'Past A', event_date: '2026-01-10', is_upcoming: false },
  { id: 2, name: 'Past B', event_date: '2026-03-10', is_upcoming: false },
  { id: 3, name: 'Past C', event_date: '2026-05-10', is_upcoming: false },
  { id: 4, name: 'Mis-flagged', event_date: '2026-06-10', is_upcoming: true },
  { id: 5, name: 'Future', event_date: '2026-11-10', is_upcoming: false },
];
const G = (id, ev, winner, method, extra) => Object.assign({
  id, event_id: ev, fighter_a_id: 1, fighter_b_id: 50 + id,
  fighter_a_name: 'Me', fighter_b_name: 'Opp' + id, winner_id: winner, method,
}, extra || {});
const BOOKINGS = [
  G(1, 1, 1, 'KO/TKO'),                                           // real win
  G(2, 2, 52, 'Submission'),                                      // real loss
  G(3, 3, 1, 'Decision - Unanimous', { is_active: false }),       // retired, method populated
  G(4, 3, 54, 'KO/TKO',              { is_active: false }),       // retired, loss populated
  G(5, 4, 1, 'Submission'),                                       // event still flagged upcoming
  G(6, 5, 1, 'KO/TKO'),                                           // future date, method populated
  G(7, 2, null, '   '),                                           // blank method
  G(8, 1, null, null),                                            // never fought
  G(9, 3, null, 'Overturned', { is_active: true }),               // real no contest
];

t('a retired booking never counts as a completed fight, even with a method', () => {
  const ids = FL.recentForm(BOOKINGS, EV2, 1, TODAY).map(r => r.fightId);
  [3, 4].forEach(id => ok(ids.indexOf(id) === -1, `retired booking ${id} listed as form`));
});

t('upcoming, future-dated, blank-method and unfought bookings never count', () => {
  const ids = FL.recentForm(BOOKINGS, EV2, 1, TODAY).map(r => r.fightId);
  [5, 6, 7, 8].forEach(id => ok(ids.indexOf(id) === -1, `booking ${id} listed as form`));
  eq(ids, [9, 2, 1]);
});

t('isCompleted needs an active booking, a past card and a method', () => {
  const past = EV2[0];
  ok(FL.isCompleted(G(1, 1, 1, 'KO/TKO'), past, TODAY), 'a real fight rejected');
  ok(!FL.isCompleted(G(1, 1, 1, 'KO/TKO', { is_active: false }), past, TODAY), 'retired accepted');
  ok(!FL.isCompleted(G(1, 1, 1, 'KO/TKO'), null, TODAY), 'a fight with no event accepted');
  ok(FL.isCompleted(G(1, 1, 1, 'KO/TKO', { is_active: null }), past, TODAY), 'a NULL is_active must not hide a real fight');
});

// ----------------------------------------------- UFC record vs fight history
// 2026-10-13, Louie Sutherland: fighters.ufc_wins/ufc_losses read 0-2 while
// fights held four completed UFC bouts (1-3). The page printed both.

const SUTHERLAND = { id: 1, wins: 11, losses: 6, draws: 0, ufc_wins: 0, ufc_losses: 2, ufc_draws: 0 };

t('the UFC record is counted from completed fights, not fighters totals', () => {
  const rec = FL.ufcRecord(BOOKINGS, EV2, 1, TODAY);
  eq(rec, { w: 1, l: 1, d: 0, nc: 1, total: 3 });
  eq(FL.formatUfcRecord(rec), '1-1 (1 NC)');
});

t('stale fighter totals cannot reach the record (regression: 0-2 vs 1-3)', () => {
  const ev = [
    { id: 10, name: 'a', event_date: '2025-10-25', is_upcoming: false },
    { id: 11, name: 'b', event_date: '2026-03-21', is_upcoming: false },
    { id: 12, name: 'c', event_date: '2026-05-02', is_upcoming: false },
    { id: 13, name: 'd', event_date: '2026-08-08', is_upcoming: false },
  ];
  const f = [
    { id: 322, event_id: 10, fighter_a_id: 275, fighter_b_id: 1, winner_id: 275, method: 'Submission' },
    { id: 142, event_id: 11, fighter_a_id: 1, fighter_b_id: 3673, winner_id: 3673, method: 'KO/TKO' },
    { id: 5,   event_id: 12, fighter_a_id: 4548, fighter_b_id: 1, winner_id: 1, method: 'Decision - Unanimous' },
    { id: 45887, event_id: 13, fighter_a_id: 1, fighter_b_id: 428, winner_id: 428, method: 'Submission' },
  ];
  const rec = FL.ufcRecord(f, ev, 1, TODAY);
  eq(FL.formatUfcRecord(rec), '1-3');
  const form = FL.recentForm(f, ev, 1, TODAY);
  eq(form.filter(r => r.result === 'W').length, rec.w, 'record wins differ from listed wins');
  eq(form.filter(r => r.result === 'L').length, rec.l, 'record losses differ from listed losses');
  ok(FL.formatUfcRecord(rec) !== SUTHERLAND.ufc_wins + '-' + SUTHERLAND.ufc_losses, 'stale total reproduced');
});

t('a fighter with no completed fights reads "No UFC fights", never a stale total', () => {
  eq(FL.formatUfcRecord(FL.ufcRecord(BOOKINGS, EV2, 999, TODAY)), 'No UFC fights');
});

t('a pro record smaller than the UFC record is flagged as out of date', () => {
  ok(FL.proRecordIsBehind({ wins: 0, losses: 5 }, { w: 1, l: 1 }), 'stale pro wins not flagged');
  ok(!FL.proRecordIsBehind({ wins: 11, losses: 6 }, { w: 1, l: 3 }), 'a normal pro record flagged');
});

t('Fight Lab never prints fighters.ufc_wins as the UFC record', () => {
  const fn = PAGE.slice(PAGE.indexOf('function ufcRec('), PAGE.indexOf('function recOf('));
  ok(fn.length > 0, 'ufcRec not found in fight.html');
  ok(!/ufc_wins|ufc_losses/.test(fn), 'ufcRec reads the fighters totals again');
  ok(/formatUfcRecord/.test(fn), 'ufcRec no longer formats the counted record');
  ok(/is_active/.test(PAGE.slice(PAGE.indexOf('async function loadForm'), PAGE.indexOf('function localToday'))),
    'loadForm no longer reads is_active, so retired bookings cannot be excluded');
});

// ------------------------------- late-round copy matches the SQL it explains

const SQL = fs.readFileSync(path.join(__dirname, '..', 'v_fighter_consistency.sql'), 'utf8');

t('"solid" is defined by the same thresholds the view uses', () => {
  const conf = SQL.slice(SQL.indexOf('AS consistency_score'), SQL.indexOf('AS confidence_tier'));
  ok(new RegExp('r1_minutes < ' + FL.SOLID_R1_MINUTES + '\\b').test(conf), 'round-one minutes threshold drifted from the SQL');
  ok(new RegExp('r3p_minutes >= ' + FL.SOLID_LATE_MINUTES + '\\b').test(conf), 'late-minutes threshold drifted from the SQL');
  ok(FL.SOLID_SAMPLE_NOTE.indexOf(String(FL.SOLID_LATE_MINUTES)) > -1 &&
     FL.SOLID_SAMPLE_NOTE.indexOf(String(FL.SOLID_R1_MINUTES)) > -1, 'the sample note no longer states both thresholds');
});

t('the score caps and the minimum late minutes match the view', () => {
  ok(new RegExp('ELSE\\s+' + (FL.SCORE_CAP_MIN / 100).toFixed(2)).test(SQL), 'lowest cap drifted from the SQL');
  ok(new RegExp('THEN ' + (FL.SCORE_CAP_MAX / 100).toFixed(1) + '\\b').test(SQL), 'highest cap drifted from the SQL');
  ok(new RegExp('r3p_minutes >= ' + FL.MIN_LATE_MINUTES + '\\b').test(SQL), 'minimum late minutes drifted from the SQL');
});

t('the score is explained as a weighted, capped blend and never shown as a percentage', () => {
  ok(/weighted/i.test(FL.LATE_ROUND_NOTE) && /capped/i.test(FL.LATE_ROUND_NOTE), 'the note no longer says weighted and capped');
  ok(!/%/.test(FL.LATE_ROUND_NOTE), 'the note prints a percentage');
  const late = PAGE.slice(PAGE.indexOf('function renderLate'), PAGE.indexOf('function renderForm'));
  ok(!/r\.score \+ '%/.test(late) && !/keptPct/.test(late), 'the late-round card prints the score as a percentage');
});

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
// ------------------------------------------------------------- discipline
// T-102 (owner, 2026-10-16): pages show the discipline the UFC lists, copied
// from UFC.com into fighters.fighting_style — never the calculated label.
t('discipline is the UFC.com value as stored', () => {
  const r = FL.disciplineRead({ fighting_style: 'Kickboxer', fighting_style_src: 'ufc.com' });
  eq(r.label, 'Kickboxer'); eq(r.source, 'ufc.com');
  eq(FL.disciplineRead({ fighting_style: ' Wrestling ', fighting_style_src: 'manual' }).source, 'manual');
});
t('no discipline, or a generic one, shows nothing — never a calculated stand-in', () => {
  [null, '', 'MMA', 'Mixed Martial Arts', 'Freestyle', 'N/A'].forEach(v => eq(FL.disciplineRead({ fighting_style: v }), null));
  eq(FL.disciplineRead(null), null);
});
t('no page renders the calculated style any more', () => {
  const fs = require('fs'), path = require('path');
  ['fight.html', 'fighter.html', 'index.html'].forEach(f => {
    const src = fs.readFileSync(path.join(__dirname, '..', f), 'utf8');
    ok(!/FL\.styleRead\(|from\('v_fighter_style'\)/.test(src), f + ' still reads the calculated style');
  });
});
t('no page copy still describes the retired calculated style (D-030)', () => {
  // The calculated label was replaced by the UFC-listed discipline on
  // 2026-10-16, but fight.html kept explaining the old round-one calculation
  // under the new pill until 2026-10-21 — the page said the style was "read
  // from what they actually did" while showing UFC.com's listing.
  const fs = require('fs'), path = require('path');
  const stale = /Style compares what a fighter does in round one|Style is read from what they actually did|"Mixes both" means|Three labels is deliberately/;
  ['fight.html', 'fighter.html', 'index.html', 'event.html'].forEach(f => {
    const src = fs.readFileSync(path.join(__dirname, '..', f), 'utf8');
    ok(!stale.test(src), f + ' still explains the retired calculated style');
  });
  const page = fs.readFileSync(path.join(__dirname, '..', 'fight.html'), 'utf8');
  ok(/UFC\.com athlete page/.test(page), 'fight.html no longer names where the fighting style comes from');
});

if (failures.length) {
  console.error(`fight-lab: ${failures.length} failed, ${passed} passed`);
  failures.forEach(f => console.error('  ✗ ' + f));
  process.exit(1);
}
console.log(`fight-lab: ${passed} passed`);
