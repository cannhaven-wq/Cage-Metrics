// THE CANNON CARD BRIEF — one email before each UFC card. Runs on Wednesday
// morning UTC via the digest.yml workflow. Pulls the next upcoming card from
// Supabase, reports what the market has done to it — the biggest line moves,
// where the sportsbooks disagree most, how much of the card is priced and how
// fresh those prices are — and emails it to every active row in
// email_subscribers via Resend.
//
// It used to send a "Model pick / Confidence" table. It does not any more:
// CFL stopped publishing a forecast in September 2026 when it could not be
// shown to beat the market price. The Brief's promise is "know what changed
// before fight night", never "here are our picks".
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

// modelAgreementLabel() used to live here — the Brief no longer reports how
// many models agreed on a pick, because it no longer reports a pick.

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

// One line per priced fight: where the market sits, how far it has moved
// since our first capture and over the last 24 hours, and how far apart the
// books are. Sorted by absolute movement, because "what changed" is the
// point of the email.
//
// Reads v_fight_market_movement, which is a definer view — `fight_odds`
// itself is admin-only, so a direct read here returns nothing under the anon
// key and only works by accident under the service key.
async function buildMarketLines(event) {
  const { data: fights } = await sb.from('fights')
    .select('id, fighter_a_id, fighter_b_id, fighter_a_name, fighter_b_name, is_main_event, is_title_fight, weight_class')
    .eq('event_id', event.id)
    .order('is_main_event', { ascending: false })
    .order('id', { ascending: true });
  if (!fights || !fights.length) return [];

  const { data: mkt, error } = await sb
    .from('v_fight_market_movement').select('*').eq('event_id', event.id);
  if (error) { console.warn('[brief] market view unavailable:', error.message); return []; }
  const byFight = {};
  (mkt || []).forEach(r => { byFight[r.fight_id] = r; });

  const lines = [];
  for (const f of fights) {
    const r = byFight[f.id];
    if (!r || r.market_p_a == null) continue;
    const pA = +r.market_p_a;
    const open = r.open_p_a == null ? null : +r.open_p_a;
    const h24  = r.market_p_a_24h == null ? null : +r.market_p_a_24h;
    const move = open == null ? null : (pA - open) * 100;
    const move24 = h24 == null ? null : (pA - h24) * 100;
    const favIsA = pA >= 0.5;
    lines.push({
      aName: f.fighter_a_name,
      bName: f.fighter_b_name,
      flag: f.is_title_fight ? 'TITLE' : (f.is_main_event ? 'MAIN' : ''),
      favName: favIsA ? f.fighter_a_name : f.fighter_b_name,
      favPct: Math.round((favIsA ? pA : 1 - pA) * 100),
      bestAmerican: favIsA ? r.best_american_a : r.best_american_b,
      bestBook: favIsA ? r.best_book_a : r.best_book_b,
      books: r.book_count == null ? null : +r.book_count,
      booksAtOpen: r.books_at_open == null ? null : +r.books_at_open,
      spread: r.book_spread_pts == null ? null : +r.book_spread_pts,
      move, move24,
      moveToward: move == null ? null : (move > 0 ? f.fighter_a_name : f.fighter_b_name),
      move24Toward: move24 == null ? null : (move24 > 0 ? f.fighter_a_name : f.fighter_b_name),
      lastUpdated: r.last_updated,
      fightId: f.id,
    });
  }
  lines.sort((x, y) => Math.abs(y.move || 0) - Math.abs(x.move || 0));
  return lines;
}

// Surname for tight copy. A generational suffix is not a name — "Raul Rosas
// Jr." is Rosas, not Jr. Same rule as fight-insights.js::lastName; kept in
// step by hand because build/ has no browser modules.
const NAME_SUFFIX = /^(jr\.?|sr\.?|ii|iii|iv|v)$/i;
function lastName(n) {
  const parts = String(n || '').trim().split(/\s+/);
  while (parts.length > 1 && NAME_SUFFIX.test(parts[parts.length - 1])) parts.pop();
  return parts[parts.length - 1] || n;
}

function fmtAmerican(n) {
  if (n == null || !isFinite(+n)) return '—';
  n = Math.round(+n);
  return (n > 0 ? '+' : '') + n;
}

function ageWords(ts) {
  if (!ts) return 'unknown';
  const mins = Math.max(0, Math.round((Date.now() - new Date(ts).getTime()) / 60000));
  if (mins < 60) return mins + ' min ago';
  const h = Math.round(mins / 60);
  return h < 48 ? h + (h === 1 ? ' hour ago' : ' hours ago') : Math.round(h / 24) + ' days ago';
}

function renderHtml({ event, lines, unsubscribeToken }) {
  const unsubUrl = `${SITE}/unsubscribe.html?token=${encodeURIComponent(unsubscribeToken || '')}`;

  const moveCell = (pts, toward) => {
    if (pts == null) return '<span style="color:#777;">no history</span>';
    if (Math.abs(pts) < 0.5) return '<span style="color:#777;">unchanged</span>';
    const col = pts > 0 ? '#2fdccb' : '#ffb547';
    return `<span style="color:${col};font-weight:600;">${Math.abs(pts).toFixed(1)} pts</span>` +
           `<span style="color:#888;"> to ${escHtml(lastName(toward))}</span>`;
  };

  const rows = lines.map(l => `
    <tr>
      <td style="padding:10px 8px;border-bottom:1px solid #2a2a2a;color:#e8e8e8;">
        ${escHtml(l.aName)} <span style="color:#777;">vs</span> ${escHtml(l.bName)}
        ${l.flag ? ` <span style="color:#e63946;font-size:11px;font-weight:700;letter-spacing:1px;">[${l.flag}]</span>` : ''}
        <div style="color:#888;font-size:12px;margin-top:2px;">
          ${escHtml(l.favName)} ${l.favPct}% &middot; best ${escHtml(fmtAmerican(l.bestAmerican))}${l.bestBook ? ' at ' + escHtml(l.bestBook) : ''}
          &middot; ${l.books || '?'} book${l.books === 1 ? '' : 's'}${l.spread != null ? ', ' + l.spread.toFixed(1) + ' pts apart' : ''}
        </div>
      </td>
      <td style="padding:10px 8px;border-bottom:1px solid #2a2a2a;white-space:nowrap;">${moveCell(l.move, l.moveToward)}</td>
      <td style="padding:10px 8px;border-bottom:1px solid #2a2a2a;white-space:nowrap;">${moveCell(l.move24, l.move24Toward)}</td>
    </tr>
  `).join('');

  const freshest = lines.length ? ageWords(lines.map(l => l.lastUpdated).sort().pop()) : 'unknown';

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
        <div style="color:#e63946;font-size:11px;letter-spacing:1.5px;font-weight:700;text-transform:uppercase;">The Cannon Card Brief</div>
        <h1 style="margin:6px 0 4px;font-size:24px;color:#fff;line-height:1.25;">${escHtml(event.name)}</h1>
        <div style="color:#999;font-size:14px;">${escHtml(formatLongDate(event.event_date))}${event.location ? ' &middot; ' + escHtml(event.location) : ''}</div>
        <div style="color:#777;font-size:13px;margin-top:10px;line-height:1.55;">
          What the sportsbooks have done to this card. Sorted by how far each line has moved since we first captured it.
          Last price captured ${escHtml(freshest)} — these are captures, not live quotes.
        </div>
      </td></tr>

      <tr><td style="padding:20px;">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#111;border:1px solid #222;border-radius:8px;">
          <tr>
            <th align="left" style="padding:10px 8px;border-bottom:1px solid #2a2a2a;color:#999;font-size:11px;letter-spacing:1px;text-transform:uppercase;font-weight:600;">Fight &amp; market</th>
            <th align="left" style="padding:10px 8px;border-bottom:1px solid #2a2a2a;color:#999;font-size:11px;letter-spacing:1px;text-transform:uppercase;font-weight:600;">Since open</th>
            <th align="left" style="padding:10px 8px;border-bottom:1px solid #2a2a2a;color:#999;font-size:11px;letter-spacing:1px;text-transform:uppercase;font-weight:600;">24 h</th>
          </tr>
          ${rows || '<tr><td colspan="3" style="padding:14px;color:#999;">No sportsbook prices captured on this card yet.</td></tr>'}
        </table>
        <div style="color:#666;font-size:11.5px;line-height:1.5;margin-top:10px;">
          "Since open" compares to <em>our first capture</em> of the fight, which is when CFL started watching — not when the
          market opened. A line that moved is not a line that was wrong, and nothing in this email is a recommendation.
        </div>
      </td></tr>

      <tr><td style="padding:8px 20px 28px;">
        <a href="${SITE}/market.html?event=${event.id}" style="color:#e63946;text-decoration:none;font-weight:600;">Open the full board in Market Lab →</a>
      </td></tr>

      <tr><td style="padding:0 20px;">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:linear-gradient(135deg,#e63946,#c1121f);border-radius:8px;">
          <tr><td style="padding:22px 24px;">
            <div style="color:#fff;font-weight:700;font-size:16px;margin-bottom:6px;">Research the card in one screen</div>
            <div style="color:#fff;opacity:0.9;font-size:13px;margin-bottom:14px;">Card Lab has every fight with the vig-free consensus, the best price and who is posting it, and the matchup facts worth checking. Free, no account needed.</div>
            <a href="${SITE}/index.html#next" style="background:#fff;color:#c1121f;padding:10px 22px;border-radius:6px;font-weight:700;text-decoration:none;display:inline-block;font-size:14px;">Open Card Lab →</a>
          </td></tr>
        </table>
      </td></tr>

      <tr><td style="padding:28px 20px 8px;color:#666;font-size:12px;line-height:1.5;text-align:center;">
        Cannon Fight Lab is an analytics publication, not a sportsbook. We do not sell picks. 21+ only. 1-800-GAMBLER.
      </td></tr>
      <tr><td style="padding:0 20px 20px;color:#555;font-size:11px;text-align:center;">
        You're subscribed to the Cannon Card Brief.
        <a href="${unsubUrl}" style="color:#888;">Unsubscribe</a>
      </td></tr>

    </table>
  </td></tr>
</table>
</body></html>`;
}

function renderText({ event, lines, unsubscribeToken }) {
  const unsubUrl = `${SITE}/unsubscribe.html?token=${unsubscribeToken || ''}`;
  const moveTxt = (pts, toward) => {
    if (pts == null) return 'no history';
    if (Math.abs(pts) < 0.5) return 'unchanged';
    return `${Math.abs(pts).toFixed(1)} pts to ${lastName(toward)}`;
  };
  const out = [];
  out.push(`THE CANNON CARD BRIEF — ${event.name}`);
  out.push(formatLongDate(event.event_date) + (event.location ? ' · ' + event.location : ''));
  out.push('');
  out.push('What the sportsbooks have done to this card, biggest move first.');
  out.push('These are captured prices, not live quotes. No picks.');
  out.push('');
  for (const l of lines) {
    const flag = l.flag ? ` [${l.flag}]` : '';
    out.push(`  ${l.aName} vs ${l.bName}${flag}`);
    out.push(`    market: ${l.favName} ${l.favPct}% · best ${fmtAmerican(l.bestAmerican)}` +
             `${l.bestBook ? ' at ' + l.bestBook : ''} · ${l.books || '?'} books` +
             `${l.spread != null ? ', ' + l.spread.toFixed(1) + ' pts apart' : ''}`);
    out.push(`    since our first capture: ${moveTxt(l.move, l.moveToward)} · last 24h: ${moveTxt(l.move24, l.move24Toward)}`);
    out.push('');
  }
  if (!lines.length) out.push('  No sportsbook prices captured on this card yet.\n');
  out.push(`Full board: ${SITE}/market.html?event=${event.id}`);
  out.push(`The card: ${SITE}/index.html#next`);
  out.push('');
  out.push('"Since our first capture" is measured from when CFL started watching the fight,');
  out.push('not from when the market opened. A line that moved is not a line that was wrong.');
  out.push('');
  out.push('---');
  out.push(`Unsubscribe: ${unsubUrl}`);
  out.push('Cannon Fight Lab is an analytics publication, not a sportsbook. We do not sell picks. 21+ only.');
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

    const lines = await buildMarketLines(event);
    console.log(`[digest] ${lines.length} fights with market data.`);
    if (!lines.length) {
      console.log('[digest] no market data captured for this card yet — skipping send.');
      return;
    }

    const subscribers = await fetchActiveSubscribers();
    console.log(`[digest] ${subscribers.length} active subscribers.`);
    if (!subscribers.length) {
      console.log('[digest] no subscribers — nothing to send.');
      return;
    }

    // The subject line is the most-read string this product ships, and it was
    // the last one still saying "picks". The Brief reports what the market did;
    // it has never reported a pick since the repositioning, and now it does not
    // say it does either.
    const subject = `${event.name} — what the market did this week`;
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
