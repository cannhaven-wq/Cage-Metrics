# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-10-16 (c) — Card Lab: Compact List redesign (T-100, PR open, awaiting owner approval)

**From:** Claude
**To:** Owner
**Date:** 2026-10-16

- **Homepage opens on the card.** The card is now the compact list from the
  approved mockup: position, flags, names, best price each side, pro records,
  chevron. The main event is tagged; no co-main is named (no source says which
  bout it is). Card order / Reverse order, search and the market sorts (now a
  "Sort" menu) all work; "This card at a glance" moved below the list.
- **Section filter is honest.** Full card is the only live option; Prelims and
  Early prelims are drawn disabled, because the main card / prelims split is
  not in our data (T-096).
- **A row opens in place** into three panels — Tale of the Tape (flag wash,
  age, height, weight limit, reach, stance, country, pro and UFC record),
  Betting Odds (every sportsbook's latest price with its capture age; best
  price and market chance), Line Movement (chart; first broad capture vs now
  across the same books; last 24 h). Stacks on a phone in that order.
  Additional Analytics stays collapsed and gained fair price, range and the
  per-book first-capture detail.
- **Verified** in Chromium against production rows for UFC Fight Night:
  Buckley vs. Malott served through a local stub (the sandbox cannot reach
  Supabase): 126 checks on desktop and a 390 px phone. All JS tests and the
  Python suite pass; `card-lab-expand` and `card-lab-view` tests updated.
- **Deviations from the mockup:** no tabs inside the tape panel (all three
  panels are already visible); "Opening odds" is "First broad capture", in
  percent, because CFL has never seen a sportsbook opener; the chart is the
  existing single consensus line, not two American-odds lines; no sportsbook
  logos; weight is the division limit.

## Next action

1. **Owner:** review the T-100 pull request and its screenshots; reply
   "approved" to merge and deploy, or list changes.
2. **Owner (unchanged):** decide the T-096 running-order migration — it is
   what would make "Card order" the real running order and let the Prelims
   filters switch on.

## 2026-10-16 (b) — Fighter flags: the country they represent, checked per card (T-099)

**From:** Claude
**To:** Owner
**Date:** 2026-10-16

- T-098 is live (#84) with the flag-shape fix (#85). Owner rule recorded:
  site fixes the owner asks for ship in the same turn.
- Owner rule: a flag is the country a fighter **represents**. Fixed by hand
  (`country_src = 'manual'`): Malott → CA (UFC.com had a wrong US
  birthplace), Mahjoub → CA, Milosevic → RS, Yakhyaev → TR, Chopurov → RU,
  and 23 fighters who had no country. All 150 fighters on upcoming cards have
  a flag.
- New `flag-check.yml` (daily) + `build/check-fighter-flags.js`: Wikidata
  "country for sport", citizenship fallback, fighters on the next 14 days of
  cards only. Fills gaps, confirms matches, never overwrites; anything else
  goes into one rolling `flag-check` issue. 15 tests.

## Next action

1. **Owner:** when a `flag-check` issue opens, settle each fighter by setting
   their country by hand (`country_src = 'manual'`), or ask Claude to.
2. **Owner (unchanged):** decide the T-096 running-order migration.

## 2026-10-16 — Card Lab: every matchup expands in place (T-098, in review)

**From:** Claude
**To:** Owner
**Date:** 2026-10-16

- **Homepage card.** Each fight is now a compact preview (both names, the
  flag wash, both corners' best price, the book posting it and the market %).
  A click opens the detail **directly underneath**; several fights can be open
  at once, a second click (or "Collapse this fight") closes one, and nothing
  on the card navigates away. Card order, reverse order, search, the three
  sorts and the compact list all still work, and an opened fight stays open
  through every one of them. The compact-list rows expand in place too.
- **Opened fight shows, immediately:** a side-by-side tale of the tape
  (country, age, height, reach, division weight limit, stance, pro record, UFC
  record; a dot marks the bigger number, a dash means we do not hold it); both
  corners' best price + book, market chance, fair price and worst-to-best
  range; line movement from our first broad capture to now across the same
  books, plus the last 24 h; the per-sportsbook table with each book's
  earliest captured price and date; the existing movement chart.
- **Additional Analytics** is a collapsed section: the matchup notes and
  caveats that used to sit on every card, career striking and grappling rates
  (with the profile date), and the late-round score. It opens only on a click.
- Reuses `market.js`, `market-chart.js`, `fight-insights.js`, `fight-lab.js`.
  One small addition to `market.js`: `matchedNowProb`, the matched books'
  median now, so "from X% to Y%" never mixes two sets of books. No database
  change, no model, no subscription change.
- **Verified** in Chromium against production rows for UFC Fight Night:
  Buckley vs. Malott (13 bouts) served through a local stub — the sandbox
  cannot reach Supabase. 52 checks pass on desktop and a 390 px phone. All JS
  tests and 303 Python tests pass; `tests/card-lab-expand.test.js` is new.
- **Limits, stated on the page:** weigh-in weights are not in our data (the
  tape shows the division limit); CFL has never seen a sportsbook opener, so
  "earliest" means our first capture; the card order is still announcement
  order until the T-096 migration is applied.

## Next action

1. **Owner:** review the PR for T-098 and merge if the homepage reads right.
   After merge, check one fight opens on cannonfightlab.com.
2. **Owner (unchanged):** decide the T-096 running-order migration.

## 2026-10-15 (i) — T-097 deployed and verified live

**From:** Claude
**To:** Owner
**Date:** 2026-10-15

- PR #82 merged (`193e421`, owner-approved) and served by cannonfightlab.com:
  `index.html`, `fight.html`, `fight-overview.js`, `fight-workspace.js`,
  `fight-lab.js`, `market.js`, `_shared.js` byte-match `main`.
- Verified on the live site against production rows, desktop and 390 px
  phone: all 13 active bouts on UFC Fight Night: Buckley vs. Malott, full cards
  and compact list, search, three sorts, reverse order, remembered view, row
  links, both corners' best price, book and market %; Fight Lab overview for
  Buckley–Malott, Cerminara–Stiller (debut), Anheliger–Koslow (11.6 pt move)
  and Jourdain–Cuamba (no market). No overflow, no console errors, phone menu
  works.
- Two display fixes after verification: the compact list printed any move
  under 0.5 pts as "0.0 steady" (Cerminara–Stiller is 0.4); a fighter with one
  UFC fight was headed "Last 1 UFC fights".
- Seen, not touched (out of scope): every price on the card was captured
  ~25 hours before the check, so the page labels it stale.

## Next action

1. **Owner:** decide the T-096 running-order migration; until it is applied
   the card order is announcement order, labelled as such.
## 2026-10-15 (h) — Customer research platform: matchup overview and compact card (T-097)

**From:** Claude
**To:** Owner
**Date:** 2026-10-15

- **Fight Lab:** a "Matchup overview" now opens the page, above every
  existing section (all kept, in their order). Per fighter: age, height,
  reach, stance, records, streak, layoff, market consensus with best price
  and book; measured style; tendency lines from `fight-overview.js` (each
  states its number and sample, needs 3 UFC fights and 25 minutes, and a test
  forbids training-background words such as boxer or wrestler); last five with
  opponent, method and round; striking, strike distribution, grappling,
  control, late-round score, decisions and rounds reached. Rates come from
  `fight-workspace.js::careerWindow`, so the overview and the explorer agree.
- **Card Lab:** a "Full cards / Compact list" toggle. The list is the whole
  card on one screen, through the same order toggle, sort and search; each
  corner's best price and market % sit on the full cards too.
- **Verified** on real rows read from production (Buckley vs Malott,
  Volkanovski vs Evloev with no price yet, Cerminara vs Stiller with a
  debutant), desktop and phone, no horizontal scroll. The sandbox cannot
  reach Supabase, so the page ran against those rows through a local stub.
- **Not done, unchanged:** the official running order still needs the T-096
  migration; until then the order toggle says it is announcement order.
- **Pre-merge fixes (owner-approved deploy):** recorded finishing results
  ("3 of 3 UFC wins came by KO/TKO", "went to the judges") are no longer listed
  as tendencies. `tendencies()` returns them as `results`, shown under
  "Recorded results · how their UFC fights ended" with "a count of what
  happened, not a statistical tendency". The nine review screenshots were
  removed from the site tree (Pages serves the whole repo); they stay in
  commit `03994a3` and the PR body links them there.

## Next action

1. **Owner:** approved merge and deploy of the T-097 PR on 2026-10-15.
2. **Claude, after merge:** run `verify-live` and confirm the served
   `fight.html` and `fight-overview.js` match `main`.

---

## 2026-10-15 (g) — Event card sprint: search shipped, running order ready, three decisions (T-096)

**From:** Claude
**To:** Owner
**Date:** 2026-10-15

- **Investigated first, built nothing twice.** The running-order pipeline
  (`cfl_engine/event_flow/`) already exists, is tested, and has never run:
  its ledger table was never created and its one-time real-page check was
  never recorded. The PR reuses it rather than writing another reader.
- **In the PR:** search within the card on both card surfaces; "Bout N of M"
  labels, walkout-order sorting and "First bout first" wording, all behind
  `RUNNING_ORDER_LIVE = false` until the view exists; a proposed migration
  (`research/event-card/proposed_2026-10-15_card_running_order.sql`) that
  creates only the ledger and a select-only view, verified twice-applied on a
  throwaway Postgres; the plan with costs and risks.
- **Not shipped, and not faked:** card sections and start times. No source
  holds them. The odds provider's per-fight times are estimates.
- **T-095 closed** (merged `e103d4e`, verify-live green).

## Next action

1. **Owner:** decide the three items in
   `research/event-card/EVENT_CARD_PLAN_2026-10-15.md`. For the running
   order: apply the migration in the SQL editor, dispatch `event-flow.yml`
   as a dry run and read the printed order against the real card, commit
   `REAL_PAGE_CHECK.json`.
2. **Claude, after 1a:** flip `RUNNING_ORDER_LIVE`, add
   `v_card_running_order` to verify-live, run it.
3. **Owner:** merge the T-096 PR when ready; it is safe to merge before the
   migration (the reader stays off).

---

## 2026-10-15 (f) — Research platform audit and the first round of fixes (T-095)

**From:** Claude
**To:** Owner
**Date:** 2026-10-15

- **Audit:** [`research/data-integrity/T-095_RESEARCH_PLATFORM_AUDIT_2026-10-15.md`](../research/data-integrity/T-095_RESEARCH_PLATFORM_AUDIT_2026-10-15.md),
  measured against production; nothing written.
- **Three causes found:**
  - `fights.bout_order` has never been written, so "card order" is the
    order bouts were announced;
  - the profile scraper's 2026-07-01 deploy failed to build, so 68 of 150
    upcoming fighters' profiles miss at least one fight;
  - `fighters.age` lags birthdays (45 of 150).
- **Shipped in the PR, pages only:**
  - honest order wording and a direction toggle;
  - ages from date of birth;
  - opponent-change and debut badges;
  - Fight Lab rebuilt on the fight records, with division rank, strike
    mix, round by round, win/loss methods, opposition quality, Key points
    (fact / calculation / interpretation) and fight context.
- **Verified locally** at 1280 px and 390 px against real rows for the
  2026-10-17 card. The container cannot reach Supabase or the site.

## Next action

1. **Owner:** review the T-095 pull request; merge to deploy.
2. **Owner:** decide the three blocked items in the audit, section 3:
   - the event-flow migration (running order);
   - the profile-scraper redeploy;
   - a closing-odds view for historical odds.
3. **Claude:** after merge, run `verify-live`, then mark T-095 done.

---

## 2026-10-15 (e) — T-094 is live and verified

**From:** Claude
**To:** Owner
**Date:** 2026-10-15

- PR #77 merged as `d5c850c` with the owner's go-ahead; Pages deployed.
- `verify-live` run 38770578048 on `d5c850c`: all four jobs green. Served
  bytes match `main`, including `fight-workspace.js` and
  `fight-workspace-ui.js`; on live bouts the explorer shows six tabs with
  samples and the research sheet renders, at desktop and phone width, with no
  console errors and no pick language.

## Next action

1. **Owner:** watch the Card Lab → Fight Lab click-through on the 2026-10-17
   card (`fight_opened` with `from=card` in `v_funnel_daily`) to see whether
   visitors reach the workspace.
2. **Claude:** next customer-experience step, if approved: let a visitor share
   a read-only link to their research sheet (still no account, encoded in
   the URL), and add the explorer to `h2h.html` for any two fighters.

---

## 2026-10-15 (d) — Fight Lab research workspace (T-094, customer experience sprint 1)

**From:** Claude
**To:** Owner
**Date:** 2026-10-15

- **What a visitor can now do on `fight.html`:** explore the matchup by
  category with bars instead of a table; see career and last-5 figures side by
  side, each with its sample; open any metric for what it measures, whether
  the Factor Lab has tested it against winning, and the fight-by-fight rows
  behind it; and build a research sheet of the things *they* think matter,
  then copy, download or print it.
- **What it does not do:** rank fighters, add rows up, name a side, or show a
  CFL number. `tests/fight-workspace.test.js` checks the summary carries no
  tally and the copy carries no pick language.
- **Data:** `fight_rounds` (already public) for the last-5 rates;
  `factor-rates.json` for evidence. `fight_rounds_public_read.sql` records the
  existing grant so T-088's read check passes; **production already holds it,
  nothing to apply.**
- **Verified locally** against real rows for fight 46774 (Buckley vs Malott)
  at 1280 px and 390 px: no horizontal scroll, sheet survives a reload. The
  container cannot reach Supabase or the live site, so the post-merge check is
  `verify-live`.

## Next action

1. **Owner:** review and merge the T-094 pull request.
2. **Claude:** after merge, run `verify-live` and open a 2026-10-17 bout on the
   live site at phone and desktop width; then mark T-094 done.

---

## 2026-10-15 (c) — T-092 and T-093 live; T-091 approved but blocked by the tooling

**From:** Claude
**To:** Owner
**Date:** 2026-10-15

- **Applied with the owner's approval (D-029):**
  - **T-092:** the market view, verified at 11.3 ms per card;
  - **T-093:** three duplicate bookings flagged inactive; all odds, predictions
    and model predictions are retained.
- **Not applied: T-091.** The Supabase tool holds any SQL containing DELETE
  for a confirmation that never arrives. It was not bypassed.
- **PR #76 is merged into PR #73** (`31b6733`), so the reviewed SQL is what
  ships.
- **Scraper PRs #3 and #4 stay unmerged** until the functions exist.
- **The full rescan** is fenced by the watch pattern. Round counts still match
  the baseline: 0 rows missing, 0 changed.

## Next action

1. **Owner:** in the Supabase SQL editor, run `fight_rounds_replace_rpc.sql`
   from PR #73 (head `31b6733`), then merge PR #73.
2. **Claude:** confirm that both functions exist and that only `service_role`
   can execute them, then merge scraper PR #3 and then PR #4.
   - Neither merge starts a rescan.
   - The Weekly Scraper cron is redeployed and waits for 00:00 UTC.
3. **Claude:** set `REPAIR_MAX_FIGHTS` back to 60 so phase 5 repairs 7349 and
   classifies the 21. Then compare the round counts against
   `cfl_audit.fight_rounds_baseline_20261015`.

---

## 2026-10-15 (b) — Rescans fenced; T-091 reviewed; T-092 and T-093 ready for GO

**From:** Claude
**To:** Owner
**Date:** 2026-10-15

**Rescans.**
- The full rescan started by the PR #2 deploy (deployment `7e8e1204`) is still
  running. At 15:19 UTC it was on event 86 of 799.
- Round counts have not moved: 20,976 rows over 8,915 fights.
- Every round row and every fight row is copied to
  `cfl_audit.fight_rounds_baseline_20261015` and `cfl_audit.fights_baseline_20261015`.
  That schema is private and not exposed to the browser API.
- **A merge can no longer start a rescan.** Service `cage-metrics-event-scrapper`
  now has the Railway watch pattern `FULL_RESCAN_APPROVED`, so it only
  redeploys when a file of that name changes. To undo, clear the watch
  patterns.
- Phase 5 is still off (`REPAIR_MAX_FIGHTS=0`).

**T-091 review (PR #3 and its RPC).**
- Sound. PR #3 is already rebased onto `b977434`, and 19 scraper tests and 9
  SQL tests pass.
- I found two issues and fixed them on `claude/dreamy-wright-nludxq-rpc`, on
  top of `claude/pensive-fermi-d6pbi0-rounds-rpc`; 11 SQL tests pass:
  1. **A partial page still shrank a fight.** The function now refuses any set
     that is not exactly rounds 1..`end_round`. That shape holds for all 8,915
     fights that have rounds.
  2. **`(jsonb_populate_record(...)).*` called `nextval()` once per column**,
     37 times per row. It now uses one `LATERAL` call per row.
- A production rehearsal through the Supabase tool is impossible: it holds any
  statement containing DELETE. The local replica stands in.
- **Order:** apply the RPC, then merge PR #3, then merge PR #4. Neither merge
  starts a rescan now.

**T-092 and T-093.** The proposals, evidence and GO recommendations are in the
TASK_QUEUE rows.

**Card Brief test row.** Row 26 is unsubscribed through `unsubscribe_email`,
the email link's own path, so no send can reach it. Removing the row still
needs a DELETE, which the Supabase tool holds for confirmation.

## Next action

**Owner:**
1. GO or NO-GO on `market_movement_t092.sql`.
2. GO or NO-GO on `dead_bookings_t093.sql`.
3. GO or NO-GO on the T-091 RPC, `fight_rounds_replace_rpc.sql` with the
   review fixes.
4. Delete row 26 with `delete from email_subscribers where id = 26;`.

**Claude, after each GO:** run verify-live, compare round counts against the
baseline, and drop `cfl_audit.v_mm_candidate`.

---

## 2026-10-15 — T-086 and T-088 live, PRs #69 and #71 merged; round gaps traced; market view too slow (T-092)

**From:** Claude
**To:** Owner / ChatGPT
**Date:** 2026-10-15

**Production state re-verified, read-only ([D-028](DECISIONS.md)).** The three
migrations ChatGPT applied this morning are listed by production as
`20261015141652` (`t086_dwcs_non_ufc`), `20261015142345`
(`t088_least_privilege`) and `20261015142358`
(`t088_pre_fight_truncate_guard`). Every result in the brief still holds. **None
was re-run, and no workflow applies SQL.**

**PR #69 (T-086 website) merged as `000fcd2`.**
- The only conflict was `sitemap.xml`. The resolution kept DWCS 10.3 out.
- 739 Python tests and every Node test pass, and CI was green.

**PR #71 merged as `87feffd`.**
- Both branches had written a **D-026**. Main's (T-086) kept the number.
  PR #71's T-088 decision became **D-027**, with every citation updated.
- 745 Python tests pass, and CI was green.
- Production grants match the intended end state: 13 attacks denied, 8
  legitimate actions allowed.
- A real Card Brief insert as `anon` succeeded in a rolled-back transaction and
  left no row.
- Marketing email stays locked: `MARKETING_SEND_BLOCKERS` forces dry-run.

**Live verification.** Agent sessions cannot reach `cannonfightlab.com`, so
`verify-live.yml` gained a **Stabilization checks** job. It checks:
- that the DWCS page says "Not a UFC event";
- that the old stub is noindex and the sitemap leaves it out;
- that each product page loads with its nav and no script error;
- optionally, a real Card Brief submission from an `@example.invalid` address,
  made twice so the repeat-address path is tested as well.

Run 38753407231 passed every one of those checks, including both Card Brief
submissions.
- **Not yet removed:** the test row it wrote, `email_subscribers.id = 26`
  (`cfl-live-verify-2026-10-15@example.invalid`). The Supabase tool held the
  DELETE for a confirmation that never arrived. The address cannot receive
  mail, and marketing sends are locked.

**T-092, found by the same run.** Fight Lab's own check failed:
`v_fight_market_movement` returned HTTP 500, from statement timeouts, while
three browsers loaded the site at once.
- The view takes 5.6 s for one card against an 8 s limit, because it
  recomputes the whole odds history on every request.
- Today's migrations did not cause it: all 48 reads in the previous 24 h
  succeeded, including after them.
- **Mitigated in this PR.** `market.js` retries once. If that also fails, Card
  Lab, Fight Lab and Market Lab say "prices didn't load" instead of
  wrongly saying "no price captured".
- **The real fix is a view rewrite, which is L3.** See T-092.

**T-093, missing round records: an audit of 25 fights, which feeds T-091.**
This reconciles with the parallel session's T-091 (RPC round writes, event-scraper
PR #3, not merged).
- **1 scraper loss:** 7349, the 2026-10-14 rescan failure. T-091 restores it.
- **3 duplicate bookings, not missing data.** 43, 46 and 8780 are the same
  bouts as 27872, 27877 and 27879 on the same card. **They inflate six public
  UFC records**: Vera reads 2-0 and Zhu 0-2 from one bout. Retiring them is a
  production delete: L3, owner, precedent D-024.
- **21 from 1994–98 hold no statistic of any kind.** That is probably a source
  limitation, unconfirmed because UFCStats is unreachable from agent sessions.
- **Event-scraper PR #2 is merged as `b977434`.** Rounds are upserted before
  anything is pruned, fetches retry, a finished fight with no rounds is logged,
  and a new phase 5 handles repair. **PR #3 must rebase onto it.**
- **Merging PR #2 started a full `events_scraper.py` rescan at 14:34 UTC**
  (that service rescans on every deploy). This ran against the owner's hold,
  which I learned of from PR #72 only afterwards. Railway's tools cannot stop
  a single deployment.
  - Baseline at 14:52 UTC: 20,976 rounds over 8,915 fights, and 25 completed
    fights without rounds. Compare against it when the run finishes.
- **Phase 5 is OFF** (`REPAIR_MAX_FIGHTS=0` on *Weekly Scraper*, 14:53 UTC), so
  tonight's cron repairs nothing. PR #4 (open, not merged) makes phase 5 skip
  duplicates. Merging it redeploys, which means another full rescan.
- Downstream views inner-join `fight_rounds`, so a missing fight is left out,
  never counted as zero.
- Evidence: `research/data-integrity/T-093_MISSING_ROUND_RECORDS_2026-10-15.md`.

**Remaining limitations, none of them a regression:**
- Security Advisor still lists the following, all of them pre-existing:
  - 39 definer views. This is how the browser reads odds by design, and the
    task said not to redesign them.
  - 9 functions with no fixed search path.
  - 8 definer functions that any role can run.
  - Leaked-password protection is off. That is a one-click dashboard setting
    for the owner.
- `v_funnel_daily` and `v_traffic_daily` (daily visit counts) can be read by
  the browser. The legacy engine record is public on purpose: the Proof Center
  grades it in the open (D-011). The PRED-001 and prop locks and
  `billing_events` are unreadable from a browser, as checked today.
- Default privileges for objects created by `supabase_admin` still open to
  browser roles. Only Supabase controls those. Objects we create as `postgres`
  are private by default.

## Next action

1. **Owner, now:** decide whether to let the running full rescan finish or to
   stop it from the Railway dashboard (service `cage-metrics-event-scrapper`,
   deployment `7e8e1204`). Whoever checks it next compares the round counts
   against the 14:52 baseline.
   **Owner, T-093 (L3):** approve retiring duplicate fights 43, 46 and 8780.
2. **Owner, T-092 (L3):** approve rewriting `v_fight_market_movement` so it
   reads only the requested card's fights. The output must be proven identical
   to today's before it is applied. Until then, the retry in `market.js` is
   the only protection, and fight week is the heaviest load.
3. **Owner:** delete the verification row with
   `delete from email_subscribers where id = 26;`, and turn on
   leaked-password protection (Supabase → Auth → Password security).
4. Then the next phase, customer experience and revenue. T-090 (double opt-in)
   comes before any Card Brief is sent.

---

## 2026-10-15 — T-086 is live and verified; scraper round-data integrity is next

**From:** Claude
**To:** Owner
**Date:** 2026-10-15

**T-086 is done.** On 2026-10-14 Claude's own attempt to run the migration timed
out in the Supabase tool. Nothing reached the database, and that was verified.
The reviewed migration file was then applied on 2026-10-15 at 14:16:52 UTC.
Claude verified the result independently afterwards:

- **The moved rows are byte-identical to the originals.**
  - fights `c214474a…`, rounds `061a9bf9…`, event `385f53c7…`;
  - the migration's own stored fingerprints agree.
- **Structure is as tested:** 14 constraints, 16 indexes, RLS on, SELECT only
  for the browser roles, and ids taken from the UFC sequences.
- **The guard is validated:** `non_ufc_card_in_events` reads 0 and 800 events
  remain.
- **Frozen research is as expected:**
  - H1 is 710 / 63 with all four hashes intact;
  - RESERVE re-derives to 164, matching the D-026 correction;
  - the security advisor is unchanged.
- **The site:** PR #69 is merged and the prerender regenerated with the new code.
  The DWCS stub is noindex and the sitemap lists 800 event stubs.
- **Live check:** `verify-live` is green on 53618 / 46774 / 53620. Galanti reads
  "No UFC fights yet" on desktop and phone.

## Next action

Claude: the scraper round-data integrity task, as the owner asked on 2026-10-14.
1. Make the round replacement a single database transaction (an RPC).
2. Add retries, a check that the expected number of rows was written, and a
   non-zero exit when a round write fails.
3. Investigate and restore fight 7349's rounds.
4. Audit the other 25 completed fights that have no rounds.

No full rescan is scheduled until that lands. The RPC is a database change and
goes to the owner first.

---

## 2026-10-14 (k) — T-088 revised and rehearsed on production; nothing applied

**From:** Claude
**To:** Owner
**Date:** 2026-10-14

**PR #71 reconciled.** `main` merged in (D-025, T-084/T-085), keeping both
handoff entries. 275 tests passed on the merged tree.

**T-088 revised to the owner's review ([D-027](DECISIONS.md)).**
- **New tables, views and sequences are private by default.** Existing reads
  are unchanged, and the migration proves it before committing.
- **A new test keeps future grants honest.** It fails if a page reads an object
  that no repo SQL grants. The 16 reads granted only in production are frozen
  as a named legacy list.
- **`hub_visits`:** browser access revoked, table kept.

**Rehearsed twice, nothing applied.**
- **Replica**, re-captured from production and byte-identical for tables,
  policies and grants: 50 probes, 31 legitimate actions unchanged, every attack
  denied, idempotent, and the assertion block catches mutations.
- **Production, rolled back** (`lock_timeout` 3 s on every run):
  - the assertion passes in 0.1 s against every real view;
  - 49 of 50 probes match the replica, and the 50th was a broken probe,
    re-checked correctly (`hub_visits` anonymous insert: allowed today, denied
    under the migration);
  - the guard refuses an owner TRUNCATE;
  - the before/after fingerprint is identical.
- **Two Supabase tool limits found and worked around:** a `service_role`
  TRUNCATE, and a two-statement `EXECUTE`, both hang `execute_sql`. Details
  are in the audit.

**Card Brief.** The signup fix (T-089) ships with #71. No Brief can be emailed
until double opt-in exists: `MARKETING_SEND_BLOCKERS` in `build/send-digest.js`
(T-090) locks it.

## Next action

Owner:
1. Sign off on the production rehearsal results in the T-088 audit.
2. Merge #71 once its CI is green.

On sign-off, Claude applies both T-088 files, re-runs the production probe and
the advisor, and submits the Card Brief form on the live site. Commercial
readiness then resumes at week 1, which starts with a Resend key, and T-090
before any Brief is sent.

---

## 2026-10-13 (i) — T-086 approved with gates (D-026); nothing applied yet

**From:** Claude
**To:** Owner
**Date:** 2026-10-13

The DWCS 10.3 move is fully built and tested. Nothing has been applied.

- **Plan:** `research/data-integrity/T-086_MIGRATION_PLAN_2026-10-13.md`.
- **Migration and rollback:** one transaction each, demonstrated on a
  throwaway Postgres (13 tests, including a full round trip that is
  byte-identical).
- **Scraper guard:** cage-metrics-event-scrapper `claude/pensive-fermi-d6pbi0`.
- **Found while checking frozen data:**
  - PRED-001 RESERVE's recorded 169 includes the 5 bouts.
  - Saturday's PROP-0001 locks for Galanti counted his Contender Series bout.
  - "UFC - Road to UFC 4.6" sits in the sealed H1 set and is left alone.

## Next action

**Approved 2026-10-13 ([D-026](DECISIONS.md)), with gates.** Claude:
1. Get PR #69 green.
2. Merge and verify event-scraper PR #1.
3. Recheck fingerprints, foreign-key references and rollback preconditions.
4. **Report readiness to the owner before applying the destructive step.**

The RESERVE correction and the PROP-0001 sensitivity rule for 53618 are
recorded in `research/data-integrity/T-086_RESEARCH_CORRECTIONS_2026-10-13.md`.

---

## 2026-10-13 (j) — T-084 and T-085 are live and verified

**From:** Claude
**To:** Owner
**Date:** 2026-10-13

Deployed database-first, as the runbook says. PR #66 was conditionally
approved; it was merged once both views were live and checked.

1. **T-085 applied.**
   - The chart output is identical for 26712 (891 points), 46774 and 53620.
   - One fight takes 0.26 s instead of 5.8 s.
   - On the live site the chart now appears 190 ms after the page (it was
     about 2,200).
2. **T-084 view applied.**
   - Read as `anon`, the five reference records match UFCStats.
   - security_invoker; SELECT only for both browser roles; PUBLIC revoked.
   - The advisor is unchanged (39 / 10 / 0 / 8 + 8 / 9 / 1).
3. **PR #66 merged** (`1984d35`). `verify-live` passes all three jobs on
   fights 46774, 53620 and 53618.

**The T-087 lockdown is intact.** Both changed views read
`anon=r, authenticated=r` and nothing else.

**One CI incident, not a test failure.** Tests on `main` at `1984d35` stopped
in the setup fetch: the prerender bot pushed seconds later, and a shallow
`git fetch` rejected the newer `main` as non-fast-forward. Reproduced locally;
fixed by this PR's `+` refspec.

## Next action

Claude: T-086 readiness. The gates are D-026's; report readiness before the
destructive step.

---

## 2026-10-13 (g) — T-084 built, T-085 cause found, T-086 plan written; nothing applied

**From:** Claude
**To:** Owner
**Date:** 2026-10-13

- **T-084: built.** `v_fighter_ufc_record` plus `ufc-record.js` on every
  record-showing page and the `/f/` prerender. It was tested on a throwaway
  Postgres (accuracy, retired bookings, permissions, re-run, and parity with
  Fight Lab's own count) and against production through a temporary view
  (records match UFCStats; 0.4 ms for one fighter). The migration is not
  applied.
- **T-085: cause found.** The `cohort` CTE was materialised, so every fight's
  cohort was built before filtering. `NOT MATERIALIZED` takes one fight from
  5.8 s to 0.26 s with byte-identical output on 8 fights. Not applied.
- **T-086: plan only.** `is_active = false` would miss 33 of the 34 views.
  The recommendation is an `events.promotion` column, moving the 5 non-UFC
  bouts (same ids) into sibling tables, and a scraper guard. This is an L3
  decision because it removes rows from `fights`.

## Next action

Owner:
1. Merge the read-only audit PR (#65).
2. Approve opening the T-084/T-085 PR.
3. Decide on the T-086 plan.

**Order of application for T-084:** apply the view first, then deploy the pages.
Pages that load before the view exists show "—" instead of a record.

---

## 2026-10-13 (g′) — Sportsbook data is read-only to the browser (T-087)

**From:** Claude
**To:** Owner
**Date:** 2026-10-13

**Applied to production on the owner's approval.** Before this, anyone with the
site's public key could add, change or delete rows in two odds tables
(`odds_aliases`, `unmatched_odds`: RLS off, full grants), and the browser roles
held TRUNCATE — which ignores RLS — on `fight_odds` and `odds_books`.

- **Migration:** `odds_write_lockdown_migration.sql`. Privileges only: no row,
  policy, view body or RLS flag changed. It asserts its own result and rolls
  back if a browser role can still write or has lost a read.
- **Verified as `anon` and as `authenticated`:** 15 write attempts (insert,
  update, delete on the four tables and the auto-updatable
  `v_odds_books_sportsbooks`) and every sequence call denied; the market views
  the site reads still return rows; `fight_odds`/`odds_books` still return 0 rows
  to browser roles, as before. Row counts identical before and after
  (126,972 / 14 / 0 / 11).
- **Writers unaffected:** `build/fetch-odds.js` and
  `cage-metrics-odds-scrapper` (`odds_scraper.py`, `diagnose_unmatched.py`) use
  the service-role key.
- **Advisor:** both `rls_disabled_in_public` ERRORs are gone. The definer-view,
  search-path, definer-function and leaked-password findings are unchanged and
  pre-date this.
- **Regression test:** `tests/odds-write-lockdown.test.js`.

**Not fixed, deliberately (T-088):** about 25 other tables, including
`pre_fight_snapshots`, `profiles` and `user_bets`, carry the same default grant
behind RLS. It cannot be reached today, but the default privileges in `public`
still make every new table writable to both browser roles.

## Next action

Claude: T-088 — the same revoke-and-assert for `pre_fight_snapshots` first (it
is the append-only record, and its triggers stop UPDATE and DELETE but a
TRUNCATE grant is still a grant), then the user tables, then propose the
default-privilege change for review.

---

## 2026-10-13 (h) — Sportsbook list write hole closed on production

**From:** Claude
**To:** Owner
**Date:** 2026-10-13

While checking the T-084/T-085 runbook, Claude found that browsers could write
`odds_books` through the definer view `v_odds_books_sportsbooks`. A delete
there would have cascaded to every captured price from that book. On the
owner's instruction the fix was applied to production the same day and
verified ([D-025](DECISIONS.md)). This PR is the record: the migration file and
the test that reproduces the hole and proves it is closed.

**Reconciled with T-087 (cannhaven-wq/Cage-Metrics#68, below).** T-087 was
applied minutes later and covers this view plus every other odds relation and
sequence. The two agree: both leave `anon` and `authenticated` with SELECT only
on `v_odds_books_sportsbooks`, and nothing for `PUBLIC`. D-025 records the one
hole found and its reproduction; T-087 is the lockdown standard.
`tests/odds-write-lockdown.test.js` also scans this PR's SQL file.

## Next action

Owner: merge this PR (it changes no page, and nothing in the database that is
not already applied). Claude: T-086, then T-088 security hardening and
commercial readiness.

---

## 2026-10-13 (f) — Fight Lab is live; T-083 answered; two production discrepancies

**From:** Claude
**To:** Owner
**Date:** 2026-10-13

**Fight Lab is live.** cannhaven-wq/Cage-Metrics#64 was merged at the verified
commit (`bbcbbb9`), and Pages deployed it.
- **Deployment:** the `verify-live` workflow confirms the site serves the
  checked-out files.
- **Live check:** a new Fight Lab job in that workflow opened three active
  2026-10-17 bookings in Chromium at 1440 and 390 px against the production
  database. All checks passed with no console errors.
  - Buckley vs Malott: 7 books.
  - Cerminara vs Stiller: no prices, and a debutant.
  - Mahjoub vs Faglier: priced, two debutants.

**T-083: the `fights` table is right, with one exception.** It was checked
against UFCStats for 74 fighters and agrees for 73.

The exception is the Contender Series card "DWCS 10.3" (2026-08-25, 5 bouts),
which is stored as a UFC event. Because of it, Nicholas Galanti (2026-10-17
card) shows on Fight Lab as UFC 1-0 instead of a debut (T-086). `fighters.ufc_wins/losses/draws`
agrees for 13 of 74. The full write-up is in
`research/data-integrity/T-083_UFC_RECORDS_2026-10-13.md`.

**Production discrepancies, both pre-dating T-080:**

1. **The wrong UFC record is still shown** on `fighters.html`, `event.html`,
   `h2h.html`, `cardio.html` and the `/f/` stubs (T-084).
2. **The movement chart's series view takes ~3.3 s per fight** (T-085).

**Tooling on `claude/pensive-fermi-d6pbi0`, not yet in a pull request:**
- `.github/scripts/verify-fight-lab.js` and the `fight-lab` job in
  `verify-live.yml`;
- `research/data-integrity/reconcile_ufc_records.py` with its manual workflow.

## Next action

Owner:
- **T-086:** approve retiring the 5 DWCS 10.3 bouts with
  `is_active = false`. It is reversible and is the D-024 path. It should
  happen before Saturday, because Galanti is on the card.
- **T-084:** approve the fix, and say whether a `v_fighter_ufc_record` view is
  acceptable (a database change) or it should be done per page.
- **Tooling:** say whether to open the pull request for it.

After that, return to the revenue-first queue.

---

## 2026-10-13 (e) — Fight Lab Phase 1: one page for one matchup (T-080, in review)

**From:** Claude
**To:** Owner
**Date:** 2026-10-13

Owner-approved product direction: Fight Lab is the heart of CFL. Phase 1 is
built on `claude/pensive-fermi-d6pbi0` and is **not merged**. It waits for review.

`fight.html` now answers three questions in order. A row of jump links sits under
the title.

1. **Who are these fighters?** One card per corner: pro and UFC record, age,
   stance, country, the style label (`v_fighter_style`, this bout's division
   first and career second, with the fight count and a small-sample flag), and
   the last five results as W/L chips, newest first.
2. **How do they compare?**
   - **Tale of the tape** is regrouped into physical / record / striking /
     grappling, with both names pinned above the columns. On a phone the label
     moves above the pair, so each number gets half the screen. A debutant's
     rates read "no UFC data" rather than 0.
   - **Late-round performance** is side by side (`v_fighter_consistency`). Each
     card shows the plain label, the figure, the sample (solid / thin), how many
     recent fights reached round three, and the late minutes behind it. It is
     never called cardio or fatigue, and the caveat says output is not
     tiredness and does not pick winners.
   - **Last five fights** lists each fight with the opponent, method, round,
     date and card.
   - **What stands out** carries the existing matchup notes, unchanged.
3. **What does the betting market say?** Consensus, chart and every-book
   table, unchanged and now below the research.

The rules live in a new pure module, `fight-lab.js`, tested by
`tests/fight-lab.test.js` (19 tests). There is no database change. The labels
"Takedowns per 15 min" and "Submission tries per 15 min" now say what UFCStats
actually measures.

**Tested** in Chromium at 1366 px and 390 px on two real 2026-10-17 bookings:
Buckley vs Malott (full data, 7 books) and Mahjoub vs Sutherland (a debutant
with no prices, an empty-state check). This container's network policy blocks
Supabase, so the page ran against real rows read through the Supabase MCP and
replayed to the browser. That is not the deployed site. Mahjoub vs Sutherland
is one of the bookings retired by D-024; it was used only because it exercises
every empty state.

**Two findings.**

- The per-fight strike breakdown by target and position is **already stored**
  (`fights.*_head/_leg/_clinch…_landed`, 8,921 of 8,945 completed fights). Phase
  3 style labels need no scraper expansion. T-082 is re-scoped to say so.
- `fighters.ufc_wins/ufc_losses` is stale for at least one fighter (T-083).

**Review corrections (same day, owner review of PR #64).**

1. **No contradictory UFC record.** The record is now counted from the same
   completed `fights` rows the page lists. `fighters.ufc_wins/ufc_losses` is
   no longer printed. A pro record smaller than the counted UFC record reads
   "not up to date". A failed history read says so instead of "no fights".
2. **The late-round figure is a score, not a percentage.** The note now says
   what the view computes: a weighted blend of up to four capped
   late-vs-round-one ratios. "Solid" means at least 15 late minutes and at
   least 8 round-one minutes, and below 10 late minutes there is no score.
   The test reads `v_fighter_consistency.sql` and fails if either drifts.
3. **Retired and cancelled bookings never count**, even with a method
   populated. A fight counts only if `is_active` is not false, the card is
   past, the event is not flagged upcoming, and the method is non-blank.
   Checked live: none of the 5 inactive rows carries a method today; the
   rule does not rely on that.

`tests/fight-lab.test.js` now has 30 tests. The new regression tests were
confirmed to fail with each fix reverted.

## Next action

Owner: review the T-080 pull request on a phone and a desktop, against a fight on
the 2026-10-17 card. If it is approved, merge it. Then T-081 (footage links) is
next, but only if it serves the first-ten-customers goal; otherwise it waits.

---

## 2026-10-13 (d) — Commercial-readiness audit: what stands between CFL and its first $100

**From:** Claude (project-audit session)
**To:** Owner
**Date:** 2026-10-13

The audit is in `research/commercial/COMMERCIAL_READINESS_AUDIT_2026-10-13.md`.
CFL cannot take its first $100 today, and the model is not why. Four things
stand in the way:

1. Almost no audience: one engaged person in the first hour of the corrected
   human count.
2. The paid feature cannot deliver: no mail key, and the alerts cron is off.
3. No lawful way to take money: no Stripe account, no Terms, and the privacy
   page is wrong.
4. Data rights for The Odds API and UFCStats are unchecked.

The most plausible first $100 is one business customer, such as a betting
newsletter, podcast or Discord, paying for a weekly card-market brief. The
audit has a three-week plan and a kill rule.

## Next action

The owner does three things this week:

- Create a Resend key and set `RESEND_API_KEY` / `RESEND_FROM`. Claude then
  runs the alert delivery test and turns on the alerts schedule.
- Read The Odds API terms on commercial use.
- Book the first five conversations with people who publish about UFC
  betting.

Claude can build the non-transacting `/pro.html` offer page and a sample
weekly brief once the owner sets the price to show.

---

## 2026-10-13 (c) — The forecast-lock table is live; four dead bookings retired; PRED-001 merged

**From:** Claude (project-audit session)
**To:** Owner
**Date:** 2026-10-13

**PRED-001 is merged** ([cannhaven-wq/Cage-Metrics#58](https://github.com/cannhaven-wq/Cage-Metrics/pull/58),
`16de9de7`) after six rounds of independent review.

**On the owner's approval ([D-024](DECISIONS.md)):**

- `win_model_locks` is applied, and its security was verified on the live
  objects (details in D-024). It is empty.
- Four superseded bookings are retired (`is_active = false`). Afterwards, no
  fighter is booked twice on the 10-17 or 10-24 card.

**Found on the way.** The Supabase MCP tool hangs whenever a statement raises a
NOTICE. That explains every unexplained timeout today, and it is now noted in
CLAUDE.md.

## Next action

Draft PRED-002's preregistration (opponent-adjusted grappling) on DEV data,
then run the commercial-readiness audit the owner asked for next. The owner's
next phase is the first $100 of revenue.

---

## 2026-10-13 (b) — American fighters get the real flag behind them

**From:** Claude
**To:** Owner
**Date:** 2026-10-13

The country wash behind a fighter (Card Lab sides, the fighters grid, the Prop
Board names) was a gradient of three flag colours. For the US that read as a
generic red-white-and-blue band with no stars. `cfl.flagStyle` in `_shared.js`
now puts the real flag image (flagcdn, the same CDN `cfl.flagChip` already
uses) on top of that gradient; if the image fails, the old colours still show.
This applies to every country in the colour table, not only the US — the same
complaint holds for any flag with a symbol. Opacity and fade are unchanged.

## Next action

Owner: look at the next card on the live site and say whether the wash is
strong enough to read as a flag, or should go up from 16% opacity.

---

## 2026-10-13 — Stabilization merged and verified; PRED-001 reviewed and amended; forecast-lock table proposed

**From:** Claude (project-audit session)
**To:** Owner
**Date:** 2026-10-13

**Production.** #54, #55, #56 and #57 are merged. Before merging, an
independent reviewer that had written none of the code found one blocking bug
in #55: the Chookagian→Cerminara alias matched the bout, but the A/B step still
read the raw feed name. It would have dropped her price and written one-sided
rows into append-only `fight_odds`. The bug never reached production. It was
fixed, with a capture test that failed before the fix and passes after.

- **Analytics.** The migration was applied: `engaged_session` is in the CHECK,
  and `v_traffic_daily` exists. On first apply the view inherited Supabase's
  default grants (`anon` held INSERT/UPDATE/DELETE/TRUNCATE); it now holds
  SELECT only, and the repo file revokes first.
- **Main.** Tests are green at `77e38602`. The one red run, at the #54 merge,
  was a preview page generated from the old template before the post-merge
  prerender replaced it.
- **Verify live site** passed: served bytes match `main`, and the card shows
  only consensus, fair price, movement and best price.
- **Pipeline health** first run: healthy.

**PRED-001 Amendment 1 ([D-023](DECISIONS.md)).** An independent reviewer
tried to break the protocol in **six rounds** before merge. Rounds 1–5 each
found blocking problems, all closed and turned into tests. Round 6 found
nothing blocking, plus one small gap, which is also closed. Rounds 3–5 added
three rules:

- prospective looks take whole cards;
- every priced bout needs a lock row, and a bout the model declines needs an
  abstention lock (`p_a` NULL) written before the bell;
- the population comes from a committed recipe whose cutoff is the card start.

The two earliest rounds are summarised below.

- **Round 1** found five bypasses that kept every test green.
- **Round 2** found that two of them still worked:
  - the freeze history could be rewritten in place;
  - H1 outcomes, prices and card groupings were not checked, and flipping 5%
    of outcomes turned REJECT into PASS_H1.

  It also found the registry was editable, prospective inputs were chosen by
  the caller, and the lock table could be back-dated through `now()`.

Every finding is closed and is a test. Inputs to a look are now checked or
derived rather than trusted. Merged freeze, ledger and registry entries cannot
change relative to main, and CI fails if it cannot fetch main. Selective
locking makes a prospective look INVALID. H1 is 710 fights, after excluding
three that were rebooked in place. No look has been taken.

**What code cannot stop, stated in the protocol.** Anyone with database
credentials can compute a sealed log loss by hand. So no claim ever rests on
H1.

**Forecast-lock table: proposed, not applied** (`research/protocol/
proposed_2026-10-13_win_model_locks.sql`).

- Append-only for every role.
- The lock time is `clock_timestamp()`, the wall clock at insert.
- The deadline is the card's earliest start.
- One forecast per fight per experiment.
- The market snapshot is required, and `event_date` comes from `events`.
- The table refuses locks on settled fights, on retired bookings, on swapped
  corners, and with a training cutoff after the event.
- Private to both browser roles.

12 checks ran against production inside rolled-back transactions, and every
one passed. The tool times out on the full-length request, so it ran in two
halves. Nothing persisted.

## Next action

The owner decides two things:

1. **Apply the lock migration** after reading it. Claude applies it with
   `apply_migration`, re-runs the grants check, and records it.
2. **Confirm opponent-adjusted grappling as PRED-002.** Claude then writes
   the preregistration on DEV data only; nothing is trained before it is
   frozen.

Separately, the four-row stale-booking update must be applied before Friday
2026-10-16 23:00 UTC.

---

## 2026-10-12 — PRED-001: the bar a prediction model must clear, written before anyone tries

**From:** Claude (project-audit session)
**To:** Owner → research sessions (prediction benchmarks; research workstreams)
**Date:** 2026-10-12

The owner asked for an Independent Auditor and a preregistered research
protocol before any new model work. It is frozen in `research/protocol/`:
the protocol, its thresholds (`protocol.json`), the executable decision rules
(`pred_protocol.py`), a fingerprint of the sealed data (`holdout_manifest.json`),
an empty append-only ledger of looks at sealed data, and a preregistration
template. `tests/test_prediction_protocol.py` (33 tests) fails if the text or
the code drifts from its frozen hash, if a ledger budget is exceeded, or if
experiment code queries the database directly. The decision rules are checked
against synthetic worlds where the truth is known: real information passes; a
copy of the market, a noisy market and an overconfident model are rejected or
failed; a leak is flagged; and **a real gain of ~0.004 on 3,600 fights is not
confirmed**, because that is honestly too small to see.

**Said plainly.** The sealed history can only detect a gain of about 0.008. The
best gain ever measured here is 0.0034. Confirming a gain of 0.005 forecast in
advance takes about 1,650 fights. The sealed window is not virgin either: the
Factor Lab and the v4–v6 results already cover it, and the protocol says so.

**Coordination.** The prediction-benchmarks session owns the inventory of past
results (INFO-AUDIT-001, `research/info_audit/` on
`claude/optimistic-ptolemy-8g2smd` @ `cc7f810`); this protocol cites it rather
than recomputing it. The seal is recorded as [D-022](DECISIONS.md). The
research-workstreams session was told not to write a second Step 2. Both were
asked to fit nothing on 2025+ fights from now on.

## Next action

Prospective testing needs an append-only lock table for win-probability
forecasts, built on the `prop_model_locks` pattern. Creating it is a production
migration (L3 item 5); draft the SQL for the owner's approval. Until it exists,
no PRED-001 experiment can get past an H1 look. The research agents start by
copying `EXPERIMENT_TEMPLATE.md` and working on DEV only.

---

## 2026-10-12 (d) — Stabilization sprint, PR 4: what to sell first, and how to find out if anyone wants it

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-10-12

`research/commercial/COMMERCIAL_VALIDATION_2026-10-12.md`:

- **The Pro boundary withholds nothing that exists.** Every built Pro item
  (book table, charts, watchlists, alerts) is free; the rest is unbuilt.
- **Smallest differentiated offer: fight-week price and movement alerts**, plus
  a past-cards market history page. Remaining work is operational (mail key,
  delivery test, cron), not development.
- **Demand test before any build:** one honest "not available yet" page with
  the intended price and a waitlist (existing `premium_waitlist` table and
  `cflAuth.joinWaitlist`), two fight weeks of distribution in UFC betting
  communities, ten conversations, and pass/fail thresholds fixed in advance.
  An on-site box alone would measure nothing at one to four visitors a day.
- **Blockers besides demand:** T-054 (privacy policy also wrongly describes a
  cookie banner and affiliate cookies that do not exist), T-048, The Odds API
  and UFCStats terms never read, price, Stripe, mail key.

Small fixes in this PR: `disclaimer.html` and `about.html` share text no longer
say "predictions" / "prediction model"; the no-model test now covers the legal
and account pages (the disclaimer's legal body is exempted for one phrase and
listed for the lawyer, not rewritten).

## Next action

Owner: decide whether to run the demand test, and if so set the price to show
on the offer page. Correct the privacy policy's cookie statements regardless.
Then Claude builds the one static offer page (no billing) and the two-week
measurement.

---

## 2026-10-12 (c) — Stabilization sprint, PR 3: count people, not page loads

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-10-12

The funnel counted every JavaScript-executing crawler as a session. Measured
by behaviour, human-signal sessions were 28, 20 and 10 in the three full weeks
since tracking began, while raw sessions grew sixteen-fold
(`research/traffic/HUMAN_TRAFFIC_BASELINE_2026-10-12.md`).

- `engaged_session`: once per session on a real scroll, click, tap or keypress.
- `landing_view` gains `webdriver` and `ua_bot` booleans.
- `v_traffic_daily`: the daily baseline (engaged sessions, by source and by
  what they reached). Query validated read-only against production.
- `_shared.js` cache-bust normalised to `?v=rl5` on every page (was rl3 on 29,
  rl4 on one).
- `tests/engagement.test.js` (7) pins the rule; the three-place event list
  (JS, CHECK constraint, ANALYTICS_SCHEMA.md) is updated together.

## Next action

Owner: apply the updated `funnel_events_migration.sql` **before** merging this
PR (otherwise the new event is rejected until it is applied), then merge. Export
Plausible's visitors, sources and pages for 2026-09-21 → today so the baseline
can be reconciled against a bot-filtered count.

---

## 2026-10-12 (b) — Stabilization sprint, PR 2: operational repairs and a monitor

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-10-12

Stacked on PR 1. What it changes in this repo:

- **`public_read_odds.sql` now refuses to run.** It granted anon read on the raw
  odds table; live policy is admin-only, so it was never (or no longer) applied,
  and one `psql -f` would have published every quote. `tests/sql-hazards.test.js`
  fails if any root SQL file grants that again.
- **`export.yml` schedule off.** It failed every day on a missing
  `SUPABASE_URL` secret. Adding the secret would have committed the raw odds and
  fighter tables to this public repository daily — a licensing and exposure
  decision, so it waits for one.
- **New monitor, `pipeline-health.yml`** (twice daily): critical workflows
  failing, stale or disabled by GitHub; odds older than 30 h; a finished card
  with most results missing; an empty two-week calendar. One labelled issue per
  problem, closed when it clears. Data checks verified against today's live
  facts (all healthy).
- **Odds matcher alias.** Saturday's Cerminara vs Stiller had no price: the feed
  still says "Katlyn Chookagian". One reviewed alias, two tests.
- **CI now runs `build/test-fetch-odds.js`** (73 capture-path tests that never
  ran in CI).

Investigations written up, nothing applied:
`research/clv/MIGRATION_SEQUENCE_2026-10-12.md` (order and rollback for the five
unapplied migrations; the ledger seed is used=33, remaining=467 from today's log)
and `research/integrity/INTEGRITY_RECHECK_2026-10-12.md` (four checks grew; the
new corner swaps come from the odds repo's Polymarket step; four dead
double-bookings sit on the next two cards).

Outside this repo: `cage-metrics-scrapper` PR #1 fixes the fighter scraper's
build (same `mise.toml` fix as the event scraper). Corrections to the audit: the
second Railway odds-scraper service is the model trainer, not a duplicate; and
neither Railway odds service has a schedule, so their failed builds stop nothing
— Polymarket and the v1–v6 retrain run from the odds repo's GitHub Action.

## Next action

Owner, in this order: (1) approve or decline the four-row `is_active = false`
retirement in `INTEGRITY_RECHECK_2026-10-12.md` before Friday 23:00 UTC, when
the 10-17 card's snapshot is taken; (2) merge PR 1 then PR 2; (3) decide whether
to merge `cage-metrics-scrapper` #1, knowing the merge runs a full scrape once;
(4) set `RESEND_API_KEY` / `RESEND_FROM` if the Brief and alerts are to deliver.

---

## 2026-10-12 — Stabilization sprint, PR 1: the retired forecast comes off every public channel

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-10-12

The current-state audit (`audits/cfl-current-state/`, on branch
`claude/nice-bell-ussmhp`) found the forecast D-011 removed on 2026-09-21 still
going out in four places. This pull request removes it from all four and makes
each one a test failure if it returns.

- **X.** The Mon/Wed/Fri poster tweeted model win percentages three times a week
  (verified: tweet ids 2107245353053634817, 2107950714135761316,
  2108670936010387493). Its schedule came off `main` on 2026-10-12 (`38d47f7d`).
  This PR makes the guard real: the generator no longer stamps its own model copy
  `research`, and `build/social-copy-guard.js` refuses any piece whose *words*
  read as a forecast, on both posting paths.
- **fighter.html**, the most visited page: the engine's graded record ("Model
  called X of N", "a fade candidate at a short price") and the archived Prop
  Board's projections are gone.
- **Generated pages:** 14 match previews named "Cannon Fight Lab's models pick X"
  in FAQ structured data; all 75 previews, 7 card pages and 7 event stubs were
  titled "Predictions". Generators and published files both fixed;
  `prerender.js` no longer reads `model_picks`.
- **event.html** runtime title, description and keywords.

Also fixed on the way: `send-digest.js` and `social-post.js` read `open_p_a`,
removed by D-012, and the Brief's 24 h move subtracted two medians over
different book sets (the D-015 error). Both now read the matched-cohort columns.

Left deliberately: the Factor Lab's "not the record our pick engine uses"
paragraph (a negative disambiguation pinned by D-008 and its test); the archive
pages; `social/` batch files (served by Pages, carry old model copy — owner call
whether to delete, see audit item A-055).

## Next action

Owner: review and merge this PR, then check one generated preview page and
`fighter.html` on the live site. After merge, `prerender.yml` regenerates every
stub on the push to `build/**`; confirm the next stub commit does not reintroduce
"Predictions". Then PR 2 (operational repairs) — see `STATE.md`.

---

## 2026-10-05 — The pre-fight record gets a dead man's handle, and the snapshotter runs again

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-10-05

Two jobs put CFL's view on record before every bell. **Both had been failing in
silence, and both times it was a person who noticed, weeks later.** That is the
thing this entry is about — not either bug.

### The snapshotter: the symptom was not the fault

Reported: "it won't run — cron set, build succeeds, the container exits
instantly, the only runtime log is `Stopping Container`."

That was never a crash. A Railway **cron** service executes its start command on
the schedule and not otherwise; the schedule was Friday and the redeploy was
Monday, so an instant exit with no output was the correct behaviour of a service
with nothing to do. Reasoning from the symptom would have led to hunting a crash
that did not exist.

Three real defects, all latent, none visible from the log:

1. **No explicit exit on success.** `supabase-js` keeps keep-alive sockets and an
   auth-refresh timer alive, so the process would have hung after writing. Under
   Railway's cron contract a run that does not finish causes **every later run to
   be skipped** — so the first Friday would have hung and nothing would ever have
   run again. Fixed with `persistSession:false`, `autoRefreshToken:false`, a
   five-minute watchdog and an explicit exit. `test/exit-contract.test.js`
   spawns the real script against a stub client that holds the event loop open
   and fails if it has to be SIGKILLed — old code: killed at 8016 ms; new: exit
   0 in 49 ms.
2. **`engines.node` said `>=20`.** `@supabase/supabase-js` was pinned at
   `^2.39.0` — a floating minor — and a release had started requiring a native
   `WebSocket`, which Node has from 22. Nothing in the repo changed between a
   working run and a crashing one. Now `>=22` plus a `.node-version` file, and
   the dependency pinned to `~2.117.2`: an unattended weekly cron should not
   resolve a floating minor at build time.
3. **It printed nothing before its first query**, which is what made an empty log
   ambiguous in the first place. It now announces itself, its Node version and
   its pid before any `require` that can throw, and names the specific missing
   environment variable rather than both.

Verified live: **12 predictions written for UFC Fight Night: Allen vs. Duncan**
(event 4713), node v22.23.2, clean exit. Cron restored to `0 18 * * 5`.
Merged as cannhaven-wq/cfl-snapshotter#1 and #2.

### The dead man

`build/check-pre-fight-coverage.js` + `.github/workflows/dead-man.yml`. It asks,
three times a day, whether each writer's record exists for every card inside ten
days, and shouts when it does not.

- **Deadlines are absolute instants derived from the card date**, not "did the
  cron fire" — the pre-fight record at the date boundary, the model picks three
  hours before it. Same discipline as the odds cadence gate: GitHub does not
  deliver schedules when they ask, and a run landing at 03:47 reaches the same
  verdict as one landing at 00:10.
- **`partial` is deliberately not an alarm.** Healthy cards come in at 13 or 14
  against 15 — a bout with no usable history produces no verdict. If that
  shouted, every card would shout, and an alarm that fires constantly is an
  alarm that gets filtered to a folder. Under **half** the card is a different
  shape — a run that died part-way — and does breach.
- **Two channels, no new secret.** `RESEND_API_KEY` is unset (T-074), and a
  watchdog whose only channel is an unset secret has exactly the defect it
  exists to catch. A breach opens a labelled GitHub issue — one per writer per
  card, hidden marker, never one per run, **closed automatically when the record
  appears** — and reddens the build.
- **"I could not look" fails.** No key, a failed query, zero visible cards, or a
  read sitting at PostgREST's 1000-row page cap all exit non-zero. This is the
  opposite of `build/send-alerts.js`, which exits 0 on a missing key and is right
  to — a not-configured runner is not a broken market. For a dead man's handle
  the two cases it must distinguish are "nothing is wrong" and "I never looked".
- 35 offline tests, with the September 26 card as a fixture.

### Said plainly rather than papered over

**It cannot catch its own silence.** If GitHub throttles the schedule or disables
it after 60 days of repository inactivity, nothing shouts, for the same reason
nothing shouted before. It prints the gap between its own recent scheduled runs,
so a run that *does* land names the hole, and warns above 30 hours. A real fix
needs an observer outside GitHub — **T-076**, queued, not claimed as done.

Two further gaps found on the way and queued as **T-077**: the Railway cron is
Friday-only, so a card on any other weekday is never reached at all (the dead man
reports it dark, correctly, and there is nothing to fix it with); and
`predictions.closing_odds_american` is NULL in all 72 rows of all six batches
ever written — the column has never been populated by anything.

## Next action

**Nobody, until Friday night.** The watchdog is live and verified; its first
real test is the 10 October card — a Saturday — whose scheduled pre-fight
snapshot runs at **23:00 UTC Friday 9 October**, with the watchdog deadline at
**00:00 UTC Saturday 10 October**. If `snapshot.yml` fails that night, a
`dead-man` issue appears and the workflow goes red — that is the whole feature,
and it needs no help.

**A writer's run time and its deadline are different instants, and keeping them
apart is the point.** The deadline is not when the job is supposed to run; it is
when the record has to exist, and the gap between the two is the grace a late or
slow run gets before anything shouts. Four instants, in order:

| UTC | what | which kind |
|---|---|---|
| Fri 18:00 | `cfl-snapshotter` fires on Railway (`0 18 * * 5`) | writer runs |
| Fri 21:00 | model-picks deadline | watchdog checks |
| Fri 23:00 | `snapshot.yml` writes the pre-fight record | writer runs |
| Sat 00:00 | pre-fight-record deadline, at the date boundary | watchdog checks |

The two graces are **not** equal, and neither number is arbitrary. Model picks
get three hours, because a Railway cron can be late and the run itself takes
seconds. The pre-fight record gets one — its 23:00 run finishes around 23:10, so
the boundary leaves fifty minutes — and it is cut that tight on purpose, because
what the boundary buys is the rest of Saturday: `snapshot.yml` has a second pass
at 10:30 UTC, and the watchdog's third daily position at 12:00 UTC checks after
it. So a 00:00 breach is a card that can still be saved by hand, and the 12:00
check is the last word before US bells. That ordering is the difference between
an alarm somebody can act on and a postmortem.

**Reviewed and corrected 2026-10-13.** The exemption shipped describing itself
as a limit of the cron — `reachableWeekdays`, "cannot reach a card on another
weekday". **That was false**: `cfl-snapshotter` selects the next upcoming card
on *any* weekday, so a Friday wake reaches a Sunday card whenever nothing sits
between them (UFC Freedom 250, 2026-06-14, had nothing). An exemption that reads
as a guarantee nothing was missed is the wrong kind of wrong, so it is now
`monitoredWeekdays` and described as a monitoring policy, with both directions
it gets wrong written down. The forecast lock (`pre_fight_snapshots`) has no
policy and is tested to breach on all seven weekdays — the exemption stays
limited to the legacy `predictions` table.

**The watchdog's first week, measured.** 23 scheduled runs 2026-10-06 → 10-13,
all green, **zero issues and zero false alarms**; median delivery gap 6.6 h,
largest 15.2 h. The 2026-10-10 card came through fully covered on both writers
(12 fights, 12 predictions, 12 snapshots; first snapshot 10-09 02:39 UTC). The
00:45 run on 10-10 — 45 minutes past that card's record deadline — reported
"No breach: every card past its deadline has a record", so it was reading real
data, not passing vacuously.

**Settled since this entry was written: T-077 is deferred, not refused**
([D-021](DECISIONS.md), owner, 2026-10-05). The Friday-only cron stays; the
watchdog was narrowed to match it in the same pass, so a card on another weekday
reports `out_of_schedule` rather than raising an alarm nobody could act on. The
pre-fight record's scope is untouched and a midweek card still breaches on it.
Measured cost of the gap: 3 cards in 128 since 2024-01-01. **Next build priority
is the member-facing work** — odds comparison, movement charts, alert delivery —
not more snapshotter coverage.

**Owner:** nothing is required for this to work. If you want the email channel as
well as the issue, set `RESEND_API_KEY` and `RESEND_FROM` (**T-074**) — that same
pair also unblocks the weekly digest and member alerts, and **T-073** (the
controlled alert-delivery test) is waiting on it.

**ChatGPT:** review `build/check-pre-fight-coverage.js` against one question — is
the `partial` / `thin` boundary at half the card the right place for it? It is
the only judgement in the file that trades a missed alarm against a false one,
and it was set from six observed cards (13–14 rows against 13–16 fights), which
is a small sample to cut a threshold on.

---

### Verified after merge, which the entry above could not promise

Both pull requests are merged (#49 `d2d31119`, #48 `9922adaa`) and the watchdog
has now been run against the real database twice.

**A review caught a defect that would have broken it on every run.**
`dead-man.yml` pinned `permissions:` and then ran `actions/checkout@v4` — and an
explicit permissions block sets every scope it does *not* name to `none`, so the
token had `contents: none` and the job would have died 403 on its first step.
Nothing caught it here: `workflow_dispatch` needs the workflow on the default
branch, so the file had never executed, and the green CI on the pull request was
`tests.yml`, a different workflow with its own correct scope. The one path that
would have exposed it was shut by the same thing that stopped the live test.
Fixed, and `tests/dead-man.test.js` now sweeps every workflow in the repo and
fails on any that pins permissions, runs a checkout and names no `contents` —
verified against the broken file, so it is not decorative. `dead-man.yml` was
the only offender of twenty-one.

**Run 1, real clock:** no breach, correctly — on 5 October neither of the 10
October card's deadlines has passed.

**Run 2, forced past the deadline** (`now=2026-10-10T06:00:00Z`,
`open_issues=false` so a card whose record is not yet due could not raise a
false alarm):

```
BREACH  Pre-fight record is EMPTY for UFC Fight Night: Allen vs. Duncan (2026-10-10):
        0 rows for 12 fights, and the deadline passed at 2026-10-10 00:00:00Z.
   ok   Model picks: 12/12 for UFC Fight Night: Allen vs. Duncan (2026-10-10).
  ...   Model picks: not due yet for Buckley vs. Malott (2026-10-17) — deadline 2026-10-16 21:00:00Z.
```

Real counts off the live database, the breach path firing, the job red. A run
that merely says "no breach" proves nothing about whether it read anything,
which is why the second run was worth the red tick in the Actions list.

---

## 2026-09-21 (h) — Watchlists and alerts, and an alert that would rather say nothing

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-21

PR #45 merged (`7edd4e3`). Step 9 of the resequenced order — watchlists and
alerts — is done. [D-020](DECISIONS.md), T-070 / T-071 / T-072.

**There is now no unblocked build work left in the sequence.** Steps 2–5 are
yours and a lawyer's, step 6 needs your Stripe keys, and step 7 is gated behind
all of them.

### Read this first: a P0-class grant defect, and two inert protections

`REVOKE ALL ... FROM anon` left **`authenticated` holding TRUNCATE** on three of
the four new tables, inherited from Supabase's default privileges. **TRUNCATE
bypasses row level security entirely** — any signed-in member could have emptied
every other member's watchlist and alerts, with RLS never consulted. Same shape
as the `funnel_events` finding, and found the same way: by querying
`role_table_grants` after applying rather than by reading the migration.

Two further faults, both in the trigger pinning the suppression memory, both
found by testing behaviour rather than reading code:

1. It keyed on `auth.role()`, the JWT claim. A migration or psql session has no
   JWT, so it reverted **the sender's own writes** — alerts would never arm.
2. The fix used `current_user` but was `SECURITY DEFINER`, where `current_user`
   is the function's **owner**. The guard was always true: the protection read
   as though it worked and **did nothing at all**.

All three closed and verified as the `authenticated` role in a rolled-back
transaction.

### The rule the feature is built around

**An alert must never fire from a comparison CFL would refuse to print.** An
email is a stronger claim than a number on a page: the member did not go looking
for it, and it may send them to a sportsbook to act.

**The matched-cohort methodology is preserved and extended.** A movement alert
stores the **fingerprint** of the cohort it fired over — an md5 of the sorted
matched book ids, *not the count*, because one book leaving as another joins
holds the count still and moves the median. If the fingerprint or the baseline
changes, the alert **re-baselines and stays silent**. Subtracting two medians
over different book sets is the D-012 error, measured at up to 12.7 points.

### The finding that changed the design

The first version applied **one 45-minute staleness ceiling** to both kinds of
alert, borrowed from the frozen CLV limit. Against CFL's real capture cadence —
5 min only in flow, hourly on card day, otherwise **once a day** — that makes
**0 of 79 fights alertable**. Measured on the live table. The feature would have
shipped permanently silent, and a silent alert system is indistinguishable from
a broken one.

A price and a move are different claims and cannot share a rule: **a price is an
offer** (120 min, inside the hourly fight-week tier) and **a move is a
historical fact** (24 h). Alerts are inherently a fight-week feature; outside it
they correctly say nothing.

### Suppression

A **UNIQUE dedupe key claimed before the email is sent** — send-then-record
loses the record on a crash and re-sends forever; this way a crash costs one
email a member should have had rather than an unbounded number they should not.
The key is the alert plus its occurrence number, never the value, because keying
on the value mints a fresh key every tick. Then **one email per member per run**
rather than per alert, a cooldown, a daily cap, and quiet hours that stay
**off** until a time zone is collected rather than guessed.

### Verified

52 new assertions in `tests/alerts.test.js`, 20 suites green. The evaluator was
run against **live rows** from `v_fight_alert_market`: the biggest real move
(7.0 pts over 3 matched books) fires at a 3-point threshold, refuses to re-arm
after a cohort change, and every price alert is correctly refused as
`stale_for_price` at 8.6 hours old.

**Not verified, and it cannot be from here:** `build/send-alerts.js` has never
actually sent an email. This environment has no secrets and its network policy
blocks the Supabase host, so the sender can only run in CI. `alerts.yml` is
manually dispatchable with `dry_run` defaulting to **true**.

## Next action

**Owner:** dispatch **Send market alerts** with `dry_run: true` once this
merges, and read the log — it prints every refusal and its count. Then steps 2–5
of [D-019](DECISIONS.md), which nothing else moves without. Cheapest first is
**T-054**: one disclosure clause, draft already written.

**ChatGPT:** review the re-arm rule in `alerts.js::evaluate` specifically for a
case where re-baselining silently is the wrong call, and the two staleness
ceilings against what the odds cadence actually delivers in a fight week.

**Nobody:** relaxes a refusal to make an alert fire, or turns the quota into a
Pro gate before step 7.

---

## 2026-09-21 (g) — No paywall before there is a way to pay

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-21

PR #44 merged (`68a6a5a`). The Stripe backbone is on `main` and
`verify-billing-refusal.yml` is now dispatchable from its permanent home.

**The owner resequenced the remaining work** ([D-019](DECISIONS.md)).
Free-vs-Pro enforcement used to sit immediately after Stripe; it now sits
behind the gates that make paying possible.

| # | step | whose | state |
|---|---|---|---|
| 1 | Stripe backbone (#44) | Claude | **done** |
| 2 | **T-054** privacy names the analytics processor | Owner + lawyer | blocked on legal |
| 3 | **T-048** Terms of Service exists | Owner + lawyer | blocked on legal |
| 4 | **T-067** set the price | Owner (L3) | not set |
| 5 | **T-068** Stripe account, product, secrets | Owner | no account connected |
| 6 | **T-069** checkout in Stripe test mode | Claude | blocked on 4–5 |
| 7 | **T-061** apply the Free/Pro boundary | Claude | moved here |
| 8 | **T-066** turn checkout live | Owner (L3) | blocked on 2–7 |
| 9 | watchlists / movement alerts | Claude | **unblocked** |

**It is not only about courtesy to the member.** A paywall in front of a
product with no checkout is a dead end — the member meets a wall and the door
behind it does not exist. It also destroys the one measurement the funnel
instrumentation was built to take: `paywall_hit` means something when a
purchase is possible and nothing when it is not, and a month of unbuyable
paywall hits is a baseline nobody can read afterwards.

**Nothing about the blockers changed.** T-054 and T-048 are still checkout
blockers, `entitlements.js::CHECKOUT_BLOCKERS` is untouched, and
`stripe-checkout` still returns 503 before it authenticates anyone. Moving
step 7 later makes 7 and 8 independent, which they always should have been.

### The drafter's brief was out of date, and now is not

`legal-review/PROPOSED_WORDING.md` told a drafter that subscription terms were
"none of this is decided". That was true when it was written and false the
moment #44 merged: billing period, renewal, cancellation, failed payment and
expiry are now shipped, tested behaviour. The file carries a new **"How billing
actually behaves"** section so the Terms can describe the system rather than
guess at it — cancellation taking effect at period end, a failed payment not
cutting access off immediately, access ending automatically on expiry, an
unrecognised state ending access rather than continuing it.

Two things flagged so a drafter cannot over-promise: **no trial is
implemented**, and **nothing in the system issues a refund**. If the Terms
promise one, it is a manual process today.

Still outside production. `privacy.html` and `disclaimer.html` remain untouched.

### On the price

The owner's stated default is ~$9.99–$11.99 monthly, $79–$99 annually, with a
founding rate for the first cohort. **Recorded as a preference, not set**
(T-067). No number is configured and `STRIPE_PRICE_ID` is unset. Three things
it implies are also undecided and are now flagged for the drafter: whether both
periods are sold, whether the founding rate is for life or for a term, and what
happens to it on lapse and resubscription — which interacts with the undecided
question of what the beta grant obliges.

## Next action

**Owner:** steps 2–5 are yours and nothing downstream moves without them. The
cheapest one to clear first is **T-054** — it is a single disclosure clause and
the draft is already written; T-048 is the larger piece.

**Claude:** step 9 (watchlists / movement alerts) is the only unblocked build
work in the sequence. Do not start T-061 — it is deliberately behind the
payment gates now.

**Nobody:** removes a blocker to make something pass, or sets a price to unblock
themselves.

---

