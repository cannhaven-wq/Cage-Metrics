// Stabilization checks on the LIVE site, run by .github/workflows/verify-live.yml
// (job "Stabilization checks"). Same reason as verify-live.js: agent sessions
// cannot reach cannonfightlab.com, GitHub's runners can.
//
// What it checks:
//   T-086  DWCS 10.3 (event 4259) is shown as "Not a UFC event", its old
//          stub URL still answers and is noindex, and the sitemap omits it.
//   pages  Each product page loads with no uncaught script error.
//   T-089  Only when SUBMIT_CARD_BRIEF=true: submits the real Card Brief form
//          on the homepage with a controlled address (CARD_BRIEF_EMAIL, which
//          must end in @example.invalid so no mail can ever be delivered), then
//          submits it again to prove a repeat address reads as success. That
//          writes ONE row to email_subscribers; whoever runs it removes the
//          row afterwards. Marketing email is locked anyway (T-090).
'use strict';
const { chromium } = require('playwright');

const BASE = process.env.BASE_URL || 'https://cannonfightlab.com';
const FIGHT_ID = (process.env.FIGHT_ID || '').split(',')[0].trim();
const FIGHTER_ID = process.env.FIGHTER_ID || '';
const SUBMIT = /^(1|true|yes)$/i.test(process.env.SUBMIT_CARD_BRIEF || '');
const EMAIL = (process.env.CARD_BRIEF_EMAIL || '').trim().toLowerCase();

const failed = [];
const check = (name, ok, detail) => {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
  if (!ok) failed.push(name);
};
const text = s => (s || '').replace(/\s+/g, ' ').trim();

async function open(browser, url, waitFor) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  const res = await page.goto(BASE + url, { waitUntil: 'load', timeout: 60000 });
  if (waitFor) await page.waitForFunction(waitFor, null, { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(1500);
  return { ctx, page, errors, status: res ? res.status() : 0 };
}

(async () => {
  const browser = await chromium.launch();

  // --- T-086 ---------------------------------------------------------------
  {
    const { ctx, page, errors } = await open(browser, '/event.html?id=4259',
      () => /Not a UFC event/i.test(document.body.innerText));
    const body = text(await page.evaluate(() => document.body.innerText));
    check('event.html?id=4259 says "Not a UFC event"', /Not a UFC event/i.test(body), body.slice(0, 160));
    check('event.html?id=4259 has no script error', errors.length === 0, errors.join(' | '));
    await ctx.close();
  }
  {
    const r = await fetch(BASE + '/e/dwcs-10-3-4259.html?v=' + Date.now());
    const html = await r.text();
    check('old stub /e/dwcs-10-3-4259.html answers 200', r.status === 200, 'HTTP ' + r.status);
    check('old stub is noindex and says not a UFC event',
      /name="robots" content="noindex/.test(html) && /not a UFC event/i.test(html));
  }
  {
    const r = await fetch(BASE + '/sitemap.xml?v=' + Date.now());
    const xml = await r.text();
    check('sitemap.xml served', r.status === 200 && xml.includes('<urlset'), 'HTTP ' + r.status);
    check('sitemap.xml omits DWCS 10.3', !/dwcs-10-3-4259/.test(xml));
  }

  // --- pages load ----------------------------------------------------------
  const pages = [
    ['/', () => document.querySelectorAll('#fightsList .fight').length > 0],
    ['/market.html', () => document.body.innerText.length > 500],
    ['/fighters.html', () => document.body.innerText.length > 500],
    ['/stats.html', () => document.body.innerText.length > 500],
    ['/login.html', null],
    ['/signup.html', null],
    ['/watchlist.html', null],
  ];
  if (FIGHT_ID) pages.push(['/fight.html?id=' + encodeURIComponent(FIGHT_ID), () => document.body.innerText.length > 500]);
  if (FIGHTER_ID) pages.push(['/fighter.html?id=' + encodeURIComponent(FIGHTER_ID), () => document.body.innerText.length > 500]);
  for (const [url, wait] of pages) {
    const { ctx, page, errors, status } = await open(browser, url, wait);
    const nav = await page.evaluate(() => !!document.querySelector('.cfl-nav a'));
    const t = text(await page.evaluate(() => document.body.innerText));
    check(`${url} loads (HTTP ${status}), nav renders, no script error`,
      status === 200 && nav && errors.length === 0, errors.join(' | ') || t.slice(0, 100));
    if (url.startsWith('/fighter.html')) console.log('      fighter page text: ' + t.slice(0, 400));
    await ctx.close();
  }

  // --- T-089 ---------------------------------------------------------------
  if (SUBMIT) {
    if (!/@example\.invalid$/.test(EMAIL)) {
      check('CARD_BRIEF_EMAIL is an @example.invalid address', false, EMAIL || '(empty)');
    } else {
      for (const attempt of ['first signup', 'repeat signup (23505 reads as success)']) {
        const { ctx, page, errors } = await open(browser, '/', () => !!document.querySelector('.cfl-email-capture-form input'));
        const form = page.locator('.cfl-email-capture-form').first();
        await form.locator('input[type=email]').fill(EMAIL);
        await form.locator('button[type=submit]').click();
        const msg = page.locator('.cfl-email-capture-msg').first();
        await page.waitForFunction(() => {
          const m = document.querySelector('.cfl-email-capture-msg');
          return m && (m.classList.contains('ok') || m.classList.contains('err'));
        }, null, { timeout: 20000 }).catch(() => {});
        const cls = (await msg.getAttribute('class')) || '';
        check(`Card Brief ${attempt}`, /\bok\b/.test(cls) && errors.length === 0, text(await msg.textContent()));
        await ctx.close();
      }
    }
  } else {
    console.log('SKIP  Card Brief submission (SUBMIT_CARD_BRIEF is not true)');
  }

  await browser.close();
  if (failed.length) { console.log('\nCHECKS FAILED:\n  ' + failed.join('\n  ')); process.exit(1); }
  console.log('\nAll stabilization checks passed.');
})().catch(e => { console.error('VERIFY FAILED', e); process.exit(1); });
