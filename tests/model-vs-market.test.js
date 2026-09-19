/* ==========================================================================
   tests/model-vs-market.test.js — the homepage shows the sportsbook number
   and never an "edge".

   Two defects this pins, both found live on the UFC 331 card (2026-09-19,
   T-021) and both corrected under D-010:

     1. index.html blanked the market cell whenever the model sat more than
        15 points above the market and told the reader "no consensus line
        yet". The line was real — eight books, twenty minutes old. A model
        disagreement was being reported as missing data, and only in the
        direction that flattered the model.
     2. Gaps of 4 to 15 points shipped as a green "+N% model over market" with
        a "Value alert" badge and a "Value" sort. That is an edge percentage in
        the user interface, which CLAUDE.md's first rule prohibits and which
        Q-14 explicitly left standing.

   And the four contradicted public claims from AUDIT_2026-09-18 §1 (T-020):
   "graded at real closing prices" in the meta/OG strings, "find where the
   betting line is wrong" in the hero, hardcoded replay/live figures in prose,
   and the stale factor list in the how-to steps.

   This reads the shipped files and asserts on what a human sees. Comments
   and <style> are stripped first — a comment explaining why a phrase is
   forbidden must not itself trip the test for that phrase.

   Run:  node tests/model-vs-market.test.js
   ========================================================================== */

'use strict';
const fs = require('fs');
const path = require('path');

const read = f => fs.readFileSync(path.join(__dirname, '..', f), 'utf8');
const RAW = read('index.html');
const strip = src => src
  .replace(/<style>[\s\S]*?<\/style>/g, ' ')
  .replace(/<!--[\s\S]*?-->/g, ' ')
  .replace(/\/\*[\s\S]*?\*\//g, ' ')
  .replace(/^\s*\/\/.*$/gm, ' ')
  .replace(/\s+/g, ' ');
const COPY = strip(RAW);
const LOWER = COPY.toLowerCase();
const INSIGHTS = strip(read('fight-insights.js'));

let passed = 0;
const failures = [];
function t(name, fn) {
  try { fn(); passed++; }
  catch (e) { failures.push(name + ' — ' + e.message); }
}
function ok(cond, msg) { if (!cond) throw new Error(msg); }
function absent(phrase, msg) {
  ok(LOWER.indexOf(phrase.toLowerCase()) === -1, msg || ('shipped copy still contains "' + phrase + '"'));
}
function present(phrase, msg) {
  ok(COPY.indexOf(phrase) !== -1, msg || ('shipped copy lost "' + phrase + '"'));
}

// ------------------------------------------------------- 1. the market cell
t('the market cell is never blanked because the model disagrees', () => {
  ok(!/value\s*>\s*15/.test(COPY), 'the >15-point suppression guard is back');
  ok(!/marketPct\s*=\s*null;\s*value\s*=\s*0/.test(COPY), 'the market cell is nulled after a gap check');
  absent('no consensus line yet', 'a missing-data message is still used for a model disagreement');
  absent('needs a market price');
});

t('a fight with no line says so, in words that blame nobody', () => {
  present('no sportsbook line captured yet');
  present('needs a sportsbook line');
});

t('the page reads the sportsbook-only vig-free view first, with a fallback', () => {
  ok(/from\('v_fight_market_vigfree'\)/.test(COPY), 'v_fight_market_vigfree is not read');
  ok(/from\('v_fight_odds_consensus'\)/.test(COPY), 'the consensus fallback is gone');
  ok(/book_count,\s*last_updated/.test(COPY), 'book count and capture time are not selected');
});

t('every market cell carries its book count and its age', () => {
  present('vig removed');
  ok(/stale, /.test(COPY), 'a stale line is not called stale');
  ok(/renderOddsStatus/.test(COPY), 'the card-level odds status line is gone');
  present('No sportsbook lines captured for this card yet.');
});

// ---------------------------------------------------- 2. no edge percentage
t('no edge percentage, badge, alert or sort ships', () => {
  absent('value alert');
  absent('model over market');
  absent('biggest edge');
  absent('value bar');
  ok(!/class="t">Edge</.test(COPY), 'an "Edge" cell is still rendered');
  ok(!/\$\{value\.toFixed\(0\)\}%/.test(COPY), 'the signed edge percentage is still rendered');
  ok(!/VALUE_EDGE/.test(COPY), 'VALUE_EDGE is back');
  ok(!/data-sort="value"/.test(COPY), 'the Value sort is back');
  ok(!/cbadge value/.test(COPY), 'the Value badge is back');
  ok(!/tier-value/.test(COPY), 'the green value rail is back');
  ok(!/hpParlay/.test(COPY), 'the "picks clear our value bar" strip is back');
});

t('the difference is labelled as a disagreement, never as an edge', () => {
  ok(/data-sort="disagree"/.test(COPY), 'the Disagreement sort is missing');
  ok(/class="t">Difference</.test(COPY), 'the Difference cell is missing');
  present('CFL higher');
  present('market higher');
  present('mostly agree');
  present('a flag on the model, not the price');
  present('a disagreement, not a proven edge');
  present('A disagreement is not a proven betting edge');
  present("The market's price is right more often than any model");
});

t('a wide gap is a neutral badge, not a green one', () => {
  present('Far from the market');
  const css = RAW.match(/<style>[\s\S]*?<\/style>/)[0];
  ok(/\.cbadge\.gap\s*\{[^}]*color:\s*var\(--text-2\)/.test(css), '.cbadge.gap is not neutral-coloured');
  ok(!/\.cbadge\.gap\s*\{[^}]*--green/.test(css), '.cbadge.gap is green');
});

t('the model-far-above-market red flag exists and index.html loads the file that carries it', () => {
  ok(/confidence - marketPct >= 10/.test(INSIGHTS), 'fight-insights.js lost the far-above-market flag');
  ok(INSIGHTS.indexOf('more often the model missing something than the market being wrong') !== -1,
    'the far-above-market flag lost its wording');
  ['index.html', 'event.html', 'fighter.html'].forEach(f => {
    ok(/fight-insights\.js\?v=8/.test(read(f)), f + ' does not load fight-insights.js?v=8');
  });
});

t('"the books lean the other way" fires only when the books actually favour the opponent', () => {
  // marketPct is the picked fighter's market probability and a pick is always
  // above 50, so the old test (confidence - marketPct <= -3) could only fire
  // when the market was MORE sure of the same fighter — and then said the
  // books leaned the other way. The flag must key on the market side.
  ok(/marketPct != null && marketPct < 50/.test(INSIGHTS), 'the lean-the-other-way flag is not keyed on marketPct < 50');
  ok(!/confidence - marketPct <= -3/.test(INSIGHTS), 'the wrong-direction condition is back');
});

t('event.html carries the same rule: market shown, difference in points, no edge or value badge', () => {
  const EV = strip(read('event.html'));
  ok(!/edgePp > 15/.test(EV), 'event.html still blanks the market cell above a 15-point gap');
  ok(!/⚡ Value/.test(EV), 'event.html still renders a Value badge');
  ok(!/>Edge \$\{/.test(EV), 'event.html still renders an "Edge +Npp" figure');
  ok(/Difference \$\{gapStr\}/.test(EV), 'event.html lost the Difference line');
  ok(EV.indexOf('Closing market') === -1, 'event.html still calls the last captured line the closing market');
});

// -------------------------------------------- 3. the four contradicted claims
t('no closing-price claim in the strings that ship with every share', () => {
  const head = RAW.slice(0, RAW.indexOf('</head>'));
  ok(head.indexOf('closing price') === -1, 'the <head> still claims grading at closing prices');
  ok(head.indexOf('graded at real closing') === -1, 'the <head> still claims grading at closing prices');
  ok(!/\d+%/.test(head.match(/<meta name="description" content="([^"]*)"/)[1]), 'the meta description carries a hardcoded percentage');
  ok(!/\d+%/.test(head.match(/<meta property="og:description" content="([^"]*)"/)[1]), 'the OG description carries a hardcoded percentage');
  ok(!/\d+%/.test(head.match(/<meta name="twitter:description" content="([^"]*)"/)[1]), 'the Twitter description carries a hardcoded percentage');
});

t('the hero does not claim the line is wrong', () => {
  absent('betting line is wrong');
  absent('where the price looks off');
  absent('underpricing');
  present('Model vs Market.');
});

t('the replay figures stay labelled simulated and the live record is not blended in', () => {
  present('(simulated)');
  present('Historical simulation.');
  present('Live published record.');
  absent('519-139');
  absent('+10.0%');
  absent('12-5 on settled');
  absent('graded at real closing prices');
  absent('snapshot as of');
  ok(/HERO_RECORD_SOURCE = 'backtest'/.test(COPY), 'the hero record source is no longer the replay');
  ok(/\.eq\('source',\s*HERO_RECORD_SOURCE\)/.test(COPY), 'the hero query lost its source filter');
});

t('the how-to steps no longer name retired drivers or tell the reader to bet value', () => {
  absent('age, cardio, takedown defense');
  absent('bet only on value');
  absent('compare edge factors');
  present('Decide for yourself');
});

// ------------------------------------------------------------------ report
if (failures.length) {
  console.log(`\n  ${passed} passed, ${failures.length} FAILED\n`);
  failures.forEach(f => console.log(`  ✗ ${f}\n`));
  process.exit(1);
}
console.log(`\n  ${passed} passed — the homepage shows the sportsbook number and claims no edge.\n`);
