// =============================================================================
// dead-man-observer.test.js — T-076, the dead man's half of the outside observer
// =============================================================================
// PLAIN ENGLISH: every run of the dead man signs in to the database so a
// scheduler that is not GitHub's can notice when it stops. This proves the
// sign-in is honest (only real runs count, the server's clock is used), that it
// can never change whether the build goes red, and that the step summary never
// claims the observer is watching when it is not installed, not running, or has
// no way to speak.
//
// The SQL half is tested against a throwaway Postgres in
// tests/test_t076_observer_sql.py. No network here: fetch is injected.
// =============================================================================

'use strict';

const fs = require('fs');
const path = require('path');
const C = require('../build/check-pre-fight-coverage.js');

let pass = 0, fail = 0;
const pending = [];
function ok(name, cond, extra) {
  if (cond) { pass++; console.log(`  ok   ${name}`); }
  else { fail++; console.log(`  FAIL ${name}${extra ? `\n       ${extra}` : ''}`); }
}
function group(name) { console.log(`\n${name}:`); }

const ROOT = path.join(__dirname, '..');
const read = f => fs.readFileSync(path.join(ROOT, f), 'utf8');
const SQL = read('research/ops/proposed_2026-10-21_t076_dead_man_observer.sql');
const SCRIPT = read('build/check-pre-fight-coverage.js');

const GH = { GITHUB_EVENT_NAME: 'schedule', GITHUB_REPOSITORY: 'cannhaven-wq/Cage-Metrics',
             GITHUB_RUN_ID: '42', GITHUB_SERVER_URL: 'https://github.com' };

// ---------------------------------------------------------------------------
group('the heartbeat row');

const row = C.heartbeatRow('ok', GH);
ok('a scheduled run writes a dead-man row tagged schedule',
  row && row.source === 'dead-man' && row.trigger === 'schedule' && row.outcome === 'ok');
ok('it links its own run log', row.run_url === 'https://github.com/cannhaven-wq/Cage-Metrics/actions/runs/42');
ok('it never sends its own timestamp — the database stamps ran_at', !('ran_at' in row));
ok('a manual run is tagged as manual, so it cannot stand in for the schedule',
  C.heartbeatRow('ok', { ...GH, GITHUB_EVENT_NAME: 'workflow_dispatch' }).trigger === 'workflow_dispatch');
ok('a local run is tagged local', C.heartbeatRow('ok', {}).trigger === 'local');
ok('an unknown event name is tagged local, never schedule',
  C.heartbeatRow('ok', { ...GH, GITHUB_EVENT_NAME: 'push' }).trigger === 'local');
ok('a pretend-time run (COVERAGE_NOW) writes nothing',
  C.heartbeatRow('ok', { ...GH, COVERAGE_NOW: '2026-09-26T12:00:00Z' }) === null);
ok('DEAD_MAN_HEARTBEAT=off writes nothing', C.heartbeatRow('ok', { ...GH, DEAD_MAN_HEARTBEAT: 'off' }) === null);

// Every value the script can send must pass the table's CHECK constraints.
const checkList = col => {
  const m = SQL.match(new RegExp(`${col}\\s+text not null check \\(${col} in \\(([^)]*)\\)\\)`));
  return m ? [...m[1].matchAll(/'([^']+)'/g)].map(x => x[1]) : [];
};
const outcomes = checkList('outcome'), triggers = checkList('trigger'), sources = checkList('source');
ok('the CHECK lists were found in the migration', outcomes.length && triggers.length && sources.length);
ok('every outcome the script sends is allowed by the table',
  ['ok', 'breach', 'error'].every(o => outcomes.includes(o)));
ok('every trigger the script sends is allowed by the table',
  ['schedule', 'workflow_dispatch', 'local'].every(t => triggers.includes(t)));
ok('the source the script sends is allowed by the table', sources.includes(row.source));
ok('the table the script writes is the table the migration creates',
  SQL.includes(`create table if not exists public.${C.HEARTBEAT_TABLE} (`));

// ---------------------------------------------------------------------------
group('the observer verdict never overstates what is watching');

const NOW = '2026-10-21T12:00:00Z';
const ago = h => new Date(Date.parse(NOW) - h * 3600000).toISOString();

let v = C.observerVerdict(null, NOW, 'HTTP 404 {"code":"PGRST205","message":"Could not find the table"}');
ok('a missing table reads as NOT INSTALLED and names the runbook',
  v.status === 'not_installed' && /NOT INSTALLED/.test(v.line) && /RUNBOOK/.test(v.line));
v = C.observerVerdict(null, NOW, 'HTTP 500 boom');
ok('any other read failure is unreadable, not healthy', v.status === 'unreadable');
v = C.observerVerdict(null, NOW, null);
ok('an installed observer with no pass says it has never run', v.status === 'never_ran');
v = C.observerVerdict({ ran_at: ago(C.OBSERVER_MAX_AGE_HOURS + 0.5), outcome: 'fresh', armed: true }, NOW);
ok('an observer past its window is stale even when armed', v.status === 'stale' && /nothing is watching/.test(v.line));
v = C.observerVerdict({ ran_at: ago(1), outcome: 'fresh', armed: false }, NOW);
ok('a running observer with no token is NOT ARMED', v.status === 'not_armed' && /NOT ARMED/.test(v.line));
v = C.observerVerdict({ ran_at: ago(1), outcome: 'fresh', armed: null }, NOW);
ok('armed must be true, not merely present', v.status === 'not_armed');
v = C.observerVerdict({ ran_at: ago(1), outcome: 'fresh', armed: true }, NOW);
ok('only a recent, armed pass reads as armed', v.status === 'armed');
ok('the observer window covers two missed hourly passes',
  C.OBSERVER_MAX_AGE_HOURS >= 2 && C.OBSERVER_MAX_AGE_HOURS <= 6);
ok('the window matches the hourly schedule in the migration', /cron\.schedule\('cfl-dead-man-liveness', '17 \* \* \* \*'/.test(SQL));

// ---------------------------------------------------------------------------
group('the write is harmless when it fails, and never throws');

const res = (status, body) => ({ ok: status >= 200 && status < 300, status,
  text: async () => typeof body === 'string' ? body : JSON.stringify(body),
  json: async () => body });

pending.push((async () => {
  let seen = null;
  const r1 = await C.writeHeartbeat('k', row, async (url, init) => { seen = { url, init }; return res(201, ''); });
  ok('a 201 is written', r1.status === 'written');
  ok('it POSTs to the heartbeat table with the service key',
    seen.url.endsWith('/rest/v1/watchdog_heartbeats') && seen.init.method === 'POST'
    && seen.init.headers.Authorization === 'Bearer k');
  const r2 = await C.writeHeartbeat('k', row, async () => res(404, { code: 'PGRST205', message: 'Could not find the table' }));
  ok('a missing table is not_installed', r2.status === 'not_installed');
  const r3 = await C.writeHeartbeat('k', row, async () => { throw new Error('ECONNRESET'); });
  ok('a network failure is reported, not thrown', r3.status === 'failed' && /ECONNRESET/.test(r3.message));
  const r4 = await C.writeHeartbeat('k', null, async () => { throw new Error('must not be called'); });
  ok('no row, no request', r4.status === 'skipped');

  const obs = await C.readObserver('k', async () => res(200, [{ ran_at: ago(1), outcome: 'fresh', armed: true }]));
  ok('the observer read returns the latest row', obs.latest && obs.latest.armed === true && obs.error === null);
  const obs2 = await C.readObserver('k', async () => { throw new Error('offline'); });
  ok('a failed observer read returns an error, not a throw', obs2.latest === null && /offline/.test(obs2.error));

  const out = await C.liveness('k', 'ok', {}, async () => { throw new Error('offline'); });
  ok('liveness() survives a dead network', out.heartbeat === 'failed' && out.observer === 'unreadable');
})());

// ---------------------------------------------------------------------------
group('the red tick still means one thing');

const mainBody = SCRIPT.slice(SCRIPT.indexOf('async function main()'), SCRIPT.indexOf('// Exported for tests'));
ok('a breach still exits 1, after the heartbeat',
  /await liveness\(key, 'breach'\);\s*process\.exit\(1\);/.test(mainBody));
ok('liveness() is never allowed to throw out of main',
  /async function liveness[\s\S]*?try \{[\s\S]*?\} catch \(err\) \{/.test(SCRIPT));
ok('no liveness verdict decides the exit code',
  !/observer[^\n]*process\.exit|process\.exit[^\n]*observer/.test(SCRIPT));
ok('a fatal run still exits 1 after checking in as error',
  /await liveness\(key, 'error'\);\s*process\.exit\(1\);/.test(SCRIPT));

// ---------------------------------------------------------------------------
group('the migration keeps the promises the script relies on');

ok('ran_at is stamped by the server clock in a trigger',
  /new\.ran_at := clock_timestamp\(\);/.test(SQL) && /before insert on public\.watchdog_heartbeats/.test(SQL));
ok('only scheduled (and the install seed) heartbeats count toward liveness',
  /h\.trigger in \('schedule', 'migration'\)/.test(SQL));
ok('30 hours, matching the cadence report and pipeline health',
  /interval '30 hours'/.test(SQL)
  && /WORST_ACCEPTABLE_HOURS = 30;/.test(read('.github/scripts/watchdog-cadence.js'))
  && /file: 'dead-man\.yml',[^\n]*maxAgeHours: 30/.test(read('build/check-pipeline-health.js')));
ok('the alert row is inserted before the request is sent',
  SQL.indexOf('insert into public.watchdog_liveness_alerts') < SQL.indexOf('net.http_post('));
ok('one alert per stall: UNIQUE on the heartbeat it is stuck behind',
  /unique \(source, last_heartbeat_at\)/.test(SQL) && /on conflict \(source, last_heartbeat_at\) do nothing/.test(SQL));
ok('the token comes from Vault, never from the file',
  /vault\.decrypted_secrets/.test(SQL) && !/gh[ps]_[A-Za-z0-9]{20,}|github_pat_/.test(SQL));
ok('a missing token is recorded as not_configured, never as sent',
  /set delivery = 'not_configured'/.test(SQL));
ok('both browser roles lose every privilege on both tables and every function', [
  /revoke all on public\.watchdog_heartbeats from public, anon, authenticated;/,
  /revoke all on public\.watchdog_liveness_alerts from public, anon, authenticated;/,
  /revoke all on function public\.dead_man_liveness_alarm\(timestamptz\) from public, anon, authenticated;/,
  /revoke all on function public\.dead_man_liveness\(timestamptz\) from public, anon, authenticated;/,
].every(re => re.test(SQL)));
ok('nothing is granted to a browser role', !/grant[^;]*\bto\s+[^;]*\b(anon|authenticated)\b/i.test(SQL));
ok('marked proposed, not applied', /STATUS: PROPOSED, NOT APPLIED/.test(SQL));
ok('no statement that raises a NOTICE on a first apply', !/drop trigger if exists/i.test(SQL));
ok('the runbook exists and names the one owner step',
  /cfl_github_issue_token/.test(read('research/ops/T076_DEAD_MAN_OBSERVER_RUNBOOK.md')));

Promise.all(pending).then(() => {
  console.log(`\n${pass} passed, ${fail} failed`);
  if (fail) process.exit(1);
  console.log('the outside observer is honest about whether it is watching.');
}).catch(err => { console.error(err); process.exit(1); });
