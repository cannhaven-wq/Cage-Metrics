"""Readable summary, per-fight out-of-sample file, and the symmetry check.

The summary leads with a plain verdict (CLAUDE.md), states what failed at the
same prominence as what passed, and carries no betting-return figure: the
historical BFO consensus was never a price anyone could bet (PRED-001 s5).
"""
from __future__ import annotations

import hashlib
import pathlib

import numpy as np
import pandas as pd

import pred_protocol as pp
from . import model as M


def symmetry_report(wf, cands, cids, n_rows: int = 300) -> dict:
    """PRED-001's symmetry_violations() on the last confirmation fold's fitted
    model for each listed candidate: p(A beats B) + p(B beats A) must be 1."""
    by = {c.cid: c for c in cands}
    out = {}
    yr, tr, te = wf.folds["confirm"][-1]
    for cid in cids:
        c = by[cid]
        cols = wf.columns(c)
        tf = wf.transformer(c, {n: v[tr] for n, v in cols.items()})
        th = M.fit_offset_logistic(tf({n: v[tr] for n, v in cols.items()}), wf.off[tr], wf.y[tr],
                                   wf.cfg["ridge_multi" if c.kind == "multi" else "ridge_single"])
        anti = set(c.terms) | {a for a, _ in c.interact}

        def predict(row, c=c, tf=tf, th=th):
            R = {n: np.array([row[n]], dtype=float) for n in cols}
            return float(M.predict_offset_logistic(th, tf(R), np.array([M.logit(row["q"])]))[0])

        def swap(row, anti=anti):
            s = {k: (-v if k in anti else v) for k, v in row.items()}
            s["q"] = 1.0 - row["q"]
            return s

        rows = [dict({n: float(cols[n][i]) for n in cols}, q=float(wf.q[i])) for i in te[:n_rows]]
        bad = pp.symmetry_violations(predict, rows, swap)
        out[cid] = {"rows_checked": len(rows), "violations": len(bad)}
    return {"fold_year": int(yr), "by_candidate": out,
            "passed": all(v["violations"] == 0 for v in out.values())}


def write_oos(path: pathlib.Path, wf, preds_s, preds_c, cids) -> str:
    frames = []
    for st, P in (("screen", preds_s), ("confirm", preds_c)):
        idx = wf.test_idx[st]
        d = pd.DataFrame({"fight_id": wf.S.fight_id.to_numpy()[idx], "event_id": wf.event[idx],
                          "year": wf.year[idx], "stage": st, "y": wf.y[idx].astype(int),
                          "q_market": np.round(wf.q[idx], 6),
                          "p_recalibrated_market": np.round(P["__recal__"]["p"], 6)})
        for cid in cids:
            d[f"p[{cid}]"] = np.round(P[cid]["p"], 6)
        frames.append(d)
    pd.concat(frames).to_csv(path, index=False)
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def _f(x, nd=4, signed=True):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:+.{nd}f}" if signed else f"{x:.{nd}f}"


def _ci(r, key="ci95_vs_reference"):
    ci = r.get(key)
    return f"{_f(ci[0])} to {_f(ci[1])}" if ci and ci[0] is not None else "—"


def summary_md(o: dict) -> str:
    m, C, tc = o["meta"], o["candidates"], o["tier_counts"]
    fam = [c for c in C.values() if c["family_member"]]
    sl = o["shortlist"]
    leads = [cid for cid in o["ranking"] if C[cid]["tier"] == "RESEARCH_LEAD"]
    small = [cid for cid in o["ranking"] if C[cid]["tier"] == "BELOW_USEFUL_EFFECT"]
    L = []
    L.append(f"# Discovery run `{m['run_id']}`\n")
    L.append(f"**Data: {m['mode']}.** "
             + ("Clearly labelled SYNTHETIC fixture: no real fight is in it, and nothing here describes real "
                "UFC fights." if m["mode"] == "synthetic" else
                f"PRED-001 DEV partition only ({m['data']['scorable']:,} priced fights with a result; latest "
                f"event {m['data']['max_event_date']}). Fingerprints match the frozen manifest: "
                f"{m['data']['manifest_check'].get('match')}.")
             + " Exploratory result: under PRED-001 section 9 it supports no statement outside the research folder.\n")

    L.append("## Plain verdict\n")
    if leads:
        verdict = (f"{len(leads)} of {len(fam)} tested ideas held up well enough to deserve a proper, "
                   f"preregistered test. None is a proven edge.")
    elif small:
        verdict = (f"Nothing beat the betting market by a useful amount. {len(small)} idea(s) held up but "
                   f"are too small to matter.")
    elif sl:
        verdict = (f"Nothing held up. {len(sl)} idea(s) looked promising on 2010-2018 and did not survive "
                   f"2019-2024.")
    else:
        verdict = "Nothing held up. No idea passed the first screen after correcting for how many were tried."
    L.append(verdict + "\n")
    L.append(f"- Tested: **{len(fam)}** ideas ({sum(1 for c in fam if c['kind']=='single')} single factors, "
             f"{sum(1 for c in fam if c['kind']=='interaction')} factor-by-situation interactions), every one "
             f"recorded with its result in `results.json`.")
    L.append(f"- Passed the first screen ({o['config']['screen_years'][0]}-{o['config']['screen_years'][-1]}, "
             f"false-discovery rate held at {o['config']['fdr_q']}, split evenly between singles and "
             f"interactions): **{len(sl)}**.")
    for t, n in tc.items():
        L.append(f"- {t}: {n}")
    ctrl = o["controls"]
    if ctrl.get("n_controls"):
        L.append(f"- Noise controls (fake factors made of random numbers): {ctrl['n_controls']} run; "
                 f"{ctrl['raw_p_below_0_05']} looked 'significant' before correction, "
                 f"{ctrl['would_pass_bh_if_in_family']} would have passed the corrected screen.")
    L.append("")

    L.append("## The market we are trying to beat\n")
    L.append("| period | fights | cards | market log loss | after recalibrating the market | recalibration gain | market picks right |")
    L.append("|---|---|---|---|---|---|---|")
    for st, b in o["baselines"].items():
        L.append(f"| {st} {b['years'][0]}-{b['years'][-1]} | {b['n']:,} | {b['n_events']} | {b['ll_market']:.4f} | "
                 f"{b['ll_recalibrated_market']:.4f} | {_f(b['recalibration_gain'])} | {b['accuracy_market']:.1%} |")
    L.append("\nLower log loss is better. 'Recalibrating' only re-weights the market's own number; a "
             "factor gets credit only for what it adds beyond that.\n")

    def row(cid, stage):
        r = C[cid][stage]
        flag = " (H1-contaminated: non-confirmatory)" if C[cid].get("h1_contaminated") else ""
        return (f"| `{cid}`{flag} | {r['n_informative']:,} | {_f(r['delta_vs_reference'])} | {_ci(r)} | "
                f"{_f(r['delta_vs_recalibrated'])} | {_f(r['delta_vs_market'])} | "
                f"{r.get('frac_years_positive', 0) or 0:.0%} |")

    hdr = ("| candidate | fights where it says something | gain vs its reference | 95% range (by card) | "
           "gain vs re-weighted market (size test) | gain vs raw market | years positive |\n"
           "|---|---|---|---|---|---|---|")
    for title, tier in (("Research leads", "RESEARCH_LEAD"), ("Held up, but too small to matter", "BELOW_USEFUL_EFFECT"),
                        ("Unstable", "UNSTABLE"), ("Failed confirmation (2019-2024)", "FAILED_CONFIRMATION")):
        ids = [cid for cid in o["ranking"] if C[cid]["tier"] == tier]
        L.append(f"## {title}: {len(ids)}\n")
        if ids:
            L.append("Confirmation-period numbers (2019-2024), each fitted only on earlier years.\n")
            L.append(hdr)
            for cid in ids:
                L.append(row(cid, "confirm"))
            L.append("")
            for cid in ids:
                L.append(f"- `{cid}`: {C[cid]['hypothesis']}")
                ev = C[cid].get("evidence_needed")
                if ev:
                    L.append(f"  - To confirm prospectively at its measured size: about "
                             f"{ev['prospective_fights_required']:,} forecast-in-advance fights "
                             f"(~{ev['years_at_prospective_rate']} years). H1 could only detect "
                             f"{ev['h1_detectable_effect']:.3f}.")
            L.append("")

    top_rej = [cid for cid in o["ranking"] if C[cid]["tier"] == "REJECTED_SCREEN"][:12]
    L.append(f"## Closest misses at the screen (of {tc.get('REJECTED_SCREEN', 0)} rejected)\n")
    L.append("Shown so near-misses are visible, not to rescue them. Screening-period numbers (2010-2018).\n")
    L.append("| candidate | gain vs its reference | 95% range | p (one-sided) | FDR q-value (within its kind) | permutation family-wise p |")
    L.append("|---|---|---|---|---|---|")
    for cid in top_rej:
        r = C[cid]["screen"]
        L.append(f"| `{cid}` | {_f(r['delta_vs_reference'])} | {_ci(r)} | {_f(r['p_one_sided'], 4, False)} | "
                 f"{_f(r.get('bh_q_value'), 3, False)} | {_f(r.get('perm_fwer_p'), 3, False)} |")
    L.append("")

    L.append("## Everything at once, and no market at all (context, not tested)\n")
    L.append("| model | screen gain vs market | confirm gain vs market | confirm 95% range |")
    L.append("|---|---|---|---|")
    for cid, c in C.items():
        if c["kind"] in ("multi", "standalone"):
            L.append(f"| `{cid}` | {_f(c['screen']['delta_vs_market'])} | {_f(c['confirm']['delta_vs_market'])} | "
                     f"{_ci(c['confirm'], 'ci95_vs_market')} |")
    L.append("")

    a = o["audits"]
    L.append("## Leakage and integrity checks\n")
    L.append(f"- Feature sources against PRED-001's forbidden list: "
             f"{'clean' if not a['manifest_problems'] else a['manifest_problems']}.")
    L.append(f"- Corner-label readers: {'none' if not a['corner_readers'] else a['corner_readers']}.")
    if "pit" in a:
        p = a["pit"]
        L.append(f"- Point-in-time recompute ({p['dates_checked']} random cards, {p['fights_checked']} fights, "
                 f"{p['features_checked']} features, card's own results scrambled): "
                 f"{'passed' if p['passed'] else 'FAILED on ' + ', '.join(p['failed_features'])}.")
    s = a["swap"]
    L.append(f"- Corner-swap rebuild: {'passed' if s['passed'] else 'FAILED on ' + ', '.join(s['failed_features'])}.")
    L.append(f"- Fitted-model symmetry (PRED-001 checker): {'passed' if o['symmetry']['passed'] else 'FAILED'}.")
    d = a["detector_self_check"]
    L.append(f"- Leak detector self-check (a planted leak must trip it): "
             f"{'works' if d['detector_works'] else 'BROKEN'} (planted leak scored "
             f"{_f(d['planted_leak_delta_vs_market'])} vs market).")
    pn = o["permutation_null"]
    if pn.get("permutations"):
        L.append(f"- Permutation null ({pn['permutations']} shuffles): the best of {len(fam)} pure-chance "
                 f"ideas typically reaches z = {pn['max_z_null_quantiles']['0.5']:.2f} "
                 f"(95th percentile {pn['max_z_null_quantiles']['0.95']:.2f}); the best real idea reached "
                 f"{pn['observed_max_z']:.2f}.")
    L.append("")
    L.append("## What this run cannot tell you\n")
    L.append("- The market here is BestFightOdds' historical closing consensus. It has no time stamp and "
             "was never a price anyone could bet. No betting return is computed, and none should be inferred.")
    L.append("- Every year used is before 2025. The sealed 2025-26 holdout was not read and not spent.")
    L.append("- A research lead licenses a written PRED-001 preregistration and nothing else. It is not an "
             "approved model and must not appear on any public page (D-011).")
    L.append("")
    return "\n".join(L) + "\n"
