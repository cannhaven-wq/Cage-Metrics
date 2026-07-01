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
// returns the whole MMA slate at once. Free tier is 500/mo; the workflow runs
// every 2h (~360/mo) to stay well under budget.
// =============================================================================

const { createClient } = require('@supabase/supabase-js');

const ODDS_API_KEY = process.env.ODDS_API_KEY;
const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
// CI sets SUPABASE_SERVICE_ROLE_KEY; local Windows env uses SUPABASE_SECRET_KEY.
// Either works (both must be the legacy JWT service_role key to bypass RLS).
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SECRET_KEY;
const SOURCE_TAG = 'the-odds-api:mma_mixed_martial_arts';
// DRY_RUN=1 → fetch + match + build rows but DON'T write. For safe local testing.
const DRY_RUN = !!process.env.DRY_RUN;

if (!ODDS_API_KEY) {
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
// 1. Fetch raw odds from The Odds API (one request = whole MMA slate)
// -----------------------------------------------------------------------------

async function fetchOddsFromApi() {
  const url = 'https://api.the-odds-api.com/v4/sports/mma_mixed_martial_arts/odds' +
    '?regions=us&markets=h2h&oddsFormat=american&dateFormat=iso' +
    `&apiKey=${encodeURIComponent(ODDS_API_KEY)}`;

  const res = await fetch(url);
  console.log(`[odds-api] quota: used=${res.headers.get('x-requests-used')}, ` +
    `remaining=${res.headers.get('x-requests-remaining')}`);

  if (!res.ok) {
    throw new Error(`Odds API ${res.status} ${res.statusText}: ${await res.text()}`);
  }
  const events = await res.json();
  console.log(`[odds-api] got ${events.length} MMA events`);
  return events;
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
    .select('id, event_id, fighter_a_id, fighter_b_id, fighter_a_name, fighter_b_name')
    .in('event_id', ids);
  if (fErr) throw new Error(`fights fetch: ${fErr.message}`);
  console.log(`[supabase] ${fights ? fights.length : 0} candidate fights across ${events.length} events`);
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
// 4. Main: fetch, match, build per-book snapshot rows, insert
// -----------------------------------------------------------------------------

(async () => {
  try {
    const [oddsEvents, candidateFights] = await Promise.all([
      fetchOddsFromApi(),
      loadCandidateFights(),
    ]);

    const fightIndex = buildFightIndex(candidateFights);
    const bookId = await resolveBooks(oddsEvents);

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
      if (wrote > 0) matchedFights++;
    }

    if (unmatched.length) {
      console.warn(`[match] ${unmatched.length} Odds API event(s) had no fight in our DB (non-UFC promotions or name drift):`);
      for (const u of unmatched) console.warn('  - ' + u);
    }

    if (rows.length === 0) {
      console.log('[done] matched 0 fights — nothing to insert');
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
