// build/hub-templates.js — the Event Hub (/e/<slug>-<id>.html) and the fight
// page (/preview/<a>-vs-<b>-<id>.html) for any card that has a locked
// pre-fight record.
//
// Both pages are real content pages: canonical points at themselves, and a
// crawler sees the full table without running JS. The browser then loads
// fight-week.js, which refreshes the market cells from the same views and
// sends the Plausible events. The CFL number on the page is the locked
// forecast from v_fight_locked_forecast and is never recomputed — not here,
// not in the browser.
//
// After the card settles the same URL is regenerated with results and stays
// forever as the graded record. Nothing here ever redirects or deletes.
//
// Wording: fight-week-core.js owns the labels and the two standard lines.
// The markup mirrors fight-week.js (data-* hooks) — keep the two in step.

const core = require('../fight-week-core');
const books = require('../books');

const SITE = core.SITE;
const esc = core.escapeHtml;

const ASSET_V = 'fw1';   // bump with every change to fight-week.js / .css

function head({ title, description, canonical, ogTitle, jsonLd, bodyAttrs }) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${esc(title)}</title>
<meta name="description" content="${esc(description)}">
<meta name="author" content="Cannon Fight Lab">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="${canonical}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Cannon Fight Lab">
<meta property="og:title" content="${esc(ogTitle || title)}">
<meta property="og:description" content="${esc(description)}">
<meta property="og:url" content="${canonical}">
<meta property="og:image" content="${SITE}/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:locale" content="en_US">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="${esc(ogTitle || title)}">
<meta name="twitter:description" content="${esc(description)}">
<meta name="twitter:image" content="${SITE}/og-image.png">
<meta name="theme-color" content="#08090b">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Saira+Semi+Condensed:wght@600;700;800&family=IBM+Plex+Sans:wght@500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/_shared.css?v=flag4">
<link rel="stylesheet" href="/fight-week.css?v=${ASSET_V}">
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.106.1/dist/umd/supabase.min.js" integrity="sha384-9dsYHX1/12VQI+gHRtPXSM3YFsgJ+iIPjTy4WCtY7XbKG/q7MTdZxZhMd4cL9Gif" crossorigin="anonymous"></script>
<script defer data-domain="cannonfightlab.com" src="https://plausible.io/js/script.js"></script>
${(jsonLd || []).map(j => `<script type="application/ld+json">${JSON.stringify(j)}</script>`).join('\n')}
</head>
<body ${bodyAttrs || ''}>
<nav class="cfl-nav"></nav>
<div class="lab-bg" aria-hidden="true"><div class="grid"></div><div class="scan"></div></div>
`;
}

function foot(navActive) {
  return `
<footer class="cfl-footer"></footer>
<script src="/_shared.js?v=rd18"></script>
<script src="/_auth.js?v=rf1"></script>
<script src="/fight-week-core.js?v=${ASSET_V}"></script>
<script src="/books.js?v=${ASSET_V}"></script>
<script src="/fight-week.js?v=${ASSET_V}"></script>
<script>cfl.renderNav(${JSON.stringify(navActive || '')}); cfl.renderFooter();</script>
</body>
</html>
`;
}

function briefBlock(pageType, blockId, eventId, fightId) {
  return `<div class="fw-brief" data-page-type="${esc(pageType)}" data-block-id="${esc(blockId)}" data-event-id="${eventId || ''}"${fightId ? ` data-fight-id="${fightId}"` : ''}></div>`;
}

const rulesLine = () => `<p class="fw-rule"><b>${esc(core.STANDARD_LINE)}</b> Market numbers are the books' prices with the cut removed. ${esc(core.NOT_EDGE)}</p>`;

function resultText(r) {
  if (!r.winner_id) return null;
  const winnerIsA = r.winner_id === r.fighter_a_id;
  const w = winnerIsA ? r.fighter_a_name : r.fighter_b_name;
  const meth = r.method ? ` — ${r.method}${r.end_round ? ' R' + r.end_round : ''}` : '';
  return `${w} won${meth}`;
}

// ---------------------------------------------------------------------------
// Event Hub
// ---------------------------------------------------------------------------
function eventHub({ event, rows, byBook, factor, generatedAt }) {
  const url = SITE + core.hubPath(event);
  const s = core.summarize(rows);
  const dateLabel = core.fmtLongDate(event.event_date);
  const settled = s.anySettled;
  const title = `${event.name} Predictions, Odds & Model Analysis`;
  const description = settled
    ? `${event.name} graded: CFL's locked forecasts went ${s.hits}-${s.misses} on ${s.settled} fights, with the market number beside every one. Every miss shown.`
    : `${event.name}${dateLabel ? ' on ' + dateLabel : ''}: CFL's locked forecast next to the vig-free market number for all ${s.fights} fights, with ${s.big} big disagreement${s.big === 1 ? '' : 's'}. Predictions locked before results.`;

  const jsonLd = [{
    '@context': 'https://schema.org',
    '@type': 'SportsEvent',
    name: event.name,
    sport: 'Mixed Martial Arts',
    startDate: event.event_date,
    eventStatus: settled ? 'https://schema.org/EventCompleted' : 'https://schema.org/EventScheduled',
    eventAttendanceMode: 'https://schema.org/MixedEventAttendanceMode',
    url,
    location: event.location ? { '@type': 'Place', name: event.location } : undefined,
    organizer: { '@type': 'SportsOrganization', name: 'Ultimate Fighting Championship', alternateName: 'UFC' },
    subEvent: rows.map(r => ({
      '@type': 'SportsEvent',
      name: `${r.fighter_a_name} vs ${r.fighter_b_name}`,
      url: SITE + core.fightPath(r),
      competitor: [{ '@type': 'Person', name: r.fighter_a_name }, { '@type': 'Person', name: r.fighter_b_name }],
    })),
  }, {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: [
      { '@type': 'ListItem', position: 1, name: 'Home', item: SITE + '/' },
      { '@type': 'ListItem', position: 2, name: event.name, item: url },
    ],
  }];
  jsonLd.forEach(j => Object.keys(j).forEach(k => j[k] === undefined && delete j[k]));

  const tableRows = rows.map(r => {
    const d = r.disagree;
    const favA = r.cfl_p_a != null && r.cfl_p_a >= 0.5;
    const res = resultText(r);
    const hitCell = r.forecast_hit == null ? '' : (r.forecast_hit ? '<span class="fw-hit">✓ right</span>' : '<span class="fw-miss">✗ wrong</span>');
    return `<tr data-fight-id="${r.fight_id}">
      <td class="fw-bout">
        <span hidden data-name-a="${r.fight_id}" data-value="${esc(r.fighter_a_name)}"></span><span hidden data-name-b="${r.fight_id}" data-value="${esc(r.fighter_b_name)}"></span>
        <a href="${core.fightPath(r)}"><span class="${favA ? 'fw-fav' : ''}">${esc(r.fighter_a_name)}</span><span class="vs">vs</span><span class="${r.cfl_p_a != null && !favA ? 'fw-fav' : ''}">${esc(r.fighter_b_name)}</span></a>
        <span class="sub">${r.is_main_event ? '<span class="fw-tag main">Main event</span>' : ''}${r.is_title_fight ? '<span class="fw-tag">Title</span>' : ''}${esc(r.weight_class || '')}${res ? ' · ' + esc(res) : ''}</span>
      </td>
      <td class="num"><span data-cfl-a="${r.fight_id}" data-value="${r.cfl_p_a == null ? '' : r.cfl_p_a}">${core.pct(r.cfl_p_a)}</span> <span class="fw-dim">/</span> ${core.pct(r.cfl_p_b)}</td>
      <td class="num"><span data-mkt-a="${r.fight_id}">${core.pct(r.market_p_a)}</span> <span class="fw-dim">/</span> <span data-mkt-b="${r.fight_id}">${core.pct(r.market_p_b)}</span></td>
      <td class="num" data-diff="${r.fight_id}">${core.fmtPoints(d.points)}</td>
      <td data-label="${r.fight_id}"><span class="fw-label ${esc(d.kind)}">${esc(d.label)}</span></td>
      ${settled ? `<td>${hitCell}</td>` : ''}
    </tr>`;
  }).join('');

  const big = core.biggest(rows, 3).filter(r => r.disagree.big);
  const bigHtml = big.length
    ? `<div class="fw-cards">${big.map(r => disagreementCard(r)).join('')}</div>`
    : `<div class="fw-empty">No fight on this card has CFL and the market more than ${core.BIG_POINTS} points apart${s.priced < s.analyzed ? ' — some fights have no sportsbook price yet' : ''}.</div>`;

  const moves = core.biggestMoves(rows, 5);
  const noLockQuote = rows.filter(r => r.cfl_p_a != null && r.market_p_a != null && r.market_p_a_at_lock == null).length;
  const movesHtml = moves.length
    ? `<div class="fw-tablewrap"><table class="fw-table"><thead><tr><th>Fight</th><th class="num">Market at lock</th><th class="num">Market now</th><th>Move</th></tr></thead><tbody>${moves.map(r => {
        const favA = r.cfl_p_a >= 0.5; const fav = favA ? r.fighter_a_name : r.fighter_b_name;
        return `<tr><td class="fw-bout"><a href="${core.fightPath(r)}">${esc(r.fighter_a_name)} <span class="vs">vs</span> ${esc(r.fighter_b_name)}</a><span class="sub">on ${esc(core.lastName(fav))} · locked ${esc(core.fmtStamp(r.locked_at))} · quotes from ${r.book_count_at_lock} book${r.book_count_at_lock === 1 ? '' : 's'} at lock</span></td>
          <td class="num">${core.pct(r.move.then)}</td><td class="num">${core.pct(r.move.now)}</td><td data-move="${r.fight_id}">${esc(r.move.label)}</td></tr>`;
      }).join('')}</tbody></table></div>`
    : '';
  const movesNote = noLockQuote
    ? `<p class="fw-note">${noLockQuote} fight${noLockQuote === 1 ? ' has' : 's have'} no sportsbook quote on file from before the forecast was locked (books post UFC prices a few days out; CFL locks earlier), so no movement can be shown for ${noLockQuote === 1 ? 'it' : 'them'}. Only timestamped sportsbook quotes count — nothing is back-filled.</p>`
    : '';

  const factorHtml = factor
    ? `<div class="fw-card"><div class="fw-eyebrow">Factor Lab · ${esc(factor.label)}</div>
        <div class="fw-card-bout">${esc(factor.question)}</div>
        <div class="fw-card-why">Raw: ${factor.raw_pct}% on ${Number(factor.raw_n).toLocaleString()} fights. With the market held even (both sides priced inside ±140): ${factor.even_pct}% on ${Number(factor.even_n).toLocaleString()} fights. Verdict: <b>${esc(verdictWord(factor.verdict))}</b>.</div>
        <div class="fw-links"><a href="/stats.html">See every factor in the Factor Lab →</a></div></div>`
    : `<div class="fw-empty">Factor Lab data is regenerated every few hours — <a class="fw-link" href="/stats.html">open the Factor Lab</a>.</div>`;

  const gradingHtml = settled
    ? `<div class="fw-summary">
        <div class="fw-cell"><div class="t">Graded</div><div class="n">${s.hits}–${s.misses}</div><div class="s">forecasts right–wrong on ${s.settled} settled fight${s.settled === 1 ? '' : 's'}${s.allSettled ? '' : ' (card still in progress)'}</div></div>
        <div class="fw-cell"><div class="t">Locked</div><div class="n small">${esc(core.fmtStamp(s.lockedAt))}</div><div class="s">first forecast written — before results</div></div>
      </div>
      <p class="fw-note">Every row above was locked before the bell and graded against the official result; misses are shown at the same size as hits. The site-wide record lives in the <a class="fw-link" href="/track-record.html">Proof Center</a>.</p>`
    : `<div class="fw-empty">Not graded yet. Results are pulled after the card and this page becomes the permanent graded record at this same address — forecasts stay exactly as locked.</div>`;

  const bodyAttrs = `data-page="event_hub" data-event-id="${event.id}"`;
  return head({ title: `${title} | Cannon Fight Lab`, description, canonical: url, ogTitle: `${event.name} — Model vs Market`, jsonLd, bodyAttrs }) + `
<main class="fw">
  <div class="fw-eyebrow"><span>UFC card</span><span class="fw-eyebrow-dim">${esc(dateLabel)}${event.location ? ' · ' + esc(event.location) : ''}</span></div>
  <h1>${esc(title)}</h1>
  <p class="fw-lede">CFL's locked forecast for every fight, beside the sportsbook market with the cut removed. ${settled ? 'The card has been graded — every forecast below is exactly as it was locked before the bell.' : 'Where the two numbers disagree is the story of the card; where they agree, the market has already said it.'}</p>
  ${rulesLine()}

  <div class="fw-summary">
    <div class="fw-cell"><div class="t">Fights analyzed</div><div class="n">${s.analyzed}<span class="fw-dim" style="font-size:14px"> / ${s.fights}</span></div><div class="s">with a locked CFL forecast</div></div>
    <div class="fw-cell"><div class="t">Big disagreements</div><div class="n">${s.big}</div><div class="s">${core.BIG_POINTS}+ points apart · ${s.priced} priced</div></div>
    <div class="fw-cell"><div class="t">Odds last updated</div><div class="n small${core.isStale(s.lastUpdated, 24, generatedAt) ? ' fw-stale' : ''}" data-updated>${esc(core.fmtWhen(s.lastUpdated, generatedAt))}</div><div class="s">vig-free · sportsbooks only</div></div>
    <div class="fw-cell"><div class="t">${esc(core.LOCKED_LINE)}</div><div class="n small">${esc(core.fmtStamp(s.lockedAt))}</div><div class="s">locked, never revised</div></div>
  </div>

  <section class="fw-section">
    <h2>Every fight: CFL vs market</h2>
    <div class="fw-tablewrap">
      <table class="fw-table">
        <thead><tr><th>Fight</th><th class="num">CFL %</th><th class="num">Market % (vig-free)</th><th class="num">Difference</th><th>Read</th>${settled ? '<th>Result</th>' : ''}</tr></thead>
        <tbody>${tableRows}</tbody>
      </table>
    </div>
    <p class="fw-note">Percentages are for the left-hand / right-hand fighter. Difference is CFL minus market on the fighter CFL favours. "Mostly agrees" means the two are within ${core.AGREE_POINTS} points. Click a fight for the math.</p>
  </section>

  ${briefBlock('event_hub', 'after-table', event.id)}

  <section class="fw-section">
    <h2>Biggest disagreements</h2>
    <p>The fights where CFL's locked number and the market are furthest apart. ${esc(core.NOT_EDGE)}</p>
    ${bigHtml}
  </section>

  <section class="fw-section">
    <h2>Line movement since lock</h2>
    <p>How the vig-free market number on CFL's favoured fighter has changed since the forecast was locked. Live, timestamped sportsbook quotes only.</p>
    ${movesHtml}${movesNote}
  </section>

  <section class="fw-section">
    <h2>One Factor Lab finding</h2>
    ${factorHtml}
  </section>

  <section class="fw-section">
    <h2>Grading status</h2>
    ${gradingHtml}
  </section>

  <section class="fw-section">
    <h2>Go deeper</h2>
    <div class="fw-links">
      <a href="/market-board.html">Market Board — disagreements, prices and moves →</a>
      <a href="/event.html?id=${event.id}">Full stats card →</a>
      <a href="/track-record.html">Proof Center — the graded record →</a>
      <a href="/methodology.html">How the numbers are made →</a>
    </div>
    <h3 style="margin-top:18px">Fights on this card</h3>
    <div class="fw-otherfights">${rows.map(r => `<a href="${core.fightPath(r)}">${esc(r.fighter_a_name)} vs ${esc(r.fighter_b_name)}<span class="sub">${esc(r.weight_class || '')}${r.is_main_event ? ' · Main event' : ''}</span></a>`).join('')}</div>
  </section>
</main>
` + foot('home');
}

function verdictWord(v) {
  return { real: 'holds up with the market held even', lean: 'leans positive but is not proven', proxy: 'only repeats the betting line', inverted: 'points the wrong way', unproven: 'too few even-odds fights to say', insufficient: 'too few fights to say' }[v] || v;
}

function disagreementCard(r) {
  const d = r.disagree;
  const favA = r.cfl_p_a >= 0.5;
  const fav = favA ? r.fighter_a_name : r.fighter_b_name;
  const cfl = favA ? r.cfl_p_a : r.cfl_p_b;
  const mkt = favA ? r.market_p_a : r.market_p_b;
  return `<div class="fw-card" data-fight-id="${r.fight_id}">
    <div class="fw-eyebrow"><span>${esc(r.weight_class || 'Bout')}</span>${r.is_main_event ? '<span class="fw-tag main">Main event</span>' : ''}</div>
    <div class="fw-card-bout"><a href="${core.fightPath(r)}">${esc(r.fighter_a_name)} <span class="vs">vs</span> ${esc(r.fighter_b_name)}</a></div>
    <div class="fw-rule">CFL favours <b>${esc(fav)}</b> · ${esc(core.confidenceLabel(r.tier, cfl))}</div>
    <div class="fw-card-nums">
      <div class="cell"><div class="t">CFL</div><div class="n">${core.pct(cfl)}</div></div>
      <div class="cell"><div class="t">Market</div><div class="n" data-mkt-fav="${r.fight_id}">${core.pct(mkt)}</div></div>
      <div class="cell"><div class="t">Difference</div><div class="n" data-diff="${r.fight_id}">${core.fmtPoints(d.points)}</div></div>
    </div>
    <div class="fw-card-why" data-explain="${r.fight_id}">${esc(core.explain(r))}</div>
    <div data-label="${r.fight_id}"><span class="fw-label ${esc(d.kind)}">${esc(d.label)}</span></div>
    <div class="fw-notedge">${esc(core.NOT_EDGE)}</div>
  </div>`;
}

// ---------------------------------------------------------------------------
// Fight page
// ---------------------------------------------------------------------------
function statRows(a, b) {
  const num = v => (v == null ? null : +v);
  const rows = [
    { l: 'Age', a: num(a.age), b: num(b.age), fmt: v => v == null ? '—' : String(Math.round(v)), lead: 'lower' },
    { l: 'Height', a: num(a.height_in), b: num(b.height_in), fmt: v => v == null ? '—' : `${Math.floor(v / 12)}'${Math.round(v % 12)}"`, lead: 'higher' },
    { l: 'Reach', a: num(a.reach_in), b: num(b.reach_in), fmt: v => v == null ? '—' : `${v}"`, lead: 'higher' },
    { l: 'Stance', a: a.stance || null, b: b.stance || null, fmt: v => v || '—', lead: null },
    { l: 'Career record', a: rec(a), b: rec(b), fmt: v => v || '—', lead: null },
    { l: 'Sig. strikes landed / min', a: num(a.slpm), b: num(b.slpm), fmt: v => v == null ? '—' : v.toFixed(2), lead: 'higher' },
    { l: 'Sig. strikes absorbed / min', a: num(a.sapm), b: num(b.sapm), fmt: v => v == null ? '—' : v.toFixed(2), lead: 'lower' },
    { l: 'Takedowns / 15 min', a: num(a.td_avg), b: num(b.td_avg), fmt: v => v == null ? '—' : v.toFixed(2), lead: 'higher' },
    { l: 'Takedown defence', a: num(a.td_def), b: num(b.td_def), fmt: v => v == null ? '—' : `${Math.round(v <= 1 ? v * 100 : v)}%`, lead: 'higher' },
  ];
  return rows.map(r => {
    let la = false, lb = false;
    if (r.lead && r.a != null && r.b != null && r.a !== r.b) {
      const aWins = r.lead === 'higher' ? r.a > r.b : r.a < r.b;
      la = aWins; lb = !aWins;
    }
    return `<tr><td class="num${la ? ' lead' : ''}">${esc(r.fmt(r.a))}</td><td class="lbl">${esc(r.l)}</td><td class="num${lb ? ' lead' : ''}">${esc(r.fmt(r.b))}</td></tr>`;
  }).join('');
}
function rec(f) {
  if (!f || (f.wins == null && f.losses == null)) return null;
  return `${f.wins || 0}-${f.losses || 0}${f.draws ? '-' + f.draws : ''}`;
}

function fightPage({ event, row: r, fighters, cardRows, byBook, generatedAt }) {
  const url = SITE + core.fightPath(r);
  const a = fighters[r.fighter_a_id] || { id: r.fighter_a_id, name: r.fighter_a_name };
  const b = fighters[r.fighter_b_id] || { id: r.fighter_b_id, name: r.fighter_b_name };
  const d = r.disagree;
  const favA = r.cfl_p_a != null && r.cfl_p_a >= 0.5;
  const hasForecast = r.cfl_p_a != null;
  const title = `${r.fighter_a_name} vs ${r.fighter_b_name} Prediction & Odds`;
  const res = resultText(r);
  const description = hasForecast
    ? `${r.fighter_a_name} vs ${r.fighter_b_name} at ${event.name}: CFL's locked forecast ${core.pct(r.cfl_p_a)} / ${core.pct(r.cfl_p_b)} vs the vig-free market ${core.pct(r.market_p_a)} / ${core.pct(r.market_p_b)} — ${d.label.toLowerCase()}${d.points != null ? ' by ' + Math.abs(d.points) + ' points' : ''}.${res ? ' Result: ' + res + '.' : ' Predictions locked before results.'}`
    : `${r.fighter_a_name} vs ${r.fighter_b_name} at ${event.name}: market odds with the cut removed. CFL has not locked a forecast for this fight.`;

  const jsonLd = [{
    '@context': 'https://schema.org',
    '@type': 'SportsEvent',
    name: `${r.fighter_a_name} vs ${r.fighter_b_name}`,
    sport: 'Mixed Martial Arts',
    startDate: event.event_date,
    eventStatus: r.winner_id ? 'https://schema.org/EventCompleted' : 'https://schema.org/EventScheduled',
    eventAttendanceMode: 'https://schema.org/MixedEventAttendanceMode',
    url,
    superEvent: { '@type': 'SportsEvent', name: event.name, url: SITE + core.hubPath(event) },
    competitor: [
      { '@type': 'Person', name: r.fighter_a_name, url: SITE + core.fighterPath(r.fighter_a_id) },
      { '@type': 'Person', name: r.fighter_b_name, url: SITE + core.fighterPath(r.fighter_b_id) },
    ],
    location: event.location ? { '@type': 'Place', name: event.location } : undefined,
  }, {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: [
      { '@type': 'ListItem', position: 1, name: 'Home', item: SITE + '/' },
      { '@type': 'ListItem', position: 2, name: event.name, item: SITE + core.hubPath(event) },
      { '@type': 'ListItem', position: 3, name: `${r.fighter_a_name} vs ${r.fighter_b_name}`, item: url },
    ],
  }];
  jsonLd.forEach(j => Object.keys(j).forEach(k => j[k] === undefined && delete j[k]));

  const corner = (f, side) => {
    const isA = side === 'a';
    const cfl = isA ? r.cfl_p_a : r.cfl_p_b;
    const mkt = isA ? r.market_p_a : r.market_p_b;
    const fav = hasForecast && (isA ? favA : !favA);
    return `<div class="fw-corner${fav ? ' fav' : ''}">
      <div class="nm"><a href="${core.fighterPath(f.id)}">${esc(f.name)}</a></div>
      <div class="rec">${esc(rec(f) || '')}${f.nickname ? ' · "' + esc(f.nickname) + '"' : ''}</div>
      <div class="nums">
        <div class="cell"><div class="t">CFL</div><div class="n"${isA ? ` data-cfl-a="${r.fight_id}" data-value="${r.cfl_p_a == null ? '' : r.cfl_p_a}"` : ''}>${core.pct(cfl)}</div></div>
        <div class="cell"><div class="t">Market</div><div class="n" data-mkt-${side}="${r.fight_id}">${core.pct(mkt)}</div></div>
      </div>
      ${fav ? `<div class="fw-conf">${esc(core.confidenceLabel(r.tier, cfl))}</div>` : ''}
    </div>`;
  };

  const mv = r.move;
  const bookRows = (byBook && byBook[r.fight_id]) || [];
  const bookTable = bookRows.length
    ? `<table class="fw-stats" data-track="odds_view" data-fight-id="${r.fight_id}"><thead><tr><th>Book</th><th>${esc(core.lastName(r.fighter_a_name))}</th><th>${esc(core.lastName(r.fighter_b_name))}</th><th>Updated</th></tr></thead><tbody>${bookRows.slice().sort((x, y) => String(x.book_name).localeCompare(String(y.book_name))).map(q => {
        const lic = books.isLicensed(q.book_name);
        const name = lic ? `<a class="fw-link" href="${books.link(q.book_name)}" rel="noopener nofollow" target="_blank" data-book="${esc(books.label(q.book_name))}" data-fight-id="${r.fight_id}">${esc(books.label(q.book_name))}</a>` : `${esc(q.book_name)} <span class="fw-dim">(consensus only)</span>`;
        return `<tr><td class="lbl">${name}</td><td class="num">${core.fmtAmerican(q.american_odds_a)}</td><td class="num">${core.fmtAmerican(q.american_odds_b)}</td><td class="lbl">${esc(core.fmtStamp(q.captured_at))}</td></tr>`;
      }).join('')}</tbody></table>
      <p class="fw-note">Only Tennessee-licensed books are linked. Offshore quotes feed the vig-free consensus but are never offered as a price to take. Prices are for comparison, not a recommendation.</p>`
    : '<p class="fw-note">No per-book quotes on file for this fight in the current window.</p>';

  const others = (cardRows || []).filter(x => x.fight_id !== r.fight_id);
  const bodyAttrs = `data-page="fight_preview" data-event-id="${event.id}" data-fight-id="${r.fight_id}"`;

  return head({ title: `${title} | Cannon Fight Lab`, description, canonical: url, ogTitle: `${r.fighter_a_name} vs ${r.fighter_b_name} — CFL vs the market`, jsonLd, bodyAttrs }) + `
<main class="fw">
  <div class="fw-eyebrow"><span><a href="${core.hubPath(event)}">${esc(event.name)}</a></span><span class="fw-eyebrow-dim">${esc(core.fmtDate(event.event_date))} · ${esc(r.weight_class || 'Bout')}${r.is_main_event ? ' · Main event' : ''}${r.is_title_fight ? ' · Title fight' : ''}</span></div>
  <h1>${esc(title)}</h1>
  <span hidden data-name-a="${r.fight_id}" data-value="${esc(r.fighter_a_name)}"></span><span hidden data-name-b="${r.fight_id}" data-value="${esc(r.fighter_b_name)}"></span>
  ${res ? `<div class="fw-result"><b>Result:</b> ${esc(res)}. ${hasForecast ? `CFL had ${esc(favA ? r.fighter_a_name : r.fighter_b_name)} at ${core.pct(favA ? r.cfl_p_a : r.cfl_p_b)} — ${r.forecast_hit ? '<span class="fw-hit">right</span>' : '<span class="fw-miss">wrong</span>'}. The numbers below are exactly as locked before the bell.` : ''}</div>` : ''}

  <div class="fw-compare">
    ${corner(a, 'a')}
    <div class="fw-mid"><div class="vs">VS</div><div class="diff" data-diff="${r.fight_id}">${core.fmtPoints(d.points)}</div><div class="diff-l">difference<br>on CFL's pick</div><div data-label="${r.fight_id}"><span class="fw-label ${esc(d.kind)}">${esc(d.label)}</span></div></div>
    ${corner(b, 'b')}
  </div>
  <p class="fw-explain" data-explain="${r.fight_id}">${esc(core.explain(r))}</p>
  <div class="fw-notedge">${esc(core.NOT_EDGE)}</div>
  ${rulesLine()}

  <details class="fw-math" data-track="fight_expand" data-odds data-fight-id="${r.fight_id}">
    <summary>Show the math</summary>
    <div class="fw-math-body">
      <dl class="fw-kv">
        <dt>CFL, exact</dt><dd>${r.cfl_p_a == null ? '—' : `${esc(r.fighter_a_name)} ${(100 * r.cfl_p_a).toFixed(1)}% · ${esc(r.fighter_b_name)} ${(100 * r.cfl_p_b).toFixed(1)}%`}</dd>
        <dt>Market, exact (vig-free)</dt><dd>${r.market_p_a == null ? 'no sportsbook price yet' : `${esc(r.fighter_a_name)} <span data-mkt-exact-a="${r.fight_id}">${(100 * r.market_p_a).toFixed(1)}%</span> · ${esc(r.fighter_b_name)} <span data-mkt-exact-b="${r.fight_id}">${(100 * r.market_p_b).toFixed(1)}%</span>`}</dd>
        <dt>Vig-free method</dt><dd>For each sportsbook, the two moneylines are turned into implied percentages and scaled so they add to 100% (that removes the book's cut). The market number is the median across books. Prediction markets and CFL's own consensus row are excluded.</dd>
        <dt>Books in the number</dt><dd><span data-books="${r.fight_id}">${r.book_count || 0}</span> sportsbook${r.book_count === 1 ? '' : 's'}</dd>
        <dt>Odds last updated</dt><dd><span data-mkt-updated="${r.fight_id}" data-updated>${esc(core.fmtWhen(r.last_updated, generatedAt))}</span></dd>
        <dt>Forecast locked</dt><dd>${esc(core.fmtStamp(r.locked_at))}${r.model_version ? ` · ${esc(r.model_version)}` : ''}${r.record_source === 'snapshot' ? ` · frozen in the pre-fight record ${esc(core.fmtStamp(r.snapshot_at))}` : ' · in the insert-only pick ledger; the pre-fight snapshot is taken the night before the card'}</dd>
        <dt>Line movement since lock</dt><dd data-move="${r.fight_id}">${mv ? (mv.then == null ? esc(mv.label) : `${core.pct(mv.then)} → ${core.pct(mv.now)} on ${esc(core.lastName(favA ? r.fighter_a_name : r.fighter_b_name))} · ${esc(mv.label)}`) : '—'}</dd>
        <dt>Fair line from CFL's number</dt><dd>${r.cfl_p_a == null ? '—' : `${esc(core.lastName(r.fighter_a_name))} ${core.fmtAmerican(core.americanFromProb(r.cfl_p_a))} · ${esc(core.lastName(r.fighter_b_name))} ${core.fmtAmerican(core.americanFromProb(r.cfl_p_b))} (for comparison, not a recommendation)`}</dd>
      </dl>
      <h3 style="margin-top:16px">Latest quote by book</h3>
      ${bookTable}
    </div>
  </details>

  ${briefBlock('fight_preview', 'after-math', event.id, r.fight_id)}

  <section class="fw-section">
    <h2>Why the model may see it differently</h2>
    <p>The inputs behind CFL's number. The market already knows most of this; a disagreement usually means the model is weighing one of these harder than the books do — or missing something the books know.</p>
    <table class="fw-stats"><thead><tr><th style="text-align:center">${esc(r.fighter_a_name)}</th><th></th><th style="text-align:center">${esc(r.fighter_b_name)}</th></tr></thead><tbody>${statRows(a, b)}</tbody></table>
    <div class="fw-links"><a href="${core.fighterPath(a.id)}">${esc(a.name)} profile →</a><a href="${core.fighterPath(b.id)}">${esc(b.name)} profile →</a><a href="/h2h.html?a=${a.id}&b=${b.id}">Full head-to-head →</a></div>
  </section>

  <section class="fw-section">
    <h2>Rest of the card</h2>
    <div class="fw-links"><a href="${core.hubPath(event)}">← ${esc(event.name)} Event Hub</a><a href="/market-board.html">Market Board →</a></div>
    <div class="fw-otherfights">${others.map(x => `<a href="${core.fightPath(x)}">${esc(x.fighter_a_name)} vs ${esc(x.fighter_b_name)}<span class="sub">${esc(x.weight_class || '')}${x.is_main_event ? ' · Main event' : ''}${x.disagree.points != null ? ' · ' + esc(x.disagree.label) + ' ' + esc(core.fmtPoints(x.disagree.points)) : ''}</span></a>`).join('')}</div>
  </section>
</main>
` + foot('home');
}

// ---------------------------------------------------------------------------
// Redirect stub for the legacy /card/ page of an event that now has a hub.
// Old links keep working; canonical moves to the hub.
// ---------------------------------------------------------------------------
function cardRedirect(event) {
  const target = SITE + core.hubPath(event);
  return `<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${esc(event.name)} Predictions, Odds & Model Analysis | Cannon Fight Lab</title>
<meta name="robots" content="noindex, follow"><link rel="canonical" href="${target}">
<meta http-equiv="refresh" content="0; url=${target}">
<style>body{background:#0a0a0a;color:#e8e8e8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:60px 20px;text-align:center}a{color:#ff3838}</style>
</head><body><p>This card page has moved to the <a href="${target}">${esc(event.name)} Event Hub</a>.</p>
<script>setTimeout(function(){location.replace(${JSON.stringify(target)});},120);</script></body></html>
`;
}

module.exports = { eventHub, fightPage, cardRedirect, ASSET_V };
