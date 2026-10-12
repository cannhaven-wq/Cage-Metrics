"""PRED-002 Stage 1 — development years only. Run ONCE, after the freeze.

Implements PREREGISTRATION.md §2–§8 and its pre-freeze amendments A1–A5. Every
constant below is copied from the preregistration; changing one after the
freeze is an amendment, and changing one after the run is forbidden.

Input: a development-years export written by research/pred002_data/export_dev.py
(fights.csv, fight_stats.csv, fighters.csv, rounds.csv, manifest.json). This
file never reads a database.

Order of work, and why it matters:
  1. load, and refuse any fight dated 2025+ (pred_protocol.dev_only raises)
  2. choose eta on stat-prediction error, 2005-2012, without reading a result
  3. build the ratings and the incumbent engine's walk-forward forecasts
  4. PREFLIGHT, still without scoring a single forecast against a result:
     coverage floors (A1), exclusions by year (A2), corner symmetry, a
     point-in-time recheck of the ratings, the 20-card minimum.
     A preflight failure ends the run as INVALID before any score exists, and
     such a run is not a look (A5).
  5. score B and C, apply S1.1-S1.6, write the report (A4).

  python research/experiments/PRED-002/stage1.py --indir pred002_dev --outdir pred002_out
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir, os.pardir))
sys.path.insert(0, os.path.join(REPO, "cfl_engine"))
sys.path.insert(0, os.path.join(REPO, "research", "protocol"))

import pred_protocol as pp  # noqa: E402
from engine import (build_features, make_matchup_features,  # noqa: E402
                    predict_symmetric, randomize_corners)
from train import FIXED, ISO_MIN_POOL, tune  # noqa: E402

# ----------------------------------------------------------------- frozen constants
CFG = {
    "eval_years": list(range(2016, 2025)),       # §5
    "blend_first_year": 2013,                    # §5: blends fit on 2013..Y-1
    "engine_first_year": 2010,                   # A5: engine OOS from 2010 (calibration burn-in)
    "eta_grid": [0.05, 0.10, 0.20],              # §3
    "eta_window": ["2005-01-01", "2013-01-01"],  # §3: 2005-01-01 .. 2012-12-31
    "mu_cutoff": "2010-01-01",                   # §3
    "eps_floor": 0.05,                           # §3, A5: in each category's own unit
    "blend_C": 100.0,                            # A5: the engine's own blend regularisation
    "S1_1_min_delta_B": 0.002,
    "S1_3_min_delta_M": 0.006,
    "S1_4_min_positive_years": 6,
    "S1_5_slope": [0.8, 1.25], "S1_5_intercept_abs": 0.1,
    "S1_6_max_delta_M": 0.015, "S1_6_max_accuracy": 0.72,
    "A1_min_coverage_overall": 0.75,             # A1
    "A1_min_coverage_per_year": 0.70,            # A1
    "pit_sample": 200, "pit_seed": 20261012,
    "boot_B": 10000, "boot_seed": 20261012,
    "min_events": 20,
    "symmetry_tol": 1e-6,
    "prospective_target": 0.010,
}
CATS = ["distance", "clinch", "ground", "td", "ctrl"]

FRAMING = [
    "**What this is:** a historical research result on 2016–2024 fights. It "
    "decides only whether PRED-002 earns a prospective test.",
    "**What it is not:** it is not the prospective test. That test is sized "
    "for a gain of 0.010 per fight against the price at the moment of the "
    "forecast, and only it can support a claim.",
    "**And it is not a statement about money.** BestFightOdds consensus is "
    "not a price anyone could bet, and a log-loss gain says nothing by itself "
    "about beating a sportsbook's margin.",
]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def logit(p):
    p = np.clip(np.asarray(p, dtype=float), pp.EPS, 1 - pp.EPS)
    return np.log(p / (1 - p))


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=float)))


# ----------------------------------------------------------------- load
def load(indir):
    fights = pd.read_csv(os.path.join(indir, "fights.csv"))
    stats = pd.read_csv(os.path.join(indir, "fight_stats.csv"))
    fighters = pd.read_csv(os.path.join(indir, "fighters.csv"))
    rounds = pd.read_csv(os.path.join(indir, "rounds.csv"))
    pp.dev_only(fights[["event_date"]].to_dict("records"))  # raises on a sealed date
    fights["event_date"] = pd.to_datetime(fights["event_date"])
    fighters["dob"] = pd.to_datetime(fighters["dob"], errors="coerce")
    for c in ("weight_class", "n_rounds_sched", "method", "odds_a", "odds_b"):
        if c not in fights.columns:
            fights[c] = np.nan
    fights = fights.sort_values(["event_date", "fight_id"]).reset_index(drop=True)
    return fights, stats, fighters, rounds


# ----------------------------------------------------------------- ratings (§3)
def stat_pairs(fights, rounds, eps):
    """One row per (fight, fighter, opponent) with the five log-rates."""
    r = rounds.merge(fights[["fight_id", "event_date"]], on="fight_id", how="inner")
    r = r[r["fight_seconds"] > 0].copy()
    mins = r["fight_seconds"] / 60.0
    rate = {
        "distance": r["distance_landed"] / mins,
        "clinch": r["clinch_landed"] / mins,
        "ground": r["ground_landed"] / mins,
        "td": r["td_landed"] / mins * 15.0,
        "ctrl": r["ctrl_seconds"] / r["fight_seconds"],
    }
    for k in CATS:
        r[f"lr_{k}"] = np.log(np.clip(rate[k].astype(float), 0, None) + eps)
    opp = r[["fight_id", "fighter_id"]].rename(columns={"fighter_id": "opp_id"})
    pairs = r.merge(opp, on="fight_id")
    pairs = pairs[pairs["fighter_id"] != pairs["opp_id"]]
    # both corners must have round data for the fight to update anyone
    return pairs.sort_values(["event_date", "fight_id", "fighter_id"]).reset_index(drop=True)


def run_ratings(pairs, query, mu, eta, until=None, eta_window=None):
    """Online offence/defence ratings, updates batched per event date.

    query: DataFrame with fight_id, event_date, fighter_a_id, fighter_b_id —
    the fights that need features (state strictly before their date).
    Returns (features {fight_id: array(5)}, n_prior {fighter: count by date},
    squared errors inside eta_window)."""
    o = defaultdict(lambda: np.zeros(len(CATS)))
    d = defaultdict(lambda: np.zeros(len(CATS)))
    n_upd = defaultdict(int)
    feats, prior_ok, sq = {}, {}, []
    lr_cols = [f"lr_{k}" for k in CATS]
    p_dates = pairs["event_date"].to_numpy()
    q = query.sort_values("event_date")
    q_dates = q["event_date"].to_numpy()
    dates = np.unique(np.concatenate([p_dates, q_dates]))
    if until is not None:
        dates = dates[dates < np.datetime64(until)]
    p_by = {k: g for k, g in pairs.groupby("event_date")}
    q_by = {k: g for k, g in q.groupby("event_date")}
    w0, w1 = (np.datetime64(eta_window[0]), np.datetime64(eta_window[1])) if eta_window else (None, None)
    for day in dates:
        day = pd.Timestamp(day)
        for r in (q_by.get(day).itertuples(index=False) if day in q_by else ()):
            a, b = r.fighter_a_id, r.fighter_b_id
            feats[r.fight_id] = (o[a] - d[b]) - (o[b] - d[a])
            prior_ok[r.fight_id] = (n_upd[a] > 0, n_upd[b] > 0)
        if day not in p_by:
            continue
        g = p_by[day]
        deltas = []
        for r in g.itertuples(index=False):
            i, j = r.fighter_id, r.opp_id
            obs = np.array([getattr(r, c) for c in lr_cols])
            pred = mu + o[i] - d[j]
            res = obs - pred
            if w0 is not None and w0 <= np.datetime64(day) < w1 and n_upd[i] > 0 and n_upd[j] > 0:
                sq.append(res ** 2)
            deltas.append((i, j, res))
        for i, j, res in deltas:  # applied after the whole night is read
            o[i] = o[i] + eta * res
            d[j] = d[j] - eta * res
        for i in set(g["fighter_id"]):
            n_upd[i] += 1
    return feats, prior_ok, (np.mean(np.concatenate(sq)) if sq else np.nan)


# ----------------------------------------------------------------- engine (§2)
def engine_walk_forward(fights, stats, fighters, first_year, last_year, log):
    """The incumbent engine's code, retrained per year on earlier fights only.
    Predictions are P(DB corner A); training uses the engine's own corner
    randomisation, inference is symmetric, so orientation cannot leak."""
    from xgboost import XGBClassifier
    feat = build_features(fights, stats, fighters)
    rnd = randomize_corners(feat, seed=42)
    rnd = rnd[rnd["result"].isin(["a", "b"])].reset_index(drop=True)
    out = []
    for yr in range(first_year, last_year + 1):
        start = pd.Timestamp(f"{yr}-01-01")
        tr = rnd[rnd["event_date"] < start].reset_index(drop=True)
        te = feat[(feat["event_date"].dt.year == yr) & feat["result"].isin(["a", "b"])].reset_index(drop=True)
        if te.empty:
            continue
        Xtr, diff_cols, _ = make_matchup_features(tr)
        ytr = (tr["result"] == "a").astype(int).to_numpy()
        params = tune(Xtr, ytr, int(len(tr) * 0.55), log=lambda *_: None)
        es = int(len(Xtr) * 0.9)
        m = XGBClassifier(early_stopping_rounds=75, **{**FIXED, **params})
        m.fit(Xtr.iloc[:es], ytr[:es], eval_set=[(Xtr.iloc[es:], ytr[es:])], verbose=False)
        Xte, _, _ = make_matchup_features(te)
        p, _ = predict_symmetric(m, Xte, diff_cols)
        out.append(pd.DataFrame({"fight_id": te["fight_id"], "year": yr,
                                 "p_raw": p.astype("float64"),
                                 "y_db": (te["result"] == "a").astype(int)}))
        log(f"  engine fold {yr}: train {len(tr)}  test {len(te)}  params {params}")
    return pd.concat(out, ignore_index=True)


def calibrate_rolling(oos):
    """Fold Y's calibrator is fit on years before Y only, on BOTH orientations
    of every prior forecast, and applied symmetrically (A5), so the calibrated
    probability stays corner-symmetric. Platt below ISO_MIN_POOL rows."""
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression
    oos = oos.copy()
    oos["p_eng"] = oos["p_raw"]
    for yr in sorted(oos["year"].unique()):
        prior = oos[oos["year"] < yr]
        mask = oos["year"] == yr
        if prior.empty:
            continue
        P = np.concatenate([prior["p_raw"], 1 - prior["p_raw"]])
        Y = np.concatenate([prior["y_db"], 1 - prior["y_db"]])
        if len(prior) >= ISO_MIN_POOL:
            g = IsotonicRegression(y_min=pp.EPS, y_max=1 - pp.EPS, out_of_bounds="clip").fit(P, Y).predict
        else:
            lr = LogisticRegression(C=1e6, max_iter=1000).fit(logit(P).reshape(-1, 1), Y)
            g = lambda x, lr=lr: lr.predict_proba(logit(x).reshape(-1, 1))[:, 1]
        p = oos.loc[mask, "p_raw"].to_numpy()
        oos.loc[mask, "p_eng"] = 0.5 * (g(p) + 1 - g(1 - p))
    oos["p_eng"] = oos["p_eng"].clip(pp.EPS, 1 - pp.EPS)
    return oos


# ----------------------------------------------------------------- blends (§2)
def fit_blend(X, y, C):
    from sklearn.linear_model import LogisticRegression
    Xa = np.vstack([X, -X])
    ya = np.concatenate([y, 1 - y])
    lr = LogisticRegression(C=C, fit_intercept=False, max_iter=5000).fit(Xa, ya)
    return lr.coef_.ravel()


# ----------------------------------------------------------------- devig sensitivities
def devig_power(ia, ib):
    lo, hi = 0.5, 3.0
    for _ in range(100):
        k = 0.5 * (lo + hi)
        s = ia ** k + ib ** k
        lo, hi = (k, hi) if s > 1 else (lo, k)
    k = 0.5 * (lo + hi)
    return ia ** k / (ia ** k + ib ** k)


def devig_shin(ia, ib):
    S = ia + ib
    def probs(z):
        return [(np.sqrt(z * z + 4 * (1 - z) * x * x / S) - z) / (2 * (1 - z)) for x in (ia, ib)]
    lo, hi = 0.0, 0.4
    for _ in range(100):
        z = 0.5 * (lo + hi)
        pa, pb = probs(z)
        lo, hi = (z, hi) if pa + pb > 1 else (lo, z)
    pa, pb = probs(0.5 * (lo + hi))
    return pa / (pa + pb)


def american_decimal(a):
    a = float(a)
    return 1 + a / 100.0 if a > 0 else 1 + 100.0 / -a


# ----------------------------------------------------------------- main run
def run(indir, outdir, cfg=CFG, log=print, preflight_only=False):
    os.makedirs(outdir, exist_ok=True)
    report = {"experiment": "PRED-002", "stage": 1, "cfg": cfg,
              "started_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              "code_sha256": {"stage1.py": sha256_file(os.path.abspath(__file__))}}
    man_path = os.path.join(indir, "manifest.json")
    if os.path.exists(man_path):
        report["export_manifest_sha256"] = sha256_file(man_path)
        with open(man_path) as f:
            report["export_manifest"] = json.load(f)
    fights, stats, fighters, rounds = load(indir)
    report["fights_loaded"] = int(len(fights))
    report["last_event_date"] = str(fights["event_date"].max().date())

    # --- ratings: mu from pre-2010 fights, eta chosen without results (§3)
    pairs = stat_pairs(fights, rounds, cfg["eps_floor"])
    mu = pairs.loc[pairs["event_date"] < pd.Timestamp(cfg["mu_cutoff"]),
                   [f"lr_{k}" for k in CATS]].mean().to_numpy()
    q = fights[["fight_id", "event_date", "fighter_a_id", "fighter_b_id"]]
    mse = {}
    for eta in cfg["eta_grid"]:
        _, _, mse[eta] = run_ratings(pairs, q.iloc[:0], mu, eta, eta_window=cfg["eta_window"])
    eta = min(mse, key=lambda e: (mse[e], e))
    report["ratings"] = {"mu": dict(zip(CATS, map(float, mu))), "eta_mse": {str(k): float(v) for k, v in mse.items()},
                         "eta": eta, "pairs": int(len(pairs))}
    log(f"eta grid MSE {mse} -> eta {eta}")
    feats, prior_ok, _ = run_ratings(pairs, q, mu, eta)

    # --- engine walk-forward (§2) and calibration (A5)
    oos = engine_walk_forward(fights, stats, fighters, cfg["engine_first_year"],
                              max(cfg["eval_years"]), log)
    oos = calibrate_rolling(oos)
    eng = oos.set_index("fight_id")["p_eng"].to_dict()

    # --- eligible population and exclusions (§7, A2)
    df = fights[fights["result"].isin(["a", "b"]) & fights["priced"].astype(bool)].copy()
    df["year"] = df["event_date"].dt.year
    df = df[df["year"] >= cfg["blend_first_year"]]
    po = df["fight_id"].map(prior_ok)
    df["a_prior"] = po.map(lambda t: bool(t and t[0]))
    df["b_prior"] = po.map(lambda t: bool(t and t[1]))
    df["has_engine"] = df["fight_id"].isin(eng)
    df["eligible"] = df["a_prior"] & df["b_prior"] & df["has_engine"]
    excl = []
    for yr, g in df[df["year"].isin(cfg["eval_years"])].groupby("year"):
        excl.append({"year": int(yr), "priced_decided": int(len(g)),
                     "excluded_a_no_prior_splits": int((~g["a_prior"]).sum()),
                     "excluded_b_no_prior_splits": int((~g["b_prior"]).sum()),
                     "excluded_both_no_prior_splits": int((~g["a_prior"] & ~g["b_prior"]).sum()),
                     "excluded_no_engine_forecast": int((~g["has_engine"]).sum()),
                     "scored": int(g["eligible"].sum()),
                     "coverage": round(float(g["eligible"].mean()), 4)})
    ev_all = df[df["year"].isin(cfg["eval_years"])]
    report["exclusions_by_year"] = excl
    report["coverage_overall"] = round(float(ev_all["eligible"].mean()), 4)

    # --- feature matrices
    df = df[df["eligible"]].copy()
    ia, ib = df["imp_a"].to_numpy(float), df["imp_b"].to_numpy(float)
    df["q"] = ia / (ia + ib)
    df["p_eng"] = df["fight_id"].map(eng)
    R = np.vstack([feats[f] for f in df["fight_id"]])
    for k, c in enumerate(CATS):
        df[f"r_{c}"] = R[:, k]
    df["y"] = (df["result"] == "a").astype(int)
    XB_all = np.column_stack([logit(df["q"]), logit(df["p_eng"])])
    XC_all = np.column_stack([XB_all, R])

    # =============== PREFLIGHT: nothing below this block reads a result until it passes
    pre = []
    if report["coverage_overall"] < cfg["A1_min_coverage_overall"]:
        pre.append(f"A1: overall coverage {report['coverage_overall']:.1%} below "
                   f"{cfg['A1_min_coverage_overall']:.0%}")
    for row in excl:
        if row["coverage"] < cfg["A1_min_coverage_per_year"]:
            pre.append(f"A1: {row['year']} coverage {row['coverage']:.1%} below "
                       f"{cfg['A1_min_coverage_per_year']:.0%}")
    test_mask = df["year"].isin(cfg["eval_years"]).to_numpy()
    n_events = df.loc[test_mask, "event_id"].nunique()
    if n_events < cfg["min_events"]:
        pre.append(f"only {n_events} cards scored")
    # point-in-time recheck: rebuild ratings on data cut before each sampled date
    rng = np.random.default_rng(cfg["pit_seed"])
    sample = df[test_mask].iloc[rng.choice(int(test_mask.sum()), size=min(cfg["pit_sample"], int(test_mask.sum())), replace=False)]
    pit_bad = 0
    for day, g in sample.groupby("event_date"):
        cut = pairs[pairs["event_date"] < day]
        f2, _, _ = run_ratings(cut, g[["fight_id", "event_date", "fighter_a_id", "fighter_b_id"]], mu, eta)
        for fid in g["fight_id"]:
            if not np.allclose(f2[fid], feats[fid], atol=1e-12, rtol=0):
                pit_bad += 1
    report["pit_recheck"] = {"fights": int(len(sample)), "mismatches": pit_bad}
    if pit_bad:
        pre.append(f"point-in-time recheck: {pit_bad} of {len(sample)} rating rows differ when rebuilt from earlier data only")
    # antisymmetry of every model input
    for name, X in (("B", XB_all), ("C", XC_all)):
        flipped = np.column_stack([logit(1 - df["q"]), logit(1 - df["p_eng"])])
        if name == "C":
            flipped = np.column_stack([flipped, -R])
        if not np.allclose(flipped, -X, atol=1e-9):
            pre.append(f"inputs to {name} are not antisymmetric under a corner swap")
    report["preflight_failures"] = pre
    if pre:
        report["verdict"] = "INVALID"
        report["verdict_reasons"] = pre
        report["note"] = "Ended before any forecast was scored against a result. Under A5 this run is not a look."
        _write(report, outdir)
        return report
    if preflight_only:
        # A5: stopping here is not a look. Nothing has been scored.
        report["verdict"] = "PREFLIGHT_OK"
        report["verdict_reasons"] = ["preflight passed; stopped before any forecast was scored"]
        _write(report, outdir)
        return report

    # =============== SCORING (the one look)
    yv = df["y"].to_numpy()
    pB = np.full(len(df), np.nan)
    pC = np.full(len(df), np.nan)
    pC_flip = np.full(len(df), np.nan)
    coefs = {}
    for yr in cfg["eval_years"]:
        trm = ((df["year"] >= cfg["blend_first_year"]) & (df["year"] < yr)).to_numpy()
        tem = (df["year"] == yr).to_numpy()
        if not tem.any():
            continue
        bB = fit_blend(XB_all[trm], yv[trm], cfg["blend_C"])
        bC = fit_blend(XC_all[trm], yv[trm], cfg["blend_C"])
        pB[tem] = sigmoid(XB_all[tem] @ bB)
        pC[tem] = sigmoid(XC_all[tem] @ bC)
        pC_flip[tem] = sigmoid(-XC_all[tem] @ bC)
        coefs[yr] = {"B": bB.tolist(), "C": bC.tolist()}
    t = test_mask
    y, pm, pb, pc = yv[t], df["q"].to_numpy()[t], pB[t], pC[t]
    clusters = df["event_id"].to_numpy()[t]
    years = df["year"].to_numpy()[t]
    llM, llB, llC = pp.log_loss_each(y, pm), pp.log_loss_each(y, pb), pp.log_loss_each(y, pc)
    dB, dM, dBM = llB - llC, llM - llC, llM - llB

    def ci(v):
        b = pp.cluster_bootstrap(v, clusters, cfg["boot_B"], cfg["boot_seed"])
        return [float(x) for x in np.quantile(b, [0.025, 0.975])]

    a_cal, b_cal = pp.calibration_fit(y, pc)
    acc = {n: float(((p >= 0.5) == (y == 1)).mean()) for n, p in (("M", pm), ("B", pb), ("C", pc))}
    per_year = {int(yr): {"n": int((years == yr).sum()),
                          "delta_B": float(dB[years == yr].mean()),
                          "delta_M": float(dM[years == yr].mean())} for yr in sorted(set(years))}
    sym = float(np.max(np.abs(pc + pC_flip[t] - 1)))
    res = {
        "n_scored": int(t.sum()), "cards": int(len(set(clusters))),
        "log_loss": {"market": float(llM.mean()), "B": float(llB.mean()), "C": float(llC.mean())},
        "delta_B": float(dB.mean()), "delta_B_ci95": ci(dB),
        "delta_M": float(dM.mean()), "delta_M_ci95": ci(dM),
        "B_minus_market": float(dBM.mean()), "B_minus_market_ci95": ci(dBM),
        "sd_delta_M": float(dM.std(ddof=1)), "sd_delta_B": float(dB.std(ddof=1)),
        "per_year": per_year,
        "accuracy": acc,
        "brier": {n: float(pp.brier_each(y, p).mean()) for n, p in (("M", pm), ("B", pb), ("C", pc))},
        "calibration_C": {"intercept": a_cal, "slope": b_cal},
        "symmetry_max_violation_C": sym,
        "blend_coefficients": coefs,
    }
    # reliability table, C
    bins = np.clip((pc * 10).astype(int), 0, 9)
    res["reliability_C"] = [{"bin": f"{k/10:.1f}-{(k+1)/10:.1f}", "n": int((bins == k).sum()),
                             "mean_p": float(pc[bins == k].mean()) if (bins == k).any() else None,
                             "win_rate": float(y[bins == k].mean()) if (bins == k).any() else None}
                            for k in range(10)]
    # de-vig sensitivities (reported, never chosen)
    iat, ibt = ia[t], ib[t]
    for name, fn in (("power", devig_power), ("shin", devig_shin)):
        qa = np.array([fn(x, z) for x, z in zip(iat, ibt)])
        res[f"delta_M_devig_{name}"] = float((pp.log_loss_each(y, qa) - llC).mean())
    # simulated flat betting under PRED-001 §5's one rule, at the BFO consensus price
    oa, ob = df["odds_a"].to_numpy()[t], df["odds_b"].to_numpy()[t]
    stake, profit = np.zeros(len(y)), np.zeros(len(y))
    for i in range(len(y)):
        if np.isnan(oa[i]) or np.isnan(ob[i]):
            continue
        ea = pc[i] * american_decimal(oa[i]) - 1
        eb = (1 - pc[i]) * american_decimal(ob[i]) - 1
        if max(ea, eb) > 0:
            stake[i] = 1
            if ea >= eb:
                profit[i] = american_decimal(oa[i]) - 1 if y[i] == 1 else -1
            else:
                profit[i] = american_decimal(ob[i]) - 1 if y[i] == 0 else -1
    keys = {}
    idx = np.array([keys.setdefault(c, len(keys)) for c in clusters])
    ps = np.bincount(idx, weights=profit, minlength=len(keys))
    ss = np.bincount(idx, weights=stake, minlength=len(keys))
    draws = np.random.default_rng(cfg["boot_seed"]).integers(0, len(keys), size=(cfg["boot_B"], len(keys)))
    with np.errstate(invalid="ignore", divide="ignore"):
        roi_b = ps[draws].sum(1) / ss[draws].sum(1)
    res["simulated_flat_betting"] = {
        "bets": int(stake.sum()), "roi": float(profit.sum() / stake.sum()) if stake.sum() else None,
        "roi_ci95": [float(x) for x in np.nanquantile(roi_b, [0.025, 0.975])] if stake.sum() else None,
        "caveat": "BestFightOdds consensus is not a price anyone could bet.",
    }
    report["results"] = res

    # =============== verdict (§6), in the preregistered order
    reasons = []
    if res["delta_M"] > cfg["S1_6_max_delta_M"] or acc["C"] > cfg["S1_6_max_accuracy"]:
        reasons.append(f"S1.6: delta_M {res['delta_M']:.4f} or accuracy {acc['C']:.1%} trips the leak tripwire")
        verdict = "SUSPECT"
    else:
        checks = [
            ("S1.1", res["delta_B"] >= cfg["S1_1_min_delta_B"],
             f"gain over price plus engine {res['delta_B']:+.4f} (needs >= {cfg['S1_1_min_delta_B']})"),
            ("S1.2", res["delta_B_ci95"][0] > 0,
             f"its 95% range {res['delta_B_ci95'][0]:+.4f} to {res['delta_B_ci95'][1]:+.4f} (needs to sit above 0)"),
            ("S1.3", res["delta_M"] >= cfg["S1_3_min_delta_M"] and res["delta_M_ci95"][0] > 0,
             f"gain over price alone {res['delta_M']:+.4f}, range {res['delta_M_ci95'][0]:+.4f} to "
             f"{res['delta_M_ci95'][1]:+.4f} (needs >= {cfg['S1_3_min_delta_M']} and above 0)"),
            ("S1.4", sum(v["delta_B"] > 0 for v in per_year.values()) >= cfg["S1_4_min_positive_years"],
             f"positive over price plus engine in {sum(v['delta_B'] > 0 for v in per_year.values())} of "
             f"{len(per_year)} years (needs {cfg['S1_4_min_positive_years']})"),
            ("S1.5", cfg["S1_5_slope"][0] <= b_cal <= cfg["S1_5_slope"][1] and abs(a_cal) <= cfg["S1_5_intercept_abs"],
             f"calibration slope {b_cal:.3f}, intercept {a_cal:+.3f}"),
        ]
        report["conditions"] = [{"id": c, "passed": bool(ok), "detail": msg} for c, ok, msg in checks]
        failed = [f"{c}: {msg}" for c, ok, msg in checks if not ok]
        verdict = "PASS_STAGE1" if not failed else "STOP_STAGE1"
        reasons = failed or ["every Stage 1 condition held"]
    if sym > cfg["symmetry_tol"]:
        verdict, reasons = "INVALID", [f"C is not corner-symmetric (max violation {sym:.2e})"] + reasons
    report["verdict"] = verdict
    report["verdict_reasons"] = reasons
    _write(report, outdir)
    return report


def _write(report, outdir):
    report["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with open(os.path.join(outdir, "stage1_result.json"), "w") as f:
        json.dump(report, f, indent=1, default=str)
    with open(os.path.join(outdir, "STAGE1_REPORT.md"), "w") as f:
        f.write(render(report))


def _pct(x):
    return "n/a" if x is None else f"{x:+.1%}"


def render(r):
    """The Stage 1 report. A4: the three framing lines open every report,
    whatever the verdict, before any number."""
    L = ["# PRED-002 Stage 1 — result", ""] + [f"> {x}" for x in FRAMING] + [""]
    L += [f"**Verdict: {r['verdict']}**", ""] + [f"- {x}" for x in r.get("verdict_reasons", [])] + [""]
    if "results" in r:
        s = r["results"]
        L += ["## The numbers", "",
              "| | per fight | 95% range (cards resampled) |", "|---|---|---|",
              f"| gain over price plus engine (Δ_B) | {s['delta_B']:+.4f} | {s['delta_B_ci95'][0]:+.4f} to {s['delta_B_ci95'][1]:+.4f} |",
              f"| gain over price alone (Δ_M) | {s['delta_M']:+.4f} | {s['delta_M_ci95'][0]:+.4f} to {s['delta_M_ci95'][1]:+.4f} |",
              f"| price plus engine over price alone | {s['B_minus_market']:+.4f} | {s['B_minus_market_ci95'][0]:+.4f} to {s['B_minus_market_ci95'][1]:+.4f} |",
              f"| **for comparison: the prospective target** | **+0.0100** | — |", "",
              f"{s['n_scored']} fights on {s['cards']} cards. Log loss: market {s['log_loss']['market']:.4f}, "
              f"B {s['log_loss']['B']:.4f}, C {s['log_loss']['C']:.4f}.", ""]
        if "conditions" in r:
            L += ["## Conditions", "", "| | held? | detail |", "|---|---|---|"]
            L += [f"| {c['id']} | {'yes' if c['passed'] else '**no**'} | {c['detail']} |" for c in r["conditions"]]
            L += [""]
        L += ["## By year", "", "| year | fights | Δ_B | Δ_M |", "|---|---|---|---|"]
        L += [f"| {yr} | {v['n']} | {v['delta_B']:+.4f} | {v['delta_M']:+.4f} |" for yr, v in s["per_year"].items()]
        sb = s["simulated_flat_betting"]
        L += ["", "## Reported, never decisive", "",
              f"- Accuracy: market {s['accuracy']['M']:.1%}, B {s['accuracy']['B']:.1%}, C {s['accuracy']['C']:.1%}.",
              f"- Calibration of C: slope {s['calibration_C']['slope']:.3f}, intercept {s['calibration_C']['intercept']:+.3f}.",
              f"- Δ_M under other de-vig methods: power {s['delta_M_devig_power']:+.4f}, Shin {s['delta_M_devig_shin']:+.4f}.",
              f"- Simulated flat betting: {sb['bets']} bets, ROI {_pct(sb['roi'])} "
              f"(range {_pct(sb['roi_ci95'][0]) if sb['roi_ci95'] else 'n/a'} to "
              f"{_pct(sb['roi_ci95'][1]) if sb['roi_ci95'] else 'n/a'}). {sb['caveat']}", ""]
    L += ["## Population (A2)", "", "| year | priced, decided | excluded: no prior split fight (A / B / both) | scored | coverage |",
          "|---|---|---|---|---|"]
    L += [f"| {e['year']} | {e['priced_decided']} | {e['excluded_a_no_prior_splits']} / {e['excluded_b_no_prior_splits']} / "
          f"{e['excluded_both_no_prior_splits']} | {e['scored']} | {e['coverage']:.1%} |" for e in r.get("exclusions_by_year", [])]
    L += ["", "Findings apply to priced, decided UFC fights from 2016 to 2024 in which **both** fighters had "
          "at least one earlier UFC fight with round-by-round splits. They say nothing about debuts.", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--preflight-only", action="store_true",
                    help="stop before scoring (A5: not a look); used to verify the pipeline on real data before the freeze")
    a = ap.parse_args()
    r = run(a.indir, a.outdir, preflight_only=a.preflight_only)
    print(json.dumps({k: r[k] for k in ("verdict", "verdict_reasons")}, indent=1))
    print(open(os.path.join(a.outdir, "STAGE1_REPORT.md")).read())


if __name__ == "__main__":
    main()
