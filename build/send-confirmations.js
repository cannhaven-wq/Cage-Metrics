// CARD BRIEF CONFIRMATION EMAILS (T-090) — plumbing only: read, record, send.
// Every rule and every word is in build/card-brief-confirm.js.
//
// NOT SCHEDULED, AND LOCKED. No workflow runs this file, and while
// card-brief-confirm.js::CONFIRM_SEND_BLOCKERS holds a line it is dry-run
// whatever secrets are set: it lists who would be emailed (with the link
// redacted) and writes nothing to the database. Turning it on is an owner
// decision (D-027): apply the migration, approve the wording, delete the
// blockers in a reviewed PR, then decide how it is run.
//
// ORDER WHEN LIVE: record, then send. The token hash, expiry and send count are
// written first, with a compare-and-set on the send count so two passes cannot
// both claim one address; only then is the email sent. If the process dies in
// between, that address misses one confirmation email — it is never mailed
// twice. Same reasoning as user_alert_deliveries (CLAUDE.md).
//
// Environment: SUPABASE_SERVICE_ROLE_KEY (reads the private list),
// RESEND_API_KEY, RESEND_FROM, CONFIRM_DRY_RUN=1 to force a dry run.
'use strict';
const C = require('./card-brief-confirm');

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
const RESEND_KEY = process.env.RESEND_API_KEY;
const FROM = process.env.RESEND_FROM || 'Cannon Fight Lab <hello@cannonfightlab.com>';
const DRY_RUN = C.confirmDryRun({ resendKey: RESEND_KEY, envDryRun: process.env.CONFIRM_DRY_RUN });

async function fetchCandidates(sb) {
  const all = [];
  const pageSize = 1000;
  for (let from = 0; ; from += pageSize) {
    const { data, error } = await sb
      .from('email_subscribers')
      .select('id, email, unsubscribe_token, unsubscribed_at, confirmed_at, confirm_token_hash, confirm_token_expires_at, confirm_send_count')
      .is('unsubscribed_at', null)
      .is('confirmed_at', null)
      .order('id', { ascending: true })
      .range(from, from + pageSize - 1);
    if (error) throw error;
    if (!data || !data.length) break;
    all.push(...data);
    if (data.length < pageSize) break;
  }
  return all;
}

async function sendEmail({ to, subject, html, text }) {
  const res = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: { Authorization: `Bearer ${RESEND_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ from: FROM, to: [to], subject, html, text }),
  });
  if (!res.ok) return { ok: false, status: res.status, error: await res.text() };
  return { ok: true };
}

async function main() {
  if (C.CONFIRM_SEND_BLOCKERS.length) {
    console.log('[confirm] DRY RUN — sending is blocked by: ' + C.CONFIRM_SEND_BLOCKERS.join('; '));
  }
  if (!SERVICE_KEY) {
    console.log('[confirm] no SUPABASE_SERVICE_ROLE_KEY — the list is private, so there is nothing to read. Exiting.');
    return;
  }
  const { createClient } = require('@supabase/supabase-js');
  const sb = createClient(SUPABASE_URL, SERVICE_KEY, { auth: { persistSession: false, autoRefreshToken: false } });

  let rows;
  try {
    rows = await fetchCandidates(sb);
  } catch (err) {
    if (C.isMissingColumnError(err)) {
      console.log('[confirm] the double opt-in columns do not exist — card_brief_double_optin_migration.sql is not applied. Nothing to do.');
      return;
    }
    throw err;
  }
  const now = new Date();
  const due = rows.filter(r => C.needsConfirmation(r, now));
  console.log(`[confirm] ${rows.length} unconfirmed, ${due.length} due a confirmation email.`);

  let sent = 0, failed = 0, skipped = 0;
  for (const row of due) {
    const plan = C.planConfirmation(row, now);
    const html = C.renderConfirmHtml({ url: plan.url, unsubscribeToken: row.unsubscribe_token });
    const text = C.renderConfirmText({ url: plan.url, unsubscribeToken: row.unsubscribe_token });
    if (DRY_RUN) {
      console.log(`[dry-run] would email ${row.email} — "${C.CONFIRM_SUBJECT}" link ${C.redactedConfirmUrl(plan.token)} (${html.length} chars html, ${text.length} chars text). Nothing recorded.`);
      continue;
    }
    // Record first, compare-and-set on the send count.
    const { data: claimed, error } = await sb
      .from('email_subscribers')
      .update(plan.update)
      .eq('id', row.id)
      .is('confirmed_at', null)
      .is('unsubscribed_at', null)
      .eq('confirm_send_count', plan.expectSendCount)
      .select('id');
    if (error) { failed++; console.warn(`[confirm] could not record a link for ${row.email}:`, error.message); continue; }
    if (!claimed || !claimed.length) { skipped++; continue; }   // another pass got there first
    const r = await sendEmail({ to: row.email, subject: C.CONFIRM_SUBJECT, html, text });
    if (r.ok) sent++;
    else { failed++; console.warn(`[confirm] send to ${row.email} failed:`, r.status, r.error); }
    await new Promise(res => setTimeout(res, 600));   // Resend free tier ≈ 2 req/s
  }
  console.log(`[confirm] done. sent=${sent} failed=${failed} skipped=${skipped} dry_run=${DRY_RUN}`);
}

if (require.main === module) {
  main().then(() => process.exit(0)).catch(err => {
    console.error('[confirm] failed:', err);
    process.exit(1);
  });
}

module.exports = { DRY_RUN };
