/* ==========================================================================
   tests/legal-drafts.test.js — a legal draft cannot go live by accident.

   terms.html (T-048) and legal-review/privacy_draft.html (T-054) are drafts
   for the owner and a lawyer. Both are deployed with the rest of the repo,
   because GitHub Pages serves every file — so "not published" has to mean
   something checkable:

     1. Each carries a visible "Draft — not yet in effect" banner and noindex.
     2. Neither is in the sitemap or the prerender page list.
     3. Nothing links to them: not the footer, not the nav, not any root page.
     4. Every placeholder is still visibly marked, so a half-finished draft
        cannot read as a finished one.
     5. The live privacy.html is untouched by the draft.

   Publishing either is a deliberate change that will (and should) break this
   file: resolve the placeholders, remove the banner, flip robots, link it, and
   update this test in the same pull request. CHECKOUT_BLOCKERS is guarded
   separately in tests/entitlements.test.js.

   Run:  node tests/legal-drafts.test.js
   ========================================================================== */

'use strict';
const fs = require('fs');
const path = require('path');

const root = f => path.join(__dirname, '..', f);
const read = f => fs.readFileSync(root(f), 'utf8');

let passed = 0;
const failures = [];
function t(name, fn) {
  try { fn(); passed++; } catch (e) { failures.push(name + ' — ' + e.message); }
}
function ok(cond, msg) { if (!cond) throw new Error(msg); }

const DRAFTS = ['terms.html', 'legal-review/privacy_draft.html'];

DRAFTS.forEach(f => {
  t(f + ' exists, is noindex and says it is a draft', () => {
    ok(fs.existsSync(root(f)), f + ' is missing');
    const src = read(f);
    ok(/<meta[^>]+name=["']robots["'][^>]+noindex/i.test(src.slice(0, 6000)),
       f + ' is not noindex');
    ok(/Draft — not yet in effect/.test(src), f + ' has no visible draft banner');
    ok(/class="draft-banner"/.test(src), f + ' draft banner is not rendered as a banner');
  });

  t(f + ' still marks its open decisions', () => {
    const n = (read(f).match(/class="ph"/g) || []).length;
    ok(n >= 5, f + ' has only ' + n + ' marked placeholders — a draft that ' +
       'looks finished is how one gets published unreviewed');
    ok(/\[(OWNER|LAWYER|OWNER\/LAWYER):/.test(read(f)), f + ' has no bracketed owner/lawyer marker');
  });
});

t('terms.html loads the page chrome in the documented order', () => {
  const src = read('terms.html');
  const sb = src.indexOf('supabase-js@2.106.1/dist/umd/supabase.min.js" integrity="sha384-9dsYHX1/12VQI+gHRtPXSM3YFsgJ+iIPjTy4WCtY7XbKG/q7MTdZxZhMd4cL9Gif"');
  const sh = src.indexOf('<script src="_shared.js');
  const au = src.indexOf('<script src="_auth.js"></script>');
  const nav = src.indexOf('cfl.renderNav(');
  ok(sb !== -1 && sh !== -1 && au !== -1 && nav !== -1, 'a chrome script is missing');
  ok(sb < sh && sh < au && au < nav, 'chrome scripts are out of order');
  ok(/<nav class="cfl-nav"><\/nav>/.test(src) && /<footer class="cfl-footer"><\/footer>/.test(src),
     'nav/footer placeholders are missing');
});

t('no draft is in the sitemap or the prerender page list', () => {
  const sitemap = read('sitemap.xml');
  const prerender = read('build/prerender.js');
  ok(!/\/terms\.html/.test(sitemap), 'terms.html is listed in sitemap.xml');
  ok(!/privacy_draft/.test(sitemap), 'the privacy draft is listed in sitemap.xml');
  ok(!/terms\.html/.test(prerender), 'build/prerender.js lists terms.html');
  ok(!/privacy_draft/.test(prerender), 'build/prerender.js lists the privacy draft');
});

t('nothing on the site links to a draft', () => {
  const offenders = [];
  const pages = fs.readdirSync(root('.')).filter(f => /\.(html|js)$/.test(f));
  pages.forEach(f => {
    if (f === 'terms.html') return;
    const src = read(f).replace(/<!--[\s\S]*?-->/g, ' ');
    if (/href=["'][^"']*terms\.html/i.test(src) || /['"]terms\.html['"]/.test(src)) offenders.push(f + ' → terms.html');
    if (/privacy_draft/.test(src)) offenders.push(f + ' → privacy_draft');
  });
  ok(offenders.length === 0, 'a draft is linked from the live site: ' + offenders.join(', '));
});

t('the live privacy policy is not the draft', () => {
  const live = read('privacy.html');
  ok(!/Draft — not yet in effect/.test(live), 'privacy.html carries the draft banner');
  ok(!/class="ph"/.test(live), 'privacy.html carries draft placeholders');
});

t('the owner review list exists beside the drafts', () => {
  ok(fs.existsSync(root('legal-review/OWNER_REVIEW_2026-10-21.md')),
     'legal-review/OWNER_REVIEW_2026-10-21.md is missing');
});

if (failures.length) {
  console.log(`\n  ${passed} passed, ${failures.length} FAILED\n`);
  failures.forEach(f => console.log(`  ✗ ${f}\n`));
  process.exit(1);
}
console.log(`\n  ${passed} passed — the legal drafts are drafts, and nothing links to them.\n`);
