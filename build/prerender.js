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
const { matchupPreview, previewSlug } = require('./preview-templates');

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SUPABASE_KEY = 'sb_publishable_boJGOA1CFN-SF14HHFGUAw_YEEm0DU8';
const SITE = 'https://cannonfightlab.com';

const ROOT = path.resolve(__dirname, '..');
const FIGHTERS_DIR = path.join(ROOT, 'f');
const EVENTS_DIR = path.join(ROOT, 'e');
const PREVIEW_DIR = path.join(ROOT, 'preview');

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

// Matchup previews: a real indexable preview page per fight on an upcoming
// card. Generated only for `is_upcoming=true` events so the directory stays
// small and we don't accidentally index post-fight previews that contradict
// the result. Past-event preview files are pruned each run.
async function prerenderMatchupPreviews() {
  console.log('Fetching upcoming events for matchup previews...');
  const { data: upcomingEvents, error: evErr } = await sb
    .from('events')
    .select('id, name, event_date, location, is_upcoming')
    .eq('is_upcoming', true);
  if (evErr) throw evErr;
  console.log(`Got ${upcomingEvents.length} upcoming events.`);

  if (!upcomingEvents.length) {
    // Still want to prune any stale files from a previous run.
    ensureDir(PREVIEW_DIR);
    const removed = pruneStaleStubs(PREVIEW_DIR, new Set());
    console.log(`Matchup previews: 0 written, ${removed} pruned.`);
    return [];
  }

  const eventIds = upcomingEvents.map(e => e.id);
  const evMap = {};
  upcomingEvents.forEach(e => { evMap[e.id] = e; });

  const fights = await fetchAll(() => sb
    .from('fights')
    .select('id, event_id, fighter_a_id, fighter_b_id, fighter_a_name, fighter_b_name, is_main_event, is_title_fight, weight_class')
    .in('event_id', eventIds)
  );
  console.log(`Got ${fights.length} fights on upcoming cards.`);

  const fighterIds = [...new Set(fights.flatMap(f => [f.fighter_a_id, f.fighter_b_id]).filter(Boolean))];
  const fightIds   = fights.map(f => f.id).filter(Boolean);
  if (!fightIds.length) {
    ensureDir(PREVIEW_DIR);
    const removed = pruneStaleStubs(PREVIEW_DIR, new Set());
    console.log(`Matchup previews: 0 written, ${removed} pruned.`);
    return [];
  }

  // Best-effort joins. Any view that doesn't exist or errors out is treated
  // as "no data" so a missing analytics view never blocks preview generation.
  async function safe(query) {
    try {
      const { data, error } = await query;
      if (error) { console.warn('[preview] join skipped:', error.message); return []; }
      return data || [];
    } catch (e) {
      console.warn('[preview] join threw:', e.message);
      return [];
    }
  }

  const [fightersData, predsData, cardioData, finishData] = await Promise.all([
    safe(sb.from('fighters').select('id, name, nickname').in('id', fighterIds)),
    safe(sb.from('model_predictions').select('model_version, fight_id, fighter_id, model_p').in('fight_id', fightIds)),
    safe(sb.from('v_fighter_consistency').select('fighter_id, weight_class, cardio_tier').in('fighter_id', fighterIds)),
    safe(sb.from('v_fighter_finish_rate').select('fighter_id, total_fights, ko_tko_rate, sub_rate').in('fighter_id', fighterIds)),
  ]);

  const fmap = {};
  fightersData.forEach(f => { fmap[f.id] = f; });

  // picksByFight[fight_id] = [{ model_version, fighter_id, model_p }]
  const picksByFight = {};
  predsData.forEach(p => {
    if (!picksByFight[p.fight_id]) picksByFight[p.fight_id] = [];
    picksByFight[p.fight_id].push(p);
  });

  // Cardio: prefer CAREER row (per-weight-class rows are noise at this level).
  const cardioMap = {};
  cardioData.forEach(r => {
    if (r.weight_class === 'CAREER') cardioMap[r.fighter_id] = r.cardio_tier;
  });
  const finishMap = {};
  finishData.forEach(r => { finishMap[r.fighter_id] = r; });

  ensureDir(PREVIEW_DIR);
  const keep = new Set();
  const urls = [];
  let written = 0;
  let skipped = 0;

  for (const fight of fights) {
    if (!fight.id || !fight.fighter_a_id || !fight.fighter_b_id) { skipped++; continue; }
    const a = fmap[fight.fighter_a_id] || { id: fight.fighter_a_id, name: fight.fighter_a_name };
    const b = fmap[fight.fighter_b_id] || { id: fight.fighter_b_id, name: fight.fighter_b_name };
    if (!a.name || !b.name) { skipped++; continue; }
    const event = evMap[fight.event_id] || null;

    const slug = previewSlug(a.name, b.name, fight.id);
    const filename = `${slug}.html`;
    keep.add(filename);

    const html = matchupPreview({
      fight,
      fighterA: a,
      fighterB: b,
      event,
      picks: picksByFight[fight.id] || [],
      cardioA: cardioMap[a.id] || null,
      cardioB: cardioMap[b.id] || null,
      finishA: finishMap[a.id] || null,
      finishB: finishMap[b.id] || null
    });

    if (writeIfChanged(path.join(PREVIEW_DIR, filename), html)) written++;
    urls.push(`/preview/${filename}`);
  }

  const removed = pruneStaleStubs(PREVIEW_DIR, keep);
  console.log(`Matchup previews: ${written} written, ${removed} pruned, ${skipped} skipped, ${urls.length} total.`);
  return urls;
}

// RSS feed of upcoming events. Aggregators (Feedly, IFTTT, Zapier triggers,
// fight forums that auto-share feed items) ingest this and surface CFL as a
// new "post" each time the next event flips over. Kept narrow and stable —
// one item per upcoming event, sorted soonest first.
function regenerateRssFeed(upcomingEvents) {
  const now = new Date().toUTCString();
  const items = (upcomingEvents || []).map(e => {
    const url = `${SITE}/event.html?id=${e.id}`;
    const pub = e.event_date ? new Date(e.event_date + 'T00:00:00Z').toUTCString() : now;
    const desc = `Full model verdicts and edge factors for every fight on the ${escapeXml(e.name)} card${e.location ? ' — ' + escapeXml(e.location) : ''}.`;
    return [
      '  <item>',
      `    <title>${escapeXml(e.name)}</title>`,
      `    <link>${url}</link>`,
      `    <guid isPermaLink="true">${url}</guid>`,
      `    <pubDate>${pub}</pubDate>`,
      `    <description>${desc}</description>`,
      '  </item>'
    ].join('\n');
  });

  const xml = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
    '<channel>',
    `  <title>Cannon Fight Lab — Upcoming UFC Cards</title>`,
    `  <link>${SITE}/</link>`,
    `  <atom:link href="${SITE}/feed.xml" rel="self" type="application/rss+xml" />`,
    `  <description>Model verdicts and edge factors for every upcoming UFC event, posted before fight night.</description>`,
    `  <language>en-us</language>`,
    `  <lastBuildDate>${now}</lastBuildDate>`,
    '',
    ...items,
    '',
    '</channel>',
    '</rss>',
    ''
  ].join('\n');

  fs.writeFileSync(path.join(ROOT, 'feed.xml'), xml);
  console.log(`RSS feed: ${items.length} items.`);
}

function escapeXml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

// Sitemap entries: static site pages + every fighter/event stub + every
// matchup preview. Big sites eventually want a sitemap index; for now a
// single sitemap is well under Google's 50k-URL limit.
function regenerateSitemap(fighterUrls, eventUrls, previewUrls) {
  const today = new Date().toISOString().slice(0, 10);

  const staticPages = [
    { loc: '/',                priority: '1.0', changefreq: 'daily' },
    { loc: '/card-lab.html',   priority: '0.9', changefreq: 'daily' },
    { loc: '/track-record.html', priority: '0.9', changefreq: 'weekly' },
    { loc: '/cardio.html',     priority: '0.9', changefreq: 'weekly' },
    { loc: '/stats.html',      priority: '0.9', changefreq: 'weekly' },
    { loc: '/fighters.html',   priority: '0.9', changefreq: 'daily' },
    { loc: '/h2h.html',        priority: '0.8', changefreq: 'weekly' },
    { loc: '/parlay.html',     priority: '0.7', changefreq: 'weekly' },
    { loc: '/fighter.html',    priority: '0.6', changefreq: 'daily' },
    { loc: '/event.html',      priority: '0.6', changefreq: 'daily' },
    { loc: '/edges.html',      priority: '0.7', changefreq: 'monthly' },
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
  // Matchup previews ride higher than fighter/event stubs — they're real
  // content pages (no redirect) and target high-intent commercial queries.
  for (const u of previewUrls) pushUrl(u, '0.8', 'daily');
  for (const u of eventUrls)   pushUrl(u, '0.6', 'weekly');
  for (const u of fighterUrls) pushUrl(u, '0.5', 'weekly');

  lines.push('</urlset>');
  lines.push('');

  fs.writeFileSync(path.join(ROOT, 'sitemap.xml'), lines.join('\n'));
  const total = staticPages.length + previewUrls.length + eventUrls.length + fighterUrls.length;
  console.log(`Sitemap: ${total} URLs.`);
}

(async () => {
  try {
    const fighterUrls = await prerenderFighters();
    const eventUrls = await prerenderEvents();
    const previewUrls = await prerenderMatchupPreviews();

    // RSS only emits upcoming events. We've already fetched them inside
    // prerenderMatchupPreviews but didn't keep the array around — re-fetching
    // is cheap (single query, no pagination needed for <20 upcoming events).
    const { data: upcomingForRss } = await sb
      .from('events')
      .select('id, name, event_date, location')
      .eq('is_upcoming', true)
      .order('event_date', { ascending: true });
    regenerateRssFeed(upcomingForRss || []);

    regenerateSitemap(fighterUrls, eventUrls, previewUrls);
    console.log('Done.');
  } catch (err) {
    console.error('Prerender failed:', err);
    process.exit(1);
  }
})();
