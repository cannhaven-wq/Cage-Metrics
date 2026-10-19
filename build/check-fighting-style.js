// =============================================================================
// check-fighting-style.js — each fighter's discipline, as the UFC lists it
// =============================================================================
// PLAIN ENGLISH: once a day, open the UFC.com athlete page of every fighter on
// the next two weeks of cards (plus a batch of other active fighters we have
// not looked up yet) and copy the "Fighting style" field — "Boxer",
// "Kickboxer", "Wrestling", "Brazilian Jiu-Jitsu" — into
// fighters.fighting_style. Fight Lab and the fighter page show it.
//
// WHY (owner, 2026-10-16, T-102): the site used to CALCULATE a style from
// round one of the last five fights. It called Joaquin Buckley a grappler,
// because being held down by Brady and Usman dragged his striking numbers to
// nothing. The owner wants the discipline as the fighter is introduced, and
// UFC.com's athlete page is the published source for that.
//
// THE RULES:
//   - Copied, never calculated or guessed. No style on the page, no page, or a
//     page that is not this fighter → the value stays NULL and the page shows
//     nothing.
//   - A value a person set (fighting_style_src = 'manual') is never touched.
//   - A UFC.com value, once found, is not looked up again: disciplines do not
//     change week to week. A miss is retried after RETRY_DAYS.
//   - The page must name the fighter we asked about. The URL is built from the
//     name, and two fighters can share a name; a page whose heading is a
//     different person is a miss, not a match.
//   - "I could not look" is a failure: missing key, failed database read,
//     UFC.com blocking every request — non-zero exit. One fighter's 404 is
//     just a miss.
//   - A page with NO bio section is not "no style listed" — it is a page we
//     could not read (UFC.com served the run on 2026-10-19 00:30 exactly that,
//     for every fighter, five minutes after the same pages read fine). Such a
//     fighter is not stamped as checked, and a run where most pages come back
//     like that stops and fails rather than carrying on.
//
// Env:
//   SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SECRET_KEY)  required
//   STYLE_LOOKAHEAD_DAYS  default 14
//   STYLE_RECENT_DAYS     also everyone who fought on a card in this many past days, default 120
//                         (read from `fights`, because fighters.last_fight_date
//                         is NULL for many active fighters: Buckley and Malott
//                         were missed on 2026-10-19 for exactly that reason)
//   STYLE_BACKFILL        how many other recently active fighters to try per run, default 60
//   STYLE_DRY_RUN         '1' = look and report, write nothing
// =============================================================================
'use strict';

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const UFC = 'https://www.ufc.com/athlete/';
const RETRY_DAYS = 30;
const PAUSE_MS = 700;   // be a polite visitor

// ---------------------------------------------------------------- pure logic

// "Joaquin Buckley" -> "joaquin-buckley"; accents dropped, apostrophes and
// dots removed, anything else non-alphanumeric becomes a hyphen. This is how
// UFC.com builds athlete URLs.
function ufcSlug(name) {
  return String(name || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
    .toLowerCase().replace(/['’.]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

function decodeEntities(s) {
  return String(s).replace(/&amp;/g, '&').replace(/&#0?39;|&apos;|&#x27;/g, "'").replace(/&quot;/g, '"')
    .replace(/&nbsp;/g, ' ').replace(/&#(\d+);/g, (_, n) => String.fromCharCode(+n));
}
const squash = s => decodeEntities(s).replace(/\s+/g, ' ').trim();

// The "Fighting style" value from an athlete page, or null. UFC.com prints
// bio fields as a label element followed by a text element; the label match
// is exact, so "Fighting style" never picks up another field's value.
function parseFightingStyle(html) {
  const re = /class="[^"]*c-bio__label[^"]*"[^>]*>\s*([\s\S]*?)\s*<\/[a-z]+>\s*<[a-z]+[^>]*class="[^"]*c-bio__text[^"]*"[^>]*>([\s\S]*?)<\/[a-z]+>/gi;
  let m;
  while ((m = re.exec(String(html || '')))) {
    if (/^fighting style$/i.test(squash(m[1].replace(/<[^>]+>/g, '')))) {
      const v = squash(m[2].replace(/<[^>]+>/g, ''));
      return v || null;
    }
  }
  return null;
}

// Does the page carry UFC.com's bio block at all? Without it, "no style" would
// be a guess about a page we did not see.
function hasBio(html) {
  return /c-bio__label/i.test(String(html || ''));
}

// The fighter's name as the page heads it, or null.
function parsePageName(html) {
  const h = /class="[^"]*hero-profile__name[^"]*"[^>]*>([\s\S]*?)<\//i.exec(String(html || ''));
  if (h) return squash(h[1].replace(/<[^>]+>/g, '')) || null;
  const t = /<title>([\s\S]*?)<\/title>/i.exec(String(html || ''));
  return t ? squash(t[1]).replace(/\s*\|.*$/, '').trim() || null : null;
}

const sameName = (a, b) => ufcSlug(a) === ufcSlug(b);

// What to do with one fighter, given what the page said.
function decide(fighter, page) {
  if (fighter.fighting_style_src === 'manual') return { action: 'skip' };
  if (!page || page.status === 'not_found') return { action: 'not_found' };
  if (page.name && !sameName(page.name, fighter.name)) return { action: 'wrong_person', pageName: page.name };
  if (!page.style && page.bio === false) return { action: 'unreadable' };
  if (!page.style) return { action: 'no_style' };
  return { action: 'fill', style: page.style };
}

// Fighters worth looking up: never looked up, or a miss older than RETRY_DAYS.
// A found UFC.com value and a manual value are settled.
function needsLookup(f, now) {
  if (f.fighting_style_src === 'manual') return false;
  if (f.fighting_style) return false;
  if (!f.fighting_style_checked_at) return true;
  return (now - Date.parse(f.fighting_style_checked_at)) > RETRY_DAYS * 86400000;
}

// ---------------------------------------------------------------- plumbing

async function rest(key, path, init) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, Object.assign({}, init, {
    headers: Object.assign({ apikey: key, Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' }, (init && init.headers) || {}),
  }));
  if (!res.ok) throw new Error(`${init && init.method || 'GET'} ${path.split('?')[0]} -> HTTP ${res.status}: ${(await res.text()).slice(0, 300)}`);
  return res.status === 204 ? null : res.json();
}

async function fetchPage(name) {
  const url = UFC + ufcSlug(name);
  for (let attempt = 0; attempt < 3; attempt++) {
    if (attempt) await new Promise(r => setTimeout(r, 5000 * attempt));
    const res = await fetch(url, { headers: {
      'User-Agent': 'Mozilla/5.0 (compatible; CannonFightLab-style-check/1.1; +https://cannonfightlab.com)',
      Accept: 'text/html,application/xhtml+xml', 'Accept-Language': 'en-US,en;q=0.9' }, redirect: 'follow' });
    if (res.status === 404) return { status: 'not_found', url };
    if (res.status === 429 || res.status >= 500) continue;
    if (!res.ok) throw new Error(`UFC.com ${url} -> HTTP ${res.status}`);
    const html = await res.text();
    return { status: 'ok', url, name: parsePageName(html), style: parseFightingStyle(html), bio: hasBio(html),
      bytes: html.length, mentionsStyle: /fighting style/i.test(html) };
  }
  throw new Error(`UFC.com ${url} kept failing`);
}

async function main() {
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SECRET_KEY;
  if (!key) { console.error('SUPABASE_SERVICE_ROLE_KEY is not set: could not look, so this run says nothing.'); process.exit(2); }
  const days = Math.max(1, +process.env.STYLE_LOOKAHEAD_DAYS || 14);
  const recent = Math.max(0, process.env.STYLE_RECENT_DAYS == null ? 120 : +process.env.STYLE_RECENT_DAYS || 0);
  const backfill = Math.max(0, process.env.STYLE_BACKFILL == null ? 60 : +process.env.STYLE_BACKFILL || 0);
  const dry = process.env.STYLE_DRY_RUN === '1';
  const now = Date.now();
  const iso = d => new Date(d).toISOString().slice(0, 10);
  const cols = 'id,name,fighting_style,fighting_style_src,fighting_style_checked_at';

  // 1. Everyone on the next cards, and everyone on the cards of the last
  //    `recent` days.
  const events = await rest(key, `events?select=id&event_date=gte.${iso(now - Math.max(1, recent) * 86400000)}&event_date=lte.${iso(now + days * 86400000)}`);
  const fights = events.length
    ? await rest(key, `fights?select=fighter_a_id,fighter_b_id&event_id=in.(${events.map(e => e.id).join(',')})&is_active=not.is.false`)
    : [];
  const ids = [...new Set(fights.flatMap(f => [f.fighter_a_id, f.fighter_b_id]).filter(x => x != null))];
  const onCard = [];
  for (let i = 0; i < ids.length; i += 150) {   // keep the URL short
    onCard.push(...await rest(key, `fighters?select=${cols}&id=in.(${ids.slice(i, i + 150).join(',')})`));
  }

  // 2. A batch of other recently active fighters nobody has looked up yet.
  const extra = backfill
    ? await rest(key, `fighters?select=${cols}&fighting_style_src=is.null&fighting_style_checked_at=is.null&last_fight_date=not.is.null&order=last_fight_date.desc&limit=${backfill}`)
    : [];

  const seen = new Set();
  const todo = onCard.concat(extra).filter(f => !seen.has(f.id) && seen.add(f.id) && needsLookup(f, now));

  const results = [];
  let failures = 0, unreadable = 0;
  const writes = [];
  for (const f of todo) {
    let page;
    try { page = await fetchPage(f.name); }
    catch (e) { failures += 1; console.log(`  error     ${f.name} — ${e.message}`); continue; }
    const d = decide(f, page);
    results.push(Object.assign({ id: f.id, name: f.name, url: page.url }, d));
    if (d.action === 'unreadable') {
      unreadable += 1;
      if (unreadable === 1) console.log(`  first unreadable page: ${page.url} — ${page.bytes} bytes, heading "${page.name || ''}", ` +
        `mentions "Fighting style": ${page.mentionsStyle}`);
      // Mostly unreadable means the site is serving us something else: stop.
      if (unreadable >= 10 && unreadable > results.length / 2) {
        console.error(`${unreadable} of ${results.length} pages came back without a bio section. Stopping; nothing more written.`);
        process.exit(1);
      }
      continue;   // not stamped: we did not see the page
    }
    // Written at the end, after the run has passed its own sanity checks.
    writes.push({ id: f.id, body: d.action === 'fill'
      ? { fighting_style: d.style, fighting_style_src: 'ufc.com', fighting_style_checked_at: new Date().toISOString() }
      : { fighting_style_checked_at: new Date().toISOString() } });
    await new Promise(r => setTimeout(r, PAUSE_MS));
  }

  // A run that read many pages and found not one style is far likelier to be
  // UFC.com serving a different page than every fighter having none (the
  // 2026-10-19 00:30 run: 0 of 342, after 39 of 50 five minutes earlier).
  // Counted over first-time lookups only: a month's retries of fighters whose
  // page lists no style can legitimately all come back empty.
  const fresh = new Set(todo.filter(f => !f.fighting_style_checked_at).map(f => f.id));
  const firstTime = results.filter(r => fresh.has(r.id));
  const fills = firstTime.filter(r => r.action === 'fill').length;
  if (firstTime.length >= 20 && fills === 0) {
    console.error(`${firstTime.length} first-time pages read and not one fighting style found — treating this as a page we could not read. Nothing written.`);
    process.exit(1);
  }
  if (!dry) {
    for (const w of writes) {
      // Never over a person's value, even if one landed while this ran.
      await rest(key, `fighters?id=eq.${w.id}&or=(fighting_style_src.is.null,fighting_style_src.neq.manual)`,
        { method: 'PATCH', headers: { Prefer: 'return=minimal' }, body: JSON.stringify(w.body) });
    }
  }

  // Every request failing means UFC.com is blocking or down: that is "could
  // not look", not "nothing to do".
  if (todo.length && failures === todo.length) {
    console.error(`UFC.com refused all ${failures} lookups. Nothing written.`);
    process.exit(1);
  }
  const count = a => results.filter(r => r.action === a).length;
  console.log(`${onCard.length} fighters on ${events.length} card(s), ${extra.length} backfill candidates; looked up ${todo.length}.` +
    ` filled ${count('fill')}, no style listed ${count('no_style')}, page not found ${count('not_found')},` +
    ` different person ${count('wrong_person')}, unreadable ${unreadable}, errors ${failures}${dry ? ' (dry run — nothing written)' : ''}.`);
  results.forEach(r => console.log(`  ${r.action.padEnd(12)} ${r.name}${r.style ? ' — ' + r.style : ''}${r.pageName ? ' — page is ' + r.pageName : ''}`));
}

module.exports = { ufcSlug, parseFightingStyle, parsePageName, hasBio, decide, needsLookup, RETRY_DAYS };

if (require.main === module) {
  main().catch(err => { console.error('Fighting-style check could not finish: ' + err.message); process.exit(1); });
}
