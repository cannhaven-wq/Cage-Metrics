// Content engine: turns the public research data for every upcoming UFC card
// into a ready-to-review social batch (X, Instagram/TikTok, Reddit) plus a dated
// scheduling CSV, written to /social/<event-slug>-<id>/.
//
// It is a GENERATOR, not a poster: it never touches an account and needs no
// secrets (the same publishable key as the rest of the site; RLS protects
// everything). A human reviews the batch before anything is scheduled.
//
// RESEARCH POSITIONING (T-038, D-011). Until 2026-10-21 every piece here was
// built around the retired engine's pick and its win percentage, and three of
// them went out to X under CFL's name after D-011. This version is built ONLY
// from what the public product already shows:
//
//   - the sportsbook market: vig-free consensus, best observed price and the
//     book posting it, book count, capture time, the spread between books,
//     and movement over the matched book cohort since the first broad capture
//     (v_fight_market_movement, D-012; wording via market-movement.js);
//   - the tale of the tape (fighters: age, height, reach, stance, record);
//   - the discipline as the UFC lists it (fighters.fighting_style, D-030) —
//     never a calculated striker/grappler label, and nothing for "MMA";
//   - how a fighter's past fights ended (v_fighter_finish_rate) and how their
//     output held up late (v_fighter_consistency) — as DESCRIPTION only. Cardio
//     does not tell you who wins, and the copy never implies it does.
//
// It reads no forecast table of any kind. tests/social-engine.test.js greps
// this file for every private or forecast table name and fails on a hit.
//
// Every piece passes through guardPieces() before it can be written anywhere:
// build/social-copy-guard.js::forecastClaim over every string the piece
// carries, plus the opener/baseline wording market-movement.js forbids, plus
// the research-era vocabulary list below. A piece that trips any of them is
// DROPPED and named in the log — never reworded, never posted. Only pieces
// that survived the guard reach the queue, and only those carry
// positioning:'research' (see buildQueue, which runs the guard a second time).
//
// Usage:
//   cd build && node social-engine.js              # all upcoming cards
//   cd build && node social-engine.js --event=4542 # one event id
//
// The piece-building is pure (buildBatch over plain row objects) so it can be
// tested against a real-data fixture without a network: see
// tests/social-engine.test.js and tests/fixtures/social-engine-ufc333.json.

'use strict';

const fs = require('fs');
const path = require('path');
const { slugify } = require('./slug');
const { cardOrder, cardSlug } = require('./event-preview-templates');
const { forecastClaim } = require('./social-copy-guard');
const MOVEMENT = require('../market-movement');

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SUPABASE_KEY = 'sb_publishable_boJGOA1CFN-SF14HHFGUAw_YEEm0DU8';
const SITE = 'https://cannonfightlab.com';

const ROOT = path.resolve(__dirname, '..');
const SOCIAL_DIR = path.join(ROOT, 'social');

// The public tables and views this generator may read. Nothing else.
const SOURCES = Object.freeze([
  'events', 'fights', 'fighters',
  'v_fight_market_movement', 'v_fighter_finish_rate', 'v_fighter_consistency',
]);

// ---------------------------------------------------------------- helpers ---

// Description of each cardio tier: how late-round output compares with the
// fighter's own round one in past fights. Never a statement about who wins.
const CARDIO_LABEL = {
  tireless:  'output holds or rises after round 2',
  steady:    'no real late drop-off',
  tapers:    'measurable late drop-off',
  fades:     'clear late drop-off',
  collapses: 'output falls away sharply late',
};
const CARDIO_BADGE = { tireless: '🟢', steady: '🟢', tapers: '🟡', fades: '🟠', collapses: '🔴' };

// A listed discipline that says nothing about a discipline shows nothing
// (same rule as fight-lab.js::disciplineRead, D-030).
const GENERIC_STYLE = /^(mma|mixed martial arts?|freestyle|n\/?a|none|-+)$/i;

const HASHTAG_CORE = ['#MMA', '#UFC', '#MMATwitter', '#UFCOdds'];

// Minimum sample before a fighter's finish history is quoted.
const MIN_FINISH_SAMPLE = 5;

function eventHashtag(name) {
  const m = String(name).match(/UFC\s+(\d+)/i);
  if (m) return `#UFC${m[1]}`;
  if (/fight night/i.test(name)) return '#UFCFightNight';
  return '#UFC';
}

// "UFC 333: ..." -> "UFC 333"; Fight Nights keep their subtitle.
function shortName(name) {
  const m = String(name).match(/^UFC\s+\d+/i);
  return m ? m[0].toUpperCase().replace(/\s+/g, ' ') : String(name);
}

function compactEvent(name) {
  const m = String(name).match(/^UFC\s+\d+/i);
  if (m) return m[0].toUpperCase().replace(/\s+/g, ' ');
  if (/fight night/i.test(name)) return 'UFC Fight Night';
  return String(name);
}

function surname(n) {
  const parts = String(n || '').trim().split(/\s+/);
  while (parts.length > 1 && /^(jr\.?|sr\.?|ii|iii|iv|v)$/i.test(parts[parts.length - 1])) parts.pop();
  return parts[parts.length - 1] || String(n || '');
}
const upper = n => surname(n).toUpperCase();

function lastNameTag(fullName) {
  const clean = surname(fullName).replace(/[^A-Za-z]/g, '');
  return clean.length >= 3 ? '#' + clean : null;
}

function hashtags(eventName, ...names) {
  const tags = [eventHashtag(eventName), ...HASHTAG_CORE];
  names.forEach(n => { const t = lastNameTag(n); if (t && !tags.includes(t)) tags.push(t); });
  return tags.slice(0, 7).join(' ');
}

function num(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return isFinite(n) ? n : null;
}

// American price, always signed.
function am(n) {
  const v = num(n);
  if (v === null) return '—';
  return (v > 0 ? '+' : '') + Math.round(v);
}
const pct = p => Math.round(p * 100) + '%';

function fmtHeight(inches) {
  const v = num(inches);
  if (v === null) return null;
  return `${Math.floor(v / 12)}'${Math.round(v % 12)}"`;
}
function fmtRecord(f) {
  if (num(f.wins) === null || num(f.losses) === null) return null;
  return `${f.wins}-${f.losses}${num(f.draws) ? '-' + f.draws : ''}`;
}

// "Oct 20, 19:06 UTC" — a social post is read hours later, so its prices carry
// the capture time itself, not a relative age.
function stampUtc(iso) {
  const t = Date.parse(iso);
  if (!isFinite(t)) return null;
  const d = new Date(t);
  const mon = d.toLocaleDateString('en-US', { month: 'short', timeZone: 'UTC' });
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  return `${mon} ${d.getUTCDate()}, ${hh}:${mm} UTC`;
}

function formatLongDate(isoDate) {
  const d = new Date(isoDate + 'T00:00:00Z');
  return d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
}
function shortDate(isoDate) {
  const d = new Date(isoDate + 'T00:00:00Z');
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
}
function isoOffset(isoDate, days) {
  const d = new Date(isoDate + 'T12:00:00Z');
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function writeIfChanged(filepath, content) {
  try { if (fs.readFileSync(filepath, 'utf8') === content) return false; } catch (_) {}
  fs.mkdirSync(path.dirname(filepath), { recursive: true });
  fs.writeFileSync(filepath, content);
  return true;
}

function cardUrl(event, src) {
  return `${SITE}/card/${cardSlug(event.name, event.id)}.html${src ? `?src=${src}` : ''}`;
}

// ---------------------------------------------------------- data assembly ---

// Pure: plain row objects in, card rows out. Shape of `data`:
//   { event, fights, market, fighters, finish_rates, cardio }
// each an array of rows exactly as the public tables/views return them.
// Returns rows sorted in card order:
//   { fight, a, b, mkt, finA, finB, cardioA, cardioB }
function assembleRows(data) {
  const fmap = {}; (data.fighters || []).forEach(f => { fmap[f.id] = f; });
  const mkt = {}; (data.market || []).forEach(r => { mkt[r.fight_id] = r; });
  const fin = {}; (data.finish_rates || []).forEach(r => { fin[r.fighter_id] = r; });
  const cardio = {};
  (data.cardio || []).forEach(r => { if (r.weight_class === 'CAREER') cardio[r.fighter_id] = r; });

  const rows = (data.fights || [])
    .filter(f => f.id && f.fighter_a_id && f.fighter_b_id && f.is_active !== false)
    .map(fight => {
      const a = fmap[fight.fighter_a_id] || { id: fight.fighter_a_id, name: fight.fighter_a_name };
      const b = fmap[fight.fighter_b_id] || { id: fight.fighter_b_id, name: fight.fighter_b_name };
      return {
        fight, a, b,
        mkt: mkt[fight.id] || null,
        finA: finishHistory(fin[a.id]), finB: finishHistory(fin[b.id]),
        cardioA: cardioRead(cardio[a.id]), cardioB: cardioRead(cardio[b.id]),
      };
    })
    .filter(r => r.a.name && r.b.name);
  rows.sort((x, y) => cardOrder(x.fight, y.fight));
  return rows;
}

// How a fighter's past fights ended, as counts (not a rate dressed up as a
// skill). Below the sample floor it is not quoted at all.
function finishHistory(r) {
  if (!r) return null;
  const total = num(r.total_fights);
  if (total === null || total < MIN_FINISH_SAMPLE) return null;
  const ko = Math.round(total * (num(r.ko_tko_rate) || 0));
  const sub = Math.round(total * (num(r.sub_rate) || 0));
  return { total, early: ko + sub, ko, sub };
}

// Cardio tier, only where the view rates the read 'high' (enough late-round
// tape). A limited read is a guess and is not published.
function cardioRead(r) {
  if (!r || !r.cardio_tier || r.confidence_tier !== 'high' || !CARDIO_LABEL[r.cardio_tier]) return null;
  return r.cardio_tier;
}

function style(f) {
  const raw = f && f.fighting_style ? String(f.fighting_style).trim() : '';
  return raw && !GENERIC_STYLE.test(raw) ? raw : null;
}

// The market for one fight, read through market-movement.js so the movement
// refusals and wording are the site's, not this file's.
function marketRead(row) {
  const m = row.mkt;
  if (!m || num(m.market_p_a) === null || num(m.book_count) === null) return null;
  const pA = num(m.market_p_a);
  const pB = num(m.market_p_b) !== null ? num(m.market_p_b) : 1 - pA;
  const mv = MOVEMENT.describeMovement(m, { fighterA: row.a.name, fighterB: row.b.name });
  const move = mv.ok ? mv.value.pts : null;
  return {
    pA, pB,
    books: num(m.book_count),
    asOf: stampUtc(m.last_updated),
    bestA: num(m.best_american_a), bookA: m.best_book_a || null,
    bestB: num(m.best_american_b), bookB: m.best_book_b || null,
    spread: num(m.book_spread_pts),
    moveOk: mv.ok && move !== null,
    move,
    matched: mv.books.matched,
    moveStatus: mv.status,
  };
}

// "3.8 pts toward Pico" / "unchanged" — the market.js::moveWords phrasing.
function moveText(mr, row) {
  if (!mr || !mr.moveOk) return null;
  const mag = Math.abs(mr.move);
  if (mag < 0.5) return 'unchanged';
  return `${mag.toFixed(1)} pts toward ${surname(mr.move > 0 ? row.a.name : row.b.name)}`;
}

function bestLine(mr, row) {
  const parts = [];
  if (mr.bestA !== null && mr.bookA) parts.push(`${surname(row.a.name)} ${am(mr.bestA)} (${mr.bookA})`);
  if (mr.bestB !== null && mr.bookB) parts.push(`${surname(row.b.name)} ${am(mr.bestB)} (${mr.bookB})`);
  return parts.length ? parts.join(', ') : null;
}

// ------------------------------------------------------------- generators ---
// Each returns an array of raw piece objects (or []). A piece:
//   { tag, id, platform, pillar, copy, tweetBody?, hashtags, cta, question,
//     visual?, image? }
// finalizePiece() adds `tweet` and `caption`; guardPieces() decides whether it
// survives. `image` is a spec rendered to PNGs by post-cards.js.

const BASELINE_NOTE = `Movement is measured only across books quoting both at our first broad capture (when ${MOVEMENT.MIN_MATCHED_BOOKS}+ sportsbooks first had the fight priced) and now. That is when CFL started watching properly, not the first price any book posted.`;

// Market — the main event as the books have it.
function genMarketMain(event, rows) {
  const row = rows.find(r => r.fight.is_main_event) || rows[0];
  const mr = row && marketRead(row);
  if (!mr || !mr.asOf) return [];
  const A = surname(row.a.name), B = surname(row.b.name);
  const best = bestLine(mr, row);
  const mv = moveText(mr, row);
  const S = shortName(event.name);

  const copy =
`${S} main event: ${A} vs ${B}.

Books' consensus, each book's margin removed: ${A} ${pct(mr.pA)}, ${B} ${pct(mr.pB)}. ${mr.books} sportsbooks, as of ${mr.asOf}.
${best ? `Best observed price: ${best}.` : 'No best price captured yet.'}
${mv ? `Since our first broad capture (${mr.matched} matched books): ${mv}.` : 'Movement: not enough comparable books yet, so no figure.'}

That is what the books are saying, not what we think. Every book, side by side, on the card page.`;

  // Longest first; finalizePiece takes the first that fits in a tweet.
  const head = `${S} main event: books have ${A} ${pct(mr.pA)}, ${B} ${pct(mr.pB)} (${mr.books} books, margin removed, ${mr.asOf}).`;
  const tweetBody = [
    best ? `${head}\nBest observed: ${best}.` : head,
    head,
  ];

  const chips = [];
  if (mr.bestA !== null) chips.push({ k: `Best · ${upper(row.a.name)}`, v: `${am(mr.bestA)} ${mr.bookA || ''}`.trim() });
  if (mr.bestB !== null) chips.push({ k: `Best · ${upper(row.b.name)}`, v: `${am(mr.bestB)} ${mr.bookB || ''}`.trim() });
  if (mv) chips.push({ k: 'Since first broad capture', v: mv });

  return [{
    tag: 'X-POST', id: 'market-main', platform: 'X', pillar: 'Market',
    copy, tweetBody,
    image: {
      layout: 'verdict', eyebrow: `Market · ${compactEvent(event.name)}`,
      fa: upper(row.a.name), fb: upper(row.b.name),
      big: `${pct(mr.pA)} · ${pct(mr.pB)}`,
      bigCap: `Books' consensus · ${mr.books} books · margin removed`,
      chips, cta: 'Every book, side by side → cannonfightlab.com',
    },
    hashtags: hashtags(event.name, row.a.name, row.b.name),
    cta: `Every book on the card page (${cardUrl(event, 'x')})`,
    question: `Where would you shop this one?`,
  }];
}

// Movement — the biggest matched-cohort moves on the card.
function genMovers(event, rows) {
  const S = shortName(event.name);
  const reads = rows.map(r => ({ r, mr: marketRead(r) })).filter(x => x.mr && x.mr.moveOk);
  if (!reads.length) return [];
  const movers = reads.filter(x => Math.abs(x.mr.move) >= MOVEMENT.FLAT_PTS)
    .sort((x, y) => Math.abs(y.mr.move) - Math.abs(x.mr.move)).slice(0, 4);
  const hashtagsFor = movers.length ? movers.flatMap(x => [x.r.a.name, x.r.b.name]).slice(0, 2) : [];

  if (!movers.length) {
    return [{
      tag: 'X-POST', id: 'movers', platform: 'X', pillar: 'Movement',
      copy:
`${S}: nothing on the card has moved a full point since our first broad capture.

${BASELINE_NOTE}

A quiet market is a finding too. Every fight, every book, on the card page.`,
      tweetBody: `${S}: nothing on the card has moved a full point since our first broad capture (matched books only). A quiet market is a finding too.`,
      hashtags: hashtags(event.name),
      cta: `Every fight on the card page (${cardUrl(event, 'x')})`,
      question: `Expecting anything to move before the walkouts?`,
    }];
  }

  const line = x => `${surname(x.r.a.name)} vs ${surname(x.r.b.name)}: ${moveText(x.mr, x.r)} (${x.mr.matched} matched books)`;
  const lead = movers[0];
  const copy =
`${S}: where the books have moved since our first broad capture.

${movers.map(line).join('\n')}

${BASELINE_NOTE} A move is the books changing their price — it says nothing about who wins.`;

  let tweetBody = `${S}, biggest moves since our first broad capture (matched books only):`;
  for (const x of movers) {
    const next = `\n${surname(x.r.a.name)} vs ${surname(x.r.b.name)}: ${moveText(x.mr, x.r)}`;
    if ((tweetBody + next).length > 200) break;
    tweetBody += next;
  }

  const leadToward = lead.mr.move > 0 ? lead.r.a : lead.r.b;
  const leadBest = lead.mr.move > 0 ? { p: lead.mr.bestA, b: lead.mr.bookA } : { p: lead.mr.bestB, b: lead.mr.bookB };
  const chips = [{ k: 'Matched books', v: String(lead.mr.matched) }];
  if (leadBest.p !== null) chips.push({ k: `Best · ${upper(leadToward.name)}`, v: `${am(leadBest.p)} ${leadBest.b || ''}`.trim() });

  return [{
    tag: 'X-POST', id: 'movers', platform: 'X', pillar: 'Movement',
    copy, tweetBody,
    image: {
      layout: 'verdict', eyebrow: `Line movement · ${compactEvent(event.name)}`,
      fa: upper(lead.r.a.name), fb: upper(lead.r.b.name),
      big: `${Math.abs(lead.mr.move).toFixed(1)} pts`,
      bigCap: `Toward ${surname(leadToward.name)} since first broad capture`,
      chips, cta: 'Every move, every book → cannonfightlab.com',
    },
    hashtags: hashtags(event.name, ...hashtagsFor),
    cta: `Every move on the card page (${cardUrl(event, 'x')})`,
    question: `Which of these moves surprised you?`,
  }];
}

// Tale of the tape — the main event, measured differences only.
function genTape(event, rows) {
  const row = rows.find(r => r.fight.is_main_event) || rows[0];
  if (!row) return [];
  const { a, b } = row;
  const S = shortName(event.name);
  const tapeLine = f => {
    const bits = [];
    if (num(f.age) !== null) bits.push(`${f.age} yrs`);
    if (fmtHeight(f.height_in)) bits.push(fmtHeight(f.height_in));
    if (num(f.reach_in) !== null) bits.push(`${f.reach_in}" reach`);
    if (f.stance) bits.push(f.stance);
    if (fmtRecord(f)) bits.push(`${fmtRecord(f)} pro`);
    if (style(f)) bits.push(`listed by the UFC as ${style(f)}`);
    return `${surname(f.name)}: ${bits.join(' · ')}`;
  };
  const diffs = [];
  const ageGap = num(a.age) !== null && num(b.age) !== null ? Math.abs(a.age - b.age) : null;
  const reachGap = num(a.reach_in) !== null && num(b.reach_in) !== null ? Math.abs(a.reach_in - b.reach_in) : null;
  if (ageGap) diffs.push(`${surname(a.age < b.age ? a.name : b.name)} is ${ageGap} year${ageGap === 1 ? '' : 's'} younger`);
  if (reachGap) diffs.push(`${surname(a.reach_in > b.reach_in ? a.name : b.name)} has ${reachGap}" more reach`);
  if (a.stance && b.stance && a.stance !== b.stance) diffs.push(`${a.stance} meets ${b.stance}`);
  if (!diffs.length && !ageGap && !reachGap) return [];

  const copy =
`${S} main event, tale of the tape.

${tapeLine(a)}
${tapeLine(b)}

${diffs.length ? diffs.join('. ') + '.' : 'Close to identical on paper.'} Measured differences, not a read on who wins.`;

  const tweetBody = `${S} main event, tale of the tape: ${surname(a.name)} vs ${surname(b.name)}. ${diffs.join('. ')}${diffs.length ? '.' : ''}`;

  const both = (x, y) => `${x} · ${y}`;
  const chips = [];
  if (num(a.age) !== null && num(b.age) !== null) chips.push({ k: 'Age', v: both(a.age, b.age) });
  if (num(a.reach_in) !== null && num(b.reach_in) !== null) chips.push({ k: 'Reach', v: both(`${a.reach_in}"`, `${b.reach_in}"`) });
  if (fmtHeight(a.height_in) && fmtHeight(b.height_in)) chips.push({ k: 'Height', v: both(fmtHeight(a.height_in), fmtHeight(b.height_in)) });
  if (fmtRecord(a) && fmtRecord(b)) chips.push({ k: 'Pro record', v: both(fmtRecord(a), fmtRecord(b)) });

  const bigIsAge = ageGap && ageGap >= (reachGap || 0);
  return [{
    tag: 'X-POST', id: 'tape-main', platform: 'X', pillar: 'Tale of the Tape',
    copy, tweetBody,
    image: {
      layout: 'verdict', eyebrow: `Tale of the tape · ${compactEvent(event.name)}`,
      fa: upper(a.name), fb: upper(b.name),
      big: bigIsAge ? `${ageGap} yrs` : `${reachGap || 0}"`,
      bigCap: bigIsAge
        ? `Age gap · ${surname(a.age < b.age ? a.name : b.name)} younger`
        : `Reach gap · ${surname(a.reach_in > b.reach_in ? a.name : b.name)} longer`,
      chips, cta: 'Full matchup research → cannonfightlab.com',
    },
    hashtags: hashtags(event.name, a.name, b.name),
    cta: `Full matchup research (${cardUrl(event, 'x')})`,
    question: `Which of these differences matters most to you, and why?`,
  }];
}

// Book spread — the fight the sportsbooks disagree on most.
function genBookSpread(event, rows) {
  const S = shortName(event.name);
  const cands = rows.map(r => ({ r, mr: marketRead(r) }))
    .filter(x => x.mr && x.mr.spread !== null && x.mr.books >= 2 && x.mr.asOf)
    .sort((x, y) => y.mr.spread - x.mr.spread);
  if (!cands.length) return [];
  const { r, mr } = cands[0];
  const sp = MOVEMENT.describeBookSpread(r.mkt);
  if (!sp.ok) return [];
  const A = surname(r.a.name), B = surname(r.b.name);
  const best = bestLine(mr, r);
  const spreadTxt = mr.spread.toFixed(1);

  const copy =
`${S}: the books are furthest apart on ${A} vs ${B} — ${spreadTxt} pts between the highest and lowest of ${mr.books} sportsbooks, after each book's margin is removed.

${best ? `Best observed price: ${best}. ` : ''}As of ${mr.asOf}.

Same fight, different numbers depending on the book. Best price here means the best number in our data, ranked on the price alone.`;

  const tweetBody = `${S}: books are furthest apart on ${A} vs ${B}, ${spreadTxt} pts across ${mr.books} sportsbooks (margin removed, ${mr.asOf}).${best ? `\nBest observed: ${best}.` : ''}`;

  const chips = [{ k: 'Sportsbooks', v: String(mr.books) }];
  if (mr.bestA !== null) chips.push({ k: `Best · ${upper(r.a.name)}`, v: `${am(mr.bestA)} ${mr.bookA || ''}`.trim() });
  if (mr.bestB !== null) chips.push({ k: `Best · ${upper(r.b.name)}`, v: `${am(mr.bestB)} ${mr.bookB || ''}`.trim() });

  return [{
    tag: 'X-POST', id: 'books-apart', platform: 'X', pillar: 'Book spread',
    copy, tweetBody,
    image: {
      layout: 'verdict', eyebrow: `Book spread · ${compactEvent(event.name)}`,
      fa: upper(r.a.name), fb: upper(r.b.name),
      big: `${spreadTxt} pts`,
      bigCap: `${sp.plain} · margin removed`,
      chips, cta: 'Every book, side by side → cannonfightlab.com',
    },
    hashtags: hashtags(event.name, r.a.name, r.b.name),
    cta: `Every book on the card page (${cardUrl(event, 'x')})`,
    question: `Do you check more than one book before you bet?`,
  }];
}

// Finish history — how both fighters' past fights ended. History, not a read.
function genFinishHistory(event, rows) {
  const S = shortName(event.name);
  const cands = rows.filter(r => r.finA && r.finB)
    .map(r => ({ r, share: (r.finA.early / r.finA.total) + (r.finB.early / r.finB.total) }))
    .sort((x, y) => y.share - x.share);
  if (!cands.length) return [];
  const { r } = cands[0];
  const A = surname(r.a.name), B = surname(r.b.name);
  const share = f => Math.round((f.early / f.total) * 100);

  const copy =
`${S}, how their past fights ended: ${A} vs ${B}.

${A}: ${r.finA.early} of ${r.finA.total} fights on record ended inside the distance (${r.finA.ko} by KO/TKO, ${r.finA.sub} by submission).
${B}: ${r.finB.early} of ${r.finB.total} (${r.finB.ko} by KO/TKO, ${r.finB.sub} by submission).

That counts fights they lost as well as won. It is history — it describes how their past fights went, not how this one goes.`;

  const tweetBody = `${S}, how their past fights ended: ${r.finA.early} of ${A}'s ${r.finA.total} fights on record ended inside the distance, ${r.finB.early} of ${B}'s ${r.finB.total}. Wins and losses both count.`;

  return [{
    tag: 'X-POST', id: 'finish-history', platform: 'X', pillar: 'Finish history',
    copy, tweetBody,
    image: {
      layout: 'verdict', eyebrow: `Finish history · ${compactEvent(event.name)}`,
      fa: upper(r.a.name), fb: upper(r.b.name),
      big: `${share(r.finA)}% · ${share(r.finB)}%`,
      bigCap: 'Past fights ended inside the distance',
      chips: [
        { k: upper(r.a.name), v: `${r.finA.early} of ${r.finA.total}` },
        { k: upper(r.b.name), v: `${r.finB.early} of ${r.finB.total}` },
      ],
      cta: 'Full matchup research → cannonfightlab.com',
    },
    hashtags: hashtags(event.name, r.a.name, r.b.name),
    cta: `Full matchup research (${cardUrl(event, 'x')})`,
    question: `Does a finisher's record change how you watch the fight?`,
  }];
}

// Cardio — description of late-round output, never a statement about who wins.
function genCardio(event, rows) {
  const S = shortName(event.name);
  const list = [];
  for (const r of rows) {
    if (r.cardioA) list.push({ name: r.a.name, tier: r.cardioA });
    if (r.cardioB) list.push({ name: r.b.name, tier: r.cardioB });
    if (list.length >= 6) break;
  }
  if (list.length < 4) return [];
  const top = list.slice(0, 6);
  const NOTE = 'Built from round-by-round output in past fights: how much a fighter throws and lands in round 3 and later against their own round 1. It describes past fights. It does not tell you who wins, and we do not use it that way.';

  const board = {
    layout: 'board',
    eyebrow: `Cardio · ${compactEvent(event.name)}`,
    title: 'Late-round output',
    rows: top.map(f => ({ name: upper(f.name), tier: f.tier })),
    cta: 'How it is measured → cannonfightlab.com',
  };

  return [{
    tag: 'X-POST', id: 'cardio-board', platform: 'X', pillar: 'Cardio', image: board,
    copy:
`${S} cardio check — how late-round output compares with round 1, from past fights.

${top.map(f => `• ${surname(f.name)} — ${CARDIO_BADGE[f.tier]} ${f.tier} (${CARDIO_LABEL[f.tier]})`).join('\n')}

${NOTE}`,
    tweetBody: `${S} cardio check: how each fighter's output in round 3+ compares with their own round 1, from past fights. A description of the tape, not a read on who wins.`,
    hashtags: hashtags(event.name, ...top.slice(0, 2).map(f => f.name)) + ' #Cardio',
    cta: `How it is measured (${cardUrl(event, 'x')})`,
    question: `Whose gas tank would you most like to see tested?`,
  }, {
    tag: 'IG-REEL', id: 'cardio-carousel', platform: 'Instagram', pillar: 'Cardio', image: board,
    copy:
`CAROUSEL — "Late-round output"
Slide 1: "${S}: how output holds up after round 2, from past fights."
${top.map((f, i) => `Slide ${i + 2}: ${surname(f.name)} — ${CARDIO_BADGE[f.tier]} ${f.tier.toUpperCase()} — ${CARDIO_LABEL[f.tier]}`).join('\n')}
Last slide: "Description of past fights, not a read on who wins. Full card → link in bio."`,
    hashtags: hashtags(event.name, ...top.slice(0, 2).map(f => f.name)) + ' #Cardio',
    cta: 'Full card → link in bio',
    question: `Who do you think this undersells?`,
    visual: `Dark charcoal background, crimson accent, one tier badge per slide. Clinical "lab report" look, no hype.`,
  }];
}

// Reddit — the market table, the same shape social-post.js::buildPost uses.
function genRedditMarket(event, rows) {
  const lines = rows.map(r => ({ r, mr: marketRead(r) })).filter(x => x.mr && x.mr.asOf);
  if (!lines.length) return [];
  const S = shortName(event.name);
  const asOf = lines[0].mr.asOf;
  const table = lines.slice(0, 10).map(({ r, mr }) => {
    const favIsA = mr.pA >= mr.pB;
    const fav = favIsA ? r.a : r.b;
    const tag = r.fight.is_title_fight ? ' **[TITLE]**' : (r.fight.is_main_event ? ' **[MAIN]**' : '');
    const best = favIsA ? `${am(mr.bestA)}${mr.bookA ? ' (' + mr.bookA + ')' : ''}` : `${am(mr.bestB)}${mr.bookB ? ' (' + mr.bookB + ')' : ''}`;
    const mv = moveText(mr, r) || 'not enough comparable books';
    const sp = mr.spread === null ? '—' : `${mr.spread.toFixed(1)} pts`;
    return `| ${r.a.name} vs ${r.b.name}${tag} | ${surname(fav.name)} ${pct(favIsA ? mr.pA : mr.pB)} | ${best} | ${mv} | ${sp} | ${mr.books} |`;
  });
  return [{
    tag: 'REDDIT-POST', id: 'market-reddit', platform: 'Reddit (r/MMA)', pillar: 'Market',
    copy:
`TITLE: [Odds movement] ${event.name} — what the books have done so far

Nothing here says who wins. This is only what the sportsbooks are posting, as of ${asOf}.

| Fight | Books' consensus (favourite) | Best observed price | Moved since first broad capture | Books apart | Books |
|---|---|---|---|---|---|
${table.join('\n')}

Consensus is the middle book with each book's margin removed. ${BASELINE_NOTE}

(Happy to share the full board — will link in a comment if the sub allows it.)`,
    hashtags: '(Reddit — no hashtags; follow the sub\'s self-promo rules, link only if allowed)',
    cta: 'Link only on request / in a comment if allowed',
    question: `Anyone shopping more than two books for ${S}?`,
  }];
}

// ------------------------------------------------------------------ guard ---

// Vocabulary a research-era piece never uses, on top of forecastClaim. Each is
// a word the retired copy leaned on; none is needed to describe the market or
// the tape.
const RESEARCH_BANNED = [
  { name: 'model',      re: /\bmodels?\b/i },
  { name: 'predict',    re: /\bpredict/i },
  { name: 'forecast',   re: /\bforecast/i },
  { name: 'sim',        re: /\bsim(ulation)?s?\b/i },
  { name: 'confidence', re: /\bconfiden(ce|t)\b/i },
  { name: 'pick',       re: /\bpick(s|ed)?\b/i },
  { name: 'lock',       re: /\blocks?\b/i },
  { name: 'edge',       re: /\bedges?\b/i },
  { name: 'value',      re: /\bvalue\b/i },
  { name: 'verdict',    re: /\bverdicts?\b/i },
  { name: 'favoured/favorite by us', re: /\b(we|cfl)\s+(like|favou?r|back)s?\b/i },
  { name: 'fade',       re: /\bfade\s+(candidate|him|her|them|this)\b/i },
];

// The baseline wording market-movement.js forbids, plus its short forms.
const BASELINE_BANNED = MOVEMENT.FORBIDDEN_BASELINE_WORDS
  .map(w => ({ name: `baseline: ${w}`, re: new RegExp('\\b' + w.replace(/\s+/g, '\\s+') + '\\b', 'i') }))
  .concat([
    { name: 'baseline: opener', re: /\bopeners?\b/i },
    { name: 'baseline: since open', re: /\bsince\s+(the\s+)?open(ing)?\b/i },
  ]);

// Every string a piece carries, including the image text that gets rendered.
function pieceText(p) {
  const img = p.image || {};
  return [
    p.copy, p.tweet, p.caption, p.hashtags, p.cta, p.question, p.visual,
    img.eyebrow, img.title, img.big, img.bigCap, img.cta, img.fa, img.fb,
    ...(img.chips || []).flatMap(c => [c.k, c.v]),
    ...(img.rows || []).flatMap(r => [r.name, r.tier]),
  ].filter(s => s !== undefined && s !== null).join('\n');
}

// Returns the reason a piece must not ship, or null.
function refusalOf(p) {
  const text = pieceText(p);
  const fc = forecastClaim(text);
  if (fc) return `forecast: ${fc}`;
  for (const b of RESEARCH_BANNED) if (b.re.test(text)) return `research vocabulary: ${b.name}`;
  for (const b of BASELINE_BANNED) if (b.re.test(text)) return b.name;
  if (/\bundefined\b|\bNaN\b|\bnull\b/.test(text)) return 'unfilled value';
  if (p.platform === 'X' && p.image && !p.tweet) return 'tweet would exceed 280 characters';
  return null;
}

// Splits pieces into those that may ship and those that may not. Nothing is
// reworded: a refused piece is dropped whole and named.
function guardPieces(pieces) {
  const kept = [], refused = [];
  for (const p of pieces) {
    const why = refusalOf(p);
    if (why) refused.push({ id: p.id, reason: why });
    else kept.push(p);
  }
  return { kept, refused };
}

// ----------------------------------------------------------- finalising ---

// A ≤280-char tweet. Never truncated: a cut can leave half a number, so a body
// that does not fit returns null and the guard refuses the piece.
function tweetify(body, url, tag) {
  const t = `${body}\n\n${url}${tag ? '\n' + tag : ''}`;
  return t.length <= 280 ? t : null;
}

function finalizePiece(p, event) {
  const out = Object.assign({}, p);
  // tweetBody may be one string or a list of candidates, longest first.
  const bodies = [].concat(p.tweetBody || []);
  if (bodies.length) {
    let body = bodies[bodies.length - 1];
    out.tweet = null;
    for (const b of bodies) {
      const t = tweetify(b, cardUrl(event, 'x'), eventHashtag(event.name));
      if (t) { out.tweet = t; body = b; break; }
    }
    out.caption = `${body}\n\nFull card, every book — link in bio 🔗\n\n${p.hashtags}`;
  }
  delete out.tweetBody;
  return out;
}

// ------------------------------------------------------------- assembly ---

function rawPieces(event, rows) {
  return [
    ...genMarketMain(event, rows),
    ...genMovers(event, rows),
    ...genTape(event, rows),
    ...genBookSpread(event, rows),
    ...genFinishHistory(event, rows),
    ...genCardio(event, rows),
    ...genRedditMarket(event, rows),
  ].map(p => finalizePiece(p, event));
}

function buildPieces(event, rows) {
  return guardPieces(rawPieces(event, rows));
}

// Pure entry point: plain rows in, a guarded batch out.
function buildBatch(data) {
  const event = data.event;
  const rows = assembleRows(data);
  const { kept, refused } = buildPieces(event, rows);
  return { event, rows, pieces: kept, refused };
}

// ----------------------------------------------------------- auto-post ---

// The X queue: one entry per X piece with an image. The guard runs AGAIN here,
// on the exact tweet that would be posted, and only an entry that passes is
// stamped positioning:'research' — the stamp build/social-post.js requires.
// The stamp is therefore a statement this function has just checked, not a
// label the generator hands itself (which is how model copy reached X before).
function buildQueue(batches) {
  const queue = [];
  for (const { event, pieces } of batches) {
    for (const p of pieces) {
      if (p.platform !== 'X' || !p.image || !p.tweet) continue;
      if (refusalOf(p) || forecastClaim(p.tweet)) continue;
      const ims = p.images || [];
      const im = ims.find(i => i.key === 'x_land') || ims.find(i => i.key === 'square') || ims[0];
      queue.push({
        eventId: event.id,
        eventName: event.name,
        eventDate: event.event_date,
        pieceId: p.id,
        pillar: p.pillar,
        tweet: p.tweet,
        image: im ? 'social/' + im.rel : null,
        cardUrl: cardUrl(event),
        positioning: 'research',
      });
    }
  }
  queue.sort((a, b) => (a.eventDate < b.eventDate ? -1 : a.eventDate > b.eventDate ? 1 : 0));
  return queue;
}

// -------------------------------------------------------- Metricool export ---
// One-file bulk import for Instagram + TikTok. Captions are the guarded
// `caption` field — nothing here writes new words.

function bestImage(piece, keys) {
  const ims = piece.images || [];
  for (const k of keys) { const m = ims.find(i => i.key === k); if (m) return m; }
  return ims[0] || null;
}

function visualPieces(pieces) {
  return pieces.filter(p => p.platform === 'X' && p.image && p.caption && (p.images || []).length);
}

function buildMetricoolRows(batches) {
  const rows = [];
  for (const { event, pieces } of batches) {
    let day = 0;
    for (const p of visualPieces(pieces)) {
      const ig = bestImage(p, ['ig_portrait', 'square']);
      const tt = bestImage(p, ['story', 'square']);
      if (ig) rows.push({ date: isoOffset(event.event_date, -6 + day), time: '18:00', platform: 'Instagram', caption: p.caption, image: `${SITE}/social/${ig.rel}`, card: cardUrl(event) });
      if (tt) rows.push({ date: isoOffset(event.event_date, -5 + day), time: '12:00', platform: 'TikTok', caption: p.caption, image: `${SITE}/social/${tt.rel}`, card: cardUrl(event) });
      day = (day + 1) % 5;
    }
  }
  return rows;
}

function renderMetricoolCsv(rows) {
  const header = ['date', 'time', 'platform', 'caption', 'image_url', 'card_url'];
  const esc = c => /[",\n]/.test(String(c)) ? `"${String(c).replace(/"/g, '""')}"` : String(c);
  return [header, ...rows.map(r => [r.date, r.time, r.platform, r.caption, r.image, r.card])]
    .map(r => r.map(esc).join(',')).join('\n') + '\n';
}

// Structured post data for the local Desktop posting app (build/make-posting-app.js).
function buildPostsData(batches) {
  return batches.map(({ event, pieces }) => {
    const posts = [];
    visualPieces(pieces).forEach((p, i) => {
      const xImg = bestImage(p, ['x_land', 'square']);
      const sqImg = bestImage(p, ['square', 'ig_portrait', 'story']);
      const when = `${shortDate(isoOffset(event.event_date, -6 + i))}, 6:00 PM`;
      if (p.tweet) posts.push({ platform: 'X', pillar: p.pillar, caption: p.tweet, image: xImg ? 'social/' + xImg.rel : null, when: 'manual — review first' });
      posts.push({ platform: 'Instagram + TikTok', pillar: p.pillar, caption: p.caption, image: sqImg ? 'social/' + sqImg.rel : null, when });
    });
    return { card: event.name, dateLabel: formatLongDate(event.event_date), cardUrl: cardUrl(event), posts };
  }).filter(c => c.posts.length);
}

// The weekly load sheet: the soonest upcoming card's IG/TikTok posts in order.
function buildNextPostsMd(batches, today) {
  const t = today || new Date().toISOString().slice(0, 10);
  const b = batches.filter(x => x.event.event_date >= t)[0] || batches[0];
  if (!b) return '# No upcoming cards.\n';
  const { event, pieces } = b;
  const slug = `${slugify(event.name)}-${event.id}`;
  const picks = visualPieces(pieces);
  const out = [];
  out.push(`# 📲 Instagram + TikTok drafts`);
  out.push('');
  out.push(`## ${event.name} — ${formatLongDate(event.event_date)}`);
  out.push('');
  out.push(`**${picks.length} posts.** Images are in \`social/${slug}/img/\`. Review each one before scheduling — market numbers go stale, so check the capture time in the caption.`);
  out.push('');
  picks.forEach((p, i) => {
    const im = bestImage(p, ['square', 'ig_portrait', 'story']);
    const file = im ? im.rel.split('/').pop() : '(none)';
    const when = `${shortDate(isoOffset(event.event_date, -6 + i))}, 6:00 PM`;
    out.push('---');
    out.push('');
    out.push(`### Post ${i + 1}  ·  ${when}`);
    out.push(`🖼️ **Attach image:** \`${file}\`  ·  [open/download](${SITE}/social/${im ? im.rel : ''})`);
    out.push('');
    out.push('**Caption (copy everything in the box):**');
    out.push('```');
    out.push(p.caption);
    out.push('```');
    out.push('');
  });
  out.push('---');
  out.push('');
  return out.join('\n');
}

function renderBatchMd(event, rows, pieces, refused) {
  const priced = rows.filter(r => marketRead(r)).length;
  const out = [];
  out.push(`# Social batch — ${event.name}`);
  out.push('');
  out.push(`**${formatLongDate(event.event_date)}**${event.location ? ` · ${event.location}` : ''} · ${rows.length} fights · ${priced} with a sportsbook price`);
  out.push(`Landing page: ${cardUrl(event)}`);
  out.push('');
  out.push(`_Generated by \`build/social-engine.js\` from public market and fight data only — no picks. Review before posting; prices carry their capture time. Links carry \`?src=\` for Plausible attribution._`);
  out.push('');
  pieces.forEach((p, i) => {
    out.push(`## ${i + 1}. <${p.tag}> · ${p.pillar} · ${p.platform}`);
    out.push('');
    out.push('```');
    out.push(p.copy);
    out.push('```');
    if (p.tweet) { out.push('**Tweet:**'); out.push('```'); out.push(p.tweet); out.push('```'); }
    if (p.images && p.images.length) out.push(`**Images:** ${p.images.map(im => `\`${im.rel}\` (${im.label})`).join(' · ')}`);
    if (p.visual) out.push(`**Visual:** ${p.visual}`);
    out.push(`**Hashtags:** ${p.hashtags}`);
    out.push(`**CTA:** ${p.cta}`);
    out.push(`**Engagement Q:** ${p.question}`);
    out.push('');
  });
  out.push('---');
  out.push(`_${pieces.length} pieces.${refused && refused.length ? ` ${refused.length} refused by the copy guard: ${refused.map(r => `${r.id} (${r.reason})`).join('; ')}.` : ''}_`);
  out.push('');
  return out.join('\n');
}

// Dated posting plan: spreads pieces across the 6 days before the card + day
// after, morning/evening slots, one landing link per piece with ?src=.
function scheduleRows(event, pieces) {
  const offsets = [-6, -5, -4, -3, -2, -1, 0, 1];
  const times = ['09:00', '18:30'];
  return pieces.map((p, i) => {
    const off = offsets[Math.floor(i / times.length) % offsets.length];
    const time = times[i % times.length];
    const date = isoOffset(event.event_date, off);
    const pl = p.platform.toLowerCase();
    const src = pl.includes('tiktok') ? 'tiktok' : pl.includes('instagram') ? 'ig' : pl.includes('reddit') ? 'reddit' : 'x';
    const srcLink = pl.includes('reddit') ? 'value-post-no-link' : cardUrl(event, src);
    return { date, time, platform: p.platform, pillar: p.pillar, id: p.id, tag: p.tag, srcLink, status: 'draft' };
  });
}

function renderScheduleCsv(event, pieces) {
  const header = ['date', 'time_local', 'platform', 'pillar', 'piece_id', 'tag', 'src_link', 'status'];
  const rows = [header, ...scheduleRows(event, pieces).map(r =>
    [r.date, r.time, r.platform, r.pillar, r.id, r.tag, r.srcLink, r.status])];
  return rows.map(r => r.map(c => /[",]/.test(c) ? `"${c.replace(/"/g, '""')}"` : c).join(',')).join('\n') + '\n';
}

// ------------------------------------------------------------- dashboard ---
// Self-contained HTML dashboard (no server, no external calls) embedding every
// batch as inline JSON: browse by card, filter by platform/pillar, one-click
// copy on the post body / hashtags / full piece. Double-click the file to open.
function renderDashboard(batches, generatedISO) {
  const data = batches.map(b => {
    const sched = scheduleRows(b.event, b.pieces);
    const whenById = {};
    sched.forEach(r => { whenById[r.id] = `${shortDate(r.date)} · ${r.time}`; });
    return {
      id: `${slugify(b.event.name)}-${b.event.id}`,
      name: b.event.name,
      date: b.event.event_date,
      dateLabel: formatLongDate(b.event.event_date),
      location: b.event.location || '',
      cardUrl: `${SITE}/card/${cardSlug(b.event.name, b.event.id)}.html`,
      pieces: b.pieces.map(p => ({
        tag: p.tag, id: p.id, platform: p.platform, pillar: p.pillar,
        copy: p.copy, hashtags: p.hashtags, cta: p.cta, question: p.question, visual: p.visual || '',
        when: whenById[p.id] || '',
        images: (p.images || []).map(im => ({ key: im.key, label: im.label, rel: im.rel, w: im.w, h: im.h })),
      })),
      schedule: sched,
    };
  });
  // Safe-embed JSON inside <script> (escape the sequence that could close it).
  const json = JSON.stringify(data).replace(/</g, '\\u003c');
  const totalPieces = data.reduce((s, b) => s + b.pieces.length, 0);
  const totalImages = data.reduce((s, b) => s + b.pieces.reduce((n, p) => n + p.images.length, 0), 0);

  return `<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CFL Content Engine — social batches</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700;800&family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@500;600&display=swap" rel="stylesheet">
<style>
  :root { --bg:#08090b; --panel:#0f1318; --panel2:#161a20; --line:#20252d; --line2:#2b313b;
    --red:#ff3b47; --green:#3fd07a; --amber:#ffb547; --muted:#7d8794; --text2:#a0a8b4; --text:#f4f6f8; }
  * { box-sizing:border-box; }
  body { background:var(--bg); color:var(--text); font-family:"Space Grotesk",-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; margin:0; line-height:1.5; }
  header { padding:22px 20px 14px; border-bottom:1px solid var(--line); position:sticky; top:0;
    background:rgba(8,9,11,.86); backdrop-filter:saturate(160%) blur(12px); z-index:5; }
  h1 { margin:0; font-family:"Barlow Condensed",sans-serif; font-weight:800; text-transform:uppercase; letter-spacing:.02em; font-size:26px; } h1 .r { color:var(--red); }
  .sub { color:var(--muted); font-size:13px; margin-top:4px; }
  .wrap { max-width:1020px; margin:0 auto; padding:20px; }
  .controls { display:flex; gap:10px; flex-wrap:wrap; margin-top:14px; }
  select, .tabbtn { background:var(--panel); color:var(--text); border:1px solid var(--line); border-radius:8px; padding:8px 12px; font-size:13px; cursor:pointer; font-family:inherit; }
  .tabbtn.active { border-color:var(--red); color:#fff; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:16px; margin-bottom:14px; }
  .meta { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-bottom:10px; }
  .badge { font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.5px; padding:3px 8px; border-radius:6px; background:var(--red); color:#fff; font-family:"Inter",sans-serif; }
  .badge.alt { background:var(--panel2); color:var(--text2); border:1px solid var(--line); }
  .badge.pillar { background:#12202a; color:#7fd3ea; }
  pre { white-space:pre-wrap; background:#0b0d10; border:1px solid var(--line); border-radius:10px; padding:13px; font-size:13.5px; font-family:'SF Mono',Menlo,Consolas,monospace; color:#eaeef2; margin:0 0 10px; }
  .row { font-size:12.5px; color:var(--muted); margin:4px 0; }
  .row b { color:var(--text2); font-weight:600; }
  .btns { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
  button.copy { background:transparent; color:var(--red); border:1px solid var(--red); border-radius:8px; padding:6px 12px; font-size:12px; cursor:pointer; font-family:inherit; font-weight:500; }
  button.copy:hover { background:var(--red); color:#fff; }
  button.copy.done { background:var(--green); border-color:var(--green); color:#04120a; }
  .thumbs { display:flex; gap:10px; flex-wrap:wrap; margin:0 0 12px; }
  .thumb { display:block; border:1px solid var(--line); border-radius:10px; overflow:hidden; background:#0b0d10; text-decoration:none; transition:border-color .12s, transform .12s; }
  .thumb:hover { border-color:var(--red); transform:translateY(-2px); }
  .thumb img { display:block; width:132px; height:132px; object-fit:contain; background:#08090b; }
  .thumb .tlabel { display:block; font-family:"Inter",sans-serif; font-size:10.5px; color:var(--text2); text-align:center; padding:5px 4px; border-top:1px solid var(--line); }
  table { width:100%; border-collapse:collapse; font-size:12.5px; }
  th,td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); }
  th { color:var(--muted); font-weight:600; }
  a { color:var(--red); }
  .hint { color:var(--muted); font-size:12px; margin:10px 0 18px; }
  /* approval queue */
  .filters { display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; }
  .fbtn { background:var(--panel); border:1px solid var(--line); color:var(--text2); border-radius:20px; padding:6px 14px; font-size:12.5px; cursor:pointer; font-family:inherit; }
  .fbtn.active { border-color:var(--red); color:#fff; }
  #progress { margin-top:10px; font-weight:500; }
  .card.approved { border-color:var(--green); box-shadow:inset 3px 0 0 var(--green); }
  .card.posted { opacity:.5; }
  .card.skip { opacity:.42; }
  .when { font-family:"Inter",sans-serif; font-size:11px; color:var(--muted); margin-left:auto; }
  button.pub { background:var(--red); color:#fff; border:1px solid var(--red); border-radius:8px; padding:7px 14px; font-size:12.5px; font-weight:600; cursor:pointer; font-family:inherit; }
  button.pub:hover { filter:brightness(1.08); }
  button.pub.app { background:var(--panel2); color:var(--text); border-color:var(--line2); }
  button.pub.done { background:var(--green); border-color:var(--green); color:#04120a; }
  .statusbar { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; padding-top:10px; border-top:1px solid var(--line); }
  .stbtn { background:transparent; border:1px solid var(--line2); color:var(--text2); border-radius:8px; padding:6px 13px; font-size:12px; cursor:pointer; font-family:inherit; }
  .stbtn.ap.act { background:var(--green); color:#04120a; border-color:var(--green); font-weight:600; }
  .stbtn.po.act { background:var(--panel2); color:var(--text); border-color:var(--line2); font-weight:600; }
  .stbtn.sk.act { background:transparent; color:var(--muted); border-color:var(--muted); }
</style></head>
<body>
<header>
  <div class="wrap" style="padding-bottom:0">
    <h1>Cannon Fight <span class="r">Lab</span> — Content Engine</h1>
    <div class="sub">${totalPieces} ready-to-post pieces · ${totalImages} branded images across ${data.length} cards · generated ${generatedISO.slice(0,10)} · no picks, public market and fight data only</div>
    <div class="controls">
      <button class="tabbtn active" data-view="content" onclick="setView('content')">📋 Content</button>
      <button class="tabbtn" data-view="schedule" onclick="setView('schedule')">🗓️ Schedule</button>
      <select id="cardSel" onchange="render()"></select>
      <select id="platSel" onchange="render()"></select>
      <select id="pillSel" onchange="render()"></select>
    </div>
    <div class="filters" id="filters"></div>
    <div class="sub" id="progress"></div>
  </div>
</header>
<div class="wrap">
  <div class="hint"><b>Workflow:</b> review a post → <b>download its image</b> (click a thumbnail) → tap <b>Post to X</b> / <b>Submit to Reddit</b> (opens the composer pre-filled — attach the image, post) or <b>Copy caption</b> for Instagram/TikTok (post from the phone app). Then hit <b>Mark posted</b>. Your Approve/Posted marks are saved in this browser. Reddit pieces are value-posts — no link drop.</div>
  <div id="out"></div>
</div>
<script>
const DATA = JSON.parse(${JSON.stringify(json)});
let VIEW='content', SFILTER='all';
const SKEY='cfl_post_state_v1';
let STATE={}; try{ STATE=JSON.parse(localStorage.getItem(SKEY)||'{}'); }catch(e){}
function saveState(){ try{ localStorage.setItem(SKEY,JSON.stringify(STATE)); }catch(e){} }
function uid(c,p){ return c+'::'+p; }
function st(u){ return STATE[u]||'review'; }
function setSt(u,s){ STATE[u]=(STATE[u]===s?'review':s); saveState(); render(); refreshCounts(); }
function setStBtn(btn){ setSt(btn.dataset.u, btn.dataset.s); }

function opts(sel, vals, label){ sel.innerHTML = '<option value="">'+label+'</option>' + vals.map(v=>'<option>'+v+'</option>').join(''); }
function esc(s){ return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
function flash(btn,msg){ const o=btn.textContent;btn.textContent=msg||'✓ Copied';btn.classList.add('done');setTimeout(()=>{btn.textContent=o;btn.classList.remove('done');},1300); }
function copyText(t,btn){ if(navigator.clipboard && window.isSecureContext){ navigator.clipboard.writeText(t).then(()=>flash(btn)).catch(()=>fallbackCopy(t,btn)); } else { fallbackCopy(t,btn); } }
function fallbackCopy(t,btn){ const ta=document.createElement('textarea'); ta.value=t; ta.style.position='fixed'; ta.style.opacity='0'; document.body.appendChild(ta); ta.focus(); ta.select(); try{ document.execCommand('copy'); flash(btn); }catch(e){ btn.textContent='Select + copy manually'; } document.body.removeChild(ta); }
function copyBtn(btn){ copyText(btn.dataset.c, btn); }

function open2(u){ window.open(u,'_blank','noopener'); }
function pubX(btn){ open2('https://twitter.com/intent/tweet?text='+encodeURIComponent(btn.dataset.c)); flash(btn,'↗ Opened X'); }
function pubReddit(btn){ const copy=btn.dataset.c; const m=copy.match(/^\\s*TITLE:\\s*(.+)$/m); const title=m?m[1].trim():copy.split('\\n')[0].slice(0,290); let text=copy; if(m){ text=copy.slice(copy.indexOf(m[0])+m[0].length).replace(/^\\s+/,''); } open2('https://www.reddit.com/submit?title='+encodeURIComponent(title)+'&text='+encodeURIComponent(text)+'&type=TEXT'); flash(btn,'↗ Opened Reddit'); }

function fullText(p){ return p.copy+'\\n\\n'+p.hashtags; }
function pubButton(p){
  const plat=p.platform.toLowerCase();
  if(plat.indexOf('reddit')>-1) return '<button class="pub" data-c="'+esc(p.copy).replace(/"/g,'&quot;')+'" onclick="pubReddit(this)">↗ Submit to Reddit</button>';
  if(plat.indexOf('instagram')>-1||plat.indexOf('tiktok')>-1) return '<button class="pub app" data-c="'+esc(fullText(p)).replace(/"/g,'&quot;')+'" onclick="copyBtn(this)">⧉ Copy caption (post in app)</button>';
  return '<button class="pub" data-c="'+esc(fullText(p)).replace(/"/g,'&quot;')+'" onclick="pubX(this)">↗ Post to X</button>';
}
function statusCtl(u){
  const s=st(u);
  return '<div class="statusbar">'+
    '<button class="stbtn ap'+(s==='approved'?' act':'')+'" data-u="'+u+'" data-s="approved" onclick="setStBtn(this)">'+(s==='approved'?'✓ Approved':'Approve')+'</button>'+
    '<button class="stbtn po'+(s==='posted'?' act':'')+'" data-u="'+u+'" data-s="posted" onclick="setStBtn(this)">'+(s==='posted'?'✓ Posted':'Mark posted')+'</button>'+
    '<button class="stbtn sk'+(s==='skip'?' act':'')+'" data-u="'+u+'" data-s="skip" onclick="setStBtn(this)">'+(s==='skip'?'Skipped':'Skip')+'</button>'+
  '</div>';
}
function counts(){ const c={review:0,approved:0,posted:0,skip:0,total:0}; DATA.forEach(b=>b.pieces.forEach(p=>{c[st(uid(b.id,p.id))]++;c.total++;})); return c; }
function fbtn(v,label){ return '<button class="fbtn'+(SFILTER===v?' active':'')+'" data-v="'+v+'" onclick="SFILTER=this.dataset.v;refreshCounts();render();">'+label+'</button>'; }
function refreshCounts(){ const c=counts();
  document.getElementById('filters').innerHTML=fbtn('all','All ('+c.total+')')+fbtn('review','To review ('+c.review+')')+fbtn('approved','Approved ('+c.approved+')')+fbtn('posted','Posted ('+c.posted+')')+(c.skip?fbtn('skip','Skipped ('+c.skip+')'):'');
  document.getElementById('progress').textContent='📤 '+c.posted+' posted  ·  ✅ '+c.approved+' approved & ready  ·  ⏳ '+c.review+' to review';
}
function setView(v){ VIEW=v; document.querySelectorAll('.tabbtn').forEach(b=>b.classList.toggle('active',b.dataset.view===v)); render(); }
function init(){
  const cards=[...new Set(DATA.map(d=>d.name))];
  const plats=[...new Set(DATA.flatMap(d=>d.pieces.map(p=>p.platform)))];
  const pills=[...new Set(DATA.flatMap(d=>d.pieces.map(p=>p.pillar)))];
  opts(document.getElementById('cardSel'),cards,'All cards');
  opts(document.getElementById('platSel'),plats,'All platforms');
  opts(document.getElementById('pillSel'),pills,'All pillars');
  refreshCounts(); render();
}
function render(){
  const card=document.getElementById('cardSel').value, plat=document.getElementById('platSel').value, pill=document.getElementById('pillSel').value;
  const out=document.getElementById('out');
  const batches=DATA.filter(d=>!card||d.name===card);
  if(VIEW==='schedule'){
    out.innerHTML = batches.map(b=>{
      const rows=b.schedule.filter(r=>(!plat||r.platform===plat)&&(!pill||r.pillar===pill));
      if(!rows.length) return '';
      return '<div class="card"><div class="meta"><span class="badge">'+esc(b.name)+'</span><span class="row">'+esc(b.dateLabel)+'</span></div>'+
        '<table><thead><tr><th>Date</th><th>Time</th><th>Platform</th><th>Pillar</th><th>Piece</th></tr></thead><tbody>'+
        rows.map(r=>'<tr><td>'+r.date+'</td><td>'+r.time+'</td><td>'+esc(r.platform)+'</td><td>'+esc(r.pillar)+'</td><td>'+esc(r.id)+'</td></tr>').join('')+
        '</tbody></table></div>';
    }).join('') || '<p class="row">No rows match.</p>';
    return;
  }
  let html='';
  for(const b of batches){
    const pieces=b.pieces.filter(p=>(!plat||p.platform===plat)&&(!pill||p.pillar===pill)&&(SFILTER==='all'||st(uid(b.id,p.id))===SFILTER));
    if(!pieces.length) continue;
    html+='<div class="meta" style="margin:18px 0 10px"><span class="badge">'+esc(b.name)+'</span>'+
      '<span class="row">'+esc(b.dateLabel)+(b.location?' · '+esc(b.location):'')+' · <a href="'+b.cardUrl+'" target="_blank">card page ↗</a></span></div>';
    for(const p of pieces){
      const u=uid(b.id,p.id), s=st(u);
      html+='<div class="card '+(s!=='review'?s:'')+'"><div class="meta">'+
        '<span class="badge">'+esc(p.tag)+'</span><span class="badge alt">'+esc(p.platform)+'</span><span class="badge pillar">'+esc(p.pillar)+'</span>'+
        (p.when?'<span class="when">🗓 '+esc(p.when)+'</span>':'')+'</div>'+
        (p.images&&p.images.length?'<div class="thumbs">'+p.images.map(im=>'<a class="thumb" href="'+im.rel+'" target="_blank" download><img src="'+im.rel+'" loading="lazy" alt=""><span class="tlabel">'+esc(im.label)+' &darr;</span></a>').join('')+'</div>':'')+
        '<pre>'+esc(p.copy)+'</pre>'+
        (p.visual?'<div class="row"><b>Visual:</b> '+esc(p.visual)+'</div>':'')+
        '<div class="row"><b>Hashtags:</b> '+esc(p.hashtags)+'</div>'+
        '<div class="row"><b>CTA:</b> '+esc(p.cta)+'</div>'+
        '<div class="row"><b>Engagement Q:</b> '+esc(p.question)+'</div>'+
        '<div class="btns">'+pubButton(p)+
          '<button class="copy" onclick="copyBtn(this)" data-c="'+esc(p.copy).replace(/"/g,'&quot;')+'">Copy post</button>'+
          '<button class="copy" onclick="copyBtn(this)" data-c="'+esc(p.hashtags).replace(/"/g,'&quot;')+'">+tags</button>'+
          '<button class="copy" onclick="copyBtn(this)" data-c="'+esc(fullText(p)).replace(/"/g,'&quot;')+'">All</button>'+
        '</div>'+
        statusCtl(u)+
      '</div>';
    }
  }
  out.innerHTML = html || '<p class="row">Nothing matches this filter — try the All filter.</p>';
}
init();
</script>
</body></html>
`;
}

// ------------------------------------------------------------------- I/O ---
// Everything above is pure. Below is the only code that touches the network
// or the file system, and it reads exactly the SOURCES listed at the top.

async function loadCard(sb, event) {
  const { data: fights, error: fErr } = await sb.from('fights')
    .select('id, event_id, fighter_a_id, fighter_b_id, fighter_a_name, fighter_b_name, is_main_event, is_title_fight, weight_class, bout_order, is_active')
    .eq('event_id', event.id);
  if (fErr) throw new Error(`fights: ${fErr.message}`);
  const list = (fights || []).filter(f => f.id && f.fighter_a_id && f.fighter_b_id);
  if (!list.length) return { event, fights: [], market: [], fighters: [], finish_rates: [], cardio: [] };
  const ids = [...new Set(list.flatMap(f => [f.fighter_a_id, f.fighter_b_id]))];

  const [mR, fR, finR, cR] = await Promise.all([
    sb.from('v_fight_market_movement').select('*').eq('event_id', event.id),
    sb.from('fighters').select('id, name, age, height_in, reach_in, stance, wins, losses, draws, fighting_style, fighting_style_src, country').in('id', ids),
    sb.from('v_fighter_finish_rate').select('fighter_id, total_fights, decision_rate, ko_tko_rate, sub_rate').in('fighter_id', ids),
    sb.from('v_fighter_consistency').select('fighter_id, weight_class, cardio_tier, confidence_tier, recent_fights').eq('weight_class', 'CAREER').in('fighter_id', ids),
  ]);
  // A market view that cannot be read must not become a card with no prices
  // on it: say so and skip the card.
  if (mR.error) throw new Error(`v_fight_market_movement: ${mR.error.message}`);
  return {
    event, fights: list, market: mR.data || [], fighters: fR.data || [],
    finish_rates: finR.data || [], cardio: cR.data || [],
  };
}

async function main() {
  const { createClient } = require('@supabase/supabase-js');
  const { findChrome, renderPieceImages } = require('./post-cards');
  const sb = createClient(SUPABASE_URL, SUPABASE_KEY);
  const arg = (process.argv.find(a => a.startsWith('--event=')) || '').split('=')[1];

  let events;
  if (arg) {
    const { data } = await sb.from('events').select('id, name, event_date, location').eq('id', +arg);
    events = data || [];
  } else {
    const { data } = await sb.from('events').select('id, name, event_date, location')
      .eq('is_upcoming', true).order('event_date', { ascending: true });
    events = data || [];
  }
  if (!events.length) { console.log('No matching events.'); return; }

  const index = ['# Social batches', '', '_Auto-generated by `build/social-engine.js` from public market and fight data. Open `dashboard.html` to browse + copy. One folder per upcoming card._', ''];
  const batches = [];
  let totalPieces = 0, totalImages = 0;

  const chrome = findChrome();
  if (chrome) console.log(`Rendering images with: ${chrome}`);
  else console.warn('[social-engine] No Chrome/Chromium found — generating copy only (no images). Set CFL_CHROME=<path> to enable image rendering.');

  for (const event of events) {
    let data;
    try { data = await loadCard(sb, event); }
    catch (e) { console.warn(`skip ${event.name} — ${e.message}`); continue; }
    const { rows, pieces, refused } = buildBatch(data);
    refused.forEach(r => console.warn(`[social-engine] ${event.name}: refused ${r.id} — ${r.reason}`));
    if (!rows.length) { console.log(`skip ${event.name} — no fights`); continue; }
    if (!pieces.length) { console.log(`skip ${event.name} — no market or fight data to ground content`); continue; }

    const slug = `${slugify(event.name)}-${event.id}`;
    const dir = path.join(SOCIAL_DIR, slug);
    let imgCount = 0;
    if (chrome) {
      const imgDir = path.join(dir, 'img');
      for (const p of pieces) {
        p.images = renderPieceImages(chrome, p, imgDir, `${slug}/img`);
        imgCount += p.images.length;
      }
    }

    const wroteMd = writeIfChanged(path.join(dir, 'batch.md'), renderBatchMd(event, rows, pieces, refused));
    const wroteCsv = writeIfChanged(path.join(dir, 'schedule.csv'), renderScheduleCsv(event, pieces));
    batches.push({ event, pieces });
    totalPieces += pieces.length;
    totalImages += imgCount;
    index.push(`- **${event.name}** (${shortDate(event.event_date)}) — ${pieces.length} pieces, ${imgCount} images → \`social/${slug}/\``);
    console.log(`${event.name}: ${pieces.length} pieces, ${imgCount} images ${wroteMd || wroteCsv ? '(written)' : '(unchanged)'}`);
  }

  index.push('', `_${totalPieces} pieces + ${totalImages} images across ${batches.length} cards. Public market and fight data only._`, '');
  writeIfChanged(path.join(SOCIAL_DIR, 'index.md'), index.join('\n'));

  const queue = buildQueue(batches);
  writeIfChanged(path.join(SOCIAL_DIR, 'queue.json'), JSON.stringify(queue, null, 2) + '\n');
  console.log(`Queue: ${queue.length} X posts → social/queue.json`);

  const mrows = buildMetricoolRows(batches);
  writeIfChanged(path.join(SOCIAL_DIR, 'metricool.csv'), renderMetricoolCsv(mrows));
  console.log(`Metricool: ${mrows.length} IG/TikTok rows → social/metricool.csv`);

  writeIfChanged(path.join(SOCIAL_DIR, 'NEXT-POSTS.md'), buildNextPostsMd(batches));
  writeIfChanged(path.join(SOCIAL_DIR, 'posts-data.json'), JSON.stringify(buildPostsData(batches), null, 2) + '\n');

  const generatedISO = new Date().toISOString();
  writeIfChanged(path.join(SOCIAL_DIR, 'dashboard.html'), renderDashboard(batches, generatedISO));
  console.log(`Done. ${totalPieces} pieces + ${totalImages} images total. Dashboard: social/dashboard.html`);
}

module.exports = {
  SOURCES, assembleRows, buildBatch, buildPieces, rawPieces, guardPieces, refusalOf,
  pieceText, buildQueue, buildMetricoolRows, buildPostsData, buildNextPostsMd,
  renderBatchMd, tweetify, finishHistory,
};

if (require.main === module) {
  main().catch(err => { console.error('[social-engine] failed:', err); process.exit(1); });
}
