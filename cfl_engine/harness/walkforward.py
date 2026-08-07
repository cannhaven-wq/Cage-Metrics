"""Expanding-window walk-forward harness for the duration hazard model.

The model and this harness prove each other: the harness never lets the model
see a row dated on/after the block it is predicting, refits from scratch each
block, and grades the calibrated out-of-sample hazards against two benchmarks.

BENCHMARKS
  (a) constant league-average hazard -- per-round base finish rate learned on
      the fold's training rows only. This is the "no covariates" bar; the model
      must beat it or the covariates add nothing.
  (b) favorite / market base rate -- a logistic hazard on round dummies + the
      devigged closing favorite edge (|p_fav - 0.5|), fit on the training rows
      that have odds. Evaluated on the odds subset, head-to-head with the model.

CALIBRATION IS ROLLING AND OUT-OF-SAMPLE. The isotonic map applied to fold k is
fit only on pooled OOS raw hazards from folds < k (validation), never on fold k
itself and never on training rows. Early folds run uncalibrated until the pool
reaches --min-cal-rows.

METRICS (per fold + pooled): log-loss, Brier, a decile calibration table, and a
fight-level go-the-distance predicted-vs-actual table.

GATES (a change ships only if it clears all of these AND beats baseline.json):
  - model pooled log-loss < constant-hazard log-loss (full set)
  - model pooled log-loss < market log-loss (odds subset)
  - pooled log-loss < 0.62 and pooled Brier < 0.24
  - calibration within a few points per decile bucket (max |pred-actual| <= 0.05)
If gates fail the harness reports honestly and stops -- it does not tune.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "models"))
from duration import DurationHazardModel  # noqa: E402

def _jsafe(o):
    return o.item() if hasattr(o, "item") else str(o)


EPS = 1e-6
GATE_LOGLOSS = 0.62
GATE_BRIER = 0.24
GATE_CAL_MAXDEV = 0.05


def _ll(y, p):
    return log_loss(y, np.clip(p, EPS, 1 - EPS), labels=[0, 1])


def decile_calibration(y, p, n_bins=10):
    df = pd.DataFrame({"y": np.asarray(y, float), "p": np.asarray(p, float)})
    # rank-based bins so each bucket is populated even with a spiky p distribution
    df["bin"] = pd.qcut(df["p"].rank(method="first"), n_bins, labels=False)
    g = df.groupby("bin").agg(n=("y", "size"), pred=("p", "mean"), actual=("y", "mean"))
    g["abs_dev"] = (g["pred"] - g["actual"]).abs()
    return g.reset_index(drop=True)


def const_hazard_predict(train, test):
    """Per-round base finish rate from training, mapped onto test rows."""
    base = train.groupby("round")["event"].mean()
    overall = float(train["event"].mean())
    return test["round"].map(base).fillna(overall).to_numpy()


def market_hazard_fit_predict(train, test):
    """Round dummies + closing-favorite edge logistic, fit on odds rows only."""
    tr = train[train["fav_prob"].notna()].copy()
    te = test[test["fav_prob"].notna()].copy()
    if len(tr) < 200 or te.empty:
        return None, te.index
    for d in (tr, te):
        d["mismatch"] = (d["fav_prob"] - 0.5).abs()
    cols = ["r1", "r2", "r3", "mismatch"]
    lr = LogisticRegression(fit_intercept=False, max_iter=1000)
    lr.fit(tr[cols].to_numpy(), tr["event"].to_numpy())
    p = lr.predict_proba(te[cols].to_numpy())[:, 1]
    return pd.Series(p, index=te.index), te.index


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    here = os.path.dirname(__file__)
    ap.add_argument("--data", default=os.path.join(here, os.pardir, "features",
                                                    "duration_features.parquet"))
    ap.add_argument("--manifest", default=os.path.join(here, os.pardir, "features",
                                                       "feature_manifest.json"))
    ap.add_argument("--baseline", default=os.path.join(here, "baseline.json"))
    ap.add_argument("--report", default=os.path.join(here, "walkforward_report.json"))
    ap.add_argument("--block-months", type=int, default=3)
    ap.add_argument("--start", default="2014-01-01",
                    help="first test block start; everything before is base training")
    ap.add_argument("--min-cal-rows", type=int, default=800,
                    help="min pooled prior-OOS rows before rolling calibration turns on")
    args = ap.parse_args()

    pp = pd.read_parquet(args.data)
    pp["event_date"] = pd.to_datetime(pp["event_date"])
    cov_cols = json.load(open(args.manifest))["covariate_columns"]
    pp = pp.sort_values("event_date").reset_index(drop=True)

    start = pd.Timestamp(args.start)
    end = pp["event_date"].max()
    if pp[pp["event_date"] < start].empty:
        sys.exit(f"No training data before --start {args.start}.")
    blocks = []
    cur = start
    while cur <= end:
        nxt = cur + pd.DateOffset(months=args.block_months)
        blocks.append((cur, nxt))
        cur = nxt

    # accumulators
    fold_metrics = []
    oos_raw, oos_evt = [], []                 # pooled prior-OOS for rolling calib
    P = {k: [] for k in ("y", "model", "const")}          # full-set pooled
    Pm = {k: [] for k in ("y", "model", "market", "const")}  # odds-subset pooled
    gtd_pred, gtd_act = [], []                # fight-level GTD
    n_cal_folds = 0

    for (b0, b1) in blocks:
        train = pp[pp["event_date"] < b0]
        test = pp[(pp["event_date"] >= b0) & (pp["event_date"] < b1)]
        if test.empty or train["event"].nunique() < 2:
            continue

        model = DurationHazardModel().fit(train, cov_cols)
        raw = model.predict_hazard(test, calibrated=False)

        # rolling calibration from prior folds' OOS only
        if len(oos_raw) >= args.min_cal_rows:
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            iso.fit(np.clip(np.array(oos_raw), EPS, 1 - EPS), np.array(oos_evt))
            model.iso_ = iso
            pred = np.clip(iso.predict(np.clip(raw, EPS, 1 - EPS)), EPS, 1 - EPS)
            n_cal_folds += 1
        else:
            model.iso_ = None
            pred = np.clip(raw, EPS, 1 - EPS)

        y = test["event"].to_numpy()
        const = const_hazard_predict(train, test)

        # fold-level metrics (model vs const on the block)
        fm = {"block_start": str(b0.date()), "block_end": str(b1.date()),
              "n_train": int(len(train)), "n_test": int(len(test)),
              "calibrated": model.iso_ is not None,
              "model_logloss": round(_ll(y, pred), 4),
              "const_logloss": round(_ll(y, const), 4),
              "model_brier": round(brier_score_loss(y, pred), 4)}
        fold_metrics.append(fm)

        # pooled full-set
        P["y"].extend(y); P["model"].extend(pred); P["const"].extend(const)
        # pooled odds-subset with market benchmark
        mkt, idx = market_hazard_fit_predict(train, test)
        if mkt is not None:
            sel = test.loc[idx]
            Pm["y"].extend(sel["event"].to_numpy())
            Pm["model"].extend(pred[test.index.get_indexer(idx)])
            Pm["market"].extend(mkt.to_numpy())
            Pm["const"].extend(const[test.index.get_indexer(idx)])

        # fight-level GTD predicted-vs-actual (dedup covariates per fight)
        fights = test.drop_duplicates("fight_id")
        dist = model.fight_distribution(fights, calibrated=model.iso_ is not None)
        gtd_pred.extend(dist["p_gtd"].to_numpy())
        gtd_act.extend(fights["went_distance"].to_numpy())

        # add this fold to the OOS pool AFTER using the pool (prevents leakage)
        oos_raw.extend(raw.tolist()); oos_evt.extend(y.tolist())

    if not P["y"]:
        sys.exit("No test folds produced predictions. Check --start / --block-months.")

    # ---------------------------------------------------------------- pooled
    y = np.array(P["y"]); pm = np.array(P["model"]); pc = np.array(P["const"])
    pooled = {
        "n_test_rows": int(len(y)), "n_folds": len(fold_metrics),
        "n_calibrated_folds": n_cal_folds,
        "model_logloss": round(_ll(y, pm), 4),
        "const_logloss": round(_ll(y, pc), 4),
        "model_brier": round(brier_score_loss(y, pm), 4),
        "const_brier": round(brier_score_loss(y, pc), 4),
    }
    cal = decile_calibration(y, pm)
    pooled["cal_max_abs_dev"] = round(float(cal["abs_dev"].max()), 4)

    market_block = None
    if Pm["y"]:
        ym = np.array(Pm["y"]); mm = np.array(Pm["market"])
        mo = np.array(Pm["model"]); mc = np.array(Pm["const"])
        market_block = {
            "n_odds_rows": int(len(ym)),
            "model_logloss": round(_ll(ym, mo), 4),
            "market_logloss": round(_ll(ym, mm), 4),
            "const_logloss": round(_ll(ym, mc), 4),
            "model_brier": round(brier_score_loss(ym, mo), 4),
            "market_brier": round(brier_score_loss(ym, mm), 4),
        }

    # fight-level GTD
    gp = np.array(gtd_pred); ga = np.array(gtd_act)
    gtd_cal = decile_calibration(ga, gp, n_bins=10)
    gtd_block = {"n_fights": int(len(ga)),
                 "pred_gtd_rate": round(float(gp.mean()), 4),
                 "actual_gtd_rate": round(float(ga.mean()), 4),
                 "gtd_brier": round(brier_score_loss(ga, gp), 4),
                 "gtd_max_abs_dev": round(float(gtd_cal["abs_dev"].max()), 4)}

    # ---------------------------------------------------------------- gates
    gates = {
        "beats_constant_hazard": pooled["model_logloss"] < pooled["const_logloss"],
        "logloss_under_0.62": pooled["model_logloss"] < GATE_LOGLOSS,
        "brier_under_0.24": pooled["model_brier"] < GATE_BRIER,
        "calibration_within_5pts": pooled["cal_max_abs_dev"] <= GATE_CAL_MAXDEV,
    }
    if market_block is not None:
        gates["beats_market"] = market_block["model_logloss"] < market_block["market_logloss"]
    all_pass = all(gates.values())

    report = {"generated_start": args.start, "block_months": args.block_months,
              "pooled": pooled, "market_odds_subset": market_block, "gtd": gtd_block,
              "gates": gates, "all_gates_pass": all_pass,
              "calibration_table": cal.round(4).to_dict("records"),
              "gtd_calibration_table": gtd_cal.round(4).to_dict("records"),
              "folds": fold_metrics}
    with open(args.report, "w") as fh:
        json.dump(report, fh, indent=2, default=_jsafe)

    # ---------------------------------------------------------------- print
    print("=" * 72)
    print(f"WALK-FORWARD  {len(fold_metrics)} folds  |  {pooled['n_test_rows']} test "
          f"person-period rows  |  {n_cal_folds} calibrated folds")
    print("=" * 72)
    print("\nPOOLED (full set)           model     constant")
    print(f"  log-loss                 {pooled['model_logloss']:.4f}    {pooled['const_logloss']:.4f}"
          f"   (lower is better)")
    print(f"  Brier                    {pooled['model_brier']:.4f}    {pooled['const_brier']:.4f}")
    if market_block:
        print(f"\nODDS SUBSET ({market_block['n_odds_rows']} rows)      model     market     constant")
        print(f"  log-loss                 {market_block['model_logloss']:.4f}    "
              f"{market_block['market_logloss']:.4f}     {market_block['const_logloss']:.4f}")
        print(f"  Brier                    {market_block['model_brier']:.4f}    "
              f"{market_block['market_brier']:.4f}")
    print("\nCALIBRATION (decile: predicted hazard vs actual finish rate)")
    print(f"  {'bin':>3} {'n':>6} {'pred':>8} {'actual':>8} {'abs_dev':>8}")
    for i, r in cal.iterrows():
        print(f"  {i:>3} {int(r['n']):>6} {r['pred']:>8.3f} {r['actual']:>8.3f} {r['abs_dev']:>8.3f}")
    print(f"  max abs deviation: {pooled['cal_max_abs_dev']:.3f}")
    print(f"\nGO-THE-DISTANCE (fight level, n={gtd_block['n_fights']})")
    print(f"  predicted GTD rate {gtd_block['pred_gtd_rate']:.3f}  vs  "
          f"actual {gtd_block['actual_gtd_rate']:.3f}   (Brier {gtd_block['gtd_brier']:.3f}, "
          f"max decile dev {gtd_block['gtd_max_abs_dev']:.3f})")

    print("\nGATES")
    for k, v in gates.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print(f"\n  ==> {'ALL GATES PASS' if all_pass else 'GATES FAILED'}")

    # ---------------------------------------------------------------- baseline
    base_exists = os.path.exists(args.baseline)
    if all_pass and not base_exists:
        with open(args.baseline, "w") as fh:
            json.dump({"model_logloss": pooled["model_logloss"],
                       "model_brier": pooled["model_brier"],
                       "cal_max_abs_dev": pooled["cal_max_abs_dev"],
                       "n_test_rows": pooled["n_test_rows"],
                       "written_from_start": args.start}, fh, indent=2, default=_jsafe)
        print(f"\nBASELINE written -> {args.baseline}")
    elif base_exists:
        base = json.load(open(args.baseline))
        beats = (pooled["model_logloss"] < base["model_logloss"]
                 and pooled["model_brier"] <= base["model_brier"])
        print(f"\nBASELINE (existing): log-loss {base['model_logloss']} / "
              f"Brier {base['model_brier']}")
        print(f"  this run: log-loss {pooled['model_logloss']} / Brier {pooled['model_brier']}"
              f"  ->  {'BEATS baseline' if beats else 'does NOT beat baseline'}")

    print("\nSHIP RULE: a change ships only if it PASSES every gate AND beats "
          "baseline.json (lower log-loss, no worse Brier). Otherwise it does not ship.")
    print(f"\nreport -> {args.report}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
