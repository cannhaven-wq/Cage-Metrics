// Build script: pulls every fighter and event from Supabase, writes a static
// stub HTML at /f/<slug>-<id>.html and /e/<slug>-<id>.html, regenerates
// sitemap.xml. Designed to run unattended in CI on a 6-hour cron.
//
// The Supabase URL and key here are the same publishable anon key already
// committed in _shared.js. RLS protects everything. No secrets needed.
//
// Stale stubs (deleted fighters/events) are also cleaned up.

const fs = require('fs');
const path = require('path');
const { createClient } = require('@supabase/supabase-js');

const { slugify } = require('./slug');
const { fighterStub, eventStub } = require('./templates');

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SUPABASE_KEY = 'sb_publishable_boJGOA1CFN-SF14HHFGUAw_YEEm0DU8';
const SITE = 'https://cannonfightlab.com';

const ROOT = path.resolve(__dirname, '..');
const FIGHTERS_DIR = path.join(ROOT, 'f');
const EVENTS_DIR = path.join(ROOT, 'e');

const sb = createClient(SUPABASE_URL, SUPABASE_KEY);

// Page through Supabase results — the API caps responses at 1000 rows.
async function fetchAll(buildQuery) {
  const all = [];
  let from = 0;
  const pageSize = 1000;
  while (true) {
    const { data, error } = await buildQuery().range(from, from + pageSize - 1);
    if (error) throw error;
    if (!data || data.length === 0) break;
    all.push(...data);
    if (data.length < pageSize) break;
    from += pageSize;
  }
  return all;
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

// Write file only if content differs. Saves git diff churn — most stubs are
// stable run-to-run, so unchanged files stay unchanged on disk.
function writeIfChanged(filepath, content) {
  try {
    const existing = fs.readFileSync(filepath, 'utf8');
    if (existing === content) return false;
  } catch (_) { /* missing file is fine */ }
  fs.writeFileSync(filepath, content);
  return true;
}

// Remove any stub files in `dir` whose filename isn't in `keep`.
function pruneStaleStubs(dir, keep) {
  if (!fs.existsSync(dir)) return 0;
  const onDisk = fs.readdirSync(dir).filter(n => n.endsWith('.html'));
  let removed = 0;
  for (const name of onDisk) {
    if (!keep.has(name)) {
      fs.unlinkSync(path.join(dir, name));
      removed++;
    }
  }
  return removed;
}

async function prerenderFighters() {
  console.log('Fetching fighters...');
  const fighters = await fetchAll(() => sb
    .from('fighters')
    .select('id, name, nickname, division, wins, losses, draws, ufc_wins, ufc_losses, ufc_draws, height_in')
  );
  console.log(`Got ${fighters.length} fighters.`);

  ensureDir(FIGHTERS_DIR);
  const keep = new Set();
  const urls = [];
  let written = 0;

  for (const f of fighters) {
    if (!f.id || !f.name) continue;
    const slug = slugify(f.name);
    const filename = `${slug}-${f.id}.html`;
    keep.add(filename);
    if (writeIfChanged(path.join(FIGHTERS_DIR, filename), fighterStub(f))) {
      written++;
    }
    urls.push(`/f/${filename}`);
  }
  const removed = pruneStaleStubs(FIGHTERS_DIR, keep);
  console.log(`Fighters: ${written} written, ${removed} pruned, ${urls.length} total stubs.`);
  return urls;
}

async function prerenderEvents() {
  console.log('Fetching events...');
  const events = await fetchAll(() => sb
    .from('events')
    .select('id, name, event_date, location, is_upcoming')
  );
  console.log(`Got ${events.length} events.`);

  console.log('Fetching fights for competitor lists...');
  const fights = await fetchAll(() => sb
    .from('fights')
    .select('event_id, fighter_a_id, fighter_b_id, fighter_a_name, fighter_b_name')
  );
  console.log(`Got ${fights.length} fights.`);

  // Group competitor info by event_id so each event gets its participant list.
  const byEvent = {};
  for (const fight of fights) {
    if (!byEvent[fight.event_id]) byEvent[fight.event_id] = [];
    if (fight.fighter_a_id && fight.fighter_a_name) {
      byEvent[fight.event_id].push({ id: fight.fighter_a_id, name: fight.fighter_a_name });
    }
    if (fight.fighter_b_id && fight.fighter_b_name) {
      byEvent[fight.event_id].push({ id: fight.fighter_b_id, name: fight.fighter_b_name });
    }
  }

  ensureDir(EVENTS_DIR);
  const keep = new Set();
  const urls = [];
  let written = 0;

  for (const e of events) {
    if (!e.id || !e.name) continue;
    const slug = slugify(e.name);
    const filename = `${slug}-${e.id}.html`;
    keep.add(filename);
    if (writeIfChanged(path.join(EVENTS_DIR, filename), eventStub(e, byEvent[e.id] || []))) {
      written++;
    }
    urls.push(`/e/${filename}`);
  }
  const removed = pruneStaleStubs(EVENTS_DIR, keep);
  console.log(`Events: ${written} written, ${removed} pruned, ${urls.length} total stubs.`);
  return urls;
}

// Sitemap entries: static site pages + every fighter/event stub. Big sites
// eventually want a sitemap index; for now a single sitemap is well under
// Google's 50k-URL limit.
function regenerateSitemap(fighterUrls, eventUrls) {
  const today = new Date().toISOString().slice(0, 10);

  const staticPages = [
    { loc: '/',                priority: '1.0', changefreq: 'daily' },
    { loc: '/cardio.html',     priority: '0.9', changefreq: 'weekly' },
    { loc: '/stats.html',      priority: '0.9', changefreq: 'weekly' },
    { loc: '/fighters.html',   priority: '0.9', changefreq: 'daily' },
    { loc: '/h2h.html',        priority: '0.8', changefreq: 'weekly' },
    { loc: '/parlay.html',     priority: '0.7', changefreq: 'weekly' },
    { loc: '/fighter.html',    priority: '0.6', changefreq: 'daily' },
    { loc: '/event.html',      priority: '0.6', changefreq: 'daily' },
    { loc: '/pricing.html',    priority: '0.5', changefreq: 'monthly' },
    { loc: '/about.html',      priority: '0.5', changefreq: 'monthly' },
    { loc: '/contact.html',    priority: '0.4', changefreq: 'monthly' },
    { loc: '/disclaimer.html', priority: '0.3', changefreq: 'yearly' }
  ];

  const lines = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ''
  ];

  function pushUrl(loc, priority, changefreq) {
    lines.push('  <url>');
    lines.push(`    <loc>${SITE}${loc}</loc>`);
    lines.push(`    <lastmod>${today}</lastmod>`);
    lines.push(`    <changefreq>${changefreq}</changefreq>`);
    lines.push(`    <priority>${priority}</priority>`);
    lines.push('  </url>');
    lines.push('');
  }

  for (const p of staticPages) pushUrl(p.loc, p.priority, p.changefreq);
  for (const u of eventUrls)   pushUrl(u, '0.6', 'weekly');
  for (const u of fighterUrls) pushUrl(u, '0.5', 'weekly');

  lines.push('</urlset>');
  lines.push('');

  fs.writeFileSync(path.join(ROOT, 'sitemap.xml'), lines.join('\n'));
  const total = staticPages.length + eventUrls.length + fighterUrls.length;
  console.log(`Sitemap: ${total} URLs.`);
}

(async () => {
  try {
    const fighterUrls = await prerenderFighters();
    const eventUrls = await prerenderEvents();
    regenerateSitemap(fighterUrls, eventUrls);
    console.log('Done.');
  } catch (err) {
    console.error('Prerender failed:', err);
    process.exit(1);
  }
})();
