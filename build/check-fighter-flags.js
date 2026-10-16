// =============================================================================
// check-fighter-flags.js — the right flag for every fighter on the next cards
// =============================================================================
// PLAIN ENGLISH: once a day, look at every fighter booked in the next couple of
// weeks and ask Wikidata which country they compete for. Fill in a missing
// flag, quietly confirm one that agrees, and list anything that disagrees so a
// person can decide. It never overwrites a flag that is already there.
//
// THE RULE (owner, 2026-10-16): a fighter's flag is the country they REPRESENT,
// not where they were born. Wikidata has a property for exactly that —
// "country for sport" (P1532). Citizenship (P27) is the fallback, and only
// when there is exactly one; a dual citizen with no sporting country is a
// question for a person, not a guess.
//
// WHY ONLY UPCOMING CARDS: the people a visitor actually sees are the ones on
// the next cards. Checking them a few days ahead catches a wrong flag before it
// is on screen, and over time the active roster cleans itself. A fighter who
// has been settled once is never looked up again.
//
// WHAT "SETTLED" MEANS, carried in fighters.country_src:
//   manual               a person set it. Never touched.
//   ufc.com+wikidata     the UFC.com flag and Wikidata agree.
//   wikidata:sport       filled by this job from "country for sport".
//   wikidata:citizenship filled by this job from a single citizenship.
// Anything else (ufc.com, the older 'wikidata' backfill, null) is checked.
//
// WHY A DISAGREEMENT IS NEVER WRITTEN: Wikidata is wrong sometimes too, and the
// one bad flag we found (Mike Malott) was a source being confidently wrong.
// Replacing one source's error with another's would be the same mistake with a
// different logo. So a disagreement goes to a GitHub issue with both answers
// and the links, and stays there until somebody sets it by hand.
//
// NAME MATCHING is exact, on English label or alias, restricted to people whose
// occupation is mixed martial artist. More than one match is "ambiguous", none
// is "not found" — both are listed for a person, neither is guessed. Accented
// names our data spells without accents will often not match; that costs a
// manual lookup, never a wrong flag.
//
// "I COULD NOT LOOK" IS A FAILURE: missing key, failed read, Wikidata down —
// non-zero exit, nothing written. A silent run must mean "nothing to do".
//
// Env:
//   SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SECRET_KEY)  required
//   FLAG_LOOKAHEAD_DAYS   default 14
//   FLAG_DRY_RUN          '1' = decide and report, write nothing
//   FLAG_JSON_OUT         path for the report the issue step reads
// =============================================================================
'use strict';

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const WDQS = 'https://query.wikidata.org/sparql';
const MMA_FIGHTER = 'Q11607585';   // occupation: mixed martial artist

const SETTLED = new Set(['manual', 'ufc.com+wikidata', 'wikidata:sport', 'wikidata:citizenship']);

// Wikidata's "country for sport" for British fighters is often a home nation,
// which has no ISO 3166-1 code of its own. The site flies one flag for the UK.
const HOME_NATIONS = { Q21: 'GB', Q22: 'GB', Q25: 'GB', Q26: 'GB' };

// ---------------------------------------------------------------- pure logic

// One fighter's Wikidata rows -> { status, code, label, via, qids }.
// rows: [{ qid, sportQid, sportCode, sportLabel, citQid, citCode, citLabel }]
function representedCountry(rows) {
  const people = [...new Set(rows.map(r => r.qid))];
  if (people.length === 0) return { status: 'not_found', qids: [] };
  if (people.length > 1) return { status: 'ambiguous', qids: people };

  const codeOf = (qid, code) => code || HOME_NATIONS[qid] || null;
  const uniq = (key, codeKey, labelKey) => {
    const m = new Map();
    rows.forEach(r => { if (r[key]) m.set(r[key], { code: codeOf(r[key], r[codeKey]), label: r[labelKey] }); });
    return [...m.values()];
  };
  const sport = uniq('sportQid', 'sportCode', 'sportLabel');
  const cit = uniq('citQid', 'citCode', 'citLabel');
  const sportCodes = [...new Set(sport.map(s => s.code).filter(Boolean))];
  const citCodes = [...new Set(cit.map(s => s.code).filter(Boolean))];

  if (sportCodes.length === 1) {
    return { status: 'found', code: sportCodes[0], label: sport.find(s => s.code === sportCodes[0]).label, via: 'sport', qids: people };
  }
  if (sportCodes.length > 1) return { status: 'ambiguous', qids: people, note: 'more than one country for sport: ' + sportCodes.join(', ') };
  if (citCodes.length === 1) {
    return { status: 'found', code: citCodes[0], label: cit.find(s => s.code === citCodes[0]).label, via: 'citizenship', qids: people };
  }
  if (citCodes.length > 1) return { status: 'ambiguous', qids: people, note: 'several citizenships and no country for sport: ' + citCodes.join(', ') };
  return { status: 'no_country', qids: people };
}

// What to do with one fighter. Never returns a write that replaces a flag.
function decide(fighter, wd) {
  if (SETTLED.has(fighter.country_src)) return { action: 'skip' };
  if (!wd || wd.status === 'not_found') return { action: 'not_found' };
  if (wd.status === 'ambiguous') return { action: 'ambiguous', note: wd.note || 'more than one Wikidata person with this name', qids: wd.qids };
  if (wd.status === 'no_country') return { action: 'not_found', note: 'on Wikidata but with no country', qids: wd.qids };

  const have = (fighter.country_code || '').toUpperCase();
  if (!have) {
    return { action: 'fill', code: wd.code, label: wd.label, src: 'wikidata:' + wd.via, qids: wd.qids };
  }
  if (have === wd.code) return { action: 'confirm', src: 'ufc.com+wikidata', qids: wd.qids };
  return { action: 'disagree', have, want: wd.code, wantLabel: wd.label, via: wd.via, qids: wd.qids };
}

function sparqlFor(names) {
  const lit = s => '"' + String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"@en';
  return `SELECT ?name ?p ?sport ?sportCode ?sportLabel ?cit ?citCode ?citLabel WHERE {
  VALUES ?name { ${names.map(lit).join(' ')} }
  ?p rdfs:label|skos:altLabel ?name .
  ?p wdt:P106 wd:${MMA_FIGHTER} .
  OPTIONAL { ?p wdt:P1532 ?sport . OPTIONAL { ?sport wdt:P297 ?sportCode . } ?sport rdfs:label ?sportLabel . FILTER(LANG(?sportLabel) = "en") }
  OPTIONAL { ?p wdt:P27 ?cit . OPTIONAL { ?cit wdt:P297 ?citCode . } ?cit rdfs:label ?citLabel . FILTER(LANG(?citLabel) = "en") }
}`;
}

// SPARQL JSON -> Map(name -> rows in representedCountry's shape)
function groupBindings(json) {
  const qid = u => u ? String(u).split('/').pop() : null;
  const out = new Map();
  ((json && json.results && json.results.bindings) || []).forEach(b => {
    const name = b.name && b.name.value;
    if (!name) return;
    const row = {
      qid: qid(b.p && b.p.value),
      sportQid: qid(b.sport && b.sport.value), sportCode: b.sportCode && b.sportCode.value, sportLabel: b.sportLabel && b.sportLabel.value,
      citQid: qid(b.cit && b.cit.value), citCode: b.citCode && b.citCode.value, citLabel: b.citLabel && b.citLabel.value,
    };
    (out.get(name) || out.set(name, []).get(name)).push(row);
  });
  return out;
}

// ---------------------------------------------------------------- plumbing

async function rest(key, path, init) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, Object.assign({}, init, {
    headers: Object.assign({ apikey: key, Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' }, (init && init.headers) || {}),
  }));
  if (!res.ok) throw new Error(`${init && init.method || 'GET'} ${path.split('?')[0]} -> HTTP ${res.status}: ${(await res.text()).slice(0, 300)}`);
  return res.status === 204 ? null : res.json();
}

// The public query service has short outages (a 502 on the first real run,
// 2026-10-16). A server error or a rate limit is retried with a pause; anything
// else, or a fourth failure, still fails the run and writes nothing.
async function wikidata(names, waitMs) {
  const pause = waitMs == null ? 15000 : waitMs;
  let last;
  for (let attempt = 0; attempt < 4; attempt++) {
    if (attempt) await new Promise(r => setTimeout(r, pause * attempt));
    try { return await wikidataOnce(names); }
    catch (e) { last = e; if (!/HTTP (429|5\d\d)|fetch failed|ECONNRESET|ETIMEDOUT/.test(e.message)) throw e; }
  }
  throw last;
}

async function wikidataOnce(names) {
  const res = await fetch(WDQS, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Accept: 'application/sparql-results+json',
      'User-Agent': 'CannonFightLab-flag-check/1.0 (https://cannonfightlab.com)',
    },
    body: 'query=' + encodeURIComponent(sparqlFor(names)),
  });
  if (!res.ok) throw new Error(`Wikidata -> HTTP ${res.status}: ${(await res.text()).slice(0, 300)}`);
  return groupBindings(await res.json());
}

async function main() {
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SECRET_KEY;
  if (!key) { console.error('SUPABASE_SERVICE_ROLE_KEY is not set: could not look, so this run says nothing.'); process.exit(2); }
  const days = Math.max(1, +process.env.FLAG_LOOKAHEAD_DAYS || 14);
  const dry = process.env.FLAG_DRY_RUN === '1';

  const today = new Date();
  const iso = d => d.toISOString().slice(0, 10);
  const until = new Date(today.getTime() + days * 86400000);
  const events = await rest(key, `events?select=id,name,event_date&event_date=gte.${iso(new Date(today.getTime() - 86400000))}&event_date=lte.${iso(until)}&order=event_date`);
  if (!events.length) { console.log(`No card in the next ${days} days. Nothing to check.`); return write({ now: today.toISOString(), events: [], results: [] }); }

  const fights = await rest(key, `fights?select=event_id,fighter_a_id,fighter_b_id&event_id=in.(${events.map(e => e.id).join(',')})&is_active=not.is.false`);
  const cardOf = new Map();
  fights.forEach(f => [f.fighter_a_id, f.fighter_b_id].forEach(id => {
    if (id != null && !cardOf.has(id)) cardOf.set(id, events.find(e => e.id === f.event_id));
  }));
  const ids = [...cardOf.keys()];
  const fighters = ids.length
    ? await rest(key, `fighters?select=id,name,country,country_code,country_src&id=in.(${ids.join(',')})`)
    : [];

  const todo = fighters.filter(f => !SETTLED.has(f.country_src));
  const wd = todo.length ? await wikidata([...new Set(todo.map(f => f.name))]) : new Map();

  // Use the country name the site already uses for a code ("China", not
  // Wikidata's "People's Republic of China"), so one flag never carries two
  // spellings. Wikidata's label is only used for a country we have never had.
  const decisions = fighters.map(f => [f, decide(f, representedCountry(wd.get(f.name) || []))]);
  const fillCodes = [...new Set(decisions.filter(([, d]) => d.action === 'fill').map(([, d]) => d.code))];
  const knownName = new Map();
  if (fillCodes.length) {
    const named = await rest(key, `fighters?select=country_code,country&country_code=in.(${fillCodes.join(',')})&country=not.is.null&limit=2000`);
    named.forEach(r => { if (!knownName.has(r.country_code)) knownName.set(r.country_code, r.country); });
  }

  const results = [];
  for (const [f, d0] of decisions) {
    const d = d0.action === 'fill' && knownName.has(d0.code) ? Object.assign({}, d0, { label: knownName.get(d0.code) }) : d0;
    if (d.action === 'skip') continue;
    const ev = cardOf.get(f.id);
    results.push(Object.assign({ id: f.id, name: f.name, have: f.country_code || null, haveLabel: f.country || null,
      card: ev ? ev.name : null, date: ev ? ev.event_date : null }, d));
    if (dry) continue;
    const stamp = new Date().toISOString();
    if (d.action === 'fill') {
      await rest(key, `fighters?id=eq.${f.id}&country_code=is.null`, { method: 'PATCH', headers: { Prefer: 'return=minimal' },
        body: JSON.stringify({ country: d.label, country_code: d.code, country_src: d.src, country_checked_at: stamp }) });
    } else if (d.action === 'confirm') {
      await rest(key, `fighters?id=eq.${f.id}`, { method: 'PATCH', headers: { Prefer: 'return=minimal' },
        body: JSON.stringify({ country_src: d.src, country_checked_at: stamp }) });
    } else {
      // disagree / ambiguous / not_found: record that we looked, change nothing else.
      await rest(key, `fighters?id=eq.${f.id}`, { method: 'PATCH', headers: { Prefer: 'return=minimal' },
        body: JSON.stringify({ country_checked_at: stamp }) });
    }
  }

  const count = a => results.filter(r => r.action === a).length;
  console.log(`${fighters.length} fighters on ${events.length} card(s); ${fighters.length - results.length} already settled.` +
    ` filled ${count('fill')}, confirmed ${count('confirm')}, disagree ${count('disagree')},` +
    ` ambiguous ${count('ambiguous')}, not found ${count('not_found')}${dry ? ' (dry run — nothing written)' : ''}.`);
  results.filter(r => r.action !== 'confirm').forEach(r =>
    console.log(`  ${r.action.padEnd(9)} ${r.name} — have ${r.have || 'none'}${r.want ? ', Wikidata ' + r.want : r.code ? ', set ' + r.code : ''}`));
  write({ now: today.toISOString(), dry, events, results });
}

function write(report) {
  if (process.env.FLAG_JSON_OUT) require('fs').writeFileSync(process.env.FLAG_JSON_OUT, JSON.stringify(report, null, 2));
}

module.exports = { representedCountry, decide, sparqlFor, groupBindings, wikidata, SETTLED, HOME_NATIONS };

if (require.main === module) {
  main().catch(err => { console.error('Flag check could not finish: ' + err.message); process.exit(1); });
}
