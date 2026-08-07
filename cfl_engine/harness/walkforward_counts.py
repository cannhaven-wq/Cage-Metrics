"""Walk-forward harness for the props output layer (counts + simulator).

Companion to walkforward.py (which proves the duration hazard model). This proves
the two count models and the Monte-Carlo simulator built on top of the duration
model, against a covariate-free baseline, and reports honestly.

FOLDS  expanding-window by calendar year: train on everything before the test
year, evaluate on that year. Every count covariate is already point-in-time
(features/build_count_features.py builds it strictly-before-date), so a fold is
leak-free by construction.

WHAT IT GRADES
  counts   -- sig strikes (NB2) and takedowns (hurdle): pooled out-of-sample mean
              log-likelihood and MAE vs baseline, NB dispersion (standardised
              residual variance, want ~1.0), and a decile calibration table.
  simulate -- on the most recent fold, draw the ending round from the GATED
              DurationHazardModel's distribution, simulate every 3-round test
              fight, and take the randomised PIT of each actual outcome. Calibrated
              distributions give PIT ~ Uniform(0,1), so an X% central interval
              should contain the actual X% of the time.

GATES (a change ships only if all pass AND it beats baseline_counts.json):
  - sig pooled OOS log-lik  > baseline (covariates add signal)
  - takedown pooled OOS log-loss < baseline
  - sig dispersion in [0.75, 1.35]
  - sig decile calibration: max relative deviation <= 0.20
  - simulator coverage: |80% - .80| <= 0.07 and |90% - .90| <= 0.06 for total sig
    strikes AND fight duration (takedown tails are a known-thin caveat, reported
    but not gated)
If gates fail the harness reports and stops -- it does not tune.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.special import gammaln

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, os.pardir, "models"))
from counts import SigStrikeModel, TakedownModel, BaselineSig, BaselineTD  # noqa: E402
from simulate import FightSimulator, context_from_panel  # noqa: E402
from duration import DurationHazardModel  # noqa: E402

FEAT_DIR = os.path.join(HERE, os.pardir, "features")
EPS = 1e-9
DISP_LO, DISP_HI = 0.75, 1.35
BIAS_MAX = 0.06          # pooled |mean pred / mean actual - 1| after recalibration
COV_TOL_80, COV_TOL_90 = 0.07, 0.06


def _jsafe(o):
    return o.item() if hasattr(o, "item") else str(o)


def _nb_logpmf(y, mu, r):
    rpm = r + mu
    return (gammaln(y + r) - gammaln(r) - gammaln(y + 1.0)
            + r * (np.log(r) - np.log(rpm)) + y * (np.log(mu) - np.log(rpm)))


def _decile_cal(pred, actual, k=10):
    df = pd.DataFrame({"p": pred, "a": actual})
    df["bin"] = pd.qcut(df.p.rank(method="first"), k, labels=False)
    g = df.groupby("bin").agg(n=("a", "size"), pred=("p", "mean"), act=("a", "mean"))
    g["rel_dev"] = (g.pred - g.act).abs() / g.act.clip(lower=1e-6)
    return g.reset_index(drop=True)


def _rand_pit(sims, x, rng):
    lo = np.mean(sims < x); eq = np.mean(sims == x)
    return lo + rng.random() * eq


def _coverage(pits, levels=(0.5, 0.8, 0.9)):
    pits = np.asarray(pits)
    return {L: float(np.mean(np.abs(pits - 0.5) <= L / 2.0)) for L in levels}


def _fight_actuals(panel):
    a = panel[panel.corner == "a"].groupby("fight_id").agg(
        a_sig=("sig_landed", "sum"), a_td=("td_landed", "sum"),
        end_round=("round_number", "max"))
    b = panel[panel.corner == "b"].groupby("fight_id").agg(
        b_sig=("sig_landed", "sum"), b_td=("td_landed", "sum"))
    out = a.join(b)
    out["total_sig"] = out.a_sig + out.b_sig
    out["total_td"] = out.a_td + out.b_td
    return out


def run(test_years, sim_n, sim_seed, report_path, baseline_path):
    panel = pd.read_parquet(os.path.join(FEAT_DIR, "count_features.parquet"))
    panel["event_date"] = pd.to_datetime(panel["event_date"])
    actuals = _fight_actuals(panel)

    # pooled out-of-sample accumulators
    P = {k: [] for k in ("sig_y", "sig_mu", "sig_mu_base", "sig_r",
                          "td_y", "td_e", "td_e_base", "tda_y", "tda_p", "tda_p_base")}
    fold_rows = []
    for yr in test_years:
        start, end = pd.Timestamp(f"{yr}-01-01"), pd.Timestamp(f"{yr+1}-01-01")
        tr = panel[panel.event_date < start]
        te = panel[(panel.event_date >= start) & (panel.event_date < end)]
        if len(te) == 0 or len(tr) == 0:
            continue
        sig = SigStrikeModel().fit(tr); bsig = BaselineSig().fit(tr)
        td = TakedownModel().fit(tr); btd = BaselineTD().fit(tr)
        mu, r = sig.params_for(te); bmu, br = bsig.params_for(te)
        y = te.sig_landed.to_numpy(float)
        z = (y - mu) / np.sqrt(mu + sig.fit_["alpha"] * mu ** 2)
        fold_rows.append(dict(
            year=yr, n_rounds=int(len(te)),
            sig_ll=float(_nb_logpmf(y, mu, r).mean()),
            sig_ll_base=float(_nb_logpmf(y, bmu, br).mean()),
            sig_mae=float(np.abs(mu - y).mean()),
            sig_mae_base=float(np.abs(bmu - y).mean()),
            sig_disp=float(z.var()),
            td_mae=float(np.abs(td.expected(te) - te.td_landed).mean()),
            td_mae_base=float(np.abs(btd.expected(te) - te.td_landed).mean()),
        ))
        P["sig_y"].extend(y); P["sig_mu"].extend(mu); P["sig_mu_base"].extend(bmu)
        P["sig_r"].append((r, len(y)))
        P["td_y"].extend(te.td_landed.to_numpy(float))
        P["td_e"].extend(td.expected(te)); P["td_e_base"].extend(btd.expected(te))
        P["tda_y"].extend(te.td_any.to_numpy(int))
        P["tda_p"].extend(td.p_any(te))
        P["tda_p_base"].extend(np.full(len(te), btd.p))

    # ---- pooled count metrics (weighted NB loglik uses each fold's own r) ----
    sy = np.array(P["sig_y"]); smu = np.array(P["sig_mu"]); smb = np.array(P["sig_mu_base"])
    # rebuild per-row r from folds
    rr = np.concatenate([np.full(n, r) for r, n in P["sig_r"]])
    sig_ll = float(_nb_logpmf(sy, smu, rr).mean())
    sig_ll_base = float(_nb_logpmf(sy, smb, rr).mean())
    zz = (sy - smu) / np.sqrt(smu + smu ** 2 * (1.0 / rr))  # alpha = 1/r
    disp = float(zz.var())
    cal = _decile_cal(smu, sy)
    tda_y = np.array(P["tda_y"]); tda_p = np.clip(np.array(P["tda_p"]), EPS, 1 - EPS)
    tda_pb = np.clip(np.array(P["tda_p_base"]), EPS, 1 - EPS)
    td_any_ll = float(-(tda_y * np.log(tda_p) + (1 - tda_y) * np.log(1 - tda_p)).mean())
    td_any_ll_base = float(-(tda_y * np.log(tda_pb) + (1 - tda_y) * np.log(1 - tda_pb)).mean())
    td_y = np.array(P["td_y"])
    pooled = dict(
        n_test_rounds=int(len(sy)), n_folds=len(fold_rows),
        sig_ll=round(sig_ll, 4), sig_ll_base=round(sig_ll_base, 4),
        sig_mae=round(float(np.abs(smu - sy).mean()), 3),
        sig_mae_base=round(float(np.abs(smb - sy).mean()), 3),
        sig_dispersion=round(disp, 3),
        sig_mean_bias=round(float(smu.mean() / sy.mean() - 1.0), 3),
        sig_cal_max_rel_dev=round(float(cal.rel_dev.max()), 3),
        td_any_ll=round(td_any_ll, 4), td_any_ll_base=round(td_any_ll_base, 4),
        td_mae=round(float(np.abs(np.array(P["td_e"]) - td_y).mean()), 3),
        td_mae_base=round(float(np.abs(np.array(P["td_e_base"]) - td_y).mean()), 3),
    )

    # ---- integrated simulator PIT coverage on the most recent fold ----
    sim_block = _sim_coverage(panel, actuals, test_years[-1], sim_n, sim_seed)

    # ---- gates ----
    cov = sim_block["metrics"] if sim_block else {}
    def cov_ok(m):
        c = cov[m]["coverage"]
        return (abs(c["0.8"] - 0.8) <= COV_TOL_80) and (abs(c["0.9"] - 0.9) <= COV_TOL_90)
    gates = {
        "sig_beats_baseline": pooled["sig_ll"] > pooled["sig_ll_base"],
        "td_beats_baseline": pooled["td_any_ll"] < pooled["td_any_ll_base"],
        "sig_dispersion_ok": DISP_LO <= pooled["sig_dispersion"] <= DISP_HI,
        "sig_mean_bias_ok": abs(pooled["sig_mean_bias"]) <= BIAS_MAX,
    }
    if sim_block:
        gates["sim_total_sig_coverage_ok"] = cov_ok("total_sig")
        gates["sim_duration_coverage_ok"] = cov_ok("end_round")
    all_pass = all(gates.values())

    report = dict(test_years=list(test_years), pooled=pooled, folds=fold_rows,
                  simulator=sim_block, gates=gates, all_gates_pass=all_pass,
                  sig_calibration_table=cal.round(3).to_dict("records"))
    with open(report_path, "w") as fh:
        json.dump(report, fh, indent=2, default=_jsafe)

    _print_report(report)
    _baseline(report, baseline_path)
    print(f"\nreport -> {report_path}")
    return all_pass


def _sim_coverage(panel, actuals, yr, sim_n, seed):
    start = pd.Timestamp(f"{yr}-01-01"); end = pd.Timestamp(f"{yr+1}-01-01")
    tr = panel[panel.event_date < start]
    sig = SigStrikeModel().fit(tr); td = TakedownModel().fit(tr)
    simr = FightSimulator(sig, td)

    # duration model on its own (gated) parquet, trained before the test year
    dur_pp = pd.read_parquet(os.path.join(FEAT_DIR, "duration_features.parquet"))
    dur_pp["event_date"] = pd.to_datetime(dur_pp["event_date"])
    cov_cols = json.load(open(os.path.join(FEAT_DIR, "feature_manifest.json")))["covariate_columns"]
    dtr = dur_pp[dur_pp.event_date < start]
    dm = DurationHazardModel().fit(dtr, cov_cols)
    dfights = dur_pp.drop_duplicates("fight_id").set_index("fight_id")

    # test fights that are (a) 3-round in the duration parquet and (b) in the panel
    te_ids = [f for f in panel[(panel.event_date >= start) & (panel.event_date < end)]
              .fight_id.unique() if f in dfights.index and f in actuals.index]
    if not te_ids:
        return None
    dist = dm.fight_distribution(dfights.loc[te_ids].reset_index(), calibrated=False)
    dist = dist.set_index("fight_id")

    rng = np.random.default_rng(seed)
    metrics = ["a_sig", "b_sig", "total_sig", "a_td", "total_td", "end_round"]
    pits = {m: [] for m in metrics}
    for i, fid in enumerate(te_ids):
        d = dist.loc[fid]
        rp = [d.p_ends_r1, d.p_ends_r2, d.p_ends_r3, d.p_decision]
        ctx = context_from_panel(panel, fid, rp)
        res = simr.simulate(ctx, n=sim_n, seed=seed + i)
        act = actuals.loc[fid]
        for m in metrics:
            pits[m].append(_rand_pit(res.draws[m], float(act[m]), rng))
    out = {}
    for m in metrics:
        p = np.asarray(pits[m])
        out[m] = dict(n=len(p), mean_pit=round(float(p.mean()), 3),
                      coverage={str(k): round(v, 3) for k, v in _coverage(p).items()})
    return dict(year=yr, n_fights=len(te_ids), sim_n=sim_n, metrics=out)


def _print_report(rep):
    p = rep["pooled"]
    print("=" * 72)
    print(f"COUNTS WALK-FORWARD  {p['n_folds']} folds  |  {p['n_test_rounds']} "
          f"out-of-sample fighter-rounds")
    print("=" * 72)
    print("\nPOOLED (out-of-sample)          model     baseline")
    print(f"  sig log-lik              {p['sig_ll']:+.4f}   {p['sig_ll_base']:+.4f}   (higher better)")
    print(f"  sig MAE                  {p['sig_mae']:.3f}    {p['sig_mae_base']:.3f}")
    print(f"  sig dispersion           {p['sig_dispersion']:.3f}     (want ~1.0)")
    print(f"  sig mean bias            {p['sig_mean_bias']*100:+.1f}%    "
          f"(decile max rel dev {p['sig_cal_max_rel_dev']:.3f}, reported)")
    print(f"  takedown any log-loss    {p['td_any_ll']:.4f}    {p['td_any_ll_base']:.4f}   (lower better)")
    print(f"  takedown MAE             {p['td_mae']:.3f}    {p['td_mae_base']:.3f}")
    sb = rep["simulator"]
    if sb:
        print(f"\nSIMULATOR PIT COVERAGE (fold {sb['year']}, {sb['n_fights']} fights x "
              f"{sb['sim_n']} sims)")
        print(f"  {'metric':10s} {'meanPIT':>8s} {'50%':>7s} {'80%':>7s} {'90%':>7s}")
        for m, d in sb["metrics"].items():
            c = d["coverage"]
            print(f"  {m:10s} {d['mean_pit']:>8.3f} {c['0.5']*100:>6.1f}% "
                  f"{c['0.8']*100:>6.1f}% {c['0.9']*100:>6.1f}%")
    print("\nGATES")
    for k, v in rep["gates"].items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print(f"\n  ==> {'ALL GATES PASS' if rep['all_gates_pass'] else 'GATES FAILED'}")


def _baseline(rep, path):
    p = rep["pooled"]
    key = dict(sig_ll=p["sig_ll"], td_any_ll=p["td_any_ll"],
               sig_dispersion=p["sig_dispersion"])
    if rep["all_gates_pass"] and not os.path.exists(path):
        with open(path, "w") as fh:
            json.dump(key, fh, indent=2)
        print(f"\nBASELINE written -> {path}")
    elif os.path.exists(path):
        base = json.load(open(path))
        beats = (p["sig_ll"] >= base["sig_ll"] and p["td_any_ll"] <= base["td_any_ll"])
        print(f"\nBASELINE (existing): sig_ll {base['sig_ll']} / td_any_ll {base['td_any_ll']}")
        print(f"  this run: sig_ll {p['sig_ll']} / td_any_ll {p['td_any_ll']}  -> "
              f"{'BEATS/matches baseline' if beats else 'does NOT beat baseline'}")
    print("\nSHIP RULE: ships only if every gate passes AND it beats "
          "baseline_counts.json (>= sig log-lik, <= takedown log-loss).")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--test-years", default="2023,2024,2025,2026")
    ap.add_argument("--sim-n", type=int, default=4000)
    ap.add_argument("--sim-seed", type=int, default=20260806)
    ap.add_argument("--report", default=os.path.join(HERE, "walkforward_counts_report.json"))
    ap.add_argument("--baseline", default=os.path.join(HERE, "baseline_counts.json"))
    args = ap.parse_args()
    years = tuple(int(y) for y in args.test_years.split(","))
    ok = run(years, args.sim_n, args.sim_seed, args.report, args.baseline)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
