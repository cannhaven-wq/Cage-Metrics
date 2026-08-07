"""Point-in-time feature panel for the props output layer (count models).

build_panels() runs one strictly-before-date chronological pass and returns two
frames, so nothing in a fighter's feature vector was measurable only after the
fight it describes. write_artifacts() persists them to features/*.parquet so the
counts harness reads parquet exactly like the duration harness does.

  round panel  -> one row per (fight, round, fighter perspective).
      Response columns: sig_landed, td_landed, td_any, kd.
      Exposure:         round_minutes  (offset = log of this).
      Covariates (all PIT, shrunk):
        own_sig_off_pm   own sig strikes landed / min, career-to-date
        opp_sig_def_pm   opponent's sig strikes ALLOWED / min  (their defense)
        own_td_off_pm    own takedowns / min
        opp_td_def_pm    opponent's takedowns ALLOWED / min
        own_grapp_pm     own grappling activity (td*60 + ctrl_sec) / min
        opp_grapp_pm     opponent grappling activity / min  (style matchup)
        own_decay        own late-round vs round-1 sig rate ratio (<1 = fades)
        round_number     1..5
        own_exp_min / opp_exp_min   prior minutes of tape (sample weight / floor)

  fight frame  -> one row per fight: rounds_sched, rounds_fought, finished (bool),
        + PIT finish-threat covariates (knockdown and submission rates for and
        against both corners). Carries the fight-level context the simulator needs.

CRITICAL covariate discipline (per spec): opponent "defense" rates are strikes /
takedowns ALLOWED per minute, reconstructed here from the fights/rounds data with
shrinkage, point-in-time. The career fighters.td_def / str_def fields are NEVER
used (they don't even exist in fighters.csv, and must not be reintroduced).

Round durations are reconstructed, not stored: rounds before the last are 300s;
the last round fought is fight_seconds - 300*(rounds_fought-1).
"""
from __future__ import annotations

import os
from collections import defaultdict

import numpy as np
import pandas as pd

DATA = os.path.join(os.path.dirname(__file__), os.pardir, "data")
ENGINE_DATA = DATA

ROUND_SECS = 300.0
SHRINK_MIN = 15.0   # pseudo-exposure (minutes) for rate shrinkage ~ one fight
EPS = 1e-9
MIN_YEAR = 2010     # modern-era cutoff (cfl-prop-model rule): EMIT rows for fights
                    # on/after this year; PIT history still accumulates over ALL
                    # fights so veterans are never treated as debutants.


def _load_raw():
    fr = pd.read_csv(os.path.join(DATA, "fight_rounds.csv"))
    fights = pd.read_csv(os.path.join(ENGINE_DATA, "fights.csv"))
    stats = pd.read_csv(os.path.join(ENGINE_DATA, "fight_stats.csv"))
    fighters = pd.read_csv(os.path.join(ENGINE_DATA, "fighters.csv"))

    # fight-level duration (consistent across corners; verified no nulls)
    dur = stats.groupby("fight_id", as_index=False).fight_seconds.max()
    fights = fights.merge(dur, on="fight_id", how="left")

    fights = fights[fights.event_date.notna()].copy()
    fights["event_date"] = pd.to_datetime(fights.event_date)
    # keep only fights we have rounds for
    fr = fr[fr.fight_id.isin(set(fights.fight_id))].copy()
    fights = fights[fights.fight_id.isin(set(fr.fight_id))].copy()
    return fr, fights, fighters


def _round_seconds(round_number, rounds_fought, fight_seconds):
    if round_number < rounds_fought:
        return ROUND_SECS
    last = fight_seconds - ROUND_SECS * (rounds_fought - 1)
    # clamp: decisions land near 300; guard against bad/short fight_seconds
    return float(min(ROUND_SECS, max(10.0, last)))


def _shrunk(x_sum, m_sum, prior, k=SHRINK_MIN):
    """Shrink a per-minute rate toward `prior` with pseudo-exposure k minutes."""
    return (x_sum + prior * k) / (m_sum + k)


def build_panels():
    """Single chronological pass. Returns (round_panel, fight_frame)."""
    fr, fights, _ = _load_raw()

    rounds_fought = fr.groupby("fight_id").round_number.max()
    finfo = fights.set_index("fight_id")

    # explode fight_rounds into per-round dicts keyed by fight for the walk
    fr = fr.sort_values(["fight_id", "round_number"])
    rounds_by_fight = {fid: g for fid, g in fr.groupby("fight_id")}

    # order fights strictly by date; batch by date so same-day fights can't see
    # each other (mirrors engine.py's strictly-before-date rule).
    fights = fights.sort_values(["event_date", "fight_id"])
    dates = fights.event_date.values
    order = fights.fight_id.tolist()

    # ---- accumulators (career-to-date, updated only after each date batch) ----
    def new_acc():
        return dict(min=0.0, sig_off=0.0, sig_def=0.0, td_off=0.0, td_def=0.0,
                    kd_off=0.0, kd_def=0.0, sub_off=0.0, sub_def=0.0, ctrl_off=0.0,
                    min_r1=0.0, sig_r1=0.0, min_late=0.0, sig_late=0.0, nf=0)

    acc = defaultdict(new_acc)
    g = new_acc()  # global pooled

    def g_rate(off_key):
        return (g[off_key] / g["min"]) if g["min"] > 0 else 0.0

    round_rows = []
    fight_rows = []
    pending = []  # (fight_id) accumulated within current date, folded in after

    fights_grouped = fights.groupby("event_date", sort=True)

    for edate, day in fights_grouped:
        # snapshot global priors as-of this date
        pr_sig = g_rate("sig_off")          # avg sig/min (off == def globally)
        pr_td = g_rate("td_off")            # avg td/min
        pr_kd = g_rate("kd_off")
        pr_sub = g_rate("sub_off")
        pr_grapp = ((g["td_off"] * 60.0 + g["ctrl_off"]) / g["min"]) if g["min"] > 0 else 0.0

        # first: emit features for every fight on this date using pre-date acc
        for row in day.itertuples(index=False):
            fid = row.fight_id
            if fid not in rounds_by_fight:
                continue
            a_id, b_id = int(row.fighter_a_id), int(row.fighter_b_id)
            rf = int(rounds_fought[fid])
            fsec = float(row.fight_seconds) if pd.notna(row.fight_seconds) else ROUND_SECS * rf
            sched = int(row.n_rounds_sched) if pd.notna(row.n_rounds_sched) else 3
            if edate.year < MIN_YEAR:        # fold into history but do not emit
                pending.append(fid)
                continue
            finished = _is_finish(row.method, rf, sched)

            def feats(fid_self, fid_opp):
                s, o = acc[fid_self], acc[fid_opp]
                own_sig_off = _shrunk(s["sig_off"], s["min"], pr_sig)
                opp_sig_def = _shrunk(o["sig_def"], o["min"], pr_sig)
                own_td_off = _shrunk(s["td_off"], s["min"], pr_td)
                opp_td_def = _shrunk(o["td_def"], o["min"], pr_td)
                own_grapp = _shrunk(s["td_off"] * 60.0 + s["ctrl_off"], s["min"], pr_grapp)
                opp_grapp = _shrunk(o["td_off"] * 60.0 + o["ctrl_off"], o["min"], pr_grapp)
                early = _shrunk(s["sig_r1"], s["min_r1"], pr_sig)
                late = _shrunk(s["sig_late"], s["min_late"], pr_sig)
                decay = late / (early + EPS)
                return dict(own_sig_off_pm=own_sig_off, opp_sig_def_pm=opp_sig_def,
                            own_td_off_pm=own_td_off, opp_td_def_pm=opp_td_def,
                            own_grapp_pm=own_grapp, opp_grapp_pm=opp_grapp,
                            own_decay=decay, own_exp_min=s["min"], opp_exp_min=o["min"])

            fa, fb = feats(a_id, b_id), feats(b_id, a_id)
            grp = rounds_by_fight[fid]
            for rr in grp.itertuples(index=False):
                rn = int(rr.round_number)
                if rn > rf:
                    continue
                rmin = _round_seconds(rn, rf, fsec) / 60.0
                # corner A perspective
                round_rows.append({
                    "fight_id": fid, "event_date": edate, "round_number": rn,
                    "fighter_id": a_id, "opp_id": b_id, "corner": "a",
                    "round_minutes": rmin, "rounds_sched": sched,
                    "is_finish_round": int(rn == rf and finished),
                    "sig_landed": _num(rr.a_sig_landed), "td_landed": _num(rr.a_td_landed),
                    "kd": _num(rr.a_kd), **fa})
                # corner B perspective
                round_rows.append({
                    "fight_id": fid, "event_date": edate, "round_number": rn,
                    "fighter_id": b_id, "opp_id": a_id, "corner": "b",
                    "round_minutes": rmin, "rounds_sched": sched,
                    "is_finish_round": int(rn == rf and finished),
                    "sig_landed": _num(rr.b_sig_landed), "td_landed": _num(rr.b_td_landed),
                    "kd": _num(rr.b_kd), **fb})

            # fight-level row for the duration model
            fight_rows.append({
                "fight_id": fid, "event_date": edate,
                "rounds_sched": sched, "rounds_fought": rf,
                "finished": int(finished),
                "a_kd_off": _shrunk(acc[a_id]["kd_off"], acc[a_id]["min"], pr_kd),
                "b_kd_off": _shrunk(acc[b_id]["kd_off"], acc[b_id]["min"], pr_kd),
                "a_kd_def": _shrunk(acc[a_id]["kd_def"], acc[a_id]["min"], pr_kd),
                "b_kd_def": _shrunk(acc[b_id]["kd_def"], acc[b_id]["min"], pr_kd),
                "a_sub_off": _shrunk(acc[a_id]["sub_off"], acc[a_id]["min"], pr_sub),
                "b_sub_off": _shrunk(acc[b_id]["sub_off"], acc[b_id]["min"], pr_sub),
                "a_sub_def": _shrunk(acc[a_id]["sub_def"], acc[a_id]["min"], pr_sub),
                "b_sub_def": _shrunk(acc[b_id]["sub_def"], acc[b_id]["min"], pr_sub),
                "exp_min": min(acc[a_id]["min"], acc[b_id]["min"]),
            })
            pending.append(fid)

        # then: fold this date's fights into the accumulators (strictly-after)
        for fid in pending:
            row = finfo.loc[fid]
            a_id, b_id = int(row.fighter_a_id), int(row.fighter_b_id)
            rf = int(rounds_fought[fid])
            fsec = float(row.fight_seconds) if pd.notna(row.fight_seconds) else ROUND_SECS * rf
            grp = rounds_by_fight[fid]
            for rr in grp.itertuples(index=False):
                rn = int(rr.round_number)
                if rn > rf:
                    continue
                rmin = _round_seconds(rn, rf, fsec) / 60.0
                _fold(acc[a_id], g, rmin, rn,
                      _num(rr.a_sig_landed), _num(rr.b_sig_landed),
                      _num(rr.a_td_landed), _num(rr.b_td_landed),
                      _num(rr.a_kd), _num(rr.b_kd),
                      _num(rr.a_sub_att), _num(rr.b_sub_att), _num(rr.a_ctrl))
                _fold(acc[b_id], g, rmin, rn,
                      _num(rr.b_sig_landed), _num(rr.a_sig_landed),
                      _num(rr.b_td_landed), _num(rr.a_td_landed),
                      _num(rr.b_kd), _num(rr.a_kd),
                      _num(rr.b_sub_att), _num(rr.a_sub_att), _num(rr.b_ctrl))
            acc[a_id]["nf"] += 1
            acc[b_id]["nf"] += 1
        pending.clear()

    panel = pd.DataFrame(round_rows)
    fight_frame = pd.DataFrame(fight_rows)
    panel["td_any"] = (panel["td_landed"] > 0).astype(int)
    return panel, fight_frame


def _fold(a, g, rmin, rn, sig_off, sig_def, td_off, td_def, kd_off, kd_def,
          sub_off, sub_def, ctrl_off):
    for tgt in (a, g):
        tgt["min"] += rmin
        tgt["sig_off"] += sig_off; tgt["sig_def"] += sig_def
        tgt["td_off"] += td_off;   tgt["td_def"] += td_def
        tgt["kd_off"] += kd_off;   tgt["kd_def"] += kd_def
        tgt["sub_off"] += sub_off; tgt["sub_def"] += sub_def
        tgt["ctrl_off"] += ctrl_off
        if rn == 1:
            tgt["min_r1"] += rmin; tgt["sig_r1"] += sig_off
        if rn >= 3:
            tgt["min_late"] += rmin; tgt["sig_late"] += sig_off


def _num(v):
    return 0.0 if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)


def _is_finish(method, rounds_fought, rounds_sched):
    """Finish = fight ended before the scheduled distance (KO/TKO/SUB)."""
    if method is None or (isinstance(method, float) and np.isnan(method)):
        method = ""
    m = str(method).lower()
    if m.startswith(("ko", "tko", "sub")) or "knockout" in m or "submission" in m:
        return 1
    if m.startswith("dec") or "decision" in m:
        return 0
    # fall back on time: fewer rounds than scheduled => finish
    return int(int(rounds_fought) < int(rounds_sched))


COUNT_COV_COLS = ["own_sig_off_pm", "opp_sig_def_pm", "own_td_off_pm",
                  "opp_td_def_pm", "own_grapp_pm", "opp_grapp_pm", "own_decay",
                  "own_exp_min", "opp_exp_min"]


def write_artifacts(outdir=None):
    """Build the panels and persist count_features.parquet + count_manifest.json.

    The round panel is the count-model training grain (one row per fighter-round);
    the fight frame carries the duration finish-threat covariates. Both are written
    so the counts harness reads parquet exactly like the duration harness does.
    """
    import json
    from datetime import datetime
    outdir = outdir or os.path.dirname(__file__)
    panel, ff = build_panels()
    ppath = os.path.join(outdir, "count_features.parquet")
    fpath = os.path.join(outdir, "count_fight_frame.parquet")
    panel.to_parquet(ppath, index=False)
    ff.to_parquet(fpath, index=False)

    manifest = {
        "generated_at_utc": datetime.utcnow().isoformat() + "Z",
        "source": "cfl_engine/data CSVs: fight_rounds, fights, fight_stats, fighters",
        "round_grain": "one row per (fight, round, fighter perspective)",
        "responses": {"sig_landed": "NB2 target", "td_landed": "hurdle target",
                      "td_any": "hurdle stage-1 target"},
        "offset": "log(round_minutes)  (5:00 rounds; finish round = leftover seconds)",
        "min_year_emitted": MIN_YEAR,
        "point_in_time": ("all rate covariates use only fights strictly before "
                          "event_date, batched by date; shrunk toward the "
                          "expanding league mean (pseudo-exposure "
                          f"{SHRINK_MIN} minutes). History accumulates over ALL "
                          f"fights; only rows on/after {MIN_YEAR} are emitted."),
        "covariate_discipline": ("opponent 'def' rates are strikes/TDs ALLOWED per "
                                 "minute rebuilt from fight_rounds; career "
                                 "str_def/td_def fields are never used"),
        "count_covariate_columns": COUNT_COV_COLS,
        "n_round_rows": int(len(panel)), "n_fights": int(ff.fight_id.nunique()),
        "sig_mean": float(panel.sig_landed.mean()),
        "sig_var": float(panel.sig_landed.var()),
        "td_any_rate": float(panel.td_any.mean()),
        "finish_rate": float(ff.finished.mean()),
        "date_range": [str(panel.event_date.min().date()),
                       str(panel.event_date.max().date())],
    }
    with open(os.path.join(outdir, "count_manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, default=str)
    print(f"wrote {len(panel)} round rows -> {ppath}")
    print(f"wrote {len(ff)} fight rows -> {fpath}")
    print(f"  sig mean/var {manifest['sig_mean']:.1f}/{manifest['sig_var']:.1f}  "
          f"td_any {manifest['td_any_rate']:.3f}  finish {manifest['finish_rate']:.3f}")
    return panel, ff


if __name__ == "__main__":
    write_artifacts()
