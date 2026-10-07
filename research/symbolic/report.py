"""SYM-002 evaluation + report. Reads private/results/fold_*.pkl, writes
private/results/metrics.json and private/REPORT.md. Fits nothing new except the
pre-declared leakage illustration (v1 structure on career-table inputs)."""
from __future__ import annotations

import json
import os
import pickle

import numpy as np
import pandas as pd

import symreg as S
from features import CFG, DATA, FEATS, HERE
from run_experiment import Prep, logit, predict, refit, serial

PRIV = os.path.join(HERE, "private")
YEARS = CFG["validation"]["outer_test_years"]
HEADLINE = [y for y in YEARS if y != 2026]
MODELS = ["A_symbolic", "B_symbolic", "C_lr_plus_symbolic", "LR_linear", "v1_refit", "v1_reported_coefs",
          "v1_market_refit", "v1_market_reported_coefs", "elo_only", "market_archived"]
COMPARE = [("A_symbolic", "LR_linear"), ("A_symbolic", "v1_refit"), ("A_symbolic", "v1_reported_coefs"),
           ("C_lr_plus_symbolic", "LR_linear"), ("B_symbolic", "market_archived"),
           ("B_symbolic", "v1_market_refit"), ("LR_linear", "v1_refit"), ("market_archived", "LR_linear"),
           ("market_archived", "A_symbolic")]
BOOT, BOOT_SEED = 2000, 7


def metrics(p, y):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    # calibration: y ~ sigmoid(a + b * logit(p))
    X = np.column_stack([np.ones_like(p), logit(p)])
    w = np.array([0.0, 1.0])
    for _ in range(50):
        q = S.sigmoid(X @ w)
        H = (X * (q * (1 - q))[:, None]).T @ X + 1e-9 * np.eye(2)
        st = np.linalg.solve(H, X.T @ (q - y)); w -= st
        if np.abs(st).max() < 1e-10:
            break
    bins = np.clip((p * 10).astype(int), 0, 9)
    ece = sum(abs(p[bins == b].mean() - y[bins == b].mean()) * (bins == b).mean() for b in range(10) if (bins == b).any())
    return {"n": int(len(y)), "logloss": S.logloss(p, y), "brier": float(np.mean((p - y) ** 2)),
            "accuracy": float(np.mean((p > 0.5) == (y == 1))), "cal_intercept": float(w[0]),
            "cal_slope": float(w[1]), "ece": float(ece)}


def reliability(p, y):
    bins = np.clip((p * 10).astype(int), 0, 9)
    return [{"bin": f"{b/10:.1f}-{(b+1)/10:.1f}", "n": int((bins == b).sum()),
             "mean_pred": float(p[bins == b].mean()), "observed": float(y[bins == b].mean())}
            for b in range(10) if (bins == b).sum() > 0]


def ll_vec(p, y):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def boot_diff(df, m1, m2):
    """Event-level bootstrap of mean log-loss(m1) - log-loss(m2). Negative favours m1."""
    d = ll_vec(df[m1].to_numpy(), df.y.to_numpy()) - ll_vec(df[m2].to_numpy(), df.y.to_numpy())
    g = pd.DataFrame({"e": df.event_id.to_numpy(), "d": d}).groupby("e").d.agg(["sum", "count"])
    s, c = g["sum"].to_numpy(), g["count"].to_numpy()
    rng = np.random.default_rng(BOOT_SEED)
    idx = rng.integers(len(g), size=(BOOT, len(g)))
    bs = s[idx].sum(1) / c[idx].sum(1)
    return {"diff": float(d.mean()), "ci95": [float(np.quantile(bs, .025)), float(np.quantile(bs, .975))],
            "n_fights": int(len(d)), "n_events": int(len(g))}


def standalone_predict(model_json, df):
    """Predict from a serialised model ONLY (no in-memory objects)."""
    pr = model_json["preprocessing"]
    def side(s):
        X = df[[f"{s}_{f}" for f in model_json["features"]]].set_axis(model_json["features"], axis=1).copy()
        X["height_in"] = X.height_in.fillna(pr["height_median"])
        r = pr["reach_from_height"]
        X["reach_in"] = X.reach_in.fillna(r["intercept"] + r["slope"] * X.height_in)
        feats = model_json["features"]
        Z = (X - pd.Series(pr["mean"])[feats]) / pd.Series(pr["std"])[feats]
        Z = Z.reindex(columns=feats)      # pandas re-sorts columns on misaligned labels; pin the order
        return np.clip(Z.fillna(0.0).to_numpy(float), -pr["clip_z"], pr["clip_z"])
    A, B = side("a"), side("b")
    z = logit(df.p_a_archived.to_numpy()) if model_json["kind"] == "B" else np.zeros(len(df))
    for t in model_json["terms"]:
        tree = _tuple(t["tree"])
        z += t["weight"] * S.term(tree, A, B) / t["train_std"]
    return S.sigmoid(z)


def _tuple(t):
    return tuple(_tuple(x) if isinstance(x, list) else x for x in t)


def main():
    folds = {y: pickle.load(open(os.path.join(PRIV, "results", f"fold_{y}.pkl"), "rb")) for y in YEARS}
    final = pickle.load(open(os.path.join(PRIV, "results", "fold_final.pkl"), "rb"))
    allp = []
    for y, o in folds.items():
        d = pd.concat([o["test"], o["preds"]], axis=1); d["fold"] = y; allp.append(d)
    P = pd.concat(allp, ignore_index=True)
    head, h26 = P[P.fold.isin(HEADLINE)], P[P.fold == 2026]
    M = {"per_fold": {}, "pooled_2021_2025": {}, "historical_2026": {}, "comparisons_2021_2025": {},
         "comparisons_2026": {}, "fold_wins": {}}
    for y in YEARS:
        d = P[P.fold == y]
        M["per_fold"][y] = {m: metrics(d[m].to_numpy(), d.y.to_numpy()) for m in MODELS}
        M["per_fold"][y]["_n_events"] = int(d.event_id.nunique())
    for m in MODELS:
        M["pooled_2021_2025"][m] = metrics(head[m].to_numpy(), head.y.to_numpy())
        M["historical_2026"][m] = metrics(h26[m].to_numpy(), h26.y.to_numpy())
    for m1, m2 in COMPARE:
        k = f"{m1} vs {m2}"
        M["comparisons_2021_2025"][k] = boot_diff(head, m1, m2)
        M["comparisons_2026"][k] = boot_diff(h26, m1, m2)
        wins = sum(M["per_fold"][y][m1]["logloss"] < M["per_fold"][y][m2]["logloss"] for y in HEADLINE)
        M["fold_wins"][k] = wins
        c = M["comparisons_2021_2025"][k]
        c["improves_by_preregistered_rule"] = bool(c["ci95"][1] < 0 and wins >= 4)
    M["reliability_2021_2025"] = {m: reliability(head[m].to_numpy(), head.y.to_numpy())
                                  for m in ("A_symbolic", "B_symbolic", "LR_linear", "market_archived")}

    # stability across seeds/configs
    M["stability"] = {}
    for exp in ("A", "B"):
        rows = []
        for y, o in folds.items():
            for r in o[f"stability_{exp}"]:
                rows.append({**r, "fold": y})
        st = pd.DataFrame(rows)
        M["stability"][exp] = {
            "per_fold_test_ll_across_15_runs": st.groupby("fold").test_ll.agg(["min", "median", "max", "std"]).round(5).to_dict("index"),
            "per_config_mean_test_ll_2021_2025": st[st.fold.isin(HEADLINE)].groupby("config").test_ll.mean().round(5).to_dict(),
            "distinct_structures_per_fold": st.groupby("fold").expression.nunique().to_dict(),
            "selected_expression_per_fold": {y: folds[y]["models"][exp]["inner_score"][3] for y in YEARS},
            "selected_nodes_per_fold": {y: int(folds[y]["models"][exp]["inner_score"][2]) for y in YEARS},
        }
        st.to_csv(os.path.join(PRIV, "results", f"stability_{exp}.csv"), index=False)
    M["candidates_scored"] = {y: {e: folds[y][f"n_candidates_{e}"] for e in ("A", "B")} for y in YEARS}
    M["candidates_scored"]["final"] = {e: final[f"n_candidates_{e}"] for e in ("A", "B")}
    M["swap_test_max_error"] = {y: {k: v for k, v in o.items() if k.startswith("swap")} for y, o in folds.items()}

    # verified-price fights (descriptive only)
    v = h26[h26.p_a_verified.notna()].copy()
    v["market_verified"] = v.p_a_verified
    M["verified_prices_2026"] = {m: metrics(v[m].to_numpy(), v.y.to_numpy())
                                 for m in ("market_verified", "market_archived", "A_symbolic", "B_symbolic", "LR_linear")}
    M["verified_prices_2026"]["_n_events"] = int(v.event_id.nunique())

    # saved-model re-prediction check: serialise each fold-2025 model and predict from JSON alone
    df = pd.read_parquet(os.path.join(DATA, "features.parquet"))
    o = folds[2025]
    test = df.set_index("fight_id").loc[o["test"].fight_id].reset_index()
    chk = {}
    for name, kind, col in (("A", "A", "A_symbolic"), ("B", "B", "B_symbolic"), ("C_lr_plus_symbolic", "C", "C_lr_plus_symbolic")):
        js = json.loads(json.dumps(serial(o["models"][name], kind), default=float))
        chk[col] = float(np.max(np.abs(standalone_predict(js, test) - o["preds"][col].to_numpy())))
    for name in ("A", "B", "C_lr_plus_symbolic", "LR_linear"):
        js = json.load(open(os.path.join(PRIV, "models", f"final_{name}.json")))
        tr = df[df.eligible_fighters & (df.event_date < "2026-10-04") & (df.event_date >= "2008-01-01")]
        if name == "B":
            tr = tr[tr.p_a_archived.between(0.01, 0.99)]
        po = Prep(df[df.eligible_fighters & (df.event_date < "2026-10-04") & (df.event_date >= "2008-01-01")])
        A_, B_ = po.AB(tr)
        m = final["models"][name]
        mem = predict(m["trees"], m["sds"], m["w"], A_, B_, logit(tr.p_a_archived.to_numpy()) if name == "B" else None)
        chk[f"final_{name}"] = float(np.max(np.abs(standalone_predict(js, tr) - mem)))
    M["saved_model_reprediction_max_abs_error"] = chk

    # leakage illustration: v1 structure on career-table inputs vs point-in-time, test 2026
    tr = df[df.eligible_fighters & (df.event_date >= "2008-01-01") & (df.event_date < "2026-01-01")]
    te = df[df.eligible_eval & (df.event_date.dt.year == 2026)]
    def zd(d, a, b, sd):
        return ((d[a] - d[b]) / sd).fillna(0).to_numpy()
    out = {}
    for label, cols in (("point_in_time", ("age_yrs", "elo", "sapm")), ("career_table", ("leaky_age_now", "elo", "leaky_sapm"))):
        sds = [float(np.std(tr[f"a_{c}"] - tr[f"b_{c}"])) for c in cols]
        X = np.column_stack([zd(tr, f"a_{c}", f"b_{c}", s) for c, s in zip(cols, sds)])
        Xt = np.column_stack([zd(te, f"a_{c}", f"b_{c}", s) for c, s in zip(cols, sds)])
        w = S.fit_logistic(X, tr.y.to_numpy())
        out[label] = {"weights_on_standardised_diffs": dict(zip(cols, map(float, w))), **metrics(S.sigmoid(Xt @ w), te.y.to_numpy())}
    M["leak_illustration_v1_structure_2026"] = out

    json.dump(M, open(os.path.join(PRIV, "results", "metrics.json"), "w"), indent=1, default=float)
    P.to_csv(os.path.join(PRIV, "results", "oos_predictions.csv"), index=False)
    print(json.dumps({k: M[k] for k in ("comparisons_2021_2025", "fold_wins")}, indent=1, default=float))


if __name__ == "__main__":
    main()
