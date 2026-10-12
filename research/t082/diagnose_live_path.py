"""T-082 — does the live engine compute what its backtest computed?

A pipeline audit of the incumbent engine (engine_v2), not a model experiment.
Nothing here is fitted to be kept, nothing is published, and nothing is written
to the database. It runs against a fresh `cfl_engine/export_data.py` export and
prints its findings. It ran once, as a one-off contents:read GitHub Actions
workflow (run 38298613704, since removed), because the agent sandbox cannot
reach the Supabase host. Results: results_2026-10-12.json, T082_REPORT_2026-10-12.md.

Why it exists. On the locked pre-fight record (2026-08-15 -> 10-10) the engine
scored 0.717 log loss against a backtest of ~0.654, and its live picks back the
DB "A" corner far less often than the backtest did (41% vs 54%) while A corners
win as often as ever. Either the live code path differs from the backtest path,
or the live data differs from what the backtest saw, or it is noise. Three
checks separate those:

  A. FEATURES.  For every live engine_v2 fight, rebuild the serving features
     exactly as predict_upcoming does (history = completed fights before the
     publish date, plus the target card as placeholder rows, per event) and
     compare them, column by column, to the backtest builder's features for the
     same fight. A correct serving path gives identical features except where a
     fighter fought between the publish date and the bout.

  B. REPRODUCTION.  Re-run the production training + calibration path as of
     each publish date and compare the reproduced P(A) with the locked p_cal.
     Probabilities only; no outcome of a live fight is read.

  C. PATH EQUIVALENCE on DEV ONLY.  On fights from 2022-09-17 to 2024-01-19
     (the backtest's fold 3, entirely before the PRED-001 seal), train the
     backtest path and the live path on the same pre-cutoff fights and compare
     their predictions, their corner tilt, and their log loss. Every fight and
     outcome this check reads is dated before 2025-01-01.

Sealed-data note (PRED-001 §2). Checks A and B read fights dated 2025+ only in
the way production already does every morning: the live engine is trained on
all completed fights. They score nothing on sealed data and print no outcome of
a sealed fight. Check C is DEV-only and asserts it.

Usage (repo root, after export_data.py):
  PYTHONPATH=cfl_engine python research/t082/diagnose_live_path.py --outdir out_t082
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.join(HERE, os.pardir, os.pardir, "cfl_engine")
sys.path.insert(0, ENGINE_DIR)

import predict_upcoming as pu  # noqa: E402  (production serving module, unmodified)
from engine import (FIGHTER_FEATS, STATIC_FEATS, build_features,  # noqa: E402
                    devig_a, load_data, make_matchup_features,
                    predict_symmetric, randomize_corners)
from export_data import fetch_all  # noqa: E402
from train import EPS, FIXED, tune  # noqa: E402
from xgboost import XGBClassifier  # noqa: E402

DATA_DIR = os.path.join(ENGINE_DIR, "data")
SEAL = pd.Timestamp("2025-01-01")
C_START, C_END = pd.Timestamp("2022-09-17"), pd.Timestamp("2024-01-20")
CORNER_FEATS = FIGHTER_FEATS + STATIC_FEATS


def ll(y, p):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    y = np.asarray(y, float)
    return float(np.mean(-(y * np.log(p) + (1 - y) * np.log(1 - p))))


def serve_features(history: pd.DataFrame, stats, fighters, card: pd.DataFrame):
    """predict_upcoming's serving build, line for line: the card's rows are
    placeholders (result 'nc', no odds) appended to completed history, one
    build per event, and only the card's rows are kept."""
    rows = card.copy()
    rows["result"] = "nc"
    rows["method"] = np.nan
    rows["odds_a"] = np.nan
    rows["odds_b"] = np.nan
    parts = []
    for _key, grp in rows.groupby("event_key"):
        g = grp.reindex(columns=history.columns)
        combined = pd.concat([history, g], ignore_index=True)
        feat = build_features(combined, stats, fighters)
        parts.append(feat[feat["fight_id"].isin(set(grp["fight_id"]))])
    return pd.concat(parts, ignore_index=True)


def corner_summary(p_a: np.ndarray, q_a: np.ndarray) -> dict:
    has_q = ~np.isnan(q_a)
    pa, qa = p_a[has_q], q_a[has_q]
    dis = (pa >= 0.5) != (qa >= 0.5)
    return {
        "n": int(len(p_a)),
        "pick_a_share": round(float(np.mean(p_a >= 0.5)), 4),
        "mean_conf": round(float(np.mean(np.maximum(p_a, 1 - p_a))), 4),
        "share_conf_ge_0_70": round(float(np.mean(np.maximum(p_a, 1 - p_a) >= 0.70)), 4),
        "n_with_market": int(has_q.sum()),
        "market_fav_a_share": round(float(np.mean(qa >= 0.5)), 4) if has_q.any() else None,
        "disagree_share": round(float(np.mean(dis)), 4) if has_q.any() else None,
        "disagree_engine_b_market_a": int(np.sum(dis & (qa >= 0.5))),
        "disagree_engine_a_market_b": int(np.sum(dis & (qa < 0.5))),
    }


# ---------------------------------------------------------------- live pulls
def pull_live(base_url: str, key: str) -> pd.DataFrame:
    picks = fetch_all(base_url, key, "model_picks",
                      "select=fight_id,p_cal,pick_side,published_at,model_version"
                      "&source=eq.live&model_version=eq.engine_v2&order=fight_id")
    ids = sorted({p["fight_id"] for p in picks})
    frows = []
    for i in range(0, len(ids), 150):
        chunk = ",".join(str(x) for x in ids[i:i + 150])
        frows += fetch_all(base_url, key, "fights",
                           "select=id,event_id,fighter_a_id,fighter_b_id,"
                           f"weight_class,scheduled_rounds&id=in.({chunk})")
    evs = {e["id"]: e for e in fetch_all(base_url, key, "events",
                                         "select=id,event_date&order=id")}
    fmap = {f["id"]: f for f in frows}
    out = []
    for p in picks:
        f = fmap.get(p["fight_id"])
        if f is None:
            continue
        pa = float(p["p_cal"]) if p["pick_side"] == "a" else 1.0 - float(p["p_cal"])
        out.append({
            "fight_id": p["fight_id"], "event_id": f["event_id"],
            "event_key": f["event_id"],
            "event_date": pd.Timestamp(evs[f["event_id"]]["event_date"]),
            "fighter_a_id": f["fighter_a_id"], "fighter_b_id": f["fighter_b_id"],
            "weight_class": f["weight_class"],
            "n_rounds_sched": f["scheduled_rounds"],
            "locked_p_a": pa,
            "published_at": pd.Timestamp(p["published_at"]),
        })
    return pd.DataFrame(out)


def pull_live_market(base_url: str, key: str, fight_ids) -> dict:
    """Market P(A) the pre-fight snapshot froze for each fight (first snapshot)."""
    out = {}
    ids = list(fight_ids)
    for i in range(0, len(ids), 150):
        chunk = ",".join(str(x) for x in ids[i:i + 150])
        rows = fetch_all(base_url, key, "pre_fight_snapshots",
                         "select=fight_id,snapshot_at,implied_prob_a,implied_prob_b"
                         f"&fight_id=in.({chunk})&order=snapshot_at")
        for r in rows:
            if r["fight_id"] in out:
                continue
            a, b = r.get("implied_prob_a"), r.get("implied_prob_b")
            if a is not None and b is not None and (a + b) > 0:
                out[r["fight_id"]] = float(a) / (float(a) + float(b))
    return out


# ---------------------------------------------------------------- checks
def check_a(live, fights, stats, fighters, feat_all) -> dict:
    """Serving features vs backtest features, per corner, per feature."""
    t0 = time.time()
    rows = []
    for pub_date, card in live.groupby(live["published_at"].dt.normalize().dt.tz_localize(None)):
        history = fights[fights["event_date"] < pub_date]
        sf = serve_features(history, stats, fighters, card)
        rows.append(sf)
    serve = pd.concat(rows, ignore_index=True).set_index("fight_id")
    back = feat_all.set_index("fight_id")
    common = serve.index.intersection(back.index)
    report = {"fights_compared": int(len(common)),
              "fights_not_yet_in_history": int(len(serve.index.difference(back.index)))}
    per_feat = {}
    for f in CORNER_FEATS:
        for side in ("a", "b"):
            c = f"{side}_{f}"
            s, b = serve.loc[common, c].astype(float), back.loc[common, c].astype(float)
            both_nan = s.isna() & b.isna()
            diff = ~both_nan & ~np.isclose(s.fillna(-9e9), b.fillna(-9e9), atol=1e-9)
            per_feat[c] = {"mismatches": int(diff.sum()),
                           "mean_serve": None if s.isna().all() else round(float(s.mean()), 4),
                           "mean_backtest": None if b.isna().all() else round(float(b.mean()), 4)}
    report["per_feature"] = per_feat
    report["total_mismatching_cells"] = int(sum(v["mismatches"] for v in per_feat.values()))
    # the shared columns the model also reads
    for c in ("wc_code", "n_rounds_sched"):
        s, b = serve.loc[common, c].astype(float), back.loc[common, c].astype(float)
        report[f"{c}_mismatches"] = int((~np.isclose(s.fillna(-1), b.fillna(-1))).sum())
    report["seconds"] = round(time.time() - t0, 1)
    return report, serve


def check_b(live, fights, stats, fighters, market) -> dict:
    """Re-run production training/calibration as of each publish date."""
    t0 = time.time()
    calibrate, _blend = pu.fit_calibrator_and_blend(log=lambda *_: None)
    out = []
    for pub_date, card in live.groupby(live["published_at"].dt.normalize().dt.tz_localize(None)):
        history = fights[fights["event_date"] < pub_date]
        feat_hist = build_features(history, stats, fighters)
        model, diff_cols = pu.train_final_model(feat_hist, log=lambda *_: None)
        sf = serve_features(history, stats, fighters, card)
        X, dc, _ = make_matchup_features(sf)
        assert dc == diff_cols
        p_raw, _ = predict_symmetric(model, X, diff_cols)
        p_cal = np.clip(calibrate(p_raw), pu.PUBLISH_P_MIN, pu.PUBLISH_P_MAX)
        got = pd.DataFrame({"fight_id": sf["fight_id"].to_numpy(), "repro_p_a": p_cal,
                            "repro_p_raw_a": p_raw})
        out.append(card[["fight_id", "locked_p_a"]].merge(got, on="fight_id"))
    df = pd.concat(out, ignore_index=True)
    d = (df["repro_p_a"] - df["locked_p_a"]).abs()
    q = np.array([market.get(int(f), np.nan) for f in df["fight_id"]])
    return {
        "n": int(len(df)),
        "abs_diff_max": round(float(d.max()), 6),
        "abs_diff_mean": round(float(d.mean()), 6),
        "share_within_0_001": round(float((d < 1e-3).mean()), 4),
        "share_same_side": round(float(((df["repro_p_a"] >= 0.5) == (df["locked_p_a"] >= 0.5)).mean()), 4),
        "corr": round(float(np.corrcoef(df["repro_p_a"], df["locked_p_a"])[0, 1]), 4),
        "locked": corner_summary(df["locked_p_a"].to_numpy(), q),
        "reproduced": corner_summary(df["repro_p_a"].to_numpy(), q),
        "seconds": round(time.time() - t0, 1),
    }, df


def check_c(fights, stats, fighters, oos_csv) -> dict:
    """DEV-only: backtest path vs live path on the backtest's fold 3."""
    t0 = time.time()
    dev = fights[fights["event_date"] < SEAL].reset_index(drop=True)
    assert dev["event_date"].max() < SEAL, "check C must not read sealed fights"
    feat_all = build_features(dev, stats, fighters)
    window = feat_all[(feat_all["event_date"] >= C_START) & (feat_all["event_date"] < C_END)
                      & feat_all["result"].isin(["a", "b"])].reset_index(drop=True)
    feat_train = feat_all[feat_all["event_date"] < C_START].reset_index(drop=True)

    # calibrator: isotonic on the committed walk-forward OOS of folds 0-2 only
    # (all dated before C_START), the rows the backtest's own fold-3 calibrator saw
    from sklearn.isotonic import IsotonicRegression
    oos = pd.read_csv(oos_csv)
    prior = oos[oos["fold"] < 3]
    assert pd.to_datetime(prior["event_date"]).max() <= C_START
    iso = IsotonicRegression(y_min=EPS, y_max=1 - EPS, out_of_bounds="clip")
    iso.fit(prior["p_raw"].to_numpy(), prior["y"].to_numpy())

    y_db = (window["result"] == "a").astype(int).to_numpy()
    q_db = np.array([devig_a(a, b) for a, b in zip(window["odds_a"], window["odds_b"])])

    # --- backtest path: walk_forward's fold model (ES on the last 10% of train)
    def backtest_path(seed):
        rnd = randomize_corners(feat_train, seed=seed)
        md = rnd[rnd["result"].isin(["a", "b"])].reset_index(drop=True)
        y = (md["result"] == "a").astype(int).to_numpy()
        X, diff_cols, _ = make_matchup_features(md)
        params = tune(X, y, int(len(md) * 0.55), log=lambda *_: None)
        es = int(len(X) * 0.9)
        m = XGBClassifier(early_stopping_rounds=75, **{**FIXED, **params})
        m.fit(X.iloc[:es], y[:es], eval_set=[(X.iloc[es:], y[es:])], verbose=False)
        Xw, _, _ = make_matchup_features(window)   # DB corners; symmetric inference
        p_raw, _ = predict_symmetric(m, Xw, diff_cols)
        return p_raw, params, int(m.best_iteration)

    bt_raw, bt_params, bt_iter = backtest_path(42)
    bt7_raw, _, _ = backtest_path(7)

    # --- live path: predict_upcoming.train_final_model + serving feature build
    lv_model, lv_cols = pu.train_final_model(feat_train, log=lambda *_: None)
    card = dev[(dev["event_date"] >= C_START) & (dev["event_date"] < C_END)
               & dev["result"].isin(["a", "b"])].copy()
    card["event_key"] = card["event_date"]
    # history for each card is every completed fight before it (production's
    # view on publish day), so build per event date against `dev`
    parts = []
    for d, grp in card.groupby("event_date"):
        hist = dev[dev["event_date"] < d]
        parts.append(serve_features(hist, stats, fighters, grp))
    sf = pd.concat(parts, ignore_index=True).set_index("fight_id").loc[window["fight_id"]].reset_index()
    feat_cells = 0
    for f in CORNER_FEATS:
        for side in ("a", "b"):
            c = f"{side}_{f}"
            s, b = sf[c].astype(float), window[c].astype(float)
            feat_cells += int((~(s.isna() & b.isna()) & ~np.isclose(s.fillna(-9e9), b.fillna(-9e9))).sum())
    Xs, dc, _ = make_matchup_features(sf)
    assert dc == lv_cols
    lv_raw, _ = predict_symmetric(lv_model, Xs, lv_cols)

    res = {"window": [str(C_START.date()), str((C_END - pd.Timedelta(days=1)).date())],
           "fights": int(len(window)), "train_fights_before_window": int(len(feat_train)),
           "serving_vs_backtest_feature_mismatching_cells": feat_cells,
           "backtest_params": bt_params, "backtest_best_iter": bt_iter}
    for name, raw in (("backtest_seed42", bt_raw), ("backtest_seed7", bt7_raw), ("live_path", lv_raw)):
        cal = iso.predict(raw)
        res[name] = {**corner_summary(cal, q_db),
                     "log_loss_cal": round(ll(y_db, cal), 4),
                     "log_loss_raw": round(ll(y_db, raw), 4),
                     "a_win_share": round(float(y_db.mean()), 4)}
    res["live_vs_backtest_mean_abs_diff_p"] = round(float(np.mean(np.abs(iso.predict(lv_raw) - iso.predict(bt_raw)))), 4)
    res["seed7_vs_seed42_mean_abs_diff_p"] = round(float(np.mean(np.abs(iso.predict(bt7_raw) - iso.predict(bt_raw)))), 4)
    res["market_log_loss"] = round(ll(y_db[~np.isnan(q_db)], q_db[~np.isnan(q_db)]), 4)
    res["seconds"] = round(time.time() - t0, 1)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="out_t082")
    ap.add_argument("--skip", default="", help="comma list of checks to skip (a,b,c)")
    args = ap.parse_args()
    skip = set(filter(None, args.skip.split(",")))
    os.makedirs(args.outdir, exist_ok=True)

    import sklearn
    import xgboost
    report = {"run_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
              "versions": {"xgboost": xgboost.__version__, "sklearn": sklearn.__version__,
                           "pandas": pd.__version__, "numpy": np.__version__}}

    fights, stats, fighters = load_data(os.path.join(DATA_DIR, "fights.csv"),
                                        os.path.join(DATA_DIR, "fight_stats.csv"),
                                        os.path.join(DATA_DIR, "fighters.csv"))
    report["export"] = {"fights": int(len(fights)),
                        "last_event_date": str(fights["event_date"].max().date())}

    if "c" not in skip:
        report["C_path_equivalence_dev"] = check_c(fights, stats, fighters, pu.OOS_CSV)
        print(json.dumps({"C": report["C_path_equivalence_dev"]}, indent=1), flush=True)

    if not ({"a", "b"} <= skip):
        base_url = os.environ["SUPABASE_URL"].rstrip("/")
        key = pu._env_key()
        live = pull_live(base_url, key)
        market = pull_live_market(base_url, key, live["fight_id"])
        report["live_fights"] = int(len(live))
        report["live_publish_dates"] = int(live["published_at"].dt.normalize().nunique())
        report["live_days_ahead_median"] = round(float(
            ((live["event_date"] - live["published_at"].dt.tz_localize(None)).dt.total_seconds() / 86400).median()), 2)
        if "a" not in skip:
            feat_all = build_features(fights, stats, fighters)
            report["A_feature_parity"], serve = check_a(live, fights, stats, fighters, feat_all)
            print(json.dumps({"A": {k: v for k, v in report["A_feature_parity"].items()
                                    if k != "per_feature"}}, indent=1), flush=True)
            bad = {k: v for k, v in report["A_feature_parity"]["per_feature"].items() if v["mismatches"]}
            print(json.dumps({"A_mismatching_features": bad}, indent=1), flush=True)
            # corner balance of the serving features, live vs backtest years
            gaps = {}
            for f in CORNER_FEATS:
                gaps[f] = round(float((serve[f"a_{f}"] - serve[f"b_{f}"]).mean()), 4)
            report["A_live_mean_a_minus_b"] = gaps
        if "b" not in skip:
            report["B_reproduction"], df = check_b(live, fights, stats, fighters, market)
            df.to_csv(os.path.join(args.outdir, "b_reproduction.csv"), index=False)
            print(json.dumps({"B": report["B_reproduction"]}, indent=1), flush=True)

    with open(os.path.join(args.outdir, "t082_report.json"), "w") as f:
        json.dump(report, f, indent=1, default=str)
    print("wrote", os.path.join(args.outdir, "t082_report.json"))


if __name__ == "__main__":
    main()
