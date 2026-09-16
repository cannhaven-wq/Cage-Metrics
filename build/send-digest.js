// Fight Week Brief — the email sender. Runs via the digest.yml workflow:
// Wednesday (pre-card) and Monday (post-card). Two templates:
//
//   pre-card  — the next card with a locked CFL forecast: every fight's CFL
//               number beside the vig-free market number, the biggest
//               disagreements, and whether the odds are fresh.
//   post-card — the last graded card: the biggest hit and the biggest miss
//               at the same size, then every fight with its result. The
//               numbers are exactly what was locked before the bell.
//
// Every CFL number comes from v_fight_locked_forecast (the pre-fight record);
// the market number from v_fight_market_vigfree. Nothing is computed here —
// the same views the Event Hub reads (see fight_week_views.sql and
// build/fight-week-data.js).
//
// Rules: no sportsbook names or links in the email; every disagreement
// carries "A disagreement is not a proven betting edge."; if the odds are
// stale the email says so.
//
// Environment variables (all set as repo secrets — see TRAFFIC_FUNNEL.md):
//   RESEND_API_KEY                — Resend API key (required for live send)
//   RESEND_FROM                   — e.g. "Cannon Fight Lab <hello@cannonfightlab.com>"
//   SUPABASE_SERVICE_ROLE_KEY     — service-role key, bypasses RLS so we can
//                                   read email_subscribers
//   DIGEST_DRY_RUN                — "1" or "true" → render + log, never send
//   DIGEST_MODE                   — "pre" (default) | "post" | "auto"
//   DIGEST_PREVIEW_OUT            — optional path: write the rendered HTML
//                                   there (for eyeballing a dry run)
//
// Without RESEND_API_KEY the script falls back to dry-run automatically.

const fs = require('fs');
const { createClient } = require('@supabase/supabase-js');
const core = require('../fight-week-core');
const fwData = require('./fight-week-data');

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SUPABASE_ANON_KEY = 'sb_publishable_boJGOA1CFN-SF14HHFGUAw_YEEm0DU8';
const SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
const RESEND_KEY  = process.env.RESEND_API_KEY;
const FROM        = process.env.RESEND_FROM || 'Cannon Fight Lab <hello@cannonfightlab.com>';
const DRY_RUN     = !RESEND_KEY || /^(1|true|yes)$/i.test(process.env.DIGEST_DRY_RUN || '');
const MODE        = (process.env.DIGEST_MODE || 'pre').toLowerCase();
const SITE        = core.SITE;

// Service key bypasses RLS so we can read email_subscribers; fall back to
// the anon key for dry-run mode where we're not actually sending.
const sb = createClient(SUPABASE_URL, SERVICE_KEY || SUPABASE_ANON_KEY);

const todayUTC = () => new Date().toISOString().slice(0, 10);
const esc = core.escapeHtml;

// ---------------------------------------------------------------------------
// Which card?
// ---------------------------------------------------------------------------
async function pickEvent(mode) {
  const withRecord = await fwData.eventsWithRecord(sb);
  const t = todayUTC();
  if (mode === 'pre') {
    const up = withRecord.filter(e => e.event_date >= t).sort((a, b) => (a.event_date < b.event_date ? -1 : 1));
    return up[0] || null;
  }
  if (mode === 'post') {
    const past = withRecord.filter(e => e.event_date < t);   // newest first already
    return past[0] || null;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Shared email chrome (inline styles — email clients ignore stylesheets)
// ---------------------------------------------------------------------------
const C = { bg: '#0a0a0a', panel: '#111', line: '#2a2a2a', text: '#e8e8e8', dim: '#999', red: '#e63946', green: '#3fd07a', amber: '#ffb547' };
const td = (extra) => `style="padding:10px 8px;border-bottom:1px solid ${C.line};color:${C.text};font-size:14px;${extra || ''}"`;
const th = () => `align="left" style="padding:10px 8px;border-bottom:1px solid ${C.line};color:${C.dim};font-size:11px;letter-spacing:1px;text-transform:uppercase;font-weight:600;"`;

function shell({ eyebrow, title, sub, body, unsubscribeToken }) {
  const unsubUrl = `${SITE}/unsubscribe.html?token=${encodeURIComponent(unsubscribeToken || '')}`;
  return `<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:${C.bg};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:${C.bg};padding:24px 0;">
  <tr><td align="center">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="600" style="max-width:600px;width:100%;">
      <tr><td style="padding:0 20px 18px;">
        <div style="font-family:'Barlow Condensed',Impact,sans-serif;font-size:24px;font-weight:800;color:#fff;letter-spacing:1px;">CANNON FIGHT <span style="color:${C.red};">LAB</span></div>
      </td></tr>
      <tr><td style="padding:0 20px 6px;">
        <div style="color:${C.red};font-size:11px;letter-spacing:1.5px;font-weight:700;text-transform:uppercase;">${esc(eyebrow)}</div>
        <h1 style="margin:6px 0 4px;font-size:24px;color:#fff;line-height:1.25;">${esc(title)}</h1>
        <div style="color:${C.dim};font-size:14px;">${sub}</div>
      </td></tr>
      ${body}
      <tr><td style="padding:22px 20px 8px;color:${C.dim};font-size:12px;line-height:1.5;">
        ${esc(core.STANDARD_LINE)} Market numbers are the books' prices with the cut removed. ${esc(core.NOT_EDGE)}
      </td></tr>
      <tr><td style="padding:6px 20px 8px;color:#666;font-size:12px;line-height:1.5;text-align:center;">
        Cannon Fight Lab is an analytics publication, not a sportsbook. 21+ only. 1-800-GAMBLER.
      </td></tr>
      <tr><td style="padding:0 20px 20px;color:#555;font-size:11px;text-align:center;">
        You're subscribed to the Fight Week Brief from Cannon Fight Lab.
        <a href="${unsubUrl}" style="color:#888;">Unsubscribe</a>
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>`;
}

const section = (html) => `<tr><td style="padding:14px 20px 4px;">${html}</td></tr>`;
const h2 = (t) => `<div style="color:#fff;font-size:17px;font-weight:700;margin:6px 0 8px;">${esc(t)}</div>`;
const note = (t) => `<div style="color:${C.dim};font-size:13px;line-height:1.5;">${t}</div>`;

function staleLine(lastUpdated, now) {
  if (!lastUpdated) return `<span style="color:${C.amber};">No sportsbook prices are on file yet.</span>`;
  const stale = core.isStale(lastUpdated, 24, now);
  const when = esc(core.fmtWhen(lastUpdated, now));
  return stale
    ? `<span style="color:${C.amber};">Odds in this email are stale — last updated ${when}.</span>`
    : `Odds last updated ${when}.`;
}

// ---------------------------------------------------------------------------
// Pre-card
// ---------------------------------------------------------------------------
function renderPreCard({ event, rows, summary: s, now, unsubscribeToken }) {
  const hubUrl = SITE + core.hubPath(event);
  const table = rows.map(r => {
    const d = r.disagree;
    const favA = r.cfl_p_a != null && r.cfl_p_a >= 0.5;
    return `<tr>
      <td ${td()}>${esc(r.fighter_a_name)} <span style="color:#777;">vs</span> ${esc(r.fighter_b_name)}${r.is_main_event ? ` <span style="color:${C.red};font-size:11px;font-weight:700;letter-spacing:1px;">[MAIN]</span>` : ''}<div style="color:${C.dim};font-size:12px;">${esc(r.weight_class || '')}${r.cfl_p_a != null ? ` · CFL favours ${esc(favA ? r.fighter_a_name : r.fighter_b_name)}` : ''}</div></td>
      <td ${td('white-space:nowrap;text-align:right;')}>${core.pct(r.cfl_p_a)} / ${core.pct(r.cfl_p_b)}</td>
      <td ${td('white-space:nowrap;text-align:right;')}>${core.pct(r.market_p_a)} / ${core.pct(r.market_p_b)}</td>
      <td ${td('white-space:nowrap;text-align:right;')}>${core.fmtPoints(d.points)}<div style="color:${C.dim};font-size:11px;">${esc(d.label)}</div></td>
    </tr>`;
  }).join('');

  const big = core.biggest(rows, 3).filter(r => r.disagree.big);
  const bigHtml = big.length ? big.map(r => {
    const favA = r.cfl_p_a >= 0.5;
    return `<div style="background:${C.panel};border:1px solid ${C.line};border-radius:8px;padding:12px 14px;margin-bottom:8px;">
      <div style="color:#fff;font-weight:700;font-size:15px;">${esc(r.fighter_a_name)} vs ${esc(r.fighter_b_name)} <span style="color:${C.dim};font-weight:400;font-size:12px;">· ${esc(r.weight_class || '')}</span></div>
      <div style="color:${C.text};font-size:13px;margin-top:4px;line-height:1.5;">${esc(core.explain(r))}</div>
      <div style="color:${C.amber};font-size:12px;margin-top:6px;">${esc(core.NOT_EDGE)}</div>
    </div>`;
  }).join('') : note(`No fight on this card has CFL and the market more than ${core.BIG_POINTS} points apart yet.`);

  const body = section(`
    <div style="background:${C.panel};border:1px solid ${C.line};border-radius:8px;padding:12px 14px;color:${C.text};font-size:13px;line-height:1.6;">
      <b>${s.analyzed}</b> of ${s.fights} fights have a locked CFL forecast · <b>${s.big}</b> big disagreement${s.big === 1 ? '' : 's'} (${core.BIG_POINTS}+ points) · ${staleLine(s.lastUpdated, now)}<br>
      ${esc(core.LOCKED_LINE)} Forecasts locked ${esc(core.fmtStamp(s.lockedAt))} and never revised.
    </div>`)
  + section(h2('Biggest disagreements') + bigHtml)
  + section(h2('Every fight: CFL vs market') + `
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:${C.panel};border:1px solid ${C.line};border-radius:8px;">
      <tr><th ${th()}>Fight</th><th ${th()} style="text-align:right">CFL %</th><th ${th()} style="text-align:right">Market %</th><th ${th()} style="text-align:right">Diff</th></tr>
      ${table || `<tr><td colspan="4" ${td()}>No fights listed yet.</td></tr>`}
    </table>
    ${note('Percentages are for the left / right fighter. Difference is CFL minus market on the fighter CFL favours.')}`)
  + section(`<a href="${hubUrl}" style="color:${C.red};text-decoration:none;font-weight:600;">Open the ${esc(event.name)} Event Hub — the math behind every fight →</a>`);

  return shell({
    eyebrow: 'Fight Week Brief · before the card',
    title: `${event.name} — model vs market`,
    sub: `${esc(core.fmtLongDate(event.event_date))}${event.location ? ' &middot; ' + esc(event.location) : ''}`,
    body,
    unsubscribeToken,
  });
}

function renderPreCardText({ event, rows, summary: s, now, unsubscribeToken }) {
  const out = [];
  out.push(`CANNON FIGHT LAB — Fight Week Brief (before the card)`);
  out.push(`${event.name} — model vs market`);
  out.push(core.fmtLongDate(event.event_date) + (event.location ? ' · ' + event.location : ''));
  out.push('');
  out.push(`${s.analyzed} of ${s.fights} fights have a locked CFL forecast · ${s.big} big disagreement(s) · ${s.lastUpdated ? (core.isStale(s.lastUpdated, 24, now) ? 'ODDS ARE STALE — last updated ' : 'odds last updated ') + core.fmtWhen(s.lastUpdated, now) : 'no sportsbook prices on file yet'}`);
  out.push(`${core.LOCKED_LINE} Forecasts locked ${core.fmtStamp(s.lockedAt)}.`);
  out.push('');
  out.push('Biggest disagreements:');
  const big = core.biggest(rows, 3).filter(r => r.disagree.big);
  if (!big.length) out.push('  none over ' + core.BIG_POINTS + ' points yet');
  big.forEach(r => { out.push(`  ${r.fighter_a_name} vs ${r.fighter_b_name}: ${core.explain(r)}`); out.push(`    ${core.NOT_EDGE}`); });
  out.push('');
  out.push('Every fight (CFL % / market % / difference on CFL\'s favoured fighter):');
  rows.forEach(r => out.push(`  ${r.fighter_a_name} vs ${r.fighter_b_name}${r.is_main_event ? ' [MAIN]' : ''}: CFL ${core.pct(r.cfl_p_a)}/${core.pct(r.cfl_p_b)} · market ${core.pct(r.market_p_a)}/${core.pct(r.market_p_b)} · ${core.fmtPoints(r.disagree.points)} (${r.disagree.label})`));
  out.push('');
  out.push(`Event Hub: ${SITE}${core.hubPath(event)}`);
  out.push('');
  out.push(`${core.STANDARD_LINE} ${core.NOT_EDGE}`);
  out.push('---');
  out.push(`Unsubscribe: ${SITE}/unsubscribe.html?token=${unsubscribeToken || ''}`);
  out.push('Cannon Fight Lab is an analytics publication, not a sportsbook. 21+ only.');
  return out.join('\n');
}

// ---------------------------------------------------------------------------
// Post-card — the biggest miss gets exactly the same box as the biggest hit.
// ---------------------------------------------------------------------------
function resultLine(r) {
  if (!r.winner_id) return 'no result yet';
  const w = r.winner_id === r.fighter_a_id ? r.fighter_a_name : r.fighter_b_name;
  return `${w} won${r.method ? ' — ' + r.method + (r.end_round ? ' R' + r.end_round : '') : ''}`;
}
function outcomeBox(label, r, color) {
  if (!r) return `<td width="50%" valign="top" style="padding:0 4px;"><div style="background:${C.panel};border:1px solid ${C.line};border-radius:8px;padding:12px 14px;color:${C.dim};font-size:13px;">${esc(label)}: none on this card.</div></td>`;
  const favA = r.cfl_p_a >= 0.5;
  const fav = favA ? r.fighter_a_name : r.fighter_b_name;
  const cfl = favA ? r.cfl_p_a : r.cfl_p_b;
  const mkt = favA ? r.market_p_a : r.market_p_b;
  return `<td width="50%" valign="top" style="padding:0 4px;">
    <div style="background:${C.panel};border:1px solid ${color};border-radius:8px;padding:12px 14px;">
      <div style="color:${color};font-size:11px;letter-spacing:1px;font-weight:700;text-transform:uppercase;">${esc(label)}</div>
      <div style="color:#fff;font-weight:700;font-size:15px;margin-top:4px;">${esc(r.fighter_a_name)} vs ${esc(r.fighter_b_name)}</div>
      <div style="color:${C.text};font-size:13px;margin-top:4px;line-height:1.5;">CFL had ${esc(fav)} at <b>${core.pct(cfl)}</b>${mkt != null ? ` (market ${core.pct(mkt)})` : ''}. ${esc(resultLine(r))}.</div>
    </div>
  </td>`;
}

function renderPostCard({ event, rows, summary: s, unsubscribeToken }) {
  const hubUrl = SITE + core.hubPath(event);
  const hm = core.hitAndMiss(rows);
  const table = rows.map(r => {
    const mark = r.forecast_hit == null ? '' : (r.forecast_hit ? `<span style="color:${C.green};font-weight:700;">✓ right</span>` : `<span style="color:${C.red};font-weight:700;">✗ wrong</span>`);
    return `<tr>
      <td ${td()}>${esc(r.fighter_a_name)} <span style="color:#777;">vs</span> ${esc(r.fighter_b_name)}<div style="color:${C.dim};font-size:12px;">${esc(resultLine(r))}</div></td>
      <td ${td('white-space:nowrap;text-align:right;')}>${core.pct(r.cfl_p_a)} / ${core.pct(r.cfl_p_b)}</td>
      <td ${td('white-space:nowrap;text-align:right;')}>${core.pct(r.market_p_a)} / ${core.pct(r.market_p_b)}</td>
      <td ${td('white-space:nowrap;')}>${mark}</td>
    </tr>`;
  }).join('');

  const body = section(`
    <div style="background:${C.panel};border:1px solid ${C.line};border-radius:8px;padding:12px 14px;color:${C.text};font-size:13px;line-height:1.6;">
      CFL's locked forecasts went <b>${s.hits}–${s.misses}</b> on ${s.settled} settled fight${s.settled === 1 ? '' : 's'}${s.allSettled ? '' : ' (some results still pending)'}. Every number below is exactly as it was locked ${esc(core.fmtStamp(s.lockedAt))} — nothing revised after the bell.
    </div>`)
  + section(h2('Biggest hit · Biggest miss') + `
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"><tr>
      ${outcomeBox('Biggest hit', hm.hit, C.green)}
      ${outcomeBox('Biggest miss', hm.miss, C.red)}
    </tr></table>
    ${note('"Biggest" is the highest-confidence forecast on each side. A model that only shows winners is selling something.')}`)
  + section(h2('Every fight, graded') + `
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:${C.panel};border:1px solid ${C.line};border-radius:8px;">
      <tr><th ${th()}>Fight</th><th ${th()} style="text-align:right">CFL %</th><th ${th()} style="text-align:right">Market % (last on file)</th><th ${th()}>Forecast</th></tr>
      ${table}
    </table>
    ${note('Market % is the last vig-free sportsbook number on file for the fight — blank when no sportsbook quote was captured.')}`)
  + section(`<a href="${hubUrl}" style="color:${C.red};text-decoration:none;font-weight:600;">The permanent graded record for ${esc(event.name)} →</a>`);

  return shell({
    eyebrow: 'Fight Week Brief · after the card',
    title: `${event.name} — graded`,
    sub: `${esc(core.fmtLongDate(event.event_date))}${event.location ? ' &middot; ' + esc(event.location) : ''}`,
    body,
    unsubscribeToken,
  });
}

function renderPostCardText({ event, rows, summary: s, unsubscribeToken }) {
  const hm = core.hitAndMiss(rows);
  const line = (label, r) => {
    if (!r) return `${label}: none on this card.`;
    const favA = r.cfl_p_a >= 0.5;
    return `${label}: ${r.fighter_a_name} vs ${r.fighter_b_name} — CFL had ${favA ? r.fighter_a_name : r.fighter_b_name} at ${core.pct(favA ? r.cfl_p_a : r.cfl_p_b)}. ${resultLine(r)}.`;
  };
  const out = [];
  out.push(`CANNON FIGHT LAB — Fight Week Brief (after the card)`);
  out.push(`${event.name} — graded`);
  out.push('');
  out.push(`CFL's locked forecasts went ${s.hits}-${s.misses} on ${s.settled} settled fights. Locked ${core.fmtStamp(s.lockedAt)}, never revised.`);
  out.push('');
  out.push(line('BIGGEST HIT', hm.hit));
  out.push(line('BIGGEST MISS', hm.miss));
  out.push('');
  out.push('Every fight:');
  rows.forEach(r => out.push(`  ${r.fighter_a_name} vs ${r.fighter_b_name}: CFL ${core.pct(r.cfl_p_a)}/${core.pct(r.cfl_p_b)} · market ${core.pct(r.market_p_a)}/${core.pct(r.market_p_b)} · ${resultLine(r)} · ${r.forecast_hit == null ? 'pending' : (r.forecast_hit ? 'RIGHT' : 'WRONG')}`));
  out.push('');
  out.push(`Permanent graded record: ${SITE}${core.hubPath(event)}`);
  out.push('');
  out.push(`${core.STANDARD_LINE} ${core.NOT_EDGE}`);
  out.push('---');
  out.push(`Unsubscribe: ${SITE}/unsubscribe.html?token=${unsubscribeToken || ''}`);
  out.push('Cannon Fight Lab is an analytics publication, not a sportsbook. 21+ only.');
  return out.join('\n');
}

// ---------------------------------------------------------------------------
// Delivery
// ---------------------------------------------------------------------------
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
  const { error } = await sb
    .from('email_subscribers')
    .update({ last_sent_at: new Date().toISOString() })
    .in('email', emails);
  if (error) console.warn('[digest] last_sent_at update failed:', error.message);
}

// The email never carries sportsbook branding. Belt and braces: refuse to send
// if a known book name slipped into the rendered copy.
const BOOK_WORDS = /fanduel|draftkings|betmgm|caesars|betrivers|bovada|betonline|betus|fanatics|hard rock|bally|betly|unibet|betway|polymarket|kalshi/i;

(async () => {
  try {
    const mode = MODE === 'auto' ? 'pre' : MODE;
    const event = await pickEvent(mode);
    if (!event) { console.log(`[digest] no ${mode}-card event with a locked forecast — nothing to send.`); return; }
    console.log(`[digest] mode=${mode} event: ${event.name} (${event.event_date})`);

    const card = await fwData.loadCard(sb, event);
    const rows = card.rows;
    const summary = core.summarize(rows);
    if (!summary.analyzed) { console.log('[digest] no locked forecasts on this card — skipping send.'); return; }
    if (mode === 'post' && !summary.anySettled) { console.log('[digest] card not graded yet — skipping post-card send.'); return; }
    const now = new Date();

    const render = mode === 'post'
      ? { html: t => renderPostCard({ event, rows, summary, unsubscribeToken: t }), text: t => renderPostCardText({ event, rows, summary, unsubscribeToken: t }) }
      : { html: t => renderPreCard({ event, rows, summary, now, unsubscribeToken: t }), text: t => renderPreCardText({ event, rows, summary, now, unsubscribeToken: t }) };
    const subject = mode === 'post'
      ? `Fight Week Brief: ${event.name} graded — biggest hit, biggest miss`
      : `Fight Week Brief: ${event.name} — model vs market`;

    const sample = render.html('PREVIEW');
    if (BOOK_WORDS.test(sample.replace(/<[^>]+>/g, ' '))) throw new Error('rendered email mentions a sportsbook — refusing to send');
    if (process.env.DIGEST_PREVIEW_OUT) {
      fs.writeFileSync(process.env.DIGEST_PREVIEW_OUT, sample);
      fs.writeFileSync(process.env.DIGEST_PREVIEW_OUT.replace(/\.html?$/i, '') + '.txt', render.text('PREVIEW'));
      console.log(`[digest] preview written to ${process.env.DIGEST_PREVIEW_OUT}`);
    }

    const subscribers = await fetchActiveSubscribers();
    console.log(`[digest] ${subscribers.length} active subscribers.`);
    if (!subscribers.length) { console.log('[digest] no subscribers — nothing to send.'); return; }

    let sent = 0, failed = 0;
    const sentEmails = [];
    for (const sub of subscribers) {
      const r = await sendOne({ to: sub.email, subject, html: render.html(sub.unsubscribe_token), text: render.text(sub.unsubscribe_token) });
      if (r.ok) { sent++; sentEmails.push(sub.email); }
      else { failed++; console.warn(`[digest] send to ${sub.email} failed:`, r.status, r.error); }
      if (!DRY_RUN) await new Promise(r => setTimeout(r, 600));   // Resend free tier ≈ 2 req/sec
    }
    await markSent(sentEmails);
    console.log(`[digest] done. mode=${mode} sent=${sent} failed=${failed} dry_run=${DRY_RUN}`);
  } catch (err) {
    console.error('[digest] failed:', err);
    process.exit(1);
  }
})();
