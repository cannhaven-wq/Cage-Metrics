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

  cfl.initials = function (name) {
    if (!name) return '?';
    return name.split(/\s+/).filter(Boolean).map(w => w[0]).join('').slice(0, 2).toUpperCase();
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
        <a class="cfl-nav-cta-link ${active === 'cardlab' ? 'active' : ''}" href="card-lab.html">Card Lab</a>
        <a href="picks.html" ${active === 'picks' ? 'class="active"' : ''}>Picks</a>
        <a href="index.html" ${active === 'home' ? 'class="active"' : ''}>
          <span class="full">Next Card</span><span class="short">Card</span>
        </a>
        <a href="track-record.html" ${active === 'track' ? 'class="active"' : ''}>
          <span class="full">Track Record</span><span class="short">Record</span>
        </a>
        <div class="cfl-nav-menu">
          <button type="button" class="cfl-nav-menu-btn ${['parlay','cardio','stats','mybook','predictor'].indexOf(active) !== -1 ? 'active' : ''}" aria-haspopup="true">Tools</button>
          <div class="cfl-nav-menu-panel">
            <a href="parlay.html" ${active === 'parlay' ? 'class="active"' : ''}>Parlay Builder</a>
            <a href="cardio.html" ${active === 'cardio' ? 'class="active"' : ''}>Cardio Scores</a>
            <a href="stats.html" ${active === 'stats' ? 'class="active"' : ''}>Stat Finder</a>
            <a href="predictor.html" ${active === 'predictor' ? 'class="active"' : ''}>Model Lab</a>
            <a href="mybook.html" ${active === 'mybook' ? 'class="active"' : ''} data-auth-only="true" style="display:none">My Book</a>
          </div>
        </div>
        <a href="pricing.html" ${active === 'pricing' ? 'class="active"' : ''}>Pricing</a>
      </div>
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
