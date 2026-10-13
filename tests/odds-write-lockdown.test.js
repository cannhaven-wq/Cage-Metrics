// The browser roles may read sportsbook data and may never write it (T-087).
//
// Until 2026-10-13 anon AND authenticated held INSERT, UPDATE, DELETE and
// TRUNCATE on fight_odds, odds_books, odds_aliases and unmatched_odds — the
// Supabase default grant, never revoked. RLS refused REST writes on the first
// two; nothing refused them on the other two, which had RLS off.
// odds_write_lockdown_migration.sql revoked it in production. This keeps the
// file honest and stops any other root SQL file from handing writes back.
'use strict';
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const FILE = 'odds_write_lockdown_migration.sql';

let n = 0, failed = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { failed++; console.error('FAIL', name, '\n  ', e.message); } };
const ok = (c, m) => { if (!c) throw new Error(m); };
const noComments = s => s.replace(/--.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');

const RAW = ['fight_odds', 'odds_books', 'odds_aliases', 'unmatched_odds'];
const SERVICE_ONLY = ['odds_aliases', 'unmatched_odds'];
const SEQUENCES = ['fight_odds_id_seq', 'odds_books_id_seq', 'odds_aliases_id_seq', 'unmatched_odds_id_seq', 'prop_odds_id_seq'];
// Keep their existing SELECT (admin-only RLS decides rows); lose every write.
const RAW_KEEP_SELECT = ['fight_odds', 'odds_books'];
// Read by the website; SELECT is granted back to both browser roles.
const WEBSITE_READS = ['v_fight_odds_latest_by_book', 'v_odds_books_sportsbooks',
  'v_fight_market_movement', 'v_fight_market_vigfree', 'v_fight_odds_consensus', 'v_fight_market_horizons',
  'v_fight_chart_series', 'v_fight_chart_books', 'v_fight_chart_meta', 'v_fight_alert_market'];

const sql = noComments(fs.readFileSync(path.join(ROOT, FILE), 'utf8'));
const statements = sql.split(';').map(s => s.trim()).filter(Boolean);
const names = s => (s.match(/public\.([a-z_0-9]+)/g) || []).map(x => x.slice(7));
const revokeTables = statements.filter(s => /^REVOKE\b[^;]*\bON\s+TABLE\b/i.test(s));
const revokeWrites = statements.filter(s => /^REVOKE\s+(?!ALL)[^;]*\bON\s+TABLE\b/i.test(s));
const revokeSeqs = statements.filter(s => /^REVOKE\s+ALL\s+ON\s+SEQUENCE\b/i.test(s));
const grants = statements.filter(s => /^GRANT\b/i.test(s));
const revoked = revokeTables.flatMap(names);
const granted = grants.flatMap(names);

t('every odds relation is revoked from PUBLIC, anon and authenticated', () => {
  ok(revokeTables.length > 0, 'no REVOKE ALL ON TABLE statement');
  for (const s of revokeTables.concat(revokeSeqs)) {
    for (const role of ['PUBLIC', 'anon', 'authenticated']) {
      ok(new RegExp(`FROM[^;]*\\b${role}\\b`).test(s), `a REVOKE does not name ${role}`);
    }
  }
  for (const r of RAW.concat(WEBSITE_READS)) ok(revoked.includes(r), `${r} is not in the REVOKE`);
  const seqs = revokeSeqs.flatMap(names);
  for (const s of SEQUENCES) ok(seqs.includes(s), `sequence ${s} is not revoked`);
});

t('the raw quote tables lose every write privilege and keep SELECT', () => {
  const w = revokeWrites.filter(s => RAW_KEEP_SELECT.every(r => names(s).includes(r)));
  ok(w.length === 1, 'no single write-only REVOKE covering fight_odds and odds_books');
  const privs = w[0].split(/\bON\b/i)[0];
  for (const p of ['INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER', 'MAINTAIN']) {
    ok(new RegExp(`\\b${p}\\b`).test(privs), `${p} is not revoked from the raw tables`);
  }
  ok(!/\bSELECT\b/.test(privs), 'the raw tables lose SELECT — the admin read in lab.html would break');
  for (const r of RAW_KEEP_SELECT) {
    ok(!revokeTables.some(s => /^REVOKE\s+ALL\b/i.test(s) && names(s).includes(r)), `${r} is in a REVOKE ALL`);
  }
});

t('the only privilege given back is SELECT', () => {
  ok(grants.length > 0, 'no GRANT — the website would lose its reads');
  for (const g of grants) {
    ok(/^GRANT\s+SELECT\s+ON\s+TABLE\b/i.test(g), `non-SELECT grant: ${g.slice(0, 80)}`);
    ok(!/\bPUBLIC\b/.test(g.replace(/public\./g, '')), 'grants to PUBLIC');
  }
});

t('website reads keep SELECT; service-only tables get none', () => {
  for (const r of WEBSITE_READS) ok(granted.includes(r), `${r} lost its SELECT grant`);
  for (const r of SERVICE_ONLY) ok(!granted.includes(r), `${r} is granted to a browser role again`);
  for (const r of granted) ok(revoked.includes(r), `${r} is granted without being revoked first`);
});

t('the migration proves itself before committing', () => {
  ok(/RAISE\s+EXCEPTION/i.test(sql), 'the post-condition block no longer raises');
  ok(/has_table_privilege\([\s\S]{0,120}?'INSERT,UPDATE,DELETE,TRUNCATE/i.test(sql), 'write check missing');
  ok(/has_sequence_privilege/i.test(sql), 'sequence check missing');
  for (const r of revoked) ok(new RegExp(`'${r}'`).test(sql), `${r} is revoked but not asserted`);
  ok(!/RAISE\s+NOTICE/i.test(sql), 'a NOTICE hangs the Supabase MCP tool (CLAUDE.md)');
});

t('the migration touches privileges only — never rows or policies', () => {
  ok(!/\b(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|TRUNCATE\s+(TABLE\s+)?\w|DROP\s|ALTER\s+TABLE|CREATE\s+POLICY)/i.test(sql),
    `${FILE} does more than grant and revoke`);
});

t('no root SQL file hands browser roles a write on sportsbook data', () => {
  const targets = RAW.concat(['v_odds_books_sportsbooks', 'v_fight_odds_latest_by_book']);
  for (const f of fs.readdirSync(ROOT).filter(x => x.endsWith('.sql'))) {
    const body = noComments(fs.readFileSync(path.join(ROOT, f), 'utf8'));
    for (const g of body.split(';').filter(s => /\bGRANT\b/i.test(s))) {
      if (!/\bTO\b[^;]*\b(anon|authenticated|PUBLIC)\b/i.test(g)) continue;
      if (!/\b(ALL|INSERT|UPDATE|DELETE|TRUNCATE|TRIGGER)\b/i.test(g.split(/\bON\b/i)[0])) continue;
      for (const r of targets) {
        ok(!new RegExp(`\\bON\\s+(TABLE\\s+)?[^;]*\\b(public\\.)?${r}\\b`, 'i').test(g), `${f} grants a write on ${r} to a browser role`);
      }
    }
  }
});

if (failed) { console.error(`\n  ${failed} failed, ${n} passed`); process.exit(1); }
console.log(`\n  ${n} passed — browser roles can read sportsbook data and cannot write it.`);
