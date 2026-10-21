/* ==========================================================================
   tests/fight-overview.test.js — Fight Lab's matchup overview.

   Holds the three rules at the top of fight-overview.js: a tendency is a
   measurement and never a training background; there are no tendencies from
   a thin sample; nothing picks a side. Plus where the overview sits on the
   page and that it reuses the existing rate builders.

   Run:  node tests/fight-overview.test.js
   ========================================================================== */
'use strict';
const fs = require('fs');
const path = require('path');
const O = require('../fight-overview.js');
const W = require('../fight-workspace.js');
const FL = require('../fight-lab.js');

const read = f => fs.readFileSync(path.join(__dirname, '..', f), 'utf8');
let passed = 0;
const failures = [];
function t(name, fn) { try { fn(); passed += 1; } catch (err) { failures.push(name + '\n      ' + err.message); } }
function ok(c, what) { if (!c) throw new Error(what || 'expected truthy'); }
function eq(a, b, what) { if (a !== b) throw new Error((what || 'not equal') + ': ' + JSON.stringify(a) + ' !== ' + JSON.stringify(b)); }

// ---- fixtures: fight rows shaped like `fights` --------------------------------
const ME = 1;
let nextId = 100;
function bout(o) {
  const id = nextId++;
  return Object.assign({
    id, event_id: id, fighter_a_id: ME, fighter_b_id: 900 + id, fighter_a_name: 'Me', fighter_b_name: 'Opp ' + id,
    winner_id: ME, method: 'Decision - Unanimous', end_round: 3, end_time: '5:00', is_active: true,
    a_kd: 0, b_kd: 0, a_sig_str_landed: 60, b_sig_str_landed: 30, a_sig_str_attempted: 120, b_sig_str_attempted: 90,
    a_td_landed: 3, b_td_landed: 0, a_td_attempted: 6, b_td_attempted: 3, a_sub_attempts: 1, b_sub_attempts: 0,
    a_ctrl_seconds: 300, b_ctrl_seconds: 0,
    a_head_landed: 30, b_head_landed: 20, a_body_landed: 15, b_body_landed: 5, a_leg_landed: 15, b_leg_landed: 5,
    a_distance_landed: 30, b_distance_landed: 25, a_clinch_landed: 15, b_clinch_landed: 3, a_ground_landed: 15, b_ground_landed: 2,
  }, o);
}
function world(bouts) {
  const events = bouts.map((f, i) => ({ id: f.event_id, name: 'UFC ' + f.event_id, event_date: '2025-0' + (1 + (i % 9)) + '-01', is_upcoming: false }));
  const completed = FL.completedFights(bouts, events, ME, '2026-10-15');
  const career = W.careerWindow(completed, ME);
  return {
    completed, career,
    stats: O.statLine({}, career),
    mix: W.strikeMix(career.totals),
    methods: W.methods(completed, ME),
    facts: W.formFacts(completed, ME, '2026-10-15'),
  };
}

// ---- T-082, retired under D-030: no calculated style sub-label --------------
// The style a page shows is the UFC's listed discipline. A calculated label
// beside it would compete with it — UFC.com itself lists "Striker" and
// "Grappler" as disciplines — so the overview names no style at all, and the
// measurements T-082 would have turned into labels stay numbered lines.
const STYLE_SUBLABEL = /\b(boxing[- ]led|kick[- ]heavy|clinch[- ]heavy|clinch fighter|offensive wrestl\w*|defensive wrestl\w*|submission threat|pressure fighter|counter[- ]?striker|striker|grappler|mixes both|hybrid)\b/i;
t('T-082: no tendency or result line carries a style label, across a range of profiles', () => {
  const profiles = [
    world([bout(), bout(), bout(), bout()]),
    world([bout({ a_leg_landed: 40, a_distance_landed: 70, a_clinch_landed: 0, a_ground_landed: 0 }), bout(), bout(), bout()]),
    world([bout({ a_clinch_landed: 40, a_td_attempted: 12, a_td_landed: 6, a_ctrl_seconds: 600 }), bout(), bout()]),
    world([bout({ method: 'Submission', a_sub_attempts: 4 }), bout({ method: 'Submission', a_sub_attempts: 3 }), bout({ method: 'Submission' })]),
  ];
  profiles.forEach(p => { const r = O.tendencies(p); r.lines.concat(r.results).forEach(l =>
    ok(!STYLE_SUBLABEL.test(l.text), 'style label in a measured line: ' + l.text)); });
});
t('T-082: each proposed sub-label already has a numbered measurement instead', () => {
  const src = read('fight-overview.js');
  // boxing-led vs kick-heavy -> where and what they land; clinch-heavy -> clinch
  // share; offensive / defensive wrestling -> attempts and defence; submission
  // threat -> attempts per 15 and submission wins.
  ['distance', 'legs', 'head', 'clinch', 'shoots', 'control', 'tddef', 'tdweak', 'subtries', 'subwins'].forEach(k =>
    ok(new RegExp("(push|record)\\('" + k + "'").test(src), 'missing measured line: ' + k));
});

// ---- rule 1: measurements, never backgrounds --------------------------------
t('no background label in any tendency line, across a range of profiles', () => {
  const profiles = [
    world([bout(), bout(), bout(), bout()]),
    world([bout({ method: 'KO/TKO', end_round: 1, end_time: '2:00' }), bout({ method: 'KO/TKO' }), bout({ method: 'KO/TKO' }), bout()]),
    world([bout({ method: 'Submission' }), bout({ method: 'Submission' }), bout({ method: 'Submission' })]),
  ];
  profiles.forEach(p => { const r = O.tendencies(p); r.lines.concat(r.results).forEach(l => ok(!O.hasBackgroundClaim(l.text), 'background claim: ' + l.text)); });
});

t('the background detector catches the labels the owner named', () => {
  ['a boxer', 'pure kickboxer', 'a wrestler', 'submission specialist', 'BJJ black belt', 'Muay Thai'].forEach(s =>
    ok(O.hasBackgroundClaim(s), 'missed: ' + s));
  ok(!O.hasBackgroundClaim('Looks for takedowns: 4.0 attempts per 15 minutes.'), 'false positive on a measured line');
});

t('the source file itself prints no background label outside the detector', () => {
  const src = read('fight-overview.js').replace(/const BACKGROUND_WORDS[^\n]*\n/, '').replace(/\/\*[\s\S]*?\*\//g, '');
  ok(!/['"][^'"]*\b(boxer|kickboxer|wrestler|submission specialist)\b[^'"]*['"]/i.test(src), 'a background label is in a printed string');
});

t('every tendency line carries its number and its basis', () => {
  const p = world([bout(), bout(), bout(), bout(), bout()]);
  const r = O.tendencies(p);
  ok(r.lines.length > 0, 'expected tendencies from five fights');
  r.lines.forEach(l => { ok(/\d/.test(l.text), 'no number in: ' + l.text); ok(l.basis && l.basis.length, 'no basis on: ' + l.text); });
});

t('measured lines describe what the fixture shows', () => {
  const r = O.tendencies(world([bout(), bout(), bout(), bout()]));
  const keys = r.lines.map(l => l.key);
  ['clinch', 'ground', 'legs', 'body', 'outland', 'shoots', 'control', 'subtries'].forEach(k => ok(keys.includes(k), 'missing ' + k + ' in ' + keys));
  ok(!keys.includes('distance'), 'distance share is 50% here, under the cut-off');
});

// ---- rule 2: no tendencies from a thin sample --------------------------------
t('under the fight floor there are no rate tendencies, and the reason says so', () => {
  const r = O.tendencies(world([bout(), bout()]));
  ok(!r.lines.some(l => ['clinch', 'legs', 'shoots', 'control', 'outland'].includes(l.key)), 'rate tendency from two fights');
  ok(/too little/.test(r.reason), 'reason missing: ' + r.reason);
});

t('recorded finishing results are never presented as a tendency, on any sample', () => {
  const RESULT_KEYS = ['kowins', 'subwins', 'decwins', 'kolosses', 'sublosses', 'judges'];
  const quick = () => bout({ method: 'KO/TKO', end_round: 1, end_time: '1:00' });
  const thin = O.tendencies(world([quick(), quick(), quick()]));
  ok(thin.results.some(l => l.key === 'kowins'), 'KO result missing from a short-fight sample');
  ok(!thin.lines.some(l => RESULT_KEYS.includes(l.key)), 'a result was listed as a tendency');
  ok(/statistical tendencies/.test(thin.reason), 'reason must name statistical tendencies: ' + thin.reason);
  const full = O.tendencies(world([bout({ method: 'KO/TKO' }), bout({ method: 'KO/TKO' }), bout({ method: 'KO/TKO' }), bout(), bout()]));
  ok(!full.lines.some(l => RESULT_KEYS.includes(l.key)), 'a result was listed as a tendency on a full sample');
});

t('a profile summary alone never produces rate tendencies', () => {
  const s = O.statLine({ slpm: 6, sapm: 2, td_avg: 4, str_acc: 50 }, null);
  eq(s.source, 'profile');
  const r = O.tendencies({ stats: s, mix: null, methods: null, facts: null });
  eq(r.lines.length, 0, 'lines from a profile summary');
});

t('a debut has no stats source at all', () => {
  eq(O.statLine({ slpm: 0, sapm: 0 }, W.careerWindow([], ME)).source, 'none');
});

t('finishing methods need three wins, losses need two', () => {
  const two = O.tendencies(world([bout({ method: 'KO/TKO' }), bout({ method: 'KO/TKO' })]));
  ok(!two.results.some(l => l.key === 'kowins'), 'KO result from two wins');
  const three = O.tendencies(world([bout({ method: 'KO/TKO' }), bout({ method: 'KO/TKO' }), bout({ method: 'KO/TKO' })]));
  ok(three.results.some(l => l.key === 'kowins' && /3 of 3 UFC wins/.test(l.text)), 'KO result missing from three KO wins');
});

// ---- how far fights go -------------------------------------------------------
t('distance counts rounds reached, decisions and late finishes from the records', () => {
  const p = world([
    bout({ end_round: 5, method: 'Decision - Split' }),
    bout({ end_round: 3, winner_id: 999, method: 'Decision - Unanimous' }),
    bout({ end_round: 1, end_time: '1:10', method: 'KO/TKO' }),
    bout({ end_round: 4, end_time: '2:00', method: 'Submission' }),
  ]);
  const d = O.distance(p.completed, ME);
  eq(d.fights, 4); eq(d.reachedR3, 3); eq(d.intoR4, 2);
  eq(d.decisions.w, 1); eq(d.decisions.l, 1); eq(d.finishedIn.r1, 1); eq(d.finishedIn.r3plus, 1);
});

// ---- rule 3: nothing picks a side --------------------------------------------
t('the module exports no comparison or scoring function', () => {
  Object.keys(O).forEach(k => ok(!/lead|winner|score|edge|advantage|pick/i.test(k), 'suspicious export: ' + k));
});

// ---- the page -----------------------------------------------------------------
const PAGE = read('fight.html');
t('the overview sits above every detailed section', () => {
  const at = id => PAGE.indexOf('id="' + id + '"');
  ok(at('secOverview') > 0, 'secOverview missing');
  ['secWho', 'secContext', 'secCompare', 'secMarket', 'secChart', 'secBooks', 'secSheet'].forEach(id =>
    ok(at('secOverview') < at(id), 'overview is not above ' + id));
});

t('fight.html loads fight-overview.js after the rules it builds on', () => {
  const i = s => PAGE.indexOf(s);
  ok(i('<script src="fight-overview.js?v=') > i('<script src="fight-workspace.js?v='), 'load order');
  ok(i('<script src="fight-overview.js?v=') > i('<script src="market.js?v='), 'load order (market)');
});

t('the overview reuses the existing rate builders rather than its own', () => {
  const body = PAGE.slice(PAGE.indexOf('function renderOverview'), PAGE.indexOf('function monthsAgo'));
  ['W.careerWindow', 'W.strikeMix', 'FL.disciplineRead', 'FL.lateRoundRead', 'M.readSide', 'O.tendencies'].forEach(s =>
    ok(body.includes(s), 'renderOverview does not use ' + s));
  ok(/bookCount/.test(body) && /fresh\.when/.test(body), 'a price is shown without its book count or age');
});

t('a failed load hides the overview too', () => {
  ok(/\['secOverview', 'secWho'/.test(PAGE), 'fail() does not hide the overview');
});

if (failures.length) {
  console.error('fight-overview: ' + failures.length + ' failed, ' + passed + ' passed');
  failures.forEach(f => console.error('  ✗ ' + f));
  process.exit(1);
}
console.log('fight-overview: ' + passed + ' passed');
