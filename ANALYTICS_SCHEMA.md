# Funnel analytics — the event schema

Status: **instrumented 2026-09-21** (T-047). Fifteen of the nineteen events
emit today; the other four are declared hooks with nothing to fire on yet, and
the table below says which is which. Storage is
[`funnel_events_migration.sql`](funnel_events_migration.sql); the emitter is
`cfl.track` in `_shared.js`; `tests/analytics-events.test.js` holds the three
rules.

## The rule that comes first

**No NEW third-party analytics vendor is added without an owner decision.** A
vendor script is a third party reading every page view of a gambling-adjacent
site, and that is a privacy commitment, not a build step.

**Correction, 2026-09-21.** This section previously implied no vendor existed.
One already did: **Plausible** (`plausible.io/js/script.js`) has been loaded on
25 of the 30 root pages, and was there before this document was written. The
five without it are the two redirect stubs, `lab.html`, `reset.html` and
`unsubscribe.html`. So the choice was never "vendor or no vendor" — it was
whether to add a second one, and the answer is no.

**A gap that came with that discovery: `privacy.html` does not name Plausible.**
A third-party processor runs on every page and the privacy policy does not
disclose it. That is a compliance gap, not a preference, and the wording of a
privacy policy is an owner-and-lawyer decision under
`coordination/CRITICAL_GATES.md` item 9 — so it is queued as **T-054** with
draft wording, not shipped quietly.

## What we actually need to answer

Nine questions, in order. The event list exists to answer these and nothing
else; an event that answers none of them does not get added.

1. Where did the visitor land?
2. Did they reach Card Lab?
3. Did they open a fight?
4. Did they interact with Market Lab?
5. Did they subscribe to the Cannon Card Brief?
6. Did they come back during the same fight week?
7. Did they view pricing?
8. Did they begin checkout?
9. Did they pay?

## The events

One emitter, `cfl.track(name, props)`, in `_shared.js`. One name per row. Names
are `snake_case` and never change meaning — a renamed event is a new event.

Fifteen emit today. Four are **declared, not emitted** — marked below with the
reason. They are in the list and in the database's CHECK constraint so the
sprint that builds a checkout or a share button does not invent its own names.

| event | fires when | props |
|---|---|---|
| `landing_view` | first page of a session, whatever it is | `path`, `referrer_host`, `utm_source` |
| `card_lab_view` | the card section is scrolled into view on `/` | `event_id`, `fight_count` |
| `fight_opened` | Fight Lab opens, from any entry point | `fight_id`, `from` (`card`/`market`/`event`/`direct`) |
| `market_lab_view` | `/market.html` renders its board | `event_id`, `fight_count` |
| `book_breakdown_expanded` | a per-book row is expanded | `fight_id`, `book_count` |
| `market_sort_changed` | the board is re-sorted | `sort` |
| `factor_lab_view` | `/stats.html` renders | — |
| `methodology_opened` | any "how we calculate this" disclosure is opened | `surface`, `topic` |
| `fighter_page_view` | `/fighter.html` or an `/f/` stub | `fighter_id` |
| `event_page_view` | `/event.html` or an `/e/` stub | `event_id` |
| `best_price_clicked` | **declared, not emitted** — the best-price cell is not a clickable element. It becomes one only if there is somewhere to click, which is gated behind T-049 | `fight_id`, `book` |
| `fight_shared` | **declared, not emitted** — no share control exists on any page | `fight_id`, `channel` |
| `card_brief_signup_started` | the signup form is focused | `source` (which CTA) |
| `card_brief_signup_completed` | the insert succeeds | `source` |
| `pricing_view` | `/pricing.html` renders | — |
| `pro_cta_clicked` | any upgrade CTA | `source` |
| `checkout_started` | **declared, not emitted** — no checkout exists | `plan` |
| `checkout_completed` | **declared, not emitted** — no checkout exists | `plan` |
| `return_visit` | a session begins with a prior session inside 7 days | `days_since`, `same_fight_week` |

`landing_view` and `return_visit` fire from `cfl.trackSessionStart()` in
`_shared.js`, once per session, on every page. Everything else is wired at the
surface that owns it.

## What is deliberately not collected

- No email, name or user id in event props. `card_brief_signup_completed`
  records that a signup happened, never who.
- No IP address and no device fingerprint.
- No cross-site identifier, and no advertising pixel.
- No bet amounts, ever — `mybook.html` is a private utility and its contents
  never enter an event.

A session id is a random value in `sessionStorage`, regenerated per session and
never joined to an account.

## Avoiding double counting

- `fight_opened` fires once per Fight Lab render, not once per data load.
  Market Lab's row-expand is `book_breakdown_expanded`, which is a different
  question and must not also fire `fight_opened`.
- Prerendered `/f/` and `/e/` stubs redirect to the canonical page after
  ~120 ms. The stub does **not** emit; the page it lands on does, so one visit
  is one event.
- `landing_view` fires on the first page of a session only. Every page also has
  its own `*_view`; they are not substitutes for each other.

## Where the events go

**Two sinks, one emitter**, and the split is deliberate.

**`funnel_events`** (Supabase, applied 2026-09-21) is the one CFL owns.
`INSERT` for `anon` and `authenticated`; **no `SELECT` for either**, because an
analytics table a visitor can read back is a list of what every other visitor
did. Everything else — `SELECT`, `UPDATE`, `DELETE`, `TRUNCATE`, `REFERENCES`,
`TRIGGER` — is explicitly revoked. Counts are read through `v_funnel_daily`, an
owner-rights view that returns aggregates and never a row. This sink is what
answers *"did they come back during the same fight week"*, which a hosted
dashboard cannot without joining to our own card calendar.

**Plausible**, already present, receives the **event name only**. Custom
properties are a paid Plausible feature, and spending money is an L3 decision
that would otherwise get taken by accident through a props argument. Name only
costs nothing and gives an immediate dashboard.

If either sink is missing or throws, the other still fires and the page is
unaffected — `tests/analytics-events.test.js` asserts both directions.

### One thing the revokes taught us

On first apply, `anon` held `UPDATE` and `DELETE` on the new table. Not from
anything in the migration — a new table in `public` **inherits** broad grants
from Supabase's default privileges. RLS denied both (no policy means deny), so
nothing was exploitable, but that is one layer doing the work of two, and it
becomes zero layers the day someone adds a permissive `FOR ALL` policy. The
revokes are load-bearing. **Verify grants after applying; do not assume the
migration's own text describes the result.**
