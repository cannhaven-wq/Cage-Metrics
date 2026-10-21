# Free / Pro boundary — CFL Owner decision A5 (2026-10-21)

**Nothing is enforced.** Billing is off, pricing is deferred (A3), and Stripe
is deferred (A4). This records the boundary so that, when a gate is built, it
matches the decision.

| what | tier | status |
|---|---|---|
| Current line movement (the last 14 days, chart included) | **Free** | approved |
| Line-movement history older than 14 days | **Pro** | approved |
| Every sportsbook's current price | **Free** | approved |
| Each sportsbook's historical prices | **Pro** | approved |
| Price- and movement-alert limits for Free and Pro | — | **deferred** |

**Where it lives.** `entitlements.js::SURFACES` (presentation only;
`enforced: false` on every row). The server gate, when it lands, goes through
`current_user_is_pro()`, as it always has.

**Not yet matching:** `research/commercial/t061_pro_gates.DRAFT.sql` drafts
a gate on the **whole** movement chart. Under this decision the gate must
cover only data older than 14 days. That gets fixed when T-061 is actually
built, after pricing. Nothing is applied in the meantime.
