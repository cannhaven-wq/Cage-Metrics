// Diff two factor-rates.json files: cohort sizes and every factor verdict.
//
// T-027. The paging fix changes which rows the Factor Lab reads, so it can move
// published verdicts. This prints exactly what moved, so that movement is seen
// and accepted before it reaches stats.html rather than after.
//
//   node build/compare-factor-rates.js <before.json> <after.json>
//
// Exit 0 if no verdict moved, 1 if any did — so it can gate a publish step.

'use strict';

const fs = require('fs');

const [, , beforePath, afterPath] = process.argv;
if (!beforePath || !afterPath) {
  console.error('usage: node build/compare-factor-rates.js <before.json> <after.json>');
  process.exit(2);
}

const read = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const A = read(beforePath);
const B = read(afterPath);

// One flat row per bucket: "<factor>/<bucket label>".
function index(j) {
  const out = new Map();
  for (const f of j.factors || []) {
    for (const b of f.buckets || []) {
      out.set(`${f.id} / ${b.label}`, {
        verdict: b.verdict,
        evenN: b.even ? b.even.n : null,
        evenPct: b.even ? b.even.pct : null,
        allN: b.all ? b.all.n : null,
      });
    }
    out.set(`${f.id} / (factor verdict)`, { verdict: f.verdict, evenN: null, evenPct: null, allN: null });
  }
  return out;
}

const ia = index(A);
const ib = index(B);

console.log('=== dataset ===');
for (const k of ['fights_scored', 'market_even_cohort', 'first_event', 'last_event']) {
  const a = A.dataset ? A.dataset[k] : undefined;
  const b = B.dataset ? B.dataset[k] : undefined;
  const flag = a === b ? '' : '   <-- CHANGED';
  console.log(`  ${k.padEnd(20)} ${String(a).padStart(12)} -> ${String(b).padStart(12)}${flag}`);
}

// fights_scored was already correct before the fix, so it is the control: if it
// moves, the change did something it should not have.
if (A.dataset && B.dataset && A.dataset.fights_scored !== B.dataset.fights_scored) {
  console.log('\n  !! fights_scored moved. That is the control and it should not change.');
  console.log('     Treat this run as suspect rather than publishing it.');
}

console.log('\n=== verdict changes ===');
let moved = 0;
for (const key of new Set([...ia.keys(), ...ib.keys()])) {
  const a = ia.get(key);
  const b = ib.get(key);
  if (!a) { console.log(`  + ${key}  (new)`); moved += 1; continue; }
  if (!b) { console.log(`  - ${key}  (gone)`); moved += 1; continue; }
  if (a.verdict !== b.verdict) {
    console.log(`  ~ ${key}\n      verdict ${a.verdict} -> ${b.verdict}`
      + `   market-even n ${a.evenN} -> ${b.evenN}, ${a.evenPct}% -> ${b.evenPct}%`);
    moved += 1;
  }
}
if (!moved) console.log('  none');

console.log('\n=== market-even sample changes (verdict unchanged) ===');
let resized = 0;
for (const key of ia.keys()) {
  const a = ia.get(key);
  const b = ib.get(key);
  if (!b || a.verdict !== b.verdict) continue;
  if (a.evenN !== b.evenN) {
    console.log(`    ${key}: n ${a.evenN} -> ${b.evenN}, ${a.evenPct}% -> ${b.evenPct}%`);
    resized += 1;
  }
}
if (!resized) console.log('  none');

console.log(`\n${moved} verdict(s) moved, ${resized} bucket(s) resized without changing verdict.`);
process.exit(moved ? 1 : 0);
