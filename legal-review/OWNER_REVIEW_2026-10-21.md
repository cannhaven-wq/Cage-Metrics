# Owner review — legal drafts, 2026-10-21

**Status: drafts for Reed and a lawyer. Nothing here is in effect.**

Two drafts close the two checkout blockers in `entitlements.js::CHECKOUT_BLOCKERS`,
once they are approved — not before:

| task | draft | live page touched? |
|---|---|---|
| T-048 Terms of Service | [`terms.html`](../terms.html) | No. New page, `noindex`, draft banner, linked from nowhere, not in the sitemap |
| T-054 Privacy (names Plausible) | [`legal-review/privacy_draft.html`](privacy_draft.html) | No. `privacy.html` is unchanged |

`tests/legal-drafts.test.js` keeps both in draft state: banner, `noindex`, not
in the sitemap, not linked. **Both blockers stay in `CHECKOUT_BLOCKERS`**; this
work removes neither.

The recommended answers below are a drafter's suggestions to speed the review.
They are not legal advice, and every one marked LAWYER needs a lawyer.

---

## Decisions needed — every placeholder, with a recommendation

### Both documents

| # | Question | Who | Recommended answer |
|---|---|---|---|
| 1 | **Legal entity name and type.** The live Privacy Policy and Disclaimer both say "Cannon Fight Lab LLC, a Tennessee limited liability company". Nothing in the repo confirms it is registered. | Owner + lawyer | Confirm against the state registration. If the LLC is not formed, either form it before checkout or name Reed Cannon as sole proprietor — and correct the two live pages at the same time |
| 2 | **Contact address for legal notices / privacy requests.** Today the only route is the Formspree contact form. | Owner + lawyer | Add one dedicated address (e.g. a `legal@` or `privacy@` mailbox on cannonfightlab.com). A postal address only if counsel says a regime that applies requires one |
| 3 | **Effective date.** | Owner | The date the approved version is merged |

### Terms of Service (`terms.html`)

| # | Section | Question | Who | Recommended answer |
|---|---|---|---|---|
| 4 | 2 Eligibility | Is stating 21+ enough, or must sign-up enforce it? Sign-up has no age check today | Lawyer | At minimum add a required "I am 21 or older and accept the Terms" checkbox on `signup.html` before checkout launches — cheap, and it makes the Terms actually accepted rather than only posted |
| 5 | 5 Account | No self-serve account deletion exists. What is the process and response time? | Owner | Manual deletion via the contact page, completed within 30 days (inside the CCPA 45-day and GDPR one-month windows). Build a self-serve button later |
| 6 | 6 Beta | Do beta members get anything when paid plans launch (founding rate, notice, nothing)? | Owner + lawyer | Promise **notice only** in the Terms (e.g. 30 days' email before any beta feature becomes paid). Make any founding-member rate an offer at launch, not a Terms obligation |
| 7 | 7 Pro | Price and billing periods | Owner (L3, CRITICAL_GATES item 7) | Owner's stated range: ~$9.99–11.99/mo, ~$79–99/yr. Note `pricing.html` FAQ currently says "around $10–15 a month" — reconcile the two before launch |
| 8 | 7 Pro | Free trial? None exists in code | Owner | "There is no free trial" — the whole product is free during beta, which already serves that purpose |
| 9 | 7 Pro | Refund policy. Nothing in the system issues refunds | Owner + lawyer | No refunds for partial periods (cancel keeps access to period end, which is already implemented), discretionary refund on request within 7 days of a first charge, and always where the law requires one. Say refunds are handled manually |
| 10 | 7 Pro | Founding-member rate — for life or a term; what happens on lapse and resubscribe? | Owner | If offered: locked while the subscription stays continuous; lost on lapse. Simple to explain and to implement with a Stripe price id |
| 11 | 7 Pro | Notice period for price changes | Owner + lawyer | 30 days by email, effective at the next renewal |
| 12 | 7 Pro | Taxes — included or excluded, who collects | Lawyer | Prices exclusive of tax; use Stripe Tax if counsel says collection is required in any state served |
| 13 | 10 Acceptable use | May people quote or screenshot CFL figures with credit? | Owner | Yes, for personal and editorial use with credit and a link. It is free distribution for a research brand |
| 14 | 11 IP | Is any code (e.g. `edges.js`, `market.js`) open source? No licence file exists | Owner | Keep "no licence granted" for now. `edges.html` calls `edges.js` "open-source"; either add a licence (MIT) to that file or soften that word on the archive page |
| 15 | 11 IP | Entity that owns the IP | Owner + lawyer | Same answer as #1 |
| 16 | 14 Liability | Liability cap | Lawyer | Greater of fees paid in the prior 12 months or US$50 (drafted that way) |
| 17 | 14 Liability | Indemnity clause? How should liability treat the fact that users act financially on published prices? | Lawyer | Include a narrow indemnity for misuse only. The "no picks, prices not live, check the sportsbook" facts in section 3 are the substantive protection; keep them prominent |
| 18 | 15 Termination | What does a paying member get if CFL closes their account without a breach? | Owner + lawyer | Pro-rata refund of the unused paid period |
| 19 | 16 Changes | Notice period for material changes | Owner + lawyer | 30 days by email for account holders; on-site notice for everyone |
| 20 | 17 Disputes | Governing law | Lawyer | The state where the entity in #1 is formed (Tennessee if the LLC is confirmed). Do not infer it from the helplines on `disclaimer.html` — `PROPOSED_WORDING.md` flags those as unverified |
| 21 | 17 Disputes | Venue / courts | Lawyer | Courts of the county of the entity's principal place of business |
| 22 | 17 Disputes | Arbitration and class-action waiver? | Lawyer | Not at launch, unless counsel recommends it. They add consumer-law complexity (mass-arbitration fees, state carve-outs) for a product with no revenue yet |
| 23 | 18 General | Boilerplate (entire agreement, severability, assignment) | Lawyer | Confirm as drafted |

### Privacy draft (`legal-review/privacy_draft.html`)

| # | Section | Question | Who | Recommended answer |
|---|---|---|---|---|
| 24 | 2 Plausible | Verify "no cookies, no cross-site tracking, no stored IP" against Plausible's current DPA | Lawyer | Check, then keep — it matches Plausible's published description, but it is their claim. Sign Plausible's DPA if not already done |
| 25 | 2 Counter | "Anonymous" or "pseudonymised" for `funnel_events`, given a per-session code exists? | Lawyer | Likely "pseudonymised" under GDPR while the session code exists; "de-identified" is the CCPA term. The facts in the draft are exact either way |
| 26 | 2 Account | Must the policy say operators can technically reach the database? | Lawyer | Yes, one sentence: "people who operate CFL can access the database to maintain it, and do not look at your saved data for any other reason" |
| 27 | 2 Browser storage | Does ePrivacy require consent for the last-visit date / session code in local and session storage? | Lawyer | The sign-in session is strictly necessary. The analytics items likely need consent for EU/UK visitors, or should be switched off for them. Cheapest fix if needed: stop writing `cfl_last_seen` and lose the `return_visit` event |
| 28 | 3 Providers | DPA references, lawful basis, or links to each provider's policy? | Lawyer | Add a link to each provider's privacy policy in the table; DPAs on file, not printed |
| 29 | 3 Providers | Is Resend already sending alert emails? | Owner | Check whether `RESEND_API_KEY` is set for `alerts.yml`. If it is, change "not sending yet" for alerts. The Card Brief stays blocked in code (T-090) either way |
| 30 | 5 Retention | Retention periods. No deletion job exists for `funnel_events` or contact messages | Owner + lawyer | `funnel_events`: 13 months, then build the prune job before the policy says so. Contact messages: 12 months (set in Formspree). Accounts: until deletion request. Do not publish a period that is not implemented |
| 31 | 6 Rights | No self-serve deletion or export | Owner | Same as #5: manual, within 30 days |
| 32 | 6 Rights | Which regimes actually apply (CCPA/CPRA, GDPR, UK GDPR, state laws)? Lawful basis per use? | Lawyer | CCPA thresholds are unlikely to be met yet; keep the rights language universal anyway. If EU/UK visitors are served, a lawful-basis line per use is needed |
| 33 | 8 Transfers | Correct transfer mechanism (the live "by using the site you consent" is weak) | Lawyer | Rely on providers' Standard Contractual Clauses / Data Privacy Framework certification; say so |

---

## What the privacy draft drops from the live `privacy.html`, and why

Each of these is stated on the live page today and is **not true** of the site
as built. They should be corrected when the draft is approved, and they are
the strongest argument for approving it promptly:

1. **"We use cookies for analytics and to make affiliate links work."** CFL sets
   no cookies (sign-in uses local storage; Plausible is cookieless), and the
   site carries no affiliate links (`disclaimer.html` §5 says so).
2. **"remembering whether you have accepted the cookie banner"** and **"opt out
   … through the cookie banner on first visit"**. There is no cookie banner.
3. **Affiliate tracking cookies and sportsbook referral data sharing.** No
   affiliate links exist; nothing is shared with any sportsbook.
4. **"our analytics provider records … your IP address (truncated where
   possible)"**. Plausible states it does not store IP addresses at all (it
   uses them transiently for location and unique-visitor counting). Our own
   counter stores no IP. The city-level location claim is consistent with
   Plausible and is kept.
5. **"Analytics data is retained in aggregated form for up to 24 months"** and
   **"Contact-form messages … up to 12 months"**. No such deletion is
   implemented.
6. **"We do not collect data from anyone we know to be under 13"** sits beside a
   21+ rule. The draft states 21 consistently.
7. **The live page does not name any processor** — Plausible, Supabase,
   Formspree, Google Fonts, jsDelivr or GitHub Pages. That is the T-054 gap.

## Related, outside these drafts (flagged, not changed)

- `disclaimer.html` §2 still says "a 62% favorite under our model" — model
  language on a legal page, exempted in `tests/no-model-on-public-surfaces.test.js`
  pending owner wording. Suggested replacement: "A fighter the market prices as
  a 62% favourite still loses about 38% of the time."
- `disclaimer.html` names Tennessee REDLINE and the Tennessee Sports Wagering
  Council. `PROPOSED_WORDING.md` flags both as unverified; keep that open until
  #1 and #20 are settled.

## To publish, once approved

1. Resolve every highlighted placeholder (`class="ph"`) in both files.
2. `terms.html`: remove the draft banner, set robots to `index, follow`, add it
   to the footer in `_shared.js::renderFooter` and to `build/prerender.js`'s
   page list, and link it from `signup.html`.
3. Replace the body of `privacy.html` with the approved draft (drop the
   `<base href="/">` line and the draft banner), then delete the draft file.
4. Update `tests/legal-drafts.test.js` in the same pull request.
5. Only then remove T-048 and T-054 from `entitlements.js::CHECKOUT_BLOCKERS` —
   as part of T-066, in the reviewed pull request that turns checkout on.
