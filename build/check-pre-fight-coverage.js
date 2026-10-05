// =============================================================================
// check-pre-fight-coverage.js — the dead man's handle on the pre-fight record
// =============================================================================
// PLAIN ENGLISH: before every card, two separate jobs are supposed to write down
// what CFL thinks, ahead of the bell. This asks, out loud, whether they did. If
// a card is close and the record is empty, this is the thing that shouts.
//
// -----------------------------------------------------------------------------
// WHY THIS EXISTS, WITH THE RECEIPT
// -----------------------------------------------------------------------------
// Both writers have failed silently, and both failures were found by a person
// noticing weeks later rather than by anything in this repo:
//
//   predictions           last written 2026-08-03. The Railway cron schedule
//                         had never been set, so the service deployed, built
//                         cleanly, and ran zero times. Five batches in five
//                         months and nothing said a word.
//
//   pre_fight_snapshots   UFC Fight Night: Rosas Jr. vs. Barcelos, 2026-09-26,
//                         13 fights, 0 rows. The guard around the per-fight
//                         loop caught `Exception`, and the thing it needed to
//                         catch was `SystemExit`, which inherits from
//                         BaseException. The table is append-only by trigger,
//                         so that card's pre-fight record is gone permanently.
//                         There is no fixing it after the fact — which is
//                         exactly why the alarm has to come BEFORE the bell.
//
// A green build and an empty table look identical from the outside. That is the
// failure class this closes.
//
// -----------------------------------------------------------------------------
// "I COULD NOT LOOK" IS A FAILURE HERE
// -----------------------------------------------------------------------------
// build/send-alerts.js exits 0 when its key is missing, and is right to: a
// not-configured runner is not a broken market. This script takes the opposite
// line, and the difference is the whole point of a dead man's handle. A
// watchdog that cannot read the database must not report silence as health,
// because "nothing is wrong" and "I never looked" are the two things it exists
// to tell apart. Missing key, failed query, zero events visible — every one of
// those exits non-zero.
//
// -----------------------------------------------------------------------------
// WHY PARTIAL COVERAGE IS NOT AN ALARM
// -----------------------------------------------------------------------------
// Healthy cards come in at 13 or 14 rows against 15 fights: a bout whose
// fighters have no usable history produces no verdict, and the writers skip it
// rather than invent one. If 14-of-15 shouted, every card would shout, and an
// alarm that goes off on every card is an alarm that gets filtered to a folder.
// So the ladder is:
//
//   dark      0 rows past the deadline                  -> BREACH, shout
//   thin      below HALF the fights                     -> BREACH, shout
//             (that is a run that died part-way, not a gap in the data)
//   partial   between half and all                      -> noted, no alarm
//   covered   a row for every fight                     -> quiet
//   pending   deadline has not passed yet               -> quiet
//
// -----------------------------------------------------------------------------
// DEADLINES ARE ABSOLUTE INSTANTS, NOT "DID THE CRON FIRE"
// -----------------------------------------------------------------------------
// Same rule as the odds cadence gate: never reason from the wall clock modulo an
// interval, because GitHub does not deliver schedules when they ask. Each
// writer's deadline is an instant derived from the event date, and every run
// asks only "has that instant passed, and is the record still empty". A run
// delivered at 23:47 instead of 23:00 reaches the same verdict.
//
// -----------------------------------------------------------------------------
// WHAT THIS CANNOT SEE, STATED PLAINLY
// -----------------------------------------------------------------------------
// Its own silence. If GitHub stops delivering this workflow — throttling, or the
// 60-day inactivity disable — then nothing shouts, for the same reason nothing
// shouted before. The workflow prints the gap between its own recent runs so a
// run that DOES land reports the hole, but closing it properly needs an observer
// outside GitHub. Tracked as an owner item, not pretended away here.
//
// -----------------------------------------------------------------------------
// ENV
// -----------------------------------------------------------------------------
//   SUPABASE_SERVICE_ROLE_KEY  (or SUPABASE_SECRET_KEY) — required. `fights`
//       is public, but `predictions` and `pre_fight_snapshots` are not readable
//       by `anon`, and an anon read of them returns zero rows with HTTP 200 and
//       no error — a watchdog reading "0 rows" as "dark" off a permission
//       failure would cry wolf on every healthy card.
//   COVERAGE_LOOKAHEAD_DAYS    how far ahead to look. Default 10.
//   COVERAGE_NOW               ISO instant, for testing. Default: now.
//   GITHUB_STEP_SUMMARY        written to when present.
//   COVERAGE_JSON_OUT          path for the machine-readable result.
// =============================================================================

'use strict';

const fs = require('fs');

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';

// ---------------------------------------------------------------------------
// The two writers. Each deadline is expressed as hours before the event date's
// own 00:00 UTC boundary, so one rule covers a card on any day of the week.
// ---------------------------------------------------------------------------
const WRITERS = [
  {
    key: 'predictions',
    table: 'predictions',
    label: 'Model picks',
    writer: 'cfl-snapshotter (Railway cron, Fridays 18:00 UTC)',
    // Fri 18:00 UTC + 3h grace = Fri 21:00 = 3h before Saturday 00:00 UTC.
    deadlineHoursBeforeDate: 3,
    // A card not on a Saturday is never reached by a Friday-only cron. That is
    // a real gap and this says so rather than hiding it, but it is a different
    // sentence from "the cron is broken".
    note: 'A card that is not on a Saturday is outside this cron entirely.',
  },
  {
    key: 'pre_fight_snapshots',
    table: 'pre_fight_snapshots',
    label: 'Pre-fight record',
    writer: 'snapshot.yml (GitHub Actions, 23:00 UTC night-before + 10:30 UTC day-of)',
    // The night-before run finishes around 23:10 on D-1; the deadline is the
    // date boundary itself, which both gives it 50 minutes of slack and leaves
    // the whole of D for a person to fix it before a US bell.
    deadlineHoursBeforeDate: 0,
    note: 'Append-only by trigger. A card that goes off dark cannot be filled in afterwards.',
  },
];

// Below this share of the card, rows present means a run that died part-way
// rather than fights with no usable data.
const THIN_RATIO = 0.5;

// ---------------------------------------------------------------------------
// Pure core. No network, no clock of its own — `now` is always passed in, the
// same arrangement alerts.js has, so every branch is reachable from a test.
// ---------------------------------------------------------------------------

/** The instant a writer's record must exist by, for a card on `eventDate`. */
function deadlineFor(eventDate, hoursBefore) {
  const midnight = Date.parse(`${eventDate}T00:00:00Z`);
  if (Number.isNaN(midnight)) throw new Error(`unparseable event_date: ${eventDate}`);
  return new Date(midnight - hoursBefore * 3600 * 1000).toISOString();
}

/**
 * One verdict per (writer, event).
 *
 * events: [{ id, name, event_date, fights, counts: { predictions, pre_fight_snapshots } }]
 * now:    ISO instant
 */
function assess(events, now, writers = WRITERS) {
  const nowMs = Date.parse(now);
  if (Number.isNaN(nowMs)) throw new Error(`unparseable now: ${now}`);
  const today = new Date(nowMs).toISOString().slice(0, 10);

  const checks = [];
  for (const ev of events) {
    // A card with no bouts booked has nothing to predict. Not a gap.
    if (!ev.fights) continue;
    // Past the date, nothing can be written any more — append-only on one side
    // and pointless on the other. Shouting about it daily forever teaches
    // people to ignore the alarm.
    if (ev.event_date < today) continue;

    for (const w of writers) {
      const have = Number((ev.counts || {})[w.key] || 0);
      const deadline = deadlineFor(ev.event_date, w.deadlineHoursBeforeDate);
      const due = Date.parse(deadline) <= nowMs;
      const thin = Math.max(1, Math.floor(ev.fights * THIN_RATIO));

      let status;
      if (!due) status = 'pending';
      else if (have === 0) status = 'dark';
      else if (have < thin) status = 'thin';
      else if (have < ev.fights) status = 'partial';
      else status = 'covered';

      checks.push({
        writer: w.key,
        label: w.label,
        writtenBy: w.writer,
        note: w.note,
        event_id: ev.id,
        event_name: ev.name,
        event_date: ev.event_date,
        fights: ev.fights,
        rows: have,
        deadline,
        status,
        breach: status === 'dark' || status === 'thin',
      });
    }
  }

  checks.sort((a, b) =>
    a.event_date.localeCompare(b.event_date) || a.writer.localeCompare(b.writer));
  return checks;
}

/** One line a person can read without opening the database. */
function describe(c) {
  const d = c.deadline.replace('T', ' ').replace('.000Z', 'Z').replace(/\.\d+Z$/, 'Z');
  switch (c.status) {
    case 'dark':
      return `${c.label} is EMPTY for ${c.event_name} (${c.event_date}): `
           + `0 rows for ${c.fights} fights, and the deadline passed at ${d}. `
           + `Written by ${c.writtenBy}. ${c.note}`;
    case 'thin':
      return `${c.label} is INCOMPLETE for ${c.event_name} (${c.event_date}): `
           + `${c.rows} rows for ${c.fights} fights, under half the card, `
           + `deadline ${d}. That shape means a run that stopped part-way. `
           + `Written by ${c.writtenBy}.`;
    case 'partial':
      return `${c.label}: ${c.rows}/${c.fights} for ${c.event_name} `
           + `(${c.event_date}) — short of the full card, within normal range `
           + `for bouts with no usable history.`;
    case 'covered':
      return `${c.label}: ${c.rows}/${c.fights} for ${c.event_name} (${c.event_date}).`;
    default:
      return `${c.label}: not due yet for ${c.event_name} (${c.event_date}) — `
           + `deadline ${d}, ${c.rows} rows so far.`;
  }
}

/** The dedupe marker. One open issue per writer per card, never per run. */
function markerFor(c) {
  return `<!-- cfl-deadman:${c.writer}:${c.event_id} -->`;
}

// ---------------------------------------------------------------------------
// Reads. Plain fetch on purpose: this script installs no dependencies, because
// every dependency is one more way for the watchdog itself to fail to start.
// ---------------------------------------------------------------------------
// PostgREST caps a response at 1000 rows by default and says so only in the
// Content-Range header. A tally built on a truncated list undercounts, and an
// undercount here reads as a dark or thin card — the watchdog would cry wolf
// off its own pagination. So a full page is treated as a read it cannot trust.
const REST_PAGE_CAP = 1000;

async function rest(path, key) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    headers: {
      apikey: key,
      Authorization: `Bearer ${key}`,
      Accept: 'application/json',
    },
  });
  if (!res.ok) {
    throw new Error(`REST ${path} -> HTTP ${res.status} ${await res.text()}`);
  }
  const rows = await res.json();
  if (Array.isArray(rows) && rows.length >= REST_PAGE_CAP) {
    throw new Error(
      `REST ${path} returned ${rows.length} rows, at or above the ${REST_PAGE_CAP} `
      + `page cap. The tally would be built on a truncated list and would read `
      + `healthy cards as dark. Narrow COVERAGE_LOOKAHEAD_DAYS or page this read.`);
  }
  return rows;
}

async function load(key, now, lookaheadDays) {
  const today = new Date(Date.parse(now)).toISOString().slice(0, 10);
  const until = new Date(Date.parse(now) + lookaheadDays * 86400000)
    .toISOString().slice(0, 10);

  const events = await rest(
    `events?select=id,name,event_date&event_date=gte.${today}`
    + `&event_date=lte.${until}&order=event_date.asc`, key);

  // Zero visible cards is not "all clear". Either the schedule genuinely has no
  // card in the next ten days (rare, and worth a human look) or the read is
  // broken. Both are things to go and check, so neither is silent.
  if (!Array.isArray(events) || events.length === 0) {
    throw new Error(
      `no events found between ${today} and ${until}. Either the schedule is `
      + `empty for ten days or this read is broken — a watchdog cannot tell `
      + `those apart, so it refuses to report health.`);
  }

  const ids = events.map(e => e.id);
  const inList = `(${ids.join(',')})`;

  const fights = await rest(`fights?select=id,event_id&event_id=in.${inList}`, key);
  const rows = {};
  for (const w of WRITERS) {
    rows[w.key] = await rest(
      `${w.table}?select=event_id,fight_id&event_id=in.${inList}`, key);
  }

  // DISTINCT fight_id, not row count. `predictions` is keyed
  // (fight_id, snapshot_label), so a second label would double every count and
  // a half-written card would read as covered. What matters is how many FIGHTS
  // have a record, never how many rows exist.
  const tally = (list, idKey) => {
    const seen = {};
    for (const r of list) {
      (seen[r.event_id] || (seen[r.event_id] = new Set())).add(r[idKey]);
    }
    return Object.fromEntries(Object.entries(seen).map(([k, v]) => [k, v.size]));
  };
  const fightCount = tally(fights, 'id');
  const writerCounts = {};
  for (const w of WRITERS) writerCounts[w.key] = tally(rows[w.key], 'fight_id');

  return events.map(e => ({
    id: e.id,
    name: e.name,
    event_date: e.event_date,
    fights: fightCount[e.id] || 0,
    counts: WRITERS.reduce((m, w) => (m[w.key] = writerCounts[w.key][e.id] || 0, m), {}),
  }));
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------
async function main() {
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SECRET_KEY;
  if (!key) {
    // Deliberately a failure. See the header: a watchdog that cannot look must
    // not pass. The two names are both accepted because this repo's workflows
    // and the Railway service each use a different one.
    throw new Error(
      'SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SECRET_KEY) is not set. This check '
      + 'cannot read predictions or pre_fight_snapshots without it, and an anon '
      + 'read of either returns zero rows with HTTP 200 — indistinguishable from '
      + 'a dark card. Failing rather than reporting a clean card.');
  }

  const now = process.env.COVERAGE_NOW || new Date().toISOString();
  const lookahead = Number(process.env.COVERAGE_LOOKAHEAD_DAYS || 10);

  console.log(`[coverage] as of ${now}, looking ${lookahead} days ahead`);

  const events = await load(key, now, lookahead);
  const checks = assess(events, now);
  const breaches = checks.filter(c => c.breach);

  for (const c of checks) {
    const tag = c.breach ? 'BREACH ' : c.status === 'pending' ? '  ...  ' : '   ok  ';
    console.log(`${tag} ${describe(c)}`);
  }

  const out = process.env.COVERAGE_JSON_OUT;
  if (out) {
    fs.writeFileSync(out, JSON.stringify(
      { now, lookahead, checks, breaches: breaches.map(c => ({ ...c, marker: markerFor(c), message: describe(c) })) },
      null, 2));
    console.log(`[coverage] wrote ${out}`);
  }

  const summary = process.env.GITHUB_STEP_SUMMARY;
  if (summary) {
    const lines = ['## Pre-fight record coverage', '', `As of \`${now}\`.`, ''];
    if (breaches.length) {
      lines.push(`### ${breaches.length} breach${breaches.length === 1 ? '' : 'es'}`, '');
      for (const c of breaches) lines.push(`- **${c.status.toUpperCase()}** — ${describe(c)}`);
    } else {
      lines.push('### No breach', '', 'Every card past its deadline has a record.');
    }
    lines.push('', '| card | date | writer | rows | fights | deadline | status |',
                   '|---|---|---|---|---|---|---|');
    for (const c of checks) {
      lines.push(`| ${c.event_name} | ${c.event_date} | ${c.writer} | ${c.rows} | `
               + `${c.fights} | ${c.deadline} | ${c.status} |`);
    }
    fs.appendFileSync(summary, lines.join('\n') + '\n');
  }

  if (breaches.length) {
    console.error(`\n[coverage] ${breaches.length} breach(es) — exiting 1 so this cannot pass quietly.`);
    process.exit(1);
  }
  console.log(`\n[coverage] ${checks.length} checks, no breach.`);
}

// Exported for tests/dead-man.test.js. The pure half is what is worth testing.
module.exports = { deadlineFor, assess, describe, markerFor, WRITERS, THIN_RATIO };

if (require.main === module) {
  main().catch(err => {
    console.error(`[coverage] FATAL: ${err.message}`);
    process.exit(1);
  });
}
