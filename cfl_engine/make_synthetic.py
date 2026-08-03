"""Synthetic UFC-like dataset for validating the pipeline harness end-to-end.

Latent-skill fighters with age curves and drift, within-division matchmaking,
stat lines correlated with true skill, and a noisy-but-sharp closing market.
This exists to prove the machinery works and the audits fire -- it makes zero
claims about real UFC data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

WEIGHT_CLASSES = ["FLW", "BW", "FW", "LW", "WW", "MW", "LHW", "HW"]


def _to_american(imp: float) -> float:
    dec = 1.0 / imp
    return round((dec - 1.0) * 100.0) if dec >= 2.0 else round(-100.0 / (dec - 1.0))


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def generate(outdir: str, n_fighters: int = 1100, seed: int = 7):
    rng = np.random.default_rng(seed)
    debut = pd.Timestamp("2010-01-01") + pd.to_timedelta(
        rng.integers(0, 14 * 365, n_fighters), unit="D")
    career_years = np.clip(rng.normal(9, 2.5, n_fighters), 2, 14)
    wc = rng.choice(WEIGHT_CLASSES, n_fighters)
    # static physical attrs: height scales with weight class, reach with height.
    # Deliberately holey (mirrors real coverage: reach is null for ~44% of
    # fighters, stance ~19%) so the NaN paths in engine._static_maps get hit.
    wc_idx = np.array([WEIGHT_CLASSES.index(w) for w in wc], dtype=float)
    height = np.round(rng.normal(64.0 + 1.6 * wc_idx, 1.5, n_fighters), 0)
    reach = np.round(height + rng.normal(1.5, 1.8, n_fighters), 0)
    height[rng.random(n_fighters) < 0.07] = np.nan
    reach[rng.random(n_fighters) < 0.44] = np.nan
    stance = rng.choice(["Orthodox", "Southpaw", "Switch"], n_fighters,
                        p=[0.76, 0.19, 0.05]).astype(object)
    stance[rng.random(n_fighters) < 0.19] = None
    fighters = pd.DataFrame({
        "fighter_id": [f"F{i:05d}" for i in range(n_fighters)],
        "name": [f"Fighter {i}" for i in range(n_fighters)],
        "debut": debut,
        "retire": debut + pd.to_timedelta((career_years * 365).astype(int), unit="D"),
        "dob": debut - pd.to_timedelta((rng.uniform(20, 29, n_fighters) * 365).astype(int), unit="D"),
        "base_skill": rng.normal(0, 1, n_fighters),
        "weight_class": wc,
        "height_in": height,
        "reach_in": reach,
        "stance": stance,
    })

    def skill_at(i: int, date: pd.Timestamp) -> float:
        yrs = (date - fighters.at[i, "debut"]).days / 365.25
        drift = np.sin(yrs * 1.7 + fighters.at[i, "base_skill"]) * 0.18
        age = (date - fighters.at[i, "dob"]).days / 365.25
        return fighters.at[i, "base_skill"] + drift - 0.06 * max(0.0, age - 34.0) ** 1.3

    last_fought = np.full(n_fighters, pd.Timestamp("2009-01-01"))
    months = pd.date_range("2010-02-01", "2026-06-01", freq="MS")
    fight_rows, stat_rows = [], []
    fid = 0

    for m_i, month in enumerate(months):
        for ev in range(3):
            date = month + pd.Timedelta(days=int(rng.integers(0, 27)))
            event_id = f"E{m_i:03d}_{ev}"
            active = np.where((fighters["debut"] <= date) & (fighters["retire"] >= date))[0]
            if len(active) < 4:
                continue
            layoff = np.array([(date - last_fought[i]).days for i in active], dtype=float)
            w = np.clip(layoff, 30, 700)
            w[layoff < 45] = 0.001  # just fought -> effectively unavailable
            pick_n = min(24, (len(active) // 2) * 2)
            chosen = rng.choice(active, size=pick_n, replace=False, p=w / w.sum())

            by_wc: dict[str, list[int]] = {}
            for i in chosen:
                by_wc.setdefault(fighters.at[i, "weight_class"], []).append(i)
            slot = 0
            for wc, ids in by_wc.items():
                ids = sorted(ids, key=lambda i: skill_at(i, date))
                for j in range(0, len(ids) - 1, 2):
                    ia, ib = ids[j], ids[j + 1]
                    sa = skill_at(ia, date) + rng.normal(0, 0.35)
                    sb = skill_at(ib, date) + rng.normal(0, 0.35)
                    true_p = sigmoid(1.35 * (sa - sb))
                    u = rng.random()
                    if u < 0.010:
                        result = "draw"
                    elif u < 0.015:
                        result = "nc"
                    else:
                        result = "a" if rng.random() < true_p else "b"

                    n_rounds = 5 if slot == 0 else 3
                    gap = abs(sa - sb)
                    p_fin = np.clip(0.35 + 0.18 * gap, 0.2, 0.85)
                    finished = result in ("a", "b") and rng.random() < p_fin
                    if finished:
                        method = "KO/TKO" if rng.random() < 0.55 else "SUB"
                        secs = int(rng.uniform(40, n_rounds * 300))
                    else:
                        method = "DEC" if result in ("a", "b") else ("DRAW" if result == "draw" else "NC")
                        secs = n_rounds * 300

                    mkt = float(np.clip(true_p + rng.normal(0, 0.045), 0.04, 0.96))
                    over = 1.046  # ~4.6% overround, split proportionally
                    imp_a = min(mkt * (over ** 0.5), 0.98)
                    imp_b = min((1 - mkt) * (over ** 0.5), 0.98)
                    odds_a = _to_american(imp_a)
                    odds_b = _to_american(imp_b)

                    fight_id = f"FT{fid:06d}"
                    fid += 1
                    fight_rows.append({
                        "fight_id": fight_id, "event_id": event_id, "event_date": date.date(),
                        "fighter_a_id": fighters.at[ia, "fighter_id"],
                        "fighter_b_id": fighters.at[ib, "fighter_id"],
                        "result": result, "method": method, "weight_class": wc,
                        "n_rounds_sched": n_rounds, "odds_a": odds_a, "odds_b": odds_b,
                    })

                    mins = secs / 60.0
                    for me, opp_s, own_s in ((ia, sb, sa), (ib, sa, sb)):
                        att = max(4, int(rng.normal(8, 2) * mins))
                        acc = float(np.clip(0.25 + 0.5 * sigmoid(0.8 * (own_s - opp_s)), 0.1, 0.75))
                        landed = int(rng.binomial(att, acc))
                        td_att = int(rng.poisson(1.6 * mins / 15 + 0.2))
                        td_p = float(np.clip(0.40 + 0.15 * (own_s - opp_s), 0.05, 0.9))
                        td_l = int(rng.binomial(td_att, td_p)) if td_att else 0
                        stat_rows.append({
                            "fight_id": fight_id, "fighter_id": fighters.at[me, "fighter_id"],
                            "sig_landed": landed, "sig_attempted": att,
                            "td_landed": td_l, "td_attempted": td_att,
                            "sub_attempts": int(rng.poisson(0.5 * mins / 15)),
                            "knockdowns": int(rng.binomial(max(landed, 1), float(np.clip(0.015 + 0.01 * (own_s - opp_s), 0.001, 0.08)))),
                            "control_seconds": int(secs * float(np.clip(rng.beta(2, 5) * sigmoid(own_s - opp_s), 0, 0.6))),
                            "fight_seconds": secs,
                        })
                    last_fought[ia] = date
                    last_fought[ib] = date
                    slot += 1

    fights = pd.DataFrame(fight_rows)
    stats = pd.DataFrame(stat_rows)
    fighters_out = fighters[["fighter_id", "name", "dob", "weight_class",
                             "height_in", "reach_in", "stance"]].copy()
    fights.to_csv(f"{outdir}/fights.csv", index=False)
    stats.to_csv(f"{outdir}/fight_stats.csv", index=False)
    fighters_out.to_csv(f"{outdir}/fighters.csv", index=False)
    print(f"synthetic: {len(fights)} fights, {len(stats)} stat rows, {n_fighters} fighters -> {outdir}")
    return fights, stats, fighters_out


if __name__ == "__main__":
    import sys
    generate(sys.argv[1] if len(sys.argv) > 1 else ".")
