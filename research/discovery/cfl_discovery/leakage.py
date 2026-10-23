"""Leakage detection. Four independent checks, run on every real-data run.

1. manifest_check     every feature's declared sources against PRED-001 s3's
                      forbidden list. A fight's OWN result columns are allowed
                      only as history (time rule: strictly before the date).
2. corner_readers     an A-minus-B feature that is nearly always the same sign
                      is reading the corner label (corner A wins ~64%).
3. pit_audit          PRED-001 s3 audit: for randomly drawn DEV cards, rebuild
                      every feature from a copy of the data cut off strictly
                      before the card, with the card's own results, methods,
                      times and fight totals SCRAMBLED, and require exact
                      equality with the full build.
4. swap_audit         rebuild every feature with the corners swapped in the
                      raw data. Antisymmetric features must flip sign exactly,
                      context features must not move, the market must become
                      1 - q. This is what makes the no-intercept model corner
                      symmetric for real, not just on paper.

Plus the per-candidate "too good" tripwires (evaluate.stage_record) and a
detector self-check with a planted leak (run.py), so a broken detector is
visible rather than quietly passing everything.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import data as D

# PRED-001 section 3, transcribed. The protocol text is the authority.
FORBIDDEN_ALWAYS = {
    "fighters.wins", "fighters.losses", "fighters.draws", "fighters.ufc_wins", "fighters.ufc_losses",
    "fighters.ufc_draws", "fighters.slpm", "fighters.str_acc", "fighters.sapm", "fighters.str_def",
    "fighters.td_avg", "fighters.td_acc", "fighters.td_def", "fighters.sub_avg", "fighters.age",
    "fighters.division", "fighters.last_fight_date",
    "model_predictions", "model_picks", "model_edges", "prop_projections", "pre_fight_snapshots",
}
OWN_RESULT = {"fights.winner_id", "fights.method", "fights.end_round", "fights.end_time",
              "fights.<per-corner totals>", "fight_rounds"}
ALLOWED_STATIC = {"fighters.height_in", "fighters.reach_in", "fighters.stance", "fighters.dob", "fighters.sex"}


def manifest_check(specs) -> list[str]:
    from .features import HIST
    problems = []
    for s in specs:
        for src in s.sources:
            base = src.split("(")[0].strip()
            if src in FORBIDDEN_ALWAYS or base in FORBIDDEN_ALWAYS:
                problems.append(f"{s.name}: forbidden source {src}")
            if src in OWN_RESULT and s.time_rule != HIST:
                problems.append(f"{s.name}: result column {src} used without the strictly-before rule")
            if src.startswith("fighters.") and src not in ALLOWED_STATIC:
                problems.append(f"{s.name}: present-day fighters column {src}")
            if src.startswith("fighters.") and not s.static:
                problems.append(f"{s.name}: profile value {src} not declared static")
    return problems


def corner_readers(table: pd.DataFrame, specs, threshold: float = 0.9) -> list[str]:
    S = table[table.is_scorable]
    bad = []
    for s in specs:
        if s.kind != "anti":
            continue
        v = S[s.name].to_numpy(float)
        v = v[np.isfinite(v) & (v != 0)]
        if len(v) and abs(np.mean(np.sign(v))) > threshold:
            bad.append(f"{s.name}: same sign on {abs(np.mean(np.sign(v))):.0%} of fights")
    return bad


RESULT_COLS = ["winner", "method", "end_round", "end_time"] + \
              [f"{s}_{k}" for k in D.STAT_STEMS for s in "ab"]


def _scramble(day: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Replace a card's own outcomes with junk of the right type."""
    day = day.copy()
    n = len(day)
    day["winner"] = rng.choice(["a", "b", ""], size=n)
    day["method"] = rng.choice(["KO/TKO", "Submission", "Decision - Unanimous", "Overturned"], size=n)
    day["end_round"] = rng.integers(1, 6, size=n).astype(float)
    day["end_time"] = [f"{rng.integers(0, 5)}:{rng.integers(10, 60)}" for _ in range(n)]
    for k in D.STAT_STEMS:
        for s in "ab":
            day[f"{s}_{k}"] = rng.integers(0, 300, size=n).astype(float)
    return day


def _same(a, b, tol=1e-9) -> bool:
    if (pd.isna(a) and pd.isna(b)):
        return True
    if pd.isna(a) or pd.isna(b):
        return False
    return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(a)))


def pit_audit(dev: D.DevData, full_table: pd.DataFrame, specs, builder, n_dates: int,
              seed: int) -> dict:
    """Recompute features for every fight on `n_dates` random scorable cards
    from data cut off strictly before the card, the card's own outcomes
    scrambled. `builder(fights, stats, fighters) -> (table, specs)`."""
    rng = np.random.default_rng(seed)
    raw = dev.fights
    dates = sorted(full_table.loc[full_table.is_scorable, "event_date"].dt.strftime("%Y-%m-%d").unique())
    pick = sorted(rng.choice(dates, size=min(n_dates, len(dates)), replace=False))
    names = [s.name for s in specs if s.family != "control"]
    full = full_table.set_index("fight_id")
    mismatches, checked = [], 0
    for d in pick:
        before = raw[raw.event_date < d]
        day = _scramble(raw[raw.event_date == d], rng)
        trunc = D.DevData(fights=pd.concat([before, day], ignore_index=True), fighters=dev.fighters,
                          sha256={}, manifest_check={})
        f, s, x = D.prepare(trunc)
        T, _ = builder(f, s, x)
        T = T.set_index("fight_id")
        for fid in day.fight_id:
            checked += 1
            for n in names:
                if not _same(T.at[fid, n], full.at[fid, n]):
                    mismatches.append({"fight_id": int(fid), "event_date": d, "feature": n,
                                       "full": None if pd.isna(full.at[fid, n]) else float(full.at[fid, n]),
                                       "cut_off": None if pd.isna(T.at[fid, n]) else float(T.at[fid, n])})
    bad_features = sorted({m["feature"] for m in mismatches})
    return {"dates_checked": len(pick), "fights_checked": checked, "features_checked": len(names),
            "mismatches": mismatches[:50], "n_mismatches": len(mismatches),
            "failed_features": bad_features, "passed": not mismatches}


def swap_corners(raw: pd.DataFrame) -> pd.DataFrame:
    r = raw.copy()
    pairs = [("fighter_a_id", "fighter_b_id"), ("bfo_open_a", "bfo_open_b"), ("bfo_close_a", "bfo_close_b")]
    pairs += [(f"a_{k}", f"b_{k}") for k in D.STAT_STEMS]
    for a, b in pairs:
        r[a], r[b] = raw[b].to_numpy(), raw[a].to_numpy()
    r["winner"] = raw["winner"].map({"a": "b", "b": "a"}).fillna(raw["winner"])
    r.loc[raw.winner == "", "winner"] = ""
    return r


def swap_audit(dev: D.DevData, full_table: pd.DataFrame, specs, builder) -> dict:
    sw = D.DevData(fights=swap_corners(dev.fights), fighters=dev.fighters, sha256={}, manifest_check={})
    f, s, x = D.prepare(sw)
    T, _ = builder(f, s, x)
    A = full_table.set_index("fight_id")
    B = T.set_index("fight_id").loc[A.index]
    sc = A.is_scorable.to_numpy()
    out = {"failed_features": [], "detail": {}}
    for sp in specs:
        if sp.family == "control":
            continue
        a, b = A[sp.name].to_numpy(float)[sc], B[sp.name].to_numpy(float)[sc]
        target = -a if sp.kind == "anti" else a
        both = np.isfinite(target) & np.isfinite(b)
        nan_mismatch = int(np.sum(np.isfinite(target) != np.isfinite(b)))
        worst = float(np.max(np.abs(target[both] - b[both]))) if both.any() else 0.0
        if nan_mismatch or worst > 1e-6:
            out["failed_features"].append(sp.name)
            out["detail"][sp.name] = {"max_abs_error": worst, "missing_mismatch": nan_mismatch}
    qa, qb = A.q_close.to_numpy(float)[sc], B.q_close.to_numpy(float)[sc]
    out["market_max_error"] = float(np.nanmax(np.abs(qa - (1 - qb))))
    ya, yb = A.y.to_numpy(float)[sc], B.y.to_numpy(float)[sc]
    out["outcome_flips"] = bool(np.all(ya == 1 - yb))
    out["passed"] = not out["failed_features"] and out["market_max_error"] < 1e-9 and out["outcome_flips"]
    return out
