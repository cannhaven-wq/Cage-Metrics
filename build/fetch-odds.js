// =============================================================================
// build/fetch-odds.js — pull current UFC moneyline odds from The Odds API and
// write per-book snapshot rows into Supabase `fight_odds`.
// =============================================================================
// This writes the SAME snapshot shape the cage-metrics-odds-scrapper Railway
// cron uses — one row per (fight, side, book, captured_at):
//
//   { fight_id, fighter_id, book_id, side:'A'|'B', american_odds, implied_prob,
//     captured_at, source_url }   (is_opener / is_closer default FALSE)
//
// so the existing `v_fight_odds_consensus` view and the parlay/event/index
// pages read it with no other changes. (The previous version of this file wrote
// a one-row-per-fight `american_odds_a/b` shape that collided with the live
// table — that's why the workflow was disabled. Fixed here.)
//
// Runs in CI via .github/workflows/odds.yml. Requires two secrets:
//   - ODDS_API_KEY              (the-odds-api.com)
//   - SUPABASE_SERVICE_ROLE_KEY (Supabase → Project Settings → API; legacy JWT
//                                service_role key, NOT the sb_secret_ format)
//
// The service-role key bypasses RLS so we can write without an auth session.
// Keep it in GitHub Secrets only — never commit it.
//
// Cost: ONE API request per run (regions=us, markets=h2h) = 1 credit, and it
// returns the whole MMA slate at once. Free tier is 500/mo.
//
// CADENCE (changed 2026-08-30): the workflow now wakes HOURLY, but this script
// decides whether the run is worth a credit before spending one — see
// shouldSpendCredit(). A price captured once a day is not a closing price: with
// the old every-2h-on-paper schedule the freshest line we held going into a
// bell could be ~24h stale, which makes CLV a guess. Now:
//
//   * card today or tomorrow (UTC) -> capture every hour, so the last line we
//     hold before any bell is at most ~60 minutes old
//   * no card in that window       -> one baseline capture a day (08:00 UTC) to
//     keep openers and slow line movement on file
//
// Budget: ~8 card-adjacent days/month x 24 + ~22 quiet days x 1 = ~215 credits,
// well inside the 500 cap and far denser where it actually matters. Quiet-hour
// runs exit BEFORE the API call, so they cost nothing.
// =============================================================================

const { createClient } = require('@supabase/supabase-js');

const ODDS_API_KEY = process.env.ODDS_API_KEY;
const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
// CI sets SUPABASE_SERVICE_ROLE_KEY; local Windows env uses SUPABASE_SECRET_KEY.
// Either works (both must be the legacy JWT service_role key to bypass RLS).
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SECRET_KEY;
const SOURCE_TAG = 'the-odds-api:mma_mixed_martial_arts';
// DRY_RUN=1 → fetch + match + build rows but DON'T write. For safe local testing.
// A fixture replay is always a dry run: synthetic quotes must never be stored.
const DRY_RUN = !!process.env.DRY_RUN || !!process.env.ODDS_FIXTURE;

// Which feed and response shape produced a row. Bumped when the request or the
// parsing changes in a way that could shift timings without changing a price —
// CLV-001 §4 item 6 exists because that has to be detectable afterwards.
const FEED_VERSION = 'odds-api-v4:h2h:2026-09-16';

// Credentials are checked inside main(), not at module load, so this file can be
// require()d by build/test-fetch-odds.js to exercise the pure row builders with
// no key and no network. A script that cannot be tested without credentials
// tends not to be tested.
function requireCredentials() {
  if (!ODDS_API_KEY && !process.env.ODDS_FIXTURE) {
    console.error('ODDS_API_KEY missing. Set it in GitHub Secrets (or env for local runs).');
    process.exit(1);
  }
  if (!SUPABASE_SERVICE_KEY) {
    console.error('SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SECRET_KEY) missing.');
    process.exit(1);
  }
}

const sb = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY || 'no-key-required-for-require', {
  auth: { persistSession: false, autoRefreshToken: false }
});

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------

// Casing, apostrophes, accents, punctuation, and generational suffixes all vary
// between the Odds API and our `fighters` table. Normalize aggressively, and
// strip trailing jr/sr/ii/iii/iv/v so "Kai Kamaka III" == "Kai Kamaka" and
// "Khalil Rountree Jr" == "Khalil Rountree". Applied to BOTH sides so it stays
// symmetric.
function normalizeName(name) {
  return String(name || '')
    .toLowerCase()
    .normalize('NFD').replace(/\p{Diacritic}/gu, '')
    .replace(/'/g, '')
    .replace(/[^a-z0-9 ]/g, ' ')
    .replace(/\b(jr|sr|ii|iii|iv|v)\b/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function americanToImplied(american) {
  if (american == null) return null;
  if (american > 0) return 100 / (american + 100);
  return -american / (-american + 100);
}

function impliedToAmerican(p) {
  if (p == null || p <= 0 || p >= 1) return null;
  return Math.round(p >= 0.5 ? (-100 * p) / (1 - p) : (100 * (1 - p)) / p);
}

// The synthetic consensus "book": one row per (fight, side) per run holding the
// median implied probability across all real books in that snapshot. Gives the
// models a single canonical price series — and, via the is_opener flag below, a
// locked opening price — even though the underlying book set varies run to run.
const CONSENSUS_BOOK_NAME = 'CFL Consensus (Odds API)';

// -----------------------------------------------------------------------------
// 0. Cadence gate — is this hourly wake-up worth a credit?
// -----------------------------------------------------------------------------
// Runs against `events` only (free), before any Odds API call. FORCE=1 (set by
// workflow_dispatch) always spends, so a manual run is never silently skipped.

const BASELINE_HOUR_UTC = 8;

// CLV-001's staleness limit is 45 minutes, and it was derived from a MEASURED
// 30-minute near-card capture interval plus 15 minutes of grace. An hourly
// capture cannot satisfy it: a bell at :59 leaves the freshest quote 59 minutes
// old, and the observation is unscored on a stale price.
//
// So near a bell the job captures every 30 minutes, which is the cadence the
// frozen limit already assumes. Worst case becomes 29 minutes and change, and
// the limit is satisfiable by construction rather than by luck.
//
// The workflow wakes every 15 minutes; shouldCaptureNow() decides, before any
// API call, whether the wake is worth a credit. Quiet wakes cost nothing.
const NEAR_BELL_WINDOW_H = Number(process.env.NEAR_BELL_WINDOW_H || 3);
const NEAR_BELL_INTERVAL_MIN = 30;

// -----------------------------------------------------------------------------
// Credit budget — the hard ceiling (CLV-001 Amendment 4)
// -----------------------------------------------------------------------------
// Five-minute capture through a live card is what makes the late pre-fight proxy
// worth having: the last price before the card starts is then five minutes old
// rather than thirty. It is also expensive enough to break the free tier if it
// runs unchecked.
//
// Measured, 2025-01 to 2026-08: 3.7 UFC events a month on average, 6 in the
// busiest month. At 5-minute cadence a single card costs roughly 93 h2h credits.
// Six of those plus the daily baselines is ~640 — over a 500-credit allowance.
//
// So the cadence is a TARGET and the ceiling is a GOVERNOR. Before each call the
// job asks how many credits are left this month, how many cards are still to
// come, and picks the finest cadence on the ladder that fits. When the budget is
// tight it degrades 5 -> 10 -> 15 -> 30 rather than stopping, because a
// thirty-minute-old price still clears the frozen 45-minute staleness limit; and
// below a hard floor it stops entirely rather than spending a credit that does
// not exist.
//
// No paid tier, ever, without an L3. The governor exists so that stays true
// without anyone having to watch it.
const MONTHLY_CREDIT_CAP = Number(process.env.ODDS_MONTHLY_CAP || 500);
// Standing reserve: one baseline capture a day for a whole month (~30) plus
// headroom for retries and manual FORCE runs. Held back before any card is
// budgeted, so a busy month cannot eat the days between cards.
//
// 75, not 45. Walked across months of 1 through 8 cards, a 45-credit reserve
// goes eight credits over the allowance at seven cards; 75 leaves a worst case
// of +19. The cost of the larger reserve is that a busy month coarsens its
// cadence sooner — lead time, not correctness.
const CREDIT_RESERVE = Number(process.env.ODDS_CREDIT_RESERVE || 75);
const CREDIT_HARD_FLOOR = 10;
const LIVE_CADENCE_LADDER = [5, 10, 15, 30];
const WAKE_INTERVAL_MIN = 5;              // must match the cron in odds.yml
const TOTALS_MIN_INTERVAL_MIN = 30;       // DUR-001 keeps its density, not more

// What one card costs at the COARSEST rung — 30-minute flow capture plus the
// card day's hourly captures outside the flow window. Measured by walking a card
// day through shouldCaptureNow at the 30-minute rung.
//
// It has to be reserved for every card still to come, not just averaged in.
// Without it the governor spends generously on the first cards of a busy month
// and arrives at the last one with nothing — which is how a six-card month went
// eight credits over the allowance in testing before this line existed.
const MIN_CARD_COST = 35;

// A card day also costs hourly captures outside the flow window — the hours
// before the lead-in opens and after the card is over. Measured at ~15. The
// projection has to include it: budgeting only the flow calls understates a
// card by that much, and four cards' worth of understatement is a blown
// allowance.
const CARD_DAY_HOURLY_TAIL = 15;

// The finest affordable cadence for the rest of this card, or null to stop.
// Pure — build/test-fetch-odds.js walks whole months through it.
function planLiveCadence({ creditsRemaining, cardsRemaining, minutesRemainingInCard }) {
  if (!Number.isFinite(creditsRemaining)) {
    // Unknown budget is treated as tight, not as unlimited. The usage ledger is
    // unreadable on a fresh database and on the first run of the month, and
    // guessing generously there is how a free tier turns into a bill.
    //
    // The coarsest rung is safe here without a fit check, and provably so: a
    // month spent entirely at 30 minutes costs ~35 credits a card, so even eight
    // cards plus daily baselines sit far inside the allowance. The test
    // 'the coarsest rung alone can never exhaust the allowance' pins that, which
    // is what makes this branch defensible rather than hopeful.
    return LIVE_CADENCE_LADDER[LIVE_CADENCE_LADDER.length - 1];
  }
  if (creditsRemaining <= CREDIT_HARD_FLOOR) return null;
  // What this card may spend: what is left, less the standing reserve, less the
  // floor cost of every card that still has to happen after it.
  const laterCards = Math.max(0, (cardsRemaining ?? 1) - 1);
  const perCard = Math.max(
    0, creditsRemaining - CREDIT_RESERVE - MIN_CARD_COST * laterCards);
  for (const minutes of LIVE_CADENCE_LADDER) {
    const calls = Math.ceil(Math.max(0, minutesRemainingInCard) / minutes)
      + CARD_DAY_HOURLY_TAIL;
    if (calls <= perCard) return minutes;
  }
  // NOTHING on the ladder fits. Stop.
  //
  // This used to fall through to the coarsest rung, which quietly converted "we
  // cannot afford any cadence" into "spend at 30 minutes anyway" — a ceiling
  // with a hole in it, and the hole opened exactly when the budget was tightest.
  // A ceiling that yields under pressure is not a ceiling.
  //
  // Stopping loses the rest of this card's capture. Overspending would mean paid
  // usage, which is an L3 decision and not one a scheduled job gets to make.
  return null;
}

// How long after a card's scheduled start it can still be running. Prelims to
// main event is about five hours; seven is a generous ceiling that bounds the
// spend if a completion signal never arrives. It is a CAPTURE bound, not a
// measurement rule — it decides how much data exists, never what a number means,
// so it is tunable without an amendment.
const EVENT_FLOW_MAX_H = Number(process.env.EVENT_FLOW_MAX_H || 7);

// -----------------------------------------------------------------------------
// Event flow (CLV-001 Amendment 3)
// -----------------------------------------------------------------------------
// A card is one scheduled start and then a queue. The published commence time
// belongs to the FIRST bout; every later bout begins when the one before it
// ends. So "capture near the bell" cannot mean "capture near the one timestamp
// we were given" — that timestamp is right for one fight out of thirteen.
//
// Instead the card enters FLOW at its scheduled start and stays in flow until
// its last bout is done (or the ceiling above, whichever comes first). Through
// the flow the job captures every 30 minutes, which is what gives each fight in
// the queue a quote inside the 45-minute staleness limit of its own start.
//
// The previous bout ending is a TRIGGER here and nothing more. It sharpens which
// fight we are capturing for; it does not decide any fight's closing price. The
// close is the last valid pre-live quote for the upcoming fight, decided in
// cfl_engine/clv/scoring.py against v_clv_close_reference.

// Is a card currently running? Lead-in counts too: NEAR_BELL_WINDOW_H before the
// scheduled start, so the opening bout has a fresh quote of its own.
//
// ONLY a real schedule counts. DUR-001's v_fight_start_best always answers,
// falling back to the event date at 18:00 UTC, so a caller reading start_at
// without start_basis would burst-capture against a placeholder for every fight
// ever recorded.
function nearBellWindow(candidateFights, now = new Date(), windowH = NEAR_BELL_WINDOW_H) {
  const t = now.getTime();
  return (candidateFights || []).some(f => {
    if (!f.start_at) return false;
    if (!['bell_at', 'provider_commence'].includes(f.start_basis)) return false;
    const s = new Date(f.start_at).getTime();
    if (f.card_complete) return false;          // the night is over, stop spending
    // Lead-in before the scheduled start, then the whole flow window after it.
    return s > t - EVENT_FLOW_MAX_H * 3600000 && s < t + windowH * 3600000;
  });
}

// Which fight the capture is currently FOR, given what has finished. Used for
// logging and for stamping bout_started_at; it does not gate anything, because
// the job captures the whole slate in one request either way.
//
// `completed_at` comes from the fight_bout_completions ledger and is only ever
// an EXACT observation — never the result scraper's "we first saw a winner at
// T", which is completion plus unknown lag. An upper bound used here would mark
// the next fight as started too late and admit in-play quotes as its close.
function currentBout(cardFights, now = new Date()) {
  const ordered = (cardFights || [])
    .filter(f => Number.isInteger(f.bout_order))
    .sort((a, b) => a.bout_order - b.bout_order);
  if (!ordered.length) return null;
  const t = now.getTime();
  for (const f of ordered) {
    if (!f.completed_at || new Date(f.completed_at).getTime() > t) return f;
  }
  return null;                                   // every bout on the card is done
}

// The best account, at capture time, of when a fight began — the value stamped
// into fight_odds.bout_started_at, and what is_live is keyed to.
//
//   1. an actual confirmed bell
//   2. the previous bout's exact completion
//   3. the card's scheduled start — FIRST BOUT ONLY
//   else null, meaning unknown. Never a guess, and never the card's scheduled
//   start applied to a later bout: that would sit hours early and mark every
//   real quote in between as in-play.
function boutStartedAt(fight, prevCompletedAt, scheduledFirstBoutAt) {
  if (fight && fight.bell_at) return new Date(fight.bell_at).toISOString();
  if (prevCompletedAt) return new Date(prevCompletedAt).toISOString();
  if (fight && fight.bout_order === 1 && scheduledFirstBoutAt) {
    return new Date(scheduledFirstBoutAt).toISOString();
  }
  return null;
}

// Minutes of card still to run — how much 5-minute capture is still owed. Used
// only by the budget governor, so an over-estimate costs cadence, never data.
function minutesRemainingInCard(candidateFights, now = new Date()) {
  const t = now.getTime();
  let latest = 0;
  for (const f of candidateFights || []) {
    if (!f.start_at) continue;
    if (!['bell_at', 'provider_commence'].includes(f.start_basis)) continue;
    const end = new Date(f.start_at).getTime() + EVENT_FLOW_MAX_H * 3600000;
    if (end > latest) latest = end;
  }
  return latest <= t ? 0 : Math.round((latest - t) / 60000);
}

// The cadence decision for one wake-up. Pure, so build/test-fetch-odds.js can
// walk whole months through it and count the credits.
//
// `budget` is { creditsRemaining, cardsRemaining }. Omit it and the governor
// treats the budget as unknown, which means tight — see planLiveCadence.
function shouldCaptureNow(candidateFights, now, hasCardInWindow, budget = {}) {
  const min = now.getUTCMinutes();
  if (nearBellWindow(candidateFights, now)) {
    const cadence = planLiveCadence({
      creditsRemaining: budget.creditsRemaining,
      cardsRemaining: budget.cardsRemaining ?? 1,
      minutesRemainingInCard: budget.minutesRemainingInCard
        ?? minutesRemainingInCard(candidateFights, now),
    });
    if (cadence === null) {
      return { yes: false, cadence: null,
               why: `no cadence fits the remaining budget ` +
                    `(${budget.creditsRemaining ?? 'unknown'} credit(s) left, ` +
                    `${budget.cardsRemaining ?? 1} card(s) still to cover) — ` +
                    `capture stopped rather than spending past the free allowance` };
    }
    if (min % cadence < WAKE_INTERVAL_MIN) {
      return { yes: true, cadence,
               why: `card in flow — ${cadence}-minute cadence` +
                    (cadence === LIVE_CADENCE_LADDER[0] ? '' : ' (budget-degraded)') };
    }
    return { yes: false, cadence, why: `card in flow but off the ${cadence}-minute beat` };
  }
  if (hasCardInWindow) {
    if (min < WAKE_INTERVAL_MIN) {
      return { yes: true, cadence: 60, why: 'card today or tomorrow — hourly cadence' };
    }
    return { yes: false, cadence: 60, why: 'card window but not the top of the hour' };
  }
  if (now.getUTCHours() === BASELINE_HOUR_UTC && min < WAKE_INTERVAL_MIN) {
    return { yes: true, cadence: 1440, why: 'daily baseline capture' };
  }
  return { yes: false, cadence: null,
           why: 'no card today or tomorrow and not the baseline hour' };
}

// The authoritative credit count is the Odds API's own x-requests-remaining
// header. Each run stores it so the NEXT run — a separate Actions invocation
// with no shared memory — can gate BEFORE calling. An unreadable or empty ledger
// yields null, which planLiveCadence treats as tight rather than unlimited.
async function readCreditBudget(now) {
  const { data, error } = await sb
    .from('odds_api_usage')
    .select('requests_remaining, observed_at')
    .order('observed_at', { ascending: false })
    .limit(1);
  if (error) {
    console.warn(`[budget] odds_api_usage unavailable (${error.message}) — ` +
      `treating the budget as unknown, which means tight. Apply ` +
      `research/clv/proposed_2026-09-16_event_flow.sql.`);
    return { creditsRemaining: undefined, cardsRemaining: 1 };
  }
  const last = (data || [])[0];

  // The provider resets the allowance monthly. A reading from a previous month
  // tells us nothing about this one, so it is discarded rather than trusted.
  let creditsRemaining;
  if (last && last.observed_at &&
      last.observed_at.slice(0, 7) === now.toISOString().slice(0, 7)) {
    creditsRemaining = Number(last.requests_remaining);
  } else if (last) {
    console.log('[budget] last usage reading is from a previous month — the ' +
      'allowance has reset; assuming a full cap until this month\'s first call.');
    creditsRemaining = MONTHLY_CREDIT_CAP;
  }

  // How many cards still have to be paid for out of what is left.
  const monthEnd = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 0))
    .toISOString().slice(0, 10);
  const { data: rest } = await sb
    .from('events')
    .select('id')
    .gte('event_date', now.toISOString().slice(0, 10))
    .lte('event_date', monthEnd);
  const cardsRemaining = Math.max(1, (rest || []).length);

  return { creditsRemaining, cardsRemaining };
}

// Record what the provider says we have left. Append-only; a failure here must
// never take the capture down, but it does mean the next run flies blind and
// therefore conservatively.
async function recordCreditUsage(used, remaining) {
  if (remaining == null) return;
  const { error } = await sb.from('odds_api_usage').insert([{
    requests_used: used == null ? null : Number(used),
    requests_remaining: Number(remaining),
    observed_at: new Date().toISOString(),
  }]);
  if (error) console.warn(`[budget] could not record usage: ${error.message}`);
}

async function shouldSpendCredit(candidateFights) {
  const now = new Date();
  if (process.env.FORCE) {
    // FORCE overrides the CADENCE, never the CEILING. A hand-fired run is
    // allowed to ignore the beat so "is this thing on?" is never a silent skip;
    // it is not allowed to spend a credit the allowance does not have.
    const { creditsRemaining } = await readCreditBudget(now);
    if (Number.isFinite(creditsRemaining) && creditsRemaining <= CREDIT_HARD_FLOOR) {
      console.error(`[cadence] FORCE set, but only ${creditsRemaining} credit(s) ` +
        `remain — at or below the hard floor of ${CREDIT_HARD_FLOOR}. Refusing: ` +
        `the ceiling is not overridable, and going past it means paid usage.`);
      return false;
    }
    console.log(`[cadence] FORCE set — capturing regardless of schedule ` +
      `[${creditsRemaining ?? 'unknown'} credit(s) left]`);
    return true;
  }
  const today = now.toISOString().slice(0, 10);
  const tomorrow = new Date(now.getTime() + 86400000).toISOString().slice(0, 10);

  const { data: near, error } = await sb
    .from('events')
    .select('name, event_date')
    .gte('event_date', today)
    .lte('event_date', tomorrow);
  if (error) throw new Error(`cadence events check: ${error.message}`);

  const budget = await readCreditBudget(now);
  const decision = shouldCaptureNow(candidateFights, now, !!(near && near.length), budget);
  console.log(`[cadence] ${decision.yes ? 'capturing' : 'skipping (0 credits)'} — ${decision.why}` +
    ` [budget: ${budget.creditsRemaining ?? 'unknown'} credit(s) left, ` +
    `${budget.cardsRemaining} card(s) still to cover this month]`);
  return decision.yes;
}

// -----------------------------------------------------------------------------
// 1. Fetch raw odds from The Odds API (one request = whole MMA slate)
// -----------------------------------------------------------------------------

// DUR-001 (2026-09-14): the same request also carries the fight TOTALS market
// (over/under rounds) when wantTotals() says so. Each extra market costs one
// more credit per call (quota = markets x regions), so totals ride along only
// where a close can actually form — see wantTotals(). Totals rows go to the
// private, append-only `prop_odds` ledger; the moneyline path is unchanged.
let lastQuota = { used: null, remaining: null };

async function fetchOddsFromApi(markets = 'h2h') {
  // ODDS_FIXTURE=<path.json>: replay a saved/synthetic Odds API payload instead
  // of spending a credit. Forces DRY_RUN semantics upstream (see main) so a
  // fixture can never reach the database. Used by the DUR-001 ingestion check.
  if (process.env.ODDS_FIXTURE) {
    const fs = require('fs');
    const events = JSON.parse(fs.readFileSync(process.env.ODDS_FIXTURE, 'utf8'));
    console.log(`[odds-api] FIXTURE ${process.env.ODDS_FIXTURE}: ${events.length} events (markets=${markets}; no credit spent)`);
    return events;
  }
  const url = 'https://api.the-odds-api.com/v4/sports/mma_mixed_martial_arts/odds' +
    `?regions=us&markets=${encodeURIComponent(markets)}&oddsFormat=american&dateFormat=iso` +
    `&apiKey=${encodeURIComponent(ODDS_API_KEY)}`;

  // Retry transient failures (network, 429, 5xx) — a lost run here can cost a
  // fight's opener, since openers are first-capture. 4xx (bad key/params) is
  // not retried: the answer won't change and failed calls still show quota use.
  let lastErr;
  for (let attempt = 1; attempt <= 3; attempt++) {
    let res;
    try {
      res = await fetch(url);
    } catch (netErr) {
      lastErr = netErr;
      await new Promise(r => setTimeout(r, 2000 * attempt));
      continue;
    }
    console.log(`[odds-api] HTTP ${res.status} quota: used=${res.headers.get('x-requests-used')}, ` +
      `remaining=${res.headers.get('x-requests-remaining')}, last=${res.headers.get('x-requests-last')}`);
    // The provider's own count is the only authoritative budget. Store it so the
    // next run — a separate Actions invocation — can gate before calling.
    lastQuota = { used: res.headers.get('x-requests-used'),
                  remaining: res.headers.get('x-requests-remaining') };
    if (res.ok) {
      const events = await res.json();
      console.log(`[odds-api] got ${events.length} MMA events`);
      return events;
    }
    lastErr = new Error(`Odds API ${res.status} ${res.statusText}: ${await res.text()}`);
    if (res.status < 500 && res.status !== 429) break;
    await new Promise(r => setTimeout(r, 2000 * attempt));
  }
  throw lastErr;
}

// -----------------------------------------------------------------------------
// 2. Candidate fights (last 7 days through everything scheduled forward)
// -----------------------------------------------------------------------------

async function loadCandidateFights() {
  const cutoff = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);

  const { data: events, error: evErr } = await sb
    .from('events')
    .select('id, event_date')
    .gte('event_date', cutoff);
  if (evErr) throw new Error(`events fetch: ${evErr.message}`);
  if (!events || events.length === 0) {
    console.log('[supabase] no candidate events in the recent/upcoming window');
    return [];
  }

  const ids = events.map(e => e.id);
  const { data: fights, error: fErr } = await sb
    .from('fights')
    .select('id, event_id, fighter_a_id, fighter_b_id, fighter_a_name, fighter_b_name, bell_at')
    .in('event_id', ids);
  if (fErr) throw new Error(`fights fetch: ${fErr.message}`);
  console.log(`[supabase] ${fights ? fights.length : 0} candidate fights across ${events.length} events`);

  // Best-known start time per fight (bell_at > provider commence > event-date
  // fallback), from the DUR-001 start hierarchy view. Used by wantTotals() and
  // promoteClosers(). Missing view (migration not applied) => empty map.
  const byDate = new Map(events.map(e => [e.id, e.event_date]));
  const { data: starts, error: sErr } = await sb
    .from('v_fight_start_best')
    .select('fight_id, start_at, start_basis')
    .in('fight_id', (fights || []).map(f => f.id));
  if (sErr) console.warn(`[start] v_fight_start_best unavailable (${sErr.message}) — apply dur001_migration.sql`);
  const startById = new Map((starts || []).map(s => [s.fight_id, s]));
  for (const f of fights || []) {
    f.event_date = byDate.get(f.event_id) || null;
    const s = startById.get(f.id);
    f.start_at = s ? s.start_at : null;
    f.start_basis = s ? s.start_basis : null;
  }

  await attachEventFlow(fights || []);
  return fights || [];
}

// Running order and bout completions (CLV-001 Amendment 3). Both ledgers are
// append-only and both may be absent — the migration that creates them is
// proposed, not applied — so every field here degrades to null and the capture
// falls back to the card-level cadence it had before. A missing ledger costs
// coverage; it never costs correctness, because an unknown bout start produces
// is_live = null, and null is never treated as "pre-start".
async function attachEventFlow(fights) {
  if (!fights.length) return;
  const ids = fights.map(f => f.id);

  const { data: order, error: oErr } = await sb
    .from('fight_bout_order')
    .select('fight_id, event_id, bout_order, observed_at')
    .in('fight_id', ids)
    .order('observed_at', { ascending: false });
  if (oErr) {
    console.warn(`[flow] fight_bout_order unavailable (${oErr.message}) — running ` +
      `order unknown, so no fight can be identified as the card's first bout. ` +
      `Apply research/clv/proposed_2026-09-16_event_flow.sql.`);
  }
  const orderBy = new Map();
  for (const o of order || []) {
    if (!orderBy.has(o.fight_id)) orderBy.set(o.fight_id, o);  // latest wins
  }

  // is_exact only. The result scraper's "we first saw a winner at T" is
  // completion PLUS unknown lag; using it would place the next bout's start too
  // late and admit in-play quotes as its close.
  const { data: done, error: cErr } = await sb
    .from('fight_bout_completions')
    .select('fight_id, completed_at')
    .in('fight_id', ids)
    .eq('is_exact', true);
  if (cErr) {
    console.warn(`[flow] fight_bout_completions unavailable (${cErr.message}) — ` +
      `no bout completions, so only a card's first bout can ever be scored.`);
  }
  const doneBy = new Map();
  for (const c of done || []) {
    const prev = doneBy.get(c.fight_id);
    if (!prev || c.completed_at > prev) doneBy.set(c.fight_id, c.completed_at);
  }

  // event -> bout_order -> fight_id, so "the bout before this one" is a lookup
  // rather than an assumption about id ordering.
  const byEventOrder = new Map();
  for (const f of fights) {
    const o = orderBy.get(f.id);
    f.bout_order = o ? o.bout_order : null;
    f.completed_at = doneBy.get(f.id) || null;
    if (o) byEventOrder.set(`${o.event_id}|${o.bout_order}`, f.id);
  }
  for (const f of fights) {
    const o = orderBy.get(f.id);
    f.prev_completed_at = null;
    if (o && o.bout_order > 1) {
      const prevId = byEventOrder.get(`${o.event_id}|${o.bout_order - 1}`);
      if (prevId) f.prev_completed_at = doneBy.get(prevId) || null;
    }
  }

  // A card is finished when every bout on it has an exact completion. Used only
  // to stop spending credits on a night that is over.
  const cardFights = new Map();
  for (const f of fights) {
    if (!f.event_id) continue;
    if (!cardFights.has(f.event_id)) cardFights.set(f.event_id, []);
    cardFights.get(f.event_id).push(f);
  }
  for (const [, group] of cardFights) {
    const complete = group.length > 0 && group.every(f => f.completed_at);
    for (const f of group) f.card_complete = complete;
  }

  const withOrder = fights.filter(f => Number.isInteger(f.bout_order)).length;
  console.log(`[flow] running order known for ${withOrder}/${fights.length} candidate ` +
    `fight(s); ${doneBy.size} exact bout completion(s) on file`);
}

// Reduce a normalized name to first + last token only, so middle names don't
// block a match ("ian machado garry" -> "ian garry" to meet the Odds API's
// "Ian Garry"). Single-token names pass through unchanged.
function firstLast(normalized) {
  const t = normalized.split(' ').filter(Boolean);
  return t.length <= 1 ? normalized : `${t[0]} ${t[t.length - 1]}`;
}

// Third-tier key: the normalized name with every space removed, so word-break
// drift between sources ("JooSang Yoo" vs "Joo Sang Yoo", "DeLima" vs
// "De Lima") still matches. Symmetric, and stricter than first+last because
// every letter has to agree.
function squash(normalized) {
  return normalized.replace(/ /g, '');
}

function pairKey(a, b) {
  return [a, b].sort().join('||');
}

// Index fights by sorted normalized name pair, regardless of which fighter the
// Odds API calls home vs away. Keep two indexes: a strict full-name one and a
// looser first+last one used only as a fallback.
function buildFightIndex(fights) {
  const strict = {};
  const loose = {};
  const squashed = {};
  for (const f of fights) {
    if (!f.fighter_a_name || !f.fighter_b_name) continue;
    const a = normalizeName(f.fighter_a_name);
    const b = normalizeName(f.fighter_b_name);
    strict[pairKey(a, b)] = f;
    const lk = pairKey(firstLast(a), firstLast(b));
    if (!(lk in loose)) loose[lk] = f; // first writer wins; ambiguous keys stay put
    const sk = pairKey(squash(a), squash(b));
    if (!(sk in squashed)) squashed[sk] = f;
  }
  return { strict, loose, squashed };
}

function lookupFight(index, homeName, awayName) {
  const a = normalizeName(homeName);
  const b = normalizeName(awayName);
  return index.strict[pairKey(a, b)]
    || index.loose[pairKey(firstLast(a), firstLast(b))]
    || index.squashed[pairKey(squash(a), squash(b))]
    || null;
}

// -----------------------------------------------------------------------------
// 3. Book directory — resolve Odds API book titles to odds_books.id,
//    creating any we haven't seen before.
// -----------------------------------------------------------------------------

async function resolveBooks(oddsEvents) {
  // distinct {title, key} pairs present in this slate
  const seen = new Map(); // normalized title -> { title, key }
  for (const e of oddsEvents) {
    for (const bm of e.bookmakers || []) {
      if (!bm.title) continue;
      const n = bm.title.trim().toLowerCase();
      if (!seen.has(n)) seen.set(n, { title: bm.title.trim(), key: bm.key || null });
    }
  }

  const { data: existing, error } = await sb.from('odds_books').select('id, name');
  if (error) throw new Error(`odds_books fetch: ${error.message}`);
  const byName = new Map((existing || []).map(b => [b.name.trim().toLowerCase(), b.id]));

  // Insert any missing books (uniform keys → DB defaults apply; name is UNIQUE
  // so ignoreDuplicates guards against a concurrent insert).
  const missing = [...seen.values()].filter(b => !byName.has(b.title.toLowerCase()));
  if (missing.length) {
    const { error: insErr } = await sb
      .from('odds_books')
      .upsert(missing.map(b => ({ name: b.title, short_code: b.key })),
              { onConflict: 'name', ignoreDuplicates: true });
    if (insErr) throw new Error(`odds_books insert: ${insErr.message}`);
    console.log(`[books] added ${missing.length} new book(s): ${missing.map(b => b.title).join(', ')}`);

    const { data: refreshed, error: reErr } = await sb.from('odds_books').select('id, name');
    if (reErr) throw new Error(`odds_books re-fetch: ${reErr.message}`);
    byName.clear();
    (refreshed || []).forEach(b => byName.set(b.name.trim().toLowerCase(), b.id));
  }
  return byName; // normalized name -> book_id
}

// -----------------------------------------------------------------------------
// 3b. Start times — the only thing that makes "the close" mean anything
// -----------------------------------------------------------------------------
// ufcstats gives us an event DATE and no start time. The Odds API gives a
// per-fight commence_time, and it is the only source we have for one today.
// It is a PROVIDER ESTIMATE, not the bell, so it is recorded in the append-only
// fight_start_estimates ledger (source 'odds_api_commence'), never written into
// fights.bell_at — that column stays reserved for a confirmed actual bell.
// v_fight_start_best resolves bell_at > latest provider commence > event-date
// fallback, and settlement defines the close as the last non-live capture
// STRICTLY BEFORE that start, rather than "the newest row we happen to hold" —
// which is how post-settlement sentinel prices (-199900 / +199900) end up
// flagged as closers and poison CLV.
//
// Duplicate observations (same fight, same commence) are no-ops via the ledger's
// unique index; a reschedule appends a new row and becomes the latest estimate.

async function recordStartEstimates(commenceByFight) {
  if (!commenceByFight.size) return;
  const rows = [...commenceByFight.entries()].map(([fight_id, start_at]) => ({
    fight_id, source: 'odds_api_commence', start_at,
  }));
  const { error } = await sb
    .from('fight_start_estimates')
    .upsert(rows, { onConflict: 'fight_id,source,start_at', ignoreDuplicates: true });
  if (error) {
    // Ledger missing (migration not applied) must not take the moneyline
    // capture down with it.
    console.warn(`[start] fight_start_estimates write failed: ${error.message}`);
    return;
  }
  console.log(`[start] recorded provider commence for ${rows.length} fight(s) (duplicates ignored)`);
}

// -----------------------------------------------------------------------------
// 3c. Closer promotion — one closing price per (fight, fighter, book)
// -----------------------------------------------------------------------------
// Openers are known at capture time; closers are not, because we cannot know a
// capture is the last one until the bell rings. So this runs after the fact:
// for every fight whose bell has passed, the latest capture before the bell
// becomes that book's closer, and anything else loses the flag.
//
// It CLEARS as well as sets, deliberately. The Polymarket scraper marks its
// newest row as the closer whether or not the fight has started, so its flag
// walks forward into post-fight captures. Left alone, that is a closing price
// taken after the result was known.
//
// Fights with no real start time (no bell_at and no provider commence — i.e.
// only the event-date fallback) are never touched — that leaves the BFO-era
// history (book 6, closers set by the backfill) exactly as it is.
//
// This flag only exists on the moneyline table. prop_odds never stores a closer
// flag: its close is computed by v_prop_odds_lifecycle from the same start
// hierarchy, so it can be recomputed when better start times arrive.

const CLOSER_LOOKBACK_DAYS = 21;

async function promoteClosers(candidateFights) {
  const now = Date.now();
  const floor = now - CLOSER_LOOKBACK_DAYS * 86400000;
  const due = (candidateFights || []).filter(f => {
    if (!f.start_at || !['bell_at', 'provider_commence'].includes(f.start_basis)) return false;
    const t = new Date(f.start_at).getTime();
    return t < now && t > floor;
  });
  if (!due.length) return;

  let promoted = 0, demoted = 0;
  for (const f of due) {
    const bell = new Date(f.start_at).toISOString();
    const { data: caps, error } = await sb
      .from('fight_odds')
      .select('id, fighter_id, book_id, captured_at, is_closer')
      .eq('fight_id', f.id);
    if (error) throw new Error(`closer scan (fight ${f.id}): ${error.message}`);
    if (!caps || !caps.length) continue;

    // Winner per (fighter, book): latest capture strictly before the bell.
    const best = new Map();
    for (const c of caps) {
      if (!(c.captured_at < bell)) continue;
      const k = `${c.fighter_id}|${c.book_id}`;
      const cur = best.get(k);
      if (!cur || c.captured_at > cur.captured_at) best.set(k, c);
    }
    const keep = new Set([...best.values()].map(c => c.id));

    const toSet = [...keep].filter(id => !caps.find(c => c.id === id).is_closer);
    const toClear = caps.filter(c => c.is_closer && !keep.has(c.id)).map(c => c.id);

    if (toSet.length) {
      const { error: e1 } = await sb
        .from('fight_odds').update({ is_closer: true }).in('id', toSet);
      if (e1) throw new Error(`closer set (fight ${f.id}): ${e1.message}`);
      promoted += toSet.length;
    }
    if (toClear.length) {
      const { error: e2 } = await sb
        .from('fight_odds').update({ is_closer: false }).in('id', toClear);
      if (e2) throw new Error(`closer clear (fight ${f.id}): ${e2.message}`);
      demoted += toClear.length;
    }
  }
  if (promoted || demoted) {
    console.log(`[closers] ${due.length} fight(s) past the bell: promoted ${promoted} ` +
      `capture(s), cleared ${demoted} stale/post-bell flag(s)`);
  }
}

// -----------------------------------------------------------------------------
// 3d. Fight totals (DUR-001) — over/under rounds, appended to prop_odds
// -----------------------------------------------------------------------------
// Every quote is one immutable row: (fight, book, line, captured_at) with both
// prices, the provider's commence time as seen at capture, a live flag
// (captured at/after commence => in-play, never a close) and the raw provider
// metadata. No opener/closer flags are stored: v_prop_odds_lifecycle derives
// them from the start hierarchy, so they can be recomputed later.
//
// Credit budget. Totals add one credit per call. They are requested when:
//   * FORCE=1 (manual run), or
//   * a candidate fight's best-known start is within TOTALS_HOURLY_WINDOW_H
//     hours (hourly density right where the close forms), or
//   * it is an even UTC hour inside the card window, or
//   * it is the daily baseline hour (so opening lines are on file for the
//     Phase-8 opener test).
// Set ODDS_MARKETS to override entirely (e.g. 'h2h' to switch totals off).
const TOTALS_HOURLY_WINDOW_H = Number(process.env.TOTALS_HOURLY_WINDOW_H || 6);
const TOTALS_ENABLED = (process.env.ODDS_MARKETS || 'h2h,totals').split(',').map(s => s.trim()).includes('totals');

function wantTotals(candidateFights, now = new Date()) {
  if (!TOTALS_ENABLED) return { yes: false, why: 'totals disabled via ODDS_MARKETS' };
  if (process.env.FORCE) return { yes: true, why: 'FORCE set' };
  // Totals cost a second credit on every call they ride. Under 5-minute h2h
  // capture that would double the card's bill for no benefit to DUR-001, whose
  // close is derived from the same start hierarchy and needs density, not every
  // five minutes. Capped at one totals call per TOTALS_MIN_INTERVAL_MIN, which
  // is the density DUR-001 already had — never less.
  if (now.getUTCMinutes() % TOTALS_MIN_INTERVAL_MIN >= WAKE_INTERVAL_MIN) {
    return { yes: false, why: `off the ${TOTALS_MIN_INTERVAL_MIN}-minute totals beat ` +
                              `(h2h-only call, 1 credit)` };
  }
  const t = now.getTime();
  const near = (candidateFights || []).some(f => {
    if (!f.start_at) return false;
    const s = new Date(f.start_at).getTime();
    return s > t - 3600000 && s < t + TOTALS_HOURLY_WINDOW_H * 3600000;
  });
  if (near) return { yes: true, why: `a fight starts within ${TOTALS_HOURLY_WINDOW_H}h` };
  if (now.getUTCHours() === BASELINE_HOUR_UTC) return { yes: true, why: 'daily baseline hour' };
  const today = now.toISOString().slice(0, 10);
  const tomorrow = new Date(t + 86400000).toISOString().slice(0, 10);
  const cardWindow = (candidateFights || []).some(f => f.event_date === today || f.event_date === tomorrow);
  if (cardWindow && now.getUTCHours() % 2 === 0) return { yes: true, why: 'even hour in the card window' };
  return { yes: false, why: cardWindow ? 'odd hour in the card window' : 'no card in window' };
}

// One prop_odds row per (book, line) for a matched Odds API event.
function buildTotalsRows(e, fight, bookId, captured_at) {
  const rows = [];
  const commence = e.commence_time ? new Date(e.commence_time).toISOString() : null;
  const is_live = !!(commence && captured_at >= commence);
  for (const bm of e.bookmakers || []) {
    const bid = bookId.get((bm.title || '').trim().toLowerCase());
    if (!bid) continue;
    for (const m of bm.markets || []) {
      if (m.key !== 'totals' || !Array.isArray(m.outcomes)) continue;
      // Group Over/Under by line (books can post alternates; keep each pair).
      const byLine = new Map();
      for (const o of m.outcomes) {
        if (o.point == null || o.price == null) continue;
        const k = String(o.point);
        if (!byLine.has(k)) byLine.set(k, { point: Number(o.point) });
        const slot = byLine.get(k);
        const nm = String(o.name || '').toLowerCase();
        if (nm === 'over') slot.over = Math.round(o.price);
        else if (nm === 'under') slot.under = Math.round(o.price);
      }
      for (const slot of byLine.values()) {
        if (slot.over == null || slot.under == null || !(slot.point > 0)) continue;
        rows.push({
          fight_id: fight.id,
          event_id: fight.event_id,
          event_date: fight.event_date,
          market_type: 'total_rounds',
          fighter_id: null,
          line: slot.point,
          over_odds: slot.over,
          under_odds: slot.under,
          book_id: bid,
          source: 'odds_api',
          source_event_id: e.id || null,
          captured_at,
          source_commence_at: commence,
          is_live,
          raw: { bookmaker_key: bm.key || null, bookmaker_last_update: bm.last_update || null,
                 market_last_update: m.last_update || null, home_team: e.home_team, away_team: e.away_team },
        });
      }
    }
  }
  return rows;
}

// -----------------------------------------------------------------------------
// 3e. Moneyline rows (CLV-001) — one row per (fight, fighter, book)
// -----------------------------------------------------------------------------
// Pure: no database, no clock of its own, no network. build/test-fetch-odds.js
// exercises it against a fixture, which is how the capture path gets verified
// before the migration that stores its output is applied anywhere.
//
// The h2h path used to throw away everything the totals path keeps. Same loop,
// same payload, same provider metadata — and the moneyline rows recorded a price
// and a timestamp and nothing else. That asymmetry is the whole reason CLV-001's
// capture requirements read as unmet: the mechanism was already running in the
// next table over. These fields are named exactly as prop_odds names them.
//
// Columns added by research/clv/proposed_2026-09-16_fight_odds_capture.sql. Until
// that is applied, CAPTURE_COLUMNS are stripped before the insert — see
// detectCaptureColumns(). The capture degrades, it never fails and it never
// half-writes.

const CAPTURE_COLUMNS = [
  'source_event_id', 'feed_version', 'source_commence_at', 'bout_started_at',
  'is_live', 'provider_last_update', 'retrieved_at', 'opponent_fighter_id',
  'market_status', 'raw',
];

function buildMoneylineRows(e, fight, bookId, captured_at, retrieved_at) {
  const rows = [];
  const commence = e.commence_time ? new Date(e.commence_time).toISOString() : null;

  // Amendment 3: liveness is PER FIGHT, keyed to when THIS bout began — not to
  // the card's commence time. Keying it to the card would mark every quote taken
  // after the first bell as in-play for all thirteen fights and throw away
  // exactly the quotes the later fights close on.
  //
  // null is a third state and means "we do not know when this fight started",
  // which on a card whose running order or bout completions are unrecorded is
  // the truth. It is never collapsed to false: false asserts the quote was
  // pre-start, and that is a fact we would not have.
  const bout_started_at = boutStartedAt(fight, fight.prev_completed_at,
                                        fight.bout_order === 1 ? commence : null);
  const is_live = bout_started_at ? captured_at >= bout_started_at : null;

  const nA = normalizeName(fight.fighter_a_name), flA = firstLast(nA);
  const nB = normalizeName(fight.fighter_b_name), flB = firstLast(nB);

  for (const bm of e.bookmakers || []) {
    const h2h = (bm.markets || []).find(m => m.key === 'h2h');
    if (!h2h || !Array.isArray(h2h.outcomes)) continue;
    const bid = bookId.get((bm.title || '').trim().toLowerCase());
    if (!bid) continue;

    // Map each outcome to our canonical A/B by NAME, not by the provider's
    // home/away order, tolerating middle-name drift via the first+last fallback.
    for (const o of h2h.outcomes) {
      if (o.price == null) continue;
      const n = normalizeName(o.name);
      let side, fighter_id, opponent_fighter_id;
      if (n === nA || firstLast(n) === flA || squash(n) === squash(nA)) {
        side = 'A'; fighter_id = fight.fighter_a_id; opponent_fighter_id = fight.fighter_b_id;
      } else if (n === nB || firstLast(n) === flB || squash(n) === squash(nB)) {
        side = 'B'; fighter_id = fight.fighter_b_id; opponent_fighter_id = fight.fighter_a_id;
      } else {
        continue; // draw / unexpected label
      }
      rows.push({
        fight_id: fight.id,
        fighter_id,
        book_id: bid,
        side,
        american_odds: Math.round(o.price),
        implied_prob: Number(americanToImplied(o.price).toFixed(6)),
        captured_at,
        source_url: SOURCE_TAG,
        // Explicit on EVERY row. PostgREST bulk inserts union the keys of all
        // rows and send NULL for any a row lacks, which overrides the column
        // default and trips NOT NULL — this is what killed every scheduled run
        // from 2026-07-31 to 2026-09-15 (rows flipped to true later in main).
        is_opener: false,

        // ---- CLV-001 §4 capture requirements, none of them backfillable ----
        source_event_id: e.id || null,              // item 9  — provider market id
        feed_version: FEED_VERSION,                 // item 6  — feed + shape
        source_commence_at: commence,               // item 7  — the CARD's schedule
        bout_started_at,                            // item 7  — when THIS bout began
        is_live,                                    //         — in-play, never a close
        provider_last_update: bm.last_update        // item 11 — when the BOOK moved
          ? new Date(bm.last_update).toISOString() : null,
        retrieved_at,                               // item 11 — when WE looked
        opponent_fighter_id,                        // item 10 — what the price referred to
        market_status: marketStatusOf(bm, h2h),     // item 8  — open/suspended/taken down
        raw: {                                      // item 12 — link back to the source
          bookmaker_key: bm.key || null,
          bookmaker_last_update: bm.last_update || null,
          market_last_update: h2h.last_update || null,
          home_team: e.home_team,
          away_team: e.away_team,
          outcome_name: o.name,
        },
      });
    }
  }
  return rows;
}

// The Odds API does not report suspension directly: a book that has pulled a
// market simply stops appearing in the payload. So the only honest values here
// are 'open' (it quoted) and null (it said nothing) — 'suspended' and
// 'taken_down' are in the constraint's vocabulary for a provider that does
// report them, and are never guessed from an absence. Inferring 'taken_down'
// from a missing bookmaker would turn "we did not see it" into "it was pulled",
// which is exactly the kind of manufactured fact R-13 is about.
function marketStatusOf(bm, market) {
  if (!market || !Array.isArray(market.outcomes) || market.outcomes.length === 0) return null;
  return 'open';
}

// Strip the CLV-001 capture keys when the migration has not been applied, so an
// un-migrated database keeps capturing exactly what it captured before. Returns
// a NEW array; the originals are left intact for the dry-run printout, which
// should always show what we would ideally store.
function stripUnsupported(rows, supported) {
  const drop = CAPTURE_COLUMNS.filter(c => !supported.has(c));
  if (!drop.length) return rows;
  return rows.map(r => {
    const out = { ...r };
    for (const c of drop) delete out[c];
    return out;
  });
}

// One probe, before any write: which of the capture columns does fight_odds
// actually have? PostgREST rejects a select naming an unknown column, so ask for
// them one at a time and believe the answer.
async function detectCaptureColumns() {
  const supported = new Set();
  for (const col of CAPTURE_COLUMNS) {
    const { error } = await sb.from('fight_odds').select(col).limit(1);
    if (!error) supported.add(col);
  }
  if (supported.size === CAPTURE_COLUMNS.length) {
    console.log('[capture] all CLV-001 capture columns present');
  } else {
    const missing = CAPTURE_COLUMNS.filter(c => !supported.has(c));
    console.warn(`[capture] fight_odds is missing ${missing.length} capture column(s): ` +
      `${missing.join(', ')} — apply research/clv/proposed_2026-09-16_fight_odds_capture.sql. ` +
      `Capturing the legacy columns only; every quote taken meanwhile is ` +
      `permanently unscorable under CLV-001 and cannot be backfilled.`);
  }
  return supported;
}

async function writePropOdds(rows) {
  if (!rows.length) return 0;
  const CHUNK = 500;
  for (let i = 0; i < rows.length; i += CHUNK) {
    const { error } = await sb.from('prop_odds').insert(rows.slice(i, i + CHUNK));
    if (error) throw new Error(`prop_odds insert: ${error.message}`);
  }
  return rows.length;
}

// -----------------------------------------------------------------------------
// 4. Main: fetch, match, build per-book snapshot rows, insert
// -----------------------------------------------------------------------------

async function main() {
  try {
    requireCredentials();

    // Candidate fights FIRST, and free — they come from Supabase, not the Odds
    // API. The cadence gate needs their start times to know whether a bell is
    // near, and wantTotals() needs them to decide on the extra totals credit.
    const candidateFights = await loadCandidateFights();
    if (!(await shouldSpendCredit(candidateFights))) return;
    const totals = wantTotals(candidateFights);
    console.log(`[totals] ${totals.yes ? 'requesting' : 'skipping'} fight totals — ${totals.why}`);
    const oddsEvents = await fetchOddsFromApi(totals.yes ? 'h2h,totals' : 'h2h');

    const fightIndex = buildFightIndex(candidateFights);
    const bookId = await resolveBooks(oddsEvents);

    // retrieved_at is when the payload came back; captured_at stays the row's
    // canonical instant. They are the same value on a normal run and diverge
    // only if the write is delayed — which is exactly the case §4 item 11 wants
    // legible rather than hidden.
    const retrieved_at = new Date().toISOString();
    const captured_at = retrieved_at;
    const rows = [];
    const unmatched = [];
    const commenceByFight = new Map(); // fight_id -> provider commence_time (ISO)
    const totalsRows = [];             // prop_odds rows (DUR-001)
    let matchedFights = 0;

    for (const e of oddsEvents) {
      if (!e.home_team || !e.away_team) continue;

      const fight = lookupFight(fightIndex, e.home_team, e.away_team);
      if (!fight) {
        unmatched.push(`${e.home_team} vs ${e.away_team} (${(e.commence_time || '').slice(0, 10)})`);
        continue;
      }
      if (process.env.DEBUG) {
        console.log(`[match] API "${e.home_team} vs ${e.away_team}" -> fight ${fight.id} (${fight.fighter_a_name} vs ${fight.fighter_b_name})`);
      }

      const mlRows = buildMoneylineRows(e, fight, bookId, captured_at, retrieved_at);
      rows.push(...mlRows);
      const wrote = mlRows.length;
      // Fight totals (DUR-001) — independent of whether h2h matched a price.
      if (totals.yes) totalsRows.push(...buildTotalsRows(e, fight, bookId, captured_at));

      if (wrote > 0) matchedFights++;
      if (wrote > 0 || totals.yes) {
        // Proof that this capture is actually near the bell. The Odds API gives
        // us commence_time, which ufcstats does not — so this is the only place
        // we can see how stale our "closing" price would be if the feed stopped
        // here. Anything over ~120 min on a card day means the hourly cadence
        // isn't landing and CLV is being settled against a stale line.
        if (e.commence_time) {
          commenceByFight.set(fight.id, new Date(e.commence_time).toISOString());
          const mins = Math.round((new Date(e.commence_time) - new Date(captured_at)) / 60000);
          if (mins >= -60 && mins <= 24 * 60) {
            console.log(`[start] fight ${fight.id} (${e.home_team} vs ${e.away_team}) — captured ${mins} min before commence_time`);
          }
        }
      }
    }

    if (unmatched.length) {
      console.warn(`[match] ${unmatched.length} Odds API event(s) had no fight in our DB (non-UFC promotions or name drift):`);
      for (const u of unmatched) console.warn('  - ' + u);
    }

    if (DRY_RUN) {
      console.log(`[dry-run] would record provider commence for ${commenceByFight.size} fight(s), ` +
        `append ${totalsRows.length} totals quote(s) to prop_odds, and promote moneyline closers ` +
        `for any fight past its start.`);
      for (const r of totalsRows.slice(0, 8)) {
        console.log(`  totals fight ${r.fight_id} book ${r.book_id} line ${r.line} ` +
          `O ${r.over_odds > 0 ? '+' : ''}${r.over_odds} / U ${r.under_odds > 0 ? '+' : ''}${r.under_odds}` +
          ` commence ${r.source_commence_at} live=${r.is_live}`);
      }
    } else {
      await recordStartEstimates(commenceByFight);
      // Uses the start times already on file, so this still closes out last
      // night's card on a run where nothing new matched.
      await promoteClosers(candidateFights);
      // Totals are appended before the moneyline path's zero-match guard so a
      // totals-only slate (books post totals late; h2h drift) is never lost.
      const nTotals = await writePropOdds(totalsRows);
      if (nTotals) console.log(`[totals] appended ${nTotals} totals quote(s) to prop_odds at ${captured_at}`);
    }

    if (rows.length === 0) {
      // Zero matches is legitimate in the off-week lull before books post the
      // next card — but during fight week odds always exist, so matching
      // nothing with a card imminent means the matcher or the API feed is
      // broken. Fail loudly instead of silently skipping snapshot windows
      // (openers are first-capture; quiet gaps corrupt them).
      const today = new Date().toISOString().slice(0, 10);
      const soon = new Date(Date.now() + 3 * 86400000).toISOString().slice(0, 10);
      const { data: imminent, error: imErr } = await sb
        .from('events')
        .select('name, event_date')
        .gte('event_date', today)
        .lte('event_date', soon);
      if (imErr) throw new Error(`imminent events check: ${imErr.message}`);
      if (imminent && imminent.length) {
        throw new Error(`matched 0 fights while ${imminent.length} card(s) are within 3 days ` +
          `(${imminent.map(e => e.name).join(', ')}) — matching is broken`);
      }
      console.log('[done] matched 0 fights — nothing to insert (no imminent card, likely off-week)');
      return;
    }

    // ---- consensus rows: median implied prob per (fight, side) across books ----
    let consensusBookId = bookId.get(CONSENSUS_BOOK_NAME.toLowerCase());
    if (!consensusBookId) {
      const { data: cb, error: cbErr } = await sb
        .from('odds_books')
        .upsert([{ name: CONSENSUS_BOOK_NAME, short_code: 'cflc' }],
                { onConflict: 'name', ignoreDuplicates: false })
        .select('id')
        .single();
      if (cbErr) throw new Error(`consensus book upsert: ${cbErr.message}`);
      consensusBookId = cb.id;
    }
    const bySide = new Map(); // fight_id|fighter_id -> { template row, probs[] }
    for (const r of rows) {
      const k = `${r.fight_id}|${r.fighter_id}`;
      if (!bySide.has(k)) bySide.set(k, { r, probs: [] });
      bySide.get(k).probs.push(r.implied_prob);
    }
    for (const { r, probs } of bySide.values()) {
      probs.sort((x, y) => x - y);
      const mid = Math.floor(probs.length / 2);
      const med = probs.length % 2 ? probs[mid] : (probs[mid - 1] + probs[mid]) / 2;
      const american = impliedToAmerican(med);
      if (american == null) continue;
      rows.push({
        fight_id: r.fight_id,
        fighter_id: r.fighter_id,
        book_id: consensusBookId,
        side: r.side,
        american_odds: american,
        implied_prob: Number(med.toFixed(6)),
        captured_at,
        source_url: SOURCE_TAG,
        is_opener: false,
      });
    }

    // ---- opener flagging: first captured price per (fight, side, book) ----
    // A row is the opener if that (fight, fighter, book) combo has never had an
    // opener row before. This is what gives every future pick a locked opening
    // price — the models' ROI accounting depends on it (see model/v6 in the
    // scrapper repo). BFO-era history already carries is_opener on book 6.
    const fightIds = [...new Set(rows.map(r => r.fight_id))];
    const priorOpeners = [];
    for (let from = 0; ; from += 1000) {
      const { data: page, error: poErr } = await sb
        .from('fight_odds')
        .select('fight_id, fighter_id, book_id')
        .in('fight_id', fightIds)
        .eq('is_opener', true)
        .range(from, from + 999);
      if (poErr) throw new Error(`prior openers fetch: ${poErr.message}`);
      priorOpeners.push(...(page || []));
      if (!page || page.length < 1000) break;
    }
    const hasOpener = new Set(priorOpeners.map(o => `${o.fight_id}|${o.fighter_id}|${o.book_id}`));
    let openersMarked = 0;
    for (const r of rows) {
      const k = `${r.fight_id}|${r.fighter_id}|${r.book_id}`;
      if (!hasOpener.has(k)) {
        r.is_opener = true;
        hasOpener.add(k); // one opener per combo per run
        openersMarked++;
      }
    }
    if (openersMarked) console.log(`[openers] marking ${openersMarked} first-capture row(s) as openers`);

    if (DRY_RUN) {
      console.log(`[dry-run] would insert ${rows.length} row(s) across ${matchedFights} fight(s). Sample:`);
      for (const r of rows.slice(0, 12)) {
        console.log(`  fight ${r.fight_id} side ${r.side} book ${r.book_id} ${r.american_odds > 0 ? '+' : ''}${r.american_odds} (p=${r.implied_prob})`);
      }
      return;
    }

    // Snapshot insert (append-only, like the BFO cron). Chunk to stay safe.
    // Capture columns are stripped if the migration has not been applied, so an
    // un-migrated database keeps working exactly as before rather than failing
    // every run on an unknown column.
    const supported = await detectCaptureColumns();
    const toInsert = stripUnsupported(rows, supported);
    const CHUNK = 500;
    for (let i = 0; i < toInsert.length; i += CHUNK) {
      const { error: insErr } = await sb.from('fight_odds').insert(toInsert.slice(i, i + CHUNK));
      if (insErr) throw new Error(`fight_odds insert: ${insErr.message}`);
    }

    await recordCreditUsage(lastQuota.used, lastQuota.remaining);

    const scorable = supported.size === CAPTURE_COLUMNS.length;
    console.log(`[done] inserted ${toInsert.length} snapshot row(s) across ${matchedFights} fight(s) at ${captured_at}` +
      (scorable ? ' — CLV-001 capture complete' : ' — CLV-001 capture INCOMPLETE, these quotes can never be scored'));
  } catch (err) {
    console.error('[fetch-odds] failed:', err.message);
    process.exit(1);
  }
}

// Run when invoked, export when required. build/test-fetch-odds.js requires this
// file to check the pure row builders against a fixture — with no API key, no
// Supabase key and no network — which is how the capture path is verified before
// the migration that stores its output is applied to anything.
if (require.main === module) main();

module.exports = {
  buildMoneylineRows, buildTotalsRows, marketStatusOf, stripUnsupported,
  nearBellWindow, shouldCaptureNow, currentBout, boutStartedAt,
  planLiveCadence, minutesRemainingInCard, wantTotals,
  CAPTURE_COLUMNS, FEED_VERSION, NEAR_BELL_WINDOW_H, NEAR_BELL_INTERVAL_MIN,
  EVENT_FLOW_MAX_H, MONTHLY_CREDIT_CAP, CREDIT_RESERVE, CREDIT_HARD_FLOOR,
  LIVE_CADENCE_LADDER, WAKE_INTERVAL_MIN, TOTALS_MIN_INTERVAL_MIN,
  normalizeName, firstLast, squash, americanToImplied, buildFightIndex, lookupFight,
};
