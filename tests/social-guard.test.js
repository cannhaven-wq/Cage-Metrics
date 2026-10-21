// The social channel cannot publish a forecast.
//
// For three weeks after D-011 the Mon/Wed/Fri poster sent the retired model's
// win percentages to X, because the generator stamped its own model copy
// positioning:'research' and that stamp was the poster's only check. This pins
// the three things that now stop it: no schedule, a stamp only the guard can
// grant, and a guard that reads the words.
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

// THE STAMP RULE (rewritten 2026-10-21, T-038). Until then this test said the
// generator must never stamp its own copy 'research', because a self-applied
// label was exactly how model copy reached X. The research-era generator now
// does stamp — and the rule is what makes that safe: the stamp may be applied
// ONLY by code that has just run the word guard on the exact text being
// stamped, and a stamped piece that reads as a forecast fails here. A stamp
// with no guard in front of it is the old defect and still fails.
t('the generator stamps research only on pieces its own guard has just passed', () => {
  const s = read('build/social-engine.js');
  const code = s.replace(/^\s*\/\/.*$/gm, '');
  const stamps = code.match(/positioning\s*:\s*['"]research['"]/g) || [];
  if (!stamps.length) return; // not stamping at all is always safe
  ok(stamps.length === 1, `social-engine.js stamps 'research' in ${stamps.length} places — keep it to buildQueue`);
  ok(/require\(['"]\.\/social-copy-guard['"]\)/.test(code), 'social-engine.js stamps research without loading the guard');
  const fn = code.slice(code.indexOf('function buildQueue'));
  const body = fn.slice(0, fn.indexOf('\n}\n'));
  ok(/positioning\s*:\s*['"]research['"]/.test(body), "the 'research' stamp is applied outside buildQueue");
  const guardAt = body.search(/forecastClaim\(|refusalOf\(/);
  const stampAt = body.search(/positioning\s*:\s*['"]research['"]/);
  ok(guardAt > -1 && guardAt < stampAt, 'buildQueue stamps research before (or without) running the guard');

  // And on what it actually produces: real data in, every stamped entry clean;
  // a forecast in, nothing stamped.
  const E = require('../build/social-engine');
  const fx = require('./fixtures/social-engine-ufc333.json');
  const b = E.buildBatch(fx);
  const q = E.buildQueue([{ event: b.event, pieces: b.pieces }]);
  ok(q.length > 0, 'the real-data fixture produced an empty queue');
  q.forEach(e => ok(e.positioning !== 'research' || !forecastClaim(e.tweet), `stamped research but reads as a forecast: ${e.tweet}`));
  const poisoned = [{ id: 'x', platform: 'X', pillar: 'x', image: { layout: 'verdict' }, copy: SHIPPED[0], tweet: SHIPPED[0], hashtags: '', cta: '', question: '' }];
  ok(E.buildQueue([{ event: b.event, pieces: poisoned }]).length === 0, 'a shipped forecast was stamped research');
});

t('the poster checks the words, on both paths', () => {
  const s = read('build/social-post.js');
  ok(/require\(['"]\.\/social-copy-guard['"]\)/.test(s), 'social-post.js does not load the guard');
  ok((s.match(/forecastClaim\(/g) || []).length >= 3, 'guard not applied to both the queue and the legacy path');
  ok(!/our model/i.test(s.replace(/\/\/.*$/gm, '')), 'social-post.js still carries "our model" in code');
});

t('the manual drafter prints the market post, not a pick table (T-039)', () => {
  const s = read('build/draft-post.js');
  const code = s.replace(/\/\/.*$/gm, '');
  ok(/require\(['"]\.\/social-post['"]\)/.test(code), 'draft-post.js no longer reuses social-post.js::buildPost');
  ok(/forecastClaim\(/.test(code), 'draft-post.js does not run the forecast guard');
  ok(!/model_picks|Model pick|Confidence/i.test(code), 'draft-post.js reads or prints the retired model again');
  const p = read('build/social-post.js');
  ok(/if \(require\.main === module\)/.test(p), 'requiring social-post.js would post — the drafter must never post');
});

if (failed) { console.error(`\n  ${failed} failed, ${n} passed`); process.exit(1); }
console.log(`\n  ${n} passed — the social channel cannot publish a forecast.`);
