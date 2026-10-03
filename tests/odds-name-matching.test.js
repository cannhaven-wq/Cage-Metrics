/* ==========================================================================
   tests/odds-name-matching.test.js — the feed's name for a fighter is not ours.

   WHY THIS EXISTS

   On 2026-10-02, the day before UFC 332, two fights on the card had no
   sportsbook price and the page correctly showed "No line yet". The books had
   them priced. The capture job had fetched them. It simply could not tell they
   were the same fight, because the feed uses a different FIRST name:

       ours "Mick Parkin"             feed "Michael Parkin"
       ours "Alexander Hernandez"     feed "Alex Hernandez"
       ours "Alexander Volkanovski"   feed "Alex Volkanovski"   <- UFC 333 MAIN

   All three existing tiers — full name, first+last, spaces-squashed — key on
   the full given name, so every one of them missed, and missed identically.
   A prefix rule would recover Alex/Alexander and still miss Mick/Michael
   ("Mic", then k vs h). The surname pair is the only key that reaches it.

   THE DANGEROUS HALF

   `fight_odds` is APPEND-ONLY. A wrong match writes a real sportsbook price
   onto the wrong fight, permanently, and that price then feeds the vig-free
   consensus, the matched movement cohort and CLV scoring. Nobody can delete it
   afterwards.

   So the asymmetry is the whole design: failing to match costs a visible "No
   line yet" that the page is honest about. Matching wrongly costs a number
   that cannot be removed. Every test below that asserts a REFUSAL is therefore
   load-bearing — more than the ones asserting a match.

   Run:  node tests/odds-name-matching.test.js
   ========================================================================== */

'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SRC = path.join(__dirname, '..', 'build', 'fetch-odds.js');
const src = fs.readFileSync(SRC, 'utf8');

// Pull the pure matcher out of the module rather than require()ing it: the CI
// node job installs no dependencies, and fetch-odds.js imports the Supabase
// client at the top. This still exercises the REAL source — edit the functions
// and this test moves with them.
function extract(name) {
  const re = new RegExp('function ' + name + '\\s*\\([^)]*\\)\\s*\\{');
  const at = src.search(re);
  if (at === -1) throw new Error('could not find function ' + name + ' in build/fetch-odds.js');
  let i = src.indexOf('{', at), depth = 0;
  for (let j = i; j < src.length; j++) {
    if (src[j] === '{') depth++;
    else if (src[j] === '}') { depth--; if (depth === 0) return src.slice(at, j + 1); }
  }
  throw new Error('unbalanced braces reading ' + name);
}

const sandbox = {};
vm.createContext(sandbox);
vm.runInContext(
  ['normalizeName', 'firstLast', 'squash', 'lastName', 'pairKey',
   'buildFightIndex', 'lookupFight'].map(extract).join('\n'),
  sandbox);
const { buildFightIndex, lookupFight, lastName, normalizeName } = sandbox;

let passed = 0;
const failures = [];
function t(name, fn) { try { fn(); passed++; } catch (e) { failures.push(name + ' — ' + e.message); } }
function ok(c, m) { if (!c) throw new Error(m); }
function eq(a, b, m) {
  if (a !== b) throw new Error((m || 'value') + ': expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a));
}

const CARD = [
  { id: 1, fighter_a_name: 'Johnny Walker',         fighter_b_name: 'Mick Parkin' },
  { id: 2, fighter_a_name: 'Rafael Dos Anjos',      fighter_b_name: 'Alexander Hernandez' },
  { id: 3, fighter_a_name: 'Alexander Volkanovski', fighter_b_name: 'Movsar Evloev' },
  { id: 4, fighter_a_name: 'Jean Silva',            fighter_b_name: 'Yadong Wang' },
];

/* ------------------------------------------- the three real misses, verbatim */

t('the exact names the feed sent on 2026-10-02 now match', () => {
  const ix = buildFightIndex(CARD);
  [['Johnny Walker', 'Michael Parkin', 1],
   ['Rafael dos Anjos', 'Alex Hernandez', 2],
   ['Alex Volkanovski', 'Movsar Evloev', 3]].forEach(([h, a, want]) => {
    const got = lookupFight(ix, h, a);
    ok(got, `"${h} vs ${a}" still does not match — this is the live miss`);
    eq(got.id, want, `"${h} vs ${a}" matched the wrong fight`);
  });
});

t('the fights that already matched still match the same way', () => {
  const ix = buildFightIndex(CARD);
  eq(lookupFight(ix, 'Jean Silva', 'Yadong Wang').id, 4, 'an exact name stopped matching');
  eq(lookupFight(ix, 'Johnny Walker', 'Mick Parkin').id, 1, 'our own spelling stopped matching');
});

/* ----------------------------------------------- the refusals that matter more */

t('an AMBIGUOUS surname pair matches NOTHING — it is deleted, not resolved', () => {
  // Two fights, same surnames. First-writer-wins would silently pick one and
  // write a real price onto a 50/50 guess, into a table nobody can edit.
  const ix = buildFightIndex([
    { id: 10, fighter_a_name: 'Jon Silva',  fighter_b_name: 'Mike Wang' },
    { id: 11, fighter_a_name: 'Paul Silva', fighter_b_name: 'Dave Wang' },
  ]);
  eq(lookupFight(ix, 'Someone Silva', 'Other Wang'), null,
     'an ambiguous surname pair resolved to a fight — fight_odds is append-only, '
     + 'so that price could never be taken back');
});

t('sharing ONE surname is not enough', () => {
  const ix = buildFightIndex(CARD);
  eq(lookupFight(ix, 'Johnny Walker', 'Totally Different'), null,
     'matched on a single shared surname');
  eq(lookupFight(ix, 'Someone Else', 'Mick Parkin'), null,
     'matched on a single shared surname');
});

t('two fighters with the SAME surname cannot key the tier', () => {
  // "Silva vs Silva" would produce a degenerate self-pair key.
  const ix = buildFightIndex([
    { id: 20, fighter_a_name: 'Anderson Silva', fighter_b_name: 'Thales Silva' },
  ]);
  eq(lookupFight(ix, 'Wanderlei Silva', 'Erick Silva'), null,
     'a same-surname fight matched a different same-surname fight');
});

t('a very short surname cannot key the tier', () => {
  // Two-letter tokens collide far too easily to risk a permanent write.
  const ix = buildFightIndex([
    { id: 30, fighter_a_name: 'Kai Yu', fighter_b_name: 'Rong Li' },
  ]);
  eq(lookupFight(ix, 'Someone Yu', 'Another Li'), null,
     'a two-letter surname keyed the surname tier');
});

t('a completely unrelated bout still returns null', () => {
  const ix = buildFightIndex(CARD);
  eq(lookupFight(ix, 'Mohammad Fahmi', 'Ahmed El Sisy'), null,
     'a non-UFC event matched a UFC fight');
});

/* ------------------------------------------------------------- tier ordering */

t('the surname tier is LAST — a stricter tier always wins', () => {
  // If the surname tier ran first it could outrank an exact full-name match.
  const ix = buildFightIndex([
    { id: 40, fighter_a_name: 'Alex Pereira',      fighter_b_name: 'Jon Jones' },
    { id: 41, fighter_a_name: 'Alexandre Pereira', fighter_b_name: 'Jonny Jones' },
  ]);
  const got = lookupFight(ix, 'Alex Pereira', 'Jon Jones');
  ok(got, 'an exact name stopped matching when a near-duplicate existed');
  eq(got.id, 40, 'a looser tier outranked an exact full-name match');
});

t('lastName handles a multi-word surname the way the feed writes it', () => {
  eq(lastName(normalizeName('Rafael Dos Anjos')), 'anjos', 'ours');
  eq(lastName(normalizeName('Rafael dos Anjos')), 'anjos', 'the feed');
  eq(lastName(normalizeName('Cris')), 'cris', 'a single-token name must not throw');
});

// ------------------------------------------------------------------ report
if (failures.length) {
  console.log(`\n  ${passed} passed, ${failures.length} FAILED\n`);
  failures.forEach(f => console.log(`  ✗ ${f}\n`));
  process.exit(1);
}
console.log(`\n  ${passed} passed — the feed's spelling is recovered, and an ambiguous one is refused.\n`);
