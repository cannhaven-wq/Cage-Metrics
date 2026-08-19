"""CFL cardio fade-slope model — Steps 3-5: fit, exposure metrics, validation.

The model:

    output_rate ~ cumulative_min_midpoint + opponent_output_rate + C(weight_class)
    groups      = fighter_id
    re_formula  = ~cumulative_min_midpoint

The per-fighter random slope on cumulative_min_midpoint IS the cardio score.
More negative = output falls away faster as the fight wears on.

Why a mixed model rather than a per-fighter regression: partial pooling. A
fighter with two eligible fights gets pulled toward the population mean; one
with fifteen barely moves. That is exactly the correction the censoring problem
needs — fighters who finish early simply have less late-round data, and pooling
handles the resulting uncertainty honestly. No extra shrinkage is applied on
top; doing it twice would over-shrink.

Nothing about finishing enters the model. Not as a feature, not as a filter.

Usage:
    python cfl_engine/cardio/fit_model.py                  # full fit + validation
    python cfl_engine/cardio/fit_model.py --skip-validation
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = os.path.join(HERE, "round_observations.csv")
DEFAULT_OUT = os.path.join(HERE, "fighter_cardio.csv")

FORMULA = "output_rate ~ cumulative_min_midpoint + opponent_output_rate + C(weight_class)"
RE_FORMULA = "~cumulative_min_midpoint"
SLOPE_KEY = "cumulative_min_midpoint"

# Validation split. Fights strictly before this date train the model; the rest
# are held out. Chosen to leave a few hundred fighters with testable late-round
# data on the far side.
DEFAULT_CUTOFF = "2023-01-01"


# --------------------------------------------------------------------------- data
def load(csv_path):
    df = pd.read_csv(csv_path)
    df["fight_date"] = df["fight_date"].astype(str)
    return df


def fighter_names():
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not base or not key:
        return {}
    headers = {"apikey": key, "Authorization": "Bearer " + key}
    out, offset = {}, 0
    while True:
        p = {"select": "id,name", "limit": "1000", "offset": str(offset)}
        req = urllib.request.Request(base + "/rest/v1/fighters?" + urllib.parse.urlencode(p),
                                     headers=headers)
        with urllib.request.urlopen(req) as r:
            batch = json.loads(r.read())
        for f in batch:
            out[f["id"]] = f["name"]
        if len(batch) < 1000:
            return out
        offset += 1000


# --------------------------------------------------------------------------- fit
def fit_model(df, label="model"):
    print("\n" + "=" * 78)
    print("FITTING  %s   (%d observations, %d fighters)"
          % (label, len(df), df.fighter_id.nunique()))
    print("=" * 78)
    md = smf.mixedlm(FORMULA, data=df, groups=df["fighter_id"], re_formula=RE_FORMULA)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = md.fit(method="lbfgs", maxiter=200)
    print("converged: %s" % fit.converged)
    fe = fit.fe_params
    print("\nfixed effects of interest:")
    print("  intercept (baseline output/min)      %+8.4f" % fe.get("Intercept", np.nan))
    print("  cumulative_min_midpoint (pop. fade)  %+8.4f  per minute" % fe.get(SLOPE_KEY, np.nan))
    print("  opponent_output_rate                 %+8.4f" % fe.get("opponent_output_rate", np.nan))
    print("\nrandom-effect covariance (fighter level):")
    print(fit.cov_re.to_string())
    return fit


def extract_slopes(fit):
    """Per-fighter fade slope (BLUP) plus a posterior SE where available."""
    re_dict = fit.random_effects
    rows = []
    cov_by_group = getattr(fit, "random_effects_cov", None)
    if callable(cov_by_group):
        try:
            cov_by_group = cov_by_group()
        except Exception:
            cov_by_group = None
    for fid, vals in re_dict.items():
        slope = float(vals.get(SLOPE_KEY, np.nan))
        se = np.nan
        if isinstance(cov_by_group, dict):
            c = cov_by_group.get(fid)
            try:
                se = float(np.sqrt(c.loc[SLOPE_KEY, SLOPE_KEY]))
            except Exception:
                se = np.nan
        rows.append({"fighter_id": fid, "fade_slope_dev": slope, "slope_se": se})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- exposure
def exposure(df):
    """Step 4 — how much evidence backs each fighter's slope."""
    g = df.groupby("fighter_id")
    start = df["cumulative_min_midpoint"] - df["round_duration_min"] / 2.0
    end = df["cumulative_min_midpoint"] + df["round_duration_min"] / 2.0
    past10 = (end - np.maximum(10.0, start)).clip(lower=0.0)
    tmp = df.assign(_past10=past10)

    reached_r3 = (df[df.round_num >= 3]
                  .groupby("fighter_id")["fight_id"].nunique()
                  .rename("n_fights_reaching_r3"))

    out = pd.DataFrame({
        "total_min_fought": g["round_duration_min"].sum(),
        "n_fights": g["fight_id"].nunique(),
        "n_round_obs": g.size(),
    })
    out["min_past_10"] = tmp.groupby("fighter_id")["_past10"].sum()
    out = out.join(reached_r3).fillna({"n_fights_reaching_r3": 0})
    out["n_fights_reaching_r3"] = out["n_fights_reaching_r3"].astype(int)
    return out.reset_index()


# --------------------------------------------------------------------------- validation
def observed_decline(df):
    """Observed R1 -> R3+ output change per fighter, in strikes/min."""
    r1 = df[df.round_num == 1].groupby("fighter_id")["output_rate"].mean()
    r3 = df[df.round_num >= 3].groupby("fighter_id")["output_rate"].mean()
    both = pd.concat([r1.rename("r1"), r3.rename("r3")], axis=1).dropna()
    return (both["r3"] - both["r1"]).rename("observed_decline")


def validate(df, cutoff, names):
    print("\n" + "=" * 78)
    print("STEP 5 — VALIDATION (time-based split at %s)" % cutoff)
    print("=" * 78)
    train = df[df.fight_date < cutoff]
    test = df[df.fight_date >= cutoff]
    print("train: %d obs / %d fights / %d fighters   (%s -> %s)"
          % (len(train), train.fight_id.nunique(), train.fighter_id.nunique(),
             train.fight_date.min(), train.fight_date.max()))
    print("test : %d obs / %d fights / %d fighters   (%s -> %s)"
          % (len(test), test.fight_id.nunique(), test.fighter_id.nunique(),
             test.fight_date.min(), test.fight_date.max()))

    fit = fit_model(train, label="TRAIN split")
    slopes = extract_slopes(fit).set_index("fighter_id")
    exp_train = exposure(train).set_index("fighter_id")

    obs = observed_decline(test)
    # Naive baseline: the fighter's own raw R1->R3 gap in the TRAINING data.
    # If the mixed model does not beat this, the machinery is not earning its keep.
    naive = observed_decline(train).rename("naive_train_decline")

    ev = pd.concat([slopes["fade_slope_dev"], naive, obs,
                    exp_train[["n_fights_reaching_r3", "min_past_10"]]], axis=1).dropna(
        subset=["fade_slope_dev", "observed_decline"])

    print("\nheld-out fighters with a fitted slope and testable late-round data: %d" % len(ev))
    if len(ev) < 30:
        print("  too few to judge — widen the window.")
        return fit

    for min_r3 in (0, 3, 5):
        sub = ev[ev.n_fights_reaching_r3 >= min_r3]
        if len(sub) < 20:
            continue
        r_model = sub["fade_slope_dev"].corr(sub["observed_decline"])
        rho_model = sub["fade_slope_dev"].corr(sub["observed_decline"], method="spearman")
        naive_sub = sub.dropna(subset=["naive_train_decline"])
        r_naive = (naive_sub["naive_train_decline"].corr(naive_sub["observed_decline"])
                   if len(naive_sub) > 20 else np.nan)
        print("\n  fighters with >= %d prior fights reaching R3   (n=%d)" % (min_r3, len(sub)))
        print("    fitted slope vs held-out decline : r = %+.3f   (spearman %+.3f)"
              % (r_model, rho_model))
        print("    naive train R1->R3 gap           : r = %+.3f   (n=%d)"
              % (r_naive, len(naive_sub)))

    core = ev[ev.n_fights_reaching_r3 >= 3].copy()
    if len(core) >= 40:
        core["bucket"] = pd.qcut(core["fade_slope_dev"], 4,
                                 labels=["Q1 fades hardest", "Q2", "Q3", "Q4 holds best"])
        print("\n  held-out output change (strikes/min, R1 -> R3+) by fitted-slope quartile:")
        tab = core.groupby("bucket", observed=True)["observed_decline"].agg(["mean", "median", "count"])
        print(tab.to_string(float_format=lambda v: "%+.2f" % v))
    return fit


def face_validity(slopes, exp, names, min_r3=5):
    print("\n" + "=" * 78)
    print("FACE VALIDITY — fighters with >= %d fights reaching round 3" % min_r3)
    print("=" * 78)
    m = slopes.merge(exp, on="fighter_id")
    m = m[m.n_fights_reaching_r3 >= min_r3].copy()
    m["name"] = m.fighter_id.map(names).fillna(m.fighter_id.astype(str))
    if m.empty:
        print("  none qualify.")
        return
    cols = ["name", "fade_slope_dev", "n_fights", "n_fights_reaching_r3", "min_past_10"]
    fmt = lambda d: d[cols].to_string(
        index=False,
        formatters={"fade_slope_dev": lambda v: "%+.4f" % v,
                    "min_past_10": lambda v: "%.1f" % v})
    print("\n  FADES HARDEST (most negative slope — output drops fastest):")
    print(fmt(m.nsmallest(10, "fade_slope_dev")))
    print("\n  HOLDS BEST (most positive slope — output holds or climbs):")
    print(fmt(m.nlargest(10, "fade_slope_dev")))


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--cutoff", default=DEFAULT_CUTOFF)
    ap.add_argument("--skip-validation", action="store_true")
    args = ap.parse_args()

    df = load(args.csv)
    names = fighter_names()

    if not args.skip_validation:
        validate(df, args.cutoff, names)

    # Production fit: everything.
    fit = fit_model(df, label="FULL (production)")
    slopes = extract_slopes(fit)
    exp = exposure(df)

    pop_slope = float(fit.fe_params.get(SLOPE_KEY, np.nan))
    out = slopes.merge(exp, on="fighter_id")
    # fade_slope_dev is the fighter's DEVIATION from the population fade. The
    # shipped score is the fighter's own absolute fade per minute.
    out["fade_slope"] = out["fade_slope_dev"] + pop_slope
    out["population_slope"] = pop_slope

    face_validity(slopes, exp, names)

    out = out[["fighter_id", "fade_slope", "fade_slope_dev", "population_slope", "slope_se",
               "total_min_fought", "min_past_10", "n_fights", "n_fights_reaching_r3",
               "n_round_obs"]].sort_values("fade_slope")
    out.to_csv(args.out, index=False)
    print("\n" + "=" * 78)
    print("Wrote %d fighter rows to %s" % (len(out), args.out))
    print("  population fade: %+.4f strikes/min per minute of fight time" % pop_slope)
    print("  fade_slope     : min %+.4f  median %+.4f  max %+.4f"
          % (out.fade_slope.min(), out.fade_slope.median(), out.fade_slope.max()))
    print("  slope_se availability: %d of %d rows"
          % (out.slope_se.notna().sum(), len(out)))
    print("=" * 78)


if __name__ == "__main__":
    main()
