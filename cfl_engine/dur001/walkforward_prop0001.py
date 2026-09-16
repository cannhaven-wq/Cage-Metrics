"""PROP-0001 historical walk-forward — read-only, local.

    python cfl_engine/dur001/walkforward_prop0001.py --from-supabase \
        --mode block --start 2018-01-01 --out out_real/prop0001_wf_block

    python cfl_engine/dur001/walkforward_prop0001.py --from-exports data/exports \
        --mode event --start 2023-01-01 --end 2025-12-31 --out out_real/prop0001_wf_event

What this is
------------
Re-runs the frozen PROP-0001 recipe forward through history and reports how it
would have scored on fights it had not seen. It imports the frozen code rather
than reimplementing it — `models/duration.py`, `features/build_features.py` and
`PITWorld` / `fit_prop0001` from `lock_prop0001.py` — so the spec under test is
the same object the locks are written from.

Two modes:

  block   expanding-window blocks of `--block-months` (default 6) from --start.
          This is the shape of the 2026-08-06 gate report, so the manifest
          compares itself against `cfl_engine/harness/walkforward_report.json`
          and reports MATCHES or DIFFERS.

  event   one fold per UFC event, chronological. Closer to how the model is
          actually served — refit, then score exactly one card.

Point-in-time
-------------
Two separate guarantees, and both matter:

  * FEATURES are point-in-time by construction. `feats_asof` reads only rounds
    and fights strictly before the fight being scored, so building the panel
    once and splitting it by date does not leak.
  * The FIT is restricted per fold: coefficients for a fold come only from rows
    dated before that fold starts, and the isotonic calibrator only from the
    trailing 365 days before that same boundary. That is `fit_prop0001`'s frozen
    recipe, applied at each fold boundary.

What this deliberately does NOT do
----------------------------------
No comparison against market data. The frozen gate report carries a
`market_odds_subset` block; this script does not compute one and does not read
`fight_odds`. DUR-001's market question is answered by `dur001_analysis.py` on
locks written before the bell, not by a historical backfill — a backfill scored
against closing prices it could see is not evidence about a prospective model.
Market coverage is a pilot question, later.

Nothing here is written to `prop_model_locks`, or to the database at all.

Honest limit on MATCHES/DIFFERS
-------------------------------
The script that produced `walkforward_report.json` is not in the repository.
This is a reimplementation of the documented recipe, so DIFFERS means "these two
numbers disagree", not necessarily "the data moved". Read a DIFFERS as a prompt
to find out which of the two is wrong, and change neither until you know.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
REPO = os.path.dirname(ENGINE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ENGINE, "features"))
sys.path.insert(0, os.path.join(ENGINE, "models"))

import build_features as bf                                    # noqa: E402
from lock_prop0001 import PITWorld, fit_prop0001, SEED, load_all, env_key  # noqa: E402

HARNESS_REPORT = os.path.join(ENGINE, "harness", "walkforward_report.json")
EPS = 1e-9
# Tolerance for calling a reproduced metric equal to the frozen one. The frozen
# report stores 4 decimals, so anything inside half a unit in the last place is
# the same number printed twice.
MATCH_TOL = 5e-5


# ------------------------------------------------------------------ data load
def load_from_exports(d: str, log=print):
    """Load the four tables from build/export_tables.py output (JSONL)."""
    out = []
    for name in ("events", "fighters", "fights", "fight_rounds"):
        p = os.path.join(d, f"{name}.jsonl")
        if not os.path.isfile(p):
            sys.exit(f"missing export: {p} (run build/export_tables.py first)")
        with open(p) as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
        log(f"  {name}: {len(rows)} rows")
        out.append(rows)
    return tuple(out)


def load_from_supabase(log=print):
    base = os.environ.get("SUPABASE_URL")
    if not base:
        sys.exit("SUPABASE_URL not set.")
    return load_all(base.rstrip("/"), env_key(), log=log)


# ---------------------------------------------------------------------- folds
def block_folds(dates: pd.Series, start: pd.Timestamp, end: pd.Timestamp | None,
                block_months: int):
    """[(fold_start, fold_end)] — consecutive block_months windows from start."""
    hi = end if end is not None else dates.max() + pd.Timedelta(days=1)
    folds, cur = [], start
    while cur < hi:
        nxt = cur + pd.DateOffset(months=block_months)
        folds.append((cur, min(nxt, hi)))
        cur = nxt
    return folds


def event_folds(fdf: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp | None):
    """[(fold_start, fold_end)] — one fold per distinct event date in range."""
    d = fdf["event_date"]
    # NB: build the mask in two steps. `(end is None) | (d <= end)` would still
    # evaluate `d <= None` — Python's `|` is not short-circuiting — and pandas
    # raises on comparing datetime64 to None.
    mask = d >= start
    if end is not None:
        mask &= d <= end
    sel = sorted(pd.unique(d[mask]))
    return [(pd.Timestamp(x), pd.Timestamp(x) + pd.Timedelta(days=1)) for x in sel]


# -------------------------------------------------------------------- metrics
def logloss(y, p):
    p = np.clip(np.asarray(p, dtype=float), 1e-15, 1 - 1e-15)
    y = np.asarray(y, dtype=float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(y, p):
    return float(np.mean((np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2))


def calibration_table(y, p, bins: int = 10):
    """Equal-count bins over predicted hazard. Returns rows + max abs deviation."""
    df = pd.DataFrame({"y": np.asarray(y, dtype=float), "p": np.asarray(p, dtype=float)})
    df = df.sort_values("p").reset_index(drop=True)
    if len(df) == 0:
        return [], None
    edges = np.linspace(0, len(df), bins + 1).astype(int)
    rows = []
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        if hi <= lo:
            continue
        chunk = df.iloc[lo:hi]
        pred, actual = float(chunk.p.mean()), float(chunk.y.mean())
        rows.append({"n": int(len(chunk)), "pred": round(pred, 4),
                     "actual": round(actual, 4), "abs_dev": round(abs(pred - actual), 4)})
    return rows, (max(r["abs_dev"] for r in rows) if rows else None)


# ------------------------------------------------------------------ the walk
def run_walkforward(pp, fdf, cov, phi, folds, log=print):
    """Fit on everything before each fold, score the fold. Returns per-row preds."""
    preds, fold_meta = [], []
    for k, (lo, hi) in enumerate(folds):
        train = pp[pp.event_date < lo]
        test = pp[(pp.event_date >= lo) & (pp.event_date < hi)]
        if len(test) == 0:
            continue
        if train.fight_id.nunique() < 200:
            log(f"  fold {k} [{lo.date()} → {hi.date()}]: only "
                f"{train.fight_id.nunique()} training fights, skipped")
            continue

        model, meta = fit_prop0001(train, cov, lo.date(), log=lambda *_: None)
        h = model.predict_hazard(test, calibrated=True)
        base_rate = float(train["event"].mean())

        preds.append(pd.DataFrame({
            "fold": k, "fight_id": test.fight_id.to_numpy(),
            "event_date": test.event_date.to_numpy(), "round": test["round"].to_numpy(),
            "event": test["event"].to_numpy(), "p_hazard": h, "p_const": base_rate,
        }))
        fold_meta.append({
            "fold": k, "start": str(lo.date()), "end": str(hi.date()),
            "n_train_fights": meta["n_train_fights"], "n_train_rows": meta["n_train_rows"],
            "n_cal_rows": meta["n_cal_rows"], "calibrated": meta["n_cal_rows"] > 0,
            "n_test_rows": int(len(test)), "n_test_fights": int(test.fight_id.nunique()),
            "test_logloss": round(logloss(test["event"], h), 4),
            "const_logloss": round(logloss(test["event"], np.full(len(test), base_rate)), 4),
            "regularized_fallback": meta["regularized_fallback"],
        })
        log(f"  fold {k} [{lo.date()} → {hi.date()}]: train {meta['n_train_fights']} fights, "
            f"test {len(test)} rows, LL {fold_meta[-1]['test_logloss']} "
            f"vs const {fold_meta[-1]['const_logloss']}")

    if not preds:
        sys.exit("no scorable folds — check --start / --end against the data range.")
    return pd.concat(preds, ignore_index=True), fold_meta


def gtd_block(pred: pd.DataFrame, fdf: pd.DataFrame):
    """Fight-level goes-the-distance calibration, from the per-round hazards."""
    rows = []
    for fid, g in pred.groupby("fight_id"):
        g = g.sort_values("round")
        h = dict(zip(g["round"].astype(int), g["p_hazard"]))
        if not {1, 2, 3} <= set(h):
            continue        # a fight that ended early contributes no r2/r3 hazard row
        p_gtd = (1 - h[1]) * (1 - h[2]) * (1 - h[3])
        rows.append({"fight_id": fid, "p_gtd": p_gtd})
    if not rows:
        return {"n_fights": 0}
    g = pd.DataFrame(rows).merge(
        fdf[["fight_id", "outcome_kind"]].drop_duplicates("fight_id"),
        on="fight_id", how="left")
    g["y_gtd"] = (g["outcome_kind"] == "decision").astype(float)
    tbl, maxdev = calibration_table(g.y_gtd, g.p_gtd)
    return {"n_fights": int(len(g)),
            "pred_gtd_rate": round(float(g.p_gtd.mean()), 4),
            "actual_gtd_rate": round(float(g.y_gtd.mean()), 4),
            "gtd_brier": round(brier(g.y_gtd, g.p_gtd), 4),
            "gtd_max_abs_dev": round(maxdev, 4) if maxdev is not None else None,
            "gtd_calibration_table": tbl}


def compare_to_harness(pooled: dict, log=print):
    """Compare pooled metrics against the frozen gate report.

    Only `pooled` is compared. The frozen report's `market_odds_subset` is
    deliberately not reproduced (see the module docstring).
    """
    if not os.path.isfile(HARNESS_REPORT):
        return {"status": "NO_REFERENCE", "detail": f"{HARNESS_REPORT} not found"}
    with open(HARNESS_REPORT) as fh:
        ref = json.load(fh)
    rp = ref.get("pooled", {})
    fields = ["n_test_rows", "n_folds", "n_calibrated_folds", "model_logloss",
              "const_logloss", "model_brier", "const_brier", "cal_max_abs_dev"]
    rows, ok = [], True
    for f in fields:
        a, b = pooled.get(f), rp.get(f)
        if a is None or b is None:
            match = None
        elif isinstance(a, (int, np.integer)) and isinstance(b, (int, np.integer)):
            match = int(a) == int(b)
        else:
            match = abs(float(a) - float(b)) <= MATCH_TOL
        ok = ok and (match is True)
        rows.append({"field": f, "reproduced": a, "frozen": b, "match": match})
    return {"status": "MATCHES" if ok else "DIFFERS",
            "reference": os.path.relpath(HARNESS_REPORT, REPO),
            "tolerance": MATCH_TOL,
            "note": ("market_odds_subset is deliberately not reproduced: this run "
                     "performs no comparison against market data."),
            "fields": rows}


# ----------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-supabase", action="store_true")
    src.add_argument("--from-exports", metavar="DIR")
    ap.add_argument("--mode", choices=("block", "event"), default="block")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", default=None)
    ap.add_argument("--block-months", type=int, default=6)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    t0 = dt.datetime.now(dt.timezone.utc)
    print(f"[wf] loading data ...")
    events, fighters, fights, rounds = (
        load_from_supabase() if args.from_supabase else load_from_exports(args.from_exports))

    # cutoff = tomorrow: the panel is every completed fight. Per-fold fitting is
    # what enforces the walk-forward, not this cutoff.
    cutoff = dt.date.today() + dt.timedelta(days=1)
    print(f"[wf] building point-in-time panel ...")
    world = PITWorld(events, fighters, fights, rounds, cutoff)
    pp, fdf, cov, med, phi = world.training_panel(seed=args.seed)
    print(f"[wf] panel: {pp.fight_id.nunique()} fights / {len(pp)} person-period rows, "
          f"{len(cov)} covariates, phi={ {k: round(v, 4) for k, v in phi.items()} }")

    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end) if args.end else None
    folds = (block_folds(pp.event_date, start, end, args.block_months)
             if args.mode == "block" else event_folds(fdf, start, end))
    print(f"[wf] {args.mode} mode: {len(folds)} candidate fold(s)")

    pred, fold_meta = run_walkforward(pp, fdf, cov, phi, folds)

    pooled = {
        "n_test_rows": int(len(pred)),
        "n_folds": len(fold_meta),
        "n_calibrated_folds": sum(1 for f in fold_meta if f["calibrated"]),
        "model_logloss": round(logloss(pred.event, pred.p_hazard), 4),
        "const_logloss": round(logloss(pred.event, pred.p_const), 4),
        "model_brier": round(brier(pred.event, pred.p_hazard), 4),
        "const_brier": round(brier(pred.event, pred.p_const), 4),
    }
    cal_tbl, cal_max = calibration_table(pred.event, pred.p_hazard)
    pooled["cal_max_abs_dev"] = round(cal_max, 4) if cal_max is not None else None

    os.makedirs(args.out, exist_ok=True)
    pred_path = os.path.join(args.out, "predictions.csv")
    pred.sort_values(["event_date", "fight_id", "round"]).to_csv(pred_path, index=False)
    with open(pred_path, "rb") as fh:
        pred_sha = hashlib.sha256(fh.read()).hexdigest()

    manifest = {
        "generated_utc": t0.isoformat(),
        "mode": args.mode,
        "start": args.start,
        "end": args.end,
        "block_months": args.block_months if args.mode == "block" else None,
        "seed": args.seed,
        "source": "supabase" if args.from_supabase else args.from_exports,
        "model_version": "PROP-0001@v1",
        "n_covariates": len(cov),
        "phi": {str(k): round(v, 6) for k, v in phi.items()},
        "pooled": pooled,
        "gtd": gtd_block(pred, fdf),
        "calibration_table": cal_tbl,
        "harness_comparison": compare_to_harness(pooled),
        "predictions_path": os.path.relpath(pred_path, REPO),
        "predictions_sha256": pred_sha,
        "market_comparison": None,
        "market_comparison_note": (
            "Not computed. This run performs no performance comparison against "
            "market data; that is a DUR-001 question answered from pre-fight "
            "locks, not from a historical backfill."),
        "folds": fold_meta,
    }
    man_path = os.path.join(args.out, "manifest.json")
    with open(man_path, "w") as fh:
        json.dump(manifest, fh, indent=2)

    print(f"\n[wf] pooled: {json.dumps(pooled)}")
    hc = manifest["harness_comparison"]
    print(f"[wf] harness_comparison: {hc['status']}")
    for row in hc.get("fields", []):
        flag = {True: "ok", False: "DIFF", None: "n/a"}[row["match"]]
        print(f"      {row['field']:<20} reproduced={row['reproduced']!s:<10} "
              f"frozen={row['frozen']!s:<10} {flag}")
    print(f"\n[wf] rows: {len(pred)}")
    print(f"[wf] predictions_sha256: {pred_sha}")
    print(f"[wf] manifest: {os.path.relpath(man_path, REPO)}")
    if hc["status"] == "DIFFERS":
        print("\n[wf] DIFFERS — stopping here. Change nothing until you know which "
              "side is wrong; the frozen report is evidence, not a target to hit.")


if __name__ == "__main__":
    main()
