// build/fight-week-data.js — data access for the Event Hub, fight pages and
// the digest templates. Reads the same public views the browser reads
// (fight_week_views.sql), with the publishable anon key. Nothing here
// computes a prediction: the CFL number comes from v_fight_locked_forecast,
// which is the locked pre-fight record and nothing else.

const fs = require('fs');
const path = require('path');
const core = require('../fight-week-core');

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

// Best-effort read: a missing view (e.g. fight_week_views.sql not yet applied)
// degrades to "no data" instead of failing the whole prerender.
async function safe(query, label) {
  try {
    const { data, error } = await query;
    if (error) { console.warn(`[fight-week] ${label} skipped: ${error.message}`); return []; }
    return data || [];
  } catch (e) {
    console.warn(`[fight-week] ${label} threw: ${e.message}`);
    return [];
  }
}

const byKey = (rows, k) => { const m = {}; rows.forEach(r => { m[r[k]] = r; }); return m; };

// Every event that has at least one locked forecast, newest first. These are
// the events that get a full Event Hub page at their /e/ URL — forever.
async function eventsWithRecord(sb) {
  const fc = await safe(sb.from('v_fight_locked_forecast').select('event_id'), 'locked forecast events');
  const ids = [...new Set(fc.map(r => r.event_id).filter(Boolean))];
  if (!ids.length) return [];
  const events = await fetchAll(() => sb.from('events')
    .select('id, name, event_date, location, is_upcoming')
    .in('id', ids));
  return events.sort((a, b) => (a.event_date < b.event_date ? 1 : -1));
}

// The card the site is "about" right now: the soonest upcoming event that has
// a locked forecast; else the most recent event with one (the latest graded
// card — the homepage's fallback).
function pickCurrent(eventsWithRec, todayStr) {
  const t = todayStr || new Date().toISOString().slice(0, 10);
  const upcoming = eventsWithRec.filter(e => e.event_date >= t).sort((a, b) => (a.event_date < b.event_date ? -1 : 1));
  if (upcoming.length) return { event: upcoming[0], phase: 'upcoming' };
  const past = eventsWithRec.filter(e => e.event_date < t);
  return past.length ? { event: past[0], phase: 'graded' } : { event: null, phase: 'none' };
}

// Everything the hub / fight pages / digest need for one event.
async function loadCard(sb, event) {
  const fights = await fetchAll(() => sb.from('fights')
    .select('*')
    .eq('event_id', event.id));
  const fightIds = fights.map(f => f.id);
  if (!fightIds.length) return { event, fights: [], rows: [], byBook: {}, fighters: {} };

  const [forecasts, market, atLock, byBookRows] = await Promise.all([
    safe(sb.from('v_fight_locked_forecast').select('*').in('fight_id', fightIds), 'locked forecasts'),
    safe(sb.from('v_fight_market_vigfree').select('*').in('fight_id', fightIds), 'vig-free market'),
    safe(sb.from('v_fight_market_at_lock').select('*').in('fight_id', fightIds), 'market at lock'),
    safe(sb.from('v_fight_odds_latest_by_book').select('*').in('fight_id', fightIds), 'latest by book'),
  ]);

  const rows = core.assembleCard(event, fights, byKey(forecasts, 'fight_id'), byKey(market, 'fight_id'), byKey(atLock, 'fight_id'));
  const byBook = {};
  byBookRows.forEach(r => { (byBook[r.fight_id] = byBook[r.fight_id] || []).push(r); });

  const fighterIds = [...new Set(fights.flatMap(f => [f.fighter_a_id, f.fighter_b_id]).filter(Boolean))];
  const fighterRows = fighterIds.length
    ? await safe(sb.from('fighters')
        .select('id, name, nickname, age, height_in, reach_in, stance, wins, losses, draws, ufc_wins, ufc_losses, ufc_draws, slpm, sapm, td_avg, td_acc, td_def, country')
        .in('id', fighterIds), 'fighters')
    : [];

  return { event, fights, rows, byBook, fighters: byKey(fighterRows, 'id') };
}

// One related Factor Lab finding, from the build's own factor-rates.json — the
// factor with the strongest market-controlled result. Nothing is recomputed.
function factorFinding(rootDir) {
  try {
    const p = path.join(rootDir || path.resolve(__dirname, '..'), 'factor-rates.json');
    const d = JSON.parse(fs.readFileSync(p, 'utf8'));
    const heads = (d.factors || []).map(f => ({ f, h: (f.buckets || []).find(b => b.headline) || (f.buckets || [])[0] }))
      .filter(x => x.h && x.h.even && x.h.all);
    if (!heads.length) return null;
    const real = heads.filter(x => x.h.verdict === 'real');
    const pickFrom = real.length ? real : heads;
    pickFrom.sort((x, y) => (y.h.even.pct || 0) - (x.h.even.pct || 0));
    const { f, h } = pickFrom[0];
    return {
      id: f.id,
      label: f.label,
      question: f.question,
      verdict: h.verdict,
      raw_pct: h.all.pct, raw_n: h.all.n,
      even_pct: h.even.pct, even_n: h.even.n,
      generated_at: d.generated_at,
      even_cohort: d.dataset && d.dataset.market_even_cohort,
    };
  } catch (e) {
    return null;
  }
}

module.exports = { fetchAll, safe, eventsWithRecord, pickCurrent, loadCard, factorFinding };
