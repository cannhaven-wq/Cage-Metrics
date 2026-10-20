/* ==========================================================================
   market-chart.js — the movement chart, and the rules it cannot break.

   PLAIN ENGLISH: the line is the middle sportsbook price over time. Every
   point on it comes from THE SAME sportsbooks. If a book starts quoting
   halfway through the window it does not join the line halfway through,
   because a line that gains a book shows a step no market actually made.

   THE FOUR RULES, and why each is here rather than in the page:

    1. ONE FIXED COHORT for the whole plotted window. The cohort is decided in
       SQL (`v_fight_chart_series`, the `broad_baseline` matched cohort) and
       this file asserts it rather than trusting it: if `cohort_books` is not
       identical on every point, the series is REFUSED and an error state is
       rendered. A chart is the easiest place to hide a cohort change, so it
       is the place to check hardest.
    2. NEVER INTERPOLATE, and never fabricate an x. Every point is a real
       capture instant. Between its own quotes a book's price does not move —
       the number it posted stands until it posts another — so the line is
       drawn as a STEP, not a slope. A diagonal between two captures would
       claim the price passed through values it never held.
    3. REFUSE RATHER THAN THIN. Below `MIN_COHORT_BOOKS` there is no consensus
       line at all. Not a dashed line, not a shorter window, not a smaller
       cohort quietly substituted.
    4. THE COHORT SIZE IS ALWAYS ON SCREEN, not only in a tooltip. A reader
       who cannot see how many books a line is built from cannot judge it.

   Per-book lines are exempt from rules 1 and 3: one sportsbook's own quotes
   are observations, not an average, so there is no cohort to keep fixed.
   Rule 2 still applies — they are stepped too.

   Renders inline SVG. No chart library, because this repo has no bundler and
   a 60KB dependency for one line chart is a bad trade.

   Depends on: _shared.js (cfl.escapeHtml), market.js (M.fmtPct, M.fmtStampUtc).
   ========================================================================== */
(function () {
  'use strict';

  const C = {};

  // Mirrored in market_chart_views.sql, market_horizon_views.sql (MIN_BOOKS)
  // and market.js (MIN_MATCHED_BOOKS). Change all of them together.
  C.MIN_COHORT_BOOKS = 3;

  // Site tokens, not a new palette. The consensus is the emphasis line; the
  // per-book lines are recessive ink, deliberately NOT a set of peer hues —
  // seven categorical colours on one axis is unreadable and cycling them is
  // worse. Identity comes from hover, direct labels and the legend, never from
  // colour alone. Checked against the #0b0e12 surface: consensus↔selected
  // CVD ΔE 15.5 (protan), normal-vision 23.4, both above threshold, all
  // contrast ≥ 3:1.
  const INK = {
    consensus: '#2fdccb',   // --probe
    book:      '#6b7480',   // --text-3, recessive
    selected:  '#ffb547',   // --amber, one highlighted book
    grid:      '#1a1f27',   // --line
    axis:      '#6b7480',
    surface:   '#0b0e12'    // --panel-2
  };

  const PAD = { t: 4, r: 9, b: 5, l: 12 };

  function esc(s) { return window.cfl ? cfl.escapeHtml(String(s)) : String(s); }
  function num(v) { const n = +v; return isFinite(n) ? n : null; }

  /* ----------------------------------------------------------------------
     validateSeries — rule 1, enforced rather than assumed.
     Returns { ok, reason, cohortBooks, points }.
     ---------------------------------------------------------------------- */
  C.validateSeries = function (rows, meta) {
    const status = (meta && meta.series_status) || 'no_broad_capture';
    if (status !== 'ok') {
      return { ok: false, reason: status, cohortBooks: (meta && +meta.cohort_books) || 0, points: [] };
    }
    if (!Array.isArray(rows) || rows.length < 2) {
      // One point is not a history. Two is the minimum that can show a change.
      return { ok: false, reason: 'not_enough_history',
               cohortBooks: (meta && +meta.cohort_books) || 0, points: [] };
    }
    const sizes = {};
    rows.forEach(r => { sizes[+r.cohort_books] = true; });
    const distinct = Object.keys(sizes);
    if (distinct.length !== 1) {
      // The one thing this chart exists to prevent. Refuse loudly.
      return { ok: false, reason: 'cohort_changed_mid_series',
               cohortBooks: 0, points: [], detail: distinct.join(', ') };
    }
    const cohortBooks = +distinct[0];
    if (cohortBooks < C.MIN_COHORT_BOOKS) {
      return { ok: false, reason: 'insufficient_matched_books', cohortBooks, points: [] };
    }
    const points = rows
      .map(r => ({ t: Date.parse(r.at), p: num(r.market_p_a) }))
      .filter(d => isFinite(d.t) && d.p !== null)
      .sort((a, b) => a.t - b.t);
    if (points.length < 2) {
      return { ok: false, reason: 'not_enough_history', cohortBooks, points: [] };
    }
    return { ok: true, reason: null, cohortBooks, points };
  };

  /* ----------------------------------------------------------------------
     Honest empty states. Every refusal names itself; none is a bare dash.
     ---------------------------------------------------------------------- */
  C.refusalCopy = function (reason, cohortBooks, detail) {
    switch (reason) {
      case 'no_broad_capture':
        return {
          head: 'No movement chart yet',
          body: 'CFL has not seen this fight priced by ' + C.MIN_COHORT_BOOKS +
                ' different sportsbooks at once, so there is no comparable ' +
                'market to plot. The chart appears once three books are quoting.'
        };
      case 'insufficient_matched_books':
        return {
          head: 'No movement chart yet',
          body: 'Only ' + cohortBooks + ' sportsbook' + (cohortBooks === 1 ? '' : 's') +
                ' quoted both at the start of the window and now. We need ' +
                C.MIN_COHORT_BOOKS + ' to draw a line that means the same thing ' +
                'at both ends, and we would rather show nothing than a line ' +
                'built on a changing set of books.'
        };
      case 'not_enough_history':
        return {
          head: 'Not enough history yet',
          body: 'We have only captured this market once since three books ' +
                'started quoting. A second capture gives the line something to move between.'
        };
      case 'cohort_changed_mid_series':
        return {
          head: 'Chart withheld — the data failed its own check',
          body: 'The sportsbooks behind this line were not identical at every ' +
                'point (' + esc(detail || '') + '), which would make the line show a ' +
                'step the market never made. Rather than draw it, CFL is ' +
                'refusing it. This is a bug on our side, not a quiet market.'
        };
      default:
        return { head: 'No movement chart', body: 'No comparable market history to plot.' };
    }
  };

  /* ----------------------------------------------------------------------
     buildSvg — a stepped line, one y axis, real x positions.
     ---------------------------------------------------------------------- */
  function scaleMaker(points, w, h, yLo, yHi) {
    const t0 = points[0].t, t1 = points[points.length - 1].t;
    const span = Math.max(1, t1 - t0);
    return {
      x: t => PAD.l + ((t - t0) / span) * (w - PAD.l - PAD.r),
      y: p => PAD.t + (1 - (p - yLo) / Math.max(0.0001, yHi - yLo)) * (h - PAD.t - PAD.b),
      t0, t1
    };
  }

  // Rule 2: a step path. Horizontal to the next capture instant, then vertical
  // to the new value. Never a diagonal.
  function stepPath(points, sc) {
    let d = '';
    points.forEach((pt, i) => {
      const x = sc.x(pt.t), y = sc.y(pt.p);
      if (i === 0) { d += 'M' + x.toFixed(1) + ' ' + y.toFixed(1); return; }
      d += ' H' + x.toFixed(1) + ' V' + y.toFixed(1);
    });
    return d;
  }

  C.render = function (el, opts) {
    const o = opts || {};
    const meta = o.meta || {};
    const v = C.validateSeries(o.series || [], meta);
    const nameA = o.nameA || 'corner A';
    const nameB = o.nameB || 'corner B';

    if (!v.ok) {
      const c = C.refusalCopy(v.reason, v.cohortBooks, v.detail);
      el.innerHTML =
        '<div class="mc-empty"><div class="mc-empty-h">' + esc(c.head) + '</div>' +
        '<div class="mc-empty-b">' + esc(c.body) + '</div></div>';
      return { ok: false, reason: v.reason };
    }

    // viewBox units. 100x34 rather than a square-ish box: a time series wants
    // to be wide. CSS caps the pixel height, and because the background lives
    // on the CSS rather than on a <rect>, the letterboxing that cap creates is
    // invisible instead of showing as bars either side.
    const W = 100, H = 34;
    const ps = v.points;
    // One y axis, always. Padded to the data with a floor of 10 points of
    // range so a quiet market does not render as dramatic noise.
    let lo = Math.min.apply(null, ps.map(d => d.p));
    let hi = Math.max.apply(null, ps.map(d => d.p));
    const mid = (lo + hi) / 2, half = Math.max(0.05, (hi - lo) * 0.65);
    lo = Math.max(0, mid - half); hi = Math.min(1, mid + half);

    const sc = scaleMaker(ps, W, H, lo, hi);
    const books = Array.isArray(o.books) ? o.books : [];
    const showBooks = !!o.showBooks && books.length > 0;

    // Per-book lines first, so the consensus sits on top of them.
    let bookPaths = '';
    if (showBooks) {
      const byBook = {};
      books.forEach(r => {
        const t = Date.parse(r.at), p = num(r.fair_a);
        if (!isFinite(t) || p === null || t < sc.t0) return;
        (byBook[r.book_id] = byBook[r.book_id] || { name: r.book_name, pts: [] }).pts.push({ t, p });
      });
      Object.keys(byBook).forEach(id => {
        const b = byBook[id];
        b.pts.sort((x, y) => x.t - y.t);
        if (b.pts.length < 2) return;
        const sel = String(o.selectedBook || '') === String(id);
        bookPaths += '<path d="' + stepPath(b.pts, sc) + '" fill="none" ' +
          'stroke="' + (sel ? INK.selected : INK.book) + '" ' +
          'stroke-width="' + (sel ? 0.5 : 0.28) + '" ' +
          'stroke-opacity="' + (sel ? 1 : 0.55) + '" ' +
          'vector-effect="non-scaling-stroke" data-book="' + esc(id) + '"></path>';
      });
    }

    // Grid lines live in the SVG; their LABELS do not. Text inside a scaled
    // viewBox scales with the chart — at desktop width these rendered around
    // 19px. HTML labels positioned over the plot keep the site's type scale and
    // its text tokens, which is what the labels should wear anyway.
    const gy = [hi, (lo + hi) / 2, lo];
    const grid = gy.map(p =>
      '<line x1="' + PAD.l + '" x2="' + (W - PAD.r) + '" y1="' + sc.y(p).toFixed(1) +
      '" y2="' + sc.y(p).toFixed(1) + '" stroke="' + INK.grid + '" stroke-width="0.15"></line>'
    ).join('');
    const axisLabels = gy.map(p =>
      '<span class="mc-ylab" style="top:' + ((sc.y(p) / H) * 100).toFixed(2) + '%">' +
      Math.round(p * 100) + '%</span>'
    ).join('');

    // Direct label on the last point — identity without relying on colour.
    const last = ps[ps.length - 1];
    const lx = sc.x(last.t), ly = sc.y(last.p);

    el.innerHTML =
      '<div class="mc-wrap">' +
        // preserveAspectRatio="none" so the viewBox fills the element exactly. Two
        // reasons, and the first is a correctness bug rather than a preference:
        // the HTML axis labels are positioned as a percentage of the ELEMENT, so
        // any letterboxing puts them out of line with their own grid rows. It
        // also stops a capped height wasting a third of the width. Strokes keep
        // their real weight via vector-effect, and no SVG text survives here, so
        // nothing that would distort is left inside.
        '<svg class="mc-svg" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" role="img" ' +
          'aria-label="Vig-free consensus probability for ' + esc(nameA) +
          ' over time, from ' + esc(C.MIN_COHORT_BOOKS) + ' or more sportsbooks">' +
          grid + bookPaths +
          '<path d="' + stepPath(ps, sc) + '" fill="none" stroke="' + INK.consensus +
            '" stroke-width="0.55" vector-effect="non-scaling-stroke" stroke-linejoin="round"></path>' +
          '<line class="mc-cross" x1="0" x2="0" y1="' + PAD.t + '" y2="' + (H - PAD.b) +
            '" stroke="' + INK.axis + '" stroke-width="0.2" style="display:none"></line>' +
        '</svg>' +
        axisLabels +
        // The end marker is HTML too: preserveAspectRatio="none" would stretch
        // an SVG circle into an ellipse.
        '<span class="mc-dot" style="top:' + ((ly / H) * 100).toFixed(2) + '%;left:' +
          ((lx / W) * 100).toFixed(2) + '%"></span>' +
        // The direct label: identity and current value without relying on colour.
        '<span class="mc-endlab" style="top:' + ((ly / H) * 100).toFixed(2) + '%;left:' +
          ((lx / W) * 100).toFixed(2) + '%">' + Math.round(last.p * 100) + '%</span>' +
        '<div class="mc-tip" role="status" aria-live="polite" style="display:none"></div>' +
      '</div>' +
      // Rule 4: the cohort size is on screen, not only in a tooltip.
      '<div class="mc-foot">' +
        '<span class="mc-key"><i style="background:' + INK.consensus + '"></i>' +
          esc(nameA) + ' — middle of ' + v.cohortBooks + ' sportsbooks</span>' +
        (showBooks ? '<span class="mc-key"><i style="background:' + INK.book + '"></i>each sportsbook</span>' : '') +
        '<span class="mc-span">' + esc(fmtRange(sc.t0, sc.t1)) + '</span>' +
      '</div>';

    wireHover(el, ps, sc, W, nameA, nameB, v.cohortBooks);
    return { ok: true, cohortBooks: v.cohortBooks, points: ps.length, from: sc.t0, to: sc.t1 };
  };

  function fmtRange(t0, t1) {
    const d = Math.round((t1 - t0) / 86400000);
    const hrs = Math.round((t1 - t0) / 3600000);
    const span = d >= 2 ? d + ' days' : (hrs >= 2 ? hrs + ' hours' : 'under an hour');
    return span + ' of capture';
  }

  // Crosshair + tooltip. An SVG chart is interactive by default.
  function wireHover(el, ps, sc, W, nameA, nameB, cohortBooks) {
    const svg = el.querySelector('.mc-svg');
    const tip = el.querySelector('.mc-tip');
    const cross = el.querySelector('.mc-cross');
    if (!svg || !tip || !cross) return;
    function at(clientX) {
      const r = svg.getBoundingClientRect();
      const ux = ((clientX - r.left) / r.width) * W;
      let best = ps[0], bd = Infinity;
      ps.forEach(p => { const d = Math.abs(sc.x(p.t) - ux); if (d < bd) { bd = d; best = p; } });
      return best;
    }
    function show(ev) {
      const cx = ev.touches ? ev.touches[0].clientX : ev.clientX;
      const p = at(cx);
      cross.setAttribute('x1', sc.x(p.t).toFixed(1));
      cross.setAttribute('x2', sc.x(p.t).toFixed(1));
      cross.style.display = '';
      const pct = (p.p * 100).toFixed(1);
      tip.innerHTML = '<b>' + Math.round(p.p * 100) + '% ' + esc(nameA) + '</b>' +
        '<span>' + (100 - Math.round(p.p * 100)) + '% ' + esc(nameB) + '</span>' +
        '<span>' + esc(window.cflMarket ? cflMarket.fmtStampUtc(new Date(p.t).toISOString()) : new Date(p.t).toUTCString()) + '</span>' +
        '<span>' + cohortBooks + ' sportsbooks, vig removed</span>';
      tip.style.display = '';
      const r = svg.getBoundingClientRect();
      tip.style.left = Math.max(0, Math.min(r.width - 150, (sc.x(p.t) / W) * r.width - 75)) + 'px';
    }
    function hide() { cross.style.display = 'none'; tip.style.display = 'none'; }
    svg.addEventListener('mousemove', show);
    svg.addEventListener('mouseleave', hide);
    svg.addEventListener('touchstart', show, { passive: true });
    svg.addEventListener('touchmove', show, { passive: true });
    svg.addEventListener('touchend', hide);
  }

  /* ----------------------------------------------------------------------
     A table of the same numbers. Identity and value never depend on the plot.
     ---------------------------------------------------------------------- */
  C.tableHtml = function (rows, nameA, cohortBooks) {
    if (!Array.isArray(rows) || !rows.length) return '';
    const body = rows.map(r =>
      '<tr><td>' + esc(window.cflMarket ? cflMarket.fmtStampUtc(r.at) : r.at) + '</td>' +
      '<td>' + (num(r.market_p_a) === null ? '—' : (num(r.market_p_a) * 100).toFixed(1) + '%') + '</td>' +
      '<td>' + esc(r.cohort_books) + '</td></tr>'
    ).join('');
    return '<table class="mc-table"><caption>Every captured point behind the chart. ' +
      esc(cohortBooks) + ' sportsbooks throughout.</caption><thead><tr>' +
      '<th>Captured (UTC)</th><th>' + esc(nameA) + '</th><th>Books</th>' +
      '</tr></thead><tbody>' + body + '</tbody></table>';
  };

  /* ----------------------------------------------------------------------
     Loading. Single fight only — see §Performance in market_chart_views.sql.
     A literal fight_id is 22 ms; twelve fights is 4.6 s and a subquery does
     not push down at all. Do not batch this.
     ---------------------------------------------------------------------- */
  C.load = async function (fightId) {
    const out = { meta: null, series: [], books: [] };
    const sb = window.cflSupabase;
    if (!sb || !fightId) return out;
    try {
      const [meta, series] = await Promise.all([
        sb.from('v_fight_chart_meta').select('*').eq('fight_id', fightId).maybeSingle(),
        sb.from('v_fight_chart_series').select('at, market_p_a, cohort_books')
          .eq('fight_id', fightId).order('at', { ascending: true })
      ]);
      out.meta = meta && meta.data ? meta.data : null;
      out.series = (series && series.data) || [];
    } catch (e) {
      console.warn('[market-chart] series unavailable:', e.message);
    }
    return out;
  };

  C.loadBooks = async function (fightId) {
    const sb = window.cflSupabase;
    if (!sb || !fightId) return [];
    try {
      const { data } = await sb.from('v_fight_chart_books')
        .select('book_id, book_name, at, fair_a, in_cohort')
        .eq('fight_id', fightId).order('at', { ascending: true });
      return data || [];
    } catch (e) { return []; }
  };

  /* ----------------------------------------------------------------------
     Polymarket — an opt-in line, OFF by default, on its own small chart.

     Polymarket is a prediction market, not a sportsbook: its price is what
     traders last paid, not a number a book is offering. So it never joins the
     sportsbook line above, the best price, or any movement figure — those all
     read v_odds_books_sportsbooks, which excludes it by name. It is drawn
     separately, dashed, and labelled every time. Its main use is a fight no
     sportsbook has priced yet, which otherwise shows nothing.

     Source: v_fight_polymarket_series (polymarket_chart_view.sql), which
     already refuses live, closed, post-bell and settled-looking prices.
     ---------------------------------------------------------------------- */
  C.PM_INK = { a: '#ff4d57', b: '#4f8dff', grid: '#1a1f27', label: '#6b7480' };
  C.PM_NOTE = 'Polymarket is a prediction market, not a sportsbook. Its price is what ' +
    'traders last paid, not an offer from a book, and it is not part of any sportsbook number on this page.';

  const _pmCache = {};
  C.loadPolymarket = function (fightId) {
    const sb = window.cflSupabase;
    if (!sb || !fightId) return Promise.resolve([]);
    if (!_pmCache[fightId]) {
      _pmCache[fightId] = Promise.resolve(sb.from('v_fight_polymarket_series')
        .select('at, p_a').eq('fight_id', fightId).order('at', { ascending: true }))
        .then(r => (r && r.data) || [])
        .catch(e => { delete _pmCache[fightId]; console.warn('[market-chart] polymarket unavailable:', e.message); return null; });
    }
    return _pmCache[fightId];
  };

  C.polymarketPoints = function (rows) {
    return (Array.isArray(rows) ? rows : [])
      .map(r => ({ t: Date.parse(r.at), p: num(r.p_a) }))
      .filter(d => isFinite(d.t) && d.p !== null && d.p > 0 && d.p < 1)
      .sort((x, y) => x.t - y.t);
  };

  // rows === null means the read failed, which is not the same as "no market".
  C.polymarketHtml = function (rows, nameA, nameB) {
    const nA = nameA || 'corner A', nB = nameB || 'corner B';
    const note = '<p class="mc-empty-b" style="margin:8px 0 0;font-size:12px">' + esc(C.PM_NOTE) + '</p>';
    if (rows === null) {
      return '<div class="mc-empty"><div class="mc-empty-h">Polymarket price unavailable</div>' +
        '<div class="mc-empty-b">The Polymarket history could not be loaded. Nothing else on this page is affected.</div></div>';
    }
    const ps = C.polymarketPoints(rows);
    const stamp = t => window.cflMarket ? cflMarket.fmtStampUtc(new Date(t).toISOString()) : new Date(t).toUTCString();
    const pct = p => Math.round(p * 100) + '%';
    // Corner B is 100 minus corner A as shown, so the pair always sums to 100.
    const pctB = p => (100 - Math.round(p * 100)) + '%';
    if (!ps.length) {
      return '<div class="mc-empty"><div class="mc-empty-h">No Polymarket price</div>' +
        '<div class="mc-empty-b">CFL has not captured an open Polymarket market on this fight.</div></div>';
    }
    if (ps.length === 1) {
      const p = ps[0];
      return '<div class="mc-empty"><div class="mc-empty-h">Polymarket: ' + esc(nA) + ' ' + pct(p.p) +
        ', ' + esc(nB) + ' ' + pctB(p.p) + '</div>' +
        '<div class="mc-empty-b">One capture so far (' + esc(stamp(p.t)) + '). A line appears once there is a second one to move to.</div>' +
        note + '</div>';
    }
    const W = 320, H = 120, L = 34, R = 10, T = 8, B = 10;
    const all = ps.map(d => d.p).concat(ps.map(d => 1 - d.p));
    let lo = Math.min.apply(null, all), hi = Math.max.apply(null, all);
    const pad = Math.max(0.03, (hi - lo) * 0.12);
    lo = Math.max(0, lo - pad); hi = Math.min(1, hi + pad);
    const t0 = ps[0].t, t1 = ps[ps.length - 1].t, span = Math.max(1, t1 - t0);
    const x = t => L + (t - t0) / span * (W - L - R);
    const y = p => T + (1 - (p - lo) / Math.max(1e-4, hi - lo)) * (H - T - B);
    // Stepped, like every other line here: a price stands until the next capture.
    const step = f => ps.map((d, i) => (i ? ' H' + x(d.t).toFixed(1) + ' V' : 'M' + x(d.t).toFixed(1) + ' ') + y(f(d.p)).toFixed(1)).join('');
    let grid = '';
    for (let g = Math.ceil(lo * 10) / 10; g <= hi + 1e-9; g += 0.1) {
      const yy = y(g).toFixed(1);
      grid += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + yy + '" y2="' + yy + '" stroke="' + C.PM_INK.grid + '" stroke-width=".6"/>' +
        '<text x="' + (L - 6) + '" y="' + yy + '" fill="' + C.PM_INK.label + '" font-size="8.5" text-anchor="end" dominant-baseline="middle">' + Math.round(g * 100) + '%</text>';
    }
    const first = ps[0], last = ps[ps.length - 1];
    const line = (f, c) => '<path d="' + step(f) + '" fill="none" stroke="' + c + '" stroke-width="1.6" stroke-dasharray="5 3"/>';
    return '<div class="mc-pm-chart">' +
      '<div class="mc-foot" style="margin:0 0 6px">' +
        '<span class="mc-key"><i style="background:' + C.PM_INK.a + '"></i>' + esc(nA) + ' ' + pct(last.p) + '</span>' +
        '<span class="mc-key"><i style="background:' + C.PM_INK.b + '"></i>' + esc(nB) + ' ' + pctB(last.p) + '</span>' +
        '<span class="mc-span">' + esc(fmtRange(t0, t1)) + '</span>' +
      '</div>' +
      '<svg viewBox="0 0 ' + W + ' ' + H + '" style="width:100%;height:auto;display:block" role="img" aria-label="' +
        esc('Polymarket price: ' + nA + ' ' + pct(first.p) + ' to ' + pct(last.p) + ', ' + nB + ' ' +
            pctB(first.p) + ' to ' + pctB(last.p) + ', ' + ps.length + ' captures') + '">' +
        grid + line(p => p, C.PM_INK.a) + line(p => 1 - p, C.PM_INK.b) +
      '</svg>' +
      '<p class="mc-empty-b" style="margin:6px 0 0;font-size:12px">' + ps.length + ' Polymarket captures, ' +
        esc(stamp(first.t)) + ' to ' + esc(stamp(last.t)) + '.</p>' +
      note + '</div>';
  };

  // The switch. Off by default; nothing is fetched until it is turned on.
  C.polymarketToggleHtml = function (fightId, nameA, nameB) {
    const id = esc(String(fightId));
    return '<div class="mc-pm" data-pm-fight="' + id + '" data-pm-a="' + esc(nameA || '') + '" data-pm-b="' + esc(nameB || '') + '" style="margin-top:10px">' +
      '<div class="mc-controls" style="margin-bottom:8px"><button type="button" data-pm-toggle aria-pressed="false" ' +
        'aria-controls="mcpm-' + id + '">Show Polymarket</button></div>' +
      '<div id="mcpm-' + id + '" data-pm-body hidden></div></div>';
  };

  // One delegated listener for every switch on the page, so a re-rendered
  // card needs no re-wiring.
  C.wirePolymarket = function (root) {
    const r = root || (typeof document !== 'undefined' ? document : null);
    if (!r || r.__cflPmWired) return;
    r.__cflPmWired = true;
    r.addEventListener('click', async (ev) => {
      const btn = ev.target && ev.target.closest && ev.target.closest('[data-pm-toggle]');
      if (!btn) return;
      const box = btn.closest('[data-pm-fight]');
      const body = box && box.querySelector('[data-pm-body]');
      if (!body) return;
      const on = btn.getAttribute('aria-pressed') !== 'true';
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
      btn.textContent = on ? 'Hide Polymarket' : 'Show Polymarket';
      if (!on) { body.setAttribute('hidden', ''); return; }
      body.removeAttribute('hidden');
      body.innerHTML = '<div class="mc-empty-b">Loading Polymarket…</div>';
      btn.disabled = true;
      const rows = await C.loadPolymarket(box.getAttribute('data-pm-fight'));
      btn.disabled = false;
      body.innerHTML = C.polymarketHtml(rows, box.getAttribute('data-pm-a'), box.getAttribute('data-pm-b'));
    });
  };
  if (typeof document !== 'undefined' && typeof window !== 'undefined') C.wirePolymarket(document);

  const api = { INK, ...C };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else window.cflChart = api;
})();
