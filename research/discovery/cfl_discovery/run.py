"""Run the Phase 1 discovery pipeline end to end.

    python -m cfl_discovery.run --data dev        # the committed DEV export
    python -m cfl_discovery.run --data synthetic  # labelled synthetic fixture

(from research/discovery/). Every real-data run is appended to the ledger;
nothing is ever overwritten. See research/discovery/README.md.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import pathlib
import subprocess
import time

import numpy as np
import pandas as pd

import pred_protocol as pp
from . import DISCOVERY_DIR, REPO, __version__
from . import candidates as C
from . import data as D
from . import evaluate as E
from . import features as F
from . import leakage as L
from . import ledger as LG
from . import report as R
from . import synthetic as SY

CONFIG = DISCOVERY_DIR / "config" / "phase1.json"
PRED001_KEYS = {"minimum_useful_effect": "minimum_useful_effect",
                "leak_delta": "leak_tripwire_delta_ll",
                "leak_accuracy_lift": "leak_tripwire_accuracy_lift"}

TIER_ORDER = ["RESEARCH_LEAD", "BELOW_USEFUL_EFFECT", "UNSTABLE", "FAILED_CONFIRMATION",
              "REJECTED_SCREEN", "INSUFFICIENT_SAMPLE", "LEAK_SUSPECT"]
TIER_PLAIN = {
    "RESEARCH_LEAD": "passed screening and confirmation, held up across years and de-vig methods, and "
                     "beat the market by at least the minimum useful amount. Worth a preregistered PRED-001 test; "
                     "proves nothing yet.",
    "BELOW_USEFUL_EFFECT": "survived every test, but its gain over the market is smaller than the 0.003 "
                           "PRED-001 treats as worth having.",
    "UNSTABLE": "confirmed on average, but the gain flips sign across years or de-vig methods.",
    "FAILED_CONFIRMATION": "looked promising in 2010-2018 and did not hold up in 2019-2024.",
    "REJECTED_SCREEN": "no evidence it adds anything beyond the market after correcting for how many "
                       "things were tried.",
    "INSUFFICIENT_SAMPLE": "too few fights where the feature says anything to judge.",
    "LEAK_SUSPECT": "too good to be true, or failed a leakage audit. Treated as a bug, never as a finding.",
}


def file_sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def code_sha() -> dict:
    files = sorted((DISCOVERY_DIR / "cfl_discovery").glob("*.py"))
    files += [REPO / "cfl_engine" / "engine.py", REPO / "research" / "protocol" / "pred_protocol.py",
              REPO / "cfl_engine" / "clv" / "devig.py"]
    return {str(p.relative_to(REPO)): file_sha(p) for p in files}


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short=12", "HEAD"], cwd=REPO,
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return "unknown"


def load_config(path: pathlib.Path = CONFIG, overrides: dict | None = None) -> dict:
    cfg = json.loads(pathlib.Path(path).read_text())
    cfg.update(overrides or {})
    for k, pk in PRED001_KEYS.items():
        if cfg[k] != pp.T[pk]:
            raise ValueError(f"config {k}={cfg[k]} disagrees with frozen PRED-001 {pk}={pp.T[pk]}; "
                             f"a discovery run may not loosen a protocol threshold")
    if max(cfg["confirm_years"]) >= pp.DEV_END.year or max(cfg["screen_years"]) >= pp.DEV_END.year:
        raise ValueError("a test year falls outside DEV")
    return cfg


def _json_default(o):
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, float) and not np.isfinite(o):
        return None
    raise TypeError(type(o))


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float) and not np.isfinite(o):
        return None
    if isinstance(o, np.floating):
        return None if not np.isfinite(o) else float(o)
    return o


def write_json(path: pathlib.Path, obj) -> str:
    path.write_text(json.dumps(_clean(obj), indent=1, sort_keys=False, default=_json_default) + "\n")
    return file_sha(path)


def detector_self_check(wf: E.WalkForward, cfg: dict) -> dict:
    """Plant a leaked feature (the fight's own result, lightly blurred) and
    confirm the 'too good' tripwire fires on it. A detector that cannot catch
    a planted leak is reported as broken, and the run says so."""
    rng = np.random.default_rng(1)
    S = wf.S.copy()
    S["__planted_leak__"] = (2 * S.y - 1) * 0.8 + rng.normal(0, 1.0, len(S))
    cand = C.Candidate("SELF:planted_leak", "single", ["__planted_leak__"], family_member=False)
    rec_p = wf.oos(None, "screen", S)["p"]
    o = wf.oos(cand, "screen", S)
    rec = E.stage_record(wf, cand, "screen", o["p"], o["coefs"], rec_p, "recalibrated market",
                         rec_p, cfg, boot=0, seed=0, S=S)
    return {"planted_leak_delta_vs_market": rec["delta_vs_market"], "tripwires": rec["tripwires"],
            "detector_works": bool(rec["tripwires"])}


def run(data: str = "dev", cfg_overrides: dict | None = None, out_root: pathlib.Path | None = None,
        ledger_path: pathlib.Path | None = None, synthetic_kwargs: dict | None = None,
        label: str = "", verbose: bool = True) -> dict:
    t0 = time.time()
    cfg = load_config(overrides=cfg_overrides)
    log = (lambda *a: print(f"[{time.time() - t0:7.1f}s]", *a, flush=True)) if verbose else (lambda *a: None)

    # ---------------------------------------------------------------- data
    if data == "dev":
        dev = D.load_dev()
        mode = "real-dev"
    elif data == "synthetic":
        dev = SY.make(**(synthetic_kwargs or {}))
        mode = "synthetic"
    else:
        raise ValueError(data)
    fights, stats, fighters = D.prepare(dev)
    builder = lambda f, s, x: F.build(f, s, x, noise_controls=cfg["noise_controls"], seed=cfg["noise_seed"])
    table, specs = builder(fights, stats, fighters)
    log(f"data {mode}: {len(table)} fights, {int(table.is_scorable.sum())} scorable, {len(specs)} features")

    cands = C.build_catalog(specs, cfg)
    family = [c for c in cands if c.family_member]
    run_id = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + (f"-{label}" if label else "") \
        + ("-synthetic" if mode == "synthetic" else "")
    out_root = pathlib.Path(out_root) if out_root else DISCOVERY_DIR / "runs"
    out = out_root / run_id
    out.mkdir(parents=True, exist_ok=False)
    files = {}
    files["config.json"] = write_json(out / "config.json", cfg)
    files["catalog.json"] = write_json(out / "catalog.json", [c.as_dict() for c in cands])
    files["feature_manifest.json"] = write_json(out / "feature_manifest.json", [s.as_dict() for s in specs])
    log(f"catalog: {len(cands)} candidates, {len(family)} in the tested family")

    # ---------------------------------------------------------------- leakage audits
    audits = {"manifest_problems": L.manifest_check(specs),
              "corner_readers": L.corner_readers(table, specs)}
    if cfg["pit_audit_dates"]:
        audits["pit"] = L.pit_audit(dev, table, specs, builder, cfg["pit_audit_dates"], cfg["pit_audit_seed"])
        log(f"PIT audit: {audits['pit']['fights_checked']} fights, passed={audits['pit']['passed']}")
    audits["swap"] = L.swap_audit(dev, table, specs, builder)
    log(f"corner-swap audit passed={audits['swap']['passed']}")
    leaky = set(audits.get("pit", {}).get("failed_features", [])) | set(audits["swap"]["failed_features"])
    leaky |= {p.split(":")[0] for p in audits["manifest_problems"] + audits["corner_readers"]}

    wf = E.WalkForward(table, cfg)
    audits["detector_self_check"] = detector_self_check(wf, cfg)

    # ---------------------------------------------------------------- stage 1: screen
    preds_s = E.screen_family(wf, cands, "screen")
    log("screen predictions done")
    recal_s = preds_s["__recal__"]["p"]
    results = {c.cid: {"cid": c.cid, "kind": c.kind, "terms": c.terms,
                       "interact": [list(p) for p in c.interact], "parent": c.parent,
                       "family_member": c.family_member, "hypothesis": c.hypothesis,
                       "families": c.families} for c in cands}
    idx_s = wf.test_idx["screen"]
    for i, c in enumerate(cands):
        ref = preds_s[c.parent]["p"] if c.parent else (recal_s if c.kind != "standalone" else wf.q[idx_s])
        ref_name = f"parent {c.parent}" if c.parent else ("market" if c.kind == "standalone"
                                                         else "recalibrated market")
        results[c.cid]["screen"] = E.stage_record(
            wf, c, "screen", preds_s[c.cid]["p"], preds_s[c.cid]["coefs"], ref, ref_name, recal_s, cfg,
            boot=cfg["bootstrap_screen"], seed=cfg["bootstrap_seed"])
    log("screen records done")

    # multiple testing over the tested family only
    # The FDR budget is split across the two kinds before anything is scored
    # (config fdr_split): 616-odd interactions must not drown 44 singles, and
    # the split keeps the overall false-discovery rate at fdr_q.
    fam_p = np.array([results[c.cid]["screen"]["p_one_sided"] for c in family], dtype=float)
    for kind, share in cfg["fdr_split"].items():
        sub = [c for c in family if c.kind == kind]
        if not sub:
            continue
        p_sub = np.array([results[c.cid]["screen"]["p_one_sided"] for c in sub], dtype=float)
        q_sub = cfg["fdr_q"] * share
        bh = E.benjamini_hochberg(p_sub, q_sub)
        bh_adj = E.bh_adjusted(p_sub)
        hm = E.holm(p_sub, cfg["screen_holm_alpha"] * share)
        for c, b, ba, h in zip(sub, bh, bh_adj, hm):
            r = results[c.cid]["screen"]
            r["bh_pass"], r["bh_q_value"], r["holm_pass"] = bool(b), float(ba), bool(h)
            r["fdr_family"], r["fdr_q_family"] = kind, q_sub

    # permutation max-statistic null over the whole family
    perm = {"permutations": cfg["permutations"]}
    if cfg["permutations"]:
        rng = np.random.default_rng(cfg["permutation_seed"])
        cols = sorted({t for c in family for t in c.terms} | {x for c in family for _, x in c.interact})
        obs_z = E.family_z(wf, family, preds_s, "screen")
        maxes = []
        for b in range(cfg["permutations"]):
            Sp = E.permute_within_year(wf, cols, rng)
            pp_ = E.screen_family(wf, family, "screen", S=Sp, cache={})
            maxes.append(float(np.max(E.family_z(wf, family, pp_, "screen"))))
            if verbose and (b + 1) % 10 == 0:
                log(f"permutation {b + 1}/{cfg['permutations']}")
        maxes = np.array(maxes)
        for c, z in zip(family, obs_z):
            results[c.cid]["screen"]["perm_fwer_p"] = float((1 + np.sum(maxes >= z)) / (1 + len(maxes)))
        perm.update({"max_z_null_quantiles": {str(q): float(np.quantile(maxes, q)) for q in (0.5, 0.9, 0.95, 0.99)},
                     "observed_max_z": float(np.max(obs_z))})

    # ---------------------------------------------------------------- shortlist (fixed before confirmation)
    def eligible(c):
        r = results[c.cid]["screen"]
        return (r["n_informative"] >= cfg["min_informative_screen"] and r["n_events"] >= cfg["min_events"])

    def touches_leak(c):
        return bool(set(c.terms) & leaky) or any(a in leaky or x in leaky for a, x in c.interact)

    pool = [c for c in family if results[c.cid]["screen"]["bh_pass"] and eligible(c)
            and not results[c.cid]["screen"]["tripwires"] and not touches_leak(c)
            and results[c.cid]["screen"]["delta_vs_reference"] > 0]
    pool.sort(key=lambda c: -results[c.cid]["screen"]["z_vs_reference"])
    shortlist = [c.cid for c in pool[: cfg["max_shortlist"]]]
    sl_obj = {"shortlist": shortlist, "fixed_before_confirmation": True,
              "rule": f"BH at q={cfg['fdr_q']} split {cfg['fdr_split']} on the screen, delta>0, minimum sample, no tripwire, "
                      f"no failed audit; top {cfg['max_shortlist']} by z"}
    files["shortlist.json"] = write_json(out / "shortlist.json", sl_obj)
    log(f"shortlist: {len(shortlist)} candidates (sha {files['shortlist.json'][:12]})")

    # ---------------------------------------------------------------- stage 2: confirm
    preds_c = E.screen_family(wf, cands, "confirm")
    recal_c = preds_c["__recal__"]["p"]
    idx_c = wf.test_idx["confirm"]
    for c in cands:
        ref = preds_c[c.parent]["p"] if c.parent else (recal_c if c.kind != "standalone" else wf.q[idx_c])
        ref_name = f"parent {c.parent}" if c.parent else ("market" if c.kind == "standalone"
                                                         else "recalibrated market")
        results[c.cid]["confirm"] = E.stage_record(
            wf, c, "confirm", preds_c[c.cid]["p"], preds_c[c.cid]["coefs"], ref, ref_name, recal_c, cfg,
            boot=cfg["bootstrap_confirm"] if (c.cid in shortlist or not c.family_member) else cfg["bootstrap_screen"],
            seed=cfg["bootstrap_seed"])
    sl_p = np.array([results[c]["confirm"]["p_one_sided"] for c in shortlist], dtype=float)
    sl_holm = E.holm(sl_p, cfg["confirm_alpha"]) if len(shortlist) else np.array([], bool)
    for cid, h in zip(shortlist, sl_holm):
        results[cid]["confirm"]["holm_pass_over_shortlist"] = bool(h)
    log("confirm records done")

    # recalibrated market itself, for the record
    baselines = {}
    for st, rp in (("screen", recal_s), ("confirm", recal_c)):
        idx = wf.test_idx[st]
        y, q = wf.y[idx], wf.q[idx]
        baselines[st] = {"n": int(len(idx)), "n_events": int(len(np.unique(wf.event[idx]))),
                         "years": wf.stages[st],
                         "ll_market": float(pp.log_loss_each(y, q).mean()),
                         "ll_recalibrated_market": float(pp.log_loss_each(y, rp).mean()),
                         "recalibration_gain": float((pp.log_loss_each(y, q) - pp.log_loss_each(y, rp)).mean()),
                         "accuracy_market": float(np.mean((q > 0.5) == (y == 1))),
                         "market_calibration": dict(zip(("intercept", "slope"), pp.calibration_fit(y, q)))}

    # ---------------------------------------------------------------- sensitivity + symmetry on the shortlist
    sens = {}
    for qcol in cfg["devig_sensitivities"]:
        w2 = wf.with_q(qcol)
        if not np.all(np.isfinite(w2.q)):
            sens[qcol] = {"skipped": "de-vig undefined on some fights"}
            continue
        rc = w2.oos(None, "confirm")["p"]
        for cid in shortlist:
            c = next(x for x in cands if x.cid == cid)
            o = w2.oos(c, "confirm")
            y = w2.y[idx_c]
            d = pp.log_loss_each(y, w2.q[idx_c]) - pp.log_loss_each(y, o["p"])
            results[cid]["confirm"].setdefault("devig_sensitivity_delta_vs_market", {})[qcol] = round(float(d.mean()), 6)
    for cid in shortlist:
        y = wf.y[idx_c]
        a, b = pp.calibration_fit(y, preds_c[cid]["p"])
        results[cid]["confirm"]["calibration"] = {"intercept": round(a, 4), "slope": round(b, 4)}

    # ---------------------------------------------------------------- tiers
    mue = cfg["minimum_useful_effect"]
    for c in cands:
        r = results[c.cid]
        s, k = r["screen"], r["confirm"]
        notes = []
        if not c.family_member:
            tier = {"control": "CONTROL", "multi": "CONTEXT_MODEL", "standalone": "CONTEXT_MODEL"}[c.kind]
            if s["tripwires"] or k["tripwires"]:
                notes.append("tripwire fired")
            r["tier"], r["notes"] = tier, notes
            continue
        if s["tripwires"] or k["tripwires"] or touches_leak(c):
            tier = "LEAK_SUSPECT"
            notes += s["tripwires"] + k["tripwires"] + (["uses a feature that failed a leakage audit"]
                                                         if touches_leak(c) else [])
        elif not eligible(c):
            tier = "INSUFFICIENT_SAMPLE"
        elif c.cid not in shortlist:
            tier = "REJECTED_SCREEN"
        elif not (k.get("holm_pass_over_shortlist") and k["ci95_vs_reference"][0] > 0
                  and k["n_informative"] >= cfg["min_informative_confirm"]):
            tier = "FAILED_CONFIRMATION"
        else:
            years = list(s["per_year_delta_vs_reference"].values()) + list(k["per_year_delta_vs_reference"].values())
            frac = float(np.mean(np.array(years) > 0))
            sens_ok = all(v > 0 for v in k.get("devig_sensitivity_delta_vs_market", {}).values())
            agree = min(x for x in (s["key_coef_sign_agreement"], k["key_coef_sign_agreement"]) if x is not None)
            same_sign = np.sign(s["key_coef_median"] or 0) == np.sign(k["key_coef_median"] or 0)
            r["stability"] = {"frac_years_positive_all": round(frac, 4), "devig_sensitivity_ok": sens_ok,
                              "min_sign_agreement": agree, "coef_sign_same_both_stages": bool(same_sign)}
            if (frac < cfg["stability_min_frac_years_positive"] or agree < cfg["stability_min_sign_agreement"]
                    or not same_sign):
                tier = "UNSTABLE"
            elif k["delta_vs_market"] < mue or not sens_ok:
                tier = "BELOW_USEFUL_EFFECT" if sens_ok else "UNSTABLE"
            else:
                tier = "RESEARCH_LEAD"
        r["tier"], r["notes"] = tier, notes

    # evidence still needed, for anything that got past the screen
    for cid in shortlist:
        k = results[cid]["confirm"]
        sd = max(pp.T["sd_floor_incremental"], k["sd_delta_vs_market"] or 0)
        target = max(pp.T["min_target_effect"], k["delta_vs_market"])
        n_req = pp.required_n(sd, target, pp.T["alpha_prospective_per_evaluation"], pp.T["power"],
                              mue=pp.T["minimum_useful_effect"])
        results[cid]["evidence_needed"] = {
            "sd_used": round(sd, 4), "target_effect": round(target, 4),
            "prospective_fights_required": n_req,
            "years_at_prospective_rate": round(n_req / cfg["prospective_fights_per_year"], 1),
            "h1_detectable_effect": round(pp.detectable_effect(sd, pp.MANIFEST["partitions"]["H1"]["decided_priced"],
                                                               pp.T["alpha_h1_per_evaluation"], pp.T["power"]), 4),
        }

    # control false-discovery check: would any noise candidate have passed the screen gate?
    ctrl = [c for c in cands if c.kind == "control"]
    if ctrl:
        # each control joins the family of its own kind, as if it were real
        bh_with = []
        for kind, share in cfg["fdr_split"].items():
            sub_c = [c for c in ctrl if (c.kind == "control") and ((kind == "interaction") == bool(c.interact))]
            p_real = [results[c.cid]["screen"]["p_one_sided"] for c in family if c.kind == kind]
            p_ctrl = [results[c.cid]["screen"]["p_one_sided"] for c in sub_c]
            if p_ctrl:
                bh_with += list(E.benjamini_hochberg(np.array(p_real + p_ctrl, float),
                                                     cfg["fdr_q"] * share)[len(p_real):])
        ctrl_summary = {
            "n_controls": len(ctrl),
            "raw_p_below_0_05": int(sum(results[c.cid]["screen"]["p_one_sided"] < 0.05 for c in ctrl)),
            "would_pass_bh_if_in_family": int(np.sum(bh_with)),
            "controls_confirm_delta_positive": int(sum(results[c.cid]["confirm"]["delta_vs_reference"] > 0
                                                       for c in ctrl)),
        }
    else:
        ctrl_summary = {"n_controls": 0}

    # symmetry: PRED-001's own checker on the final fitted fold of each shortlisted model
    sym = R.symmetry_report(wf, cands, shortlist + [c.cid for c in cands if c.kind == "multi"])

    ranking = sorted(
        [c.cid for c in family],
        key=lambda cid: (TIER_ORDER.index(results[cid]["tier"]),
                         -(results[cid]["confirm"].get("ci95_vs_reference", [-9])[0]
                           if cid in shortlist else results[cid]["screen"]["z_vs_reference"] or -9)))
    tiers = {t: sum(1 for c in family if results[c.cid]["tier"] == t) for t in TIER_ORDER}

    meta = {
        "run_id": run_id, "mode": mode, "engine_version": __version__, "git_commit": git_commit(),
        "utc_started": run_id[:16], "seconds": round(time.time() - t0, 1),
        "protocol": "PRED-001 (frozen), DEV partition only; exploratory - section 9 allows no claim outside the research folder",
        "data": {"sha256": dev.sha256, "manifest_check": dev.manifest_check,
                 "fights": int(len(table)), "scorable": int(table.is_scorable.sum()),
                 "max_event_date": str(table.event_date.max().date())},
        "config_sha256": files["config.json"], "catalog_sha256": C.catalog_sha256(cands),
        "code_sha256": code_sha(), "n_candidates": len(cands), "n_family": len(family),
        "shortlist_sha256": files["shortlist.json"],
    }
    out_obj = {"meta": meta, "config": cfg, "tier_counts": tiers, "tier_meaning": TIER_PLAIN, "baselines": baselines,
               "audits": audits, "permutation_null": perm, "controls": ctrl_summary, "symmetry": sym,
               "shortlist": shortlist, "ranking": ranking, "candidates": results}
    files["results.json"] = write_json(out / "results.json", out_obj)
    files["oos_predictions.csv"] = R.write_oos(out / "oos_predictions.csv", wf, preds_s, preds_c,
                                               shortlist + [c.cid for c in cands if c.kind in ("multi", "standalone")])
    (out / "SUMMARY.md").write_text(R.summary_md(out_obj))
    files["SUMMARY.md"] = file_sha(out / "SUMMARY.md")

    entry = {"run_id": run_id, "mode": mode, "git_commit": meta["git_commit"],
             "config_id": cfg["config_id"], "config_sha256": meta["config_sha256"],
             "catalog_sha256": meta["catalog_sha256"], "data_sha256": dev.sha256,
             "code_sha256": hashlib.sha256(json.dumps(meta["code_sha256"], sort_keys=True).encode()).hexdigest(),
             "n_candidates": len(cands), "n_family": len(family), "shortlist": shortlist,
             "tier_counts": tiers,
             "files": {str((out / k).relative_to(DISCOVERY_DIR if ledger_path is None else out_root.parent))
                       : v for k, v in files.items()}}
    lp = ledger_path or (DISCOVERY_DIR / "ledger.jsonl")
    entry = LG.append(lp, entry)
    log(f"done: {out} (ledger seq {entry['seq']})")
    return {"out": out, "results": out_obj, "ledger_entry": entry}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", choices=["dev", "synthetic"], default="dev")
    ap.add_argument("--label", default="")
    ap.add_argument("--permutations", type=int, default=None)
    ap.add_argument("--pit-dates", type=int, default=None)
    ap.add_argument("--planted-reach", type=float, default=0.22, help="synthetic only")
    a = ap.parse_args(argv)
    ov = {}
    if a.permutations is not None:
        ov["permutations"] = a.permutations
    if a.pit_dates is not None:
        ov["pit_audit_dates"] = a.pit_dates
    sk = {"planted_reach": a.planted_reach} if a.data == "synthetic" else None
    run(a.data, cfg_overrides=ov, synthetic_kwargs=sk, label=a.label)


if __name__ == "__main__":
    main()
