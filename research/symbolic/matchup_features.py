"""SYM-003 matchup feature builder (rules: config_sym003.json, frozen 9bf99be2).

Reads private/data/fights.csv and the SYM-002 features.parquet (point-in-time,
corners already randomised). Writes private/data/matchup.parquet with one row per
fight: W1..W3, S1..S3, O1..O6, each antisymmetric f(A,B) - f(B,A).

Point-in-time rules
  * Every per-fighter rate for a fight on date D uses bouts strictly before D
    (merge_asof with allow_exact_matches=False).
  * Opponent-adjusted residuals compare a historical bout's actual numbers with
    the opponent's rates GOING INTO that bout (that bout's own features row),
    never the opponent's later career.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from features import DATA, HERE, fight_seconds, outcome

CFG3 = json.load(open(os.path.join(HERE, "config_sym003.json")))
K_MIN = 25.0
HALF_LIFE = 730.0
O_PSEUDO_MIN = 15.0
RESID = ["r_str_off", "r_str_def", "r_td_off", "r_td_def", "r_ctrl_off", "r_ctrl_def"]


def long_bouts():
    f = pd.read_csv(os.path.join(DATA, "fights.csv"), parse_dates=["event_date"])
    f["res"] = [outcome(r) for r in f.itertuples(index=False)]
    f["secs"] = [fight_seconds(r, t) for r, t in zip(f.end_round, f.end_time)]
    f = f[f.res != "none"]
    stat_cols = ["a_sig_l", "a_sig_a", "a_td_l", "a_ctrl", "a_kd", "b_sig_l", "b_sig_a", "b_td_l", "b_ctrl", "b_kd"]
    f["has_stats"] = f[stat_cols].notna().all(axis=1) & (f.secs > 0)
    rows = []
    for me, op in (("a", "b"), ("b", "a")):
        d = pd.DataFrame({
            "fight_id": f.fight_id, "date": f.event_date, "fid": f[f"fighter_{me}_id"], "opp": f[f"fighter_{op}_id"],
            "has_stats": f.has_stats, "mins": f.secs / 60.0,
            "own_sig_l": f[f"{me}_sig_l"], "own_sig_a": f[f"{me}_sig_a"], "own_td_l": f[f"{me}_td_l"],
            "own_ctrl": f[f"{me}_ctrl"], "own_kd": f[f"{me}_kd"],
            "opp_sig_l": f[f"{op}_sig_l"], "opp_td_l": f[f"{op}_td_l"], "opp_ctrl": f[f"{op}_ctrl"], "opp_kd": f[f"{op}_kd"],
        })
        rows.append(d)
    return pd.concat(rows, ignore_index=True).sort_values(["date", "fight_id"]).reset_index(drop=True)


def league_by_date(L):
    """League rates over stat bouts strictly before each date (fighter-bout level)."""
    s = L[L.has_stats]
    g = s.groupby("date").agg(mins=("mins", "sum"), sig_l=("own_sig_l", "sum"), sig_a=("own_sig_a", "sum"),
                              td_l=("own_td_l", "sum"), ctrl=("own_ctrl", "sum"), kd=("own_kd", "sum")).sort_index()
    c = g.cumsum().shift(1)          # strictly before the date
    out = pd.DataFrame({"L_slpm": c.sig_l / c.mins, "L_acc": c.sig_l / c.sig_a, "L_td15": 15 * c.td_l / c.mins,
                        "L_ctrl": c.ctrl / 60.0 / c.mins, "L_kd15": 15 * c.kd / c.mins}).reset_index()
    return out


def conceded_rates(L, lg, query):
    """tdag15 / kdag15 for each (fid, date) in `query`, from bouts strictly before that date."""
    s = L[L.has_stats].groupby(["fid", "date"]).agg(mins=("mins", "sum"), opp_td=("opp_td_l", "sum"),
                                                     opp_kd=("opp_kd", "sum")).reset_index()
    s = s.sort_values("date")
    s[["c_mins", "c_td", "c_kd"]] = s.groupby("fid")[["mins", "opp_td", "opp_kd"]].cumsum()
    q = query.sort_values("date").copy()
    q = pd.merge_asof(q, s[["fid", "date", "c_mins", "c_td", "c_kd"]].sort_values("date"), on="date", by="fid",
                      allow_exact_matches=False)
    q = pd.merge_asof(q.sort_values("date"), lg.sort_values("date"), on="date")
    q[["c_mins", "c_td", "c_kd"]] = q[["c_mins", "c_td", "c_kd"]].fillna(0.0)
    q["tdag15"] = 15 * (q.c_td + K_MIN * q.L_td15 / 15) / (q.c_mins + K_MIN)
    q["kdag15"] = 15 * (q.c_kd + K_MIN * q.L_kd15 / 15) / (q.c_mins + K_MIN)
    return q[["fid", "date", "tdag15", "kdag15"]]


def build():
    F = pd.read_parquet(os.path.join(DATA, "features.parquet"))
    L = long_bouts()
    lg = league_by_date(L)

    # ---- per-fighter pre-fight conceded rates for every fight row (both corners)
    q = pd.concat([F[["a_id", "event_date"]].set_axis(["fid", "date"], axis=1),
                   F[["b_id", "event_date"]].set_axis(["fid", "date"], axis=1)]).drop_duplicates()
    conc = conceded_rates(L, lg, q).drop_duplicates(["fid", "date"])
    F = F.merge(lg.rename(columns={"date": "event_date"}), on="event_date", how="left")
    for s in ("a", "b"):
        F = F.merge(conc.rename(columns={"fid": f"{s}_id", "date": "event_date", "tdag15": f"{s}_tdag15",
                                         "kdag15": f"{s}_kdag15"}), on=[f"{s}_id", "event_date"], how="left")
    # league values are NaN only for the very first date in the table; harmless (no eligible rows there)

    # ---- W and S: natural-scale cross products, antisymmetric
    def x(sa, sb, f):          # helper: (A value, B value)
        return F[f"{sa}_{f}"], F[f"{sb}_{f}"]
    out = pd.DataFrame({"fight_id": F.fight_id})
    out["W1"] = (F.a_td_per15 * F.b_tdag15 - F.b_td_per15 * F.a_tdag15) / F.L_td15
    out["W2"] = (F.a_ctrl_share * F.b_ctrl_against - F.b_ctrl_share * F.a_ctrl_against) / F.L_ctrl
    out["W3"] = F.a_td_acc * (1 - F.b_td_def) - F.b_td_acc * (1 - F.a_td_def)
    out["S1"] = (F.a_slpm * F.b_sapm - F.b_slpm * F.a_sapm) / F.L_slpm
    out["S2"] = (F.a_str_acc * (1 - F.b_str_def) - F.b_str_acc * (1 - F.a_str_def)) / F.L_acc
    out["S3"] = (F.a_kd_per15 * F.b_kdag15 - F.b_kd_per15 * F.a_kdag15) / F.L_kd15

    # ---- O: opponent-adjusted residuals per historical bout
    # opponent's pre-bout rates come from that bout's own feature row (point in time)
    side_cols = ["slpm", "sapm", "td_per15", "ctrl_share", "ctrl_against"]
    pre = pd.concat([
        F[["fight_id", "a_id", "event_date"] + [f"a_{c}" for c in side_cols] + ["a_tdag15"]].set_axis(
            ["fight_id", "fid", "date"] + side_cols + ["tdag15"], axis=1),
        F[["fight_id", "b_id", "event_date"] + [f"b_{c}" for c in side_cols] + ["b_tdag15"]].set_axis(
            ["fight_id", "fid", "date"] + side_cols + ["tdag15"], axis=1)])
    B = L[L.has_stats].merge(pre.rename(columns={"fid": "opp", **{c: f"opp_pre_{c}" for c in side_cols + ['tdag15']}})
                             .drop(columns="date"), on=["fight_id", "opp"], how="left")
    m = B.mins
    B["r_str_off"] = B.own_sig_l / m - B.opp_pre_sapm
    B["r_str_def"] = B.opp_pre_slpm - B.opp_sig_l / m
    B["r_td_off"] = 15 * B.own_td_l / m - B.opp_pre_tdag15
    B["r_td_def"] = B.opp_pre_td_per15 - 15 * B.opp_td_l / m
    B["r_ctrl_off"] = B.own_ctrl / 60.0 / m - B.opp_pre_ctrl_against
    B["r_ctrl_def"] = B.opp_pre_ctrl_share - B.opp_ctrl / 60.0 / m
    n_missing_pre = int(B[RESID].isna().any(axis=1).sum())
    B = B.dropna(subset=RESID)
    hist = {fid: (g.date.to_numpy(), g.mins.to_numpy(), g[RESID].to_numpy()) for fid, g in B.groupby("fid")}

    def o_vec(fid, date):
        if fid not in hist:
            return np.zeros(len(RESID))
        d, mins, R = hist[fid]
        keep = d < np.datetime64(date)
        if not keep.any():
            return np.zeros(len(RESID))
        age = (np.datetime64(date) - d[keep]).astype("timedelta64[D]").astype(float)
        w = mins[keep] * 0.5 ** (age / HALF_LIFE)
        return (w[:, None] * R[keep]).sum(0) / (w.sum() + O_PSEUDO_MIN)

    oa = np.array([o_vec(i, d) for i, d in zip(F.a_id, F.event_date)])
    ob = np.array([o_vec(i, d) for i, d in zip(F.b_id, F.event_date)])
    for k in range(len(RESID)):
        out[f"O{k + 1}"] = oa[:, k] - ob[:, k]
        out[f"a_O_{RESID[k]}"] = oa[:, k]
        out[f"b_O_{RESID[k]}"] = ob[:, k]

    new = [f"W{i}" for i in (1, 2, 3)] + [f"S{i}" for i in (1, 2, 3)] + [f"O{i}" for i in range(1, 7)]
    elig = F.eligible_fighters.to_numpy()
    nan_counts = {c: int(out.loc[elig, c].isna().sum()) for c in new}
    out[new] = out[new].fillna(0.0)
    out.to_parquet(os.path.join(DATA, "matchup.parquet"), index=False)
    info = {"rows": len(out), "nan_on_eligible_rows_before_fill": nan_counts,
            "historical_bouts_dropped_for_missing_opponent_pre_rates": n_missing_pre,
            "historical_bouts_used_for_O": int(len(B))}
    print(json.dumps(info, indent=1))
    return out, info


if __name__ == "__main__":
    build()
