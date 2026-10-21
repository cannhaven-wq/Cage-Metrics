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
  // Card Lab is a compact list since T-100/T-101 (2026-10-16): one
  // `.cl-item` per fight in #fightsList, both corners' best price as `.cl-ob`
  // in the row, and the main event opens on arrival with its Line Movement
  // panel (`.fx-p-move`). This script waited for the pre-redesign `.fight` /
  // `.probs` markup until 2026-10-21 and so reported a healthy page as "card
  // did not render" — the selectors below are the current markup.
  let rendered = true;
  try {
    await page.waitForFunction(() => document.querySelectorAll('#fightsList .cl-item').length >= 1 && !!document.querySelector('#heroGlance .glance'), null, { timeout: 45000 });
  } catch (e) { rendered = false; }
  // The opened fight's panels load after the row; give the movement panel time.
  await page.waitForFunction(() => {
    const m = document.querySelector('#fightsList .cl-item.open .fx-p-move');
    return !!m && !/Loading/.test(m.textContent.replace(/Loading the line…/, ''));
  }, null, { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(800);
  const report = await page.evaluate(() => {
    const txt = el => el ? el.textContent.replace(/\s+/g, ' ').trim() : null;
    const items = [...document.querySelectorAll('#fightsList .cl-item')];
    return {
      title: document.title,
      metaDescription: (document.querySelector('meta[name="description"]') || {}).content || null,
      heroEyebrow: txt(document.querySelector('.hero .eyebrow, .eyebrow')),
      heroTitle: txt(document.querySelector('h1')),
      glance: [...document.querySelectorAll('#heroGlance .glance .cell')].map(c => txt(c)),
      gaps: [...document.querySelectorAll('#heroGlance .gap-list li')].map(li => txt(li)),
      sortOptions: [...document.querySelectorAll('#sortSel option')].map(o => o.value),
      fights: items.map(f => ({
        id: f.id,
        open: f.classList.contains('open'),
        row: txt(f.querySelector('.cl-row')),
        bestPrices: [...f.querySelectorAll('.cl-row .cl-ob')].map(o => txt(o) + (o.classList.contains('none') ? ' [' + (o.getAttribute('title') || '') + ']' : '')),
      })),
      openMovement: txt(document.querySelector('#fightsList .cl-item.open .fx-p-move')),
      scripts: [...document.querySelectorAll('script[src]')].map(s => s.getAttribute('src')),
      checks: (() => {
        // Visible text only: inline scripts carry comments that document the
        // very rules checked here (see the no-opening-line note in index.html).
        const clone = document.body.cloneNode(true);
        clone.querySelectorAll('script, style, noscript, template').forEach(n => n.remove());
        const body = clone.textContent;
        const open = document.querySelector('#fightsList .cl-item.open .fx-p-move');
        return {
          // --- nothing sells a bet ---------------------------------------
          noValueAlert: !/Value alert/.test(body),
          noConsensusExcuse: !/no consensus line/.test(body),
          noEdgePercent: !/\bEdge\s*[+-]?\d+(\.\d+)?\s*%/i.test(body),
          // --- the forecast is off the product (D-011) -------------------
          // A NUMBER attributed to the model or to CFL. Not the words: the
          // homepage says plainly that "we used to publish a model forecast",
          // which is the disclosure D-011 asks for, not a forecast.
          noModelNumber: !/\b(model|engine|CFL|our pick)\b[^.%\n]{0,40}\b\d{1,3}(\.\d+)?\s*%/i.test(body),
          noPickBar: document.querySelectorAll('#fightsList .pickbar').length === 0,
          // --- every row carries both corners' best price -----------------
          everyFightHasBothBestPrices:
            items.length > 0 && items.every(f => f.querySelectorAll('.cl-row .cl-ob').length === 2),
          // A dash is allowed; a dash with no reason beside it is not.
          everyDashExplainsItself:
            [...document.querySelectorAll('#fightsList .cl-ob.none')].every(o => /book|line|quote|price/i.test(o.getAttribute('title') || '')),
          // --- movement says what it measured (D-012) --------------------
          // CFL has never observed a sportsbook opener and may not imply it.
          noOpeningLineClaim:
            !/since open\b/i.test(body) && !/opening line/i.test(body),
          mainEventOpensOnArrival: !!document.querySelector('#fightsList .cl-item.is-main.open'),
          movementIsLabelledAsACapture: !!open && /first broad capture/i.test(open.textContent),
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
    // Sorts since T-100: card position / biggest move / books disagree.
    for (const sort of ['move', 'spread']) {
      await page.selectOption('#sortSel', sort).catch(() => {});
      await page.waitForTimeout(300);
      report['sortedBy_' + sort] = await page.evaluate(() =>
        [...document.querySelectorAll('#fightsList .cl-item .cl-row')].map(r => r.textContent.replace(/\s+/g, ' ').trim()));
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
