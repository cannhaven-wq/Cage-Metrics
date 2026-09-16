/* ==========================================================================
   tests/proof-copy.test.js — regression tests on the words proof.html ships.

   Three of the corrections this page went through are copy corrections, and a
   copy correction with no test is a copy correction that comes back:

     * it must not claim the working tables are immutable (they are not);
     * it must describe methodology as versioned, not as impossible to change;
     * it must not claim to contain prediction systems it never queries;
     * it must not put a legacy-derived progress figure against the CLV gate.

   This reads the shipped file and asserts on the strings a human will see.
   Code comments and the <style> block are stripped first — a comment explaining
   why a claim is forbidden must not itself trip the test for that claim.

   Run:  node tests/proof-copy.test.js
   ========================================================================== */

'use strict';
const fs = require('fs');
const path = require('path');

const read = f => fs.readFileSync(path.join(__dirname, '..', f), 'utf8');
const RAW = read('proof.html');

// The shipped copy spans both files — proof-gates.js owns the gate, status and
// timing strings that the page renders verbatim, so both are in the corpus.
const strip = src => src
  .replace(/<style>[\s\S]*?<\/style>/g, ' ')
  .replace(/\/\*[\s\S]*?\*\//g, ' ')
  .replace(/^\s*\/\/.*$/gm, ' ')
  .replace(/\s+/g, ' ');
const COPY = strip(RAW) + ' ' + strip(read('proof-gates.js'));

// Banned-phrase checks run against copy with the MARKUP REMOVED. A claim split
// by an inline <strong> is the same claim to a reader, and an earlier version of
// this file could be evaded by exactly that.
const LOWER = COPY.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').toLowerCase();

let passed = 0;
const failures = [];
function t(name, fn) {
  try { fn(); passed++; }
  catch (e) { failures.push(name + '\n      ' + e.message); }
}
function absent(phrase, why) {
  if (LOWER.indexOf(phrase.toLowerCase()) !== -1) {
    throw new Error('shipped copy must not contain ' + JSON.stringify(phrase) + ' — ' + why);
  }
}
function present(re, why) {
  if (!re.test(COPY)) throw new Error('shipped copy is missing: ' + why);
}

// ------------------------------- 2. no false immutability -------------------
// model_picks and model_edges carry no append-only triggers, and model_edges is
// deliberately updated post-card to settle the closing price. Nothing on the
// page may imply otherwise.

t('no copy claims a posted row can never be edited', function () {
  [
    'can never be edited',
    'never be edited afterwards',
    'never edited again',
    'cannot be changed or deleted',
    'can never be changed',
    'rows are locked',
    'picks are locked',
    'tamper-proof',
    'impossible to edit',
  ].forEach(function (p) { absent(p, 'the working tables are not sealed'); });
});

t('the page states outright that the source tables are not locked', function () {
  present(/tables behind this page are not themselves locked/i,
          'the disclosure that the working tables are not sealed');
  present(/ordinary working table/i, 'the plain description of the picks table');
  present(/settlement, not a revision/i,
          'the explanation that the post-card closing-price update is settlement');
});

t('immutability is only ever claimed for the sealed copy, and named as separate', function () {
  present(/separate<\/?em>? ?record (that )?the database (refuses|will not let)/i,
          'immutability attributed to the separate sealed record');
  present(/sealed copy is not by itself proof of timing/i,
          'the audit row keeping immutability and timing apart');
});

t('picks with no sealed copy are reported as uncovered, not as passing', function () {
  present(/not covered|uncovered|never as passing/i, 'uncovered-pick disclosure');
});

// ------------------------------- 3. timing is graded, not asserted ----------

t('the page never answers the pre-fight question with a bare yes', function () {
  [
    'yes — all 151',
    'yes - all 151',
    'all timestamped ahead of the card',
    'verified ahead of the card',
    'all of them were posted before',
  ].forEach(function (p) { absent(p, 'timing is graded per row, never asserted wholesale'); });
});

t('the page explains why a same-day timestamp is not proof', function () {
  present(/same-day/i, 'the same-day grade');
  present(/before the first bell/i, 'the reason a card date cannot settle timing');
});

// ------------- 3b. the live bucket is a dataset, not a timing proof ---------
// REGRESSION. source='live' identifies the prospective feed. It does NOT by
// itself establish that any given row preceded its fight — that is what the
// per-row timing grades are for. No label may collapse the two.

t('no label describes the whole live bucket as proven pre-fight', function () {
  [
    'posted before the fight',
    'posted before its card',
    'written to the database before the card started',
    'every call posted before',
    'all posted before the fight',
    'every live pick was posted before',
    'locked before the bell',
    'locked before fight night',
  ].forEach(function (p) {
    absent(p, "source='live' names the dataset, it does not prove per-row timing");
  });
});

t('the live record is labelled as a feed, and points at the per-row grading', function () {
  present(/live ?\/ ?prospective/i, 'the live bucket labelled as the prospective record');
  present(/graded separately/i, 'copy saying timing is graded separately');
  present(/calls from the live feed/i, 'the archive note describing the feed rather than asserting timing');
  present(/not by itself proof|does <em>not<\/em>, on its own, prove|not, on its own, prove/i,
          'an explicit statement that being in the live feed is not a timing proof');
});

// ------------------------------- 4. governance, not impossibility -----------

t('the rules question is not answered "No"', function () {
  [
    "a: 'No — rows are locked",
    'we cannot change the rules',
    'the rules can never change',
  ].forEach(function (p) { absent(p, 'the honest answer is versioning, not impossibility'); });
});

t('methodology change is described as versioned and dated', function () {
  present(/versioned and dated|versioned, dated|only versioned and dated/i, 'the versioning promise');
  present(/stay tied to the rules they were scored under|tied to the rules/i,
          'the promise that old results are not re-graded');
  present(/never moved after/i, 'the promise that a threshold is not moved after the fact');
});

// ------------------------------- 5. scope ----------------------------------

t('the page does not claim to hold every prediction CFL has made', function () {
  [
    'every prediction in our database',
    'every cfl prediction',
    'every prediction on record',
    'all of our predictions',
  ].forEach(function (p) { absent(p, 'the page only reads the main engine'); });
});

t('the page names its scope and what it excludes', function () {
  present(/main[- ]engine/i, 'the main-engine scope wording');
  present(/duration and prop models|prop models run under their own|own research protocols/i,
          'the statement that other research records are not here');
  present(/does not speak for the rest of the lab/i, 'the audit row limiting scope');
});

// ------------------------------- 1. CLV gate -------------------------------

t('no legacy-derived CLV progress figure is rendered', function () {
  ['clvpaircount', '46 of 100', 'of 100 picks with both', 'picks with both a posted price and a closing price'].forEach(function (p) {
    absent(p, 'legacy closing_odds pairs are not CLV-001 progress');
  });
});

t('the market gate renders no progress bar and no count', function () {
  if (/id="marketGate"[\s\S]{0,4000}?class="prog"/.test(RAW)) {
    throw new Error('the deferred market gate must not render a progress bar');
  }
});

t('the CLV gate ships the agreed fail-closed sentence', function () {
  present(/Prospective market-price validation is collecting/i, 'the collecting sentence');
  present(/No CLV figure is publication-approved yet/i, 'the not-approved sentence');
});

t('the CLV freeze claim is narrowed to CLV-001 results', function () {
  // REGRESSION. UFC outcomes and legacy price data predate CLV-001, so "frozen
  // before any result could be seen" is broader than the truth. The defensible
  // claim is about CLV-001's own results.
  [
    'frozen before any result can be seen',
    'frozen before any result is visible',
    'frozen before any result could be seen',
    'before any result was seen',
  ].forEach(function (p) { absent(p, 'the freeze claim must be scoped to CLV-001 results'); });
  present(/frozen before any CLV-001 result was computed or reviewed/i,
          'the narrowed freeze wording naming CLV-001');
});

t('the page says the market rule is not its own', function () {
  present(/not ours to apply|the rule that decides when this may be published is not ours|belongs to a research protocol/i,
          'the deferral to the owning protocol');
  present(/CLV-001/, 'the owning protocol named');
});

// ------------------------------- preserved behaviour ------------------------

t('the no-CTA rule still holds on the proof page', function () {
  ['btn-primary', 'create free account', 'analyze the next card', 'sign up for', 'start your free'].forEach(function (p) {
    absent(p, 'the proof page carries no CTA');
  });
});

t('the page is still noindex', function () {
  present(/<meta name="robots" content="noindex, nofollow">/, 'the noindex directive');
});

t('replay rows still never get a publication timestamp', function () {
  present(/re-run, not posted/, 'the replay timestamp placeholder');
});

// ------------------------------------------------------------------- report

if (failures.length) {
  console.error('\n  ' + failures.length + ' FAILED, ' + passed + ' passed\n');
  failures.forEach(function (f) { console.error('  ✗ ' + f); });
  console.error('');
  process.exit(1);
}
console.log('\n  ' + passed + ' passed — shipped copy matches what the data actually supports.\n');
