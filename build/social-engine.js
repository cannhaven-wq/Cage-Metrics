// Content engine: turns the live model state for every upcoming UFC card into
// a ready-to-post social batch (X, TikTok/IG Reels, Reddit) + a dated
// scheduling CSV, written to /social/<event-slug>-<id>/.
//
// It is a GENERATOR, not a poster — it never touches an account and needs no
// secrets (same publishable anon key as the rest of the site; RLS protects
// everything). A human reviews the batch, then schedules it.
//
// Brand rules enforced in every template:
//   - value-first, curious-insider tone; NO hype/guarantees/"best picks"/betting language
//   - every piece ends with a soft CTA + a genuine engagement question
//   - links carry ?src=<platform> so Plausible can attribute signups
//   - real model data only; "camp intel" is never fabricated — pieces that
//     need news carry an explicit [verify + insert real intel] slot.
//
// Usage:
//   cd build && node social-engine.js            # all upcoming cards
//   cd build && node social-engine.js --event=117  # one event id

const fs = require('fs');
const path = require('path');
const { createClient } = require('@supabase/supabase-js');
const { slugify } = require('./slug');
const { consensusPick, cardOrder, cardSlug } = require('./event-preview-templates');
const { findChrome, renderPieceImages } = require('./post-cards');

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SUPABASE_KEY = 'sb_publishable_boJGOA1CFN-SF14HHFGUAw_YEEm0DU8';
const SITE = 'https://cannonfightlab.com';

const ROOT = path.resolve(__dirname, '..');
const SOCIAL_DIR = path.join(ROOT, 'social');

const sb = createClient(SUPABASE_URL, SUPABASE_KEY);

// ---------------------------------------------------------------- helpers ---

const CARDIO_LABEL = {
  tireless:  'tireless (output holds R3+)',
  steady:    'steady (no real late dropoff)',
  tapers:    'tapers (measurable late fade)',
  fades:     'fades (real trouble in deep water)',
  collapses: 'collapses (output falls off a cliff R3+)'
};
const CARDIO_FLAGGED = new Set(['tapers', 'fades', 'collapses']);
const CARDIO_BADGE = { tireless: '🟢', steady: '🟢', tapers: '🟡', fades: '🟠', collapses: '🔴' };

const HASHTAG_CORE = ['#MMA', '#UFC', '#MMATwitter', '#FightIQ', '#MMAanalytics'];

function eventHashtag(name) {
  // "UFC 329: ..." -> #UFC329 ; "UFC Fight Night: ..." -> #UFCFightNight
  const m = String(name).match(/UFC\s+(\d+)/i);
  if (m) return `#UFC${m[1]}`;
  if (/fight night/i.test(name)) return '#UFCFightNight';
  return '#UFC';
}

// Short, sentence-friendly event label. Numbered cards collapse to "UFC 329"
// (the subtitle is redundant mid-copy); Fight Nights keep their subtitle since
// that's what identifies them.
function shortName(name) {
  const m = String(name).match(/^UFC\s+\d+/i);
  return m ? m[0].toUpperCase().replace(/\s+/g, ' ') : String(name);
}

function lastNameTag(fullName) {
  const parts = String(fullName).trim().split(/\s+/);
  const last = parts[parts.length - 1] || '';
  const clean = last.replace(/[^A-Za-z]/g, '');
  return clean.length >= 3 ? '#' + clean : null;
}

function hashtags(eventName, ...names) {
  const tags = [eventHashtag(eventName), ...HASHTAG_CORE];
  names.forEach(n => { const t = lastNameTag(n); if (t && !tags.includes(t)) tags.push(t); });
  return tags.slice(0, 8).join(' ');
}

function link(page, src) { return `${SITE}/${page}?src=${src}`; }

function finishPct(rec) {
  if (!rec || !rec.total_fights) return null;
  return { pct: Math.round(((rec.ko_tko_rate || 0) + (rec.sub_rate || 0)) * 100), n: rec.total_fights };
}

function formatLongDate(isoDate) {
  const d = new Date(isoDate + 'T00:00:00');
  return d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
}
function shortDate(isoDate) {
  const d = new Date(isoDate + 'T00:00:00');
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
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

// ---------------------------------------------------------- data assembly ---

// Returns { event, rows } where each row is
//   { fight, a, b, pick, cardioA, cardioB, finA, finB }
// pick = consensusPick(...) | null, cardio* = tier string | null, fin* = {pct,n} | null
async function loadCard(event) {
  const { data: fights } = await sb.from('fights')
    .select('id, fighter_a_id, fighter_b_id, fighter_a_name, fighter_b_name, is_main_event, is_title_fight, weight_class')
    .eq('event_id', event.id);
  const list = (fights || []).filter(f => f.id && f.fighter_a_id && f.fighter_b_id);
  if (!list.length) return { event, rows: [] };

  const fighterIds = [...new Set(list.flatMap(f => [f.fighter_a_id, f.fighter_b_id]))];
  const fightIds = list.map(f => f.id);

  const [fR, pR, cR, finR] = await Promise.all([
    sb.from('fighters').select('id, name, nickname').in('id', fighterIds),
    sb.from('model_predictions').select('fight_id, fighter_id, model_p').in('fight_id', fightIds),
    sb.from('v_fighter_consistency').select('fighter_id, weight_class, cardio_tier').in('fighter_id', fighterIds),
    sb.from('v_fighter_finish_rate').select('fighter_id, total_fights, ko_tko_rate, sub_rate').in('fighter_id', fighterIds),
  ]);

  const fmap = {}; (fR.data || []).forEach(f => { fmap[f.id] = f; });
  const picksByFight = {};
  (pR.data || []).forEach(p => { (picksByFight[p.fight_id] || (picksByFight[p.fight_id] = [])).push(p); });
  const cardio = {}; (cR.data || []).forEach(r => { if (r.weight_class === 'CAREER') cardio[r.fighter_id] = r.cardio_tier; });
  const finish = {}; (finR.data || []).forEach(r => { finish[r.fighter_id] = r; });

  const rows = list.map(fight => {
    const a = fmap[fight.fighter_a_id] || { id: fight.fighter_a_id, name: fight.fighter_a_name };
    const b = fmap[fight.fighter_b_id] || { id: fight.fighter_b_id, name: fight.fighter_b_name };
    return {
      fight, a, b,
      pick: consensusPick(picksByFight[fight.id] || [], a, b),
      cardioA: cardio[a.id] || null,
      cardioB: cardio[b.id] || null,
      finA: finishPct(finish[a.id]),
      finB: finishPct(finish[b.id]),
    };
  }).filter(r => r.a.name && r.b.name);

  rows.sort((x, y) => cardOrder(x.fight, y.fight));
  return { event, rows };
}

// For a row, resolve the picked ("winner") and non-picked ("other") sides with
// their cardio/finish, so pillar templates can talk about "the pick" naturally.
function sides(row) {
  if (!row.pick) return null;
  const winIsA = row.pick.winnerId === row.a.id;
  return {
    win:   winIsA ? row.a : row.b,
    other: winIsA ? row.b : row.a,
    winCardio:   winIsA ? row.cardioA : row.cardioB,
    otherCardio: winIsA ? row.cardioB : row.cardioA,
    winFin:   winIsA ? row.finA : row.finB,
    otherFin: winIsA ? row.finB : row.finA,
    pct: row.pick.pct, agree: row.pick.agree, total: row.pick.total,
  };
}

// --------------------------------------------------------- image specs ---
// Structured data → the post-card renderer turns these into finished PNGs sized
// per platform. Punchy display names (surname only) keep headlines tight.
function lastName(n) {
  const p = String(n).trim().split(/\s+/);
  return (p[p.length - 1] || String(n)).toUpperCase();
}
function cap(t) { return t ? t.charAt(0).toUpperCase() + t.slice(1) : t; }

// Compact event label for image eyebrows — one clean line. Numbered cards keep
// their number; Fight Nights drop the subtitle (the headline names the fight).
function compactEvent(name) {
  const m = String(name).match(/^UFC\s+\d+/i);
  if (m) return m[0].toUpperCase().replace(/\s+/g, ' ');
  if (/fight night/i.test(name)) return 'UFC Fight Night';
  return String(name);
}

function baseVerdictImage(event, s, pillarLabel) {
  return {
    layout: 'verdict',
    eyebrow: `${pillarLabel} · ${compactEvent(event.name)}`,
    fa: lastName(s.win.name),
    fb: lastName(s.other.name),
    big: `${s.pct}%`,
    bigCap: `Model leans ${lastName(s.win.name)}`,
    chips: [
      { k: 'Confidence', v: `${s.pct}%` },
      { k: 'Models agree', v: `${s.agree}/${s.total}` },
    ],
    cta: 'Full card breakdown → cannonfightlab.com',
  };
}

// ------------------------------------------------------------- generators ---
// Each returns an array of piece objects (or []). A piece:
//   { tag, id, platform, pillar, copy, hashtags, cta, question, visual?, image? }
// `image` (optional) is a spec rendered to PNGs by post-cards.js.

function pieceCardLink(event, src) {
  return `${SITE}/card/${cardSlug(event.name, event.id)}.html?src=${src}`;
}

// Pillar 1 — Sensor Read (main event, cardio-vs-pick tension when present)
function genSensorRead(event, rows) {
  const main = rows.find(r => r.fight.is_main_event) || rows[0];
  if (!main || !main.pick) return [];
  const s = sides(main);
  const ehash = eventHashtag(event.name);
  const url = pieceCardLink(event, 'x');

  let tensionLines;
  if (s.winCardio && CARDIO_FLAGGED.has(s.winCardio) && s.winFin && s.winFin.pct >= 55) {
    // Model likes the pick BUT flags their cardio → timeline bet.
    tensionLines =
`2/ But our cardio sensor tags ${s.win.name} "${s.winCardio}"${s.otherCardio ? `, ${s.other.name} "${s.otherCardio}"` : ''}.

3/ So the model finish-weights ${s.win.name} (${s.winFin.pct}% of wins are finishes over ${s.winFin.n}) — but the longer it goes, the more that edge thins.

4/ Read it as a timeline bet: end it early, ${s.win.name}. Deep water? The number drifts the other way.`;
  } else if (s.otherCardio && CARDIO_FLAGGED.has(s.otherCardio)) {
    tensionLines =
`2/ The lever our sensor leans on: ${s.other.name} tags "${s.otherCardio}" late${s.winFin ? `, and ${s.win.name} finishes ${s.winFin.pct}% of wins (${s.winFin.n})` : ''}.

3/ Translation — the danger window is the championship rounds, not the opening exchanges.`;
  } else {
    tensionLines =
`2/ What's driving it: ${s.winFin ? `${s.win.name} finishes ${s.winFin.pct}% of wins over ${s.winFin.n} graded fights` : 'a stack of small edges rather than one headline stat'}.

3/ Not a lock — a lean the models happen to share, and we'll show you every factor behind it.`;
  }

  const copy =
`Our model locked ${shortName(event.name)} — and the ${s.win.name}–${s.other.name} read is more interesting than the pick itself. 🧵

1/ The verdict: ${s.win.name}, ${s.pct}% (${s.agree} of ${s.total} models agree).

${tensionLines}

5/ Every factor is on the card page. Curious where you land.`;

  const img = baseVerdictImage(event, s, 'Sensor Read');
  if (s.winCardio && CARDIO_FLAGGED.has(s.winCardio)) img.chips.push({ k: 'Cardio', v: cap(s.winCardio), tone: 'warn' });
  else if (s.winFin) img.chips.push({ k: 'Finish rate', v: `${s.winFin.pct}%`, tone: 'win' });

  return [{
    tag: 'X-POST', id: 'sensor-main', platform: 'X', pillar: 'P1-SensorRead',
    copy, image: img,
    hashtags: hashtags(event.name, s.win.name, s.other.name),
    cta: `Full model + factors on site (${url}) — what do you think?`,
    question: `Round 1 ${s.win.name} or deep-water ${s.other.name}?`,
  }, {
    tag: 'TIKTOK-REEL', id: 'sensor-main-reel', platform: 'TikTok', pillar: 'P1-SensorRead', image: img,
    copy:
`HOOK (0-3s): "Our model picked ${s.win.name}. Then our OWN data started arguing with it."
BODY (3-22s): "${s.pct}% ${s.win.name} — ${s.winFin ? `they finish ${s.winFin.pct}% of their wins` : 'the models agree'}. ${s.winCardio && CARDIO_FLAGGED.has(s.winCardio) ? `But we tag them "${s.winCardio}." ${s.other.name}? "${s.otherCardio || 'steadier'}." Same fight, two timelines.` : `The edge is real but thin — here's what tips it.`}"
CTA (22-30s): "We show you the whole disagreement — link in bio. What's your call?"`,
    hashtags: hashtags(event.name, s.win.name, s.other.name) + ' #FightTok #fyp',
    cta: 'Full read → link in bio',
    question: `${s.win.name} early or ${s.other.name} late — where's your line?`,
    visual: `Creator to camera / green-screen over the card page; animated % counter reading ${s.pct}%; split "${(s.winCardio||'').toUpperCase()} / ${(s.otherCardio||'').toUpperCase()}" badges; crimson-on-black captions, fast cuts.`,
  }];
}

// Pillar 2 — Cardio & Collapse (favorites carrying a flagged tier)
function genCardio(event, rows) {
  const flagged = [];
  for (const r of rows) {
    const s = sides(r);
    if (s && s.winCardio && CARDIO_FLAGGED.has(s.winCardio)) {
      flagged.push({ name: s.win.name, tier: s.winCardio, note: `favored (${s.pct}%) but flagged` });
    }
  }
  if (flagged.length < 2) return []; // need at least a couple to make the point
  const top = flagged.slice(0, 4);
  const ehash = eventHashtag(event.name);
  const url = pieceCardLink(event, 'x');

  const boardImg = {
    layout: 'board',
    eyebrow: `Cardio Sensor · ${compactEvent(event.name)}`,
    title: 'The Gas Tank Board',
    rows: top.map(f => ({ name: lastName(f.name), tier: f.tier })),
    cta: 'Full card graded → cannonfightlab.com',
  };

  const listX = top.map(f => `• ${f.name} — ${CARDIO_BADGE[f.tier]} ${f.tier}`).join('\n');
  const xThread = {
    tag: 'X-POST', id: 'cardio-flagged', platform: 'X', pillar: 'P2-Cardio', image: boardImg,
    copy:
`Cardio sensor, ${shortName(event.name)}: ${top.length} model favorites are quietly flagged as late-faders. 🫁

${listX}

Built from round-by-round output rates, not vibes. Favorites ≠ finishers when the tank's empty — round 3 is where box scores get exposed.`,
    hashtags: hashtags(event.name, ...top.map(f => f.name)) + ' #Cardio',
    cta: `Full card graded on site (${url}) — what do you think?`,
    question: `Which of these do you think holds up fine, and why?`,
  };

  const carousel = {
    tag: 'IG-REEL', id: 'cardio-carousel', platform: 'Instagram', pillar: 'P2-Cardio', image: boardImg,
    copy:
`CAROUSEL — "The Gas Tank Board"
Slide 1: "${top.length} ${shortName(event.name)} favorites our cardio data is side-eyeing. 🫁"
${top.map((f, i) => `Slide ${i + 2}: ${f.name} — ${CARDIO_BADGE[f.tier]} ${f.tier.toUpperCase()} — ${CARDIO_LABEL[f.tier]}`).join('\n')}
Slide ${top.length + 2}: "Full card, every factor → link in bio."
CAPTION: Cardio doesn't lie in round 3. Here's who our model says quietly fades at ${shortName(event.name)}. Not hype — just the rate data.`,
    hashtags: hashtags(event.name, ...top.map(f => f.name)) + ' #Cardio #UFCReels',
    cta: 'Full breakdown + how it\'s built → link in bio',
    question: `Who's gassing that we\'ve got wrong?`,
    visual: `Dark charcoal (#0a0a0a) background, crimson (#e63946) accent, bold condensed white type, one large tier badge (🟢🟡🟠🔴) per slide, a small round-by-round line chart declining. Clinical "lab report" aesthetic.`,
  };

  const reddit = {
    tag: 'REDDIT-POST', id: 'cardio-reddit', platform: 'Reddit (r/MMA)', pillar: 'P2-Cardio',
    copy:
`TITLE: I graded every ${shortName(event.name)} fighter's round-3+ cardio from rate data. ${top.length} favorites came back flagged as late-faders — curious if the eye test agrees.

Been scoring deep-water cardio on 5 tiers (tireless → collapses) off round-by-round output rather than gut feel. On this card the model favors these fighters, but tags their gas tank:

${top.map(f => `- ${f.name} — ${f.tier}`).join('\n')}

Not saying they lose — saying the model thinks the danger window is late, which is the opposite of where casual reads put it. Which of these holds up fine in round 3 to you, and where's the data lying to me?

(Happy to share the full graded card + method — will DM to respect self-promo rules.)`,
    hashtags: '(Reddit — no hashtags; follow the sub\'s self-promo ratio, link only if asked)',
    cta: 'Link only on request / in a comment if allowed',
    question: `Which flagged favorite do the tape-watchers think is fine?`,
  };

  return [xThread, carousel, reddit];
}

// Pillar 3 — Coin-Flip Corner (genuine 53–57% near-toss-ups)
function genCoinFlip(event, rows) {
  const flips = rows
    .map(r => ({ r, s: sides(r) }))
    .filter(x => x.s && x.s.pct >= 53 && x.s.pct <= 57);
  if (!flips.length) return [];
  const url = pieceCardLink(event, 'x');
  const lead = flips[0];

  const coinImg = baseVerdictImage(event, lead.s, 'Coin-Flip Corner');
  coinImg.bigCap = `Razor-thin edge, ${lastName(lead.s.win.name)}`;
  coinImg.chips[1].k = 'Models';
  if (lead.s.winFin) coinImg.chips.push({ k: 'Finish rate', v: `${lead.s.winFin.pct}%`, tone: 'win' });

  const pieces = [{
    tag: 'X-POST', id: 'coinflip-lead', platform: 'X', pillar: 'P3-CoinFlip', image: coinImg,
    copy:
`Coin-Flip Corner 🪙

${lead.s.win.name} vs ${lead.s.other.name}. Our model: ${lead.s.win.name} ${lead.s.pct}%.

That's not a lean — that's a shrug with a lab coat on.${lead.s.winCardio && lead.s.otherCardio ? ` The wrinkle: ${lead.s.win.name} "${lead.s.winCardio}", ${lead.s.other.name} "${lead.s.otherCardio}."` : ''}

We'll tell you when we're barely off 50/50 — because a model you can only trust when it's confident isn't much of a model.`,
    hashtags: hashtags(event.name, lead.s.win.name, lead.s.other.name),
    cta: `Full factor breakdown on site (${url}) — what do you think?`,
    question: `Who cracks first?`,
  }, {
    tag: 'TIKTOK-REEL', id: 'coinflip-reel', platform: 'TikTok', pillar: 'P3-CoinFlip', image: coinImg,
    copy:
`HOOK: "Every picks account swears they KNOW this fight. We don't — here's the truth."
BODY: "${lead.s.win.name} vs ${lead.s.other.name}. Our model: ${lead.s.pct}%. That's a coin flip wearing a lab coat. Anyone selling you a lock is selling you something."
CTA: "We publish the coin flips as coin flips — link in bio. Who cracks first?"`,
    hashtags: hashtags(event.name, lead.s.win.name, lead.s.other.name) + ' #FightTok #fyp',
    cta: 'Link in bio',
    question: `Pass, or is the close call where the value hides?`,
    visual: `A spinning coin morphing into a ${lead.s.pct}% dial; deadpan tone; "COIN-FLIP CORNER" crimson stamp on black.`,
  }];

  if (flips.length >= 2) {
    pieces.push({
      tag: 'REDDIT-POST', id: 'coinflip-reddit', platform: 'Reddit (r/ufc)', pillar: 'P3-CoinFlip',
      copy:
`TITLE: Which ${shortName(event.name)} fights are genuine coin-flips? My model spat out ${flips.length} inside 53–57% and I think being honest about that matters.

Everyone posts locks. Nobody posts "I don't know." These came back near 50/50:
${flips.map(f => `- ${f.s.win.name} ${f.s.pct}% / ${f.s.other.name}`).join('\n')}

I'd rather flag these as toss-ups than fake conviction. When a fight is legitimately even, what's your process — pass, or is that exactly where the value is? Not selling anything, just comparing how people handle real uncertainty.`,
      hashtags: '(Reddit — genuine discussion post, no link unless asked)',
      cta: 'No link unless requested',
      question: `Pass or play the true toss-ups?`,
    });
  }
  return pieces;
}

// Pillar 4 — What If the Sim Saw… (top finisher + an intel slot)
function genWhatIf(event, rows) {
  let best = null;
  for (const r of rows) {
    const s = sides(r);
    if (!s || !s.winFin || s.winFin.n < 5) continue;
    if (!best || s.winFin.pct > best.s.winFin.pct) best = { r, s };
  }
  const pieces = [];
  const url = pieceCardLink(event, 'x');

  if (best && best.s.winFin.pct >= 70) {
    const s = best.s;
    const whatifImg = baseVerdictImage(event, s, 'What-If the Sim Saw');
    whatifImg.chips.push({ k: 'Finish rate', v: `${s.winFin.pct}%`, tone: 'win' });
    pieces.push({
      tag: 'X-POST', id: 'whatif-finisher', platform: 'X', pillar: 'P4-WhatIf', image: whatifImg,
      copy:
`"What if the sim saw it?" 🔧

${s.win.name} over ${s.other.name} — model has it ${s.pct}%.

The input we keep chewing on: ${s.win.name} finishes ${s.winFin.pct}% of their wins over ${s.winFin.n} fights. Should "rarely needs the judges" weigh heavier than it does? Genuinely asking — it moves the number.`,
      hashtags: hashtags(event.name, s.win.name, s.other.name),
      cta: `Play with the factors yourself on site (${url}) — what do you think?`,
      question: `Where would you set the dial?`,
    });
  }

  // Intel-slot piece — deliberately a template with a verify placeholder. We do
  // NOT fabricate news; the operator fills this only with sourced, real intel.
  pieces.push({
    tag: 'BONUS', id: 'whatif-intel-slot', platform: 'X / Reel', pillar: 'P4-WhatIf',
    copy:
`⚠️ INTEL SLOT — post ONLY after you verify the news. Do not invent.

"Public models run on stats. We watch the stuff the stats can't see yet.

[verify + insert real intel — e.g. camp change / short-notice replacement / weight-cut note for a ${shortName(event.name)} fighter].

So the question we're chewing on: does the sim need to adjust — and what flips if it does?"`,
    hashtags: hashtags(event.name) + ' #UFCNews',
    cta: `Before/after on the site (${link('card-lab.html', 'x')}) — would you make the adjustment?`,
    question: `Adjust the model, or trust the base rates?`,
  });
  return pieces;
}

// A couple of always-on format pieces (poll + teaser) for reach.
function genReach(event, rows) {
  const main = rows.find(r => r.fight.is_main_event) || rows[0];
  const withVerdict = rows.filter(r => r.pick).length;
  const url = pieceCardLink(event, 'x');
  const pieces = [];

  if (main && main.pick) {
    const s = sides(main);
    const pollImg = baseVerdictImage(event, s, 'Main Event');
    if (s.winFin) pollImg.chips.push({ k: 'Finish rate', v: `${s.winFin.pct}%`, tone: 'win' });
    pieces.push({
      tag: 'X-POST', id: 'poll-main', platform: 'X', pillar: 'P1-SensorRead', image: pollImg,
      copy:
`${shortName(event.name)} main event. Our model: ${s.win.name} ${s.pct}% (${s.agree}/${s.total} models).

Where does this fight actually get decided? 👇`,
      hashtags: hashtags(event.name, s.win.name, s.other.name),
      cta: `See how the sim weighs it (${url})`,
      question: `Poll: R1 finish / grind-it-out / late TKO / decision`,
    });
  }

  pieces.push({
    tag: 'BONUS', id: 'teaser-loop', platform: 'TikTok / Reel', pillar: 'Awareness',
    copy:
`10s TEASER LOOP — "${rows.length} fights. ${withVerdict} model verdicts. 1 card. Here's where our engines disagree 👀 (link in bio)"`,
    hashtags: hashtags(event.name) + ' #FightTok #fyp',
    cta: 'Link in bio',
    question: `Which call surprises you?`,
    visual: `Fast montage of the card page / sensor board; crimson-on-black; loops seamlessly.`,
  });
  return pieces;
}

// --------------------------------------------------------------- assembly ---

function buildPieces(event, rows) {
  return [
    ...genSensorRead(event, rows),
    ...genCardio(event, rows),
    ...genCoinFlip(event, rows),
    ...genWhatIf(event, rows),
    ...genReach(event, rows),
  ];
}

function renderBatchMd(event, rows, pieces) {
  const withVerdict = rows.filter(r => r.pick).length;
  const out = [];
  out.push(`# Social batch — ${event.name}`);
  out.push('');
  out.push(`**${formatLongDate(event.event_date)}**${event.location ? ` · ${event.location}` : ''} · ${rows.length} fights · ${withVerdict} model verdicts`);
  out.push(`Landing page: ${SITE}/card/${cardSlug(event.name, event.id)}.html`);
  out.push('');
  out.push(`_Generated by \`build/social-engine.js\` from live model data. Review before posting. Betting-free, hype-free; links carry \`?src=\` for Plausible attribution._`);
  out.push('');

  const byPillar = {};
  pieces.forEach(p => { (byPillar[p.pillar] || (byPillar[p.pillar] = [])).push(p); });

  pieces.forEach((p, i) => {
    out.push(`## ${i + 1}. <${p.tag}> · ${p.pillar} · ${p.platform}`);
    out.push('');
    out.push('```');
    out.push(p.copy);
    out.push('```');
    if (p.images && p.images.length) out.push(`**Images:** ${p.images.map(im => `\`${im.rel}\` (${im.label})`).join(' · ')}`);
    if (p.visual) out.push(`**Visual:** ${p.visual}`);
    out.push(`**Hashtags:** ${p.hashtags}`);
    out.push(`**CTA:** ${p.cta}`);
    out.push(`**Engagement Q:** ${p.question}`);
    out.push('');
  });
  out.push('---');
  out.push(`_${pieces.length} pieces. Next batch: rerun the engine, or feed verified intel to unlock the Pillar-4 slots._`);
  out.push('');
  return out.join('\n');
}

// Dated posting plan: spreads pieces across the 6 days before the card + day
// after, morning/evening slots, one landing link per piece with ?src=.
function scheduleRows(event, pieces) {
  const offsets = [-6, -5, -4, -3, -2, -1, 0, 1]; // T-6 .. T-1, event day, T+1
  const times = ['09:00', '18:30'];
  return pieces.map((p, i) => {
    const off = offsets[Math.floor(i / times.length) % offsets.length];
    const time = times[i % times.length];
    const date = isoOffset(event.event_date, off);
    const src = p.platform.toLowerCase().includes('tiktok') ? 'tiktok'
      : p.platform.toLowerCase().includes('instagram') ? 'ig'
      : p.platform.toLowerCase().includes('reddit') ? 'reddit' : 'x';
    const srcLink = p.platform.toLowerCase().includes('reddit') ? 'value-post-no-link'
      : `${SITE}/card/${cardSlug(event.name, event.id)}.html?src=${src}`;
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
    <div class="sub">${totalPieces} ready-to-post pieces · ${totalImages} branded images across ${data.length} cards · generated ${generatedISO.slice(0,10)} · betting-free, real model data</div>
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

// ------------------------------------------------------------------- main ---

async function main() {
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

  const index = ['# Social batches', '', '_Auto-generated by `build/social-engine.js`. Open `dashboard.html` to browse + copy. One folder per upcoming card._', ''];
  const batches = [];
  let totalPieces = 0;
  let totalImages = 0;

  const chrome = findChrome();
  if (chrome) console.log(`Rendering images with: ${chrome}`);
  else console.warn('[social-engine] No Chrome/Chromium found — generating copy only (no images). Set CFL_CHROME=<path> to enable image rendering.');

  for (const event of events) {
    const { rows } = await loadCard(event);
    if (!rows.length) { console.log(`skip ${event.name} — no fights`); continue; }
    const pieces = buildPieces(event, rows);
    if (!pieces.length) { console.log(`skip ${event.name} — no model data to ground content`); continue; }

    const slug = `${slugify(event.name)}-${event.id}`;
    const dir = path.join(SOCIAL_DIR, slug);

    // Render finished, on-brand post images (per-platform sizes) for every
    // piece that carries an image spec. Copy still generates if this is skipped.
    let imgCount = 0;
    if (chrome) {
      const imgDir = path.join(dir, 'img');
      for (const p of pieces) {
        p.images = renderPieceImages(chrome, p, imgDir, `${slug}/img`);
        imgCount += p.images.length;
      }
    }

    const wroteMd = writeIfChanged(path.join(dir, 'batch.md'), renderBatchMd(event, rows, pieces));
    const wroteCsv = writeIfChanged(path.join(dir, 'schedule.csv'), renderScheduleCsv(event, pieces));
    batches.push({ event, pieces });
    totalPieces += pieces.length;
    totalImages += imgCount;
    index.push(`- **${event.name}** (${shortDate(event.event_date)}) — ${pieces.length} pieces, ${imgCount} images → \`social/${slug}/\``);
    console.log(`${event.name}: ${pieces.length} pieces, ${imgCount} images ${wroteMd || wroteCsv ? '(written)' : '(unchanged)'}`);
  }

  index.push('', `_${totalPieces} pieces + ${totalImages} images across ${batches.length} cards. Betting-free, hype-free, real model data only._`, '');
  writeIfChanged(path.join(SOCIAL_DIR, 'index.md'), index.join('\n'));

  // The access layer: one self-contained page to browse + copy everything.
  const generatedISO = new Date().toISOString();
  writeIfChanged(path.join(SOCIAL_DIR, 'dashboard.html'), renderDashboard(batches, generatedISO));
  console.log(`Done. ${totalPieces} pieces + ${totalImages} images total. Dashboard: social/dashboard.html`);
}

main().catch(err => { console.error('[social-engine] failed:', err); process.exit(1); });
