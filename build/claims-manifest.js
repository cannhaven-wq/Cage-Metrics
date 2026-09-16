// Public claim manifest: every headline number the site quotes about its own
// record, computed from the database and written to data/claims.json.
//
// Why this exists: the homepage, Proof Center, About and Methodology used to
// carry typed-in figures ("3,288 fights / 61.6%", "12-5 live") that drifted
// from the tables behind them, and some of them quietly added the historical
// replay to the live record. Pages now read this file instead of carrying a
// number in prose, and every claim says exactly where it came from.
//
// Rules the manifest enforces:
//   - Historical replay and live results are SEPARATE claims. Nothing here
//     adds them together, and nothing on the site should either.
//   - Every claim names its source (table/view + filter) and its model.
//   - kind is 'historical_replay' or 'live'. Pages label them
//     "Engine v2 historical replay" and "Live record".
//   - as_of is when the number was pulled, and the pages print it.
//
// Runs in .github/workflows/prerender.yml (`npm run claims`) on the same
// 6-hour cron as the stubs, and commits data/claims.json back to main.
//
// The graded views are readable with the publishable key, same as the site.
// The closing-favorite benchmark needs fight_odds, which has no anon SELECT
// policy, so it is only recomputed when SUPABASE_SERVICE_ROLE_KEY (or
// SUPABASE_SECRET_KEY) is set; without it the previous value is carried over
// with its old as_of so the page still shows an honest date.

const fs = require('fs');
const path = require('path');
const { createClient } = require('@supabase/supabase-js');

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SUPABASE_ANON_KEY = 'sb_publishable_boJGOA1CFN-SF14HHFGUAw_YEEm0DU8';
const SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SECRET_KEY || null;

const ROOT = path.resolve(__dirname, '..');
const OUT = path.join(ROOT, 'data', 'claims.json');

// One engine family publishes to model_picks / model_edges. The replay rows
// are all engine_v2; live rows span engine_v1 and engine_v2 and are graded
// as one family (see CLAUDE.md: never filter the family by model_version).
const REPLAY_MODEL = 'engine_v2';
const LIVE_MODEL = 'engine (v1+v2 live family)';

const sb = createClient(SUPABASE_URL, SERVICE_KEY || SUPABASE_ANON_KEY);

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

const pct1 = x => (100 * x).toFixed(1) + '%';
const fmtInt = n => Number(n).toLocaleString('en-US');
const fmtMoney = n => (n < 0 ? '-$' : '+$') + fmtInt(Math.abs(Math.round(n)));

// Net result of a flat $100 bet at American odds.
function flat100(won, american) {
  if (won == null || american == null) return null;
  if (!won) return -100;
  return american > 0 ? american : 10000 / Math.abs(american);
}
// Decimal profit multiple (per $1 staked) at American odds.
function profitMult(american) {
  return american > 0 ? american / 100 : 100 / Math.abs(american);
}

function accuracyClaim({ id, label, rows, kind, model, source, extra }) {
  const graded = rows.filter(r => r.hit === true || r.hit === false);
  const hits = graded.filter(r => r.hit === true).length;
  const pending = rows.length - graded.length;
  const dates = graded.map(r => r.event_date).filter(Boolean).sort();
  return {
    id, label, kind,
    value: graded.length ? +(100 * hits / graded.length).toFixed(1) : null,
    display: graded.length ? pct1(hits / graded.length) : '—',
    sample_size: graded.length,
    hits, misses: graded.length - hits, pending,
    first_event: dates[0] || null,
    last_event: dates[dates.length - 1] || null,
    model_id: model,
    source,
    ...(extra || {}),
  };
}

function edgeClaim({ id, label, rows, kind, model, source, priceField, priceLabel }) {
  const graded = rows.filter(r => r.won === true || r.won === false);
  const wins = graded.filter(r => r.won === true).length;
  const losses = graded.length - wins;
  const pending = rows.length - graded.length;
  // Flat $100 on every graded bet, at the named price. Bets with no price on
  // record are excluded from the money figure (but still count in the W-L).
  const priced = graded.filter(r => r[priceField] != null);
  const pnl = priced.reduce((s, r) => s + flat100(r.won, r[priceField]), 0);
  // Edge-sized: stake_frac is the engine's suggested fraction; return per
  // dollar staked across the whole run.
  const sized = priced.filter(r => r.stake_frac != null && +r.stake_frac > 0);
  const sizedStake = sized.reduce((s, r) => s + (+r.stake_frac), 0);
  const sizedRet = sized.reduce((s, r) => s + (+r.stake_frac) * (r.won ? profitMult(r[priceField]) : -1), 0);
  const dates = graded.map(r => r.event_date).filter(Boolean).sort();
  return {
    id, label, kind,
    value: `${wins}-${losses}`,
    display: `${wins}-${losses}`,
    sample_size: graded.length,
    wins, losses, pending,
    win_rate_pct: graded.length ? +(100 * wins / graded.length).toFixed(1) : null,
    flat_100_pnl: priced.length ? Math.round(pnl) : null,
    flat_100_pnl_display: priced.length ? fmtMoney(pnl) : '—',
    flat_100_roi_pct: priced.length ? +(100 * pnl / (100 * priced.length)).toFixed(1) : null,
    priced_bets: priced.length,
    price_basis: priceLabel,
    sized_roi_pct: sizedStake > 0 ? +(100 * sizedRet / sizedStake).toFixed(1) : null,
    first_event: dates[0] || null,
    last_event: dates[dates.length - 1] || null,
    model_id: model,
    source,
  };
}

// Closing-favorite benchmark on the replay fights: how often did the fighter
// the market closed as the favorite win, and how did the engine do on the
// same fights. Needs fight_odds (service key). Returns null when it can't run.
async function favoriteBenchmark(replayRows) {
  if (!SERVICE_KEY) return null;
  const graded = replayRows.filter(r => r.hit === true || r.hit === false);
  const byFight = new Map(graded.map(r => [r.fight_id, r]));
  // Chunk the id filter — a single .in() over ~3,000 ids overflows the URL.
  const ids = [...byFight.keys()];
  const closers = [];
  for (let i = 0; i < ids.length; i += 300) {
    const chunk = ids.slice(i, i + 300);
    closers.push(...await fetchAll(() => sb
      .from('fight_odds')
      .select('fight_id, fighter_id, implied_prob')
      .eq('is_closer', true)
      .in('fight_id', chunk)));
  }
  // Average each side's closing implied probability across books.
  const agg = {};
  for (const o of closers) {
    if (!byFight.has(o.fight_id) || o.implied_prob == null) continue;
    const f = agg[o.fight_id] || (agg[o.fight_id] = {});
    const s = f[o.fighter_id] || (f[o.fighter_id] = { sum: 0, n: 0 });
    s.sum += +o.implied_prob; s.n += 1;
  }
  let n = 0, favWins = 0, engineHits = 0;
  for (const [fightId, sides] of Object.entries(agg)) {
    const ids = Object.keys(sides);
    if (ids.length !== 2) continue;
    const [a, b] = ids.map(id => ({ id: +id, p: sides[id].sum / sides[id].n }));
    if (a.p === b.p) continue; // pick'em — no favorite to back
    const fav = a.p > b.p ? a.id : b.id;
    const row = byFight.get(+fightId);
    n += 1;
    if (row.winner_id === fav) favWins += 1;
    if (row.hit === true) engineHits += 1;
  }
  if (!n) return null;
  return {
    id: 'market_favorite_replay_accuracy',
    label: 'Closing favorite · straight-up accuracy on the same replay fights',
    kind: 'historical_replay',
    value: +(100 * favWins / n).toFixed(1),
    display: pct1(favWins / n),
    sample_size: n,
    hits: favWins,
    engine_accuracy_same_fights_pct: +(100 * engineHits / n).toFixed(1),
    engine_accuracy_same_fights_display: pct1(engineHits / n),
    model_id: 'market (closing consensus)',
    source: "fight_odds WHERE is_closer = true, averaged per side, joined to v_model_picks_graded WHERE source='backtest'; pick'em lines excluded",
  };
}

async function main() {
  console.log(`[claims] key: ${SERVICE_KEY ? 'service' : 'publishable'}`);

  const picks = await fetchAll(() => sb.from('v_model_picks_graded')
    .select('fight_id, event_date, tier, source, model_version, hit, winner_id')
    .order('event_date', { ascending: true }).order('id', { ascending: true }));
  const edges = await fetchAll(() => sb.from('v_model_edges_graded')
    .select('fight_id, event_date, source, model_version, won, stake_frac, odds_at_publish, closing_odds')
    .order('event_date', { ascending: true }).order('id', { ascending: true }));
  console.log(`[claims] ${picks.length} pick rows, ${edges.length} edge rows.`);

  const replayPicks = picks.filter(r => r.source === 'backtest');
  const livePicks = picks.filter(r => r.source === 'live');
  const replayEdges = edges.filter(r => r.source === 'backtest');
  const liveEdges = edges.filter(r => r.source === 'live');

  const liveVersions = [...new Set(livePicks.map(r => r.model_version).filter(Boolean))].sort();
  const replayVersions = [...new Set(replayPicks.map(r => r.model_version).filter(Boolean))].sort();
  if (replayVersions.length !== 1 || replayVersions[0] !== REPLAY_MODEL) {
    console.warn(`[claims] replay rows carry model_version ${JSON.stringify(replayVersions)}; labeled as ${REPLAY_MODEL}.`);
  }

  const countOf = async table => {
    const { count, error } = await sb.from(table).select('id', { count: 'exact', head: true });
    if (error) throw error;
    return count;
  };
  const liveCounts = { fighters: await countOf('fighters'), events: await countOf('events'), fights: await countOf('fights') };
  const fightCount = liveCounts.fights;

  const claims = [];

  claims.push(accuracyClaim({
    id: 'engine_replay_accuracy',
    label: 'Engine v2 historical replay · straight-up accuracy',
    rows: replayPicks, kind: 'historical_replay', model: REPLAY_MODEL,
    source: "v_model_picks_graded WHERE source='backtest' AND hit IS NOT NULL",
  }));
  claims.push(accuracyClaim({
    id: 'engine_replay_locks',
    label: 'Engine v2 historical replay · Lock-tier accuracy',
    rows: replayPicks.filter(r => r.tier === 'Lock'), kind: 'historical_replay', model: REPLAY_MODEL,
    source: "v_model_picks_graded WHERE source='backtest' AND tier='Lock' AND hit IS NOT NULL",
  }));
  claims.push(edgeClaim({
    id: 'value_replay_record',
    label: 'Engine v2 historical replay · Value bets, graded at the closing price',
    rows: replayEdges, kind: 'historical_replay', model: REPLAY_MODEL,
    source: "v_model_edges_graded WHERE source='backtest' AND won IS NOT NULL",
    priceField: 'closing_odds', priceLabel: 'closing price (closing_odds)',
  }));

  claims.push(accuracyClaim({
    id: 'engine_live_accuracy',
    label: 'Live record · straight-up accuracy',
    rows: livePicks, kind: 'live', model: LIVE_MODEL,
    source: "v_model_picks_graded WHERE source='live' AND hit IS NOT NULL",
    extra: { model_versions_present: liveVersions },
  }));
  claims.push(accuracyClaim({
    id: 'engine_live_locks',
    label: 'Live record · Lock-tier accuracy',
    rows: livePicks.filter(r => r.tier === 'Lock'), kind: 'live', model: LIVE_MODEL,
    source: "v_model_picks_graded WHERE source='live' AND tier='Lock' AND hit IS NOT NULL",
  }));
  claims.push(edgeClaim({
    id: 'value_live_record',
    label: 'Live record · Value flags, graded at the price posted',
    rows: liveEdges, kind: 'live', model: LIVE_MODEL,
    source: "v_model_edges_graded WHERE source='live' AND won IS NOT NULL",
    priceField: 'odds_at_publish', priceLabel: 'price at publish (odds_at_publish)',
  }));

  const liveDates = livePicks.map(r => r.event_date).filter(Boolean).sort();
  claims.push({
    id: 'live_since',
    label: 'Live record · first card on record',
    kind: 'live',
    value: liveDates[0] || null,
    display: liveDates[0]
      ? new Date(liveDates[0] + 'T00:00:00Z').toLocaleDateString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' })
      : '—',
    sample_size: livePicks.length,
    model_id: LIVE_MODEL,
    source: "MIN(event_date) FROM v_model_picks_graded WHERE source='live'",
  });

  claims.push({
    id: 'fights_in_database',
    label: 'Fights in the database',
    kind: 'live',
    value: fightCount,
    display: fmtInt(fightCount),
    sample_size: fightCount,
    model_id: null,
    source: 'COUNT(*) FROM fights',
  });

  // Favorite benchmark: recompute with the service key, else carry the last
  // published value forward (with its own as_of) rather than drop it.
  const now = new Date().toISOString();
  let prev = null;
  try { prev = JSON.parse(fs.readFileSync(OUT, 'utf8')); } catch (_) { /* first run */ }
  const fav = await favoriteBenchmark(replayPicks);
  if (fav) {
    claims.push({ ...fav, as_of: now });
  } else {
    const old = prev && prev.claims && (Array.isArray(prev.claims)
      ? prev.claims.find(c => c.id === 'market_favorite_replay_accuracy')
      : prev.claims.market_favorite_replay_accuracy);
    if (old) {
      console.warn('[claims] no service key — carrying market_favorite_replay_accuracy forward from ' + old.as_of);
      claims.push({ ...old, status: 'STALE' });
    } else {
      console.warn('[claims] no service key and no prior value — market_favorite_replay_accuracy omitted.');
    }
  }

  for (const c of claims) {
    if (!c.as_of) c.as_of = now;
    // VERIFIED = pulled from the named source this run. STALE = carried over
    // from a previous run because the source wasn't reachable (see above).
    if (!c.status) c.status = 'VERIFIED';
  }

  // Two composite views of the same numbers, for consumers that want the
  // whole record split in one read. Still never added together.
  const byId = {};
  for (const c of claims) byId[c.id] = c;
  const pick = (id, fields) => Object.fromEntries(fields.map(k => [k, byId[id] ? byId[id][k] : null]));
  byId.historical_simulation = {
    id: 'historical_simulation',
    label: 'Engine v2 historical replay (composite)',
    kind: 'historical_replay',
    value: {
      accuracy: pick('engine_replay_accuracy', ['value', 'display', 'sample_size', 'hits', 'misses']),
      locks: pick('engine_replay_locks', ['value', 'display', 'sample_size', 'hits', 'misses']),
      value_bets: pick('value_replay_record', ['value', 'display', 'sample_size', 'wins', 'losses', 'flat_100_pnl', 'flat_100_pnl_display', 'sized_roi_pct', 'price_basis']),
      closing_favorite: pick('market_favorite_replay_accuracy', ['value', 'display', 'sample_size', 'engine_accuracy_same_fights_pct']),
    },
    display: byId.engine_replay_accuracy.display,
    sample_size: byId.engine_replay_accuracy.sample_size,
    model_id: REPLAY_MODEL,
    source: 'composite of engine_replay_accuracy, engine_replay_locks, value_replay_record, market_favorite_replay_accuracy',
    status: byId.market_favorite_replay_accuracy && byId.market_favorite_replay_accuracy.status === 'STALE' ? 'STALE' : 'VERIFIED',
    as_of: now,
  };
  byId.live_published = {
    id: 'live_published',
    label: 'Live record (composite)',
    kind: 'live',
    value: {
      accuracy: pick('engine_live_accuracy', ['value', 'display', 'sample_size', 'hits', 'misses', 'pending']),
      locks: pick('engine_live_locks', ['value', 'display', 'sample_size', 'hits', 'misses', 'pending']),
      value_flags: pick('value_live_record', ['value', 'display', 'sample_size', 'wins', 'losses', 'pending', 'flat_100_pnl', 'flat_100_pnl_display', 'price_basis']),
      since: byId.live_since.value,
    },
    display: byId.engine_live_accuracy.display,
    sample_size: byId.engine_live_accuracy.sample_size,
    model_id: LIVE_MODEL,
    source: 'composite of engine_live_accuracy, engine_live_locks, value_live_record, live_since',
    status: 'VERIFIED',
    as_of: now,
  };

  const manifest = {
    generated_at: now,
    note: 'Historical replay and live results are separate claims. Never add them together. Pages label kind=historical_replay as "Engine v2 historical replay" and kind=live as "Live record". status: VERIFIED = pulled from source this run; STALE = carried forward from an earlier run.',
    live_counts: liveCounts,
    claims: byId,
  };

  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(manifest, null, 2) + '\n');
  for (const c of Object.values(byId)) console.log(`  ${c.id.padEnd(34)} ${String(c.display).padEnd(10)} n=${c.sample_size}  [${c.kind}] ${c.status}`);
  console.log(`[claims] wrote ${path.relative(ROOT, OUT)}`);
}

main().catch(err => { console.error('[claims] failed:', err); process.exit(1); });
