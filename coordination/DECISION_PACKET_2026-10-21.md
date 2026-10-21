# Owner decision packet — 2026-10-21

Everything Claude could build without you is built, tested and merged, or
waiting in a draft PR. What is left here is only what CRITICAL_GATES.md
reserves for you: legal wording, money, published claims, migrations on
security or append-only tables, and outbound marketing.

Each item: **what you are deciding · my recommendation · what happens if you
approve.** Answer by item number; "approve" on an item means the
recommendation.

---

## A. Turn on payments (in this order)

**A1. Legal pages — T-048 Terms, T-054 Privacy.** Drafts are complete in
[PR #102](https://github.com/cannhaven-wq/Cage-Metrics/pull/102), with 33 open
questions, each with a recommended answer, in
`legal-review/OWNER_REVIEW_2026-10-21.md`.
- *Recommendation:* send both drafts and the 33 answers to a lawyer. In the
  meantime, at least approve replacing the live privacy page. It currently
  claims cookies, a cookie banner, affiliate sharing and IP storage, none of
  which exist.
- *If approved:* the drafts go live, the footer links them, and the
  T-048/T-054 checkout blockers are removed in the same PR.

**A2. Disclaimer wording.** `disclaimer.html` §2 says "a 62% favorite under
our model", which is a model number on a public page (D-011). Tests exempt the
sentence deliberately because legal wording is yours.
- *Recommendation:* replace it with "A fighter the betting market prices as a
  62% favorite still loses roughly 38% of the time, if that price is accurate."
- *If approved:* a one-line PR, and the test exemption is removed.

**A3. Price — T-067.**
- *Recommendation:* $9.99/month and $89/year. A founding rate for the first
  cohort, kept while the subscription stays continuous and lost if it lapses.
  No free trial, because the beta already serves that purpose.
- *If approved:* the amounts go into `entitlements.js::PLANS` (now null).
  `pricing.html` stops saying "Price not set".
- *Note:* the old "$10–15 a month" FAQ line is already removed. It was an
  undecided number.

**A4. Stripe account — T-068 → T-069 → T-066.**
- *You do:* follow `research/commercial/STRIPE_SETUP_RUNBOOK.md`. Create the
  account, product and price, and the webhook. Set the three function secrets
  in **test mode**.
- *Then Claude:* runs `build/stripe-test-e2e.js`, which refuses live keys.
- *Then you:* approve one go-live PR. It removes the blockers, enables the
  button and updates `verify-billing-refusal.yml`.
- *Unconfirmed:* the harness will confirm whether Stripe's 2025-03-31 API moved
  the period-end field. The webhook now handles both shapes and fails closed
  either way.

**A5. Free/Pro boundary — T-061.** The draft is in
`research/commercial/t061_pro_gates.DRAFT.sql`. It has three conflicts that
only you can settle:
1. Does gating the movement chart take it away from free readers on Card Lab?
   *Recommendation:* keep the current movement free, and make the history
   beyond 14 days Pro.
2. Does "book-by-book table" mean current prices or price history?
   *Recommendation:* current prices are free; history is Pro.
3. Are alerts metered or Pro-only? *Recommendation:* metered, 3 free and 50 Pro.

## B. Email

**B1. Resend keys — T-074.** Set `RESEND_API_KEY` and `RESEND_FROM`.
- *If approved:* member alerts can be tested (T-073), the dead-man email can
  send, and confirmation emails become possible.

**B2. Double opt-in — T-090.** It is built and merged (#106).
- *Recommendation:* approve applying `card_brief_double_optin_migration.sql`.
  It is one transaction, checks itself, and has been rehearsed on a replica.
  Approve the confirmation-email wording together with A1.
- *If approved:* new sign-ups get one confirmation link, and the Brief only
  ever goes to confirmed addresses.

**B3. Social posting — T-105.** The generator now uses research data only
(#104), and posting is hard-blocked.
- *Recommendation:* approve manual posting only. Preview a dispatch run first.
  Leave the schedule off for two weeks.
- *If approved:* one PR deletes the `POSTING_BLOCKERS` line.

**B4. Two-minute email pop-up — T-035.**
- *Recommendation:* decline. It works against COPY_STYLE's anti-tout rule, and
  the inline Card Brief form already exists.

## C. Database changes (L3)

**C1. Running order — T-096**, unblocking T-030 and T-032. *See section F,
filled in when the running-order work reports back.*

**C2. Lock `fight_odds` against edits — T-031.**
- *Recommendation:* approve, and apply on Sunday 2026-10-25, after UFC 333 and
  between cards.
- *If approved:* stored odds can no longer be edited or deleted by anyone,
  which strengthens the record.

**C3. Rewrite a fight's rounds in one transaction — T-091**, PR #73.
- *Recommendation:* approve. Claude applies it with `psql`, because the
  Supabase tool holds back SQL that deletes.
- *If approved:* a re-scrape can never leave a fight half-written.

**C4. Outside watcher for the dead man — T-076.** Built in #105.
- *You do:* create a fine-grained GitHub token (Issues: read/write, this repo
  only), approve applying the migration, and store the token in Vault. The
  steps are in `research/ops/T076_DEAD_MAN_OBSERVER_RUNBOOK.md`.
- *Unconfirmed:* whether your Supabase plan bills for pg_cron or pg_net.

## D. Published claims and product

**D1. Edge Factors correction — T-025.**
- *Recommendation:* merge [PR #103](https://github.com/cannhaven-wq/Cage-Metrics/pull/103)
  (update the date if you merge later).

**D2. Parlay Calculator and My Book — T-050.**
- *Recommendation:* keep both reachable. Neither carries a model, and both cost
  nothing to keep.

**D3. My Book "vs earliest price seen" — T-041.**
- *Recommendation:* keep it. It describes the member's own bet, not a CFL
  performance claim, so the CLV publication gate doesn't apply.

**D4. Sportsbook jurisdiction labels — T-049.**
- *Recommendation:* don't label. A jurisdiction claim is a legal claim, and the
  table is neutral without one.

## E. Research and records

**E1. DUR-001 held amendment clauses — T-002.**
- *Recommendation:* approve (f), (g), (j) and (k), which are governance,
  terminology, closer provenance and no dirty locks. Decline (a)–(e). They
  change scoring and eligibility, and outcomes have been readable since they
  were written, so approving them now would risk results-motivated amendments.

**E2. Owner name in the records — T-009.** Which is correct: "Reed Cannon" or
"Michael Cannon"?
- *If you answer:* a new decision entry records it. Old entries are not edited.

**E3. Historical odds purchase — T-107** (budget up to $30, D-031).
- *Recommendation:* don't buy. The 2020–24 data could only detect a very large
  edge, and a positive result would not be confirmatory. Prospective capture is
  already building the honest sample.

**E4. Fight 8566 (UFC 17) result.** Ours says "Decision, unanimous";
Wikipedia says "KO (elbow) 3:15".
- *Recommendation:* no change until a third source agrees. UFCStats is
  currently blocked from our runners.

## F. Running order — T-096 / T-030 / T-032

*Pending the running-order workstream's report.*
