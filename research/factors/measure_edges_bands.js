// T-024 / T-H — remeasure the exact bands edges.js publishes, under market control.
//
// READ-ONLY. Issues SELECTs and writes one JSON file under research/factors/.
// It touches no production surface, no migration, and no append-only table.
//
// WHY THIS EXISTS
//
// edges.js assigns hardcoded win rates to its factors:
//
//     recordEdge   gap >= 0.08 -> 60%, >= 0.15 -> 65%, >= 0.25 -> 70%, >= 0.40 -> 72%
//     tdDefEdge    gap >= 10   -> 52.5%, >= 20 -> 54%, >= 30 -> 56%
//
// Those constants trace to no artifact. CFL_RESEARCH_STATE.md's rule is that a
// number does not appear on a CFL surface unless it can be traced to an
// artifact named there, and edges.html publishes both ranges as "Active".
//
// factor-rates.json already measures similar factors at ITS OWN band edges and
// disagrees: UFC record reads 55.1% market-even (CI 46.8-63.3) against a
// claimed 60-72%, and takedown defence reads 49.3% (CI 43.7-55.0) against a
// claimed 52-56%. But those are not the same bands, so the comparison is
// suggestive rather than decisive. This script closes that gap by scoring
// edges.js's OWN trigger conditions and OWN band edges.
//
// METHOD — identical to build/factor-rates.js, deliberately
//
//   * Point-in-time. Fights are walked in chronological order and each result
//     is folded into both fighters' state only AFTER that fight is scored.
//     Career totals off the `fighters` table are never used: they contain the
//     result being predicted, and that bug was live once and inflated the
//     record factor to 75.5%.
//   * Market control. A fight counts in the `even` cohort only when neither
//     side closed outside +/-EVEN_BAND. A factor that is strong raw and
//     collapses under market control was reading the favourite, not the fight.
//   * Wilson intervals, which behave at small n.
//   * The same verdict ladder: real / inverted / lean / proxy / unproven /
//     insufficient.
//
// TWO SUBSTITUTIONS, BOTH DELIBERATE AND BOTH STATED IN THE OUTPUT
//
//   1. edges.js reads `fighters.wins` / `fighters.losses` — PRO record,
//      present-day, including bouts outside the UFC. There is no point-in-time
//      pro record in this database, so this script applies edges.js's smoothing
//      and bands to the point-in-time UFC record instead. The rule is
//      edges.js's; the underlying record is the only honest one available.
//      For a LIVE pick, reading present-day career totals is legitimate — the
//      fight has not happened. For any backtest it is leakage, which is why
//      this substitution is not optional.
//
//   2. edges.js reads `fighters.td_def` and `fighters.td_avg` — again
//      present-day career figures. Both are rebuilt point-in-time here from
//      prior fights only.
//
// Everything else — the 0.08 trigger, the Laplace +2/+4 smoothing, the
// four record bands, the 10-point trigger, the three td_def bands and the
// willHaveWrestling gate at td_avg >= 1.0 — is edges.js's, copied exactly.
//
// USAGE
//
//   SUPABASE_SECRET_KEY=... node research/factors/measure_edges_bands.js
//
// fight_odds has no SELECT policy for `anon`, so the publishable key returns
// zero rows with no error. The script refuses to write a result in that case
// rather than publish a confidently empty market column — same guard, and the
// same reasoning, as build/factor-rates.js.

'use strict';

const fs = require('fs');
const path = require('path');

// ---------------------------------------------------------------- constants
// Lifted from build/factor-rates.js. Changing one here and not there makes the
// two artifacts incomparable, which is the whole point of the exercise.
const MIN_SAMPLE = 100;
const LEAN_PCT = 55;
const EVEN_BAND = 140;
const MIN_TD_ATTEMPTS = 5;

// Lifted from edges.js. These are the numbers under test.
const RECORD_MIN_COMBINED_FIGHTS = 3;
const RECORD_TRIGGER = 0.08;
const RECORD_BANDS = [
  { label: '0.08-0.15 gap', lo: 0.08, hi: 0.15, claimed: 60.0 },
  { label: '0.15-0.25 gap', lo: 0.15, hi: 0.25, claimed: 65.0 },
  { label: '0.25-0.40 gap', lo: 0.25, hi: 0.40, claimed: 70.0 },
  { label: '0.40+ gap', lo: 0.40, hi: 999, claimed: 72.0 },
];

const TD_TRIGGER = 10;
const TD_BANDS = [
  { label: '10-20 point gap', lo: 10, hi: 20, claimed: 52.5 },
  { label: '20-30 point gap', lo: 20, hi: 30, claimed: 54.0 },
  { label: '30+ point gap', lo: 30, hi: 999, claimed: 56.0 },
];
const TD_LOW = 1.0; // STYLE_THRESHOLDS.TD_LOW — the willHaveWrestling gate

// The age rule edges.js retired on 2026-05-17, restated so it can be scored on
// the same footing as the two factors that survived it.
const AGE_TRIGGER = 1;
const AGE_BANDS = [
  { label: '1-2 years younger', lo: 1, hi: 2 },
  { label: '3-4 years younger', lo: 2, hi: 4 },
  { label: '5-6 years younger', lo: 4, hi: 6 },
  { label: '7+ years younger', lo: 6, hi: 999 },
];

// ------------------------------------------------------------------- stats
function wilson(wins, n) {
  if (!n) return [0, 0];
  const z = 1.959963985;
  const p = wins / n;
  const d = 1 + (z * z) / n;
  const c = p + (z * z) / (2 * n);
  const s = z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n));
  return [(100 * (c - s)) / d, (100 * (c + s)) / d];
}

function rate(wins, n) {
  if (!n) return null;
  const [lo, hi] = wilson(wins, n);
  return {
    n,
    wins,
    pct: +((100 * wins) / n).toFixed(1),
    ci_lo: +lo.toFixed(1),
    ci_hi: +hi.toFixed(1),
  };
}

// The same ladder build/factor-rates.js publishes, so the two artifacts can be
// read side by side without translating verdicts.
function verdictFor(all, even) {
  if (!all || all.n < MIN_SAMPLE) return 'insufficient';
  if (!even || even.n < MIN_SAMPLE) return 'unproven';
  if (even.ci_lo > 50) return 'real';
  if (even.ci_hi < 50) return 'inverted';
  if (even.pct >= LEAN_PCT) return 'lean';
  return 'proxy';
}

// Does the claimed rate sit inside the measured market-even interval? This is
// the question the whole script exists to answer, so it is computed rather
// than left to a reader eyeballing two columns.
function claimVerdict(claimed, even) {
  if (claimed == null) return null;
  if (!even || even.n < MIN_SAMPLE) return 'untested';
  if (claimed < even.ci_lo) return 'claim_below_interval';
  if (claimed > even.ci_hi) return 'claim_above_interval';
  return 'claim_inside_interval';
}

// ---------------------------------------------------------------- helpers
const fightMinutes = (f) => {
  const r = f.end_round == null ? null : Number(f.end_round);
  if (!r) return null;
  let secs = (r - 1) * 300;
  if (f.end_time) {
    const [m, s] = String(f.end_time).split(':').map(Number);
    if (!Number.isNaN(m)) secs += m * 60 + (Number.isNaN(s) ? 0 : s);
  } else {
    secs += 300;
  }
  return secs / 60;
};

const ageAt = (fighter, date) => {
  if (!fighter || !fighter.dob || !date) return null;
  const d = new Date(date);
  const b = new Date(fighter.dob);
  if (Number.isNaN(d) || Number.isNaN(b)) return null;
  let a = d.getFullYear() - b.getFullYear();
  const m = d.getMonth() - b.getMonth();
  if (m < 0 || (m === 0 && d.getDate() < b.getDate())) a -= 1;
  return a;
};

const median = (arr) => {
  if (!arr || !arr.length) return null;
  const s = [...arr].sort((x, y) => x - y);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
};

// ------------------------------------------------- the rules under test
// Each returns { gap, pickId } or null when the factor does not fire.
// These mirror edges.js exactly; the tests pin them against hand-worked cases.

// edges.js: aRate = (aw + 2) / (aTotal + 4)
const smoothed = (wins, fights) => (wins + 2) / (fights + 4);

function recordRule(m) {
  const sA = m.sA;
  const sB = m.sB;
  if (sA.fights + sB.fights < RECORD_MIN_COMBINED_FIGHTS) return null;
  const aRate = smoothed(sA.wins, sA.fights);
  const bRate = smoothed(sB.wins, sB.fights);
  const gap = Math.abs(aRate - bRate);
  if (gap < RECORD_TRIGGER) return null;
  return { gap, pickId: aRate > bRate ? m.a.id : m.b.id };
}

const tdDefOf = (s) =>
  (s && s.td_faced >= MIN_TD_ATTEMPTS ? 100 * (1 - s.td_conceded / s.td_faced) : null);

// td_avg is takedowns landed per 15 minutes, the same unit fighters.td_avg uses.
const tdAvgOf = (s) => (s && s.minutes > 0 ? (s.td_landed / s.minutes) * 15 : null);

function willHaveWrestling(sA, sB) {
  const a = tdAvgOf(sA) == null ? 0 : tdAvgOf(sA);
  const b = tdAvgOf(sB) == null ? 0 : tdAvgOf(sB);
  return a >= TD_LOW || b >= TD_LOW;
}

function tdDefRule(m, applyWrestlingGate) {
  const da = tdDefOf(m.sA);
  const db = tdDefOf(m.sB);
  if (da == null || db == null) return null;
  if (applyWrestlingGate && !willHaveWrestling(m.sA, m.sB)) return null;
  const gap = Math.abs(da - db);
  if (gap < TD_TRIGGER) return null;
  return { gap, pickId: da > db ? m.a.id : m.b.id };
}

function ageRule(m) {
  if (m.ageA == null || m.ageB == null) return null;
  const gap = Math.abs(m.ageA - m.ageB);
  if (gap < AGE_TRIGGER) return null;
  return { gap, pickId: m.ageA < m.ageB ? m.a.id : m.b.id };
}

// ------------------------------------------------------------- scoring
// One factor -> a headline row plus one row per band. `bands` may carry a
// `claimed` rate, in which case the claim is tested against the interval.
function scoreFactor(matchups, rule, bands) {
  const fired = [];
  for (const m of matchups) {
    const r = rule(m);
    if (r) fired.push({ m, gap: r.gap, correct: r.pickId === m.winner });
  }

  const tally = (rows) => {
    const all = { n: 0, w: 0 };
    const even = { n: 0, w: 0 };
    for (const row of rows) {
      all.n += 1;
      if (row.correct) all.w += 1;
      if (row.m.even) {
        even.n += 1;
        if (row.correct) even.w += 1;
      }
    }
    return { all: rate(all.w, all.n), even: rate(even.w, even.n) };
  };

  const head = tally(fired);
  const out = {
    headline: {
      label: 'Any gap the rule fires on',
      all: head.all,
      even: head.even,
      verdict: verdictFor(head.all, head.even),
    },
    bands: [],
  };

  for (const b of bands) {
    const rows = fired.filter((r) => r.gap >= b.lo && r.gap < b.hi);
    const t = tally(rows);
    out.bands.push({
      label: b.label,
      claimed_by_edges_js: b.claimed == null ? null : b.claimed,
      all: t.all,
      even: t.even,
      verdict: verdictFor(t.all, t.even),
      claim_verdict: claimVerdict(b.claimed, t.even),
    });
  }
  return out;
}

// ---------------------------------------------------------------- main
async function main() {
  // Required lazily so the pure functions above can be unit-tested with no
  // dependency installed and no network available.
  const { createClient } = require('@supabase/supabase-js');

  const SUPABASE_URL = process.env.SUPABASE_URL || 'https://uftancejftcryfvbggll.supabase.co';
  const SUPABASE_KEY = process.env.SUPABASE_SECRET_KEY
    || process.env.SUPABASE_SERVICE_ROLE_KEY
    || '';
  if (!SUPABASE_KEY) {
    throw new Error(
      'No SUPABASE_SECRET_KEY / SUPABASE_SERVICE_ROLE_KEY in the environment.\n'
      + 'fight_odds has no SELECT policy for anon, so the publishable key cannot '
      + 'read the market-control column and this measurement would be meaningless.',
    );
  }
  const sb = createClient(SUPABASE_URL, SUPABASE_KEY);

  const fetchAll = async (build) => {
    const out = [];
    const page = 1000;
    for (let from = 0; ; from += page) {
      const { data, error } = await build().range(from, from + page - 1);
      if (error) throw new Error(error.message);
      out.push(...data);
      if (data.length < page) break;
    }
    return out;
  };

  console.log('Pulling events, fights, fighters, closing odds ...');
  const [events, fights, fighters, odds] = await Promise.all([
    fetchAll(() => sb.from('events').select('id, event_date')),
    fetchAll(() => sb.from('fights').select(
      'id, event_id, fighter_a_id, fighter_b_id, winner_id, method, end_round, end_time, '
      + 'a_td_landed, b_td_landed, a_td_attempted, b_td_attempted')),
    fetchAll(() => sb.from('fighters').select('id, name, dob')),
    fetchAll(() => sb.from('fight_odds')
      .select('fight_id, fighter_id, american_odds, is_closer').eq('is_closer', true)),
  ]);
  console.log(`  events=${events.length} fights=${fights.length} `
    + `fighters=${fighters.length} closing-odds rows=${odds.length}`);

  if (odds.length === 0) {
    throw new Error('fight_odds returned 0 rows — the market-control column would be '
      + 'empty, so every band would publish as "unproven". Refusing to write.');
  }

  const matchups = buildMatchups({ events, fights, fighters, odds });
  console.log(`  scored matchups=${matchups.length} `
    + `market-even=${matchups.filter((m) => m.even).length}`);

  const result = {
    generated_at: new Date().toISOString(),
    purpose: 'T-024 — score edges.js\'s own trigger conditions and band edges under '
      + 'the market control build/factor-rates.js applies.',
    method: {
      point_in_time: true,
      even_band_american: EVEN_BAND,
      min_sample: MIN_SAMPLE,
      lean_pct: LEAN_PCT,
      interval: 'Wilson 95%',
      substitutions: [
        'edges.js reads present-day PRO record off the fighters table; this uses '
        + 'point-in-time UFC record, because a backtest against present-day career '
        + 'totals contains the result being predicted.',
        'edges.js reads present-day fighters.td_def and fighters.td_avg; both are '
        + 'rebuilt point-in-time from prior fights only.',
      ],
    },
    dataset: {
      fights_scored: matchups.length,
      market_even_cohort: matchups.filter((m) => m.even).length,
    },
    factors: {
      record: scoreFactor(matchups, recordRule, RECORD_BANDS),
      td_def_with_wrestling_gate: scoreFactor(
        matchups, (m) => tdDefRule(m, true), TD_BANDS,
      ),
      td_def_ungated: scoreFactor(matchups, (m) => tdDefRule(m, false), TD_BANDS),
      age_retired_rule: scoreFactor(matchups, ageRule, AGE_BANDS),
    },
  };

  const out = path.join(__dirname, 'edges_bands_measured.json');
  fs.writeFileSync(out, `${JSON.stringify(result, null, 2)}\n`);
  console.log(`Wrote ${out}`);
}

// Chronological walk with strictly-before state. Exported so the tests can
// drive it with fixtures instead of a database.
function buildMatchups({ events, fights, fighters, odds }) {
  const evDate = new Map(events.map((e) => [e.id, e.event_date]));
  const F = new Map(fighters.map((f) => [f.id, f]));

  const closeBook = new Map();
  for (const o of odds) {
    if (o.american_odds == null) continue;
    const k = `${o.fight_id}|${o.fighter_id}`;
    if (!closeBook.has(k)) closeBook.set(k, []);
    closeBook.get(k).push(o.american_odds);
  }
  const closeOf = (fightId, fighterId) => median(closeBook.get(`${fightId}|${fighterId}`));

  const dated = fights
    .map((f) => ({ f, date: evDate.get(f.event_id) }))
    .filter((x) => x.date)
    .sort((x, y) => (x.date < y.date ? -1 : x.date > y.date ? 1 : x.f.id - y.f.id));

  const state = new Map();
  const blank = () => ({ fights: 0, wins: 0, minutes: 0, td_landed: 0, td_faced: 0, td_conceded: 0 });
  const stateOf = (id) => {
    if (!state.has(id)) state.set(id, blank());
    return state.get(id);
  };

  const matchups = [];
  for (const { f, date } of dated) {
    const a = F.get(f.fighter_a_id);
    const b = F.get(f.fighter_b_id);

    if (a && b && f.winner_id != null) {
      const oa = closeOf(f.id, f.fighter_a_id);
      const ob = closeOf(f.id, f.fighter_b_id);
      matchups.push({
        id: f.id,
        date,
        a,
        b,
        winner: f.winner_id,
        ageA: ageAt(a, date),
        ageB: ageAt(b, date),
        sA: { ...stateOf(f.fighter_a_id) },
        sB: { ...stateOf(f.fighter_b_id) },
        even: oa != null && ob != null
          && oa >= -EVEN_BAND && oa <= EVEN_BAND
          && ob >= -EVEN_BAND && ob <= EVEN_BAND,
      });
    }

    // Fold in AFTER scoring. This ordering is the whole point-in-time guarantee.
    const mins = fightMinutes(f);
    for (const side of ['a', 'b']) {
      const fid = side === 'a' ? f.fighter_a_id : f.fighter_b_id;
      const oid = side === 'a' ? f.fighter_b_id : f.fighter_a_id;
      if (fid == null) continue;
      const s = stateOf(fid);
      s.fights += 1;
      if (f.winner_id === fid) s.wins += 1;
      if (mins) s.minutes += mins;
      const own = side === 'a' ? f.a_td_landed : f.b_td_landed;
      const oppLanded = side === 'a' ? f.b_td_landed : f.a_td_landed;
      const oppAtt = side === 'a' ? f.b_td_attempted : f.a_td_attempted;
      if (own != null) s.td_landed += Number(own) || 0;
      if (oppAtt != null) s.td_faced += Number(oppAtt) || 0;
      if (oppLanded != null) s.td_conceded += Number(oppLanded) || 0;
      void oid;
    }
  }
  return matchups;
}

const api = {
  MIN_SAMPLE, LEAN_PCT, EVEN_BAND,
  RECORD_TRIGGER, RECORD_BANDS, TD_TRIGGER, TD_BANDS, TD_LOW, AGE_BANDS,
  wilson, rate, verdictFor, claimVerdict,
  smoothed, recordRule, tdDefOf, tdAvgOf, willHaveWrestling, tdDefRule, ageRule,
  scoreFactor, buildMatchups, fightMinutes, ageAt, median,
};

if (require.main === module) {
  main().catch((err) => { console.error(err.message); process.exit(1); });
} else {
  module.exports = api;
}
