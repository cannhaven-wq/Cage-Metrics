// disc001-export.js — writes the DISC-001 DEV export.
//
// The recipe is research/factors/disc001_dev_export.sql; this file produces the
// same two outputs, byte for byte, through the REST API (the only route the CI
// runner has). The md5 of each output is printed so it can be checked against
// md5(string_agg(...)) of the SQL, run directly in the database.
//
// DEV ONLY. Events are read with event_date < 2025-01-01 at the source, every
// later read is keyed off those events' ids, and the script throws if a sealed
// date appears anyway. Prices are read only for DEV fight ids, so no sealed
// price leaves the database either.
//
//   SUPABASE_SERVICE_ROLE_KEY=... node build/disc001-export.js
//
// fight_odds is private to both browser roles, so the publishable key reads
// zero rows with no error. The script refuses to write an export with no
// prices rather than produce a market-free file.

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { createClient } = require('@supabase/supabase-js');

const SUPABASE_URL = process.env.SUPABASE_URL || 'https://uftancejftcryfvbggll.supabase.co';
const KEY = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY;
const DEV_END = '2025-01-01';
const OUT = path.join(__dirname, '..', 'research', 'experiments', 'DISC-001', 'data');
const PAGE = 1000;

const METHOD = {
  'KO/TKO': 'K', "TKO - Doctor's Stoppage": 'T', 'Submission': 'S',
  'Decision - Unanimous': 'U', 'Decision - Split': 'P', 'Decision - Majority': 'M',
  'Overturned': 'O', 'Could Not Continue': 'C', 'DQ': 'Q',
};

function chunks(arr, n) {
  const out = [];
  for (let i = 0; i < arr.length; i += n) out.push(arr.slice(i, i + n));
  return out;
}

// Pages with a stable order. An unordered .range() reads an unstable subset
// (T-027), which is how the Factor Lab once scored 869 fights instead of 1,220.
async function all(build) {
  const rows = [];
  for (let from = 0; ; from += PAGE) {
    const { data, error } = await build().range(from, from + PAGE - 1);
    if (error) throw new Error(error.message);
    rows.push(...data);
    if (data.length < PAGE) return rows;
  }
}

const s = (v) => (v === null || v === undefined ? '' : String(v));
const b = (v) => (v === null || v === undefined ? '' : (v ? '1' : '0'));
const md5 = (t) => crypto.createHash('md5').update(t, 'utf8').digest('hex');

async function main() {
  if (!KEY) throw new Error('SUPABASE_SERVICE_ROLE_KEY is not set: fight_odds would read as empty');
  const sb = createClient(SUPABASE_URL, KEY, { auth: { persistSession: false, autoRefreshToken: false } });

  const events = await all(() => sb.from('events').select('id,event_date').lt('event_date', DEV_END).order('id'));
  const dateOf = new Map(events.map((e) => [e.id, e.event_date]));
  for (const e of events) if (!(e.event_date < DEV_END)) throw new Error(`sealed event ${e.id}`);

  const cols = 'id,event_id,fighter_a_id,fighter_b_id,winner_id,method,end_round,end_time,' +
    'scheduled_rounds,is_title_fight,is_main_event,a_kd,b_kd,is_active';
  const fightsAll = [];
  for (const ids of chunks(events.map((e) => e.id), 100)) {
    fightsAll.push(...await all(() => sb.from('fights').select(cols).in('event_id', ids).order('id')));
  }

  const fights = fightsAll.filter((f) => f.fighter_a_id !== null && f.fighter_b_id !== null && f.is_active !== false);

  const books = await all(() => sb.from('odds_books').select('id,name').ilike('name', 'BFO%').order('id'));
  if (!books.length) throw new Error('no BFO book found');
  const bfo = books.map((x) => x.id);

  const price = new Map(); // fight_id -> { a, b }
  const byId = new Map(fights.map((f) => [f.id, f]));
  for (const ids of chunks(fights.map((f) => f.id), 150)) {
    const rows = await all(() => sb.from('fight_odds').select('id,fight_id,fighter_id,american_odds')
      .in('fight_id', ids).in('book_id', bfo).eq('is_closer', true).order('id'));
    for (const r of rows) {
      const f = byId.get(r.fight_id);
      const p = price.get(r.fight_id) || { a: null, b: null };
      if (r.fighter_id === f.fighter_a_id && r.american_odds !== null) p.a = p.a === null ? r.american_odds : Math.max(p.a, r.american_odds);
      if (r.fighter_id === f.fighter_b_id && r.american_odds !== null) p.b = p.b === null ? r.american_odds : Math.max(p.b, r.american_odds);
      price.set(r.fight_id, p);
    }
  }
  if (!price.size) throw new Error('zero BFO closers read: wrong key or a policy change; refusing to write');

  fights.sort((x, y) => {
    const dx = dateOf.get(x.event_id), dy = dateOf.get(y.event_id);
    return dx < dy ? -1 : dx > dy ? 1 : (x.event_id - y.event_id) || (x.id - y.id);
  });

  const lines = fights.map((f) => {
    const res = f.winner_id === f.fighter_a_id ? 'A'
      : f.winner_id === f.fighter_b_id ? 'B'
      : /^decision/i.test(f.method || '') ? 'D' : 'N';
    const m = METHOD[f.method] || 'X';
    const t = /^\d+:\d{2}$/.test(f.end_time || '') ? f.end_time.split(':') : null;
    const secs = t ? parseInt(t[0], 10) * 60 + parseInt(t[1], 10) : null;
    const p = price.get(f.id) || { a: null, b: null };
    return [f.id, f.event_id, dateOf.get(f.event_id), f.fighter_a_id, f.fighter_b_id, res, m,
      s(f.end_round), s(secs), s(f.scheduled_rounds), b(f.is_title_fight), b(f.is_main_event),
      s(f.a_kd), s(f.b_kd), s(p.a), s(p.b)].join(',');
  });
  const fightsCsv = lines.join('\n');

  const fighterIds = [...new Set(fightsAll.flatMap((f) => [f.fighter_a_id, f.fighter_b_id]).filter((x) => x !== null))];
  const fighters = [];
  for (const ids of chunks(fighterIds, 200)) {
    fighters.push(...await all(() => sb.from('fighters').select('id,dob').in('id', ids).order('id')));
  }
  fighters.sort((x, y) => x.id - y.id);
  const fightersCsv = fighters.map((f) => `${f.id},${s(f.dob)}`).join('\n');

  for (const line of lines) if (!(line.split(',')[2] < DEV_END)) throw new Error(`sealed row: ${line}`);

  fs.mkdirSync(OUT, { recursive: true });
  fs.writeFileSync(path.join(OUT, 'dev_fights.csv'), fightsCsv + '\n');
  fs.writeFileSync(path.join(OUT, 'dev_fighters.csv'), fightersCsv + '\n');
  console.log(`dev_fights.csv   ${lines.length} rows, ${price.size} with a BFO closer, md5 ${md5(fightsCsv)}`);
  console.log(`dev_fighters.csv ${fighters.length} rows, md5 ${md5(fightersCsv)}`);
}

main().then(() => process.exit(0), (e) => { console.error(e.message); process.exit(1); });
