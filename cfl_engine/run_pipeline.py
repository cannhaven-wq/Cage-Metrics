"""CFL Engine pipeline: one probability brain, two product faces, full leak audit.

Usage:
  python run_pipeline.py --fights fights.csv --stats fight_stats.csv \
      --fighters fighters.csv --outdir out/
  python run_pipeline.py --synthetic --outdir out_synth/   # harness validation
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

import audit
import faces
from engine import (build_features, devig_a, load_data, make_matchup_features,
                    randomize_corners)
from train import chronological_folds, rolling_blend, rolling_calibrate, tune, walk_forward


def run(fights, stats, fighters, outdir, seed=42, log=print):
    os.makedirs(outdir, exist_ok=True)

    log("[1/7] building point-in-time features + Elo ...")
    feat = build_features(fights, stats, fighters)
    feat = randomize_corners(feat, seed=seed)

    model_df = feat[feat["result"].isin(["a", "b"])].reset_index(drop=True)
    n_dropped = len(feat) - len(model_df)
    y = (model_df["result"] == "a").astype(int).to_numpy()
    model_df["q_mkt"] = [devig_a(a, b) for a, b in zip(model_df["odds_a"], model_df["odds_b"])]

    X, diff_cols, all_cols = make_matchup_features(model_df)
    log(f"      {len(model_df)} decisive fights ({n_dropped} draw/NC dropped), "
        f"{len(all_cols)} features, odds coverage "
        f"{model_df['q_mkt'].notna().mean():.0%}")

    log("[2/7] tuning on base window only (pre-evaluation data) ...")
    folds = chronological_folds(len(model_df))
    base_end = len(folds[0][0])
    params = tune(X, y, base_end, log=log)

    log("[3/7] walk-forward training ...")
    oos, last_model = walk_forward(X, y, diff_cols, params, folds, log=log)

    log("[4/7] rolling calibration + market blend ...")
    meta_cols = ["fight_id", "event_date", "fighter_a_id", "fighter_b_id", "weight_class",
                 "odds_a", "odds_b", "q_mkt", "a_n_fights", "b_n_fights"]
    oos = oos.merge(model_df[meta_cols].reset_index().rename(columns={"index": "row"}),
                    on="row", how="left")
    oos = rolling_calibrate(oos)
    oos = rolling_blend(oos)

    log("[5/7] Face 1 (picks) + Face 2 (edges) ...")
    f1 = faces.face1_table(oos)
    bets, f2 = faces.face2_edges(oos)

    log("[6/7] leak audit ...")
    cal = oos[oos["calibrated"]]
    mkt = cal[cal["q_mkt"].notna()]
    blocks = [
        audit.metric_block(cal["y"].to_numpy(), cal["p_raw"].to_numpy(), "model_raw"),
        audit.metric_block(cal["y"].to_numpy(), cal["p_cal"].to_numpy(), "model_calibrated"),
    ]
    if len(mkt) > 100:
        blocks += [
            audit.metric_block(mkt["y"].to_numpy(), mkt["p_cal"].to_numpy(), "model_cal_(odds_rows)"),
            audit.metric_block(mkt["y"].to_numpy(), mkt["p_blend"].to_numpy(), "blend_(odds_rows)"),
            audit.metric_block(mkt["y"].to_numpy(), mkt["q_mkt"].to_numpy(), "market_vigfree_close"),
            audit.metric_block(mkt["y"].to_numpy(),
                               (mkt["q_mkt"] >= 0.5).astype(float).to_numpy(), "always_favorite"),
        ]
    metrics = pd.DataFrame(blocks)
    flags = audit.too_good_flags(oos)
    pit = audit.pit_structural_check(model_df, fights)
    cal_table, ece = audit.calibration_table(oos)
    seg = audit.segment_brier(oos)
    imp = audit.feature_importance(last_model, list(X.columns))
    asym = oos["raw_asymmetry"]

    log("[7/7] writing report ...")
    oos.to_csv(f"{outdir}/oos_predictions.csv", index=False)
    if not bets.empty:
        bets.to_csv(f"{outdir}/edge_bets.csv", index=False)
    imp.to_csv(f"{outdir}/feature_importance.csv", index=False)

    lines = ["# CFL Engine report", ""]
    lines += ["## Headline metrics (out-of-sample, calibrated folds)", "",
              metrics.to_markdown(index=False), ""]
    lines += ["## Leak audit", "",
              f"- Corner-symmetry residual (pre-averaging): mean {asym.mean():.4f}, "
              f"max {asym.max():.4f}; symmetric averaging enforces P(A)+P(B)=1 exactly at inference.",
              f"- Point-in-time structural check: {pit['mismatches']} mismatches "
              f"in {pit['checked']} sampled rows (must be 0).",
              f"- Calibration ECE: {ece:.4f}", ""]
    lines += [f"- {f}" for f in flags] or ["- No too-good red flags fired."]
    lines += ["", "## Face 1 — picks by tier (sell the accuracy)", "",
              f1.to_markdown(), ""]
    lines += ["## Face 2 — edge bets vs vig-free close (sell the ROI)", ""]
    if f2 and f2.get("n_bets", 0) > 0:
        lines += [f"- {k}: {v:.4f}" if isinstance(v, float) else f"- {k}: {v}"
                  for k, v in f2.items()]
        lines += ["", "Reminder: realized ROI on this sample size is mostly noise; "
                  "the product metric is CLV beat rate once bet-time lines are captured."]
    else:
        lines += ["- No odds provided or no bets cleared the edge threshold."]
    lines += ["", "## Calibration table", "", cal_table.to_markdown(index=False), ""]
    if not seg.empty:
        lines += ["## Segment Brier: model vs market (positive = market wins; candidate no-bet zones)",
                  "", seg.to_markdown(index=False), ""]
    lines += ["## Top features (gain)", "", imp.to_markdown(index=False), ""]
    with open(f"{outdir}/report.md", "w") as f:
        f.write("\n".join(lines))
    log(f"done -> {outdir}/report.md")
    return oos, metrics, flags, f1, f2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fights")
    ap.add_argument("--stats")
    ap.add_argument("--fighters")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--synthetic", action="store_true")
    args = ap.parse_args()

    if args.synthetic:
        import make_synthetic
        os.makedirs(args.outdir, exist_ok=True)
        make_synthetic.generate(args.outdir)
        args.fights = f"{args.outdir}/fights.csv"
        args.stats = f"{args.outdir}/fight_stats.csv"
        args.fighters = f"{args.outdir}/fighters.csv"

    fights, stats, fighters = load_data(args.fights, args.stats, args.fighters)
    run(fights, stats, fighters, args.outdir)


if __name__ == "__main__":
    main()
