// T-088: the browser roles may write exactly what the website writes.
//
// research/security/proposed_2026-10-13_t088_least_privilege.sql revokes every
// browser write in `public` and gives back an explicit allowlist. That only
// stays true if the allowlist and the site agree, so this test reads both:
// every `.from('<table>').insert|update|upsert|delete` in the browser code must
// be covered by a GRANT in the migration, and the migration must grant nothing
// the browser does not use. A new browser write without a grant fails here,
// before it fails for a visitor.
//
// tests/test_t088_rehearsal.py replays the migration against a replica; this
// one is static, so it runs everywhere.
'use strict';
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const SEC = path.join(ROOT, 'research', 'security');
const MIG = 'proposed_2026-10-13_t088_least_privilege.sql';
const GUARD = 'proposed_2026-10-13_t088_pre_fight_truncate_guard.sql';

let n = 0, failed = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { failed++; console.error('FAIL', name, '\n  ', e.message); } };
const ok = (c, m) => { if (!c) throw new Error(m); };
const noComments = s => s.replace(/--.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');

const migRaw = fs.readFileSync(path.join(SEC, MIG), 'utf8');
const mig = noComments(migRaw);
const stmts = mig.split(';').map(s => s.replace(/\s+/g, ' ').trim()).filter(Boolean);

// GRANT <privs> ON [TABLE] public.x[, ...] TO roles  ->  { table: { role: Set(priv) } }
const granted = {};
for (const s of stmts.filter(s => /^GRANT\b/i.test(s) && !/\bSEQUENCE\b/i.test(s))) {
  const m = s.match(/^GRANT (.+?) ON (?:TABLE )?(.+?) TO (.+)$/i);
  ok(m, `unparsed GRANT: ${s}`);
  const privs = m[1].replace(/\([^)]*\)/g, '').split(',').map(x => x.trim().toUpperCase());
  const tables = m[2].split(',').map(x => x.trim().replace(/^public\./, ''));
  const roles = m[3].split(',').map(x => x.trim());
  for (const tb of tables) for (const r of roles) for (const p of privs) {
    ((granted[tb] = granted[tb] || {})[r] = granted[tb][r] || new Set()).add(p);
  }
}

// Every browser-side write in the site code.
const siteFiles = fs.readdirSync(ROOT).filter(f => /\.(html|js)$/.test(f));
const writes = [];
for (const f of siteFiles) {
  const src = fs.readFileSync(path.join(ROOT, f), 'utf8');
  const re = /\.from\(\s*['"]([a-z_]+)['"]\s*\)\s*\.\s*(insert|update|upsert|delete)\b/g;
  let m;
  while ((m = re.exec(src))) writes.push({ file: f, table: m[1], op: m[2] });
}
const needs = op => ({ insert: ['INSERT'], update: ['UPDATE'], delete: ['DELETE'], upsert: ['INSERT', 'UPDATE'] })[op];

t('the migration lives under research/, marked PROPOSED, never at the repo root', () => {
  ok(/PROPOSED\. NOT APPLIED\./.test(migRaw), 'lost its PROPOSED header');
  ok(/L3/.test(migRaw), 'does not name the L3 gate');
  ok(!fs.existsSync(path.join(ROOT, MIG)), 'a copy sits at the root, where habit applies files');
});

t('every browser write in the site is granted', () => {
  ok(writes.length >= 10, `found only ${writes.length} browser writes — the scan is broken`);
  for (const w of writes) {
    const has = (granted[w.table] && (granted[w.table].authenticated || granted[w.table].anon)) || new Set();
    for (const p of needs(w.op)) ok(has.has(p), `${w.file}: .from('${w.table}').${w.op}() needs ${p}, and the migration does not grant it`);
  }
});

t('nothing is granted that the browser does not use', () => {
  const used = new Set(writes.map(w => w.table));
  for (const tb of Object.keys(granted)) ok(used.has(tb), `grants a write on ${tb}, which no page writes`);
});

t('visitors get column-level INSERT only, on three tables', () => {
  const anonTables = Object.keys(granted).filter(tb => granted[tb].anon);
  ok(JSON.stringify(anonTables.sort()) === JSON.stringify(['email_subscribers', 'funnel_events', 'premium_waitlist']),
    `anon is granted writes on: ${anonTables}`);
  for (const s of stmts.filter(s => /^GRANT\b/i.test(s) && /\banon\b/.test(s) && !/\bSEQUENCE\b/i.test(s))) {
    ok(/^GRANT INSERT \(/i.test(s), `anon grant is not column-level INSERT: ${s}`);
  }
  ok(/GRANT INSERT \(email, source\)\s+ON public\.email_subscribers/i.test(mig), 'email_subscribers is not limited to (email, source) — a visitor could choose their own unsubscribe_token');
  ok(!/unsubscribe_token/.test(mig.split('DO $$')[0]), 'unsubscribe_token is granted');
});

t('profiles: members may change their display name and nothing else', () => {
  ok(/GRANT UPDATE \(display_name\)\s+ON public\.profiles\s+TO authenticated/i.test(mig), 'profiles UPDATE is not column-level');
  ok(!/GRANT (INSERT|DELETE|UPDATE)\b(?! \(display_name\))[^;]*public\.profiles/i.test(mig), 'profiles gets a wider grant');
});

t('the revoke covers every write privilege, every table and view, and PUBLIC', () => {
  const r = stmts.find(s => /^REVOKE .* ON ALL TABLES IN SCHEMA public FROM/i.test(s));
  ok(r, 'no REVOKE ... ON ALL TABLES IN SCHEMA public');
  for (const p of ['INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER', 'MAINTAIN']) ok(new RegExp(`\\b${p}\\b`).test(r), `${p} is not revoked`);
  ok(!/\bSELECT\b/.test(r), 'the revoke touches SELECT — reads are meant to be unchanged');
  for (const role of ['PUBLIC', 'anon', 'authenticated']) ok(new RegExp(`\\b${role}\\b`).test(r.split(' FROM ')[1]), `not revoked from ${role}`);
  ok(!/\bGRANT\b[^;]*\b(TRUNCATE|REFERENCES|TRIGGER|MAINTAIN|ALL)\b/i.test(mig), 'something grants TRUNCATE / REFERENCES / TRIGGER / MAINTAIN / ALL back');
  ok(!/^GRANT SELECT/im.test(mig), 'grants SELECT — reads are meant to be untouched');
});

t('sequences: USAGE only, only behind a browser insert', () => {
  ok(/REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC, anon, authenticated/i.test(mig), 'sequences not revoked');
  for (const s of stmts.filter(s => /^GRANT\b[^;]*\bSEQUENCE\b/i.test(s))) ok(/^GRANT USAGE ON SEQUENCE/i.test(s), `sequence grant is not USAGE: ${s}`);
  for (const tb of ['email_subscribers', 'premium_waitlist', 'funnel_events', 'user_bets', 'user_alerts']) {
    ok(new RegExp(`public\\.${tb}_id_seq`).test(mig), `${tb} inserts a serial id from the browser but its sequence gets no USAGE`);
  }
});

t('new tables, views and sequences are private by default (D-T088-2)', () => {
  ok(/ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public\s+REVOKE ALL ON TABLES FROM anon, authenticated/i.test(mig), 'new tables and views still get a default browser grant');
  ok(/ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public\s+REVOKE ALL ON SEQUENCES FROM anon, authenticated/i.test(mig), 'new sequences still get a default browser grant');
  ok(!/ALTER DEFAULT PRIVILEGES[^;]*\bGRANT\b/i.test(mig), 'a default privilege is granted back');
});

// Once new objects are private, a page that reads a new table or view gets
// "permission denied" unless a migration grants it. Every object the site reads
// must therefore be granted in repo SQL — except these, whose read predates the
// habit and exists only in production (and which T-088 leaves exactly as is;
// its step 5 (c) proves it). Do not add to this list: grant the new object.
const LEGACY_READS_GRANTED_ONLY_IN_PRODUCTION = new Set([
  'email_subscribers', 'events', 'fight_odds', 'fighters', 'fights', 'funnel_events',
  'model_predictions', 'model_versions', 'odds_books', 'prediction_indicators',
  'premium_waitlist', 'profiles', 'user_bankrolls', 'user_bets', 'v_fighter_style',
  'v_predictions_with_results',
]);
t('every object a page reads is granted SELECT in repo SQL (or is a named legacy read)', () => {
  const sqlFiles = [];
  const walk = d => { for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    if (e.name === 'node_modules' || e.name.startsWith('.')) continue;
    const p = path.join(d, e.name);
    if (e.isDirectory()) walk(p); else if (e.name.endsWith('.sql') && !/t088_replica_/.test(e.name)) sqlFiles.push(p);
  } };
  walk(ROOT);
  const allSql = sqlFiles.map(f => noComments(fs.readFileSync(f, 'utf8'))).join('\n');
  const reads = new Set();
  for (const f of siteFiles) {
    const re = /\.from\(\s*['"]([a-z_0-9]+)['"]\s*\)/g;
    let m; const src = fs.readFileSync(path.join(ROOT, f), 'utf8');
    while ((m = re.exec(src))) reads.add(m[1]);
  }
  ok(reads.size >= 30, `found only ${reads.size} reads — the scan is broken`);
  for (const r of reads) {
    if (LEGACY_READS_GRANTED_ONLY_IN_PRODUCTION.has(r)) continue;
    const g = new RegExp(`grant\\s+(?:all\\b|[^;]*\\bselect\\b)[^;]*\\bon\\s+(?:table\\s+)?[^;]*\\b(?:public\\.)?${r}\\b[^;]*\\bto\\s+[^;]*\\b(anon|authenticated)\\b`, 'i');
    ok(g.test(allSql), `a page reads ${r}, and no repo SQL grants it SELECT — once T-088 lands, a NEW object like this is unreadable`);
  }
  for (const r of LEGACY_READS_GRANTED_ONLY_IN_PRODUCTION) ok(reads.has(r), `${r} is on the legacy list but no page reads it any more — remove it`);
});

t('the allowlist in the assertion block matches the GRANTs exactly', () => {
  const block = mig.slice(mig.indexOf('allow constant text[]'), mig.indexOf('BEGIN', mig.indexOf('allow constant text[]')));
  const entries = [...block.matchAll(/'(anon|authenticated)\|([a-z_]+)\|([A-Z]+)\|([a-z_]*)'/g)];
  ok(entries.length > 0, 'no allowlist found');
  const fromBlock = new Set(entries.map(e => `${e[1]}|${e[2]}|${e[3]}`));
  const fromGrants = new Set();
  for (const tb of Object.keys(granted)) for (const r of Object.keys(granted[tb])) for (const p of granted[tb][r]) fromGrants.add(`${r}|${tb}|${p}`);
  for (const x of fromGrants) ok(fromBlock.has(x), `granted but not asserted: ${x}`);
  for (const x of fromBlock) ok(fromGrants.has(x), `asserted but not granted: ${x}`);
  ok(/RAISE EXCEPTION 'T-088 least-privilege check failed/.test(mig), 'the assertion no longer raises');
  ok(/read changed on/.test(mig), 'the reads-unchanged check is gone');
});

t('no statement can hang the Supabase MCP tool', () => {
  for (const f of [MIG, GUARD, 't088_probe.sql']) {
    const s = noComments(fs.readFileSync(path.join(SEC, f), 'utf8'));
    ok(!/RAISE\s+NOTICE/i.test(s), `${f} raises a NOTICE`);
    ok(!/DROP\s+TRIGGER\s+IF\s+EXISTS/i.test(s), `${f} uses DROP TRIGGER IF EXISTS`);
  }
});

t('the pre-fight TRUNCATE guard is statement-level and binds every role', () => {
  const g = noComments(fs.readFileSync(path.join(SEC, GUARD), 'utf8'));
  ok(/BEFORE TRUNCATE ON public\.pre_fight_snapshots\s+FOR EACH STATEMENT/i.test(g), 'not a statement-level BEFORE TRUNCATE trigger');
  ok(/SET search_path = ''/.test(g), 'trigger function search_path not pinned');
  ok(!/\bOLD\.|\bNEW\./i.test(g), 'a statement-level trigger function must not read OLD/NEW');
});

t('Card Brief signup is a plain insert that treats a repeat as success', () => {
  const auth = fs.readFileSync(path.join(ROOT, '_auth.js'), 'utf8');
  const body = auth.slice(auth.indexOf('auth.subscribeEmail'), auth.indexOf('// -------- nav integration'));
  ok(/\.from\('email_subscribers'\)\s*\.insert\(/.test(body), 'subscribeEmail is not a plain insert');
  ok(!/\.upsert\(/.test(body), 'subscribeEmail upserts again — ON CONFLICT needs a SELECT policy visitors do not have, and every signup fails');
  ok(/'23505'/.test(body), 'a repeat signup is not treated as success');
  ok(!/return \{ data, error \}/.test(body), 'the raw database error reaches the visitor');
});

if (failed) { console.error(`\n  ${failed} failed, ${n} passed`); process.exit(1); }
console.log(`\n  ${n} passed — every browser write is granted, and nothing else is.`);
