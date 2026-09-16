// =============================================================================
// build/test-fetch-odds.js — verify the CLV-001 capture path OFFLINE.
// =============================================================================
//   node --test build/test-fetch-odds.js
//
// No API key, no Supabase key, no network, no credit spent, nothing written.
// It replays the saved Odds API fixture through the same pure row builders the
// live job uses and asserts that every CLV-001 §4 capture requirement lands on
// every row.
//
// This exists because of the order Reed set: the capture path is verified BEFORE
// the migration that stores its output is applied anywhere. "Verified" has to
// mean something checkable at that point, and the only thing checkable before a
// migration exists is the code that will fill it. So the row builders were
// pulled out of the main loop and made pure, and this walks them.
//
// What it CANNOT verify, and nobody should read it as verifying: that the
// provider keeps sending these fields, that the columns accept them, or that a
// real card produces three two-sided books inside 45 minutes of the bell. Those
// need the migration applied and one card captured. See the handoff.
// =============================================================================

const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');

const {
  buildMoneylineRows, marketStatusOf, stripUnsupported,
  nearBellWindow, shouldCaptureNow,
  CAPTURE_COLUMNS, FEED_VERSION, NEAR_BELL_INTERVAL_MIN,
  normalizeName,
} = require('./fetch-odds');

const FIXTURE = path.join(__dirname, '..', 'cfl_engine', 'dur001', 'fixtures',
                          'odds_api_totals_fixture.json');
const events = JSON.parse(fs.readFileSync(FIXTURE, 'utf8'));

// The fixture is a saved payload. Only its PRICES and metadata are read here —
// no result, no outcome, nothing about how any fight went.
const EVENT = events[0];
const BOOK_ID = new Map([['draftkings', 11], ['fanduel', 1], ['betmgm', 12],
                         ['bovada', 10], ['betrivers', 3], ['betonline.ag', 9]]);

// A fight row shaped like loadCandidateFights() produces, matched to the fixture.
const FIGHT = {
  id: 47325, event_id: 900, event_date: '2026-09-19',
  fighter_a_id: 509, fighter_b_id: 1704,
  fighter_a_name: EVENT.home_team, fighter_b_name: EVENT.away_team,
};

const CAPTURED_AT = '2026-09-20T01:40:00.000Z';   // 20 min before commence
const RETRIEVED_AT = '2026-09-20T01:39:55.000Z';

function rows() {
  return buildMoneylineRows(EVENT, FIGHT, BOOK_ID, CAPTURED_AT, RETRIEVED_AT);
}

// ---------------------------------------------------------------------------
// The capture requirements, one test each
// ---------------------------------------------------------------------------

test('the fixture produces moneyline rows at all', () => {
  const r = rows();
  assert.ok(r.length >= 2, `expected both corners from at least one book, got ${r.length}`);
});

test('every row carries every CLV-001 capture column', () => {
  for (const row of rows()) {
    for (const col of CAPTURE_COLUMNS) {
      assert.ok(col in row, `row for fighter ${row.fighter_id} is missing ${col}`);
    }
  }
});

test('item 9 — the provider market id is the provider\'s, not ours', () => {
  for (const row of rows()) {
    assert.strictEqual(row.source_event_id, EVENT.id);
    assert.ok(row.source_event_id, 'a null market id makes Q-10 unenforceable');
  }
});

test('item 7 — the scheduled start is the commence time as seen at capture', () => {
  const expected = new Date(EVENT.commence_time).toISOString();
  for (const row of rows()) assert.strictEqual(row.source_commence_at, expected);
});

test('item 11 — provider and retrieval timestamps are stored separately', () => {
  for (const row of rows()) {
    assert.strictEqual(row.retrieved_at, RETRIEVED_AT);
    assert.ok(row.provider_last_update, 'the book\'s own last_update must survive');
    assert.notStrictEqual(row.provider_last_update, row.captured_at,
      'collapsing the two would hide feed lag, which is what the staleness ' +
      'limit measures');
  }
});

test('item 10 — the opponent at quote time is recorded, and is the other corner', () => {
  for (const row of rows()) {
    assert.ok(row.opponent_fighter_id);
    assert.notStrictEqual(row.opponent_fighter_id, row.fighter_id);
    const corners = new Set([FIGHT.fighter_a_id, FIGHT.fighter_b_id]);
    assert.ok(corners.has(row.opponent_fighter_id));
    assert.strictEqual(
      row.opponent_fighter_id,
      row.fighter_id === FIGHT.fighter_a_id ? FIGHT.fighter_b_id : FIGHT.fighter_a_id);
  }
});

test('item 6 — the feed version is stamped on every row', () => {
  for (const row of rows()) assert.strictEqual(row.feed_version, FEED_VERSION);
});

test('item 12 — raw links back to what the provider actually said', () => {
  for (const row of rows()) {
    assert.ok(row.raw, 'without raw, the publish side is an assertion not a record');
    assert.ok(row.raw.bookmaker_key);
    assert.ok(row.raw.outcome_name, 'the label the provider used must survive');
    assert.strictEqual(normalizeName(row.raw.outcome_name).length > 0, true);
  }
});

// ---------------------------------------------------------------------------
// is_live — an in-play price is never a close
// ---------------------------------------------------------------------------

test('a capture before commence is not live', () => {
  for (const row of rows()) assert.strictEqual(row.is_live, false);
});

test('a capture at or after commence IS live', () => {
  const atBell = new Date(EVENT.commence_time).toISOString();
  for (const row of buildMoneylineRows(EVENT, FIGHT, BOOK_ID, atBell, atBell)) {
    assert.strictEqual(row.is_live, true,
      'a quote taken at or after the bell is in-play and can never be a close');
  }
});

test('is_live is null, not false, when the provider gives no commence time', () => {
  const noCommence = { ...EVENT, commence_time: null };
  for (const row of buildMoneylineRows(noCommence, FIGHT, BOOK_ID, CAPTURED_AT, RETRIEVED_AT)) {
    assert.strictEqual(row.is_live, null,
      'null means "unknown"; false would assert it was a pre-start price, which ' +
      'is a fact we do not have');
    assert.strictEqual(row.source_commence_at, null);
  }
});

// ---------------------------------------------------------------------------
// Side mapping — by name, never by the provider's home/away order
// ---------------------------------------------------------------------------

test('sides map by fighter name, not by provider order', () => {
  const swapped = { ...EVENT, home_team: EVENT.away_team, away_team: EVENT.home_team };
  const normal = rows();
  const flipped = buildMoneylineRows(swapped, FIGHT, BOOK_ID, CAPTURED_AT, RETRIEVED_AT);
  const key = r => `${r.fighter_id}|${r.book_id}|${r.american_odds}|${r.side}`;
  assert.deepStrictEqual(normal.map(key).sort(), flipped.map(key).sort(),
    'swapping the provider\'s home/away labels must not change which fighter ' +
    'got which price');
});

test('an unrecognised outcome label is dropped, never guessed onto a corner', () => {
  const withDraw = JSON.parse(JSON.stringify(EVENT));
  for (const bm of withDraw.bookmakers) {
    const h2h = bm.markets.find(m => m.key === 'h2h');
    if (h2h) h2h.outcomes.push({ name: 'Draw', price: 2000 });
  }
  const before = rows().length;
  assert.strictEqual(
    buildMoneylineRows(withDraw, FIGHT, BOOK_ID, CAPTURED_AT, RETRIEVED_AT).length,
    before, 'a Draw outcome must not be attached to either fighter');
});

test('a book we do not know is skipped rather than invented', () => {
  const r = buildMoneylineRows(EVENT, FIGHT, new Map([['draftkings', 11]]),
                               CAPTURED_AT, RETRIEVED_AT);
  assert.ok(r.every(x => x.book_id === 11));
});

// ---------------------------------------------------------------------------
// market_status — absence is not evidence
// ---------------------------------------------------------------------------

test('a quoting market is open', () => {
  assert.strictEqual(marketStatusOf({}, { outcomes: [{ name: 'a', price: 100 }] }), 'open');
});

test('a missing or empty market is null, never taken_down', () => {
  assert.strictEqual(marketStatusOf({}, null), null);
  assert.strictEqual(marketStatusOf({}, { outcomes: [] }), null);
  // The Odds API reports a pulled market by omitting the bookmaker entirely.
  // Inferring 'taken_down' from that would turn "we did not see it" into "it was
  // pulled" — a manufactured fact, the same family as an epoch timestamp.
});

// ---------------------------------------------------------------------------
// Degrading when the migration is not applied
// ---------------------------------------------------------------------------

test('capture columns are stripped when the table does not have them', () => {
  const stripped = stripUnsupported(rows(), new Set());
  for (const row of stripped) {
    for (const col of CAPTURE_COLUMNS) {
      assert.ok(!(col in row), `${col} must not be sent to an un-migrated table`);
    }
    // The legacy shape survives untouched, so an un-migrated database keeps
    // capturing exactly what it captured before.
    for (const col of ['fight_id', 'fighter_id', 'book_id', 'side', 'american_odds',
                       'implied_prob', 'captured_at', 'source_url', 'is_opener']) {
      assert.ok(col in row, `stripping must not disturb the legacy column ${col}`);
    }
  }
});

test('a partially migrated table keeps only the columns it has', () => {
  const stripped = stripUnsupported(rows(), new Set(['source_event_id', 'is_live']));
  for (const row of stripped) {
    assert.ok('source_event_id' in row);
    assert.ok('is_live' in row);
    assert.ok(!('raw' in row));
    assert.ok(!('opponent_fighter_id' in row));
  }
});

test('stripping does not mutate the rows it was given', () => {
  const original = rows();
  stripUnsupported(original, new Set());
  assert.ok('raw' in original[0],
    'the dry-run printout must still show what we would ideally store');
});

// ---------------------------------------------------------------------------
// Near-bell cadence — the 45-minute limit has to be satisfiable
// ---------------------------------------------------------------------------

const BELL = new Date('2026-09-20T02:00:00Z');
const CARD = [{ id: 1, start_at: BELL.toISOString(), start_basis: 'provider_commence' }];

test('a fight with only the event-date fallback never triggers a near-bell burst', () => {
  const fallbackOnly = [{ id: 1, start_at: BELL.toISOString(),
                          start_basis: 'event_date_fallback' }];
  assert.strictEqual(
    nearBellWindow(fallbackOnly, new Date('2026-09-20T01:00:00Z')), false,
    'the fallback is the event date at 18:00 UTC — a placeholder, not a ' +
    'schedule (CLV-001 Amendment 2 (b))');
  assert.strictEqual(nearBellWindow(CARD, new Date('2026-09-20T01:00:00Z')), true);
});

test('near a bell the job captures every 30 minutes', () => {
  const spent = [];
  for (let m = 0; m < 180; m += 15) {          // the 3h before the bell
    const at = new Date(BELL.getTime() - (180 - m) * 60000);
    if (shouldCaptureNow(CARD, at, true).yes) spent.push(at.toISOString().slice(11, 16));
  }
  assert.deepStrictEqual(spent, ['23:00', '23:30', '00:00', '00:30', '01:00', '01:30']);
  assert.strictEqual(NEAR_BELL_INTERVAL_MIN, 30);
});

test('the freshest pre-bell quote is always inside the 45-minute limit', () => {
  // Walk every possible bell minute; for each, find the last capture strictly
  // before it and check the gap. This is the property the whole cadence change
  // exists for, so it is checked exhaustively rather than on one example.
  for (let bellMin = 0; bellMin < 60; bellMin++) {
    const bell = new Date(`2026-09-20T02:${String(bellMin).padStart(2, '0')}:00Z`);
    const card = [{ id: 1, start_at: bell.toISOString(), start_basis: 'provider_commence' }];
    let last = null;
    for (let back = 240; back >= 1; back--) {
      const at = new Date(bell.getTime() - back * 60000);
      if (at.getUTCMinutes() % 15 !== 0) continue;   // the workflow wakes at :00/:15/:30/:45
      if (shouldCaptureNow(card, at, true).yes) last = at;
    }
    assert.ok(last, `no capture at all before a bell at :${bellMin}`);
    const ageMin = (bell - last) / 60000;
    assert.ok(ageMin < 45,
      `bell at :${bellMin} would be scored against a quote ${ageMin} min old, ` +
      `outside the frozen 45-minute limit`);
  }
});

test('away from a card the cadence stays cheap', () => {
  const quiet = new Date('2026-09-02T08:00:00Z');   // baseline hour, no card
  assert.strictEqual(shouldCaptureNow([], quiet, false).yes, true);
  assert.strictEqual(shouldCaptureNow([], new Date('2026-09-02T09:00:00Z'), false).yes, false);
  assert.strictEqual(shouldCaptureNow([], new Date('2026-09-02T08:15:00Z'), false).yes, false,
    'the baseline is one capture, not four');
});

test('a card day away from any bell is hourly, not every 15 minutes', () => {
  const far = new Date('2026-09-20T12:00:00Z');     // card today, bell long past
  assert.strictEqual(shouldCaptureNow(CARD, far, true).yes, true);
  assert.strictEqual(shouldCaptureNow(CARD, new Date('2026-09-20T12:15:00Z'), true).yes, false);
});

test('the credit budget for a card day stays inside the free tier', () => {
  // 13 fights, 30 minutes apart, the shape of a real card.
  const card = Array.from({ length: 13 }, (_, i) => ({
    id: i, start_basis: 'provider_commence',
    start_at: new Date(BELL.getTime() + i * 30 * 60000).toISOString(),
  }));
  let credits = 0;
  for (let m = 0; m < 24 * 60; m += 15) {
    const at = new Date(Date.UTC(2026, 8, 20, 0, 0) + m * 60000);
    if (shouldCaptureNow(card, at, true).yes) credits++;
  }
  // ~8 card days a month plus ~22 baseline days must stay under 500/month.
  const monthly = credits * 8 + 22;
  assert.ok(monthly < 500,
    `${credits} credits on a card day projects to ${monthly}/month, over the ` +
    `free tier — the cadence needs narrowing, not the staleness limit widening`);
});
