// Manual draft: prints a Reddit post and an X post for the next UFC card, for
// a person to read, edit and post by hand. It posts nothing and needs no
// secrets (same publishable anon key as the rest of the site).
//
// It used to print a "Model pick / Confidence" table from model_picks. CFL
// stopped publishing a forecast in September 2026 (D-011), so this now prints
// exactly what the auto-poster would post — what the market has done to the
// card — by calling build/social-post.js::buildPost. One builder, so the
// manual draft and the automatic post cannot drift apart (T-039).
//
// Every line is still run through the forecast guard: if anything reads like a
// pick, the draft is refused rather than printed.
//
// Usage:
//   cd build && node draft-post.js              # next upcoming card
//   cd build && node draft-post.js --event=117  # one event id

const { createClient } = require('@supabase/supabase-js');
const { buildPost } = require('./social-post');
const { forecastClaim } = require('./social-copy-guard');

const SUPABASE_URL = 'https://uftancejftcryfvbggll.supabase.co';
const SUPABASE_KEY = 'sb_publishable_boJGOA1CFN-SF14HHFGUAw_YEEm0DU8';

const sb = createClient(SUPABASE_URL, SUPABASE_KEY, {
  auth: { persistSession: false, autoRefreshToken: false },
});

const todayUTC = () => new Date().toISOString().slice(0, 10);

async function findEvent() {
  const arg = process.argv.find(a => a.startsWith('--event='));
  let q = sb.from('events').select('id, name, event_date, location');
  if (arg) q = q.eq('id', +arg.split('=')[1]).limit(1);
  else q = q.eq('is_upcoming', true).gte('event_date', todayUTC()).order('event_date', { ascending: true }).limit(1);
  const { data, error } = await q;
  if (error) throw new Error(`events read failed: ${error.message}`);
  return data && data[0];
}

async function main() {
  const event = await findEvent();
  if (!event) { console.error('[draft-post] no upcoming event found.'); return 2; }

  const post = await buildPost(event);
  if (!post) {
    console.error(`[draft-post] "${event.name}" has no fight with a measured market move yet — nothing to draft.`);
    return 3;
  }
  const claim = forecastClaim(post.tweet) || forecastClaim(post.redditTitle) || forecastClaim(post.redditBody);
  if (claim) { console.error(`[draft-post] refusing: the draft reads as a forecast (${claim}).`); return 4; }

  process.stdout.write('=================== REDDIT ===================\n\n');
  process.stdout.write(`${post.redditTitle}\n\n${post.redditBody}\n`);
  process.stdout.write('\n\n=================== X ===================\n\n');
  process.stdout.write(`--- (${post.tweet.length} chars${post.tweet.length > 280 ? ' ⚠️ OVER 280' : ''}) ---\n${post.tweet}\n`);
  return 0;
}

main()
  .then(code => process.exit(code))
  .catch(err => { console.error('[draft-post] failed:', err); process.exit(1); });
