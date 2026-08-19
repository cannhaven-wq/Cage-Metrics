"""CFL cardio fade-slope model — Step 2: round-observation feature table.

One row per (fight, fighter, round). The time variable is cumulative minutes
elapsed at the MIDPOINT of the round, not the round index: round 3 of a fight
whose first two rounds ended early sits at a different point in the fight than
round 3 of one that went the full ten minutes, and the model should see that.

Output rate is significant strikes ATTEMPTED per minute. Attempted, not landed:
landed folds the opponent's defence into what is meant to measure the fighter's
own work rate.

HARD RULES (enforced here, do not relax downstream):
  * Rounds that did not happen produce no rows. There is no zero-imputation
    anywhere in this file. A fight ending at 2:41 of round 2 yields exactly two
    rows per fighter, the second with round_duration_min = 2.683.
  * Rounds shorter than MIN_ROUND_MIN are dropped - a per-minute rate over a
    40-second denominator is noise.
  * No-contests, DQs and overturned results are excluded entirely.
  * NOTHING derived from finishes enters the feature set. Finishing changes how
    much late-round data a fighter has, which is censoring, not signal. The
    mixed model's partial pooling is what corrects for it.

Usage:  python cfl_engine/cardio/build_features.py [--out path.csv]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from collections import defaultdict

import pandas as pd

# --------------------------------------------------------------------------- config
MIN_ROUND_MIN = 1.0          # drop rounds under 60s (spec: "~60 seconds")
FULL_ROUND_MIN = 5.0
MIN_DIVISION_FIGHTS = 30     # rarer labels collapse to 'Other' (see build_division_label)

# Results that are not a normal contested finish. Their round data either did
# not arise from honest competition (DQ) or the bout was voided (Overturned),
# so they never enter the model.
EXCLUDED_METHODS = {"DQ", "Overturned", "Could Not Continue", "Other", None}

_TIME_RE = re.compile(r"^(\d+):(\d{1,2})$")


# --------------------------------------------------------------------------- io
def _env(name):
    v = os.environ.get(name)
    if not v:
        raise SystemExit(name + " not set in the environment.")
    return v


def fetch_all(path, params):
    """Page through a PostgREST table (1000-row cap per request)."""
    base = _env("SUPABASE_URL").rstrip("/")
    key = _env("SUPABASE_SECRET_KEY")
    headers = {"apikey": key, "Authorization": "Bearer " + key}
    out = []
    offset = 0
    while True:
        p = dict(params)
        p["limit"] = "1000"
        p["offset"] = str(offset)
        req = urllib.request.Request(
            base + "/rest/v1/" + path + "?" + urllib.parse.urlencode(p), headers=headers)
        with urllib.request.urlopen(req) as r:
            batch = json.loads(r.read())
        out.extend(batch)
        if len(batch) < 1000:
            return out
        offset += 1000


# --------------------------------------------------------------------------- helpers
def parse_clock(value):
    """'4:42' -> 4.7 minutes. None when unparseable."""
    if value is None:
        return None
    m = _TIME_RE.match(str(value).strip())
    if not m:
        return None
    return int(m.group(1)) + int(m.group(2)) / 60.0


def round_duration(fight, round_num):
    """True length of one round. None means 'cannot be determined' - drop it.

    A round before the ending round is a full five minutes. The ending round is
    however long the clock says. When the clock is missing we can still infer a
    full round if the fight reached its scheduled distance; otherwise we refuse
    to guess.
    """
    end_round = fight.get("end_round")
    if end_round is None:
        return None
    if round_num < end_round:
        return FULL_ROUND_MIN
    if round_num > end_round:
        return None                      # should not exist; verified it does not
    clock = parse_clock(fight.get("end_time"))
    if clock is not None and clock > 0:
        return clock
    if fight.get("scheduled_rounds") and end_round == fight["scheduled_rounds"]:
        return FULL_ROUND_MIN            # went the distance, clock just missing
    return None


def build_division_label(weight_class, sex):
    """Division label used as the model's fixed-effect covariate.

    Two adaptations the live schema forces:

    1. fights.weight_class does NOT distinguish women's divisions. A women's
       bantamweight bout is stored as 'Bantamweight', identical to a men's one,
       even though the two have very different output rates. fighters.sex
       carries the distinction, so it is folded in here.
    2. The tail of the column is ~90 one-off tournament labels from the 1990s
       and TUF. As fixed-effect levels these are singletons that add a dummy
       column each and estimate nothing, so collapse_rare folds them to 'Other'.
    """
    wc = (weight_class or "Unknown").strip()
    return ("W " + wc) if (sex or "").upper().startswith("F") else wc


def collapse_rare(df, col, min_fights):
    per = df.groupby(col)["fight_id"].nunique()
    keep = set(per[per >= min_fights].index)
    df[col] = df[col].where(df[col].isin(keep), "Other")
    return df


# --------------------------------------------------------------------------- build
def build():
    print("Pulling events, fights, fighters, rounds ...")
    events = {e["id"]: e for e in fetch_all("events", {"select": "id,event_date,is_upcoming"})}
    fights = {f["id"]: f for f in fetch_all(
        "fights", {"select": "id,event_id,fighter_a_id,fighter_b_id,method,"
                             "end_round,end_time,scheduled_rounds,weight_class"})}
    sex_of = {f["id"]: f.get("sex") for f in fetch_all("fighters", {"select": "id,sex"})}
    rounds = fetch_all("fight_rounds", {"select": "fight_id,round_number,fighter_a_id,fighter_b_id,"
                                                  "a_sig_str_attempted,b_sig_str_attempted"})
    print("  events=%d fights=%d fighters=%d round_rows=%d"
          % (len(events), len(fights), len(sex_of), len(rounds)))

    by_fight = defaultdict(list)
    for r in rounds:
        by_fight[r["fight_id"]].append(r)

    records = []
    dropped = defaultdict(int)

    for fight_id, rrows in by_fight.items():
        fight = fights.get(fight_id)
        if fight is None:
            dropped["no_fight_row"] += len(rrows) * 2
            continue
        if fight.get("method") in EXCLUDED_METHODS:
            dropped["excluded_method"] += len(rrows) * 2
            continue
        event = events.get(fight["event_id"])
        if event is None or event.get("is_upcoming"):
            dropped["no_event_or_upcoming"] += len(rrows) * 2
            continue
        fight_date = (event.get("event_date") or "")[:10]
        if not fight_date:
            dropped["no_date"] += len(rrows) * 2
            continue

        rrows = sorted(rrows, key=lambda x: x["round_number"])

        # Walk the fight forward accumulating elapsed time. A round we cannot
        # measure breaks the cumulative clock, so we stop the fight there rather
        # than carry a wrong elapsed time into later rounds.
        elapsed = 0.0
        per_round = []                    # (row, duration, midpoint)
        for rr in rrows:
            dur = round_duration(fight, rr["round_number"])
            if dur is None:
                dropped["undeterminable_duration"] += 2
                break
            per_round.append((rr, dur, elapsed + dur / 2.0))
            elapsed += dur

        division = build_division_label(fight.get("weight_class"),
                                        sex_of.get(fight["fighter_a_id"]))

        for rr, dur, midpoint in per_round:
            if dur < MIN_ROUND_MIN:
                dropped["round_under_60s"] += 2
                continue
            for corner, other in (("a", "b"), ("b", "a")):
                fighter_id = rr["fighter_" + corner + "_id"]
                opponent_id = rr["fighter_" + other + "_id"]
                if fighter_id is None:
                    dropped["missing_fighter_id"] += 1
                    continue
                own = rr.get(corner + "_sig_str_attempted")
                opp = rr.get(other + "_sig_str_attempted")
                if own is None or opp is None:
                    dropped["null_strike_counts"] += 1
                    continue
                records.append({
                    "fight_id": fight_id,
                    "fighter_id": fighter_id,
                    "opponent_id": opponent_id,
                    "round_num": rr["round_number"],
                    "round_duration_min": round(dur, 4),
                    "cumulative_min_midpoint": round(midpoint, 4),
                    "output_rate": own / dur,
                    "opponent_output_rate": opp / dur,
                    "weight_class": division,
                    "fight_date": fight_date,
                    # Phase 2 hook: exponential recency decay drops in here as a
                    # per-observation weight without touching anything else.
                    "obs_weight": 1.0,
                })

    df = pd.DataFrame.from_records(records)
    df = collapse_rare(df, "weight_class", MIN_DIVISION_FIGHTS)
    df = df.sort_values(["fight_date", "fight_id", "fighter_id", "round_num"]).reset_index(drop=True)

    print("\nDropped observations by reason:")
    for k, v in sorted(dropped.items(), key=lambda x: -x[1]):
        print("   %6d  %s" % (v, k))
    return df


def main():
    ap = argparse.ArgumentParser()
    default_out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "round_observations.csv")
    ap.add_argument("--out", default=default_out)
    args = ap.parse_args()

    df = build()
    df.to_csv(args.out, index=False)

    print("\nWrote %d round-observations to %s" % (len(df), args.out))
    print("  fighters      : %d" % df.fighter_id.nunique())
    print("  fights        : %d" % df.fight_id.nunique())
    print("  date range    : %s -> %s" % (df.fight_date.min(), df.fight_date.max()))
    print("  divisions     : %d" % df.weight_class.nunique())
    print("  output_rate   : mean %.2f  median %.2f  max %.1f"
          % (df.output_rate.mean(), df.output_rate.median(), df.output_rate.max()))
    print("  midpoint (min): min %.2f  max %.2f"
          % (df.cumulative_min_midpoint.min(), df.cumulative_min_midpoint.max()))
    print("\n  observations by round:")
    print(df.round_num.value_counts().sort_index().to_string())
    print("\n  observations by division:")
    print(df.weight_class.value_counts().to_string())


if __name__ == "__main__":
    main()
