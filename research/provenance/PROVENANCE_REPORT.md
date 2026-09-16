# PROP-0001 lock provenance audit — 2026-09-15

Scope: the 48 rows in `prop_model_locks` with `model_version = 'PROP-0001@v1'`
(ids 5–52, UFC 331, 12 fights). Every one carries
`code_version = 322a5b09e739-dirty`. This audit asks what "dirty" was, and
whether the rows can still be trusted.

Run read-only. No writes, no migrations, no Odds API calls, no fight results
were read.

---

## Finding

> **The 48 forecasts have verified prediction provenance and append-only
> integrity. Exact source-code provenance is incomplete because
> model-generating code was untracked at lock time.**

That sentence is the whole audit. Everything below is the evidence for it, and
the two halves should not be collapsed into each other.

**Verified.** The locks were on record before the bell, they have not been
touched since, and they are arithmetically coherent:

- All 48 rows reproduce their own stated probability from their own stored
  hazards to seven decimal places.
- The ledger hash in the preregistration **reproduces exactly**, so the 48 rows
  are byte-for-byte what was hashed when DUR-001 was frozen.
- The table physically cannot be edited after the fact — the database rejects
  UPDATE, DELETE and TRUNCATE for every role, including `service_role`.

**Incomplete.** What cannot be established is exactly which source code
produced them:

- The locks were written from a tree with uncommitted model code in it,
  including `lock_prop0001.py` itself, which was untracked at that moment and
  so has no recorded content for that run.
- The one frozen model file involved (`build_features.py`) was changed in a way
  that moves code around without changing any number it produces — but that is
  a statement about the *committed* refactor, not proof that the tree at lock
  time held only that refactor.

The honest reading: these are valid live locks whose forecasts are trustworthy,
carrying a documented gap in code provenance. Not "the locks are fine" and not
"the locks are compromised" — the first overclaims and the second is false.

---

## 1. What `322a5b09e739-dirty` points at

| | |
|---|---|
| commit | `322a5b09e7399931480834d2fa99abdca5c9741e` |
| subject | engine-serve: refresh fighter_ratings daily after the export |
| authored | 2026-09-02 00:09:33 -0500 |
| contents | a 6-line change to `.github/workflows/engine-serve.yml`, nothing else |
| ancestor of `main` | yes |

The locks were written on 2026-09-15. So the checkout that produced them was
sitting on a commit from **13 days earlier** and roughly 50 commits behind
`main`, with uncommitted work on top.

## 2. What the uncommitted work was

`322a5b0` is the **direct parent** of `6be7198`:

```
git log -1 --pretty='%h parents=%p' 6be7198
6be7198 parents=322a5b0
```

`6be7198` ("DUR-001: capture fight totals, freeze PROP-0001 locks,
residual-market analysis", 2026-09-14) is the commit the preregistration names
as the freeze commit for model + features + lock script.

That makes the reconstruction unambiguous: the working tree that wrote the
locks had HEAD at `322a5b0` and carried, uncommitted, the changes that were
committed shortly afterwards as `6be7198`.

Of the files in that delta, three are model-generating:

| file | change | frozen? |
|---|---|---|
| `cfl_engine/dur001/lock_prop0001.py` | **+454, new file** — did not exist in git at all | yes |
| `cfl_engine/features/build_features.py` | 97 lines moved | yes |
| `cfl_engine/models/duration.py` | unchanged | yes |

Saved verbatim as
[`prop0001_locks_2026-09-15_dirty.RECONSTRUCTED.diff`](prop0001_locks_2026-09-15_dirty.RECONSTRUCTED.diff)
(`git diff 322a5b0 6be7198`), sha256
`0fc6f5c5642aacb55e55daf0f1e869fb76cef9639082847e2a04b79911fcfddc`.

**This file is a reconstruction, not the original dirty diff.** The original
working tree lived on Reed's machine. This session runs in a fresh ephemeral
clone: no stashes, no reflog beyond today's checkout, no `.orig`/`.bak`/`~`
files, clean tree. The true dirty diff is unrecoverable from here. What is
saved is the best available proxy — the committed form of the same work. If
the lock run happened mid-edit, the real diff was a *subset* of this.

### Did the dirty state touch model-generating code?

**YES.** Provable, not inferred: `lock_prop0001.py` — the script that computed
and wrote these very rows — has its first appearance in git history in
`6be7198`, twelve days after the commit the locks name. At lock time it existed
only as an untracked working-tree file.

### Does that change any number?

Almost certainly not. The `build_features.py` delta is a **pure refactor**: the
`RATE_FEATS` / `MEAN_FEATS` / `ABS_FEATS` / `STANCES` / `STYLES` lists and the
diff/mean/abs-diff/one-hot assembly were lifted verbatim out of `main()` up to
module level as `matchup_features()`, and `main()` now calls it. Same lists,
same arithmetic, same key insertion order, so the same 49 columns in the same
order.

The refactor's stated purpose is in its own comment, and it is exactly the
thing you would want: make the live lock script assemble *the identical row*
the training panel uses, so there is no train/serve skew. `lock_prop0001.py`
calls `bf.matchup_features(x, y)`.

Caveat, stated plainly: "the committed refactor is behaviour-preserving" is
verified. "The tree at lock time contained exactly the committed refactor and
nothing else" is **not** verifiable from here.

## 3. The rows are internally self-consistent — 48/48

Recomputed `predicted_probability` from each row's own stored `haz_r*` and
`phi_r*` using `threshold_probs()` from `lock_prop0001.py`:

```
S1 = 1-h1 ; S2 = (1-h1)(1-h2)
over 0.5      = 1 - phi1*h1
over 1.5      = S1 * (1 - phi2*h2)
over 2.5      = S2 * (1 - phi3*h3)
goes_distance = S2 * (1 - h3)
```

| check | result |
|---|---|
| rows | 48 |
| `predicted_probability` reproduced to 1e-5 | **48 / 48 pass, 0 fail** |
| max absolute error | 7.95e-7 |
| `p_ends_r1/r2/r3` + `p_decision` reproduced to 1e-5 | 48 / 48 pass |
| `p_ends_r1+r2+r3+p_decision = 1` to 1e-9 | 44 / 48 |

The residual error sits at ~1e-7 throughout, which is the rounding of the
stored numerics, not a logic difference. The four rows that miss the
1e-9 partition check miss it by the same ~1e-7 rounding and pass comfortably
at 1e-5.

Shape checks also pass: 12 fights × (3 `total_rounds` thresholds + 1
`goes_distance`) = 48; every row carries exactly **49** feature keys, matching
the preregistration's "49 covariates from `covariate_columns()`"; exactly one
distinct `code_version` across all 48.

**Read this for what it is.** It proves the stored rows are arithmetically
coherent with each other and with the frozen threshold formula, regardless of
the dirty tree. It does **not** prove the hazards themselves came from the
frozen model — that would need a re-run, which the preregistration forbids and
which would be the wrong thing to do anyway.

## 4. The ledger hash — reproduced

The preregistration (§3) records:

> first 48 locks (UFC 331, 12 fights) | `prop_model_locks` ids 5–52, ledger
> hash `df3ab0cca0757eb9c452e9bfb0cede38` (md5 of row_to_json ordered by id)

**That hash reproduces exactly.** The recipe is in the repository, at
[`cfl_engine/dur001/health.py:157`](../../cfl_engine/dur001/health.py):

```sql
select md5(string_agg(row_to_json(l)::text, '|' order by id))
from prop_model_locks l
```

Two details that the preregistration's one-line description omits, and that have
to be right or the hash misses: the separator is a **pipe**, and the aggregate
runs over the **whole table**, unfiltered by `model_version`. Both were
confirmed server-side and against the local export:

| | |
|---|---|
| `md5(string_agg(row_to_json(l)::text,'\|' order by id))` | `df3ab0cca0757eb9c452e9bfb0cede38` |
| preregistration §3 | `df3ab0cca0757eb9c452e9bfb0cede38` |
| match | **yes** |
| `count(*)` over the whole table | 48 (so the unfiltered and filtered sets coincide today) |

This is the strongest single result in the audit. It means the 48 rows are
**byte-for-byte identical** to what was hashed when DUR-001 was frozen —
nothing has been revised, reordered, or re-serialised since.

It also corroborates the append-only guarantee independently.
`prop_model_locks` carries `prop_model_locks_block_update`, `_block_delete` and
`_block_truncate`, all `BEFORE ... EXECUTE FUNCTION
prop_model_locks_no_rewrite()`, which raise unconditionally — row-level UPDATE
and DELETE and statement-level TRUNCATE are rejected for every role including
`service_role`. The triggers say the rows *cannot* have changed; the hash says
they *did not*.

### Correction

An earlier pass of this audit reported the hash as unreproducible and concluded
the recipe had been lost. That was wrong. 42 recipes were tried and all missed,
but the search was over the wrong files — `lock_prop0001.py`,
`dur001_analysis.py`, `dur001/README.md` and `dur001_migration.sql` — and
`health.py` was not among them. The pipe separator was never tested. The recipe
was in the codebase the whole time.

For reference, the literal reading of the preregistration's wording
(`md5(string_agg(row_to_json(t)::text, '' ORDER BY id))`, empty separator,
filtered to `PROP-0001@v1`) gives `b1101e17322402428ef50a74fda1123c`, which is
what led the first pass astray.

The one real defect here is documentation: §3 describes the recipe loosely
enough that it cannot be re-derived from the preregistration alone. Worth
tightening to name the separator and the scope, and to point at `health.py`.

## 5. Artifacts in this folder

| file | sha256 | what |
|---|---|---|
| `prop_model_locks_2026-09-15.full.jsonl` | `9baabbca8bc3b4bb426cb56ee355d60fddf74385fac4823901f6cfe61669cbe6` | all 48 rows, complete, `row_to_json` ordered by id, one per line |
| `prop_model_locks_2026-09-15.jsonl` | `6ccbbae074ed7c44536e25f76f5c84bfce885178b30a5f230f3b4cd120516176` | same 48 rows without the bulky `features` blob, plus per-row `row_sha256`, `features_sha256` and `features_n_keys` |
| `prop0001_locks_2026-09-15_dirty.RECONSTRUCTED.diff` | `0fc6f5c5642aacb55e55daf0f1e869fb76cef9639082847e2a04b79911fcfddc` | reconstructed dirty delta (`git diff 322a5b0 6be7198`) |

The full export was verified end to end: Postgres computed the sha256 of the
canonical JSONL server-side, and the file written to disk hashes identically.
No value passed through a hand transcription.

## 6. Recommended rule going forward

No lock is written from a `-dirty` tree. If a dirty run is ever unavoidable,
the lock row must carry the sha256 of the full working-tree diff alongside
`code_version`, and that diff must be committed to `research/provenance/`
before the card starts.

The same applies to ledger hashes — with the narrower lesson this audit
actually supports. The recipe *was* in code (`health.py:157`), which is why the
hash verified. What failed was the preregistration's description of it: "md5 of
row_to_json ordered by id" omits the pipe separator and the table scope, so a
reader cannot re-derive the number from §3 alone. A cited hash should name its
recipe precisely or point at the function that computes it.

Proposed as a registry row on DUR-001 (see `CFL_RESEARCH_STATE.md`) and as
amendment item (k) in `cfl_engine/dur001/AMENDMENT_DRAFT_2026-09-15.md`.
