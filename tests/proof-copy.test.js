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

// track-record.html is the adjacent summary page. It is not the Proof Center,
// but it describes the SAME rows, so a timing claim it makes that the data
// cannot support contradicts everything above. Scanned separately so its
// findings name the right file.
const TRACK_RAW = read('track-record.html');
// Three views, because they answer different questions:
//   MARKUP — comments gone, tags kept: for attribute checks such as an href.
//   TEXT   — tags gone too: the actual prose a reader sees. Presence of a claim
//            must be proved HERE, never in the raw source — an earlier version
//            of this file was satisfied by a code comment, which is the whole
//            failure mode these tests exist to catch.
//   LOWER  — TEXT lowercased, for banned-phrase matching.
const TRACK_MARKUP = strip(TRACK_RAW);
// The market-price section alone. Scoped so that describing the REPLAY's
// grading price elsewhere on the page does not read as a claim about CLV-001's
// benchmark — those are different things and only one is under CLV-001.
const CLV_BLOCK = (function () {
  const i = TRACK_MARKUP.indexOf('id="clvStatus"');
  if (i === -1) return '';
  const j = TRACK_MARKUP.indexOf('<!-- Honesty box', i);
  return TRACK_MARKUP.slice(i, j === -1 ? i + 4000 : j).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
})();
const TRACK_TEXT = TRACK_MARKUP.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
const TRACK = TRACK_TEXT.toLowerCase();

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

// ------------------- track-record.html must not contradict this page --------
// REGRESSION. track-record.html shipped "added once, never revised" and "Locked
// before the bell — our real pre-fight record" while describing rows in tables
// that carry no such guarantee, and while splitting live-vs-simulated on a date
// comparison that includes same-day rows. Neither claim may come back.

function trackAbsent(phrase, why) {
  if (TRACK.indexOf(phrase.toLowerCase()) !== -1) {
    throw new Error('track-record.html must not contain ' + JSON.stringify(phrase) + ' — ' + why);
  }
}
// Prose the reader actually sees.
function trackPresent(re, why) {
  if (!re.test(TRACK_TEXT)) throw new Error('track-record.html is missing: ' + why);
}
// Markup-level, for links and attributes that tag-stripping would eat.
function trackLinks(re, why) {
  if (!re.test(TRACK_MARKUP)) throw new Error('track-record.html is missing: ' + why);
}

t('track-record.html does not claim rows are written once and never revised', function () {
  [
    'added once, never revised',
    'added once, never edited',
    'added once, never re-priced',
    'never revised',
    'never edited',
  ].forEach(function (p) {
    trackAbsent(p, 'model_picks and model_edges carry no append-only guarantee');
  });
});

t('track-record.html makes no wholesale pre-bell claim', function () {
  [
    'locked before the bell',
    'locked-before-the-bell',
    'locked before fight night',
    'locked-before-the-fight',
    'locked live',
    'before the card started',
    'written to the database before the event',
    'written to the database before fight night',
    'our real pre-fight record',
  ].forEach(function (p) {
    trackAbsent(p, 'the live bucket is a dataset, not a per-row timing proof');
  });
});

t('track-record.html uses the same framing and points at the row-level grades', function () {
  trackPresent(/prospective/i, 'the live record described as prospective');
  trackPresent(/recorded with a timestamp|recorded with timestamps/i,
               'calls described as recorded with timestamps rather than proven pre-bell');
  trackPresent(/graded (row by row|per row|each row)|grades each row|varies/i,
               'a statement that timing evidence varies by row');
  trackLinks(/href="proof\.html"/, 'a link to the Proof Center for the row-level grades');
});

t('the same-day banner split on track-record.html is described honestly', function () {
  // The split itself is a date comparison that includes same-day rows. The copy
  // beside it must say so rather than imply the rows beat the first bell.
  trackPresent(/includes same-day rows/i,
               'a disclosure that the live/simulated split includes same-day rows');
});

// ------------- track-record.html defers to CLV-001 the same way -------------
// REGRESSION. track-record.html shipped its own CLV methodology: a 100-pick
// threshold and a benchmark described as "the closing price". Both are
// CLV-001's to define. Neither may live on this page.

t('track-record.html has a market-price section that defers to CLV-001', function () {
  if (!CLV_BLOCK) throw new Error('track-record.html is missing its #clvStatus section');
  [
    /Prospective market-price validation is collecting/i,
    /CLV-001/,
    /No CLV figure is publication-approved yet/i,
    /only when CLV-001's own publication gate is satisfied/i,
  ].forEach(function (re) {
    if (!re.test(CLV_BLOCK)) throw new Error('the CLV section is missing: ' + re);
  });
});

t('track-record.html states no CLV threshold of its own', function () {
  [
    '100+ locked picks',
    '100 locked picks',
    'once 100',
    'both a posted price and a closing price',
    'both a posted and closing price',
  ].forEach(function (p) {
    trackAbsent(p, 'the CLV publication threshold belongs to CLV-001, not this page');
  });
  // And no bare number-plus-pick threshold anywhere in the CLV section.
  if (/\b\d{2,}\s*(\+\s*)?(locked\s+)?(picks|bets|observations)\b/i.test(CLV_BLOCK)) {
    throw new Error('the CLV section must not state a local observation threshold: ' + CLV_BLOCK.slice(0, 200));
  }
});

t('track-record.html does not call the CLV benchmark the literal closing price', function () {
  ['the closing price', 'the closing line', 'beat the closing'].forEach(function (p) {
    if (CLV_BLOCK.toLowerCase().indexOf(p) !== -1) {
      throw new Error('the CLV section must not name the benchmark ' + JSON.stringify(p) +
                      ' — CLV-001 owns that definition; use "CFL closing-price proxy" if naming it');
    }
  });
  // Where the page does name the stored field, it is a proxy, not a verified close.
  if (/(at|to) the (real )?closing price/i.test(TRACK_TEXT)) {
    throw new Error('track-record.html presents a stored field as the literal closing price');
  }
});

t('track-record.html contains no "live locked record" wording', function () {
  ['live locked record', 'locked record'].forEach(function (p) {
    trackAbsent(p, "source='live' and a date-level split do not prove pre-bell timing");
  });
});

t('track-record.html does not claim to hold every CFL prediction or model', function () {
  [
    "every pick we've made",
    "every model we've ever run",
    "every model we've run",
    'every cfl prediction',
    'every prediction we',
    'all of our models',
  ].forEach(function (p) {
    trackAbsent(p, 'duration and prop research run under separate protocols and are not on this page');
  });
  trackPresent(/main[- ]engine/i, 'the main-engine scope wording');
  trackPresent(/own protocols and appear nowhere on this page|their own protocols/i,
               'a statement that other research does not appear here');
});

// ------------------------------------------------------------------- report

if (failures.length) {
  console.error('\n  ' + failures.length + ' FAILED, ' + passed + ' passed\n');
  failures.forEach(function (f) { console.error('  ✗ ' + f); });
  console.error('');
  process.exit(1);
}
console.log('\n  ' + passed + ' passed — shipped copy matches what the data actually supports.\n');
