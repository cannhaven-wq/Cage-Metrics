// No Cannon Card Brief is emailed until every address has confirmed itself.
//
// Owner direction, 2026-10-14 (T-088 review): implement double opt-in before
// sending marketing email. The Card Brief form accepts any address anyone
// types, so a real send could mail people who never asked. Until T-090 lands,
// build/send-digest.js must stay dry-run even with RESEND_API_KEY set — and
// this test keeps the lock in code rather than in somebody's memory.
'use strict';
const fs = require('fs');
const path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', 'build', 'send-digest.js'), 'utf8');

let n = 0, failed = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { failed++; console.error('FAIL', name, '\n  ', e.message); } };
const ok = (c, m) => { if (!c) throw new Error(m); };

t('the blocker list exists and names T-090', () => {
  const m = src.match(/const MARKETING_SEND_BLOCKERS = \[([\s\S]*?)\];/);
  ok(m, 'MARKETING_SEND_BLOCKERS is gone');
  ok(/T-090/.test(m[1]), 'the double opt-in blocker (T-090) was removed — that needs confirmation built first, and a reviewed PR');
});

t('any blocker forces dry-run, whatever secrets are set', () => {
  ok(/const DRY_RUN\s*=[\s\S]*?MARKETING_SEND_BLOCKERS\.length > 0;/.test(src), 'DRY_RUN no longer depends on the blockers');
  ok(/if \(DRY_RUN\) \{\s*console\.log\(`\[dry-run\]/.test(src), 'sendOne no longer honours DRY_RUN');
  ok(/async function markSent[\s\S]*?if \(DRY_RUN/.test(src), 'markSent no longer honours DRY_RUN');
});

t('a blocked run says why', () => {
  ok(/sending is blocked by: ' \+ MARKETING_SEND_BLOCKERS\.join/.test(src), 'a blocked run does not print its blockers');
});

if (failed) { console.error(`\n  ${failed} failed, ${n} passed`); process.exit(1); }
console.log(`\n  ${n} passed — no Card Brief is sent until addresses confirm themselves (T-090).`);
