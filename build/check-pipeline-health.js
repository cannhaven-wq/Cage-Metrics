// =============================================================================
// check-pipeline-health.js — are the jobs that keep CFL current still working?
// =============================================================================
// PLAIN ENGLISH: CFL is kept current by scheduled jobs in three places — GitHub
// Actions, Railway, and Supabase. When one of them stops, nothing on the site
// says so; the numbers just quietly get old. This looks at each one and says
// out loud which have stopped.
//
// WHY, WITH THE RECEIPTS (all found by the 2026-10-12 audit, not by an alarm):
//   - export.yml failed on every scheduled run; nobody read the red tick.
//   - the fighter scraper's Railway builds failed from July onward.
//   - the social poster ran "successfully" while publishing retired copy.
// build/check-pre-fight-coverage.js (the dead man) already watches the
// pre-fight record. This watches everything else that keeps the site fresh.
//
// TWO KINDS OF CHECK
//   workflow  the latest SCHEDULED run of a critical GitHub workflow failed, or
//             there has been no successful scheduled run within its window, or
//             GitHub has disabled the workflow (the 60-day inactivity rule).
//   data      the thing the job writes is visibly stale in the database:
//               - no Odds API sportsbook quote captured within 30 hours;
//               - a card dated 60+ hours ago still has most fights
//                 with no result (the Railway event scraper writes results);
//               - no UFC card on the calendar in the next 14 days (the same
//                 scraper adds upcoming cards).
//             Data checks catch the Railway jobs, which GitHub cannot see.
//
// "I COULD NOT LOOK" IS A FAILURE, as in the dead man: a missing key, a failed
// request, or an unreadable answer exits non-zero rather than reporting health.
//
// WHAT THIS CANNOT SEE
//   - Its own silence (same limit as the dead man; T-076).
//   - The fighter scraper: fighters.updated_at has no trigger behind it, so it
//     is not a freshness signal, and no other column records a profile refresh.
//     Watching that needs a trigger or a scrape-log table first.
//
// The decision logic is pure (assess) and pinned by tests/pipeline-health.test.js.
//
// ENV
//   SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SECRET_KEY) — required; fight_odds
//       is admin-only, so the publishable key would read zero rows and look
//       like a dead odds job.
//   GH_TOKEN, GITHUB_REPOSITORY — required for the workflow checks.
//   HEALTH_NOW — pretend it is this ISO instant (testing).
//   HEALTH_JSON_OUT — write the report here for the issue step.
// =============================================================================

'use strict';

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const H = 3600 * 1000;

// Each critical scheduled workflow and how long it may go without a success.
// Windows are generous on purpose: GitHub delivers schedules late and drops
// some, and an alarm that fires on every throttled day gets ignored. Once-a-day
// jobs get 36 h: their deliveries have been measured up to ~8 h late, so an early
// run followed by a late one can sit ~32 h apart with nothing wrong.
const WORKFLOWS = [
  { file: 'odds.yml',         label: 'Odds capture (The Odds API)',      maxAgeHours: 30 },
  { file: 'prerender.yml',    label: 'Prerendered pages and sitemap',     maxAgeHours: 18 },
  { file: 'snapshot.yml',     label: 'Pre-fight snapshot',                maxAgeHours: 30 },
  { file: 'dead-man.yml',     label: 'Dead man (pre-fight coverage)',     maxAgeHours: 30 },
  { file: 'engine-serve.yml', label: 'Engine daily publish (private)',    maxAgeHours: 36 },
  { file: 'settle-clv.yml',   label: 'Closing-price settlement',          maxAgeHours: 36 },
  { file: 'prop-locks.yml',   label: 'DUR-001/002 duration locks',        maxAgeHours: 36 },
];

const ODDS_MAX_AGE_HOURS = 30;
// Measured from 00:00 UTC on the card's date. A card ends around 06:00 UTC the
// next day and the event scraper runs at 00:00 UTC, so results should be in by
// day 2; 60 h allows one missed night.
const RESULTS_GRACE_HOURS = 60;
const RESULTS_LOOKBACK_DAYS = 10;
const RESULTS_MISSING_SHARE = 0.5;
const CALENDAR_LOOKAHEAD_DAYS = 14;

// ---------------------------------------------------------------- decisions

// facts = {
//   workflows: { [file]: { state, runs: [{ conclusion, status, created_at }] } | { error } },
//   lastOddsCapture: ISO | null,
//   completedCards: [{ id, name, event_date, fights, withResult }],
//   upcomingCards: [{ id, name, event_date }],
// }
function assess(facts, now, workflows = WORKFLOWS) {
  const t = +new Date(now);
  const breaches = [];
  const ok = [];
  const add = (marker, message) => breaches.push({ marker: `<!-- cfl-health:${marker} -->`, message });

  for (const w of workflows) {
    const f = (facts.workflows || {})[w.file];
    if (!f || f.error) { add(`wf:${w.file}:unreadable`, `${w.label}: could not read its run history (${f && f.error || 'no data'}).`); continue; }
    if (f.state && f.state !== 'active') {
      add(`wf:${w.file}:disabled`, `${w.label}: GitHub reports the workflow as "${f.state}", so its schedule is not running.`);
      continue;
    }
    const done = (f.runs || []).filter(r => r.status === 'completed');
    const latest = done[0];
    const lastOk = done.find(r => r.conclusion === 'success');
    if (latest && ['failure', 'timed_out', 'startup_failure'].includes(latest.conclusion)) {
      add(`wf:${w.file}:failing`, `${w.label}: the latest scheduled run (${latest.created_at}) ended "${latest.conclusion}".`);
      continue;
    }
    const ageH = lastOk ? (t - +new Date(lastOk.created_at)) / H : Infinity;
    if (ageH > w.maxAgeHours) {
      add(`wf:${w.file}:stale`, `${w.label}: no successful scheduled run in ${lastOk ? Math.round(ageH) + ' hours' : 'the visible history'} (allowed ${w.maxAgeHours}).`);
      continue;
    }
    ok.push(`${w.label}: last success ${Math.round(ageH)} h ago.`);
  }

  if (facts.lastOddsCapture == null) {
    add('data:odds:none', 'Odds: no Odds API sportsbook quote found at all.');
  } else {
    const ageH = (t - +new Date(facts.lastOddsCapture)) / H;
    if (ageH > ODDS_MAX_AGE_HOURS) add('data:odds:stale', `Odds: the newest sportsbook quote is ${Math.round(ageH)} hours old (allowed ${ODDS_MAX_AGE_HOURS}). Market pages are showing old prices.`);
    else ok.push(`Odds: newest sportsbook quote ${ageH.toFixed(1)} h old.`);
  }

  for (const c of facts.completedCards || []) {
    const sinceH = (t - +new Date(c.event_date + 'T00:00:00Z')) / H;
    if (sinceH < RESULTS_GRACE_HOURS || c.fights === 0) continue;
    const missing = c.fights - c.withResult;
    if (missing / c.fights > RESULTS_MISSING_SHARE) {
      add(`data:results:${c.id}`, `Results: ${c.name} (${c.event_date}) has ${missing} of ${c.fights} fights with no result recorded. The Railway event scraper writes results nightly.`);
    } else ok.push(`Results: ${c.name} ${c.withResult}/${c.fights}.`);
  }

  if (!(facts.upcomingCards || []).length) {
    add('data:calendar:empty', `Calendar: no UFC card in the next ${CALENDAR_LOOKAHEAD_DAYS} days. The Railway event scraper adds upcoming cards; the UFC almost never goes two weeks dark.`);
  } else ok.push(`Calendar: ${facts.upcomingCards.length} card(s) in the next ${CALENDAR_LOOKAHEAD_DAYS} days.`);

  return { now: new Date(t).toISOString(), breaches, ok };
}

// ---------------------------------------------------------------- reading

async function rest(path, key) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    headers: { apikey: key, Authorization: `Bearer ${key}`, Accept: 'application/json' },
  });
  if (!res.ok) throw new Error(`Supabase ${path.split('?')[0]} -> HTTP ${res.status}`);
  return res.json();
}

async function gh(path, token) {
  const res = await fetch(`https://api.github.com/${path}`, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json' },
  });
  if (!res.ok) throw new Error(`GitHub ${path} -> HTTP ${res.status}`);
  return res.json();
}

const isoDay = ms => new Date(ms).toISOString().slice(0, 10);

async function load({ key, token, repo, now }) {
  const t = +new Date(now);
  const facts = { workflows: {} };

  for (const w of WORKFLOWS) {
    try {
      const meta = await gh(`repos/${repo}/actions/workflows/${w.file}`, token);
      const runs = await gh(`repos/${repo}/actions/workflows/${w.file}/runs?event=schedule&per_page=20`, token);
      facts.workflows[w.file] = { state: meta.state, runs: runs.workflow_runs || [] };
    } catch (e) {
      facts.workflows[w.file] = { error: e.message };
    }
  }

  // feed_version is set only on rows written by build/fetch-odds.js (The Odds
  // API), so this is "the sportsbook capture", not Polymarket.
  const odds = await rest('fight_odds?select=captured_at&feed_version=not.is.null&order=captured_at.desc&limit=1', key);
  facts.lastOddsCapture = odds[0] ? odds[0].captured_at : null;

  const from = isoDay(t - RESULTS_LOOKBACK_DAYS * 24 * H);
  const to = isoDay(t);
  const done = await rest(`events?select=id,name,event_date&event_date=gte.${from}&event_date=lt.${to}&order=event_date.desc`, key);
  facts.completedCards = [];
  for (const e of done) {
    const fights = await rest(`fights?select=id,winner_id,method,is_active&event_id=eq.${e.id}`, key);
    const live = fights.filter(f => f.is_active !== false);
    facts.completedCards.push({ ...e, fights: live.length, withResult: live.filter(f => f.winner_id != null || (f.method && f.method.trim())).length });
  }

  const ahead = isoDay(t + CALENDAR_LOOKAHEAD_DAYS * 24 * H);
  facts.upcomingCards = await rest(`events?select=id,name,event_date&event_date=gte.${to}&event_date=lte.${ahead}`, key);
  return facts;
}

async function main() {
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SECRET_KEY;
  const token = process.env.GH_TOKEN;
  const repo = process.env.GITHUB_REPOSITORY;
  const now = process.env.HEALTH_NOW || new Date().toISOString();
  if (!key || !token || !repo) {
    console.error('[health] missing SUPABASE_SERVICE_ROLE_KEY, GH_TOKEN or GITHUB_REPOSITORY — could not look, which is a failure.');
    process.exit(1);
  }
  let report;
  try {
    report = assess(await load({ key, token, repo, now }), now);
  } catch (e) {
    console.error('[health] could not read the facts:', e.message);
    process.exit(1);
  }
  report.ok.forEach(l => console.log('   ok  ' + l));
  report.breaches.forEach(b => console.log('BREACH ' + b.message));
  if (process.env.HEALTH_JSON_OUT) require('fs').writeFileSync(process.env.HEALTH_JSON_OUT, JSON.stringify(report, null, 2));
  process.exit(report.breaches.length ? 1 : 0);
}

if (require.main === module) main();
module.exports = { assess, WORKFLOWS, ODDS_MAX_AGE_HOURS, RESULTS_GRACE_HOURS };
