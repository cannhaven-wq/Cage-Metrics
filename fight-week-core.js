/* ==========================================================================
   Cannon Fight Lab — fight-week core (shared by the browser and the build)
   --------------------------------------------------------------------------
   Pure helpers behind the Event Hub, fight pages, the Market Board and the
   homepage. No DOM, no network. Loaded with <script src="/fight-week-core.js">
   in the browser (exposes window.cflFightWeek) and require()'d by
   build/prerender.js and build/send-digest.js, the same way edges.js is shared
   with the snapshotter.

   Every number a page shows comes from the database rows passed in here:
     - the CFL number is the LOCKED forecast (v_fight_locked_forecast) — never
       recomputed at render time;
     - the market number is vig-free (v_fight_market_vigfree / _at_lock);
   this file only formats, labels and orders them.

   Wording rules (COPY_STYLE.md + the September 2026 doctrine): plain English,
   the gap between the two numbers is called a disagreement — never an edge, a
   lock, a value bet or a best bet. Every disagreement block carries NOT_EDGE.
   ========================================================================== */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.cflFightWeek = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const SITE = 'https://cannonfightlab.com';

  // The two sentences every disagreement surface carries, verbatim.
  const NOT_EDGE = 'A disagreement is not a proven betting edge.';
  const STANDARD_LINE = 'CFL publishes model forecasts and market analysis, not handicapper picks.';
  const LOCKED_LINE = 'Predictions locked before results.';

  // Display thresholds (points of probability). These label a gap; they do not
  // change any model, pick rule or threshold.
  const AGREE_POINTS = 5;    // under this the two numbers "mostly agree"
  const BIG_POINTS = 10;     // at or above this it is a "big disagreement"
  const HUGE_POINTS = 25;    // flagged as unusually large — check the matchup

  // ---- slug (same rule as build/slug.js — keep in step) ----
  function slugify(s) {
    return String(s == null ? '' : s)
      .toLowerCase()
      .replace(/'/g, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'item';
  }

  function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  // ---- URLs ----
  // The Event Hub lives at the event's /e/ stub path (that stub becomes a full
  // page once the card has a locked record). Fight pages live at /preview/.
  function hubPath(event) { return `/e/${slugify(event.name)}-${event.id}.html`; }
  function fightPath(fight) {
    const id = fight.id != null ? fight.id : fight.fight_id;
    return `/preview/${slugify(fight.fighter_a_name)}-vs-${slugify(fight.fighter_b_name)}-${id}.html`;
  }
  function fighterPath(id) { return `/fighter.html?id=${id}`; }

  // ---- odds maths ----
  function americanFromProb(p) {
    if (p == null || !(p > 0) || !(p < 1)) return null;
    return Math.round(p >= 0.5 ? (-100 * p) / (1 - p) : (100 * (1 - p)) / p);
  }
  function probFromAmerican(o) {
    if (o == null || isNaN(o)) return null;
    return o < 0 ? (-o) / (-o + 100) : 100 / (o + 100);
  }
  function fmtAmerican(o) {
    if (o == null || isNaN(o)) return '—';
    return (o > 0 ? '+' : '') + String(Math.round(o));
  }
  // The better price for a bettor is the one that pays more: higher American.
  function betterPrice(a, b) {
    if (a == null) return b; if (b == null) return a;
    return a >= b ? a : b;
  }

  function pct(p, digits) {
    if (p == null || isNaN(p)) return '—';
    return (100 * p).toFixed(digits == null ? 0 : digits) + '%';
  }
  // Whole points of probability, signed (positive = CFL higher on that side).
  function diffPoints(cflP, mktP) {
    if (cflP == null || mktP == null) return null;
    return Math.round((cflP - mktP) * 100);
  }
  function fmtPoints(d) {
    if (d == null) return '—';
    return (d > 0 ? '+' : '') + d + (Math.abs(d) === 1 ? ' pt' : ' pts');
  }

  function lastName(n) { const p = String(n || '').trim().split(/\s+/); return p[p.length - 1] || n; }

  // ---- labels ----
  // Which corner does CFL favour, and how much do the two numbers differ on
  // that corner? The label is about the CFL-favoured fighter so a reader can
  // say "CFL is higher on Van" in one breath.
  function disagreement(row) {
    if (row.cfl_p_a == null) return { kind: 'no_forecast', label: 'No locked forecast', points: null, side: null };
    if (row.market_p_a == null) return { kind: 'no_market', label: 'No sportsbook price yet', points: null, side: null };
    const side = row.cfl_p_a >= 0.5 ? 'a' : 'b';
    const cfl = side === 'a' ? row.cfl_p_a : row.cfl_p_b;
    const mkt = side === 'a' ? row.market_p_a : row.market_p_b;
    const points = diffPoints(cfl, mkt);
    const abs = Math.abs(points);
    let label, kind;
    if (abs < AGREE_POINTS) { label = 'Mostly agrees'; kind = 'agree'; }
    else if (points > 0) { label = 'CFL higher'; kind = 'cfl_higher'; }
    else { label = 'Market higher'; kind = 'market_higher'; }
    return { kind, label, points, side, abs, big: abs >= BIG_POINTS, huge: abs >= HUGE_POINTS };
  }

  // One plain sentence explaining the gap, in the CFL-favoured fighter's terms.
  function explain(row) {
    const d = disagreement(row);
    const nameA = lastName(row.fighter_a_name), nameB = lastName(row.fighter_b_name);
    if (d.kind === 'no_forecast') return 'CFL has not locked a forecast for this fight yet.';
    const favName = row.cfl_p_a >= 0.5 ? nameA : nameB;
    const cfl = row.cfl_p_a >= 0.5 ? row.cfl_p_a : row.cfl_p_b;
    if (d.kind === 'no_market') {
      return `CFL puts ${favName} at ${pct(cfl)}. No sportsbook has posted a price yet, so there is nothing to compare it to.`;
    }
    const mkt = row.cfl_p_a >= 0.5 ? row.market_p_a : row.market_p_b;
    const base = `CFL puts ${favName} at ${pct(cfl)}; the books, with their cut removed, say ${pct(mkt)}.`;
    if (d.kind === 'agree') return `${base} The two numbers are within ${AGREE_POINTS} points — they mostly agree.`;
    const dir = d.kind === 'cfl_higher' ? 'higher' : 'lower';
    let s = `${base} CFL is ${d.abs} points ${dir} on ${favName} than the market.`;
    if (d.huge) s += ' That gap is unusually large — the model may be missing something the market knows, so treat it as a question, not an answer.';
    return s;
  }

  // Line movement since the forecast was locked, on the CFL-favoured corner.
  function movement(row) {
    if (row.cfl_p_a == null || row.market_p_a == null) return null;
    const side = row.cfl_p_a >= 0.5 ? 'a' : 'b';
    const now = side === 'a' ? row.market_p_a : row.market_p_b;
    const then = row.market_p_a_at_lock == null ? null
      : (side === 'a' ? row.market_p_a_at_lock : row.market_p_b_at_lock);
    if (then == null) return { side, then: null, now, points: null, label: 'No sportsbook price on file at lock time' };
    const points = diffPoints(now, then);
    // "Toward" means the market number moved in the direction of CFL's
    // number on that corner — whichever side of the market CFL sits on.
    const cflFav = side === 'a' ? row.cfl_p_a : row.cfl_p_b;
    const toward = (points > 0 && cflFav > then) || (points < 0 && cflFav < then);
    const signed = (points > 0 ? '+' : '') + points;
    let label;
    if (Math.abs(points) < 1) label = 'Unchanged since lock';
    else if (toward) label = `Market moved toward CFL (${signed} pts)`;
    else label = `Market moved away from CFL (${signed} pts)`;
    return { side, then, now, points, toward, label };
  }

  // Engine tiers are internal words. What the reader gets is how sure the
  // model is, in plain terms.
  function confidenceLabel(tier, p) {
    const t = String(tier || '').toLowerCase();
    if (t === 'lock') return 'High confidence';
    if (t === 'pick') return 'Moderate confidence';
    if (t === 'lean') return 'Slight lean';
    if (p != null) return p >= 0.65 ? 'High confidence' : (p >= 0.57 ? 'Moderate confidence' : 'Slight lean');
    return '';
  }

  // ---- time ----
  function fmtWhen(ts, now) {
    if (!ts) return 'unknown';
    const d = new Date(ts);
    if (isNaN(d)) return 'unknown';
    const n = now ? new Date(now) : new Date();
    const mins = Math.round((n - d) / 60000);
    let rel;
    if (mins < 1) rel = 'just now';
    else if (mins < 60) rel = `${mins} min ago`;
    else if (mins < 48 * 60) rel = `${Math.round(mins / 60)} h ago`;
    else rel = `${Math.round(mins / 1440)} days ago`;
    const abs = d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'America/Chicago' }) + ' CT';
    return `${rel} (${abs})`;
  }
  function fmtStamp(ts) {
    if (!ts) return '—';
    const d = new Date(ts);
    if (isNaN(d)) return '—';
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'America/Chicago' }) + ' CT';
  }
  function isStale(ts, hours, now) {
    if (!ts) return true;
    const d = new Date(ts);
    if (isNaN(d)) return true;
    const n = now ? new Date(now) : new Date();
    return (n - d) > (hours == null ? 24 : hours) * 3600000;
  }
  function fmtDate(isoDate) {
    if (!isoDate) return '';
    const d = new Date(isoDate + 'T00:00:00');
    return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
  }
  function fmtLongDate(isoDate) {
    if (!isoDate) return '';
    const d = new Date(isoDate + 'T00:00:00');
    return d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
  }

  // ---- card order ----
  // Same rule as cfl.orderCard in _shared.js (dead-booking cleanup + main
  // event from the event name + bout_order when present). Duplicated here so
  // the build can order a card without a browser.
  function orderCard(fights, eventName) {
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
      const n1 = m[1].trim().toLowerCase(), n2 = m[2].trim().toLowerCase();
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
  }

  // ---- assembly ----
  // Join the four data sets into one row per fight. `market` and `atLock` are
  // keyed by fight_id; `forecasts` too. Returns rows in card order, each with
  // the disagreement/movement computed once.
  function assembleCard(event, fights, forecasts, market, atLock) {
    const ordered = orderCard(fights.slice(), event && event.name);
    return ordered.map(f => {
      const fc = forecasts[f.id] || null;
      const mk = market[f.id] || null;
      const lk = atLock[f.id] || null;
      const row = {
        fight: f,
        fight_id: f.id,
        event_id: f.event_id,
        fighter_a_id: f.fighter_a_id,
        fighter_b_id: f.fighter_b_id,
        fighter_a_name: f.fighter_a_name,
        fighter_b_name: f.fighter_b_name,
        weight_class: f.weight_class,
        is_main_event: !!f.is_main_event,
        is_title_fight: !!f.is_title_fight,
        winner_id: f.winner_id || null,
        method: f.method || null,
        end_round: f.end_round || null,
        cfl_p_a: fc ? +fc.cfl_p_a : null,
        cfl_p_b: fc ? +fc.cfl_p_b : null,
        pick_side: fc ? fc.pick_side : null,
        pick_fighter_id: fc ? fc.pick_fighter_id : null,
        tier: fc ? fc.tier : null,
        model_version: fc ? fc.model_version : null,
        locked_at: fc ? fc.locked_at : null,
        record_source: fc ? fc.record_source : null,
        snapshot_at: fc ? fc.snapshot_at : null,
        forecast_hit: fc ? fc.forecast_hit : null,
        market_p_a: mk && mk.market_p_a != null ? +mk.market_p_a : null,
        market_p_b: mk && mk.market_p_b != null ? +mk.market_p_b : null,
        book_count: mk ? mk.book_count : 0,
        last_updated: mk ? mk.last_updated : null,
        market_p_a_at_lock: lk && lk.market_p_a_at_lock != null ? +lk.market_p_a_at_lock : null,
        market_p_b_at_lock: lk && lk.market_p_b_at_lock != null ? +lk.market_p_b_at_lock : null,
        book_count_at_lock: lk ? lk.book_count_at_lock : 0,
        quoted_at_lock: lk ? lk.quoted_at : null,
      };
      row.disagree = disagreement(row);
      row.move = movement(row);
      return row;
    });
  }

  // Summary numbers for a card: fights analyzed, big disagreements, freshest
  // odds timestamp, grading status.
  function summarize(rows) {
    const analyzed = rows.filter(r => r.cfl_p_a != null);
    const priced = analyzed.filter(r => r.market_p_a != null);
    const big = priced.filter(r => r.disagree.big);
    let lastUpdated = null;
    rows.forEach(r => { if (r.last_updated && (!lastUpdated || r.last_updated > lastUpdated)) lastUpdated = r.last_updated; });
    let lockedAt = null;
    analyzed.forEach(r => { if (r.locked_at && (!lockedAt || r.locked_at < lockedAt)) lockedAt = r.locked_at; });
    const settled = analyzed.filter(r => r.winner_id != null);
    const hits = settled.filter(r => r.forecast_hit === true).length;
    return {
      fights: rows.length,
      analyzed: analyzed.length,
      priced: priced.length,
      big: big.length,
      lastUpdated,
      lockedAt,
      settled: settled.length,
      hits,
      misses: settled.length - hits,
      allSettled: rows.length > 0 && rows.every(r => r.winner_id != null),
      anySettled: settled.length > 0,
    };
  }

  // Biggest disagreements first (by absolute points), priced fights only.
  function biggest(rows, n) {
    return rows.filter(r => r.disagree.points != null)
      .slice().sort((x, y) => y.disagree.abs - x.disagree.abs)
      .slice(0, n == null ? rows.length : n);
  }

  // Biggest moves since lock, when both sides are on file.
  function biggestMoves(rows, n) {
    return rows.filter(r => r.move && r.move.points != null)
      .slice().sort((x, y) => Math.abs(y.move.points) - Math.abs(x.move.points))
      .slice(0, n == null ? rows.length : n);
  }

  // Post-card: the biggest hit and the biggest miss, measured by how far the
  // locked CFL number was from the market on the corner CFL favoured. Both
  // come back so the caller cannot show one without the other.
  function hitAndMiss(rows) {
    const graded = rows.filter(r => r.forecast_hit != null && r.cfl_p_a != null);
    const byConf = g => g.slice().sort((x, y) => Math.max(y.cfl_p_a, y.cfl_p_b) - Math.max(x.cfl_p_a, x.cfl_p_b));
    const hits = byConf(graded.filter(r => r.forecast_hit === true));
    const misses = byConf(graded.filter(r => r.forecast_hit === false));
    return { hit: hits[0] || null, miss: misses[0] || null, hits: hits.length, misses: misses.length };
  }

  return {
    SITE, NOT_EDGE, STANDARD_LINE, LOCKED_LINE,
    AGREE_POINTS, BIG_POINTS, HUGE_POINTS,
    slugify, escapeHtml, hubPath, fightPath, fighterPath,
    americanFromProb, probFromAmerican, fmtAmerican, betterPrice,
    pct, diffPoints, fmtPoints, lastName,
    disagreement, explain, movement, confidenceLabel,
    fmtWhen, fmtStamp, isStale, fmtDate, fmtLongDate,
    orderCard, assembleCard, summarize, biggest, biggestMoves, hitAndMiss,
  };
});
