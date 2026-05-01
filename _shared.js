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
  window.cflSupabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY);

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
    const navHtml = `
      <a class="cfl-logo" href="index.html">
        <span class="full">Cannon Fight <span class="accent">Lab</span></span>
        <span class="short">C<span class="accent">F</span>L</span>
      </a>
      <div class="cfl-nav-links">
        <a href="index.html" ${active === 'home' ? 'class="active"' : ''}>Next event</a>
        <a href="fighters.html" ${active === 'fighters' ? 'class="active"' : ''}>Fighters</a>
        <a href="h2h.html" ${active === 'h2h' ? 'class="active"' : ''}>Head-to-head</a>
        <a href="parlay.html" ${active === 'parlay' ? 'class="active"' : ''}>Parlay builder</a>
        <a href="stats.html" ${active === 'stats' ? 'class="active"' : ''}>Stat finder</a>
        <span class="cfl-nav-tag">Beta</span>
      </div>
    `;
    const navEl = document.querySelector('nav.cfl-nav');
    if (navEl) navEl.innerHTML = navHtml;
  };

  // --------- Footer renderer ---------
  cfl.renderFooter = function () {
    const footerHtml = `
      <div class="footer-logo">Cannon Fight <span class="accent">Lab</span></div>
      <div class="cfl-footer-text">Stats for entertainment purposes only. Always gamble responsibly. 1-800-GAMBLER</div>
      <div class="cfl-footer-links">
        <a href="about.html">About</a>
        <a href="contact.html">Contact</a>
        <a href="disclaimer.html">Disclaimer</a>
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

  window.cfl = cfl;
})();
