// =============================================================================
// research/model-event-accuracy.js — Per-event accuracy for a trained ML model
// =============================================================================
// Reports a single trained model's graded-pick accuracy on one event, straight
// from the `model_predictions` table — the same source the homepage and
// event.html per-event model breakdown read from.
//
// Usage:
//   node model-event-accuracy.js [eventId] [modelVersion]
//
// Defaults to the Macau card (event 113 — UFC Fight Night: Song vs. Figueiredo)
// and model v5:
//   node model-event-accuracy.js            # -> event 113, v5
//   node model-event-accuracy.js 113 v5
//   node model-event-accuracy.js 113 v4
//
// Zero dependencies — uses the built-in global fetch (Node 18+) and the public
// anon key, so no `npm install` is needed. Run it from a machine whose network
// can reach the Supabase host (the CI/cloud sandbox blocks it).
//
// Accuracy convention matches the frontend: count one pick per fight (the side
// the model gave model_p > 0.5), restricted to graded fights (outcome_known =
// true), and a pick is a hit when `won` is true.
// =============================================================================

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SUPABASE_KEY = 'sb_publishable_boJGOA1CFN-SF14HHFGUAw_YEEm0DU8';

const eventId = process.argv[2] || '113';
const modelVersion = process.argv[3] || 'v5';

async function rest(path) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    headers: { apikey: SUPABASE_KEY, Authorization: `Bearer ${SUPABASE_KEY}` },
  });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} on ${path}: ${await res.text()}`);
  }
  return res.json();
}

(async () => {
  // 1. Resolve the event so we know its name + date.
  const events = await rest(
    `events?id=eq.${eventId}&select=id,name,event_date,is_upcoming`
  );
  if (!events.length) {
    console.error(`No event with id ${eventId}`);
    process.exit(1);
  }
  const event = events[0];
  console.log(
    `\nEvent #${event.id}: ${event.name}  (${event.event_date}, upcoming=${event.is_upcoming})`
  );
  console.log(`Model: ${modelVersion}\n`);

  // 2. Pull this model's predictions for the event. model_predictions is keyed
  //    by event_date on the frontend; we filter the same way and scope to this
  //    model. If two events share a date this would mix them — flagged below.
  const preds = await rest(
    `model_predictions?event_date=eq.${event.event_date}` +
      `&model_version=eq.${encodeURIComponent(modelVersion)}` +
      `&select=*&order=model_p.desc`
  );

  if (!preds.length) {
    console.log(`No ${modelVersion} predictions found for ${event.event_date}.`);
    console.log(
      `(The snapshotter may not have logged picks for this card, or the ` +
        `model id differs — try a different version.)`
    );
    process.exit(0);
  }

  // Sanity: did other events land on the same date? If so, accuracy below is
  // for the date, not strictly this event.
  const sameDay = await rest(
    `events?event_date=eq.${event.event_date}&select=id,name`
  );
  if (sameDay.length > 1) {
    console.log(
      `⚠  ${sameDay.length} events share ${event.event_date} — model_predictions ` +
        `is keyed by date, so the numbers below cover all of them:`
    );
    sameDay.forEach((e) => console.log(`     #${e.id} ${e.name}`));
    console.log('');
  }

  // 3. Tally exactly as the frontend does: picked side = model_p > 0.5, graded
  //    only, hit = won === true.
  let picks = 0,
    hits = 0,
    graded = 0,
    ungraded = 0;
  for (const p of preds) {
    if (Number(p.model_p) <= 0.5) continue; // only the picked side of each fight
    if (p.outcome_known !== true) {
      ungraded++;
      continue;
    }
    graded++;
    picks++;
    if (p.won === true) hits++;
  }

  // 4. Per-fight detail, best-effort on whatever name columns exist.
  const nameKey =
    ['predicted_winner_name', 'pick_name', 'fighter_name', 'winner_name'].find(
      (k) => k in preds[0]
    ) || null;
  console.log('Picked side per fight (graded only):');
  for (const p of preds) {
    if (Number(p.model_p) <= 0.5) continue;
    if (p.outcome_known !== true) continue;
    const mark = p.won === true ? '✓' : p.won === false ? '✗' : '?';
    const who = nameKey ? p[nameKey] : `fight ${p.fight_id ?? p.id ?? '?'}`;
    console.log(`  ${mark} ${who}  (${(Number(p.model_p) * 100).toFixed(1)}%)`);
  }

  console.log('\n---');
  if (picks > 0) {
    console.log(
      `${modelVersion} on "${event.name}": ${hits}/${picks} = ` +
        `${((hits / picks) * 100).toFixed(1)}%`
    );
  } else {
    console.log(`${modelVersion} on "${event.name}": no graded picks yet.`);
  }
  if (ungraded > 0) {
    console.log(`(${ungraded} picked fights still ungraded / not yet decided.)`);
  }
  console.log('');
})().catch((err) => {
  console.error('model-event-accuracy failed:', err.message || err);
  process.exit(1);
});
