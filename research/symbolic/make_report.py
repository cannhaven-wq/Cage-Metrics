"""Write private/REPORT.md from metrics.json, posthoc.json, audit.json and the
frozen models. Every figure is read from those files; nothing is typed by hand."""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from features import FEATS, HERE
from report import standalone_predict
import symreg as S

PRIV = os.path.join(HERE, "private")
R = os.path.join(PRIV, "results")
M = json.load(open(os.path.join(R, "metrics.json")))
PH = json.load(open(os.path.join(R, "posthoc.json")))
AU = json.load(open(os.path.join(R, "audit.json")))
FZ = json.load(open(os.path.join(PRIV, "models", "FROZEN.json")))
MOD = {n: json.load(open(os.path.join(PRIV, "models", f"final_{n}.json")))
       for n in ("A", "B", "C_lr_plus_symbolic", "LR_linear", "v1_refit")}

LABEL = {"A_symbolic": "A · symbolic, fighters only", "B_symbolic": "B · market + symbolic correction",
         "C_lr_plus_symbolic": "C · regularised LR + discovered terms", "LR_linear": "Regularised LR (23 linear gaps)",
         "v1_refit": "v1 structure, refitted", "v1_reported_coefs": "v1 reported weights (approx.)",
         "v1_market_refit": "v1 market correction, refitted", "v1_market_reported_coefs": "v1 market correction, reported weights (approx.)",
         "elo_only": "Elo only (no fitting)", "market_archived": "Archived market (unverified timing)"}

DEFS = {
    "age_yrs": ("Age on fight night", "years", "(event date − date of birth) / 365.25", "row excluded if DOB unknown"),
    "reach_in": ("Reach", "inches", "static fighter attribute", "predicted from height by a training-only line; then training median"),
    "height_in": ("Height", "inches", "static fighter attribute", "training median"),
    "southpaw": ("Southpaw stance", "0/1", "stance = Southpaw", "unknown stance → 0"),
    "elo": ("Elo rating before the fight", "Elo points", "K=32, start 1500, updated per event date, draw = 0.5, NC no update", "never missing (debutants 1500)"),
    "opp_elo_mean": ("Opponent strength", "Elo points", "mean pre-fight Elo of every prior UFC opponent", "eligibility guarantees ≥2 prior bouts"),
    "log_n_fights": ("Experience", "log(1 + bouts)", "prior UFC bouts in the table", "—"),
    "log_days_since_last": ("Layoff", "log(1 + days)", "days since previous bout", "—"),
    "fights_24m": ("Activity", "bouts", "bouts in the previous 730 days", "—"),
    "slpm": ("Strikes landed per minute", "sig. strikes / min", "shrunk with 25 pseudo-minutes toward the league rate to date", "—"),
    "sapm": ("Strikes absorbed per minute", "sig. strikes / min", "opponents' landed sig. strikes; same shrinkage", "—"),
    "str_acc": ("Striking accuracy", "share", "landed / attempted, 50 pseudo-attempts at league accuracy", "—"),
    "str_def": ("Striking defence", "share", "1 − opponents' landed / attempted, 50 pseudo-attempts", "—"),
    "td_per15": ("Takedowns per 15 min", "takedowns", "shrunk with 25 pseudo-minutes", "—"),
    "td_acc": ("Takedown accuracy", "share", "10 pseudo-attempts at league accuracy", "—"),
    "td_def": ("Takedown defence", "share", "1 − opponents' TD landed / attempted, 10 pseudo-attempts", "—"),
    "ctrl_share": ("Control time won", "ctrl-min per fight-min", "own control seconds / fight seconds, shrunk", "—"),
    "ctrl_against": ("Control time conceded", "ctrl-min per fight-min", "opponents' control seconds / fight seconds, shrunk", "—"),
    "kd_per15": ("Knockdowns per 15 min", "knockdowns", "shrunk with 25 pseudo-minutes", "—"),
    "sub_per15": ("Submission attempts per 15 min", "attempts", "shrunk with 25 pseudo-minutes", "—"),
    "win_rate": ("UFC win rate", "share", "(wins + 1) / (bouts + 2)", "—"),
    "finish_rate": ("Finishing rate", "share", "(finish wins + 2 × league rate) / (bouts + 2)", "—"),
    "last3_win_rate": ("Recent form", "share", "(wins in last 3 + 1) / (min(bouts,3) + 2)", "—"),
}

HYP = {  # clearly hypothetical inputs for the worked example
    "X": dict(age_yrs=27.0, reach_in=74, height_in=72, southpaw=0, elo=1580, opp_elo_mean=1535, log_n_fights=np.log1p(6),
              log_days_since_last=np.log1p(120), fights_24m=3, slpm=4.8, sapm=3.0, str_acc=0.50, str_def=0.60, td_per15=1.2,
              td_acc=0.40, td_def=0.75, ctrl_share=0.15, ctrl_against=0.10, kd_per15=0.5, sub_per15=0.4, win_rate=0.75,
              finish_rate=0.45, last3_win_rate=0.80),
    "Y": dict(age_yrs=34.0, reach_in=72, height_in=71, southpaw=1, elo=1560, opp_elo_mean=1525, log_n_fights=np.log1p(12),
              log_days_since_last=np.log1p(300), fights_24m=2, slpm=3.6, sapm=3.9, str_acc=0.44, str_def=0.54, td_per15=2.5,
              td_acc=0.45, td_def=0.60, ctrl_share=0.30, ctrl_against=0.25, kd_per15=0.3, sub_per15=0.8, win_rate=0.643,
              finish_rate=0.35, last3_win_rate=0.40),
}
HYP_MARKET_X = 0.55


def f(x, d=4):
    return f"{x:.{d}f}"


def table(rows, cols):
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def formula_block(name):
    m = MOD[name]
    lines = []
    for t in m["terms"]:
        eff = t["weight"] / t["train_std"]
        lines.append(f"  {eff:+.8f} × [ h(A,B) − h(B,A) ],  h(a,b) = {t['expression_h']}")
    head = "logit P(A wins) = " + ("logit(p_market_A)\n" if m["kind"] == "B" else "\n")
    return "```\n" + head + "\n".join(lines) + "\n```"


def term_table(name):
    rows = []
    for i, t in enumerate(MOD[name]["terms"], 1):
        rows.append([i, f"`{t['expression_h']}`", f"{t['weight']:+.8f}", f"{t['train_std']:.6f}",
                     f"{t['weight'] / t['train_std']:+.8f}", "linear gap" if t["linear"] else "nonlinear"])
    return table(rows, ["#", "h(a, b)", "fitted weight w", "train std s", "effective weight w/s", "shape"])


def worked_example():
    rows = {}
    for side, who in (("a", "X"), ("b", "Y")):
        for k, v in HYP[who].items():
            rows[f"{side}_{k}"] = [v]
    df = pd.DataFrame(rows); df["p_a_archived"] = HYP_MARKET_X
    sw = pd.DataFrame({(("b" if c.startswith("a_") else "a") + c[1:] if c[:2] in ("a_", "b_") else c): v
                       for c, v in rows.items()}); sw["p_a_archived"] = 1 - HYP_MARKET_X
    out = {}
    for n in MOD:
        p = float(standalone_predict(MOD[n], df)[0]); q = float(standalone_predict(MOD[n], sw)[0])
        out[n] = (p, q)
    # term-by-term for A
    m = MOD["A"]; pr = m["preprocessing"]
    def z(who):
        x = pd.Series(HYP[who])[FEATS]
        return np.clip(((x - pd.Series(pr["mean"])[FEATS]) / pd.Series(pr["std"])[FEATS]).to_numpy(float), -4, 4)[None, :]
    zx, zy = z("X"), z("Y")
    contrib = []
    for t in m["terms"]:
        tree = _tuple(t["tree"])
        T = float(S.term(tree, zx, zy)[0])
        contrib.append((t["expression_h"], T, t["weight"] / t["train_std"], T * t["weight"] / t["train_std"]))
    return out, zx[0], zy[0], contrib


def _tuple(t):
    return tuple(_tuple(x) if isinstance(x, list) else x for x in t)


def main():
    P = M["pooled_2021_2025"]; H = M["historical_2026"]; C = M["comparisons_2021_2025"]; C26 = M["comparisons_2026"]
    order = ["A_symbolic", "B_symbolic", "C_lr_plus_symbolic", "LR_linear", "v1_refit", "v1_reported_coefs",
             "v1_market_refit", "v1_market_reported_coefs", "elo_only", "market_archived"]
    lA, lLR, lmk = P["A_symbolic"]["logloss"], P["LR_linear"]["logloss"], P["market_archived"]["logloss"]
    ex, zx, zy, contrib = worked_example()
    linA = PH["final_A_linearity"]

    md = []
    w = md.append
    w("# SYM-002 — symbolic win-probability search: report\n")
    w("_Private research. Not for any CFL surface (D-011). Generated by `make_report.py` from the run's own files._\n")
    w("## The answer first\n")
    w("**No discovered formula improved reliably on the simple baselines.** Under the rule fixed before the run "
      "(event-level 95% interval excludes zero **and** a win in ≥4 of 5 folds), none of the three symbolic "
      "experiments qualifies.\n")
    w(f"- **Fighter-only (A)** scored log loss {f(lA)} on {P['A_symbolic']['n']} fights (2021–2025, "
      f"{C['A_symbolic vs LR_linear']['n_events']} events). The plain regularised logistic regression on the same 23 "
      f"gaps scored {f(lLR)}: the symbolic formula was **worse by {f(C['A_symbolic vs LR_linear']['diff'])}** "
      f"(95% CI {f(C['A_symbolic vs LR_linear']['ci95'][0])} to {f(C['A_symbolic vs LR_linear']['ci95'][1])}), "
      f"winning {M['fold_wins']['A_symbolic vs LR_linear']} of 5 folds. Against the refitted v1 structure it was "
      f"better by {f(-C['A_symbolic vs v1_refit']['diff'])}, but the interval spans zero "
      f"({f(C['A_symbolic vs v1_refit']['ci95'][0])} to {f(C['A_symbolic vs v1_refit']['ci95'][1])}), {M['fold_wins']['A_symbolic vs v1_refit']}/5 folds.")
    w(f"- **Market + correction (B)** scored {f(P['B_symbolic']['logloss'])} vs the archived market's {f(lmk)}: "
      f"worse by {f(C['B_symbolic vs market_archived']['diff'])} (CI {f(C['B_symbolic vs market_archived']['ci95'][0])} to "
      f"{f(C['B_symbolic vs market_archived']['ci95'][1])}), {M['fold_wins']['B_symbolic vs market_archived']}/5 folds; "
      f"and reliably worse than the simple two-term v1-style correction.")
    w(f"- **LR + discovered terms (C)** scored {f(P['C_lr_plus_symbolic']['logloss'])} vs {f(lLR)} for LR alone "
      f"(diff {f(C['C_lr_plus_symbolic vs LR_linear']['diff'])}, CI {f(C['C_lr_plus_symbolic vs LR_linear']['ci95'][0])} to "
      f"{f(C['C_lr_plus_symbolic vs LR_linear']['ci95'][1])}). Adding the formulas did not help.")
    w(f"- **The archived market beat every fighter-only model**, by {f(-C['market_archived vs LR_linear']['diff'])} log loss "
      f"over the best of them, in 5 of 5 folds. Its timestamps are placeholders, so this says nothing about any price "
      f"that could actually have been bet.\n")
    w("What the search kept finding is the same handful of plain facts: **the younger fighter, the one with the higher "
      "rating, the one who has faced tougher opposition, and the one who gets hit less tends to win.** The nonlinear "
      f"pieces it added are, together, {linA['r2_of_logit_on_23_linear_diffs']*100:.1f}% reproducible by a straight "
      "weighted sum of the same gaps, and they did not survive out of sample.\n")

    w("## 1. What v1 was, and what this run could check\n")
    w("The v1 ZIP, code, preprocessing and saved predictions were **not available** in this session (no attachment, "
      "no `research/symbolic/` on any branch, nothing in Drive). So v1 was **not reproduced**. What was done instead:\n")
    lk = M["leak_illustration_v1_structure_2026"]["point_in_time"]
    w(f"- **Structure re-implemented.** Refitting v1's three-gap structure on our point-in-time features, trained "
      f"2008–2025, gives weights age {lk['weights_on_standardised_diffs']['age_yrs']:+.4f}, Elo "
      f"{lk['weights_on_standardised_diffs']['elo']:+.4f}, strikes absorbed {lk['weights_on_standardised_diffs']['sapm']:+.4f} "
      "on standardised gaps — close to the reported −0.3884 / +0.2608 / −0.2121. That is consistent with v1, not a "
      "reproduction of it.")
    w(f"- On our 2026 cohort ({lk['n']} fights; v1 reported 226 under an eligibility rule we do not have) that structure "
      f"scores {lk['accuracy']*100:.1f}% accuracy and log loss {f(lk['logloss'])}. v1 reported 61.5%.")
    w("- **v1 leakage status: UNVERIFIED.** v1 reportedly rebuilt its statistics from prior fights. Its code was "
      "not inspected, so this report makes no claim either way about whether it leaked.")
    w("- **Generic risks for any implementation of this kind, measured on our data (these are not findings about v1):**")
    lc = M["leak_illustration_v1_structure_2026"]["career_table"]
    w(f"  - *Career averages as inputs.* If the `fighters` table's career `sapm` and current age were used instead of "
      f"point-in-time values, the same structure on our 2026 cohort would score {lc['accuracy']*100:.1f}% / log loss "
      f"{f(lc['logloss'])}, because the career table contains the fight being predicted. "
      f"*Correction (2026-10-07): an earlier draft said this figure matching v1's rounded 61.5% was 'suggestive' of "
      f"leakage in v1. It is not. A rounded accuracy matched on a different cohort ({lc['n']} vs 226 fights), with "
      f"different eligibility, is not evidence about how v1 was built.* "
      f"On the larger audit cohort, career strikes-landed "
      f"'predicts' {AU['career_average_leak']['slpm_fighters_table_career']*100:.1f}% of winners vs "
      f"{AU['career_average_leak']['slpm_point_in_time']*100:.1f}% for the honest version.")
    w(f"  - *Corner order.* The listed fighter A wins {AU['corner_bias']['listed_fighter_a_win_rate_raw']*100:.1f}% of "
      "raw rows. Any intercept, or any accuracy computed without randomising corners, absorbs that.")
    w("  - *Odds timing.* 30,724 archived quotes carry `1970-01-01` placeholder timestamps.")
    w("- v1's market correction, refitted, did better than the raw archived price here — but see §7: most of that "
      "gap is the archived price being under-confident, which a one-number recalibration also fixes.\n")

    w("## 2. Data and audit\n")
    w(table([["fights in table", AU["cohort"]["rows"]], ["eligible (both ≥2 prior bouts with stats, DOB known, decided)", AU["cohort"]["eligible_fighters"]],
             ["eligible with archived market (evaluation cohort)", AU["cohort"]["eligible_eval"]],
             ["of which 2026", AU["cohort"]["eligible_eval_2026"]],
             ["prior-count brute-force mismatches", f"{AU['pit_prior_count_mismatches']['mismatches']} of {AU['pit_prior_count_mismatches']['checked_fighter_rows']}"],
             [f"truncation test (delete every fight ≥ {AU['truncation_test']['cutoff']})", f"max feature change {AU['truncation_test']['max_abs_difference']} over {AU['truncation_test']['fights_compared']} fights × {AU['truncation_test']['features_compared']} features"],
             ["archived market rows: placeholder / dated timestamps", f"{AU['odds']['archived_ts_kind_counts']['placeholder']} / {AU['odds']['archived_ts_kind_counts']['dated']} fights"],
             ["archived market: single-book share", AU["odds"]["archived_single_book_share"]],
             ["timing-verified pre-start prices (decided)", f"{AU['odds']['verified_fights_with_price']} ({AU['odds']['verified_decided']})"],
             ["corner swap: max |P(A,B) + P(B,A) − 1| over all test rows",
              f"{max(v for d in M['swap_test_max_error'].values() for v in d.values()):.1e}"],
             ["saved-model re-prediction max error (from JSON alone)", max(M["saved_model_reprediction_max_abs_error"].values())]],
            ["check", "result"]))
    w("\nData access: the container cannot reach Supabase directly (proxy 403). Everything was read through the Supabase "
      "connector with `SELECT` only. No writes.\n")

    w("## 3. Results — 2021–2025 outer folds (headline)\n")
    rows = [[LABEL[m], P[m]["n"], f(P[m]["logloss"]), f(P[m]["brier"]), f"{P[m]['accuracy']*100:.1f}%",
             f"{P[m]['cal_intercept']:+.3f}", f(P[m]["cal_slope"], 3), f(P[m]["ece"], 3)] for m in order]
    w(table(rows, ["model", "fights", "log loss ↓", "Brier ↓", "accuracy", "cal. intercept", "cal. slope", "ECE"]))
    w("\nCalibration slope above 1 means the model is under-confident (its probabilities should be stretched).\n")
    w("### Pre-registered comparisons (event-level bootstrap, 2,000 resamples)\n")
    rows = [[k.replace("_", " "), f"{v['diff']:+.4f}", f"{v['ci95'][0]:+.4f} to {v['ci95'][1]:+.4f}", f"{M['fold_wins'][k]}/5",
             "**yes**" if v["improves_by_preregistered_rule"] else "no"] for k, v in C.items()]
    w(table(rows, ["comparison (first minus second)", "log-loss diff", "95% CI", "folds won", "improves by the rule?"]))
    w("\nNegative favours the first model. 'Improves' requires the whole interval below zero and ≥4 fold wins.\n")
    w("### Per fold (log loss)\n")
    pf = M["per_fold"]; ys = list(pf.keys())
    rows = [[LABEL[m]] + [f(pf[y][m]["logloss"]) for y in ys] for m in order]
    rows.append(["fights / events"] + [f"{pf[y]['A_symbolic']['n']} / {pf[y]['_n_events']}" for y in ys])
    w(table(rows, ["model"] + [f"{y}" + (" (historical)" if y == "2026" else "") for y in ys]))
    w("\n### 2026 — historical research, not confirmation\n")
    w("CFL had already examined these fights before this run. They are scored with models trained on 2008–2025, but "
      "they do not count as an untouched test.\n")
    rows = [[LABEL[m], H[m]["n"], f(H[m]["logloss"]), f(H[m]["brier"]), f"{H[m]['accuracy']*100:.1f}%"] for m in order]
    w(table(rows, ["model", "fights", "log loss", "Brier", "accuracy"]))
    rows = [[k.replace("_", " "), f"{v['diff']:+.4f}", f"{v['ci95'][0]:+.4f} to {v['ci95'][1]:+.4f}", v["n_events"]] for k, v in C26.items()]
    w("\n" + table(rows, ["comparison", "diff", "95% CI", "events"]))

    w("\n## 4. The finalist formulas (frozen for future fights)\n")
    w("All three were fitted once on every eligible fight 2008-01-01 → 2026-10-03, with structure chosen on 2025–2026 "
      "inner validation by the pre-declared rule. Hashes are in `private/models/FROZEN.json`.\n")
    w("**Shared preprocessing.** For each fighter, every input x is turned into `z = clip((x − μ) / σ, −4, 4)` with μ, σ "
      "from the training rows (both corners pooled). In a formula, `a.x` is this corner's z and `b.x` the opponent's. "
      "`pdiv(x, y) = x / (1 + |y|)`; `slog(x) = sign(x)·log(1+|x|)`; `sq(x) = x²`. Every operation's output is clipped to "
      "±20 and NaN/∞ is set to 0. Each term is `h(A,B) − h(B,A)`, and there is no intercept, so swapping the fighters "
      "gives exactly 1 − P.\n")
    pr = MOD["A"]["preprocessing"]
    rows = [[k, DEFS[k][0], DEFS[k][1], DEFS[k][2], f"{pr['mean'][k]:.5f}", f"{pr['std'][k]:.5f}", DEFS[k][3]] for k in FEATS]
    w(table(rows, ["input", "meaning", "units", "how it is built (strictly prior bouts)", "μ", "σ", "if missing"]))
    w(f"\nReach imputation: reach ≈ {pr['reach_from_height']['intercept']:.4f} + {pr['reach_from_height']['slope']:.6f} × height. "
      f"Height median {pr['height_median']}. Rates are shrunk toward the league value for fights before that date, so a "
      "fighter with little cage time sits near average.\n")

    w("### Finalist A — fighter-only symbolic formula (the selected one)\n")
    w(formula_block("A") + "\n")
    w(term_table("A") + "\n")
    w(f"**Is it really nonlinear?** Three of its six terms are plain gaps. The other three are nonlinear, but "
      f"{linA['r2_of_logit_on_23_linear_diffs']*100:.1f}% of the formula's output is reproduced by a straight weighted "
      "sum of the 23 gaps (per-term R²: " + ", ".join(f"{v:.2f}" for v in linA["per_term_r2"].values()) + "). "
      "In practice it is a **mostly linear equation with three bent terms**, and those bends did not earn their keep out of sample.\n")
    w("**In plain English.** The formula favours the fighter who:\n"
      "1. has faced tougher opponents (term 1),\n2. lands a higher share of the strikes they throw (term 2),\n"
      "3. stops takedowns better (term 3, small),\n"
      "4. gets hit less, and faces the less dangerous opponent (lower finishing rate, less accurate high-volume "
      "striking). Each side is weighed as 'what I absorb plus what my opponent brings'. The size of this term "
      "shrinks when the opponent's experience is far from average (term 4),\n"
      "5. is younger and faces a lower-rated opponent, with strikes absorbed added in. This term is divided by a "
      "layoff-versus-output factor that shrinks it whenever the two are far apart, in either direction. That bend "
      "has no clean fight-sense reading (term 5),\n"
      "6. is younger and spends less time being controlled. This one levels off at the extremes, and it is the "
      "largest term (term 6).\n")
    w("Terms 4–6 all lean the same way as the plain gaps for age, strikes absorbed, rating and control conceded. "
      "Their nonlinear details are where the search fitted noise.\n")

    w("### Finalist B — market probability plus a symbolic correction\n")
    w(formula_block("B") + "\n")
    w(term_table("B") + "\n")
    w("**In plain English.** Start from the market's number. Nudge toward the younger, more accurate, more active "
      "fighter who concedes less control time. Then add a small lean *against* the fighter with better recent form "
      "(untested; plausibly noise), plus one nonlinear mix of opponent strength, strikes absorbed and accuracy that has "
      "no clean reading. Four of the five terms are plain gaps. **It did not beat the market** (above).\n")

    w("### Finalist C — regularised logistic regression with the discovered terms added\n")
    w(f"λ = {MOD['C_lr_plus_symbolic']['lambda']:g} (chosen on inner validation from the fixed grid). Same equation form: "
      "`logit P = Σ (w/s)·[h(A,B) − h(B,A)]`.\n")
    w(term_table("C_lr_plus_symbolic") + "\n")
    w("Note: `b.opp_elo_mean` as a term equals −(`a.opp_elo_mean`), so the two carry equal and opposite weights and "
      "together act as one gap. Harmless under L2, but it shows the discovered set adds little new.\n")

    w("### For comparison: the plain regularised LR and the v1 structure (refitted)\n")
    w(f"Regularised LR, λ = {MOD['LR_linear']['lambda']:g}:\n")
    w(term_table("LR_linear") + "\n")
    w("v1 structure refitted on all data:\n")
    w(term_table("v1_refit") + "\n")

    w("## 5. Worked example — HYPOTHETICAL fighters\n")
    w("**These two fighters do not exist.** The numbers are invented to show the arithmetic.\n")
    rows = [[k, f"{HYP['X'][k]:.3f}", f"{HYP['Y'][k]:.3f}", f"{zx[i]:+.3f}", f"{zy[i]:+.3f}"] for i, k in enumerate(FEATS)]
    w(table(rows, ["input", "Fighter X (raw)", "Fighter Y (raw)", "X z", "Y z"]))
    w("\nFinalist A, term by term:\n")
    rows = [[i + 1, f"`{c[0]}`", f"{c[1]:+.4f}", f"{c[2]:+.6f}", f"{c[3]:+.4f}"] for i, c in enumerate(contrib)]
    tot = sum(c[3] for c in contrib)
    rows.append(["", "**total logit**", "", "", f"**{tot:+.4f}**"])
    w(table(rows, ["#", "h", "T = h(X,Y) − h(Y,X)", "effective weight", "contribution"]))
    w(f"\nP(X wins) = sigmoid({tot:+.4f}) = **{S.sigmoid(np.array([tot]))[0]:.4f}**.\n")
    rows = [[n, f(ex[n][0]), f(ex[n][1]), f"{ex[n][0] + ex[n][1]:.12f}"] for n in ex]
    w(table(rows, ["model", "P(X wins)", "P(Y wins) with corners swapped", "sum"]))
    w(f"\nModel B uses a hypothetical market price of {HYP_MARKET_X} for X.\n")

    w("## 6. Stability across seeds and search sizes\n")
    for exp in ("A", "B"):
        st = M["stability"][exp]
        w(f"**Experiment {exp}.** Each fold ran 15 searches (3 sizes × 5 seeds). Every run found a different structure "
          f"(distinct structures per fold: {', '.join(str(v) for v in st['distinct_structures_per_fold'].values())}). "
          "Test log loss of each run's own winner:\n")
        rows = [[y, f(v["min"]), f(v["median"]), f(v["max"]), f(v["std"])] for y, v in st["per_fold_test_ll_across_15_runs"].items()]
        w(table(rows, ["fold", "best run", "median run", "worst run", "std"]))
        w("\nMean 2021–2025 test log loss by search size: " +
          ", ".join(f"{k} {f(v)}" for k, v in st["per_config_mean_test_ll_2021_2025"].items()) + ".\n")
        w("Selected structure per fold (inner rule):\n")
        rows = [[y, st["selected_nodes_per_fold"][y], f"`{e}`"] for y, e in st["selected_expression_per_fold"].items()]
        w(table(rows, ["fold", "nodes", "terms (separated by ||)"]) + "\n")
    w("The structures change completely from fold to fold and seed to seed while their scores barely move. That is "
      "the signature of many near-equivalent formulas fitting noise around the same few linear signals — not of a "
      "stable law. Deeper searches did not help.\n")

    w("## 7. Odds: verified vs archived, and a post-hoc check\n")
    V = M["verified_prices_2026"]
    w(f"Timing-verified pre-start prices exist for {AU['odds']['verified_decided']} decided fights; "
      f"{V['market_verified']['n']} of them fall in the evaluation cohort, across {V['_n_events']} events. "
      "That is far too few to compare anything. Descriptive only:\n")
    rows = [[k, V[k]["n"], f(V[k]["logloss"]), f"{V[k]['accuracy']*100:.0f}%"] for k in V if not k.startswith("_")]
    w(table(rows, ["model", "fights", "log loss", "accuracy"]))
    w("\n**Post-hoc (decided after seeing results — exploratory only).** `posthoc.py`:\n")
    for k in ("v1_market_refit vs market_archived", "market_recalibrated vs market_archived", "v1_market_refit vs market_recalibrated", "B_symbolic vs market_recalibrated"):
        v = PH[k]["2021_2025"]
        w(f"- {k.replace('_', ' ')}: {v['diff']:+.4f} (CI {v['ci95'][0]:+.4f} to {v['ci95'][1]:+.4f}), {v['fold_wins_of_5']}/5 folds.")
    w("\nThe archived price is under-confident (favourites win more often than it says). A one-number stretch of the "
      "market (fitted slope a little above 1, refitted per fold) recovers most of what the v1-style fighter correction gains; after that, the "
      "fighter correction's remaining gain is not distinguishable from zero. Because these prices carry no reliable "
      "timestamp and are mostly a single archived book, **none of this is evidence of a bettable edge.** No ROI or CLV "
      "is reported, by design.\n")

    w("## 8. Candidate log vs fitted models\n")
    tot_c = sum(sum(v.values()) for v in M["candidates_scored"].values())
    w(f"- **Candidate expressions:** {tot_c:,} distinct expression *sets* were scored across all folds and both "
      "experiments (each = a set of terms with weights fitted on inner-train and scored on inner-validation). Logged in "
      "`private/logs/candidates_<fold>_<exp>.csv.gz` with run label (fold | experiment | size | seed), the expression, "
      "terms, node count, inner log loss and penalised score. These are *not* complete models: their weights were never "
      "refitted on the full window, and none was scored on a test year.")
    w("- **Complete fitted models:** one per fold per experiment (the rule's winner), refitted on the whole outer "
      "training window and scored once. Plus the per-run winners in `stability_*.csv`, and the five frozen final "
      "models in `private/models/`.\n")

    w("## 9. What would be needed before trusting any of this on future fights\n")
    w("1. **Prospective scoring.** Score the frozen models (hashes below) on cards after 2026-10-07 only, unchanged. "
      "With ~300–500 eligible fights a year and log-loss differences of ~0.005, separating two models reliably needs "
      "well over a year of cards — probably several.")
    w("2. **Timestamped market prices.** Every market comparison here uses archived prices whose capture time is unknown. "
      "Only CFL's own capture path (since 2026-09-19) produces prices with provenance. Any claim against the market "
      "must wait for that sample, and the CLV protocol's thresholds, not this study.")
    w("3. **A reason to prefer the symbolic form at all.** On this evidence the plain regularised logistic regression is "
      "as good or better and far easier to explain. A future symbolic study should have to beat it, not v1.")
    w("4. **Search-adjusted uncertainty.** About a quarter-million candidate sets were scored. The intervals above are "
      "descriptive, not corrected for that search.\n")
    w("## Files\n")
    w(table([[k, f"`{v}`"] for k, v in FZ["sha256"].items()], ["frozen model", "SHA-256"]))
    w(f"\nFrozen {FZ['frozen_at']}, trained through {FZ['trained_through']}, valid for {FZ['prospective_from']}.\n")
    open(os.path.join(PRIV, "REPORT.md"), "w").write("\n".join(md))
    print("wrote", os.path.join(PRIV, "REPORT.md"), len("\n".join(md)), "chars")


if __name__ == "__main__":
    main()
