# Handoff

The live baton. Newest entry at the top; keep the last three, drop the rest —
git history holds the others.

Every entry carries **From**, **To**, **Date**, and a `## Next action` that
names something specific enough to start on without asking a question back.
"Continue the work" is not a next action.

Whoever writes an entry updates [`STATE.md`](STATE.md) in the same commit.

---

## 2026-09-18 — CI: the test suite now actually runs, and it is bigger than `tests/`

**From:** Claude
**To:** ChatGPT → Owner
**Date:** 2026-09-18

**No migration applied. No production write. No CLV published. No paid API call.**
No `fight_odds` row read, deleted or rewritten. This session made no database
call of any kind and no network call beyond git, PyPI and the GitHub API.

### What landed

| # | what | where |
|---|---|---|
| 1 | `.github/workflows/tests.yml` — the whole suite on every push and pull request | T-010, **done** |
| 2 | the read-only audit that found the gap | [`reviews/2026-09-18-claude-ci-audit.md`](reviews/2026-09-18-claude-ci-audit.md) |
| 3 | the engine dependency set, unpinned and recorded rather than quietly widened | T-011, **queued** |

**The finding, in one line: seventeen test modules existed and no workflow ran
any of them.** The only test invoked anywhere in `.github/workflows/` was one
`unittest` module inside `event-flow.yml`. Everything passed; nothing was
checking. For a frozen-file hash check, a publication gate and the L3 gate, a
tripwire nobody pulls is decoration.

Measured on this commit: `624 passed, 4 skipped, 4557 subtests passed` for
Python, `31` and `40` for the two Node files.

### `tests/` was not the whole suite, and the first draft only ran `tests/`

The workflow's first draft ran `pytest tests/` and reported 168 passing tests.
The repo has **624 across seventeen modules**; the other 456 live under
`cfl_engine/` and `research/` and are the ones guarding the frozen model path —
`test_lock_prop0002.py`'s conformance proof that DUR-002 is collecting against,
the CLV-001 scorer, the event-flow card resolution, the integrity checks.

A green tick over an untested engine is worse than no tick, because people
believe it. The workflow now runs `pytest` from the repo root, which needs
`cfl_engine/requirements.txt` installed: three modules reach
`cfl_engine/engine.py`, which imports numpy and pandas at module scope, and
without the wheels eight tests fail on `ModuleNotFoundError` — a red suite that
is really a missing install.

### What ChatGPT's review corrected, and what it got

Four items came back on PR #22. All four are addressed:

1. **The T-010 claim was false when written.** The pull request said T-010 was
   tracked in `TASK_QUEUE.md` and it was not — `main` ended at T-009 and the
   branch did not touch the queue. Fixed by making the claim true rather than by
   deleting it: T-010 is now a row, with a note, and T-011 alongside it.
2. **The dated audit did not exist.** Now written, under the existing reviews
   convention.
3. **Stale base.** Rebased from `1e0c3d3` onto `0c89b21` (the prerender
   auto-commit), zero conflicts, the whole suite rerun green on the new base.
4. **Unpinned `pytest`.** Now `pytest==9.1.1`, the version the green run was made
   on. An unbounded install lets a runner-side change turn the build red with no
   repo change behind it, and a build that reddens for reasons nobody caused is a
   build people stop reading.

### Three claims in my own pull request text that were wrong

Worth listing, because two of them were safety claims and the third is the kind
of number `CLAUDE.md` says not to write down.

1. **"No network and no database."** Half right. `tests/test_sql_behaviour.py`
   *does* use a database — a throwaway cluster it builds itself with `initdb` on
   a unix socket in a temp directory, torn down afterwards, never reading
   `SUPABASE_DB_URL`, skipping where `initdb` is absent. `ubuntu-latest` ships
   PostgreSQL, so those tests run in CI rather than skipping.
2. **One test in the repo talks to production.**
   `cfl_engine/dur001/test_dur001.py` holds a test that posts SQL to the Supabase
   **management API** for the live project — carefully, as a DO block that rolls
   the whole transaction back, but it is a production write path, and the
   repo-root pytest run now contains it. It is gated on `SUPABASE_ACCESS_TOKEN`
   and this workflow passes no secrets, so it skips. **That is load-bearing.**
   Adding a secret to `tests.yml` would make every pull request, fork ones
   included, a production write. The workflow header now says so beside the
   reason `contents: read` is enough.
3. **A subtest count written as a constant.** The body quoted `4,237`; the count
   moves with the data the suites walk. It is now written as a dated reading.

The security claim survives (1) and (2) intact. The sentences carrying it did
not, and have been replaced with ones that are true.

### What was deliberately left alone

`cfl_engine/requirements.txt` carries `>=` ranges for all eight of pandas, numpy,
scikit-learn, scipy, statsmodels, pyarrow, xgboost and tabulate, and the CI job
installs it as written. So the suite can still go red on somebody else's release
— the same failure the `pytest` pin prevents, left standing on the larger half of
the dependency set.

Not fixed here on purpose: that file is the **engine's** manifest, shared with
the jobs that run the model. Narrowing it is a change to the engine's runtime,
not to CI, and it should land with a run behind it rather than as a line slipped
into a CI pull request. Likely a CI-only constraints file. **T-011**, queued, not
started.

`HANDOFF.md` was also trimmed to the last three entries, which is what the top of
this file has always instructed and what the previous two handoffs did not do.
Git history holds the rest.

## Next action

**ChatGPT:** T-011 — say whether the CI Python job should install from a
CI-only constraints file pinning the eight engine packages, or whether
`cfl_engine/requirements.txt` itself should be narrowed. The second choice
changes what the model runs on, which is why it is not mine to pick.

**Owner:** nothing new. The two live asks are unchanged and both predate this
session — remove or disable the second Railway backfill service (the last
precondition on the immutability migration), and T-009, which name the
governance records should carry.

---

## 2026-09-17 — consolidation: three merges landed, CLV-001 rebased and held

**From:** Claude
**To:** Owner → ChatGPT
**Date:** 2026-09-17

**No migration applied. No production write. No CLV published. No paid API call.**
No `fight_odds` row deleted or rewritten, here or anywhere. Every database call
made in this session was read-only.

### What landed

Consolidation in a fixed order, each step verified on the remote before the next
began — not merely committed locally.

| # | what | result |
|---|---|---|
| 1 | PR #14 — DUR-002's first collection | merged, `1a5cf890` |
| 2 | PR #15 — the `coordination/` layer | merged, `934721ba` |
| 3 | odds scrapper retirement | merged, `cage-metrics-odds-scrapper@af54180` (PR #1) |
| 4 | PR #16 — CLV-001 v1.0.10 | rebased onto the new `main`, **held unmerged** |

**Step 1** put DUR-002's 48 prospective observations on `main`. Verified before
merge: `lock_prop0002.py`'s sha256 on `main` is byte-identical to the value
recorded in `registry.json` and the register.

**Step 2** put the coordination layer on `main` and wired it into `CLAUDE.md`.

**Step 3** is the one that was only ever a branch. `backfill_odds.py` is now
retired on `main`: it imports `sys` alone, holds no write verb, and exits
non-zero. Confirmed before merge that no workflow and no `nixpacks.toml` start
command invokes it.

**Step 4** rebased 19 commits onto the new `main` with **zero conflicts**, and
confirmed the rebase did not revert DUR-002 to `armed` — both branches edit
`research/registry.json` and only that check rules it out.

### What I corrected in the rebase

The coordination records were written before steps 1–3 landed and had gone stale:

- `STATE.md` — DUR-002 read "**armed**, zero observations". Now collecting, 48
  rows on 12 fights. **This was the load-bearing one**: `STATE.md` is the file
  `CLAUDE.md` tells every session to read first, and nothing cross-checks it
  against the research register, so it would have gone on being wrong silently.
- `CRITICAL_GATES.md` — same stale assertion in the read-only clause.
- `TASK_QUEUE.md` — T-001 **dropped**. It asked to automate a one-shot
  transition that has now happened; automation for it has no remaining value.
  Reason recorded rather than deleted.
- `FIGHT_ODDS_WRITER_INVENTORY.md` — the retirement is merged, not a branch.

### The Railway service is still open, and it is a gate

The odds scrapper's README describes a **second Railway service** whose start
command was overridden to `backfill_odds.py`. Railway config is not in git and
this session holds no Railway credential, so it cannot be confirmed from here.

Measured instead, read-only, to bound the risk: the backfill's last write sits
at `fight_odds.id ≤ 384002`, and the rows written immediately after it captured
at **2026-05-26T23:02:20Z**. It has not written in nearly four months, and as of
`af54180` it cannot write if invoked. That shows the service has not *run*. It
cannot show it does not *exist*.

**`proposed_2026-09-16_fight_odds_immutability.sql` stays gated on the owner's
dashboard check.** The other four migrations are additive and not gated on it.

## Next action

**Owner:** remove or disable the second Railway backfill service, and confirm —
that closes the last precondition on the immutability migration. PR #16 is
rebased, green and waiting on your word to merge; it was deliberately not
merged in this session.

**ChatGPT:** the migration application plan, for five migrations applied
deliberately and sequentially. Every one is still unapplied.

---

## 2026-09-16 — D-004: the legacy BFO backfill is retired

**From:** Claude
**To:** Owner → ChatGPT review
**Date:** 2026-09-16

**No migration applied. No production write. No CLV published. No paid API call.**
No `fight_odds` row deleted or rewritten, here or anywhere.

Two repositories:

| repo | commit | branch |
|---|---|---|
| `cage-metrics-odds-scrapper` | `d8e1908` | `retire/backfill-odds-2026-09-16` (pushed, **not merged** — it is not my default branch to push to) |
| `Cage-Metrics` | see below | `research/clv-001-revision` |

### The retirement

`backfill_odds.py` now prints a retirement notice and **exits non-zero**. It
holds no `delete`, `insert`, `update` or `upsert` — verified by grep after the
change, and by running it.

Non-zero is the deliberate part. A scheduler that read a silent success would go
on calling it forever and nobody would learn it had been retired.

The docstring carries the full reasoning rather than a one-line "retired":
what it did, the R-01 clause it collides with, the fact that its
delete-before-insert was *the* mechanism of its idempotency, and — for whoever
wants the capability back — that the append-only replacement appends a second
observation and resolves by `(observed_at DESC, id DESC)`, the pattern
`fight_bout_completions` already uses. The implementation is preserved in git
history at `1ad1aa6`.

### No automation referenced it

Checked before changing anything:

- `.github/workflows/` — three workflows, running `polymarket/backfill_history.py`,
  `polymarket/probe_history.py`, and the nightly model-training loop. None
  mentions it.
- `nixpacks.toml` — `[start] cmd = "python odds_scraper.py"`.
- No `Procfile`, no `railway.json`/`railway.toml`.
- The only references anywhere were **documentation**: two in `README.md` and one
  comment in `backtest_queries.sql`. All three updated.

**One thing I cannot verify.** The README described a *second Railway service*
whose start command was overridden to `backfill_odds.py`. Railway configuration
is not in git. If that service still exists it will now exit non-zero with the
notice instead of deleting anything — loud and harmless — and it should be
removed. Flagged in the README and the inventory.

### Nothing scorable was lost

BFO publishes the price but not when it was observed, so the script stamped
`captured_at` as the Unix epoch *by design* — the source comment reads
"placeholder; opener time isn't precisely known". R-13 excludes every such row
from scoring permanently; they are the bulk of the 30,724 it names. The rows it
already wrote are untouched and still feed `model/v5`, `model/v6` and the rest,
which read opener/closer prices without needing a capture instant.

### Cage-Metrics side

- **`CLAUDE.md`** — `cage-metrics-odds-scrapper` added to the related-repos
  list, named as the main writer to `fight_odds`, linked to the inventory.
- **`FIGHT_ODDS_WRITER_INVENTORY.md`** — status block at the top: no known
  repository-based writer conflict remains. The blocker is left described in
  full rather than deleted; a retired conflict nobody can read the reasoning for
  is one somebody re-creates.
- **`DECISIONS.md`** — **D-004**, quoting the owner, recording that the repo
  change is revertible and the rule it protects is not: a ledger that has been
  append-only and then is not was never append-only.
- **`STATE.md`**, **`HANDOFF.md`** — this.

### Tests

| suite | result |
|---|---|
| `tests/` (repo, incl. static migration + Postgres behavioural) | **171 passed**, 3 skipped |
| `cfl_engine/clv/` | **200 passed** (`test_scoring` 167 + `test_devig` 33) |
| `build/test-fetch-odds.js` (Node) | **66 passed** |

**437 total, all green.** No CLV-001 code changed in this pass. Still locally
reported.

### Where this leaves the migration

`proposed_2026-09-16_fight_odds_immutability.sql` has **no known
repository-based writer conflict**. It remains unapplied, with the other four.

## Next action

**ChatGPT:** the migration application plan.

**Owner:** merge `retire/backfill-odds-2026-09-16` in the odds scrapper (pushed
as a branch, not to `main`), and check whether the second Railway service still
exists.

---
