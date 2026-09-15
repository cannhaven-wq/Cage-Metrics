// =============================================================================
// build/fetch-odds.js — pull current UFC moneyline odds from The Odds API and
// write per-book snapshot rows into Supabase `fight_odds`.
// =============================================================================
// This writes the SAME snapshot shape the cage-metrics-odds-scrapper Railway
// cron uses — one row per (fight, side, book, captured_at):
//
//   { fight_id, fighter_id, book_id, side:'A'|'B', american_odds, implied_prob,
//     captured_at, source_url }   (is_opener / is_closer default FALSE)
//
// so the existing `v_fight_odds_consensus` view and the parlay/event/index
// pages read it with no other changes. (The previous version of this file wrote
// a one-row-per-fight `american_odds_a/b` shape that collided with the live
// table — that's why the workflow was disabled. Fixed here.)
//
// Runs in CI via .github/workflows/odds.yml. Requires two secrets:
//   - ODDS_API_KEY              (the-odds-api.com)
//   - SUPABASE_SERVICE_ROLE_KEY (Supabase → Project Settings → API; legacy JWT
//                                service_role key, NOT the sb_secret_ format)
//
// The service-role key bypasses RLS so we can write without an auth session.
// Keep it in GitHub Secrets only — never commit it.
//
// Cost: ONE API request per run (regions=us, markets=h2h) = 1 credit, and it
// returns the whole MMA slate at once. Free tier is 500/mo.
//
// CADENCE (changed 2026-08-30): the workflow now wakes HOURLY, but this script
// decides whether the run is worth a credit before spending one — see
// shouldSpendCredit(). A price captured once a day is not a closing price: with
// the old every-2h-on-paper schedule the freshest line we held going into a
// bell could be ~24h stale, which makes CLV a guess. Now:
//
//   * card today or tomorrow (UTC) -> capture every hour, so the last line we
//     hold before any bell is at most ~60 minutes old
//   * no card in that window       -> one baseline capture a day (08:00 UTC) to
//     keep openers and slow line movement on file
//
// Budget: ~8 card-adjacent days/month x 24 + ~22 quiet days x 1 = ~215 credits,
// well inside the 500 cap and far denser where it actually matters. Quiet-hour
// runs exit BEFORE the API call, so they cost nothing.
// =============================================================================

const { createClient } = require('@supabase/supabase-js');

const ODDS_API_KEY = process.env.ODDS_API_KEY;
const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
// CI sets SUPABASE_SERVICE_ROLE_KEY; local Windows env uses SUPABASE_SECRET_KEY.
// Either works (both must be the legacy JWT service_role key to bypass RLS).
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SECRET_KEY;
const SOURCE_TAG = 'the-odds-api:mma_mixed_martial_arts';
// DRY_RUN=1 → fetch + match + build rows but DON'T write. For safe local testing.
// A fixture replay is always a dry run: synthetic quotes must never be stored.
const DRY_RUN = !!process.env.DRY_RUN || !!process.env.ODDS_FIXTURE;

if (!ODDS_API_KEY && !process.env.ODDS_FIXTURE) {
  console.error('ODDS_API_KEY missing. Set it in GitHub Secrets (or env for local runs).');
  process.exit(1);
}
if (!SUPABASE_SERVICE_KEY) {
  console.error('SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SECRET_KEY) missing.');
  process.exit(1);
}

const sb = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY, {
  auth: { persistSession: false, autoRefreshToken: false }
});

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------

// Casing, apostrophes, accents, punctuation, and generational suffixes all vary
// between the Odds API and our `fighters` table. Normalize aggressively, and
// strip trailing jr/sr/ii/iii/iv/v so "Kai Kamaka III" == "Kai Kamaka" and
// "Khalil Rountree Jr" == "Khalil Rountree". Applied to BOTH sides so it stays
// symmetric.
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

function americanToImplied(american) {
  if (american == null) return null;
  if (american > 0) return 100 / (american + 100);
  return -american / (-american + 100);
}

function impliedToAmerican(p) {
  if (p == null || p <= 0 || p >= 1) return null;
  return Math.round(p >= 0.5 ? (-100 * p) / (1 - p) : (100 * (1 - p)) / p);
}

// The synthetic consensus "book": one row per (fight, side) per run holding the
// median implied probability across all real books in that snapshot. Gives the
// models a single canonical price series — and, via the is_opener flag below, a
// locked opening price — even though the underlying book set varies run to run.
const CONSENSUS_BOOK_NAME = 'CFL Consensus (Odds API)';

// -----------------------------------------------------------------------------
// 0. Cadence gate — is this hourly wake-up worth a credit?
// -----------------------------------------------------------------------------
// Runs against `events` only (free), before any Odds API call. FORCE=1 (set by
// workflow_dispatch) always spends, so a manual run is never silently skipped.

const BASELINE_HOUR_UTC = 8;

async function shouldSpendCredit() {
  if (process.env.FORCE) {
    console.log('[cadence] FORCE set — capturing regardless of schedule');
    return true;
  }
  const now = new Date();
  const today = now.toISOString().slice(0, 10);
  const tomorrow = new Date(now.getTime() + 86400000).toISOString().slice(0, 10);

  const { data: near, error } = await sb
    .from('events')
    .select('name, event_date')
    .gte('event_date', today)
    .lte('event_date', tomorrow);
  if (error) throw new Error(`cadence events check: ${error.message}`);

  if (near && near.length) {
    console.log(`[cadence] card window (${near.map(e => `${e.name} ${e.event_date}`).join('; ')}) — hourly capture`);
    return true;
  }
  if (now.getUTCHours() === BASELINE_HOUR_UTC) {
    console.log('[cadence] no card today or tomorrow — taking the daily baseline capture');
    return true;
  }
  console.log(`[cadence] no card today or tomorrow and it is not the ${BASELINE_HOUR_UTC}:00 UTC baseline hour — skipping (0 credits)`);
  return false;
}

// -----------------------------------------------------------------------------
// 1. Fetch raw odds from The Odds API (one request = whole MMA slate)
// -----------------------------------------------------------------------------

// DUR-001 (2026-09-14): the same request also carries the fight TOTALS market
// (over/under rounds) when wantTotals() says so. Each extra market costs one
// more credit per call (quota = markets x regions), so totals ride along only
// where a close can actually form — see wantTotals(). Totals rows go to the
// private, append-only `prop_odds` ledger; the moneyline path is unchanged.
async function fetchOddsFromApi(markets = 'h2h') {
  // ODDS_FIXTURE=<path.json>: replay a saved/synthetic Odds API payload instead
  // of spending a credit. Forces DRY_RUN semantics upstream (see main) so a
  // fixture can never reach the database. Used by the DUR-001 ingestion check.
  if (process.env.ODDS_FIXTURE) {
    const fs = require('fs');
    const events = JSON.parse(fs.readFileSync(process.env.ODDS_FIXTURE, 'utf8'));
    console.log(`[odds-api] FIXTURE ${process.env.ODDS_FIXTURE}: ${events.length} events (markets=${markets}; no credit spent)`);
    return events;
  }
  const url = 'https://api.the-odds-api.com/v4/sports/mma_mixed_martial_arts/odds' +
    `?regions=us&markets=${encodeURIComponent(markets)}&oddsFormat=american&dateFormat=iso` +
    `&apiKey=${encodeURIComponent(ODDS_API_KEY)}`;

  // Retry transient failures (network, 429, 5xx) — a lost run here can cost a
  // fight's opener, since openers are first-capture. 4xx (bad key/params) is
  // not retried: the answer won't change and failed calls still show quota use.
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
      console.log(`[odds-api] got ${events.length} MMA events`);
      return events;
    }
    lastErr = new Error(`Odds API ${res.status} ${res.statusText}: ${await res.text()}`);
    if (res.status < 500 && res.status !== 429) break;
    await new Promise(r => setTimeout(r, 2000 * attempt));
  }
  throw lastErr;
}

// -----------------------------------------------------------------------------
// 2. Candidate fights (last 7 days through everything scheduled forward)
// -----------------------------------------------------------------------------

async function loadCandidateFights() {
  const cutoff = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);

  const { data: events, error: evErr } = await sb
    .from('events')
    .select('id, event_date')
    .gte('event_date', cutoff);
  if (evErr) throw new Error(`events fetch: ${evErr.message}`);
  if (!events || events.length === 0) {
    console.log('[supabase] no candidate events in the recent/upcoming window');
    return [];
  }

  const ids = events.map(e => e.id);
  const { data: fights, error: fErr } = await sb
    .from('fights')
    .select('id, event_id, fighter_a_id, fighter_b_id, fighter_a_name, fighter_b_name, bell_at')
    .in('event_id', ids);
  if (fErr) throw new Error(`fights fetch: ${fErr.message}`);
  console.log(`[supabase] ${fights ? fights.length : 0} candidate fights across ${events.length} events`);

  // Best-known start time per fight (bell_at > provider commence > event-date
  // fallback), from the DUR-001 start hierarchy view. Used by wantTotals() and
  // promoteClosers(). Missing view (migration not applied) => empty map.
  const byDate = new Map(events.map(e => [e.id, e.event_date]));
  const { data: starts, error: sErr } = await sb
    .from('v_fight_start_best')
    .select('fight_id, start_at, start_basis')
    .in('fight_id', (fights || []).map(f => f.id));
  if (sErr) console.warn(`[start] v_fight_start_best unavailable (${sErr.message}) — apply dur001_migration.sql`);
  const startById = new Map((starts || []).map(s => [s.fight_id, s]));
  for (const f of fights || []) {
    f.event_date = byDate.get(f.event_id) || null;
    const s = startById.get(f.id);
    f.start_at = s ? s.start_at : null;
    f.start_basis = s ? s.start_basis : null;
  }
  return fights || [];
}

// Reduce a normalized name to first + last token only, so middle names don't
// block a match ("ian machado garry" -> "ian garry" to meet the Odds API's
// "Ian Garry"). Single-token names pass through unchanged.
function firstLast(normalized) {
  const t = normalized.split(' ').filter(Boolean);
  return t.length <= 1 ? normalized : `${t[0]} ${t[t.length - 1]}`;
}

function pairKey(a, b) {
  return [a, b].sort().join('||');
}

// Index fights by sorted normalized name pair, regardless of which fighter the
// Odds API calls home vs away. Keep two indexes: a strict full-name one and a
// looser first+last one used only as a fallback.
function buildFightIndex(fights) {
  const strict = {};
  const loose = {};
  for (const f of fights) {
    if (!f.fighter_a_name || !f.fighter_b_name) continue;
    const a = normalizeName(f.fighter_a_name);
    const b = normalizeName(f.fighter_b_name);
    strict[pairKey(a, b)] = f;
    const lk = pairKey(firstLast(a), firstLast(b));
    if (!(lk in loose)) loose[lk] = f; // first writer wins; ambiguous keys stay put
  }
  return { strict, loose };
}

function lookupFight(index, homeName, awayName) {
  const a = normalizeName(homeName);
  const b = normalizeName(awayName);
  return index.strict[pairKey(a, b)] || index.loose[pairKey(firstLast(a), firstLast(b))] || null;
}

// -----------------------------------------------------------------------------
// 3. Book directory — resolve Odds API book titles to odds_books.id,
//    creating any we haven't seen before.
// -----------------------------------------------------------------------------

async function resolveBooks(oddsEvents) {
  // distinct {title, key} pairs present in this slate
  const seen = new Map(); // normalized title -> { title, key }
  for (const e of oddsEvents) {
    for (const bm of e.bookmakers || []) {
      if (!bm.title) continue;
      const n = bm.title.trim().toLowerCase();
      if (!seen.has(n)) seen.set(n, { title: bm.title.trim(), key: bm.key || null });
    }
  }

  const { data: existing, error } = await sb.from('odds_books').select('id, name');
  if (error) throw new Error(`odds_books fetch: ${error.message}`);
  const byName = new Map((existing || []).map(b => [b.name.trim().toLowerCase(), b.id]));

  // Insert any missing books (uniform keys → DB defaults apply; name is UNIQUE
  // so ignoreDuplicates guards against a concurrent insert).
  const missing = [...seen.values()].filter(b => !byName.has(b.title.toLowerCase()));
  if (missing.length) {
    const { error: insErr } = await sb
      .from('odds_books')
      .upsert(missing.map(b => ({ name: b.title, short_code: b.key })),
              { onConflict: 'name', ignoreDuplicates: true });
    if (insErr) throw new Error(`odds_books insert: ${insErr.message}`);
    console.log(`[books] added ${missing.length} new book(s): ${missing.map(b => b.title).join(', ')}`);

    const { data: refreshed, error: reErr } = await sb.from('odds_books').select('id, name');
    if (reErr) throw new Error(`odds_books re-fetch: ${reErr.message}`);
    byName.clear();
    (refreshed || []).forEach(b => byName.set(b.name.trim().toLowerCase(), b.id));
  }
  return byName; // normalized name -> book_id
}

// -----------------------------------------------------------------------------
// 3b. Start times — the only thing that makes "the close" mean anything
// -----------------------------------------------------------------------------
// ufcstats gives us an event DATE and no start time. The Odds API gives a
// per-fight commence_time, and it is the only source we have for one today.
// It is a PROVIDER ESTIMATE, not the bell, so it is recorded in the append-only
// fight_start_estimates ledger (source 'odds_api_commence'), never written into
// fights.bell_at — that column stays reserved for a confirmed actual bell.
// v_fight_start_best resolves bell_at > latest provider commence > event-date
// fallback, and settlement defines the close as the last non-live capture
// STRICTLY BEFORE that start, rather than "the newest row we happen to hold" —
// which is how post-settlement sentinel prices (-199900 / +199900) end up
// flagged as closers and poison CLV.
//
// Duplicate observations (same fight, same commence) are no-ops via the ledger's
// unique index; a reschedule appends a new row and becomes the latest estimate.

async function recordStartEstimates(commenceByFight) {
  if (!commenceByFight.size) return;
  const rows = [...commenceByFight.entries()].map(([fight_id, start_at]) => ({
    fight_id, source: 'odds_api_commence', start_at,
  }));
  const { error } = await sb
    .from('fight_start_estimates')
    .upsert(rows, { onConflict: 'fight_id,source,start_at', ignoreDuplicates: true });
  if (error) {
    // Ledger missing (migration not applied) must not take the moneyline
    // capture down with it.
    console.warn(`[start] fight_start_estimates write failed: ${error.message}`);
    return;
  }
  console.log(`[start] recorded provider commence for ${rows.length} fight(s) (duplicates ignored)`);
}

// -----------------------------------------------------------------------------
// 3c. Closer promotion — one closing price per (fight, fighter, book)
// -----------------------------------------------------------------------------
// Openers are known at capture time; closers are not, because we cannot know a
// capture is the last one until the bell rings. So this runs after the fact:
// for every fight whose bell has passed, the latest capture before the bell
// becomes that book's closer, and anything else loses the flag.
//
// It CLEARS as well as sets, deliberately. The Polymarket scraper marks its
// newest row as the closer whether or not the fight has started, so its flag
// walks forward into post-fight captures. Left alone, that is a closing price
// taken after the result was known.
//
// Fights with no real start time (no bell_at and no provider commence — i.e.
// only the event-date fallback) are never touched — that leaves the BFO-era
// history (book 6, closers set by the backfill) exactly as it is.
//
// This flag only exists on the moneyline table. prop_odds never stores a closer
// flag: its close is computed by v_prop_odds_lifecycle from the same start
// hierarchy, so it can be recomputed when better start times arrive.

const CLOSER_LOOKBACK_DAYS = 21;

async function promoteClosers(candidateFights) {
  const now = Date.now();
  const floor = now - CLOSER_LOOKBACK_DAYS * 86400000;
  const due = (candidateFights || []).filter(f => {
    if (!f.start_at || !['bell_at', 'provider_commence'].includes(f.start_basis)) return false;
    const t = new Date(f.start_at).getTime();
    return t < now && t > floor;
  });
  if (!due.length) return;

  let promoted = 0, demoted = 0;
  for (const f of due) {
    const bell = new Date(f.start_at).toISOString();
    const { data: caps, error } = await sb
      .from('fight_odds')
      .select('id, fighter_id, book_id, captured_at, is_closer')
      .eq('fight_id', f.id);
    if (error) throw new Error(`closer scan (fight ${f.id}): ${error.message}`);
    if (!caps || !caps.length) continue;

    // Winner per (fighter, book): latest capture strictly before the bell.
    const best = new Map();
    for (const c of caps) {
      if (!(c.captured_at < bell)) continue;
      const k = `${c.fighter_id}|${c.book_id}`;
      const cur = best.get(k);
      if (!cur || c.captured_at > cur.captured_at) best.set(k, c);
    }
    const keep = new Set([...best.values()].map(c => c.id));

    const toSet = [...keep].filter(id => !caps.find(c => c.id === id).is_closer);
    const toClear = caps.filter(c => c.is_closer && !keep.has(c.id)).map(c => c.id);

    if (toSet.length) {
      const { error: e1 } = await sb
        .from('fight_odds').update({ is_closer: true }).in('id', toSet);
      if (e1) throw new Error(`closer set (fight ${f.id}): ${e1.message}`);
      promoted += toSet.length;
    }
    if (toClear.length) {
      const { error: e2 } = await sb
        .from('fight_odds').update({ is_closer: false }).in('id', toClear);
      if (e2) throw new Error(`closer clear (fight ${f.id}): ${e2.message}`);
      demoted += toClear.length;
    }
  }
  if (promoted || demoted) {
    console.log(`[closers] ${due.length} fight(s) past the bell: promoted ${promoted} ` +
      `capture(s), cleared ${demoted} stale/post-bell flag(s)`);
  }
}

// -----------------------------------------------------------------------------
// 3d. Fight totals (DUR-001) — over/under rounds, appended to prop_odds
// -----------------------------------------------------------------------------
// Every quote is one immutable row: (fight, book, line, captured_at) with both
// prices, the provider's commence time as seen at capture, a live flag
// (captured at/after commence => in-play, never a close) and the raw provider
// metadata. No opener/closer flags are stored: v_prop_odds_lifecycle derives
// them from the start hierarchy, so they can be recomputed later.
//
// Credit budget. Totals add one credit per call. They are requested when:
//   * FORCE=1 (manual run), or
//   * a candidate fight's best-known start is within TOTALS_HOURLY_WINDOW_H
//     hours (hourly density right where the close forms), or
//   * it is an even UTC hour inside the card window, or
//   * it is the daily baseline hour (so opening lines are on file for the
//     Phase-8 opener test).
// Set ODDS_MARKETS to override entirely (e.g. 'h2h' to switch totals off).
const TOTALS_HOURLY_WINDOW_H = Number(process.env.TOTALS_HOURLY_WINDOW_H || 6);
const TOTALS_ENABLED = (process.env.ODDS_MARKETS || 'h2h,totals').split(',').map(s => s.trim()).includes('totals');

function wantTotals(candidateFights, now = new Date()) {
  if (!TOTALS_ENABLED) return { yes: false, why: 'totals disabled via ODDS_MARKETS' };
  if (process.env.FORCE) return { yes: true, why: 'FORCE set' };
  const t = now.getTime();
  const near = (candidateFights || []).some(f => {
    if (!f.start_at) return false;
    const s = new Date(f.start_at).getTime();
    return s > t - 3600000 && s < t + TOTALS_HOURLY_WINDOW_H * 3600000;
  });
  if (near) return { yes: true, why: `a fight starts within ${TOTALS_HOURLY_WINDOW_H}h` };
  if (now.getUTCHours() === BASELINE_HOUR_UTC) return { yes: true, why: 'daily baseline hour' };
  const today = now.toISOString().slice(0, 10);
  const tomorrow = new Date(t + 86400000).toISOString().slice(0, 10);
  const cardWindow = (candidateFights || []).some(f => f.event_date === today || f.event_date === tomorrow);
  if (cardWindow && now.getUTCHours() % 2 === 0) return { yes: true, why: 'even hour in the card window' };
  return { yes: false, why: cardWindow ? 'odd hour in the card window' : 'no card in window' };
}

// One prop_odds row per (book, line) for a matched Odds API event.
function buildTotalsRows(e, fight, bookId, captured_at) {
  const rows = [];
  const commence = e.commence_time ? new Date(e.commence_time).toISOString() : null;
  const is_live = !!(commence && captured_at >= commence);
  for (const bm of e.bookmakers || []) {
    const bid = bookId.get((bm.title || '').trim().toLowerCase());
    if (!bid) continue;
    for (const m of bm.markets || []) {
      if (m.key !== 'totals' || !Array.isArray(m.outcomes)) continue;
      // Group Over/Under by line (books can post alternates; keep each pair).
      const byLine = new Map();
      for (const o of m.outcomes) {
        if (o.point == null || o.price == null) continue;
        const k = String(o.point);
        if (!byLine.has(k)) byLine.set(k, { point: Number(o.point) });
        const slot = byLine.get(k);
        const nm = String(o.name || '').toLowerCase();
        if (nm === 'over') slot.over = Math.round(o.price);
        else if (nm === 'under') slot.under = Math.round(o.price);
      }
      for (const slot of byLine.values()) {
        if (slot.over == null || slot.under == null || !(slot.point > 0)) continue;
        rows.push({
          fight_id: fight.id,
          event_id: fight.event_id,
          event_date: fight.event_date,
          market_type: 'total_rounds',
          fighter_id: null,
          line: slot.point,
          over_odds: slot.over,
          under_odds: slot.under,
          book_id: bid,
          source: 'odds_api',
          source_event_id: e.id || null,
          captured_at,
          source_commence_at: commence,
          is_live,
          raw: { bookmaker_key: bm.key || null, bookmaker_last_update: bm.last_update || null,
                 market_last_update: m.last_update || null, home_team: e.home_team, away_team: e.away_team },
        });
      }
    }
  }
  return rows;
}

async function writePropOdds(rows) {
  if (!rows.length) return 0;
  const CHUNK = 500;
  for (let i = 0; i < rows.length; i += CHUNK) {
    const { error } = await sb.from('prop_odds').insert(rows.slice(i, i + CHUNK));
    if (error) throw new Error(`prop_odds insert: ${error.message}`);
  }
  return rows.length;
}

// -----------------------------------------------------------------------------
// 4. Main: fetch, match, build per-book snapshot rows, insert
// -----------------------------------------------------------------------------

(async () => {
  try {
    if (!(await shouldSpendCredit())) return;

    // Candidate fights first: wantTotals() needs their start times to decide
    // whether this call should spend the extra credit on the totals market.
    const candidateFights = await loadCandidateFights();
    const totals = wantTotals(candidateFights);
    console.log(`[totals] ${totals.yes ? 'requesting' : 'skipping'} fight totals — ${totals.why}`);
    const oddsEvents = await fetchOddsFromApi(totals.yes ? 'h2h,totals' : 'h2h');

    const fightIndex = buildFightIndex(candidateFights);
    const bookId = await resolveBooks(oddsEvents);

    const captured_at = new Date().toISOString();
    const rows = [];
    const unmatched = [];
    const commenceByFight = new Map(); // fight_id -> provider commence_time (ISO)
    const totalsRows = [];             // prop_odds rows (DUR-001)
    let matchedFights = 0;

    for (const e of oddsEvents) {
      if (!e.home_team || !e.away_team) continue;

      const fight = lookupFight(fightIndex, e.home_team, e.away_team);
      if (!fight) {
        unmatched.push(`${e.home_team} vs ${e.away_team} (${(e.commence_time || '').slice(0, 10)})`);
        continue;
      }
      if (process.env.DEBUG) {
        console.log(`[match] API "${e.home_team} vs ${e.away_team}" -> fight ${fight.id} (${fight.fighter_a_name} vs ${fight.fighter_b_name})`);
      }

      const nA = normalizeName(fight.fighter_a_name), flA = firstLast(nA);
      const nB = normalizeName(fight.fighter_b_name), flB = firstLast(nB);
      let wrote = 0;

      for (const bm of e.bookmakers || []) {
        const h2h = (bm.markets || []).find(m => m.key === 'h2h');
        if (!h2h || !Array.isArray(h2h.outcomes)) continue;
        const bid = bookId.get((bm.title || '').trim().toLowerCase());
        if (!bid) continue;

        // Map each outcome to our canonical A/B by name (not by home/away order),
        // tolerating middle-name drift via the first+last fallback.
        for (const o of h2h.outcomes) {
          if (o.price == null) continue;
          const n = normalizeName(o.name);
          let side, fighter_id;
          if (n === nA || firstLast(n) === flA) { side = 'A'; fighter_id = fight.fighter_a_id; }
          else if (n === nB || firstLast(n) === flB) { side = 'B'; fighter_id = fight.fighter_b_id; }
          else continue; // draw / unexpected label
          rows.push({
            fight_id: fight.id,
            fighter_id,
            book_id: bid,
            side,
            american_odds: Math.round(o.price),
            implied_prob: Number(americanToImplied(o.price).toFixed(6)),
            captured_at,
            source_url: SOURCE_TAG,
          });
          wrote++;
        }
      }
      // Fight totals (DUR-001) — independent of whether h2h matched a price.
      if (totals.yes) totalsRows.push(...buildTotalsRows(e, fight, bookId, captured_at));

      if (wrote > 0) matchedFights++;
      if (wrote > 0 || totals.yes) {
        // Proof that this capture is actually near the bell. The Odds API gives
        // us commence_time, which ufcstats does not — so this is the only place
        // we can see how stale our "closing" price would be if the feed stopped
        // here. Anything over ~120 min on a card day means the hourly cadence
        // isn't landing and CLV is being settled against a stale line.
        if (e.commence_time) {
          commenceByFight.set(fight.id, new Date(e.commence_time).toISOString());
          const mins = Math.round((new Date(e.commence_time) - new Date(captured_at)) / 60000);
          if (mins >= -60 && mins <= 24 * 60) {
            console.log(`[start] fight ${fight.id} (${e.home_team} vs ${e.away_team}) — captured ${mins} min before commence_time`);
          }
        }
      }
    }

    if (unmatched.length) {
      console.warn(`[match] ${unmatched.length} Odds API event(s) had no fight in our DB (non-UFC promotions or name drift):`);
      for (const u of unmatched) console.warn('  - ' + u);
    }

    if (DRY_RUN) {
      console.log(`[dry-run] would record provider commence for ${commenceByFight.size} fight(s), ` +
        `append ${totalsRows.length} totals quote(s) to prop_odds, and promote moneyline closers ` +
        `for any fight past its start.`);
      for (const r of totalsRows.slice(0, 8)) {
        console.log(`  totals fight ${r.fight_id} book ${r.book_id} line ${r.line} ` +
          `O ${r.over_odds > 0 ? '+' : ''}${r.over_odds} / U ${r.under_odds > 0 ? '+' : ''}${r.under_odds}` +
          ` commence ${r.source_commence_at} live=${r.is_live}`);
      }
    } else {
      await recordStartEstimates(commenceByFight);
      // Uses the start times already on file, so this still closes out last
      // night's card on a run where nothing new matched.
      await promoteClosers(candidateFights);
      // Totals are appended before the moneyline path's zero-match guard so a
      // totals-only slate (books post totals late; h2h drift) is never lost.
      const nTotals = await writePropOdds(totalsRows);
      if (nTotals) console.log(`[totals] appended ${nTotals} totals quote(s) to prop_odds at ${captured_at}`);
    }

    if (rows.length === 0) {
      // Zero matches is legitimate in the off-week lull before books post the
      // next card — but during fight week odds always exist, so matching
      // nothing with a card imminent means the matcher or the API feed is
      // broken. Fail loudly instead of silently skipping snapshot windows
      // (openers are first-capture; quiet gaps corrupt them).
      const today = new Date().toISOString().slice(0, 10);
      const soon = new Date(Date.now() + 3 * 86400000).toISOString().slice(0, 10);
      const { data: imminent, error: imErr } = await sb
        .from('events')
        .select('name, event_date')
        .gte('event_date', today)
        .lte('event_date', soon);
      if (imErr) throw new Error(`imminent events check: ${imErr.message}`);
      if (imminent && imminent.length) {
        throw new Error(`matched 0 fights while ${imminent.length} card(s) are within 3 days ` +
          `(${imminent.map(e => e.name).join(', ')}) — matching is broken`);
      }
      console.log('[done] matched 0 fights — nothing to insert (no imminent card, likely off-week)');
      return;
    }

    // ---- consensus rows: median implied prob per (fight, side) across books ----
    let consensusBookId = bookId.get(CONSENSUS_BOOK_NAME.toLowerCase());
    if (!consensusBookId) {
      const { data: cb, error: cbErr } = await sb
        .from('odds_books')
        .upsert([{ name: CONSENSUS_BOOK_NAME, short_code: 'cflc' }],
                { onConflict: 'name', ignoreDuplicates: false })
        .select('id')
        .single();
      if (cbErr) throw new Error(`consensus book upsert: ${cbErr.message}`);
      consensusBookId = cb.id;
    }
    const bySide = new Map(); // fight_id|fighter_id -> { template row, probs[] }
    for (const r of rows) {
      const k = `${r.fight_id}|${r.fighter_id}`;
      if (!bySide.has(k)) bySide.set(k, { r, probs: [] });
      bySide.get(k).probs.push(r.implied_prob);
    }
    for (const { r, probs } of bySide.values()) {
      probs.sort((x, y) => x - y);
      const mid = Math.floor(probs.length / 2);
      const med = probs.length % 2 ? probs[mid] : (probs[mid - 1] + probs[mid]) / 2;
      const american = impliedToAmerican(med);
      if (american == null) continue;
      rows.push({
        fight_id: r.fight_id,
        fighter_id: r.fighter_id,
        book_id: consensusBookId,
        side: r.side,
        american_odds: american,
        implied_prob: Number(med.toFixed(6)),
        captured_at,
        source_url: SOURCE_TAG,
      });
    }

    // ---- opener flagging: first captured price per (fight, side, book) ----
    // A row is the opener if that (fight, fighter, book) combo has never had an
    // opener row before. This is what gives every future pick a locked opening
    // price — the models' ROI accounting depends on it (see model/v6 in the
    // scrapper repo). BFO-era history already carries is_opener on book 6.
    const fightIds = [...new Set(rows.map(r => r.fight_id))];
    const priorOpeners = [];
    for (let from = 0; ; from += 1000) {
      const { data: page, error: poErr } = await sb
        .from('fight_odds')
        .select('fight_id, fighter_id, book_id')
        .in('fight_id', fightIds)
        .eq('is_opener', true)
        .range(from, from + 999);
      if (poErr) throw new Error(`prior openers fetch: ${poErr.message}`);
      priorOpeners.push(...(page || []));
      if (!page || page.length < 1000) break;
    }
    const hasOpener = new Set(priorOpeners.map(o => `${o.fight_id}|${o.fighter_id}|${o.book_id}`));
    let openersMarked = 0;
    for (const r of rows) {
      const k = `${r.fight_id}|${r.fighter_id}|${r.book_id}`;
      if (!hasOpener.has(k)) {
        r.is_opener = true;
        hasOpener.add(k); // one opener per combo per run
        openersMarked++;
      }
    }
    if (openersMarked) console.log(`[openers] marking ${openersMarked} first-capture row(s) as openers`);

    if (DRY_RUN) {
      console.log(`[dry-run] would insert ${rows.length} row(s) across ${matchedFights} fight(s). Sample:`);
      for (const r of rows.slice(0, 12)) {
        console.log(`  fight ${r.fight_id} side ${r.side} book ${r.book_id} ${r.american_odds > 0 ? '+' : ''}${r.american_odds} (p=${r.implied_prob})`);
      }
      return;
    }

    // Snapshot insert (append-only, like the BFO cron). Chunk to stay safe.
    const CHUNK = 500;
    for (let i = 0; i < rows.length; i += CHUNK) {
      const { error: insErr } = await sb.from('fight_odds').insert(rows.slice(i, i + CHUNK));
      if (insErr) throw new Error(`fight_odds insert: ${insErr.message}`);
    }

    console.log(`[done] inserted ${rows.length} snapshot row(s) across ${matchedFights} fight(s) at ${captured_at}`);
  } catch (err) {
    console.error('[fetch-odds] failed:', err.message);
    process.exit(1);
  }
})();
