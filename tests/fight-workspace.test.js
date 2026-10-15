/* ==========================================================================
   tests/fight-workspace.test.js — Fight Lab's research workspace.

   What it holds:
     - recent rates are computed from round rows, oriented by the row itself,
       and a fight without round data or a recorded length is left out and
       named, never filled in;
     - every "does it predict winners" answer comes from factor-rates.json, and
       a metric that names a factor names one that exists;
     - the sheet is the visitor's: no tally, no ranking, no pick, stored only in
       the browser;
     - fight.html wires it in without moving the existing sections.

   Run:  node tests/fight-workspace.test.js
   ========================================================================== */
'use strict';
const fs = require('fs');
const path = require('path');
const W = require('../fight-workspace.js');
const FL = require('../fight-lab.js');

const read = f => fs.readFileSync(path.join(__dirname, '..', f), 'utf8');
const RATES = JSON.parse(read('factor-rates.json'));

let passed = 0;
const failures = [];
function t(name, fn) { try { fn(); passed += 1; } catch (e) { failures.push(name + '\n      ' + e.message); } }
function ok(c, what) { if (!c) throw new Error(what || 'expected truthy'); }
function eq(a, b, what) { if (a !== b) throw new Error((what || 'value') + ': expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a)); }
function near(a, b, what) { if (a == null || Math.abs(a - b) > 1e-9) throw new Error((what || 'value') + ': expected ' + b + ', got ' + a); }

// ------------------------------------------------------------ fight length

t('a fight clock reads as minutes; anything else is unknown, not zero', () => {
  near(W.clockMinutes('4:42'), 4.7, '4:42');
  eq(W.clockMinutes('5:00'), 5);
  eq(W.clockMinutes(''), null);
  eq(W.clockMinutes('0:00'), null);
  eq(W.clockMinutes('7:00'), null, 'a round is five minutes');
});

t('fight length is full rounds plus the clock the last one ended on', () => {
  near(W.fightMinutes({ end_round: 3, end_time: '2:17' }), 12 + 17 / 60);
  eq(W.fightMinutes({ end_round: 3, end_time: '5:00' }), 15);
  eq(W.fightMinutes({ end_round: null, end_time: '5:00' }), null);
  eq(W.fightMinutes({ end_round: 2, end_time: null }), null);
});

// ------------------------------------------------------------ recent window

const ME = 10, OPP1 = 20, OPP2 = 30, OPP3 = 40;
const ev = (id, d) => ({ id, event_date: d, name: 'Card ' + id, is_upcoming: false });
const fights = [
  // ME in corner B: the round rows must be read from B's side.
  { id: 1, event_id: 101, fighter_a_id: OPP1, fighter_b_id: ME, fighter_a_name: 'One', winner_id: ME, method: 'KO/TKO', end_round: 1, end_time: '2:30' },
  { id: 2, event_id: 102, fighter_a_id: ME, fighter_b_id: OPP2, fighter_b_name: 'Two', winner_id: OPP2, method: 'Decision - Unanimous', end_round: 3, end_time: '5:00' },
  // No round rows at all: must be skipped and named.
  { id: 3, event_id: 103, fighter_a_id: ME, fighter_b_id: OPP3, fighter_b_name: 'Three', winner_id: ME, method: 'Submission', end_round: 2, end_time: '1:00' },
];
const events = [ev(101, '2026-06-01'), ev(102, '2026-03-01'), ev(103, '2025-12-01')];
const round = (fid, n, a, b, x) => Object.assign({
  fight_id: fid, round_number: n, fighter_a_id: a, fighter_b_id: b,
  a_sig_str_landed: 0, a_sig_str_attempted: 0, b_sig_str_landed: 0, b_sig_str_attempted: 0,
  a_td_landed: 0, a_td_attempted: 0, b_td_landed: 0, b_td_attempted: 0,
  a_ctrl_seconds: 0, b_ctrl_seconds: 0, a_kd: 0, b_kd: 0, a_sub_attempts: 0, b_sub_attempts: 0,
}, x);
const rounds = {
  1: [round(1, 1, OPP1, ME, { b_sig_str_landed: 10, b_sig_str_attempted: 20, a_sig_str_landed: 2, a_sig_str_attempted: 10, b_kd: 1 })],
  2: [1, 2, 3].map(n => round(2, n, ME, OPP2, {
    a_sig_str_landed: 10, a_sig_str_attempted: 30, b_sig_str_landed: 12, b_sig_str_attempted: 24,
    a_td_landed: n === 1 ? 1 : 0, a_td_attempted: 2, b_td_attempted: n === 3 ? 2 : 0, b_td_landed: n === 3 ? 1 : 0,
    a_ctrl_seconds: 60,
  })),
};
const comp = FL.completedFights(fights, events, ME, '2026-10-15');
const rw = W.recentWindow(comp, rounds, ME);

t('the window is the last five completed fights, and a fight with no rounds is named, not filled', () => {
  eq(rw.window, 3);
  eq(rw.used.length, 2);
  eq(rw.skipped.length, 1);
  eq(rw.skipped[0].fightId, 3);
  eq(rw.skipped[0].reason, 'no round data');
});

t('rates read each round from the fighter’s own side and match the career units', () => {
  near(rw.minutes, 2.5 + 15, 'minutes');
  const r = rw.rates;
  near(r.slpm, 40 / 17.5, 'landed a minute');                // 10 + 30
  near(r.str_acc, 40 / 110 * 100, 'accuracy');               // 20 + 90 attempted
  near(r.sapm, 38 / 17.5, 'absorbed a minute');              // 2 + 36
  near(r.str_def, (1 - 38 / 82) * 100, 'defence');           // 10 + 72 thrown at
  near(r.td_avg, 1 / 17.5 * 15, 'takedowns per 15');
  near(r.td_acc, 1 / 6 * 100, 'takedown accuracy');
  near(r.td_def, 50, 'takedown defence');
  near(r.ctrl15, 3 / 17.5 * 15, 'control minutes per 15');
  near(r.kd15, 1 / 17.5 * 15, 'knockdowns per 15');
});

t('a rate with nothing to divide by is missing, not zero', () => {
  const r = W.rates({ sigL: 0, sigA: 0, oppSigL: 0, oppSigA: 0, tdL: 0, tdA: 0, oppTdL: 0, oppTdA: 0, ctrl: 0, kd: 0, sub: 0 }, 10);
  eq(r.str_acc, null); eq(r.td_def, null); eq(r.td_acc, null);
  eq(W.rates({}, 0), null);
});

t('record facts come from the same completed list the page shows', () => {
  const f = W.formFacts(comp, ME, '2026-10-15');
  eq(f.ufcFights, 3); eq(f.ufcWins, 2); eq(f.ufcLosses, 1);
  eq(f.finishWins, 2); eq(f.streak.kind, 'W'); eq(f.streak.count, 1);
  eq(f.daysSinceLast, W.daysBetween('2026-06-01', '2026-10-15'));
  eq(f.last5Distance, 1);
});

// ------------------------------------------------------------ evidence

t('every factor a metric cites exists in factor-rates.json', () => {
  const cited = [];
  Object.values(W.METRICS).forEach(list => list.forEach(m => { if (m.factor) cited.push(m.factor); }));
  const ui = read('fight-workspace-ui.js');
  (ui.match(/evidence\(C\.factorRates, '([a-z_]+)'\)/g) || []).forEach(s => cited.push(s.match(/'([a-z_]+)'/)[1]));
  ok(cited.length >= 6, 'expected the explorer to cite the Factor Lab');
  cited.forEach(id => ok(W.evidence(RATES, id), id + ' is cited but not in factor-rates.json'));
});

t('evidence quotes the artifact, sample and range included', () => {
  const e = W.evidence(RATES, 'strike_volume');
  const f = RATES.factors.find(x => x.id === 'strike_volume');
  const h = f.buckets.find(b => b.headline);
  eq(e.verdict, h.verdict);
  ok(e.line.indexOf(h.even.n.toLocaleString('en-US')) >= 0, 'sample size missing');
  ok(e.line.indexOf(String(Math.round(h.even.ci_lo))) >= 0, 'range missing');
  eq(W.evidence(RATES, 'not_a_factor'), null, 'an untested factor must not borrow a result');
});

t('an untested metric says it is untested, and a difference is never called evidence', () => {
  ok(/not tested/i.test(W.NOT_TESTED) && /not evidence/i.test(W.NOT_TESTED));
  ok(/does not tell you how this fight goes/i.test(W.ONE_FIGHT));
});

t('a percentage gap is in points', () => {
  const m = W.METRICS.striking.find(x => x.key === 'str_acc');
  eq(W.line(m, 48, 36).gapText, '12 pts');
});

t('bars use a fixed scale per metric, not the larger of the pair', () => {
  Object.values(W.METRICS).forEach(list => list.forEach(m => ok(m.max > 0, m.key + ' has no fixed scale')));
});

// ------------------------------------------------------------ the sheet

t('an unreadable or foreign sheet is an empty sheet, never an exception', () => {
  eq(W.parseSheet('not json', 5).items.length, 0);
  eq(W.parseSheet(JSON.stringify({ v: 1, fightId: '6', items: [] }), 5).items.length, 0);
  eq(W.parseSheet(JSON.stringify({ v: 99, fightId: '5', items: [{ id: 'x', label: 'y' }] }), 5).items.length, 0);
  eq(W.parseSheet(JSON.stringify({ v: 1, fightId: '5', items: [{ id: 'x', label: 'y' }, null, { id: 3 }] }), 5).items.length, 1);
});

t('add, move and remove keep the visitor’s order and do not duplicate', () => {
  const s = W.emptySheet(5);
  W.addItem(s, { id: 'a', label: 'A' }); W.addItem(s, { id: 'b', label: 'B' }); W.addItem(s, { id: 'a', label: 'A again' });
  eq(s.items.length, 2);
  W.moveItem(s, 'b', -1); eq(s.items[0].id, 'b');
  W.removeItem(s, 'b'); eq(s.items.length, 1);
});

t('the summary is grouped by the visitor’s importance and carries no tally or verdict', () => {
  const s = W.emptySheet(5);
  W.addItem(s, { id: 'm:slpm', label: 'Strikes landed', a: '4.1', b: '3.2', imp: 'minor' });
  W.addItem(s, { id: 'm:age', label: 'Age', a: '32', b: '34', imp: 'key', note: 'matters to me' });
  s.notes = 'my own words';
  const txt = W.summaryText(s, { title: 'X vs Y', nameA: 'X', nameB: 'Y' });
  ok(txt.indexOf('KEY TO MY READ') < txt.indexOf('MINOR'), 'importance order lost');
  ok(/My note: matters to me/.test(txt) && /my own words/.test(txt), 'visitor notes missing');
  ok(/publishes no pick/.test(txt), 'the summary lost its no-pick statement');
  ok(!/\b(advantage|edge|favou?red|winner|leads? in|score:|total|\d+ of \d+ categories)\b/i.test(txt.replace(W.SUMMARY_FOOTER, '')),
    'the summary adds rows up or names a side');
});

// ------------------------------------------------------------ the copy

const BANNED = [/\bbest bet\b/i, /\bvalue (?:bet|edge)\b/i, /\bbetting edge\b/i, /\bour model\b/i,
  /\bmodels? picks?\b/i, /\b(High|Medium|Low) confidence\b/i, /\bwe like\b/i, /\block of\b/i,
  /\bshould (?:bet|back|take)\b/i, /\bwin probability\b/i];
['fight-workspace.js', 'fight-workspace-ui.js'].forEach(f => {
  t(f + ' publishes no pick, tier or tout language', () => {
    const src = read(f).replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/^\s*\/\/.*$/gm, ' ');
    BANNED.forEach(re => { const m = src.match(re); ok(!m, f + ' contains "' + (m && m[0]) + '"'); });
  });
  t(f + ' writes nothing to the database', () => {
    const src = read(f);
    ok(!/\.from\(|\.insert\(|\.upsert\(|\.rpc\(|fetch\(/.test(src), f + ' talks to the network');
  });
});

t('the sheet lives in localStorage only', () => {
  const ui = read('fight-workspace-ui.js');
  ok(/localStorage\.setItem\(W\.sheetKey/.test(ui), 'sheet is not saved to localStorage');
  ok(/try \{[^}]*localStorage/.test(ui), 'localStorage access must be guarded');
});

// ------------------------------------------------------------ the page

const PAGE = read('fight.html');
t('fight.html loads the workspace after fight-lab.js, rules before UI', () => {
  const i = s => PAGE.indexOf(s);
  ok(i('<script src="fight-lab.js') > 0 && i('<script src="fight-lab.js') < i('<script src="fight-workspace.js?v='), 'order: fight-lab, workspace');
  ok(i('<script src="fight-workspace.js?v=') < i('<script src="fight-workspace-ui.js?v='), 'order: workspace, ui');
});

t('the explorer sits inside "How do they compare?" before the tale of the tape, and the sheet has a home', () => {
  const at = id => PAGE.indexOf('id="' + id + '"');
  ok(at('secCompare') < at('secExplore') && at('secExplore') < at('secStats'), 'explorer misplaced');
  ok(at('secSheet') > at('secBooks'), 'sheet section missing or misplaced');
  ok(/'secSheet'\]\.forEach/.test(PAGE), 'a failed load must hide the sheet too');
});

t('round data is read through the public table with the columns the rates need', () => {
  ok(/from\('fight_rounds'\)/.test(PAGE), 'fight.html does not read fight_rounds');
  ['a_sig_str_attempted', 'b_td_attempted', 'a_ctrl_seconds', 'b_kd'].forEach(c =>
    ok(PAGE.indexOf(c) > 0, 'fight_rounds read is missing ' + c));
});

if (failures.length) {
  console.error('fight-workspace: ' + failures.length + ' failed, ' + passed + ' passed');
  failures.forEach(f => console.error('  ✗ ' + f));
  process.exit(1);
}
console.log('fight-workspace: ' + passed + ' passed');
