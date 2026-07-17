"""CFL Engine core: data contracts, point-in-time features, Elo, market utils.

Iron rule enforced throughout: features for fight N may only use information
from strictly before fight N's event_date. Career stats are rebuilt
chronologically, never joined from present-day scrapes.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

HALF_LIFE_DAYS = 730.0  # 2-year half-life for recency decay
ELO_K = 32.0
ELO_START = 1500.0

REQUIRED_FIGHT_COLS = ["fight_id", "event_date", "fighter_a_id", "fighter_b_id", "result"]
OPTIONAL_FIGHT_COLS = ["weight_class", "n_rounds_sched", "method", "odds_a", "odds_b"]
REQUIRED_STAT_COLS = [
    "fight_id", "fighter_id", "sig_landed", "sig_attempted", "td_landed",
    "td_attempted", "sub_attempts", "knockdowns", "control_seconds", "fight_seconds",
]
REQUIRED_FIGHTER_COLS = ["fighter_id"]

# per-fighter pre-fight features produced by the history loop
FIGHTER_FEATS = [
    "n_fights", "win_rate", "streak", "days_since_last", "age", "pre_elo",
    "slpm", "sapm", "str_acc", "str_def", "td_per15", "td_acc", "td_def",
    "sub_per15", "kd_per15", "ctrl_pct", "finish_rate", "last_ko_loss",
]
MEAN_FEATS = ["n_fights", "age", "days_since_last"]  # symmetric context features
SHARED_FEATS = ["n_rounds_sched", "wc_code"]


# ----------------------------------------------------------------------------- loading
def _validate(df: pd.DataFrame, required: list[str], name: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"{name} is missing required columns: {missing}. "
            f"See README.md for the exact data contract."
        )


def load_data(fights_path: str, stats_path: str, fighters_path: str):
    fights = pd.read_csv(fights_path)
    stats = pd.read_csv(stats_path)
    fighters = pd.read_csv(fighters_path)
    _validate(fights, REQUIRED_FIGHT_COLS, "fights.csv")
    _validate(stats, REQUIRED_STAT_COLS, "fight_stats.csv")
    _validate(fighters, REQUIRED_FIGHTER_COLS, "fighters.csv")

    fights["event_date"] = pd.to_datetime(fights["event_date"])
    bad = ~fights["result"].isin(["a", "b", "draw", "nc"])
    if bad.any():
        raise ValueError(f"fights.result must be one of a/b/draw/nc; {bad.sum()} bad rows")
    for col in OPTIONAL_FIGHT_COLS:
        if col not in fights.columns:
            fights[col] = np.nan
    if "dob" in fighters.columns:
        fighters["dob"] = pd.to_datetime(fighters["dob"], errors="coerce")
    else:
        fighters["dob"] = pd.NaT
    return fights.sort_values("event_date").reset_index(drop=True), stats, fighters


# ----------------------------------------------------------------------------- market
def american_to_prob(odds: float) -> float:
    if pd.isna(odds):
        return np.nan
    odds = float(odds)
    return 100.0 / (odds + 100.0) if odds > 0 else -odds / (-odds + 100.0)


def american_to_decimal(odds: float) -> float:
    if pd.isna(odds):
        return np.nan
    odds = float(odds)
    return 1.0 + odds / 100.0 if odds > 0 else 1.0 - 100.0 / odds


def devig_a(odds_a: float, odds_b: float) -> float:
    """Vig-free market probability for the A side (proportional devig)."""
    pa, pb = american_to_prob(odds_a), american_to_prob(odds_b)
    if pd.isna(pa) or pd.isna(pb):
        return np.nan
    return pa / (pa + pb)


# ----------------------------------------------------------------------------- elo
def compute_elo(fights: pd.DataFrame):
    """Point-in-time Elo. Returns pre-fight ratings for the a/b corners as given.

    Updates are batched per event_date: real data contains same-night multiple
    fights (1990s tournaments), and the iron rule is strictly-before-date, so a
    result from earlier the same evening must not enter a later pre-fight rating.
    """
    rating: dict = defaultdict(lambda: ELO_START)
    pre_a, pre_b = [], []
    pending: list[tuple] = []
    prev_date = None
    for r in fights.itertuples(index=False):
        if prev_date is not None and r.event_date != prev_date:
            for fid, delta in pending:
                rating[fid] += delta
            pending = []
        prev_date = r.event_date
        ra, rb = rating[r.fighter_a_id], rating[r.fighter_b_id]
        pre_a.append(ra)
        pre_b.append(rb)
        if r.result == "nc":
            continue
        score_a = {"a": 1.0, "b": 0.0, "draw": 0.5}[r.result]
        exp_a = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
        pending.append((r.fighter_a_id, ELO_K * (score_a - exp_a)))
        pending.append((r.fighter_b_id, ELO_K * ((1.0 - score_a) - (1.0 - exp_a))))
    for fid, delta in pending:
        rating[fid] += delta
    return np.array(pre_a), np.array(pre_b)


# ----------------------------------------------------------------------------- history features
def _decayed(h: list[dict], now: pd.Timestamp) -> dict:
    """Recency-decayed pre-fight aggregates from a fighter's strictly-prior history."""
    out = {f: np.nan for f in FIGHTER_FEATS if f not in ("age", "pre_elo")}
    out["n_fights"] = len(h)
    if not h:
        out["streak"] = 0.0
        out["last_ko_loss"] = 0.0
        return out

    days_ago = np.array([(now - x["event_date"]).days for x in h], dtype=float)
    w = 0.5 ** (days_ago / HALF_LIFE_DAYS)

    def ws(key):
        return float(np.sum(w * np.array([x[key] for x in h], dtype=float)))

    secs, mins = ws("fight_seconds"), ws("fight_seconds") / 60.0
    sig_l, sig_a = ws("sig_landed"), ws("sig_attempted")
    osig_l, osig_a = ws("opp_sig_landed"), ws("opp_sig_attempted")
    td_l, td_a = ws("td_landed"), ws("td_attempted")
    otd_l, otd_a = ws("opp_td_landed"), ws("opp_td_attempted")

    out["win_rate"] = ws("win") / ws("one")
    out["slpm"] = sig_l / mins if mins > 0 else np.nan
    out["sapm"] = osig_l / mins if mins > 0 else np.nan
    out["str_acc"] = sig_l / sig_a if sig_a > 0 else np.nan
    out["str_def"] = 1.0 - (osig_l / osig_a) if osig_a > 0 else np.nan
    out["td_per15"] = td_l / secs * 900.0 if secs > 0 else np.nan
    out["td_acc"] = td_l / td_a if td_a > 0 else np.nan
    out["td_def"] = 1.0 - (otd_l / otd_a) if otd_a > 0 else np.nan
    out["sub_per15"] = ws("sub_attempts") / secs * 900.0 if secs > 0 else np.nan
    out["kd_per15"] = ws("knockdowns") / secs * 900.0 if secs > 0 else np.nan
    out["ctrl_pct"] = ws("control_seconds") / secs if secs > 0 else np.nan
    out["finish_rate"] = ws("finish_win") / ws("one")
    out["days_since_last"] = float(days_ago.min())
    out["last_ko_loss"] = float(h[-1]["ko_loss"])

    streak = 0.0
    for x in reversed(h):
        if x["win"] == 0.5:
            break
        if streak == 0.0:
            streak = 1.0 if x["win"] == 1.0 else -1.0
        elif (streak > 0) == (x["win"] == 1.0):
            streak += np.sign(streak)
        else:
            break
    out["streak"] = streak
    return out


def build_long_table(fights: pd.DataFrame, stats: pd.DataFrame) -> pd.DataFrame:
    """One row per (fight, fighter) with own + opponent stats and result flags."""
    opp = stats.rename(columns={c: f"opp_{c}" for c in stats.columns if c != "fight_id"})
    merged = stats.merge(opp, on="fight_id")
    merged = merged[merged["fighter_id"] != merged["opp_fighter_id"]].copy()

    meta = []
    for r in fights.itertuples(index=False):
        for me, them, side in ((r.fighter_a_id, r.fighter_b_id, "a"), (r.fighter_b_id, r.fighter_a_id, "b")):
            if r.result in ("a", "b"):
                win = 1.0 if r.result == side else 0.0
            else:
                win = 0.5
            method = str(r.method) if pd.notna(r.method) else ""
            is_finish = method.upper().startswith(("KO", "TKO", "SUB"))
            meta.append({
                "fight_id": r.fight_id, "fighter_id": me, "event_date": r.event_date,
                "win": win, "finish_win": 1.0 if (win == 1.0 and is_finish) else 0.0,
                "ko_loss": 1.0 if (win == 0.0 and method.upper().startswith(("KO", "TKO"))) else 0.0,
                "one": 1.0,
            })
    long_df = pd.DataFrame(meta).merge(merged, on=["fight_id", "fighter_id"], how="left")
    for c in REQUIRED_STAT_COLS[2:] + [f"opp_{c}" for c in REQUIRED_STAT_COLS[2:]]:
        if c in long_df.columns:
            long_df[c] = long_df[c].fillna(0.0)
    return long_df.sort_values(["event_date", "fight_id"]).reset_index(drop=True)


def build_features(fights: pd.DataFrame, stats: pd.DataFrame, fighters: pd.DataFrame) -> pd.DataFrame:
    """Attach point-in-time a_/b_ features to each fight (original corner order)."""
    fights = fights.sort_values("event_date").reset_index(drop=True).copy()
    pre_a, pre_b = compute_elo(fights)
    fights["a_pre_elo"], fights["b_pre_elo"] = pre_a, pre_b

    long_df = build_long_table(fights, stats)
    hist: dict = defaultdict(list)
    feat_map: dict = {}
    for rec in long_df.to_dict("records"):
        key = (rec["fight_id"], rec["fighter_id"])
        # strictly-before-date only: same-night earlier bouts (90s tournaments)
        # are excluded, matching the iron rule and the PIT structural check
        prior = [x for x in hist[rec["fighter_id"]] if x["event_date"] < rec["event_date"]]
        feat_map[key] = _decayed(prior, rec["event_date"])
        hist[rec["fighter_id"]].append(rec)

    dob = fighters.set_index("fighter_id")["dob"].to_dict()
    rows = []
    for r in fights.itertuples(index=False):
        row = {}
        for side, fid in (("a", r.fighter_a_id), ("b", r.fighter_b_id)):
            f = feat_map[(r.fight_id, fid)]
            for k, v in f.items():
                row[f"{side}_{k}"] = v
            d = dob.get(fid, pd.NaT)
            row[f"{side}_age"] = (r.event_date - d).days / 365.25 if pd.notna(d) else np.nan
        rows.append(row)
    feat_df = pd.DataFrame(rows)
    out = pd.concat([fights.reset_index(drop=True), feat_df], axis=1)
    out["wc_code"] = pd.factorize(out["weight_class"].astype(str))[0].astype(float)
    out["n_rounds_sched"] = pd.to_numeric(out["n_rounds_sched"], errors="coerce").fillna(3.0)
    return out


# ----------------------------------------------------------------------------- corners + matchup
def randomize_corners(df: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """Randomly swap a/b corners to kill any orientation bias in the source data."""
    rng = np.random.default_rng(seed)
    flip = rng.random(len(df)) < 0.5
    df = df.copy()
    a_cols = [c for c in df.columns if c.startswith("a_")]
    swap_pairs = [(c, "b_" + c[2:]) for c in a_cols]
    swap_pairs += [("fighter_a_id", "fighter_b_id"), ("odds_a", "odds_b")]
    for ca, cb in swap_pairs:
        tmp = df.loc[flip, ca].copy()
        df.loc[flip, ca] = df.loc[flip, cb].to_numpy()
        df.loc[flip, cb] = tmp.to_numpy()
    res = df["result"].copy()
    df.loc[flip & (res == "a"), "result"] = "b"
    df.loc[flip & (res == "b"), "result"] = "a"
    df["corner_flipped"] = flip
    return df


def make_matchup_features(df: pd.DataFrame):
    """Differential (A-B) + symmetric-mean features. Returns (X, diff_cols, all_cols)."""
    X = pd.DataFrame(index=df.index)
    diff_cols = []
    for f in FIGHTER_FEATS:
        c = f"d_{f}"
        X[c] = df[f"a_{f}"] - df[f"b_{f}"]
        diff_cols.append(c)
    for f in MEAN_FEATS:
        X[f"m_{f}"] = (df[f"a_{f}"] + df[f"b_{f}"]) / 2.0
    for f in SHARED_FEATS:
        X[f] = df[f]
    return X, diff_cols, list(X.columns)


def predict_symmetric(model, X: pd.DataFrame, diff_cols: list[str]):
    """Average over both corner orderings so P(A)+P(B)=1 exactly.

    Returns (p_symmetric, raw_asymmetry) where raw_asymmetry = |p + p_swap - 1|
    before averaging -- a direct read on residual orientation sensitivity.
    """
    Xs = X.copy()
    Xs[diff_cols] = -Xs[diff_cols]
    p = model.predict_proba(X)[:, 1]
    p_swap = model.predict_proba(Xs)[:, 1]
    return 0.5 * (p + (1.0 - p_swap)), np.abs(p + p_swap - 1.0)
