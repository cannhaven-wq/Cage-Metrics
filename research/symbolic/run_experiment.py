"""SYM-002 orchestrator. Runs every outer fold plus the final prospective fit.

    python run_experiment.py            # all folds, in parallel
    python run_experiment.py --fold 2021

Writes, under private/ (git-ignored):
  results/fold_<id>.pkl          predictions, selections, per-run stability
  logs/candidates_<id>_<exp>.csv.gz   every candidate expression scored
  models/final_<exp>.json        frozen prospective models + SHA-256
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import pickle
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

import symreg as S
from features import CFG, DATA, FEATS, HERE

PRIV = os.path.join(HERE, "private")
SC, VC = CFG["search"], CFG["validation"]
CLIP = CFG["preprocessing"]["clip_z"]
LAMBDA_GRID = [1 / c for c in (0.01, 0.03, 0.1, 0.3, 1, 3)]
V1_REPORTED = {"age_yrs": -0.38835367, "elo": 0.26080176, "sapm": -0.21207802}
V1_MARKET_REPORTED = {"sapm": -0.14957978, "age_yrs": -0.12853881}
IDX = {f: i for i, f in enumerate(FEATS)}


# ------------------------------------------------------------------ preprocessing
class Prep:
    """Fold-local scaling + imputation, learned from training rows only."""

    def __init__(self, df):
        both = pd.concat([df[[f"a_{f}" for f in FEATS]].set_axis(FEATS, axis=1),
                          df[[f"b_{f}" for f in FEATS]].set_axis(FEATS, axis=1)])
        ok = both[["reach_in", "height_in"]].dropna()
        self.reach_slope, self.reach_icpt = np.polyfit(ok.height_in, ok.reach_in, 1)
        self.height_median = float(both.height_in.median())
        both = self._impute(both)
        self.mean = both.mean().to_dict()
        self.std = both.std().replace(0, 1).to_dict()

    def _impute(self, X):
        X = X.copy()
        X["height_in"] = X.height_in.fillna(self.height_median)
        X["reach_in"] = X.reach_in.fillna(self.reach_icpt + self.reach_slope * X.height_in)
        return X

    def side(self, df, s):
        X = self._impute(df[[f"{s}_{f}" for f in FEATS]].set_axis(FEATS, axis=1))
        Z = ((X - pd.Series(self.mean)) / pd.Series(self.std)).reindex(columns=FEATS)
        return np.clip(Z.fillna(0.0).to_numpy(float), -CLIP, CLIP)

    def AB(self, df):
        return self.side(df, "a"), self.side(df, "b")

    def to_dict(self):
        return {"mean": self.mean, "std": self.std, "clip_z": CLIP,
                "reach_from_height": {"intercept": self.reach_icpt, "slope": self.reach_slope},
                "height_median": self.height_median}


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


# ------------------------------------------------------------------ structure refit
def refit(trees, A, B, y, off=None, lam=1.0):
    cols, kept, sds = [], [], []
    for t in trees:
        v = S.term(t, A, B)
        s = float(np.std(v))
        if np.isfinite(s) and s > 1e-8:
            cols.append(v / s); kept.append(t); sds.append(s)
    X = np.column_stack(cols)
    w = S.fit_logistic(X, y, off, lam)
    return kept, np.array(sds), w


def predict(trees, sds, w, A, B, off=None):
    z = np.zeros(A.shape[0]) if off is None else off.copy()
    for t, s, wk in zip(trees, sds, w):
        z += wk * S.term(t, A, B) / s
    return S.sigmoid(z)


# ------------------------------------------------------------------ fold
def split(df, fold):
    base = df[df.eligible_fighters & (df.event_date >= CFG["data"]["train_rows_from"])]
    if fold == "final":
        cut = pd.Timestamp("2026-10-04")
        test = base.iloc[0:0]
        val_from = pd.Timestamp("2025-01-01")
    else:
        cut = pd.Timestamp(f"{fold}-01-01")
        test = df[df.eligible_eval & (df.event_date.dt.year == fold)]
        val_from = pd.Timestamp(f"{fold - 2}-01-01")
    train = base[base.event_date < cut]
    return train, train[train.event_date < val_from], train[train.event_date >= val_from], test


def run_search(itr, iva, names, use_market, label, cand_log):
    pi = Prep(itr)
    Atr, Btr = pi.AB(itr); Ava, Bva = pi.AB(iva)
    data = S.SearchData(Atr, Btr, itr.y.to_numpy(), Ava, Bva, iva.y.to_numpy(),
                        logit(itr.p_a_archived.to_numpy()) if use_market else None,
                        logit(iva.p_a_archived.to_numpy()) if use_market else None)
    runs = []
    for cname, c in SC["configs"].items():
        for seed in SC["seeds"]:
            s = S.Search(data, names, c["max_depth"], c["max_terms"], seed, SC["population"],
                         SC["generations"], SC["tournament"], SC["elitism"], SC["hall_of_fame"],
                         SC["complexity_penalty_per_node"], log=cand_log, run_label=f"{label}|{cname}|{seed}")
            hof = s.run()
            runs.append({"config": cname, "seed": seed, "hof": hof})
    return runs


def run_fold(fold):
    t0 = time.time()
    df = pd.read_parquet(os.path.join(DATA, "features.parquet"))
    train, itr, iva, test = split(df, fold)
    out = {"fold": fold, "n_train": len(train), "n_inner_train": len(itr), "n_inner_val": len(iva),
           "n_test": len(test), "n_test_events": int(test.event_id.nunique())}
    po = Prep(train)
    A, B = po.AB(train); y = train.y.to_numpy()
    At, Bt = po.AB(test) if len(test) else (None, None)
    preds = {}
    models = {}

    for exp, use_mkt in (("A", False), ("B", True)):
        tr = train[train.p_a_archived.between(0.01, 0.99)] if use_mkt else train
        i_tr = itr[itr.p_a_archived.between(0.01, 0.99)] if use_mkt else itr
        i_va = iva[iva.p_a_archived.between(0.01, 0.99)] if use_mkt else iva
        log = []
        runs = run_search(i_tr, i_va, FEATS, use_mkt, f"{fold}|{exp}", log)
        with gzip.open(os.path.join(PRIV, "logs", f"candidates_{fold}_{exp}.csv.gz"), "wt") as fh:
            fh.write("run,expression_set,n_terms,nodes,inner_val_logloss,penalised_score\n")
            for r in log:
                fh.write(",".join([r[0], '"' + r[1].replace('"', "'") + '"'] + [str(x) for x in r[2:]]) + "\n")
        out[f"n_candidates_{exp}"] = len(log)
        Ae, Be = po.AB(tr); ye = tr.y.to_numpy()
        off = logit(tr.p_a_archived.to_numpy()) if use_mkt else None
        offt = logit(test.p_a_archived.to_numpy()) if (use_mkt and len(test)) else None

        # pre-declared rule: global best penalised inner score across all 15 runs
        allbest = sorted(((r["hof"][0], r) for r in runs), key=lambda x: x[0][0][0])
        (score, ind), _ = allbest[0]
        trees, sds, w = refit(list(ind), Ae, Be, ye, off)
        models[exp] = {"trees": trees, "sds": sds, "w": w, "inner_score": score, "prep": po.to_dict()}
        if len(test):
            preds[f"{exp}_symbolic"] = predict(trees, sds, w, At, Bt, offt)
            ps = predict(trees, sds, w, Bt, At, None if offt is None else -offt)
            out[f"swap_max_err_{exp}"] = float(np.max(np.abs(preds[f"{exp}_symbolic"] + ps - 1)))
        # stability: every run's own best, refitted and scored
        stab = []
        for r in runs:
            (sc, ind_r) = r["hof"][0]
            tr_r, sd_r, w_r = refit(list(ind_r), Ae, Be, ye, off)
            row = {"config": r["config"], "seed": r["seed"], "inner_penalised": sc[0], "inner_ll": sc[1],
                   "nodes": sc[2], "expression": sc[3]}
            if len(test):
                p = predict(tr_r, sd_r, w_r, At, Bt, offt)
                row["test_ll"] = S.logloss(p, test.y.to_numpy())
            stab.append(row)
        out[f"stability_{exp}"] = stab
        out[f"hof_{exp}"] = [(sc, [S.to_str(t, FEATS) for t in ind]) for r in runs for sc, ind in r["hof"][:5]]
        if exp == "A":
            hof_all = sorted({sc[3]: (sc, ind) for r in runs for sc, ind in r["hof"]}.values(), key=lambda x: x[0][0])
            discovered = {}
            for sc, ind in hof_all[:5]:
                for t in ind:
                    if t[0] != "x" or t[1] != 0:                     # skip plain linear diffs (already in base)
                        discovered[S.to_str(t, FEATS)] = t

    # ---------------- Experiment C and the linear baseline (same lambda selection)
    pi = Prep(itr)
    Ai, Bi = pi.AB(itr); Av, Bv = pi.AB(iva)
    lin = [("x", 0, i) for i in range(len(FEATS))]
    for name, trees in (("C_lr_plus_symbolic", lin + list(discovered.values())), ("LR_linear", lin)):
        best = None
        for lam in LAMBDA_GRID:
            k, s_, w_ = refit(trees, Ai, Bi, itr.y.to_numpy(), lam=lam)
            ll = S.logloss(predict(k, s_, w_, Av, Bv), iva.y.to_numpy())
            if best is None or ll < best[0]:
                best = (ll, lam)
        k, s_, w_ = refit(trees, A, B, y, lam=best[1])
        models[name] = {"trees": k, "sds": s_, "w": w_, "lambda": best[1], "inner_ll": best[0], "prep": po.to_dict()}
        if len(test):
            preds[name] = predict(k, s_, w_, At, Bt)
            out[f"swap_max_err_{name}"] = float(np.max(np.abs(preds[name] + predict(k, s_, w_, Bt, At) - 1)))

    # ---------------- v1 reference structure, refitted; and v1 reported weights (approximate)
    v1 = [("x", 0, IDX["age_yrs"]), ("x", 0, IDX["elo"]), ("x", 0, IDX["sapm"])]
    k, s_, w_ = refit(v1, A, B, y)
    models["v1_refit"] = {"trees": k, "sds": s_, "w": w_, "prep": po.to_dict()}
    tm = train[train.p_a_archived.between(0.01, 0.99)]
    Am, Bm = po.AB(tm)
    v1m = [("x", 0, IDX["sapm"]), ("x", 0, IDX["age_yrs"])]
    km, sm, wm = refit(v1m, Am, Bm, tm.y.to_numpy(), logit(tm.p_a_archived.to_numpy()))
    models["v1_market_refit"] = {"trees": km, "sds": sm, "w": wm, "prep": po.to_dict()}
    if len(test):
        yt = test.y.to_numpy()
        preds["v1_refit"] = predict(k, s_, w_, At, Bt)
        preds["v1_market_refit"] = predict(km, sm, wm, At, Bt, logit(test.p_a_archived.to_numpy()))
        # reported coefficients on standardised differences (d / train std of d)
        z = np.zeros(len(test)); zm = logit(test.p_a_archived.to_numpy())
        for f, c in V1_REPORTED.items():
            sd = float(np.std(train[f"a_{f}"] - train[f"b_{f}"]))
            z += c * (test[f"a_{f}"] - test[f"b_{f}"]).to_numpy() / sd
        for f, c in V1_MARKET_REPORTED.items():
            sd = float(np.std(train[f"a_{f}"] - train[f"b_{f}"]))
            zm += c * (test[f"a_{f}"] - test[f"b_{f}"]).to_numpy() / sd
        preds["v1_reported_coefs"] = S.sigmoid(z)
        preds["v1_market_reported_coefs"] = S.sigmoid(zm)
        preds["market_archived"] = test.p_a_archived.to_numpy()
        preds["elo_only"] = S.sigmoid(np.log(10) / 400 * (test.a_elo - test.b_elo).to_numpy())
        out["test"] = test[["fight_id", "event_id", "event_date", "y", "p_a_verified", "mins_before_start"]].reset_index(drop=True)
        out["preds"] = pd.DataFrame(preds)
    out["models"] = models
    out["discovered_terms_for_C"] = list(discovered.keys())
    out["seconds"] = round(time.time() - t0, 1)
    pickle.dump(out, open(os.path.join(PRIV, "results", f"fold_{fold}.pkl"), "wb"))
    if fold == "final":
        save_final(models)
    print(f"fold {fold} done in {out['seconds']}s", flush=True)
    return fold


def serial(m, kind):
    return {"kind": kind, "features": FEATS, "preprocessing": m["prep"],
            "terms": [{"expression_h": S.to_str(t, FEATS), "tree": t, "train_std": float(s), "weight": float(w),
                       "linear": S.is_linear(t)} for t, s, w in zip(m["trees"], m["sds"], m["w"])],
            "lambda": m.get("lambda", 1.0),
            "formula": "P(A wins) = sigmoid(" + ("logit(p_market_A) + " if kind == "B" else "")
                       + "sum_k weight_k * (h_k(zA, zB) - h_k(zB, zA)) / train_std_k)"}


def save_final(models):
    os.makedirs(os.path.join(PRIV, "models"), exist_ok=True)
    hashes = {}
    for name, kind in (("A", "A"), ("B", "B"), ("C_lr_plus_symbolic", "C"), ("LR_linear", "LR"), ("v1_refit", "v1")):
        body = json.dumps(serial(models[name], kind), indent=1, default=float, sort_keys=True)
        path = os.path.join(PRIV, "models", f"final_{name}.json")
        open(path, "w").write(body)
        hashes[name] = hashlib.sha256(body.encode()).hexdigest()
    json.dump({"frozen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "trained_through": "2026-10-03",
               "prospective_from": "events after 2026-10-07", "sha256": hashes},
              open(os.path.join(PRIV, "models", "FROZEN.json"), "w"), indent=2)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fold", default=None)
    a = ap.parse_args()
    for d in ("results", "logs", "models"):
        os.makedirs(os.path.join(PRIV, d), exist_ok=True)
    folds = [a.fold if a.fold == "final" else int(a.fold)] if a.fold else VC["outer_test_years"] + ["final"]
    with Pool(min(4, len(folds))) as pool:
        for f in pool.imap_unordered(run_fold, folds):
            pass
