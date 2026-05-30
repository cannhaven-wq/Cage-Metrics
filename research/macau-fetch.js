// =============================================================================
// research/macau-fetch.js — one-shot fetch of v5 picks + actual results
// =============================================================================
// Runs on a GitHub Actions runner (open internet) because the cloud dev sandbox
// can't reach the Supabase host. Zero deps: built-in fetch + the public anon
// key. Dumps everything needed to answer "what did v5 predict and what
// happened" for one event — both human-readable and raw JSON, so the exact
// model_predictions schema doesn't have to be guessed up front.
//
// Usage: node research/macau-fetch.js [eventId] [modelVersion]
// Default: event 113 (UFC Fight Night: Song vs. Figueiredo, Macau), model v5.
// =============================================================================

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SUPABASE_KEY = 'sb_publishable_boJGOA1CFN-SF14HHFGUAw_YEEm0DU8';

// Re-read trigger: bump to re-run the CI fetch against current Supabase state.
const eventId = process.argv[2] || '113';
const modelVersion = process.argv[3] || 'v5';

async function rest(path) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    headers: { apikey: SUPABASE_KEY, Authorization: `Bearer ${SUPABASE_KEY}` },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} on ${path}: ${await res.text()}`);
  return res.json();
}

const out = [];
const log = (s = '') => out.push(s);

(async () => {
  log(`# Macau fetch — event ${eventId}, model ${modelVersion}`);
  log(`Generated: ${new Date().toISOString()}\n`);

  // --- Event ---------------------------------------------------------------
  const events = await rest(`events?id=eq.${eventId}&select=*`);
  if (!events.length) { log(`No event id ${eventId}`); return finish(); }
  const ev = events[0];
  log(`## Event`);
  log(`#${ev.id}: ${ev.name}  (${ev.event_date}, upcoming=${ev.is_upcoming})\n`);

  // --- Fights (actual results) --------------------------------------------
  const fights = await rest(
    `fights?event_id=eq.${eventId}` +
    `&select=id,fighter_a_id,fighter_b_id,fighter_a_name,fighter_b_name,winner_id,method,end_round,weight_class,is_main_event` +
    `&order=is_main_event.desc,id.asc`
  );
  const fightById = {};
  fights.forEach((f) => (fightById[f.id] = f));
  const winnerName = (f) =>
    f.winner_id == null ? null
      : f.winner_id === f.fighter_a_id ? f.fighter_a_name
      : f.winner_id === f.fighter_b_id ? f.fighter_b_name
      : `id ${f.winner_id}`;

  log(`## Actual results (${fights.length} fights)`);
  for (const f of fights) {
    const w = winnerName(f);
    const tag = f.is_main_event ? ' [MAIN]' : '';
    if (w) log(`  ${f.fighter_a_name} vs ${f.fighter_b_name}${tag} → WON: ${w} (${f.method || '?'}${f.end_round ? `, R${f.end_round}` : ''})`);
    else   log(`  ${f.fighter_a_name} vs ${f.fighter_b_name}${tag} → not yet decided`);
  }
  log('');

  // --- v5 predictions ------------------------------------------------------
  const preds = await rest(
    `model_predictions?event_date=eq.${ev.event_date}` +
    `&model_version=eq.${encodeURIComponent(modelVersion)}&select=*`
  );
  log(`## ${modelVersion} predictions for ${ev.event_date}: ${preds.length} rows`);

  // Best-effort join to fights so we can show predicted-vs-actual.
  const fightKey = preds[0]
    ? ['fight_id', 'fightId', 'fight'].find((k) => k in preds[0])
    : null;
  const pickNameKey = preds[0]
    ? ['predicted_winner_name', 'pick_name', 'fighter_name', 'winner_name', 'predicted_name'].find((k) => k in preds[0])
    : null;

  let picks = 0, hits = 0, gradedPicks = 0;
  // Keep only the picked side (model_p > 0.5) of each fight.
  const picked = preds.filter((p) => Number(p.model_p) > 0.5);
  for (const p of picked) {
    const f = fightKey ? fightById[p[fightKey]] : null;
    const who = pickNameKey ? p[pickNameKey]
      : f ? `(fight ${p[fightKey]}: ${f.fighter_a_name} vs ${f.fighter_b_name})`
      : `(fight ${fightKey ? p[fightKey] : '?'})`;
    const conf = `${(Number(p.model_p) * 100).toFixed(1)}%`;
    let result = 'ungraded';
    if (p.outcome_known === true) {
      gradedPicks++; picks++;
      if (p.won === true) { hits++; result = '✓ HIT'; }
      else if (p.won === false) result = '✗ MISS';
      else result = '? (graded, won=null)';
    } else if (f && f.winner_id != null) {
      result = `actual: ${winnerName(f)} (pred not yet graded)`;
    }
    log(`  ${result.padEnd(28)} ${modelVersion} picked ${who} @ ${conf}`);
  }
  log('');
  log(`## ${modelVersion} accuracy on this card: ${hits}/${picks}` +
      (picks ? ` = ${((hits / picks) * 100).toFixed(1)}%` : ' (no graded picks)'));
  log('');

  // --- Raw JSON (so nothing is lost to schema guesses) --------------------
  log(`## RAW: model_predictions (${modelVersion})`);
  log('```json');
  log(JSON.stringify(preds, null, 2));
  log('```');
  log(`## RAW: fights`);
  log('```json');
  log(JSON.stringify(fights, null, 2));
  log('```');

  finish();
})().catch((err) => {
  log(`\nERROR: ${err.message || err}`);
  finish();
  process.exit(1);
});

function finish() {
  const fs = require('fs');
  const text = out.join('\n') + '\n';
  fs.writeFileSync('research/macau-result.md', text);
  process.stdout.write(text);
}
