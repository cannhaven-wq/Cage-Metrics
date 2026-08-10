"""Build the discrete-time duration dataset: one row per (fight, round).

Target product: a fight-DURATION model (how long a 3-round fight lasts /
whether it goes the distance) and the walk-forward harness that judges it.
This module produces the person-period table the hazard model trains on.

WHY WE RECONSTRUCT, NOT JOIN THE VIEWS
--------------------------------------
The brief names v_fighter_style and v_fighter_round_profile as sources.
v_fighter_round_profile does not exist in the live schema, and v_fighter_style
is a *present-day* career aggregate (it carries `sample_fights`/`confidence`
computed over a fighter's whole career). Joining either onto a 2013 fight would
feed post-2013 information into a 2013 prediction -- exactly the career-total
leakage the CLAUDE.md iron rule forbids. So we rebuild both the round-profile
features and the style bucket POINT-IN-TIME here, from fight_rounds, using
strictly-before-date history only, and we reuse v_fighter_style's *formula*
(grapp_score = td*60 + ctrl per round /90 ; strk_score = sig landed per round
/16 ; dominance-ratio buckets) so the definition stays consistent with the site.

STRUCTURE OF THE OUTPUT (discrete-time / person-period)
-------------------------------------------------------
For each qualifying fight we emit one row per round the fight actually reached:
  - a finish in round r  -> rows for rounds 1..r ; event=1 only on row r
  - a decision (went 3)  -> rows for rounds 1,2,3 ; event=0 on all three
The hazard model reads event = P(fight ends this round | it reached this round).

DATA RULES (from CLAUDE.md / cfl_engine):
  - Strictly point-in-time: every feature uses only fights BEFORE event_date.
    History is built over ALL fights (incl. pre-2010 and 5-round bouts) so
    veterans are not treated as debutants; only rows with event_date >= 2010
    and scheduled_rounds == 3 are emitted.
  - Corner side is RANDOMIZED per fight (seeded) before any A-vs-B feature is
    formed. Duration is corner-symmetric, so the model leans on the symmetric
    (mean / abs-diff) features; the signed diffs are provided as specified and
    simply carry little weight after randomization.
  - Low-sample fighters are shrunk toward the league mean (pseudo-minutes prior
    K, default 25, for the round-profile rates; a pseudo-fights prior for the
    fight-history proportions). Debutants therefore inherit the league profile.

Credentials: env SUPABASE_URL + a service key (SUPABASE_SECRET_KEY /
SUPABASE_SERVICE_ROLE_KEY / SUPABASE_SERVICE_KEY). Service key required --
fight_odds is anon-blocked and returns zero rows silently otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import date, datetime
from statistics import median

import numpy as np
import pandas as pd

PAGE = 1000
MIN_YEAR = 2010                # emit rows for fights on/after this event_date
NC_OVERRIDE = ("overturned", "could not continue", "no contest", "other")
ROUND_SECONDS = 300.0          # a full round; used as the per-round minute base

# round-level stats we melt out of fight_rounds (own side) + opp sig for absorbed
ROUND_STATS = ("sig_str_landed", "sig_str_attempted", "td_landed",
               "ctrl_seconds", "kd", "sub_attempts")


# ------------------------------------------------------------------- supabase io
def _env_key() -> str:
    for name in ("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY"):
        if os.environ.get(name):
            return os.environ[name]
    sys.exit("No Supabase service key in env (SUPABASE_SECRET_KEY / "
             "SUPABASE_SERVICE_ROLE_KEY / SUPABASE_SERVICE_KEY).")


def fetch_all(base_url: str, key: str, table: str, params: str) -> list[dict]:
    rows: list[dict] = []
    start = 0
    while True:
        req = urllib.request.Request(
            f"{base_url}/rest/v1/{table}?{params}",
            headers={"apikey": key, "Authorization": f"Bearer {key}",
                     "Range-Unit": "items", "Range": f"{start}-{start + PAGE - 1}"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            page = json.load(resp)
        rows.extend(page)
        if len(page) < PAGE:
            return rows
        start += PAGE


def american_to_prob(odds) -> float:
    if odds is None:
        return float("nan")
    odds = float(odds)
    return 100.0 / (odds + 100.0) if odds > 0 else -odds / (-odds + 100.0)


# ----------------------------------------------------------------- outcome logic
def classify_outcome(method, end_round, sched):
    """Return (kind, finish_round). kind in {'finish','decision','nc','bad'}.

    finish_round is 1..sched for finishes, else None. 'bad'/'nc' rows are not
    emitted and not counted toward fight-history proportions.
    """
    m = (method or "").strip().lower()
    if not m:
        return ("bad", None)
    if any(m.startswith(x) for x in NC_OVERRIDE):
        return ("nc", None)
    if m.startswith("decision") or "draw" in m:
        return ("decision", None)
    # anything else with a real winner is a finish (KO/TKO/Submission/Doctor)
    if end_round is None:
        return ("bad", None)
    r = int(end_round)
    if sched and not (1 <= r <= int(sched)):
        return ("bad", None)
    return ("finish", r)


def result_for(winner_id, a_id, b_id, kind):
    """Win/loss/draw label for a fighter's own history (side-agnostic caller)."""
    if kind == "decision" and winner_id is None:
        return "draw"
    if winner_id == a_id:
        return ("a")
    if winner_id == b_id:
        return ("b")
    return None


# --------------------------------------------------------- per-fighter histories
def build_round_records(rounds, fight_date, fight_corner):
    """Melt fight_rounds -> per (fighter, fight) list of round dicts, chrono.

    Each record: {date, fight_id, round_number, sig_landed, sig_att, sig_absorbed,
    td_landed, ctrl, kd, kd_against, sub_att}. Ordered by (date, fight, round).
    """
    per_fighter: dict[int, list[dict]] = defaultdict(list)
    for r in rounds:
        fid = r["fight_id"]
        d = fight_date.get(fid)
        if d is None:
            continue
        rn = r.get("round_number")
        if rn is None:
            continue
        for me, opp in (("a", "b"), ("b", "a")):
            fighter = r.get(f"fighter_{me}_id")
            if fighter is None:
                continue
            per_fighter[fighter].append({
                "date": d, "fight_id": fid, "round_number": int(rn),
                "sig_landed": r.get(f"{me}_sig_str_landed") or 0,
                "sig_att": r.get(f"{me}_sig_str_attempted") or 0,
                "sig_absorbed": r.get(f"{opp}_sig_str_landed") or 0,
                "td_landed": r.get(f"{me}_td_landed") or 0,
                "ctrl": r.get(f"{me}_ctrl_seconds") or 0,
                "kd": r.get(f"{me}_kd") or 0,
                "kd_against": r.get(f"{opp}_kd") or 0,
                "sub_att": r.get(f"{me}_sub_attempts") or 0,
            })
    for fid in per_fighter:
        per_fighter[fid].sort(key=lambda x: (x["date"], x["fight_id"], x["round_number"]))
    return per_fighter


def build_fight_history(fights, fight_date):
    """Per-fighter chronological list of prior *fights* with outcome flags."""
    per_fighter: dict[int, list[dict]] = defaultdict(list)
    for f in fights:
        d = fight_date.get(f["id"])
        if d is None:
            continue
        kind, fr = classify_outcome(f["method"], f["end_round"], f["scheduled_rounds"])
        for me in ("a", "b"):
            fighter = f[f"fighter_{me}_id"]
            if fighter is None:
                continue
            res = result_for(f["winner_id"], f["fighter_a_id"], f["fighter_b_id"], kind)
            won = None if res is None else (res == me)
            per_fighter[fighter].append({
                "date": d, "fight_id": f["id"], "kind": kind, "won": won,
                "end_round": f["end_round"], "sched": f["scheduled_rounds"],
            })
    for fid in per_fighter:
        per_fighter[fid].sort(key=lambda x: (x["date"], x["fight_id"]))
    return per_fighter


# ------------------------------------------------------------- league priors
def league_priors(round_recs, K, K_slope):
    """Global per-minute rates + mean decay slope, used as shrinkage priors.

    A prior is a fixed constant, not a per-fight value -- it carries no outcome
    information about any specific fight, so using a global mean here does not
    breach point-in-time (the per-fighter accumulation below is what must be,
    and is, strictly-before-date).
    """
    tot = defaultdict(float)
    tot_min = 0.0
    tot_ctrl_den = 0.0
    slopes, n_slopes = [], 0
    gslopes = []
    for recs in round_recs.values():
        for x in recs:
            tot["sig_landed"] += x["sig_landed"]
            tot["sig_absorbed"] += x["sig_absorbed"]
            tot["td_landed"] += x["td_landed"]
            tot["ctrl"] += x["ctrl"]
            tot["kd"] += x["kd"]
            tot["kd_against"] += x["kd_against"]
            tot["sub_att"] += x["sub_att"]
        tot_min += len(recs) * (ROUND_SECONDS / 60.0)
        tot_ctrl_den += len(recs) * ROUND_SECONDS
    pri = {
        "sig_landed_pm": tot["sig_landed"] / tot_min if tot_min else 0.0,
        "sig_absorbed_pm": tot["sig_absorbed"] / tot_min if tot_min else 0.0,
        "td_pm": tot["td_landed"] / tot_min if tot_min else 0.0,
        "kd_pm": tot["kd"] / tot_min if tot_min else 0.0,
        "kd_against_pm": tot["kd_against"] / tot_min if tot_min else 0.0,
        "sub_pm": tot["sub_att"] / tot_min if tot_min else 0.0,
        "ctrl_pct": tot["ctrl"] / tot_ctrl_den if tot_ctrl_den else 0.0,
    }
    # league mean decay slopes (strike + grapple), sig vs round_number
    for recs in round_recs.values():
        if len(recs) >= 3:
            rn = np.array([x["round_number"] for x in recs], float)
            if rn.max() > rn.min():
                sig = np.array([x["sig_landed"] for x in recs], float)
                grap = np.array([x["td_landed"] * 60 + x["ctrl"] for x in recs], float)
                slopes.append(np.polyfit(rn, sig, 1)[0])
                gslopes.append(np.polyfit(rn, grap, 1)[0])
    pri["strike_decay"] = float(np.mean(slopes)) if slopes else 0.0
    pri["grap_decay"] = float(np.mean(gslopes)) if gslopes else 0.0
    return pri


def league_fight_rates(fight_hist):
    """Global finish-win / finish-loss / decision / win rates + mean end_round."""
    fw = fl = dec = win = n = 0
    end_sum = end_n = 0
    for recs in fight_hist.values():
        for x in recs:
            if x["kind"] not in ("finish", "decision"):
                continue
            n += 1
            if x["won"]:
                win += 1
            if x["kind"] == "decision":
                dec += 1
            elif x["won"]:
                fw += 1
            elif x["won"] is False:
                fl += 1
            if x["end_round"] is not None:
                end_sum += int(x["end_round"]); end_n += 1
    return {
        "finish_win_rate": fw / n if n else 0.0,
        "finish_loss_rate": fl / n if n else 0.0,
        "decision_rate": dec / n if n else 0.0,
        "win_rate": win / n if n else 0.0,
        "avg_end_round": end_sum / end_n if end_n else 2.5,
    }


# --------------------------------------------- point-in-time feature snapshots
def round_profile_asof(prior_recs, pri, K, K_slope):
    """PIT round-profile feature dict from a fighter's strictly-prior rounds."""
    n = len(prior_recs)
    minutes = n * (ROUND_SECONDS / 60.0)
    ctrl_den = n * ROUND_SECONDS
    s = defaultdict(float)
    for x in prior_recs:
        for k in ("sig_landed", "sig_absorbed", "td_landed", "ctrl", "kd",
                  "kd_against", "sub_att"):
            s[k] += x[k]

    def shrink_pm(total, prior_rate):
        return (total + K * prior_rate) / (minutes + K)

    out = {
        "rp_sig_landed_pm": shrink_pm(s["sig_landed"], pri["sig_landed_pm"]),
        "rp_sig_absorbed_pm": shrink_pm(s["sig_absorbed"], pri["sig_absorbed_pm"]),
        "rp_td_pm": shrink_pm(s["td_landed"], pri["td_pm"]),
        "rp_kd_pm": shrink_pm(s["kd"], pri["kd_pm"]),
        "rp_kd_against_pm": shrink_pm(s["kd_against"], pri["kd_against_pm"]),
        "rp_sub_pm": shrink_pm(s["sub_att"], pri["sub_pm"]),
        # control % shrunk in seconds units (K minutes -> K*60 seconds prior)
        "rp_ctrl_pct": (s["ctrl"] + K * 60.0 * pri["ctrl_pct"]) / (ctrl_den + K * 60.0),
        "rp_n_rounds": float(n),
    }
    out["rp_pace_pm"] = out["rp_sig_landed_pm"] + out["rp_sig_absorbed_pm"]

    # decay slopes, shrunk toward league slope by round count
    def decay(key_fn, prior_slope):
        if n >= 3:
            rn = np.array([x["round_number"] for x in prior_recs], float)
            if rn.max() > rn.min():
                y = np.array([key_fn(x) for x in prior_recs], float)
                sl = float(np.polyfit(rn, y, 1)[0])
                w = n / (n + K_slope)
                return w * sl + (1 - w) * prior_slope
        return prior_slope

    out["rp_strike_decay"] = decay(lambda x: x["sig_landed"], pri["strike_decay"])
    out["rp_grap_decay"] = decay(lambda x: x["td_landed"] * 60 + x["ctrl"], pri["grap_decay"])
    return out


def style_asof(prior_recs):
    """PIT grappler/striker/hybrid via v_fighter_style's R1 dominance formula."""
    r1 = [x for x in prior_recs if x["round_number"] == 1]
    if len(r1) < 2:                       # view requires r1_minutes >= 10
        return "unknown"
    n = len(r1)
    grapp = np.mean([x["td_landed"] * 60 + x["ctrl"] for x in r1]) / 90.0
    strk = np.mean([x["sig_landed"] for x in r1]) / 16.0
    if grapp >= 1.0 and strk >= 1.0 and grapp < 2 * strk and strk < 2 * grapp:
        return "hybrid"
    if grapp >= 1.0 and grapp >= 2 * strk:
        return "grappler"
    if strk >= 1.0 and strk >= 2 * grapp:
        return "striker"
    return "hybrid" if (grapp >= 1.0 and strk >= 1.0) else "unknown"


def fight_history_asof(prior_fights, lr, K_fights):
    """PIT fight-history proportions (shrunk toward league) + streak."""
    clean = [x for x in prior_fights if x["kind"] in ("finish", "decision")]
    n = len(clean)
    fw = sum(1 for x in clean if x["kind"] == "finish" and x["won"])
    fl = sum(1 for x in clean if x["kind"] == "finish" and x["won"] is False)
    dec = sum(1 for x in clean if x["kind"] == "decision")
    win = sum(1 for x in clean if x["won"])
    ers = [int(x["end_round"]) for x in clean if x["end_round"] is not None]

    def shrink(k_count, prior_p):
        return (k_count + K_fights * prior_p) / (n + K_fights)

    out = {
        "fh_finish_win_rate": shrink(fw, lr["finish_win_rate"]),
        "fh_finish_loss_rate": shrink(fl, lr["finish_loss_rate"]),
        "fh_decision_rate": shrink(dec, lr["decision_rate"]),
        "fh_win_rate": shrink(win, lr["win_rate"]),
        "fh_avg_end_round": ((sum(ers) + K_fights * lr["avg_end_round"])
                             / (len(ers) + K_fights)) if (ers or True) else lr["avg_end_round"],
        "fh_n_fights": float(n),
    }
    streak = 0.0
    for x in reversed(clean):
        if x["won"] is None:              # draw breaks the streak
            break
        cur = 1.0 if x["won"] else -1.0
        if streak == 0.0:
            streak = cur
        elif (streak > 0) == x["won"]:
            streak += np.sign(streak)
        else:
            break
    out["fh_streak"] = streak
    return out


# ---------------------------------------------------------------- assembly
def stance_flag(stance):
    if stance is None:
        return None
    s = str(stance).strip().lower()
    return s if s in ("orthodox", "southpaw", "switch") else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    here = os.path.dirname(__file__)
    ap.add_argument("--out", default=os.path.join(here, "duration_features.parquet"))
    ap.add_argument("--manifest", default=os.path.join(here, "feature_manifest.json"))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--K", type=float, default=25.0,
                    help="pseudo-minutes shrinkage prior for round-profile rates")
    ap.add_argument("--K-slope", type=float, default=8.0,
                    help="pseudo-rounds shrinkage prior for decay slopes")
    ap.add_argument("--K-fights", type=float, default=5.0,
                    help="pseudo-fights shrinkage prior for fight-history rates")
    args = ap.parse_args()

    base_url = os.environ["SUPABASE_URL"].rstrip("/")
    key = _env_key()

    print("pulling events, fighters, fights, fight_rounds, closing odds ...")
    events = fetch_all(base_url, key, "events", "select=id,event_date,is_upcoming&order=id")
    fighters = fetch_all(base_url, key, "fighters",
                         "select=id,name,dob,height_in,reach_in,stance&order=id")
    fight_cols = ("id,event_id,fighter_a_id,fighter_b_id,winner_id,method,"
                  "weight_class,scheduled_rounds,end_round,end_time")
    fights = fetch_all(base_url, key, "fights", f"select={fight_cols}&order=id")
    round_cols = ("fight_id,fighter_a_id,fighter_b_id,round_number,"
                  + ",".join(f"{s}_{stem}" for stem in ROUND_STATS for s in ("a", "b")))
    rounds = fetch_all(base_url, key, "fight_rounds", f"select={round_cols}&order=id")
    odds = fetch_all(base_url, key, "fight_odds",
                     "select=fight_id,fighter_id,american_odds,implied_prob,captured_at"
                     "&is_closer=eq.true&order=id")
    print(f"  events={len(events)} fighters={len(fighters)} fights={len(fights)} "
          f"round_rows={len(rounds)} closer_odds={len(odds)}")

    ev = {e["id"]: e for e in events}
    fight_date, upcoming = {}, set()
    for f in fights:
        e = ev.get(f["event_id"])
        if e and e["event_date"] and not e["is_upcoming"]:
            fight_date[f["id"]] = pd.Timestamp(e["event_date"])
        elif e and e["is_upcoming"]:
            upcoming.add(f["id"])

    # closing devig favorite prob per fight (for the harness market benchmark)
    by_fighter: dict[tuple, list[float]] = defaultdict(list)
    corners = {f["id"]: (f["fighter_a_id"], f["fighter_b_id"]) for f in fights}
    for r in odds:
        p = r["implied_prob"]
        if p is None and r["american_odds"] is not None:
            p = american_to_prob(r["american_odds"])
        c = corners.get(r["fight_id"])
        if p is None or not (0.0 < float(p) < 1.0) or c is None or r["fighter_id"] not in c:
            continue
        by_fighter[(r["fight_id"], r["fighter_id"])].append(float(p))
    fav_prob = {}                          # fight_id -> devigged favorite prob (>=0.5)
    for fid, (a, b) in corners.items():
        pa = by_fighter.get((fid, a)); pb = by_fighter.get((fid, b))
        if pa and pb:
            ma, mb = median(pa), median(pb)
            if ma + mb > 0:
                da = ma / (ma + mb)
                fav_prob[fid] = max(da, 1 - da)

    # per-fighter chronological histories (over ALL fights, incl. pre-2010 / 5rd)
    round_recs = build_round_records(rounds, fight_date, corners)
    fight_hist = build_fight_history(fights, fight_date)
    pri = league_priors(round_recs, args.K, args.K_slope)
    lr = league_fight_rates(fight_hist)
    print(f"  league priors: sig_landed_pm={pri['sig_landed_pm']:.2f} "
          f"pace_pm={pri['sig_landed_pm']+pri['sig_absorbed_pm']:.2f} "
          f"strike_decay={pri['strike_decay']:.3f}")
    print(f"  league fight rates: finish_win={lr['finish_win_rate']:.3f} "
          f"finish_loss={lr['finish_loss_rate']:.3f} decision={lr['decision_rate']:.3f} "
          f"avg_end_round={lr['avg_end_round']:.2f}")

    # index each fighter's own fights by fight_id -> position, for prefix slicing
    fight_pos = {fid: {x["fight_id"]: i for i, x in enumerate(recs)}
                 for fid, recs in fight_hist.items()}
    # index round records by (fighter, fight) -> first index (rounds are contiguous)
    round_start: dict[int, dict] = {}
    for fid, recs in round_recs.items():
        d = {}
        for i, x in enumerate(recs):
            d.setdefault(x["fight_id"], i)
        round_start[fid] = d

    fmeta = {f["id"]: f for f in fighters}

    def feats_asof(fighter_id, fight_id, when):
        prior_r = []
        rr = round_recs.get(fighter_id)
        if rr:
            cut = round_start.get(fighter_id, {}).get(fight_id, len(rr))
            prior_r = rr[:cut]              # strictly-before this fight's rounds
        prior_f = []
        fh = fight_hist.get(fighter_id)
        if fh:
            pos = fight_pos[fighter_id].get(fight_id, len(fh))
            prior_f = fh[:pos]
        d = {}
        d.update(round_profile_asof(prior_r, pri, args.K, args.K_slope))
        d.update(fight_history_asof(prior_f, lr, args.K_fights))
        d["style"] = style_asof(prior_r)
        meta = fmeta.get(fighter_id, {})
        dob = meta.get("dob")
        d["age"] = ((when - pd.Timestamp(dob)).days / 365.25) if dob else np.nan
        d["reach_in"] = pd.to_numeric(meta.get("reach_in"), errors="coerce")
        d["height_in"] = pd.to_numeric(meta.get("height_in"), errors="coerce")
        d["stance"] = stance_flag(meta.get("stance"))
        return d

    # -------- emit qualifying fights (sched==3, >=2010, clean finish/decision)
    rng = np.random.default_rng(args.seed)
    # NOTE deliberate omissions to avoid exact/near collinearity (which explodes
    # the Wald CIs without helping prediction):
    #   - rp_pace_pm == rp_sig_landed_pm + rp_sig_absorbed_pm exactly -> keep the
    #     two components in diffs, keep pace only as a mean feature.
    #   - fh_finish_win + fh_finish_loss + fh_decision ~= 1 -> drop fh_decision_rate;
    #     avg_end_round already carries the "goes-long" signal distinctly.
    RATE_FEATS = ["rp_sig_landed_pm", "rp_sig_absorbed_pm", "rp_td_pm",
                  "rp_ctrl_pct", "rp_kd_pm", "rp_kd_against_pm", "rp_sub_pm",
                  "rp_strike_decay", "rp_grap_decay", "fh_finish_win_rate",
                  "fh_finish_loss_rate", "fh_win_rate",
                  "fh_avg_end_round", "fh_streak", "age", "reach_in", "height_in"]
    MEAN_FEATS = ["rp_pace_pm", "rp_kd_pm", "rp_kd_against_pm", "rp_sub_pm", "rp_td_pm",
                  "rp_ctrl_pct", "rp_strike_decay", "rp_grap_decay",
                  "fh_finish_win_rate", "fh_finish_loss_rate",
                  "fh_avg_end_round", "fh_win_rate", "fh_n_fights", "age"]
    ABS_FEATS = ["age", "reach_in", "height_in", "fh_win_rate", "rp_pace_pm",
                 "fh_finish_win_rate"]
    STANCES = ["orthodox", "southpaw", "switch"]
    STYLES = ["grappler", "striker", "hybrid"]

    excluded = defaultdict(int)
    fight_rows = []
    for f in fights:
        if f["scheduled_rounds"] != 3:
            excluded["not_sched3"] += 1; continue
        if f["id"] in upcoming:
            excluded["upcoming"] += 1; continue
        when = fight_date.get(f["id"])
        if when is None:
            excluded["no_event_date"] += 1; continue
        if when.year < MIN_YEAR:
            excluded["pre_2010"] += 1; continue
        kind, fr = classify_outcome(f["method"], f["end_round"], f["scheduled_rounds"])
        if kind == "nc":
            excluded["no_contest"] += 1; continue
        if kind == "bad":
            excluded["bad_method_or_round"] += 1; continue
        a_id, b_id = f["fighter_a_id"], f["fighter_b_id"]
        if a_id is None or b_id is None:
            excluded["missing_corner"] += 1; continue

        # RANDOMIZE side assignment BEFORE building any A-vs-B feature
        if rng.random() < 0.5:
            a_id, b_id = b_id, a_id
        fa = feats_asof(a_id, f["id"], when)
        fb = feats_asof(b_id, f["id"], when)

        row = {
            "fight_id": f["id"], "event_date": when, "weight_class": f["weight_class"],
            "outcome_kind": kind, "finish_round": fr,
            "reached": (fr if kind == "finish" else 3),
            "went_distance": 1 if kind == "decision" else 0,
            "fav_prob": fav_prob.get(f["id"], np.nan),
            "fighter_a_id": a_id, "fighter_b_id": b_id,
        }
        # signed diffs (as specified) + symmetric means + abs-diffs (duration signal)
        for k in RATE_FEATS:
            row[f"d_{k}"] = fa[k] - fb[k]
        for k in MEAN_FEATS:
            row[f"m_{k}"] = (fa[k] + fb[k]) / 2.0
        for k in ABS_FEATS:
            row[f"ad_{k}"] = abs(fa[k] - fb[k])
        # stance matchup (unordered one-hot; unknown -> all zero baseline)
        sp = tuple(sorted([fa["stance"] or "unk", fb["stance"] or "unk"]))
        for i, s1 in enumerate(STANCES):
            for s2 in STANCES[i:]:
                row[f"stance_{s1[:3]}_{s2[:3]}"] = 1.0 if sp == tuple(sorted([s1, s2])) else 0.0
        # style matchup (unordered one-hot; unknown -> all zero baseline)
        yp = tuple(sorted([fa["style"], fb["style"]]))
        for i, y1 in enumerate(STYLES):
            for y2 in STYLES[i:]:
                row[f"style_{y1[:4]}_{y2[:4]}"] = 1.0 if yp == tuple(sorted([y1, y2])) else 0.0
        row["a_style"], row["b_style"] = fa["style"], fb["style"]
        fight_rows.append(row)

    if not fight_rows:
        sys.exit(f"No fights survived filtering. excluded={dict(excluded)}")
    fdf = pd.DataFrame(fight_rows).sort_values(["event_date", "fight_id"]).reset_index(drop=True)

    # -------- expand fights -> person-period rows (one per round reached)
    feat_cols = [c for c in fdf.columns if c.startswith(("d_", "m_", "ad_", "stance_", "style_"))]
    pp_rows = []
    for r in fdf.itertuples(index=False):
        rd = r._asdict()
        for rnum in range(1, rd["reached"] + 1):
            event = 1 if (rd["outcome_kind"] == "finish" and rnum == rd["finish_round"]) else 0
            pr = {"fight_id": rd["fight_id"], "event_date": rd["event_date"],
                  "round": rnum, "event": event,
                  "r1": 1.0 if rnum == 1 else 0.0, "r2": 1.0 if rnum == 2 else 0.0,
                  "r3": 1.0 if rnum == 3 else 0.0,
                  "weight_class": rd["weight_class"], "fav_prob": rd["fav_prob"],
                  "went_distance": rd["went_distance"], "reached": rd["reached"],
                  "finish_round": rd["finish_round"], "outcome_kind": rd["outcome_kind"]}
            for c in feat_cols:
                pr[c] = rd[c]
            pp_rows.append(pr)
    pp = pd.DataFrame(pp_rows)

    # median-impute numeric covariates that are still NaN (age/reach/height gaps);
    # dummies/means are complete because shrinkage backfills debutants.
    cov_cols = [c for c in feat_cols]
    med = pp[cov_cols].median(numeric_only=True)
    pp[cov_cols] = pp[cov_cols].fillna(med)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    pp.to_parquet(args.out, index=False)

    manifest = {
        "generated_at_utc": datetime.utcnow().isoformat() + "Z",
        "source": "supabase: fights, fight_rounds, fighters, events, fight_odds",
        "note_on_views": ("v_fighter_round_profile absent and v_fighter_style is a "
                          "present-day career aggregate; both reconstructed POINT-IN-TIME "
                          "from fight_rounds to avoid career-total leakage. Style uses "
                          "v_fighter_style's R1 dominance formula."),
        "row_grain": "one row per (fight, round reached) -- discrete-time person-period",
        "target": "event = 1 if the fight ends (finish) in this round else 0",
        "filters": {"scheduled_rounds": 3, "min_event_year": MIN_YEAR,
                    "excluded_outcomes": "no_contest / overturned / could_not_continue / bad"},
        "point_in_time": "all features use only fights strictly before event_date",
        "corner_randomization_seed": args.seed,
        "shrinkage": {"round_profile_pseudo_minutes_K": args.K,
                      "decay_slope_pseudo_rounds_K": args.K_slope,
                      "fight_history_pseudo_fights_K": args.K_fights},
        "league_priors": pri, "league_fight_rates": lr,
        "n_fights": int(fdf.shape[0]), "n_person_period_rows": int(pp.shape[0]),
        "round_dummies": ["r1", "r2", "r3"],
        "covariate_columns": cov_cols,
        "passthrough_columns": ["fight_id", "event_date", "round", "event",
                                "weight_class", "fav_prob", "went_distance",
                                "reached", "finish_round", "outcome_kind"],
        "excluded_counts": dict(excluded),
        "outcome_distribution": fdf["outcome_kind"].value_counts().to_dict(),
        "finish_round_distribution": fdf[fdf.outcome_kind == "finish"]
            ["finish_round"].value_counts().sort_index().to_dict(),
        "gtd_rate": float(fdf["went_distance"].mean()),
        "fav_prob_coverage": float(fdf["fav_prob"].notna().mean()),
    }
    with open(args.manifest, "w") as fh:
        json.dump(manifest, fh, indent=2, default=str)

    print(f"\nwrote {pp.shape[0]} person-period rows over {fdf.shape[0]} fights -> {args.out}")
    print(f"  manifest -> {args.manifest}")
    print(f"  covariates: {len(cov_cols)} | GTD rate: {manifest['gtd_rate']:.3f} "
          f"| odds coverage: {manifest['fav_prob_coverage']:.1%}")
    print(f"  outcome dist: {manifest['outcome_distribution']}")
    print(f"  finish-round dist: {manifest['finish_round_distribution']}")
    print(f"  excluded: {dict(excluded)}")


if __name__ == "__main__":
    main()
