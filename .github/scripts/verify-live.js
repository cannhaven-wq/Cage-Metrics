// Loads the LIVE homepage in headless Chromium, with real data, and reports
// what a visitor actually sees. Run by .github/workflows/verify-live.yml.
//
// Read-only. It opens https://cannonfightlab.com/ like a browser would, waits
// for the card to render from the production database, and prints a report:
// the title, the hero, the card header and odds-status line, every fight
// row's market cells, and a handful of yes/no checks
// (no "Value alert", no "no consensus line", no "Edge" cell, no horizontal
// overflow on a phone). Screenshots go to the directory named by OUT_DIR and
// are uploaded as a workflow artifact.
//
// Why this exists: the agent sessions that ship the site run behind an egress
// policy that blocks cannonfightlab.com, so "it built" was the only thing they
// could see. This runs on GitHub's network and looks at the served page.
'use strict';
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const BASE = process.env.BASE_URL || 'https://cannonfightlab.com';
const OUT = process.env.OUT_DIR || 'live-shots';
fs.mkdirSync(OUT, { recursive: true });

async function shoot(browser, { name, viewport, mobile }) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: mobile ? 2 : 1, isMobile: !!mobile, hasTouch: !!mobile });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  const bust = 'verify=' + Date.now();
  const res = await page.goto(BASE + '/?' + bust, { waitUntil: 'load', timeout: 60000 });
  const headers = res ? res.headers() : {};
  let rendered = true;
  try {
    await page.waitForFunction(() => document.querySelectorAll('#fightsList .fight').length >= 1 && !!document.querySelector('#heroGlance .glance'), null, { timeout: 45000 });
  } catch (e) { rendered = false; }
  await page.waitForTimeout(800);
  const report = await page.evaluate(() => {
    const txt = el => el ? el.textContent.replace(/\s+/g, ' ').trim() : null;
    return {
      title: document.title,
      metaDescription: (document.querySelector('meta[name="description"]') || {}).content || null,
      heroEyebrow: txt(document.getElementById('heroEyebrow')),
      heroTitle: txt(document.getElementById('heroTitle')),
      hpProof: txt(document.getElementById('hpProof')),
      glance: [...document.querySelectorAll('#heroGlance .glance .cell')].map(c => txt(c)),
      gaps: [...document.querySelectorAll('#heroGlance .gap-list li')].map(li => txt(li)),
      cardHead: txt(document.getElementById('cardHead')),
      oddsStatus: txt(document.getElementById('oddsStatus')),
      sortButtons: [...document.querySelectorAll('#sortSeg button')].map(b => b.textContent.trim()),
      fights: [...document.querySelectorAll('#fightsList .fight')].map(f => ({
        id: f.id,
        head: txt(f.querySelector('.fight-hd')),
        cells: [...f.querySelectorAll('.probs .cell')].map(c => txt(c)),
        marketNote: txt(f.querySelector('.mkt-note')),
      })),
      scripts: [...document.querySelectorAll('script[src]')].map(s => s.getAttribute('src')),
      checks: (() => {
        const body = document.body.textContent;
        const rows = [...document.querySelectorAll('#fightsList .fight .probs')];
        const cellTitles = [...document.querySelectorAll('.probs .cell .t')].map(t => t.textContent.trim());
        const cellNums = [...document.querySelectorAll('.probs .cell .n')].map(n => n.textContent.trim());
        return {
          // --- nothing sells a bet ---------------------------------------
          noValueAlert: !/Value alert/.test(body),
          noConsensusExcuse: !/no consensus line/.test(body),
          noEdgeCell: cellTitles.indexOf('Edge') === -1,
          noEdgePercent: !cellNums.some(n => /^[+-]\d+%$/.test(n)),

          // --- the forecast is off the product (D-011) -------------------
          noModelColumn: cellTitles.indexOf('Model') === -1 && cellTitles.indexOf('CFL') === -1,
          noPickBar: document.querySelectorAll('#fightsList .fight .pickbar').length === 0,

          // --- movement says what it measured (D-012) --------------------
          // The card shows four market cells: consensus, fair price, market
          // move, best price. It was three before the repositioning, and this
          // assertion said 3 — that is what it is pinning.
          everyFightHasFourMarketCells:
            rows.length > 0 && rows.every(p => p.querySelectorAll('.cell').length === 4),
          // "Since open" was a column header until 2026-09-21. CFL has never
          // observed a sportsbook opener and may not imply that it has.
          noOpeningLineClaim:
            !/since open\b/i.test(body) && !/opening line/i.test(body),
          movementIsLabelledAsACapture:
            cellTitles.indexOf('Market move') !== -1,
          // A dash is allowed; a dash with no reason beside it is not.
          everyMarketNoteExplainsItself:
            [...document.querySelectorAll('#fightsList .fight')].every(f => {
              const n = f.querySelector('.mkt-note');
              const t = n ? n.textContent : '';
              return !n || /sportsbook|book|capture|comparable|priced/i.test(t);
            }),

          // --- layout ---------------------------------------------------
          noHorizontalOverflow: document.documentElement.scrollWidth <= window.innerWidth,
        };
      })(),
    };
  });
  report.rendered = rendered;
  report.httpStatus = res ? res.status() : null;
  report.responseHeaders = { 'cache-control': headers['cache-control'], age: headers.age, etag: headers.etag, 'last-modified': headers['last-modified'], 'x-served-by': headers['x-served-by'], 'x-cache': headers['x-cache'] };
  report.consoleErrors = errors;
  await page.screenshot({ path: path.join(OUT, name + '-full.png'), fullPage: true });
  await page.screenshot({ path: path.join(OUT, name + '-top.png') });
  if (rendered) {
    // The sort was data-sort="disagree" before the repositioning; it is now
    // "move" (biggest market move) and "spread" (books disagree).
    for (const sort of ['move', 'spread']) {
      await page.click('#sortSeg button[data-sort="' + sort + '"]').catch(() => {});
      await page.waitForTimeout(300);
      report['sortedBy_' + sort] = await page.evaluate(() =>
        [...document.querySelectorAll('#fightsList .fight')].map(f => {
          const m = f.querySelector('.matchup');
          const cells = [...f.querySelectorAll('.probs .cell')].map(c => c.textContent.replace(/\s+/g, ' ').trim());
          return (m ? m.textContent.replace(/\s+/g, ' ').trim() : f.id) + ' | ' + cells.join(' | ');
        }));
      await page.locator('#next').screenshot({ path: path.join(OUT, name + '-card-by-' + sort + '.png') }).catch(() => {});
    }
  }
  await ctx.close();
  return report;
}

(async () => {
  const browser = await chromium.launch();
  const out = {
    desktop: await shoot(browser, { name: 'live-desktop', viewport: { width: 1440, height: 900 } }),
    mobile: await shoot(browser, { name: 'live-mobile', viewport: { width: 390, height: 844 }, mobile: true }),
  };
  await browser.close();
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(out, null, 2));
  console.log('::group::live report');
  console.log(JSON.stringify(out, null, 2));
  console.log('::endgroup::');
  const failed = [];
  for (const k of ['desktop', 'mobile']) {
    if (!out[k].rendered) failed.push(k + ': card did not render');
    for (const [c, v] of Object.entries(out[k].checks)) if (!v) failed.push(k + ': ' + c);
  }
  if (failed.length) { console.log('CHECKS FAILED:\n  ' + failed.join('\n  ')); process.exit(1); }
  console.log('All live checks passed.');
})().catch(e => { console.error('VERIFY FAILED', e); process.exit(1); });
