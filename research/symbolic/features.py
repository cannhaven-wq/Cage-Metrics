"""SYM-002 point-in-time feature builder.

Every per-fighter number for a fight on date D is computed from that fighter's
bouts with event_date < D only. Updates are applied per event date, so a result
from earlier the same night never reaches a later bout that night (same rule as
cfl_engine/engine.py::compute_elo).

Career averages on the `fighters` table (slpm, sapm, str_def, current age ...)
are NOT used: they include the very fights being predicted. They are attached
only under a `leaky_` prefix so the audit can measure the leak.

Input  : private/data/{fights,fighters_static,fighters_career_LEAKY,market_*}.csv
Output : private/data/features.parquet (one row per fight, corners randomised)
"""
from __future__ import annotations

import json
import os
from collections import defaultdict

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "private", "data")
CFG = json.load(open(os.path.join(HERE, "config.json")))

NC_METHODS = ("overturned", "could not continue", "other", "no contest")
FEATS = CFG["features_per_fighter"]
SH = CFG["shrinkage"]
K_MIN = SH["rate_pseudo_minutes"]
K_STR, K_TD = SH["accuracy_pseudo_attempts"]["str"], SH["accuracy_pseudo_attempts"]["td"]
K_PROP = SH["proportion_pseudo_fights"]
ELO_K, ELO_START = CFG["elo"]["K"], CFG["elo"]["start"]


def fight_seconds(end_round, end_time) -> float:
    try:
        m, s = str(end_time).split(":")
        return (int(end_round) - 1) * 300.0 + int(m) * 60.0 + int(s)
    except (ValueError, TypeError):
        return np.nan


def outcome(row) -> str:
    """'a' / 'b' / 'draw' / 'nc' / 'none' (not yet fought or unusable)."""
    meth = str(row.method or "").strip().lower()
    if row.is_upcoming == 1 or not meth or meth == "nan":
        return "none"
    if any(meth.startswith(x) for x in NC_METHODS):
        return "nc"
    if pd.notna(row.winner_id):
        if row.winner_id == row.fighter_a_id:
            return "a"
        if row.winner_id == row.fighter_b_id:
            return "b"
        return "none"
    return "draw" if meth.startswith("decision") else "nc"


class League:
    """Expanding league totals over bouts strictly before the current date."""

    def __init__(self):
        self.t = defaultdict(float)

    def add(self, own, opp, secs, won_finish, decided):
        t = self.t
        t["sig_l"] += own["sig_l"]; t["sig_a"] += own["sig_a"]
        t["td_l"] += own["td_l"]; t["td_a"] += own["td_a"]
        t["ctrl"] += own["ctrl"]; t["kd"] += own["kd"]; t["sub"] += own["sub"]
        t["secs"] += secs; t["n"] += 1
        t["fin"] += won_finish; t["dec"] += decided

    def rate(self, k, per="secs"):
        d = self.t[per]
        return self.t[k] / d if d > 0 else np.nan


def build() -> pd.DataFrame:
    fights = pd.read_csv(os.path.join(DATA, "fights.csv"), parse_dates=["event_date"])
    stat = pd.read_csv(os.path.join(DATA, "fighters_static.csv"), parse_dates=["dob"]).set_index("fighter_id")
    fights["res"] = [outcome(r) for r in fights.itertuples(index=False)]
    fights["secs"] = [fight_seconds(r, t) for r, t in zip(fights.end_round, fights.end_time)]
    fights = fights.sort_values(["event_date", "fight_id"]).reset_index(drop=True)

    elo = defaultdict(lambda: float(ELO_START))
    hist = defaultdict(list)         # fighter -> list of bout dicts (strictly prior)
    league = League()
    out = []

    for date, day in fights.groupby("event_date", sort=True):
        # ---- 1. features for every bout on this date, from prior history only
        lg = dict(slpm=league.rate("sig_l"), acc=league.rate("sig_l", "sig_a"),
                  td=league.rate("td_l"), tdacc=league.rate("td_l", "td_a"),
                  ctrl=league.rate("ctrl"), kd=league.rate("kd"), sub=league.rate("sub"),
                  fin=league.rate("fin", "n"))
        for r in day.itertuples(index=False):
            row = dict(fight_id=r.fight_id, event_id=r.event_id, event_date=date, res=r.res,
                       is_title=r.is_title, weight_class=r.weight_class, sched_rounds=r.sched_rounds)
            for side, fid in (("a", r.fighter_a_id), ("b", r.fighter_b_id)):
                row[f"{side}_id"] = fid
                f = fighter_features(fid, date, hist[fid], elo, stat, lg)
                for k, v in f.items():
                    row[f"{side}_{k}"] = v
            out.append(row)

        # ---- 2. only now fold this date's results into history / Elo / league
        pending = []
        for r in day.itertuples(index=False):
            if r.res == "none":
                continue
            a = dict(sig_l=r.a_sig_l, sig_a=r.a_sig_a, td_l=r.a_td_l, td_a=r.a_td_a,
                     ctrl=r.a_ctrl, kd=r.a_kd, sub=r.a_sub)
            b = dict(sig_l=r.b_sig_l, sig_a=r.b_sig_a, td_l=r.b_td_l, td_a=r.b_td_a,
                     ctrl=r.b_ctrl, kd=r.b_kd, sub=r.b_sub)
            has_stats = all(pd.notna(v) for v in list(a.values()) + list(b.values())) and pd.notna(r.secs) and r.secs > 0
            finish = not str(r.method).lower().startswith("decision")
            ra, rb = elo[r.fighter_a_id], elo[r.fighter_b_id]
            for me, opp, own, oth, opp_elo, mine in ((r.fighter_a_id, r.fighter_b_id, a, b, rb, "a"),
                                                       (r.fighter_b_id, r.fighter_a_id, b, a, ra, "b")):
                won = r.res == mine
                hist[me].append(dict(date=date, own=own, opp=oth, secs=r.secs, stats=has_stats,
                                     won=won, lost=r.res in ("a", "b") and not won,
                                     won_finish=won and finish, opp_elo=opp_elo))
                if has_stats:
                    league.add(own, oth, r.secs, float(won and finish), float(r.res in ("a", "b")))
            if r.res in ("a", "b", "draw"):
                sa = {"a": 1.0, "b": 0.0, "draw": 0.5}[r.res]
                ea = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
                pending += [(r.fighter_a_id, ELO_K * (sa - ea)), (r.fighter_b_id, -ELO_K * (sa - ea))]
        for fid, d in pending:
            elo[fid] += d

    df = pd.DataFrame(out)
    return randomise_and_attach(df)


def fighter_features(fid, date, h, elo, stat, lg) -> dict:
    o = {k: np.nan for k in FEATS}
    s = stat.loc[fid] if fid in stat.index else None
    if s is not None:
        o["age_yrs"] = (date - s.dob).days / 365.25 if pd.notna(s.dob) else np.nan
        o["reach_in"] = s.reach_in
        o["height_in"] = s.height_in
        o["southpaw"] = 1.0 if str(s.stance) == "Southpaw" else 0.0
    o["elo"] = elo[fid]
    n = len(h)
    o["n_prior"] = n
    o["log_n_fights"] = np.log1p(n)
    o["fights_24m"] = sum((date - x["date"]).days <= 730 for x in h)
    o["log_days_since_last"] = np.log1p((date - h[-1]["date"]).days) if n else np.nan
    o["opp_elo_mean"] = float(np.mean([x["opp_elo"] for x in h])) if n else np.nan
    w = sum(x["won"] for x in h)
    o["win_rate"] = (w + 1.0) / (n + 2.0)
    o["finish_rate"] = (sum(x["won_finish"] for x in h) + K_PROP * (lg["fin"] if np.isfinite(lg["fin"]) else 0.3)) / (n + K_PROP)
    last3 = h[-3:]
    o["last3_win_rate"] = (sum(x["won"] for x in last3) + 1.0) / (len(last3) + 2.0)

    hs = [x for x in h if x["stats"]]
    o["n_stats"] = len(hs)
    mins = sum(x["secs"] for x in hs) / 60.0
    tot = lambda who, k: float(sum(x[who][k] for x in hs))
    rate = lambda num, prior: (num + K_MIN * prior) / (mins + K_MIN)       # per minute, shrunk
    o["slpm"] = rate(tot("own", "sig_l"), lg["slpm"] * 60)
    o["sapm"] = rate(tot("opp", "sig_l"), lg["slpm"] * 60)
    o["str_acc"] = (tot("own", "sig_l") + K_STR * lg["acc"]) / (tot("own", "sig_a") + K_STR)
    o["str_def"] = 1.0 - (tot("opp", "sig_l") + K_STR * lg["acc"]) / (tot("opp", "sig_a") + K_STR)
    o["td_per15"] = 15 * rate(tot("own", "td_l"), lg["td"] * 60)
    o["td_acc"] = (tot("own", "td_l") + K_TD * lg["tdacc"]) / (tot("own", "td_a") + K_TD)
    o["td_def"] = 1.0 - (tot("opp", "td_l") + K_TD * lg["tdacc"]) / (tot("opp", "td_a") + K_TD)
    o["ctrl_share"] = rate(tot("own", "ctrl") / 60.0, lg["ctrl"])          # ctrl-minutes per minute
    o["ctrl_against"] = rate(tot("opp", "ctrl") / 60.0, lg["ctrl"])
    o["kd_per15"] = 15 * rate(tot("own", "kd"), lg["kd"] * 60)
    o["sub_per15"] = 15 * rate(tot("own", "sub"), lg["sub"] * 60)
    return o


def randomise_and_attach(df: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(CFG["data"]["corner_randomisation_seed"])
    flip = rng.random(len(df)) < 0.5
    a_cols = [c for c in df.columns if c.startswith("a_")]
    for ac in a_cols:
        bc = "b_" + ac[2:]
        av, bv = df[ac].copy(), df[bc].copy()
        df.loc[flip, ac], df.loc[flip, bc] = bv[flip], av[flip]
    df["res"] = np.where(flip & (df.res == "a"), "B", np.where(flip & (df.res == "b"), "A", df.res))
    df["res"] = df.res.str.lower()
    df["corner_flipped"] = flip
    df["y"] = np.where(df.res == "a", 1.0, np.where(df.res == "b", 0.0, np.nan))

    m = pd.read_csv(os.path.join(DATA, "market_archived.csv"))
    v = pd.read_csv(os.path.join(DATA, "market_verified.csv"))
    df = df.merge(m[["fight_id", "p_a_archived", "n_books", "ts_kind"]], on="fight_id", how="left")
    df = df.merge(v[["fight_id", "p_a_verified", "mins_before_start"]], on="fight_id", how="left")
    for c in ("p_a_archived", "p_a_verified"):     # market file is in the ORIGINAL corner order
        df[c] = np.where(df.corner_flipped, 1.0 - df[c], df[c])

    leak = pd.read_csv(os.path.join(DATA, "fighters_career_LEAKY.csv")).set_index("fighter_id")
    for side in ("a", "b"):
        for k in ("age_now", "sapm", "slpm", "str_def", "td_avg"):
            df[f"{side}_leaky_{k}"] = df[f"{side}_id"].map(leak[k])

    df["eligible_fighters"] = (df.y.notna() & (df.a_n_stats >= 2) & (df.b_n_stats >= 2)
                               & df.a_age_yrs.notna() & df.b_age_yrs.notna())
    df["eligible_eval"] = df.eligible_fighters & df.p_a_archived.between(0.01, 0.99)
    return df


if __name__ == "__main__":
    d = build()
    d.to_parquet(os.path.join(DATA, "features.parquet"), index=False)
    y = d.event_date.dt.year
    print("rows", len(d), "eligible_fighters", int(d.eligible_fighters.sum()), "eligible_eval", int(d.eligible_eval.sum()))
    print(d[d.eligible_eval].groupby(y[d.eligible_eval]).size().loc[2008:].to_dict())
    print("A-win rate after randomisation (eligible):", round(d.loc[d.eligible_fighters, "y"].mean(), 4))
