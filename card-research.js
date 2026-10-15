/* ==========================================================================
   Cannon Fight Lab — card-research.js
   Card-level facts shared by Card Lab (index.html), the event page and Fight
   Lab: a fighter's age today, which bookings on a card changed opponent, who
   is making a UFC debut, and — most important — what the order of a card
   actually is. Pure: no network, no DOM, no clock of its own.

   THE ORDER RULE. The real running order lives in the event-flow ledger
   (see runningOrder below), which is built but not yet applied. Without it,
   cfl.orderCard puts the main event first and then sorts by insert id, which
   is the order the bouts were ANNOUNCED, not the order they will be fought.
   So no surface may call that "the running order", "top of the card down" or
   "opener", and the main-card / prelim split and start times are not known
   at all. Only a complete observation of the card makes the order official.
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

  // ---- running order ------------------------------------------------------
  // The running order comes from ONE place: the event-flow ledger
  // (fight_bout_order, written by cfl_engine/event_flow/ingest_bout_order.py
  // from the UFCStats card page), read through v_card_running_order, which
  // returns the latest COMPLETE card observation. Its numbering is
  // 1 = FIRST BOUT TO WALK OUT; the main event carries the highest number.
  //
  // fights.bout_order is NOT a source: it counts the other way (1 = main
  // event), nothing writes it, and reading it would invert a card silently.
  //
  // The page asks for the view only once it exists. Until the migration is
  // applied a request would 404 on every page load, so the switch below stays
  // false and flips in the same change that ships the view
  // (research/event-card/EVENT_CARD_PLAN_2026-10-15.md).
  const RUNNING_ORDER_LIVE = false;

  // `active` are the card's active bookings; `rows` are view rows
  // { fight_id, bout_order, observed_at }. Returns:
  //   official — every active bout has a position from one observation;
  //   partial  — an observation exists but some active bouts are not in it
  //              (booked after it); those are named, never guessed into place;
  //   none     — no observation.
  function runningOrder(active, rows) {
    const live = (active || []).filter(f => f && f.is_active !== false);
    const pos = {};
    let observedAt = null;
    (rows || []).forEach(r => {
      if (!r || r.bout_order == null) return;
      pos[r.fight_id] = +r.bout_order;
      if (!observedAt || r.observed_at > observedAt) observedAt = r.observed_at;
    });
    const placed = live.filter(f => pos[f.id] != null);
    const missing = live.filter(f => pos[f.id] == null);
    const status = !placed.length ? 'none' : missing.length ? 'partial' : 'official';
    return { status, pos, observedAt, total: live.length, missing: missing.map(f => f.id) };
  }

  // Order a card for display. `dir` 'down' = main event first, 'up' = main
  // event last. With an official order, 'up' is the true walkout order. With
  // anything less, the existing order is kept as given (main event, then the
  // order the bouts were announced) and 'up' simply reverses it.
  function sortCard(fights, ro, dir) {
    const rows = (fights || []).slice();
    if (ro && ro.status === 'official') {
      rows.sort((a, b) => ro.pos[b.id] - ro.pos[a.id]);   // highest walkout number = main event first
    }
    return dir === 'up' ? rows.reverse() : rows;
  }

  // "Bout 7 of 13" — only from an official order.
  function boutLabel(ro, fightId) {
    if (!ro || ro.status !== 'official' || ro.pos[fightId] == null) return null;
    return 'Bout ' + ro.pos[fightId] + ' of ' + ro.total;
  }

  // What the order on screen is, in words. Takes runningOrder()'s result.
  function orderInfo(ro) {
    const official = !!(ro && ro.status === 'official');
    const seen = ro && ro.observedAt ? String(ro.observedAt).slice(0, 10) : null;
    const pending = 'CFL does not hold the official running order for this card, so the main event comes first and the rest follow in the order the bouts were announced.';
    const notes = {
      official: 'Official running order, read from the UFCStats card' + (seen ? ' on ' + seen : '') + '.',
      partial: 'Running order not complete: ' + (ro ? ro.missing.length : 0) + ' bout(s) were booked after CFL last read the card' +
        (seen ? ' (' + seen + ')' : '') + ', so the main event comes first and the rest follow in the order the bouts were announced.',
      none: pending,
    };
    const status = ro ? ro.status : 'none';
    return {
      official,
      status,
      note: notes[status] + ' Start times and the main card / prelims split are not in our data yet.',
      noteReversed: official
        ? 'Official running order, first bout first.' + ' Start times and the main card / prelims split are not in our data yet.'
        : 'Reversed: main event last. Below the main event this is announcement order, not the order they will be fought.',
      labels: official ? ['Main event first', 'First bout first'] : ['Main event first', 'Main event last'],
    };
  }

  // Reads the running order for one card. null = not available (switch off,
  // view missing or the read failed) — which the page treats as "none".
  async function loadRunningOrder(sb, eventId) {
    if (!RUNNING_ORDER_LIVE || !sb || eventId == null) return null;
    try {
      const { data, error } = await sb.from('v_card_running_order')
        .select('fight_id, bout_order, observed_at').eq('event_id', eventId);
      return error ? null : (data || []);
    } catch (e) { return null; }
  }

  // ---- search within a card -------------------------------------------------
  // Case- and accent-insensitive; every word typed must appear somewhere in the
  // bout: either fighter's name or nickname, or the weight class. "jas fly"
  // finds Blanchfield vs Jasudavicius at flyweight.
  function norm(s) {
    return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  }
  function fightMatches(fight, fmap, query) {
    const words = norm(query).split(' ').filter(Boolean);
    if (!words.length) return true;
    const a = (fmap && fmap[fight.fighter_a_id]) || {}, b = (fmap && fmap[fight.fighter_b_id]) || {};
    const hay = norm([a.name, a.nickname, b.name, b.nickname, fight.fighter_a_name, fight.fighter_b_name, fight.weight_class].join(' '));
    return words.every(w => hay.indexOf(w) >= 0);
  }

  const api = { ageOn, applyAges, opponentChanges, isDebut, RUNNING_ORDER_LIVE, runningOrder, sortCard, boutLabel, orderInfo,
                loadRunningOrder, norm, fightMatches };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else window.cflCard = api;
})();
