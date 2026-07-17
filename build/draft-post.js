// Build script: generates a draft Reddit post + Twitter thread for the next
// UFC event, based on the current state of model_predictions + fighter data
// in Supabase. Output goes to stdout — copy-paste into Reddit and Twitter,
// tweak the intro line, post.
//
// Intended cadence:
//   - Wednesday before each card: run this, post to r/MMABetting and Twitter.
//   - Sunday after: run with --mode=recap (TODO: separate script) to grade.
//
// No secrets needed. Same publishable anon key as the rest of the site —
// everything we read here is anon-readable via RLS.
//
// Usage:
//   cd build && node draft-post.js
//   cd build && node draft-post.js > ../drafts/$(date +%Y-%m-%d).txt

const { createClient } = require('@supabase/supabase-js');

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SUPABASE_KEY = 'sb_publishable_boJGOA1CFN-SF14HHFGUAw_YEEm0DU8';
const SITE = 'https://cannonfightlab.com';

const sb = createClient(SUPABASE_URL, SUPABASE_KEY);

function todayUTC()     { return new Date().toISOString().slice(0, 10); }
function yesterdayUTC() { return new Date(Date.now() - 86400000).toISOString().slice(0, 10); }

// Pick the event to post about, using the same precedence as the homepage:
// happening-now (today or last night) → next upcoming → most recent past.
async function findEvent() {
  const t = todayUTC(); const y = yesterdayUTC();

  let r = await sb.from('events')
    .select('id, name, event_date, location, ufc_url')
    .gte('event_date', y).lte('event_date', t)
    .order('event_date', { ascending: false }).limit(1);
  if (r.data && r.data[0]) return { event: r.data[0], phase: 'happening' };

  r = await sb.from('events')
    .select('id, name, event_date, location, ufc_url')
    .eq('is_upcoming', true).gt('event_date', t)
    .order('event_date', { ascending: true }).limit(1);
  if (r.data && r.data[0]) return { event: r.data[0], phase: 'upcoming' };

  r = await sb.from('events')
    .select('id, name, event_date, location, ufc_url')
    .eq('is_upcoming', false)
    .order('event_date', { ascending: false }).limit(1);
  if (r.data && r.data[0]) return { event: r.data[0], phase: 'past' };

  throw new Error('No events found in DB');
}

// Reddit table cells: escape pipes and a couple of markdown specials so a
// fighter named "A.J." or a nickname with `_` doesn't break formatting.
function escMd(s) {
  if (s == null) return '';
  return String(s).replace(/\|/g, '\\|').replace(/([_*])/g, '\\$1');
}

function formatLongDate(isoDate) {
  const d = new Date(isoDate + 'T00:00:00');
  return d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
}

// Plain-English agreement label for the two public models (Value + Fight IQ).
// Handles the one-model case too (a fight only one model has graded).
function modelAgreementLabel(agree, total) {
  if (total <= 1) return '1 model';
  if (agree === total) return total === 2 ? 'both models' : `all ${total} models`;
  return `${agree} of ${total} models`;
}

async function main() {
  const { event, phase } = await findEvent();

  // All the data the draft needs, parallelized into one round trip.
  const { data: fights } = await sb.from('fights')
    .select('id, fighter_a_id, fighter_b_id, fighter_a_name, fighter_b_name, is_main_event, is_title_fight, weight_class')
    .eq('event_id', event.id)
    .order('is_main_event', { ascending: false })
    .order('id', { ascending: true });

  const fighterIds = [...new Set((fights || []).flatMap(f => [f.fighter_a_id, f.fighter_b_id]).filter(Boolean))];
  const fightIds = (fights || []).map(f => f.id);

  if (!fightIds.length) {
    console.error(`[draft-post] event "${event.name}" has no fights yet — bail.`);
    process.exit(2);
  }

  const [fightersR, predsR, cardioR, finishR] = await Promise.all([
    sb.from('fighters').select('id, name, nickname').in('id', fighterIds),
    // Public models only ('v6' Value, 'v3' Fight IQ). Node script — window.cfl
    // doesn't exist here; source of truth is cfl.PUBLIC_MODELS in _shared.js.
    sb.from('model_predictions').select('model_version, fight_id, fighter_id, model_p').in('fight_id', fightIds).in('model_version', ['v6', 'v3']),
    sb.from('v_fighter_consistency').select('fighter_id, weight_class, cardio_tier').in('fighter_id', fighterIds),
    sb.from('v_fighter_finish_rate').select('fighter_id, total_fights, ko_tko_rate, sub_rate').in('fighter_id', fighterIds),
  ]);

  const fmap = {};
  (fightersR.data || []).forEach(f => { fmap[f.id] = f; });

  // picksByFight[fight_id][model_version] = { fighter_id, model_p }
  // Only count a model as "picking" a side if its probability > 0.5.
  const picksByFight = {};
  (predsR.data || []).forEach(p => {
    if (p.model_p == null || +p.model_p <= 0.5) return;
    const slot = picksByFight[p.fight_id] || (picksByFight[p.fight_id] = {});
    slot[p.model_version] = { fighter_id: p.fighter_id, model_p: +p.model_p };
  });

  // Cardio (CAREER row only — the per-weight-class rows are noise for a one-line note).
  const cardio = {};
  (cardioR.data || []).forEach(r => {
    if (r.weight_class === 'CAREER') cardio[r.fighter_id] = r.cardio_tier;
  });

  const finish = {};
  (finishR.data || []).forEach(r => { finish[r.fighter_id] = r; });

  // Build one "line" per fight that has at least one model pick. Fights with
  // no graded prediction (e.g. added after the last training run) are skipped
  // — better to omit than to post an empty row.
  const lines = [];
  for (const f of (fights || [])) {
    const a = fmap[f.fighter_a_id]; const b = fmap[f.fighter_b_id];
    if (!a || !b) continue;
    const picks = picksByFight[f.id] || {};
    const versions = Object.keys(picks).sort();
    if (!versions.length) continue;

    // Consensus side = the fighter most models picked.
    const tally = {};
    versions.forEach(v => {
      tally[picks[v].fighter_id] = (tally[picks[v].fighter_id] || 0) + 1;
    });
    const sortedSides = Object.entries(tally).sort((x, y) => y[1] - x[1]);
    const winnerId = +sortedSides[0][0];
    const winner = fmap[winnerId];
    const loser  = winner.id === a.id ? b : a;
    const agree  = sortedSides[0][1];
    const total  = versions.length;

    // Average model_p across models that agreed on the consensus side.
    const winningPs = versions
      .filter(v => picks[v].fighter_id === winnerId)
      .map(v => picks[v].model_p);
    const avgP = winningPs.reduce((s, x) => s + x, 0) / winningPs.length;

    // One short edge note. Priority:
    //   1. Loser cardio bad → "fades/collapses/tapers"
    //   2. Winner is a finisher (8+ fights, ≥60% finish rate)
    //   3. (blank)
    let note = '';
    const loserCardio = cardio[loser.id];
    if (loserCardio === 'fades' || loserCardio === 'collapses' || loserCardio === 'tapers') {
      note = `${loser.name} ${loserCardio} late`;
    } else {
      const wf = finish[winner.id];
      if (wf && wf.total_fights >= 8) {
        const fr = (wf.ko_tko_rate || 0) + (wf.sub_rate || 0);
        if (fr >= 0.6) note = `${winner.name} finishes ${Math.round(fr * 100)}% of wins`;
      }
    }

    let flag = '';
    if (f.is_title_fight) flag = ' [TITLE]';
    else if (f.is_main_event) flag = ' [MAIN]';

    lines.push({
      aName: a.name, bName: b.name, flag,
      pickName: winner.name,
      pct: Math.round(avgP * 100),
      agree, total,
      agreeLabel: modelAgreementLabel(agree, total),
      note,
    });
  }

  if (!lines.length) {
    console.error(`[draft-post] no model picks exist for any fight on "${event.name}" yet — bail.`);
    process.exit(3);
  }

  const dateLabel = formatLongDate(event.event_date);
  const eventUrl  = `${SITE}/event.html?id=${event.id}`;
  const picksUrl  = `${SITE}/picks.html`;
  const trackUrl  = `${SITE}/track-record.html`;

  // ----- Reddit markdown -----
  const r = [];
  r.push(`# ${event.name} — model picks before the card`);
  r.push('');
  r.push(`**${dateLabel}**${event.location ? ` · ${event.location}` : ''}`);
  r.push('');
  r.push(`Posting the verdicts here *before* the fights so the receipts are time-stamped. Grading thread Sunday — wins and misses, no edits.`);
  r.push('');
  r.push(`| Fight | Model pick | Confidence | Note |`);
  r.push(`|---|---|---|---|`);
  for (const l of lines) {
    r.push(`| ${escMd(l.aName)} vs ${escMd(l.bName)}${l.flag} | **${escMd(l.pickName)}** | ${l.pct}% (${l.agreeLabel}) | ${escMd(l.note)} |`);
  }
  r.push('');
  r.push(`Per-fight breakdown with the edge factors that drove each verdict: ${eventUrl}`);
  r.push(`Rolling accuracy across every prior card: ${trackUrl}`);
  r.push('');
  r.push(`*Free tool. No Discord, no DMs, no capped picks. Free account unlocks every edge factor, saved picks, and the weekly preview email: ${SITE}/signup.html?src=reddit*`);

  // ----- Twitter thread -----
  // Tweet 1 = hook + link. Then one tweet per fight (truncated to 280 with
  // the warning printed if any tweet would exceed). Final tweet = receipts CTA.
  const tweets = [];
  tweets.push(
    `🥊 ${event.name} — model picks, posted BEFORE the card so the receipts are timestamped.\n\n` +
    `${dateLabel}\n\n` +
    `Full breakdown: ${eventUrl}\n\n` +
    `Fights ↓`
  );
  for (const l of lines) {
    let tweet = `${l.aName} vs ${l.bName}${l.flag}\n` +
                `→ ${l.pickName} (${l.pct}%, ${l.agreeLabel})`;
    if (l.note) tweet += `\n${l.note}`;
    tweets.push(tweet);
  }
  tweets.push(
    `Grading thread Sunday. Track record never deletes a missed call.\n\n` +
    `Free account unlocks every edge factor + the weekly preview email:\n` +
    `${SITE}/signup.html?src=x`
  );

  process.stdout.write('=================== REDDIT (paste into r/MMABetting) ===================\n\n');
  process.stdout.write(r.join('\n') + '\n');
  process.stdout.write('\n\n=================== TWITTER / X THREAD ===================\n\n');
  tweets.forEach((t, i) => {
    const over = t.length > 280 ? ` ⚠️ OVER 280` : '';
    process.stdout.write(`--- Tweet ${i + 1} (${t.length} chars${over}) ---\n${t}\n\n`);
  });
}

main().catch(err => {
  console.error('[draft-post] failed:', err);
  process.exit(1);
});
