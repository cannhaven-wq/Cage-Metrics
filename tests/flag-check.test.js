/* ==========================================================================
   tests/flag-check.test.js — the daily fighter-flag check (owner rule
   2026-10-16: the flag is the country a fighter REPRESENTS).

   What must never happen: an existing flag overwritten by Wikidata, a guess
   made when there are two candidates, or a person's hand correction re-checked.

   Run:  node tests/flag-check.test.js
   ========================================================================== */
'use strict';
const fs = require('fs');
const path = require('path');
const F = require('../build/check-fighter-flags.js');
let passed = 0; const failures = [];
function t(name, fn) { try { fn(); passed += 1; } catch (err) { failures.push(name + '\n      ' + err.message); } }
function eq(a, b, what) { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error((what || '') + ' expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a)); }
function ok(c, what) { if (!c) throw new Error(what || 'expected truthy'); }

const row = o => Object.assign({ qid: 'Q1' }, o);

t('country for sport wins over citizenship', () => {
  // Milosevic shape: Swedish citizen, competes for Serbia.
  const w = F.representedCountry([row({ sportQid: 'Q403', sportCode: 'RS', sportLabel: 'Serbia', citQid: 'Q34', citCode: 'SE', citLabel: 'Sweden' })]);
  eq([w.status, w.code, w.via], ['found', 'RS', 'sport']);
});

t('a single citizenship is the fallback', () => {
  const w = F.representedCountry([row({ citQid: 'Q16', citCode: 'CA', citLabel: 'Canada' })]);
  eq([w.status, w.code, w.via], ['found', 'CA', 'citizenship']);
});

t('two citizenships and no sporting country is a question, not a guess', () => {
  const w = F.representedCountry([row({ citQid: 'Q16', citCode: 'CA' }), row({ citQid: 'Q794', citCode: 'IR' })]);
  eq(w.status, 'ambiguous');
});

t('two people with the same name is ambiguous', () => {
  eq(F.representedCountry([row({ qid: 'Q1', citCode: 'US', citQid: 'Q30' }), row({ qid: 'Q2', citCode: 'US', citQid: 'Q30' })]).status, 'ambiguous');
});

t('a home nation flies the UK flag', () => {
  const w = F.representedCountry([row({ sportQid: 'Q21', sportLabel: 'England' })]);
  eq([w.status, w.code], ['found', 'GB']);
});

t('no match is not_found', () => { eq(F.representedCountry([]).status, 'not_found'); });

t('a missing flag is filled', () => {
  const d = F.decide({ country_code: null, country_src: null }, { status: 'found', code: 'MX', label: 'Mexico', via: 'sport', qids: ['Q9'] });
  eq([d.action, d.code, d.src], ['fill', 'MX', 'wikidata:sport']);
});

t('an existing flag is NEVER overwritten — a disagreement is reported', () => {
  // Malott shape: we had US, the truth is CA.
  const d = F.decide({ country_code: 'US', country_src: 'ufc.com' }, { status: 'found', code: 'CA', label: 'Canada', via: 'sport', qids: ['Q9'] });
  eq([d.action, d.have, d.want], ['disagree', 'US', 'CA']);
});

t('agreement is recorded so the fighter is not looked up again', () => {
  const d = F.decide({ country_code: 'us', country_src: 'ufc.com' }, { status: 'found', code: 'US', via: 'citizenship', qids: [] });
  eq([d.action, d.src], ['confirm', 'ufc.com+wikidata']);
  ok(F.SETTLED.has(d.src), 'a confirmed fighter would be re-checked every day');
});

t('a hand correction is never touched', () => {
  eq(F.decide({ country_code: 'CA', country_src: 'manual' }, { status: 'found', code: 'US', via: 'sport' }).action, 'skip');
});

t('the older citizenship backfill is re-checked under the represents rule', () => {
  ok(!F.SETTLED.has('wikidata') && !F.SETTLED.has('ufc.com') && !F.SETTLED.has(null), 'old sources are treated as settled');
});

t('SPARQL asks for country for sport and citizenship, mixed martial artists only, names escaped', () => {
  const q = F.sparqlFor(['Mike Malott', 'Joe "Quote" O\'Neil']);
  ok(/wdt:P1532/.test(q) && /wdt:P27/.test(q) && /wdt:P106 wd:Q11607585/.test(q), 'query is missing a property');
  ok(q.includes('"Joe \\"Quote\\" O\'Neil"@en'), 'a quote in a name breaks the query');
});

t('bindings group by name and keep both countries', () => {
  const g = F.groupBindings({ results: { bindings: [{
    name: { value: 'Nina Milosevic' }, p: { value: 'http://www.wikidata.org/entity/Q5' },
    sport: { value: 'http://www.wikidata.org/entity/Q403' }, sportCode: { value: 'RS' }, sportLabel: { value: 'Serbia' },
    cit: { value: 'http://www.wikidata.org/entity/Q34' }, citCode: { value: 'SE' }, citLabel: { value: 'Sweden' } }] } });
  eq(F.representedCountry(g.get('Nina Milosevic')).code, 'RS');
});

t('the runner fails loudly rather than reporting silence', () => {
  const src = fs.readFileSync(path.join(__dirname, '..', 'build', 'check-fighter-flags.js'), 'utf8');
  ok(/process\.exit\(2\)/.test(src) && /process\.exit\(1\)/.test(src), 'a missing key or a failed read exits 0');
  ok(/country_code=is\.null/.test(src), 'a fill can race an existing flag and overwrite it');
});

t('the workflow cannot write to the repo, and the issue says nothing was changed', () => {
  const wf = fs.readFileSync(path.join(__dirname, '..', '.github', 'workflows', 'flag-check.yml'), 'utf8');
  ok(/contents: read/.test(wf) && !/contents: write/.test(wf), 'workflow can write the repo');
  ok(/Nothing here was changed automatically/.test(wf), 'issue does not say disagreements are untouched');
});

if (failures.length) {
  console.error('flag-check: ' + failures.length + ' failed, ' + passed + ' passed');
  failures.forEach(f => console.error('  ✗ ' + f)); process.exit(1);
}
console.log('flag-check: ' + passed + ' passed');
