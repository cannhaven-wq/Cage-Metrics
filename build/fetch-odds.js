// =============================================================================
// build/fetch-odds.js — pull current UFC moneyline odds and upsert into Supabase
// =============================================================================
// Hits The Odds API for MMA h2h moneylines across US bookmakers, normalizes
// fighter names, matches each Odds API event to a fight in our `fights` table,
// averages implied probability across books (vig-removed), and upserts one row
// per matched fight into `fight_odds`.
//
// Runs in CI via .github/workflows/odds.yml. Requires two secrets:
//   - ODDS_API_KEY              (the-odds-api.com)
//   - SUPABASE_SERVICE_ROLE_KEY (Supabase project settings → API)
//
// Service-role key bypasses RLS so the script can write to fight_odds without
// needing an authenticated session. Keep it in GitHub Secrets only.
//
// Cost: one API request per run, one region (us), one market (h2h). Free tier
// is 500 req/mo → plenty of headroom for every-6-hours.
// =============================================================================

const { createClient } = require('@supabase/supabase-js');

const ODDS_API_KEY = process.env.ODDS_API_KEY;
const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;

if (!ODDS_API_KEY) {
  console.error('ODDS_API_KEY missing. Set it in GitHub Secrets.');
  process.exit(1);
}
if (!SUPABASE_SERVICE_KEY) {
  console.error('SUPABASE_SERVICE_ROLE_KEY missing. Set it in GitHub Secrets.');
  process.exit(1);
}

const sb = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY, {
  auth: { persistSession: false, autoRefreshToken: false }
});

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------

// Casing, apostrophes, accents, punctuation all vary between the Odds API and
// our `fighters` table. Normalize aggressively so equal-by-spelling names match.
function normalizeName(name) {
  return String(name || '')
    .toLowerCase()
    .normalize('NFD').replace(/\p{Diacritic}/gu, '')
    .replace(/'/g, '')
    .replace(/[^a-z0-9 ]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function americanToImplied(american) {
  if (american == null) return null;
  if (american > 0) return 100 / (american + 100);
  return -american / (-american + 100);
}

// Inverse — given a vig-free probability, return the "fair" American odds for
// display. Sign convention: negative for favorites, positive for underdogs.
function impliedToAmerican(implied) {
  if (implied == null || implied <= 0 || implied >= 1) return null;
  if (implied >= 0.5) return Math.round(-implied / (1 - implied) * 100);
  return Math.round((1 - implied) / implied * 100);
}

// -----------------------------------------------------------------------------
// 1. Fetch raw odds from The Odds API
// -----------------------------------------------------------------------------

async function fetchOddsFromApi() {
  const url = 'https://api.the-odds-api.com/v4/sports/mma_mixed_martial_arts/odds' +
    '?regions=us&markets=h2h&oddsFormat=american&dateFormat=iso' +
    `&apiKey=${encodeURIComponent(ODDS_API_KEY)}`;

  const res = await fetch(url);
  const used = res.headers.get('x-requests-used');
  const remaining = res.headers.get('x-requests-remaining');
  console.log(`[odds-api] quota: used=${used}, remaining=${remaining}`);

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Odds API ${res.status} ${res.statusText}: ${body}`);
  }
  const events = await res.json();
  console.log(`[odds-api] got ${events.length} events`);
  return events;
}

// -----------------------------------------------------------------------------
// 2. Pull fights we might match against (recent + upcoming events)
// -----------------------------------------------------------------------------

async function loadCandidateFights() {
  // Look at events from the last 7 days through whatever's scheduled forward.
  // The Odds API returns upcoming fights mostly, but may include in-progress.
  const cutoff = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);

  const { data: events, error: evErr } = await sb
    .from('events')
    .select('id, event_date, is_upcoming')
    .gte('event_date', cutoff);
  if (evErr) throw new Error(`events fetch: ${evErr.message}`);
  if (!events || events.length === 0) {
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

// Index fights by sorted-pair of normalized names so we can look up regardless
// of which fighter is A/B in our DB vs home/away in the Odds API.
function buildFightIndex(fights) {
  const idx = {};
  for (const f of fights) {
    if (!f.fighter_a_name || !f.fighter_b_name) continue;
    const a = normalizeName(f.fighter_a_name);
    const b = normalizeName(f.fighter_b_name);
    const key = [a, b].sort().join('||');
    idx[key] = f;
  }
  return idx;
}

// -----------------------------------------------------------------------------
// 3. For each Odds API event, average books → vig-removed implied prob
// -----------------------------------------------------------------------------

function averageBookOdds(oddsEvent) {
  let sumHome = 0;
  let sumAway = 0;
  let count = 0;

  for (const bm of oddsEvent.bookmakers || []) {
    const h2h = (bm.markets || []).find(m => m.key === 'h2h');
    if (!h2h || !Array.isArray(h2h.outcomes)) continue;

    const home = h2h.outcomes.find(o => o.name === oddsEvent.home_team);
    const away = h2h.outcomes.find(o => o.name === oddsEvent.away_team);
    if (!home || !away) continue;

    const homeImp = americanToImplied(home.price);
    const awayImp = americanToImplied(away.price);
    if (homeImp == null || awayImp == null) continue;

    const total = homeImp + awayImp;
    if (total <= 0) continue;

    // Vig-removed per book before averaging — this is more correct than
    // averaging raw American odds.
    sumHome += homeImp / total;
    sumAway += awayImp / total;
    count++;
  }

  if (count === 0) return null;
  return {
    impliedHome: sumHome / count,
    impliedAway: sumAway / count,
    bookmakerCount: count,
  };
}

// -----------------------------------------------------------------------------
// 4. Main: fetch, match, average, upsert
// -----------------------------------------------------------------------------

(async () => {
  try {
    const [oddsEvents, candidateFights] = await Promise.all([
      fetchOddsFromApi(),
      loadCandidateFights(),
    ]);

    const fightIndex = buildFightIndex(candidateFights);
    const rows = [];
    const unmatched = [];

    for (const e of oddsEvents) {
      if (!e.home_team || !e.away_team) continue;

      const home = normalizeName(e.home_team);
      const away = normalizeName(e.away_team);
      const key = [home, away].sort().join('||');
      const fight = fightIndex[key];

      if (!fight) {
        unmatched.push(`${e.home_team} vs ${e.away_team} (${e.commence_time})`);
        continue;
      }

      const avg = averageBookOdds(e);
      if (!avg) {
        console.warn(`[match] ${fight.fighter_a_name} vs ${fight.fighter_b_name}: no usable book odds`);
        continue;
      }

      // The Odds API's "home_team" is just a label — figure out whether it
      // maps to our fighter_a or fighter_b so we store the probabilities
      // under the right column.
      const homeMatchesA = home === normalizeName(fight.fighter_a_name);
      const impliedA = homeMatchesA ? avg.impliedHome : avg.impliedAway;
      const impliedB = homeMatchesA ? avg.impliedAway : avg.impliedHome;

      rows.push({
        fight_id: fight.id,
        event_id: fight.event_id,
        fighter_a_id: fight.fighter_a_id,
        fighter_b_id: fight.fighter_b_id,
        fighter_a_name: fight.fighter_a_name,
        fighter_b_name: fight.fighter_b_name,
        american_odds_a: impliedToAmerican(impliedA),
        american_odds_b: impliedToAmerican(impliedB),
        implied_prob_a: Number(impliedA.toFixed(4)),
        implied_prob_b: Number(impliedB.toFixed(4)),
        bookmaker_count: avg.bookmakerCount,
        fetched_at: new Date().toISOString(),
      });
    }

    if (unmatched.length > 0) {
      console.warn(`[match] ${unmatched.length} Odds API events had no matching fight in our DB:`);
      for (const u of unmatched) console.warn('  - ' + u);
    }

    if (rows.length === 0) {
      console.log('[done] no rows to upsert');
      return;
    }

    const { error: upErr } = await sb
      .from('fight_odds')
      .upsert(rows, { onConflict: 'fight_id' });
    if (upErr) throw new Error(`upsert: ${upErr.message}`);

    console.log(`[done] upserted ${rows.length} fight_odds rows`);
  } catch (err) {
    console.error('[fetch-odds] failed:', err.message);
    process.exit(1);
  }
})();
