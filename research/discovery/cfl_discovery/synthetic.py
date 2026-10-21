"""Clearly labelled synthetic fixtures, in the exact shape of the DEV export.

A world where the truth is known, so the engine can be checked end to end:

  * every fighter has a hidden skill; the market prices skill well (with a
    little noise) and nothing else;
  * one planted effect the market does NOT price: reach. With
    `planted_reach` > 0, a longer reach genuinely raises the chance of winning;
  * everything else (stance, layoff, the stats, ...) carries skill
    information the market already has, or none at all;
  * corner A is the favourite about 64% of the time, as in real UFC data, so
    a model that reads the corner label would look skilful.

A correct engine should find reach (when planted), should not find noise, and
should not confirm anything when planted_reach = 0.

Dates run 2007-2024 so fixtures pass PRED-001's dev_only() guard. No row is,
or resembles, a real fight; ids are offset by 10,000,000.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import DevData

ID0 = 10_000_000


def _american(p: float, vig: float) -> int:
    q = min(max(p * (1 + vig), 0.01), 0.99)
    a = -100 * q / (1 - q) if q >= 0.5 else 100 * (1 - q) / q
    a = int(round(a))
    if -100 < a < 100:
        a = -100 if a <= 0 else 100
    return a


def make(n_fighters: int = 700, events_per_year: int = 24, fights_per_event: int = 11,
         years: tuple = (2007, 2024), planted_reach: float = 0.22, market_noise: float = 0.25,
         seed: int = 7) -> DevData:
    rng = np.random.default_rng(seed)
    fid = np.arange(n_fighters) + ID0
    skill = rng.standard_normal(n_fighters)
    reach = np.round(rng.normal(72, 3.0, n_fighters))
    height = np.round(reach - rng.normal(1.5, 1.5, n_fighters))
    stance = rng.choice(["Orthodox", "Southpaw", "Switch"], p=[0.75, 0.2, 0.05], size=n_fighters)
    born = pd.to_datetime("1975-01-01") + pd.to_timedelta(rng.integers(0, 9000, n_fighters), unit="D")
    wc = rng.choice(["Lightweight", "Welterweight", "Middleweight", "Bantamweight", "Heavyweight"],
                    size=n_fighters)
    fighters = pd.DataFrame({"fighter_id": fid, "height_in": height, "reach_in": reach,
                             "stance": stance, "dob": born.strftime("%Y-%m-%d"), "sex": "M"})
    rows = []
    fight_id, event_id = ID0, ID0
    for yr in range(years[0], years[1] + 1):
        days = np.sort(rng.choice(np.arange(1, 360), size=events_per_year, replace=False))
        for d in days:
            date = (pd.Timestamp(f"{yr}-01-01") + pd.Timedelta(days=int(d))).strftime("%Y-%m-%d")
            event_id += 1
            picked = rng.choice(n_fighters, size=2 * fights_per_event, replace=False)
            for k in range(fights_per_event):
                i, j = picked[2 * k], picked[2 * k + 1]
                true_logit = 1.1 * (skill[i] - skill[j]) + planted_reach * (reach[i] - reach[j]) / 3.0
                mkt_logit = 1.1 * (skill[i] - skill[j]) + rng.normal(0, market_noise)
                # put the market favourite in corner A ~64% of the time
                fav_first = rng.random() < 0.64
                if (mkt_logit < 0) == fav_first:
                    i, j = j, i
                    true_logit, mkt_logit = -true_logit, -mkt_logit
                q = 1 / (1 + np.exp(-mkt_logit))
                q_open = 1 / (1 + np.exp(-(mkt_logit + rng.normal(0, 0.25))))
                a_wins = rng.random() < 1 / (1 + np.exp(-true_logit))
                fight_id += 1
                rnd = int(rng.integers(1, 4))
                mins = (rnd - 1) * 5 + rng.uniform(0.5, 5)
                stat = {}
                for s, me, them in (("a", i, j), ("b", j, i)):
                    rate = np.exp(0.15 * (skill[me] - skill[them]))
                    sl = rng.poisson(4.0 * rate * mins)
                    stat.update({f"{s}_kd": rng.poisson(0.05 * rate * mins), f"{s}_sig_landed": sl,
                                 f"{s}_sig_attempted": sl + rng.poisson(5 * mins),
                                 f"{s}_td_landed": rng.poisson(0.2 * mins),
                                 f"{s}_td_attempted": rng.poisson(0.5 * mins) + 0,
                                 f"{s}_sub_attempts": rng.poisson(0.1 * mins), f"{s}_rev": 0,
                                 f"{s}_ctrl_seconds": int(rng.poisson(20 * mins)),
                                 f"{s}_head_landed": sl // 2, f"{s}_body_landed": sl // 4,
                                 f"{s}_leg_landed": sl - sl // 2 - sl // 4,
                                 f"{s}_distance_landed": sl // 2, f"{s}_clinch_landed": sl // 4,
                                 f"{s}_ground_landed": sl - sl // 2 - sl // 4})
                    stat[f"{s}_td_attempted"] = max(stat[f"{s}_td_attempted"], stat[f"{s}_td_landed"])
                rows.append({
                    "fight_id": fight_id, "event_id": event_id, "event_date": date,
                    "fighter_a_id": fid[i], "fighter_b_id": fid[j], "winner": "a" if a_wins else "b",
                    "method": rng.choice(["KO/TKO", "Submission", "Decision - Unanimous"]),
                    "end_round": rnd, "end_time": f"{int(mins - (rnd - 1) * 5)}:{int(rng.integers(10, 59))}",
                    "scheduled_rounds": 5 if k == fights_per_event - 1 else 3, "weight_class": wc[i],
                    "is_title_fight": 0, "is_main_event": int(k == fights_per_event - 1), "bout_order": np.nan,
                    **stat,
                    "bfo_open_a": _american(q_open, 0.025), "bfo_open_b": _american(1 - q_open, 0.025),
                    "bfo_close_a": _american(q, 0.025), "bfo_close_b": _american(1 - q, 0.025),
                    "is_active": 1,
                })
    fights = pd.DataFrame(rows)
    fights["weight_class"] = fights["weight_class"].astype(str)
    fights["method"] = fights["method"].astype(str)
    return DevData(fights=fights, fighters=fighters, sha256={"synthetic": f"seed={seed}"},
                   manifest_check={"match": None, "synthetic": True})
