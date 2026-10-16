/* ==========================================================================
   tests/card-lab-expand.test.js — Card Lab's expandable matchups (T-098).

   PLAIN ENGLISH: on the homepage, clicking a fight opens three panels — tale
   of the tape, betting odds, line movement — directly underneath it. Several fights can be open at
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

const build = slice('function buildFightCard', 'const _open');
const body  = slice('function matchupBodyHtml', 'function tapeHtml');
const tape  = slice('function tapeHtml', 'function oddsPanelHtml');
const bet   = slice('function oddsPanelHtml', 'function moreHtml');
const more  = slice('function moreHtml', 'function setFightOpen');
const open  = slice('function setFightOpen', 'function wireExpansion');
const wire  = slice('function wireExpansion', 'async function hydrateFight');
const books = slice('function booksTableHtml', '// Surname for tight copy.');
const NEW_CODE = slice('function miniFlag', '// Surname for tight copy.');

t('the row is a real button that says what it controls', () => {
  ok(/<button type="button" class="cl-toggle"' \+ toggleAttrs/.test(build), 'row is not a button');
  ok(/aria-expanded="' \+ isOpen \+ '" aria-controls="fxb-' \+ fight\.id/.test(build), 'aria-expanded / aria-controls missing');
  ok(/id="fxb-' \+ fight\.id \+ '"' \+ \(isOpen \? '' : ' hidden'\)/.test(build), 'panel is not hidden by default');
});

t('the row carries position, both flags, names, prices and pro records, and never links out', () => {
  ok(/'<span class="cl-no">' \+ \(idx \+ 1\)/.test(build), 'card position missing');
  ok(/const corner = \(f, side\) => [^\n]*miniFlag\(f\)/.test(build), 'a flag is missing');
  ok(/rowName\(f\)/.test(build) && /rowRecord\(f\)/.test(build), 'a name or pro record is missing');
  ok(/corner\(a, 'a'\) \+ odds\(readA, a, 'a'\)/.test(build) && /odds\(readB, b, 'b'\) \+ corner\(b, 'b'\)/.test(build), 'both corners are not drawn and priced');
  ok(/bestAmerican/.test(build) && /bestBook/.test(build), 'price or book missing from the row');
  ok(/bookCount/.test(build) && /fresh\.when/.test(build), 'book count or capture age missing from the row price');
  const btn = build.slice(build.indexOf('class="cl-toggle"'), build.indexOf("'</button>' + starHtml"));
  ok(!/<a /.test(btn), 'a link inside the row button');
});

t('the open fight has three panels in order: tape, odds, movement', () => {
  const i = body.indexOf('Tale of the Tape'), j = body.indexOf('Betting Odds'), k = body.indexOf('Line Movement');
  ok(i > 0 && j > i && k > j, 'panels missing or out of order');
  ok(/cfl\.flagStyle\(f\)/.test(tape), 'flag wash dropped from the tape');
});

t('only the main event is named; nothing invents a co-main or a card section', () => {
  ok(/fight\.is_main_event \? 'Main event · '/.test(build), 'main event not labelled');
  ok(/' is-main'/.test(build), 'main event is not the featured row');
  ok(!/co-?main/i.test(NEW_CODE.replace(/^\s*\/\/.*$/gm, ' ').replace(/'[^']*not[^']*'/g, '')), 'a co-main label appears in page code');
  ok(/id="sectionSeg"/.test(PAGE) && /disabled aria-disabled="true"[^>]*>Prelims</.test(PAGE), 'prelim filter is live without a source');
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
  ok(/<summary>[\s\S]*?Additional Analytics/.test(more), 'section is not labelled "Additional Analytics"');
  ok(!/_moreOpen\.add\(/.test(open), 'expanding a fight opens Additional Analytics');
});

t('the tale of the tape has every row the brief asks for, and a dash for a gap', () => {
  ['Age', 'Height', 'Weight', 'Reach', 'Stance', 'Country', 'Pro record', 'UFC record'].forEach(r =>
    ok(tape.indexOf("['" + r + "'") !== -1, 'tape row missing: ' + r));
  ok(/title="Not in our data">—/.test(tape), 'missing data is not a labelled dash');
  ok(/weigh-in weights are not in our data/.test(tape), 'weight row claims a weigh-in figure');
});

t('the betting panel shows both corners, the books, the age and the movement working', () => {
  ['Best price', 'Market chance', 'Fair price', 'Across books'].forEach(r =>
    ok(more.indexOf("line('" + r + "'") !== -1, 'market detail row missing: ' + r));
  ok(/fxbooks-/.test(bet) && /fxchart-/.test(bet), 'sportsbook table or chart missing from the panels');
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

t('the main event opens on arrival, once, unless a #fight-N link names another', () => {
  const load = slice('async function loadFights', 'function renderSourceNote');
  ok(/if \(!_autoOpened\) \{\s*_autoOpened = true;/.test(load), 'auto-open is not once-only');
  ok(/fights\.find\(f => f\.is_main_event\)/.test(load), 'auto-open is not the main event');
  ok(/!\/\^#fight-\\d\+\$\/\.test\(location\.hash/.test(load), 'a shared link to another fight would also open the main event');
  ok(load.indexOf('_open.add(main.id)') < load.indexOf('renderCards();'), 'opened after the first paint');
  ok(!/_moreOpen\.add/.test(load), 'auto-open also opens Additional Analytics');
});

if (failures.length) {
  console.error('card-lab-expand: ' + failures.length + ' failed, ' + passed + ' passed');
  failures.forEach(f => console.error('  ✗ ' + f)); process.exit(1);
}
console.log('card-lab-expand: ' + passed + ' passed');
