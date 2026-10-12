# 08 — Commercial readiness assessment

Audit date: 2026-10-12. This section uses only evidence collected in reports 02–07. It does not propose a new product roadmap. Where a judgement is mine rather than a fact, it is labelled INFERRED.

## 1. The ten questions

**1. What exactly is Cannon Fight Lab today?**
A free, public, static website that shows UFC bettors the sportsbook market for the next card (vig-free consensus, best price, matched-cohort movement, per-book table), a fighter and event statistics database scraped from UFCStats, a market-controlled factor test, and a public archive of a retired prediction model with its graded record. Behind it: a Supabase database, a three-week-old clean odds time series, a Python research engine that still runs privately, a subscription system that is built and locked, and an unusually heavy governance layer. It has no customers, no revenue, no price, and no paid feature.

**2. What functionality is genuinely usable?**
VERIFIED usable today: Card Lab, Market Lab, Fight Lab, Factor Lab, event pages, fighter pages (with stale profiles), head-to-head, cardio, parlay calculator, Proof Center, accounts, watchlist star. The odds capture feeding the market pages is running on the current card. VERIFIED not usable: alerts (no schedule, no mail key), the weekly Brief (no key, no subscribers, dead column), checkout (locked), any Pro tier, Reddit posting, event-flow ingestion, the daily export. Contradicting the product: the X poster.

**3. Is there a clearly defined customer?**
No. The positioning document names "a UFC bettor with no stats background" and the boundary document names "a bettor-researcher who wants depth, history, monitoring". Nobody matching either description has been observed: 8 accounts, none active for a month, 0 subscribers, 14 return visits in three weeks, no interviews or feedback on record. The traffic that does exist (300–460 sessions a day, rising) is search visitors landing on individual fighter, head-to-head and event pages and leaving — a reference-site audience, not a market-intelligence audience.

**4. What specific problem does the existing product solve?**
For the observed audience: "what is this fighter's record and stats, and how do these two compare" — a question UFCStats, Tapology and Wikipedia also answer, with fresher data. For the intended audience: "what is the market saying about this card, has it moved, and where is the best price" — a real question, well answered on the four product pages, but one that odds-comparison sites, BestFightOdds and the sportsbooks' own apps also answer, usually with more books and live prices. CFL's stated differentiator (provenance, matched-cohort honesty, refusals named) is a methodological virtue that the observed audience has not shown it values.

**5. Would the current implementation support charging customers today?**
No. Technically the checkout, webhook and entitlement code are complete and tested, and could be switched on in one pull request once a Stripe account, a price and two legal pages exist. Commercially there is nothing to sell: everything a Pro tier would withhold is either free (alerts, watchlists, charts, book table) or unbuilt (history, "since last visit", advanced analytics), and the one feature members were promised — email alerts — cannot send. Charging today would be charging for a star icon.

**6. What is the closest existing feature to a commercially usable product?**
INFERRED: the **market data layer and its pages** — Market Lab plus Fight Lab, backed by the provenance-complete multi-book odds series captured since 2026-09-19 and the matched-cohort movement and alert views. It is the only part of the system where CFL has something others do not publish in the same form (timestamped, provenance-tagged, cohort-honest line history for UFC), the code is finished and tested, and a paid version (full history, per-book series, alerts) is already specified in `PRODUCT_BOUNDARY.md`. Its weaknesses are small data (four cards), a free-tier API that caps capture, unverified redistribution terms, and no evidence anyone wants to pay for it.

The runner-up is the **fighter and event statistics database**, because that is what traffic actually consumes — but it is a scraped derivative with no licence, a fighter table five months stale, and a market that is already served free by larger sites.

**7. What is the smallest amount of remaining work required to deliver something chargeable?**
If the owner decides to charge for the market layer (the only candidate with a built Pro boundary):

| step | who | size |
|---|---|---|
| Stop the social poster and scrub the three remaining model leaks (A-001, A-006, A-007) | Claude | half a day |
| Fix the fighter scraper deploy so profiles refresh (A-002) | owner/Claude, other repo | one day |
| Set `RESEND_*`, run the alert delivery test, enable the alerts cron, fix the dead `open_p_a` reads (T-074, T-073, A-005) | owner + Claude | one day |
| Privacy names Plausible; Terms page exists (T-054, T-048) | owner + lawyer | days to weeks, external |
| Price, Stripe account, secrets, test-mode run, checkout live (T-067, T-068, T-069, T-066) | owner + Claude | two days once legal is done |
| Gate the Pro rows: per-book table, full movement history, alerts quota (T-061) | Claude | two to three days |
| Build at least one Pro-only thing that is not currently free: historical lookback of past cards' market history (the data exists from 2026-09-19) | Claude | one week |

Roughly **two to three weeks of engineering plus the legal and account work**, with the explicit caveat that nothing in the evidence says a customer exists at the end of it. The engineering is not the long pole; the legal pages and the demand question are.

**8. What is the most serious technical obstacle?**
INFERRED: **operational fragility across five repositories and three schedulers with no observer.** Two Railway services have failed to deploy since July, one export cron has failed daily, an alert cron is off, and the social cron is doing the wrong thing — all green in the only dashboards the project reads, or red where nobody looks. The project's own history records seventeen silent breakages. Any paid promise (alerts, fresh prices, fresh profiles) depends on this plumbing, and it cannot be trusted unattended today. The close second is that **the core schema has no source of truth in this repository**, so the system cannot be rebuilt from git.

**9. What is the most serious business obstacle?**
**No evidence of demand for the thing that was built, and clear evidence of demand for something else.** After seven months there are zero paying users, zero active accounts, zero subscribers, and the traffic that is arriving wants a free stats reference, not market intelligence. The prediction product that might have had a market was tested honestly and failed to beat the market; the replacement product is methodologically careful but has not been shown to anyone who would pay for it. Underneath that sits an unexamined licensing position on both data sources.

**10. Which parts should be preserved, suspended, or retired?**

| preserve (running, cheap, or uniquely valuable) | suspend (keep code, stop spending attention) | retire (stop, archive, or delete) |
|---|---|---|
| `build/fetch-odds.js` capture and the provenance-tagged `fight_odds` series since 2026-09-19 — the only asset that appreciates with time | DUR-001/DUR-002 and CLV-001 — leave the daily locks running, stop amending protocols until there is a product that needs the answer | Social auto-poster and the whole `social/` pipeline — stop today; its only output contradicts the positioning |
| The matched-cohort market views, `market.js`, `market-chart.js`, and the four product pages | The `cfl_engine` win model — keep the daily private record (it costs nothing), stop research on beating the market; the artifacts already answer the question | Legacy v1–v6 nightly retraining in the odds-scraper repo; `lab.html`, `distanceEdges.js`, `research/validate.js`, `draft-post.js`, `make-posting-app.js` |
| Pre-fight snapshots and the dead man's handle | Stripe, entitlements and alerts code — finished, tested, dormant; switch on only behind a decision to sell | `export.yml` (or redirect it to a private store); the duplicate odds-scraper Railway service; the 16 scratch edge functions; 38 merged branches and 5 abandoned ones |
| The test suite and CI | `fight-week-v2`, SYM-002/003 (PR #53), the unmerged spec branches — close or merge, do not leave open | `h2h.html` as a separate surface — either make it the entry to Fight Lab or fold it |
| The event scraper (only writer of results that is actually running) | The coordination layer — keep STATE/DECISIONS as the record; stop the daily amendment cadence | Prop Board cron (`props-refresh.yml`) feeding an archived page; `mybook.html` per the 2026-08-19 decision |
| The prerender pipeline — it is the whole acquisition channel | | |

## 2. Options, ranked by remaining effort, risk, and evidence of demand

| option | additional effort | risk | evidence of demand | notes |
|---|---|---|---|---|
| **A. Stop development; keep the free site running as a reference and portfolio piece** | ~2 days to stop the social poster, scrub leaks, fix or retire the dead services, write one closing decision | low | n/a | Costs stay at hosting; the odds series keeps accruing for a later decision. The evidence supports this as the default. |
| **B. Serve the audience that is actually arriving: a fresh, fast UFC stats reference (fighter, h2h, event pages), free, ad- or affiliate-supported later** | fix fighter scraper; make h2h/fighter pages the product; remove market/model clutter; ~2 weeks | medium: licensing of scraped UFCStats data; large free incumbents; affiliate gated by T-049 | **the only observed demand**: ~3,000 reference-page sessions in 14 days and rising | Abandons the market-intelligence positioning that was decided three weeks ago. Monetisation path is affiliate or ads, not subscription, and both are L3. |
| **C. Finish the market-intelligence subscription as specified** | ~2–3 weeks engineering + legal + Stripe (question 7) + a Pro-only history feature | high: no observed demand; alerts untested in production; API free-tier cap; redistribution terms unknown; competitors with live prices | none: ~150 product-surface sessions in 3 weeks, 0 sign-ups, 0 subscribers | The cleanest engineering path and the weakest demand case. Would need a demand test (a waitlist with a price on it, or ten conversations) before the build. |
| **D. Sell or license the data layer (odds series, snapshots) rather than a consumer product** | resolve Odds API and UFCStats terms; apply immutability; seed the ledger; weeks of accumulation | high: terms may forbid it; dataset is three weeks old; buyers unknown | none | Not viable until the series is months old and the terms are known. Keep capturing. |
| **E. Return to a picks product** | — | — | — | Ruled out by the project's own evidence (`04_` Part B): no model beats the close, prospective sample is tiny, and the owner already decided (D-011). Reopening it would require new evidence, not more development. |

## 3. Assessment

The project is not commercially viable in its current form, and the evidence does not point to a short path that makes it so. What it has is: a working free product for an audience it has not found, a reference database for an audience it did not intend, a locked subscription for a tier that withholds nothing, research infrastructure that proved its own model does not beat the market, and operations that fail silently. What it lacks is any customer signal.

The disciplined choice this evidence supports is **Option A now** — stop the contradictions, stop the dead crons, keep the free site and the odds capture running at near-zero cost — followed by a **cheap demand test** before any further build: either put a price on the specified Pro tier and count waitlist signups from the existing traffic for a month, or talk to ten of the bettors the positioning describes. If neither produces buyers, Option B is the only path with observed demand, and it is a different business with its own licensing question. Option C should not be built on hope.

## 4. What this assessment could not establish

Plausible referrers (where the traffic comes from and whether it is human); whether any X follower engaged with the posts; the owner's costs and hours; The Odds API tier and terms; UFCStats' position on scraping; the state of the four external repos beyond Railway metadata; whether the eight accounts are real users. Each would sharpen, not reverse, the conclusions above.
