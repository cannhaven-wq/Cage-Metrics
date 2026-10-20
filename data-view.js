/* ==========================================================================
   data-view.js — Charts or Numbers, the reader's choice.

   A reader can get lost in a wall of figures, so data surfaces draw their
   numbers as bars by default and a switch puts the plain figures back. The
   choice is remembered in this browser and applies on every page.

   How it works: a page renders BOTH versions of a figure. Elements marked
   .dv-c are the chart, .dv-n the plain numbers, and one attribute on <html>
   (data-dv="charts" | "numbers") decides which shows. Switching never
   refetches or re-renders anything.

   The bars draw numbers the page already shows. They add no pick, no
   prediction and no "better" side: corner colours say whose bar is whose and
   nothing else.

   Used by index.html (Card Lab), market.html (Market Lab), stats.html
   (Factor Lab). Exposed as window.cflDataView.
   ========================================================================== */
(function (root) {
  'use strict';
  const KEY = 'cfl.dataView';
  const MODES = ['charts', 'numbers'];

  // Storage can be missing or throw (private windows, blocked site data), and
  // the page must still draw — charts is the default either way.
  function read() {
    try { const v = root.localStorage.getItem(KEY); return MODES.indexOf(v) >= 0 ? v : 'charts'; }
    catch (e) { return 'charts'; }
  }
  function write(v) { try { root.localStorage.setItem(KEY, v); } catch (e) { /* convenience only */ } }

  let mode = read();

  function apply() {
    const doc = root.document;
    if (!doc) return;
    doc.documentElement.setAttribute('data-dv', mode);
    doc.querySelectorAll('.dv-toggle button[data-dv]').forEach(b => {
      const on = b.getAttribute('data-dv') === mode;
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', String(on));
    });
  }

  function set(v) {
    if (MODES.indexOf(v) < 0 || v === mode) return;
    mode = v;
    write(v);
    apply();
  }

  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  // The switch. Every copy on a page stays in step through apply().
  function toggleHtml() {
    const btn = (v, label, icon) => '<button type="button" data-dv="' + v + '" aria-pressed="' + (mode === v) + '"' +
      (mode === v ? ' class="active"' : '') + '>' + icon + label + '</button>';
    return '<div class="dv-toggle" role="group" aria-label="Show data as charts or numbers">' +
      btn('charts', 'Charts', '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20V13M10 20V8M16 20v-5M22 20H2"/></svg>') +
      btn('numbers', 'Numbers', '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18M3 12h18M3 18h18"/></svg>') +
      '</div>';
  }

  // Two shares of one whole, side by side: the market's chance for each
  // corner. pA is 0..1. Labels sit inside their own segment.
  function split(pA, nameA, nameB, opts) {
    if (pA == null || !isFinite(pA)) return '';
    const a = clamp(pA * 100, 0, 100), b = 100 - a;
    const ra = Math.round(a), rb = 100 - ra;
    const thin = opts && opts.thin;
    const label = (nameA ? nameA + ' ' : '') + ra + '%, ' + (nameB ? nameB + ' ' : '') + rb + '%';
    return '<div class="dv-split' + (thin ? ' thin' : '') + '" role="img" aria-label="' + esc((opts && opts.aria ? opts.aria + ': ' : '') + label) + '">' +
      '<i class="a" style="width:' + a.toFixed(1) + '%">' + (thin ? '' : '<b>' + ra + '%</b>') + '</i>' +
      '<i class="b" style="width:' + b.toFixed(1) + '%">' + (thin ? '' : '<b>' + rb + '%</b>') + '</i>' +
      '</div>';
  }

  // Two measurements compared: bars grow outward from the centre, each scaled
  // to the larger of the pair. Returns '' when either is missing.
  function mirror(va, vb, aria) {
    if (va == null || vb == null || !isFinite(va) || !isFinite(vb)) return '';
    const max = Math.max(Math.abs(va), Math.abs(vb)) || 1;
    const wa = Math.abs(va) / max * 100, wb = Math.abs(vb) / max * 100;
    return '<div class="dv-mirror dv-c" role="img" aria-label="' + esc(aria || '') + '">' +
      '<span class="dv-half a"><i style="width:' + wa.toFixed(1) + '%"></i></span>' +
      '<span class="dv-half b"><i style="width:' + wb.toFixed(1) + '%"></i></span></div>';
  }

  // A win / loss / draw record as one bar. Losses are drawn at the same
  // weight as wins.
  function record(w, l, d, side) {
    w = +w || 0; l = +l || 0; d = +d || 0;
    const n = w + l + d;
    if (!n) return '';
    const pct = x => (x / n * 100).toFixed(1);
    return '<div class="dv-rec ' + (side || '') + '" role="img" aria-label="' + esc(w + ' wins, ' + l + ' losses' + (d ? ', ' + d + ' draws' : '')) + '">' +
      (w ? '<i class="w" style="width:' + pct(w) + '%"></i>' : '') +
      (l ? '<i class="l" style="width:' + pct(l) + '%"></i>' : '') +
      (d ? '<i class="d" style="width:' + pct(d) + '%"></i>' : '') + '</div>';
  }

  // A signed movement in percentage points, drawn as a bar out from a centre
  // line toward the corner it moved to. `max` is the full half-width.
  function move(pts, max) {
    if (pts == null || !isFinite(pts)) return '';
    const w = clamp(Math.abs(pts) / (max || 10) * 50, Math.abs(pts) >= 0.5 ? 2 : 0, 50);
    const side = pts > 0 ? 'a' : 'b';
    return '<span class="dv-move" aria-hidden="true"><i class="' + side + '" style="width:' + w.toFixed(1) + '%"></i><span class="mid"></span></span>';
  }

  // How far apart the books are, as a short meter. `wide` is where the page
  // already calls the spread wide; the meter fills at twice that.
  function meter(v, wide) {
    if (v == null || !isFinite(v)) return '';
    const full = (wide || 5) * 2;
    const w = clamp(v / full * 100, v > 0 ? 3 : 0, 100);
    return '<span class="dv-meter' + (v >= (wide || 5) ? ' wide' : '') + '" aria-hidden="true"><i style="width:' + w.toFixed(1) + '%"></i></span>';
  }

  const CSS = `
html[data-dv="numbers"] .dv-c { display: none !important; }
html:not([data-dv="numbers"]) .dv-n { display: none !important; }
.dv-toggle { display: inline-flex; background: var(--bg-2, #0f1319); border: 1px solid var(--line, #1a1f27); border-radius: 10px; padding: 3px; gap: 2px; flex: none; }
.dv-toggle button { display: inline-flex; align-items: center; gap: 6px; font-family: var(--font-display, inherit); font-size: 12.5px; font-weight: 600; color: var(--text-2, #9aa4b0); background: transparent; border: 0; padding: 7px 12px; border-radius: 8px; cursor: pointer; }
.dv-toggle button:hover { color: #fff; }
.dv-toggle button.active { background: var(--bg-4, #1c222b); color: #fff; }
.dv-toggle svg { width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; }
.dv-split { display: flex; height: 22px; border-radius: 6px; overflow: hidden; background: var(--bg-3, #161b22); gap: 2px; }
.dv-split.thin { height: 5px; border-radius: 3px; gap: 1px; }
.dv-split i { display: flex; align-items: center; min-width: 0; font-style: normal; }
.dv-split i.a { background: #ff4d57; justify-content: flex-start; padding-left: 7px; }
.dv-split i.b { background: #4f8dff; justify-content: flex-end; padding-right: 7px; }
.dv-split.thin i { padding: 0; }
.dv-split b { font-size: 11.5px; font-weight: 700; color: #fff; white-space: nowrap; font-variant-numeric: tabular-nums; }
.dv-mirror { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin-top: 5px; }
.dv-mirror .dv-half { display: flex; height: 6px; background: rgba(255,255,255,.06); border-radius: 3px; overflow: hidden; }
.dv-mirror .dv-half.a { justify-content: flex-end; }
.dv-mirror .dv-half i { display: block; height: 100%; border-radius: 3px; }
.dv-mirror .dv-half.a i { background: #ff4d57; } .dv-mirror .dv-half.b i { background: #4f8dff; }
.dv-rec { display: flex; height: 6px; border-radius: 3px; overflow: hidden; gap: 1px; margin-top: 4px; min-width: 60px; }
.dv-rec i.w { background: var(--text-2, #9aa4b0); } .dv-rec i.l { background: var(--text-3, #6b7480); opacity: .55; } .dv-rec i.d { background: #c9a54a; }
.dv-rec.a i.w { background: #ff4d57; } .dv-rec.b i.w { background: #4f8dff; }
.dv-move { position: relative; display: block; width: 72px; height: 6px; background: var(--bg-3, #161b22); border-radius: 3px; margin-top: 5px; }
.dv-move i { position: absolute; top: 0; bottom: 0; border-radius: 3px; }
.dv-move i.a { right: 50%; background: #ff4d57; } .dv-move i.b { left: 50%; background: #4f8dff; }
.dv-move .mid { position: absolute; left: 50%; top: -2px; bottom: -2px; width: 1px; background: var(--text-3, #6b7480); }
.dv-meter { display: block; width: 56px; height: 6px; background: var(--bg-3, #161b22); border-radius: 3px; overflow: hidden; margin-top: 5px; }
.dv-meter i { display: block; height: 100%; background: var(--text-2, #9aa4b0); border-radius: 3px; }
.dv-meter.wide i { background: var(--amber, #f2b544); }
.dv-key { display: flex; gap: 12px; font-size: 11.5px; color: var(--text-3, #6b7480); margin: 0 0 8px; flex-wrap: wrap; }
.dv-key span::before { content: ''; display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 5px; vertical-align: -1px; }
.dv-key .a::before { background: #ff4d57; } .dv-key .b::before { background: #4f8dff; }
`;

  function injectCss() {
    const doc = root.document;
    if (!doc || doc.getElementById('dv-css')) return;
    const s = doc.createElement('style');
    s.id = 'dv-css';
    s.textContent = CSS;
    (doc.head || doc.documentElement).appendChild(s);
  }

  if (root.document) {
    injectCss();
    apply();
    // One delegated listener, so a switch rendered after load works too.
    root.document.addEventListener('click', e => {
      const b = e.target && e.target.closest && e.target.closest('.dv-toggle button[data-dv]');
      if (b) set(b.getAttribute('data-dv'));
    });
  }

  const api = { mode: () => mode, set, apply, toggleHtml, split, mirror, record, move, meter, esc };
  root.cflDataView = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
