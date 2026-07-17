// Matchup-preview stub: a real, indexable, content-bearing static page for
// every fight on an upcoming UFC card. Unlike fighter/event stubs (which
// redirect users back to the dynamic page), the preview is the destination.
// It carries the model's verdict, the per-fighter cardio tier, and finish
// rates so a cold visitor arriving from a Google search for
//     "fighter a vs fighter b prediction"
// sees real, opinionated content immediately — and a Create-account CTA
// at the top of the page.
//
// Canonical URL points at the preview itself (not at h2h.html or event.html)
// since the content is unique to the preview.

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

function previewSlug(aName, bName, fightId) {
  return `${slugify(aName)}-vs-${slugify(bName)}-${fightId}`;
}

// Plain-English agreement label for the two public models (Value + Fight IQ).
// Handles the one-model case too (a fight only one model has graded).
function modelAgreementLabel(agree, total) {
  if (total <= 1) return '1 model';
  if (agree === total) return total === 2 ? 'both models agree' : `all ${total} models agree`;
  return `${agree} of ${total} models agree`;
}

// Render one preview page for a single fight. All params are optional except
// `fight`, `fighterA`, `fighterB`. Missing fields fall back to neutral copy
// so the page always renders something (no NaN%, no "null fights" etc.).
function matchupPreview({
  fight,
  fighterA,
  fighterB,
  event,
  picks,       // [{ model_version, fighter_id, model_p }]
  cardioA,     // 'tireless' | 'steady' | 'tapers' | 'fades' | 'collapses' | null
  cardioB,
  finishA,     // { total_fights, ko_tko_rate, sub_rate } | null
  finishB
}) {
  const slug = previewSlug(fighterA.name, fighterB.name, fight.id);
  const url = `${SITE}/preview/${slug}.html`;

  const eventName = event?.name || 'UFC';
  const dateLabel = event ? formatLongDate(event.event_date) : '';
  const weight = fight.weight_class ? ` ${fight.weight_class}` : '';
  const flag = fight.is_title_fight ? ' Title Fight' : (fight.is_main_event ? ' Main Event' : '');

  // ---- consensus model verdict ----
  const validPicks = (picks || []).filter(p => p.model_p != null && +p.model_p > 0.5);
  const tally = {};
  validPicks.forEach(p => { tally[p.fighter_id] = (tally[p.fighter_id] || 0) + 1; });
  const sortedSides = Object.entries(tally).sort((x, y) => y[1] - x[1]);

  let verdictLine = '';
  let descVerdict = '';
  let winnerName = null;
  if (sortedSides.length) {
    const winnerId = +sortedSides[0][0];
    const winner = winnerId === fighterA.id ? fighterA : fighterB;
    winnerName = winner.name;
    const winningPs = validPicks
      .filter(p => p.fighter_id === winnerId)
      .map(p => +p.model_p);
    const avgP = winningPs.reduce((s, x) => s + x, 0) / winningPs.length;
    const pct = Math.round(avgP * 100);
    const agree = sortedSides[0][1];
    const total = validPicks.length;
    const agreeLabel = modelAgreementLabel(agree, total);
    verdictLine = `<strong>${escapeHtml(winner.name)}</strong> · ${pct}% confidence · ${agreeLabel}`;
    descVerdict = `Model verdict: ${winner.name} (${pct}%, ${agreeLabel}). `;
  } else {
    verdictLine = `Verdict pending — model picks publish closer to fight night.`;
  }

  // ---- per-fighter edge notes ----
  function cardioLine(cardio) {
    if (!cardio) return null;
    const labels = {
      tireless:  '🟢 Tireless — output holds R3+',
      steady:    '🟢 Steady cardio',
      tapers:    '🟡 Tapers late',
      fades:     '🟠 Fades in deep waters',
      collapses: '🔴 Collapses R3+'
    };
    return labels[cardio] || null;
  }
  function finishLine(finish) {
    if (!finish || !finish.total_fights || finish.total_fights < 5) return null;
    const fr = (finish.ko_tko_rate || 0) + (finish.sub_rate || 0);
    if (fr < 0.3) return null;
    return `Finishes ${Math.round(fr * 100)}% of wins (${finish.total_fights} fights graded)`;
  }

  const aCardio = cardioLine(cardioA);
  const bCardio = cardioLine(cardioB);
  const aFinish = finishLine(finishA);
  const bFinish = finishLine(finishB);

  // ---- meta ----
  const title = `${fighterA.name} vs ${fighterB.name} — Prediction, Cardio & Edges | Cannon Fight Lab`;
  const description = (
    `${fighterA.name} vs ${fighterB.name}${flag ? ' (' + flag.trim() + ')' : ''} at ` +
    `${eventName}${dateLabel ? ' on ' + dateLabel : ''}. ${descVerdict}` +
    `Cardio scores, finish rates, and the strongest edge factors for both fighters.`
  ).trim();

  const sportsEventJsonLd = {
    '@context': 'https://schema.org',
    '@type': 'SportsEvent',
    'name': `${fighterA.name} vs ${fighterB.name}`,
    'sport': 'Mixed Martial Arts',
    'startDate': event?.event_date || undefined,
    'eventStatus': 'https://schema.org/EventScheduled',
    'eventAttendanceMode': 'https://schema.org/MixedEventAttendanceMode',
    'url': url,
    'superEvent': event ? {
      '@type': 'SportsEvent',
      'name': event.name,
      'url': `${SITE}/event.html?id=${event.id}`
    } : undefined,
    'organizer': {
      '@type': 'SportsOrganization',
      'name': 'Ultimate Fighting Championship',
      'alternateName': 'UFC'
    },
    'competitor': [
      { '@type': 'Person', 'name': fighterA.name, 'url': `${SITE}/fighter.html?id=${fighterA.id}` },
      { '@type': 'Person', 'name': fighterB.name, 'url': `${SITE}/fighter.html?id=${fighterB.id}` }
    ]
  };
  // Drop undefined keys so JSON.stringify doesn't emit `"key":undefined` (it
  // would just omit them, but explicit cleanup makes the JSON-LD readable in
  // view-source).
  Object.keys(sportsEventJsonLd).forEach(k => sportsEventJsonLd[k] === undefined && delete sportsEventJsonLd[k]);

  const faqJsonLd = winnerName ? {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    'mainEntity': [{
      '@type': 'Question',
      'name': `Who wins ${fighterA.name} vs ${fighterB.name}?`,
      'acceptedAnswer': {
        '@type': 'Answer',
        'text': `Cannon Fight Lab's models pick ${winnerName}. CFL runs two public models — one built only from fight tape, one built to beat the opening price. Every pick is locked before the bell and graded in public, misses included.`
      }
    }]
  } : null;

  const breadcrumbJsonLd = {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    'itemListElement': [
      { '@type': 'ListItem', 'position': 1, 'name': 'Home',     'item': SITE + '/' },
      { '@type': 'ListItem', 'position': 2, 'name': 'Previews', 'item': SITE + '/preview/' },
      { '@type': 'ListItem', 'position': 3, 'name': `${fighterA.name} vs ${fighterB.name}`, 'item': url }
    ]
  };

  const h2hUrl = `${SITE}/h2h.html?a=${fighterA.id}&b=${fighterB.id}`;
  const eventUrl = event ? `${SITE}/event.html?id=${event.id}` : `${SITE}/`;
  const signupUrl = `${SITE}/signup.html?next=${encodeURIComponent('/preview/' + slug + '.html')}`;

  const fighterCard = (f, cardioStr, finishStr) => `
    <article class="cfl-prev-card">
      <h2><a href="${SITE}/fighter.html?id=${f.id}">${escapeHtml(f.name)}</a></h2>
      ${f.nickname ? `<div class="cfl-prev-nick">"${escapeHtml(f.nickname)}"</div>` : ''}
      <ul class="cfl-prev-bullets">
        ${cardioStr ? `<li>${escapeHtml(cardioStr)}</li>` : ''}
        ${finishStr ? `<li>${escapeHtml(finishStr)}</li>` : ''}
        ${!cardioStr && !finishStr ? '<li>Profile loads on the full fighter page.</li>' : ''}
      </ul>
    </article>
  `;

  const jsonLdBlobs = [sportsEventJsonLd, breadcrumbJsonLd];
  if (faqJsonLd) jsonLdBlobs.push(faqJsonLd);

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
<meta property="og:title" content="${escapeHtml(`${fighterA.name} vs ${fighterB.name} — Prediction & Edges`)}">
<meta property="og:description" content="${escapeHtml(description)}">
<meta property="og:url" content="${url}">
<meta property="og:image" content="${SITE}/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Cannon Fight Lab — UFC matchup preview">
<meta property="og:locale" content="en_US">

<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="${escapeHtml(`${fighterA.name} vs ${fighterB.name} — Prediction & Edges`)}">
<meta name="twitter:description" content="${escapeHtml(description)}">
<meta name="twitter:image" content="${SITE}/og-image.png">

<meta name="theme-color" content="#0a0a0a">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">

${jsonLdBlobs.map(j => `<script type="application/ld+json">${JSON.stringify(j)}</script>`).join('\n')}

<style>
  body { background:#0a0a0a; color:#e8e8e8; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,sans-serif; margin:0; line-height:1.55; }
  .cfl-prev-wrap { max-width:880px; margin:0 auto; padding:40px 20px 80px; }
  .cfl-prev-eyebrow { color:#e63946; text-transform:uppercase; letter-spacing:1px; font-size:12px; font-weight:700; margin-bottom:10px; }
  .cfl-prev-eyebrow a { color:inherit; text-decoration:none; }
  .cfl-prev-eyebrow a:hover { text-decoration:underline; }
  h1 { font-size:34px; line-height:1.2; margin:0 0 8px; color:#fff; }
  h1 .vs { color:#999; padding:0 6px; font-weight:400; }
  .cfl-prev-meta { color:#999; font-size:14px; margin-bottom:28px; }
  .cfl-prev-meta strong { color:#e63946; }
  .cfl-prev-verdict { background:#181818; border:1px solid #2a2a2a; border-left:3px solid #e63946; padding:18px 20px; border-radius:6px; margin-bottom:30px; font-size:16px; }
  .cfl-prev-verdict-label { display:block; color:#999; font-size:11px; letter-spacing:1px; text-transform:uppercase; margin-bottom:6px; }
  .cfl-prev-cta { background:linear-gradient(135deg,#e63946 0%,#c1121f 100%); color:#fff; padding:22px 24px; border-radius:8px; margin-bottom:36px; display:flex; gap:18px; align-items:center; flex-wrap:wrap; }
  .cfl-prev-cta-text { flex:1 1 280px; }
  .cfl-prev-cta-text strong { display:block; font-size:17px; margin-bottom:3px; }
  .cfl-prev-cta-text span { color:#fff; opacity:0.85; font-size:13px; }
  .cfl-prev-cta a.btn { background:#fff; color:#c1121f; padding:10px 22px; border-radius:6px; font-weight:700; text-decoration:none; white-space:nowrap; font-size:14px; }
  .cfl-prev-cta a.btn:hover { background:#f5f5f5; }
  .cfl-prev-grid { display:grid; grid-template-columns:1fr 1fr; gap:18px; margin-bottom:30px; }
  @media (max-width:640px){ .cfl-prev-grid { grid-template-columns:1fr; } }
  .cfl-prev-card { background:#111; border:1px solid #222; border-radius:6px; padding:18px; }
  .cfl-prev-card h2 { font-size:18px; margin:0 0 4px; }
  .cfl-prev-card h2 a { color:#fff; text-decoration:none; }
  .cfl-prev-card h2 a:hover { color:#e63946; }
  .cfl-prev-nick { color:#999; font-style:italic; font-size:13px; margin-bottom:10px; }
  .cfl-prev-bullets { list-style:none; padding:0; margin:0; }
  .cfl-prev-bullets li { padding:6px 0; color:#d0d0d0; font-size:14px; border-bottom:1px solid #1a1a1a; }
  .cfl-prev-bullets li:last-child { border-bottom:none; }
  .cfl-prev-deeper { background:#111; border:1px solid #222; border-radius:6px; padding:18px 20px; }
  .cfl-prev-deeper h3 { font-size:14px; color:#999; text-transform:uppercase; letter-spacing:1px; margin:0 0 10px; }
  .cfl-prev-deeper a { color:#e63946; text-decoration:none; display:block; padding:6px 0; font-size:14px; }
  .cfl-prev-deeper a:hover { text-decoration:underline; }
  .cfl-prev-foot { color:#666; font-size:12px; margin-top:36px; text-align:center; }
  .cfl-prev-foot a { color:#999; }
</style>
</head>
<body>

<div class="cfl-prev-wrap">

  <div class="cfl-prev-eyebrow">
    <a href="${eventUrl}">${escapeHtml(eventName)}</a>
  </div>

  <h1>${escapeHtml(fighterA.name)} <span class="vs">vs</span> ${escapeHtml(fighterB.name)}</h1>

  <div class="cfl-prev-meta">
    ${dateLabel ? escapeHtml(dateLabel) : ''}${event?.location ? ' &middot; ' + escapeHtml(event.location) : ''}${weight ? ' &middot; ' + escapeHtml(weight.trim()) : ''}${flag ? ' &middot; <strong>' + escapeHtml(flag.trim()) + '</strong>' : ''}
  </div>

  <div class="cfl-prev-verdict">
    <span class="cfl-prev-verdict-label">Model verdict</span>
    ${verdictLine}
  </div>

  <div class="cfl-prev-cta">
    <div class="cfl-prev-cta-text">
      <strong>Track this pick on your free account</strong>
      <span>Free during beta — see every edge factor, save your picks, get the weekly preview email.</span>
    </div>
    <a class="btn" href="${signupUrl}">Create free account →</a>
  </div>

  <div class="cfl-prev-grid">
    ${fighterCard(fighterA, aCardio, aFinish)}
    ${fighterCard(fighterB, bCardio, bFinish)}
  </div>

  <div class="cfl-prev-deeper">
    <h3>Go deeper</h3>
    <a href="${h2hUrl}">Head-to-head: ${escapeHtml(fighterA.name)} vs ${escapeHtml(fighterB.name)} →</a>
    <a href="${eventUrl}">Full card &amp; verdicts: ${escapeHtml(eventName)} →</a>
    <a href="${SITE}/cardio.html">How the cardio score works →</a>
    <a href="${SITE}/edges.html">How model verdicts are built →</a>
  </div>

  <p class="cfl-prev-foot">
    Cannon Fight Lab is an analytics publication, not a sportsbook. 21+ only.
    <a href="${SITE}/disclaimer.html">Disclaimer</a>
  </p>

</div>

</body>
</html>
`;
}

module.exports = { matchupPreview, previewSlug };
