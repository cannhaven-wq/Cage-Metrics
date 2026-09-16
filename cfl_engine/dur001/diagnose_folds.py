"""Fold-by-fold diagnostic: reproduced walk-forward vs the frozen gate report.

    python cfl_engine/dur001/diagnose_folds.py --run out_real/prop0001_wf_block
    python cfl_engine/dur001/diagnose_folds.py --run out_real/prop0001_wf_block --json

Why this exists
---------------
`walkforward_prop0001.py --mode block` reports MATCHES or DIFFERS against
`cfl_engine/harness/walkforward_report.json`. DIFFERS on its own is useless: it
says two numbers disagree without saying where. This lays the two runs side by
side per fold so the disagreement can be localised to a stage.

It is a **read-only comparison of two existing artifacts**. It fits nothing,
tunes nothing, and has no options that could change either side. That is
deliberate — the failure mode this whole investigation is guarding against is
turning a provenance question into model selection by nudging a knob until the
numbers line up.

What it separates
-----------------
Four stages, each of which could cause a pooled-metric difference, and each of
which leaves a different fingerprint:

  1. FOLD STRUCTURE   different block boundaries -> different windows
  2. DATA SELECTION   same boundaries, different row counts
  3. CALIBRATION      same rows, different `calibrated` flags or calibration
                      row counts; raw vs calibrated log loss shows the size of
                      the isotonic step
  4. BASELINE         same rows and calibration, different `const_logloss` —
                      the two harnesses define the constant-hazard baseline
                      differently, which says nothing about the model

Reading the verdict
-------------------
The verdict names the earliest stage that differs, because a difference at an
early stage makes every later comparison meaningless. If fold structure differs,
do not read anything into the calibration columns.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(HERE)
REPO = os.path.dirname(ENGINE)
HARNESS_REPORT = os.path.join(ENGINE, "harness", "walkforward_report.json")


def load(path: str) -> dict:
    with open(path) as fh:
        return json.load(fh)


def pair_folds(frozen: list[dict], mine: list[dict]) -> list[dict]:
    """Match folds on block_start, which is the only stable key across runs.

    Index-matching would silently pair the wrong folds if either run skipped
    one (the harness skips folds with too little training data).
    """
    by_start = {f["start"]: f for f in mine}
    rows = []
    for fz in frozen:
        rows.append({"start": fz["block_start"], "end": fz["block_end"],
                     "frozen": fz, "mine": by_start.get(fz["block_start"])})
    extra = sorted(set(by_start) - {f["block_start"] for f in frozen})
    for s in extra:
        rows.append({"start": s, "end": by_start[s]["end"],
                     "frozen": None, "mine": by_start[s]})
    return rows


def agreement(rows: list[dict]) -> dict:
    """Does the frozen report's log loss track our RAW or our CALIBRATED series?

    The decisive question once fold structure and rows agree. If the frozen
    numbers sit on the raw series, the frozen run was not applying the isotonic
    map this recipe applies — whatever its `calibrated` flag says.
    """
    raw_err, cal_err, exact_raw, exact_cal = [], [], [], []
    for r in rows:
        fz, me = r["frozen"], r["mine"]
        if not fz or not me or fz["n_test"] != me["n_test_rows"]:
            continue                      # only compare folds scoring the same rows
        dr = abs(me["raw_logloss"] - fz["model_logloss"])
        dc = abs(me["test_logloss"] - fz["model_logloss"])
        raw_err.append(dr)
        cal_err.append(dc)
        if dr <= 5e-4:
            exact_raw.append(r["start"])
        if dc <= 5e-4:
            exact_cal.append(r["start"])
    if not raw_err:
        return {"comparable_folds": 0}
    n = len(raw_err)
    return {
        "comparable_folds": n,
        "mean_abs_diff_raw_vs_frozen": round(sum(raw_err) / n, 5),
        "mean_abs_diff_calibrated_vs_frozen": round(sum(cal_err) / n, 5),
        "folds_where_raw_matches_frozen": exact_raw,
        "folds_where_calibrated_matches_frozen": exact_cal,
        "frozen_tracks": ("raw" if sum(raw_err) < sum(cal_err) else "calibrated"),
    }


def classify(rows: list[dict]) -> dict:
    """Earliest differing stage, with the folds implicated."""
    unmatched = [r["start"] for r in rows if r["frozen"] is None or r["mine"] is None]

    test_diff, cal_diff, const_diff = [], [], []
    for r in rows:
        fz, me = r["frozen"], r["mine"]
        if not fz or not me:
            continue
        if fz["n_test"] != me["n_test_rows"]:
            test_diff.append(r["start"])
        if bool(fz["calibrated"]) != bool(me["calibrated"]):
            cal_diff.append(r["start"])
        if abs(fz["const_logloss"] - me["const_logloss"]) > 5e-5:
            const_diff.append(r["start"])

    # A row-count difference confined to the LAST fold is the two runs having
    # been generated on different days, not a panel-filter disagreement. Calling
    # that DATA_SELECTION would bury the real finding under a known artifact, so
    # it gets its own benign stage and the classification continues past it.
    last_start = rows[-1]["start"] if rows else None
    window_only = bool(test_diff) and test_diff == [last_start]
    interior_test_diff = [] if window_only else test_diff

    if unmatched:
        stage, detail = "FOLD_STRUCTURE", (
            f"{len(unmatched)} fold(s) exist on only one side: {unmatched[:5]}")
    elif interior_test_diff:
        stage, detail = "DATA_SELECTION", (
            f"{len(interior_test_diff)} interior fold(s) differ in test-row count: "
            f"{interior_test_diff[:5]}")
    elif cal_diff:
        stage, detail = "CALIBRATION", (
            f"{len(cal_diff)} fold(s) differ in whether calibration ran: {cal_diff}")
    elif const_diff:
        stage, detail = "BASELINE", (
            f"{len(const_diff)} fold(s) differ in const_logloss on identical rows")
    else:
        stage, detail = "NONE", "no structural difference found"

    return {"earliest_differing_stage": stage, "detail": detail,
            "final_fold_window_difference_only": window_only,
            "folds_with_test_row_diff": test_diff,
            "folds_with_calibration_diff": cal_diff,
            "folds_with_const_diff": const_diff,
            "unmatched_folds": unmatched}


def render(rows, verdict, pooled_mine, pooled_frozen, agree) -> str:
    out = []
    out.append("FOLD-BY-FOLD — reproduced run vs frozen gate report")
    out.append("=" * 118)
    out.append(f"{'window':<24}{'n_test':>14}{'cal':>10}{'n_cal':>8}"
               f"{'LL raw':>9}{'LL cal':>9}{'iso Δ':>8}{'LL frozen':>11}{'const M/F':>18}")
    out.append("-" * 118)
    for r in rows:
        fz, me = r["frozen"], r["mine"]
        win = f"{r['start']}→{r['end']}"
        if me is None:
            out.append(f"{win:<24}{'— missing here —':>60}")
            continue
        if fz is None:
            out.append(f"{win:<24}{me['n_test_rows']:>14}{'—':>10}"
                       f"{me['n_cal_rows']:>8}{me['raw_logloss']:>9}"
                       f"{me['test_logloss']:>9}{me['calibration_gain']:>8}"
                       f"{'— not in frozen —':>29}")
            continue
        ntest = (f"{me['n_test_rows']}" if fz["n_test"] == me["n_test_rows"]
                 else f"{me['n_test_rows']}/{fz['n_test']}*")
        cal = (f"{str(me['calibrated'])[0]}/{str(fz['calibrated'])[0]}"
               + ("*" if bool(me["calibrated"]) != bool(fz["calibrated"]) else ""))
        const = f"{me['const_logloss']}/{fz['const_logloss']}"
        if abs(me["const_logloss"] - fz["const_logloss"]) > 5e-5:
            const += "*"
        out.append(f"{win:<24}{ntest:>14}{cal:>10}{me['n_cal_rows']:>8}"
                   f"{me['raw_logloss']:>9}{me['test_logloss']:>9}"
                   f"{me['calibration_gain']:>8}{fz['model_logloss']:>11}{const:>18}")
    out.append("-" * 118)
    out.append("  * = differs.  cal column is mine/frozen.  iso Δ = raw LL − calibrated LL")
    out.append("    (positive means the isotonic step helped on that fold).")
    out.append("")
    out.append(f"pooled model_logloss   mine {pooled_mine.get('model_logloss')}   "
               f"frozen {pooled_frozen.get('model_logloss')}")
    out.append(f"pooled n_test_rows     mine {pooled_mine.get('n_test_rows')}   "
               f"frozen {pooled_frozen.get('n_test_rows')}")
    out.append(f"calibrated folds       mine {pooled_mine.get('n_calibrated_folds')}   "
               f"frozen {pooled_frozen.get('n_calibrated_folds')}")
    if pooled_mine.get("model_logloss_raw") is not None:
        raw, cal = pooled_mine["model_logloss_raw"], pooled_mine["model_logloss"]
        fz = pooled_frozen.get("model_logloss")
        out.append("")
        out.append("pooled, isotonic bypassed vs applied:")
        out.append(f"  raw        {raw}   |raw − frozen|        {abs(raw - fz):.4f}")
        out.append(f"  calibrated {cal}   |calibrated − frozen| {abs(cal - fz):.4f}")
        out.append(f"  the frozen recipe's isotonic step costs "
                   f"{pooled_mine.get('calibration_gain_pooled')} log loss pooled")
    out.append("")
    if agree.get("comparable_folds"):
        out.append(f"Across the {agree['comparable_folds']} folds scoring identical rows, "
                   f"the frozen log loss tracks our {agree['frozen_tracks'].upper()} series:")
        out.append(f"  mean |raw − frozen|        {agree['mean_abs_diff_raw_vs_frozen']}"
                   f"   (matches to 5e-4 on {len(agree['folds_where_raw_matches_frozen'])} fold(s))")
        out.append(f"  mean |calibrated − frozen| {agree['mean_abs_diff_calibrated_vs_frozen']}"
                   f"   (matches to 5e-4 on {len(agree['folds_where_calibrated_matches_frozen'])} fold(s))")
        out.append("")
    if verdict.get("final_fold_window_difference_only"):
        out.append("Test-row counts differ ONLY in the final fold — the two runs were "
                   "generated on\ndifferent days. Not a panel-filter difference; "
                   "classification continued past it.")
        out.append("")
    out.append(f"EARLIEST DIFFERING STAGE: {verdict['earliest_differing_stage']}")
    out.append(f"  {verdict['detail']}")
    out.append("")
    out.append(INTERPRETATION.get(verdict["earliest_differing_stage"], ""))
    return "\n".join(out)


INTERPRETATION = {
    "FOLD_STRUCTURE":
        "Fold structure differs, so nothing downstream is comparable. Fix the\n"
        "boundaries before reading any other column.",
    "DATA_SELECTION":
        "Row counts differ on matched folds. Check the panel filters and the data\n"
        "window before concluding anything about calibration.",
    "CALIBRATION":
        "Fold structure and row counts agree; the difference is the isotonic step.\n"
        "\n"
        "Check which series the frozen log loss tracks, above. If it tracks RAW,\n"
        "the frozen report measures these same hazards with the isotonic map\n"
        "BYPASSED — so it is not a validation of the live-lock recipe, which\n"
        "applies that map. It validates the same model without its final step.\n"
        "\n"
        "Do NOT tune the isotonic procedure to close the gap. Two separate\n"
        "questions fall out of this, and they are decided by different people:\n"
        "  1. relabel the gate report for what it measures (documentation);\n"
        "  2. whether the live-lock recipe should keep a calibration step that\n"
        "     costs log loss (a model-version decision, with a new\n"
        "     preregistration - never an edit to the frozen recipe).",
    "BASELINE":
        "Only the constant-hazard baseline differs, on identical rows with\n"
        "identical calibration. That is a property of the comparison baseline,\n"
        "not of the model. A single pooled event rate and a per-round constant\n"
        "hazard are both defensible; they are not the same number.",
    "NONE":
        "No structural difference found. If pooled metrics still differ, the\n"
        "cause is inside a fold rather than in its shape.",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True,
                    help="output directory from walkforward_prop0001.py")
    ap.add_argument("--reference", default=HARNESS_REPORT)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    man_path = os.path.join(args.run, "manifest.json")
    if not os.path.isfile(man_path):
        sys.exit(f"no manifest at {man_path} — run walkforward_prop0001.py first")
    if not os.path.isfile(args.reference):
        sys.exit(f"no reference report at {args.reference}")

    mine, frozen = load(man_path), load(args.reference)
    if not mine.get("folds"):
        sys.exit("this manifest has no per-fold detail; re-run the harness")
    if "raw_logloss" not in mine["folds"][0]:
        sys.exit("this manifest predates the raw/calibrated diagnostic; re-run the "
                 "harness to regenerate it")

    rows = pair_folds(frozen["folds"], mine["folds"])
    verdict = classify(rows)
    agree = agreement(rows)

    if args.json:
        print(json.dumps({
            "verdict": verdict,
            "agreement": agree,
            "pooled_reproduced": mine["pooled"],
            "pooled_frozen": frozen["pooled"],
            "folds": [{"start": r["start"], "frozen": r["frozen"], "reproduced": r["mine"]}
                      for r in rows],
        }, indent=2))
    else:
        print(render(rows, verdict, mine["pooled"], frozen["pooled"], agree))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
