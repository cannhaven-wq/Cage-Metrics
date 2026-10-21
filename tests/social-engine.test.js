// The content engine builds research pieces from public data, and nothing else.
//
// T-038 rewrote build/social-engine.js for the research positioning (D-011).
// This runs the real generator over a real card — tests/fixtures/
// social-engine-ufc333.json, read from production with SELECTs on 2026-10-21 —
// and checks what would actually be published:
//
//   - no piece reads as a forecast (social-copy-guard.js::forecastClaim);
//   - no CFL number: every figure in every piece traces back to the fixture;
//   - no "opening line" wording (market-movement.js::FORBIDDEN_BASELINE_WORDS);
//   - the source never names a forecast or private table (leak check);
//   - only guarded pieces are stamped positioning:'research', and a poisoned
//     piece is refused rather than stamped.
//
// Run: node tests/social-engine.test.js
'use strict';
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const E = require('../build/social-engine');
const { forecastClaim } = require('../build/social-copy-guard');
const MOVEMENT = require('../market-movement');
const FX = require('./fixtures/social-engine-ufc333.json');

let n = 0, failed = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { failed++; console.error('FAIL', name, '\n  ', e.message); } };
const ok = (c, m) => { if (!c) throw new Error(m); };

const batch = E.buildBatch(FX);
const pieces = batch.pieces;

// Every string a piece carries, found by walking the object — independent of
// the generator's own pieceText(), so a field it forgets is still checked.
function allText(o) {
  if (o == null) return [];
  if (typeof o === 'string') return [o];
  if (typeof o === 'number') return [String(o)];
  if (Array.isArray(o)) return o.flatMap(allText);
  // `layout` names a renderer template ('verdict' / 'board'), not shown text.
  if (typeof o === 'object') return Object.keys(o).filter(k => k !== 'layout').flatMap(k => allText(o[k]));
  return [];
}
const textOf = p => allText(p).join('\n');

// ------------------------------------------------------------ the batch ---

t('the real card produces a full batch, nothing refused', () => {
  ok(pieces.length >= 6, `only ${pieces.length} pieces from a 14-fight priced card`);
  ok(batch.refused.length === 0, 'refused on real data: ' + JSON.stringify(batch.refused));
  const ids = pieces.map(p => p.id);
  ['market-main', 'movers', 'tape-main', 'books-apart', 'finish-history', 'cardio-board', 'market-reddit']
    .forEach(id => ok(ids.includes(id), `missing piece ${id}`));
});

t('the cancelled bout is not on the card', () => {
  ok(!batch.rows.some(r => r.fight.id === 48648), 'is_active=false bout 48648 was used');
});

t('no piece reads as a forecast', () => {
  pieces.forEach(p => { const c = forecastClaim(textOf(p)); ok(!c, `${p.id}: ${c}`); });
});

t('no piece speaks for a model, a pick or a confidence', () => {
  const BAN = /\bmodels?\b|\bpredict|\bforecast|\bpicks?\b|\bconfiden(ce|t)\b|\bedge\b|\bvalue\b|\blocks?\b|\bverdict|\bsim\b|our number|cfl'?s number|win probability/i;
  pieces.forEach(p => { const m = textOf(p).match(BAN); ok(!m, `${p.id} says "${m && m[0]}"`); });
});

t('no piece calls the baseline an opener', () => {
  pieces.forEach(p => {
    const s = textOf(p).toLowerCase();
    MOVEMENT.FORBIDDEN_BASELINE_WORDS.forEach(w => ok(!s.includes(w), `${p.id} says "${w}"`));
    ok(!/\bopen(er|ers|ing)?\b/.test(s), `${p.id} uses "open" wording`);
  });
});

t('movement is only ever quoted against the first broad capture', () => {
  pieces.forEach(p => {
    const s = textOf(p);
    if (/\bpts toward\b/.test(s)) ok(/first broad capture/.test(s), `${p.id} quotes a move without its baseline`);
  });
});

t('every X tweet fits, and every market price carries its book count and capture time', () => {
  pieces.filter(p => p.platform === 'X').forEach(p => {
    ok(p.tweet && p.tweet.length <= 280, `${p.id} tweet ${p.tweet ? p.tweet.length : 'missing'}`);
    if (/\bBest observed\b|margin removed/.test(p.tweet)) {
      ok(/\d+ (sports)?books/.test(p.tweet), `${p.id} quotes a price with no book count`);
      ok(/\d{2}:\d{2} UTC/.test(p.tweet), `${p.id} quotes a price with no capture time`);
    }
  });
});

t('cardio and finish history are description, never a read on the winner', () => {
  pieces.filter(p => p.pillar === 'Cardio' || p.pillar === 'Finish history')
    .forEach(p => ok(/who wins|how this one goes/.test(p.copy), `${p.id} does not say it is description only`));
});

t('style is only ever the UFC-listed discipline', () => {
  const listed = new Set(FX.fighters.map(f => f.fighting_style).filter(Boolean));
  pieces.forEach(p => {
    const s = textOf(p);
    ok(!/\b(grappler|hybrid)\b/i.test(s), `${p.id} carries a calculated style label`);
    (s.match(/listed by the UFC as ([^·\n.]+)/g) || []).forEach(m => {
      const v = m.replace('listed by the UFC as ', '').trim();
      ok(listed.has(v), `${p.id} shows style "${v}" that is not in fighters.fighting_style`);
    });
  });
});

// ----------------------------------------------------- traceable numbers ---
// Every number a reader sees must be one the fixture holds, or a plain
// arithmetic of two fixture values (a rounded share, an age or reach gap).
// Anything else is a number CFL made up — which is what a forecast is.

function allowedNumbers() {
  const A = new Set();
  const add = v => { if (v !== null && v !== undefined && v !== '') A.add(String(v)); };
  const ev = FX.event;
  (ev.name.match(/\d+/g) || []).forEach(add);
  ev.event_date.split('-').forEach(x => { add(x); add(String(+x)); });
  FX.market.forEach(m => {
    add(Math.round(m.market_p_a * 100)); add(Math.round(m.market_p_b * 100));
    add(Math.abs(m.best_american_a)); add(Math.abs(m.best_american_b));
    add(m.book_count); add(m.matched_book_count);
    if (m.movement_pts_a != null) add(Math.abs(m.movement_pts_a).toFixed(1));
    if (m.book_spread_pts != null) add((+m.book_spread_pts).toFixed(1));
    const d = new Date(m.last_updated);
    add(d.getUTCDate()); add(String(d.getUTCHours()).padStart(2, '0')); add(String(d.getUTCMinutes()).padStart(2, '0'));
  });
  const fid = {}; FX.fighters.forEach(f => { fid[f.id] = f; });
  FX.fighters.forEach(f => {
    [f.age, f.reach_in, f.wins, f.losses, f.draws].forEach(add);
    if (f.height_in != null) { add(Math.floor(f.height_in / 12)); add(f.height_in % 12); }
  });
  FX.fights.forEach(fi => {
    const a = fid[fi.fighter_a_id], b = fid[fi.fighter_b_id];
    if (!a || !b) return;
    if (a.age != null && b.age != null) add(Math.abs(a.age - b.age));
    if (a.reach_in != null && b.reach_in != null) add(Math.abs(a.reach_in - b.reach_in));
  });
  FX.finish_rates.forEach(r => {
    const ko = Math.round(r.total_fights * r.ko_tko_rate), sub = Math.round(r.total_fights * r.sub_rate);
    [r.total_fights, ko, sub, ko + sub, Math.round(((ko + sub) / r.total_fights) * 100)].forEach(add);
  });
  add(FX.fights.filter(f => f.is_active !== false).length);
  return A;
}

// Template wording that legitimately carries a digit, removed before the
// numbers are pulled out. Each is fixed text, not data.
const FIXED = [
  /https?:\/\/\S+/g, /#\w+/g,
  /\bround (1|2|3)\b\+?/gi, /\bR3\+/g, /\bround 3\+/gi,
  new RegExp('\\b' + MOVEMENT.MIN_MATCHED_BOOKS + '\\+ (sportsbooks|books)', 'g'),
  /\bSlide \d+\b/g, /\b1:1\b|9:16\b/g,
];

t('every number in every piece traces back to the real data', () => {
  const A = allowedNumbers();
  pieces.forEach(p => {
    let s = textOf(p);
    FIXED.forEach(re => { s = s.replace(re, ' '); });
    (s.match(/\d+(?:\.\d+)?/g) || []).forEach(tok => {
      const norm = tok.includes('.') ? tok : String(+tok);
      ok(A.has(tok) || A.has(norm), `${p.id}: "${tok}" is not in the fixture`);
    });
  });
});

t('every percentage is the market consensus or a counted share, never a CFL number', () => {
  const mk = new Set(FX.market.flatMap(m => [Math.round(m.market_p_a * 100), Math.round(m.market_p_b * 100)]));
  const fin = new Set(FX.finish_rates.map(r => {
    const e = Math.round(r.total_fights * r.ko_tko_rate) + Math.round(r.total_fights * r.sub_rate);
    return Math.round((e / r.total_fights) * 100);
  }));
  pieces.forEach(p => (textOf(p).match(/\d+%/g) || []).forEach(x => {
    const v = parseInt(x, 10);
    ok(p.pillar === 'Finish history' ? fin.has(v) : mk.has(v), `${p.id}: ${x} is neither`);
  }));
});

// ------------------------------------------------------------ leak check ---

const SRC = fs.readFileSync(path.join(ROOT, 'build/social-engine.js'), 'utf8');
const PRIVATE = ['model_picks', 'model_predictions', 'win_model_locks', 'pre_fight_snapshots',
  'v_pre_fight_graded', 'model_versions', 'v_model_picks_graded', 'v_model_edges_graded',
  'v_fight_locked_forecast', 'prop_projections', 'v_fighter_model_record', 'fight_odds',
  'odds_books', 'user_bets', 'email_subscribers', 'profiles', 'consensusPick', 'p_cal'];

t('the generator source never names a forecast or private table', () => {
  PRIVATE.forEach(name => ok(!SRC.includes(name), `build/social-engine.js mentions ${name}`));
  ok(!/\bpredictions\b/.test(SRC), 'build/social-engine.js mentions the predictions table');
});

t('the generator reads only its declared public sources', () => {
  const reads = [...SRC.matchAll(/\.from\(\s*['"`]([\w.]+)['"`]\s*\)/g)].map(m => m[1]);
  ok(reads.length >= 5, 'expected the loader to read the public tables');
  reads.forEach(r => ok(E.SOURCES.includes(r), `reads ${r}, which is not in SOURCES`));
  E.SOURCES.forEach(s => ok(!PRIVATE.includes(s), `SOURCES lists private ${s}`));
});

t('requiring the generator has no side effects', () => {
  ok(/if \(require\.main === module\)/.test(SRC), 'main() runs on require');
  ok(!/^const .*createClient\(/m.test(SRC), 'a Supabase client is built at module load');
});

// ------------------------------------------------- the research stamp ---

t('every queue entry is stamped research AND passes the guard', () => {
  const q = E.buildQueue([{ event: batch.event, pieces }]);
  ok(q.length >= 4, `queue has ${q.length} entries`);
  q.forEach(e => {
    ok(e.positioning === 'research', `${e.pieceId} not stamped research`);
    ok(!forecastClaim(e.tweet), `${e.pieceId} stamped research but reads as a forecast`);
    ok(e.tweet.length <= 280, `${e.pieceId} tweet over 280`);
  });
});

t('a forecast piece is refused, not stamped', () => {
  const poison = [
    { id: 'p1', platform: 'X', pillar: 'x', copy: 'our model reads A 62% over B', tweet: 'our model reads A 62% over B', image: { layout: 'verdict' }, hashtags: '', cta: '', question: '' },
    { id: 'p2', platform: 'X', pillar: 'x', copy: 'Moved 3 pts since the opening line', tweet: 'Moved 3 pts since the opening line', image: { layout: 'verdict' }, hashtags: '', cta: '', question: '' },
    { id: 'p3', platform: 'X', pillar: 'x', copy: 'fine', tweet: 'fine', image: { layout: 'verdict', bigCap: 'Model leans A', chips: [] }, hashtags: '', cta: '', question: '' },
  ];
  const g = E.guardPieces(poison);
  ok(g.kept.length === 0, 'guard kept: ' + g.kept.map(p => p.id).join(','));
  const q = E.buildQueue([{ event: batch.event, pieces: poison }]);
  ok(q.length === 0, 'buildQueue stamped a refused piece research');
});

t('an over-long tweet is refused, never truncated mid-number', () => {
  ok(E.tweetify('x'.repeat(300), 'https://a', '#t') === null, 'tweetify truncated instead of refusing');
});

if (failed) { console.error(`\n  ${failed} failed, ${n} passed`); process.exit(1); }
console.log(`\n  ${n} passed — the content engine publishes research, from real data, and nothing else.`);
