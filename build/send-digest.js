// Weekly preview-email sender. Runs on Wednesday morning UTC via the
// digest.yml workflow. Pulls the next upcoming UFC card from Supabase,
// renders the same per-fight verdict + edge breakdown that draft-post.js
// uses, and emails it to every active row in email_subscribers via Resend.
//
// Funnel hand-off: the email body contains a "Create free account →" CTA
// pointing at signup.html?src=digest so we can attribute account signups
// back to the digest in analytics.
//
// Environment variables (all set as repo secrets — see TRAFFIC_FUNNEL.md):
//   RESEND_API_KEY                — Resend API key (required for live send)
//   RESEND_FROM                   — e.g. "Cannon Fight Lab <hello@cannonfightlab.com>"
//                                   (Resend requires a verified sender domain)
//   SUPABASE_SERVICE_ROLE_KEY     — service-role key, bypasses RLS so we can
//                                   read email_subscribers
//   DIGEST_DRY_RUN                — "1" or "true" → render + log, never send
//
// Without RESEND_API_KEY the script falls back to dry-run automatically —
// it prints what it WOULD send and exits 0. That way the workflow on a fresh
// fork doesn't fail; you only flip the switch by adding the secret.

const { createClient } = require('@supabase/supabase-js');

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SUPABASE_ANON_KEY = 'sb_publishable_boJGOA1CFN-SF14HHFGUAw_YEEm0DU8';
const SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
const RESEND_KEY  = process.env.RESEND_API_KEY;
const FROM        = process.env.RESEND_FROM || 'Cannon Fight Lab <hello@cannonfightlab.com>';
const DRY_RUN     = !RESEND_KEY || /^(1|true|yes)$/i.test(process.env.DIGEST_DRY_RUN || '');
const SITE        = 'https://cannonfightlab.com';

// Service key bypasses RLS so we can read email_subscribers; fall back to
// the anon key for dry-run mode where we're not actually sending.
const sb = createClient(SUPABASE_URL, SERVICE_KEY || SUPABASE_ANON_KEY);

const todayUTC = () => new Date().toISOString().slice(0, 10);

function escHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

function formatLongDate(isoDate) {
  if (!isoDate) return '';
  const d = new Date(isoDate + 'T00:00:00');
  return d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
}

// Plain-English agreement label for the two public models (Value + Fight IQ).
// Handles the one-model case too (a fight only one model has graded).
function modelAgreementLabel(agree, total) {
  if (total <= 1) return 'the engine';
  if (agree === total) return total === 2 ? 'both models' : `all ${total} models`;
  return `${agree} of ${total} models`;
}

async function findNextEvent() {
  const t = todayUTC();
  const { data, error } = await sb
    .from('events')
    .select('id, name, event_date, location, ufc_url')
    .eq('is_upcoming', true)
    .gte('event_date', t)
    .order('event_date', { ascending: true })
    .limit(1);
  if (error) throw error;
  return (data && data[0]) || null;
}

async function buildVerdictLines(event) {
  const { data: fights } = await sb.from('fights')
    .select('id, fighter_a_id, fighter_b_id, fighter_a_name, fighter_b_name, is_main_event, is_title_fight, weight_class')
    .eq('event_id', event.id)
    .order('is_main_event', { ascending: false })
    .order('id', { ascending: true });
  if (!fights || !fights.length) return [];

  const fightIds   = fights.map(f => f.id);
  const fighterIds = [...new Set(fights.flatMap(f => [f.fighter_a_id, f.fighter_b_id]).filter(Boolean))];

  const [predsR, cardioR] = await Promise.all([
    // Engine picks (model_picks) — the one current model. A locked 'live' row
    // outranks a 'backtest' replay row for the same fight. The retired
    // v3/v6 model_predictions are archive-only and never publish here.
    sb.from('model_picks')
      .select('fight_id, pick_fighter_id, p_cal, source')
      .in('fight_id', fightIds),
    sb.from('v_fighter_consistency')
      .select('fighter_id, weight_class, cardio_tier')
      .in('fighter_id', fighterIds)
  ]);

  const engineByFight = {};
  (predsR.data || []).forEach(p => {
    const prev = engineByFight[p.fight_id];
    if (prev && prev.source === 'live' && p.source !== 'live') return;
    engineByFight[p.fight_id] = p;
  });
  const picksByFight = {};
  Object.values(engineByFight).forEach(p => {
    if (p.p_cal == null) return;
    (picksByFight[p.fight_id] = picksByFight[p.fight_id] || {}).engine =
      { fighter_id: p.pick_fighter_id, model_p: +p.p_cal };
  });
  const cardio = {};
  (cardioR.data || []).forEach(r => {
    if (r.weight_class === 'CAREER') cardio[r.fighter_id] = r.cardio_tier;
  });

  const lines = [];
  for (const f of fights) {
    const picks = picksByFight[f.id] || {};
    const versions = Object.keys(picks);
    if (!versions.length) continue;
    const tally = {};
    versions.forEach(v => { tally[picks[v].fighter_id] = (tally[picks[v].fighter_id] || 0) + 1; });
    const sorted = Object.entries(tally).sort((x, y) => y[1] - x[1]);
    const winnerId = +sorted[0][0];
    const aSide = winnerId === f.fighter_a_id;
    const winnerName = aSide ? f.fighter_a_name : f.fighter_b_name;
    const loserName  = aSide ? f.fighter_b_name : f.fighter_a_name;
    const winningPs = versions
      .filter(v => picks[v].fighter_id === winnerId)
      .map(v => picks[v].model_p);
    const avg = winningPs.reduce((s, x) => s + x, 0) / winningPs.length;
    const note = (() => {
      const lc = cardio[aSide ? f.fighter_b_id : f.fighter_a_id];
      if (lc === 'fades' || lc === 'collapses' || lc === 'tapers') return `${loserName} ${lc} late`;
      return '';
    })();
    lines.push({
      aName: f.fighter_a_name,
      bName: f.fighter_b_name,
      flag: f.is_title_fight ? 'TITLE' : (f.is_main_event ? 'MAIN' : ''),
      pickName: winnerName,
      pct: Math.round(avg * 100),
      agree: sorted[0][1],
      total: versions.length,
      agreeLabel: modelAgreementLabel(sorted[0][1], versions.length),
      note
    });
  }
  return lines;
}

function renderHtml({ event, lines, unsubscribeToken }) {
  const eventUrl = `${SITE}/event.html?id=${event.id}`;
  const signupUrl = `${SITE}/signup.html?src=digest`;
  const unsubUrl = `${SITE}/unsubscribe.html?token=${encodeURIComponent(unsubscribeToken || '')}`;

  const rows = lines.map(l => `
    <tr>
      <td style="padding:10px 8px;border-bottom:1px solid #2a2a2a;color:#e8e8e8;">
        ${escHtml(l.aName)} <span style="color:#777;">vs</span> ${escHtml(l.bName)}
        ${l.flag ? ` <span style="color:#e63946;font-size:11px;font-weight:700;letter-spacing:1px;">[${l.flag}]</span>` : ''}
      </td>
      <td style="padding:10px 8px;border-bottom:1px solid #2a2a2a;color:#fff;font-weight:600;">${escHtml(l.pickName)}</td>
      <td style="padding:10px 8px;border-bottom:1px solid #2a2a2a;color:#bbb;white-space:nowrap;">${l.pct}% <span style="color:#777;">(${l.agreeLabel})</span></td>
    </tr>
    ${l.note ? `<tr><td colspan="3" style="padding:0 8px 10px;color:#999;font-size:13px;font-style:italic;border-bottom:1px solid #2a2a2a;">↳ ${escHtml(l.note)}</td></tr>` : ''}
  `).join('');

  return `<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#0a0a0a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#0a0a0a;padding:24px 0;">
  <tr><td align="center">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="max-width:600px;width:100%;">
      <tr><td style="padding:0 20px 18px;">
        <div style="font-family:'Barlow Condensed',Impact,sans-serif;font-size:24px;font-weight:800;color:#fff;letter-spacing:1px;">
          CANNON FIGHT <span style="color:#e63946;">LAB</span>
        </div>
      </td></tr>

      <tr><td style="padding:0 20px 6px;">
        <div style="color:#e63946;font-size:11px;letter-spacing:1.5px;font-weight:700;text-transform:uppercase;">This week's card</div>
        <h1 style="margin:6px 0 4px;font-size:24px;color:#fff;line-height:1.25;">${escHtml(event.name)}</h1>
        <div style="color:#999;font-size:14px;">${escHtml(formatLongDate(event.event_date))}${event.location ? ' &middot; ' + escHtml(event.location) : ''}</div>
      </td></tr>

      <tr><td style="padding:20px;">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#111;border:1px solid #222;border-radius:8px;">
          <tr>
            <th align="left" style="padding:10px 8px;border-bottom:1px solid #2a2a2a;color:#999;font-size:11px;letter-spacing:1px;text-transform:uppercase;font-weight:600;">Fight</th>
            <th align="left" style="padding:10px 8px;border-bottom:1px solid #2a2a2a;color:#999;font-size:11px;letter-spacing:1px;text-transform:uppercase;font-weight:600;">Model pick</th>
            <th align="left" style="padding:10px 8px;border-bottom:1px solid #2a2a2a;color:#999;font-size:11px;letter-spacing:1px;text-transform:uppercase;font-weight:600;">Confidence</th>
          </tr>
          ${rows || '<tr><td colspan="3" style="padding:14px;color:#999;">Verdicts publishing closer to fight night.</td></tr>'}
        </table>
      </td></tr>

      <tr><td style="padding:8px 20px 28px;">
        <a href="${eventUrl}" style="color:#e63946;text-decoration:none;font-weight:600;">View the full card with edges →</a>
      </td></tr>

      <tr><td style="padding:0 20px;">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:linear-gradient(135deg,#e63946,#c1121f);border-radius:8px;">
          <tr><td style="padding:22px 24px;">
            <div style="color:#fff;font-weight:700;font-size:16px;margin-bottom:6px;">Track your picks on a free account</div>
            <div style="color:#fff;opacity:0.9;font-size:13px;margin-bottom:14px;">Save fighters to your watchlist, see every model verdict, and unlock all edge factors. Free during beta.</div>
            <a href="${signupUrl}" style="background:#fff;color:#c1121f;padding:10px 22px;border-radius:6px;font-weight:700;text-decoration:none;display:inline-block;font-size:14px;">Create free account →</a>
          </td></tr>
        </table>
      </td></tr>

      <tr><td style="padding:28px 20px 8px;color:#666;font-size:12px;line-height:1.5;text-align:center;">
        Cannon Fight Lab is an analytics publication, not a sportsbook. 21+ only. 1-800-GAMBLER.
      </td></tr>
      <tr><td style="padding:0 20px 20px;color:#555;font-size:11px;text-align:center;">
        You're subscribed to the Cannon Fight Lab weekly fight preview.
        <a href="${unsubUrl}" style="color:#888;">Unsubscribe</a>
      </td></tr>

    </table>
  </td></tr>
</table>
</body></html>`;
}

function renderText({ event, lines, unsubscribeToken }) {
  const eventUrl = `${SITE}/event.html?id=${event.id}`;
  const signupUrl = `${SITE}/signup.html?src=digest`;
  const unsubUrl = `${SITE}/unsubscribe.html?token=${unsubscribeToken || ''}`;
  const out = [];
  out.push(`CANNON FIGHT LAB — ${event.name}`);
  out.push(formatLongDate(event.event_date) + (event.location ? ' · ' + event.location : ''));
  out.push('');
  out.push('Model picks (locked in before the bell):');
  out.push('');
  for (const l of lines) {
    const flag = l.flag ? ` [${l.flag}]` : '';
    out.push(`  ${l.aName} vs ${l.bName}${flag}`);
    out.push(`    → ${l.pickName} (${l.pct}%, ${l.agreeLabel})`);
    if (l.note) out.push(`    ↳ ${l.note}`);
    out.push('');
  }
  out.push(`Full card with edges: ${eventUrl}`);
  out.push('');
  out.push('Create a free account to track picks and unlock every edge:');
  out.push(`  ${signupUrl}`);
  out.push('');
  out.push('---');
  out.push(`Unsubscribe: ${unsubUrl}`);
  out.push('Cannon Fight Lab is an analytics publication, not a sportsbook. 21+ only.');
  return out.join('\n');
}

async function fetchActiveSubscribers() {
  if (!SERVICE_KEY) {
    console.warn('[digest] no SUPABASE_SERVICE_ROLE_KEY set — using anon key.');
    console.warn('[digest] RLS will return an empty list. Set the secret to actually read subscribers.');
  }
  const all = [];
  let from = 0;
  const pageSize = 1000;
  while (true) {
    const { data, error } = await sb
      .from('email_subscribers')
      .select('email, unsubscribe_token')
      .is('unsubscribed_at', null)
      .range(from, from + pageSize - 1);
    if (error) throw error;
    if (!data || !data.length) break;
    all.push(...data);
    if (data.length < pageSize) break;
    from += pageSize;
  }
  return all;
}

async function sendOne({ to, subject, html, text }) {
  if (DRY_RUN) {
    console.log(`[dry-run] would send to ${to} — subject: "${subject}" (${html.length} chars html, ${text.length} chars text)`);
    return { ok: true, dryRun: true };
  }
  const res = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${RESEND_KEY}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ from: FROM, to: [to], subject, html, text })
  });
  if (!res.ok) {
    const bodyText = await res.text();
    return { ok: false, status: res.status, error: bodyText };
  }
  return { ok: true };
}

async function markSent(emails) {
  if (DRY_RUN || !emails.length) return;
  // Bulk update — Postgres accepts an IN clause through PostgREST.
  const { error } = await sb
    .from('email_subscribers')
    .update({ last_sent_at: new Date().toISOString() })
    .in('email', emails);
  if (error) console.warn('[digest] last_sent_at update failed:', error.message);
}

(async () => {
  try {
    const event = await findNextEvent();
    if (!event) { console.log('[digest] no upcoming events — nothing to send.'); return; }
    console.log(`[digest] next event: ${event.name} (${event.event_date})`);

    const lines = await buildVerdictLines(event);
    console.log(`[digest] ${lines.length} fights with verdicts.`);
    if (!lines.length) {
      console.log('[digest] no model picks yet for this card — skipping send.');
      return;
    }

    const subscribers = await fetchActiveSubscribers();
    console.log(`[digest] ${subscribers.length} active subscribers.`);
    if (!subscribers.length) {
      console.log('[digest] no subscribers — nothing to send.');
      return;
    }

    const subject = `${event.name} — model picks before the card`;
    let sent = 0;
    let failed = 0;
    const sentEmails = [];
    for (const sub of subscribers) {
      const html = renderHtml({ event, lines, unsubscribeToken: sub.unsubscribe_token });
      const text = renderText({ event, lines, unsubscribeToken: sub.unsubscribe_token });
      const r = await sendOne({ to: sub.email, subject, html, text });
      if (r.ok) { sent++; sentEmails.push(sub.email); }
      else { failed++; console.warn(`[digest] send to ${sub.email} failed:`, r.status, r.error); }
      // Resend free tier ≈ 2 req/sec — naive throttle.
      if (!DRY_RUN) await new Promise(r => setTimeout(r, 600));
    }
    await markSent(sentEmails);
    console.log(`[digest] done. sent=${sent} failed=${failed} dry_run=${DRY_RUN}`);
  } catch (err) {
    console.error('[digest] failed:', err);
    process.exit(1);
  }
})();
