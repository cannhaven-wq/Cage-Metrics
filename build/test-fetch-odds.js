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
  nearBellWindow, shouldCaptureNow, currentBout, boutStartedAt, proxyCutoffAt,
  planLiveCadence, minutesRemainingInCard, wantTotals, resolveCurrentCard,
  spentThisMonth, remainingCredits,
  CAPTURE_COLUMNS, FEED_VERSION, NEAR_BELL_INTERVAL_MIN, EVENT_FLOW_MAX_H,
  MONTHLY_CREDIT_CAP, CREDIT_HARD_FLOOR, CREDIT_RESERVE, LIVE_CADENCE_LADDER,
  FREE_TIER_CREDIT_CAP, APPROVED_CREDIT_RESERVE,
  resolveMonthlyCap, resolveReserve, clampToFreeAllowance,
  WAKE_INTERVAL_MIN, TOTALS_MIN_INTERVAL_MIN,
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
// is_live — PER FIGHT, and an in-play price is never a close (Amendment 3)
// ---------------------------------------------------------------------------
// A card is one scheduled start and then a queue. Keying liveness to the card's
// commence time marks every quote taken after the first bell as in-play for all
// thirteen fights, and throws away exactly the quotes the later fights close on.
// These tests exist to stop that being reintroduced.

const FIRST_BOUT = { ...FIGHT, bout_order: 1, prev_completed_at: null };
const CONFIRMED_BELL = '2026-09-20T02:07:00.000Z';

test('bout_started_at is filled ONLY by a confirmed bell', () => {
  // Amendment 5.1. It used to fall back to the previous bout's completion,
  // asserting that fight N+1 began the instant fight N ended. It did not — the
  // walkout sits between them — and this column's only job is to hold facts.
  const later = { ...FIGHT, bout_order: 7,
                  prev_completed_at: '2026-09-20T03:30:00.000Z' };
  for (const row of buildMoneylineRows(EVENT, later, BOOK_ID, CAPTURED_AT, RETRIEVED_AT)) {
    assert.strictEqual(row.bout_started_at, null,
      'the previous bout ending is not this fight starting');
    assert.strictEqual(row.is_live, null,
      'unknown, because no bell is on file — never false, which would assert ' +
      'the quote was pre-start');
  }
  const withBell = { ...later, bell_at: CONFIRMED_BELL };
  for (const row of buildMoneylineRows(EVENT, withBell, BOOK_ID, CAPTURED_AT, RETRIEVED_AT)) {
    assert.strictEqual(row.bout_started_at, CONFIRMED_BELL);
    assert.strictEqual(row.is_live, false, 'captured before the bell');
  }
});

test('bout 1 does not get a bout_started_at from the card schedule either', () => {
  for (const row of buildMoneylineRows(EVENT, FIRST_BOUT, BOOK_ID, CAPTURED_AT, RETRIEVED_AT)) {
    assert.strictEqual(row.bout_started_at, null,
      'a scheduled start is a schedule, not a record that the fight began');
    assert.strictEqual(row.is_live, null);
  }
});

test('is_live becomes true only once a real bell has passed', () => {
  const withBell = { ...FIRST_BOUT, bell_at: CONFIRMED_BELL };
  const after = '2026-09-20T02:10:00.000Z';
  for (const row of buildMoneylineRows(EVENT, withBell, BOOK_ID, after, after)) {
    assert.strictEqual(row.is_live, true,
      'a quote taken after the bell is in-play and can never be a close');
  }
});

// ---------------------------------------------------------------------------
// proxy_cutoff_at — the frozen cutoff, under its own name
// ---------------------------------------------------------------------------

test('bout 1 takes the card scheduled start as its cutoff', () => {
  const expected = new Date(EVENT.commence_time).toISOString();
  for (const row of buildMoneylineRows(EVENT, FIRST_BOUT, BOOK_ID, CAPTURED_AT, RETRIEVED_AT)) {
    assert.strictEqual(row.proxy_cutoff_at, expected);
  }
});

test('a later bout takes the previous bout completion as its cutoff', () => {
  const prevDone = '2026-09-20T03:30:00.000Z';
  const later = { ...FIGHT, bout_order: 7, prev_completed_at: prevDone };
  for (const row of buildMoneylineRows(EVENT, later, BOOK_ID, CAPTURED_AT, RETRIEVED_AT)) {
    assert.strictEqual(row.proxy_cutoff_at, prevDone);
    assert.strictEqual(row.bout_started_at, null,
      'the cutoff and the start are different columns because they are ' +
      'different claims');
  }
});

test('a later bout with no completion recorded has no cutoff', () => {
  const later = { ...FIGHT, bout_order: 7, prev_completed_at: null };
  for (const row of buildMoneylineRows(EVENT, later, BOOK_ID, CAPTURED_AT, RETRIEVED_AT)) {
    assert.strictEqual(row.proxy_cutoff_at, null);
  }
});

test('a later bout never inherits the card schedule as its cutoff', () => {
  const later = { ...FIGHT, bout_order: 7, prev_completed_at: null };
  const cardStart = new Date(EVENT.commence_time).toISOString();
  for (const row of buildMoneylineRows(EVENT, later, BOOK_ID, CAPTURED_AT, RETRIEVED_AT)) {
    assert.notStrictEqual(row.proxy_cutoff_at, cardStart);
  }
});

test('proxyCutoffAt follows the frozen two cases and nothing else', () => {
  const prev = '2026-09-20T03:30:00.000Z';
  const sched = '2026-09-20T02:00:00.000Z';
  assert.strictEqual(proxyCutoffAt({ bout_order: 1 }, null, sched), sched);
  assert.strictEqual(proxyCutoffAt({ bout_order: 7 }, prev, sched), prev);
  assert.strictEqual(proxyCutoffAt({ bout_order: 7 }, null, sched), null,
    'a later bout must never fall back to the card schedule');
  assert.strictEqual(proxyCutoffAt({ bout_order: null }, prev, sched), null,
    'unknown running order is neither case');
  assert.strictEqual(proxyCutoffAt({ bout_order: 1, bell_at: CONFIRMED_BELL }, null, sched),
                     sched, 'a bell does not override the frozen cutoff');
});

test('the card schedule is still recorded separately from the cutoff', () => {
  for (const row of rows()) {
    assert.strictEqual(row.source_commence_at,
                       new Date(EVENT.commence_time).toISOString());
  }
});

// ---------------------------------------------------------------------------
// Running order — the latest COMPLETE CARD, not the latest row per fight
// ---------------------------------------------------------------------------
//
// `fight_bout_order` is an observation ledger: the whole card is appended as one
// observation sharing one observed_at, and history is never edited. So a booking
// that was pulled from the card still has its old row on file forever. Resolving
// per fight would let that dead row stay "current" and give the card two bout 1s.

const OBS_1 = '2026-09-19T12:00:00.000Z';   // card as first seen: A, B, C
const OBS_2 = '2026-09-20T12:00:00.000Z';   // A scratched: B, C

// As the query returns them: observed_at DESC, id DESC.
const ORDER_LEDGER = [
  { id: 5, fight_id: 'C', event_id: 900, bout_order: 2, observed_at: OBS_2, source: 'ufcstats_card' },
  { id: 4, fight_id: 'B', event_id: 900, bout_order: 1, observed_at: OBS_2, source: 'ufcstats_card' },
  { id: 3, fight_id: 'C', event_id: 900, bout_order: 3, observed_at: OBS_1, source: 'ufcstats_card' },
  { id: 2, fight_id: 'B', event_id: 900, bout_order: 2, observed_at: OBS_1, source: 'ufcstats_card' },
  { id: 1, fight_id: 'A', event_id: 900, bout_order: 1, observed_at: OBS_1, source: 'ufcstats_card' },
];

// The same event -> bout_order -> fight_id index attachEventFlow builds, so the
// previous-bout assertions below exercise the real lookup and not a paraphrase.
function positionIndex(current) {
  const byEventOrder = new Map();
  for (const [fightId, o] of current) {
    byEventOrder.set(`${o.event_id}|${o.bout_order}`, fightId);
  }
  return byEventOrder;
}

test('the current card is the latest complete observation, A=1,B=2,C=3 -> B=1,C=2', () => {
  const current = resolveCurrentCard(ORDER_LEDGER);
  assert.strictEqual(current.get('B').bout_order, 1);
  assert.strictEqual(current.get('C').bout_order, 2);
  assert.strictEqual(current.size, 2, 'the current card is exactly what the ' +
    'latest observation contained');
});

test('a scratched bout is historical only and holds no current position', () => {
  const current = resolveCurrentCard(ORDER_LEDGER);
  assert.strictEqual(current.has('A'), false,
    'A is absent from the latest observation, so it is not on the card');
  const byEventOrder = positionIndex(current);
  assert.strictEqual(byEventOrder.get('900|1'), 'B',
    'position 1 belongs to B; A must not still occupy it');
  assert.notStrictEqual(byEventOrder.get('900|1'), 'A');
  assert.strictEqual(byEventOrder.get('900|3'), undefined,
    'the card is two bouts long now — there is no third position to inherit');
});

test('the previous bout of C is B, never the scratched A', () => {
  const current = resolveCurrentCard(ORDER_LEDGER);
  const byEventOrder = positionIndex(current);
  const c = current.get('C');
  const prev = byEventOrder.get(`${c.event_id}|${c.bout_order - 1}`);
  assert.strictEqual(prev, 'B');
  assert.notStrictEqual(prev, 'A',
    "a dead booking's completion must never become the next bout's cutoff");
});

test('the first bout of the current card is B, and B alone', () => {
  const current = resolveCurrentCard(ORDER_LEDGER);
  const firsts = [...current].filter(([, o]) => o.bout_order === 1).map(([id]) => id);
  assert.deepStrictEqual(firsts, ['B'],
    'exactly one fight may be identified as bout 1 — that is what takes the ' +
    "card's scheduled start as its cutoff");
});

test('another source cannot truncate or extend the current card', () => {
  const mixed = [
    { id: 9, fight_id: 'D', event_id: 900, bout_order: 1, observed_at: '2026-09-21T00:00:00.000Z',
      source: 'manual' },
    ...ORDER_LEDGER,
  ];
  const current = resolveCurrentCard(mixed);
  assert.strictEqual(current.has('D'), false,
    'only ufcstats_card carries complete-card semantics');
  assert.strictEqual(current.get('B').bout_order, 1);
  assert.strictEqual(current.size, 2);
});

test('each event resolves its own latest card independently', () => {
  const twoEvents = [
    { id: 8, fight_id: 'X', event_id: 901, bout_order: 1, observed_at: OBS_1, source: 'ufcstats_card' },
    ...ORDER_LEDGER,
  ];
  const current = resolveCurrentCard(twoEvents);
  assert.strictEqual(current.get('X').bout_order, 1,
    "event 901's newest observation is its own, not event 900's");
  assert.strictEqual(current.get('B').bout_order, 1);
  assert.strictEqual(current.size, 3);
});

// ---------------------------------------------------------------------------
// The closer promotion may only touch the derived flags
// ---------------------------------------------------------------------------
//
// CLV-001 Amendment 6 (g) makes fight_odds observation fields immutable by
// trigger (R-01: clv_source_quote_ids points at these rows as evidence, and
// evidence that can be rewritten afterwards is not evidence). The whitelist is
// exactly `is_opener` and `is_closer` — derived flags, recomputable, carrying no
// observation of their own.
//
// This job is the only UPDATE path in the repo. If a future edit here starts
// writing another column, that column is protected and the cron starts erroring
// at 23:00 UTC on a card night. Pinned here so it fails in the suite instead.

const SOURCE = fs.readFileSync(path.join(__dirname, 'fetch-odds.js'), 'utf8');

test('every fight_odds UPDATE writes only whitelisted derived fields', () => {
  const updates = [...SOURCE.matchAll(
    /from\(['"]fight_odds['"]\)\s*\.update\(\{([^}]*)\}/g)];
  assert.ok(updates.length > 0, 'the closer promotion is gone — if that is ' +
    'deliberate, delete this test with it');
  const allowed = new Set(['is_opener', 'is_closer']);
  for (const m of updates) {
    for (const key of m[1].split(',')) {
      const name = key.split(':')[0].trim();
      if (!name) continue;
      assert.ok(allowed.has(name),
        `fetch-odds.js UPDATEs fight_odds.${name}, which the CLV-001 ` +
        `immutability trigger rejects. Append a new observation row instead.`);
    }
  }
});

test('nothing in the odds job deletes a captured quote', () => {
  assert.ok(!/from\(['"]fight_odds['"]\)\s*\.delete\(/.test(SOURCE),
    'fight_odds is append-only (R-01): a quote that turns out to be garbage ' +
    'is excluded at scoring time by a written rule, never deleted');
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

test('capture continues through the card, not just around its scheduled start', () => {
  // The whole point of the event-flow rule. The card's ONE published start is
  // bout 1's; the twelfth fight walks out hours later, and it needs a quote
  // inside 45 minutes of ITS start, not of the card's.
  const card = [{ id: 1, start_at: BELL.toISOString(), start_basis: 'provider_commence' }];
  const fourHoursIn = new Date(BELL.getTime() + 4 * 3600000);
  assert.strictEqual(nearBellWindow(card, fourHoursIn), true,
    'four hours into a card is still the card');
  assert.strictEqual(shouldCaptureNow(card, fourHoursIn, true).yes, true);
});

test('capture stops once the card is over', () => {
  const card = [{ id: 1, start_at: BELL.toISOString(),
                  start_basis: 'provider_commence', card_complete: true }];
  const duringFlow = new Date(BELL.getTime() + 2 * 3600000);
  assert.strictEqual(nearBellWindow(card, duringFlow), false,
    'every bout has an exact completion — the night is over, stop spending');
});

test('the flow window is bounded even if no completion ever arrives', () => {
  const card = [{ id: 1, start_at: BELL.toISOString(), start_basis: 'provider_commence' }];
  const past = new Date(BELL.getTime() + (EVENT_FLOW_MAX_H + 1) * 3600000);
  assert.strictEqual(nearBellWindow(card, past), false,
    'the ceiling bounds the spend when the completion ledger is empty, which ' +
    'is its state today');
});

// ---------------------------------------------------------------------------
// The hard usage ceiling (Amendment 4)
// ---------------------------------------------------------------------------
// Five-minute capture is the target; the governor is what keeps it inside a free
// allowance. Measured: 3.7 UFC events a month on average, 6 in the busiest.

const CARD = [{ id: 1, start_at: BELL.toISOString(), start_basis: 'provider_commence' }];

function creditsForCardDay(budget, wakeEvery = 5) {
  let credits = 0;
  for (let m = 0; m < 24 * 60; m += wakeEvery) {
    const at = new Date(Date.UTC(2026, 8, 20, 0, 0) + m * 60000);
    if (shouldCaptureNow(CARD, at, true, budget).yes) credits++;
  }
  return credits;
}

test('with budget to spare the cadence is the five-minute target', () => {
  assert.strictEqual(
    planLiveCadence({ creditsRemaining: 480, cardsRemaining: 1,
                      minutesRemainingInCard: 420 }), 5);
});

test('a tight budget degrades down the ladder rather than stopping', () => {
  // One card left and a comfortable balance: the target holds.
  assert.strictEqual(
    planLiveCadence({ creditsRemaining: 300, cardsRemaining: 1,
                      minutesRemainingInCard: 120 }), 5);
  // Same balance, but three more cards to pay for afterwards and a long card
  // still to run: it must coarsen rather than spend the later cards' floor.
  const squeezed = planLiveCadence({ creditsRemaining: 300, cardsRemaining: 4,
                                     minutesRemainingInCard: 600 });
  assert.ok(squeezed > 5, 'a long card with three more to fund must coarsen');
  assert.ok(LIVE_CADENCE_LADDER.includes(squeezed));
});

test('every rung on the ladder clears the frozen staleness limit', () => {
  // The governor is allowed to trade lead time for budget, and never
  // correctness. A rung coarser than the 45-minute staleness limit would trade
  // correctness — an observation captured on that beat could be unscorable.
  for (const rung of LIVE_CADENCE_LADDER) {
    assert.ok(rung < 45,
      `a ${rung}-minute rung can leave the freshest quote outside the frozen ` +
      `45-minute limit`);
  }
  assert.strictEqual(LIVE_CADENCE_LADDER[LIVE_CADENCE_LADDER.length - 1], 30);
});

test('a squeezed budget picks a coarser rung, and only one that fits', () => {
  const budget = { creditsRemaining: 120, cardsRemaining: 1,
                   minutesRemainingInCard: 600 };
  const picked = planLiveCadence(budget);
  assert.ok(LIVE_CADENCE_LADDER.includes(picked), 'must be a real rung or null');
  const cost = Math.ceil(600 / picked) + 15;
  assert.ok(cost <= budget.creditsRemaining - CREDIT_RESERVE || picked === null,
    `picked a ${picked}-minute rung costing ${cost} against a budget that ` +
    `cannot fund it`);
});

test('at the hard floor capture stops rather than overspending', () => {
  assert.strictEqual(
    planLiveCadence({ creditsRemaining: CREDIT_HARD_FLOOR, cardsRemaining: 1,
                      minutesRemainingInCard: 60 }), null);
  const decision = shouldCaptureNow(CARD, BELL, true,
    { creditsRemaining: 0, cardsRemaining: 1 });
  assert.strictEqual(decision.yes, false);
  assert.match(decision.why, /no cadence fits/);
});

test('when NO cadence fits the budget the governor returns STOP, not 30 minutes', () => {
  // The specific hole this closes. The ladder used to fall through to its
  // coarsest rung, which turned "we cannot afford any cadence" into "spend at 30
  // minutes anyway" — and it did so exactly when the budget was tightest. A
  // ceiling that yields under pressure is not a ceiling.
  //
  // Above the hard floor, so the earlier guard does not catch it; and a balance
  // that cannot even fund the coarsest rung for the card still to run.
  const budget = {
    creditsRemaining: CREDIT_HARD_FLOOR + 5,   // above the floor
    cardsRemaining: 1,
    minutesRemainingInCard: 600,
  };
  const coarsest = LIVE_CADENCE_LADDER[LIVE_CADENCE_LADDER.length - 1];
  const coarsestCost = Math.ceil(600 / coarsest);
  assert.ok(coarsestCost > budget.creditsRemaining,
    'the fixture must be a case where even the coarsest rung is unaffordable');

  assert.strictEqual(planLiveCadence(budget), null,
    `returned a cadence when nothing fits — the coarsest rung costs ` +
    `${coarsestCost} and only ${budget.creditsRemaining} credits remain`);

  const decision = shouldCaptureNow(CARD, BELL, true, budget);
  assert.strictEqual(decision.yes, false);
  assert.strictEqual(decision.cadence, null);
  assert.match(decision.why, /no cadence fits/);
});

test('the coarsest rung alone can never exhaust the allowance', () => {
  // This is what makes "unknown budget -> coarsest rung" defensible rather than
  // hopeful: a whole month spent at the coarsest cadence has to fit, or that
  // branch is a hole of its own.
  for (let cards = 1; cards <= 8; cards++) {
    let remaining = MONTHLY_CREDIT_CAP;
    for (let card = 0; card < cards; card++) {
      remaining -= creditsForCardDay({ creditsRemaining: undefined });
    }
    assert.ok(remaining - (30 - cards) >= 0,
      `${cards} cards at the coarsest rung leaves ${remaining} for ` +
      `${30 - cards} baseline days — the unknown-budget branch would overspend`);
  }
});

test('an unknown budget is treated as tight, never as unlimited', () => {
  assert.strictEqual(
    planLiveCadence({ creditsRemaining: undefined, cardsRemaining: 1,
                      minutesRemainingInCard: 60 }), 30,
    'a fresh database or the first run of a month must not read as a blank ' +
    'cheque — that is how a free tier turns into a bill');
});

test('no plausible month exceeds the free allowance', () => {
  // The ceiling is the whole point of the governor, so this is checked across
  // every month shape rather than on the average one. Measured range is 2-6 UFC
  // events a month; 7 and 8 are included as headroom.
  for (let cards = 1; cards <= 8; cards++) {
    let remaining = MONTHLY_CREDIT_CAP;
    for (let card = 0; card < cards; card++) {
      const spent = creditsForCardDay({ creditsRemaining: remaining,
                                        cardsRemaining: cards - card });
      remaining -= spent;
      assert.ok(remaining >= 0,
        `${cards}-card month: card ${card + 1} overspent the allowance`);
    }
    const baselineDays = 30 - cards;
    assert.ok(remaining - baselineDays >= 0,
      `${cards}-card month leaves ${remaining} credits for ${baselineDays} ` +
      `baseline days — over the allowance. Raise the reserve or coarsen the ` +
      `ladder; never widen the staleness limit to compensate.`);
  }
});

test('an average month leaves the cadence at or near the target', () => {
  // 3.7 events/month measured, so 4. With a full allowance the first card
  // should run at the five-minute target rather than being pre-emptively
  // throttled.
  assert.strictEqual(
    planLiveCadence({ creditsRemaining: MONTHLY_CREDIT_CAP, cardsRemaining: 4,
                      minutesRemainingInCard: 420 }), 5);
});

test('totals do not ride every five-minute call', () => {
  // Totals cost a second credit each time they ride. DUR-001 keeps the density
  // it already had — one totals call per 30 minutes — and no more.
  const card = [{ id: 1, start_at: BELL.toISOString(),
                  start_basis: 'provider_commence', event_date: '2026-09-20' }];
  let totals = 0;
  for (let m = 0; m < 60; m += WAKE_INTERVAL_MIN) {
    const at = new Date(BELL.getTime() - 3600000 + m * 60000);
    if (wantTotals(card, at).yes) totals++;
  }
  assert.ok(totals <= 60 / TOTALS_MIN_INTERVAL_MIN,
    `${totals} totals calls in an hour — that doubles the card's bill`);
});

test('minutesRemainingInCard ignores a placeholder start', () => {
  const fallbackOnly = [{ id: 1, start_at: BELL.toISOString(),
                          start_basis: 'event_date_fallback' }];
  assert.strictEqual(minutesRemainingInCard(fallbackOnly, BELL), 0);
  assert.ok(minutesRemainingInCard(CARD, BELL) > 0);
});

// ---------------------------------------------------------------------------
// The spending rule cannot be widened from outside (Amendment 4.2)
// ---------------------------------------------------------------------------
// Any spend above the approved free allowance is money, and money is L3. An
// automated job must never be able to authorise one — not through an
// environment variable, and not by noticing the provider is willing to sell
// more. Both look like "more headroom" to a naive governor; neither is
// permission.

test('an environment variable cannot raise the credit cap', () => {
  assert.strictEqual(resolveMonthlyCap('5000'), FREE_TIER_CREDIT_CAP);
  assert.strictEqual(resolveMonthlyCap(String(FREE_TIER_CREDIT_CAP + 1)),
                     FREE_TIER_CREDIT_CAP);
  assert.strictEqual(resolveMonthlyCap('999999'), FREE_TIER_CREDIT_CAP);
});

test('an environment variable CAN lower the credit cap', () => {
  assert.strictEqual(resolveMonthlyCap('200'), 200,
    'spending less is always allowed without an L3');
});

test('a missing or nonsense cap falls back to the approved allowance', () => {
  for (const v of [undefined, '', 'abc', '0', '-5']) {
    assert.strictEqual(resolveMonthlyCap(v), FREE_TIER_CREDIT_CAP);
  }
});

test('an environment variable cannot lower the reserve', () => {
  assert.strictEqual(resolveReserve('0'), APPROVED_CREDIT_RESERVE);
  assert.strictEqual(resolveReserve('10'), APPROVED_CREDIT_RESERVE,
    'lowering a reserve frees credits the governor was told to hold back — the ' +
    'same decision as raising the cap, wearing a different hat');
  assert.strictEqual(resolveReserve('150'), 150, 'raising it is always allowed');
});

test('a provider quota above the free allowance is clamped, not spent', () => {
  assert.strictEqual(clampToFreeAllowance(20000), MONTHLY_CREDIT_CAP,
    'a paid plan attached upstream is not authorisation for this job to spend');
  assert.strictEqual(clampToFreeAllowance(MONTHLY_CREDIT_CAP + 1),
                     MONTHLY_CREDIT_CAP);
  assert.strictEqual(clampToFreeAllowance(120), 120, 'a normal balance passes');
  assert.strictEqual(clampToFreeAllowance(undefined), undefined,
    'unknown stays unknown, which the governor treats as tight');
});

test('the live cap and reserve are the approved values', () => {
  assert.strictEqual(MONTHLY_CREDIT_CAP, FREE_TIER_CREDIT_CAP);
  assert.strictEqual(CREDIT_RESERVE, APPROVED_CREDIT_RESERVE);
});

test('a clamped quota cannot buy a finer cadence than the real allowance would', () => {
  // The whole point, end to end: an inflated balance must not translate into
  // more spending.
  const inflated = planLiveCadence({
    creditsRemaining: clampToFreeAllowance(20000),
    cardsRemaining: 1, minutesRemainingInCard: 600 });
  const honest = planLiveCadence({
    creditsRemaining: MONTHLY_CREDIT_CAP,
    cardsRemaining: 1, minutesRemainingInCard: 600 });
  assert.strictEqual(inflated, honest);
});

// ---------------------------------------------------------------------------
// The monthly allowance must actually DECLINE (Amendment 5, fix 1)
// ---------------------------------------------------------------------------
// The bug: clamping a large provider balance to 500 on every run made the budget
// read 500 every time. It never declined, the governor never degraded, and the
// ceiling was decorative. Our own month-to-date count is the authoritative side
// precisely because nothing upstream can reset it.

test('month-to-date spend sums what each call actually cost', () => {
  assert.strictEqual(spentThisMonth([]), 0);
  assert.strictEqual(spentThisMonth([{ credits_charged: 1 }]), 1);
  assert.strictEqual(
    spentThisMonth([{ credits_charged: 2 }, { credits_charged: 1 }]), 3,
    'h2h+totals costs two credits, h2h alone one');
  assert.strictEqual(spentThisMonth([{}, {}]), 2,
    'a row with no recorded charge counts as one, never as zero');
});

test('a huge provider balance no longer resets the budget', () => {
  // The exact regression. Nineteen thousand credits upstream, three spent by us.
  const ledger = [{ credits_charged: 2, requests_remaining: 19500 },
                  { credits_charged: 1, requests_remaining: 19502 }];
  assert.strictEqual(remainingCredits(ledger, 19500), MONTHLY_CREDIT_CAP - 3,
    'the balance must reflect OUR spend, not the provider\'s generosity');
});

test('the budget declines monotonically as calls accumulate', () => {
  const ledger = [];
  let previous = remainingCredits(ledger, 19500);
  for (let call = 0; call < 40; call++) {
    ledger.push({ credits_charged: 1, requests_remaining: 19500 });
    const now = remainingCredits(ledger, 19500);
    assert.ok(now < previous,
      `after ${call + 1} calls the balance did not fall (${previous} -> ${now})`);
    previous = now;
  }
  assert.strictEqual(previous, MONTHLY_CREDIT_CAP - 40);
});

test('a provider balance TIGHTER than our count is believed', () => {
  const ledger = [{ credits_charged: 1, requests_remaining: 12 }];
  assert.strictEqual(remainingCredits(ledger, 12), 12,
    'the provider catches calls we made but failed to log; the smaller of the ' +
    'two accounts always wins');
});

test('with no provider reading our own count still governs', () => {
  const ledger = [{ credits_charged: 2 }, { credits_charged: 2 }];
  assert.strictEqual(remainingCredits(ledger, undefined), MONTHLY_CREDIT_CAP - 4);
});

test('a spent-out month reaches the STOP condition through our own count alone', () => {
  const ledger = Array.from({ length: MONTHLY_CREDIT_CAP }, () => ({ credits_charged: 1 }));
  const remaining = remainingCredits(ledger, 19500);
  assert.strictEqual(remaining, 0);
  assert.strictEqual(
    planLiveCadence({ creditsRemaining: remaining, cardsRemaining: 1,
                      minutesRemainingInCard: 60 }), null,
    'an exhausted allowance must stop capture even while the provider would ' +
    'happily sell more');
});
