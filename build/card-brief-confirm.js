// CARD BRIEF DOUBLE OPT-IN (T-090, owner decision D-027) — the pure parts.
//
// Plain version: anyone can type anyone's address into the Card Brief form. So
// an address gets ONE email with a confirm link, and the Brief only ever goes
// to addresses that clicked it.
//
// This file holds every rule and every word; it has no network, no database
// and no clock of its own (every function that needs the time takes `now`).
// build/send-confirmations.js is the plumbing that reads, records and sends;
// build/send-digest.js uses sendableBriefRecipients() so the Brief can only go
// to confirmed addresses. tests/card-brief-confirm.test.js pins all of it.
//
// THE TOKEN. 32 random bytes as 64 lower-case hex characters. The database
// stores only its sha256 (card_brief_double_optin_migration.sql); the raw token
// exists only in the email. public.confirm_email_subscription(p_token) hashes
// it inside Postgres and compares. Never write the raw token to the database
// or to a log — logs from GitHub Actions are readable by anyone with repo
// access, and a logged link is a working link.
'use strict';
const crypto = require('crypto');

const SITE = 'https://cannonfightlab.com';

// Confirmation email is transactional, but it is still email to an address
// that may never have asked, so it is locked in code until the owner approves
// it — the same arrangement as send-digest.js::MARKETING_SEND_BLOCKERS and
// entitlements.js::CHECKOUT_BLOCKERS. Clearing one means deleting its line in
// a reviewed PR.
const CONFIRM_SEND_BLOCKERS = [
  'T-090: the owner has not approved sending confirmation email yet (wording sits with T-054)',
  'T-090: card_brief_double_optin_migration.sql is not applied to production (L3)',
];

const TOKEN_BYTES = 32;
const TOKEN_TTL_HOURS = 7 * 24;      // a link works for a week
// One confirmation email per address, ever. An address that did not ask for
// the Brief hears from us once, not every week. Somebody who lost the email
// can be re-sent one by hand (reset confirm_send_count) — there is no
// automatic resend, on purpose.
const MAX_CONFIRM_SENDS = 1;

const TOKEN_RE = /^[0-9a-f]{64}$/;

function newToken(randomBytes = crypto.randomBytes) {
  const buf = randomBytes(TOKEN_BYTES);
  if (!buf || buf.length !== TOKEN_BYTES) throw new Error('token source returned the wrong number of bytes');
  return Buffer.from(buf).toString('hex');
}

function isWellFormedToken(tok) {
  return typeof tok === 'string' && TOKEN_RE.test(tok);
}

// sha256 of the UTF-8 token, lower-case hex — the same bytes Postgres hashes in
// confirm_email_subscription (encode(sha256(convert_to(p_token,'UTF8')),'hex')).
function hashToken(tok) {
  if (!isWellFormedToken(tok)) throw new Error('not a confirmation token');
  return crypto.createHash('sha256').update(tok, 'utf8').digest('hex');
}

function confirmUrl(tok) {
  if (!isWellFormedToken(tok)) throw new Error('not a confirmation token');
  return `${SITE}/confirm.html?t=${tok}`;
}

// For logs: enough to tell two links apart, never enough to use one.
function redactToken(tok) {
  return isWellFormedToken(tok) ? tok.slice(0, 4) + '…(redacted)' : '(none)';
}
function redactedConfirmUrl(tok) {
  return `${SITE}/confirm.html?t=${redactToken(tok)}`;
}

const ts = v => (v == null ? null : new Date(v).getTime());

// Should this subscriber row be sent a confirmation email now?
function needsConfirmation(row, now) {
  if (!row || !row.email) return false;
  if (row.unsubscribed_at != null) return false;
  if (row.confirmed_at != null) return false;
  const sent = Number(row.confirm_send_count || 0);
  if (sent >= MAX_CONFIRM_SENDS) return false;
  // A link issued and still live is not re-issued, whatever the count says.
  const exp = ts(row.confirm_token_expires_at);
  if (row.confirm_token_hash && exp != null && exp > ts(now)) return false;
  return true;
}

// What the sender records BEFORE it sends. The raw token goes in the email,
// never in `update`. `expectSendCount` is a compare-and-set: the update only
// lands if no other pass got there first.
function planConfirmation(row, now, randomBytes) {
  const token = newToken(randomBytes);
  const nowMs = ts(now);
  return {
    token,
    url: confirmUrl(token),
    update: {
      confirm_token_hash: hashToken(token),
      confirm_token_expires_at: new Date(nowMs + TOKEN_TTL_HOURS * 3600e3).toISOString(),
      confirm_sent_at: new Date(nowMs).toISOString(),
      confirm_send_count: Number(row.confirm_send_count || 0) + 1,
    },
    expectSendCount: Number(row.confirm_send_count || 0),
  };
}

// THE RULE THE BRIEF SENDER RELIES ON. Only a confirmed, still-subscribed
// address is ever a recipient. Applied after the database filter as well, so a
// query edit cannot widen the list on its own.
function isBriefRecipient(row) {
  return !!row && !!row.email && row.confirmed_at != null && row.confirmed_at !== ''
    && row.unsubscribed_at == null;
}
function sendableBriefRecipients(rows) {
  return (rows || []).filter(isBriefRecipient);
}

// Postgres "undefined column": the migration is not applied, so nobody can be
// confirmed yet. Senders treat that as "nobody to send to", never as "send to
// everyone".
function isMissingColumnError(err) {
  return !!err && (err.code === '42703' || /column .*does not exist/i.test(err.message || ''));
}

function confirmDryRun({ resendKey, envDryRun, blockers = CONFIRM_SEND_BLOCKERS } = {}) {
  return !resendKey || /^(1|true|yes)$/i.test(envDryRun || '') || blockers.length > 0;
}

function escHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

const CONFIRM_SUBJECT = 'Confirm your Cannon Card Brief signup';

function unsubscribeUrl(unsubscribeToken) {
  return `${SITE}/unsubscribe.html?token=${encodeURIComponent(unsubscribeToken || '')}`;
}

// The words. Plain, short, no hype (COPY_STYLE): what this is, one button,
// what happens if you ignore it.
function renderConfirmText({ url, unsubscribeToken }) {
  return [
    'Someone asked for the Cannon Card Brief to be sent to this address.',
    '',
    'If that was you, confirm it here:',
    url,
    '',
    `The link works for ${TOKEN_TTL_HOURS / 24} days.`,
    '',
    "If it wasn't you, ignore this email. We won't send you anything else.",
    '',
    'The Brief is one email before each UFC card: what the betting market did that week. No picks.',
    '',
    '---',
    `Remove this address now: ${unsubscribeUrl(unsubscribeToken)}`,
    'Cannon Fight Lab is an analytics publication, not a sportsbook. 21+ only. 1-800-GAMBLER.',
  ].join('\n');
}

function renderConfirmHtml({ url, unsubscribeToken }) {
  const u = escHtml(url);
  return `<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#0a0a0a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background:#0a0a0a;padding:24px 0;">
  <tr><td align="center">
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="560" style="max-width:560px;width:100%;">
      <tr><td style="padding:0 20px 18px;">
        <div style="font-size:22px;font-weight:800;color:#fff;letter-spacing:1px;">CANNON FIGHT <span style="color:#e63946;">LAB</span></div>
      </td></tr>
      <tr><td style="padding:0 20px;color:#e8e8e8;font-size:15px;line-height:1.6;">
        <p style="margin:0 0 14px;">Someone asked for the Cannon Card Brief to be sent to this address.</p>
        <p style="margin:0 0 20px;">If that was you, confirm it:</p>
        <p style="margin:0 0 20px;"><a href="${u}" style="background:#e63946;color:#fff;padding:12px 24px;border-radius:6px;font-weight:700;text-decoration:none;display:inline-block;">Confirm my email</a></p>
        <p style="margin:0 0 14px;color:#999;font-size:13px;">The link works for ${TOKEN_TTL_HOURS / 24} days. If the button does not work, paste this into your browser:<br><span style="color:#bbb;word-break:break-all;">${u}</span></p>
        <p style="margin:0 0 14px;">If it wasn't you, ignore this email. We won't send you anything else.</p>
        <p style="margin:0 0 14px;color:#999;font-size:13px;">The Brief is one email before each UFC card: what the betting market did that week. No picks.</p>
      </td></tr>
      <tr><td style="padding:24px 20px 20px;color:#555;font-size:11px;text-align:center;line-height:1.5;">
        <a href="${escHtml(unsubscribeUrl(unsubscribeToken))}" style="color:#888;">Remove this address now</a><br>
        Cannon Fight Lab is an analytics publication, not a sportsbook. 21+ only. 1-800-GAMBLER.
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>`;
}

module.exports = {
  SITE,
  CONFIRM_SEND_BLOCKERS,
  TOKEN_BYTES,
  TOKEN_TTL_HOURS,
  MAX_CONFIRM_SENDS,
  CONFIRM_SUBJECT,
  newToken,
  isWellFormedToken,
  hashToken,
  confirmUrl,
  redactToken,
  redactedConfirmUrl,
  needsConfirmation,
  planConfirmation,
  isBriefRecipient,
  sendableBriefRecipients,
  isMissingColumnError,
  confirmDryRun,
  renderConfirmText,
  renderConfirmHtml,
};
