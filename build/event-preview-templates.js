// Event-level card-prediction page: a real, indexable content page for every
// upcoming UFC card. Where the per-fight matchup preview targets
//     "fighter a vs fighter b prediction"
// this page targets the higher-volume event queries
//     "ufc 329 predictions", "ufc 329 full card picks", "ufc 329 fight card"
// by listing the model's verdict on EVERY fight on the card in one place, with
// internal links out to each per-fight preview.
//
// Canonical URL points at the card page itself (unique aggregated content).

const { slugify } = require('./slug');

const SITE = 'https://cannonfightlab.com';

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

function formatLongDate(isoDate) {
  if (!isoDate) return '';
  const d = new Date(isoDate + 'T00:00:00');
  return d.toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'
  });
}

function cardSlug(eventName, eventId) {
  return `${slugify(eventName)}-${eventId}`;
}

// Plain-English agreement label for the two public models (Value + Fight IQ).
// Handles the one-model case too (a fight only one model has graded).
function modelAgreementLabel(agree, total) {
  if (total <= 1) return '1 model';
  if (agree === total) return total === 2 ? 'both models agree' : `all ${total} models agree`;
  return `${agree} of ${total} models agree`;
}

// Consensus verdict for one fight, matching the per-fight preview's rule
// exactly: only picks with model_p > 0.5 count; the winner is the fighter the
// most models favour; confidence is the average model_p of the winning models.
// Returns null when no model has a confident pick yet (card still lists the
// bout as "verdict pending").
function consensusPick(picks, fighterA, fighterB) {
  const valid = (picks || []).filter(p => p.model_p != null && +p.model_p > 0.5);
  if (!valid.length) return null;
  const tally = {};
  valid.forEach(p => { tally[p.fighter_id] = (tally[p.fighter_id] || 0) + 1; });
  const sorted = Object.entries(tally).sort((x, y) => y[1] - x[1]);
  const winnerId = +sorted[0][0];
  const winner = winnerId === fighterA.id ? fighterA : fighterB;
  const winningPs = valid.filter(p => p.fighter_id === winnerId).map(p => +p.model_p);
  const avgP = winningPs.reduce((s, x) => s + x, 0) / winningPs.length;
  return {
    winnerId,
    winnerName: winner.name,
    pct: Math.round(avgP * 100),
    agree: sorted[0][1],
    total: valid.length
  };
}

// Order fights the way a card is presented: main event first, then remaining
// title fights, then everything else by ascending id (rough bout order). We
// don't rely on a bout_order column existing.
function cardOrder(a, b) {
  const rank = f => (f.is_main_event ? 0 : (f.is_title_fight ? 1 : 2));
  const ra = rank(a), rb = rank(b);
  if (ra !== rb) return ra - rb;
  return (a.id || 0) - (b.id || 0);
}

// rows: [{ fight, fighterA, fighterB, pick }]  (pick may be null)
function eventPreview({ event, rows, previewSlugFor }) {
  const slug = cardSlug(event.name, event.id);
  const url = `${SITE}/card/${slug}.html`;

  const dateLabel = formatLongDate(event.event_date);
  const bouts = rows.length;
  const withVerdict = rows.filter(r => r.pick).length;

  const main = rows.find(r => r.fight.is_main_event) || rows[0] || null;
  const mainPick = main ? main.pick : null;

  // ---- meta ----
  const title = `${event.name} Odds, Line Movement & Full-Card Research | Cannon Fight Lab`;
  const description = (
    `${event.name}${dateLabel ? ' — ' + dateLabel : ''}` +
    `${event.location ? ', ' + event.location : ''}. Sportsbook odds, line movement and ` +
    `matchup data for all ${bouts} fights on the card. No picks.`
  ).trim();

  // ---- JSON-LD ----
  const sportsEventJsonLd = {
    '@context': 'https://schema.org',
    '@type': 'SportsEvent',
    'name': event.name,
    'sport': 'Mixed Martial Arts',
    'startDate': event.event_date || undefined,
    'eventStatus': 'https://schema.org/EventScheduled',
    'eventAttendanceMode': 'https://schema.org/MixedEventAttendanceMode',
    'url': url,
    'location': event.location ? { '@type': 'Place', 'name': event.location } : undefined,
    'organizer': {
      '@type': 'SportsOrganization',
      'name': 'Ultimate Fighting Championship',
      'alternateName': 'UFC'
    },
    'subEvent': rows.map(r => ({
      '@type': 'SportsEvent',
      'name': `${r.fighterA.name} vs ${r.fighterB.name}`,
      'url': `${SITE}/preview/${previewSlugFor(r)}.html`,
      'competitor': [
        { '@type': 'Person', 'name': r.fighterA.name },
        { '@type': 'Person', 'name': r.fighterB.name }
      ]
    }))
  };
  Object.keys(sportsEventJsonLd).forEach(k => sportsEventJsonLd[k] === undefined && delete sportsEventJsonLd[k]);

  // The FAQ block used to answer "who does the model pick to win the main
  // event". CFL no longer publishes a forecast, so the questions it answers
  // now are the ones the page can actually answer.
  const faqEntities = [{
    '@type': 'Question',
    'name': `How many fights are on the ${event.name} card?`,
    'acceptedAnswer': {
      '@type': 'Answer',
      'text': `${bouts} fights are currently scheduled. The full card is above, each fight linking to its odds and matchup research.`
    }
  }, {
    '@type': 'Question',
    'name': `Does Cannon Fight Lab publish picks for ${event.name}?`,
    'acceptedAnswer': {
      '@type': 'Answer',
      'text': `No. CFL is a research tool: it shows the vig-free sportsbook consensus, the best price on offer and which book is posting it, how far each line has moved since we started capturing it, and the measurable differences between the two fighters. It does not tell you who will win.`
    }
  }];
  const faqJsonLd = {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    'mainEntity': faqEntities
  };

  const breadcrumbJsonLd = {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    'itemListElement': [
      { '@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': SITE + '/' },
      { '@type': 'ListItem', 'position': 2, 'name': 'Card predictions', 'item': SITE + '/card/' },
      { '@type': 'ListItem', 'position': 3, 'name': `${event.name} predictions`, 'item': url }
    ]
  };

  const jsonLdBlobs = [sportsEventJsonLd, faqJsonLd, breadcrumbJsonLd];

  const eventUrl = `${SITE}/event.html?id=${event.id}`;
  const signupUrl = `${SITE}/signup.html?next=${encodeURIComponent('/card/' + slug + '.html')}`;

  // ---- fight rows ----
  const rowHtml = rows.map(r => {
    const flag = r.fight.is_title_fight ? 'Title' : (r.fight.is_main_event ? 'Main' : '');
    const weight = r.fight.weight_class || '';
    const previewUrl = `${SITE}/preview/${previewSlugFor(r)}.html`;
    const verdictCell = r.pick
      ? `<a class="cfl-card-research" href="${SITE}/fight.html?id=${r.fight.id}">Odds &amp; research →</a>`
      : `<a class="cfl-card-research" href="${SITE}/fight.html?id=${r.fight.id}">Odds &amp; research →</a>`;
    return `
      <tr>
        <td class="cfl-card-bout">
          <a href="${previewUrl}">${escapeHtml(r.fighterA.name)} <span class="vs">vs</span> ${escapeHtml(r.fighterB.name)}</a>
          <span class="cfl-card-tags">${flag ? `<span class="cfl-card-flag">${escapeHtml(flag)}</span>` : ''}${weight ? `<span class="cfl-card-wt">${escapeHtml(weight)}</span>` : ''}</span>
        </td>
        <td class="cfl-card-verdict">${verdictCell}</td>
      </tr>`;
  }).join('');

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>${escapeHtml(title)}</title>
<meta name="description" content="${escapeHtml(description)}">
<meta name="author" content="Cannon Fight Lab">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="${url}">

<meta property="og:type" content="article">
<meta property="og:site_name" content="Cannon Fight Lab">
<meta property="og:title" content="${escapeHtml(`${event.name} — Predictions & Full-Card Picks`)}">
<meta property="og:description" content="${escapeHtml(description)}">
<meta property="og:url" content="${url}">
<meta property="og:image" content="${SITE}/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Cannon Fight Lab — UFC card predictions">
<meta property="og:locale" content="en_US">

<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="${escapeHtml(`${event.name} — Predictions & Full-Card Picks`)}">
<meta name="twitter:description" content="${escapeHtml(description)}">
<meta name="twitter:image" content="${SITE}/og-image.png">

<meta name="theme-color" content="#0a0a0a">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">

${jsonLdBlobs.map(j => `<script type="application/ld+json">${JSON.stringify(j)}</script>`).join('\n')}

<style>
  body { background:#0a0a0a; color:#e8e8e8; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,sans-serif; margin:0; line-height:1.55; }
  .cfl-card-wrap { max-width:880px; margin:0 auto; padding:40px 20px 80px; }
  .cfl-card-eyebrow { color:#e63946; text-transform:uppercase; letter-spacing:1px; font-size:12px; font-weight:700; margin-bottom:10px; }
  h1 { font-size:34px; line-height:1.2; margin:0 0 8px; color:#fff; }
  .cfl-card-meta { color:#999; font-size:14px; margin-bottom:28px; }
  .cfl-card-summary { background:#181818; border:1px solid #2a2a2a; border-left:3px solid #e63946; padding:18px 20px; border-radius:6px; margin-bottom:30px; font-size:16px; }
  .cfl-card-summary-label { display:block; color:#999; font-size:11px; letter-spacing:1px; text-transform:uppercase; margin-bottom:6px; }
  .cfl-card-summary strong { color:#fff; }
  .cfl-card-cta { background:linear-gradient(135deg,#e63946 0%,#c1121f 100%); color:#fff; padding:22px 24px; border-radius:8px; margin-bottom:36px; display:flex; gap:18px; align-items:center; flex-wrap:wrap; }
  .cfl-card-cta-text { flex:1 1 280px; }
  .cfl-card-cta-text strong { display:block; font-size:17px; margin-bottom:3px; }
  .cfl-card-cta-text span { color:#fff; opacity:0.85; font-size:13px; }
  .cfl-card-cta a.btn { background:#fff; color:#c1121f; padding:10px 22px; border-radius:6px; font-weight:700; text-decoration:none; white-space:nowrap; font-size:14px; }
  .cfl-card-cta a.btn:hover { background:#f5f5f5; }
  h2.cfl-card-h2 { font-size:20px; color:#fff; margin:0 0 14px; }
  table.cfl-card-table { width:100%; border-collapse:collapse; margin-bottom:30px; }
  table.cfl-card-table td { border-bottom:1px solid #1c1c1c; padding:13px 8px; vertical-align:middle; }
  .cfl-card-bout a { color:#fff; text-decoration:none; font-size:15px; font-weight:600; }
  .cfl-card-bout a:hover { color:#e63946; }
  .cfl-card-bout .vs { color:#777; font-weight:400; padding:0 4px; }
  .cfl-card-tags { display:block; margin-top:4px; }
  .cfl-card-flag { display:inline-block; background:#c1121f; color:#fff; font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; padding:2px 6px; border-radius:3px; margin-right:6px; }
  .cfl-card-wt { color:#888; font-size:12px; }
  .cfl-card-verdict { text-align:right; white-space:nowrap; }
  .cfl-card-verdict strong { color:#fff; font-size:15px; display:block; }
  .cfl-card-conf { color:#e63946; font-size:12px; }
  .cfl-card-research { color:#e63946; font-size:13px; text-decoration:none; white-space:nowrap; }
  .cfl-card-research:hover { text-decoration:underline; }
  .cfl-card-pending { color:#777; font-size:13px; font-style:italic; }
  .cfl-card-deeper { background:#111; border:1px solid #222; border-radius:6px; padding:18px 20px; }
  .cfl-card-deeper h3 { font-size:14px; color:#999; text-transform:uppercase; letter-spacing:1px; margin:0 0 10px; }
  .cfl-card-deeper a { color:#e63946; text-decoration:none; display:block; padding:6px 0; font-size:14px; }
  .cfl-card-deeper a:hover { text-decoration:underline; }
  .cfl-card-foot { color:#666; font-size:12px; margin-top:36px; text-align:center; }
  .cfl-card-foot a { color:#999; }
</style>
</head>
<body>

<div class="cfl-card-wrap">

  <div class="cfl-card-eyebrow">UFC Card Research</div>

  <h1>${escapeHtml(event.name)} — Odds &amp; Full-Card Research</h1>

  <div class="cfl-card-meta">
    ${dateLabel ? escapeHtml(dateLabel) : ''}${event.location ? ' &middot; ' + escapeHtml(event.location) : ''}${bouts ? ' &middot; ' + bouts + ' fights' : ''}
  </div>

  <div class="cfl-card-summary">
    <span class="cfl-card-summary-label">What this page is</span>
    The ${bouts}-fight card, each bout linking to its live sportsbook odds, line movement
    and matchup data. Cannon Fight Lab does not publish a pick on any of them.
  </div>

  <div class="cfl-card-cta">
    <div class="cfl-card-cta-text">
      <strong>The whole market on this card, one screen</strong>
      <span>Vig-free consensus, the best price and who is posting it, and what has moved since we started watching. Free, no account needed.</span>
    </div>
    <a class="btn" href="${SITE}/market.html?event=${event.id}">Open Market Lab →</a>
  </div>

  <h2 class="cfl-card-h2">Full card</h2>
  <table class="cfl-card-table">
    <tbody>${rowHtml}
    </tbody>
  </table>

  <div class="cfl-card-deeper">
    <h3>Go deeper</h3>
    <a href="${eventUrl}">Live card &amp; odds: ${escapeHtml(event.name)} →</a>
    <a href="${SITE}/market.html?event=${event.id}">Market Lab — every sportsbook, side by side →</a>
    <a href="${SITE}/index.html#next">Card Lab — the next card, one screen →</a>
    <a href="${SITE}/stats.html">Factor Lab — which fight stats actually hold up →</a>
  </div>

  <p class="cfl-card-foot">
    Cannon Fight Lab is an analytics publication, not a sportsbook. 21+ only.
    <a href="${SITE}/disclaimer.html">Disclaimer</a>
  </p>

</div>

</body>
</html>
`;
}

module.exports = { eventPreview, cardSlug, consensusPick, cardOrder };
