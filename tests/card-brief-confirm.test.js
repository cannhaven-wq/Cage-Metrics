// Card Brief double opt-in (T-090, D-027): the pure rules, the sender's
// locks, and the confirm page.
//
// What this pins, in plain words:
//   * the Brief only ever goes to an address that clicked its confirm link;
//   * the link's token is random, the database only ever gets its hash, and
//     a log never prints a working link;
//   * an address that did not ask is emailed at most once;
//   * the confirmation sender is locked (named blockers, no schedule);
//   * confirm.html calls the confirm function and says what happened in plain
//     words, without echoing anything from the database.
// The database half is proven against a real Postgres in
// tests/test_card_brief_optin_sql.py.
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const ROOT = path.join(__dirname, '..');
const read = p => fs.readFileSync(path.join(ROOT, p), 'utf8');
const C = require('../build/card-brief-confirm');

let n = 0, failed = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { failed++; console.error('FAIL', name, '\n  ', e.message); } };
const ok = (c, m) => { if (!c) throw new Error(m); };

const NOW = new Date('2026-10-21T12:00:00Z');
const fixedBytes = b => () => Buffer.alloc(32, b);

// ---- who receives the Brief -------------------------------------------------
const ROWS = [
  { email: 'confirmed@x.invalid', confirmed_at: '2026-10-20T10:00:00Z', unsubscribed_at: null },
  { email: 'unconfirmed@x.invalid', confirmed_at: null, unsubscribed_at: null },
  { email: 'missing-field@x.invalid', unsubscribed_at: null },
  { email: 'empty-string@x.invalid', confirmed_at: '', unsubscribed_at: null },
  { email: 'confirmed-then-left@x.invalid', confirmed_at: '2026-10-01T00:00:00Z', unsubscribed_at: '2026-10-10T00:00:00Z' },
  { email: '', confirmed_at: '2026-10-20T10:00:00Z', unsubscribed_at: null },
  null,
];

t('only a confirmed, still-subscribed address is a Brief recipient', () => {
  const got = C.sendableBriefRecipients(ROWS).map(r => r.email);
  ok(JSON.stringify(got) === JSON.stringify(['confirmed@x.invalid']), 'recipients were: ' + JSON.stringify(got));
});

t('an unconfirmed address is never in the send list, however it arrives', () => {
  for (const r of ROWS.filter(Boolean)) {
    if (r.email === 'confirmed@x.invalid') continue;
    ok(!C.isBriefRecipient(r), 'would send to ' + JSON.stringify(r));
  }
  ok(C.sendableBriefRecipients(undefined).length === 0, 'undefined input did not give an empty list');
  ok(C.sendableBriefRecipients([]).length === 0, 'empty input did not give an empty list');
});

const digest = read('build/send-digest.js');
const fetchSubs = digest.slice(digest.indexOf('async function fetchActiveSubscribers'), digest.indexOf('async function sendOne'));

t('the digest query asks only for confirmed, subscribed rows', () => {
  ok(fetchSubs.length > 100, 'fetchActiveSubscribers not found');
  ok(/\.not\('confirmed_at', 'is', null\)/.test(fetchSubs), 'the query no longer filters on confirmed_at');
  ok(/\.is\('unsubscribed_at', null\)/.test(fetchSubs), 'the query no longer filters out unsubscribed rows');
  ok(/select\('[^']*\bconfirmed_at\b[^']*'\)/.test(fetchSubs), 'confirmed_at is not selected, so the second filter cannot see it');
});

t('the digest filters what comes back a second time', () => {
  ok(/require\('\.\/card-brief-confirm'\)/.test(digest), 'send-digest.js does not use card-brief-confirm.js');
  ok(/return sendableBriefRecipients\(all\);/.test(fetchSubs), 'the fetched rows are not passed through sendableBriefRecipients');
  ok(!/return all;/.test(fetchSubs), 'an unfiltered list is returned somewhere');
});

t('a missing confirmed_at column means nobody, never everybody', () => {
  ok(/isMissingColumnError\(error\)\)\s*\{[\s\S]*?return \[\];/.test(fetchSubs), 'the missing-column case does not return an empty list');
  ok(C.isMissingColumnError({ code: '42703', message: 'column email_subscribers.confirmed_at does not exist' }), '42703 not recognised');
  ok(!C.isMissingColumnError({ code: '42501', message: 'permission denied' }), 'permission denied read as a missing column');
  ok(!C.isMissingColumnError(null), 'null read as an error');
});

t('every send in the digest goes to the filtered list', () => {
  const main = digest.slice(digest.indexOf('const subscribers = await fetchActiveSubscribers()'));
  ok(main.length > 100, 'the main loop no longer reads fetchActiveSubscribers()');
  ok(/for \(const sub of subscribers\)/.test(main), 'the send loop is not over the filtered list');
  ok((digest.match(/sendOne\(/g) || []).length === 2, 'sendOne is called from somewhere new');
});

// ---- the token ---------------------------------------------------------------
t('a token is 32 random bytes as 64 lower-case hex', () => {
  const a = C.newToken(), b = C.newToken();
  ok(C.isWellFormedToken(a) && C.isWellFormedToken(b), 'not 64 lower-case hex: ' + a);
  ok(a !== b, 'two tokens matched');
  ok(C.newToken(fixedBytes(0xab)) === 'ab'.repeat(32), 'did not use the injected byte source');
  let threw = false; try { C.newToken(() => Buffer.alloc(8)); } catch (e) { threw = true; }
  ok(threw, 'a short random source was accepted');
});

t('the hash is the same sha256 Postgres computes, and is not the token', () => {
  const tok = 'a'.repeat(64);
  const h = C.hashToken(tok);
  ok(h === crypto.createHash('sha256').update(tok).digest('hex'), 'not sha256 hex');
  // Same constant the SQL test stores for this token.
  ok(h === 'ffe054fe7ae0cb6dc65c3af9b61d5209f439851db43d0ba5997337df154668eb', 'hash does not match the SQL fixture');
  ok(h !== tok && /^[0-9a-f]{64}$/.test(h), 'hash shape');
  for (const bad of ['', 'A'.repeat(64), 'a'.repeat(63), null, undefined, 42]) {
    let threw = false; try { C.hashToken(bad); } catch (e) { threw = true; }
    ok(threw, 'hashed a non-token: ' + String(bad));
  }
});

t('the confirm link is the confirm page with the raw token', () => {
  const tok = 'c'.repeat(64);
  ok(C.confirmUrl(tok) === 'https://cannonfightlab.com/confirm.html?t=' + tok, C.confirmUrl(tok));
});

t('a log line never carries a working link', () => {
  const tok = '0123456789abcdef'.repeat(4);
  const r = C.redactedConfirmUrl(tok);
  ok(r.indexOf(tok) === -1 && r.indexOf(tok.slice(0, 8)) === -1, 'redacted link still holds the token: ' + r);
  const sender = read('build/send-confirmations.js').replace(/redactedConfirmUrl\(plan\.token\)/g, 'REDACTED');
  for (const line of sender.split('\n').filter(l => /console\.(log|warn|error)/.test(l))) {
    ok(!/plan\.(url|token)|confirmUrl\(|\btoken\b(?!s)/.test(line.replace(/'[^']*'/g, '')), 'send-confirmations.js may log a raw link or token: ' + line.trim());
  }
});

// ---- who gets a confirmation email, and what is recorded -----------------------
const base = { id: 1, email: 'new@x.invalid', unsubscribed_at: null, confirmed_at: null, confirm_token_hash: null, confirm_token_expires_at: null, confirm_send_count: 0 };

t('a new, unconfirmed address is due one confirmation email', () => {
  ok(C.needsConfirmation(base, NOW), 'not due');
});

t('confirmed, unsubscribed, already-mailed or live-link addresses are not', () => {
  ok(!C.needsConfirmation({ ...base, confirmed_at: '2026-10-20T00:00:00Z' }, NOW), 'confirmed');
  ok(!C.needsConfirmation({ ...base, unsubscribed_at: '2026-10-20T00:00:00Z' }, NOW), 'unsubscribed');
  ok(!C.needsConfirmation({ ...base, confirm_send_count: C.MAX_CONFIRM_SENDS }, NOW), 'already sent the maximum');
  ok(!C.needsConfirmation({ ...base, confirm_send_count: 0, confirm_token_hash: 'f'.repeat(64), confirm_token_expires_at: '2026-10-25T00:00:00Z' }, NOW), 'live link re-issued');
  ok(!C.needsConfirmation({ ...base, email: '' }, NOW), 'no address');
  ok(!C.needsConfirmation(null, NOW), 'null row');
});

t('an address that did not ask is mailed at most once', () => {
  ok(C.MAX_CONFIRM_SENDS === 1, 'MAX_CONFIRM_SENDS is ' + C.MAX_CONFIRM_SENDS + ' — more than one unasked email needs an owner decision');
  ok(!C.needsConfirmation({ ...base, confirm_send_count: 1, confirm_token_hash: 'f'.repeat(64), confirm_token_expires_at: '2026-10-01T00:00:00Z' }, NOW),
     'an expired link is re-sent automatically');
});

t('the record written before sending holds the hash, never the token', () => {
  const plan = C.planConfirmation(base, NOW, fixedBytes(0x11));
  ok(plan.token === '11'.repeat(32), 'token');
  const u = plan.update;
  ok(JSON.stringify(Object.keys(u).sort()) === JSON.stringify(['confirm_send_count', 'confirm_sent_at', 'confirm_token_expires_at', 'confirm_token_hash']),
     'unexpected columns written: ' + Object.keys(u));
  ok(u.confirm_token_hash === C.hashToken(plan.token), 'hash');
  ok(JSON.stringify(u).indexOf(plan.token) === -1, 'the raw token is in the database write');
  ok(u.confirm_token_expires_at === '2026-10-28T12:00:00.000Z', 'expiry is not a week: ' + u.confirm_token_expires_at);
  ok(u.confirm_sent_at === NOW.toISOString(), 'sent_at');
  ok(u.confirm_send_count === 1 && plan.expectSendCount === 0, 'send count compare-and-set');
  ok(!('confirmed_at' in u), 'the sender writes confirmed_at');
});

// ---- the sender is locked --------------------------------------------------------
const sender = read('build/send-confirmations.js');

t('confirmation sending is blocked by name until the owner clears it', () => {
  const m = read('build/card-brief-confirm.js').match(/const CONFIRM_SEND_BLOCKERS = \[([\s\S]*?)\];/);
  ok(m && /T-090/.test(m[1]), 'CONFIRM_SEND_BLOCKERS is gone or no longer names T-090');
  ok(C.CONFIRM_SEND_BLOCKERS.length >= 1, 'no blocker stands');
  ok(C.confirmDryRun({ resendKey: 'live-key', envDryRun: '' }) === true, 'a key alone turns sending on while a blocker stands');
  ok(C.confirmDryRun({ resendKey: 'live-key', envDryRun: '', blockers: [] }) === false, 'the switch does not work at all once cleared');
  ok(C.confirmDryRun({ resendKey: '', envDryRun: '', blockers: [] }) === true, 'no key is not a dry run');
  ok(C.confirmDryRun({ resendKey: 'k', envDryRun: '1', blockers: [] }) === true, 'CONFIRM_DRY_RUN=1 ignored');
  ok(/const DRY_RUN = C\.confirmDryRun\(/.test(sender), 'send-confirmations.js does not take DRY_RUN from confirmDryRun');
  ok(/sending is blocked by: ' \+ C\.CONFIRM_SEND_BLOCKERS\.join/.test(sender), 'a blocked run does not say why');
});

t('a dry run writes nothing and sends nothing', () => {
  const loop = sender.slice(sender.indexOf('for (const row of due)'));
  const dry = loop.indexOf('if (DRY_RUN)');
  ok(dry > -1, 'the loop does not check DRY_RUN');
  ok(dry < loop.indexOf('.update(') && dry < loop.indexOf('sendEmail('), 'something happens before the dry-run check');
  ok(/if \(DRY_RUN\) \{[\s\S]*?continue;\s*\}/.test(loop), 'the dry-run branch does not skip the write and the send');
});

t('live: the link is recorded before the email is sent, with a compare-and-set', () => {
  const loop = sender.slice(sender.indexOf('for (const row of due)'));
  ok(loop.indexOf('.update(plan.update)') < loop.indexOf('sendEmail('), 'sent before recording');
  ok(/\.eq\('confirm_send_count', plan\.expectSendCount\)/.test(loop), 'no compare-and-set on the send count');
  ok(/\.is\('confirmed_at', null\)/.test(loop), 'could re-issue to a confirmed address');
  ok(/if \(!claimed \|\| !claimed\.length\) \{ skipped\+\+; continue; \}/.test(loop), 'sends even when the claim did not land');
});

t('nothing schedules either sender for confirmation email', () => {
  const wf = path.join(ROOT, '.github', 'workflows');
  for (const f of fs.readdirSync(wf)) {
    const y = fs.readFileSync(path.join(wf, f), 'utf8');
    ok(!/send-confirmations/.test(y), `${f} runs send-confirmations.js — that is an owner decision (D-027)`);
  }
  ok(!/"send-confirmations"/.test(read('build/package.json')), 'package.json gained a send-confirmations script');
});

// ---- the email's words -----------------------------------------------------------
t('the confirmation email is plain, says what to do and what happens if ignored', () => {
  const tok = 'd'.repeat(64);
  const args = { url: C.confirmUrl(tok), unsubscribeToken: 'u'.repeat(32) };
  for (const body of [C.renderConfirmText(args), C.renderConfirmHtml(args)]) {
    ok(body.indexOf(C.confirmUrl(tok)) > -1, 'the link is missing');
    ok(/ignore this email/i.test(body), 'does not say what happens if ignored');
    ok(/7 days/.test(body), 'does not say how long the link works');
    ok(/unsubscribe\.html\?token=u{32}/.test(body), 'no way to remove the address');
    ok(/No picks/.test(body), 'does not say what the Brief is');
    for (const w of [/\bpick of\b/i, /\block\b/i, /\bedge\b/i, /win probability/i, /guarantee/i, /\bopen(ing)? line\b/i, /since open/i]) {
      ok(!w.test(body), 'tout or banned wording: ' + w);
    }
  }
  ok(C.renderConfirmHtml({ url: 'https://x/"><script>', unsubscribeToken: '"><b>' }).indexOf('<script>') === -1, 'HTML not escaped');
});

// ---- confirm.html ----------------------------------------------------------------
const page = read('confirm.html');

t('confirm.html is noindex and loads the standard scripts in order', () => {
  ok(/<meta name="robots" content="noindex, nofollow">/.test(page), 'not noindex');
  const sb = page.indexOf('supabase-js@2.106.1/dist/umd/supabase.min.js');
  const sh = page.indexOf('<script src="_shared.js');
  const au = page.indexOf('<script src="_auth.js');
  const nav = page.indexOf('cfl.renderNav()');
  ok(sb > -1 && sh > sb && au > sh && nav > au, 'script order is not supabase → _shared.js → _auth.js → renderNav');
  ok(/integrity="sha384-9dsYHX1\/12VQI\+gHRtPXSM3YFsgJ\+iIPjTy4WCtY7XbKG\/q7MTdZxZhMd4cL9Gif"/.test(page), 'Supabase script is not SRI-pinned to the site-wide hash');
  ok(/<nav class="cfl-nav"><\/nav>/.test(page) && /<footer class="cfl-footer"><\/footer>/.test(page), 'nav/footer placeholders missing');
});

t('confirm.html calls the confirm function with the link token', () => {
  ok(/\.rpc\('confirm_email_subscription',\s*\{\s*p_token:/.test(page), 'does not call confirm_email_subscription');
  ok(/params\.get\('t'\)/.test(page), 'does not read ?t=');
  ok(!/\.from\('email_subscribers'\)/.test(page), 'reads the private list directly');
});

t('confirm.html says what happened in plain words, and echoes nothing', () => {
  for (const s of ['You’re confirmed', 'This link has expired or doesn’t work', 'We couldn’t check your link']) {
    ok(page.indexOf(s) > -1, 'missing outcome: ' + s);
  }
  ok(!/error\.message/.test(page), 'shows the database wording to a visitor');
  ok(/cfl\.escapeHtml/.test(page) || !/innerHTML\s*=\s*[^'"`]*\+/.test(page), 'interpolates without escaping');
  ok(/history\.replaceState\(null, '', location\.pathname\)/.test(page), 'the token stays in the address bar and browser history');
});

if (failed) { console.error(`\n  ${failed} failed, ${n} passed`); process.exit(1); }
console.log(`\n  ${n} passed — the Card Brief goes only to addresses that confirmed themselves (T-090).`);
