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

t('without bout_order the order is called announcement order, never the running order', () => {
  const none = CR.orderInfo([{ id: 1, bout_order: null }, { id: 2, bout_order: null }]);
  eq(none.official, false);
  ok(/announced/i.test(none.note) && /does not hold the official running order/i.test(none.note));
  ok(/start times/i.test(none.note) && /prelims/i.test(none.note), 'the note must say start times and the prelim split are not known');
  ok(!/open/i.test(none.labels.join(' ')), 'without a running order there is no "opening bout" to sort by');
  const all = CR.orderInfo([{ id: 1, bout_order: 1 }, { id: 2, bout_order: 2 }]);
  eq(all.official, true);
  const part = CR.orderInfo([{ id: 1, bout_order: 1 }, { id: 2, bout_order: null }]);
  eq(part.official, false, 'a partial order is not the official order');
});

t('Card Lab and the event page load card-research.js and show the order note', () => {
  [['index.html', 'orderNote'], ['event.html', 'evOrderNote']].forEach(([f, id]) => {
    const src = read(f);
    ok(/<script src="card-research\.js\?v=\d+"><\/script>/.test(src), f + ' does not load card-research.js');
    ok(src.indexOf('id="' + id + '"') > 0 || src.indexOf("id=\"" + id + "\"") > 0, f + ' has no order note');
    ok(/orderInfo\(/.test(src), f + ' does not take its wording from orderInfo');
    ok(/applyAges\(/.test(src) && /\bdob\b/.test(src), f + ' does not compute ages from the date of birth');
  });
  ok(!/top of the card down/i.test(read('index.html')), 'Card Lab still claims "top of the card down"');
});

if (failures.length) {
  console.error('card-research: ' + failures.length + ' failed, ' + passed + ' passed');
  failures.forEach(f => console.error('  ✗ ' + f));
  process.exit(1);
}
console.log('card-research: ' + passed + ' passed');
