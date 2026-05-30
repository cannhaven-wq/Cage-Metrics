// =============================================================================
// research/macau-backfill.js — write Macau (event 113) results into Supabase
// =============================================================================
// One-off backfill because ufcstats blocks datacenter IPs, so the Railway
// scraper can't fetch the results. Runs on a GitHub runner with the
// SUPABASE_SERVICE_ROLE_KEY secret (bypasses RLS). Results transcribed from the
// official ufcstats event page (winner listed first per bout).
//
//   events:            is_upcoming = false on #113
//   fights:            winner_id + method + end_round on all 13 bouts
//   model_predictions: grade every model's picks (outcome_known, won) for the
//                      decided fights; the No-Contest fight is left ungraded.
//
// Idempotent: safe to re-run. If the scraper is ever fixed it will simply
// re-upsert the same values.
// =============================================================================

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
const EVENT_ID = 113;
const EVENT_DATE = '2026-05-30';

// fight_id -> { winner: fighter_id|null, method, round }   (null winner = NC)
const RESULTS = {
  38:    { winner: 1200,  method: 'Submission',          round: 2 }, // Song Yadong (Guillotine)
  39:    { winner: 2559,  method: 'KO/TKO',              round: 1 }, // Alonzo Menifield (Punch)
  40:    { winner: 1488,  method: 'KO/TKO',              round: 1 }, // Sergei Pavlovich (Punch)
  41:    { winner: 2981,  method: 'KO/TKO',              round: 1 }, // Kai Asakura (Punch)
  42:    { winner: null,  method: 'No Contest',          round: 2 }, // Perez vs Sumudaerji (CNC)
  43:    { winner: 2938,  method: 'Decision - Unanimous', round: 3 }, // Jake Matthews
  44:    { winner: 4266,  method: 'KO/TKO',              round: 1 }, // Luis Felipe Dias (Punch)
  45:    { winner: 44,    method: 'KO/TKO',              round: 2 }, // Cody Haddon (Knee)
  46:    { winner: 2353,  method: 'Submission',          round: 1 }, // Rei Tsuruya (RNC)
  47:    { winner: 1021,  method: 'Decision - Unanimous', round: 3 }, // Angela Hill
  48:    { winner: 2549,  method: 'Submission',          round: 1 }, // Jaqueline Amorim (Armbar)
  8780:  { winner: 10976, method: 'KO/TKO',              round: 1 }, // Rodrigo Vera (Punches)
  26712: { winner: 4039,  method: 'Decision - Split',     round: 3 }, // Jose Henrique
};

const out = [];
const log = (s = '') => out.push(s);

function headers(extra = {}) {
  return { apikey: SERVICE_KEY, Authorization: `Bearer ${SERVICE_KEY}`, 'Content-Type': 'application/json', ...extra };
}
async function patch(path, body) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    method: 'PATCH', headers: headers({ Prefer: 'return=minimal' }), body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`PATCH ${path} -> ${res.status} ${res.statusText}: ${await res.text()}`);
}
async function get(path) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, { headers: headers() });
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}: ${await res.text()}`);
  return res.json();
}

(async () => {
  log(`# Macau backfill — event ${EVENT_ID}`);
  log(`Generated: ${new Date().toISOString()}\n`);
  if (!SERVICE_KEY) { log('ABORT: SUPABASE_SERVICE_ROLE_KEY not set (dry run, no writes).'); return finish(1); }

  // 1) mark event completed
  await patch(`events?id=eq.${EVENT_ID}`, { is_upcoming: false });
  log(`✓ events #${EVENT_ID}: is_upcoming=false`);

  // 2) write fight results
  for (const [fid, r] of Object.entries(RESULTS)) {
    await patch(`fights?id=eq.${fid}`, { winner_id: r.winner, method: r.method, end_round: r.round });
    log(`✓ fight ${fid}: winner_id=${r.winner ?? 'NULL (NC)'}  ${r.method} R${r.round}`);
  }

  // 3) grade every model's predictions for the decided fights
  const preds = await get(`model_predictions?event_date=eq.${EVENT_DATE}&select=id,fight_id,fighter_id,model_version`);
  let graded = 0, skipped = 0;
  for (const p of preds) {
    const r = RESULTS[p.fight_id];
    if (!r || r.winner == null) { skipped++; continue; } // unknown fight or No-Contest -> leave ungraded
    await patch(`model_predictions?id=eq.${p.id}`, { outcome_known: true, won: p.fighter_id === r.winner });
    graded++;
  }
  log(`✓ model_predictions graded: ${graded}  (skipped ungraded/NC: ${skipped})`);
  log('');

  // 4) verify
  const ev = await get(`events?id=eq.${EVENT_ID}&select=id,is_upcoming`);
  const acc = await get(`v_event_accuracy?event_id=eq.${EVENT_ID}&select=*`).catch((e) => `ERR ${e.message}`);
  log(`## verify event: ${JSON.stringify(ev)}`);
  log(`## verify v_event_accuracy: ${JSON.stringify(acc)}`);
  finish(0);
})().catch((e) => { log(`\nERROR: ${e.message}`); finish(1); });

function finish(code) {
  require('fs').writeFileSync('research/macau-backfill-result.md', out.join('\n') + '\n');
  process.stdout.write(out.join('\n') + '\n');
  process.exit(code);
}
