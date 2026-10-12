# 01 — Executive summary: Cannon Fight Lab, current state

Audit date: 2026-10-12. Independent, read-only audit of the `Cage-Metrics` repository (1,063 commits since 2026-04-26), the live Supabase database, the Railway services, and the GitHub Actions history. Nothing in the application was changed; the only writes are the nine reports in this directory. Every finding is tagged VERIFIED, INFERRED or UNKNOWN in the detailed reports (02–09).

## The project in plain English

Cannon Fight Lab started in April 2026 as a UFC stats site for bettors, became a picks product within three weeks, built six prediction models by the end of May, replaced them with a more careful Python engine in July, tested that engine honestly against the betting market in August and September, found it does not beat the market, and on 2026-09-21 removed every prediction from the public site. The same day it built a subscription system, a Free/Pro boundary, watchlists and email alerts for the repositioned "market-intelligence" product. None of that is switched on. Seven months in, there is no revenue, no price, no paying tier, eight registered accounts (none active in the last month), zero email subscribers, and a growing stream of search visitors who come for fighter stat pages and leave.

## What works (VERIFIED)

- **A free market-intelligence site that is coherent and tested.** Card Lab, Market Lab, Fight Lab and Factor Lab show the next card's vig-free consensus, best price, matched-cohort movement and per-book table with honest captions; the odds capture feeding them ran this morning and has priced 14 of 16 fights on the next card.
- **A clean odds time series since 2026-09-19**: 11,794 provenance-tagged quotes from 10 US sportsbooks, captured several times a day around cards. Small, but the one asset that improves with time.
- **An auditable pre-fight record** (106 append-only snapshots across 9 cards) with a working watchdog.
- **Strong engineering discipline**: 629 Python tests and 17 Node test files pass locally and on every push; policy-as-tests keep the model off the public pages; billing, alerts and entitlement logic are pure, tested modules.
- **Traffic is growing, but it is not human.** Session counts rose from ~10 a day in late September to 350–465 a day, yet 3,000 of the last 3,033 sessions carry no referrer, 7 viewed a second page, 4 lasted over a minute, and the hourly spread is flat around the clock. This is crawlers fetching the ~5,400 prerendered stubs. Human visits are on the order of 1–6 a day (corrected 2026-10-12; detail in `05_` §5).

## What does not work (VERIFIED)

- **The social poster still publishes model percentages.** Run log of 2026-10-09: a tweet with "BONFIM 50% over PRADO" went out to X. Three times a week, in CFL's name, the one channel that contradicts the positioning decided on 2026-09-21.
- **Two scrapers are dead or failing.** The fighter scraper's last successful deploy was 2026-05-22; 4,495 of 4,554 fighter profiles are five months stale and 2,222 have no division. Every deploy of the odds scraper since 2026-07-01 has failed on both of its Railway services.
- **Member features deliver nothing.** Alerts have no schedule and no mail key; the weekly Brief has no key, no subscribers, and reads a database column that no longer exists; Reddit posting has no credentials; the daily export fails on a missing secret and has never produced output.
- **The model still leaks onto the product in three places**: the most visited page (`fighter.html`) renders engine win/loss records and "fade candidate" wording; 14 of 75 SEO preview pages carry "Cannon Fight Lab's models pick X" in structured data; `event.html` titles say "UFC Predictions".
- **The research proved a negative.** Every honest model loses to the closing market by 0.014–0.044 log loss; the only ones that match it use the market as an input; the prospective record is 65 bets and zero protocol-grade CLV observations. No model supports a picks product or trading.
- **Operations fail silently.** The project's own history records seventeen silent breakages; this audit found four more red or wrong crons that nobody noticed. There is no observer outside GitHub.

## Commercial readiness

**Not ready, and no short path.** The checkout code is finished and could be switched on in one pull request once a Stripe account, a price and two legal pages exist — but there is nothing to sell: everything the specified Pro tier would withhold is either already free (alerts, watchlists, charts, book table) or not built (history, "since last visit"). The apparent audience is crawlers; a human audience of any kind has barely been observed. Detailed options are in `08_COMMERCIAL_READINESS.md`; the evidence supports stopping development, cleaning up the contradictions, keeping the free site and the odds capture running at near-zero cost, and running a cheap demand test before any further build.

## Top five blockers

1. **No demand signal and no customer definition** — 0 paying users, 0 active accounts, 0 subscribers, and the apparent traffic is crawler activity; human visits are a handful a day.
2. **Nothing to sell** — no price, no Stripe account, no Pro feature withheld; two legal pages (privacy naming Plausible, Terms) block checkout by the code's own design.
3. **Positioning is not true of the whole system** — the social poster, one product page and the preview stubs still publish the retired model.
4. **Operational fragility** — five repositories, three schedulers, two dead Railway services, one failing cron, no external observer, core schema not in git.
5. **Unexamined data licensing** — the stats product is scraped from UFCStats (which blocks the scrapers), odds come from a free API tier with no redistribution terms on file, and both are republished on 5,400 pages.

## Component counts

| class | count | examples |
|---|---|---|
| Production ready | 14 | Card Lab, Market Lab, Fight Lab, Factor Lab, event page, fighters index, cardio, Proof Center, accounts, watchlist UI, analytics, tests/CI, prerender pipeline, odds capture job |
| Functional but incomplete | 16 | fighter page (rule breach), parlay, My Book, pricing/Stripe (locked), entitlements (ungated), engine, snapshots and dead man, pre-fight record, CLV protocol, DUR experiments, event scraper, Supabase schema, edge functions, odds data layer, archive pages, documentation |
| Prototype | 4 | `lab.html`, cardio mixed model, `make-posting-app.js`, Discord alert |
| Broken | 7 | social poster (rule breach, live), preview JSON-LD leak, fighter scraper (dead), odds scraper deploys, `export.yml`, digest/social `open_p_a` reads, `h2h` as an unmanaged main landing page |
| Planned only | 6 | alerts delivery, Brief delivery, Free/Pro gating, Event Flow ingestion, CLV publication, Pro-only history |
| Unknown | 5 | four external repositories' internals, Odds API account/terms, Plausible traffic quality, costs, email-confirmation setting |

## Uncertainty and evidence limits

The live site could not be fetched from the audit container; rendered behaviour is judged from code and the repo's last live verification (2026-09-21). Plausible, Stripe, Supabase and Railway billing, The Odds API account, the X timeline and the four related repositories were not accessible. Costs are entirely unknown. Traffic source is unknown. The full list is in `09_EVIDENCE_AND_LIMITATIONS.md`.

## Reports

| file | content |
|---|---|
| `02_SYSTEM_ARCHITECTURE.md` | technical inventory, Mermaid data-flow diagram, job-by-job live status |
| `03_FEATURE_INVENTORY.md` | every user-facing feature, readiness, rule violations |
| `04_DATA_AND_MODELS.md` | verified record counts, ingestion status, integrity, every model and its evidence |
| `05_BUSINESS_AND_MONETIZATION.md` | revenue, payments, users, traffic, costs, what stops charging |
| `06_OPEN_ITEMS.md` | prioritised backlog with evidence and effort |
| `07_PROJECT_HISTORY.md` | timeline, pivots, abandoned work, fragmentation |
| `08_COMMERCIAL_READINESS.md` | the ten questions, ranked options, preserve/suspend/retire |
| `09_EVIDENCE_AND_LIMITATIONS.md` | what was inspected, what was not, what remains unverified |
