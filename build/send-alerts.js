// =============================================================================
// send-alerts.js — the only thing that emails a member about a market.
// =============================================================================
// PLAIN ENGLISH: members asked to hear when a price they want shows up, or when
// a market moves more than they can ignore. This checks, and emails the ones
// whose thing actually happened. Everyone else hears nothing, and the reason is
// written down.
//
// -----------------------------------------------------------------------------
// WHAT THIS SCRIPT DOES NOT DECIDE
// -----------------------------------------------------------------------------
// Almost everything. The market refusals are in SQL (`v_fight_alert_market`),
// beside the numbers they refuse. The firing, re-arm and suppression rules are
// in `alerts.js`, which is pure and tested offline. This file is plumbing:
// read, ask, record, send, record again. That split is deliberate — the part
// that decides whether to make a claim about a market should not be the part
// that is hardest to test.
//
// -----------------------------------------------------------------------------
// THE ORDER OF OPERATIONS, WHICH IS THE WHOLE DESIGN
// -----------------------------------------------------------------------------
//   1. insert the delivery row, with its UNIQUE dedupe key
//   2. only then send the email
//   3. then mark the row sent and arm the alert
//
// Backwards — send, then record — loses the record whenever the process dies
// between the two, and the next pass sends again. This way a crash costs a
// member ONE email they should have had; the other order costs them an
// unbounded number they should not. A `pending` row that never reached `sent`
// is visible in the table and is the thing to go and look at.
//
// A duplicate key (23505) means another pass already told them. That is not an
// error, it is the mechanism working, and the run carries on.
//
// -----------------------------------------------------------------------------
// GITHUB CRON IS NOT A SCHEDULE
// -----------------------------------------------------------------------------
// GitHub throttles high-frequency schedules hard — measured, `odds.yml` asks for
// every 5 minutes and was delivered four times in a day at arbitrary minutes
// (CLAUDE.md). Nothing here may assume it runs when it asked to. Every rule is
// written against ELAPSED TIME from a stored timestamp, never against the wall
// clock modulo an interval, which is the defect that cost a whole card day of
// odds capture.
//
// It is also harmless to run often: the per-member cooldown and the dedupe key
// mean extra passes send nothing.
//
// -----------------------------------------------------------------------------
// ENV
// -----------------------------------------------------------------------------
//   SUPABASE_SERVICE_ROLE_KEY   required to read across members and to write
//                               delivery rows and the armed state
//   RESEND_API_KEY              missing -> automatic dry run
//   RESEND_FROM                 verified sender
//   ALERTS_DRY_RUN              "1"/"true" -> render and log, never send
// =============================================================================

const { createClient } = require('@supabase/supabase-js');
const A = require('../alerts.js');

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SERVICE_KEY  = process.env.SUPABASE_SERVICE_ROLE_KEY;
const RESEND_KEY   = process.env.RESEND_API_KEY;
const FROM         = process.env.RESEND_FROM || 'Cannon Fight Lab <hello@cannonfightlab.com>';
const DRY_RUN      = !RESEND_KEY || /^(1|true|yes)$/i.test(process.env.ALERTS_DRY_RUN || '');
const SITE         = 'https://cannonfightlab.com';

if (!SERVICE_KEY) {
  console.error('[alerts] SUPABASE_SERVICE_ROLE_KEY is not set — cannot evaluate alerts.');
  console.error('[alerts] Exiting 0: a missing secret is a not-configured runner, not a failure.');
  process.exit(0);
}

const sb = createClient(SUPABASE_URL, SERVICE_KEY, { auth: { persistSession: false } });
const esc = s => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

// ---------------------------------------------------------------------------
// Counters. Printed at the end, because "sent 0" and "did not run" must not
// look the same in a workflow log.
// ---------------------------------------------------------------------------
const tally = { alerts: 0, fired: 0, rebaselined: 0, refused: {}, members: 0,
                emails: 0, duplicates: 0, failed: 0 };
const note = r => { tally.refused[r] = (tally.refused[r] || 0) + 1; };

async function main() {
  const now = Date.now();
  // Say WHICH dry run this is. "Nothing was sent" has two very different
  // causes — the operator asked for a rehearsal, or the mailer was never
  // configured — and a controlled delivery test needs to tell them apart
  // before it concludes anything. Presence only; no secret is printed.
  const why = !RESEND_KEY ? 'no RESEND_API_KEY — the mailer is not configured'
            : 'ALERTS_DRY_RUN was set';
  console.log('[alerts] run at ' + new Date(now).toISOString() +
              (DRY_RUN ? '  (DRY RUN: ' + why + ')' : '  (LIVE — emails will be sent)'));
  console.log('[alerts] mailer: RESEND_API_KEY ' + (RESEND_KEY ? 'present' : 'ABSENT') +
              ' · RESEND_FROM ' + (process.env.RESEND_FROM ? 'set' : 'defaulted to ' + FROM));

  // ---- 1. every active alert, with the market beside it --------------------
  const { data: alerts, error: aErr } = await sb
    .from('user_alerts')
    .select('*')
    .eq('is_active', true);
  if (aErr) throw aErr;
  tally.alerts = (alerts || []).length;
  if (!tally.alerts) { report(); return; }

  const fightIds = [...new Set(alerts.map(a => a.fight_id))];
  const { data: markets, error: mErr } = await sb
    .from('v_fight_alert_market')
    .select('*')
    .in('fight_id', fightIds);
  if (mErr) throw mErr;
  const byFight = new Map((markets || []).map(m => [m.fight_id, m]));

  // ---- 2. decide, one alert at a time --------------------------------------
  const fired = new Map();          // user_id -> [{alert, market, verdict}]
  const rebaseline = [];

  for (const alert of alerts) {
    const market = byFight.get(alert.fight_id) || null;
    const v = A.evaluate(alert, market, now);

    if (v.rebaseline) {
      // The cohort or the baseline changed underneath a fired alert. Store the
      // new reading and say NOTHING: the comparison that would have been made
      // is one CFL would refuse to print. Costs one notification; the
      // alternative costs the member's trust in every notification.
      rebaseline.push({ id: alert.id, armed_value: v.value,
                        armed_cohort_fp: v.cohortFp, armed_baseline_at: v.baselineAt });
      tally.rebaselined++;
      note('cohort_changed_rebaselined');
      continue;
    }
    if (!v.fire) { note(v.reason || 'unknown'); continue; }

    tally.fired++;
    if (!fired.has(alert.user_id)) fired.set(alert.user_id, []);
    fired.get(alert.user_id).push({ alert, market, verdict: v });
  }

  // Re-baselines are a bulk write and touch nothing a member can see.
  for (const r of rebaseline) {
    await sb.from('user_alerts').update({
      armed_value: r.armed_value, armed_cohort_fp: r.armed_cohort_fp,
      armed_baseline_at: r.armed_baseline_at, last_evaluated_at: new Date(now).toISOString()
    }).eq('id', r.id);
  }

  if (!fired.size) { report(); return; }

  // ---- 3. per-member gates, then ONE email each ----------------------------
  const userIds = [...fired.keys()];
  const [{ data: prefsRows }, { data: profileRows }] = await Promise.all([
    sb.from('user_alert_prefs').select('*').in('user_id', userIds),
    sb.from('profiles').select('id, display_name').in('id', userIds)
  ]);
  const prefsBy = new Map((prefsRows || []).map(p => [p.user_id, p]));
  const nameBy  = new Map((profileRows || []).map(p => [p.id, p.display_name]));

  const dayStart = new Date(now); dayStart.setUTCHours(0, 0, 0, 0);

  for (const userId of userIds) {
    const items = fired.get(userId);
    const prefs = prefsBy.get(userId) || A.DEFAULT_PREFS;

    // Recent delivery state, read fresh rather than cached: another pass may
    // have sent to this member since this run started.
    const { data: recent } = await sb
      .from('user_alert_deliveries')
      .select('fired_at, send_status')
      .eq('user_id', userId)
      .eq('send_status', 'sent')
      .gte('fired_at', dayStart.toISOString())
      .order('fired_at', { ascending: false });

    const state = {
      lastSentAt: recent && recent.length ? recent[0].fired_at : null,
      sentToday: (recent || []).length
    };
    const gate = A.maySendToUser(prefs, state, now);

    const email = await addressFor(userId);
    if (!email) { note('no_email_on_file'); continue; }

    // ---- 3a. claim each occurrence BEFORE sending anything ----------------
    const claimed = [];
    for (const item of items) {
      const seq = (item.alert.fire_count || 0) + 1;
      const key = A.dedupeKey(item.alert.id, seq);
      const said = A.describeFiring(item.alert, item.market, item.verdict.value);
      const row = {
        user_id: userId, alert_id: item.alert.id, fight_id: item.alert.fight_id,
        kind: item.alert.kind, dedupe_key: key,
        send_status: gate.ok ? (DRY_RUN ? 'dry_run' : 'pending') : 'suppressed',
        suppressed_reason: gate.ok ? null : gate.reason,
        // The numbers exactly as they were sent. If a member ever says "you
        // told me it moved six points and it had not", this is the answer.
        payload: {
          head: said.head, body: said.body,
          value: item.verdict.value,
          movement_pts_a: item.market.movement_pts_a,
          matched_book_count: item.market.matched_book_count,
          book_count: item.market.book_count,
          market_age_minutes: Math.round(Number(item.market.market_age_minutes)),
          last_updated: item.market.last_updated,
          movement_method: item.market.movement_method,
          cohort_fp: item.market.cohort_fp,
          baseline_at: item.market.baseline_at
        }
      };
      const { error } = await sb.from('user_alert_deliveries').insert(row);
      if (error) {
        // 23505: another pass already claimed this occurrence. The mechanism
        // working, not a fault.
        if (error.code === '23505') { tally.duplicates++; continue; }
        console.error('[alerts] could not record delivery', error.message);
        tally.failed++;
        continue;
      }
      claimed.push({ item, key, said, seq });
    }

    if (!claimed.length) continue;

    // A suppressed member still gets their occurrences RECORDED — so the alert
    // arms, and they are not told about the same crossing later as though it
    // were new. They simply are not emailed about it.
    if (!gate.ok) {
      note(gate.reason);
      for (const c of claimed) await armAlert(c, now);
      continue;
    }

    tally.members++;
    const html = renderEmail(nameBy.get(userId), claimed);
    const subject = claimed.length === 1
      ? claimed[0].said.head
      : claimed.length + ' of your CFL alerts fired';

    let ok = true, err = null;
    if (DRY_RUN) {
      console.log('\n--- WOULD SEND to ' + mask(email) + ' ---');
      console.log('Subject: ' + subject);
      claimed.forEach(c => console.log('  • ' + c.said.head + '\n    ' + c.said.body));
    } else {
      const res = await send(email, subject, html);
      ok = res.ok; err = res.error;
    }

    const keys = claimed.map(c => c.key);
    await sb.from('user_alert_deliveries')
      .update(ok ? { send_status: DRY_RUN ? 'dry_run' : 'sent', sent_at: new Date().toISOString() }
                 : { send_status: 'failed', error: String(err).slice(0, 500) })
      .in('dedupe_key', keys);

    if (ok) {
      tally.emails++;
      for (const c of claimed) await armAlert(c, now);
      await trackFired(claimed);
    } else {
      tally.failed++;
      // Deliberately NOT armed on a failed send: the occurrence stays unclaimed
      // in the member's eyes and the next pass can try again. The delivery row
      // survives as `failed`, so the history is honest about it.
    }
  }

  report();
}

// ---------------------------------------------------------------------------
// Arming: the suppression memory. Written by this script and nobody else — a
// database trigger restores these columns for every other role, because a
// member who could clear them could put themselves in a notification loop.
// ---------------------------------------------------------------------------
async function armAlert(c, now) {
  const patch = {
    fire_count: (c.item.alert.fire_count || 0) + 1,
    last_fired_at: new Date(now).toISOString(),
    last_evaluated_at: new Date(now).toISOString()
  };
  if (c.item.alert.kind === 'market_move') {
    patch.armed_value       = c.item.verdict.value;
    patch.armed_cohort_fp   = c.item.verdict.cohortFp;
    patch.armed_baseline_at = c.item.verdict.baselineAt;
  }
  const { error } = await sb.from('user_alerts').update(patch).eq('id', c.item.alert.id);
  if (error) console.error('[alerts] could not arm alert ' + c.item.alert.id, error.message);
}

// ---------------------------------------------------------------------------
// Funnel. Server-side emission into the same table the browser writes, with a
// session id that is obviously not a visitor's. Nothing identifying: no member
// id, no email, no fight-level identifier beyond the kind.
// ---------------------------------------------------------------------------
async function trackFired(claimed) {
  const rows = claimed.map(c => ({
    event: 'alert_fired',
    session_id: 'srv:alerts',
    path: '/alerts',
    props: { kind: c.item.alert.kind, seq: c.seq }
  }));
  const { error } = await sb.from('funnel_events').insert(rows);
  if (error) console.error('[alerts] funnel insert failed (non-fatal)', error.message);
}

// ---------------------------------------------------------------------------
// The member's address. auth.users is not reachable through PostgREST, so this
// goes through the admin API, which the service-role key is for.
// ---------------------------------------------------------------------------
const addressCache = new Map();
async function addressFor(userId) {
  if (addressCache.has(userId)) return addressCache.get(userId);
  let email = null;
  try {
    const { data, error } = await sb.auth.admin.getUserById(userId);
    if (!error && data && data.user) email = data.user.email || null;
  } catch (e) { /* fall through — a missing address is a skip, not a crash */ }
  addressCache.set(userId, email);
  return email;
}

const mask = e => String(e).replace(/^(.).*(@.*)$/, '$1***$2');

// ---------------------------------------------------------------------------
// The email. Plain verdict first, plain reason second (COPY_STYLE.md). Every
// number carries its book count and its capture age. No recommendation, no
// stake, no "act now", and the unsubscribe route is one click into settings.
// ---------------------------------------------------------------------------
function renderEmail(name, claimed) {
  const hello = name ? 'Hi ' + esc(name) + ',' : 'Hi,';
  const blocks = claimed.map(c => `
    <tr><td style="padding:18px 0;border-bottom:1px solid #26262b">
      <div style="font:600 17px/1.35 -apple-system,Segoe UI,Roboto,sans-serif;color:#f4f4f5;margin-bottom:6px">
        ${esc(c.said.head)}
      </div>
      <div style="font:400 14px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;color:#a1a1aa">
        ${esc(c.said.body)}
      </div>
      <div style="margin-top:10px">
        <a href="${SITE}/fight.html?id=${encodeURIComponent(c.item.alert.fight_id)}&src=alert"
           style="font:600 13px/1 -apple-system,Segoe UI,Roboto,sans-serif;color:#ef4444;text-decoration:none">
          Open this fight in Fight Lab →</a>
      </div>
    </td></tr>`).join('');

  return `<!DOCTYPE html><html><body style="margin:0;background:#0a0a0a;padding:28px 16px">
  <table role="presentation" width="100%" style="max-width:560px;margin:0 auto">
    <tr><td style="font:800 20px/1.2 -apple-system,Segoe UI,Roboto,sans-serif;color:#f4f4f5;padding-bottom:4px">
      Cannon Fight <span style="color:#ef4444">Lab</span></td></tr>
    <tr><td style="font:400 14px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;color:#a1a1aa;padding-bottom:6px">
      ${hello} here is what you asked to hear about.</td></tr>
    ${blocks}
    <tr><td style="padding-top:20px;font:400 12px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;color:#71717a">
      Prices are the last CFL captured, never live, and every one above is shown
      with the number of sportsbooks behind it and when it was taken. Check the
      sportsbook before you act. CFL publishes no picks and no forecast.
      <br><br>
      <a href="${SITE}/watchlist.html?src=alert" style="color:#a1a1aa">Manage your alerts</a>
      &nbsp;·&nbsp;
      <a href="${SITE}/watchlist.html?src=alert#prefs" style="color:#a1a1aa">Send fewer of these</a>
    </td></tr>
  </table></body></html>`;
}

async function send(to, subject, html) {
  try {
    const res = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + RESEND_KEY, 'Content-Type': 'application/json' },
      body: JSON.stringify({ from: FROM, to: [to], subject, html })
    });
    if (!res.ok) return { ok: false, error: 'resend ' + res.status + ' ' + (await res.text()).slice(0, 200) };
    return { ok: true, error: null };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

function report() {
  console.log('\n[alerts] ' + tally.alerts + ' active · ' + tally.fired + ' fired · ' +
              tally.emails + ' emails to ' + tally.members + ' members · ' +
              tally.rebaselined + ' re-baselined · ' + tally.duplicates + ' duplicates · ' +
              tally.failed + ' failed');
  const refusals = Object.entries(tally.refused).sort((a, b) => b[1] - a[1]);
  if (refusals.length) {
    console.log('[alerts] nothing sent for these reasons, which is the point:');
    refusals.forEach(([r, n]) => console.log('           ' + String(n).padStart(5) + '  ' + r));
  }
}

main().catch(e => { console.error('[alerts] FAILED', e); process.exit(1); });
