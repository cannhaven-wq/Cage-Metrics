/* ==========================================================================
   tests/sitemap-hygiene.test.js — the sitemap may not contradict the pages.

   Two defects this pins, both found in the shipped sitemap.xml on 2026-09-21:

     1. /card-lab.html was listed. It carries
        <meta name="robots" content="noindex"> and is a meta-refresh stub to
        "/". The sitemap was asking Google to crawl a URL the page itself asks
        Google to drop. A sitemap entry is a claim that a URL is worth
        indexing; a noindex tag is a claim that it is not. Both cannot be true.
     2. /fighter.html and /event.html were listed bare, with no ?id=. Without
        a query string those are empty shells — no fighter, no event, nothing
        unique to index. The populated versions are the /f/ and /e/ stubs,
        already in the sitemap in their thousands.

   This reads the shipped sitemap.xml and the shipped HTML and asserts they
   agree. It does not run the prerender build.

   Run:  node tests/sitemap-hygiene.test.js
   ========================================================================== */

'use strict';
const fs = require('fs');
const path = require('path');

const root = f => path.join(__dirname, '..', f);
const read = f => fs.readFileSync(root(f), 'utf8');

const SITEMAP = read('sitemap.xml');
const PRERENDER = read('build/prerender.js');

const locs = (SITEMAP.match(/<loc>([^<]+)<\/loc>/g) || [])
  .map(m => m.replace(/<\/?loc>/g, ''));

let passed = 0;
const failures = [];
function t(name, fn) {
  try { fn(); passed++; }
  catch (e) { failures.push(name + ' — ' + e.message); }
}
function ok(cond, msg) { if (!cond) throw new Error(msg); }

const ORIGIN = 'https://cannonfightlab.com';
// Root-level .html pages the sitemap lists (stubs under /f/, /e/, /card/ and
// /preview/ are generated and checked separately below).
const topLevel = locs
  .filter(u => u.startsWith(ORIGIN + '/'))
  .map(u => u.slice(ORIGIN.length))
  .filter(u => /^\/[^/]*$/.test(u) && (u === '/' || u.endsWith('.html')));

t('the sitemap is non-trivial and well formed at the edges', () => {
  ok(locs.length > 1000, 'only ' + locs.length + ' URLs in the sitemap');
  ok(/^<\?xml/.test(SITEMAP), 'no XML declaration');
  ok(/<\/urlset>\s*$/.test(SITEMAP), 'urlset is not closed');
  const dupes = locs.filter((u, i) => locs.indexOf(u) !== i);
  ok(dupes.length === 0, 'duplicate URLs in the sitemap: ' + dupes.slice(0, 5).join(', '));
});

t('every URL is absolute on the canonical domain', () => {
  const bad = locs.filter(u => !u.startsWith(ORIGIN + '/'));
  ok(bad.length === 0, 'off-domain or relative URLs: ' + bad.slice(0, 5).join(', '));
});

t('no legacy domain or branding survives in the sitemap', () => {
  ok(!/cage-?metrics/i.test(SITEMAP), 'a Cage Metrics URL is still listed');
});

t('no noindex page is listed in the sitemap', () => {
  const offenders = [];
  topLevel.forEach(u => {
    if (u === '/') return;
    const f = u.slice(1);
    if (!fs.existsSync(root(f))) { offenders.push(f + ' (listed but not in the repo)'); return; }
    const head = read(f).slice(0, 4000);
    if (/<meta[^>]+name=["']robots["'][^>]+noindex/i.test(head)) offenders.push(f + ' (noindex)');
  });
  ok(offenders.length === 0, 'sitemap lists pages that ask not to be indexed: ' + offenders.join(', '));
});

t('no meta-refresh redirect stub is listed in the sitemap', () => {
  const offenders = topLevel.filter(u => {
    if (u === '/') return false;
    const f = u.slice(1);
    return fs.existsSync(root(f)) && /http-equiv=["']refresh["']/i.test(read(f).slice(0, 4000));
  });
  ok(offenders.length === 0, 'redirect stubs listed: ' + offenders.join(', '));
});

t('the query-string shells are not listed bare', () => {
  ['/fighter.html', '/event.html'].forEach(u =>
    ok(topLevel.indexOf(u) === -1,
       u + ' is listed with no ?id= — it renders an empty shell'));
});

t('the generator list agrees with the shipped sitemap', () => {
  ok(!/loc:\s*'\/card-lab\.html'/.test(PRERENDER),
     'build/prerender.js still emits /card-lab.html');
  ok(!/loc:\s*'\/fighter\.html'/.test(PRERENDER),
     'build/prerender.js still emits the bare /fighter.html');
  ok(!/loc:\s*'\/event\.html'/.test(PRERENDER),
     'build/prerender.js still emits the bare /event.html');
  // everything the generator does list must be a real, indexable file
  const gen = (PRERENDER.match(/loc:\s*'(\/[a-z0-9-]*\.html)'/g) || [])
    .map(m => m.match(/'(\/[^']+)'/)[1]);
  ok(gen.length >= 10, 'the static page list looks truncated (' + gen.length + ')');
  gen.forEach(u => {
    const f = u.slice(1);
    ok(fs.existsSync(root(f)), 'prerender lists a missing file: ' + f);
    const head = read(f).slice(0, 4000);
    ok(!/<meta[^>]+name=["']robots["'][^>]+noindex/i.test(head),
       'prerender lists a noindex page: ' + f);
  });
});

t('every listed page has a title and a canonical tag', () => {
  const offenders = [];
  topLevel.forEach(u => {
    if (u === '/') return;
    const f = u.slice(1);
    if (!fs.existsSync(root(f))) return;
    const head = read(f).slice(0, 8000);
    if (!/<title>[^<]{5,}<\/title>/i.test(head)) offenders.push(f + ' (no title)');
    if (!/<link[^>]+rel=["']canonical["']/i.test(head)) offenders.push(f + ' (no canonical)');
  });
  ok(offenders.length === 0, offenders.join(', '));
});

t('listed pages have unique titles', () => {
  const seen = {};
  const dupes = [];
  topLevel.forEach(u => {
    const f = u === '/' ? 'index.html' : u.slice(1);
    if (!fs.existsSync(root(f))) return;
    const m = read(f).slice(0, 8000).match(/<title>([^<]+)<\/title>/i);
    if (!m) return;
    const title = m[1].trim();
    if (seen[title]) dupes.push(title + ' (' + seen[title] + ' and ' + f + ')');
    seen[title] = f;
  });
  ok(dupes.length === 0, 'duplicate <title> across listed pages: ' + dupes.join('; '));
});

t('robots.txt points at the canonical sitemap and blocks nothing', () => {
  const r = read('robots.txt');
  ok(/Sitemap:\s*https:\/\/cannonfightlab\.com\/sitemap\.xml/i.test(r),
     'robots.txt does not name the canonical sitemap');
  ok(!/^\s*Disallow:\s*\/\s*$/mi.test(r), 'robots.txt disallows the whole site');
  ok(!/cage-?metrics/i.test(r), 'robots.txt still names the old brand');
});

t('the retired picks stub is a single hop, not a chain', () => {
  const picks = read('picks.html');
  ok(/http-equiv=["']refresh["'][^>]*url=\/["']/i.test(picks),
     'picks.html does not refresh straight to /');
  ok(!/card-lab\.html/.test(picks.replace(/<!--[\s\S]*?-->/g, '')),
     'picks.html still hops through card-lab.html');
  ok(/rel=["']canonical["'][^>]*href=["']https:\/\/cannonfightlab\.com\/["']/i.test(picks),
     'picks.html canonical does not point at the homepage');
});

// ------------------------------------------------------------------ report
if (failures.length) {
  console.log(`\n  ${passed} passed, ${failures.length} FAILED\n`);
  failures.forEach(f => console.log(`  ✗ ${f}\n`));
  process.exit(1);
}
console.log(`\n  ${passed} passed — the sitemap and the pages agree on what is indexable.\n`);
