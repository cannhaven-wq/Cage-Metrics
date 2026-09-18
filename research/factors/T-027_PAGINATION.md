# T-027 — why the published market-even cohort was short

**2026-09-18. Diagnosis and rerun procedure. No number in this document is a new
measurement, and `factor-rates.json` is unchanged by the work it describes.**

---

## The plain-English version

The Factor Lab reads its betting-odds rows from the database a thousand at a
time. It asked for them by position — "rows 1–1000", then "rows 1001–2000" — but
never told the database what order to put them in. The database is allowed to
answer in a different order each time it is asked. When it does, "rows
1001–2000" is a slice of a *different* list, so some rows are read twice and
others are never read at all.

The count still looks right, which is why nobody caught it. You get about the
right number of rows. They are just not the right rows.

---

## What is established, and what is not

**Established, from the code and the committed artifact:**

| | |
|---|---|
| `build/factor-rates.js` paged with `.range()` and **no `.order()`** | yes — four call sites |
| Those pages are **separate SQL statements** | yes — `build()` constructs a fresh query per page |
| Postgres guarantees row order across them | **no** |
| The scored-fight denominator matches FE-001 | **yes, exactly — 8,739 both** |
| The market-even numerator matches | **no — 869 published, 1,220 direct** |

**Not established, and not claimed:** that unstable scan order is the *sole*
cause, or that it accounts for the whole 869 → 1,220 gap. That cannot be settled
without running the corrected script against the database. See the rerun below.

## Why the defect is localised to the odds read

This is the part that makes the diagnosis more than a plausible story.

`factor-rates.json` records `fights_scored: 8739`. FE-001's independent SQL
counts **the same 8,739**. The scored population is built from `events`,
`fights` and `fighters`, and a fight is scored only if both fighters resolve and
a winner is set — so all three of those reads came back **complete**. The
market-even flag is computed from one further input and nothing else:

```js
even: oa != null && ob != null && oa >= -140 && oa <= 140 && ob >= -140 && ob <= 140
```

where `oa` / `ob` come from `closeOf()`, which reads only the `fight_odds`
array. Same denominator, same ±140 band, same `is_closer = true` filter, same
median-across-books rule as FE-001. **The only input that can move the numerator
is the odds read**, so a definitional difference is ruled out and the loss is
confined to that one fetch.

### Why that read and not the other three

`fight_odds` is the only one of the four that is **large and filtered**:
~110k rows narrowed by `.eq('is_closer', true)` to ~16k, across sixteen
requests. The others are small unfiltered selects, where a plain sequential scan
returns the same physical order run after run — consistent with their counts
being exact. A large filtered scan is where the planner may go parallel, and a
parallel sequential scan hands blocks to workers as they ask for them, so the
order genuinely differs between two executions of the identical query.

Duplicates matter as much as the misses here, and in a second way: a duplicated
row is pushed into `closeBook` twice, so it also skews the median across books
for that fighter.

### A mechanism considered and rejected as the main cause

`build/fetch-odds.js` UPDATEs `is_closer` (promoting and clearing flags), and
`odds.yml` wakes every five minutes, so the predicate being paged **is** mutated
while the read runs. Under OFFSET paging that shifts every later page.

It is real, and it is **too small to be the main cause**: the promotion only
touches fights inside `CLOSER_LOOKBACK_DAYS` of their bell — a handful of recent
cards, not the ~2,500 rows the gap implies. Recorded because it is a second,
independent reason the fix must be keyset rather than merely ordered.

## The fix, and why keyset rather than `.order()`

Adding `.order('id')` would fix the unstable-order half and leave the
concurrent-write half: with OFFSET, a row inserted or a flag flipped ahead of
the cursor still shifts every later page. `fight_odds` is append-only and
written every five minutes, so that is a live race, not a theoretical one.

Keyset paging — order by a unique ascending key, ask for rows strictly greater
than the last one seen — defines each page by **data** rather than by position,
and is immune to both. Implemented in [`build/paginate.js`](../../build/paginate.js).

It requires a unique key that is actually selected, so `id` was added to the
`fight_odds` select list. The paginator **throws** if the key is absent or
non-unique rather than returning a short result — silent truncation is the bug
being removed, so it is not an acceptable failure mode for the fix.

Regression coverage: [`tests/factor-rates-paging.test.js`](../../tests/factor-rates-paging.test.js),
10 assertions, no network and no key. It reproduces the old algorithm against a
planner that reorders per statement and shows it losing and duplicating rows,
then shows keyset returning every row exactly once against the same and a worse
order. Verified to bite: restoring `.range()` fails it.

---

## The authoritative rerun

**Not run here.** This environment has no credentials and no egress — the agent
proxy refuses `CONNECT` to `*.supabase.co` with a 403, and `fight_odds` has no
`SELECT` policy for `anon` in any case.

### Environment

| var | value | why |
|---|---|---|
| `SUPABASE_SECRET_KEY` | the project's `service_role` / secret key | **required.** `fight_odds` has no `anon` SELECT policy; the publishable key returns zero rows, and the script hard-fails rather than publish an empty market column |
| `SUPABASE_URL` | optional | defaults to the project URL already in the script |

`SUPABASE_SERVICE_ROLE_KEY` is accepted as a fallback name.

### Command

**Preferred: the validation workflow.** It already holds the service key as an
Actions secret, has egress, and cannot write to the repository.

```
Actions -> "Factor Lab validation (manual, publishes nothing)" -> Run workflow
```

It prints the comparison to the run summary and uploads the candidate as an
artifact. Nothing is committed.

**Locally**, if you have the key and egress:

```bash
cd build
npm ci
SUPABASE_SECRET_KEY='<secret key>' npm run factor-rates
```

It prints the two lines that settle this before it writes anything:

```
  events=… fights=… fighters=… closing-odds rows=…
  scored matchups=…  market-even cohort=…
```

### What to compare, and against what

The pre-fix values, from the artifact committed at `2026-09-18T15:30:30Z`:

| | published (pre-fix) | FE-001 direct SQL | corrected run |
|---|---|---|---|
| `fights_scored` | 8,739 | 8,739 | **must still be 8,739** |
| `market_even_cohort` | 869 | 1,220 | ? |

**`fights_scored` is the control.** It was already correct, so if it moves, the
fix changed something it should not have and the run should be treated as
suspect rather than published.

Then diff every factor verdict with the committed comparison script:

```bash
# from the repo root, BEFORE regenerating
git show HEAD:factor-rates.json > /tmp/before.json

# ... run the regeneration above ...

node build/compare-factor-rates.js /tmp/before.json factor-rates.json
```

It prints the dataset deltas, every bucket whose **verdict** moved, and every
bucket that changed **sample size without** changing verdict — the second list
matters, because a bucket that gained 40% more fights and kept its verdict is
still a different measurement. It exits non-zero if any verdict moved, so it can
gate a publish step rather than merely inform one.

It also calls out `fights_scored` moving, which should not happen.

### FE-001's prediction, to be confirmed or refuted

If the cohort corrects to ~1,220, FE-001 expects at least these to move:

| factor | before | after |
|---|---|---|
| UFC-record headline | `lean` | **`real`** |
| age 7–9 band | `real` | **`lean`** |
| takedown-defence 20–30 band | `unproven` | `proxy` |

A verdict moving *down* (age 7–9) matters as much as one moving up. If the
corrected run does not reproduce these, the paging hypothesis is not the whole
story and the remaining gap needs its own investigation.

---

## Publishing is now a separate, deliberate act

**This section used to say that merging the fix was itself the publish action.
That was true when it was written and is no longer true.** It is corrected here
rather than deleted, because the reasoning is the reason the gate exists.

**What it said.** `prerender.yml` ran `npm run factor-rates` on a 6-hour cron
with a service key and committed `factor-rates.json` to `main`. So merging the
reader fix would not merely have permitted a corrected run — within six hours it
would have *performed* one, unattended, and published the resulting verdicts to
`stats.html` with nobody having looked at them.

**What changed.** The publish gate landed first, deliberately ahead of this fix:

- `prerender.yml` no longer regenerates the Factor Lab and no longer stages
  `factor-rates.json`. It still does stubs, sitemap and feed on the same cron.
- [`factor-rates-validate.yml`](../../.github/workflows/factor-rates-validate.yml)
  is manual only, runs under `permissions: contents: read` — so the token it is
  handed **cannot write to the repository** — and produces a candidate artifact
  plus a comparison, committing nothing.
- `tests/publish-gate.test.js` keeps it that way.

**So the sequence is now:** merge the reader fix → run the validation workflow
by hand → read the comparison → decide. Merging changes what a *future*
regeneration would compute; it no longer performs or publishes one.

**`factor-rates.json` therefore goes stale** until someone refreshes it on
purpose, and publishing a reviewed candidate is a deliberate commit in a pull
request where the moved verdicts appear in the diff. That is still gate #8 and
still the owner's — it is simply no longer something a merge can do by accident.

## The corrected run — 2026-09-18, and it confirms the diagnosis

Run through
[`factor-rates-validate.yml`](../../.github/workflows/factor-rates-validate.yml)
on `main` at `71ec020d`
([run 35377644563](https://github.com/cannhaven-wq/Cage-Metrics/actions/runs/35377644563)).
**Nothing was published.** The job ended with *"Clean: the published
factor-rates.json is untouched."*

Recorded here because the workflow artifact expires in 30 days and a log is not
an evidence base.

### The headline

| | published | corrected |
|---|---|---|
| `fights_scored` | 8,739 | **8,739** |
| `market_even_cohort` | 869 | **1,220** |

**The control held.** `fights_scored` was correct before the fix and is
unchanged by it, which is what distinguishes "the reader was dropping odds
rows" from "the change moved something it should not have".

And the corrected cohort is **1,220 — exactly the figure FE-001 reached by
querying the database directly.** Two independent routes to the same number,
one of which never touched this script. The pagination hypothesis is no longer
a hypothesis.

### Verdicts that moved: 7

| factor / bucket | before | after | market-even n | rate |
|---|---|---|---|---|
| `ufc_record` / headline | `lean` | **`real`** | 136 → 185 | 55.1% → 58.4% |
| `ufc_record` / factor verdict | `lean` | **`real`** | — | — |
| `age` / 7–9 years younger | `real` | **`lean`** | 151 → 201 | 58.9% → 56.7% |
| `reach` / 6+ inches longer | `unproven` | `proxy` | 77 → 114 | 58.4% → 54.4% |
| `southpaw_reach` / when it fires | `unproven` | `proxy` | 77 → 103 | 49.4% → 49.5% |
| `southpaw_reach` / factor verdict | `unproven` | `proxy` | — | — |
| `td_def` / 20–30 point edge | `unproven` | `proxy` | 84 → 121 | 51.2% → 51.2% |

FE-001 predicted three of these — `ufc_record` up, `age` 7–9 down, `td_def`
20–30 out of `unproven` — and all three landed, in the predicted direction, at
close to the predicted samples. The other four were not predicted and are new.

**A verdict moved DOWN as well as up.** Age's 7–9 band loses its `real` status
on a 33% larger sample. A correction that only ever flattered us would be the
suspicious kind.

28 further buckets changed sample size without changing verdict — every one
gaining roughly 30–40%, which is the shape you would expect if the reader had
been dropping odds rows roughly uniformly rather than in one region.

### ⚠ The finding that needs the most care before anything ships

**`ufc_record` becomes `real` — and that is not the factor FE-001 found dead.**

They are different measurements that both get called "record" in conversation:

| | Factor Lab `ufc_record` | FE-001's `edges.js` record |
|---|---|---|
| Record used | **UFC-only** | **professional, whole career** |
| Quantity | raw win-rate gap | Laplace-smoothed `(w+2)/(w+l+4)` |
| Bands | 10 / 15 / 22 / 30 points | 0.08 / 0.15 / 0.25 / 0.40 |
| Corrected market-even result | **58.4%, `real`** | **50.2%, a coin flip** |

So publishing this candidate would put a `real` verdict on a record factor on
`stats.html` in the same week FE-001 concluded the record factor the product
actually ships is market echo. Both can be true — they are different
definitions — but a reader will not make that distinction on their own, and
`CLAUDE.md`'s standing rule is that a UFC bettor with no stats background must
be able to follow it.

**Consequences if the candidate is published as-is:**

1. `CLAUDE.md`'s line *"Only age currently survives market control"* becomes
   false and needs correcting in the same change.
2. `stats.html` would assert that UFC record predicts winners under market
   control — a **new public performance claim**, gate #8 in its own right, not
   merely the restoration of a correct old one.
3. The distinction between the two record factors would have to be visible on
   the page, or the site contradicts its own research artifact.

None of that is an argument against publishing. It is an argument against
publishing it as a routine refresh.

## Not fixed here

The same OFFSET-without-order pattern is in `build/prerender.js:37`,
`build/send-digest.js:261` and `build/fetch-odds.js`. `prerender.js` pages
`fighters` and `events` to build the SEO stubs, so the same instability would
show up as missing or duplicated stubs rather than as a wrong number.

Deliberately left alone: T-027 is scoped to the measurement defect, and
`build/paginate.js` is now available to whatever picks the rest up.
