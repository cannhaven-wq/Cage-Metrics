/* ==========================================================================
   Cannon Fight Lab — shared JS
   Loaded by every page. Provides:
     - window.cflSupabase  → Supabase client
     - window.cfl          → helpers namespace
   ========================================================================== */

(function () {
  // --------- Supabase client ---------
  const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
  const SUPABASE_KEY = 'sb_publishable_boJGOA1CFN-SF14HHFGUAw_YEEm0DU8';
  // The default Supabase JS client uses a lock mechanism around auth state
  // that can get stuck in some browsers, causing all subsequent DB queries
  // to hang on a pending Promise. We pass an explicit auth config that uses
  // a no-op lock to avoid the bug. See:
  // https://github.com/supabase/auth-js/issues/762
  window.cflSupabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
      storage: window.localStorage,
      storageKey: 'cfl-auth',
      // No-op lock: we don't have multi-tab use cases that need synchronization
      // and the default lock has a hang bug. Replace with a passthrough.
      lock: async (name, acquireTimeout, fn) => fn()
    }
  });

  // --------- Helpers ---------
  const cfl = {};

  // --------- Model registry (July 2026 three-product restructure) ---------
  // The models the public site shows. All six are live. Caveats: v1/v2 don't
  // beat the closing favorite, and v5 was trained with the market line — its
  // accuracy is partly the market's own and it can't produce a pick before a
  // line exists. Each model's tagline states its limit. Story: edges.html.
  //
  // trainEnd is duplicated here (not just in model_versions) on purpose: it
  // is the client-side floor below which a model's graded stats must never be
  // displayed, even if the DB row's test_start_date is wrong. That exact bug
  // is how v6 publicly claimed a 2021-2026 "never seen" record that included
  // four years of its own training data.
  cfl.MODELS = {
    v6: {
      slot: 'roi',
      name: 'Value — beats the opener',
      tagline: 'Hunts fights where the opening line is wrong. Every pick locked at first write, never re-priced.',
      trainEnd: '2024-12-31',
      money: true,
    },
    v3: {
      slot: 'accuracy',
      name: 'Fight IQ — tape only',
      tagline: 'Predicts winners from fighter data alone. Never sees a betting line, so its number is fully independent of the market.',
      trainEnd: '2022-12-31',
      money: false,
    },
    v5: {
      slot: 'accuracy',
      name: 'Accuracy v5 — market + tape',
      tagline: 'XGBoost on 44 features including the Vegas line. Its 70% is tied to the market, so it reads best as a benchmark, not a live pre-line pick.',
      trainEnd: '2023-12-31',
      money: false,
    },
    v4: {
      slot: 'accuracy',
      name: 'Stacker — models on models',
      tagline: 'Blends v1/v2/v3 into one number, plus the opener. Sharper on a smaller, higher-conviction pick set.',
      trainEnd: '2024-12-31',
      money: false,
    },
    v2: {
      slot: 'accuracy',
      name: 'Elo — opponent quality',
      tagline: "Baseline tape stats plus a fighter Elo, so beating a contender counts more than beating a debutant.",
      trainEnd: '2022-12-31',
      money: false,
    },
    v1: {
      slot: 'accuracy',
      name: 'Baseline — tape only',
      tagline: 'The reference model: rolling fighter stats, no opponent-quality signal. Shows what every later feature actually buys.',
      trainEnd: '2022-12-31',
      money: false,
    },
  };
  cfl.PUBLIC_MODELS = ['v6', 'v3', 'v5', 'v4', 'v2', 'v1'];

  cfl.modelName = function (id, dbName) {
    return (cfl.MODELS[id] && cfl.MODELS[id].name) || dbName || id;
  };

  // One plain-English definition per model, reused by every picker and the
  // "How each model works" panel. 'engine' and 'consensus' aren't in
  // cfl.MODELS, so they're handled explicitly. Single source of truth — edit
  // the tagline in cfl.MODELS / cfl.ENGINE and it updates everywhere.
  cfl.modelDef = function (id) {
    if (id === 'engine') return cfl.ENGINE.accuracy.tagline;
    if (id === 'consensus') return 'The average call across every model shown — a fight only counts when the models agree. A useful gut-check, but only as sound as the models feeding it.';
    return (cfl.MODELS[id] && cfl.MODELS[id].tagline) || '';
  };

  // --------- Engine (July 2026 "one engine" rebuild) ---------
  // The engine is one brain with two product faces. It publishes to the
  // model_picks / model_edges tables (read via the graded views below), NOT
  // model_predictions — so it deliberately lives outside cfl.MODELS, whose
  // keys are model_version values queried against model_predictions.
  // engine_v1/engine_v2/… rows are one model family: never filter by
  // model_version (the string is provenance, shown as-is). Simulated-vs-live
  // maps to the source column ('backtest' / 'live'). Every backtest row is
  // out-of-sample by construction (walk-forward; the uncalibrated fold 0 is
  // excluded at publish), so no trainEnd window clamp applies here.
  cfl.ENGINE = {
    family: 'engine',
    accuracy: {
      name: 'Fight IQ — tape only',
      tagline: 'One calibrated winner probability per fight, built from fighter history, fight stats, and physical attributes. Never sees a betting line.',
    },
    roi: {
      name: 'Value — where the price is wrong',
      tagline: 'Flags fights where the model disagrees with the vig-free market price, with a disciplined stake attached. Live picks are locked at first write, never re-priced.',
    },
    tiers: { Lock: 0.65, Pick: 0.57 }, // mirrors cfl_engine/faces.py tier_of
  };

  // Graded-view loaders. Both views join fights server-side: hit/won are NULL
  // while the fight is unresolved (render as pending, never as a loss). Pass a
  // modifier to filter, e.g. cfl.fetchEnginePicks(q => q.eq('source', 'live')).
  cfl.fetchEnginePicks = function (mod) {
    const sb = window.cflSupabase;
    return cfl.fetchAll(() => {
      const q = sb.from('v_model_picks_graded').select('*')
        .order('event_date', { ascending: true }).order('id', { ascending: true });
      return mod ? mod(q) : q;
    });
  };
  cfl.fetchEngineEdges = function (mod) {
    const sb = window.cflSupabase;
    return cfl.fetchAll(() => {
      const q = sb.from('v_model_edges_graded').select('*')
        .order('event_date', { ascending: true }).order('id', { ascending: true });
      return mod ? mod(q) : q;
    });
  };

  // Honest out-of-sample floor for a model's graded stats: the later of the
  // DB's test_start_date and the day after the model's training cutoff.
  cfl.modelWindowStart = function (id, testStartDate) {
    const m = cfl.MODELS[id];
    let floor = testStartDate || null;
    if (m && m.trainEnd) {
      const d = new Date(m.trainEnd + 'T00:00:00Z');
      d.setUTCDate(d.getUTCDate() + 1);
      const afterTrain = d.toISOString().slice(0, 10);
      if (!floor || afterTrain > floor) floor = afterTrain;
    }
    return floor;
  };

  cfl.initials = function (name) {
    if (!name) return '?';
    return name.split(/\s+/).filter(Boolean).map(w => w[0]).join('').slice(0, 2).toUpperCase();
  };

  // Put an upcoming card's fights into true card order and drop dead bookings.
  //
  // The fights table has two decay modes this compensates for:
  //  - upserts key on ufc_fight_id, so a booking that drops off the UFCStats
  //    event page stops being updated and can keep a stale is_main_event=true
  //    forever (two "main events", the older row id winning the sort);
  //  - opponent changes create a NEW ufc_fight_id, and nothing pruned the old
  //    row, so the same fighter can appear in two fights on one card.
  //
  // Strategy, in order of trust:
  //  1. rows the scraper marked is_active=false are dropped (column may not
  //     exist yet — absent reads as undefined, which passes);
  //  2. a fighter booked in two fights keeps only the newest row (higher id);
  //  3. the real main event is resolved from the event name ("...: X vs. Y"),
  //     which is authoritative in a way the flag isn't; ties on the flag keep
  //     the newest claimant. The winning row's is_main_event is corrected in
  //     place so page labels agree with the sort;
  //  4. sort by bout_order when the scraper has written it, else main event
  //     first then insert id (id order matches page order within one scrape).
  cfl.orderCard = function (fights, eventName) {
    if (!Array.isArray(fights) || fights.length === 0) return fights || [];
    let rows = fights.filter(f => f.is_active !== false);

    const newestByFighter = new Map();
    rows.forEach(f => {
      [f.fighter_a_id, f.fighter_b_id].forEach(id => {
        if (id == null) return;
        const prev = newestByFighter.get(id);
        if (!prev || f.id > prev.id) newestByFighter.set(id, f);
      });
    });
    rows = rows.filter(f =>
      (f.fighter_a_id == null || newestByFighter.get(f.fighter_a_id) === f) &&
      (f.fighter_b_id == null || newestByFighter.get(f.fighter_b_id) === f));

    let mainRow = null;
    const m = (eventName || '').match(/:\s*(.+?)\s+vs\.?\s+(.+)$/i);
    if (m) {
      const n1 = m[1].trim().toLowerCase();
      const n2 = m[2].trim().toLowerCase();
      mainRow = rows.find(f => {
        const names = ((f.fighter_a_name || '') + '|' + (f.fighter_b_name || '')).toLowerCase();
        return names.includes(n1) && names.includes(n2);
      }) || null;
    }
    if (!mainRow) {
      const claims = rows.filter(f => f.is_main_event);
      if (claims.length) mainRow = claims.reduce((a, b) => (b.id > a.id ? b : a));
    }
    rows.forEach(f => { f.is_main_event = (f === mainRow); });

    const hasOrder = rows.some(f => f.bout_order != null);
    rows.sort((a, b) => {
      if (hasOrder && a.bout_order != null && b.bout_order != null) return a.bout_order - b.bout_order;
      if (a.is_main_event !== b.is_main_event) return a.is_main_event ? -1 : 1;
      return a.id - b.id;
    });
    return rows;
  };

  cfl.escapeHtml = function (s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  };

  cfl.formatRecord = function (w, l, d) {
    if (w == null && l == null && d == null) return '—';
    return `${w ?? 0}-${l ?? 0}-${d ?? 0}`;
  };

  cfl.formatHeight = function (inches) {
    if (inches == null) return '—';
    const ft = Math.floor(inches / 12);
    const inch = Math.round(inches % 12);
    return `${ft}'${inch}"`;
  };

  cfl.formatReach = function (inches) {
    if (inches == null) return '—';
    return `${inches}"`;
  };

  cfl.formatDate = function (isoDate) {
    if (!isoDate) return '—';
    const d = new Date(isoDate + 'T00:00:00');
    return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
  };

  cfl.formatDateShort = function (isoDate) {
    if (!isoDate) return '—';
    const d = new Date(isoDate + 'T00:00:00');
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  cfl.daysUntil = function (isoDate) {
    if (!isoDate) return null;
    const target = new Date(isoDate + 'T00:00:00');
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return Math.round((target - today) / (1000 * 60 * 60 * 24));
  };

  // --------- Current-event window ---------
  // How long a card stays on the home page / Card Lab after its own date ends,
  // before we roll over to the next upcoming event. Local time, not UTC.
  // 6h keeps a Saturday-night card up through Sunday sunrise, then rolls.
  cfl.ROLLOVER_HOURS = 6;

  // Returns { fromStr, todayStr } — the inclusive event_date range that counts
  // as "happening now". Single source of truth: index.html and card-lab.html
  // both select the current event with this window.
  cfl.eventWindow = function (nowOverride) {
    const now = nowOverride || new Date();
    const from = new Date(now.getTime() - cfl.ROLLOVER_HOURS * 3600000);
    return { fromStr: localDateStr(from), todayStr: localDateStr(now) };
  };

  function localDateStr(d) {
    const p = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  }

  // --------- Active fighter cutoff ---------
  cfl.activeCutoff = (function () {
    const d = new Date();
    d.setMonth(d.getMonth() - 24);
    return d.toISOString().slice(0, 10);
  })();

  // --------- URL helpers ---------
  cfl.fighterUrl = function (id) { return `fighter.html?id=${id}`; };
  cfl.eventUrl = function (id) { return `event.html?id=${id}`; };
  cfl.h2hUrl = function (aId, bId) {
    const params = new URLSearchParams();
    if (aId) params.set('a', aId);
    if (bId) params.set('b', bId);
    return `h2h.html?${params.toString()}`;
  };

  cfl.getQueryParam = function (key) {
    return new URLSearchParams(window.location.search).get(key);
  };

  // --------- Nav renderer ---------
  // Marks active link based on current page
  cfl.renderNav = function (active) {
    // DOM order matters on mobile: slot comes before burger so the flex layout
    // ends up [logo] ......... [slot][burger] with burger as the far-right tap
    // target (standard mobile pattern). The drawer is position:fixed so its
    // DOM position doesn't affect the bar layout.
    const navHtml = `
      <a class="cfl-logo" href="index.html">
        <span class="full">Cannon Fight <span class="accent">Lab</span></span>
        <span class="short">C<span class="accent">F</span>L</span>
      </a>
      <div class="cfl-nav-links" id="cflNavLinks">
        <a class="cfl-nav-cta-link ${active === 'home' || active === 'cardlab' ? 'active' : ''}" href="index.html#next">Card Lab</a>
        <a href="track-record.html" ${active === 'track' ? 'class="active"' : ''}>
          <span class="full">Track Record</span><span class="short">Record</span>
        </a>
        <a href="props.html" ${active === 'props' ? 'class="active"' : ''}>
          <span class="full">Prop Board</span><span class="short">Props</span>
        </a>
        <div class="cfl-nav-menu">
          <button type="button" class="cfl-nav-menu-btn ${['parlay','cardio','stats','mybook','predictor'].indexOf(active) !== -1 ? 'active' : ''}" aria-haspopup="true">Tools</button>
          <div class="cfl-nav-menu-panel">
            <a href="parlay.html" ${active === 'parlay' ? 'class="active"' : ''}>Parlay Builder</a>
            <a href="cardio.html" ${active === 'cardio' ? 'class="active"' : ''}>Cardio Scores</a>
            <a href="stats.html" ${active === 'stats' ? 'class="active"' : ''}>Factor Lab</a>
            <a href="predictor.html" ${active === 'predictor' ? 'class="active"' : ''}>Model Lab</a>
            <a href="mybook.html" ${active === 'mybook' ? 'class="active"' : ''} data-auth-only="true" style="display:none">My Book</a>
          </div>
        </div>
        <a href="pricing.html" ${active === 'pricing' ? 'class="active"' : ''}>Pricing</a>
      </div>
      <span class="cfl-nav-status" title="Model live"><span class="live-dot"></span>MODEL&nbsp;·&nbsp;LIVE</span>
      <div class="cfl-nav-slot" id="cflNavSlot"></div>
      <button class="cfl-nav-burger" id="cflNavBurger" aria-label="Menu" aria-expanded="false">
        <span></span><span></span><span></span>
      </button>
    `;
    const navEl = document.querySelector('nav.cfl-nav');
    if (navEl) {
      navEl.innerHTML = navHtml;
      // Wire the auth slot once cflAuth is available. cflAuth handles its own
      // re-rendering on auth state change so we don't need to call this again.
      if (window.cflAuth) {
        const slot = document.getElementById('cflNavSlot');
        window.cflAuth.renderNavSlot(slot);
      }
      // Mobile drawer toggle
      const burger = document.getElementById('cflNavBurger');
      const links  = document.getElementById('cflNavLinks');
      if (burger && links) {
        burger.addEventListener('click', () => {
          const open = navEl.classList.toggle('cfl-nav-open');
          burger.setAttribute('aria-expanded', open ? 'true' : 'false');
        });
        // Close on link tap (mobile)
        links.querySelectorAll('a').forEach(a => {
          a.addEventListener('click', () => {
            navEl.classList.remove('cfl-nav-open');
            burger.setAttribute('aria-expanded', 'false');
          });
        });
      }
    }
  };

  // --------- Footer renderer ---------
  cfl.renderFooter = function () {
    const footerHtml = `
      <div class="footer-logo">Cannon Fight <span class="accent">Lab</span></div>
      <div class="cfl-footer-text">Cannon Fight Lab is an analytics publication, not a sportsbook. Statistics describe historical patterns and do not predict individual fight outcomes. 21+ only. Problem gambling? Call 1-800-GAMBLER or the Tennessee REDLINE at 1-800-889-9789.</div>
      <div class="cfl-footer-links">
        <a href="about.html">About</a>
        <a href="contact.html">Contact</a>
        <a href="methodology.html">Methodology</a>
        <a href="disclaimer.html">Disclaimer</a>
        <a href="privacy.html">Privacy</a>
      </div>
    `;
    const footEl = document.querySelector('footer.cfl-footer');
    if (footEl) footEl.innerHTML = footerHtml;
  };

  // --------- Loading / error helpers ---------
  cfl.loadingHtml = function (msg) {
    return `<div class="loading-state"><div class="loading-spinner"></div><div>${cfl.escapeHtml(msg || 'Loading…')}</div></div>`;
  };

  cfl.errorHtml = function (msg) {
    return `<div class="error-state">${cfl.escapeHtml(msg)}</div>`;
  };

  // --------- Pagination helper for Supabase queries ---------
  // Use to grab >1000 rows, since Supabase caps per-call at 1000
  cfl.fetchAll = async function (queryBuilder) {
    let all = [];
    let from = 0;
    const pageSize = 1000;
    while (true) {
      const { data, error } = await queryBuilder().range(from, from + pageSize - 1);
      if (error) throw error;
      if (!data || data.length === 0) break;
      all = all.concat(data);
      if (data.length < pageSize) break;
      from += pageSize;
    }
    return all;
  };

  // --------- Fighter chip (compact representation) ---------
  cfl.fighterChip = function (fighter, opts) {
    opts = opts || {};
    const size = opts.size || 'md';
    const link = opts.link !== false;
    const inner = `
      <div class="cfl-avatar ${size}">${cfl.escapeHtml(cfl.initials(fighter.name))}</div>
      <div class="fighter-info">
        <div class="fighter-name">${cfl.escapeHtml(fighter.name)}</div>
        ${opts.subline ? `<div class="fighter-meta">${cfl.escapeHtml(opts.subline)}</div>` : ''}
      </div>
    `;
    if (link && fighter.id) {
      return `<a href="${cfl.fighterUrl(fighter.id)}" class="fighter-chip-link">${inner}</a>`;
    }
    return `<div class="fighter-chip">${inner}</div>`;
  };

  // --------- Traffic-funnel widgets ---------
  // Drop a signup CTA into any page:
  //   <div class="cfl-funnel-cta" data-source="fighters-bottom"></div>
  // …then call cfl.renderFunnelCtas() after the page loads. We auto-hide
  // each banner if the visitor is already signed in, so it never nags
  // existing users.
  cfl.renderFunnelCtas = function () {
    const els = document.querySelectorAll('.cfl-funnel-cta:not([data-cfl-rendered])');
    if (!els.length) return;
    const signedIn = window.cflAuth && window.cflAuth.isSignedIn && window.cflAuth.isSignedIn();
    els.forEach(el => {
      el.setAttribute('data-cfl-rendered', '1');
      if (signedIn) { el.style.display = 'none'; return; }
      const source = el.getAttribute('data-source') || 'inline';
      const headline = el.getAttribute('data-headline') || 'Free during beta — every edge factor unlocked.';
      const sub = el.getAttribute('data-sub') || 'Create a free account to track your picks, see every model verdict, and get the weekly preview email.';
      el.innerHTML = `
        <div class="cfl-funnel-cta-inner">
          <div class="cfl-funnel-cta-copy">
            <strong>${cfl.escapeHtml(headline)}</strong>
            <span>${cfl.escapeHtml(sub)}</span>
          </div>
          <div class="cfl-funnel-cta-actions">
            <a class="btn" href="/signup.html?src=${encodeURIComponent(source)}">Create free account →</a>
          </div>
        </div>
      `;
    });
    // Re-evaluate on auth change so the banner disappears immediately after
    // signup without a hard reload.
    if (window.cflAuth && window.cflAuth.onAuthChange) {
      window.cflAuth.onAuthChange((user) => {
        if (user) {
          document.querySelectorAll('.cfl-funnel-cta[data-cfl-rendered]').forEach(el => { el.style.display = 'none'; });
        }
      });
    }
  };

  // Email-only lead magnet. Drop:
  //   <div class="cfl-email-capture" data-source="home-footer"></div>
  // …then call cfl.renderEmailCaptures(). Submitting writes to the
  // email_subscribers table; the digest workflow picks it up from there.
  cfl.renderEmailCaptures = function () {
    const els = document.querySelectorAll('.cfl-email-capture:not([data-cfl-rendered])');
    els.forEach(el => {
      el.setAttribute('data-cfl-rendered', '1');
      const source = el.getAttribute('data-source') || 'inline';
      const headline = el.getAttribute('data-headline') || 'Weekly fight preview, free.';
      const sub = el.getAttribute('data-sub') || 'Get every upcoming UFC card with the model’s verdict in your inbox.';
      el.innerHTML = `
        <div class="cfl-email-capture-inner">
          <div class="cfl-email-capture-copy">
            <strong>${cfl.escapeHtml(headline)}</strong>
            <span>${cfl.escapeHtml(sub)}</span>
          </div>
          <form class="cfl-email-capture-form" novalidate>
            <input type="email" required placeholder="you@example.com" autocomplete="email" aria-label="Email address">
            <button type="submit">Subscribe</button>
          </form>
          <div class="cfl-email-capture-msg" aria-live="polite"></div>
        </div>
      `;
      const form = el.querySelector('form');
      const input = el.querySelector('input[type=email]');
      const btn = el.querySelector('button');
      const msg = el.querySelector('.cfl-email-capture-msg');
      form.addEventListener('submit', async (ev) => {
        ev.preventDefault();
        msg.textContent = '';
        msg.classList.remove('err', 'ok');
        if (!window.cflAuth || !window.cflAuth.subscribeEmail) {
          msg.classList.add('err');
          msg.textContent = 'Subscription is temporarily unavailable.';
          return;
        }
        btn.disabled = true;
        const originalLabel = btn.textContent;
        btn.textContent = 'Submitting…';
        const { error } = await window.cflAuth.subscribeEmail(input.value, source);
        btn.disabled = false;
        btn.textContent = originalLabel;
        if (error) {
          msg.classList.add('err');
          msg.textContent = error.message || 'Something went wrong. Try again.';
          return;
        }
        msg.classList.add('ok');
        msg.textContent = 'Subscribed. Check your inbox before the next card.';
        form.reset();
      });
    });
  };

  // Auto-render funnel widgets whenever the DOM is ready. Safe to call this
  // even on pages that don't include any widget elements — the queries return
  // empty NodeLists and short-circuit.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      cfl.renderFunnelCtas();
      cfl.renderEmailCaptures();
    });
  } else {
    setTimeout(() => { cfl.renderFunnelCtas(); cfl.renderEmailCaptures(); }, 0);
  }

  window.cfl = cfl;
})();
