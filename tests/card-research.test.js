/* ==========================================================================
   tests/card-research.test.js — card-level facts shared by Card Lab, the
   event page and Fight Lab.

   What it holds:
     - age is computed from the date of birth, birthday-exact;
     - an opponent change is read from the card's own retired bookings;
     - a debut is never guessed when the UFC record could not be loaded;
     - no page calls the card order "the running order" unless bout_order is
       actually there, and the pages that order a card say what the order is.

   Run:  node tests/card-research.test.js
   ========================================================================== */
'use strict';
const fs = require('fs');
const path = require('path');
const CR = require('../card-research.js');
const read = f => fs.readFileSync(path.join(__dirname, '..', f), 'utf8');

let passed = 0;
const failures = [];
function t(name, fn) { try { fn(); passed += 1; } catch (e) { failures.push(name + '\n      ' + e.message); } }
function ok(c, what) { if (!c) throw new Error(what || 'expected truthy'); }
function eq(a, b, what) { if (a !== b) throw new Error((what || 'value') + ': expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a)); }

t('age is birthday-exact', () => {
  eq(CR.ageOn('1994-10-16', '2026-10-15'), 31, 'the day before the birthday');
  eq(CR.ageOn('1994-10-15', '2026-10-15'), 32, 'on the birthday');
  eq(CR.ageOn('1994-04-27', '2026-10-15'), 32);
  eq(CR.ageOn(null, '2026-10-15'), null);
  eq(CR.ageOn('2030-01-01', '2026-10-15'), null, 'an impossible date is not an age');
});

t('applyAges replaces a stale stored age and keeps it when there is no dob', () => {
  const fs_ = [{ age: 31, dob: '1990-01-01' }, { age: 40, dob: null }];
  CR.applyAges(fs_, '2026-10-15');
  eq(fs_[0].age, 36); eq(fs_[1].age, 40);
});

t('an opponent change comes from a retired booking on the same card', () => {
  const card = [
    { id: 1, fighter_a_id: 10, fighter_b_id: 20, fighter_a_name: 'A Ten', fighter_b_name: 'B Twenty', is_active: true },
    { id: 2, fighter_a_id: 30, fighter_b_id: 10, fighter_a_name: 'C Thirty', fighter_b_name: 'A Ten', is_active: false },
    { id: 3, fighter_a_id: 40, fighter_b_id: 50, fighter_a_name: 'D', fighter_b_name: 'E', is_active: false },
  ];
  const ch = CR.opponentChanges(card, card[0]);
  eq(ch.length, 1); eq(ch[0].fighterName, 'A Ten'); eq(ch[0].formerOpponent, 'C Thirty');
  eq(CR.opponentChanges(card.slice(0, 1), card[0]).length, 0);
});

t('a debut is only claimed from a loaded UFC record', () => {
  eq(CR.isDebut({ ufc_wins: 0, ufc_losses: 0, ufc_draws: 0, ufc_no_contests: 0 }), true);
  eq(CR.isDebut({ ufc_wins: 0, ufc_losses: 1, ufc_draws: 0, ufc_no_contests: 0 }), false);
  eq(CR.isDebut({ ufc_record_unavailable: true, ufc_wins: null }), null);
  eq(CR.isDebut({}), null);
});

// ---- running order (event-flow ledger, 1 = first walkout) ----------------
const card = [10, 11, 12, 13].map(id => ({ id, is_active: true, fighter_a_id: id * 10, fighter_b_id: id * 10 + 1 }));
// The ledger numbers the main event (13) highest: 13 walks out last.
const obs = [{ fight_id: 12, bout_order: 1, observed_at: '2026-10-12T07:20:00Z' }, { fight_id: 10, bout_order: 2, observed_at: '2026-10-12T07:20:00Z' },
             { fight_id: 11, bout_order: 3, observed_at: '2026-10-12T07:20:00Z' }, { fight_id: 13, bout_order: 4, observed_at: '2026-10-12T07:20:00Z' }];

t('a complete observation makes the order official; anything less does not', () => {
  eq(CR.runningOrder(card, obs).status, 'official');
  const part = CR.runningOrder(card, obs.slice(1));
  eq(part.status, 'partial'); eq(part.missing.length, 1); eq(part.missing[0], 12, 'the late booking is named, not placed');
  eq(CR.runningOrder(card, null).status, 'none'); eq(CR.runningOrder(card, []).status, 'none');
  eq(CR.runningOrder(card.concat([{ id: 99, is_active: false }]), obs).status, 'official', 'a retired booking does not block the order');
});

t('official order: main event first going down, first walkout first going up', () => {
  const ro = CR.runningOrder(card, obs);
  eq(CR.sortCard(card, ro, 'down').map(f => f.id).join(','), '13,11,10,12');
  eq(CR.sortCard(card, ro, 'up').map(f => f.id).join(','), '12,10,11,13');
  eq(CR.boutLabel(ro, 12), 'Bout 1 of 4'); eq(CR.boutLabel(ro, 13), 'Bout 4 of 4');
});

t('without an official order nothing is placed by guesswork', () => {
  const part = CR.runningOrder(card, obs.slice(1));
  eq(CR.sortCard(card, part, 'down').map(f => f.id).join(','), '10,11,12,13', 'the given (announcement) order is kept');
  eq(CR.sortCard(card, part, 'up').map(f => f.id).join(','), '13,12,11,10');
  eq(CR.boutLabel(part, 10), null, 'no "Bout N of M" from a partial observation');
  eq(CR.boutLabel(null, 10), null);
});

t('the wording follows the evidence', () => {
  const none = CR.orderInfo(CR.runningOrder(card, null));
  eq(none.official, false);
  ok(/announced/i.test(none.note) && /does not hold the official running order/i.test(none.note));
  ok(/start times/i.test(none.note) && /prelims/i.test(none.note), 'start times and the prelim split must be named as not held');
  ok(!/first bout|open/i.test(none.labels.join(' ')), 'without a running order there is no "first bout" to sort by');
  const part = CR.orderInfo(CR.runningOrder(card, obs.slice(1)));
  ok(/not complete/i.test(part.note) && /1 bout/.test(part.note), 'a partial order says how many are unplaced');
  const off = CR.orderInfo(CR.runningOrder(card, obs));
  eq(off.official, true); ok(/Official running order/.test(off.note) && /2026-10-12/.test(off.note));
  eq(off.labels[1], 'First bout first');
  ok(/start times/i.test(off.note), 'an official order still does not claim start times');
  eq(CR.orderInfo(null).official, false);
});

t('fights.bout_order is never read as the running order (it counts the other way)', () => {
  const src = read('card-research.js').replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
  ok(!/\.bout_order\b/.test(src.replace(/r\.bout_order/g, '')), 'card-research.js reads a bout_order other than the ledger view row');
  ok(/from\('v_card_running_order'\)/.test(src), 'the running order must come from the ledger view');
});

t('the running-order read stays off until the view exists', () => {
  eq(CR.RUNNING_ORDER_LIVE, false, 'flip this only in the change that ships v_card_running_order');
  return CR.loadRunningOrder({ from: () => { throw new Error('must not query while off'); } }, 1).then(r => eq(r, null));
});

t('the view is defined in repo SQL, read-only to the browser, ledger revoked', () => {
  const sql = read('research/event-card/apply_2026-10-21_running_order.sql');
  ok(/create or replace view public\.v_card_running_order/i.test(sql));
  ok(/grant select on public\.v_card_running_order to anon, authenticated/i.test(sql));
  ok(/revoke all on public\.fight_bout_order from anon, authenticated/i.test(sql));
  ok(!/grant[^;]*(insert|update|delete|all)[^;]*v_card_running_order/i.test(sql), 'the view must be select-only');
  ok(/where source in \('ufcstats_card', 'espn_scoreboard'\)/.test(sql) && /f\.is_active/.test(sql), 'only the two automated card sources, active bookings only');
  ok(!/odds_api_usage|fight_bout_completions/i.test(sql.replace(/--.*$/gm, '')), 'this file must not create the CLV-owned tables');
  ok(/SUPERSEDED/.test(read('research/event-card/proposed_2026-10-15_card_running_order.sql')), 'the 2026-10-15 file is a pointer, not a second definition');
});

// ---- search ----------------------------------------------------------------
t('search is case- and accent-insensitive and needs every word', () => {
  const fmap = { 1: { name: 'Erin Blanchfield' }, 2: { name: 'Jasmine Jasudavičius', nickname: 'Jas' } };
  const f = { fighter_a_id: 1, fighter_b_id: 2, weight_class: 'Flyweight' };
  ok(CR.fightMatches(f, fmap, 'jasudavicius'), 'accents ignored');
  ok(CR.fightMatches(f, fmap, 'BLANCH fly'), 'case ignored, two words across name and weight class');
  ok(!CR.fightMatches(f, fmap, 'blanchfield heavy'), 'every word must match');
  ok(CR.fightMatches(f, fmap, '   '), 'an empty search matches everything');
  ok(CR.fightMatches({ fighter_a_name: 'Kyle Nelson', fighter_b_name: 'Cristian Perez' }, {}, 'perez'), 'booking names are searched when a profile is missing');
});

t('Card Lab and the event page load card-research.js and show the order note and search', () => {
  [['index.html', 'orderNote', 'cardSearch'], ['event.html', 'evOrderNote', 'evSearch']].forEach(([f, id, search]) => {
    const src = read(f);
    ok(/<script src="card-research\.js\?v=\d+"><\/script>/.test(src), f + ' does not load card-research.js');
    ok(src.indexOf('id="' + id + '"') > 0 || src.indexOf("id=\"" + id + "\"") > 0, f + ' has no order note');
    ok(/orderInfo\(/.test(src), f + ' does not take its wording from orderInfo');
    ok(/applyAges\(/.test(src) && /\bdob\b/.test(src), f + ' does not compute ages from the date of birth');
    ok(src.indexOf('id="' + search + '"') > 0 && /fightMatches\(/.test(src), f + ' has no search within the card');
    ok(/runningOrder\(/.test(src) && /sortCard\(/.test(src) && /orderInfo\(st\.ro\)|orderInfo\(_cardState\.ro\)/.test(src), f + ' does not order from the running-order ledger');
  });
  ok(!/top of the card down/i.test(read('index.html')), 'Card Lab still claims "top of the card down"');
});

if (failures.length) {
  console.error('card-research: ' + failures.length + ' failed, ' + passed + ' passed');
  failures.forEach(f => console.error('  ✗ ' + f));
  process.exit(1);
}
console.log('card-research: ' + passed + ' passed');
