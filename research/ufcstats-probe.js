// =============================================================================
// research/ufcstats-probe.js — dump what ufcstats actually returns
// =============================================================================
// Both list pages came back HTTP 200 but only ~3KB with no event data. This
// version dumps the raw body + final URL for several host/scheme variants so we
// can see whether ufcstats is down, redirecting, or serving a placeholder.
// Read-only. Output → research/ufcstats-probe.md
// =============================================================================

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36';
const MACAU_HASH = '1e75e6c9de99fa76'; // event 113's stored ufc_url hash

const out = [];
const log = (s = '') => out.push(s);

async function dump(url) {
  log(`## GET ${url}`);
  try {
    const res = await fetch(url, { headers: { 'User-Agent': UA, 'Accept': 'text/html' }, redirect: 'follow' });
    const body = await res.text();
    log(`HTTP ${res.status} ${res.statusText}  final-url=${res.url}  bytes=${body.length}`);
    log('content-type: ' + (res.headers.get('content-type') || '?'));
    log('server: ' + (res.headers.get('server') || '?'));
    log('--- body (first 2500 chars) ---');
    log(body.slice(0, 2500));
    log('--- end body ---\n');
  } catch (e) {
    log(`ERROR: ${e.message}\n`);
  }
}

(async () => {
  log(`# ufcstats raw probe`);
  log(`Generated: ${new Date().toISOString()}\n`);

  await dump('http://www.ufcstats.com/statistics/events/completed');
  await dump('https://www.ufcstats.com/statistics/events/completed');
  await dump('https://ufcstats.com/statistics/events/completed');
  await dump('http://ufcstats.com/statistics/events/completed');
  await dump(`http://www.ufcstats.com/event-details/${MACAU_HASH}`);
  await dump(`https://www.ufcstats.com/event-details/${MACAU_HASH}`);

  const fs = require('fs');
  fs.writeFileSync('research/ufcstats-probe.md', out.join('\n') + '\n');
  process.stdout.write(out.join('\n') + '\n');
})().catch((e) => { console.error('probe failed:', e.message); process.exit(1); });
