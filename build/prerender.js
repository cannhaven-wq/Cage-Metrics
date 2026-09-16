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
const { eventPreview, cardSlug, consensusPick, cardOrder } = require('./event-preview-templates');
const hub = require('./hub-templates');
const fwData = require('./fight-week-data');
const core = require('../fight-week-core');

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SUPABASE_KEY = 'sb_publishable_boJGOA1CFN-SF14HHFGUAw_YEEm0DU8';
const SITE = 'https://cannonfightlab.com';

const ROOT = path.resolve(__dirname, '..');
const FIGHTERS_DIR = path.join(ROOT, 'f');
const EVENTS_DIR = path.join(ROOT, 'e');
const PREVIEW_DIR = path.join(ROOT, 'preview');
const CARD_DIR = path.join(ROOT, 'card');

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

  // Event Hubs. Any card with a locked pre-fight record gets a full page at
  // its /e/ URL — the current card's hub, and every past card's permanent
  // graded record. Everything else keeps the redirect stub. A hub URL is
  // never deleted or redirected once it exists: the record is the product.
  const withRecord = await fwData.eventsWithRecord(sb);
  const hubIds = new Set(withRecord.map(e => e.id));
  const factor = fwData.factorFinding(ROOT);
  const generatedAt = new Date().toISOString();
  const hubCards = {};   // event_id -> loaded card (reused by the fight pages)
  for (const e of withRecord) {
    try {
      hubCards[e.id] = await fwData.loadCard(sb, e);
    } catch (err) {
      console.warn(`[hub] card load failed for event ${e.id}: ${err.message}`);
    }
  }

  ensureDir(EVENTS_DIR);
  const keep = new Set();
  const urls = [];
  const hubUrls = [];
  let written = 0;
  let hubsWritten = 0;

  for (const e of events) {
    if (!e.id || !e.name) continue;
    const slug = slugify(e.name);
    const filename = `${slug}-${e.id}.html`;
    keep.add(filename);
    const card = hubIds.has(e.id) ? hubCards[e.id] : null;
    if (card && card.rows.length) {
      const html = hub.eventHub({ event: e, rows: card.rows, byBook: card.byBook, factor, generatedAt });
      if (writeIfChanged(path.join(EVENTS_DIR, filename), html)) hubsWritten++;
      hubUrls.push(`/e/${filename}`);
    } else {
      if (writeIfChanged(path.join(EVENTS_DIR, filename), eventStub(e, byEvent[e.id] || []))) written++;
      urls.push(`/e/${filename}`);
    }
  }
  const removed = pruneStaleStubs(EVENTS_DIR, keep);
  console.log(`Events: ${written} stubs written, ${hubsWritten} hubs written, ${removed} pruned, ${urls.length + hubUrls.length} total.`);

  const current = fwData.pickCurrent(withRecord);
  return { eventUrls: urls, hubUrls, hubCards, withRecord, current, generatedAt };
}

// Matchup previews: a real indexable preview page per fight on an upcoming
// card. Generated only for `is_upcoming=true` events so the directory stays
// small and we don't accidentally index post-fight previews that contradict
// the result. Past-event preview files are pruned each run.
async function prerenderMatchupPreviews(hubState) {
  // ---- fight pages for every card with a locked record (current + past) ----
  // Written first so the legacy preview generator below never overwrites
  // them; their filenames go into `hubKeep` so pruning leaves them alone.
  const hubKeep = new Set();
  const fightUrls = [];
  const currentFightUrls = [];
  let fightPagesWritten = 0;
  ensureDir(PREVIEW_DIR);
  for (const ev of (hubState.withRecord || [])) {
    const card = hubState.hubCards[ev.id];
    if (!card || !card.rows.length) continue;
    for (const r of card.rows) {
      if (!r.fighter_a_id || !r.fighter_b_id) continue;
      const filename = path.basename(core.fightPath(r));
      hubKeep.add(filename);
      const html = hub.fightPage({ event: ev, row: r, fighters: card.fighters, cardRows: card.rows, byBook: card.byBook, generatedAt: hubState.generatedAt });
      if (writeIfChanged(path.join(PREVIEW_DIR, filename), html)) fightPagesWritten++;
      const u = `/preview/${filename}`;
      fightUrls.push(u);
      if (hubState.current.event && hubState.current.event.id === ev.id) currentFightUrls.push(u);
    }
  }
  console.log(`Fight pages: ${fightPagesWritten} written, ${fightUrls.length} total (cards with a locked record).`);
  const hubEventIds = new Set(Object.keys(hubState.hubCards || {}).map(Number));

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
    ensureDir(CARD_DIR);
    const removed = pruneStaleStubs(PREVIEW_DIR, hubKeep);
    const removedCards = pruneStaleStubs(CARD_DIR, new Set());
    console.log(`Matchup previews: 0 written, ${removed} pruned. Card pages: 0 written, ${removedCards} pruned.`);
    return { previewUrls: [], cardUrls: [], fightUrls, currentFightUrls };
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
    ensureDir(CARD_DIR);
    const removed = pruneStaleStubs(PREVIEW_DIR, hubKeep);
    const removedCards = pruneStaleStubs(CARD_DIR, new Set());
    console.log(`Matchup previews: 0 written, ${removed} pruned. Card pages: 0 written, ${removedCards} pruned.`);
    return { previewUrls: [], cardUrls: [], fightUrls, currentFightUrls };
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

  const [fightersData, snapData, predsData, cardioData, finishData] = await Promise.all([
    safe(sb.from('fighters').select('id, name, nickname, wins, losses, draws, height_in, reach_in, stance, age, dob, slpm, td_avg, td_def, str_acc').in('id', fighterIds)),
    // Locked forecasts only. First choice is the immutable pre-fight snapshot
    // (pre_fight_snapshots: append-only, one row per fight, written the night
    // before the card). Until that exists, the insert-only live model_picks
    // row. Never a 'backtest' row and never a recompute at render time — a
    // preview page may only ever show what was already on the record.
    safe(sb.from('pre_fight_snapshots').select('fight_id, engine_pick_fighter_id, engine_p_cal, engine_tier, engine_model_version, snapshot_at').in('fight_id', fightIds)),
    safe(sb.from('model_picks').select('fight_id, pick_fighter_id, p_cal, tier, model_version, published_at, source').in('fight_id', fightIds).eq('source', 'live')),
    safe(sb.from('v_fighter_consistency').select('fighter_id, weight_class, cardio_tier').in('fighter_id', fighterIds)),
    safe(sb.from('v_fighter_finish_rate').select('fighter_id, total_fights, ko_tko_rate, sub_rate').in('fighter_id', fighterIds)),
  ]);

  const fmap = {};
  fightersData.forEach(f => { fmap[f.id] = f; });

  // picksByFight[fight_id] = [{ fighter_id, model_p, tier, locked, locked_at }]
  // Earliest snapshot wins (the table is append-only; a second row can only be
  // a late-booked re-run and is skipped by the snapshotter anyway).
  const lockedByFight = {};
  snapData.forEach(r => {
    if (r.engine_pick_fighter_id == null || r.engine_p_cal == null) return;
    const prev = lockedByFight[r.fight_id];
    if (prev && prev.locked === 'snapshot' && prev.locked_at <= r.snapshot_at) return;
    lockedByFight[r.fight_id] = { fighter_id: r.engine_pick_fighter_id, model_p: +r.engine_p_cal, tier: r.engine_tier || null, model_version: r.engine_model_version || null, locked: 'snapshot', locked_at: r.snapshot_at };
  });
  predsData.forEach(p => {
    if (lockedByFight[p.fight_id] && lockedByFight[p.fight_id].locked === 'snapshot') return;
    const prev = lockedByFight[p.fight_id];
    if (prev && prev.locked_at <= p.published_at) return;   // insert-only: first write stands
    lockedByFight[p.fight_id] = { fighter_id: p.pick_fighter_id, model_p: p.p_cal == null ? null : +p.p_cal, tier: p.tier || null, model_version: p.model_version || null, locked: 'live', locked_at: p.published_at };
  });
  const picksByFight = {};
  Object.entries(lockedByFight).forEach(([fid, p]) => { picksByFight[fid] = [p]; });

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

  // Rows accumulated per event for the event-level card pages. Each row reuses
  // the same fighter/pick data already assembled for the per-fight preview.
  const rowsByEvent = {};

  for (const fight of fights) {
    if (!fight.id || !fight.fighter_a_id || !fight.fighter_b_id) { skipped++; continue; }
    if (hubEventIds.has(fight.event_id)) continue;   // fight page already written above
    const a = fmap[fight.fighter_a_id] || { id: fight.fighter_a_id, name: fight.fighter_a_name };
    const b = fmap[fight.fighter_b_id] || { id: fight.fighter_b_id, name: fight.fighter_b_name };
    if (!a.name || !b.name) { skipped++; continue; }
    const event = evMap[fight.event_id] || null;

    const slug = previewSlug(a.name, b.name, fight.id);
    const filename = `${slug}.html`;
    keep.add(filename);

    const picks = picksByFight[fight.id] || [];
    const html = matchupPreview({
      fight,
      fighterA: a,
      fighterB: b,
      event,
      picks,
      cardioA: cardioMap[a.id] || null,
      cardioB: cardioMap[b.id] || null,
      finishA: finishMap[a.id] || null,
      finishB: finishMap[b.id] || null
    });

    if (writeIfChanged(path.join(PREVIEW_DIR, filename), html)) written++;
    urls.push(`/preview/${filename}`);

    if (event) {
      if (!rowsByEvent[event.id]) rowsByEvent[event.id] = [];
      rowsByEvent[event.id].push({
        fight,
        fighterA: a,
        fighterB: b,
        slug,
        pick: consensusPick(picks, a, b)
      });
    }
  }

  hubKeep.forEach(n => keep.add(n));
  const removed = pruneStaleStubs(PREVIEW_DIR, keep);
  console.log(`Matchup previews: ${written} written, ${removed} pruned, ${skipped} skipped, ${urls.length} total.`);

  // ---- event-level card-prediction pages ----
  ensureDir(CARD_DIR);
  const cardKeep = new Set();
  const cardUrls = [];
  let cardsWritten = 0;

  for (const ev of upcomingEvents) {
    const filename = `${cardSlug(ev.name, ev.id)}.html`;
    if (hubEventIds.has(ev.id)) {
      // The Event Hub at /e/ is the card page now; keep the old URL alive.
      cardKeep.add(filename);
      if (writeIfChanged(path.join(CARD_DIR, filename), hub.cardRedirect(ev))) cardsWritten++;
      continue;
    }
    const rows = (rowsByEvent[ev.id] || []).slice().sort((x, y) => cardOrder(x.fight, y.fight));
    if (!rows.length) continue;
    cardKeep.add(filename);
    const html = eventPreview({
      event: ev,
      rows,
      previewSlugFor: r => r.slug
    });
    if (writeIfChanged(path.join(CARD_DIR, filename), html)) cardsWritten++;
    cardUrls.push(`/card/${filename}`);
  }

  const cardsRemoved = pruneStaleStubs(CARD_DIR, cardKeep);
  console.log(`Card pages: ${cardsWritten} written, ${cardsRemoved} pruned, ${cardUrls.length} total.`);

  return { previewUrls: urls, cardUrls, fightUrls, currentFightUrls };
}

// RSS feed of upcoming events. Aggregators (Feedly, IFTTT, Zapier triggers,
// fight forums that auto-share feed items) ingest this and surface CFL as a
// new "post" each time the next event flips over. Kept narrow and stable —
// one item per upcoming event, sorted soonest first.
function regenerateRssFeed(upcomingEvents) {
  const now = new Date().toUTCString();
  const items = (upcomingEvents || []).map(e => {
    const url = `${SITE}${core.hubPath(e)}`;
    const pub = e.event_date ? new Date(e.event_date + 'T00:00:00Z').toUTCString() : now;
    const desc = `CFL's locked model forecast beside the vig-free market number for every fight on the ${escapeXml(e.name)} card${e.location ? ' — ' + escapeXml(e.location) : ''}. Predictions locked before results.`;
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
    `  <description>Locked model forecasts and vig-free market analysis for every upcoming UFC event, posted before fight night.</description>`,
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
function regenerateSitemap(fighterUrls, eventUrls, previewUrls, cardUrls, hubState) {
  const today = new Date().toISOString().slice(0, 10);
  const current = hubState && hubState.current && hubState.current.event;
  const currentHub = current ? core.hubPath(current) : null;
  const currentFights = new Set((hubState && hubState.currentFightUrls) || []);

  const staticPages = [
    { loc: '/',                priority: '1.0', changefreq: 'daily' },
    { loc: '/market-board.html', priority: '0.9', changefreq: 'hourly' },
    { loc: '/methodology.html', priority: '0.7', changefreq: 'monthly' },
    { loc: '/props.html',      priority: '0.8', changefreq: 'daily' },
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
  // The current Event Hub and its fight pages are the product: top of the
  // sitemap, refreshed hourly. Past hubs are the permanent graded record.
  if (currentHub) pushUrl(currentHub, '1.0', 'hourly');
  for (const u of currentFights) pushUrl(u, '0.9', 'hourly');
  for (const u of ((hubState && hubState.hubUrls) || [])) if (u !== currentHub) pushUrl(u, '0.8', 'weekly');
  for (const u of ((hubState && hubState.fightUrls) || [])) if (!currentFights.has(u)) pushUrl(u, '0.6', 'weekly');
  // Legacy event-level card pages (cards with no locked record yet).
  for (const u of (cardUrls || [])) pushUrl(u, '0.9', 'daily');
  // Matchup previews ride higher than fighter/event stubs — they're real
  // content pages (no redirect) and target high-intent commercial queries.
  for (const u of previewUrls) pushUrl(u, '0.8', 'daily');
  for (const u of eventUrls)   pushUrl(u, '0.6', 'weekly');
  for (const u of fighterUrls) pushUrl(u, '0.5', 'weekly');

  lines.push('</urlset>');
  lines.push('');

  fs.writeFileSync(path.join(ROOT, 'sitemap.xml'), lines.join('\n'));
  const hubCount = ((hubState && hubState.hubUrls) || []).length + ((hubState && hubState.fightUrls) || []).length;
  const total = staticPages.length + hubCount + (cardUrls || []).length + previewUrls.length + eventUrls.length + fighterUrls.length;
  console.log(`Sitemap: ${total} URLs.`);
}

(async () => {
  try {
    const fighterUrls = await prerenderFighters();
    const hubState = await prerenderEvents();
    const eventUrls = hubState.eventUrls;
    const { previewUrls, cardUrls, fightUrls, currentFightUrls } = await prerenderMatchupPreviews(hubState);
    hubState.fightUrls = fightUrls;
    hubState.currentFightUrls = currentFightUrls;

    // RSS only emits upcoming events. We've already fetched them inside
    // prerenderMatchupPreviews but didn't keep the array around — re-fetching
    // is cheap (single query, no pagination needed for <20 upcoming events).
    const { data: upcomingForRss } = await sb
      .from('events')
      .select('id, name, event_date, location')
      .eq('is_upcoming', true)
      .order('event_date', { ascending: true });
    regenerateRssFeed(upcomingForRss || []);

    regenerateSitemap(fighterUrls, eventUrls, previewUrls, cardUrls, hubState);
    console.log('Done.');
  } catch (err) {
    console.error('Prerender failed:', err);
    process.exit(1);
  }
})();
