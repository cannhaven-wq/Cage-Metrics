# Funnel analytics — the event schema

Status: **specified, not yet instrumented.** Written 2026-09-21 as the design
[T-047](coordination/TASK_QUEUE.md) implements. Nothing on the site emits these
events today, and this file exists so that when something does, there is one
list rather than three.

## The rule that comes first

**No third-party analytics vendor is added without an owner decision.** A
vendor script is a third party reading every page view of a gambling-adjacent
site, and that is a privacy commitment, not a build step — `privacy.html` would
have to change with it. The default below uses infrastructure CFL already owns.

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
| `best_price_clicked` | a best-price cell is clicked | `fight_id`, `book` |
| `fight_shared` | a share control is used | `fight_id`, `channel` |
| `card_brief_signup_started` | the signup form is focused | `source` (which CTA) |
| `card_brief_signup_completed` | the insert succeeds | `source` |
| `pricing_view` | `/pricing.html` renders | — |
| `pro_cta_clicked` | any upgrade CTA | `source` |
| `checkout_started` | **future hook** — no checkout exists | `plan` |
| `checkout_completed` | **future hook** — no checkout exists | `plan` |
| `return_visit` | a session begins with a prior session inside 7 days | `days_since`, `same_fight_week` |

The last three are declared and not emitted. They are here so that the sprint
that builds checkout does not invent its own names.

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

The default is a `funnel_events` table in the Supabase project CFL already
runs: insert-only, RLS `INSERT TO anon, authenticated` with no `SELECT` for
either, read through a definer view that exposes counts and never rows. That
keeps the data in infrastructure the project already discloses, needs no new
vendor and no `privacy.html` change, and costs one table.

The alternative — a hosted, cookieless product analytics vendor — is easier to
query and is an owner decision, because it is a third party and a privacy
disclosure. It is not made here.
