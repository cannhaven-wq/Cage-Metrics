"""WIN-001 point-in-time features. Pure pandas/numpy, no network.

Every number here is computed from fights dated STRICTLY BEFORE the fight it
describes (PRED-001 §3). State is updated per event date, after every fight on
that date has been scored, so a same-night earlier bout never leaks into a
later one (the 1990s tournament rule).

Input tables are the DEV export in ./data (see DATA.md) or, for the auditor,
the same shape pulled over the whole history. Column names follow the export:

  fights:   id, event_id, event_date, a, b, w, m, wc, sr, er, et, t,
            a_sl b_sl a_sa b_sa a_tl b_tl a_ta b_ta a_sub b_sub a_kd b_kd
            a_ctrl b_ctrl
  fighters: id, dob, h, r, s
  closing:  fight_id, american_a, american_b   (BFO closing consensus, ints)
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
import pandas as pd

ELO_K = 32.0
ELO_START = 1500.0
HALF_LIFE_DAYS = 3 * 365.25     # weight of a past fight halves every three years
PRIOR_MINUTES = 15.0            # one fight's worth of league-average pace for debutants
LEAGUE = {"sl_pm": 3.6, "sa_pm": 3.6, "td_p15": 1.4, "tdd_p15": 1.4, "kd_p15": 0.25, "sub_p15": 0.5}

NC_PREFIX = ("overturned", "could not continue", "no contest", "other")

# Antisymmetric matchup features: d_x = x(A) - x(B). No intercept is fitted,
# so p(A beats B) = 1 - p(B beats A) holds exactly (PRED-001 §3 corner symmetry).
DIFF_FEATURES = [
    "elo", "ufc_gap", "n_fights", "log_layoff", "age", "reach", "height",
    "sl_pm", "sa_pm", "td_p15", "tdd_p15", "kd_p15", "sub_p15",
    "finish_rate", "finished_rate", "win_rate",
]


def fight_seconds(sr, er, et, method) -> float:
    try:
        mm, ss = str(et).split(":")
        return (int(er) - 1) * 300 + int(mm) * 60 + int(ss)
    except (ValueError, TypeError, AttributeError):
        m = str(method or "").lower()
        if m.startswith("decision") and sr == sr and sr:
            return int(sr) * 300
        return float("nan")


def result_code(w, a, b, method) -> str:
    m = str(method or "").strip().lower()
    if any(m.startswith(x) for x in NC_PREFIX):
        return "nc"
    if w == w and w is not None:
        if int(w) == int(a):
            return "a"
        if int(w) == int(b):
            return "b"
        return "nc"
    if m.startswith("decision") or "draw" in m:
        return "draw"
    return "nc"


def logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def american_to_implied(x: float) -> float:
    x = float(x)
    return 100.0 / (x + 100.0) if x > 0 else -x / (-x + 100.0)


def devig_proportional(am_a, am_b) -> float:
    pa, pb = american_to_implied(am_a), american_to_implied(am_b)
    return pa / (pa + pb)


class _Side:
    """One fighter's share of one past fight, as the state keeps it."""
    __slots__ = ("date", "mins", "sl", "sa", "osl", "osa", "tl", "ta", "otl", "ota",
                 "kd", "sub", "win", "loss", "fin_win", "fin_loss")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k, 0.0))


def _fighter_features(past: list[_Side], date, elo: float) -> dict:
    if not past:
        f = {k: LEAGUE[k] for k in LEAGUE}
        f.update(elo=elo, ufc_gap=0.0, n_fights=0.0, log_layoff=math.log1p(365.0),
                 finish_rate=0.0, finished_rate=0.0, win_rate=0.5)
        return f
    w = np.array([0.5 ** ((date - p.date).days / HALF_LIFE_DAYS) for p in past])
    mins = np.array([p.mins for p in past]) * w
    tot = mins.sum() + PRIOR_MINUTES

    def rate(attr, per, league):
        v = np.array([getattr(p, attr) for p in past]) * w
        return (v.sum() + league * PRIOR_MINUTES / per) / tot * per

    n = float(len(past))
    wins = sum(p.win for p in past)
    losses = sum(p.loss for p in past)
    return dict(
        elo=elo,
        ufc_gap=float(wins - losses),
        n_fights=n,
        log_layoff=math.log1p((date - max(p.date for p in past)).days),
        sl_pm=rate("sl", 1.0, LEAGUE["sl_pm"]),
        sa_pm=rate("osl", 1.0, LEAGUE["sa_pm"]),
        td_p15=rate("tl", 15.0, LEAGUE["td_p15"]),
        tdd_p15=rate("otl", 15.0, LEAGUE["tdd_p15"]),
        kd_p15=rate("kd", 15.0, LEAGUE["kd_p15"]),
        sub_p15=rate("sub", 15.0, LEAGUE["sub_p15"]),
        finish_rate=(sum(p.fin_win for p in past) + 0.5) / (n + 2.0),
        finished_rate=(sum(p.fin_loss for p in past) + 0.5) / (n + 2.0),
        win_rate=(wins + 1.0) / (n + 2.0),
    )


def build_rows(fights: pd.DataFrame, fighters: pd.DataFrame) -> pd.DataFrame:
    """One row per fight with a_*/b_* point-in-time features and the result code.

    Walks every fight in date order (ALL fights, decided or not, so a veteran's
    history is complete) and emits features for each. Strictly before-date.
    """
    f = fights.copy()
    f["event_date"] = pd.to_datetime(f["event_date"])
    f = f.sort_values(["event_date", "id"]).reset_index(drop=True)
    fi = fighters.set_index("id")
    dob = pd.to_datetime(fi["dob"], errors="coerce").to_dict()
    height = pd.to_numeric(fi["h"], errors="coerce").to_dict()
    reach = pd.to_numeric(fi["r"], errors="coerce").to_dict()

    elo: dict = defaultdict(lambda: ELO_START)
    hist: dict = defaultdict(list)
    pending_elo: list = []
    pending_hist: list = []
    prev_date = None
    out = []

    for r in f.itertuples(index=False):
        if prev_date is not None and r.event_date != prev_date:
            for fid, d in pending_elo:
                elo[fid] += d
            for fid, side in pending_hist:
                hist[fid].append(side)
            pending_elo, pending_hist = [], []
        prev_date = r.event_date
        a, b = int(r.a), int(r.b)
        row = {"fight_id": int(r.id), "event_id": int(r.event_id), "event_date": r.event_date,
               "a": a, "b": b, "result": result_code(r.w, a, b, r.m)}
        for side, fid in (("a", a), ("b", b)):
            feats = _fighter_features(hist[fid], r.event_date, elo[fid])
            d = dob.get(fid)
            feats["age"] = (r.event_date - d).days / 365.25 if d is not None and d == d else np.nan
            feats["reach"] = reach.get(fid, np.nan)
            feats["height"] = height.get(fid, np.nan)
            for k, v in feats.items():
                row[f"{side}_{k}"] = v
        out.append(row)

        res = row["result"]
        if res == "nc":
            continue
        score_a = {"a": 1.0, "b": 0.0, "draw": 0.5}[res]
        exp_a = 1.0 / (1.0 + 10 ** ((elo[b] - elo[a]) / 400.0))
        pending_elo.append((a, ELO_K * (score_a - exp_a)))
        pending_elo.append((b, ELO_K * ((1.0 - score_a) - (1.0 - exp_a))))
        secs = fight_seconds(r.sr, r.er, r.et, r.m)
        mins = secs / 60.0 if secs == secs else 15.0
        m = str(r.m or "").lower()
        finish = not m.startswith("decision")
        g = lambda v: float(v) if v == v and v is not None else 0.0  # noqa: E731
        pending_hist.append((a, _Side(date=r.event_date, mins=mins, sl=g(r.a_sl), sa=g(r.a_sa),
                                      osl=g(r.b_sl), osa=g(r.b_sa), tl=g(r.a_tl), ta=g(r.a_ta),
                                      otl=g(r.b_tl), ota=g(r.b_ta), kd=g(r.a_kd), sub=g(r.a_sub),
                                      win=float(res == "a"), loss=float(res == "b"),
                                      fin_win=float(res == "a" and finish),
                                      fin_loss=float(res == "b" and finish))))
        pending_hist.append((b, _Side(date=r.event_date, mins=mins, sl=g(r.b_sl), sa=g(r.b_sa),
                                      osl=g(r.a_sl), osa=g(r.a_sa), tl=g(r.b_tl), ta=g(r.b_ta),
                                      otl=g(r.a_tl), ota=g(r.a_ta), kd=g(r.b_kd), sub=g(r.b_sub),
                                      win=float(res == "b"), loss=float(res == "a"),
                                      fin_win=float(res == "b" and finish),
                                      fin_loss=float(res == "a" and finish))))
    return pd.DataFrame(out)


def matchup_matrix(rows: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """A - B differences. A missing side (no reach on file) contributes 0:
    'no information' rather than a guess, and still antisymmetric."""
    X = pd.DataFrame(index=rows.index)
    for k in features:
        X["d_" + k] = (rows[f"a_{k}"] - rows[f"b_{k}"]).fillna(0.0)
    return X
