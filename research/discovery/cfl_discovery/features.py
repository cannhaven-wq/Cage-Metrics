"""Point-in-time base features, each with a PRED-001 section 3 manifest entry.

Three layers, all computed from rows dated STRICTLY before the fight:

  1. The engine's own history features (cfl_engine/engine.py::build_features,
     imported unchanged): decayed striking/grappling rates, Elo, streak, age,
     layoff, static profile values.
  2. Extra history features the engine does not build (UFC record count,
     strength of schedule, division moves, five-round experience, ...), from a
     second chronological loop with the same strictly-before-date rule.
  3. Matchup, market and context features derived from the two above and from
     the booking itself (scheduled rounds, title, weight class) and the BFO
     opening/closing consensus.

Corner symmetry is structural. Every feature that can enter a model on its own
is ANTISYMMETRIC: swapping the corners flips its sign (A minus B). Context
features are SYMMETRIC and only ever enter multiplied by an antisymmetric one.
A model with no intercept over antisymmetric terms therefore satisfies
p(A beats B) = 1 - p(B beats A) exactly, which is PRED-001's symmetry rule.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

import engine as cfl_engine  # cfl_engine/engine.py, reused unchanged


@dataclass
class FeatureSpec:
    name: str
    kind: str                 # "anti" (A minus B) or "ctx" (symmetric context)
    family: str               # history / physical / style / matchup / market / context / control
    sources: list             # table.column the value is built from
    time_rule: str            # how it is kept point-in-time
    static: bool = False      # a present-day profile value treated as fixed (PRED-001 s3 caveat)
    plain: str = ""           # one plain-English sentence
    h1_contaminated: bool = False   # measures a factor whose all-years verdict (incl. sealed years) CFL has seen
    contamination: str = ""         # which published verdict, if so

    def as_dict(self):
        return asdict(self)


HIST = "fights/fight totals with event_date strictly before this fight's event_date"
BOOK = "known at booking: this fight's own scheduling fields, never its result"
# PRED-001 s2: the Factor Lab (factor-rates.json) and edges.js computed their
# verdicts over every year, including the sealed H1 window. A feature that
# measures one of those factors cannot count as clean historical evidence,
# whatever this engine finds; it can only earn a prospective test. Flagged
# conservatively: every feature that measures the same thing, not only the
# ones a person picked because the verdict looked good (consolidation audit E3).
H1_CONTAMINATED = {
    "d_age": "Factor Lab 'age'",
    "c_age_mean": "Factor Lab 'age'",
    "d_reach_in": "Factor Lab 'reach'",
    "d_height_in": "Factor Lab 'height'",
    "d_is_southpaw": "Factor Lab 'southpaw_reach'",
    "mu_southpaw_vs_orthodox": "Factor Lab 'southpaw_reach'",
    "d_ufc_net": "Factor Lab 'ufc_record'",
    "d_ufc_raw_rate": "Factor Lab 'ufc_record'",
    "d_win_rate": "edges.js 'record' (FE-001)",
    "d_td_def": "Factor Lab 'td_def' and edges.js 'td_def'",
    "mu_grapple": "built on takedown defence (Factor Lab 'td_def')",
    "d_slpm": "Factor Lab 'strike_volume'",
    "mu_net_strike": "built on strikes landed per minute (Factor Lab 'strike_volume')",
    "d_finish_rate": "Factor Lab 'finish_rate'",
    "d_dec_rate": "close to the complement of finishing (Factor Lab 'finish_rate')",
    "d_last3_win_rate": "a record measure (Factor Lab 'ufc_record', edges.js 'record')",
}

MKT = "BFO consensus prices for this fight; the opener precedes the close, the close is the benchmark the model is scored against"

# --- per-fighter history features from the engine --------------------------------
ENGINE_FIGHTER = {
    "n_fights": ("history", "UFC fights before this one"),
    "win_rate": ("history", "recency-weighted share of past fights won"),
    "streak": ("history", "current win (+) or losing (-) streak"),
    "days_since_last": ("history", "days since the fighter's previous fight"),
    "pre_elo": ("history", "Elo rating before the fight, updated only on earlier cards"),
    "slpm": ("style", "significant strikes landed per minute, recency-weighted"),
    "sapm": ("style", "significant strikes absorbed per minute"),
    "str_acc": ("style", "share of significant strikes attempted that landed"),
    "str_def": ("style", "share of opponents' significant strikes avoided"),
    "td_per15": ("style", "takedowns landed per 15 minutes"),
    "td_acc": ("style", "takedown success rate"),
    "td_def": ("style", "share of opponents' takedowns stopped"),
    "sub_per15": ("style", "submission attempts per 15 minutes"),
    "kd_per15": ("style", "knockdowns scored per 15 minutes"),
    "ctrl_pct": ("style", "share of fight time spent in control"),
    "finish_rate": ("history", "recency-weighted share of fights won by finish"),
    "last_ko_loss": ("history", "lost the previous fight by knockout"),
}
ENGINE_STATIC = {
    "age": ("physical", "age on fight night, from date of birth", ["fighters.dob", "events.event_date"]),
    "height_in": ("physical", "height in inches", ["fighters.height_in"]),
    "reach_in": ("physical", "reach in inches", ["fighters.reach_in"]),
    "is_southpaw": ("physical", "fights southpaw", ["fighters.stance"]),
    "is_switch": ("physical", "fights switch stance", ["fighters.stance"]),
}
EXTRA_FIGHTER = {
    "ufc_net": ("history", "UFC wins minus UFC losses in the record so far (raw count, not weighted)"),
    "ufc_raw_rate": ("history", "UFC wins divided by UFC wins plus losses, unweighted"),
    "ko_losses": ("history", "times knocked out before"),
    "sub_losses": ("history", "times submitted before"),
    "last3_win_rate": ("history", "wins in the last three fights, as a share"),
    "opp_elo_mean": ("history", "average pre-fight Elo of past opponents (strength of schedule)"),
    "n_5rd": ("history", "previous five-round fights"),
    "n_title": ("history", "previous title fights"),
    "wc_move": ("history", "pounds moved up (+) or down (-) from the previous fight's division"),
    "fights_365": ("history", "fights in the 365 days before this one"),
    "mean_minutes": ("history", "average fight length in minutes"),
    "dec_rate": ("history", "share of past fights that went to the judges"),
    "years_active": ("history", "years since the first UFC fight in the record"),
    "elo_trend": ("history", "Elo now minus Elo three fights ago"),
    "lost_last": ("history", "lost the previous fight (any method)"),
}


def _extra_history(f: pd.DataFrame) -> dict:
    """(fight_id, fighter_id) -> extra features, strictly before event_date.

    `f` must already carry a_pre_elo / b_pre_elo from the engine (which is
    itself batched per event date)."""
    hist: dict = defaultdict(list)
    out: dict = {}
    # Process a whole event date before appending any of its fights to history:
    # same-night results never enter a same-night feature.
    for _, day in f.groupby("event_date", sort=True):
        recs = []
        for r in day.itertuples(index=False):
            for me, them, side, my_elo, their_elo in (
                    (r.fighter_a_id, r.fighter_b_id, "a", r.a_pre_elo, r.b_pre_elo),
                    (r.fighter_b_id, r.fighter_a_id, "b", r.b_pre_elo, r.a_pre_elo)):
                h = hist[me]
                d = r.event_date
                wl = [x for x in h if x["res"] in (0.0, 1.0)]
                wins = sum(x["res"] for x in wl)
                feats = {
                    "ufc_net": float(wins - (len(wl) - wins)),
                    "ufc_raw_rate": wins / len(wl) if wl else np.nan,
                    "ko_losses": float(sum(1 for x in h if x["res"] == 0.0 and x["ko"])),
                    "sub_losses": float(sum(1 for x in h if x["res"] == 0.0 and x["sub"])),
                    "last3_win_rate": (sum(x["res"] for x in wl[-3:]) / len(wl[-3:])) if wl else np.nan,
                    "opp_elo_mean": float(np.mean([x["opp_elo"] for x in h])) if h else np.nan,
                    "n_5rd": float(sum(1 for x in h if x["sched"] == 5)),
                    "n_title": float(sum(1 for x in h if x["title"] == 1)),
                    "wc_move": (r.wc_limit - h[-1]["wc_limit"]) if h else np.nan,
                    "fights_365": float(sum(1 for x in h if (d - x["date"]).days <= 365)),
                    "mean_minutes": float(np.nanmean([x["secs"] for x in h]) / 60.0)
                    if h and not all(np.isnan(x["secs"]) for x in h) else np.nan,
                    "dec_rate": float(np.mean([x["dec"] for x in h])) if h else np.nan,
                    "years_active": (d - h[0]["date"]).days / 365.25 if h else np.nan,
                    "elo_trend": (my_elo - h[-3]["my_elo"]) if len(h) >= 3 else np.nan,
                    "lost_last": float(h[-1]["res"] == 0.0) if h else np.nan,
                }
                out[(r.fight_id, me)] = feats
                m = (r.method or "").upper()
                res = {"a": 1.0, "b": 0.0, "draw": 0.5}.get(r.result, None)
                if res is not None and side == "b" and r.result in ("a", "b"):
                    res = 1.0 - res
                recs.append((me, {
                    "date": d, "res": res if r.result != "nc" else None,
                    "ko": m.startswith(("KO", "TKO")), "sub": m.startswith("SUB"),
                    "dec": float(m.startswith("DECISION")), "opp_elo": their_elo,
                    "my_elo": my_elo, "sched": r.n_rounds_sched,
                    "title": r.is_title_fight, "wc_limit": r.wc_limit, "secs": r.fight_seconds,
                }))
        for me, rec in recs:
            hist[me].append(rec)
    return out


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def build(fights: pd.DataFrame, stats: pd.DataFrame, fighters: pd.DataFrame,
          noise_controls: int = 0, seed: int = 0) -> tuple[pd.DataFrame, list[FeatureSpec]]:
    """Return (table, manifest). `table` has one row per fight in `fights`
    (all of them: history needs unscored fights too) with fight metadata,
    market columns and every base feature."""
    eng_in = fights[["fight_id", "event_date", "fighter_a_id", "fighter_b_id", "result",
                     "weight_class", "n_rounds_sched", "method", "odds_a", "odds_b"]].copy()
    eng = cfl_engine.build_features(eng_in, stats, fighters.rename(columns={"fighter_id": "fighter_id"}))
    eng = eng.set_index("fight_id")
    f = fights.set_index("fight_id").copy()
    for side in "ab":
        for k in list(ENGINE_FIGHTER) + list(ENGINE_STATIC):
            f[f"{side}_{k}"] = eng[f"{side}_{k}"]
    f = f.reset_index()
    extra = _extra_history(f)
    for side, col in (("a", "fighter_a_id"), ("b", "fighter_b_id")):
        for k in EXTRA_FIGHTER:
            f[f"{side}_{k}"] = [extra[(fid, pid)][k] for fid, pid in zip(f.fight_id, f[col])]

    sex = dict(zip(fighters.fighter_id, fighters.sex))
    stance = dict(zip(fighters.fighter_id, fighters.stance))

    T = pd.DataFrame({"fight_id": f.fight_id, "event_id": f.event_id, "event_date": f.event_date,
                      "fighter_a_id": f.fighter_a_id, "fighter_b_id": f.fighter_b_id,
                      "y": f.y, "is_scorable": f.is_scorable, "q_close": f.q_close,
                      "q_close_power": f.q_close_power, "q_close_shin": f.q_close_shin,
                      "q_open": f.q_open, "odds_a": f.odds_a, "odds_b": f.odds_b})
    specs: list[FeatureSpec] = []

    def anti(name, values, family, sources, rule, plain, static=False):
        T[name] = np.asarray(values, dtype=float)
        specs.append(FeatureSpec(name, "anti", family, sources, rule, static, plain,
                                 name in H1_CONTAMINATED, H1_CONTAMINATED.get(name, "")))

    def ctx(name, values, sources, rule, plain, family="context", static=False):
        T[name] = np.asarray(values, dtype=float)
        specs.append(FeatureSpec(name, "ctx", family, sources, rule, static, plain,
                                 name in H1_CONTAMINATED, H1_CONTAMINATED.get(name, "")))

    hist_src = ["fights.winner_id", "fights.method", "fights.end_round", "fights.end_time",
                "fights.<per-corner totals>", "events.event_date"]
    for k, (fam, plain) in ENGINE_FIGHTER.items():
        anti(f"d_{k}", f[f"a_{k}"] - f[f"b_{k}"], fam, hist_src + ["(cfl_engine.build_features)"], HIST,
             f"difference in {plain}")
    for k, (fam, plain, src) in ENGINE_STATIC.items():
        anti(f"d_{k}", f[f"a_{k}"] - f[f"b_{k}"], fam, src,
             "profile value treated as fixed; age computed from dob at the fight date",
             f"difference in {plain}", static=True)
    for k, (fam, plain) in EXTRA_FIGHTER.items():
        anti(f"d_{k}", f[f"a_{k}"] - f[f"b_{k}"], fam, hist_src + ["fights.weight_class",
             "fights.scheduled_rounds", "fights.is_title_fight"], HIST, f"difference in {plain}")

    # --- matchup features: antisymmetric by construction --------------------------
    a, b = f, f
    anti("mu_net_strike", (a.a_slpm - a.a_sapm) - (b.b_slpm - b.b_sapm), "matchup", hist_src, HIST,
         "who out-lands their opponents by more, per minute")
    anti("mu_grapple", a.a_td_per15 * (1 - b.b_td_def) - b.b_td_per15 * (1 - a.a_td_def), "matchup",
         hist_src, HIST, "takedown rate of each fighter times how often the other fails to stop takedowns")
    anti("mu_strike_eff", a.a_str_acc * (1 - b.b_str_def) - b.b_str_acc * (1 - a.a_str_def), "matchup",
         hist_src, HIST, "striking accuracy of each fighter against the other's defence")
    st_a = [str(stance.get(x, "")).lower() for x in f.fighter_a_id]
    st_b = [str(stance.get(x, "")).lower() for x in f.fighter_b_id]
    sa = np.array([1.0 if s == "southpaw" else 0.0 if s else np.nan for s in st_a])
    sb = np.array([1.0 if s == "southpaw" else 0.0 if s else np.nan for s in st_b])
    oa = np.array([1.0 if s == "orthodox" else 0.0 if s else np.nan for s in st_a])
    ob = np.array([1.0 if s == "orthodox" else 0.0 if s else np.nan for s in st_b])
    anti("mu_southpaw_vs_orthodox", sa * ob - sb * oa, "matchup", ["fighters.stance"],
         "profile value treated as fixed", "a southpaw facing an orthodox fighter", static=True)
    anti("mu_debut", (f.a_n_fights == 0).astype(float) - (f.b_n_fights == 0).astype(float), "matchup",
         hist_src, HIST, "one fighter is making a UFC debut and the other is not")

    # --- market features ----------------------------------------------------------
    lc, lo = _logit(f.q_close), _logit(f.q_open)
    anti("mk_move", lc - lo, "market", ["fight_odds(BFO opener)", "fight_odds(BFO closer)"], MKT,
         "how far the price moved toward this fighter between the opening and closing consensus")
    anti("mk_cubic", lc ** 3, "market", ["fight_odds(BFO closer)"], MKT,
         "a bend in how big favourites and big underdogs are priced (favourite-longshot shape)")

    # --- symmetric context features ------------------------------------------------
    ctx("c_five_round", (f.n_rounds_sched == 5).astype(float), ["fights.scheduled_rounds"], BOOK,
        "scheduled for five rounds")
    ctx("c_title", f.is_title_fight.fillna(0).astype(float), ["fights.is_title_fight"], BOOK, "title fight")
    ctx("c_main_event", f.is_main_event.fillna(0).astype(float), ["fights.is_main_event"], BOOK, "main event")
    ctx("c_heavy", (f.wc_limit >= 205).astype(float), ["fights.weight_class"], BOOK,
        "light heavyweight or heavyweight")
    ctx("c_small", (f.wc_limit <= 135).astype(float), ["fights.weight_class"], BOOK,
        "bantamweight or lighter")
    ctx("c_women", np.array([1.0 if sex.get(x) == "F" and sex.get(y) == "F" else 0.0
                             for x, y in zip(f.fighter_a_id, f.fighter_b_id)]),
        ["fighters.sex"], "profile value treated as fixed", "women's bout", static=True)
    ctx("c_experience", np.log1p((f.a_n_fights + f.b_n_fights) / 2.0), hist_src, HIST,
        "how many UFC fights the two have had, on average")
    ctx("c_any_debut", ((f.a_n_fights == 0) | (f.b_n_fights == 0)).astype(float), hist_src, HIST,
        "at least one fighter is debuting")
    ctx("c_age_mean", (f.a_age + f.b_age) / 2.0, ["fighters.dob", "events.event_date"],
        "dob at fight date", "the two fighters' average age", static=True)
    ctx("c_layoff_max", np.fmax(f.a_days_since_last, f.b_days_since_last) / 365.25, hist_src, HIST,
        "the longer of the two layoffs, in years")
    ctx("c_mkt_conf", np.abs(lc), ["fight_odds(BFO closer)"], MKT, "how lopsided the closing price is")
    ctx("c_overround", f.overround_close, ["fight_odds(BFO closer)"], MKT, "the bookmakers' margin at close")
    ctx("c_abs_move", np.abs(lc - lo), ["fight_odds(BFO opener)", "fight_odds(BFO closer)"], MKT,
        "how much the price moved, either direction")
    ctx("c_era", (f.event_date.dt.year - 2016) / 5.0, ["events.event_date"], BOOK,
        "how recent the fight is (time trend)")

    # --- negative controls: pure noise, antisymmetric, independent of everything --
    rng = np.random.default_rng(seed)
    for i in range(noise_controls):
        anti(f"ctrl_noise_{i:02d}", rng.standard_normal(len(f)), "control", ["(random, seeded)"],
             "independent of all data", "pure noise: should never be discovered")
    return T, specs


def anti_names(specs) -> list[str]:
    return [s.name for s in specs if s.kind == "anti"]


def ctx_names(specs) -> list[str]:
    return [s.name for s in specs if s.kind == "ctx"]
