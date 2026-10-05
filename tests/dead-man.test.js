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
console.log(`\n${pass} passed, ${fail} failed`);
if (fail) {
  console.log('The watchdog is the one thing whose bugs look like silence. Fix this.');
  process.exit(1);
}
console.log('the dead man\'s handle lets go when it should.');
