/* ==========================================================================
   Cannon Fight Lab — card-research.js
   Card-level facts shared by Card Lab (index.html), the event page and Fight
   Lab: a fighter's age today, which bookings on a card changed opponent, who
   is making a UFC debut, and — most important — what the order of a card
   actually is. Pure: no network, no DOM, no clock of its own.

   THE ORDER RULE. `fights.bout_order` (the real running order) has never been
   written for any card: the pipeline that captures it is built but switched
   off pending approval (event-flow.yml, T-029). Without it, cfl.orderCard
   puts the main event first and then sorts by insert id, which is the order
   the bouts were ANNOUNCED, not the order they will be fought. So no surface
   may call that "the running order", "top of the card down" or "opener", and
   the main-card / prelim split and start times are not known at all. When
   bout_order is present for every bout, orderInfo says so and the wording
   changes with it.
   ========================================================================== */
(function () {
  'use strict';

  // Age on `today` from 'YYYY-MM-DD'. The stored fighters.age is not
  // recomputed as birthdays pass (45 of the 150 fighters on upcoming cards
  // read a year young on 2026-10-15), so pages use this whenever there is a
  // date of birth.
  function ageOn(dob, today) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(dob || '');
    const t = /^(\d{4})-(\d{2})-(\d{2})/.exec(today || '');
    if (!m || !t) return null;
    let age = (+t[1]) - (+m[1]);
    if ((+t[2]) < (+m[2]) || ((+t[2]) === (+m[2]) && (+t[3]) < (+m[3]))) age -= 1;
    return age >= 15 && age <= 70 ? age : null;
  }

  // Overwrites f.age with the age today when a date of birth is held, and
  // keeps the stored value otherwise. Returns the same array.
  function applyAges(fighters, today) {
    (fighters || []).forEach(f => {
      if (!f) return;
      const a = ageOn(f.dob, today);
      if (a != null) f.age = a;
    });
    return fighters;
  }

  // Bookings on the card that fell off it (is_active = false) and involve one
  // of this bout's fighters. A fact from the card's own history: the scraper
  // retires a booking when it leaves the UFCStats event page.
  function opponentChanges(cardFights, fight) {
    const ids = [fight.fighter_a_id, fight.fighter_b_id];
    return (cardFights || []).filter(x => x && x.is_active === false && x.id !== fight.id &&
      (ids.indexOf(x.fighter_a_id) >= 0 || ids.indexOf(x.fighter_b_id) >= 0))
      .map(x => {
        const aIn = ids.indexOf(x.fighter_a_id) >= 0;
        return {
          fightId: x.id,
          fighterId: aIn ? x.fighter_a_id : x.fighter_b_id,
          fighterName: aIn ? x.fighter_a_name : x.fighter_b_name,
          formerOpponent: aIn ? x.fighter_b_name : x.fighter_a_name,
        };
      });
  }

  // A UFC debut, from the counted UFC record (ufc-record.js). Unknown when the
  // record could not be loaded — never guessed.
  function isDebut(f) {
    if (!f || f.ufc_record_unavailable || f.ufc_wins == null) return null;
    return (+f.ufc_wins + +f.ufc_losses + +(f.ufc_draws || 0) + +(f.ufc_no_contests || 0)) === 0;
  }

  // What the order on screen is. `fights` are the active bookings as shown.
  function orderInfo(fights) {
    const active = (fights || []).filter(f => f && f.is_active !== false);
    const official = active.length > 0 && active.every(f => f.bout_order != null);
    return {
      official,
      note: official
        ? 'Official running order, main event first.'
        : 'Main event first, then in the order the bouts were announced. CFL does not hold the official running order, the main card / prelims split or start times yet.',
      noteReversed: official
        ? 'Official running order, opening bout first.'
        : 'Reversed: main event last. Below the main event this is announcement order, not the order they will be fought.',
      labels: official ? ['Main event first', 'Opening bout first'] : ['Main event first', 'Main event last'],
    };
  }

  const api = { ageOn, applyAges, opponentChanges, isDebut, orderInfo };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else window.cflCard = api;
})();
