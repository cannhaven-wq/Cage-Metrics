// Post-card image renderer for the content engine.
//
// Turns a structured `image` spec (derived from live model data by
// social-engine.js) into finished, on-brand PNG graphics sized for every
// platform — square, IG portrait, 9:16 story/reel, and 16:9 for X.
//
// Rendering is done by driving a headless Chrome/Chromium (the same trick the
// logo + PDF build uses): we write a self-contained HTML document per image and
// screenshot it at an exact viewport. No image libraries, no canvas — the
// browser lays out real CFL type and vector graphics, so output is identical to
// the site. If no browser is found the engine degrades gracefully (copy still
// generates; images are skipped with a warning).
//
// Everything here is derived from the live design system (_shared.css): exact
// brand hex, Barlow Condensed / Space Grotesk / Inter, the pulse mark.

const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawnSync } = require('child_process');

// ------------------------------------------------------------ brand tokens ---
const C = {
  bg: '#08090b', surf: '#0f1318', surf2: '#161a20', line: '#20252d', line2: '#2b313b',
  red: '#ff3b47', green: '#3fd07a', amber: '#ffb547', orange: '#ff8a4c',
  text: '#f4f6f8', text2: '#a0a8b4', text3: '#7d8794',
};
const TIER_COLOR = { tireless: C.green, steady: C.green, tapers: C.amber, fades: C.orange, collapses: C.red };

const FONT_LINK =
  '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>' +
  '<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=Space+Grotesk:wght@400;500;600&family=Inter:wght@500;600;700&display=block" rel="stylesheet">';

// The pulse mark (dark tile), reused from the logo system.
const PULSE_TILE =
  '<svg class="logo" viewBox="0 0 512 512"><defs><linearGradient id="pg" x1="0" y1="0" x2="0" y2="1">' +
  '<stop offset="0" stop-color="#12161c"/><stop offset="1" stop-color="#0b0d11"/></linearGradient></defs>' +
  '<rect x="8" y="8" width="496" height="496" rx="120" fill="url(#pg)" stroke="#232a33" stroke-width="6"/>' +
  '<g fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-width="30">' +
  '<path d="M104 256 L172 256 L198 230 L224 256 L256 256" stroke="#f4f6f8"/>' +
  '<path d="M256 256 L288 152 L314 370 L340 256" stroke="#ff3b47"/>' +
  '<path d="M340 256 L364 256 L390 238 L416 256" stroke="#f4f6f8"/></g></svg>';

// ------------------------------------------------------------------ sizes ---
// mode: 'stack' (all 1080 wide → vw-based type stays visually constant) or
// 'wide' (16:9 → two-column, vh-based).
const SIZES = {
  x_land:      { w: 1600, h: 900,  mode: 'wide',  label: 'X / landscape 16:9' },
  square:      { w: 1080, h: 1080, mode: 'stack', label: 'Square 1:1' },
  ig_portrait: { w: 1080, h: 1350, mode: 'stack', label: 'Instagram 4:5' },
  story:       { w: 1080, h: 1920, mode: 'stack', label: 'Story / Reel 9:16' },
};

function sizesForPlatform(platform, layout) {
  const p = String(platform).toLowerCase();
  let keys;
  if (p.includes('tiktok')) keys = ['story', 'square'];
  else if (p.includes('instagram')) keys = ['ig_portrait', 'story'];
  else if (p.includes('reddit')) keys = ['square'];
  else if (p.includes('reel')) keys = ['story', 'square'];
  else keys = ['x_land', 'square']; // X and everything else
  if (layout === 'board') keys = keys.filter(k => SIZES[k].mode !== 'wide'); // board is stack-only
  return [...new Set(keys)];
}

// --------------------------------------------------------------- templates ---
function esc(s) { return String(s == null ? '' : s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c])); }

function chipHtml(chips) {
  return (chips || []).map(c => {
    const tone = c.tone === 'warn' ? ' warn' : c.tone === 'win' ? ' win' : '';
    return `<div class="chip"><span class="k">${esc(c.k)}</span><span class="v${tone}">${esc(c.v)}</span></div>`;
  }).join('');
}

function bodyVerdict(spec) {
  const vs = spec.fb ? `<span class="hl">${esc(spec.fa)}</span><span class="vs">vs</span><span class="hl">${esc(spec.fb)}</span>`
                     : `<span class="hl">${esc(spec.fa)}</span>`;
  return `
<div class="top"><span class="logowrap">${PULSE_TILE}</span><span class="brand">Cannon Fight Lab</span></div>
<div class="eyebrow">${esc(spec.eyebrow)}</div>
<div class="headline">${vs}</div>
<div class="grow"></div>
<div class="numblock">
  <div class="big">${esc(spec.big)}</div><div class="bar"></div>
  <div class="bigcap">${esc(spec.bigCap)}</div>
</div>
<div class="chips">${chipHtml(spec.chips)}</div>
<div class="grow"></div>
<div class="cta">${esc(spec.cta)}</div>`;
}

function bodyBoard(spec) {
  const rows = (spec.rows || []).map(r => {
    const col = TIER_COLOR[r.tier] || C.amber;
    return `<div class="brow"><span class="bdot" style="background:${col}"></span>` +
      `<span class="bname">${esc(r.name)}</span>` +
      `<span class="btier" style="color:${col}">${esc(r.tier)}</span></div>`;
  }).join('');
  return `
<div class="top"><span class="logowrap">${PULSE_TILE}</span><span class="brand">Cannon Fight Lab</span></div>
<div class="eyebrow">${esc(spec.eyebrow)}</div>
<div class="headline"><span class="hl">${esc(spec.title)}</span></div>
<div class="grow"></div>
<div class="board">${rows}</div>
<div class="grow"></div>
<div class="cta">${esc(spec.cta)}</div>`;
}

// Style: two modes. Stack uses vw (constant width 1080). Wide uses vh.
const STYLE = `
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%;background:${C.bg};overflow:hidden}
.wrap{width:100vw;height:100vh;background:${C.bg};position:relative;overflow:hidden;
  font-family:"Space Grotesk",sans-serif;color:${C.text}}
.glow{position:absolute;width:70vw;height:70vw;top:-24vw;right:-22vw;
  background:radial-gradient(circle,rgba(255,59,71,.16),transparent 62%)}
.pad{position:absolute;inset:0;display:flex;flex-direction:column}
.logo{display:block}
.brand{font-family:"Barlow Condensed",sans-serif;font-weight:800;text-transform:uppercase;color:${C.text}}
.top{display:flex;align-items:center}
.eyebrow{font-family:"Inter",sans-serif;font-weight:600;text-transform:uppercase;color:${C.text3}}
.headline{font-family:"Barlow Condensed",sans-serif;font-weight:800;text-transform:uppercase;
  color:${C.text};line-height:.92}
.headline .vs{color:${C.text3};margin:0 .14em;font-size:.62em;vertical-align:.05em}
.grow{flex:1}
.big{font-family:"Barlow Condensed",sans-serif;font-weight:800;color:${C.text};line-height:.86}
.bar{background:${C.red};border-radius:100px}
.bigcap{font-family:"Space Grotesk",sans-serif;font-weight:500;text-transform:uppercase;
  color:${C.text2};letter-spacing:.02em}
.chips{display:flex;flex-wrap:wrap}
.chip{border:1px solid ${C.line};background:${C.surf};display:flex;flex-direction:column}
.chip .k{font-family:"Inter",sans-serif;font-weight:600;text-transform:uppercase;letter-spacing:.09em;color:${C.text3}}
.chip .v{font-family:"Inter",sans-serif;font-weight:700;font-variant-numeric:tabular-nums;color:${C.text}}
.chip .v.warn{color:${C.amber}}
.chip .v.win{color:${C.green}}
.cta{font-family:"Space Grotesk",sans-serif;font-weight:500;color:${C.text3}}
.board{display:flex;flex-direction:column}
.brow{display:flex;align-items:center;border-top:1px solid ${C.line}}
.bdot{border-radius:50%;flex:none}
.bname{font-family:"Barlow Condensed",sans-serif;font-weight:700;text-transform:uppercase;color:${C.text};flex:1}
.btier{font-family:"Inter",sans-serif;font-weight:700;text-transform:uppercase;letter-spacing:.04em}

/* ---- STACK (1080 wide: square / portrait / story) ---- */
.mode-stack .pad{padding:8.6vw}
.mode-stack .top{gap:2.4vw}
.mode-stack .logo{width:8.4vw;height:8.4vw}
.mode-stack .brand{font-size:2.9vw;letter-spacing:.06em}
.mode-stack .eyebrow{margin-top:6vw;font-size:2.35vw;letter-spacing:.24em}
.mode-stack .headline{margin-top:2vw;font-size:9.4vw}
.mode-stack .big{font-size:19vw}
.mode-stack .bar{width:15vw;height:1.4vw;margin-top:1vw}
.mode-stack .bigcap{margin-top:2.4vw;font-size:3.2vw}
.mode-stack .chips{margin-top:5.4vw;gap:1.6vw}
.mode-stack .chip{border-radius:1.5vw;padding:1.7vw 2.3vw;gap:.6vw}
.mode-stack .chip .k{font-size:1.75vw}
.mode-stack .chip .v{font-size:3.2vw}
.mode-stack .cta{margin-top:4.6vw;font-size:2.75vw}
.mode-stack .board{margin-top:1vw}
.mode-stack .brow{gap:2.4vw;padding:2.9vw 0}
.mode-stack .bdot{width:2.4vw;height:2.4vw}
.mode-stack .bname{font-size:6.4vw}
.mode-stack .btier{font-size:2.7vw}

/* ---- WIDE (1600x900: X landscape, two-column) ---- */
.mode-wide .pad{flex-direction:row;gap:5vh;padding:8vh 7vh}
.mode-wide .col-l{flex:1;display:flex;flex-direction:column;min-width:0}
.mode-wide .col-r{width:42%;display:flex;flex-direction:column;justify-content:center}
.mode-wide .top{gap:2.2vh}
.mode-wide .logo{width:8.6vh;height:8.6vh}
.mode-wide .brand{font-size:3.1vh;letter-spacing:.06em}
.mode-wide .eyebrow{margin-top:5vh;font-size:2.5vh;letter-spacing:.22em}
.mode-wide .headline{margin-top:1.6vh;font-size:9.2vh}
.mode-wide .cta{margin-top:auto;font-size:2.8vh}
.mode-wide .big{font-size:26vh}
.mode-wide .bar{width:16vh;height:1.5vh;margin-top:1vh}
.mode-wide .bigcap{margin-top:2.2vh;font-size:3.4vh}
.mode-wide .chips{margin-top:4vh;gap:1.6vh}
.mode-wide .chip{border-radius:1.4vh;padding:1.7vh 2.2vh;gap:.6vh}
.mode-wide .chip .k{font-size:1.9vh}
.mode-wide .chip .v{font-size:3.4vh}
`;

// Build a full standalone HTML document for one image at one size.
function cardHtml(spec, sizeKey) {
  const size = SIZES[sizeKey];
  const inner = spec.layout === 'board' ? bodyBoard(spec) : bodyVerdict(spec);
  // Wide mode splits verdict into two columns; board never uses wide.
  let pad;
  if (size.mode === 'wide' && spec.layout !== 'board') {
    const vs = spec.fb ? `<span class="hl">${esc(spec.fa)}</span><span class="vs">vs</span><span class="hl">${esc(spec.fb)}</span>`
                       : `<span class="hl">${esc(spec.fa)}</span>`;
    pad = `<div class="pad">
      <div class="col-l">
        <div class="top"><span class="logowrap">${PULSE_TILE}</span><span class="brand">Cannon Fight Lab</span></div>
        <div class="eyebrow">${esc(spec.eyebrow)}</div>
        <div class="headline">${vs}</div>
        <div class="cta">${esc(spec.cta)}</div>
      </div>
      <div class="col-r">
        <div class="big">${esc(spec.big)}</div><div class="bar"></div>
        <div class="bigcap">${esc(spec.bigCap)}</div>
        <div class="chips">${chipHtml(spec.chips)}</div>
      </div>
    </div>`;
  } else {
    pad = `<div class="pad">${inner}</div>`;
  }
  return `<!doctype html><html><head><meta charset="utf-8">${FONT_LINK}<style>${STYLE}</style></head>` +
    `<body><div class="wrap mode-${size.mode}"><div class="glow"></div>${pad}</div></body></html>`;
}

// ------------------------------------------------------------ chrome driver ---
function findChrome() {
  const envp = process.env.CFL_CHROME || process.env.CHROME_PATH || process.env.PUPPETEER_EXECUTABLE_PATH;
  const candidates = [envp,
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium', '/usr/bin/chromium-browser',
  ].filter(Boolean);
  for (const c of candidates) { try { if (fs.existsSync(c)) return c; } catch (_) {} }
  // last resort: ask the OS
  for (const probe of [['which', 'google-chrome'], ['which', 'chromium'], ['which', 'chromium-browser']]) {
    try { const r = spawnSync(probe[0], [probe[1]], { encoding: 'utf8' }); const p = (r.stdout || '').trim(); if (p && fs.existsSync(p)) return p; } catch (_) {}
  }
  return null;
}

const TMP = path.join(os.tmpdir(), 'cfl-postcards');
const PROFILE = path.join(os.tmpdir(), 'cfl-postcards-profile');
let _n = 0;

function renderOne(chrome, html, w, h, outPath) {
  fs.mkdirSync(TMP, { recursive: true });
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  const htmlPath = path.join(TMP, `card-${process.pid}-${_n++}.html`);
  fs.writeFileSync(htmlPath, html);
  try { if (fs.existsSync(outPath)) fs.unlinkSync(outPath); } catch (_) {}
  const url = 'file://' + (process.platform === 'win32' ? '/' : '') + htmlPath.replace(/\\/g, '/');
  const args = [
    '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', '--no-default-browser-check',
    '--no-sandbox', '--disable-dev-shm-usage', // required for headless Chrome on CI runners
    `--user-data-dir=${PROFILE}`, '--force-device-scale-factor=1',
    '--virtual-time-budget=7000', '--run-all-compositor-stages-before-draw',
    `--window-size=${w},${h}`, `--screenshot=${outPath}`, url,
  ];
  const r = spawnSync(chrome, args, { encoding: 'utf8', timeout: 45000 });
  try { fs.unlinkSync(htmlPath); } catch (_) {}
  return fs.existsSync(outPath);
}

// Render every target size for one piece's image spec.
// Returns [{ key, w, h, label, file, rel }]. `outDir` = card's img dir,
// `relBase` = path prefix to reach it from dashboard.html (e.g. "<slug>/img").
function renderPieceImages(chrome, piece, outDir, relBase) {
  if (!piece.image || !chrome) return [];
  const keys = sizesForPlatform(piece.platform, piece.image.layout);
  const out = [];
  for (const key of keys) {
    const size = SIZES[key];
    const fname = `${piece.id}__${key}.png`;
    const outPath = path.join(outDir, fname);
    const html = cardHtml(piece.image, key);
    if (renderOne(chrome, html, size.w, size.h, outPath)) {
      out.push({ key, w: size.w, h: size.h, label: size.label, file: outPath, rel: `${relBase}/${fname}` });
    }
  }
  return out;
}

module.exports = { findChrome, sizesForPlatform, renderPieceImages, cardHtml, SIZES, C };
