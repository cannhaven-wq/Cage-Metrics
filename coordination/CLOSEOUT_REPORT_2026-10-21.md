# Backlog closeout report — 2026-10-21

**Plain verdict.** Every task Claude could finish without the owner is
finished, merged and live, or built and parked behind an approval it can't
grant itself. Of 44 tracked items (the 40 originally listed, T-091 which had
no row, and T-105/T-106/T-107 created today):

- **11 done**
- **6 dropped**, each with its reason
- **27 open**

Every open item waits on either an owner decision or a source we can't
reach. None is independently executable.

The owner's decisions are in one place:
[`DECISION_PACKET_2026-10-21.md`](DECISION_PACKET_2026-10-21.md).

## Production state

- **Live site:** `verify-live` run 39624296849 on main `bd32d57` passed on
  desktop and mobile against cannonfightlab.com. All 14 UFC 333 fights render
  with both best prices. The main event opens on arrival with its movement
  panel. There is no model number and no opening-line wording.
  - This check had been failing because its script tested the
    pre-redesign markup. Production was fine. Fixed in #110.
- **Tests on main:** run 39623982849 passed with everything combined, and
  each later merge passed CI.
- **Deploy:** Pages run for `bd32d57` succeeded.
- **Merged today:** #101, #104, #105, #106, #107, #108, #109, #110, #111,
  #112, and #113 once its CI is green.
- **Draft PRs for the owner:** #102 (Terms + Privacy), #103 (`edges.html`
  correction).

## Task by task

| id | final state | evidence / what remains |
|---|---|---|
| T-002 | open: owner | DUR-001 clause votes. Recommendation in packet E1 |
| T-003 | done | Protocol frozen 2026-09-16 (D-003) |
| T-006 | done | Two-sided capture: 194/194 sportsbook groups since 10-20 |
| T-007 | done | CLV L3 questions resolved, protocol frozen (D-004) |
| T-009 | open: owner | Which owner name is correct. Packet E2 |
| T-011 | done | CI pins; 756 passed, 4 skipped on Python 3.11 (#101) |
| T-024 | done | FE-001, 2026-09-18 |
| T-025 | open: owner | Correction ready in draft #103 |
| T-029 | done | Empty credit ledger reads as tight (#101) |
| T-030 | open: blocked | Real-page check passed on ESPN (#113); needs owner source choice + T-096 |
| T-031 | open: owner | Odds immutability; apply between cards (packet C2) |
| T-032 | open: blocked | Built (#113); runs once T-096's migration is applied |
| T-033 | dropped | Superseded by Market Lab, Fight Lab and the Card Brief |
| T-034 | dropped | Superseded by `proof-gates.js` and the shipped funnel |
| T-035 | open: owner | Email pop-up; recommendation: decline (packet B4) |
| T-038 | done | Generator rewritten, real-data tests, posting hard-blocked (#104) |
| T-039 | done | Drafter reuses the market post (#101) |
| T-041 | open: owner | Recommendation: keep (packet D3) |
| T-048 | open: owner | Terms draft complete (#102); lawyer approval |
| T-049 | open: owner | Recommendation: no jurisdiction labels (packet D4) |
| T-050 | open: owner | Recommendation: keep both pages (packet D2) |
| T-054 | open: owner | Privacy draft complete (#102); lawyer approval |
| T-055 | done | Funnel read (#101); Head-to-Head links → Fight Lab (#108) |
| T-058 | dropped | Per-fight charts already ship (T-098/T-101) |
| T-061 | open: blocked | Draft gates and tests ready (#109); behind payments |
| T-062 | dropped | Covered by the double opt-in |
| T-066 | open: owner | Checkout go-live; after A1, A3, A4 |
| T-067 | open: owner | Price; recommendation in packet A3 |
| T-068 | open: owner | Stripe account; runbook in #109 |
| T-069 | open: blocked | Test-mode harness ready (#109); needs test keys |
| T-073 | open: blocked | Alert delivery test needs the Resend keys (T-074) |
| T-074 | open: owner | Resend keys (packet B1) |
| T-076 | open: blocked | Observer built (#105); three owner steps (packet C4) |
| T-077 | open: deferred | Owner decision D-021; no consumer of `predictions` |
| T-081 | dropped | Footage links: ongoing curation cost, a paywall, and an L3 analytics change |
| T-082 | dropped | Conflicts with D-030; leftover copy fixed (#105) |
| T-089 | done | Production database proof + browser test 28/28 (#112). **No live-site submission has been made** |
| T-090 | open: owner | Double opt-in built (#106); apply the migration (packet B2) |
| T-091 | open: owner | Rounds-replace RPC (PR #73); packet C3 |
| T-093 | open: blocked | **21 early fights unverified**: UFCStats blocks runners; Wikipedia can't settle it (#111) |
| T-096 | open: owner | Running-order migration + source choice (#113; packet F) |
| T-105 | open: owner | Restart social posting (packet B3) |
| T-106 | done | BT-001: no scorable window (#107) |
| T-107 | open: owner | Buy historical odds; recommendation: don't (packet E3) |

## Historical testing result (T-106)

No strategy can be scored yet. CFL's executable, timed sportsbook prices
begin 2026-09-19. Every settled fight since then is either sealed for
PRED-001 or still collecting for PRED-002. Older stored prices are either
consensus figures or were captured days to weeks before the fight.

Nothing was tuned, and no sealed outcome was read.

Measured without looking at outcomes:
- a single book's median margin is **4.2%**;
- taking the best price within 3 hours of the bell cuts it to **2.65%**;
- detecting a +5% edge needs about **5,400 bets**.

Details: [`research/backtest/RESULTS_2026-10-21.md`](../research/backtest/RESULTS_2026-10-21.md).

## Found along the way

- **The live privacy page makes false claims:** cookies, a cookie banner,
  affiliate sharing, IP storage, and retention periods nothing enforces. The
  fix is the owner's: #102, packet A1.
- **The disclaimer prints "62% favorite under our model".** Wording is in
  packet A2.
- **Stripe API 2025-03-31 could have granted open-ended Pro.** Fixed to fail
  closed (#109). This was never deployed.
- **Fight 8566 (UFC 17) result disagrees with Wikipedia.** Not changed;
  packet E4.
- **UFCStats now blocks GitHub Actions runners.** The production scraper on
  Railway is unaffected: 10-17 has rounds for all 13 active bouts.

## Not verified

- No live-site Card Brief submission has been made.
- None of the proposed migrations has run on Supabase. Each was rehearsed on
  a throwaway Postgres or a replica.
- ESPN's terms of use have not been reviewed.
- The Stripe API change is from memory; the test-mode harness will confirm it.
