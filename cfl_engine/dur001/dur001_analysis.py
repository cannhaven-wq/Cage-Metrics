"""DUR-001 — does PROP-0001 add information after the vig-free closing UFC
totals market is known?

Inputs (all read-only, service key):
  v_prop_odds_closing_consensus   median vig-free closing P(over) per (fight, line)
  v_prop_odds_opening_consensus   same at the opener (Phase 8)
  prop_model_locks                PROP-0001 P(over) locked pre-fight (Phase 4)
  v_prop_fight_duration           elapsed seconds + void flag (outcome)
  fights / events                 scheduled rounds, event clustering

One analysis row = one (fight, sportsbook total threshold) with a closing
consensus AND a PROP-0001 lock at that exact threshold.

Settlement (Over X.5 rounds): wins iff elapsed time > X*300 + 150 seconds, i.e.
the fight goes PAST 2:30 of round X+1. Ending exactly at 2:30 settles Under
(standard book rule: "past the halfway point"). Whole-number lines push when the
fight ends exactly on the round bell and are excluded. No-contests / overturned
results are void and excluded. Only scheduled 3-round fights qualify (PROP-0001
scope). All of this is fixed BEFORE any result is looked at.

Phases:
  5  raw log loss / Brier / calibration, market vs CFL, G_LL = LL_market - LL_CFL
  6  walk-forward residual test — per event, on PRIOR events only, fit
       baseline   logit(P) = a + b*logit(P_close)
       challenger logit(P) = a + b*logit(P_close) + g*[logit(P_CFL) - logit(P_close)]
     and score the held-out event. Primary metric G_LL = LL_base - LL_chal.
  7  event-cluster bootstrap (10,000 draws of whole events) of every metric.
  8  opener test — walk-forward, predict logit(P_close) from logit(P_open)
     with and without logit(P_CFL); compare OOS squared error.
  9  pre-registered decision (DECISION_RULES below), frozen 2026-09-14.

Usage:
  python cfl_engine/dur001/dur001_analysis.py                  # live data
  python cfl_engine/dur001/dur001_analysis.py --draws 10000 --out out_real/dur001
  python cfl_engine/dur001/dur001_analysis.py --synthetic 40   # pipeline check on
                                                               # SYNTHETIC events (never stored)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ENGINE, "features"))

MODEL_VERSION = "PROP-0001@v1"
MIDPOINT = 150
ROUND_SECONDS = 300
EPS = 1e-6
RIDGE = 1e-3                 # tiny L2 on the walk-forward logistic fits (separation guard)
MIN_PRIOR_EVENTS = 8         # first scored event needs at least this many prior events
MIN_PRIOR_ROWS = 40

# --------------------------------------------------------------- frozen rules
# PROMOTE the duration branch only if ALL hold on the residual (Phase 6) test.
DECISION_RULES = {
    "residual_G_LL_positive": "G_LL = LL_market_baseline - LL_market_plus_CFL > 0 (OOS)",
    "bootstrap_ci_excludes_zero": "event-cluster 95% CI lower bound of G_LL > 0",
    "practical_gain": "G_LL >= 0.003 log-loss per fight-threshold",
    "brier_not_worse": "challenger Brier - baseline Brier <= 0.001",
    "calibration_acceptable": "challenger OOS calibration slope in [0.8, 1.2] and |intercept| <= 0.10",
    "reject_if_ceiling_low": "if the 95% CI upper bound < 0.003, REJECT (an economically meaningful effect is unlikely) — do not keep adding features",
}
PRACTICAL_GAIN = 0.003
BRIER_TOL = 0.001
SLOPE_BAND = (0.8, 1.2)
INTERCEPT_TOL = 0.10


# ------------------------------------------------------------------- helpers
def american_to_q(a):
    a = float(a)
    return (-a) / ((-a) + 100.0) if a < 0 else 100.0 / (a + 100.0)


def devig_two_way(over_odds, under_odds):
    qo, qu = american_to_q(over_odds), american_to_q(under_odds)
    return qo / (qo + qu), qu / (qo + qu)


def settle_over(duration_seconds, line, scheduled_rounds=3):
    """Return 1 / 0 for an Over bet at `line` rounds, None for push/void."""
    if duration_seconds is None or (isinstance(duration_seconds, float) and np.isnan(duration_seconds)):
        return None
    line = float(line)
    whole = int(np.floor(line))
    if abs(line - whole - 0.5) < 1e-9:                 # X.5 -> 2:30 of round X+1
        cut = whole * ROUND_SECONDS + MIDPOINT
        return int(duration_seconds > cut)
    if abs(line - round(line)) < 1e-9:                 # whole number -> round bell
        cut = int(round(line)) * ROUND_SECONDS
        if abs(duration_seconds - cut) < 1e-9:
            return None                                # push
        return int(duration_seconds > cut)
    return None


def logit(p):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def log_loss(p, y):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS); y = np.asarray(y, float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def brier(p, y):
    return (np.asarray(p, float) - np.asarray(y, float)) ** 2


def fit_logistic(X, y, ridge=RIDGE, iters=50):
    """Newton logistic regression with intercept and a tiny ridge (not on the
    intercept). X: (n,k). Returns coef vector [a, b1..bk]."""
    X = np.asarray(X, float); y = np.asarray(y, float)
    n, k = X.shape
    A = np.hstack([np.ones((n, 1)), X])
    w = np.zeros(k + 1)
    R = np.eye(k + 1) * ridge; R[0, 0] = 0.0
    for _ in range(iters):
        p = sigmoid(A @ w)
        g = A.T @ (p - y) + R @ w
        H = (A * (p * (1 - p))[:, None]).T @ A + R
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            step = np.linalg.lstsq(H, g, rcond=None)[0]
        w -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    return w


def fit_ols(X, y, ridge=RIDGE):
    X = np.asarray(X, float); y = np.asarray(y, float)
    A = np.hstack([np.ones((len(X), 1)), X])
    R = np.eye(A.shape[1]) * ridge; R[0, 0] = 0.0
    return np.linalg.solve(A.T @ A + R, A.T @ y)


def calibration(p, y):
    """Logistic recalibration of y on logit(p): intercept, slope."""
    if len(p) < 10 or len(set(np.asarray(y).tolist())) < 2:
        return {"intercept": None, "slope": None}
    w = fit_logistic(logit(p)[:, None], y)
    return {"intercept": float(w[0]), "slope": float(w[1])}


# ------------------------------------------------------------------ the data
def load_live(base_url, key, log=print):
    import build_features as bf
    close = bf.fetch_all(base_url, key, "v_prop_odds_closing_consensus",
                         "select=fight_id,event_id,event_date,line,bookmaker_count,median_over_prob_vigfree,"
                         "start_basis,latest_book_close_at,book_ids&market_type=eq.total_rounds")
    opener = bf.fetch_all(base_url, key, "v_prop_odds_opening_consensus",
                          "select=fight_id,line,bookmaker_count,median_over_prob_vigfree&market_type=eq.total_rounds")
    locks = bf.fetch_all(base_url, key, "prop_model_locks",
                         "select=fight_id,threshold,predicted_probability,actual_lock_at"
                         f"&model_version=eq.{MODEL_VERSION}&market_type=eq.total_rounds&side=eq.over")
    dur = bf.fetch_all(base_url, key, "v_prop_fight_duration",
                       "select=fight_id,event_id,event_date,scheduled_rounds,duration_seconds,is_void,method")
    log(f"  closes={len(close)} openers={len(opener)} locks={len(locks)} graded_fights="
        f"{sum(1 for d in dur if d['duration_seconds'] is not None)}")
    c = pd.DataFrame(close); o = pd.DataFrame(opener); l = pd.DataFrame(locks); d = pd.DataFrame(dur)
    if c.empty or l.empty:
        return pd.DataFrame()
    c["line"] = c["line"].astype(float); l["threshold"] = l["threshold"].astype(float)
    df = c.merge(l.rename(columns={"threshold": "line", "predicted_probability": "p_cfl"}),
                 on=["fight_id", "line"], how="inner")
    if not o.empty:
        o["line"] = o["line"].astype(float)
        df = df.merge(o.rename(columns={"median_over_prob_vigfree": "p_open",
                                        "bookmaker_count": "open_books"})[["fight_id", "line", "p_open", "open_books"]],
                      on=["fight_id", "line"], how="left")
    else:
        df["p_open"] = np.nan; df["open_books"] = np.nan
    df = df.merge(d[["fight_id", "scheduled_rounds", "duration_seconds", "is_void"]], on="fight_id", how="left")
    df = df.rename(columns={"median_over_prob_vigfree": "p_market", "bookmaker_count": "close_books"})
    # the lock must predate the close (belt and braces; the DB guard already enforces pre-start)
    df["actual_lock_at"] = pd.to_datetime(df["actual_lock_at"], utc=True)
    df["latest_book_close_at"] = pd.to_datetime(df["latest_book_close_at"], utc=True)
    df = df[df["actual_lock_at"] <= df["latest_book_close_at"]]
    return df


def make_synthetic(n_events=40, seed=7, cfl_signal=0.0, cfl_noise=0.5):
    """SYNTHETIC events for a pipeline check. Never stored.

    cfl_signal = 0 is a true null: CFL is the market plus independent noise, so
    it carries NOTHING the close does not already know. cfl_signal = 1 makes CFL
    an independent noisy read of the truth, which the residual test should find."""
    rng = np.random.default_rng(seed)
    rows = []
    for e in range(n_events):
        date = dt.date(2026, 10, 3) + dt.timedelta(days=7 * e)
        for f in range(rng.integers(8, 13)):
            truth = rng.normal(0.15, 0.9)                      # latent logit P(over 2.5)
            mkt = truth + rng.normal(0, 0.35)                  # market sees truth + noise
            cfl = mkt + cfl_signal * (truth - mkt) + rng.normal(0, cfl_noise)
            y = int(rng.random() < sigmoid(truth))
            rows.append({"fight_id": e * 100 + f, "event_id": e, "event_date": date.isoformat(),
                         "line": 2.5, "p_market": sigmoid(mkt), "p_cfl": sigmoid(cfl),
                         "p_open": sigmoid(mkt + rng.normal(0, 0.25)), "close_books": 5, "open_books": 4,
                         "start_basis": "synthetic", "scheduled_rounds": 3, "is_void": False,
                         "duration_seconds": 800 if y else 700})
    return pd.DataFrame(rows)


def prepare(df: pd.DataFrame):
    df = df.copy()
    df = df[df["scheduled_rounds"].fillna(3).astype(int) == 3]
    df = df[~df["is_void"].fillna(False).astype(bool)]
    df["y"] = [settle_over(d, l) for d, l in zip(df["duration_seconds"], df["line"])]
    df = df[df["y"].notna()].copy()
    df["y"] = df["y"].astype(int)
    df["event_date"] = pd.to_datetime(df["event_date"]).dt.date
    df = df.sort_values(["event_date", "event_id", "fight_id", "line"]).reset_index(drop=True)
    df["x_mkt"] = logit(df["p_market"]); df["x_cfl"] = logit(df["p_cfl"])
    df["x_res"] = df["x_cfl"] - df["x_mkt"]
    return df


# --------------------------------------------------------------- the phases
def phase5_raw(df):
    out = {"n_rows": int(len(df)), "n_fights": int(df.fight_id.nunique()),
           "n_events": int(df.event_id.nunique()),
           "n_books_median_close": float(df.close_books.median()) if len(df) else None,
           "coverage_by_threshold": {str(k): int(v) for k, v in df.line.value_counts().sort_index().items()},
           "close_basis": {str(k): int(v) for k, v in df.start_basis.value_counts().items()}}
    if len(df):
        out.update({
            "LL_market": float(log_loss(df.p_market, df.y).mean()),
            "LL_cfl": float(log_loss(df.p_cfl, df.y).mean()),
            "Brier_market": float(brier(df.p_market, df.y).mean()),
            "Brier_cfl": float(brier(df.p_cfl, df.y).mean()),
            "cal_market": calibration(df.p_market, df.y),
            "cal_cfl": calibration(df.p_cfl, df.y),
        })
        out["G_LL_raw"] = out["LL_market"] - out["LL_cfl"]
        out["over_rate"] = float(df.y.mean())
    return out


def walk_forward(df, min_prior_events=MIN_PRIOR_EVENTS, min_prior_rows=MIN_PRIOR_ROWS):
    """Per-row OOS predictions from baseline and challenger fit on prior events."""
    events = list(dict.fromkeys(zip(df.event_date, df.event_id)))   # chronological
    p_base = np.full(len(df), np.nan); p_chal = np.full(len(df), np.nan)
    coefs = []
    for i, (d, e) in enumerate(events):
        if i < min_prior_events:
            continue
        prior = df[[(dd < d) for dd in df.event_date]]
        if len(prior) < min_prior_rows:
            continue
        wb = fit_logistic(prior[["x_mkt"]].to_numpy(), prior.y.to_numpy())
        wc = fit_logistic(prior[["x_mkt", "x_res"]].to_numpy(), prior.y.to_numpy())
        m = (df.event_id == e) & (df.event_date == d)
        Xb = df.loc[m, ["x_mkt"]].to_numpy(); Xc = df.loc[m, ["x_mkt", "x_res"]].to_numpy()
        p_base[m.to_numpy()] = sigmoid(wb[0] + Xb @ wb[1:])
        p_chal[m.to_numpy()] = sigmoid(wc[0] + Xc @ wc[1:])
        coefs.append({"event_date": str(d), "event_id": int(e), "n_prior": int(len(prior)),
                      "base": [float(x) for x in wb], "chal": [float(x) for x in wc]})
    return p_base, p_chal, coefs


def phase6_residual(df):
    p_base, p_chal, coefs = walk_forward(df)
    m = ~np.isnan(p_base)
    sc = df[m].copy(); sc["p_base"] = p_base[m]; sc["p_chal"] = p_chal[m]
    out = {"n_scored_rows": int(len(sc)), "n_scored_events": int(sc.event_id.nunique()) if len(sc) else 0,
           "n_fit_events": len(coefs), "last_coefs": coefs[-1] if coefs else None}
    if len(sc):
        out.update({
            "LL_market_baseline": float(log_loss(sc.p_base, sc.y).mean()),
            "LL_market_plus_cfl": float(log_loss(sc.p_chal, sc.y).mean()),
            "Brier_baseline": float(brier(sc.p_base, sc.y).mean()),
            "Brier_challenger": float(brier(sc.p_chal, sc.y).mean()),
            "cal_challenger": calibration(sc.p_chal, sc.y),
            "cal_baseline": calibration(sc.p_base, sc.y),
            "gamma_trajectory": [c["chal"][2] for c in coefs],
        })
        out["G_LL"] = out["LL_market_baseline"] - out["LL_market_plus_cfl"]
        out["delta_Brier"] = out["Brier_challenger"] - out["Brier_baseline"]
    return out, sc


def phase7_bootstrap(sc, draws=10000, seed=20260914, log=print):
    """Resample whole events with replacement; recompute every metric on the
    fixed walk-forward OOS predictions (no refitting inside the bootstrap)."""
    if len(sc) == 0:
        return {"draws": 0}
    rng = np.random.default_rng(seed)
    ev_ids = sc.event_id.unique()
    groups = {e: sc[sc.event_id == e] for e in ev_ids}
    G, dB, slope, rawG = [], [], [], []
    for _ in range(draws):
        pick = rng.choice(ev_ids, size=len(ev_ids), replace=True)
        s = pd.concat([groups[e] for e in pick], ignore_index=True)
        G.append(float((log_loss(s.p_base, s.y) - log_loss(s.p_chal, s.y)).mean()))
        dB.append(float((brier(s.p_chal, s.y) - brier(s.p_base, s.y)).mean()))
        rawG.append(float((log_loss(s.p_market, s.y) - log_loss(s.p_cfl, s.y)).mean()))
        if len(s) >= 40 and s.y.nunique() == 2:
            slope.append(calibration(s.p_chal, s.y)["slope"])
    def ci(a):
        a = np.asarray([x for x in a if x is not None], float)
        return {"mean": float(a.mean()), "lo95": float(np.percentile(a, 2.5)),
                "hi95": float(np.percentile(a, 97.5))} if len(a) else None
    return {"draws": draws, "n_events": int(len(ev_ids)),
            "G_LL": ci(G), "delta_Brier": ci(dB), "cal_slope_challenger": ci(slope), "G_LL_raw": ci(rawG),
            "mean_CLV": None, "ROI": None,
            "note": "mean CLV / ROI are null: DUR-001 places no bets and optimises no thresholds."}


def phase8_opener(df):
    d = df[df.p_open.notna()].copy()
    if len(d) < MIN_PRIOR_ROWS:
        return {"n_rows": int(len(d)), "note": "insufficient rows with an opening consensus"}
    d["x_open"] = logit(d.p_open)
    events = list(dict.fromkeys(zip(d.event_date, d.event_id)))
    e_base, e_chal = [], []
    for i, (dd, e) in enumerate(events):
        if i < MIN_PRIOR_EVENTS:
            continue
        prior = d[[(x < dd) for x in d.event_date]]
        if len(prior) < MIN_PRIOR_ROWS:
            continue
        wb = fit_ols(prior[["x_open"]].to_numpy(), prior.x_mkt.to_numpy())
        wc = fit_ols(prior[["x_open", "x_cfl"]].to_numpy(), prior.x_mkt.to_numpy())
        m = (d.event_id == e) & (d.event_date == dd)
        yb = wb[0] + d.loc[m, ["x_open"]].to_numpy() @ wb[1:]
        yc = wc[0] + d.loc[m, ["x_open", "x_cfl"]].to_numpy() @ wc[1:]
        e_base.extend(((d.loc[m, "x_mkt"].to_numpy() - yb) ** 2).tolist())
        e_chal.extend(((d.loc[m, "x_mkt"].to_numpy() - yc) ** 2).tolist())
    if not e_base:
        return {"n_rows": int(len(d)), "note": "not enough events for a walk-forward opener test"}
    return {"n_rows": int(len(d)), "n_scored": len(e_base),
            "MSE_open_only": float(np.mean(e_base)), "MSE_open_plus_cfl": float(np.mean(e_chal)),
            "MSE_gain": float(np.mean(e_base) - np.mean(e_chal))}


def phase9_decision(p6, p7):
    checks = {}
    if "G_LL" not in p6 or not p7.get("G_LL"):
        return {"verdict": "INSUFFICIENT DATA", "checks": checks,
                "reason": "no fully out-of-sample scored events yet"}
    g = p6["G_LL"]; lo = p7["G_LL"]["lo95"]; hi = p7["G_LL"]["hi95"]
    cal = p6["cal_challenger"]
    checks["residual_G_LL_positive"] = bool(g > 0)
    checks["bootstrap_ci_excludes_zero"] = bool(lo > 0)
    checks["practical_gain"] = bool(g >= PRACTICAL_GAIN)
    checks["brier_not_worse"] = bool(p6["delta_Brier"] <= BRIER_TOL)
    checks["calibration_acceptable"] = bool(cal["slope"] is not None and SLOPE_BAND[0] <= cal["slope"] <= SLOPE_BAND[1]
                                            and abs(cal["intercept"]) <= INTERCEPT_TOL)
    ceiling_low = bool(hi < PRACTICAL_GAIN)
    if all(checks.values()):
        verdict = "PROMOTE"
    elif ceiling_low:
        verdict = "REJECT"
    else:
        verdict = "HOLD"
    return {"verdict": verdict, "checks": checks, "ceiling_below_practical_gain": ceiling_low,
            "G_LL": g, "ci95": [lo, hi], "rules": DECISION_RULES}


# ------------------------------------------------------------------------ main
def run(df, draws, out_dir, label, log=print):
    df = prepare(df)
    log(f"[dur001] {label}: {len(df)} fight-threshold rows, {df.fight_id.nunique() if len(df) else 0} fights, "
        f"{df.event_id.nunique() if len(df) else 0} events after settlement filters")
    p5 = phase5_raw(df)
    p6, sc = phase6_residual(df)
    p7 = phase7_bootstrap(sc, draws=draws)
    p8 = phase8_opener(df)
    p9 = phase9_decision(p6, p7)
    report = {"experiment": "DUR-001", "model_version": MODEL_VERSION, "data": label,
              "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "phase5_raw": p5, "phase6_residual": p6, "phase7_bootstrap": p7,
              "phase8_opener": p8, "phase9_decision": p9}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "dur001_report.json"), "w") as fh:
        json.dump(report, fh, indent=2, default=str)
    if len(df):
        df.to_csv(os.path.join(out_dir, "dur001_rows.csv"), index=False)
    print_summary(report)
    return report


def print_summary(r):
    p5, p6, p7, p8, p9 = (r["phase5_raw"], r["phase6_residual"], r["phase7_bootstrap"],
                          r["phase8_opener"], r["phase9_decision"])
    print("\n" + "=" * 78)
    print(f"DUR-001 — PROP-0001 vs the closing totals market   [{r['data']}]")
    print("=" * 78)
    print(f"rows {p5['n_rows']}  fights {p5['n_fights']}  events {p5['n_events']}  "
          f"coverage {p5['coverage_by_threshold']}  close basis {p5['close_basis']}")
    if "LL_market" in p5:
        print(f"raw:      LL market {p5['LL_market']:.4f} | LL CFL {p5['LL_cfl']:.4f} | "
              f"G_LL(raw) {p5['G_LL_raw']:+.4f} | Brier {p5['Brier_market']:.4f} vs {p5['Brier_cfl']:.4f}")
    if "G_LL" in p6:
        print(f"residual: LL base {p6['LL_market_baseline']:.4f} | LL base+CFL {p6['LL_market_plus_cfl']:.4f} | "
              f"G_LL {p6['G_LL']:+.4f}  (scored {p6['n_scored_rows']} rows / {p6['n_scored_events']} events)")
        print(f"          dBrier {p6['delta_Brier']:+.4f} | challenger cal slope "
              f"{p6['cal_challenger']['slope']} intercept {p6['cal_challenger']['intercept']}")
    if p7.get("G_LL"):
        print(f"bootstrap ({p7['draws']} event draws): G_LL {p7['G_LL']['mean']:+.4f} "
              f"[{p7['G_LL']['lo95']:+.4f}, {p7['G_LL']['hi95']:+.4f}] | dBrier "
              f"[{p7['delta_Brier']['lo95']:+.4f}, {p7['delta_Brier']['hi95']:+.4f}]")
    if "MSE_gain" in p8:
        print(f"opener:   MSE open-only {p8['MSE_open_only']:.4f} | +CFL {p8['MSE_open_plus_cfl']:.4f} | "
              f"gain {p8['MSE_gain']:+.4f} ({p8['n_scored']} rows)")
    else:
        print(f"opener:   {p8.get('note')}")
    print(f"VERDICT:  {p9['verdict']}  checks={p9.get('checks')}")
    print("=" * 78)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--draws", type=int, default=10000)
    ap.add_argument("--out", default=os.path.join(ENGINE, os.pardir, "out_real", "dur001"))
    ap.add_argument("--synthetic", type=int, default=0, metavar="N_EVENTS",
                    help="run on N synthetic events instead of live data (pipeline check only)")
    ap.add_argument("--synthetic-signal", type=float, default=0.0,
                    help="planted residual CFL signal for the synthetic run (0 = none)")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if args.synthetic:
        df = make_synthetic(args.synthetic, cfl_signal=args.synthetic_signal)
        run(df, args.draws, os.path.join(args.out, "synthetic"),
            f"SYNTHETIC {args.synthetic} events, planted signal {args.synthetic_signal}")
        return
    base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = (os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
           or os.environ.get("SUPABASE_SERVICE_KEY"))
    if not base_url or not key:
        sys.exit("SUPABASE_URL + service key required (or use --synthetic N).")
    print("[dur001] loading live closes, locks and outcomes ...")
    df = load_live(base_url, key)
    if df.empty:
        print("[dur001] no (closing consensus × PROP-0001 lock) rows yet — the ledgers are "
              "prospective; re-run after the first captured card settles.")
        run(pd.DataFrame(columns=["fight_id", "event_id", "event_date", "line", "p_market", "p_cfl",
                                  "p_open", "close_books", "open_books", "start_basis",
                                  "scheduled_rounds", "is_void", "duration_seconds"]),
            args.draws, args.out, "live (empty)")
        return
    run(df, args.draws, args.out, "live")


if __name__ == "__main__":
    main()
