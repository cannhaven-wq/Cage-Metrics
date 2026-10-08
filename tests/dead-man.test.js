// =============================================================================
// dead-man.test.js — the watchdog's own tripwire
// =============================================================================
// PLAIN ENGLISH: this proves the thing that shouts when the pre-fight record is
// missing actually shouts, including on the two real failures that already
// happened and were only noticed weeks later by a person.
//
// A watchdog is the one piece of code whose bugs are invisible by construction:
// it is supposed to be quiet, and a broken one is quiet too. So the cases that
// matter most here are the ones that must NOT be quiet.
//
// No dependencies — the Node job in tests.yml installs none. The script under
// test reads the database only inside main(); its pure half is exported.
// =============================================================================

'use strict';

const C = require('../build/check-pre-fight-coverage.js');

let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log(`  ok   ${name}`); }
  else { fail++; console.log(`  FAIL ${name}${extra ? `\n       ${extra}` : ''}`); }
}
function group(name) { console.log(`\n${name}:`); }

const card = (over = {}) => ({
  id: 4550,
  name: 'UFC Fight Night: Rosas Jr. vs. Barcelos',
  event_date: '2026-09-26',
  fights: 13,
  counts: { predictions: 0, pre_fight_snapshots: 0 },
  ...over,
});
const find = (checks, writer) => checks.find(c => c.writer === writer);

// ---------------------------------------------------------------------------
group('deadlines are instants derived from the card date');

ok('pre-fight record is due at the date boundary itself',
  C.deadlineFor('2026-09-26', 0) === '2026-09-26T00:00:00.000Z',
  C.deadlineFor('2026-09-26', 0));

ok('model picks are due 3h earlier, i.e. Friday 21:00 UTC for a Saturday card',
  C.deadlineFor('2026-09-26', 3) === '2026-09-25T21:00:00.000Z',
  C.deadlineFor('2026-09-26', 3));

ok('a month boundary does not wrap wrongly',
  C.deadlineFor('2026-10-01', 3) === '2026-09-30T21:00:00.000Z',
  C.deadlineFor('2026-10-01', 3));

ok('an unparseable date throws rather than producing a silent NaN deadline',
  (() => { try { C.deadlineFor('not-a-date', 0); return false; } catch { return true; } })());

// ---------------------------------------------------------------------------
group('THE SEPTEMBER 26 CASE — 13 fights, 0 snapshots, must breach');

{
  // 2026-09-26 06:00 UTC: both deadlines passed, the card has not happened yet,
  // the record is empty. This is the situation that cost that card permanently.
  const checks = C.assess([card()], '2026-09-26T06:00:00Z');
  const snap = find(checks, 'pre_fight_snapshots');
  const pred = find(checks, 'predictions');

  ok('the pre-fight record is reported dark', snap && snap.status === 'dark', snap && snap.status);
  ok('and it is a breach', snap && snap.breach === true);
  ok('the model picks are reported dark too', pred && pred.status === 'dark');
  ok('the message names the card, the count and the deadline',
    /Rosas Jr\./.test(C.describe(snap)) && /0 rows for 13 fights/.test(C.describe(snap))
      && /2026-09-26 00:00:00Z/.test(C.describe(snap)),
    C.describe(snap));
  ok('the message names who was supposed to write it',
    /snapshot\.yml/.test(C.describe(snap)), C.describe(snap));
  ok('the message says the loss is permanent',
    /cannot be filled in afterwards/.test(C.describe(snap)), C.describe(snap));
}

// ---------------------------------------------------------------------------
group('before the deadline, silence');

{
  // 2026-09-25 12:00 UTC: neither deadline has passed. An empty record here is
  // normal — the writers have not run yet.
  const checks = C.assess([card()], '2026-09-25T12:00:00Z');
  ok('nothing breaches', checks.every(c => !c.breach),
    JSON.stringify(checks.filter(c => c.breach)));
  ok('both read as pending', checks.every(c => c.status === 'pending'));
}

{
  // One minute AFTER the model-picks deadline but before the snapshot one.
  const checks = C.assess([card()], '2026-09-25T21:01:00Z');
  ok('the model-picks check turns dark the minute its own deadline passes',
    find(checks, 'predictions').status === 'dark');
  ok('and the pre-fight record is still pending, on its own clock',
    find(checks, 'pre_fight_snapshots').status === 'pending');
}

{
  // One minute BEFORE the model-picks deadline.
  const checks = C.assess([card()], '2026-09-25T20:59:00Z');
  ok('one minute before its deadline the model-picks check is still quiet',
    find(checks, 'predictions').status === 'pending');
}

// ---------------------------------------------------------------------------
group('a delivered-late run reaches the same verdict as an on-time one');

{
  // The point of absolute deadlines: GitHub delivered odds.yml at :43, :30,
  // :35 and :35 in one day. A watchdog keyed to the wall clock modulo an
  // interval would miss its window; this one cannot.
  const at = t => find(C.assess([card()], t), 'pre_fight_snapshots').status;
  ok('00:05, 03:47 and 11:12 on the day all agree',
    at('2026-09-26T00:05:00Z') === 'dark'
      && at('2026-09-26T03:47:00Z') === 'dark'
      && at('2026-09-26T11:12:00Z') === 'dark');
}

// ---------------------------------------------------------------------------
group('partial coverage does not cry wolf');

{
  // 14 of 15 is what a healthy card looks like: one bout with no usable
  // history produces no verdict. If this shouted, every card would shout.
  const checks = C.assess(
    [card({ fights: 15, counts: { predictions: 14, pre_fight_snapshots: 14 } })],
    '2026-09-26T06:00:00Z');
  ok('14 of 15 is partial, not a breach',
    checks.every(c => c.status === 'partial' && !c.breach),
    JSON.stringify(checks.map(c => c.status)));
  ok('the partial message says it is within normal range',
    /within normal range/.test(C.describe(find(checks, 'predictions'))));
}

{
  // Under half the card is a different shape: a run that died part-way.
  const checks = C.assess(
    [card({ fights: 15, counts: { predictions: 5, pre_fight_snapshots: 5 } })],
    '2026-09-26T06:00:00Z');
  ok('5 of 15 is thin, and breaches',
    checks.every(c => c.status === 'thin' && c.breach),
    JSON.stringify(checks.map(c => c.status)));
  ok('the thin message says a run stopped part-way',
    /stopped part-way/.test(C.describe(find(checks, 'predictions'))));
}

{
  const checks = C.assess(
    [card({ fights: 12, counts: { predictions: 12, pre_fight_snapshots: 12 } })],
    '2026-09-26T06:00:00Z');
  ok('a full card is covered and quiet',
    checks.every(c => c.status === 'covered' && !c.breach));
}

// ---------------------------------------------------------------------------
group('what it deliberately ignores');

{
  const checks = C.assess([card({ fights: 0 })], '2026-09-26T06:00:00Z');
  ok('a card with no bouts booked yet produces no checks at all',
    checks.length === 0, JSON.stringify(checks));
}

{
  // The bell has rung. pre_fight_snapshots is append-only by trigger, so there
  // is nothing left to do; repeating the alarm daily forever is how an alarm
  // gets filtered to a folder.
  const checks = C.assess([card()], '2026-09-27T06:00:00Z');
  ok('a card already in the past raises nothing',
    checks.length === 0, JSON.stringify(checks));
}

{
  const checks = C.assess([card()], '2026-09-26T23:59:00Z');
  ok('a card dated today still raises, right up to the end of the day',
    checks.length === 2 && checks.every(c => c.breach));
}

// ---------------------------------------------------------------------------
group('the whole slate, in the shape the live database is in today');

{
  // Real counts, read from production on 2026-10-05.
  const slate = [
    { id: 4713, name: 'UFC Fight Night: Allen vs. Duncan', event_date: '2026-10-10',
      fights: 12, counts: { predictions: 12, pre_fight_snapshots: 0 } },
    { id: 4368, name: 'UFC Fight Night: Buckley vs. Malott', event_date: '2026-10-17',
      fights: 13, counts: { predictions: 0, pre_fight_snapshots: 0 } },
  ];
  const checks = C.assess(slate, '2026-10-05T14:00:00Z');
  ok('five days out, nothing is due and nothing shouts',
    checks.length === 4 && checks.every(c => c.status === 'pending'),
    JSON.stringify(checks.map(c => [c.event_id, c.writer, c.status])));

  // Wind forward to the morning of the nearer card with the snapshot still dark.
  const later = C.assess(slate, '2026-10-10T06:00:00Z');
  ok('on the day, the written picks are covered and the empty record breaches',
    later.filter(c => c.event_id === 4713)
      .every(c => c.writer === 'predictions' ? c.status === 'covered' : c.status === 'dark'),
    JSON.stringify(later.filter(c => c.event_id === 4713).map(c => [c.writer, c.status])));
  ok('and the far card is untouched by the near one',
    later.filter(c => c.event_id === 4368).every(c => c.status === 'pending'));
}

// ---------------------------------------------------------------------------
group('one open issue per writer per card, never per run');

{
  const a = C.markerFor({ writer: 'pre_fight_snapshots', event_id: 4550 });
  const b = C.markerFor({ writer: 'predictions', event_id: 4550 });
  const c = C.markerFor({ writer: 'pre_fight_snapshots', event_id: 4551 });
  ok('the marker keys on writer and card, and nothing else',
    a === '<!-- cfl-deadman:pre_fight_snapshots:4550 -->', a);
  ok('two writers on one card get different markers', a !== b);
  ok('one writer on two cards gets different markers', a !== c);
  ok('the marker carries no timestamp, so three runs a day reuse one issue',
    !/\d{4}-\d{2}-\d{2}T/.test(a) && !/\d{10}/.test(a));
}

// ---------------------------------------------------------------------------
group('both writers are actually wired in');

ok('there are exactly two writers', C.WRITERS.length === 2);
ok('one of them is the append-only pre-fight record',
  C.WRITERS.some(w => w.key === 'pre_fight_snapshots'));
ok('the other is the model picks the Railway cron writes',
  C.WRITERS.some(w => w.key === 'predictions'));
ok('every writer names who writes it, so the alert is actionable',
  C.WRITERS.every(w => w.writer && w.writer.length > 10));

// ---------------------------------------------------------------------------
group('a writer that cannot reach a card is not a writer that failed');

{
  // D-021: the owner chose to accept the Friday-only coverage gap rather than
  // fix it, because `predictions` has no public consumer. Measured over the
  // real schedule since 2024-01-01, that is 3 cards in 128 — 125 were
  // Saturdays. The decision makes THIS code mandatory: without it the check
  // would report every midweek card `dark` forever, with nothing anybody could
  // do, and an alarm nobody can act on is one people learn to skip. That would
  // cost the Saturday cards, which are the 97.7% the whole thing is for.
  const mid = over => ({
    id: 9001, name: 'UFC Fight Night: Midweek Special', event_date: '2026-10-14', // Wednesday
    fights: 11, counts: { predictions: 0, pre_fight_snapshots: 0 }, ...over,
  });
  const checks = C.assess([mid()], '2026-10-14T06:00:00Z');
  const pred = find(checks, 'predictions');
  const snap = find(checks, 'pre_fight_snapshots');

  ok('a midweek card reports the model picks out of scope, not dark',
    pred.status === 'out_of_schedule', pred.status);
  ok('and that is not a breach', pred.breach === false);
  ok('the message names the weekday, so the reason is checkable',
    /is a Wednesday/.test(C.describe(pred)), C.describe(pred));
  ok('the message says there is nothing to fix, so nobody goes looking',
    /nothing to fix/.test(C.describe(pred)));
  ok('the message cites the decision rather than asserting it',
    /D-021/.test(C.describe(pred)));

  // THE PART THAT MATTERS MOST. Narrowing one writer must not quiet the other:
  // pre_fight_snapshots is the append-only record the hard rule is about, and
  // snapshot.yml runs daily, so a midweek card is fully in its scope.
  ok('the PRE-FIGHT RECORD still goes dark on the same midweek card',
    snap.status === 'dark', snap.status);
  ok('and still breaches',
    snap.breach === true);
}

{
  // The narrowing must not swallow a Saturday, which is 97.7% of the schedule.
  const sat = {
    id: 4550, name: 'UFC Fight Night: Rosas Jr. vs. Barcelos', event_date: '2026-09-26',
    fights: 13, counts: { predictions: 0, pre_fight_snapshots: 0 },
  };
  const checks = C.assess([sat], '2026-09-26T06:00:00Z');
  ok('a Saturday card still breaches on BOTH writers',
    checks.length === 2 && checks.every(c => c.breach && c.status === 'dark'),
    JSON.stringify(checks.map(c => [c.writer, c.status])));
  ok('and neither is reported out of scope',
    checks.every(c => c.status !== 'out_of_schedule'));
}

{
  // Every weekday, so the scope is exactly Saturday and not "most days".
  // 2026-10-11 is a Sunday, so +0..+6 walks one full week.
  const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  const reachable = [];
  for (let i = 0; i < 7; i++) {
    const date = new Date(Date.parse('2026-10-11T00:00:00Z') + i * 86400000)
      .toISOString().slice(0, 10);
    const checks = C.assess(
      [{ id: 100 + i, name: `card ${DAYS[i]}`, event_date: date, fights: 10,
         counts: { predictions: 0, pre_fight_snapshots: 0 } }],
      `${date}T06:00:00Z`);
    const p = find(checks, 'predictions');
    ok(`${DAYS[i]}: the reported weekday matches the date`, p.weekday === DAYS[i],
      `${date} -> ${p.weekday}`);
    if (p.status !== 'out_of_schedule') reachable.push(DAYS[i]);
    // Whatever the weekday, the append-only record is always in scope.
    ok(`${DAYS[i]}: the pre-fight record is in scope`,
      find(checks, 'pre_fight_snapshots').status === 'dark');
  }
  ok('Saturday is the only weekday the Friday cron reaches',
    reachable.length === 1 && reachable[0] === 'Saturday', JSON.stringify(reachable));
}

ok('the scope lives on the writer, not scattered through assess()',
  C.WRITERS.find(w => w.key === 'predictions').reachableWeekdays.join() === '6');
ok('the pre-fight record declares NO weekday scope — snapshot.yml is daily',
  C.WRITERS.find(w => w.key === 'pre_fight_snapshots').reachableWeekdays === null);

// ---------------------------------------------------------------------------
group('the workflow can actually check out the repo');

{
  // An explicit `permissions:` block sets every scope it does NOT name to
  // `none`. So a workflow that pins permissions and then runs
  // actions/checkout MUST name `contents`, or the job dies 403 on its first
  // step before any of the logic above gets a chance to run.
  //
  // dead-man.yml shipped missing it, and nothing caught it: workflow_dispatch
  // needs the workflow present on the default branch, so the file had never
  // been executed. A reviewer found it by reading. This is that reading,
  // written down.
  const fs = require('fs');
  const path = require('path');
  const DIR = path.join(__dirname, '..', '.github', 'workflows');

  // Top-level `permissions:` mapping only — enough for this check, and it
  // deliberately does not try to be a YAML parser.
  function topLevelPermissions(src) {
    const lines = src.split('\n');
    const i = lines.findIndex(l => /^permissions:\s*$/.test(l));
    if (i === -1) {
      // Either absent (repository default applies — not this defect) or the
      // inline `permissions: read-all` form, which names everything.
      return /^permissions:\s*\S/m.test(src) ? 'inline' : null;
    }
    const scopes = {};
    for (let j = i + 1; j < lines.length; j++) {
      const m = lines[j].match(/^\s+([a-z-]+):\s*(\S+)\s*$/);
      if (!m) {
        if (/^\S/.test(lines[j]) && lines[j].trim() !== '') break;
        continue;
      }
      scopes[m[1]] = m[2];
    }
    return scopes;
  }

  const files = fs.readdirSync(DIR).filter(f => f.endsWith('.yml'));
  ok('there are workflow files to check', files.length > 0);

  const offenders = [];
  for (const f of files) {
    const src = fs.readFileSync(path.join(DIR, f), 'utf8');
    if (!src.includes('actions/checkout')) continue;
    const perms = topLevelPermissions(src);
    if (perms === null || perms === 'inline') continue;   // default or read-all
    // A job-level permissions block can supply it instead; if any job names
    // contents, that is this file's answer and the top level is not the gate.
    if (!('contents' in perms) && !/^\s+contents:\s/m.test(src)) offenders.push(f);
  }
  ok('no workflow pins permissions, runs checkout, and forgets `contents`',
    offenders.length === 0,
    offenders.length ? `missing contents scope: ${offenders.join(', ')}` : '');

  const dm = fs.readFileSync(path.join(DIR, 'dead-man.yml'), 'utf8');
  const perms = topLevelPermissions(dm);
  ok('dead-man.yml grants contents: read', perms.contents === 'read', JSON.stringify(perms));
  ok('dead-man.yml never grants contents: write — it commits nothing, ever',
    perms.contents !== 'write');
  ok('dead-man.yml grants issues: write, so it can speak',
    perms.issues === 'write', JSON.stringify(perms));
  ok('dead-man.yml grants actions: read, for the cadence self-check',
    perms.actions === 'read', JSON.stringify(perms));
  ok('dead-man.yml really does run a checkout, so the scope is load-bearing',
    dm.includes('actions/checkout'));
}

// ---------------------------------------------------------------------------
console.log(`\n${pass} passed, ${fail} failed`);
if (fail) {
  console.log('The watchdog is the one thing whose bugs look like silence. Fix this.');
  process.exit(1);
}
console.log('the dead man\'s handle lets go when it should.');
