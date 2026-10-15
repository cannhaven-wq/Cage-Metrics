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


// ------------------------------------------------------------ sprint 2

// The same three fights as fight rows with per-fight totals, for careerWindow.
const withTotals = fights.map(f => Object.assign({}, f, f.id === 3 ? { a_sig_str_attempted: null } : {
  a_sig_str_landed: f.id === 1 ? 2 : 30, a_sig_str_attempted: f.id === 1 ? 10 : 90,
  b_sig_str_landed: f.id === 1 ? 10 : 36, b_sig_str_attempted: f.id === 1 ? 20 : 72,
  a_head_landed: f.id === 1 ? 1 : 20, b_head_landed: f.id === 1 ? 6 : 10,
  a_body_landed: 0, b_body_landed: f.id === 1 ? 4 : 10, a_leg_landed: f.id === 1 ? 1 : 10, b_leg_landed: f.id === 1 ? 0 : 16,
  a_td_landed: 1, a_td_attempted: 6, b_td_landed: 1, b_td_attempted: 2,
}));
const compT = FL.completedFights(withTotals, events, ME, '2026-10-15');

t('all-UFC rates are rebuilt from fight rows, from the fighter’s own side, and a row without totals is named', () => {
  const cw = W.careerWindow(compT, ME);
  eq(cw.fights, 2); eq(cw.skipped.length, 1); eq(cw.skipped[0].reason, 'no fight totals');
  near(cw.rates.slpm, (10 + 30) / 17.5, 'fight 1 is read from corner B');
  near(cw.rates.sapm, (2 + 36) / 17.5);
  eq(cw.last, '2026-06-01'); eq(cw.first, '2026-03-01');
});

t('strike mix is shares of what landed', () => {
  const mix = W.strikeMix(W.careerWindow(compT, ME).totals);
  eq(mix.landed, 40);
  near(mix.target.head, 26 / 40 * 100); near(mix.target.body, 4 / 40 * 100); near(mix.target.leg, 10 / 40 * 100);
  eq(W.strikeMix(null), null);
});

t('round by round counts a final round only for the minutes it lasted', () => {
  const rr = W.roundByRound(comp, rounds, ME);
  eq(rr[0].round, 1); eq(rr[0].fights, 2);
  near(rr[0].minutes, 2.5 + 5); near(rr[0].landedPm, 20 / 7.5);
  eq(rr[2].fights, 1); near(rr[2].minutes, 5);
});

t('methods split wins and losses by how they ended', () => {
  const m = W.methods(comp, ME);
  eq(m.win.ko, 1); eq(m.win.sub, 1); eq(m.loss.dec, 1); eq(m.win.total, 2); eq(m.loss.total, 1);
});

t('an opponent’s record is counted only from fights before the one described', () => {
  const opp = [{ f: { id: 9, winner_id: OPP1, method: 'KO/TKO' }, e: { event_date: '2025-01-01' } },
               { f: { id: 8, winner_id: 99, method: 'KO/TKO' }, e: { event_date: '2026-09-01' } }];
  const rec = W.recordBefore(opp, OPP1, '2026-06-01');
  eq(rec.w, 1); eq(rec.l, 0, 'a later loss must not count');
  const rows = W.opposition([{ opponentId: OPP1, date: '2026-06-01' }, { opponentId: OPP2, date: '2026-03-01' }], { [OPP1]: opp, [OPP2]: [] });
  eq(rows[0].oppRecord.w, 1); eq(rows[1].oppDebut, true);
});

t('division rank keeps men and women apart by who actually fought whom', () => {
  const bout = (a, b, id) => ({ id, fighter_a_id: a, fighter_b_id: b, end_round: 3, end_time: '5:00',
    a_sig_str_landed: a, a_sig_str_attempted: 100, b_sig_str_landed: b, b_sig_str_attempted: 100 });
  const pool = [];
  for (let i = 0; i < 12; i++) pool.push(bout(100 + i, 100 + ((i + 1) % 12), i));        // one group
  for (let i = 0; i < 12; i++) pool.push(bout(200 + i, 200 + ((i + 1) % 12), 50 + i));   // a separate group
  const base = W.divisionBaseline(pool, [100]);
  eq(base.fighters, 12, 'only the anchor’s group is in the pool');
  const all = W.divisionBaseline(pool, null);
  eq(all.fighters, 24);
  eq(W.percentile(base.slpm, 1e9), 100); eq(W.percentile(base.slpm, -1), 0);
  eq(W.percentile([1, 2, 3], 2), null, 'under ten fighters is no rank at all');
});

t('the weight limit is the division’s, and catch weight has none', () => {
  eq(W.weightLimit('Welterweight'), 170); eq(W.weightLimit('Strawweight'), 115); eq(W.weightLimit('Catch Weight'), null);
});

t('key points come in three labelled kinds and never name a winner', () => {
  const x = (last, o) => Object.assign({ name: last, last, age: 30, reach: 72, height: 70, stance: 'Orthodox', debut: false,
    career: { fights: 8, rates: { slpm: 5, sapm: 3, td_avg: 2.5, td_def: 60, str_def: 55 } }, recent: null,
    facts: { streak: { kind: 'W', count: 4 }, daysSinceLast: 400 }, methods: { win: { ko: 5, sub: 0, dec: 1, other: 0, total: 6 }, loss: { ko: 2, sub: 0, dec: 0, other: 0, total: 2 } },
    pct: { slpm: 92, str_def: 50, td_avg: 85, td_def: 10, sapm: 50 }, style: { key: 'grappler' }, late: { tier: 'steady', score: 104 } }, o);
  const A = x('Alpha'), B = x('Bravo', { reach: 76, age: 35, stance: 'Southpaw', style: { key: 'striker' }, late: { tier: 'fades', score: 70 }, debut: true });
  const pts = W.keyPoints(A, B, { fight: { is_title_fight: true }, changes: [{ fighterName: 'Bravo', formerOpponent: 'Charlie' }], divisionLabel: 'welterweights' });
  ['fact', 'calc', 'read'].forEach(k => ok(pts.some(p => p.kind === k), 'no ' + k + ' point'));
  ok(pts.every(p => W.KIND_LABEL[p.kind]), 'every point has a label');
  ok(pts.some(p => /Opponent change/.test(p.text)) && pts.some(p => /debut/.test(p.text)), 'context facts missing');
  ok(pts.some(p => /higher than about 92%/.test(p.text)), 'percentile not stated as a plain share');
  pts.forEach(p => {
    ok(!/\b(will win|should win|favou?red to|edge|advantage in this fight|lock|pick|bet on)\b/i.test(p.text), 'key point reads as a pick: ' + p.text);
    ok(!/\b(he|she|his|her|him)\b/i.test(p.text), 'key point assumes a pronoun: ' + p.text);
  });
  ok(pts.filter(p => p.kind === 'read').every(p => /\?/.test(p.text) || /If it goes/.test(p.text)), 'an interpretation must be framed as a question');
});

t('Fight Lab loads the card rules before the workspace and shows fight context', () => {
  const i = s => PAGE.indexOf(s);
  ok(i('<script src="card-research.js?v=') > 0 && i('<script src="card-research.js?v=') < i('<script src="fight-workspace.js?v='), 'card-research.js must load first');
  ok(PAGE.indexOf('id="secContext"') > 0 && PAGE.indexOf('id="secContext"') < PAGE.indexOf('id="secCompare"'), 'fight context missing or misplaced');
  ok(/Not covered yet/.test(read('fight-workspace-ui.js')), 'the context must say what CFL does not cover');
  ok(/\bdob\b/.test(PAGE) && /ageOn\(/.test(PAGE), 'Fight Lab does not compute age from the date of birth');
});

if (failures.length) {
  console.error('fight-workspace: ' + failures.length + ' failed, ' + passed + ' passed');
  failures.forEach(f => console.error('  ✗ ' + f));
  process.exit(1);
}
console.log('fight-workspace: ' + passed + ' passed');
