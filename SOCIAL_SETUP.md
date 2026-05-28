# Social media setup — X & Reddit

Step-by-step guide for creating the Cannon Fight Lab accounts on X (Twitter)
and Reddit, then wiring them into the auto-poster (`build/social-post.js` +
`.github/workflows/social-post.yml`). All steps are mobile-friendly.

**Brand decisions made:**
- Handle: `@CannonFightLab` (fallback `@cannonfightlab` or `@CFLpicks` if taken)
- Display name: `Cannon Fight Lab`
- Avatar: `apple-touch-icon.png` from this repo (180×180, ready to use)
- Voice: analytics-publication tone — never "lock", "smash play", "DM me",
  or any tout-service language. Calibrated, receipted, public.

## Profile copy (paste into both)

- **Display name:** `Cannon Fight Lab`
- **Bio (160 chars, fits both):**
  > Calibrated UFC predictions backed by real data. Cardio scores, edge
  > factors, public track record. Every pick locked before the bell.
  > cannonfightlab.com
- **Location:** `Tennessee`
- **Website:** `https://cannonfightlab.com`

---

## X / Twitter (~10 min)

### Account

1. **Sign up** — `x.com/i/flow/signup` → email + phone verify (mandatory).
   Username: `CannonFightLab`.
2. Add bio, avatar, location, website from the copy above.

### Developer API (required for auto-posting)

3. **Apply for developer access** —
   `developer.x.com/en/portal/petition/essential/basic-info` → "Hobbyist /
   Making a bot" → describe as *"Posting weekly UFC analytics summaries
   from my own site"*. Approval is usually instant.
4. **Create an app** — Developer Portal → Projects & Apps → "+ Add App" →
   name it `cfl-funnel`.
5. **Set permissions FIRST (critical order)** — App settings → "User
   authentication settings" → Edit → **Read and Write** → Type: "Web App"
   → Callback URL: `https://cannonfightlab.com` → Website URL:
   `https://cannonfightlab.com` → save.
   > Without Read+Write set BEFORE generating access tokens, posting fails
   > with "Your client app is not configured with the appropriate oauth1
   > app permissions for this endpoint." If you already generated tokens,
   > regenerate them after fixing permissions.
6. **Generate tokens** — "Keys and tokens" tab → copy each value into a
   safe place (you only see most of them once):
   - **API Key** → env var `X_API_KEY`
   - **API Key Secret** → `X_API_SECRET`
   - Click "Generate" under *Access Token and Secret*:
     - **Access Token** → `X_ACCESS_TOKEN`
     - **Access Token Secret** → `X_ACCESS_SECRET`

### Pinned intro tweet

```
🥊 Cannon Fight Lab — UFC predictions backed by real data, not vibes.

→ Cardio scores: who fades in deep waters
→ Edge factors: every verdict is auditable
→ Track record: every pick locked before the bell, never edited

Free during beta: cannonfightlab.com
```

Pin from the tweet's "..." menu → Pin to your profile.

---

## Reddit (~5 min)

### Account

1. **Sign up** — `reddit.com/register` → username `CannonFightLab` →
   verify email.
2. **Profile setup** — Reddit app → tap your avatar → Edit profile → add
   the bio + avatar from the copy above.

### Script app (required for auto-posting)

3. **Open** `reddit.com/prefs/apps` in your **mobile browser** (the Reddit
   app doesn't expose this page).
4. Scroll to the bottom → "are you a developer? create an app..." →
   fill in:
   - **name:** `cfl-funnel`
   - **type:** select `script` *(NOT "web app" — script type is the only
     one that supports the password grant we use)*
   - **description:** (leave blank)
   - **about url:** (leave blank)
   - **redirect uri:** `http://localhost:8080` (unused but required field)
   - tap "create app"
5. **Copy credentials** — the new app card shows:
   - The short string just under the app name (looks like `aBcD1234efGh`)
     → env var `REDDIT_CLIENT_ID`
   - The "secret" field → `REDDIT_CLIENT_SECRET`
6. **Account credentials** — already in your head:
   - Reddit username → `REDDIT_USERNAME`
   - Reddit password → `REDDIT_PASSWORD`

### Where to post

Leave `REDDIT_SUBREDDIT` **unset** initially. The poster defaults to
`u_CannonFightLab` — your own profile — which:
- Never needs karma
- Never gets removed by mods
- Still indexed by Google and shareable

Once the profile has 100+ karma from organic engagement, override
`REDDIT_SUBREDDIT` to `MMA`, `MMABetting`, or `ufc`. **Read each sub's
rules first**; r/MMA in particular shadow-removes self-promo. Safest
escalation path:

1. Months 0-1: post only to `u_CannonFightLab`.
2. Month 2: try `r/MMABetting` — explicitly allows public-track-record
   posts. Comment on others' threads for 2 weeks before posting your own.
3. Month 3+: consider `r/UFCDiscussion`, `r/SeriousMMA`. Skip `r/MMA`
   unless you've built relationships with mods.

### Reddit intro post (on your profile)

- **Title:** `Built a free UFC analytics site — cardio scores, edge factors, public track record`
- **Body:**
  ```
  Cannon Fight Lab is a free analytics tool I built for picking UFC fights.

  - Cardio score per fighter (R3+/R1 output ratio) so you know who fades
  - Every model verdict shows the edge factors that drove it — no black box
  - 8,000+ historical fights backtested; rolling accuracy posted publicly
  - Every weekly pick is locked before the bell, never retroactively edited

  Free during beta, no Discord, no DMs, no premium picks group.

  cannonfightlab.com

  Posting picks here each Wednesday before the card. Grading thread Sundays.
  ```

---

## Wiring the credentials in

You have **10 values** total after both setups (6 X + 4 Reddit). They go
in two places — both use the same names:

### 1. Claude Code environment

Open the Claude Code on-the-web environment settings for this environment
→ Environment variables section → add each. After this, every future
Claude Code session reads them from `process.env` automatically — no more
re-asking.

### 2. GitHub Actions secrets

Repo → Settings → Secrets and variables → Actions → New repository
secret → add each (same names). The scheduled `social-post.yml` workflow
references `${{ secrets.X_API_KEY }}` etc., so the Wednesday cron only
goes live once these exist.

| Env / secret name | Value source |
|---|---|
| `X_API_KEY` | X Dev Portal → app → Keys and tokens → "API Key" |
| `X_API_SECRET` | same screen → "API Key Secret" |
| `X_ACCESS_TOKEN` | same screen → "Access Token" (generated after Read+Write set) |
| `X_ACCESS_SECRET` | same screen → "Access Token Secret" |
| `REDDIT_CLIENT_ID` | reddit.com/prefs/apps → string under app name |
| `REDDIT_CLIENT_SECRET` | reddit.com/prefs/apps → "secret" field |
| `REDDIT_USERNAME` | your Reddit account username |
| `REDDIT_PASSWORD` | your Reddit account password |
| `REDDIT_SUBREDDIT` | *omit* until karma is built |

Until these exist, both platforms stay in graceful-skip mode — the
workflow runs on schedule, logs "secrets missing → skipping", exits 0.
Set them and the **next** Wednesday cron goes live.

## Verifying the wiring

Manual smoke-test from the Actions tab → "Social auto-poster" workflow
→ Run workflow → leave "dry_run" = `true` → Run.

In the logs you should see:
```
[social] posting for event <id>: <event name>
[social] tweet length: <NNN>
[x] dry-run, would post:
---
<the tweet>
---
[reddit] dry-run, would post to r/u_CannonFightLab:
TITLE: ...
---
<the body>
---
```

If a platform's secrets are missing it logs `[<platform>] secrets missing
→ skipping` instead. Once both look right, flip `dry_run` off for the
real post (or just wait for the cron).
