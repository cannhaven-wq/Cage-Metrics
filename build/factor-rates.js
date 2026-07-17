// =============================================================================
// factor-rates.js — Historical Analysis engine
// =============================================================================
// Computes, for every edge factor, how often the favoured fighter actually won
// across UFC history — and writes it to ../factor-rates.json for stats.html.
//
//   npm run factor-rates          (from build/)
//
// Two rules govern this file. Both exist because we broke them before.
//
// 1. POINT-IN-TIME ONLY. Every performance stat is rebuilt from fights that had
//    already happened when the fight being scored took place. The `fighters`
//    table holds career-to-date aggregates (wins, td_def, slpm) — those include
//    the fight being scored and every fight after it. Scoring history with them
//    is how "record predicts 75.5% of fights" happened: a fighter's final record
//    contains the answer. Physical traits (dob, reach, height, stance) are the
//    only fields safe to read straight off `fighters`.
//
// 2. EVERY RATE SHIPS WITH ITS SAMPLE AND ITS MARKET-CONTROLLED TWIN. A factor
//    that only wins when the fighter it favours is also the betting favourite is
//    reporting the market back to us. The `even` cohort (both sides priced
//    -140..+140 at close) is the test: hold the market flat, see if the factor
//    still knows anything.
// =============================================================================

const fs = require('fs');
const path = require('path');
const { createClient } = require('@supabase/supabase-js');

const SUPABASE_URL = process.env.SUPABASE_URL || 'https://uftancejftcryfvbggll.supabase.co';
const SUPABASE_KEY = process.env.SUPABASE_SECRET_KEY
  || process.env.SUPABASE_SERVICE_ROLE_KEY
  || 'sb_publishable_boJGOA1CFN-SF14HHFGUAw_YEEm0DU8';

const OUT = path.join(path.resolve(__dirname, '..'), 'factor-rates.json');

// Below this many fights a rate is noise dressed as a number. We refuse to
// publish it rather than let the reader talk themselves into it.
const MIN_SAMPLE = 100;
// "The market called it a coin flip": both sides inside this American-odds band
// at close.
const EVEN_BAND = 140;
// A fighter needs this much UFC history before their point-in-time form stats
// mean anything.
const MIN_PRIOR_FIGHTS = 3;
const MIN_TD_ATTEMPTS = 5;

const sb = createClient(SUPABASE_URL, SUPABASE_KEY);

// ---------------------------------------------------------------------------
// Supabase paging
// ---------------------------------------------------------------------------
async function fetchAll(build) {
  const out = [];
  const page = 1000;
  for (let from = 0; ; from += page) {
    const { data, error } = await build().range(from, from + page - 1);
    if (error) throw new Error(error.message);
    out.push(...data);
    if (data.length < page) break;
  }
  return out;
}

// ---------------------------------------------------------------------------
// Stats helpers
// ---------------------------------------------------------------------------

// Wilson score interval — behaves at small n and near 0/1, unlike normal
// approximation, which is exactly where these cohorts live.
function wilson(wins, n) {
  if (!n) return [0, 0];
  const p = wins / n;
  const z = 1.96;
  const d = 1 + (z * z) / n;
  const centre = (p + (z * z) / (2 * n)) / d;
  const margin = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d;
  return [100 * (centre - margin), 100 * (centre + margin)];
}

function rate(wins, n) {
  if (!n) return null;
  const [lo, hi] = wilson(wins, n);
  return {
    n,
    wins,
    pct: +(100 * wins / n).toFixed(1),
    ci_lo: +lo.toFixed(1),
    ci_hi: +hi.toFixed(1),
  };
}

// A factor earns "real" only by beating a coin flip with the market held flat.
function verdictFor(all, even) {
  if (!all || all.n < MIN_SAMPLE) return 'insufficient';
  if (!even || even.n < MIN_SAMPLE) return 'unproven';
  if (even.ci_lo > 50) return 'real';
  if (even.ci_hi < 50) return 'inverted';
  return 'proxy';
}

const fightMinutes = (f) => {
  if (!f.end_round) return null;
  let secs = 0;
  if (f.end_time && /^\d+:\d+$/.test(f.end_time)) {
    const [m, s] = f.end_time.split(':').map(Number);
    secs = m * 60 + s;
  } else {
    secs = 5 * 60;
  }
  return ((f.end_round - 1) * 5 * 60 + secs) / 60;
};

const ageAt = (fighter, date) => {
  if (!fighter || !fighter.dob || !date) return null;
  const ms = new Date(date) - new Date(fighter.dob);
  if (!isFinite(ms)) return null;
  const yrs = ms / (365.25 * 24 * 3600 * 1000);
  return yrs > 15 && yrs < 60 ? yrs : null;
};

const median = (arr) => {
  if (!arr || !arr.length) return null;
  const s = arr.slice().sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
};

// ---------------------------------------------------------------------------
// Factor definitions
//
// Each factor answers one question: "when this factor points at a fighter, how
// often does that fighter win?" `pick` returns the favoured fighter id, or null
// when the factor doesn't fire for that matchup.
// ---------------------------------------------------------------------------
const FACTORS = [
  {
    id: 'age',
    label: 'Age',
    question: 'Does the younger fighter win?',
    basis: 'physical',
    note: 'Age at the moment of the fight, from date of birth. Nothing here can be contaminated by later results.',
    buckets: [
      { label: '1–2 years younger', lo: 0, hi: 2 },
      { label: '3–4 years younger', lo: 2, hi: 4 },
      { label: '5–6 years younger', lo: 4, hi: 6 },
      { label: '7–9 years younger', lo: 6, hi: 9 },
      { label: '10+ years younger', lo: 9, hi: 999 },
    ],
    gap: (m) => (m.ageA != null && m.ageB != null ? Math.abs(m.ageA - m.ageB) : null),
    pick: (m) => (m.ageA < m.ageB ? m.a.id : m.b.id),
  },
  {
    id: 'reach',
    label: 'Reach',
    question: 'Does the longer fighter win?',
    basis: 'physical',
    note: 'Reach in inches off the tale of the tape. Fixed for a fighter\'s career.',
    buckets: [
      { label: '1 inch longer', lo: 0, hi: 1 },
      { label: '2–3 inches longer', lo: 1, hi: 3 },
      { label: '4–5 inches longer', lo: 3, hi: 5 },
      { label: '6+ inches longer', lo: 5, hi: 999 },
    ],
    gap: (m) => (m.a.reach_in != null && m.b.reach_in != null ? Math.abs(m.a.reach_in - m.b.reach_in) : null),
    pick: (m) => (m.a.reach_in > m.b.reach_in ? m.a.id : m.b.id),
  },
  {
    id: 'height',
    label: 'Height',
    question: 'Does the taller fighter win?',
    basis: 'physical',
    note: 'Height in inches off the tale of the tape.',
    buckets: [
      { label: '1–2 inches taller', lo: 0, hi: 2 },
      { label: '3–4 inches taller', lo: 2, hi: 4 },
      { label: '5+ inches taller', lo: 4, hi: 999 },
    ],
    gap: (m) => (m.a.height_in != null && m.b.height_in != null ? Math.abs(m.a.height_in - m.b.height_in) : null),
    pick: (m) => (m.a.height_in > m.b.height_in ? m.a.id : m.b.id),
  },
  {
    id: 'southpaw_reach',
    label: 'Southpaw + reach',
    question: 'Does the southpaw with the longer reach beat the orthodox fighter?',
    basis: 'physical',
    note: 'Exactly one southpaw, facing an orthodox fighter, holding a reach edge. Single cohort — no gap buckets.',
    single: true,
    fires: (m) => {
      const sa = (m.a.stance || '').toLowerCase();
      const sb = (m.b.stance || '').toLowerCase();
      const spA = sa === 'southpaw';
      const spB = sb === 'southpaw';
      if (spA === spB) return null;
      const paw = spA ? m.a : m.b;
      const orth = spA ? m.b : m.a;
      if ((orth.stance || '').toLowerCase() !== 'orthodox') return null;
      if (paw.reach_in == null || orth.reach_in == null) return null;
      if (paw.reach_in - orth.reach_in < 2) return null;
      return paw.id;
    },
  },
  {
    id: 'ufc_record',
    label: 'UFC record',
    question: 'Does the fighter with the better UFC record win?',
    basis: 'point-in-time',
    note: 'Win rate over UFC fights that had already happened, Laplace-smoothed. Rebuilt fight by fight — never the career total off the fighters table, which contains the result being scored.',
    buckets: [
      { label: '8–15 point edge', lo: 0.08, hi: 0.15 },
      { label: '15–25 point edge', lo: 0.15, hi: 0.25 },
      { label: '25–40 point edge', lo: 0.25, hi: 0.40 },
      { label: '40+ point edge', lo: 0.40, hi: 999 },
    ],
    gap: (m) => {
      if (!m.sA || !m.sB) return null;
      if (m.sA.fights < MIN_PRIOR_FIGHTS || m.sB.fights < MIN_PRIOR_FIGHTS) return null;
      const ra = (m.sA.wins + 2) / (m.sA.fights + 4);
      const rb = (m.sB.wins + 2) / (m.sB.fights + 4);
      return Math.abs(ra - rb);
    },
    pick: (m) => {
      const ra = (m.sA.wins + 2) / (m.sA.fights + 4);
      const rb = (m.sB.wins + 2) / (m.sB.fights + 4);
      return ra > rb ? m.a.id : m.b.id;
    },
  },
  {
    id: 'td_def',
    label: 'Takedown defence',
    question: 'Does the fighter with better takedown defence win?',
    basis: 'point-in-time',
    note: 'Takedowns stuffed as a share of takedowns faced, over prior fights only.',
    buckets: [
      { label: '10–20 point edge', lo: 10, hi: 20 },
      { label: '20–30 point edge', lo: 20, hi: 30 },
      { label: '30+ point edge', lo: 30, hi: 999 },
    ],
    gap: (m) => {
      const da = tdDef(m.sA);
      const db = tdDef(m.sB);
      return da == null || db == null ? null : Math.abs(da - db);
    },
    pick: (m) => (tdDef(m.sA) > tdDef(m.sB) ? m.a.id : m.b.id),
  },
  {
    id: 'strike_volume',
    label: 'Striking volume',
    question: 'Does the busier striker win?',
    basis: 'point-in-time',
    note: 'Significant strikes landed per minute over prior fights only.',
    buckets: [
      { label: '0.5–1.5 more per minute', lo: 0.5, hi: 1.5 },
      { label: '1.5–3 more per minute', lo: 1.5, hi: 3 },
      { label: '3+ more per minute', lo: 3, hi: 999 },
    ],
    gap: (m) => {
      const sa = slpm(m.sA);
      const sb = slpm(m.sB);
      return sa == null || sb == null ? null : Math.abs(sa - sb);
    },
    pick: (m) => (slpm(m.sA) > slpm(m.sB) ? m.a.id : m.b.id),
  },
  {
    id: 'finish_rate',
    label: 'Finishing rate',
    question: 'Does the fighter who finishes more often win?',
    basis: 'point-in-time',
    note: 'Share of prior UFC wins that came by KO/TKO or submission.',
    buckets: [
      { label: '20–40 point edge', lo: 0.20, hi: 0.40 },
      { label: '40–60 point edge', lo: 0.40, hi: 0.60 },
      { label: '60+ point edge', lo: 0.60, hi: 999 },
    ],
    gap: (m) => {
      const fa = finishRate(m.sA);
      const fb = finishRate(m.sB);
      return fa == null || fb == null ? null : Math.abs(fa - fb);
    },
    pick: (m) => (finishRate(m.sA) > finishRate(m.sB) ? m.a.id : m.b.id),
  },
];

const tdDef = (s) => (s && s.td_faced >= MIN_TD_ATTEMPTS ? 100 * (1 - s.td_conceded / s.td_faced) : null);
const slpm = (s) => (s && s.fights >= MIN_PRIOR_FIGHTS && s.minutes > 0 ? s.sig_landed / s.minutes : null);
const finishRate = (s) => (s && s.wins >= MIN_PRIOR_FIGHTS ? s.finishes / s.wins : null);

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
async function main() {
  const usingServiceKey = SUPABASE_KEY.startsWith('eyJ') || SUPABASE_KEY.startsWith('sb_secret');
  console.log(`Reading ${SUPABASE_URL} with ${usingServiceKey ? 'service' : 'publishable'} key`);

  console.log('Pulling events, fights, fighters, closing odds ...');
  const [events, fights, fighters, odds] = await Promise.all([
    fetchAll(() => sb.from('events').select('id, event_date')),
    fetchAll(() => sb.from('fights').select(
      'id, event_id, fighter_a_id, fighter_b_id, winner_id, method, end_round, end_time, '
      + 'a_sig_str_landed, b_sig_str_landed, a_td_landed, b_td_landed, a_td_attempted, b_td_attempted')),
    fetchAll(() => sb.from('fighters').select('id, name, dob, reach_in, height_in, stance')),
    fetchAll(() => sb.from('fight_odds').select('fight_id, fighter_id, american_odds, is_closer').eq('is_closer', true)),
  ]);
  console.log(`  events=${events.length} fights=${fights.length} fighters=${fighters.length} closing-odds rows=${odds.length}`);

  // fight_odds has no SELECT policy for `anon` — it returns 0 rows and no error.
  // Without odds there is no market-control column, and every factor would
  // publish as "unproven": the page would look fine and say nothing. Fail here
  // instead of shipping a confidently empty table.
  if (odds.length === 0) {
    throw new Error(
      'fight_odds returned 0 rows — the market-control column would be empty.\n'
      + (usingServiceKey
        ? 'Service key is in use, so this is a real data problem: check the odds feed.'
        : 'Set SUPABASE_SECRET_KEY (or SUPABASE_SERVICE_ROLE_KEY) — the publishable key cannot read fight_odds.'),
    );
  }
  if (fights.length === 0 || fighters.length === 0) {
    throw new Error('fights/fighters came back empty — refusing to overwrite factor-rates.json.');
  }

  const evDate = new Map(events.map((e) => [e.id, e.event_date]));
  const F = new Map(fighters.map((f) => [f.id, f]));

  // Closing price per fighter per fight, median across books.
  const closeBook = new Map();
  for (const o of odds) {
    if (o.american_odds == null) continue;
    const k = `${o.fight_id}|${o.fighter_id}`;
    if (!closeBook.has(k)) closeBook.set(k, []);
    closeBook.get(k).push(o.american_odds);
  }
  const closeOf = (fightId, fighterId) => median(closeBook.get(`${fightId}|${fighterId}`));

  // Chronological walk. State is strictly "what we knew before this fight".
  const dated = fights
    .map((f) => ({ f, date: evDate.get(f.event_id) }))
    .filter((x) => x.date)
    .sort((x, y) => (x.date < y.date ? -1 : x.date > y.date ? 1 : x.f.id - y.f.id));

  const state = new Map();
  const blank = () => ({ fights: 0, wins: 0, finishes: 0, sig_landed: 0, minutes: 0, td_faced: 0, td_conceded: 0 });
  const stateOf = (id) => {
    if (!state.has(id)) state.set(id, blank());
    return state.get(id);
  };
  const snapshot = (s) => ({ ...s });

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
        sA: snapshot(stateOf(f.fighter_a_id)),
        sB: snapshot(stateOf(f.fighter_b_id)),
        // "The market called it even": neither side priced beyond the band.
        even: oa != null && ob != null
          && oa >= -EVEN_BAND && oa <= EVEN_BAND
          && ob >= -EVEN_BAND && ob <= EVEN_BAND,
      });
    }

    // Fold this fight into both fighters' state — after it has been scored.
    const mins = fightMinutes(f);
    const finish = /ko|tko|submission/i.test(f.method || '');
    for (const side of ['a', 'b']) {
      const fid = side === 'a' ? f.fighter_a_id : f.fighter_b_id;
      if (fid == null) continue;
      const s = stateOf(fid);
      s.fights += 1;
      if (f.winner_id === fid) {
        s.wins += 1;
        if (finish) s.finishes += 1;
      }
      const landed = side === 'a' ? f.a_sig_str_landed : f.b_sig_str_landed;
      if (landed != null && mins) {
        s.sig_landed += landed;
        s.minutes += mins;
      }
      const oppTdAtt = side === 'a' ? f.b_td_attempted : f.a_td_attempted;
      const oppTdLanded = side === 'a' ? f.b_td_landed : f.a_td_landed;
      if (oppTdAtt != null) s.td_faced += oppTdAtt;
      if (oppTdLanded != null) s.td_conceded += oppTdLanded;
    }
  }

  const evenCount = matchups.filter((m) => m.even).length;
  console.log(`  scored matchups=${matchups.length}  market-even cohort=${evenCount}`);

  // -------------------------------------------------------------------------
  // Score every factor
  // -------------------------------------------------------------------------
  const out = [];
  for (const factor of FACTORS) {
    const tally = (rows) => {
      let n = 0;
      let w = 0;
      for (const m of rows) {
        const winnerSide = factor.single ? factor.fires(m) : null;
        if (factor.single) {
          if (winnerSide == null) continue;
          n += 1;
          if (m.winner === winnerSide) w += 1;
          continue;
        }
        const g = factor.gap(m);
        if (g == null || !(g > factor._lo && g <= factor._hi)) continue;
        const favoured = factor.pick(m);
        if (favoured == null) continue;
        n += 1;
        if (m.winner === favoured) w += 1;
      }
      return rate(w, n);
    };

    const buckets = [];
    if (factor.single) {
      const all = tally(matchups);
      const even = tally(matchups.filter((m) => m.even));
      buckets.push({ label: 'When it fires', all, even, verdict: verdictFor(all, even) });
    } else {
      for (const b of factor.buckets) {
        factor._lo = b.lo;
        factor._hi = b.hi;
        const all = tally(matchups);
        const even = tally(matchups.filter((m) => m.even));
        buckets.push({ label: b.label, all, even, verdict: verdictFor(all, even) });
      }
      // Headline row: the factor firing at any strength at all.
      factor._lo = factor.buckets[0].lo;
      factor._hi = 999999;
      const allAny = tally(matchups);
      const evenAny = tally(matchups.filter((m) => m.even));
      buckets.unshift({
        label: 'Any gap (all fights it fires on)',
        headline: true,
        all: allAny,
        even: evenAny,
        verdict: verdictFor(allAny, evenAny),
      });
    }

    const head = buckets.find((b) => b.headline) || buckets[0];
    out.push({
      id: factor.id,
      label: factor.label,
      question: factor.question,
      basis: factor.basis,
      note: factor.note,
      verdict: head.verdict,
      buckets,
    });
    const h = head.all;
    const e = head.even;
    console.log(
      `  ${factor.label.padEnd(20)} raw ${h ? `${h.pct}% (n=${h.n})`.padEnd(18) : 'n/a'.padEnd(18)}`
      + ` market-even ${e ? `${e.pct}% (n=${e.n})`.padEnd(16) : 'n/a'.padEnd(16)} → ${head.verdict.toUpperCase()}`,
    );
  }

  const payload = {
    generated_at: new Date().toISOString(),
    dataset: {
      fights_scored: matchups.length,
      market_even_cohort: evenCount,
      first_event: dated[0] ? dated[0].date : null,
      last_event: dated[dated.length - 1] ? dated[dated.length - 1].date : null,
    },
    rules: {
      min_sample: MIN_SAMPLE,
      even_band_american: EVEN_BAND,
      min_prior_fights: MIN_PRIOR_FIGHTS,
    },
    factors: out,
  };

  fs.writeFileSync(OUT, JSON.stringify(payload, null, 2) + '\n');
  console.log(`\nWrote ${OUT}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
