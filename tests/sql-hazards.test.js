// Root SQL files that must never be applied by habit.
//
// The repo keeps its migrations as loose *.sql files at the root, applied by
// hand. One of them, public_read_odds.sql, granted anon SELECT on the raw odds
// table for months after the rule became "admin-only, read through definer
// views" — one `psql -f` away from publishing every quote. This keeps that
// shut, and keeps the two one-off destructive cleanups marked as such.
'use strict';
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');

let n = 0, failed = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { failed++; console.error('FAIL', name, '\n  ', e.message); } };
const ok = (c, m) => { if (!c) throw new Error(m); };
const noComments = s => s.replace(/--.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');

const rootSql = fs.readdirSync(ROOT).filter(f => f.endsWith('.sql'));

t('no root SQL file opens the raw odds tables to the browser', () => {
  for (const f of rootSql) {
    const sql = noComments(fs.readFileSync(path.join(ROOT, f), 'utf8'));
    for (const table of ['fight_odds', 'odds_books']) {
      const grant = new RegExp(`GRANT\\s+[^;]*\\bSELECT\\b[^;]*\\bON\\s+(?:TABLE\\s+)?(?:public\\.)?${table}\\b[^;]*\\bTO\\b[^;]*\\b(anon|authenticated)\\b`, 'i');
      ok(!grant.test(sql), `${f} grants anon/authenticated SELECT on ${table}`);
      const policy = new RegExp(`CREATE\\s+POLICY[^;]*\\bON\\s+(?:public\\.)?${table}\\b[^;]*\\bFOR\\s+SELECT\\b[^;]*\\bTO\\b[^;]*\\banon\\b[^;]*USING\\s*\\(\\s*true\\s*\\)`, 'i');
      ok(!policy.test(sql), `${f} creates a public read policy on ${table}`);
    }
  }
});

t('public_read_odds.sql refuses to run', () => {
  const sql = fs.readFileSync(path.join(ROOT, 'public_read_odds.sql'), 'utf8');
  ok(/RAISE EXCEPTION/.test(noComments(sql)), 'public_read_odds.sql no longer raises when applied');
  ok(/RETIRED\. DO NOT APPLY/.test(sql), 'public_read_odds.sql lost its retirement header');
});

if (failed) { console.error(`\n  ${failed} failed, ${n} passed`); process.exit(1); }
console.log(`\n  ${n} passed — no root SQL file can open the raw odds table by habit.`);
