// Matchup-preview stub: a real, indexable, content-bearing static page for
// every fight on an upcoming UFC card. Unlike fighter/event stubs (which
// redirect users back to the dynamic page), the preview is the destination.
// It carries the engine's LOCKED forecast (pre-fight snapshot, or the
// insert-only live row until the snapshot exists — never a recompute, never a
// backtest row), a short tale-of-the-tape comparison, the per-fighter cardio
// tier and finish rates, and the Fight Week Market Brief signup, so a cold
// visitor arriving from a Google search for
//     "fighter a vs fighter b prediction"
// sees real, opinionated content immediately.
//
// Canonical URL points at the preview itself (not at h2h.html or event.html)
// since the content is unique to the preview.

const { slugify } = require('./slug');

const SITE = 'https://cannonfightlab.com';
// Keep in step with the ?v= on every root page (see CLAUDE.md "Caching gotcha").
const SHARED_JS = '/_shared.js?v=rd17';
const AUTH_JS = '/_auth.js?v=rf1';
const SUPABASE_CDN = '<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.106.1/dist/umd/supabase.min.js" integrity="sha384-9dsYHX1/12VQI+gHRtPXSM3YFsgJ+iIPjTy4WCtY7XbKG/q7MTdZxZhMd4cL9Gif" crossorigin="anonymous"></script>';
const PLAUSIBLE = '<script defer data-domain="cannonfightlab.com" src="https://plausible.io/js/script.js"></script>';

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

function formatShortDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return '';
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
}

function previewSlug(aName, bName, fightId) {
  return `${slugify(aName)}-vs-${slugify(bName)}-${fightId}`;
}

// Mirrors cfl.ENGINE.tiers in _shared.js / tier_of in cfl_engine/faces.py.
function tierWord(p) {
  if (p == null) return '';
  if (p >= 0.65) return 'Lock';
  if (p >= 0.57) return 'Pick';
  return 'Lean';
}

// Shared CSS for the signup component (the class names _shared.js renders).
// Copied rather than loading _shared.css so the preview keeps its own layout.
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

// Tale of the tape rows. Every value is optional; a row is dropped when both
// sides are missing so the table never shows a column of dashes.
function tapeRows(a, b) {
  const rec = f => (f.wins == null && f.losses == null) ? null : `${f.wins ?? 0}-${f.losses ?? 0}${f.draws ? '-' + f.draws : ''}`;
  const ht = f => f.height_in == null ? null : `${Math.floor(f.height_in / 12)}'${Math.round(f.height_in % 12)}"`;
  const rch = f => f.reach_in == null ? null : `${f.reach_in}"`;
  const age = f => {
    if (f.dob) {
      const d = new Date(f.dob + 'T00:00:00Z'); const now = new Date();
      let y = now.getUTCFullYear() - d.getUTCFullYear();
      if (now.getUTCMonth() < d.getUTCMonth() || (now.getUTCMonth() === d.getUTCMonth() && now.getUTCDate() < d.getUTCDate())) y -= 1;
      return String(y);
    }
    return f.age == null ? null : String(f.age);
  };
  const num = (v, dp) => v == null ? null : Number(v).toFixed(dp);
  const pct = v => v == null ? null : `${Math.round(Number(v) * (Number(v) <= 1 ? 100 : 1))}%`;
  const rows = [
    ['Record', rec(a), rec(b)],
    ['Height', ht(a), ht(b)],
    ['Reach', rch(a), rch(b)],
    ['Stance', a.stance || null, b.stance || null],
    ['Age', age(a), age(b)],
    ['Sig. strikes / min', num(a.slpm, 1), num(b.slpm, 1)],
    ['Strike accuracy', pct(a.str_acc), pct(b.str_acc)],
    ['Takedowns / 15 min', num(a.td_avg, 1), num(b.td_avg, 1)],
    ['Takedown defense', pct(a.td_def), pct(b.td_def)],
  ];
  return rows.filter(r => r[1] != null || r[2] != null);
}

// Render one preview page for a single fight. All params are optional except
// `fight`, `fighterA`, `fighterB`. Missing fields fall back to neutral copy
// so the page always renders something (no NaN%, no "null fights" etc.).
function matchupPreview({
  fight,
  fighterA,
  fighterB,
  event,
  picks,       // [{ fighter_id, model_p, tier, locked: 'snapshot'|'live', locked_at }]
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

  // ---- locked engine forecast ----
  const locked = (picks || []).find(p => p.model_p != null && p.fighter_id != null) || null;
  let verdictLine = '';
  let descVerdict = '';
  let winnerName = null;
  let pct = null;
  let lockNote = '';
  if (locked) {
    const winner = locked.fighter_id === fighterA.id ? fighterA : (locked.fighter_id === fighterB.id ? fighterB : null);
    if (winner) {
      winnerName = winner.name;
      pct = Math.round(+locked.model_p * 100);
      const tw = locked.tier || tierWord(+locked.model_p);
      lockNote = locked.locked === 'snapshot'
        ? `Locked in the pre-fight snapshot${locked.locked_at ? ' on ' + formatShortDate(locked.locked_at) : ''} — never revised.`
        : `Locked at first write${locked.locked_at ? ' on ' + formatShortDate(locked.locked_at) : ''} — never revised.`;
      verdictLine = `<strong>${escapeHtml(winner.name)}</strong> · ${pct}% · ${escapeHtml(tw)}`;
      descVerdict = `CFL's odds-blind engine forecasts ${winner.name} at ${pct}%. `;
    }
  }
  if (!winnerName) {
    verdictLine = `Forecast pending — the engine's forecast locks before fight night.`;
  }

  // ---- per-fighter notes ----
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
  const tape = tapeRows(fighterA, fighterB);

  // ---- meta (unique per page) ----
  const title = `${fighterA.name} vs ${fighterB.name} Prediction & Odds | Cannon Fight Lab`;
  const tapeBits = [];
  const recA = tape.find(r => r[0] === 'Record'); if (recA) tapeBits.push(`${fighterA.name.split(' ').pop()} ${recA[1] || '—'} vs ${fighterB.name.split(' ').pop()} ${recA[2] || '—'}`);
  const description = (
    `${fighterA.name} vs ${fighterB.name}${flag ? ' (' + flag.trim() + ')' : ''} at ` +
    `${eventName}${dateLabel ? ', ' + dateLabel : ''}. ${descVerdict}` +
    `${tapeBits.length ? tapeBits.join('; ') + '. ' : ''}` +
    `Locked forecast, tale of the tape, cardio and finish rates — graded in public, misses included.`
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
  Object.keys(sportsEventJsonLd).forEach(k => sportsEventJsonLd[k] === undefined && delete sportsEventJsonLd[k]);

  const faqJsonLd = winnerName ? {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    'mainEntity': [{
      '@type': 'Question',
      'name': `Who wins ${fighterA.name} vs ${fighterB.name}?`,
      'acceptedAnswer': {
        '@type': 'Answer',
        'text': `Cannon Fight Lab's odds-blind engine forecasts ${winnerName} at ${pct}%. The forecast was locked before the bell and is graded in public, misses included. CFL publishes model forecasts and market analysis; it does not sell handicapper picks.`
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

  const tapeHtml = tape.length ? `
  <h2 class="cfl-prev-h2">Tale of the tape</h2>
  <table class="cfl-prev-tape">
    <thead><tr><th></th><th>${escapeHtml(fighterA.name)}</th><th>${escapeHtml(fighterB.name)}</th></tr></thead>
    <tbody>${tape.map(r => `<tr><td>${escapeHtml(r[0])}</td><td>${escapeHtml(r[1] ?? '—')}</td><td>${escapeHtml(r[2] ?? '—')}</td></tr>`).join('')}</tbody>
  </table>` : '';

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
<meta property="og:title" content="${escapeHtml(`${fighterA.name} vs ${fighterB.name} — Prediction & Odds`)}">
<meta property="og:description" content="${escapeHtml(description)}">
<meta property="og:url" content="${url}">
<meta property="og:image" content="${SITE}/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Cannon Fight Lab — UFC matchup preview">
<meta property="og:locale" content="en_US">

<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="${escapeHtml(`${fighterA.name} vs ${fighterB.name} — Prediction & Odds`)}">
<meta name="twitter:description" content="${escapeHtml(description)}">
<meta name="twitter:image" content="${SITE}/og-image.png">

<meta name="theme-color" content="#0a0a0a">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
${PLAUSIBLE}

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
  .cfl-prev-verdict { background:#181818; border:1px solid #2a2a2a; border-left:3px solid #e63946; padding:18px 20px; border-radius:6px; margin-bottom:12px; font-size:16px; }
  .cfl-prev-verdict-label { display:block; color:#999; font-size:11px; letter-spacing:1px; text-transform:uppercase; margin-bottom:6px; }
  .cfl-prev-lock { color:#888; font-size:12px; margin:8px 0 0; }
  .cfl-prev-record { color:#999; font-size:13px; margin:0 0 26px; line-height:1.5; }
  .cfl-prev-record strong { color:#ddd; }
  .cfl-prev-record a { color:#e63946; text-decoration:none; }
  h2.cfl-prev-h2 { font-size:18px; color:#fff; margin:0 0 10px; }
  table.cfl-prev-tape { width:100%; border-collapse:collapse; margin-bottom:30px; font-size:14px; }
  table.cfl-prev-tape th { text-align:left; color:#999; font-size:11px; letter-spacing:1px; text-transform:uppercase; padding:8px; border-bottom:1px solid #2a2a2a; }
  table.cfl-prev-tape td { padding:9px 8px; border-bottom:1px solid #1c1c1c; color:#e8e8e8; }
  table.cfl-prev-tape td:first-child { color:#999; }
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
  ${SIGNUP_CSS}
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
    <span class="cfl-prev-verdict-label">Model forecast · odds-blind engine</span>
    ${verdictLine}
    ${lockNote ? `<p class="cfl-prev-lock">${escapeHtml(lockNote)}</p>` : ''}
  </div>
  <p class="cfl-prev-record">How this engine has done: <strong data-claim="engine_replay_accuracy">…</strong> straight-up on <span data-claim="engine_replay_accuracy:sample_size">…</span> fights in the Engine v2 historical replay · live record since <span data-claim="live_since">…</span>: <strong data-claim="engine_live_accuracy">…</strong> on <span data-claim="engine_live_accuracy:sample_size">…</span> settled fights. <a href="${SITE}/track-record.html">Every miss is posted →</a></p>

  <div class="cfl-email-capture" data-source="preview:${escapeHtml(String(fight.id))}"></div>

  ${tapeHtml}

  <div class="cfl-prev-grid">
    ${fighterCard(fighterA, aCardio, aFinish)}
    ${fighterCard(fighterB, bCardio, bFinish)}
  </div>

  <div class="cfl-prev-deeper">
    <h3>Go deeper</h3>
    <a href="${h2hUrl}">Head-to-head: ${escapeHtml(fighterA.name)} vs ${escapeHtml(fighterB.name)} →</a>
    <a href="${eventUrl}">Full card &amp; forecasts: ${escapeHtml(eventName)} →</a>
    <a href="${SITE}/cardio.html">How the cardio score works →</a>
    <a href="${SITE}/methodology.html">How the engine is built →</a>
  </div>

  <p class="cfl-prev-foot">
    Cannon Fight Lab publishes model forecasts and market analysis. It does not sell handicapper picks. Not a sportsbook. 21+ only.
    <a href="${SITE}/disclaimer.html">Disclaimer</a>
  </p>

</div>

${SUPABASE_CDN}
<script src="${SHARED_JS}"></script>
<script src="${AUTH_JS}"></script>
<script>
cfl.track('preview_view', { fight: ${JSON.stringify(String(fight.id))}, event: ${JSON.stringify(eventName)} });
cfl.renderClaims('/data/claims.json');
</script>
</body>
</html>
`;
}

module.exports = { matchupPreview, previewSlug };
