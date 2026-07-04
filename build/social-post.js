// Social auto-poster. Runs on Wednesday afternoon UTC via social-post.yml.
// Posts a short summary of the next UFC card to X (Twitter v2 API) and
// Reddit (script-style OAuth app). Both targets are optional — if the
// secrets for a platform aren't set, that platform is skipped silently.
//
// The post body is generated here directly rather than scraping draft-post.js
// stdout. Same source data (model_predictions + cardio) so the messaging
// stays consistent with the email digest and the on-site previews.
//
// Idempotency: we don't double-post on the same event. The script writes a
// marker file at .funnel-state/last-posted-event.txt with the event id,
// and the workflow commits it back. If the latest upcoming event matches
// the marker, the script exits 0 without posting. To force a re-post:
// delete the marker file (or set FORCE_POST=1).
//
// Secrets (set in repo settings as actions secrets, optional):
//   X_BEARER_TOKEN, X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET
//   REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD,
//   REDDIT_SUBREDDIT (defaults to "u_<username>" — i.e. user profile, safest)

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { createClient } = require('@supabase/supabase-js');
const { slugify } = require('./slug');

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SUPABASE_KEY = 'sb_publishable_boJGOA1CFN-SF14HHFGUAw_YEEm0DU8';
const SITE = 'https://cannonfightlab.com';

const ROOT = path.resolve(__dirname, '..');
const STATE_DIR = path.join(ROOT, '.funnel-state');
const MARKER = path.join(STATE_DIR, 'last-posted-event.txt');
const FORCE = /^(1|true|yes)$/i.test(process.env.FORCE_POST || '');
const DRY_RUN = /^(1|true|yes)$/i.test(process.env.SOCIAL_DRY_RUN || '');

const sb = createClient(SUPABASE_URL, SUPABASE_KEY);

const todayUTC = () => new Date().toISOString().slice(0, 10);

function formatLongDate(isoDate) {
  if (!isoDate) return '';
  const d = new Date(isoDate + 'T00:00:00');
  return d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
}

async function buildPost(event) {
  const { data: fights } = await sb.from('fights')
    .select('id, fighter_a_id, fighter_b_id, fighter_a_name, fighter_b_name, is_main_event, is_title_fight')
    .eq('event_id', event.id)
    .order('is_main_event', { ascending: false })
    .order('id', { ascending: true });
  if (!fights || !fights.length) return null;

  const fightIds = fights.map(f => f.id);
  const { data: preds } = await sb.from('model_predictions')
    .select('model_version, fight_id, fighter_id, model_p')
    .in('fight_id', fightIds);

  const picksByFight = {};
  (preds || []).forEach(p => {
    if (p.model_p == null || +p.model_p <= 0.5) return;
    (picksByFight[p.fight_id] = picksByFight[p.fight_id] || {})[p.model_version] =
      { fighter_id: p.fighter_id, model_p: +p.model_p };
  });

  // Pull up to 5 highest-confidence fights (with main/title prioritized).
  const lines = [];
  for (const f of fights) {
    const picks = picksByFight[f.id] || {};
    const versions = Object.keys(picks);
    if (!versions.length) continue;
    const tally = {};
    versions.forEach(v => { tally[picks[v].fighter_id] = (tally[picks[v].fighter_id] || 0) + 1; });
    const sorted = Object.entries(tally).sort((x, y) => y[1] - x[1]);
    const winnerId = +sorted[0][0];
    const winnerName = winnerId === f.fighter_a_id ? f.fighter_a_name : f.fighter_b_name;
    const winningPs = versions
      .filter(v => picks[v].fighter_id === winnerId)
      .map(v => picks[v].model_p);
    const avg = winningPs.reduce((s, x) => s + x, 0) / winningPs.length;
    lines.push({
      aName: f.fighter_a_name,
      bName: f.fighter_b_name,
      flag: f.is_title_fight ? 'TITLE' : (f.is_main_event ? 'MAIN' : ''),
      pickName: winnerName,
      pct: Math.round(avg * 100),
      isMain: f.is_main_event || f.is_title_fight
    });
  }
  if (!lines.length) return null;

  // Sort: main/title first (preserve given order within), then by confidence.
  lines.sort((a, b) => (b.isMain - a.isMain) || (b.pct - a.pct));
  const headlineLines = lines.slice(0, 5);

  const eventUrl = `${SITE}/event.html?id=${event.id}`;
  const date = formatLongDate(event.event_date);

  // Twitter: must fit 280 chars. Format conservatively.
  const tweet = (() => {
    const header = `🥊 ${event.name} — model picks, locked in.\n${date}\n\n`;
    const cta = `\nFull card + edges + free account:\n${eventUrl}`;
    let body = '';
    for (const l of headlineLines) {
      const tag = l.flag ? ` [${l.flag}]` : '';
      const line = `${l.aName} vs ${l.bName}${tag}\n→ ${l.pickName} ${l.pct}%\n`;
      if ((header + body + line + cta).length > 275) break;
      body += line;
    }
    return (header + body + cta).slice(0, 280);
  })();

  // Reddit: title + selftext markdown.
  const redditTitle = `[Model picks] ${event.name} — ${date}`;
  const redditBody = (() => {
    const parts = [];
    parts.push(`Posting verdicts before the card so receipts are timestamped.\n`);
    parts.push(`| Fight | Pick | Conf |`);
    parts.push(`|---|---|---|`);
    for (const l of headlineLines) {
      const tag = l.flag ? ` **[${l.flag}]**` : '';
      parts.push(`| ${l.aName} vs ${l.bName}${tag} | ${l.pickName} | ${l.pct}% |`);
    }
    parts.push('');
    parts.push(`Full card with the edge factors that drove each verdict: ${eventUrl}`);
    parts.push('');
    parts.push(`*Free tool. Free account unlocks every edge + weekly preview email: ${SITE}/signup.html?src=reddit*`);
    return parts.join('\n');
  })();

  return { tweet, redditTitle, redditBody };
}

// -------------------- X (Twitter v2) --------------------
function oauth1Header({ url, method, params, consumer, token }) {
  // RFC 5849 1.0 — only the subset needed for POST /2/tweets with JSON body.
  // For a JSON body the body is NOT included in the signature; only oauth_*
  // + query params participate.
  const oauthParams = {
    oauth_consumer_key: consumer.key,
    oauth_token: token.key,
    oauth_signature_method: 'HMAC-SHA1',
    oauth_timestamp: Math.floor(Date.now() / 1000).toString(),
    oauth_nonce: crypto.randomBytes(16).toString('hex'),
    oauth_version: '1.0'
  };
  const allParams = { ...oauthParams, ...(params || {}) };
  const enc = s => encodeURIComponent(s).replace(/[!*'()]/g, c => '%' + c.charCodeAt(0).toString(16).toUpperCase());
  const baseParams = Object.keys(allParams).sort()
    .map(k => `${enc(k)}=${enc(allParams[k])}`).join('&');
  const baseString = `${method.toUpperCase()}&${enc(url)}&${enc(baseParams)}`;
  const signingKey = `${enc(consumer.secret)}&${enc(token.secret)}`;
  const signature = crypto.createHmac('sha1', signingKey).update(baseString).digest('base64');
  const header = 'OAuth ' + Object.entries({ ...oauthParams, oauth_signature: signature })
    .sort()
    .map(([k, v]) => `${enc(k)}="${enc(v)}"`)
    .join(', ');
  return header;
}

// Upload one image to X (v1.1 media endpoint) and return its media_id_string,
// or null on any problem. Multipart bodies aren't part of the OAuth1 signature,
// so the same header helper works. Failure here is non-fatal — the caller falls
// back to a text-only tweet.
async function uploadMediaToX(imagePath, creds) {
  try {
    if (!imagePath || !fs.existsSync(imagePath)) return null;
    if (typeof FormData === 'undefined' || typeof Blob === 'undefined') {
      console.log('[x] FormData/Blob unavailable (old Node) → text-only.');
      return null;
    }
    const url = 'https://upload.twitter.com/1.1/media/upload.json';
    const auth = oauth1Header({
      url, method: 'POST', params: {},
      consumer: { key: creds.key, secret: creds.secret },
      token: { key: creds.accessToken, secret: creds.accessSecret }
    });
    const buf = fs.readFileSync(imagePath);
    const form = new FormData();
    form.append('media', new Blob([buf]), path.basename(imagePath));
    const res = await fetch(url, { method: 'POST', headers: { Authorization: auth }, body: form });
    if (!res.ok) {
      console.error('[x] media upload failed:', res.status, (await res.text()).slice(0, 200));
      return null;
    }
    const j = await res.json();
    console.log('[x] media uploaded:', j.media_id_string, `(${path.basename(imagePath)})`);
    return j.media_id_string;
  } catch (e) {
    console.error('[x] media upload error:', e.message);
    return null;
  }
}

async function postToX(tweetText, imagePath) {
  const key = process.env.X_API_KEY;
  const secret = process.env.X_API_SECRET;
  const accessToken = process.env.X_ACCESS_TOKEN;
  const accessSecret = process.env.X_ACCESS_SECRET;
  if (!key || !secret || !accessToken || !accessSecret) {
    console.log('[x] secrets missing → skipping X post.');
    return { skipped: true };
  }
  if (DRY_RUN) {
    console.log(`[x] dry-run, would post${imagePath ? ` (with image ${path.basename(imagePath)})` : ''}:\n---\n` + tweetText + '\n---');
    return { dryRun: true };
  }
  const creds = { key, secret, accessToken, accessSecret };
  const mediaId = imagePath ? await uploadMediaToX(imagePath, creds) : null;
  const url = 'https://api.twitter.com/2/tweets';
  const auth = oauth1Header({
    url, method: 'POST', params: {},
    consumer: { key, secret },
    token: { key: accessToken, secret: accessSecret }
  });
  const payload = mediaId ? { text: tweetText, media: { media_ids: [mediaId] } } : { text: tweetText };
  const res = await fetch(url, {
    method: 'POST',
    headers: { Authorization: auth, 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    const body = await res.text();
    console.error('[x] post failed:', res.status, body);
    return { ok: false, status: res.status, body };
  }
  const j = await res.json();
  console.log('[x] posted tweet id:', j.data?.id);
  return { ok: true, id: j.data?.id };
}

// -------------------- Reddit --------------------
async function postToReddit(title, selftext) {
  const clientId = process.env.REDDIT_CLIENT_ID;
  const clientSecret = process.env.REDDIT_CLIENT_SECRET;
  const username = process.env.REDDIT_USERNAME;
  const password = process.env.REDDIT_PASSWORD;
  if (!clientId || !clientSecret || !username || !password) {
    console.log('[reddit] secrets missing → skipping Reddit post.');
    return { skipped: true };
  }
  // Default to posting on the user's own profile (u_<username>) — safest;
  // self-promo rules vary wildly per subreddit. Override via REDDIT_SUBREDDIT.
  const subreddit = process.env.REDDIT_SUBREDDIT || `u_${username}`;
  const ua = `cfl-funnel/1.0 by /u/${username}`;
  if (DRY_RUN) {
    console.log(`[reddit] dry-run, would post to r/${subreddit}:\nTITLE: ${title}\n---\n${selftext}\n---`);
    return { dryRun: true };
  }
  // 1. Password grant for an access token.
  const basic = Buffer.from(`${clientId}:${clientSecret}`).toString('base64');
  const tokRes = await fetch('https://www.reddit.com/api/v1/access_token', {
    method: 'POST',
    headers: {
      Authorization: `Basic ${basic}`,
      'Content-Type': 'application/x-www-form-urlencoded',
      'User-Agent': ua
    },
    body: `grant_type=password&username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`
  });
  if (!tokRes.ok) {
    console.error('[reddit] token request failed:', tokRes.status, await tokRes.text());
    return { ok: false };
  }
  const tok = (await tokRes.json()).access_token;
  // 2. Submit the post.
  const submit = await fetch('https://oauth.reddit.com/api/submit', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${tok}`,
      'Content-Type': 'application/x-www-form-urlencoded',
      'User-Agent': ua
    },
    body: new URLSearchParams({
      sr: subreddit,
      kind: 'self',
      title,
      text: selftext,
      api_type: 'json',
      sendreplies: 'true'
    }).toString()
  });
  const sj = await submit.json().catch(() => ({}));
  const errors = sj?.json?.errors || [];
  if (!submit.ok || errors.length) {
    console.error('[reddit] submit failed:', submit.status, JSON.stringify(sj).slice(0, 400));
    return { ok: false, errors };
  }
  const url = sj?.json?.data?.url;
  console.log('[reddit] posted:', url);
  return { ok: true, url };
}

// -------------------- main --------------------
(async () => {
  try {
    fs.mkdirSync(STATE_DIR, { recursive: true });

    // Primary path: post the next un-posted CONTENT-ENGINE piece from the queue
    // (rich, on-brand, image + ?src=x card link). The engine writes social/queue.json.
    const QUEUE = path.join(ROOT, 'social', 'queue.json');
    let queue = [];
    try { queue = JSON.parse(fs.readFileSync(QUEUE, 'utf8')); } catch (_) {}

    if (queue.length) {
      const today = todayUTC();
      const POSTED = path.join(STATE_DIR, 'posted-pieces.json');
      let posted = [];
      try { posted = JSON.parse(fs.readFileSync(POSTED, 'utf8')); } catch (_) {}
      const keyOf = e => `${e.eventId}::${e.pieceId}`;

      // Only cards that haven't happened yet; oldest card first, so we drip a
      // card's pieces across the days leading up to it.
      const pool = queue.filter(e => !e.eventDate || e.eventDate >= today);
      let pick = pool.find(e => !posted.includes(keyOf(e)));
      if (!pick && FORCE) pick = pool[0] || queue[0];
      if (!pick) {
        console.log('[social] no new engine piece to post (all queued pieces already posted). FORCE_POST=1 to repost.');
        return;
      }

      const imageAbs = pick.image ? path.join(ROOT, pick.image) : null;
      const haveImage = imageAbs && fs.existsSync(imageAbs);
      console.log(`[social] posting engine piece ${keyOf(pick)} (${pick.pillar}) for "${pick.eventName}"`);
      console.log(`[social] tweet (${pick.tweet.length} chars):\n${pick.tweet}`);
      console.log(haveImage ? `[social] image: ${pick.image}` : '[social] no image file → text-only.');

      // Reddit gets the same content as a profile self-post (no subreddit spam).
      const redditTitle = `${pick.eventName} — our model's read`;
      const [xRes, rRes] = await Promise.all([
        postToX(pick.tweet, haveImage ? imageAbs : null),
        postToReddit(redditTitle, pick.tweet),
      ]);

      const ok = xRes.ok || rRes.ok || xRes.dryRun || rRes.dryRun;
      if (ok && !DRY_RUN) {
        if (!posted.includes(keyOf(pick))) posted.push(keyOf(pick));
        fs.writeFileSync(POSTED, JSON.stringify(posted, null, 2) + '\n');
        console.log(`[social] marked posted: ${keyOf(pick)}`);
      }
      console.log('[social] done. x=' + JSON.stringify(xRes) + ' reddit=' + JSON.stringify(rRes));
      return;
    }

    // ---- Fallback: legacy per-card summary (only if no queue.json exists) ----
    console.log('[social] no queue.json — falling back to legacy card summary.');
    const t = todayUTC();
    const { data: events } = await sb
      .from('events').select('id, name, event_date, location')
      .eq('is_upcoming', true).gte('event_date', t)
      .order('event_date', { ascending: true }).limit(1);
    const event = events && events[0];
    if (!event) { console.log('[social] no upcoming events.'); return; }

    let lastPosted = '';
    try { lastPosted = fs.readFileSync(MARKER, 'utf8').trim(); } catch (_) {}
    if (!FORCE && lastPosted === String(event.id)) {
      console.log(`[social] event ${event.id} already posted (marker matches). use FORCE_POST=1 to re-post.`);
      return;
    }
    const post = await buildPost(event);
    if (!post) { console.log('[social] no verdicts yet for this card — skipping.'); return; }
    const [xRes, rRes] = await Promise.all([
      postToX(post.tweet),
      postToReddit(post.redditTitle, post.redditBody)
    ]);
    const anySucceeded = xRes.ok || rRes.ok || xRes.dryRun || rRes.dryRun;
    if (anySucceeded && !DRY_RUN) { fs.writeFileSync(MARKER, String(event.id) + '\n'); }
    console.log('[social] done (legacy). x=' + JSON.stringify(xRes) + ' reddit=' + JSON.stringify(rRes));
  } catch (err) {
    console.error('[social] failed:', err);
    process.exit(1);
  }
})();
