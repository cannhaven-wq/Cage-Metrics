# Research registry, provenance audit, PROP-0001 walk-forward, alerts, backfill gate, DUR-001 amendment draft

Research infrastructure for DUR-001. Nothing here changes a user-facing surface,
and no frozen file is modified.

**No UFC 331 fight result was read, printed, or graded at any point.** The
amendment draft and the walk-forward harness were both written before any
outcome was inspected, which is the only order in which either is worth having.

---

## The headline: the locks are sound, but they were written from a dirty tree

All 48 live PROP-0001 locks carry `code_version = 322a5b09e739-dirty`. The audit
in [`research/provenance/`](research/provenance/PROVENANCE_REPORT.md) establishes
what "dirty" was.

`322a5b0` is a 6-line workflow edit dated 2026-09-02, and it is the **direct
parent** of `6be7198` — the commit the preregistration names as the freeze for
model, features and lock script. So the locks were written on 9/15 from a
13-day-stale checkout carrying, uncommitted, the work that became `6be7198`.

**The dirty state did include model-generating code**, provably:
`lock_prop0001.py` — the script that wrote these very rows — had no git history
at lock time. The one *frozen* model file involved, `build_features.py`, changed
only by a behaviour-preserving refactor that hoists the feature lists to module
level precisely so the lock script serves the identical row.

Three independent checks say the rows themselves are fine:

| check | result |
|---|---|
| `predicted_probability`, `p_ends_r1..r3`, `p_decision` recomputed from each row's own hazards and phi via `threshold_probs()` | **48 / 48 pass at 1e-5**, max error 7.95e-7 |
| preregistration ledger hash `df3ab0cc…` | **reproduces exactly** |
| `prop_model_locks` UPDATE / DELETE / TRUNCATE | rejected by trigger for every role incl. `service_role` |

The ledger hash reproducing is the strongest single result: the 48 rows are
byte-for-byte what was hashed when DUR-001 was frozen.

One correction worth flagging, because an earlier commit on this branch got it
wrong. That commit reported the hash as unreproducible after 42 failed recipes
and concluded it had been computed ad hoc and lost. That was wrong — the recipe
is in the repo at `health.py:157`, and uses a **pipe** separator over the
**whole table**, neither of which the preregistration's one-line description
mentions. The audit now records the verification and the correction.

The real defect is documentation: §3 describes the recipe too loosely to
re-derive from the preregistration alone.

---

## What is in the branch

### Provenance audit — `research/provenance/`

| file | what |
|---|---|
| `PROVENANCE_REPORT.md` | the full audit, plain-English summary first |
| `prop_model_locks_2026-09-15.full.jsonl` | all 48 rows, complete |
| `prop_model_locks_2026-09-15.jsonl` | same rows minus the `features` blob, plus per-row digests |
| `prop0001_locks_2026-09-15_dirty.RECONSTRUCTED.diff` | reconstructed dirty delta |

The full export was verified end to end — Postgres computed the sha256
server-side and the file on disk hashes identically, so no value passed through
a hand transcription.

The diff is labelled **RECONSTRUCTED** because it is. The original working tree
was on Reed's machine; this branch was built in a fresh clone with no stashes,
no reflog and no editor backups. It is `git diff 322a5b0 6be7198` — the
committed form of the same work, and the best available proxy.

### Research registry — `CFL_RESEARCH_STATE.md`, `research/registry.json`

Human-readable register and its machine-readable mirror. Both carry the frozen
file table; every one of the seven frozen files was verified byte-identical to
its freeze commit.

`tests/test_research_state.py` is the tripwire: it recomputes each frozen file's
sha256 and fails if it stops matching either registry. The hashes are pinned to
the freeze commits, not regenerated from disk — a test that derives its expected
value from the thing it tests passes by construction and proves nothing.
Verified to bite by tampering with `duration.py` and watching 3 tests fail.

It also enforces that the withdrawn **0.483378 / 3,793** figure does not
reappear: withdrawn by the statistics director on 2026-09-15 pending an
artifact, and nothing in the repository reproduces it.

### Dead-man alert — `cfl_engine/dur001/alert.py`

`health.py` answers "is capture healthy?" when asked. This answers "has
something gone quiet that nobody is watching?" on a schedule.

The fix that matters: **totals and moneyline get separate dead-man switches.**
Grading them together — on the newer of the two capture ages — hides exactly the
failure DUR-001 cares about, where `prop_odds` stalls, `fight_odds` keeps
running, the combined age looks fine, and the experiment silently loses its
market benchmark. Each stream now emits its own RED line.

### Walk-forward harness — `cfl_engine/dur001/walkforward_prop0001.py`

Re-runs the frozen recipe forward through history, importing the frozen code
rather than reimplementing it. Block mode compares its pooled metrics against
`cfl_engine/harness/walkforward_report.json` and reports MATCHES or DIFFERS.

Two things it deliberately does not do:

- **No comparison against market data.** The frozen gate report has a
  `market_odds_subset` block; this does not reproduce it and does not read
  `fight_odds`. A backfill scored against closing prices it could see is not
  evidence about a prospective model. The manifest records that omission
  explicitly rather than leaving a reader to infer it.
- **No claim that DIFFERS means the data moved.** The script that produced the
  frozen report is not in the repo, so this is a reimplementation of the
  documented recipe. DIFFERS means the two numbers disagree; which one is wrong
  is then a question, not a conclusion.

### Backfill gate — `research/dur001_backfill/`

Turns `PREREGISTRATION.md` §13 into checks that run before any work happens.
Nine gate codes; `check()` returns all violations rather than the first.

**It currently refuses everything, by design.** The blocker is `TIMING_RULE` —
amendment item (i) puts two candidate historical timing rules to Reed and
neither is picked. The runner contains no scoring code at all: writing the
scorer before the rule is chosen invites running it "just to look", and the
looking is the damage.

### Amendment draft — `cfl_engine/dur001/AMENDMENT_DRAFT_2026-09-15.md`

Items (a)–(j) as specified plus (k) from the audit. Each quotes the
preregistration lines it would replace, gives proposed text, and names the code
that would change. All marked **PROPOSED**. `PREREGISTRATION.md` is untouched.

Item (j) ships as an unapplied migration
(`cfl_engine/dur001/proposed_2026-09-15_market_last_update.sql`) exposing
`market_last_update` on `v_prop_odds_lifecycle` and requiring it to precede
`start_at` for a closer. It lives under `cfl_engine/dur001/` rather than the repo
root so the "apply root `*.sql`" habit cannot pick it up by accident.

Confirmed read-only while drafting item (g): **`bell_at` is populated on 0 of
8,992 fights**, so nothing in the database currently qualifies as a closing
line.

### Table export — `.github/workflows/export.yml`, `build/export_tables.py`

Daily 05:00 UTC plus manual dispatch, `contents: write`, pages the REST API
1,000 rows at a time, exports the ten listed tables including `fight_rounds`,
commits via `stefanzweifel/git-auto-commit-action`. Stdlib only. Not run yet.

---

## Tests

```
python -m unittest tests/test_research_state.py                  13 pass
python -m unittest cfl_engine/dur001/test_walkforward_prop0001.py \
                   cfl_engine/dur001/test_alert.py               52 pass
python -m unittest discover -s research/dur001_backfill/tests    29 pass
```

94 new tests, all passing. The pre-existing `cfl_engine/dur001/test_dur001.py`
also passes (22 passed, 1 skipped) — it needs `pytest`, which is not in
`cfl_engine/requirements.txt`. Unrelated pre-existing gap, not fixed here.

One real bug was found and fixed while testing: `event_folds` built its date
mask as `(end is None) | (d <= end)`, and Python's `|` does not short-circuit,
so pandas raised on comparing `datetime64` to `None` whenever `--end` was
omitted.

---

## Not done, and why

| step | status |
|---|---|
| Steps 7–8 — walk-forward run, alert dry-run | **not run.** `SUPABASE_URL` / `SUPABASE_SECRET_KEY` / `SUPABASE_ACCESS_TOKEN` are unset in this container. The code is here and tested; the runs need credentials. |

The audit's read-only SQL was done through the Supabase MCP connection, which is
read-only SELECTs and does not supply the env vars those two scripts need.

## Waiting on Reed

- **Amendment items (a)–(k):** approve or reject.
- **Item (h):** pick Shin or power de-vig.
- **Item (i):** pick historical timing rule **Candidate 1** (T−10 before
  earliest observed start; 0 extra credits; flags moved fights) or **Candidate
  2** (self-consistent walk-back; up to 12 extra calls per moved fight; excludes
  fights with no qualifying snapshot). Recommendation in the draft is Candidate
  1 — flagging beats excluding, since an excluded-fight rule conditions the
  sample on a property correlated with card chaos.

Until (i) is decided the backfill gate stays shut, which is the intended state.

## Browser-only, for Reed

Protect `main`; add repository secrets `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY` (export workflow), `SUPABASE_ACCESS_TOKEN` and
`DISCORD_WEBHOOK_URL` (alert); run the export workflow once manually; issue a
fine-grained repo token.
