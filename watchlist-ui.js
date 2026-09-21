/* ===========================================================================
   watchlist-ui.js — the star button and the alert form, in one place.

   Card Lab, Fight Lab and the watchlist page all offer the same two actions,
   and the rules attached to them are wording rules as much as behaviour: what
   a star means when you are signed out, what an alert may promise, and what a
   quiet alert is allowed to look like. A page that builds its own star is a
   page that can quietly drop one of those.

   Same arrangement as fight-insights.js and market.js: edit this, not the page.

   Depends on `cflSupabase`, `cflAuth`, `cfl` (_shared.js, _auth.js) and
   `cflAlerts` (alerts.js).
   =========================================================================== */

(function () {
  'use strict';

  const W = {};
  const sb = () => window.cflSupabase;

  /* ------------------------------------------------------------- the star */
  // One in-memory set per page load. A star is cheap to draw and expensive to
  // get wrong: showing a fight as un-starred when it is starred makes the next
  // click remove it, which reads as the button not working.
  let starred = null;

  W.loadStarred = async function () {
    starred = new Set();
    try {
      if (!window.cflAuth || !cflAuth.getUser()) return starred;
      const { data, error } = await sb().from('user_watchlist').select('fight_id');
      if (!error && data) data.forEach(r => starred.add(Number(r.fight_id)));
    } catch (e) { /* signed out or offline: an empty set, never a broken page */ }
    return starred;
  };

  W.isStarred = id => !!(starred && starred.has(Number(id)));

  W.starButton = function (fightId, opts) {
    const o = opts || {};
    const on = W.isStarred(fightId);
    return '<button type="button" class="cfl-star' + (on ? ' on' : '') + '"' +
           ' data-fight="' + Number(fightId) + '"' +
           ' data-from="' + (o.from || 'card') + '"' +
           ' aria-pressed="' + (on ? 'true' : 'false') + '"' +
           ' title="' + (on ? 'Remove from your watchlist' : 'Add to your watchlist') + '">' +
           '<span aria-hidden="true">' + (on ? '★' : '☆') + '</span>' +
           '<span class="cfl-sr-only">' + (on ? 'Starred' : 'Star this fight') + '</span>' +
           '</button>';
  };

  // One delegated listener per page rather than one per row.
  W.bindStars = function (root, onChange) {
    (root || document).addEventListener('click', async ev => {
      const btn = ev.target.closest && ev.target.closest('.cfl-star');
      if (!btn) return;
      ev.preventDefault();
      const id = Number(btn.dataset.fight);
      const from = btn.dataset.from || 'card';

      if (!cflAuth.getUser()) {
        // Not a paywall — an account wall, and only because the star has to be
        // stored against somebody. Say so rather than bouncing them silently.
        W.toast('Create a free account to keep a watchlist. Everything on the ' +
                'card stays free either way.', { href: '/signup.html?next=' +
                encodeURIComponent(location.pathname + location.search) , cta: 'Create account' });
        return;
      }

      const wasOn = W.isStarred(id);
      btn.disabled = true;
      try {
        if (wasOn) {
          const { error } = await sb().from('user_watchlist').delete().eq('fight_id', id);
          if (error) throw error;
          starred.delete(id);
          cfl.track('watchlist_removed', { from: from });
        } else {
          const { error } = await sb().from('user_watchlist')
            .insert({ user_id: cflAuth.getUser().id, fight_id: id });
          if (error && error.code !== '23505') throw error;
          starred.add(id);
          cfl.track('watchlist_added', { from: from });
        }
        W.paintStar(btn, !wasOn);
        if (onChange) onChange(id, !wasOn);
      } catch (e) {
        W.toast('Could not save that just now. Nothing was changed.');
      } finally {
        btn.disabled = false;
      }
    });
  };

  W.paintStar = function (btn, on) {
    btn.classList.toggle('on', !!on);
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    btn.title = on ? 'Remove from your watchlist' : 'Add to your watchlist';
    btn.innerHTML = '<span aria-hidden="true">' + (on ? '★' : '☆') + '</span>' +
      '<span class="cfl-sr-only">' + (on ? 'Starred' : 'Star this fight') + '</span>';
  };

  /* ------------------------------------------------------- what an alert says */
  // Plain English for every refusal `v_fight_alert_market` can return. A member
  // who cannot see WHY nothing arrived assumes the feature is broken, and they
  // are right to — a silent refusal and a bug look identical from outside.
  //
  // Two of these explain a refusal the member may find surprising, so they say
  // the quiet part: CFL would rather tell you nothing than tell you something
  // it cannot stand behind.
  W.STATE_COPY = {
    watching:        { tone: 'ok',   text: 'Watching. We will email you when it happens.' },
    paused:          { tone: 'off',  text: 'Paused. Turn it back on to start watching again.' },
    no_market_yet:   { tone: 'wait', text: 'No sportsbook prices for this fight yet. We will start watching as soon as there are.' },
    fight_settled:   { tone: 'done', text: 'This fight is over, so this alert has stopped.' },
    fight_inactive:  { tone: 'done', text: 'This bout came off the card, so this alert has stopped.' },
    event_past:      { tone: 'done', text: 'This card has been and gone.' },
    no_market:       { tone: 'wait', text: 'We hold no prices for this fight right now.' },
    thin_book_count: { tone: 'wait', text: 'Fewer than three sportsbooks are pricing this fight. One or two books is not a market, so we will not alert off it.' },
    stale_for_price: { tone: 'wait', text: 'Our newest price here is more than two hours old. We will not send you to a sportsbook for a number we cannot vouch for.' },
    no_best_price:   { tone: 'wait', text: 'We do not have a two-sided price for this fight yet.' },
    no_broad_capture:{ tone: 'wait', text: 'We have never held three sportsbooks on this fight at once, so there is no honest starting point to measure movement from.' },
    insufficient_matched_books:
                     { tone: 'wait', text: 'Fewer than three sportsbooks have quoted this fight at both ends, so any movement figure would be comparing different books. We would rather say nothing.' },
    no_movement_figure: { tone: 'wait', text: 'No movement figure we can stand behind yet.' },
    stale_for_move:  { tone: 'wait', text: 'The last prices here are more than a day old.' }
  };

  W.explainState = function (state) {
    return W.STATE_COPY[state] ||
      { tone: 'wait', text: 'Not watching right now.' };
  };

  /* ---------------------------------------------------------- creating one */
  W.createAlert = async function (fields) {
    const bad = cflAlerts.validate(fields);
    if (bad) return { ok: false, reason: bad };
    const user = cflAuth.getUser();
    if (!user) return { ok: false, reason: 'signed_out' };

    const row = {
      user_id: user.id,
      fight_id: Number(fields.fight_id),
      kind: fields.kind,
      side: fields.kind === 'price_target' ? fields.side : null,
      target_american: fields.kind === 'price_target' ? Number(fields.target_american) : null,
      threshold_pts: fields.kind === 'market_move' ? Number(fields.threshold_pts) : null,
      direction: fields.kind === 'market_move' ? fields.direction : null
    };
    const { error } = await sb().from('user_alerts').insert(row);
    if (error) {
      if (error.code === '23505') return { ok: false, reason: 'duplicate' };
      // The quota trigger raises check_violation. Say what it means rather than
      // printing a Postgres error at somebody.
      if (/quota/i.test(error.message || '')) return { ok: false, reason: 'quota' };
      return { ok: false, reason: 'failed', detail: error.message };
    }
    cfl.track('alert_created', { kind: fields.kind });
    return { ok: true };
  };

  W.CREATE_ERRORS = {
    signed_out: 'Create a free account first — an alert has to be stored against one.',
    duplicate:  'You already have that alert on this fight.',
    quota:      'You have reached the maximum number of active alerts. Delete one to add another.',
    side_required: 'Pick which fighter.',
    target_required: 'Enter a price.',
    target_zero: 'That is not a price.',
    target_impossible: 'American odds do not run between -100 and +100. Try +120 or -150.',
    target_range: 'That price is out of range.',
    threshold_required: 'Enter how many points of movement.',
    threshold_too_small: 'Under half a point is ordinary capture noise — it would email you constantly.',
    threshold_too_large: 'That is more than any market moves. Try something under 10 points.',
    direction_required: 'Pick which way.',
    unknown_kind: 'Pick a type of alert.',
    failed: 'Could not save that just now.'
  };

  /* ------------------------------------------------------------------ toast */
  W.toast = function (msg, opts) {
    const o = opts || {};
    let el = document.getElementById('cflToast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'cflToast';
      el.className = 'cfl-toast';
      document.body.appendChild(el);
    }
    el.innerHTML = cfl.escapeHtml(msg) +
      (o.href ? ' <a href="' + o.href + '">' + cfl.escapeHtml(o.cta || 'Go') + '</a>' : '');
    el.classList.add('show');
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove('show'), o.href ? 9000 : 4500);
  };

  const api = W;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else if (typeof window !== 'undefined') window.cflWatchlist = api;
})();
