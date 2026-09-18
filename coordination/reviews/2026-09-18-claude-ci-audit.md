# Read-only audit — are the repo's tests actually being run?

**From:** Claude
**To:** ChatGPT → Owner
**Date:** 2026-09-18
**Scope:** `.github/workflows/` and `tests/`, read-only.
**Task:** [T-010](../TASK_QUEUE.md)

> **What this audit is.** One question, asked because `coordination/` leans hard
> on tripwires: a frozen-file hash check, a publication gate, an L3 gate. Those
> only work if something pulls them. So — does anything?
>
> **Nothing was changed while auditing.** No migration, no production write, no
> database call of any kind, no network call. Reading files in a checkout and
> running the suites locally is the whole of it.

---

## The finding

**Seventeen test modules existed. No workflow ran any of them.**

Fourteen workflows live in `.github/workflows/`. Exactly one invoked a test:
`event-flow.yml` runs `python -m unittest cfl_engine.event_flow.test_event_flow`
as a step inside the ingestion job. Everything else — 624 Python tests and two
Node files — ran only when somebody remembered, on a laptop, by hand.

That is not a latent bug. Every test passes today. It is the tripwires being
decorative, which is the specific failure the coordination layer was built to
avoid — and worth stating plainly, because "we have tests for that" and "that is
checked" are the same sentence right up until they are not.

## What is at stake per file

| file | what a silent failure would mean |
|---|---|
| `tests/test_research_state.py` | Frozen-file sha256s are pinned to their freeze commits. A frozen file drifting invalidates every experiment resting on it — and drift is invisible by construction, since the file still parses and still runs. |
| `tests/test_clv_protocol.py` | The CLV publication gate opening without anybody deciding to open it, and `protocol.json` drifting back to a superseded rule. Per `STATE.md` the machine mirror has already drifted **twice**. |
| `tests/test_coordination.py` | An L3 task reaching `done` with no decision recorded against its id. Unenforced, the closed L3 list is a suggestion. |
| `tests/test_migrations_idempotent.py` | The five unapplied CLV-001 migrations quietly ceasing to be re-runnable — before anyone has run them once. |
| `tests/test_sql_behaviour.py` | A view that parses perfectly and returns the wrong row; the `fight_odds` immutability trigger admitting a price edit. |
| `tests/proof-gates.test.js` | Live and replay records totalling together; a gate failing open. |
| `tests/proof-copy.test.js` | Shipped Proof Center copy drifting from what the data supports — a `COPY_STYLE.md` violation reaching a user-facing surface. |
| `cfl_engine/dur002/test_lock_prop0002.py` | The conformance proof that PROP-0001@v2 equals the existing pipeline's raw pre-calibration probability, exactly. DUR-002 is collecting against that guarantee right now. |
| `cfl_engine/clv/test_scoring.py`, `test_devig.py` | CLV-001's scorer itself — per-row eligibility, the per-quote forecast lock, write-once settlement, the 20-event floor counted by `event_id`. |
| `cfl_engine/integrity/` | The production data-integrity checks. |

## The measured state, 2026-09-18

Whole repo, at the commit this audit lands with:

```
python -m pytest -q -rs
  624 passed, 4 skipped, 4557 subtests passed

node tests/proof-copy.test.js    31 passed
node tests/proof-gates.test.js   40 passed
```

**Four skips, all self-declared, all legitimate.** Three are in
`test_clv_protocol.py` — `protocol is frozen`, `protocol is frozen; publication
gate legitimately open`, `banner check is written for the draft state` — each an
assertion written against the draft state of a protocol that has since been
frozen. The fourth is `needs SUPABASE_ACCESS_TOKEN`, and it is discussed below;
it is the one skip that must stay a skip.

The subtest total moves with the data the suites walk — it is a reading taken on
a date, not a constant, and a later run disagreeing with it by a few is not a
regression. Per `CLAUDE.md`, the claim is what matters: **the whole suite is
green and nothing is failing silently.**

## Two corrections to how this was first described

Both are wording, and both matter because the wording is a safety claim.

**1. "No network and no database" was half right.**

`tests/test_sql_behaviour.py` **does** use a database — one it creates itself.
`initdb` builds a throwaway cluster in a temp directory, listening on a unix
socket with `listen_addresses` empty, torn down in `tearDownClass`.
`SUPABASE_DB_URL` is never read. Where `initdb` is absent every test in the file
skips rather than failing. `ubuntu-latest` ships PostgreSQL, so those tests
**run** in CI rather than skipping — a gain, not a risk.

**2. One test in the repo talks to production, and the workflow must keep it
skipping.**

`cfl_engine/dur001/test_dur001.py::test_db_ledgers_are_append_only_and_lock_guard_holds`
posts SQL to the Supabase **management API** for the live project. It is careful
— a DO block that inserts probe rows, tries to rewrite them, then raises so the
whole transaction rolls back, followed by a check that no `TEST-ONLY` lock
survived — but it is a production write path, and it is in the repo-root pytest
run.

It is gated on `SUPABASE_ACCESS_TOKEN`, and `tests.yml` passes no secrets, so it
skips. **That is load-bearing, not incidental.** Adding a secret to this
workflow would turn every pull request, fork ones included, into a production
write. The workflow header now says so in as many words, beside the reason
`permissions: contents: read` is enough.

The security claim survives both corrections intact. The sentence that carried
it did not, and has been replaced with one that is true.

## What was done about it

`.github/workflows/tests.yml` — two jobs, Python and Node, on every push and
every pull request. Named separately so a failure says which suite broke without
opening a log.

Three deliberate choices worth recording, because each is the kind of thing a
later reader would otherwise "clean up":

- **`pytest` runs from the repo root, not `pytest tests/`.** The first draft of
  this workflow ran `tests/` alone and reported 168 passing tests. The repo has
  624. The other 456 live under `cfl_engine/` and `research/` and are the ones
  guarding the frozen model path — the PROP-0001@v2 conformance proof, the
  CLV-001 scorer, the event-flow card resolution, the integrity checks. A green
  tick over an untested engine is worse than no tick, because people believe it.
- **Neither job lists its test files.** pytest discovers; the Node job globs
  `tests/*.test.js` and fails if the glob is empty. A hand-written list means a
  newly added test file is skipped in silence — the one failure mode a tripwire
  suite cannot have.
- **`pytest` is pinned exactly (`pytest==9.1.1`),** the version this green run
  was made on. An unbounded install lets a runner-side change turn the build red
  with no repo change behind it, and a suite that reddens for reasons nobody
  caused is a suite people stop reading. Bump it deliberately, with a run to
  show for it.

## The residual gap: the engine's dependencies are not pinned

Running the whole repo means the Python job installs
`cfl_engine/requirements.txt`, because three modules reach `cfl_engine/engine.py`
and it imports numpy and pandas at module scope. Without the wheels, eight tests
fail on `ModuleNotFoundError` — a red suite that is really a missing install.

That file carries `>=` ranges for all eight of pandas, numpy, scikit-learn,
scipy, statsmodels, pyarrow, xgboost and tabulate. So the job can still go red on
somebody else's release with nothing changed in this repo — precisely the failure
the `pytest` pin exists to prevent, left standing on the larger half of the
dependency set.

It was **not** fixed here, deliberately. `requirements.txt` is the engine's own
manifest, shared with the jobs that run the model; narrowing it is a change to
the engine's runtime, not to CI, and it should land with a run behind it rather
than as a line slipped into a CI pull request. The likely shape is a CI-only
constraints file, so the engine keeps its ranges and the test job stops floating.

**Queued as [T-011](../TASK_QUEUE.md).**

## What this audit did not look at

Stated so the gap is not mistaken for a clean bill:

- **Coverage.** Whether any of these seventeen modules test the right things was
  not assessed. This audit asked only whether they run.
- **The build scripts.** `build/test-fetch-odds.js` is named in `STATE.md` as the
  credit-ceiling check. It sits in `build/`, not `tests/`, so the Node job's glob
  does not reach it. Worth a look; not looked at here.
- **Every other workflow.** Thirteen workflows were read only far enough to
  answer "does this invoke a test?". Whether any of them should be running one
  is a separate question.
