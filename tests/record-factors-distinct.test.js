// Two record factors, one everyday word. They must not collapse. T-027 / FE-001.
//
// WHAT THIS GUARDS
//
// The site measures two different things that a reader would both call "record":
//
//   Factor Lab  `ufc_record`   UFC-only, RAW win-rate gap off the card,
//                              market-even ~58.4% on 185 fights -> `real`
//   edges.js    recordEdge     whole-career PROFESSIONAL record, Laplace-
//                              smoothed, market-even ~50.2% (FE-001) -> a coin flip
//
// They disagree, and the disagreement is real rather than an error: different
// record, different quantity, different bands. So the site is allowed to say
// the first one works. It is NOT allowed to let that read as the second one
// working, because the second is what actually picks fights.
//
// The failure this prevents is not a wrong number. It is a true sentence about
// one factor being read as a claim about the other — which is how "we tested
// record and it works" ends up meaning the opposite of what was measured.
//
//   node tests/record-factors-distinct.test.js

'use strict';

const fs = require('fs');
const path = require('path');

const read = (f) => fs.readFileSync(path.join(__dirname, '..', f), 'utf8');
const rates = JSON.parse(read('factor-rates.json'));

let passed = 0;
const failures = [];
function t(name, fn) {
  try { fn(); passed += 1; } catch (e) { failures.push(`${name}\n      ${e.message}`); }
}
function ok(cond, what) { if (!cond) throw new Error(what || 'expected truthy'); }
function eq(a, b, what) {
  if (a !== b) throw new Error(`${what || 'value'}: expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`);
}

const factor = (id) => (rates.factors || []).find((f) => f.id === id);
const headline = (f) => f.buckets.find((b) => b.headline) || f.buckets[0];

// --------------------------------------------- the artifact says which record

t('the Factor Lab factor is named and described as UFC-only', () => {
  const f = factor('ufc_record');
  ok(f, 'ufc_record is missing from factor-rates.json');
  ok(/UFC/.test(f.label), `label must name UFC, got "${f.label}"`);
  ok(/UFC/.test(f.question), 'the question must name UFC');
  ok(/UFC/.test(f.note), 'the note must name UFC');
});

t('the Factor Lab factor is described as the RAW gap, not a smoothed one', () => {
  // The August 2026 mistake was measuring a smoothed rate and reporting it as
  // the record you can read off a card. The note has to keep saying which.
  const f = factor('ufc_record');
  ok(/\braw\b/i.test(f.note), 'the note must say the bands are the raw gap');
  ok(!/smooth/i.test(f.note), 'the Factor Lab factor is not smoothed — the note implies it is');
});

t('the Factor Lab factor is point-in-time, not career totals', () => {
  const f = factor('ufc_record');
  eq(f.basis, 'point-in-time', 'basis');
  ok(/never the career total/i.test(f.note), 'the note must rule out career totals');
});

// ------------------------------------------- the page carries the distinction

t('stats.html says the Factor Lab record is not the engine record', () => {
  const html = read('stats.html');
  ok(/not the record our pick engine uses/i.test(html),
    'stats.html must say plainly that this is not the engine’s record factor');
  ok(/whole professional career/i.test(html),
    'stats.html must describe the engine’s record as whole-career professional');
  ok(/coin flip/i.test(html),
    'stats.html must say the engine’s version lands on a coin flip');
});

t('stats.html does not present a green light as covering the engine', () => {
  const html = read('stats.html');
  ok(/not a green light for/i.test(html),
    'the caveat must refuse the inference, not merely describe the difference');
});

t('edges.html keeps the engine record unsupported, in the same breath', () => {
  const html = read('edges.html');
  // The corrected paragraph may report the Factor Lab result. It must not let
  // that stand as support for the shipped factor.
  ok(/not the record factor this page's engine uses/i.test(html)
     || /is not the record factor/i.test(html),
    'edges.html must disclaim the shipped factor where it reports the Lab result');
  ok(/remains unsupported/i.test(html),
    'edges.html must still say the shipped Record factor is unsupported');
});

t('every correction is dated, per this repo’s convention', () => {
  for (const f of ['edges.html', 'methodology.html']) {
    ok(/Corrected 18 September 2026/.test(read(f)),
      `${f} changed a published conclusion without a dated correction`);
  }
});

// ------------------------------- the VISIBLE name disambiguates on its own
//
// The caveat further up the page is the argument; this is the label a reader
// actually meets in the one-line summary — "two actually helps: Age, UFC
// record" — with no caveat attached to it. "UFC record" alone reads as the
// record that picks fights. It is not that record, so the visible name has to
// say so by itself.
//
// The override is page-side on purpose: factor-rates.json is a verified
// measurement and is never edited to change wording.

t('the page overrides the displayed name to UFC-only record', () => {
  const html = read('stats.html');
  ok(/DISPLAY_LABEL\s*=\s*\{[^}]*ufc_record:\s*'UFC-only record'/.test(html),
    'stats.html must map ufc_record to the display name "UFC-only record"');
});

t('the summary line renders the display name, not the raw artifact label', () => {
  const html = read('stats.html');
  // The winners line is the failure point. If it goes back to f.label it prints
  // "UFC record" with nothing qualifying it.
  const m = html.match(/const winners = [^\n]*\n?[^\n]*/);
  ok(m, 'the winners summary is missing');
  ok(/map\(displayLabel\)/.test(html),
    'the summary must map through displayLabel, not f.label');
  ok(!/verdict === 'real'\)\.map\(\(f\) => f\.label\)/.test(html),
    'the summary has reverted to the raw artifact label');
});

t('the rendered summary actually says UFC-only record', () => {
  // Not a source check — reproduce what the page computes from the shipped
  // artifact, so this fails if the data, the override or the wiring drift apart.
  const DISPLAY_LABEL = { ufc_record: 'UFC-only record' };
  const heads = rates.factors.map((f) => f.buckets.find((b) => b.headline) || f.buckets[0]);
  const winners = rates.factors
    .filter((f, i) => heads[i].verdict === 'real')
    .map((f) => DISPLAY_LABEL[f.id] || f.label);
  ok(winners.includes('UFC-only record'),
    `the summary should name "UFC-only record", got: ${winners.join(', ')}`);
  ok(!winners.includes('UFC record'),
    'the summary still names the bare "UFC record"');
  ok(winners.includes('Age'), 'age should still be named a survivor');
});

t('the artifact itself is not edited to carry the display name', () => {
  // The override exists so the measurement stays byte-identical to what the
  // validation run produced. If the label moved into the JSON, that guarantee
  // is gone and the next regeneration would silently revert it.
  eq(factor('ufc_record').label, 'UFC record', 'artifact label must stay as generated');
});

// ------------------------------------------- freshness claims match reality

t('no public page still claims the Factor Lab refreshes on a timer', () => {
  const stats = read('stats.html');
  const edges = read('edges.html');
  ok(!/rebuilt from the database every few hours/i.test(edges),
    'edges.html still says the Factor Lab rebuilds every few hours');
  ok(!/Every number computed live from the full UFC history/i.test(stats),
    'stats.html still says every number is computed live');
  // It must say what IS true, not merely drop the false claim.
  ok(/not on a timer|published after review|when we review/i.test(stats),
    'stats.html should say the factor table is refreshed on review');
});

t('CLAUDE.md no longer documents the Factor Lab as running on the cron', () => {
  const md = read('CLAUDE.md');
  ok(/does NOT run `npm run factor-rates`/.test(md),
    'CLAUDE.md must record that prerender.yml no longer builds the Factor Lab');
  ok(!/run as `npm run factor-rates` inside \[`\.github\/workflows\/prerender\.yml`\]/.test(md),
    'CLAUDE.md still says factor-rates runs inside prerender.yml');
  ok(/factor-rates-validate\.yml/.test(md),
    'CLAUDE.md must name the manual validation workflow');
});

// ------------------------------------------------- stale claims are gone

t('no surface still says age is the only survivor', () => {
  for (const f of ['edges.html', 'methodology.html', 'stats.html', 'CLAUDE.md']) {
    const s = read(f);
    ok(!/Only age survives/i.test(s), `${f} still says "Only age survives"`);
    ok(!/only factor we measure that survives market control/i.test(s),
      `${f} still says age is the only factor surviving market control`);
    ok(!/Only age currently survives market control\./.test(s),
      `${f} still carries the superseded CLAUDE.md line`);
  }
});

t('no surface says UFC record fails market control any more', () => {
  const m = read('methodology.html');
  ok(!/UFC record used to sit beside it here/.test(m),
    'methodology.html still says UFC record no longer clears the bar');
});

// --------------------------------------------- age stays retired regardless

t('age is not reinstated as a pick factor by any of this', () => {
  // The standalone age result says nothing about INCREMENTAL value — the engine
  // already carries age among its covariates. Nothing here licenses putting it
  // back into the verdict, and edges.js must not have grown it.
  const e = read('edges.js');
  ok(!/\bageEdge\b/.test(e), 'ageEdge is back in edges.js — age stays retired');
});

t('edges.js is untouched by the publication', () => {
  // The whole point of the distinction is that the shipped factor did not
  // change. If this file moved, the distinction is no longer the one described.
  const e = read('edges.js');
  ok(/recordEdge/.test(e), 'recordEdge is missing from edges.js');
  ok(/\+ 2\)|\+2\)|2\) \//.test(e) || /Laplace/i.test(e),
    'edges.js recordEdge no longer looks smoothed — the copy describes a rule that changed');
});

// ------------------------------------------------- the published cohort

t('the published artifact is the corrected 1,220-fight cohort', () => {
  eq(rates.dataset.market_even_cohort, 1220, 'market_even_cohort');
  eq(rates.dataset.fights_scored, 8739, 'fights_scored (the control — must not move)');
});

t('ufc_record is published as real, and age keeps its headline', () => {
  eq(headline(factor('ufc_record')).verdict, 'real', 'ufc_record headline verdict');
  eq(headline(factor('age')).verdict, 'real', 'age headline verdict');
});

t('the page names both cohorts rather than printing one as the other', () => {
  // stats.html printed fights_scored into a sentence describing the market-even
  // cohort: "the 8,739 fights where the odds were even". Both are named now.
  const html = read('stats.html');
  ok(/id="lab-even"/.test(html), 'the market-even cohort is not rendered');
  ok(/market_even_cohort/.test(html), 'stats.html does not read market_even_cohort');
});

// ----------------------------------------------------------------- report
if (failures.length) {
  console.log(`\n  ${passed} passed, ${failures.length} FAILED\n`);
  failures.forEach((f) => console.log(`  ✗ ${f}\n`));
  process.exit(1);
}
console.log(`\n  ${passed} passed — the two record factors cannot collapse into one claim.\n`);
