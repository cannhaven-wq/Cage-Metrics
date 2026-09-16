// Event-level card-prediction page: a real, indexable content page for every
// upcoming UFC card. Where the per-fight matchup preview targets
//     "fighter a vs fighter b prediction"
// this page targets the higher-volume event queries
//     "ufc 329 predictions", "ufc 329 full card picks", "ufc 329 fight card"
// by listing the engine's LOCKED forecast on EVERY fight on the card in one
// place (pre-fight snapshot, or the insert-only live row until the snapshot
// exists — never a recompute at render time), with internal links out to each
// per-fight preview and the Fight Week Market Brief signup.
//
// Canonical URL points at the card page itself (unique aggregated content).

const { slugify } = require('./slug');

const SITE = 'https://cannonfightlab.com';
// Keep in step with the ?v= on every root page (see CLAUDE.md "Caching gotcha").
const SHARED_JS = '/_shared.js?v=rd18';
const AUTH_JS = '/_auth.js?v=rf1';
const SUPABASE_CDN = '<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.106.1/dist/umd/supabase.min.js" integrity="sha384-9dsYHX1/12VQI+gHRtPXSM3YFsgJ+iIPjTy4WCtY7XbKG/q7MTdZxZhMd4cL9Gif" crossorigin="anonymous"></script>';
const PLAUSIBLE = '<script defer data-domain="cannonfightlab.com" src="https://plausible.io/js/script.js"></script>';
const SIGNUP_CSS = `
  .cfl-email-capture { margin: 30px 0; }
  .cfl-email-capture-inner { background:#111; border:1px solid #222; padding:22px 24px; border-radius:8px; display:grid; grid-template-columns:1fr auto; gap:18px; align-items:center; }
  @media (max-width:640px){ .cfl-email-capture-inner { grid-template-columns:1fr; } }
  .cfl-email-capture-copy strong { display:block; color:#fff; font-size:16px; margin-bottom:4px; font-weight:700; }
  .cfl-email-capture-copy span { color:#bbb; font-size:13px; line-height:1.45; }
  .cfl-email-capture-form { display:flex; gap:8px; align-items:stretch; flex-wrap:wrap; }
  .cfl-email-capture-form input[type=email] { background:#0a0a0a; border:1px solid #333; color:#fff; padding:10px 12px; border-radius:6px; font-size:14px; font-family:inherit; min-width:220px; }
  .cfl-email-capture-form input[type=email]:focus { outline:none; border-color:#e63946; }
  .cfl-email-capture-form button { background:#e63946; color:#fff; border:0; padding:10px 18px; border-radius:6px; font-weight:700; font-size:14px; cursor:pointer; font-family:inherit; }
  .cfl-email-capture-form button:hover { background:#c1121f; }
  .cfl-email-capture-form button:disabled { opacity:.6; cursor:wait; }
  .cfl-email-capture-msg { grid-column:1 / -1; font-size:13px; min-height:1em; }
  .cfl-email-capture-msg.ok { color:#3fd07a; }
  .cfl-email-capture-msg.err { color:#e63946; }
`;

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

// Mirrors cfl.ENGINE.tiers in _shared.js / tier_of in cfl_engine/faces.py.
function tierWord(p) {
  if (p == null) return '';
  if (p >= 0.65) return 'Lock';
  if (p >= 0.57) return 'Pick';
  return 'Lean';
}

// The locked forecast for one fight, matching the per-fight preview exactly:
// the first (and only) locked row prerender.js hands us. Returns null when
// nothing is on the record yet (card lists the bout as "forecast pending").
function consensusPick(picks, fighterA, fighterB) {
  const p = (picks || []).find(x => x.model_p != null && x.fighter_id != null);
  if (!p) return null;
  const winner = p.fighter_id === fighterA.id ? fighterA : (p.fighter_id === fighterB.id ? fighterB : null);
  if (!winner) return null;
  return {
    winnerId: p.fighter_id,
    winnerName: winner.name,
    pct: Math.round(+p.model_p * 100),
    tier: p.tier || tierWord(+p.model_p),
    locked: p.locked || 'live',
    // One engine, one forecast per fight. Kept for build/social-engine.js,
    // which still renders an "N of M models" line off these two fields.
    agree: 1,
    total: 1
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
  const title = `${event.name} Predictions & Odds | Cannon Fight Lab`;
  const summarySentence = mainPick
    ? `Main event: the odds-blind engine forecasts ${mainPick.winnerName} at ${mainPick.pct}%. `
    : '';
  const description = (
    `${event.name} predictions and odds${dateLabel ? ' — ' + dateLabel : ''}` +
    `${event.location ? ', ' + event.location : ''}. ${summarySentence}` +
    `Locked model forecasts for all ${bouts} fights on the card${withVerdict ? ` (${withVerdict} on record)` : ''}, graded in public, misses included.`
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

  const faqEntities = [];
  if (mainPick) {
    faqEntities.push({
      '@type': 'Question',
      'name': `Who does Cannon Fight Lab's engine forecast to win the ${event.name} main event?`,
      'acceptedAnswer': {
        '@type': 'Answer',
        'text': `Cannon Fight Lab's odds-blind engine forecasts ${mainPick.winnerName} at ${mainPick.pct}% (${mainPick.tier}). The forecast was locked before the bell and is graded in public, misses included. CFL publishes model forecasts and market analysis; it does not sell handicapper picks.`
      }
    });
  }
  faqEntities.push({
    '@type': 'Question',
    'name': `How many fights are on the ${event.name} card?`,
    'acceptedAnswer': {
      '@type': 'Answer',
      'text': `${bouts} fights are currently scheduled${withVerdict ? `, with locked model forecasts on ${withVerdict} of them` : ''}. See the full card with every forecast above.`
    }
  });
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

  // ---- fight rows ----
  const rowHtml = rows.map(r => {
    const flag = r.fight.is_title_fight ? 'Title' : (r.fight.is_main_event ? 'Main' : '');
    const weight = r.fight.weight_class || '';
    const previewUrl = `${SITE}/preview/${previewSlugFor(r)}.html`;
    const verdictCell = r.pick
      ? `<strong>${escapeHtml(r.pick.winnerName)}</strong><span class="cfl-card-conf">${r.pick.pct}% · ${escapeHtml(r.pick.tier)}</span>`
      : `<span class="cfl-card-pending">Forecast pending</span>`;
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
<meta property="og:title" content="${escapeHtml(`${event.name} — Predictions & Odds`)}">
<meta property="og:description" content="${escapeHtml(description)}">
<meta property="og:url" content="${url}">
<meta property="og:image" content="${SITE}/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Cannon Fight Lab — UFC card predictions">
<meta property="og:locale" content="en_US">

<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="${escapeHtml(`${event.name} — Predictions & Odds`)}">
<meta name="twitter:description" content="${escapeHtml(description)}">
<meta name="twitter:image" content="${SITE}/og-image.png">

<meta name="theme-color" content="#0a0a0a">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
${PLAUSIBLE}

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
  .cfl-card-pending { color:#777; font-size:13px; font-style:italic; }
  .cfl-card-deeper { background:#111; border:1px solid #222; border-radius:6px; padding:18px 20px; }
  .cfl-card-deeper h3 { font-size:14px; color:#999; text-transform:uppercase; letter-spacing:1px; margin:0 0 10px; }
  .cfl-card-deeper a { color:#e63946; text-decoration:none; display:block; padding:6px 0; font-size:14px; }
  .cfl-card-deeper a:hover { text-decoration:underline; }
  .cfl-card-foot { color:#666; font-size:12px; margin-top:36px; text-align:center; }
  .cfl-card-foot a { color:#999; }
  .cfl-card-record { color:#999; font-size:13px; margin:0 0 26px; line-height:1.5; }
  .cfl-card-record strong { color:#ddd; }
  .cfl-card-record a { color:#e63946; text-decoration:none; }
  ${SIGNUP_CSS}
</style>
</head>
<body>

<div class="cfl-card-wrap">

  <div class="cfl-card-eyebrow">UFC Card Predictions</div>

  <h1>${escapeHtml(event.name)} Predictions</h1>

  <div class="cfl-card-meta">
    ${dateLabel ? escapeHtml(dateLabel) : ''}${event.location ? ' &middot; ' + escapeHtml(event.location) : ''}${bouts ? ' &middot; ' + bouts + ' fights' : ''}
  </div>

  <div class="cfl-card-summary">
    <span class="cfl-card-summary-label">Model forecast · odds-blind engine</span>
    ${mainPick
      ? `Main event: <strong>${escapeHtml(mainPick.winnerName)}</strong> · ${mainPick.pct}% · ${escapeHtml(mainPick.tier)}. Locked forecasts on record for ${withVerdict} of ${bouts} fights — never revised after the bell.`
      : `Forecasts lock before fight night. Full ${bouts}-fight card below.`}
  </div>
  <p class="cfl-card-record">How this engine has done: <strong data-claim="engine_replay_accuracy">…</strong> straight-up on <span data-claim="engine_replay_accuracy:sample_size">…</span> fights in the Engine v2 historical replay · live record since <span data-claim="live_since">…</span>: <strong data-claim="engine_live_accuracy">…</strong> on <span data-claim="engine_live_accuracy:sample_size">…</span> settled fights. <a href="${SITE}/track-record.html">Every miss is posted →</a></p>

  <div class="cfl-email-capture" data-source="card:${escapeHtml(String(event.id))}"></div>

  <h2 class="cfl-card-h2">Full card &amp; model forecasts</h2>
  <table class="cfl-card-table">
    <tbody>${rowHtml}
    </tbody>
  </table>

  <div class="cfl-card-deeper">
    <h3>Go deeper</h3>
    <a href="${eventUrl}">Live card &amp; odds: ${escapeHtml(event.name)} →</a>
    <a href="${SITE}/index.html#next">Card Lab — fights ranked by edge &amp; value →</a>
    <a href="${SITE}/track-record.html">Model track record: accuracy &amp; profit per $100 →</a>
    <a href="${SITE}/methodology.html">How the engine is built →</a>
  </div>

  <p class="cfl-card-foot">
    Cannon Fight Lab publishes model forecasts and market analysis. It does not sell handicapper picks. Not a sportsbook. 21+ only.
    <a href="${SITE}/disclaimer.html">Disclaimer</a>
  </p>

</div>

${SUPABASE_CDN}
<script src="${SHARED_JS}"></script>
<script src="${AUTH_JS}"></script>
<script>
cfl.track('preview_view', { card: ${JSON.stringify(String(event.id))}, event: ${JSON.stringify(event.name)} });
cfl.renderClaims('/data/claims.json');
</script>
</body>
</html>
`;
}

module.exports = { eventPreview, cardSlug, consensusPick, cardOrder };
