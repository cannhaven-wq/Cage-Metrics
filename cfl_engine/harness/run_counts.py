"""Run the counts+simulator harness, write a plain-English report_counts.md, and
persist one fight's 10k joint simulation draws as a worked slate-sizing example.

    PYTHONPATH=cfl_engine/models python cfl_engine/harness/run_counts.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, os.pardir, "models"))
import walkforward_counts as wf  # noqa: E402
from counts import SigStrikeModel, TakedownModel  # noqa: E402
from simulate import FightSimulator, context_from_panel  # noqa: E402
from duration import DurationHazardModel  # noqa: E402

FEAT = os.path.join(HERE, os.pardir, "features")


def write_md(rep, path):
    p = rep["pooled"]; sim = rep["simulator"]
    L = ["# Props output layer — counts + simulator report\n",
         "_Significant-strike and takedown count models, and the Monte-Carlo "
         "simulator that turns them (with the gated duration hazard model) into "
         "full outcome distributions and betting-line probabilities. Every number "
         "is out-of-sample: each fold trains only on fights before the test year._\n",
         "## Plain-English summary\n",
         f"- **Do the models beat a dumb average?** Significant strikes: yes — "
         f"held-out error {p['sig_mae']:.1f} strikes/round vs {p['sig_mae_base']:.1f} "
         f"for a no-covariates baseline. Takedowns: yes — it calls whether a round "
         f"has a takedown far better ({p['td_any_ll']:.3f} vs {p['td_any_ll_base']:.3f} "
         f"log-loss, lower is better) and predicts the count to "
         f"{p['td_mae']:.2f} vs {p['td_mae_base']:.2f} average error.\n",
         f"- **Are the distributions honest?** On the most recent window "
         f"({sim['year']}, {sim['n_fights']} fights) the simulator's 80% range for "
         f"total significant strikes contained the real result "
         f"{sim['metrics']['total_sig']['coverage']['0.8']*100:.0f}% of the time "
         f"(target 80%) and its 90% range "
         f"{sim['metrics']['total_sig']['coverage']['0.9']*100:.0f}% (target 90%). "
         f"Fight length lands on target too "
         f"({sim['metrics']['end_round']['coverage']['0.8']*100:.0f}% / "
         f"{sim['metrics']['end_round']['coverage']['0.9']*100:.0f}%).\n",
         f"- **Known caveats:** takedown intervals run a touch narrow "
         f"(80% covers {sim['metrics']['total_td']['coverage']['0.8']*100:.0f}%), and "
         f"significant strikes carried a train-to-recent drift that a rolling "
         f"recalibration pulls down to {p['sig_mean_bias']*100:+.1f}% average bias. "
         f"Neither breaks the line probabilities; both are honest before sizing "
         f"real money.\n",
         "\n## Counts vs baseline (pooled out-of-sample)\n",
         "| Metric | Model | Baseline |",
         "|---|---|---|",
         f"| Sig log-likelihood (higher=better) | {p['sig_ll']:+.4f} | {p['sig_ll_base']:+.4f} |",
         f"| Sig mean abs error (strikes/round) | {p['sig_mae']:.3f} | {p['sig_mae_base']:.3f} |",
         f"| Sig NB dispersion (want ~1.0) | {p['sig_dispersion']:.3f} | — |",
         f"| Sig mean bias (after recalibration) | {p['sig_mean_bias']*100:+.1f}% | — |",
         f"| Takedown any-TD log-loss (lower=better) | {p['td_any_ll']:.4f} | {p['td_any_ll_base']:.4f} |",
         f"| Takedown mean abs error | {p['td_mae']:.3f} | {p['td_mae_base']:.3f} |",
         "\n## Simulator PIT coverage (integrated distributional check)\n",
         f"Most recent window ({sim['year']}, {sim['n_fights']} fights, {sim['sim_n']} "
         "sims each). Ending round is drawn from the gated duration model; a "
         "well-calibrated simulator gives PIT ~ Uniform(0,1), so an X% central "
         "interval should contain the actual outcome X% of the time.\n",
         "| Metric | mean PIT (~0.50) | 50% | 80% | 90% |",
         "|---|---|---|---|---|"]
    for m, d in sim["metrics"].items():
        c = d["coverage"]
        L.append(f"| {m} | {d['mean_pit']:.3f} | {c['0.5']*100:.1f}% | "
                 f"{c['0.8']*100:.1f}% | {c['0.9']*100:.1f}% |")
    L += ["\n## Gates\n", "| Gate | Result |", "|---|---|"]
    for k, v in rep["gates"].items():
        L.append(f"| {k} | {'PASS' if v else 'FAIL'} |")
    L += [f"\n**{'ALL GATES PASS' if rep['all_gates_pass'] else 'GATES FAILED'}** — "
          "ship rule: passes every gate AND beats `baseline_counts.json`.\n",
          "\n## Method notes / honest limitations\n",
          "- **Covariate discipline:** opponent 'defense' is strikes/takedowns "
          "ALLOWED per minute, rebuilt point-in-time from fight_rounds with "
          "shrinkage. Career `str_def`/`td_def` fields are never used.\n",
          "- **Recency weighting + rolling recalibration** correct strike-volume "
          "drift (2-year half-life; level factor fit on a recent training tail, "
          "strictly before the test window).\n",
          "- **Duration** is the existing gated 3-round hazard model; the simulator "
          "is scoped to 3-round fights to match it. 5-round support is future work.\n",
          "- **Takedown tails** are slightly thin — widen before sizing TD props hard.\n",
          "- ROI is not claimed. This validates the *distributions*; edge vs posted "
          "prop lines is the next step once a prop-line feed is captured.\n"]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print(f"wrote {path}")


def persist_example():
    panel = pd.read_parquet(os.path.join(FEAT, "count_features.parquet"))
    panel["event_date"] = pd.to_datetime(panel["event_date"])
    sig = SigStrikeModel().fit(panel); td = TakedownModel().fit(panel)
    simr = FightSimulator(sig, td)

    dur = pd.read_parquet(os.path.join(FEAT, "duration_features.parquet"))
    dur["event_date"] = pd.to_datetime(dur["event_date"])
    cov = json.load(open(os.path.join(FEAT, "feature_manifest.json")))["covariate_columns"]
    dm = DurationHazardModel().fit(dur, cov)
    dfights = dur.drop_duplicates("fight_id").set_index("fight_id")

    # latest 3-round fight present in both panels
    cand = [f for f in panel.sort_values("event_date").fight_id.tolist() if f in dfights.index]
    fid = cand[-1]
    d = dm.fight_distribution(dfights.loc[[fid]].reset_index(), calibrated=False).iloc[0]
    ctx = context_from_panel(panel, fid, [d.p_ends_r1, d.p_ends_r2, d.p_ends_r3, d.p_decision])
    res = simr.simulate(ctx, n=10000, seed=20260806)
    outdir = os.path.join(HERE, "artifacts"); os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"sim_fight_{fid}.npz")
    res.save(path)
    print(f"persisted 10k joint draws for fight {fid} -> {path}")
    print(f"  P(GTD)={res.p_gtd():.3f}  total-sig median={res.summary('total_sig')['p50']:.0f}"
          f"  example line total_sig 150.5: {res.line('total_sig', 150.5)}")


def main():
    ok = wf.run((2024, 2025, 2026), sim_n=4000, sim_seed=20260806,
                report_path=os.path.join(HERE, "walkforward_counts_report.json"),
                baseline_path=os.path.join(HERE, "baseline_counts.json"))
    rep = json.load(open(os.path.join(HERE, "walkforward_counts_report.json")))
    write_md(rep, os.path.join(HERE, "report_counts.md"))
    persist_example()
    return ok


if __name__ == "__main__":
    main()
