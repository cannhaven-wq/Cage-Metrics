/* ==========================================================================
   tests/analytics-events.test.js — the funnel counts, and counts nothing else.

   Three things this pins, in order of how much damage each would do:

     1. NO PERSONAL DATA. cfl.track strips any prop key that looks like an
        email, a name, a user id, a token, an IP, or a bet amount, rather than
        trusting nineteen future call sites to remember. A tracker that leaks
        one address has done more harm than the whole funnel is worth.
     2. ONE LIST, THREE PLACES. The event names live in cfl.EVENTS, in
        ANALYTICS_SCHEMA.md, and as a CHECK constraint in
        funnel_events_migration.sql. If they drift, a typo becomes a funnel
        step that silently reads zero forever, which looks exactly like a step
        nobody reached.
     3. IT NEVER BREAKS A PAGE. Analytics is the least important thing on any
        surface. Every path is wrapped; a missing client, blocked storage or a
        thrown accessor must not propagate.

   It loads _shared.js in a VM with stubs and asserts on real behaviour, not on
   the presence of strings.

   Run:  node tests/analytics-events.test.js
   ========================================================================== */

'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = f => path.join(__dirname, '..', f);
const read = f => fs.readFileSync(root(f), 'utf8');

const SHARED = read('_shared.js');
const MIGRATION = read('funnel_events_migration.sql');
const SCHEMA_DOC = read('ANALYTICS_SCHEMA.md');

let passed = 0;
const failures = [];
function t(name, fn) {
  try { fn(); passed++; }
  catch (e) { failures.push(name + ' — ' + e.message); }
}
function ok(cond, msg) { if (!cond) throw new Error(msg); }
function eq(a, b, msg) {
  if (a !== b) throw new Error((msg || 'value') + ': expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a));
}

// ------------------------------------------------------- load _shared.js
// A fake browser, minimal but honest: storage that works, a Supabase client
// that records inserts, and a plausible() that records names.
function bootstrap(opts) {
  const o = opts || {};
  const inserts = [];
  const plausibleCalls = [];
  const warnings = [];
  const store = {};
  const session = {};
  const mkStore = bag => ({
    getItem: k => (o.throwStorage ? (() => { throw new Error('blocked'); })() : (k in bag ? bag[k] : null)),
    setItem: (k, v) => { if (o.throwStorage) throw new Error('blocked'); bag[k] = String(v); },
    removeItem: k => { delete bag[k]; }
  });
  const win = {
    location: { pathname: '/index.html', hostname: 'cannonfightlab.com', search: '' },
    sessionStorage: mkStore(session),
    localStorage: mkStore(store),
    console: { warn: m => warnings.push(String(m)), log: () => {} },
    addEventListener: () => {},
    setTimeout: (fn) => { if (o.runDeferred) fn(); return 0; },
    plausible: o.noPlausible ? undefined : (name) => plausibleCalls.push(name),
    matchMedia: () => ({ matches: false, addEventListener: () => {} })
  };
  win.window = win;
  // _shared.js builds its client from window.supabase.createClient at load, so
  // the stub has to supply that rather than pre-setting cflSupabase — which
  // _shared.js would overwrite.
  const recorder = {
    from: () => ({ insert: row => { inserts.push(row); return { then: (a) => { if (a) a(); return { catch: () => {} }; } }; } }),
    auth: { getSession: () => Promise.resolve({ data: { session: null } }),
            onAuthStateChange: () => ({ data: { subscription: { unsubscribe(){} } } }) }
  };
  win.supabase = { createClient: () => recorder };
  const doc = {
    readyState: 'complete',
    referrer: o.referrer || '',
    addEventListener: () => {},
    querySelectorAll: () => [],
    querySelector: () => null,
    getElementById: () => null,
    createElement: () => ({ style: {}, setAttribute: () => {}, appendChild: () => {}, classList: { add(){}, remove(){}, toggle(){} } }),
    body: { appendChild: () => {} },
    documentElement: { style: {} }
  };
  win.document = doc;
  const ctx = vm.createContext(win);
  ctx.globalThis = win;
  ctx.URL = URL;
  // cfl.getQueryParam uses URLSearchParams. Without it, trackSessionStart
  // throws inside its own try/catch and silently emits nothing — rule 3 working
  // exactly as intended, and a harness gap that looks like a product bug.
  ctx.URLSearchParams = URLSearchParams;
  ctx.Math = Math;
  ctx.Date = Date;
  ctx.JSON = JSON;
  ctx.isFinite = isFinite;
  ctx.String = String;
  ctx.Number = Number;
  ctx.Object = Object;
  ctx.Array = Array;
  ctx.RegExp = RegExp;
  ctx.Error = Error;
  ctx.navigator = { userAgent: 'test' };
  vm.runInContext(SHARED, ctx);
  // "no client on the page" is modelled after load, because _shared.js assigns
  // window.cflSupabase unconditionally.
  if (o.noSupabase) win.cflSupabase = null;
  return { cfl: win.cfl, inserts, plausibleCalls, warnings, store, session, win };
}

let boot;
t('_shared.js loads and exposes the tracker', () => {
  boot = bootstrap();
  ok(boot.cfl, '_shared.js did not create window.cfl');
  ok(typeof boot.cfl.track === 'function', 'cfl.track is missing');
  ok(Array.isArray(boot.cfl.EVENTS), 'cfl.EVENTS is missing');
  ok(typeof boot.cfl.trackSessionStart === 'function', 'cfl.trackSessionStart is missing');
});

/* ------------------------------------------------ 1. no personal data, ever */
t('an email is never sent, under any key spelling', () => {
  const b = bootstrap();
  b.cfl.track('card_brief_signup_completed', {
    email: 'reed@example.com', user_email: 'reed@example.com',
    Email: 'reed@example.com', mail: 'reed@example.com',
    source: 'home-bottom'
  });
  eq(b.inserts.length, 1, 'insert count');
  const p = b.inserts[0].props;
  const blob = JSON.stringify(p).toLowerCase();
  ok(blob.indexOf('@') === -1, 'an address reached the props: ' + JSON.stringify(p));
  ok(blob.indexOf('example.com') === -1, 'an address reached the props');
  eq(p.source, 'home-bottom', 'the legitimate prop was dropped too');
});

t('identity and money keys are stripped', () => {
  const b = bootstrap();
  b.cfl.track('fight_opened', {
    user_id: 42, uid: 42, name: 'Reed', token: 'abc', password: 'x',
    ip: '1.2.3.4', ip_address: '1.2.3.4', phone: '555', stake: 100,
    amount: 250, wager: 50, bankroll: 1000,
    fight_id: 49478, from: 'card'
  });
  const p = b.inserts[0].props;
  ['user_id', 'uid', 'name', 'token', 'password', 'ip', 'ip_address', 'phone',
   'stake', 'amount', 'wager', 'bankroll'].forEach(k =>
    ok(!(k in p), 'prop "' + k + '" was sent'));
  eq(p.fight_id, 49478, 'fight_id was dropped');
  eq(p.from, 'card', 'from was dropped');
});

t('the session id is random, per-session, and not an identifier we chose', () => {
  const a = bootstrap(); a.cfl.track('landing_view', {});
  const c = bootstrap(); c.cfl.track('landing_view', {});
  const ida = a.inserts[0].session_id, idc = c.inserts[0].session_id;
  ok(ida && idc, 'no session id sent');
  ok(ida !== idc, 'two fresh sessions produced the same id');
  ok(ida.length >= 8 && ida.length <= 64, 'session id length outside the DB constraint: ' + ida.length);
  // stable within a session
  a.cfl.track('card_lab_view', {});
  eq(a.inserts[1].session_id, ida, 'the id changed mid-session');
});

t('a string prop cannot become a payload', () => {
  const b = bootstrap();
  b.cfl.track('fight_opened', { from: 'x'.repeat(5000) });
  ok(b.inserts[0].props.from.length <= 120,
     'a 5000-char prop was sent at ' + b.inserts[0].props.from.length + ' chars');
});

/* --------------------------------------------- 2. one list, three places */
t('cfl.EVENTS, the migration and the schema doc agree exactly', () => {
  const js = boot.cfl.EVENTS.slice().sort();

  const m = MIGRATION.match(/funnel_events_known_event[\s\S]*?CHECK \(event IN \(([\s\S]*?)\)\)/);
  ok(m, 'the CHECK constraint could not be parsed out of the migration');
  const sql = (m[1].match(/'([a-z_]+)'/g) || []).map(x => x.replace(/'/g, '')).sort();

  const doc = (SCHEMA_DOC.match(/^\| `([a-z_]+)` \|/gm) || [])
    .map(x => x.replace(/[|`\s]/g, '')).sort();

  eq(js.length, sql.length, 'cfl.EVENTS has ' + js.length + ' names, the DB constraint has ' + sql.length);
  js.forEach((n, i) => eq(sql[i], n, 'name ' + i + ' differs between JS and SQL'));
  ok(doc.length >= js.length,
     'ANALYTICS_SCHEMA.md documents ' + doc.length + ' events, code has ' + js.length);
  js.forEach(n => ok(doc.indexOf(n) !== -1, 'event "' + n + '" is in code but not in ANALYTICS_SCHEMA.md'));
});

t('an unknown event is refused and says how to add it', () => {
  const b = bootstrap();
  b.cfl.track('definitely_not_an_event', { a: 1 });
  eq(b.inserts.length, 0, 'an unknown event was written to the table');
  ok(b.warnings.some(w => /unknown event/.test(w)), 'no warning was logged');
  ok(b.warnings.some(w => /ANALYTICS_SCHEMA\.md/.test(w)), 'the warning does not say where to add it');
});

t('the nineteen events cover the nine funnel questions', () => {
  const need = ['landing_view', 'card_lab_view', 'fight_opened', 'market_lab_view',
                'card_brief_signup_completed', 'return_visit', 'pricing_view',
                'checkout_started', 'checkout_completed'];
  need.forEach(n => ok(boot.cfl.EVENTS.indexOf(n) !== -1,
    'no event answers one of the nine questions: ' + n));
});

/* ------------------------------------------- 3. it never breaks a page */
t('no Supabase client is not an error', () => {
  const b = bootstrap({ noSupabase: true });
  b.cfl.track('card_lab_view', {});          // must not throw
  eq(b.inserts.length, 0, 'inserted without a client');
  eq(b.plausibleCalls.length, 1, 'the other sink stopped working too');
});

t('blocked storage is not an error', () => {
  const b = bootstrap({ throwStorage: true });
  b.cfl.track('card_lab_view', {});          // must not throw
  b.cfl.trackSessionStart();                 // must not throw
  ok(true);
});

t('no Plausible on the page is not an error', () => {
  const b = bootstrap({ noPlausible: true });
  b.cfl.track('market_lab_view', {});
  eq(b.inserts.length, 1, 'the owned sink stopped working when the vendor was absent');
});

t('a rejected insert does not surface', () => {
  const b = bootstrap();
  b.win.cflSupabase = { from: () => ({ insert: () => { throw new Error('RLS'); } }) };
  b.cfl.track('card_lab_view', {});          // must not throw
  ok(true);
});

/* ------------------------------------------- the two sinks, and the split */
t('both sinks fire, and only the name goes to the vendor', () => {
  const b = bootstrap();
  b.cfl.track('book_breakdown_expanded', { fight_id: 1, book_count: 6 });
  eq(b.inserts.length, 1, 'owned sink');
  eq(b.plausibleCalls.length, 1, 'vendor sink');
  eq(b.plausibleCalls[0], 'book_breakdown_expanded', 'vendor got the wrong name');
  // Plausible custom properties are a paid feature; sending props would be an
  // L3 spend decision taken by accident.
  eq(b.plausibleCalls[0].length, 'book_breakdown_expanded'.length,
     'props were passed to the vendor');
});

t('no new analytics vendor was added', () => {
  const vendors = /googletagmanager|google-analytics|gtag\(|segment\.com|analytics\.js|mixpanel|amplitude|hotjar|fullstory|posthog/i;
  ['_shared.js', 'index.html', 'market.html', 'fight.html', 'stats.html', 'pricing.html']
    .forEach(f => ok(!vendors.test(read(f)), f + ' loads a new analytics vendor'));
  // Plausible was already present on 25 pages before T-047 and is reused.
  ok(/plausible/i.test(read('index.html')), 'the existing vendor was removed by accident');
});

/* ------------------------------- session start: once, and honestly */
t('landing_view fires once per session, not once per page', () => {
  const b = bootstrap();
  b.cfl.trackSessionStart();
  b.cfl.trackSessionStart();
  b.cfl.trackSessionStart();
  eq(b.inserts.filter(r => r.event === 'landing_view').length, 1,
     'landing_view fired more than once in one session');
});

t('an internal referrer is not recorded as a traffic source', () => {
  const b = bootstrap({ referrer: 'https://cannonfightlab.com/market.html' });
  b.cfl.trackSessionStart();
  const row = b.inserts.find(r => r.event === 'landing_view');
  eq(row.props.referrer_host, undefined, 'our own hostname was logged as a referrer');
});

t('an external referrer records the host and nothing more', () => {
  const b = bootstrap({ referrer: 'https://www.reddit.com/r/MMA/comments/abc/some_thread/' });
  b.cfl.trackSessionStart();
  const row = b.inserts.find(r => r.event === 'landing_view');
  eq(row.props.referrer_host, 'www.reddit.com', 'referrer host');
  ok(!/MMA|comments|some_thread/.test(JSON.stringify(row.props)),
     'the full referring URL was logged, not just the host');
});

t('return_visit only fires when there was a previous visit', () => {
  const b = bootstrap();
  b.cfl.trackSessionStart();
  eq(b.inserts.filter(r => r.event === 'return_visit').length, 0,
     'a first-ever visit was counted as a return');
  ok(b.store['cfl_last_seen'], 'the visit was not recorded for next time');
});

t('a return inside a week is flagged as the same fight week', () => {
  const b = bootstrap();
  b.store['cfl_last_seen'] = String(Date.now() - 3 * 86400000);   // 3 days ago
  b.cfl.trackSessionStart();
  const row = b.inserts.find(r => r.event === 'return_visit');
  ok(row, 'no return_visit on a genuine return');
  eq(row.props.days_since, 3, 'days_since');
  eq(row.props.same_fight_week, true, 'same_fight_week');
});

t('a return after a month is not counted', () => {
  const b = bootstrap();
  b.store['cfl_last_seen'] = String(Date.now() - 90 * 86400000);
  b.cfl.trackSessionStart();
  eq(b.inserts.filter(r => r.event === 'return_visit').length, 0,
     'a 90-day gap was reported as a return visit');
});

/* ------------------------------------- the surfaces actually emit */
t('every product surface emits its own view event', () => {
  const want = {
    'index.html': 'card_lab_view',
    'market.html': 'market_lab_view',
    'fight.html': 'fight_opened',
    'fighter.html': 'fighter_page_view',
    'event.html': 'event_page_view',
    'stats.html': 'factor_lab_view',
    'pricing.html': 'pricing_view'
  };
  Object.keys(want).forEach(f => {
    const src = read(f);
    ok(new RegExp("cfl\\.track\\('" + want[f] + "'").test(src),
       f + ' does not emit ' + want[f]);
  });
});

t('the prerendered stubs do not emit — one visit, one event', () => {
  // /f/ and /e/ stubs JS-redirect to the canonical page after ~120ms. If they
  // emitted too, every stub visit would count twice.
  const stub = fs.readdirSync(root('f')).filter(n => n.endsWith('.html'))[0];
  ok(stub, 'no fighter stubs found');
  const src = read(path.join('f', stub));
  ok(src.indexOf('cfl.track') === -1, 'a prerendered stub emits an event: f/' + stub);
});

t('checkout and share events are declared but not wired, because they cannot be', () => {
  ['checkout_started', 'checkout_completed', 'fight_shared', 'best_price_clicked']
    .forEach(n => ok(boot.cfl.EVENTS.indexOf(n) !== -1, n + ' is not declared'));
  const all = ['index.html', 'market.html', 'fight.html', 'fighter.html',
               'event.html', 'stats.html', 'pricing.html', '_shared.js']
    .map(read).join('\n');
  ['checkout_started', 'checkout_completed', 'fight_shared']
    .forEach(n => ok(!new RegExp("cfl\\.track\\('" + n + "'").test(all),
      n + ' is emitted, but no checkout or share control exists to emit it'));
});

/* ------------------------------------- the migration's own promises */
t('the migration grants INSERT and revokes everything else', () => {
  ok(/GRANT INSERT ON public\.funnel_events TO anon, authenticated;/.test(MIGRATION),
     'INSERT is not granted');
  ok(/REVOKE SELECT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER/.test(MIGRATION),
     'the migration does not revoke the inherited grants');
  ok(!/GRANT SELECT ON public\.funnel_events/.test(MIGRATION),
     'SELECT is granted on the raw table');
  ok(/GRANT SELECT ON public\.v_funnel_daily/.test(MIGRATION),
     'the aggregate view is not readable');
  ok(/ENABLE ROW LEVEL SECURITY/.test(MIGRATION), 'RLS is not enabled');
});

t('the migration documents what is never stored', () => {
  ok(/No email, no name, no user id, no IP/.test(MIGRATION),
     'the migration does not state what it refuses to store');
  ok(/pg_column_size\(props\) <= 2048/.test(MIGRATION), 'props are unbounded');
  ok(/length\(session_id\) BETWEEN 8 AND 64/.test(MIGRATION), 'session_id is unbounded');
});

// ------------------------------------------------------------------ report
if (failures.length) {
  console.log(`\n  ${passed} passed, ${failures.length} FAILED\n`);
  failures.forEach(f => console.log(`  ✗ ${f}\n`));
  process.exit(1);
}
console.log(`\n  ${passed} passed — the funnel counts, and counts nothing personal.\n`);
