// The pipeline health check says which job stopped, and stays quiet otherwise.
'use strict';
const { assess, WORKFLOWS } = require('../build/check-pipeline-health');

let n = 0, failed = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { failed++; console.error('FAIL', name, '\n  ', e.message); } };
const ok = (c, m) => { if (!c) throw new Error(m); };

const NOW = '2026-10-12T18:00:00Z';
const hoursAgo = h => new Date(+new Date(NOW) - h * 3600e3).toISOString();
const healthyWorkflows = () => Object.fromEntries(WORKFLOWS.map(w =>
  [w.file, { state: 'active', runs: [{ status: 'completed', conclusion: 'success', created_at: hoursAgo(5) }] }]));
const healthy = () => ({
  workflows: healthyWorkflows(),
  lastOddsCapture: hoursAgo(6),
  completedCards: [{ id: 4713, name: 'UFC FN: Allen vs. Duncan', event_date: '2026-10-10', fights: 12, withResult: 12 }],
  upcomingCards: [{ id: 4368, name: 'UFC FN: Buckley vs. Malott', event_date: '2026-10-17' }],
});
const markers = r => r.breaches.map(b => b.marker).join(' ');

t('a healthy system raises nothing', () => {
  const r = assess(healthy(), NOW);
  ok(r.breaches.length === 0, 'unexpected: ' + markers(r));
});

t('the export.yml shape — every scheduled run failing — is caught', () => {
  const f = healthy();
  f.workflows['odds.yml'].runs = [{ status: 'completed', conclusion: 'failure', created_at: hoursAgo(2) },
                                  { status: 'completed', conclusion: 'success', created_at: hoursAgo(8) }];
  ok(/wf:odds\.yml:failing/.test(markers(assess(f, NOW))), 'a failing latest run was not reported');
});

t('a workflow with no success inside its window is stale', () => {
  const f = healthy();
  f.workflows['snapshot.yml'].runs = [{ status: 'completed', conclusion: 'success', created_at: hoursAgo(50) }];
  ok(/wf:snapshot\.yml:stale/.test(markers(assess(f, NOW))), 'stale not reported');
});

t('GitHub disabling a schedule (60-day rule) is caught', () => {
  const f = healthy();
  f.workflows['dead-man.yml'].state = 'disabled_inactivity';
  ok(/wf:dead-man\.yml:disabled/.test(markers(assess(f, NOW))), 'disabled workflow not reported');
});

t('an unreadable workflow is a failure, not health', () => {
  const f = healthy();
  f.workflows['prerender.yml'] = { error: 'HTTP 403' };
  ok(/wf:prerender\.yml:unreadable/.test(markers(assess(f, NOW))), '"could not look" reported as healthy');
});

t('a running (not yet completed) run does not count as a failure', () => {
  const f = healthy();
  f.workflows['odds.yml'].runs.unshift({ status: 'in_progress', conclusion: null, created_at: hoursAgo(0.1) });
  ok(assess(f, NOW).breaches.length === 0, 'an in-progress run raised a breach');
});

t('stale odds are caught; fresh odds are not', () => {
  const f = healthy(); f.lastOddsCapture = hoursAgo(31);
  ok(/data:odds:stale/.test(markers(assess(f, NOW))), 'stale odds not reported');
  f.lastOddsCapture = null;
  ok(/data:odds:none/.test(markers(assess(f, NOW))), 'no odds at all not reported');
});

t('a card without results after the grace window is caught — not before it', () => {
  const f = healthy();
  f.completedCards = [{ id: 1, name: 'Late card', event_date: '2026-10-10', fights: 12, withResult: 2 }];
  ok(/data:results:1/.test(markers(assess(f, NOW))), '60+ h old card with no results not reported');
  f.completedCards = [{ id: 2, name: 'Last night', event_date: '2026-10-11', fights: 12, withResult: 0 }];
  ok(!/data:results:2/.test(markers(assess(f, NOW))), 'a card still inside the grace window raised a breach');
});

t('a partly-resulted card (cancellations, draws) is not an alarm', () => {
  const f = healthy();
  f.completedCards = [{ id: 3, name: 'Mostly in', event_date: '2026-10-03', fights: 15, withResult: 13 }];
  ok(assess(f, NOW).breaches.length === 0, '13/15 raised a breach');
});

t('an empty calendar is caught', () => {
  const f = healthy(); f.upcomingCards = [];
  ok(/data:calendar:empty/.test(markers(assess(f, NOW))), 'empty calendar not reported');
});

t('markers are stable so one issue tracks one problem', () => {
  const f = healthy(); f.lastOddsCapture = hoursAgo(40);
  const a = markers(assess(f, NOW)), b = markers(assess(f, hoursAgo(-3)));
  ok(a === b && /^<!-- cfl-health:/.test(a), 'marker changed between runs');
});

if (failed) { console.error(`\n  ${failed} failed, ${n} passed`); process.exit(1); }
console.log(`\n  ${n} passed — a stopped job is named, and a healthy one is left alone.`);
