// Loads the LIVE homepage in headless Chromium, with real data, and reports
// what a visitor actually sees. Run by .github/workflows/verify-live.yml.
//
// Read-only. It opens https://cannonfightlab.com/ like a browser would, waits
// for the card to render from the production database, and prints a report:
// the title, the hero, the card header and odds-status line, every fight
// row's model / market / difference cells, and a handful of yes/no checks
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
        pick: txt(f.querySelector('.pickbar')),
        cells: [...f.querySelectorAll('.probs .cell')].map(c => txt(c)),
      })),
      scripts: [...document.querySelectorAll('script[src]')].map(s => s.getAttribute('src')),
      checks: {
        noValueAlert: !/Value alert/.test(document.body.textContent),
        noConsensusExcuse: !/no consensus line/.test(document.body.textContent),
        noEdgeCell: ![...document.querySelectorAll('.probs .cell .t')].some(t => t.textContent.trim() === 'Edge'),
        noEdgePercent: ![...document.querySelectorAll('.probs .cell .n')].some(n => /^[+-]\d+%$/.test(n.textContent.trim())),
        everyPickedFightHasMarketCell: [...document.querySelectorAll('#fightsList .fight .probs')].every(p => p.querySelectorAll('.cell').length === 3),
        noHorizontalOverflow: document.documentElement.scrollWidth <= window.innerWidth,
      },
    };
  });
  report.rendered = rendered;
  report.httpStatus = res ? res.status() : null;
  report.responseHeaders = { 'cache-control': headers['cache-control'], age: headers.age, etag: headers.etag, 'last-modified': headers['last-modified'], 'x-served-by': headers['x-served-by'], 'x-cache': headers['x-cache'] };
  report.consoleErrors = errors;
  await page.screenshot({ path: path.join(OUT, name + '-full.png'), fullPage: true });
  await page.screenshot({ path: path.join(OUT, name + '-top.png') });
  if (rendered) {
    await page.click('#sortSeg button[data-sort="disagree"]').catch(() => {});
    await page.waitForTimeout(300);
    report.sortedByDisagreement = await page.evaluate(() => [...document.querySelectorAll('#fightsList .fight')].map(f => (f.querySelector('.matchup') ? f.querySelector('.matchup').textContent.replace(/\s+/g, ' ').trim() : f.id) + ' | ' + (f.querySelector('.probs .cell:nth-child(3)') ? f.querySelector('.probs .cell:nth-child(3)').textContent.replace(/\s+/g, ' ').trim() : '')));
    await page.locator('#next').screenshot({ path: path.join(OUT, name + '-card-by-disagreement.png') }).catch(() => {});
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
