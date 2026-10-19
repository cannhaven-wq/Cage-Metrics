/* ==========================================================================
   tests/fighting-style.test.js — the UFC.com fighting-style job (T-102).

   PLAIN ENGLISH: the job copies the "Fighting style" field from a fighter's
   UFC.com page. It must read exactly that field, never write over a value a
   person set, and never take the style of a different fighter who happens to
   share the URL.

   Run:  node tests/fighting-style.test.js
   ========================================================================== */
'use strict';
const S = require('../build/check-fighting-style.js');
let passed = 0; const failures = [];
function t(name, fn) { try { fn(); passed += 1; } catch (err) { failures.push(name + '\n      ' + err.message); } }
function eq(a, b, what) { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error((what || '') + ' expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a)); }

const PAGE = `
<h1 class="hero-profile__name">Joaquin Buckley</h1>
<div class="c-bio__row--3col">
  <div class="c-bio__field"><div class="c-bio__label">Status</div><div class="c-bio__text">Active</div></div>
  <div class="c-bio__field"><div class="c-bio__label">Place of Birth</div><div class="c-bio__text">St. Louis, United States</div></div>
  <div class="c-bio__field"><div class="c-bio__label">Fighting style</div>
    <div class="c-bio__text">Kickboxer</div></div>
  <div class="c-bio__field"><div class="c-bio__label">Trains at</div><div class="c-bio__text">Sanford MMA</div></div>
</div>`;

t('slug matches UFC.com athlete URLs', () => {
  eq(S.ufcSlug('Joaquin Buckley'), 'joaquin-buckley');
  eq(S.ufcSlug('Marc-Andre Barriault'), 'marc-andre-barriault');
  eq(S.ufcSlug("Sean O'Malley"), 'sean-omalley');
  eq(S.ufcSlug('Jasmine Jasudavičius'), 'jasmine-jasudavicius');
  eq(S.ufcSlug('Raul Rosas Jr.'), 'raul-rosas-jr');
});

t('reads exactly the Fighting style field', () => {
  eq(S.parseFightingStyle(PAGE), 'Kickboxer');
  eq(S.parseFightingStyle(PAGE.replace(/<div class="c-bio__field"><div class="c-bio__label">Fighting style[\s\S]*?Kickboxer<\/div><\/div>/, '')), null);
  eq(S.parseFightingStyle('<div class="c-bio__label">Fighting style</div><div class="c-bio__text">Brazilian Jiu-Jitsu &amp; Wrestling</div>'), 'Brazilian Jiu-Jitsu & Wrestling');
  eq(S.parseFightingStyle(''), null);
});

t('reads the page heading', () => {
  eq(S.parsePageName(PAGE), 'Joaquin Buckley');
  eq(S.parsePageName('<title>Mike Malott | UFC</title>'), 'Mike Malott');
});

t('never writes over a person, never takes another fighter\'s style', () => {
  eq(S.decide({ name: 'Joaquin Buckley', fighting_style_src: 'manual' }, { status: 'ok', name: 'Joaquin Buckley', style: 'Boxer' }).action, 'skip');
  eq(S.decide({ name: 'Joaquin Buckley' }, { status: 'ok', name: 'Joaquin Buckley', style: 'Kickboxer' }), { action: 'fill', style: 'Kickboxer' });
  eq(S.decide({ name: 'Joaquin Buckley' }, { status: 'ok', name: 'Someone Else', style: 'Boxer' }).action, 'wrong_person');
  eq(S.decide({ name: 'Joaquin Buckley' }, { status: 'ok', name: 'Joaquin Buckley', style: null }).action, 'no_style');
  eq(S.decide({ name: 'Joaquin Buckley' }, { status: 'not_found' }).action, 'not_found');
});

t('a found or manual value is settled; a miss is retried after a month', () => {
  const now = Date.parse('2026-10-16T00:00:00Z');
  eq(S.needsLookup({ fighting_style: 'Boxer', fighting_style_src: 'ufc.com' }, now), false);
  eq(S.needsLookup({ fighting_style: null, fighting_style_src: 'manual' }, now), false);
  eq(S.needsLookup({ fighting_style: null, fighting_style_checked_at: null }, now), true);
  eq(S.needsLookup({ fighting_style: null, fighting_style_checked_at: '2026-10-10T00:00:00Z' }, now), false);
  eq(S.needsLookup({ fighting_style: null, fighting_style_checked_at: '2026-09-01T00:00:00Z' }, now), true);
});

if (failures.length) {
  console.error('fighting-style: ' + failures.length + ' failed, ' + passed + ' passed');
  failures.forEach(f => console.error('  ✗ ' + f)); process.exit(1);
}
console.log('fighting-style: ' + passed + ' passed');
