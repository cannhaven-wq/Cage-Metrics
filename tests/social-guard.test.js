// The social channel cannot publish a forecast.
//
// For three weeks after D-011 the Mon/Wed/Fri poster sent the retired model's
// win percentages to X, because the generator stamped its own model copy
// positioning:'research' and that stamp was the poster's only check. This pins
// the three things that now stop it: no schedule, no self-stamp, and a guard
// that reads the words.
'use strict';
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const read = p => fs.readFileSync(path.join(ROOT, p), 'utf8');
const { forecastClaim } = require('../build/social-copy-guard');

let n = 0, failed = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { failed++; console.error('FAIL', name, '\n  ', e.message); } };
const ok = (c, m) => { if (!c) throw new Error(m); };

// The three posts that actually went out, verbatim from the run logs.
const SHIPPED = [
  'UFC Fight Night: Allen vs. Duncan: our model reads DUNCAN 50% over ALLEN — but the matchup has a wrinkle worth seeing. Full breakdown 🧵',
  'Coin-Flip Corner 🪙 III vs FILI — our model has it just 54%. A coin flip in a lab coat. Who cracks first?',
  'BONFIM 50% over PRADO, and they finish at an elite clip. Should "rarely needs the judges" weigh heavier? Genuinely asking.',
];
for (const s of SHIPPED) t('refuses shipped forecast: ' + s.slice(0, 40), () => ok(forecastClaim(s), 'not caught: ' + s));

// Every model-era template phrasing still in the generator.
['our model reads A 62% over B', 'main event — our model: A 62%', "A 62% over B — our model's read, every factor shown.",
 'model has it 55%', 'the model likes A', 'Our pick: A', 'a value bet on B', 'A beats the closing line', 'a fade candidate at a short price',
 'win probability 61%'].forEach(s => t('refuses: ' + s, () => ok(forecastClaim(s), 'not caught: ' + s)));

// Market facts must still be postable, or the guard would silence the channel
// for the wrong reason.
['UFC 333: consensus moved 4.1 pts toward Evloev since our first broad capture (6 books).',
 'Best price on Volkanovski: +145 at DraftKings. Books are 3.2 pts apart.',
 'Nothing moved more than a point on this card. 9 fights, 8 books.',
 'Market: 62% Evloev, vig removed, 7 books.'].forEach(s => t('allows market fact: ' + s.slice(0, 40), () => ok(!forecastClaim(s), 'wrongly refused: ' + s)));

t('the poster has no schedule', () => {
  const y = read('.github/workflows/social-post.yml');
  const live = y.split('\n').filter(l => !/^\s*#/.test(l)).join('\n');
  ok(!/^\s*schedule\s*:/m.test(live) && !/cron\s*:/.test(live), 'social-post.yml carries an active schedule');
});

t('the generator does not stamp its own copy research-era', () => {
  const s = read('build/social-engine.js');
  ok(!/positioning\s*:\s*['"]research['"]/.test(s), "social-engine.js stamps positioning:'research' again");
});

t('the poster checks the words, on both paths', () => {
  const s = read('build/social-post.js');
  ok(/require\(['"]\.\/social-copy-guard['"]\)/.test(s), 'social-post.js does not load the guard');
  ok((s.match(/forecastClaim\(/g) || []).length >= 3, 'guard not applied to both the queue and the legacy path');
  ok(!/our model/i.test(s.replace(/\/\/.*$/gm, '')), 'social-post.js still carries "our model" in code');
});

if (failed) { console.error(`\n  ${failed} failed, ${n} passed`); process.exit(1); }
console.log(`\n  ${n} passed — the social channel cannot publish a forecast.`);
