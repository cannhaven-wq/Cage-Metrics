// =============================================================================
// research/subset-test.js — does dropping noisy edges improve accuracy?
// =============================================================================
// Hypothesis: the model adds too many weak edges (stance_reach at 53.4%,
// age at 57.4%) that act like correlated noise in the naive-Bayesian
// combination and dilute the strong signals (record 75.5%, slpm 64.8%).
//
// Runs the same backtest as validate.js but evaluates several edge-subset
// strategies in one pass.
// =============================================================================

const { createClient } = require('@supabase/supabase-js');
const cflEdges = require('../edges');

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SUPABASE_KEY = 'sb_publishable_boJGOA1CFN-SF14HHFGUAw_YEEm0DU8';
const sb = createClient(SUPABASE_URL, SUPABASE_KEY);

async function fetchAll(buildQuery) {
  const all = [];
  let from = 0, pageSize = 1000;
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

// Same Bayesian combine + cap as edges.js, but operates on a filtered subset.
function combine(filteredEdges) {
  if (!filteredEdges.length) return { aProb: 0.5, n: 0 };
  let aProb = 0.5;
  for (const e of filteredEdges) {
    const factor = e.favors === 'a' ? (e.pct / 100) : (1 - e.pct / 100);
    aProb = (aProb * factor) / (aProb * factor + (1 - aProb) * (1 - factor));
  }
  const strongest = Math.max.apply(null, filteredEdges.map(e => e.pct)) / 100;
  const cap = Math.min(0.78, strongest + 0.06);
  if (aProb > cap) aProb = cap;
  if (aProb < 1 - cap) aProb = 1 - cap;
  return { aProb, n: filteredEdges.length };
}

const STRONG_5 = ['record', 'cardio', 'td_def', 'slpm', 'td_acc'];
const TOP_3    = ['record', 'cardio', 'td_def'];

const SUBSETS = [
  // [label, filterFn(edge) → bool, OR special string]
  ['ALL (current baseline)',                  () => true],
  ['Drop stance_reach',                       e => e.factor !== 'stance_reach'],
  ['Drop stance_reach + age',                 e => e.factor !== 'stance_reach' && e.factor !== 'age'],
  ['Drop stance_reach + age + td_acc',        e => !['stance_reach','age','td_acc'].includes(e.factor)],
  ['Strong 5 only (record/cardio/td_def/slpm/td_acc)', e => STRONG_5.includes(e.factor)],
  ['Top 3 only (record/cardio/td_def)',       e => TOP_3.includes(e.factor)],
  ['Record only',                             e => e.factor === 'record'],
  ['Loudest edge only',                       'loudest'],
  ['Top 2 loudest only',                      'top2'],
];

(async () => {
  console.log('Fetching events...');
  const events = await fetchAll(() => sb.from('events')
    .select('id, event_date, is_upcoming').eq('is_upcoming', false));
  const eventMap = {};
  for (const e of events) eventMap[e.id] = e;

  console.log('Fetching decided fights...');
  const fights = await fetchAll(() => sb.from('fights')
    .select('id, event_id, fighter_a_id, fighter_b_id, winner_id, weight_class, method')
    .not('winner_id', 'is', null));
  console.log(`Got ${fights.length} decided fights.`);

  console.log('Fetching fighters...');
  const fighters = await fetchAll(() => sb.from('fighters').select('*'));
  const fighterMap = {};
  for (const f of fighters) fighterMap[f.id] = f;

  console.log('Fetching cardio...');
  const cardioRows = await fetchAll(() => sb.from('v_fighter_consistency')
    .select('fighter_id, weight_class, cardio_tier, confidence_tier'));
  const cardioMap = {};
  for (const r of cardioRows) {
    if (!cardioMap[r.fighter_id]) cardioMap[r.fighter_id] = { byWc: {}, career: null };
    const entry = { tier_word: r.cardio_tier, confidence: r.confidence_tier };
    if (r.weight_class === 'CAREER') cardioMap[r.fighter_id].career = entry;
    else cardioMap[r.fighter_id].byWc[r.weight_class] = entry;
  }
  const streakMap = {};

  // For each subset, track: n predictions, n correct, n abstained (no edges
  // after filtering), brier sum.
  const results = {};
  for (const [label] of SUBSETS) {
    results[label] = { total: 0, correct: 0, abstained: 0, brier: 0 };
  }

  for (const fight of fights) {
    const a = fighterMap[fight.fighter_a_id];
    const b = fighterMap[fight.fighter_b_id];
    if (!a || !b) continue;
    const event = eventMap[fight.event_id];
    if (!event) continue;

    const ctx = { streakMap, cardioMap, fightWeightClass: fight.weight_class, eventDate: event.event_date };
    const { edges } = cflEdges.computeEdges(a, b, ctx);
    const actualAWins = fight.winner_id === fight.fighter_a_id;

    for (const [label, filter] of SUBSETS) {
      let subEdges;
      if (filter === 'loudest') {
        if (!edges.length) { results[label].abstained++; continue; }
        subEdges = [edges.slice().sort((x,y) => y.pct - x.pct)[0]];
      } else if (filter === 'top2') {
        if (!edges.length) { results[label].abstained++; continue; }
        subEdges = edges.slice().sort((x,y) => y.pct - x.pct).slice(0, 2);
      } else {
        subEdges = edges.filter(filter);
      }
      if (!subEdges.length) { results[label].abstained++; continue; }

      const { aProb } = combine(subEdges);
      if (Math.abs(aProb - 0.5) < 0.001) { results[label].abstained++; continue; }

      const predictedAWins = aProb > 0.5;
      const correct = predictedAWins === actualAWins;
      results[label].total++;
      if (correct) results[label].correct++;
      const actual = actualAWins ? 1 : 0;
      results[label].brier += (aProb - actual) ** 2;
    }
  }

  console.log('');
  console.log('Subset                                                    n         correct   acc      abstain   brier');
  console.log('-------------------------------------------------------------------------------------------------------');
  for (const [label] of SUBSETS) {
    const r = results[label];
    const acc = r.total ? (r.correct / r.total * 100).toFixed(2) + '%' : '—';
    const brier = r.total ? (r.brier / r.total).toFixed(4) : '—';
    console.log(
      label.padEnd(56) +
      String(r.total).padEnd(10) +
      String(r.correct).padEnd(10) +
      acc.padEnd(9) +
      String(r.abstained).padEnd(10) +
      brier
    );
  }
})().catch(err => { console.error('subset-test failed:', err); process.exit(1); });
