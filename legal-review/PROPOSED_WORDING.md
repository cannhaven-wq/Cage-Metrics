# Proposed wording for founder / legal review — NOT production copy

**Status: draft for review. Nothing in this file is published anywhere.**

This file exists because two compliance gaps block checkout, and because
drafting legal language straight into a live page is exactly the wrong way to
close them. `coordination/CRITICAL_GATES.md` item 9 makes legal and compliance
choices the owner's, and the wording below needs a lawyer's eye, not a model's.

Both items are **checkout blockers**: they must be resolved before CFL takes a
payment, not after.

| id | gap | blocks |
|---|---|---|
| [T-054](../coordination/TASK_QUEUE.md) | `privacy.html` does not name Plausible, a third-party processor running on every page | checkout |
| [T-048](../coordination/TASK_QUEUE.md) | No Terms of Service page exists at all | checkout |

---

## T-054 — Privacy: naming the analytics processors

### The factual position, which is checkable

- **Plausible Analytics** (`plausible.io/js/script.js`) loads on 25 of the 30
  root pages. It has done so since before the September 2026 repositioning —
  this was not introduced by recent work, it was *discovered* by it. It is
  cookieless and does not track across sites, per Plausible's own product
  description; **that claim is theirs and should be verified against their
  current DPA rather than taken from this file.**
- **`funnel_events`**, CFL's own table, records anonymous counts. What it stores
  is enforced in code and schema, not merely promised: `cfl.track` strips prop
  keys matching email / name / user id / token / IP / phone / stake / amount /
  wager / bankroll, and the table constrains `props` size, `session_id` length
  and the event name. `session_id` is a per-session random value in
  `sessionStorage`, never joined to an account. See
  [`funnel_events_migration.sql`](../funnel_events_migration.sql) and
  [`ANALYTICS_SCHEMA.md`](../ANALYTICS_SCHEMA.md).

### Draft clause

> **Analytics.** We use Plausible Analytics to measure how many people visit
> Cannon Fight Lab and which pages they use. Plausible is a third-party service
> that processes this information on our behalf; it does not use cookies and
> does not follow you to other websites.
>
> We also keep our own anonymous record of which pages and features are used, so
> we can tell which parts of the site are worth building on. Those records
> contain no email address, no name, no account identifier and no IP address,
> and they are not linked to your account or to anything you have saved on the
> site.

### What a lawyer needs to decide, and we cannot

1. Whether naming the processor is sufficient, or whether a jurisdiction that
   applies to CFL's visitors requires more — a lawful basis, a retention period,
   a data-processing agreement reference, or a cookie/consent banner despite
   Plausible being cookieless.
2. Whether "anonymous" is the correct legal term for the `funnel_events` rows,
   or whether "pseudonymised" is required given a per-session identifier exists.
   **This is a legal characterisation, not a technical one, and the difference
   matters.** The technical facts are above; the label is not ours to pick.
3. Whether a retention period must be stated, and what it should be. No prune
   job exists yet — the table is deliberately prunable, and a stated period
   would need one built to match it.
4. Whether the existing `privacy.html` needs restructuring rather than one added
   clause.

---

## T-048 — Terms of Service

### The factual position

There is **no Terms of Service page**. `privacy.html` and `disclaimer.html`
exist; `disclaimer.html` already carries UFC non-affiliation, a 21+ statement,
responsible-gambling helplines and an affiliate disclosure. A Terms page is
normally expected before an account can be charged.

### What CFL actually does, as input for drafting

Facts a drafter needs, all verifiable in this repo:

- CFL is a **research and analytics publication**. It publishes sportsbook
  prices with provenance and timestamps, vig-free consensus, market movement,
  matchup comparisons and historical factor testing.
- **CFL does not publish predictions, picks or betting advice.** The forecasting
  engine was removed from every public surface in September 2026 (D-011) because
  testing could not show its disagreement with the market was worth acting on.
  The historical record of that failure is kept in public on the Model Archive.
- **CFL makes no representation that a user will profit**, and no claim to beat
  the market.
- Prices shown are **last captured, not live**, and always carry their age and
  their source count. Users are told to check the sportsbook before acting.
- **Best price ordering is mechanical** — the American number and nothing else.
  No sportsbook can pay for placement. If affiliate arrangements ever exist,
  that ordering does not change (T-049 must be resolved before any affiliate
  link ships).
- Accounts exist; during beta every account holder has premium access. **No
  payment is taken today.**
- Users can store their own bet records in My Book. That data is theirs and is
  protected per-row in the database.

### What a lawyer needs to decide

1. Governing law and jurisdiction, and whether CFL's activity requires any
   gambling-adjacent registration or disclosure in the jurisdictions it serves.
   **Do not assume a jurisdiction from the helpline numbers already on
   `disclaimer.html`** — those were not verified by this work, and the Tennessee
   REDLINE reference should be checked against where CFL actually operates and
   who it actually serves.
2. Subscription terms once Pro exists: billing period, renewal, cancellation,
   refunds. None of this is decided (`PRODUCT_BOUNDARY.md` deliberately leaves
   price and billing open) and all of it is L3.
3. Limitation of liability, and how it interacts with the fact that CFL
   publishes numbers users may act on financially.
4. Whether age-gating must be enforced rather than stated.
5. Whether the beta premium grant creates an obligation when paid tiers launch —
   grandfathering is explicitly undecided.

---

## What was deliberately NOT done

- **No legal language was written into any production page.** `privacy.html`,
  `disclaimer.html` and every other live surface are untouched by this file.
- **No helpline number, regulator name or jurisdiction claim was invented or
  copied from an audit report.** Where such a claim already exists on
  `disclaimer.html`, this file flags it for verification rather than reusing it
  as though it were verified.
- **No retention period was asserted**, because none is implemented.
