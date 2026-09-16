# SEO meta tags — per-page values

The block I added to `index.html` is the template. For each other page, replace these
values in the `<head>` (everything else stays identical).

## index.html (homepage)
```
<title>Cannon Fight Lab — UFC Fight Picks Locked and Graded in Public</title>
<meta name="description" content="Two honest UFC models: Fight IQ picks fights from tape alone, Value hunts prices worth taking. Every pick locked before the bell, graded in public, misses shown. Built on 8,853 analyzed fights.">
<link rel="canonical" href="https://cannonfightlab.com/">
<meta property="og:url" content="https://cannonfightlab.com/">
<meta property="og:title" content="Cannon Fight Lab — UFC Picks Locked & Graded in Public">
```

## card-lab.html (Card Lab — primary product page)
```
<title>Card Lab — Work the Next UFC Card in Minutes | Cannon Fight Lab</title>
<meta name="description" content="Every fight on the next UFC card ranked by model edge, confidence, and underdog value. Model probability vs the betting line, the factors behind each pick, and the red flags — one screen.">
<link rel="canonical" href="https://cannonfightlab.com/card-lab.html">
<meta property="og:url" content="https://cannonfightlab.com/card-lab.html">
<meta property="og:title" content="Card Lab — Work the Next UFC Card in Minutes">
<meta property="og:description" content="Every fight ranked by model edge, confidence, and dog value. Model vs market on one screen.">
```

## track-record.html (the summary record)
> **Timing and immutability wording is load-bearing here.** `model_picks` and
> `model_edges` are not append-only, and `source='live'` does not by itself
> prove a call preceded its fight. Do not reintroduce "locked before the bell",
> "never edited" or "every pick" — `tests/proof-copy.test.js` fails on all
> three. Per-row timing grades live on `proof.html`.

```
<title>UFC Model Track Record, Graded in Public — Cannon Fight Lab</title>
<meta name="description" content="Every main-engine fight call graded in public — simulated record labeled as simulated, live prospective record since July 2026, misses included. Accuracy, calibration, and profit at the prices on record.">
<link rel="canonical" href="https://cannonfightlab.com/track-record.html">
<meta property="og:url" content="https://cannonfightlab.com/track-record.html">
<meta property="og:title" content="UFC Model Track Record, Graded in Public — Cannon Fight Lab">
<meta property="og:description" content="Every main-engine fight call graded in public — simulated record labeled as simulated, live prospective record since July 2026, misses included.">
```

## proof.html (Proof Center — the row-level evidence layer)
> Scope wording is enforced: every description tag must say **main-engine**, and
> the page must stay `index, follow`. Both are covered by
> `tests/proof-copy.test.js`.

```
<title>Proof Center — The Main Engine's Fight Calls, Graded | Cannon Fight Lab</title>
<meta name="description" content="Every main-engine fight call in this record: when we posted it, what we said, what happened, and what $100 a bet came to. Live calls and history replays kept separate. Losses shown at the same size as wins.">
<link rel="canonical" href="https://cannonfightlab.com/proof.html">
<meta property="og:url" content="https://cannonfightlab.com/proof.html">
<meta property="og:title" content="Proof Center — Every Main-Engine Fight Call, Timestamped and Graded">
<meta property="og:description" content="Every main-engine fight call in this record: when we posted it, the price, the result, and what $100 a bet came to. Live and replayed records never mixed. Losses shown at the same size as wins.">
```

## cardio.html
```
<title>UFC Fighter Cardio Scores — Who Fades in the Late Rounds | Cannon Fight Lab</title>
<meta name="description" content="See which UFC fighters maintain output deep into fights and which ones fade. Cardio scores derived from per-round strike and takedown data, validated against 2,000+ historical fights.">
<link rel="canonical" href="https://cannonfightlab.com/cardio.html">
<meta property="og:url" content="https://cannonfightlab.com/cardio.html">
<meta property="og:title" content="UFC Fighter Cardio Scores — Cannon Fight Lab">
<meta property="og:description" content="Which UFC fighters fade late and which ones don't. Data-backed cardio scores for every fighter.">
```

## stats.html (The Factor Lab)
```
<title>The Factor Lab — Which UFC Stats Actually Predict Fights | Cannon Fight Lab</title>
<meta name="description" content="Which fighter stats predict UFC fights and which just repeat the betting line. Age is the only factor that holds up once the market is even — tested across 8,853 fights. Free.">
<link rel="canonical" href="https://cannonfightlab.com/stats.html">
<meta property="og:url" content="https://cannonfightlab.com/stats.html">
<meta property="og:title" content="The Factor Lab — Which UFC Stats Actually Predict Fights">
<meta property="og:description" content="Most stats just repeat the betting line. See which ones actually predict fights, tested across 8,853 fights.">
```

## h2h.html (Head-to-head)
```
<title>UFC Head-to-Head Comparison — Stat Matchup Tool | Cannon Fight Lab</title>
<meta name="description" content="Compare any two UFC fighters side-by-side. Records, cardio, striking, takedown defense, age, reach — full statistical breakdown for every matchup.">
<link rel="canonical" href="https://cannonfightlab.com/h2h.html">
<meta property="og:url" content="https://cannonfightlab.com/h2h.html">
<meta property="og:title" content="UFC Head-to-Head — Cannon Fight Lab">
<meta property="og:description" content="Side-by-side stats for any UFC fighter matchup.">
```

## fighters.html (roster)
```
<title>UFC Fighter Stats Database — Every Active Fighter | Cannon Fight Lab</title>
<meta name="description" content="Searchable database of every UFC fighter. Records, career stats, cardio scores, recent form.">
<link rel="canonical" href="https://cannonfightlab.com/fighters.html">
<meta property="og:url" content="https://cannonfightlab.com/fighters.html">
<meta property="og:title" content="UFC Fighter Database — Cannon Fight Lab">
<meta property="og:description" content="Every UFC fighter, searchable. Records, stats, cardio.">
```

## parlay.html
```
<title>UFC Parlay Builder — Smart Parlays Backed by Data | Cannon Fight Lab</title>
<meta name="description" content="Build UFC parlays with model-backed verdicts. See edge factors for every fight before you commit.">
<link rel="canonical" href="https://cannonfightlab.com/parlay.html">
<meta property="og:url" content="https://cannonfightlab.com/parlay.html">
<meta property="og:title" content="UFC Parlay Builder — Cannon Fight Lab">
<meta property="og:description" content="Build smart UFC parlays with data-backed model verdicts.">
```

## fighter.html (single fighter — dynamic)

This page renders different fighters via a query param. The default static title is fine
for SEO indexing, but the JS should ALSO update the `document.title` and the canonical URL
once the fighter loads. See "Dynamic SEO" section below.

```
<title>UFC Fighter Profile — Stats & Analytics | Cannon Fight Lab</title>
<meta name="description" content="UFC fighter profile with full stats: record, cardio score, striking, grappling, recent form, head-to-head matchups.">
<link rel="canonical" href="https://cannonfightlab.com/fighter.html">
<meta property="og:url" content="https://cannonfightlab.com/fighter.html">
<meta property="og:title" content="UFC Fighter Profile — Cannon Fight Lab">
```

## about.html
```
<title>About Cannon Fight Lab — How the UFC Prediction Model Works</title>
<meta name="description" content="Cannon Fight Lab is a UFC fight prediction platform. See how the model is calibrated, what edge factors it uses, and our transparent track record.">
<link rel="canonical" href="https://cannonfightlab.com/about.html">
<meta property="og:url" content="https://cannonfightlab.com/about.html">
<meta property="og:title" content="About — Cannon Fight Lab">
```

## contact.html, disclaimer.html
Same template. Lower priority for SEO. Just update title, description, and canonical.

---

## Dynamic SEO for fighter.html

For fighter detail pages, add this JavaScript after the fighter loads:

```js
function updateSEO(fighter) {
  // Update document title
  document.title = `${fighter.name} — UFC Fighter Stats & Analytics | Cannon Fight Lab`;

  // Update or create description meta
  let descTag = document.querySelector('meta[name="description"]');
  if (!descTag) {
    descTag = document.createElement('meta');
    descTag.setAttribute('name', 'description');
    document.head.appendChild(descTag);
  }
  const record = `${fighter.wins}-${fighter.losses}-${fighter.draws}`;
  descTag.setAttribute('content',
    `${fighter.name} UFC fighter stats: ${record} record, ${fighter.division} division. ` +
    `Career averages, cardio score, recent form, head-to-head matchups.`
  );

  // Update canonical URL
  const canonical = document.querySelector('link[rel="canonical"]');
  if (canonical) {
    canonical.setAttribute('href',
      `https://cannonfightlab.com/fighter.html?id=${fighter.id}`
    );
  }

  // Update OG tags
  const ogTitle = document.querySelector('meta[property="og:title"]');
  if (ogTitle) ogTitle.setAttribute('content', `${fighter.name} — UFC Fighter Stats`);
  const ogUrl = document.querySelector('meta[property="og:url"]');
  if (ogUrl) ogUrl.setAttribute('content',
    `https://cannonfightlab.com/fighter.html?id=${fighter.id}`
  );
}
```

Call `updateSEO(fighter)` right after the fighter data loads from Supabase. Modern Google
indexes JS-updated meta tags. Twitter and Facebook do NOT — for full social sharing of
fighter pages, you'd need pre-built static HTML per fighter (a build step). Defer that
until fighter SEO becomes a real traffic priority.
