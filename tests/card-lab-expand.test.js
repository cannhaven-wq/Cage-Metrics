/* ==========================================================================
   tests/card-lab-expand.test.js — Card Lab's expandable matchups (T-098).

   PLAIN ENGLISH: on the homepage, clicking a fight opens its tale of the tape
   and betting panel directly underneath it. Several fights can be open at
   once, nothing navigates away on that click, and "Additional Analytics"
   stays shut until the reader opens it.

   These rules are easy to break with one careless line (a `_open.clear()`, an
   `open` attribute on the details, an <a> around the preview), so they are
   pinned here. The page was also driven in a real browser against production
   rows; see coordination/HANDOFF.md for that run.

   Run:  node tests/card-lab-expand.test.js
   ========================================================================== */
'use strict';
const fs = require('fs');
const path = require('path');
const PAGE = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
let passed = 0; const failures = [];
function t(name, fn) { try { fn(); passed += 1; } catch (err) { failures.push(name + '\n      ' + err.message); } }
function ok(c, what) { if (!c) throw new Error(what || 'expected truthy'); }
const slice = (from, to) => PAGE.slice(PAGE.indexOf(from), PAGE.indexOf(to));

const build = slice('function buildFightCard', 'function fighterSideHtml');
const side  = slice('function fighterSideHtml', 'const _open');
const tape  = slice('function tapeHtml', 'function betHtml');
const bet   = slice('function betHtml', 'function moreHtml');
const more  = slice('function moreHtml', 'function setFightOpen');
const open  = slice('function setFightOpen', 'function wireExpansion');
const wire  = slice('function wireExpansion', 'async function hydrateFight');
const books = slice('function booksTableHtml', '// Surname for tight copy.');
const NEW_CODE = slice('function buildFightCard', '// Surname for tight copy.');

t('the preview is a real button that says what it controls', () => {
  ok(/<button type="button" class="fx-toggle"' ?\$\{toggleAttrs\}|class="fx-toggle"\$\{toggleAttrs\}/.test(build), 'preview is not a button');
  ok(/aria-expanded="' \+ isOpen \+ '" aria-controls="fxb-' \+ fight\.id/.test(build), 'aria-expanded / aria-controls missing');
  ok(/id="fxb-' \+ fight\.id \+ '"' \+ \(isOpen \? '' : ' hidden'\)/.test(build), 'panel is not hidden by default');
});

t('the preview carries both names, both flags and both prices, and never links out', () => {
  ok(/fighterSideHtml\(a, readA, 'a'\)/.test(build) && /fighterSideHtml\(b, readB, 'b'\)/.test(build), 'both corners not drawn');
  ok(/cfl\.flagClass/.test(side) && /cfl\.flagStyle/.test(side), 'flag wash dropped');
  ok(/bestAmerican/.test(side) && /bestBook/.test(side), 'price or book missing from the preview');
  ok(!/<a /.test(side), 'a link inside the preview button');
});

t('opening one fight never closes another', () => {
  ok(/_open\.add\(fid\)/.test(open), 'open does not add to the set');
  ok(!/_open\.clear\(\)/.test(PAGE), 'something clears every open fight');
  ok(!/\.forEach\([^)]*=>\s*setFightOpen\([^,]+,\s*false\)/.test(PAGE), 'something closes the other fights');
});

t('the open set survives a re-render', () => {
  const render = slice('function renderCards', 'function renderSearchStatus');
  ok(/_open\.forEach\(fid => \{ if \(document\.getElementById\('fxb-' \+ fid\)\) hydrateFight\(fid\)/.test(render), 'open fights are not repainted');
  ok(/const isOpen = _open\.has\(fight\.id\)/.test(build), 'a rebuilt fight forgets it was open');
});

t('a second click collapses, and the click handler does not navigate', () => {
  ok(/const open = !_open\.has\(fid\);\s*setFightOpen\(fid, open\)/.test(wire), 'toggle logic changed');
  ok(!/location\.(href|assign)/.test(NEW_CODE), 'the expanded panel navigates');
});

t('Additional Analytics is a collapsed <details> unless the reader opened it', () => {
  ok(/<details class="fx-more" data-more="' \+ fight\.id \+ '"' \+ \(_moreOpen\.has\(fight\.id\) \? ' open' : ''\)/.test(more), 'details opens by itself');
  ok(/<summary>Additional Analytics<\/summary>/.test(more), 'section is not labelled "Additional Analytics"');
  ok(!/_moreOpen\.add\(/.test(open), 'expanding a fight opens Additional Analytics');
});

t('the tale of the tape has every row the brief asks for, and a dash for a gap', () => {
  ['Country', 'Age', 'Height', 'Reach', 'Weight', 'Stance', 'Pro record', 'UFC record'].forEach(r =>
    ok(tape.indexOf("['" + r + "'") !== -1, 'tape row missing: ' + r));
  ok(/title="Not in our data">—/.test(tape), 'missing data is not a labelled dash');
  ok(/weigh-in weights are not in our data/.test(tape), 'weight row claims a weigh-in figure');
});

t('the betting panel shows both corners, the books, the age and the movement working', () => {
  ['Best price', 'Market chance', 'Fair price', 'Across books'].forEach(r =>
    ok(bet.indexOf("line('" + r + "'") !== -1, 'betting row missing: ' + r));
  ok(/bookCount/.test(bet) && /fresh\.when/.test(bet), 'book count or capture age missing');
  ok(/M\.baselineCaveat\(readA\)/.test(bet), 'movement printed without its caveat');
  ok(/matchedNowProb/.test(bet), '"now" is not the matched cohort');
  ok(/No sportsbook has priced this fight/.test(bet), 'no-line state does not say so');
});

t('no surface copy calls our first capture an opener', () => {
  const lower = NEW_CODE.replace(/^\s*\/\/.*$/gm, ' ').toLowerCase();
  ['opening line', 'opening price', 'opening odds', 'opening market', 'opened at', 'market open', 'the open ', 'since open']
    .forEach(p => ok(lower.indexOf(p) === -1, 'new code says "' + p + '"'));
  ok(/does not see sportsbook openers/.test(NEW_CODE), 'the chart note no longer says we do not see openers');
});

t('best price is ordered by the American number and nothing else', () => {
  ok(/Math\.max\.apply\(null, rows\.map\(r => \+r\.american_odds_a\)\)/.test(books), 'best on side A is not the max price');
  ok(/Math\.max\.apply\(null, rows\.map\(r => \+r\.american_odds_b\)\)/.test(books), 'best on side B is not the max price');
});

t('no model number reaches the expanded panel', () => {
  ['model_picks', 'model_predictions', 'pre_fight_snapshots', 'win_model_locks', 'predictions'].forEach(n =>
    ok(NEW_CODE.indexOf("from('" + n + "')") === -1, 'reads ' + n));
  ok(!/\bpick\b/i.test(NEW_CODE.replace(/^\s*\/\/.*$/gm, ' ').replace(/\/\*[\s\S]*?\*\//g, ' ')), 'the word "pick" reaches page code');
});

if (failures.length) {
  console.error('card-lab-expand: ' + failures.length + ' failed, ' + passed + ' passed');
  failures.forEach(f => console.error('  ✗ ' + f)); process.exit(1);
}
console.log('card-lab-expand: ' + passed + ' passed');
