// =============================================================================
// build/fetch-prop-lines.js — pull UFC round-TOTALS lines from The Odds API and
// write per-book snapshot rows into Supabase `prop_lines`.
// =============================================================================
// Sibling to fetch-odds.js (moneyline). This is the MARKET half of the props
// paper-trading layer: it accrues the open->close line history that
// grading/paper_clv.py needs to compute closing-line value on duration props.
//
// Scope (Stage 1): fight-level round totals only — market key `totals` on
//   sport mma_mixed_martial_arts. The Odds API carries this (licensed); it does
//   NOT carry fighter strike/takedown props, which need a paid vendor and are
//   deferred. One row per (fight, book, capture):
//
//     { fight_id, fighter_id:null, source:<book title>, stat_type:'total_rounds',
//       line:<point>, over_odds, under_odds, captured_at, source_url }
//
//   fighter_id is null because a round total is a property of the FIGHT, not a
//   fighter. paper_clv.py keys duration props on (fight_id, source, stat_type).
//
// NOT WIRED INTO CI. There is no odds-props workflow yet — this runs only when
// invoked by hand (or once you add a schedule). That's deliberate: totals cost
// extra Odds-API credits (a second market on top of h2h), so enabling the cron
// is your call. Budget note: markets=totals is billed like any market — roughly
// one extra credit per run per region; at the 2h cadence that's ~360/mo on top
// of the h2h job. Watch the 500/mo free-tier ceiling before scheduling.
//
// Safe to run locally: DRY_RUN=1 fetches + matches + builds rows but writes
// nothing. With no ODDS_API_KEY it exits cleanly (CLAUDE.md graceful-fallback).
//
// Requires (same as fetch-odds.js):
//   - ODDS_API_KEY
//   - SUPABASE_SERVICE_ROLE_KEY  (or local SUPABASE_SECRET_KEY) — legacy JWT
//     service_role key, bypasses RLS for the write.
// =============================================================================

const { createClient } = require('@supabase/supabase-js');

const ODDS_API_KEY = process.env.ODDS_API_KEY;
const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SECRET_KEY;
const SOURCE_TAG = 'the-odds-api:mma_mixed_martial_arts:totals';
const STAT_TYPE = 'total_rounds';
const DRY_RUN = !!process.env.DRY_RUN;

if (!ODDS_API_KEY) {
  // Graceful no-op rather than a loud failure, per CLAUDE.md secrets policy.
  console.log('ODDS_API_KEY unset — nothing to fetch. (Set it to capture prop lines.)');
  process.exit(0);
}
if (!SUPABASE_SERVICE_KEY) {
  console.error('SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SECRET_KEY) missing.');
  process.exit(1);
}

const sb = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY, {
  auth: { persistSession: false, autoRefreshToken: false },
});

// ----------------------------------------------------------------------------
// Name matching — identical rules to fetch-odds.js so a fight matched by the
// moneyline job matches here too. (Kept inline rather than shared to avoid
// coupling the two capture scripts; if a third market lands, factor these out.)
// ----------------------------------------------------------------------------
function normalizeName(name) {
  return String(name || '')
    .toLowerCase()
    .normalize('NFD').replace(/\p{Diacritic}/gu, '')
    .replace(/'/g, '')
    .replace(/[^a-z0-9 ]/g, ' ')
    .replace(/\b(jr|sr|ii|iii|iv|v)\b/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}
function firstLast(normalized) {
  const t = normalized.split(' ').filter(Boolean);
  return t.length <= 1 ? normalized : `${t[0]} ${t[t.length - 1]}`;
}
function pairKey(a, b) {
  return [a, b].sort().join('||');
}
function buildFightIndex(fights) {
  const strict = {};
  const loose = {};
  for (const f of fights) {
    if (!f.fighter_a_name || !f.fighter_b_name) continue;
    const a = normalizeName(f.fighter_a_name);
    const b = normalizeName(f.fighter_b_name);
    strict[pairKey(a, b)] = f;
    const lk = pairKey(firstLast(a), firstLast(b));
    if (!(lk in loose)) loose[lk] = f;
  }
  return { strict, loose };
}
function lookupFight(index, homeName, awayName) {
  const a = normalizeName(homeName);
  const b = normalizeName(awayName);
  return index.strict[pairKey(a, b)] || index.loose[pairKey(firstLast(a), firstLast(b))] || null;
}

// ----------------------------------------------------------------------------
// 1. Fetch totals from The Odds API (one request = whole MMA slate)
// ----------------------------------------------------------------------------
async function fetchTotalsFromApi() {
  const url = 'https://api.the-odds-api.com/v4/sports/mma_mixed_martial_arts/odds' +
    '?regions=us&markets=totals&oddsFormat=american&dateFormat=iso' +
    `&apiKey=${encodeURIComponent(ODDS_API_KEY)}`;

  let lastErr;
  for (let attempt = 1; attempt <= 3; attempt++) {
    let res;
    try {
      res = await fetch(url);
    } catch (netErr) {
      lastErr = netErr;
      await new Promise(r => setTimeout(r, 2000 * attempt));
      continue;
    }
    console.log(`[odds-api] quota: used=${res.headers.get('x-requests-used')}, ` +
      `remaining=${res.headers.get('x-requests-remaining')}`);
    if (res.ok) {
      const events = await res.json();
      console.log(`[odds-api] got ${events.length} MMA event(s) with a totals market`);
      return events;
    }
    lastErr = new Error(`Odds API ${res.status} ${res.statusText}: ${await res.text()}`);
    if (res.status < 500 && res.status !== 429) break;
    await new Promise(r => setTimeout(r, 2000 * attempt));
  }
  throw lastErr;
}

// ----------------------------------------------------------------------------
// 2. Candidate fights (last 7 days forward), same window as fetch-odds.js
// ----------------------------------------------------------------------------
async function loadCandidateFights() {
  const cutoff = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);
  const { data: events, error: evErr } = await sb
    .from('events')
    .select('id, event_date')
    .gte('event_date', cutoff);
  if (evErr) throw new Error(`events fetch: ${evErr.message}`);
  if (!events || !events.length) {
    console.log('[supabase] no candidate events in the recent/upcoming window');
    return [];
  }
  const ids = events.map(e => e.id);
  const { data: fights, error: fErr } = await sb
    .from('fights')
    .select('id, event_id, fighter_a_id, fighter_b_id, fighter_a_name, fighter_b_name')
    .in('event_id', ids);
  if (fErr) throw new Error(`fights fetch: ${fErr.message}`);
  console.log(`[supabase] ${fights ? fights.length : 0} candidate fights across ${events.length} events`);
  return fights || [];
}

// ----------------------------------------------------------------------------
// 3. Main: fetch, match, extract per-book totals, insert snapshots
// ----------------------------------------------------------------------------
(async () => {
  try {
    const [oddsEvents, candidateFights] = await Promise.all([
      fetchTotalsFromApi(),
      loadCandidateFights(),
    ]);
    const fightIndex = buildFightIndex(candidateFights);

    const captured_at = new Date().toISOString();
    const rows = [];
    const unmatched = [];
    let matchedFights = 0;

    for (const e of oddsEvents) {
      if (!e.home_team || !e.away_team) continue;
      const fight = lookupFight(fightIndex, e.home_team, e.away_team);
      if (!fight) {
        unmatched.push(`${e.home_team} vs ${e.away_team} (${(e.commence_time || '').slice(0, 10)})`);
        continue;
      }

      let wrote = 0;
      for (const bm of e.bookmakers || []) {
        const totals = (bm.markets || []).find(m => m.key === 'totals');
        if (!totals || !Array.isArray(totals.outcomes)) continue;

        // A totals market is two outcomes {name:'Over'|'Under', price, point}.
        // Some books post multiple alt lines (repeated points); capture each
        // distinct point as its own snapshot row so alt lines are preserved.
        const byPoint = new Map(); // point -> { over, under }
        for (const o of totals.outcomes) {
          if (o.price == null || o.point == null) continue;
          const p = Number(o.point);
          if (!byPoint.has(p)) byPoint.set(p, { over: null, under: null });
          const nm = String(o.name || '').toLowerCase();
          if (nm === 'over') byPoint.get(p).over = Math.round(o.price);
          else if (nm === 'under') byPoint.get(p).under = Math.round(o.price);
        }
        for (const [point, { over, under }] of byPoint) {
          if (over == null && under == null) continue;
          rows.push({
            fight_id: fight.id,
            fighter_id: null,               // fight-level market
            source: (bm.title || bm.key || 'unknown').trim(),
            stat_type: STAT_TYPE,
            line: point,
            over_odds: over,
            under_odds: under,
            captured_at,
            source_url: SOURCE_TAG,
          });
          wrote++;
        }
      }
      if (wrote > 0) matchedFights++;
    }

    if (unmatched.length) {
      console.warn(`[match] ${unmatched.length} Odds API totals event(s) had no fight in our DB:`);
      for (const u of unmatched) console.warn('  - ' + u);
    }

    if (rows.length === 0) {
      // Unlike moneyline, MMA totals coverage is genuinely spotty — many cards
      // never get a posted round total from US books. So zero rows is NOT an
      // error here (moneyline fails loud on an imminent card; totals must not,
      // or the job would page on every prop-less card). Just log and stop.
      console.log('[done] no totals lines matched this run (books may not post ' +
        'round totals for the current card) — nothing to insert');
      return;
    }

    if (DRY_RUN) {
      console.log(`[dry-run] would insert ${rows.length} row(s) across ${matchedFights} fight(s). Sample:`);
      for (const r of rows.slice(0, 12)) {
        console.log(`  fight ${r.fight_id} ${r.source} O/U ${r.line}: ` +
          `over ${r.over_odds} / under ${r.under_odds}`);
      }
      return;
    }

    const CHUNK = 500;
    for (let i = 0; i < rows.length; i += CHUNK) {
      const { error: insErr } = await sb.from('prop_lines').insert(rows.slice(i, i + CHUNK));
      if (insErr) throw new Error(`prop_lines insert: ${insErr.message}`);
    }
    console.log(`[done] inserted ${rows.length} totals snapshot row(s) across ` +
      `${matchedFights} fight(s) at ${captured_at}`);
  } catch (err) {
    console.error('[fetch-prop-lines] failed:', err.message);
    process.exit(1);
  }
})();
