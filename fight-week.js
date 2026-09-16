/* ==========================================================================
   Cannon Fight Lab — fight-week client
   --------------------------------------------------------------------------
   Browser-side glue for the Event Hub, fight pages, the Market Board and the
   homepage's next-card blocks. Needs (in this order): supabase-js, _shared.js,
   _auth.js, fight-week-core.js, books.js.

   What it does:
     1. Reads the current card from the public views in fight_week_views.sql —
        the locked forecast, the vig-free market now and at lock, the latest
        quote per sportsbook. It never computes a prediction.
     2. Hydrates prerendered hub / fight pages with fresh market numbers.
     3. Renders the Fight Week Brief signup block (one component, reused).
     4. Sends Plausible custom events (no personal data — ids only).
   ========================================================================== */
(function () {
  'use strict';
  const core = window.cflFightWeek;
  const books = window.cflBooks;
  const fw = {};

  // ---------------------------------------------------------------------
  // Tracking. cfl.track (added by the revenue-trust PR) wins when present;
  // otherwise talk to Plausible directly. Props are ids and labels only.
  // ---------------------------------------------------------------------
  fw.track = function (name, props) {
    try {
      const p = props || {};
      if (window.cfl && typeof window.cfl.track === 'function') return window.cfl.track(name, p);
      if (typeof window.plausible === 'function') return window.plausible(name, { props: p });
      (window.plausible = window.plausible || function () { (window.plausible.q = window.plausible.q || []).push(arguments); })(name, { props: p });
    } catch (_) { /* analytics must never break the page */ }
  };

  // Fire once when an element first scrolls into view.
  fw.onFirstView = function (el, fn) {
    if (!el) return;
    if (!('IntersectionObserver' in window)) { fn(); return; }
    const io = new IntersectionObserver((entries) => {
      if (entries.some(e => e.isIntersecting)) { io.disconnect(); fn(); }
    }, { threshold: 0.25 });
    io.observe(el);
  };

  // ---------------------------------------------------------------------
  // Data
  // ---------------------------------------------------------------------
  const sb = () => window.cflSupabase;
  const byKey = (rows, k) => { const m = {}; (rows || []).forEach(r => { m[r[k]] = r; }); return m; };

  async function safe(q, label) {
    try {
      const { data, error } = await q;
      if (error) { console.warn('[fight-week] ' + label + ':', error.message); return []; }
      return data || [];
    } catch (e) { console.warn('[fight-week] ' + label + ' threw:', e); return []; }
  }

  // Events that have a locked forecast, newest first.
  fw.eventsWithRecord = async function () {
    const fc = await safe(sb().from('v_fight_locked_forecast').select('event_id').limit(5000), 'forecast events');
    const ids = [...new Set(fc.map(r => r.event_id).filter(Boolean))];
    if (!ids.length) return [];
    const events = await safe(sb().from('events').select('id, name, event_date, location, is_upcoming').in('id', ids), 'events');
    return events.sort((a, b) => (a.event_date < b.event_date ? 1 : -1));
  };

  // The card the site is about right now: the soonest upcoming card with a
  // locked forecast, else the latest graded card.
  fw.pickCurrent = function (events) {
    const today = localDateStr(new Date());
    const upcoming = events.filter(e => e.event_date >= today).sort((a, b) => (a.event_date < b.event_date ? -1 : 1));
    if (upcoming.length) return { event: upcoming[0], phase: upcoming[0].event_date === today ? 'today' : 'upcoming' };
    const past = events.filter(e => e.event_date < today);
    return past.length ? { event: past[0], phase: 'graded' } : { event: null, phase: 'none' };
  };
  function localDateStr(d) {
    const p = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  }

  // Everything for one event: rows in card order + latest per-book quotes.
  fw.loadCard = async function (event) {
    const fights = await safe(sb().from('fights')
      .select('*')
      .eq('event_id', event.id), 'fights');
    const ids = fights.map(f => f.id);
    if (!ids.length) return { event, rows: [], byBook: {}, summary: core.summarize([]) };
    const [forecasts, market, atLock, byBookRows] = await Promise.all([
      safe(sb().from('v_fight_locked_forecast').select('*').in('fight_id', ids), 'locked forecasts'),
      safe(sb().from('v_fight_market_vigfree').select('*').in('fight_id', ids), 'vig-free market'),
      safe(sb().from('v_fight_market_at_lock').select('*').in('fight_id', ids), 'market at lock'),
      safe(sb().from('v_fight_odds_latest_by_book').select('*').in('fight_id', ids), 'latest by book'),
    ]);
    const rows = core.assembleCard(event, fights, byKey(forecasts, 'fight_id'), byKey(market, 'fight_id'), byKey(atLock, 'fight_id'));
    const byBook = {};
    byBookRows.forEach(r => { (byBook[r.fight_id] = byBook[r.fight_id] || []).push(r); });
    return { event, rows, byBook, summary: core.summarize(rows) };
  };

  fw.loadCurrent = async function () {
    const events = await fw.eventsWithRecord();
    const cur = fw.pickCurrent(events);
    if (!cur.event) return { event: null, phase: 'none', rows: [], byBook: {}, summary: core.summarize([]) };
    const card = await fw.loadCard(cur.event);
    card.phase = cur.phase;
    return card;
  };

  // ---------------------------------------------------------------------
  // Shared render bits (mirror build/hub-templates.js — keep in step)
  // ---------------------------------------------------------------------
  const esc = core.escapeHtml;

  fw.labelHtml = function (d) {
    return `<span class="fw-label ${esc(d.kind)}">${esc(d.label)}</span>`;
  };

  // One disagreement card, used by the homepage top-3 and the Market Board.
  fw.disagreementCard = function (r, eventName) {
    const d = r.disagree;
    const favA = r.cfl_p_a >= 0.5;
    const fav = favA ? r.fighter_a_name : r.fighter_b_name;
    const cfl = favA ? r.cfl_p_a : r.cfl_p_b;
    const mkt = favA ? r.market_p_a : r.market_p_b;
    return `<div class="fw-card" data-fight-id="${r.fight_id}">
      <div class="fw-eyebrow"><span>${esc(r.weight_class || 'Bout')}</span>${r.is_main_event ? '<span class="fw-tag main">Main event</span>' : ''}${eventName ? `<span class="fw-eyebrow-dim">${esc(eventName)}</span>` : ''}</div>
      <div class="fw-card-bout"><a href="${core.fightPath(r)}">${esc(r.fighter_a_name)} <span class="vs">vs</span> ${esc(r.fighter_b_name)}</a></div>
      <div class="fw-rule">CFL favours <b>${esc(fav)}</b> · ${esc(core.confidenceLabel(r.tier, cfl))}</div>
      <div class="fw-card-nums">
        <div class="cell"><div class="t">CFL</div><div class="n">${core.pct(cfl)}</div></div>
        <div class="cell"><div class="t">Market</div><div class="n" data-mkt-fav="${r.fight_id}">${core.pct(mkt)}</div></div>
        <div class="cell"><div class="t">Difference</div><div class="n" data-diff="${r.fight_id}">${core.fmtPoints(d.points)}</div></div>
      </div>
      <div class="fw-card-why" data-explain="${r.fight_id}">${esc(core.explain(r))}</div>
      <div>${fw.labelHtml(d)}</div>
      <div class="fw-notedge">${esc(core.NOT_EDGE)}</div>
    </div>`;
  };

  // ---------------------------------------------------------------------
  // Fight Week Brief signup block. One component; every placement passes a
  // page type and a block id so the saved source says where it came from.
  //   <div class="fw-brief" data-page-type="event_hub" data-block-id="after-table"></div>
  // ---------------------------------------------------------------------
  fw.BRIEF_TEXT = 'Get the next UFC card brief — model probabilities, market moves and the biggest disagreements. Free every fight week.';

  fw.renderBriefSignups = function () {
    document.querySelectorAll('.fw-brief:not([data-rendered])').forEach(el => {
      el.setAttribute('data-rendered', '1');
      const pageType = el.getAttribute('data-page-type') || 'page';
      const blockId = el.getAttribute('data-block-id') || 'brief';
      const source = `${pageType}:${blockId}`;
      const eventId = el.getAttribute('data-event-id') || document.body.getAttribute('data-event-id') || null;
      const fightId = el.getAttribute('data-fight-id') || document.body.getAttribute('data-fight-id') || null;
      const props = () => { const p = { source }; if (eventId) p.event_id = eventId; if (fightId) p.fight_id = fightId; return p; };
      el.innerHTML = `
        <div class="fw-brief-copy"><strong>Fight Week Brief</strong><span>${esc(fw.BRIEF_TEXT)}</span></div>
        <form novalidate>
          <input type="email" required placeholder="you@example.com" autocomplete="email" aria-label="Email address">
          <button type="submit">Get the brief</button>
        </form>
        <div class="fw-brief-msg" aria-live="polite"></div>
        <div class="fw-brief-fine">One email before the card, one after. Unsubscribe in one click. No sportsbook links in the email.</div>`;
      fw.onFirstView(el, () => fw.track('email_cta_view', props()));
      const form = el.querySelector('form');
      const input = el.querySelector('input[type=email]');
      const btn = el.querySelector('button');
      const msg = el.querySelector('.fw-brief-msg');
      form.addEventListener('submit', async (ev) => {
        ev.preventDefault();
        msg.textContent = ''; msg.classList.remove('ok', 'err');
        const email = String(input.value || '').trim().toLowerCase();
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
          msg.classList.add('err'); msg.textContent = 'Please enter a valid email address.';
          return;
        }
        fw.track('email_submit', props());
        btn.disabled = true; const label = btn.textContent; btn.textContent = 'Saving…';
        let ok = false, dup = false, err = null;
        try {
          // Plain insert: the table's anon policy allows INSERT only, so an
          // upsert / ON CONFLICT path is rejected by RLS. A unique-violation
          // (23505) just means they're already on the list.
          const res = await sb().from('email_subscribers').insert({ email, source });
          if (res.error) {
            if (res.error.code === '23505') dup = true; else err = res.error;
          } else ok = true;
        } catch (e) { err = e; }
        btn.disabled = false; btn.textContent = label;
        if (err) {
          msg.classList.add('err'); msg.textContent = 'Something went wrong. Try again in a minute.';
          fw.track('email_error', props());
          return;
        }
        msg.classList.add('ok');
        msg.textContent = dup ? 'You\'re already on the list — the next brief is on its way before the card.' : 'Done. The brief lands before the card.';
        fw.track('email_success', Object.assign(props(), { duplicate: dup ? 'yes' : 'no' }));
        form.reset();
      });
    });
  };

  // ---------------------------------------------------------------------
  // Hydrate a prerendered hub / fight page with fresh market numbers. The
  // markup carries data-* hooks; only market-derived cells change. The CFL
  // number is locked and is never touched here.
  // ---------------------------------------------------------------------
  fw.hydrate = async function () {
    const body = document.body;
    const page = body.getAttribute('data-page');
    const eventId = body.getAttribute('data-event-id');
    if (!page || !eventId) return;
    const fightEls = document.querySelectorAll('[data-fight-id]');
    const ids = [...new Set([...fightEls].map(e => +e.getAttribute('data-fight-id')).filter(Boolean))];
    if (!ids.length) return;

    const [market, atLock] = await Promise.all([
      safe(sb().from('v_fight_market_vigfree').select('*').in('fight_id', ids), 'hydrate market'),
      safe(sb().from('v_fight_market_at_lock').select('*').in('fight_id', ids), 'hydrate at-lock'),
    ]);
    const mk = byKey(market, 'fight_id');
    const lk = byKey(atLock, 'fight_id');
    let latest = null;

    ids.forEach(id => {
      const m = mk[id]; if (!m) return;
      if (m.last_updated && (!latest || m.last_updated > latest)) latest = m.last_updated;
      const cflA = num(attr(`[data-cfl-a="${id}"]`, 'data-value'));
      const row = {
        fight_id: id,
        fighter_a_name: attr(`[data-name-a="${id}"]`, 'data-value') || '',
        fighter_b_name: attr(`[data-name-b="${id}"]`, 'data-value') || '',
        cfl_p_a: cflA, cfl_p_b: cflA == null ? null : 1 - cflA,
        market_p_a: +m.market_p_a, market_p_b: +m.market_p_b,
        market_p_a_at_lock: lk[id] ? +lk[id].market_p_a_at_lock : null,
        market_p_b_at_lock: lk[id] ? +lk[id].market_p_b_at_lock : null,
      };
      setText(`[data-mkt-a="${id}"]`, core.pct(row.market_p_a));
      setText(`[data-mkt-b="${id}"]`, core.pct(row.market_p_b));
      setText(`[data-mkt-exact-a="${id}"]`, core.pct(row.market_p_a, 1));
      setText(`[data-mkt-exact-b="${id}"]`, core.pct(row.market_p_b, 1));
      setText(`[data-books="${id}"]`, String(m.book_count));
      setText(`[data-mkt-updated="${id}"]`, core.fmtWhen(m.last_updated));
      if (cflA != null) {
        const d = core.disagreement(row);
        const favA = cflA >= 0.5;
        setText(`[data-mkt-fav="${id}"]`, core.pct(favA ? row.market_p_a : row.market_p_b));
        setText(`[data-diff="${id}"]`, core.fmtPoints(d.points));
        setText(`[data-explain="${id}"]`, core.explain(row));
        const lab = document.querySelector(`[data-label="${id}"]`);
        if (lab) lab.innerHTML = fw.labelHtml(d);
        const mv = core.movement(row);
        if (mv) setText(`[data-move="${id}"]`, mv.label);
      }
    });
    if (latest) {
      document.querySelectorAll('[data-updated]').forEach(el => {
        el.textContent = core.fmtWhen(latest);
        el.classList.toggle('fw-stale', core.isStale(latest, 24));
      });
    }
  };
  function attr(sel, name) { const el = document.querySelector(sel); return el ? el.getAttribute(name) : null; }
  function num(v) { if (v == null || v === '') return null; const n = +v; return isNaN(n) ? null : n; }
  function setText(sel, text) { document.querySelectorAll(sel).forEach(el => { el.textContent = text; }); }

  // ---------------------------------------------------------------------
  // Page-level tracking wiring
  // ---------------------------------------------------------------------
  fw.wireTracking = function () {
    const body = document.body;
    const page = body.getAttribute('data-page');
    const eventId = body.getAttribute('data-event-id');
    const fightId = body.getAttribute('data-fight-id');
    const base = {}; if (eventId) base.event_id = eventId; if (fightId) base.fight_id = fightId;
    if (page === 'event_hub') fw.track('event_hub_view', base);
    if (page === 'fight_preview') fw.track('fight_preview_view', base);
    if (page === 'market_board') fw.track('market_board_view', base);
    if (eventId && (page === 'event_hub' || page === 'fight_preview' || page === 'market_board')) fw.recordVisit(page, eventId);

    // "Show the math" and any per-fight expander.
    document.querySelectorAll('details[data-track="fight_expand"]').forEach(d => {
      d.addEventListener('toggle', () => {
        if (!d.open) return;
        const p = Object.assign({}, base);
        const fid = d.getAttribute('data-fight-id'); if (fid) p.fight_id = fid;
        fw.track('fight_expand', p);
        if (d.hasAttribute('data-odds')) fw.track('odds_view', p);
      });
    });
    // Odds tables that are always visible count as an odds view when seen.
    document.querySelectorAll('[data-track="odds_view"]').forEach(el => {
      fw.onFirstView(el, () => {
        const p = Object.assign({}, base);
        const fid = el.getAttribute('data-fight-id'); if (fid) p.fight_id = fid;
        fw.track('odds_view', p);
      });
    });
    // Plain sportsbook links (licensed books only ever get one).
    document.addEventListener('click', (ev) => {
      const a = ev.target.closest && ev.target.closest('a[data-book]');
      if (!a) return;
      const p = Object.assign({}, base, { book: a.getAttribute('data-book') });
      const fid = a.getAttribute('data-fight-id'); if (fid) p.fight_id = fid;
      fw.track('book_click', p);
    });
  };

  // Reserved for a watchlist control; nothing on the site adds to a watchlist
  // today, so this is the one event name with no trigger.
  fw.trackWatchlistAdd = function (props) { fw.track('watchlist_add', props || {}); };

  // ---------------------------------------------------------------------
  // Card-to-card return rate (sql/retention_return_rate.sql). One anonymous
  // row per (browser, card, page, day) in hub_visits. The visitor key is a
  // random UUID this browser made up, kept for 60 days, then replaced — no
  // IP, no user agent, no account link. Insert-only; nothing reads it back
  // from the browser. Any failure is silent.
  // ---------------------------------------------------------------------
  const VISIT_KEY = 'cfl_visitor_key_v1';
  const VISIT_TTL_DAYS = 60;
  function visitorKey() {
    try {
      const raw = localStorage.getItem(VISIT_KEY);
      if (raw) {
        const o = JSON.parse(raw);
        if (o && o.key && o.until && Date.now() < o.until) return o.key;
      }
      const key = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : null;
      if (!key) return null;
      localStorage.setItem(VISIT_KEY, JSON.stringify({ key, until: Date.now() + VISIT_TTL_DAYS * 86400000 }));
      return key;
    } catch (_) { return null; }
  }
  fw.recordVisit = async function (page, eventId) {
    if (!page || !eventId) return;
    const key = visitorKey();
    if (!key) return;
    const today = new Date().toISOString().slice(0, 10);
    const stamp = `cfl_visit_${page}_${eventId}_${today}`;
    try { if (sessionStorage.getItem(stamp)) return; sessionStorage.setItem(stamp, '1'); } catch (_) { /* fine */ }
    try {
      const res = await sb().from('hub_visits').insert({ visitor_key: key, event_id: +eventId, page, seen_on: today });
      if (res.error && res.error.code !== '23505') console.debug('[fight-week] visit not recorded:', res.error.message);
    } catch (_) { /* never surface */ }
  };

  // ---------------------------------------------------------------------
  // Boot
  // ---------------------------------------------------------------------
  function boot() {
    fw.renderBriefSignups();
    fw.wireTracking();
    const page = document.body.getAttribute('data-page');
    if (page === 'event_hub' || page === 'fight_preview') fw.hydrate().catch(e => console.warn('[fight-week] hydrate failed', e));
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else setTimeout(boot, 0);

  window.cflFW = fw;
})();
