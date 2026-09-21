/* ==========================================================================
   tests/alerts.test.js — CFL may email you about a market, or it may not.

   The requirement this file exists for: AN ALERT MUST NEVER FIRE FROM A
   MISLEADING OR INSUFFICIENT MARKET COMPARISON.

   That is one sentence and at least six separate ways to get it wrong, so most
   of what is below is about the ways rather than about the happy path:

     - firing off a movement figure computed over fewer than three matched books
     - firing off a price nobody is offering any more
     - firing off a fight that is already over
     - RE-ARMING across a cohort change, so the "further move" being reported is
       really a change in which sportsbooks are in the median. This is the
       subtle one, it is the same error D-012 removed from the product, and it
       is the one a reasonable implementation gets wrong.
     - emailing the same crossing twice because two passes raced
     - emailing forty times in a fight week

   Run:  node tests/alerts.test.js
   ========================================================================== */

'use strict';
const fs = require('fs');
const path = require('path');
const root = f => path.join(__dirname, '..', f);
const read = f => fs.readFileSync(root(f), 'utf8');

const A = require('../alerts.js');
const MIGRATION = read('alerts_migration.sql');
const SENDER    = read('build/send-alerts.js');
const WORKFLOW  = read('.github/workflows/alerts.yml');
const UI        = read('watchlist-ui.js');
const PAGE      = read('watchlist.html');
const FIGHT     = read('fight.html');
const INDEX     = read('index.html');
const SHARED    = read('_shared.js');
const SCHEMA    = read('ANALYTICS_SCHEMA.md');
const FUNNEL    = read('funnel_events_migration.sql');

let passed = 0;
const failures = [];
function t(name, fn) { try { fn(); passed++; } catch (e) { failures.push(name + ' — ' + e.message); } }
function ok(c, m) { if (!c) throw new Error(m); }
function eq(a, b, m) {
  if (a !== b) throw new Error((m || 'value') + ': expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a));
}
const stripSql = s => s.replace(/^\s*--.*$/gm, ' ');
const stripJs  = s => s.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/^\s*\/\/.*$/gm, ' ');
const visible  = html => html
  .replace(/<!--[\s\S]*?-->/g, ' ')
  .replace(/<script[\s\S]*?<\/script>/gi, ' ')
  .replace(/<style[\s\S]*?<\/style>/gi, ' ')
  .replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');

const NOW = Date.parse('2026-09-21T18:00:00Z');

// A market row that is fine in every way, so each test can spoil exactly one
// thing and the failure names itself.
function goodMarket(over) {
  return Object.assign({
    fight_id: 1, fighter_a_name: 'A Fighter', fighter_b_name: 'B Fighter',
    book_count: 6, market_age_minutes: 20,
    best_american_a: 160, best_book_a: 'DraftKings',
    best_american_b: -190, best_book_b: 'FanDuel',
    movement_pts_a: 5.0, matched_book_count: 5, cohort_books: 5,
    cohort_fp: 'FP_ORIGINAL', baseline_at: '2026-09-18T08:00:00Z',
    movement_status: 'ok', alert_refusal: null, price_refusal: null, move_refusal: null
  }, over || {});
}
const priceAlert = over => Object.assign(
  { id: 1, kind: 'price_target', side: 'A', target_american: 150,
    is_active: true, fire_count: 0 }, over || {});
const moveAlert = over => Object.assign(
  { id: 2, kind: 'market_move', threshold_pts: 3, direction: 'either',
    is_active: true, fire_count: 0, armed_value: null,
    armed_cohort_fp: null, armed_baseline_at: null }, over || {});

/* ======================================================= the happy path, once */

t('a price that reaches the target fires', () => {
  const v = A.evaluate(priceAlert(), goodMarket(), NOW);
  eq(v.fire, true, 'did not fire');
  eq(v.value, 160, 'reported the wrong price');
});

t('a movement past the threshold fires', () => {
  const v = A.evaluate(moveAlert(), goodMarket(), NOW);
  eq(v.fire, true, 'did not fire');
  eq(v.value, 5, 'reported the wrong movement');
});

/* ============================== NEVER FIRE FROM AN INSUFFICIENT COMPARISON == */

t('a movement alert refuses below three matched books', () => {
  // The display path refuses this and prints a named reason. An email is a
  // stronger claim than a number on a page, so it cannot be laxer.
  [0, 1, 2].forEach(n => {
    const v = A.evaluate(moveAlert(), goodMarket({
      matched_book_count: n, cohort_books: n,
      move_refusal: 'insufficient_matched_books'
    }), NOW);
    eq(v.fire, false, 'fired on ' + n + ' matched books');
    eq(v.reason, 'insufficient_matched_books', 'reason at ' + n + ' books');
  });
});

t('a movement alert refuses when SQL nulled the figure, whatever else is set', () => {
  const v = A.evaluate(moveAlert(), goodMarket({
    movement_pts_a: null, move_refusal: 'no_movement_figure'
  }), NOW);
  eq(v.fire, false, 'fired with no movement figure');
});

t('a movement alert refuses when CFL never held a broad baseline', () => {
  const v = A.evaluate(moveAlert(), goodMarket({ move_refusal: 'no_broad_capture' }), NOW);
  eq(v.fire, false, 'fired without an honest baseline');
  eq(v.reason, 'no_broad_capture', 'reason');
});

t('nothing fires on a fight that is already over', () => {
  ['fight_settled', 'event_past', 'fight_inactive'].forEach(r => {
    eq(A.evaluate(priceAlert(), goodMarket({ price_refusal: r }), NOW).fire, false, 'price fired on ' + r);
    eq(A.evaluate(moveAlert(),  goodMarket({ move_refusal:  r }), NOW).fire, false, 'move fired on ' + r);
  });
});

t('a price alert refuses a price too old to send somebody to a book for', () => {
  const v = A.evaluate(priceAlert(), goodMarket({ price_refusal: 'stale_for_price' }), NOW);
  eq(v.fire, false, 'fired on a stale price');
  eq(v.reason, 'stale_for_price', 'reason');
});

t('the three-book floor is enforced in JS as well as in SQL', () => {
  // Belt and braces on the floor that matters most: if a future edit to the
  // view ever loses it, the sender still does not email anybody off two books.
  const v = A.evaluate(priceAlert(), goodMarket({ book_count: 2 }), NOW);
  eq(v.fire, false, 'fired off two sportsbooks with the view saying nothing');
  eq(v.reason, 'thin_book_count', 'reason');
});

t('a market refusal is never overridden by a met condition', () => {
  // The price is spectacular AND the market is refused. The refusal wins.
  const v = A.evaluate(priceAlert({ target_american: 100 }),
                       goodMarket({ best_american_a: 5000, price_refusal: 'thin_book_count' }), NOW);
  eq(v.fire, false, 'a good number beat a refusal');
});

t('nothing fires when there is no market at all', () => {
  eq(A.evaluate(priceAlert(), null, NOW).reason, 'no_market_yet', 'null market');
  eq(A.evaluate(priceAlert(), {}, NOW).reason, 'no_market_yet', 'empty market');
});

t('a paused alert fires nothing, whatever the market does', () => {
  eq(A.evaluate(priceAlert({ is_active: false }), goodMarket(), NOW).reason, 'paused', 'paused');
});

/* ========================== THE RE-ARM: never compare across a cohort change = */

t('a fired movement alert re-baselines silently when the cohort changes', () => {
  // THE CENTRAL TEST. The alert fired at 5 pts over cohort FP_ORIGINAL. It now
  // reads 9 pts — but over a DIFFERENT set of sportsbooks. The 4-point
  // "further move" is a fact about bookmaker turnover, not about the market,
  // and it is exactly the error D-012 removed (measured at up to 12.7 pts).
  const fired = moveAlert({ fire_count: 1, armed_value: 5,
                            armed_cohort_fp: 'FP_ORIGINAL',
                            armed_baseline_at: '2026-09-18T08:00:00Z' });
  const v = A.evaluate(fired, goodMarket({ movement_pts_a: 9, cohort_fp: 'FP_DIFFERENT' }), NOW);
  eq(v.fire, false, 'fired across a cohort change');
  eq(v.reason, 'cohort_changed_rebaselined', 'reason');
  eq(v.rebaseline, true, 'did not ask to re-baseline');
  eq(v.value, 9, 'the new reading must be carried so the sender can store it');
});

t('the same is true when the BASELINE instant moves, cohort identical', () => {
  const fired = moveAlert({ fire_count: 1, armed_value: 5,
                            armed_cohort_fp: 'FP_ORIGINAL',
                            armed_baseline_at: '2026-09-18T08:00:00Z' });
  const v = A.evaluate(fired, goodMarket({ movement_pts_a: 9,
                            baseline_at: '2026-09-19T08:00:00Z' }), NOW);
  eq(v.fire, false, 'fired across a baseline change');
  eq(v.reason, 'cohort_changed_rebaselined', 'reason');
});

t('a count that holds still while MEMBERSHIP changes is still a cohort change', () => {
  // Five books before, five books now, different five. Storing the count would
  // have called this unchanged; storing the fingerprint does not.
  const fired = moveAlert({ fire_count: 1, armed_value: 5,
                            armed_cohort_fp: 'FP_ORIGINAL',
                            armed_baseline_at: '2026-09-18T08:00:00Z' });
  const v = A.evaluate(fired, goodMarket({ movement_pts_a: 12,
                            matched_book_count: 5, cohort_books: 5,
                            cohort_fp: 'FP_SAME_SIZE_DIFFERENT_BOOKS' }), NOW);
  eq(v.fire, false, 'a same-size different-membership cohort was treated as unchanged');
  eq(v.reason, 'cohort_changed_rebaselined', 'reason');
});

t('the fingerprint is a fingerprint, not a count, in the SQL too', () => {
  const sql = stripSql(MIGRATION);
  ok(/md5\(string_agg\(\s*b\.book_id::text,\s*','\s*ORDER BY b\.book_id\)\)/.test(sql),
     'the cohort fingerprint is not an ordered md5 of the book ids');
  ok(/in_matched_cohort/.test(sql), 'the fingerprint is not restricted to the matched cohort');
});

t('a re-arm over the SAME cohort needs a full further step', () => {
  const armed = { fire_count: 1, armed_value: 5, armed_cohort_fp: 'FP_ORIGINAL',
                  armed_baseline_at: '2026-09-18T08:00:00Z' };
  const at = pts => A.evaluate(moveAlert(armed), goodMarket({ movement_pts_a: pts }), NOW);
  eq(at(6).fire, false, 'fired on a 1-point drift');
  eq(at(7.9).fire, false, 'fired just short of a full further step');
  eq(at(8).fire, true, 'did not fire on a full further step (5 + 3)');
});

t('a movement wobbling across the line it already reported stays quiet', () => {
  const armed = { fire_count: 1, armed_value: 5, armed_cohort_fp: 'FP_ORIGINAL',
                  armed_baseline_at: '2026-09-18T08:00:00Z' };
  [5, 4, 5.5, 3.2, 5.9].forEach(pts => {
    eq(A.evaluate(moveAlert(armed), goodMarket({ movement_pts_a: pts }), NOW).fire, false,
       'fired again at ' + pts + ' having already reported 5');
  });
});

t('a price alert is one-shot — "your price is here" is not said twice', () => {
  const v = A.evaluate(priceAlert({ fire_count: 1 }), goodMarket(), NOW);
  eq(v.fire, false, 'fired a price alert twice');
  eq(v.reason, 'already_fired', 'reason');
});

/* ================================================================ direction = */

t('direction is honoured and is signed the way SQL signs it', () => {
  // movement_pts_a positive means the market moved TOWARD fighter A.
  const m = pts => goodMarket({ movement_pts_a: pts });
  eq(A.evaluate(moveAlert({ direction: 'toward_a' }), m(5), NOW).fire, true,  'toward_a on +5');
  eq(A.evaluate(moveAlert({ direction: 'toward_a' }), m(-5), NOW).fire, false, 'toward_a on -5');
  eq(A.evaluate(moveAlert({ direction: 'toward_b' }), m(-5), NOW).fire, true,  'toward_b on -5');
  eq(A.evaluate(moveAlert({ direction: 'toward_b' }), m(5), NOW).fire, false, 'toward_b on +5');
  eq(A.evaluate(moveAlert({ direction: 'either' }),   m(-5), NOW).fire, true,  'either on -5');
});

/* ============================================================ price ordering = */

t('better means the American number and nothing else', () => {
  // The same ordering market.js and best_american_* already use. A second way
  // of ordering prices is a second answer to "which is best".
  ok(A.priceMeetsTarget(160, 150), '+160 should meet +150');
  ok(!A.priceMeetsTarget(140, 150), '+140 should not meet +150');
  ok(A.priceMeetsTarget(-105, -110), '-105 should meet -110');
  ok(!A.priceMeetsTarget(-120, -110), '-120 should not meet -110');
  ok(A.priceMeetsTarget(120, -110), '+120 should meet -110');
});

t('an impossible American price is refused at creation, not left to never fire', () => {
  // There are no American odds between -100 and +100. Accepting one makes an
  // alert that can never fire, which to the member looks exactly like a bug.
  [0, 50, -50, 99, -99].forEach(v =>
    ok(A.validate({ kind: 'price_target', side: 'A', target_american: v }),
       v + ' was accepted as a price'));
  ok(!A.validate({ kind: 'price_target', side: 'A', target_american: 100 }), '+100 is real');
  ok(!A.validate({ kind: 'price_target', side: 'A', target_american: -110 }), '-110 is real');
});

t('a half-specified alert is refused by JS and by the database', () => {
  eq(A.validate({ kind: 'price_target', target_american: 150 }), 'side_required', 'no side');
  eq(A.validate({ kind: 'price_target', side: 'A' }), 'target_required', 'no target');
  eq(A.validate({ kind: 'market_move', threshold_pts: 3 }), 'direction_required', 'no direction');
  eq(A.validate({ kind: 'market_move', direction: 'either' }), 'threshold_required', 'no threshold');
  const sql = stripSql(MIGRATION);
  ok(/CONSTRAINT user_alerts_shape CHECK/.test(sql),
     'the database does not enforce the same shape');
});

t('a threshold below half a point is refused', () => {
  // Below that, ordinary capture noise fires it and the member gets a stream of
  // emails about nothing.
  eq(A.validate({ kind: 'market_move', threshold_pts: 0.1, direction: 'either' }),
     'threshold_too_small', 'accepted a noise-level threshold');
});

/* ================================================== quiet / duplicate / spam = */

t('the dedupe key is the occurrence, never the value that triggered it', () => {
  // Keying on the value mints a fresh key every time the price ticks, which is
  // a unique constraint that permits exactly the duplicates it was added to stop.
  eq(A.dedupeKey(7, 1), 'alert:7:seq:1', 'shape');
  eq(A.dedupeKey(7, 1), A.dedupeKey(7, 1), 'not stable');
  ok(A.dedupeKey(7, 1) !== A.dedupeKey(7, 2), 'two occurrences share a key');
  ok(!/\b1[0-9]{2}\b/.test(A.dedupeKey(7, 1)), 'the key embeds a price');
});

t('the dedupe key is UNIQUE in the database and claimed before sending', () => {
  const sql = stripSql(MIGRATION);
  ok(/dedupe_key\s+text\s+NOT NULL UNIQUE/.test(sql),
     'dedupe_key is not a UNIQUE column — a check in the sender does not survive two concurrent passes');
  const js = stripJs(SENDER);
  const insertAt = js.indexOf("from('user_alert_deliveries').insert");
  const sendAt = js.search(/await send\(/);
  ok(insertAt !== -1, 'the sender never records a delivery');
  ok(insertAt < sendAt,
     'the sender emails BEFORE recording — a crash between the two re-sends forever');
  ok(/23505/.test(js), 'a duplicate key is not handled as "somebody already told them"');
});

t('one email per member per run, not one per alert', () => {
  const js = stripJs(SENDER);
  ok(/fired\.set\(|fired\.get\(/.test(js), 'firings are not grouped by member');
  ok(/claimed\.length === 1[\s\S]{0,200}alerts fired/.test(js) || /of your CFL alerts fired/.test(js),
     'no batched subject line — fifteen alerts would be fifteen emails');
});

t('cooldown, daily cap and quiet hours each hold on their own', () => {
  const prefs = { email_enabled: true, cooldown_minutes: 360, max_per_day: 6 };
  eq(A.maySendToUser(prefs, {}, NOW).ok, true, 'a clean member was blocked');
  eq(A.maySendToUser(prefs, { lastSentAt: '2026-09-21T17:00:00Z' }, NOW).reason, 'cooldown',
     'one hour after a send is not a cooldown');
  eq(A.maySendToUser(prefs, { lastSentAt: '2026-09-21T11:00:00Z' }, NOW).ok, true,
     'seven hours after a send is still blocked');
  eq(A.maySendToUser(prefs, { sentToday: 6 }, NOW).reason, 'daily_cap', 'cap not applied');
  eq(A.maySendToUser({ email_enabled: false }, {}, NOW).reason, 'email_disabled', 'opt-out ignored');
});

t('quiet hours are OFF unless set, and handle a window over midnight', () => {
  // NULL means off, deliberately: CFL does not know a member's time zone and a
  // guessed window silences the alerts they asked for at the hours they most
  // wanted them.
  eq(A.inQuietHours({}, NOW), false, 'unset quiet hours silenced somebody');
  eq(A.inQuietHours({ quiet_start_utc: 5, quiet_end_utc: 5 }, NOW), false,
     'a zero-length window silenced somebody');
  const at = h => Date.parse('2026-09-21T' + String(h).padStart(2, '0') + ':30:00Z');
  const w = { quiet_start_utc: 22, quiet_end_utc: 7 };
  eq(A.inQuietHours(w, at(23)), true, '23:30 should be inside 22->07');
  eq(A.inQuietHours(w, at(3)),  true, '03:30 should be inside 22->07');
  eq(A.inQuietHours(w, at(12)), false, '12:30 should be outside 22->07');
  eq(A.inQuietHours(w, at(7)),  false, '07:30 should be outside 22->07');
});

t('a suppressed member still has the occurrence recorded', () => {
  // Otherwise the same crossing is presented to them later as though it were
  // new, which is the duplicate this whole mechanism exists to stop.
  const js = stripJs(SENDER);
  ok(/suppressed/.test(js), 'suppression is not recorded at all');
  ok(/if \(!gate\.ok\)[\s\S]{0,400}armAlert/.test(js),
     'a suppressed member does not arm the alert, so they will be told again later');
});

/* ==================================================== a price and a move differ */

t('a price and a move do not share a staleness rule, in JS or in SQL', () => {
  ok(A.MAX_PRICE_AGE_MIN < A.MAX_MOVE_AGE_MIN,
     'a price is an offer and a move is a historical fact — they cannot share a ceiling');
  const sql = stripSql(MIGRATION);
  ok(sql.indexOf(String(A.MAX_PRICE_AGE_MIN)) !== -1,
     'the SQL does not use the same price ceiling as alerts.js (' + A.MAX_PRICE_AGE_MIN + ')');
  ok(sql.indexOf(String(A.MAX_MOVE_AGE_MIN)) !== -1,
     'the SQL does not use the same move ceiling as alerts.js (' + A.MAX_MOVE_AGE_MIN + ')');
  ok(/stale_for_price/.test(sql) && /stale_for_move/.test(sql),
     'the two staleness refusals are not separately named');
});

t('the three-book floor is the same number everywhere', () => {
  eq(A.MIN_BOOKS, 3, 'alerts.js floor');
  const sql = stripSql(MIGRATION);
  ok(/< 3\s*$|< 3\s|cohort_books < 3/m.test(sql), 'the SQL floor is not three');
});

/* ========================================================== security shape === */

t('every alert table is scoped to its owner and nothing is readable by anon', () => {
  const sql = stripSql(MIGRATION);
  ['user_watchlist', 'user_alerts', 'user_alert_prefs', 'user_alert_deliveries'].forEach(tbl => {
    ok(new RegExp('ALTER TABLE public\\.' + tbl + ' ENABLE ROW LEVEL SECURITY').test(sql),
       tbl + ' does not have RLS enabled');
    ok(new RegExp('REVOKE ALL ON public\\.' + tbl + ' FROM anon').test(sql),
       tbl + ' does not revoke from anon');
  });
});

t('REVOKE names authenticated too, because TRUNCATE bypasses RLS', () => {
  // Found by checking the grants after applying rather than by reading the
  // migration: `authenticated` had inherited TRUNCATE on three of four tables.
  // TRUNCATE is not subject to row level security, so any signed-in member
  // could have emptied every other member's alerts with RLS never consulted.
  const sql = stripSql(MIGRATION);
  ['user_watchlist', 'user_alerts', 'user_alert_prefs', 'user_alert_deliveries'].forEach(tbl => {
    ok(new RegExp('REVOKE ALL ON public\\.' + tbl + ' FROM anon, authenticated').test(sql),
       tbl + ' revokes from anon only — authenticated keeps the inherited TRUNCATE');
  });
});

t('a member can read their delivery history and cannot write or erase it', () => {
  const sql = stripSql(MIGRATION);
  ok(/CREATE POLICY "deliveries select own"/.test(sql), 'no read policy on deliveries');
  ok(!/CREATE POLICY[^;]*ON public\.user_alert_deliveries\s+FOR (INSERT|UPDATE|DELETE)/i.test(sql),
     'a member can write their own delivery rows — erasing one defeats the dedupe key');
  ok(/GRANT SELECT\s+ON public\.user_alert_deliveries TO authenticated/.test(sql),
     'deliveries are not readable by their owner');
});

t('the suppression memory is pinned against every column it must cover', () => {
  // Same lesson as the profiles P0 (D-017): protection covers exactly the
  // columns it names. This asserts on the OMISSION, so it fails when a new
  // sender-owned column is added and forgotten.
  const sql = stripSql(MIGRATION);
  const body = sql.slice(sql.indexOf('user_alerts_pin_sender_columns'));
  ['last_evaluated_at', 'last_fired_at', 'fire_count', 'armed_value',
   'armed_cohort_fp', 'armed_baseline_at', 'user_id'].forEach(col => {
    ok(new RegExp('NEW\\.' + col + '\\s*:=\\s*OLD\\.' + col).test(body),
       col + ' is not restored by the pin trigger — a member could write it');
  });
});

t('the pin trigger is SECURITY INVOKER, or it protects nothing', () => {
  // Inside a SECURITY DEFINER function `current_user` is the function's OWNER,
  // so the "is this the sender" guard is always true and the trigger is inert
  // while reading as though it works. This was live for one revision.
  const sql = stripSql(MIGRATION);
  const fn = sql.slice(sql.indexOf('CREATE OR REPLACE FUNCTION public.user_alerts_pin_sender_columns'),
                       sql.indexOf('DROP TRIGGER IF EXISTS trg_user_alerts_pin'));
  ok(!/SECURITY DEFINER/.test(fn),
     'the pin trigger is SECURITY DEFINER, which makes current_user the owner and the guard always true');
  ok(/current_user IN \(/.test(fn), 'the guard does not test current_user');
});

t('the Free/Pro split has exactly one home, and it is not switched on', () => {
  const sql = stripSql(MIGRATION);
  ok(/CREATE OR REPLACE FUNCTION public\.alert_quota\(\)/.test(sql), 'no alert_quota()');
  const fn = sql.slice(sql.indexOf('FUNCTION public.alert_quota()'),
                       sql.indexOf('COMMENT ON FUNCTION public.alert_quota()'));
  ok(!/current_user_is_pro/.test(fn),
     'the quota already gates on Pro — D-019 moved enforcement behind the payment gates');
  ok(!/current_user_is_pro/.test(stripSql(MIGRATION)),
     'something in the alerts layer gates on Pro; nothing may be enforced yet');
});

t('nothing in the alert surfaces gates a fetch on a browser tier check', () => {
  [['watchlist.html', PAGE], ['watchlist-ui.js', UI], ['fight.html', FIGHT]].forEach(([n, src]) => {
    ok(!/if\s*\(\s*cflAuth\.(isPremium|isPro)\(\)\s*\)[\s\S]{0,120}(from\(|fetch\()/.test(stripJs(src)),
       n + ' gates a data fetch on a browser tier check');
  });
});

/* ================================================================== analytics */

t('the five new event names exist in all three places', () => {
  ['watchlist_added', 'watchlist_removed', 'alert_created', 'alert_fired', 'alert_clicked']
    .forEach(name => {
      ok(SHARED.indexOf("'" + name + "'") !== -1, name + ' missing from cfl.EVENTS');
      ok(FUNNEL.indexOf("'" + name + "'") !== -1, name + ' missing from the CHECK constraint');
      ok(SCHEMA.indexOf('`' + name + '`') !== -1, name + ' missing from ANALYTICS_SCHEMA.md');
    });
});

t('the CHECK constraint can actually learn a new name', () => {
  // The add-if-absent form is re-run SAFE and not re-run CORRECT: once the
  // constraint exists it can never change, so the file and the database would
  // silently disagree about which events are legal. Adding five names is
  // exactly the case it would have failed at.
  ok(/DROP CONSTRAINT IF EXISTS funnel_events_known_event/.test(FUNNEL),
     'the constraint is added-if-absent, so editing the list changes nothing');
});

t('alert_fired is emitted by the server and says so', () => {
  const js = stripJs(SENDER);
  ok(/event: 'alert_fired'/.test(js), 'the sender never emits alert_fired');
  ok(/srv:alerts/.test(js), 'the server emission is not marked as non-visitor');
  ok(/`alert_fired`[^|]*\*\*server-side\.\*\*|server, not the browser/.test(SCHEMA),
     'ANALYTICS_SCHEMA.md does not say alert_fired is server-side');
});

t('nothing identifying is put in an alert email link or event', () => {
  // A stable per-member identifier in a URL is a stable per-member identifier
  // in analytics. The link carries src and kind, and no ids.
  const js = stripJs(SENDER);
  const links = js.match(/\$\{SITE\}[^\s"'`]*/g) || [];
  links.forEach(l => {
    ok(!/alert_id|user_id|email=/.test(l), 'an email link carries an identifier: ' + l);
  });
  ok(/props: \{ kind: [^}]*\}/.test(js), 'the funnel props are not limited to the kind');
});

/* =================================================================== delivery */

t('email is the only channel, and no SMS or push infrastructure crept in', () => {
  const sql = stripSql(MIGRATION);
  ok(/channel\s+text\s+NOT NULL DEFAULT 'email' CHECK \(channel IN \('email'\)\)/.test(sql),
     'the channel column allows something other than email');
  [SENDER, UI, PAGE].forEach(src => {
    // Word boundaries: `prefsMsg` contains "sMs" and is not a Twilio dependency.
    ok(!/\b(twilio|sms|firebase|onesignal|web-?push|apns)\b/i.test(stripJs(src)),
       'an SMS or push dependency appeared');
  });
});

t('the sender falls back to dry run rather than failing without secrets', () => {
  const js = stripJs(SENDER);
  ok(/DRY_RUN\s*=\s*!RESEND_KEY/.test(js), 'a missing Resend key does not force a dry run');
  ok(/process\.exit\(0\)/.test(js), 'a missing service key exits non-zero — a fork without secrets fails');
});

t('the workflow measures elapsed time, never the wall clock modulo an interval', () => {
  // GitHub throttles high-frequency crons: odds.yml asks for */5 and was
  // delivered four times in a day at arbitrary minutes. A rule written against
  // the wall clock simply never fires, and that defect cost a whole card day of
  // odds capture.
  const js = stripJs(SENDER);
  ok(!/getMinutes\(\)\s*%|%\s*WAKE|minute\s*%/.test(js),
     'the sender gates on the wall clock modulo an interval');
  ok(/lastSentAt|fired_at/.test(js), 'nothing is measured from a stored timestamp');
  ok(/concurrency:/.test(WORKFLOW), 'two passes can overlap');
  ok(/contents:\s*read/.test(WORKFLOW), 'the alert workflow is handed a writable token');
});

/* ======================================================================= copy */

t('an alert email reports the market and sells nothing', () => {
  const said = A.describeFiring(priceAlert(), goodMarket(), 160);
  const all = (said.head + ' ' + said.body).toLowerCase();
  // Word boundaries: "or better" is not a betting instruction, and a substring
  // match on 'bet' would have flagged it.
  [/\bbets?\b/, /\bbetting\b/, /\block\b/, /\bvalue\b/, /\bedge\b/, /we like/,
   /our pick/, /\bhammer\b/, /\bsmash\b/, /act now/, /don't miss/, /guaranteed/]
    .forEach(re => ok(!re.test(all), 'alert copy touts: ' + re));
  ok(/check the sportsbook/.test(all), 'a price email does not tell them to check the book');
  ok(/6 sportsbooks/.test(said.body), 'a price is quoted without its book count');
  ok(/captured/.test(said.body), 'a price is quoted without its age');
});

t('a movement email names the matched cohort and claims nothing about the winner', () => {
  const said = A.describeFiring(moveAlert(), goodMarket(), 5);
  ok(/5 sportsbooks quoting at both ends/.test(said.body),
     'the movement email does not say the figure is over the matched cohort');
  ok(/not a view on who wins/i.test(said.body),
     'the movement email does not disclaim a view on the winner');
  ok(!/open(ed|ing)? line|since open/i.test(said.head + said.body),
     'the movement email calls the baseline an opening line');
});

t('no surface calls the baseline an opening line', () => {
  // CFL has never observed a sportsbook opener. Visible text only: a comment
  // explaining the ban must not read as the page committing it.
  [['watchlist.html', visible(PAGE)], ['fight.html', visible(FIGHT)],
   ['index.html', visible(INDEX)]].forEach(([n, txt]) => {
    ok(!/opening line|opened at|since open\b/i.test(txt), n + ' says "opening line"');
  });
});

t('the watchlist page explains a quiet alert instead of leaving it blank', () => {
  // A member who cannot see WHY nothing arrived assumes the feature is broken,
  // and they are right to: a silent refusal and a bug look identical.
  const states = Object.keys(A.REFUSALS.reduce((m, r) => (m[r] = 1, m), {}));
  const covered = Object.keys(require('../watchlist-ui.js').STATE_COPY || {});
  ['insufficient_matched_books', 'no_broad_capture', 'thin_book_count',
   'stale_for_price', 'fight_settled', 'paused'].forEach(r =>
    ok(covered.indexOf(r) !== -1, 'no plain-English copy for the refusal "' + r + '"'));
  ok(states.length > 0, 'no refusals declared');
});

t('the watchlist page promises no pick and no stake', () => {
  const txt = visible(PAGE).toLowerCase();
  ['who to back', 'suggested stake', 'our pick', 'best bet'].forEach(p =>
    ok(txt.indexOf(p) === -1 || /will not|never/.test(txt), 'the page promises: ' + p));
  ok(/will not tell you who to back/.test(txt), 'the page does not say what an alert will not do');
});

t('the star is offered to signed-out visitors, not hidden from them', () => {
  // A missing control reads as a feature that does not exist. An account wall
  // explained on tap is truer, and it is not a paywall.
  const ui = stripJs(UI);
  ok(/Create a free account to keep a watchlist/.test(ui),
     'a signed-out visitor is not told why the star needs an account');
  ok(/stays? free/.test(ui), 'the account wall is not distinguished from a paywall');
});

t('every alert surface loads the shared modules rather than inlining them', () => {
  [['watchlist.html', PAGE], ['fight.html', FIGHT], ['index.html', INDEX]].forEach(([n, src]) => {
    ok(/<script src="alerts\.js/.test(src), n + ' does not load alerts.js');
    ok(/<script src="watchlist-ui\.js/.test(src), n + ' does not load watchlist-ui.js');
  });
});

// ------------------------------------------------------------------ report
if (failures.length) {
  console.log(`\n  ${passed} passed, ${failures.length} FAILED\n`);
  failures.forEach(f => console.log(`  ✗ ${f}\n`));
  process.exit(1);
}
console.log(`\n  ${passed} passed — an alert fires on what happened, or it stays quiet and says why.\n`);
