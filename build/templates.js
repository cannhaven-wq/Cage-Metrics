// Stub HTML templates for prerendered fighter and event pages.
//
// The stub is *not* the canonical URL — it has <link rel="canonical"> pointing
// back to fighter.html?id=N / event.html?id=N. Its job is to let social
// unfurlers (Twitter, Facebook, Discord, iMessage) and crawlers see real
// per-page meta + JSON-LD without needing JS execution. Humans who land here
// get JS-redirected to the dynamic page; crawlers read the head and stop.
//
// IMPORTANT: any change to the static fallback meta in fighter.html /
// event.html should be mirrored here, otherwise the stubs drift from the
// canonical pages.

const { slugify } = require('./slug');

const SITE = 'https://cannonfightlab.com';

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

function formatHeight(inches) {
  if (inches == null) return null;
  const ft = Math.floor(inches / 12);
  const inch = Math.round(inches % 12);
  return `${ft}'${inch}"`;
}

function formatDate(isoDate) {
  if (!isoDate) return '';
  const d = new Date(isoDate + 'T00:00:00');
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
}

function fighterStub(f) {
  const id = f.id;
  const slug = slugify(f.name);
  const stubUrl = `${SITE}/f/${slug}-${id}.html`;
  const canonicalUrl = `${SITE}/fighter.html?id=${id}`;

  const careerWLD = `${f.wins ?? 0}-${f.losses ?? 0}${f.draws ? '-' + f.draws : ''}`;
  const ufcCount = (f.ufc_wins ?? 0) + (f.ufc_losses ?? 0) + (f.ufc_draws ?? 0);
  const ufcWLD = `${f.ufc_wins ?? 0}-${f.ufc_losses ?? 0}${f.ufc_draws ? '-' + f.ufc_draws : ''}`;
  const division = f.division ? `, ${f.division}` : '';

  const title = `${f.name} — UFC Fighter Stats & Analytics | Cannon Fight Lab`;
  const description = `${f.name}${f.nickname ? ' "' + f.nickname + '"' : ''} UFC fighter stats: ${careerWLD} career record${division}. Cardio score, striking, grappling, recent form, head-to-head matchups.`;
  const ogTitle = `${f.name} — UFC Fighter Stats`;

  const athleteJsonLd = {
    '@context': 'https://schema.org',
    '@type': 'Person',
    'name': f.name,
    'url': canonicalUrl,
    'jobTitle': 'Mixed Martial Artist',
    'memberOf': { '@type': 'SportsOrganization', 'name': 'Ultimate Fighting Championship', 'alternateName': 'UFC' }
  };
  if (f.nickname) athleteJsonLd.alternateName = f.nickname;
  const heightStr = formatHeight(f.height_in);
  if (heightStr) athleteJsonLd.height = heightStr;

  const breadcrumbJsonLd = {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    'itemListElement': [
      { '@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': SITE + '/' },
      { '@type': 'ListItem', 'position': 2, 'name': 'Fighters', 'item': SITE + '/fighters.html' },
      { '@type': 'ListItem', 'position': 3, 'name': f.name, 'item': stubUrl }
    ]
  };

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>${escapeHtml(title)}</title>
<meta name="description" content="${escapeHtml(description)}">
<meta name="author" content="Cannon Fight Lab">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="${canonicalUrl}">
<meta http-equiv="refresh" content="0; url=${canonicalUrl}">

<meta property="og:type" content="profile">
<meta property="og:site_name" content="Cannon Fight Lab">
<meta property="og:title" content="${escapeHtml(ogTitle)}">
<meta property="og:description" content="${escapeHtml(description)}">
<meta property="og:url" content="${stubUrl}">
<meta property="og:image" content="${SITE}/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Cannon Fight Lab — UFC fighter profile">
<meta property="og:locale" content="en_US">

<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="${escapeHtml(ogTitle)}">
<meta name="twitter:description" content="${escapeHtml(description)}">
<meta name="twitter:image" content="${SITE}/og-image.png">

<meta name="theme-color" content="#0a0a0a">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">

<script type="application/ld+json">${JSON.stringify(athleteJsonLd)}</script>
<script type="application/ld+json">${JSON.stringify(breadcrumbJsonLd)}</script>

<style>
  body { background: #0a0a0a; color: #e8e8e8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 60px 20px; text-align: center; margin: 0; line-height: 1.5; }
  h1 { font-size: 36px; color: #fff; margin: 0 0 8px; }
  .nick { color: #a0a0a0; font-style: italic; margin-bottom: 16px; }
  .record { color: #d0d0d0; font-size: 18px; margin-bottom: 28px; }
  a { color: #ff3838; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .loading { color: #707070; font-size: 13px; margin-top: 40px; }
</style>
</head>
<body>
<h1>${escapeHtml(f.name)}</h1>
${f.nickname ? `<div class="nick">"${escapeHtml(f.nickname)}"</div>` : ''}
<div class="record">${careerWLD} career${division ? ' ' + escapeHtml(division.slice(2)) : ''}${ufcCount > 0 ? ' &middot; ' + ufcWLD + ' UFC' : ''}</div>
<p><a href="${canonicalUrl}">View full stats, cardio score, and head-to-head matchups &rarr;</a></p>
<p class="loading">Redirecting&hellip;</p>
<script>setTimeout(function(){location.replace(${JSON.stringify(canonicalUrl)});},120);</script>
</body>
</html>
`;
}

function eventStub(e, fighters) {
  const id = e.id;
  const slug = slugify(e.name);
  const stubUrl = `${SITE}/e/${slug}-${id}.html`;
  const canonicalUrl = `${SITE}/event.html?id=${id}`;

  const dateStr = formatDate(e.event_date);
  const status = e.is_upcoming ? 'Predictions' : 'Results';
  const verb = e.is_upcoming ? 'predictions and edge factors' : 'results and breakdown';
  const title = `${e.name} — UFC ${status} | Cannon Fight Lab`;
  const description = `${e.name}${dateStr ? ' on ' + dateStr : ''}${e.location ? ' in ' + e.location : ''}. Full card with model ${verb} for every fight.`;
  const ogTitle = `${e.name} — Cannon Fight Lab`;

  const sportsEventJsonLd = {
    '@context': 'https://schema.org',
    '@type': 'SportsEvent',
    'name': e.name,
    'sport': 'Mixed Martial Arts',
    'startDate': e.event_date,
    'eventStatus': e.is_upcoming ? 'https://schema.org/EventScheduled' : 'https://schema.org/EventCompleted',
    'eventAttendanceMode': 'https://schema.org/MixedEventAttendanceMode',
    'url': canonicalUrl,
    'organizer': { '@type': 'SportsOrganization', 'name': 'Ultimate Fighting Championship', 'alternateName': 'UFC' }
  };
  if (e.location) {
    sportsEventJsonLd.location = { '@type': 'Place', 'name': e.location };
  }
  if (fighters && fighters.length > 0) {
    // Dedupe by id — fighters list may include the same person across multiple
    // fights on the card if there are duplicate-name issues, though that's rare.
    const seen = new Set();
    const competitors = [];
    for (const f of fighters) {
      if (!f.id || seen.has(f.id)) continue;
      seen.add(f.id);
      competitors.push({
        '@type': 'Person',
        'name': f.name,
        'url': `${SITE}/fighter.html?id=${f.id}`
      });
    }
    if (competitors.length > 0) sportsEventJsonLd.competitor = competitors;
  }

  const breadcrumbJsonLd = {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    'itemListElement': [
      { '@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': SITE + '/' },
      { '@type': 'ListItem', 'position': 2, 'name': e.name, 'item': stubUrl }
    ]
  };

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>${escapeHtml(title)}</title>
<meta name="description" content="${escapeHtml(description)}">
<meta name="author" content="Cannon Fight Lab">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="${canonicalUrl}">
<meta http-equiv="refresh" content="0; url=${canonicalUrl}">

<meta property="og:type" content="article">
<meta property="og:site_name" content="Cannon Fight Lab">
<meta property="og:title" content="${escapeHtml(ogTitle)}">
<meta property="og:description" content="${escapeHtml(description)}">
<meta property="og:url" content="${stubUrl}">
<meta property="og:image" content="${SITE}/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Cannon Fight Lab — UFC event card">
<meta property="og:locale" content="en_US">

<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="${escapeHtml(ogTitle)}">
<meta name="twitter:description" content="${escapeHtml(description)}">
<meta name="twitter:image" content="${SITE}/og-image.png">

<meta name="theme-color" content="#0a0a0a">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">

<script type="application/ld+json">${JSON.stringify(sportsEventJsonLd)}</script>
<script type="application/ld+json">${JSON.stringify(breadcrumbJsonLd)}</script>

<style>
  body { background: #0a0a0a; color: #e8e8e8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 60px 20px; text-align: center; margin: 0; line-height: 1.5; }
  h1 { font-size: 36px; color: #fff; margin: 0 0 12px; }
  .meta { color: #a0a0a0; margin-bottom: 28px; }
  a { color: #ff3838; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .loading { color: #707070; font-size: 13px; margin-top: 40px; }
</style>
</head>
<body>
<h1>${escapeHtml(e.name)}</h1>
<div class="meta">${escapeHtml(dateStr)}${e.location ? ' &middot; ' + escapeHtml(e.location) : ''}</div>
<p><a href="${canonicalUrl}">View full card with model verdicts and edge factors &rarr;</a></p>
<p class="loading">Redirecting&hellip;</p>
<script>setTimeout(function(){location.replace(${JSON.stringify(canonicalUrl)});},120);</script>
</body>
</html>
`;
}

module.exports = { fighterStub, eventStub };
