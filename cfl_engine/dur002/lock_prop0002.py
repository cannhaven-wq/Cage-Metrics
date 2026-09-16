"""PROP-0001@v2 prediction locks for DUR-002 — the operational implementation.

    python cfl_engine/dur002/lock_prop0002.py                 # dry-run, next 8 days
    python cfl_engine/dur002/lock_prop0002.py --execute       # write locks
    python cfl_engine/dur002/lock_prop0002.py --event-id 4433 --execute

This is an IMPLEMENTATION of a specification that was already frozen. It is not
a modelling step, and it contains no modelling decisions: every one of them is
fixed by `cfl_engine/dur002/PREREGISTRATION.md`, frozen 2026-09-16T01:03:45Z.

## Thin by construction

Everything is imported from the frozen v1 lock script — `PITWorld`,
`fit_prop0001`, `serve_fight`, `upcoming_card`, `build_lock_rows`, the loaders,
the threshold mapping. `lock_prop0001.py` is not modified and not copied.

**The only intended behavioural difference is that no post-hoc calibration is
applied**, and it is implemented in one line:

    model.iso_ = None

`DurationHazardModel.predict_hazard` applies the isotonic map only
`if calibrated and self.iso_ is not None`. With `iso_` cleared, every downstream
call returns the raw hazard — identically to passing `calibrated=False`, which
`test_lock_prop0002.py` proves rather than assumes.

Clearing the calibrator rather than threading a flag through the call chain is
deliberate: a flag would need `serve_fight` to be re-implemented here, which is
exactly the duplicated-model-code this script exists to avoid.

Note the training recipe is otherwise untouched: `fit_prop0001` still fits the
base model, still fits an isotonic on the trailing year, and still refits on all
rows. v2 simply does not *use* the resulting map. That keeps the training path
bit-identical between the two versions, so any future difference between v1 and
v2 rows is attributable to the calibration step alone.

## Guards

  * `MODEL_VERSION` is hard-coded to `PROP-0001@v2` and every row is checked
    before any write. A row carrying the v1 version aborts the run.
  * v1 rows are never read for writing, updated, replaced or regraded. The
    ledger's own triggers reject UPDATE, DELETE and TRUNCATE for every role;
    this script never attempts any of them.
  * The script refuses to write from a dirty working tree unless
    `--allow-dirty` is passed, in which case the working-tree diff is hashed and
    recorded on the row. This is the direct fix for the v1 provenance gap: all
    48 v1 locks carry `code_version = ...-dirty` with no record of what "dirty"
    was (see `research/provenance/PROVENANCE_REPORT.md`).
  * Each row records this script's own sha256, so the operational implementation
    behind any v2 forecast is identifiable from the row alone.

## Once the first v2 lock is written

This script is effectively frozen. Any substantive change then requires an
amendment to the DUR-002 preregistration, or a new model version.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
import subprocess
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ENGINE, "dur001"))
sys.path.insert(0, os.path.join(ENGINE, "features"))
sys.path.insert(0, os.path.join(ENGINE, "models"))

import build_features as bf                      # noqa: E402  (frozen feature code)
import lock_prop0001 as v1                       # noqa: E402  (frozen v1 lock script)

# ---- the only values this script defines for itself -------------------------
MODEL_NAME = "PROP-0001"
MODEL_VERSION = "PROP-0001@v2"          # hard-coded; never taken from v1's module
V1_MODEL_VERSION = "PROP-0001@v1"       # refused on write
PREREGISTRATION = "cfl_engine/dur002/PREREGISTRATION.md"
FROZEN_AT = "2026-09-16T01:03:45Z"

LOCK_TABLE = v1.LOCK_TABLE
THRESHOLDS = v1.THRESHOLDS
EPS = v1.EPS


# --------------------------------------------------------------- provenance
def script_sha256() -> str:
    with open(os.path.abspath(__file__), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def working_tree_state() -> str:
    """Everything that makes the tree differ from HEAD, or '' when clean.

    Uses `git status --porcelain` and not just `git diff HEAD`, because a diff
    shows only TRACKED changes: a brand-new, never-committed script would read
    as a clean tree, which is precisely the case this guard has to catch. The
    porcelain status is concatenated with the tracked diff so the recorded hash
    identifies both which files were untracked and what the tracked edits were.

    Ignored files (out_real/, __pycache__/ and the rest of .gitignore) are
    excluded by porcelain's default, so routine artifacts never trip it.
    """
    try:
        status = subprocess.check_output(["git", "status", "--porcelain"],
                                         cwd=ENGINE, text=True)
        diff = subprocess.check_output(["git", "diff", "HEAD"], cwd=ENGINE, text=True)
    except Exception:
        return ""
    return (status + diff) if status.strip() else ""


# ------------------------------------------------------------- the one change
def strip_calibration(model):
    """Clear the isotonic map so every prediction is the raw hazard.

    This is the entire behavioural difference between v1 and v2. After this,
    `predict_hazard(df, calibrated=True)` returns exactly what
    `predict_hazard(df, calibrated=False)` returns on the same fitted model,
    because the map is only consulted when it is not None.
    """
    model.iso_ = None
    return model


# ------------------------------------------------------------------- rows
def existing_v2_locks(base_url, key, fight_ids) -> set:
    """Rows already on the ledger for THIS model version. First lock wins."""
    if not fight_ids:
        return set()
    out = set()
    ids = ",".join(str(i) for i in fight_ids)
    for r in bf.fetch_all(base_url, key, LOCK_TABLE,
                          f"select=fight_id,market_type,threshold,side"
                          f"&model_version=eq.{MODEL_VERSION}&fight_id=in.({ids})"):
        out.add((r["fight_id"], r["market_type"],
                 float(r["threshold"]) if r["threshold"] is not None else None, r["side"]))
    return out


def build_v2_rows(card, model, world, cov, med, phi, fit_info, lock_time, cutoff,
                  code_version, names, diff_sha=None, log=print):
    """v1's row builder, restamped for v2.

    `build_lock_rows` stamps `model_version` from v1's module namespace, so the
    rows come back as v1 and are restamped here. `assert_v2_only` is what makes
    that safe: it runs before any write and aborts on a single v1 row.
    """
    rows = v1.build_lock_rows(card, model, world, cov, med, phi, fit_info,
                              lock_time, cutoff, code_version, names, log=log)
    sha = script_sha256()
    out = []
    for r in rows:
        r = dict(r)
        r["model_version"] = MODEL_VERSION
        r["notes"] = (
            f"{r['notes'].split(' | hazards averaged')[0]} | "
            f"hazards averaged over both corner orderings | "
            f"DUR-002 PROP-0001@v2: RAW hazard, no post-hoc calibration "
            f"(spec frozen {FROZEN_AT}) | lock_prop0002.py sha256={sha[:16]}"
            + (f" | dirty_diff_sha256={diff_sha[:16]}" if diff_sha else "")
        )
        out.append(r)
    return out


def assert_v2_only(rows) -> None:
    """Refuse to write anything that is not a v2 row. Runs before every insert."""
    bad = [r for r in rows if r.get("model_version") != MODEL_VERSION]
    if bad:
        versions = sorted({r.get("model_version") for r in bad})
        sys.exit(f"[lock-v2] ABORT: {len(bad)} row(s) carry model_version {versions} "
                 f"instead of {MODEL_VERSION!r}. This script never writes a v1 row.")
    wrong_name = [r for r in rows if r.get("model_name") != MODEL_NAME]
    if wrong_name:
        sys.exit(f"[lock-v2] ABORT: {len(wrong_name)} row(s) carry an unexpected "
                 f"model_name; expected {MODEL_NAME!r}.")


# ------------------------------------------------------------------------ main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--event-id", type=int, default=None)
    ap.add_argument("--within-days", type=int, default=8)
    ap.add_argument("--execute", action="store_true", help="write locks (default: dry-run)")
    ap.add_argument("--allow-dirty", action="store_true",
                    help="permit writing from a dirty tree; records the diff hash")
    ap.add_argument("--out", default=os.path.join(ENGINE, os.pardir, "out_real",
                                                  "prop0002_locks_preview.csv"))
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not base_url:
        sys.exit("SUPABASE_URL not set.")
    key = v1.env_key()

    tree = working_tree_state()
    diff_sha = hashlib.sha256(tree.encode()).hexdigest() if tree.strip() else None
    if diff_sha and args.execute and not args.allow_dirty:
        sys.exit("[lock-v2] ABORT: the working tree is dirty. A lock written from an "
                 "unrecorded tree is what made the v1 provenance incomplete. Commit "
                 "first, or pass --allow-dirty to record the diff hash on each row.")

    lock_time = dt.datetime.now(dt.timezone.utc)
    cutoff = lock_time.date()                    # strictly-before-today evidence only
    code_version = v1.git_commit()
    print(f"[lock-v2] {MODEL_NAME} {MODEL_VERSION} | lock_time={lock_time.isoformat()} "
          f"| training_cutoff={cutoff} | code={code_version}")
    print(f"[lock-v2] spec frozen {FROZEN_AT} ({PREREGISTRATION})")
    print(f"[lock-v2] script sha256={script_sha256()}")
    if diff_sha:
        print(f"[lock-v2] WORKING TREE DIRTY — diff sha256={diff_sha}")

    events, fighters, fights, rounds = v1.load_all(base_url, key)
    card = v1.upcoming_card(events, fights, cutoff, args.within_days, args.event_id)
    if not card:
        print("[lock-v2] no eligible 3-round pending fights in the window — nothing to lock.")
        return
    print(f"[lock-v2] {len(card)} eligible fight(s) on: "
          + ", ".join(sorted({f['event_name'] for f in card})))

    world = v1.PITWorld(events, fighters, fights, rounds, cutoff)
    pp, fdf, cov, med, phi = world.training_panel()
    model, fit_info = v1.fit_prop0001(pp, cov, cutoff)

    # ---- the one behavioural difference ------------------------------------
    strip_calibration(model)
    print(f"[lock-v2] calibration stripped: iso_ is None -> raw hazards "
          f"(training path unchanged; {fit_info['n_cal_rows']} calibration rows fitted "
          f"and deliberately unused)")

    names = {x["id"]: x["name"] for x in fighters}
    rows = build_v2_rows(card, model, world, cov, med, phi, fit_info, lock_time,
                         cutoff, code_version, names, diff_sha)
    assert_v2_only(rows)

    have = existing_v2_locks(base_url, key, [f["id"] for f in card])
    fresh = [r for r in rows if (r["fight_id"], r["market_type"], r["threshold"], r["side"]) not in have]
    print(f"[lock-v2] {len(rows)} lock row(s) computed; {len(rows) - len(fresh)} already on "
          f"the ledger for {MODEL_VERSION} (skipped, first lock wins); {len(fresh)} new.")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    pd.DataFrame(rows).drop(columns=["features"]).to_csv(args.out, index=False)
    for f in card:
        r = {x["threshold"]: x["predicted_probability"] for x in rows
             if x["fight_id"] == f["id"] and x["market_type"] == "total_rounds"}
        d = next(x["predicted_probability"] for x in rows
                 if x["fight_id"] == f["id"] and x["market_type"] == "goes_distance")
        print(f"  fight {f['id']:>6} {names.get(f['fighter_a_id'], '?'):<22} vs "
              f"{names.get(f['fighter_b_id'], '?'):<22} "
              f"O0.5 {r[0.5]:.3f}  O1.5 {r[1.5]:.3f}  O2.5 {r[2.5]:.3f}  distance {d:.3f}")
    print(f"preview CSV -> {os.path.abspath(args.out)}")

    if not args.execute:
        print("\nDRY-RUN — nothing written. Re-run with --execute to lock.")
        return
    if not fresh:
        print("nothing new to write.")
        return
    assert_v2_only(fresh)                        # again, immediately before the insert
    written = v1.rest_post(base_url, key, LOCK_TABLE, fresh)
    print(f"[lock-v2] wrote {len(written)} immutable {MODEL_VERSION} lock row(s) "
          f"to {LOCK_TABLE}.")


if __name__ == "__main__":
    main()
