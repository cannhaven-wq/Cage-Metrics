# PR 2 — fight-week-v2: the product is the next card

Branch `fight-week-v2`, stacked on PR 1 (`revenue/trust-funnel-v1`). Open it against `revenue/trust-funnel-v1` first; retarget to `main` once PR 1 merges.

## What changed, in plain English

**The site is now built around the next UFC card, model vs market.**

1. **Event Hub** — every card that has a locked CFL forecast gets a real page at its existing `/e/…` address (this week: `/e/ufc-331-van-vs-pantoja-2-4433.html`). Title "[Event] Predictions, Odds & Model Analysis". Top: fights analyzed, big disagreements, odds last updated, "Predictions locked before results". Then a table of every fight — CFL %, vig-free market %, difference in points, a plain label (CFL higher / Market higher / Mostly agrees) — biggest disagreements, line movement since lock (live timestamped sportsbook quotes only), one Factor Lab finding, grading status. When the card settles the same URL is regenerated with results and stays as the permanent graded record. Nothing redirects or deletes a hub.
2. **Fight pages** — one per fight at `/preview/…` (the existing fight-page route). First screen: CFL % and market % for both fighters, the difference, one plain sentence, "A disagreement is not a proven betting edge." Then "Show the math" (exact probabilities, vig-free method, book count, timestamps, line movement, lock time, latest quote per book), then fighter stats framed as "why the model may see it differently", then links back to the hub and the rest of the card.
3. **Market Board** (`market-board.html`, new, in the nav) — Largest Disagreements, Price Watch (CFL probability, fair line, best posted price at a Tennessee-licensed book, "for comparison, not a recommendation"), Market Movement since lock. Offshore books feed the consensus but never get a link or a "best price" label. No affiliate data anywhere.
4. **Homepage** — hero is the next card ("[Event] — Model vs Market", button to the hub), then top 3 disagreements, what changed today, the Card Lab (kept, re-worded: Difference instead of Edge, "Disagreement" sort instead of "Value", no parlay strip), the CFL record split into Historical simulation / Live published record / Active experiments (VERIFIED claims from `data/claims.json` only), the Fight Week Brief block, then about/methodology. Falls back to the latest graded card when no upcoming card has a locked forecast.
5. **Fight Week Brief** — one signup block on the homepage, hub and fight pages, after the first useful content, no popups. Exact text as specified. Saves `source = "<page_type>:<block_id>"`. `send-digest.js` now has a pre-card email (Wednesday) and a post-card email (Monday, new cron) where the biggest miss gets exactly the same box as the biggest hit; stale odds are called stale; the sender refuses to send if a sportsbook name appears in the copy.
6. **Tracking** — Plausible events `event_hub_view`, `fight_preview_view`, `market_board_view`, `fight_expand`, `odds_view`, `book_click`, `email_cta_view`, `email_submit`, `email_success`, `email_error`, with `event_id` / `fight_id` props; `watchlist_add` is defined but has no trigger (there is no watchlist on the site). Card-to-card return rate: `sql/retention_return_rate.sql` over a new anonymous `hub_visits` ledger (see "decisions to confirm").
7. **SEO** — sitemap puts the current hub (1.0, hourly) and its fight pages (0.9) first, past hubs and their fight pages next, `market-board.html` added; RSS feed items point at hubs; hub ↔ fight ↔ Market Board all interlink; `event.html` links to the hub when one exists. No new fighter pages, no bios.

**Data layer (`fight_week_views.sql`, applied to the live DB):** `v_fight_locked_forecast` (the CFL number from the pre-fight snapshot, or the insert-only `model_picks` live row until the snapshot is taken — never recomputed at render), `v_fight_market_vigfree`, `v_fight_market_at_lock`, `v_fight_odds_latest_by_book`, `v_odds_books_sportsbooks`. `v_fight_odds_consensus` is untouched.

**Hard rules honoured:** nothing in `cfl_engine/`, `research/`, `prop_model_locks`, `pre_fight_snapshots` or the `fight_odds` ledger was touched; no new model, no threshold change; the words edge / lock / best bet / value bet do not appear in the new copy (only inside the mandated "not a proven betting edge" line and "locked before results"); RLS on the new table is INSERT-only for anon/authenticated with no read; Supabase no-op lock untouched; `?v=` bumped (`_shared.js?v=rd18`, `fight-week.*?v=fw1`).

## Decisions — approved by Reed 2026-09-16

- **Sportsbooks-only vig-free consensus** (not a wrapper over `v_fight_odds_consensus`, which double-counts CFL's synthetic row and counts Polymarket as a book): approved.
- **Tennessee-licensed book list**: now copied from the regulator's page — Caesars, Bally Bet, FanDuel, BetMGM, DraftKings, Fanatics, bet365, theScore Bet, Hard Rock Bet (BetRivers is not licensed). `books.js` records the source URL and check date (`TN_LIST_SOURCE`, `TN_LIST_CHECKED = 2026-09-16`) and the Market Board shows them.
- **`hub_visits` ledger**: approved with a defined retention — rows are deleted after **120 days** by `hub_visits_prune()` (service-role only, applied to the DB), run weekly by `.github/workflows/hub-visits-prune.yml`; the browser key rotates every 60 days. The table holds no email, IP, user agent, account id or fingerprint.
- **No `watchlist_add` trigger** until a watchlist ships: approved.
- **Fight pages / hubs from the locked forecast only**; **biggest miss beside biggest hit**: approved.
- **Fight pages stayed at `/preview/`** (`f/` is the fighter-stub namespace).

## Integration with PR #8 (`CFL_RESEARCH_STATE.md`)

PR #8 merged into `main` (`461abcd2`) after PR 1 and PR 2 were cut, which is why the file was absent from my tree. `origin/main` is now merged into `fight-week-v2` (only generated-stub conflicts, resolved by taking main's copies — CI regenerates them). On the combined tree:

- `tests/test_research_state.py`: **13 passed** with LF-normalised hashing (i.e. as CI sees it). On this Windows PC with `core.autocrlf=true` the raw run reports 22 hash failures on frozen files that are byte-identical to `main` in git — a CRLF checkout artifact, not a change to any frozen file (`git diff origin/main -- cfl_engine/ CFL_RESEARCH_STATE.md` is empty). Worth making the test normalise line endings (PR #8's file — not touched here).
- DUR-001 tripwire: 23 passed.

## Tests

- DUR-001 tripwire: `python -m pytest cfl_engine/dur001/test_dur001.py -q` → **23 passed** (before and after).
- Views: applied via `run_sql_mgmt.py`; spot-checked UFC 331 — 13 fights with locked forecasts (locked 2026-09-07 14:45 UTC), 5 sportsbooks in the vig-free number, 4 fights with a pre-lock quote.
- Prerender: `node build/prerender.js` → 11 hubs, 146 fight pages, legacy previews/cards untouched for cards without a record, sitemap 5,555 URLs. Generated files are not committed (CI regenerates on merge, as before).
- Signup block, real submit on the hub: row saved with `source = event_hub:after-table`; second submit → "already on the list" (23505 handled); test row deleted.
- `hub_visits`: one row written from the hub view; retention SQL runs (empty until a second card).
- Digest dry runs: pre-card (UFC 331) and post-card (Noche UFC, 7–6 with biggest hit and biggest miss side by side) render; text versions too.
- Browser: no console errors on homepage / hub / fight page / Market Board; no horizontal overflow at 375 px on any of the four.

## Screenshots

Desktop and mobile, in `docs/screenshots/fight-week-v2/`: `home-*`, `event-hub-*`, `fight-*`, `market-board-*`.

## Still blocked / not done

- **Sportsbook history is thin before Sep 15.** The Odds API cron was dead until it was restored in DUR-001, so past hubs show "—" for the market on most fights and "line movement since lock" only exists for fights the books priced early. This fixes itself from here on; nothing is back-filled by design.
- **Market at lock is often empty for the current card too**: CFL locked UFC 331 on Sep 7; sportsbooks posted most of the card on Sep 15. The pages say so rather than guess.
- **`watchlist_add`** has no trigger — there is no watchlist feature.
- **Two signup components now exist**: PR 1's `cfl-email-capture` (fighter pages, Proof Center, legacy previews) and this PR's `.fw-brief` (homepage, hub, fight pages). Both write to `email_subscribers`. Worth collapsing to one after both PRs land.
- **`fights.scheduled_rounds` says 3 for the UFC 331 main event** (a five-round title fight) — data quality in the scraper, not touched here.
- `gh` is not authenticated on this PC, so this PR has to be opened from the GitHub compare page.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
