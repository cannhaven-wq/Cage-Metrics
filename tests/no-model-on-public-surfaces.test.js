/* ==========================================================================
   tests/no-model-on-public-surfaces.test.js — the forecasting model does not
   appear on any forward-facing page, and the market does.

   WHAT THIS REPLACES

   This file was tests/model-vs-market.test.js. That test existed to hold a
   narrower line: the homepage could show the engine's number beside the
   sportsbook number as long as it never called the difference an "edge" and
   never hid the market cell behind a wide gap (D-010, T-020/T-021).

   In September 2026 the product moved past that line. CFL tested whether the
   engine's disagreement with the market was worth acting on, could not show
   that it was, and took the forecast off the public product rather than keep
   publishing it with a disclaimer. So the rule this file enforces is no longer
   "label the difference carefully" — it is:

     1. No forward-facing page shows a CFL win probability, a pick, a
        confidence tier, or a difference between our number and the market's.
     2. No forward-facing page reads a model-forecast table or view.
     3. The market IS shown, and never without its book count and its age.
     4. The movement baseline is never called the opening line. Since D-012 it
        is the FIRST BROAD CFL CAPTURE — the first instant three distinct
        sportsbooks had the fight priced — and movement is measured only over
        the books quoting at both ends.
     5. Best price is ordered by price, and the page says so.

   The archive pages (proof.html, track-record.html, predictor.html,
   edges.html) are exempt by design: deleting a failed test is the one thing a
   research site must not do. They carry a dated archive banner instead, which
   this file checks for.

   It reads the shipped files and asserts on what a human sees. Comments and
   <style> are stripped first — a comment explaining why a phrase is forbidden
   must not itself trip the test for that phrase.

   Run:  node tests/no-model-on-public-surfaces.test.js
   ========================================================================== */

'use strict';
const fs = require('fs');
const path = require('path');

const read = f => fs.readFileSync(path.join(__dirname, '..', f), 'utf8');

const strip = src => src
  .replace(/<style>[\s\S]*?<\/style>/g, ' ')
  .replace(/<!--[\s\S]*?-->/g, ' ')
  .replace(/\/\*[\s\S]*?\*\//g, ' ')
  .replace(/^\s*\/\/.*$/gm, ' ');

// The forward-facing product. Everything a visitor reaches from the nav or
// from search that is about an upcoming card.
const PRODUCT = ['index.html', 'market.html', 'fight.html', 'event.html',
                 'fighter.html', 'parlay.html',
                 'cardio.html', 'stats.html', 'pricing.html',
                 'about.html', 'signup.html', 'account.html', 'mybook.html',
                 // Added 2026-10-12: legal and account pages are public too, and
                 // disclaimer.html's share text said "Stats and predictions".
                 'disclaimer.html', 'privacy.html', 'contact.html', 'login.html',
                 'watchlist.html',
                 // Added 2026-10-21: the draft Terms of Service (T-048). It is
                 // noindex and unlinked, but Pages serves it, so it is held to
                 // the same ban as every other legal page.
                 'terms.html'];

// Documented history. Exempt from the model ban, required to say so.
const ARCHIVE = ['proof.html', 'track-record.html', 'predictor.html', 'edges.html',
                 'methodology.html', 'props.html'];

let passed = 0;
const failures = [];
function t(name, fn) {
  try { fn(); passed += 1; } catch (err) { failures.push(`${name}\n      ${err.message}`); }
}
function ok(cond, what) { if (!cond) throw new Error(what || 'expected truthy'); }

// --------------------------------------------------------------- the ban

// Phrases that assert a CFL forecast. Each is a regex plus the plain-English
// reason it is banned, so a failure explains itself.
const BANNED = [
  [/\bModel pick\b/i,                 'names a model pick'],
  [/\bmodel(?:’|\')?s (?:pick|verdict|number|forecast)\b/i, 'attributes a pick or number to the model'],
  [/\bModel vs\.? Market\b/i,         'frames the page as model against market'],
  [/\b(High|Medium|Low) confidence\b/i, 'publishes a confidence tier'],
  [/\bCFL higher\b|\bmarket higher\b/i, 'reports a model-vs-market difference'],
  [/\bvalue (?:alert|bet|edge)\b/i,   'claims a value bet'],
  [/\bbetting edge\b/i,               'claims a betting edge'],
  [/\bbest bet\b/i,                   'names a best bet'],
  [/\bedge factors?\b/i,              'sells edge factors'],
  [/\bValue-model\b/i,                'names the value model as a product'],
  [/\bPick-lock\b/i,                  'sells a pick-lock email'],
  [/\bodds-blind forecast\b/i,        'advertises the forecast'],
  [/\bwould_bet\b/,                   'reads the betting flag'],
  // Added 2026-10-12 after the current-state audit found each of these on a
  // public surface the list above did not cover.
  [/\bour model\b/i,                  'speaks for the model'],
  [/\bmodels? picks?\b/i,             'names a model pick'],
  [/\bfade candidates?\b/i,           'recommends fading a fighter'],
  [/\bUFC Predictions\b/i,            'titles the page as predictions'],
  [/\bPredictions? (?:&|&amp;) (?:Edges|Full-Card Picks)\b/i, 'titles the page as predictions'],
  [/\bprediction model\b/i,           'describes CFL as a prediction model'],
  [/\bStats and predictions\b/i,      'says the site publishes predictions'],
];

// Tables and views that only exist to serve a forecast.
const BANNED_READS = [
  'model_predictions', 'v_model_picks_graded', 'v_model_edges_graded',
  'v_fight_locked_forecast', 'stake_frac',
  // fighter.html read both of these until 2026-10-12: the engine's graded
  // record per fighter ("Model called X of N") and the archived Prop Board's
  // projections, shown without the archive banner.
  'v_fighter_model_record', 'v_prop_projections_current', "from('model_picks')",
];

// One documented exemption, and it is narrow. `v_fighter_consistency` grades
// each cardio read `high` or `limited` by how much round-3+ tape it rests on,
// and cardio.html surfaces that as "High confidence". It is a statement about
// SAMPLE SIZE, not about who wins a fight, and it predates the model by a
// year. Exempting the file wholesale would be too loose, so the exemption
// names the one pattern — anything else on that page still fails.
const EXEMPT = {
  'cardio.html': [/\b(High|Medium|Low) confidence\b/i],
  // disclaimer.html's "62% favorite under our model" sentence was rewritten to
  // a market example on 2026-10-21 (owner-approved, packet A2); its exemption
  // is gone, so the page is held to every rule above.
};

PRODUCT.forEach(file => {
  const src = strip(read(file));
  const exempt = EXEMPT[file] || [];
  t(`${file} publishes no CFL forecast`, () => {
    BANNED.forEach(([re, why]) => {
      if (exempt.some(e => String(e) === String(re))) return;
      const m = src.match(re);
      ok(!m, `${file} ${why} — found "${m && m[0]}"`);
    });
  });
  t(`${file} reads no forecast table`, () => {
    BANNED_READS.forEach(name => {
      ok(src.indexOf(name) === -1, `${file} still reads ${name}`);
    });
  });
});

// `model_picks` is the append-only pre-fight record. It is still written on
// every card and still read by the archive, but nothing forward-facing may
// read it, because reading it means rendering a pick.
PRODUCT.forEach(file => {
  t(`${file} does not read the locked pick record`, () => {
    const src = strip(read(file));
    ok(!/from\('model_picks'\)/.test(src), `${file} reads model_picks`);
  });
});

// ------------------------------------------------------- the market is shown

const INDEX  = strip(read('index.html'));
const MARKET = strip(read('market.html'));
const FIGHT  = strip(read('fight.html'));

t('the homepage is the card, and the card is the market', () => {
  ok(/Card Lab/.test(INDEX), 'the homepage no longer names Card Lab');
  ok(/v_fight_market_movement|loadCardMovement/.test(read('index.html')),
    'the homepage does not read the market movement view');
  ok(/vig removed/i.test(INDEX), 'the homepage does not say the vig is removed');
});

t('every market surface routes through market.js', () => {
  ['index.html', 'market.html', 'fight.html', 'event.html', 'fighter.html', 'parlay.html'].forEach(f => {
    ok(/<script src="market\.js\?v=\d+"><\/script>/.test(read(f)),
      `${f} does not load market.js — market formatting must not be re-implemented per page`);
  });
});

t('a price is never shown without its book count and its age', () => {
  const M = read('market.js');
  ok(/bookCount/.test(M) && /fresh/.test(M), 'market.js no longer carries book count and freshness');
  [['index.html', INDEX], ['market.html', MARKET], ['fight.html', FIGHT]].forEach(([name, src]) => {
    ok(/books?/i.test(src), `${name} shows no book count`);
    ok(/capture|updated|ago/i.test(src), `${name} shows no quote age`);
  });
});

t('the movement baseline is never called the opening line', () => {
  [['index.html', INDEX], ['market.html', MARKET], ['fight.html', FIGHT]].forEach(([name, src]) => {
    ok(!/\bopening line\b/i.test(src), `${name} calls our first capture the opening line`);
  });
  ok(/first broad capture|3\+ (?:books|sportsbooks)|three or more sportsbooks/i.test(INDEX),
     'the homepage does not label its baseline as the first broad capture');
  ok(/baselineCaveat/.test(read('market.js')),
     'market.js lost the movement provenance caveat');
  ok(/MIN_MATCHED_BOOKS/.test(read('market.js')),
     'market.js no longer gates movement on a matched book cohort');
  ok(!/\bopen_p_[ab]\b|\bbooks_at_open\b/.test(read('market.js')),
     'market.js still reads the retired single-instant "open" columns');
});

t('best price means the best price, and the pages say so', () => {
  const M = read('market.js');
  ok(/affiliate/i.test(M), 'market.js no longer states the no-affiliate-ordering rule');
  ok(/american/i.test(M), 'market.js no longer orders best price by the American number');
  ok(/best price/i.test(MARKET), 'Market Lab does not surface a best price');
});

// ------------------------------------------------------------ the archive

ARCHIVE.forEach(file => {
  t(`${file} carries the dated archive banner`, () => {
    const src = read(file);
    ok(/class="cfl-archive-note"/.test(src), `${file} has no archive banner`);
    ok(/no longer (?:part of|in) the product/i.test(src),
      `${file}'s banner does not say the model left the product`);
  });
});

t('the archive is still reachable, and still shows losses', () => {
  const proof = strip(read('proof.html'));
  ok(/Losses sit in the same list as wins/i.test(proof) || /losses/i.test(proof),
    'the Proof Center no longer mentions losses');
  ok(/proof\.html/.test(read('_shared.js')), 'the Proof Center left the nav');
});

// ------------------------------------------------------------ the email

t('the email product is the Cannon Card Brief and sells no picks', () => {
  const shared = read('_shared.js');
  ok(/Cannon Card Brief/.test(shared), '_shared.js no longer names the Cannon Card Brief');
  ok(/No picks\./.test(shared), 'the Brief no longer says it contains no picks');
  ok(!/model’s verdict|model's verdict/.test(strip(shared)),
    'the signup copy still promises the model’s verdict');
});

// ---------------------------------------------------- generated surfaces
// The prerender job writes ~5,400 public pages. They are not in PRODUCT, and
// until 2026-10-12 nothing checked them: 14 match previews said "Cannon Fight
// Lab's models pick X" in their FAQ structured data, and every card and preview
// page was titled "Predictions". Structured data and share titles are public
// claims even though no visitor sees them on the page, so this reads the raw
// file — scripts and JSON-LD included.

const GENERATED_BANNED = BANNED.concat([
  [/\bwho wins\b/i, 'asks who wins in structured data'],
]);
['card', 'preview', 'e'].forEach(dir => {
  const abs = path.join(__dirname, '..', dir);
  if (!fs.existsSync(abs)) return;
  const files = fs.readdirSync(abs).filter(f => f.endsWith('.html'));
  t(`${dir}/ — ${files.length} generated pages publish no forecast`, () => {
    for (const f of files) {
      const raw = fs.readFileSync(path.join(abs, f), 'utf8');
      for (const [re, why] of GENERATED_BANNED) {
        const m = raw.match(re);
        ok(!m, `${dir}/${f} ${why} — found "${m && m[0]}"`);
      }
    }
  });
});

t('the preview and card generators print no pick even when handed one', () => {
  const { matchupPreview } = require('../build/preview-templates');
  const { eventPreview } = require('../build/event-preview-templates');
  const A = { id: 2, name: 'Alpha Fighter' }, B = { id: 3, name: 'Bravo Fighter' };
  const ev = { id: 9, name: 'UFC Test Night', event_date: '2026-10-17', is_upcoming: true };
  const fight = { id: 1, weight_class: 'Lightweight', is_main_event: true };
  // A pick the old code would have printed: Alpha at 70%.
  const picks = [{ fighter_id: 2, model_p: 0.7 }];
  const html = matchupPreview({ fight, fighterA: A, fighterB: B, event: ev, picks });
  const card = eventPreview({ event: ev, rows: [{ fight, fighterA: A, fighterB: B, slug: 'x', pick: { name: A.name, pct: 70 } }], previewSlugFor: () => 'x' });
  for (const [label, out] of [['preview', html], ['card', card]]) {
    for (const [re, why] of GENERATED_BANNED) {
      const m = out.match(re);
      ok(!m, `${label} template ${why} — found "${m && m[0]}"`);
    }
    ok(!/\b70\s?%/.test(out), `${label} template printed the pick's probability`);
  }
});

t('prerender does not read the engine picks', () => {
  ok(!/from\(['"]model_picks['"]\)/.test(strip(read('build/prerender.js'))),
    'build/prerender.js reads model_picks again');
});

// ----------------------------------------------------------------- report
if (failures.length) {
  console.log(`\n  ${passed} passed, ${failures.length} FAILED\n`);
  failures.forEach(f => console.log(`  ✗ ${f}\n`));
  process.exit(1);
}
console.log(`\n  ${passed} passed — the model is off the product and the market is on it.\n`);
