/* ==========================================================================
   tests/card-brief.test.js — the Cannon Card Brief is not a picks newsletter.

   This guards the unattended publishers, which are the ones that can embarrass
   the product without anyone watching: build/send-digest.js runs on a weekly
   cron and build/social-post.js on a Mon/Wed/Fri cron. A page with the wrong
   words is a page someone can read and fix; an email with the wrong words is
   already in an inbox.

   The defect this pins was live after the repositioning: the Brief's body had
   been rewritten to report market movement and carried "We do not sell picks"
   in its own footer, while its SUBJECT LINE still read

       "<Event> — model picks before the card"

   which is the one string every subscriber sees whether they open it or not.

   Run:  node tests/card-brief.test.js
   ========================================================================== */

'use strict';
const fs = require('fs');
const path = require('path');

const read = f => fs.readFileSync(path.join(__dirname, '..', f), 'utf8');
const DIGEST = read('build/send-digest.js');
const SOCIAL = read('build/social-post.js');

// A "//" comment explaining why a phrase is banned must not trip the ban.
const stripComments = src => src
  .replace(/\/\*[\s\S]*?\*\//g, ' ')
  .replace(/^\s*\/\/.*$/gm, ' ');

let passed = 0;
const failures = [];
function t(name, fn) {
  try { fn(); passed++; }
  catch (e) { failures.push(name + ' — ' + e.message); }
}
function ok(cond, msg) { if (!cond) throw new Error(msg); }

// Phrases that only ever appear when something is being recommended. "pick"
// on its own is excluded: a disclaimer legitimately says "we do not sell
// picks", and that sentence is the opposite of the problem.
const TOUT = [
  'best bet', 'best bets', 'lock of the', 'our picks', 'cfl picks',
  'model pick', 'model picks', 'model says', 'value bet', 'value play',
  'plays of the', 'sharp money', 'free money', 'beat the book',
  'guaranteed', 'expected value', 'positive ev', "we like"
];

t('the Brief subject line sells no pick', () => {
  const subjects = DIGEST.match(/const subject\s*=\s*[`'"][^`'"]*[`'"]/g) || [];
  ok(subjects.length > 0, 'no subject line found in send-digest.js');
  subjects.forEach(line => {
    const lower = line.toLowerCase();
    TOUT.forEach(p => ok(lower.indexOf(p) === -1,
      'a Brief subject line still says "' + p + '": ' + line));
    ok(!/\bpicks?\b/.test(lower),
      'a Brief subject line still uses the word "pick": ' + line);
  });
});

t('the Brief body sells no pick', () => {
  const body = stripComments(DIGEST).toLowerCase();
  TOUT.forEach(p => ok(body.indexOf(p) === -1,
    'send-digest.js still emits "' + p + '"'));
});

t('the Brief still says plainly that CFL does not sell picks', () => {
  ok(/do not sell picks/i.test(DIGEST),
     'the disclaimer that CFL does not sell picks was lost');
});

t('the Brief reports the market, not a forecast', () => {
  const body = stripComments(DIGEST);
  ok(/buildMarketLines/.test(body), 'the Brief no longer builds market lines');
  ok(!/model_picks|p_cal|engine_pick|confidence/i.test(body),
     'send-digest.js reads the forecast tables again');
});

t('an empty card is skipped, never filled with something else', () => {
  ok(/if \(!lines\.length\)[\s\S]{0,200}return;/.test(DIGEST),
     'the Brief no longer bails out when there is nothing to report');
});

t('the social publisher refuses anything not stamped as research', () => {
  const body = stripComments(SOCIAL);
  ok(/positioning/.test(body) && /research/.test(body),
     'social-post.js no longer gates on a research positioning stamp');
  const lower = body.toLowerCase();
  TOUT.forEach(p => ok(lower.indexOf(p) === -1,
    'social-post.js still emits "' + p + '"'));
});

t('signup copy across the site matches what the Brief actually sends', () => {
  ['index.html', 'signup.html', 'about.html', '_shared.js'].forEach(f => {
    // Comments are stripped in both syntaxes: _shared.js carries a "// 'get
    // our picks' — there are none" note explaining why the phrase is banned,
    // and a guard that trips on its own rationale is a guard nobody keeps.
    const src = stripComments(read(f).replace(/<!--[\s\S]*?-->/g, ' ')).toLowerCase();
    ['best bet', 'our picks', 'model picks', 'weekly picks', 'free picks']
      .forEach(p => ok(src.indexOf(p) === -1,
        f + ' promises "' + p + '" at signup, which the Brief does not send'));
  });
});

// ------------------------------------------------------------------ report
if (failures.length) {
  console.log(`\n  ${passed} passed, ${failures.length} FAILED\n`);
  failures.forEach(f => console.log(`  ✗ ${f}\n`));
  process.exit(1);
}
console.log(`\n  ${passed} passed — the Card Brief reports the market and sells nothing.\n`);
