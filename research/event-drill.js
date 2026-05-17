// =============================================================================
// research/event-drill.js — Per-event diagnostic for edges.js verdicts
// =============================================================================
// Usage:  node event-drill.js <event_id>
//
// Pulls a single event's fights and replays computeEdges on each. Prints
// predicted vs actual, plus every edge that fired and which one was loudest.
// Useful for figuring out why a specific card had bad accuracy.
//
// Same hindsight-bias caveats as validate.js (current stats, streaks zeroed).
// =============================================================================

const { createClient } = require('@supabase/supabase-js');
const cflEdges = require('../edges');

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SUPABASE_KEY = 'sb_publishable_boJGOA1CFN-SF14HHFGUAw_YEEm0DU8';
const sb = createClient(SUPABASE_URL, SUPABASE_KEY);

const eventId = process.argv[2];
if (!eventId) { console.error('Usage: node event-drill.js <event_id>'); process.exit(1); }

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

(async () => {
  const { data: events, error: ee } = await sb.from('events')
    .select('id, name, event_date, is_upcoming').eq('id', eventId);
  if (ee) throw ee;
  if (!events || !events.length) { console.error(`No event id ${eventId}`); process.exit(1); }
  const event = events[0];
  console.log(`\nEvent #${event.id}: ${event.name}  (${event.event_date}, upcoming=${event.is_upcoming})\n`);

  const fights = await fetchAll(() => sb.from('fights')
    .select('id, fighter_a_id, fighter_b_id, winner_id, weight_class, method, is_main_event, is_title_fight')
    .eq('event_id', eventId)
    .order('is_main_event', { ascending: false })
    .order('id', { ascending: true }));
  if (!fights.length) { console.error('No fights for this event'); process.exit(1); }

  const fighterIds = new Set();
  for (const f of fights) { fighterIds.add(f.fighter_a_id); fighterIds.add(f.fighter_b_id); }
  const fighters = await fetchAll(() => sb.from('fighters').select('*').in('id', Array.from(fighterIds)));
  const fighterMap = {};
  for (const f of fighters) fighterMap[f.id] = f;

  const cardioRows = await fetchAll(() => sb.from('v_fighter_consistency')
    .select('fighter_id, weight_class, cardio_tier, confidence_tier')
    .in('fighter_id', Array.from(fighterIds)));
  const cardioMap = {};
  for (const r of cardioRows) {
    if (!cardioMap[r.fighter_id]) cardioMap[r.fighter_id] = { byWc: {}, career: null };
    const entry = { tier_word: r.cardio_tier, confidence: r.confidence_tier };
    if (r.weight_class === 'CAREER') cardioMap[r.fighter_id].career = entry;
    else cardioMap[r.fighter_id].byWc[r.weight_class] = entry;
  }

  // Streaks left empty (same as validate.js — avoids hindsight bias on streaks
  // when re-running historical events, but for tonight's actual card this DOES
  // mean streak edges are missing from the snapshot). For the live snapshotter
  // these would be populated.
  const streakMap = {};

  let total = 0, correct = 0;
  const factorTally = {};

  for (const fight of fights) {
    const a = fighterMap[fight.fighter_a_id];
    const b = fighterMap[fight.fighter_b_id];
    if (!a || !b) { console.log(`  [skip] missing fighter row, fight ${fight.id}`); continue; }
    if (fight.winner_id == null) { console.log(`  ${a.name} vs ${b.name}: NO WINNER (NC / upcoming?)`); continue; }

    const ctx = { streakMap, cardioMap, fightWeightClass: fight.weight_class, eventDate: event.event_date };
    const { edges, aProb } = cflEdges.computeEdges(a, b, ctx);

    const predictedAWins = aProb > 0.5;
    const actualAWins = fight.winner_id === fight.fighter_a_id;
    const isCorrect = (predictedAWins === actualAWins) && edges.length > 0;
    const noPred = edges.length === 0;

    total += noPred ? 0 : 1;
    if (isCorrect) correct++;

    const predictedName = predictedAWins ? a.name : b.name;
    const actualName    = actualAWins    ? a.name : b.name;
    const confidence    = Math.max(aProb, 1 - aProb);
    const mark = noPred ? '—' : (isCorrect ? '✓' : '✗');

    console.log(`${mark} ${a.name} vs ${b.name}  [${fight.weight_class}${fight.is_main_event ? ', MAIN' : ''}]`);
    console.log(`    predicted: ${predictedName} (${(confidence*100).toFixed(1)}%)   actual: ${actualName}  via ${fight.method}`);

    if (edges.length === 0) {
      console.log(`    no edges fired`);
    } else {
      const loudest = edges.slice().sort((x,y) => y.pct - x.pct)[0];
      console.log(`    edges (${edges.length}):`);
      for (const e of edges) {
        const factorPicksA = e.favors === 'a';
        const factorPicksWinner = factorPicksA === actualAWins;
        const tag = factorPicksWinner ? '✓' : '✗';
        console.log(`      ${tag} ${e.factor.padEnd(13)} ${e.pct.toFixed(1)}% → ${e.fighterName}  (${e.desc})`);
        if (!factorTally[e.factor]) factorTally[e.factor] = { fired: 0, right: 0, loudest_n: 0, loudest_right: 0 };
        factorTally[e.factor].fired++;
        if (factorPicksWinner) factorTally[e.factor].right++;
        if (e === loudest) {
          factorTally[e.factor].loudest_n++;
          if (factorPicksWinner) factorTally[e.factor].loudest_right++;
        }
      }
    }
    console.log('');
  }

  console.log(`---`);
  console.log(`Overall: ${correct}/${total} = ${total ? (correct/total*100).toFixed(1) : '—'}%`);
  console.log('');
  console.log(`Per-factor on this card (fired = times the edge appeared, loudest = times it was the loudest edge of its fight):`);
  console.log(`factor          fired  right  acc     loudest  loudest_right`);
  const factors = Object.keys(factorTally).sort((x,y) => factorTally[y].fired - factorTally[x].fired);
  for (const f of factors) {
    const t = factorTally[f];
    const acc = t.fired ? (t.right / t.fired * 100).toFixed(0) + '%' : '—';
    console.log(`${f.padEnd(15)} ${String(t.fired).padEnd(6)} ${String(t.right).padEnd(6)} ${acc.padEnd(7)} ${String(t.loudest_n).padEnd(8)} ${t.loudest_right}`);
  }
})().catch(err => { console.error('event-drill failed:', err); process.exit(1); });
