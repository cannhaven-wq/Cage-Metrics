// =============================================================================
// research/validate.js — Phase 1 baseline accuracy of edges.js verdict logic
// =============================================================================
// Pulls every decided UFC fight from Supabase, simulates the edges.js verdict
// for each, reports accuracy aggregates to research/results.md +
// research/results.json.
//
// SCOPE: this is phase 1 — an honest first measurement, not a final answer.
//
// CAVEATS (READ FIRST, INTERPRET RESULTS THROUGH THIS LENS):
//
//   1. Fighter career stats (slpm, td_avg, str_acc, td_def, etc.) are
//      CURRENT career averages, not point-in-time snapshots from before each
//      fight. For a 2018 fight we're predicting using 2024 stats. Career
//      averages are sticky for active fighters but this is hindsight bias.
//
//   2. Age is the CURRENT age (per the fighters table). For old fights the
//      age delta is still directionally right but the absolute values are
//      shifted. Effect is small; the edge function looks at gap, not
//      absolute age.
//
//   3. Cardio scores are CURRENT (last-5-fights window of v_fighter_consistency
//      as of NOW). Same hindsight problem, more severe — for a 2019 fight we
//      may be using cardio computed from 2022-2024 data.
//
//   4. Streak data is INTENTIONALLY ZEROED (empty streakMap). Using current
//      streaks would be the worst leakage of all (we'd "predict" a 2018 win
//      knowing the fighter was on a 5-fight streak going into a 2024 fight).
//      This means streakEdge / lossStreakEdge / postLossEdge never fire.
//
// IMPLICATION: overall accuracy is OPTIMISTIC. The accuracy-by-year breakdown
// shows how big the hindsight bias is — if recent fights score much higher
// than old ones, we know point-in-time reconstruction (phase 1b) is needed
// before any model decisions.
// =============================================================================

const fs = require('fs');
const path = require('path');
const { createClient } = require('@supabase/supabase-js');
const cflEdges = require('../edges');

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SUPABASE_KEY = 'sb_publishable_boJGOA1CFN-SF14HHFGUAw_YEEm0DU8';

const sb = createClient(SUPABASE_URL, SUPABASE_KEY);

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

function pct(n, d) { return d === 0 ? '—' : ((n / d) * 100).toFixed(1) + '%'; }

function bandFor(prob) {
  // Confidence on the predicted side, regardless of which corner.
  const p = Math.max(prob, 1 - prob);
  if (p < 0.55) return '50-55%';
  if (p < 0.60) return '55-60%';
  if (p < 0.65) return '60-65%';
  if (p < 0.70) return '65-70%';
  if (p < 0.75) return '70-75%';
  return '75%+';
}

(async () => {
  console.log('Fetching events...');
  const events = await fetchAll(() => sb.from('events')
    .select('id, event_date, is_upcoming')
    .eq('is_upcoming', false));
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
  console.log(`Got ${fighters.length} fighters.`);

  console.log('Fetching cardio scores from v_fighter_consistency...');
  const cardioRows = await fetchAll(() => sb.from('v_fighter_consistency')
    .select('fighter_id, weight_class, cardio_tier, confidence_tier'));
  const cardioMap = {};
  for (const r of cardioRows) {
    if (!cardioMap[r.fighter_id]) cardioMap[r.fighter_id] = { byWc: {}, career: null };
    const entry = { tier_word: r.cardio_tier, confidence: r.confidence_tier };
    if (r.weight_class === 'CAREER') cardioMap[r.fighter_id].career = entry;
    else cardioMap[r.fighter_id].byWc[r.weight_class] = entry;
  }
  console.log(`Got cardio for ${Object.keys(cardioMap).length} fighters.`);

  // Streaks intentionally empty — see file header.
  const streakMap = {};

  const stats = {
    decided_fights: fights.length,
    skipped_no_data: 0,
    no_edges: 0,
    total: 0,
    correct: 0,
    a_wins_actual: 0,    // Sanity: A/B assignment should be balanced. ~50%.
    by_band: {},
    by_year: {},
    by_division: {},
    by_factor: {},
    by_factor_solo: {},  // When this factor is the ONLY edge firing.
    edge_count_dist: {}, // How many fights had 0/1/2/3+ edges
  };

  // Age-gap analysis — INDEPENDENT of edges.js. For each integer year of age
  // gap, what fraction of historical fights did the younger fighter win? The
  // gap is preserved across time (both fighters age at the same rate) so this
  // doesn't suffer from the hindsight bias plaguing the rest of the report.
  const ageGapAll = {};       // all fights with known ages on both sides
  const ageGapVeterans = {};  // both fighters have 5+ UFC fights
  const ageGapNewcomer = {};  // at least one fighter has <5 UFC fights
  function bumpGap(map, gap, won) {
    if (!map[gap]) map[gap] = { n: 0, younger_wins: 0 };
    map[gap].n++;
    if (won) map[gap].younger_wins++;
  }

  for (const fight of fights) {
    const a = fighterMap[fight.fighter_a_id];
    const b = fighterMap[fight.fighter_b_id];
    if (!a || !b) { stats.skipped_no_data++; continue; }

    const event = eventMap[fight.event_id];
    if (!event) { stats.skipped_no_data++; continue; }

    if (fight.winner_id === fight.fighter_a_id) stats.a_wins_actual++;

    // Age-gap accounting (independent of edges.js firing)
    if (a.age != null && b.age != null) {
      const gap = Math.abs(a.age - b.age);
      if (gap >= 1) {
        const youngerIsA = a.age < b.age;
        const youngerWon = (youngerIsA && fight.winner_id === fight.fighter_a_id) ||
                           (!youngerIsA && fight.winner_id === fight.fighter_b_id);
        const bucket = Math.min(Math.floor(gap), 12);  // 12+ goes in one bucket
        bumpGap(ageGapAll, bucket, youngerWon);
        const aUfc = (a.ufc_wins || 0) + (a.ufc_losses || 0);
        const bUfc = (b.ufc_wins || 0) + (b.ufc_losses || 0);
        if (aUfc >= 5 && bUfc >= 5) {
          bumpGap(ageGapVeterans, bucket, youngerWon);
        } else {
          bumpGap(ageGapNewcomer, bucket, youngerWon);
        }
      }
    }

    const ctx = {
      streakMap,
      cardioMap,
      fightWeightClass: fight.weight_class,
      eventDate: event.event_date,
    };

    const { edges, aProb } = cflEdges.computeEdges(a, b, ctx);

    const ec = edges.length;
    stats.edge_count_dist[ec] = (stats.edge_count_dist[ec] || 0) + 1;

    if (ec === 0 || Math.abs(aProb - 0.5) < 0.001) {
      stats.no_edges++;
      continue;
    }

    const predictedAWins = aProb > 0.5;
    const actualAWins = fight.winner_id === fight.fighter_a_id;
    const correct = predictedAWins === actualAWins;

    stats.total++;
    if (correct) stats.correct++;

    const band = bandFor(aProb);
    if (!stats.by_band[band]) stats.by_band[band] = { n: 0, correct: 0 };
    stats.by_band[band].n++;
    if (correct) stats.by_band[band].correct++;

    const year = event.event_date ? event.event_date.slice(0, 4) : 'unknown';
    if (!stats.by_year[year]) stats.by_year[year] = { n: 0, correct: 0 };
    stats.by_year[year].n++;
    if (correct) stats.by_year[year].correct++;

    const div = fight.weight_class || 'Unknown';
    if (!stats.by_division[div]) stats.by_division[div] = { n: 0, correct: 0 };
    stats.by_division[div].n++;
    if (correct) stats.by_division[div].correct++;

    // Per-edge accuracy: when this edge favors a side, did that side win?
    for (const e of edges) {
      const factorPredictsAWins = e.favors === 'a';
      const factorCorrect = factorPredictsAWins === actualAWins;
      if (!stats.by_factor[e.factor]) stats.by_factor[e.factor] = { n: 0, correct: 0, pct_sum: 0 };
      stats.by_factor[e.factor].n++;
      stats.by_factor[e.factor].pct_sum += e.pct;
      if (factorCorrect) stats.by_factor[e.factor].correct++;
    }

    // Solo-edge accuracy: when this is the ONLY factor firing on this fight,
    // how often does its predicted side actually win? Cleaner signal — no
    // confounding from other edges.
    if (edges.length === 1) {
      const e = edges[0];
      const factorPredictsAWins = e.favors === 'a';
      const factorCorrect = factorPredictsAWins === actualAWins;
      if (!stats.by_factor_solo[e.factor]) stats.by_factor_solo[e.factor] = { n: 0, correct: 0, pct_sum: 0 };
      stats.by_factor_solo[e.factor].n++;
      stats.by_factor_solo[e.factor].pct_sum += e.pct;
      if (factorCorrect) stats.by_factor_solo[e.factor].correct++;
    }
  }

  // Build report
  const lines = [];
  lines.push('# edges.js validation — phase 1 baseline');
  lines.push('');
  lines.push('Generated: ' + new Date().toISOString());
  lines.push('');
  lines.push('**CAVEATS** (see header of `research/validate.js`):');
  lines.push('');
  lines.push('- Uses CURRENT fighter career stats / cardio for all fights, including past ones (hindsight bias).');
  lines.push('- Streak-based edges (streak / loss_streak / post_loss) are disabled to avoid the worst leakage.');
  lines.push('- Numbers should be read as an **upper bound**, not the true accuracy of a fair-replay model.');
  lines.push('');
  lines.push('## Headline');
  lines.push('');
  lines.push(`- Decided fights in DB: **${stats.decided_fights}**`);
  lines.push(`- Skipped (missing fighter or event row): ${stats.skipped_no_data}`);
  lines.push(`- Skipped (no edges fired): ${stats.no_edges}`);
  lines.push(`- Predictions made: **${stats.total}**`);
  lines.push(`- Predictions correct: **${stats.correct} (${pct(stats.correct, stats.total)})**`);
  lines.push('');
  lines.push(`Sanity: fighter A wins in **${pct(stats.a_wins_actual, stats.decided_fights)}** of decided fights — should be near 50% if A/B labelling is random.`);
  lines.push('');

  lines.push('## Calibration: accuracy by confidence band');
  lines.push('');
  lines.push('Does a 65% verdict actually win 65% of the time? If yes, model is calibrated.');
  lines.push('');
  lines.push('| Band     | n      | accuracy | expected |');
  lines.push('|----------|--------|----------|----------|');
  const bands = ['50-55%', '55-60%', '60-65%', '65-70%', '70-75%', '75%+'];
  for (const b of bands) {
    const s = stats.by_band[b];
    if (!s) continue;
    const expected = b.replace('%', '').split('-')[0] + '%+';
    lines.push(`| ${b.padEnd(8)} | ${String(s.n).padEnd(6)} | ${pct(s.correct, s.n).padEnd(8)} | ${expected.padEnd(8)} |`);
  }
  lines.push('');

  lines.push('## Accuracy by year');
  lines.push('');
  lines.push('Hindsight-bias proxy: if recent years score much higher than old years,');
  lines.push('the current-stats-on-old-fights problem is significant.');
  lines.push('');
  lines.push('| Year | n     | accuracy |');
  lines.push('|------|-------|----------|');
  const years = Object.keys(stats.by_year).sort();
  for (const y of years) {
    const s = stats.by_year[y];
    lines.push(`| ${y} | ${String(s.n).padEnd(5)} | ${pct(s.correct, s.n)} |`);
  }
  lines.push('');

  lines.push('## Accuracy by division');
  lines.push('');
  lines.push('| Division              | n     | accuracy |');
  lines.push('|-----------------------|-------|----------|');
  const divs = Object.keys(stats.by_division)
    .filter(d => stats.by_division[d].n >= 50)
    .sort((x, y) => stats.by_division[y].n - stats.by_division[x].n);
  for (const d of divs) {
    const s = stats.by_division[d];
    lines.push(`| ${d.padEnd(21)} | ${String(s.n).padEnd(5)} | ${pct(s.correct, s.n)} |`);
  }
  lines.push('');

  lines.push('## Per-factor accuracy');
  lines.push('');
  lines.push('When this edge fires (alongside others), did its favored side win? `pct_avg` is the average');
  lines.push('confidence the model assigned this factor — a well-calibrated factor has accuracy ≈ pct_avg.');
  lines.push('');
  lines.push('| Factor        | n      | accuracy | pct_avg |');
  lines.push('|---------------|--------|----------|---------|');
  const factors = Object.keys(stats.by_factor).sort((x, y) => stats.by_factor[y].n - stats.by_factor[x].n);
  for (const f of factors) {
    const s = stats.by_factor[f];
    const avg = s.n > 0 ? (s.pct_sum / s.n).toFixed(1) + '%' : '—';
    lines.push(`| ${f.padEnd(13)} | ${String(s.n).padEnd(6)} | ${pct(s.correct, s.n).padEnd(8)} | ${avg.padEnd(7)} |`);
  }
  lines.push('');

  lines.push('## Per-factor accuracy — SOLO edge fights only');
  lines.push('');
  lines.push('Same metric but filtered to fights where this was the ONLY factor firing. Cleaner signal.');
  lines.push('');
  lines.push('| Factor        | n      | accuracy | pct_avg |');
  lines.push('|---------------|--------|----------|---------|');
  const soloFactors = Object.keys(stats.by_factor_solo).sort((x, y) => stats.by_factor_solo[y].n - stats.by_factor_solo[x].n);
  for (const f of soloFactors) {
    const s = stats.by_factor_solo[f];
    const avg = s.n > 0 ? (s.pct_sum / s.n).toFixed(1) + '%' : '—';
    lines.push(`| ${f.padEnd(13)} | ${String(s.n).padEnd(6)} | ${pct(s.correct, s.n).padEnd(8)} | ${avg.padEnd(7)} |`);
  }
  lines.push('');

  lines.push('## Age gap → younger-fighter win rate');
  lines.push('');
  lines.push('Independent of edges.js. For each integer year of age gap, what fraction of');
  lines.push('historical fights did the younger fighter win? The gap is preserved across time');
  lines.push('(both fighters age at the same rate) so this is NOT subject to hindsight bias.');
  lines.push('');
  lines.push('Compare each row to the model\'s assigned `pct`:');
  lines.push('- 1–2 yrs: 52.0% (newcomer-discounted to 51.0%)');
  lines.push('- 3–4 yrs: 55.9% (newcomer-discounted to 53.0%)');
  lines.push('- 5–6 yrs: 58.2% (newcomer-discounted to 54.1%)');
  lines.push('- 7–9 yrs: 63.3% (newcomer-discounted to 56.7%)');
  lines.push('- 10+ yrs: 65.2% (newcomer-discounted to 57.6%)');
  lines.push('');
  lines.push('### All fights with known ages on both sides');
  lines.push('');
  lines.push('| Age gap | n     | younger wins |');
  lines.push('|---------|-------|--------------|');
  const gapKeysAll = Object.keys(ageGapAll).map(Number).sort((x, y) => x - y);
  for (const g of gapKeysAll) {
    const s = ageGapAll[g];
    const label = g >= 12 ? '12+' : String(g);
    lines.push(`| ${label.padEnd(7)} | ${String(s.n).padEnd(5)} | ${pct(s.younger_wins, s.n)} |`);
  }
  lines.push('');
  lines.push('### Veterans only (both fighters have 5+ UFC fights)');
  lines.push('');
  lines.push('Cleaner signal — strips out the newcomer cohort where younger isn\'t reliably better.');
  lines.push('');
  lines.push('| Age gap | n     | younger wins |');
  lines.push('|---------|-------|--------------|');
  const gapKeysVet = Object.keys(ageGapVeterans).map(Number).sort((x, y) => x - y);
  for (const g of gapKeysVet) {
    const s = ageGapVeterans[g];
    const label = g >= 12 ? '12+' : String(g);
    lines.push(`| ${label.padEnd(7)} | ${String(s.n).padEnd(5)} | ${pct(s.younger_wins, s.n)} |`);
  }
  lines.push('');
  lines.push('### Newcomer cohort (at least one fighter has <5 UFC fights)');
  lines.push('');
  lines.push('| Age gap | n     | younger wins |');
  lines.push('|---------|-------|--------------|');
  const gapKeysNew = Object.keys(ageGapNewcomer).map(Number).sort((x, y) => x - y);
  for (const g of gapKeysNew) {
    const s = ageGapNewcomer[g];
    const label = g >= 12 ? '12+' : String(g);
    lines.push(`| ${label.padEnd(7)} | ${String(s.n).padEnd(5)} | ${pct(s.younger_wins, s.n)} |`);
  }
  lines.push('');

  lines.push('## Edge-count distribution');
  lines.push('');
  lines.push('How many edges fired per fight?');
  lines.push('');
  lines.push('| Edges per fight | count |');
  lines.push('|-----------------|-------|');
  const ecs = Object.keys(stats.edge_count_dist).sort((a, b) => Number(a) - Number(b));
  for (const ec of ecs) {
    lines.push(`| ${ec.padEnd(15)} | ${stats.edge_count_dist[ec]} |`);
  }
  lines.push('');

  const reportText = lines.join('\n') + '\n';
  console.log(reportText);

  const outDir = __dirname;
  fs.writeFileSync(path.join(outDir, 'results.md'), reportText);
  fs.writeFileSync(path.join(outDir, 'results.json'), JSON.stringify({
    ...stats,
    age_gap_all: ageGapAll,
    age_gap_veterans: ageGapVeterans,
    age_gap_newcomer: ageGapNewcomer,
  }, null, 2));
  console.log('Wrote research/results.md and research/results.json');
})().catch(err => {
  console.error('validate.js failed:', err);
  process.exit(1);
});
