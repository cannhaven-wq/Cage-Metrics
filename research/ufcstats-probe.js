// =============================================================================
// research/ufcstats-probe.js — diagnose the broken event scraper
// =============================================================================
// The Railway scraper logs "Found 0 upcoming events" and upserts events with a
// null name — classic signature of a broken HTML parser (ufcstats markup change
// or a bot-block page). This probe runs on a GitHub runner (open internet) and
// reports what ufcstats is ACTUALLY serving, so we can tell which it is and
// pull the real Macau results + correct event hash.
//
// Read-only: fetches public ufcstats pages + reads event 113's ufc_url from
// Supabase (anon key). No writes. Output → research/ufcstats-probe.md
// =============================================================================

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SUPABASE_KEY = 'sb_publishable_boJGOA1CFN-SF14HHFGUAw_YEEm0DU8';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36';

const out = [];
const log = (s = '') => out.push(s);

async function getText(url) {
  const res = await fetch(url, { headers: { 'User-Agent': UA, 'Accept': 'text/html' } });
  const body = await res.text();
  return { status: res.status, len: body.length, body };
}

// Crude tag-strip to readable text.
const strip = (html) =>
  html.replace(/<script[\s\S]*?<\/script>/gi, '')
      .replace(/<style[\s\S]*?<\/style>/gi, '')
      .replace(/<[^>]+>/g, ' ')
      .replace(/&nbsp;/g, ' ')
      .replace(/[ \t]+/g, ' ')
      .replace(/\n\s*\n+/g, '\n')
      .trim();

(async () => {
  log(`# ufcstats probe`);
  log(`Generated: ${new Date().toISOString()}\n`);

  // (0) event 113's stored source URL
  try {
    const ev = await fetch(`${SUPABASE_URL}/rest/v1/events?id=eq.113&select=id,name,event_date,is_upcoming,ufc_url`,
      { headers: { apikey: SUPABASE_KEY, Authorization: `Bearer ${SUPABASE_KEY}` } }).then(r => r.json());
    log(`## Supabase event 113`);
    log(JSON.stringify(ev, null, 2));
    log('');
  } catch (e) { log(`## Supabase event 113: ERROR ${e.message}\n`); }

  // (1) upcoming list — the page Phase 1 reads
  for (const url of [
    'http://www.ufcstats.com/statistics/events/upcoming',
    'http://www.ufcstats.com/statistics/events/completed?page=1',
  ]) {
    try {
      const { status, len, body } = await getText(url);
      log(`## GET ${url}`);
      log(`HTTP ${status}, ${len} bytes`);
      // event links + their visible text
      const links = [...body.matchAll(/href="(http:\/\/www\.ufcstats\.com\/event-details\/[a-f0-9]+)"[^>]*>([\s\S]*?)<\/a>/gi)]
        .map(m => `${m[1]}  =>  ${strip(m[2])}`);
      log(`event-details links found: ${links.length}`);
      log(links.slice(0, 12).join('\n'));
      // does the markup the parser keys on still exist?
      log(`contains 'b-statistics__table-row': ${body.includes('b-statistics__table-row')}`);
      log(`contains 'b-link_style_black': ${body.includes('b-link_style_black')}`);
      log(`looks like a block/challenge page: ${/captcha|cloudflare|access denied|just a moment/i.test(body)}`);
      log('');
    } catch (e) { log(`## GET ${url}: ERROR ${e.message}\n`); }
  }

  // (2) the Macau event page — find it in the completed list by name/date
  try {
    const { body } = await getText('http://www.ufcstats.com/statistics/events/completed?page=1');
    const rows = [...body.matchAll(/href="(http:\/\/www\.ufcstats\.com\/event-details\/[a-f0-9]+)"[^>]*>([\s\S]*?)<\/a>/gi)];
    const macau = rows.find(m => /song|figueiredo/i.test(strip(m[2])));
    if (macau) {
      log(`## Macau event link: ${macau[1]}  (${strip(macau[2])})`);
      const { status, len, body: ev } = await getText(macau[1]);
      log(`HTTP ${status}, ${len} bytes`);
      // Fight rows: each person link + the win/loss/draw/nc flag text near it.
      const names = [...ev.matchAll(/b-link_style_black"[^>]*>\s*([\s\S]*?)<\/a>/gi)].map(m => strip(m[1]));
      const flags = [...ev.matchAll(/b-flag__text">\s*([\s\S]*?)<\/i>/gi)].map(m => strip(m[1]));
      log(`fighter-name links: ${names.length}, result flags: ${flags.length}`);
      log(`names: ${JSON.stringify(names.slice(0, 30))}`);
      log(`flags: ${JSON.stringify(flags.slice(0, 30))}`);
    } else {
      log(`## Macau event not found in completed page 1 (parser may be matching nothing, or ufcstats hasn't posted it).`);
    }
  } catch (e) { log(`## Macau page probe: ERROR ${e.message}`); }

  const fs = require('fs');
  fs.writeFileSync('research/ufcstats-probe.md', out.join('\n') + '\n');
  process.stdout.write(out.join('\n') + '\n');
})().catch((e) => { console.error('probe failed:', e.message); process.exit(1); });
