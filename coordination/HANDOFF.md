# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `### Verified after merge, which the entry above could not promise

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

## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

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

