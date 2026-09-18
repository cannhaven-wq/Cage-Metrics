// The Factor Lab cannot publish itself on a schedule. T-027.
//
// WHAT THIS GUARDS
//
// factor-rates.json holds the Factor Lab's verdicts, and stats.html renders
// them as public performance claims. prerender.yml used to regenerate that file
// every six hours with a service key and commit it to main — so the numbers
// republished unattended.
//
// That was tolerable while the script was believed correct. It stopped being
// tolerable when a reader defect was found in it (unordered pagination, T-027):
// merging the fix would have deployed it and published its effects in the same
// unreviewed step, and the first person to see the corrected verdicts would
// have been a visitor.
//
// So regeneration moved to a manual workflow that commits nothing. These
// assertions are what stops it drifting back — re-adding one line to
// prerender.yml would otherwise silently restore the old behaviour.
//
//   node tests/publish-gate.test.js

'use strict';

const fs = require('fs');
const path = require('path');

const wf = (name) => fs.readFileSync(
  path.join(__dirname, '..', '.github', 'workflows', name), 'utf8');

let passed = 0;
const failures = [];
function t(name, fn) {
  try { fn(); passed += 1; } catch (e) { failures.push(`${name}\n      ${e.message}`); }
}
function ok(cond, what) { if (!cond) throw new Error(what || 'expected truthy'); }

// Strip full-line comments before matching: this file is heavily commented, and
// a comment that mentions `npm run factor-rates` must not read as running it.
const code = (src) => src.split('\n').filter((l) => !/^\s*#/.test(l)).join('\n');

// ------------------------------------------------- the scheduled job publishes nothing

t('prerender.yml does not regenerate the Factor Lab', () => {
  ok(!/npm run factor-rates/.test(code(wf('prerender.yml'))),
    'the scheduled job runs factor-rates again — it would republish verdicts unattended');
});

t('prerender.yml does not stage or commit factor-rates.json', () => {
  const c = code(wf('prerender.yml'));
  ok(!/git add[^\n]*factor-rates\.json/.test(c),
    'factor-rates.json is staged by the scheduled commit again');
  ok(!/factor-rates\.json/.test(c),
    'factor-rates.json is referenced in the scheduled job outside a comment');
});

t('prerender.yml still does the job it is actually for', () => {
  // The gate must not have been achieved by breaking the stub regeneration.
  const c = code(wf('prerender.yml'));
  ok(/npm run prerender/.test(c), 'stub prerendering is gone');
  ok(/git add[^\n]*sitemap\.xml/.test(c), 'the sitemap is no longer committed');
  ok(/cron:/.test(c), 'the schedule is gone');
});

// ------------------------------------------------- the manual job cannot publish

t('the validation workflow exists and is manual only', () => {
  const c = code(wf('factor-rates-validate.yml'));
  ok(/workflow_dispatch/.test(c), 'no manual trigger');
  ok(!/\bcron\s*:/.test(c), 'the validation workflow has been put on a schedule');
  ok(!/^\s*push\s*:/m.test(c), 'the validation workflow now runs on push');
});

t('the validation workflow cannot write to the repository', () => {
  // This is THE safety property. `contents: read` means the token it is handed
  // cannot push, so the separation of measurement from publication is enforced
  // by the platform rather than by everyone remembering.
  const c = code(wf('factor-rates-validate.yml'));
  ok(/permissions:\s*\n\s*contents:\s*read/.test(c),
    'the validation workflow must declare `permissions: contents: read`');
  ok(!/contents:\s*write/.test(c),
    'the validation workflow has been granted write access — that defeats the gate');
});

t('the validation workflow commits and pushes nothing', () => {
  const c = code(wf('factor-rates-validate.yml'));
  ok(!/git commit/.test(c), 'the validation workflow commits');
  ok(!/git push/.test(c), 'the validation workflow pushes');
});

t('the validation workflow actually produces something to review', () => {
  // A gate that reports nothing is not safer, it is just quieter. The run has
  // to leave behind the candidate and the comparison.
  const c = code(wf('factor-rates-validate.yml'));
  ok(/npm run factor-rates/.test(c), 'it does not regenerate anything');
  ok(/upload-artifact/.test(c), 'the candidate is not uploaded for review');
  ok(/compare-factor-rates\.js/.test(c), 'it does not compare against the published file');
});

// ------------------------------------------------- the published file is unchanged

t('the published Factor Lab is the reviewed corrected cohort', () => {
  // This read 869 until 2026-09-18 and was updated in the commit that published
  // the corrected artifact — deliberately, which is what it asked for. It is not
  // a formality: it pins the published cohort to a number a human approved, so a
  // later unreviewed regeneration cannot slide a different one in unnoticed.
  const j = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'factor-rates.json'), 'utf8'));
  if (j.dataset.market_even_cohort !== 1220) {
    throw new Error(
      `market_even_cohort is ${j.dataset.market_even_cohort}, expected 1220 `
      + '(the corrected cohort, reviewed and published 2026-09-18). '
      + 'Publishing a different one is an owner decision (gate #8), and this '
      + 'assertion is updated in the same commit that publishes it, so the '
      + 'change is visible in a diff rather than arriving silently.');
  }
  // The control. It was already correct before the paging fix and must not move.
  if (j.dataset.fights_scored !== 8739) {
    throw new Error(`fights_scored is ${j.dataset.fights_scored}, expected 8739 — the control moved`);
  }
});

// ----------------------------------------------------------------- report
if (failures.length) {
  console.log(`\n  ${passed} passed, ${failures.length} FAILED\n`);
  failures.forEach((f) => console.log(`  ✗ ${f}\n`));
  process.exit(1);
}
console.log(`\n  ${passed} passed — the Factor Lab cannot publish itself on a schedule.\n`);
