#!/usr/bin/env node
/*
 * T-089 — Cannon Card Brief signup, driven in a real browser (Chromium).
 *
 * WHAT THIS IS, STATED HONESTLY
 *
 *   This is a BROWSER test against a MOCKED DATABASE. It loads the real
 *   index.html, the real _shared.js / _auth.js and the real supabase-js build
 *   the page pins, types an address into the real form and presses the real
 *   button. Every request to *.supabase.co is intercepted with page.route and
 *   answered by this script. Nothing here reaches the production database.
 *
 *   What it proves: the browser sends a PLAIN INSERT to
 *   /rest/v1/email_subscribers (no on_conflict, no Prefer resolution=...), with
 *   the address lowercased and trimmed and the capture's source; a success, a
 *   duplicate (409 / 23505) and a failure (500 / 42501) each show the right
 *   message, and the database's own wording never reaches the visitor; an
 *   invalid address sends no request at all.
 *
 *   What it does NOT prove:
 *     - that production accepts the insert. That proof is separate: the anon
 *       rolled-back insert against the real database (T-088/T-089).
 *     - that a genuine submission on the live site works. That has NOT been
 *       done.
 *
 * THE SUPABASE SCRIPT AND ITS SRI HASH
 *
 *   index.html loads supabase-js from cdn.jsdelivr.net with an integrity=
 *   sha384 hash. This test never strips or changes that attribute, so the
 *   browser enforces it on every run. The bytes come from, in order:
 *     1. CFL_SUPABASE_UMD=<path>: a local copy. Its sha384 is checked against
 *        the page's integrity= BEFORE it is served; a mismatch fails the test.
 *        (Use this offline. The npm tarball's dist/umd/supabase.js does NOT
 *        match: jsDelivr serves its own minified build at .../supabase.min.js.)
 *     2. Otherwise the request goes to the real CDN untouched (CI runners).
 *   If neither works, the page cannot run supabase-js and the test fails. It
 *   does not fall back to an unverified copy.
 *
 * RUN
 *   node tests/browser/card-brief-signup.browser.js
 *   Needs the `playwright` package resolvable (NODE_PATH or a local install)
 *   and a Chromium playwright can launch (CHROMIUM_PATH to override).
 *
 * Deliberately NOT named *.test.js: the dependency-free node loop in
 * tests.yml runs every tests/*.test.js, and this one needs a browser.
 */
'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..', '..');
const PAGE = 'index.html';
const SOURCE = 'home-bottom'; // data-source of the capture on index.html

const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'application/javascript',
  '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.xml': 'application/xml', '.ico': 'image/x-icon',
};

function serve() {
  const server = http.createServer((req, res) => {
    let p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    if (p.endsWith('/')) p += 'index.html';
    const file = path.join(ROOT, p);
    if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404); res.end('not found'); return;
    }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream' });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise(r => server.listen(0, '127.0.0.1', () => r(server)));
}

// The pinned script tag, read from the page itself so the test follows a bump.
const html = fs.readFileSync(path.join(ROOT, PAGE), 'utf8');
const tag = html.match(/<script src="(https:\/\/cdn\.jsdelivr\.net\/npm\/@supabase\/supabase-js@[^"]+)" integrity="(sha384-[^"]+)"/);
if (!tag) { console.error('FAIL: could not find the pinned supabase-js <script> in ' + PAGE); process.exit(1); }
const [, CDN_URL, SRI] = tag;

let localUmd = null;
if (process.env.CFL_SUPABASE_UMD) {
  localUmd = fs.readFileSync(process.env.CFL_SUPABASE_UMD);
  const got = 'sha384-' + crypto.createHash('sha384').update(localUmd).digest('base64');
  if (got !== SRI) {
    console.error(`FAIL: CFL_SUPABASE_UMD hash ${got} does not match the page's integrity ${SRI}. Refusing to serve it.`);
    process.exit(1);
  }
}

let passed = 0, failed = 0;
function check(name, cond, detail) {
  if (cond) { passed++; console.log('  ok   ' + name); }
  else { failed++; console.log('  FAIL ' + name + (detail ? ' — ' + detail : '')); }
}

// Answers for the insert, per case.
const RESPONSES = {
  success: { status: 201, body: '' },
  duplicate: { status: 409, body: JSON.stringify({ code: '23505', details: 'Key (email)=(x) already exists.', hint: null, message: 'duplicate key value violates unique constraint "email_subscribers_email_key"' }) },
  failure: { status: 500, body: JSON.stringify({ code: '42501', details: null, hint: null, message: 'new row violates row-level security policy for table "email_subscribers"' }) },
};

async function runCase(browser, base, name, typed, response) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const inserts = [];
  const pageErrors = [];
  let cdnServedBy = null;
  page.on('pageerror', e => pageErrors.push(String(e && e.message || e)));

  await page.route('**/*', async (route) => {
    const req = route.request();
    const url = req.url();
    if (url.startsWith(base)) return route.continue();
    if (url === CDN_URL) {
      if (localUmd) {
        cdnServedBy = 'local copy (hash checked)';
        return route.fulfill({ status: 200, contentType: 'application/javascript',
          headers: { 'Access-Control-Allow-Origin': '*' }, body: localUmd });
      }
      cdnServedBy = 'live CDN';
      return route.continue();
    }
    if (/\.supabase\.co\//.test(url)) {
      const u = new URL(url);
      if (req.method() === 'POST' && u.pathname === '/rest/v1/email_subscribers') {
        inserts.push({ url, headers: req.headers(), body: req.postData() });
        return route.fulfill({ status: response.status, contentType: 'application/json',
          headers: { 'Access-Control-Allow-Origin': '*' }, body: response.body });
      }
      if (req.method() === 'OPTIONS') {
        return route.fulfill({ status: 204, headers: { 'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*' } });
      }
      // Every other read: an empty result. Writes (e.g. funnel_events): accepted.
      return route.fulfill({ status: req.method() === 'GET' ? 200 : 201, contentType: 'application/json',
        headers: { 'Access-Control-Allow-Origin': '*', 'Content-Range': '*/0' },
        body: req.method() === 'GET' ? '[]' : '' });
    }
    return route.abort(); // analytics, fonts, anything else external
  });

  await page.goto(base + '/' + PAGE, { waitUntil: 'domcontentloaded' });
  const ready = await page.waitForFunction(() => !!(window.supabase && window.cflAuth && window.cflAuth.subscribeEmail),
    null, { timeout: 20000 }).then(() => true, () => false);
  check(`[${name}] supabase-js loaded under its SRI hash (${cdnServedBy || 'not requested'})`, ready,
    'window.supabase never appeared — CDN unreachable or integrity rejected; pageerrors: ' + pageErrors.slice(0, 3).join(' | '));
  if (!ready) { await context.close(); return; }

  const cap = page.locator(`.cfl-email-capture[data-source="${SOURCE}"]`);
  await cap.locator('input[type=email]').waitFor({ timeout: 10000 });
  await cap.locator('input[type=email]').fill(typed);
  await cap.locator('button[type=submit]').click();
  const msg = cap.locator('.cfl-email-capture-msg');
  await page.waitForFunction(el => el.textContent.trim().length > 0, await msg.elementHandle(), { timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(300); // let any late request land before counting
  const text = (await msg.textContent()).trim();
  const cls = await msg.getAttribute('class');

  if (name === 'invalid') {
    check('[invalid] no request sent to email_subscribers', inserts.length === 0, `${inserts.length} sent`);
    check('[invalid] shows the validation message', text === 'Please enter a valid email address.', JSON.stringify(text));
    await context.close();
    return;
  }

  check(`[${name}] exactly one POST to /rest/v1/email_subscribers`, inserts.length === 1, `${inserts.length} sent`);
  if (inserts.length) {
    const ins = inserts[0];
    const u = new URL(ins.url);
    const prefer = ins.headers['prefer'] || '';
    check(`[${name}] plain insert: no on_conflict in the URL`, !u.searchParams.has('on_conflict'), ins.url);
    check(`[${name}] plain insert: Prefer has no resolution=`, !/resolution=/.test(prefer), 'Prefer: ' + prefer);
    let body = null; try { body = JSON.parse(ins.body); } catch (_) {}
    const row = Array.isArray(body) ? body[0] : body;
    const want = typed.trim().toLowerCase();
    check(`[${name}] body email is trimmed + lowercased`, row && row.email === want, ins.body);
    check(`[${name}] body source is "${SOURCE}"`, row && row.source === SOURCE, ins.body);
    check(`[${name}] body carries only email and source`, row && Object.keys(row).sort().join(',') === 'email,source', ins.body);
    console.log(`       request: POST ${u.pathname}${u.search}  Prefer: ${prefer || '(none)'}  body: ${ins.body}`);
  }
  if (name === 'success' || name === 'duplicate') {
    check(`[${name}] shows the success message`, /^Subscribed\./.test(text) && /\bok\b/.test(cls), `${JSON.stringify(text)} class=${cls}`);
  } else {
    check(`[${name}] shows the generic error`, text === 'Something went wrong. Try again.' && /\berr\b/.test(cls), `${JSON.stringify(text)} class=${cls}`);
    check(`[${name}] never shows the database wording`, !/row-level|violates|42501|email_subscribers|policy/i.test(text), JSON.stringify(text));
  }
  console.log(`       message shown: ${JSON.stringify(text)}`);
  await context.close();
}

(async () => {
  console.log('T-089 browser test — mocked database, real page, real supabase-js (SRI enforced).');
  console.log(`  page: ${PAGE}  capture: data-source="${SOURCE}"  supabase-js: ${CDN_URL}`);
  const server = await serve();
  const base = `http://127.0.0.1:${server.address().port}`;
  const opts = { headless: true };
  if (process.env.CHROMIUM_PATH) opts.executablePath = process.env.CHROMIUM_PATH;
  const browser = await chromium.launch(opts);
  console.log(`  browser: Chromium ${browser.version()}`);
  try {
    await runCase(browser, base, 'success', '  Reed.Test+T089@Example.COM ', RESPONSES.success);
    await runCase(browser, base, 'duplicate', 'Already.There@Example.com', RESPONSES.duplicate);
    await runCase(browser, base, 'failure', 'rls.denied@example.com', RESPONSES.failure);
    await runCase(browser, base, 'invalid', 'not-an-email', RESPONSES.success);
  } finally {
    await browser.close();
    server.close();
  }
  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
