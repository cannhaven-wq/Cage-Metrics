// Loads LIVE Fight Lab pages in headless Chromium, against the production
// database, and reports what a visitor sees. Run by verify-live.yml.
//
// Which fights: FIGHT_IDS (comma-separated) when given. Otherwise it asks the
// production API, with the same publishable key the browser uses, for the
// next card's active bookings and takes the one with the most sportsbooks
// quoting and the one with the fewest (no market at all counts as fewest),
// so the check always covers a priced fight and a thin one without anyone
// hardcoding ids that rot after Saturday.
//
// Read-only. Prints each page's sections and a list of yes/no checks, and
// fails the job if any check fails. Screenshots go to OUT_DIR.
'use strict';
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const BASE = process.env.BASE_URL || 'https://cannonfightlab.com';
const OUT = process.env.OUT_DIR || 'live-shots';
fs.mkdirSync(OUT, { recursive: true });

// Read the public URL and publishable key from the shipped _shared.js rather
// than duplicating them here.
function publicApi() {
  const src = fs.readFileSync(path.join(__dirname, '..', '..', '_shared.js'), 'utf8');
  const url = (src.match(/SUPABASE_URL\s*=\s*'([^']+)'/) || [])[1];
  const key = (src.match(/SUPABASE_KEY\s*=\s*'([^']+)'/) || [])[1];
  if (!url || !key) throw new Error('could not read the public Supabase URL/key from _shared.js');
  return { url, key };
}

async function rest(q) {
  const { url, key } = publicApi();
  const r = await fetch(url + '/rest/v1/' + q, { headers: { apikey: key, Authorization: 'Bearer ' + key } });
  if (!r.ok) throw new Error('REST ' + r.status + ' on ' + q);
  return r.json();
}

async function pickFights() {
  if (process.env.FIGHT_IDS && process.env.FIGHT_IDS.trim()) {
    return process.env.FIGHT_IDS.split(',').map(s => s.trim()).filter(Boolean);
  }
  const today = new Date().toISOString().slice(0, 10);
  const ev = await rest('events?select=id,name,event_date&event_date=gte.' + today + '&order=event_date.asc&limit=1');
  if (!ev.length) throw new Error('no upcoming event found');
  const fights = await rest('fights?select=id,fighter_a_name,fighter_b_name,is_active&event_id=eq.' + ev[0].id);
  const active = fights.filter(f => f.is_active !== false);
  if (!active.length) throw new Error('no active bookings on ' + ev[0].name);
  const mv = await rest('v_fight_market_movement?select=fight_id,book_count&fight_id=in.(' + active.map(f => f.id).join(',') + ')');
  const books = {}; mv.forEach(m => { books[m.fight_id] = +m.book_count || 0; });
  const ranked = active.map(f => ({ id: f.id, n: books[f.id] || 0 })).sort((a, b) => b.n - a.n);
  const pick = [ranked[0].id, ranked[ranked.length - 1].id];
  console.log('Card: ' + ev[0].name + ' (' + ev[0].event_date + ')');
  ranked.forEach(r => console.log('  fight ' + r.id + ': ' + r.n + ' books'));
  return [...new Set(pick.map(String))];
}

async function shoot(browser, id, { name, viewport, mobile }) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: mobile ? 2 : 1, isMobile: !!mobile, hasTouch: !!mobile });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(BASE + '/fight.html?id=' + id + '&verify=' + Date.now(), { waitUntil: 'load', timeout: 60000 });
  let rendered = true;
  try {
    await page.waitForFunction(() => document.querySelectorAll('#flWho .who-card').length === 2 &&
      !!document.querySelector('#flForm .form-grid') && !!document.querySelector('#flLate .late-grid') &&
      !/Loading the market/.test(document.getElementById('flMarket').textContent), null, { timeout: 45000 });
  } catch (e) { rendered = false; }
  // The chart loads on its own, after the rest of the page. On 2026-10-13 its
  // series query took ~3.3 s at the database for a single fight, so wait for
  // it explicitly and report how long it took rather than guessing a pause.
  const chartStart = Date.now();
  let chartMs = null;
  try {
    await page.waitForFunction(() => !/Loading the history/.test(document.getElementById('flChart').textContent),
      null, { timeout: 20000 });
    chartMs = Date.now() - chartStart;
  } catch (e) { /* reported as chartSectionRendered: false */ }
  await page.waitForTimeout(300);
  const report = await page.evaluate(() => {
    const txt = el => el ? el.textContent.replace(/\s+/g, ' ').trim() : null;
    const clone = document.body.cloneNode(true);
    clone.querySelectorAll('script, style, noscript, template').forEach(n => n.remove());
    const body = clone.textContent;

    const corners = [...document.querySelectorAll('#flWho .who-card')].map(card => {
      const facts = txt(card.querySelector('.who-facts')) || '';
      const m = facts.match(/UFC (\d+)-(\d+)(?:-(\d+))?(?: \((\d+) NC\))?/);
      return {
        name: txt(card.querySelector('.nm')),
        facts,
        style: txt(card.querySelector('.pill')),
        chips: [...card.querySelectorAll('.chip')].map(c => c.textContent.trim()),
        ufc: m ? { w: +m[1], l: +m[2], d: +(m[3] || 0), nc: +(m[4] || 0) } : null,
        noUfc: /No UFC fights yet/.test(facts),
      };
    });
    const formCols = [...document.querySelectorAll('#flForm .form-col')].map(col => ({
      name: txt(col.querySelector('.hd')),
      rows: [...col.querySelectorAll('.form-row')].map(r => txt(r)),
      dates: [...col.querySelectorAll('.form-row .when')].map(w => Date.parse((w.textContent.split('·')[0] || '').trim())),
      empty: txt(col.querySelector('.form-none')),
    }));
    const late = [...document.querySelectorAll('#flLate .late-card')].map(c => txt(c));
    const lateValues = [...document.querySelectorAll('#flLate .late-card .num .v')].map(v => v.textContent.trim());
    const tapeRows = [...document.querySelectorAll('#flStats .tape-row')].map(r => txt(r));
    const tapeUfc = tapeRows.find(r => /UFC record/i.test(r)) || '';

    const checks = {
      fightLabScriptLoaded: !!window.cflFightLab,
      twoCornerCards: corners.length === 2,
      // The UFC record and the W/L chips come from the same list.
      recordAgreesWithChips: corners.every(c => {
        if (c.noUfc) return c.chips.length === 0;
        if (!c.ufc) return false;
        const total = c.ufc.w + c.ufc.l + c.ufc.d + c.ufc.nc;
        const w = c.chips.filter(x => x === 'W').length, l = c.chips.filter(x => x === 'L').length;
        if (c.chips.length !== Math.min(5, total)) return false;
        return w <= c.ufc.w && l <= c.ufc.l && (total > 5 || (w === c.ufc.w && l === c.ufc.l));
      }),
      tapeRecordMatchesCards: corners.every(c => c.noUfc
        ? /No UFC fights/.test(tapeUfc)
        : c.ufc && tapeUfc.indexOf(c.ufc.w + '-' + c.ufc.l) !== -1),
      lastFiveAtMostFive: formCols.every(c => c.rows.length <= 5),
      lastFiveNewestFirst: formCols.every(c => c.dates.every((d, i) => i === 0 || !(d > c.dates[i - 1]))),
      lateScoreNeverAPercent: lateValues.every(v => !/%/.test(v)),
      lateShowsSample: late.every(t => /Sample: |Not enough/.test(t)),
      lateCaveatPresent: /not a measurement of tiredness/i.test(body),
      marketSectionRendered: !!document.querySelector('#flMarket .corners') || /No sportsbook price captured/.test(txt(document.getElementById('flMarket')) || ''),
      chartSectionRendered: !!document.querySelector('#flChart #mcPlot') || !!document.querySelector('#flChart .mc-empty'),
      noPickOrEdge: !/Model pick|value bet|betting edge|best bet|CFL higher|market higher|our model/i.test(body),
      noOpeningLineClaim: !/opening line|since open\b/i.test(body),
      noHorizontalOverflow: document.documentElement.scrollWidth <= window.innerWidth,
      // T-094: the research workspace.
      workspaceScriptsLoaded: !!window.cflWorkspace && !!window.cflWorkspaceUI,
      explorerRendered: document.querySelectorAll('#flExplore .ws-tabs [role="tab"]').length >= 6 &&
        document.querySelectorAll('#flExplore .ws-m').length > 0,
      explorerShowsSample: /Verified fact|Calculated by CFL|All UFC fights|Last 5/.test(txt(document.getElementById('flExplore')) || ''),
      sheetRendered: !!document.querySelector('#flSheet .sh'),
      // T-095: fight context names what is not covered; Key points renders.
      contextRendered: /Not covered yet/.test(txt(document.getElementById('flContext')) || ''),
      keyPointsTab: !!document.querySelector('#flExplore [data-tab="key"]'),
      explorerSevenTabs: document.querySelectorAll('#flExplore .ws-tabs [role="tab"]').length === 7,
    };
    return {
      title: document.title,
      heading: txt(document.getElementById('flTitle')),
      corners, formCols: formCols.map(c => ({ name: c.name, rows: c.rows, empty: c.empty })),
      tape: tapeRows, late,
      market: txt(document.getElementById('flMarket')),
      chart: txt(document.getElementById('flChart')),
      books: [...document.querySelectorAll('#flBooks tbody tr')].map(r => txt(r)),
      checks,
    };
  });
  report.rendered = rendered;
  report.chartMsAfterPage = chartMs;
  report.consoleErrors = errors;
  await page.screenshot({ path: path.join(OUT, 'fight-' + id + '-' + name + '-full.png'), fullPage: true });
  await ctx.close();
  return report;
}

(async () => {
  const ids = await pickFights();
  const browser = await chromium.launch();
  const out = {};
  for (const id of ids) {
    out[id] = {
      desktop: await shoot(browser, id, { name: 'desktop', viewport: { width: 1440, height: 900 } }),
      mobile: await shoot(browser, id, { name: 'mobile', viewport: { width: 390, height: 844 }, mobile: true }),
    };
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, 'fight-lab-report.json'), JSON.stringify(out, null, 2));
  console.log('::group::fight lab report');
  console.log(JSON.stringify(out, null, 2));
  console.log('::endgroup::');
  const failed = [];
  for (const [id, r] of Object.entries(out)) {
    for (const k of ['desktop', 'mobile']) {
      if (!r[k].rendered) failed.push(id + ' ' + k + ': page did not finish rendering');
      if (r[k].consoleErrors.length) failed.push(id + ' ' + k + ': console errors: ' + r[k].consoleErrors.join(' | '));
      for (const [c, v] of Object.entries(r[k].checks)) if (!v) failed.push(id + ' ' + k + ': ' + c);
    }
  }
  if (failed.length) { console.log('FIGHT LAB CHECKS FAILED:\n  ' + failed.join('\n  ')); process.exit(1); }
  console.log('All Fight Lab checks passed for fights ' + ids.join(', ') + '.');
})().catch(e => { console.error('VERIFY FAILED', e); process.exit(1); });
