"""Load the committed DEV export and turn it into the engine's data contract.

The export (research/discovery/data/dev/) was produced read-only with
research/discovery/export_dev.sql, which filters event_date < 2025-01-01 in
SQL. This loader then passes every row through PRED-001's dev_only(), which
RAISES on a sealed date rather than dropping it, and checks the priced subset
against the frozen holdout manifest's DEV fingerprints. A file that drifted,
or that someone extended past 2024, is refused rather than silently used.
"""
from __future__ import annotations

import hashlib
import json
import math
import pathlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import DISCOVERY_DIR
import pred_protocol as pp  # frozen PRED-001 rules (research/protocol)
from clv.devig import power_devig, shin_devig  # frozen CLV-001 helpers (cfl_engine/clv)

DEV_DATA = DISCOVERY_DIR / "data" / "dev"

# The two DEV fingerprints frozen in research/protocol/holdout_manifest.json.
# Recomputed from the export on every load.
MANIFEST_DEV = pp.MANIFEST["partitions"]["DEV"]

STAT_STEMS = ["kd", "sig_landed", "sig_attempted", "td_landed", "td_attempted",
              "sub_attempts", "rev", "ctrl_seconds", "head_landed", "body_landed",
              "leg_landed", "distance_landed", "clinch_landed", "ground_landed"]

# Weight limits in pounds, for "moving up / down a division". Anything not
# listed (tournaments, open weight, catch weight) has no limit and yields NaN.
WEIGHT_LIMIT = {
    "Strawweight": 115, "Women's Strawweight": 115, "Flyweight": 125,
    "Women's Flyweight": 125, "Bantamweight": 135, "Women's Bantamweight": 135,
    "Featherweight": 145, "Women's Featherweight": 145, "Lightweight": 155,
    "Welterweight": 170, "Middleweight": 185, "Light Heavyweight": 205,
    "Heavyweight": 265,
}
NC_METHODS = ("overturned", "could not continue", "no contest", "other")


@dataclass
class DevData:
    fights: pd.DataFrame      # one row per DEV fight, original corner order
    fighters: pd.DataFrame    # static profile values (allowed with caveat, PRED-001 s3)
    sha256: dict              # file -> sha256 of the bytes loaded
    manifest_check: dict      # recomputed DEV fingerprints vs the frozen ones


def file_sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seconds(end_round, end_time) -> float:
    """Elapsed fight time from the official end round and clock."""
    try:
        r = int(end_round)
        m, s = str(end_time).split(":")
        return (r - 1) * 300.0 + int(m) * 60.0 + int(s)
    except (TypeError, ValueError):
        return float("nan")


def result_of(winner: str, method: str) -> str:
    """a / b / draw / nc. Scoring eligibility follows PRED-001 exactly (winner
    set to one corner); this label is only used for building HISTORY."""
    m = (method or "").lower()
    if winner in ("a", "b"):
        return winner
    if m.startswith(NC_METHODS):
        return "nc"
    return "draw" if m.startswith("decision") else "nc"


def implied(american) -> float:
    if american is None or (isinstance(american, float) and math.isnan(american)):
        return float("nan")
    return pp.american_to_implied(float(american))


def devig_all(american_a, american_b) -> tuple[float, float, float]:
    """(proportional, power, Shin) vig-free probability of corner A.
    Proportional is PRED-001's primary; the other two are sensitivities."""
    if pd.isna(american_a) or pd.isna(american_b):
        return (np.nan, np.nan, np.nan)
    ia, ib = implied(american_a), implied(american_b)
    prop = pp.devig_proportional(float(american_a), float(american_b))
    try:
        pw = power_devig(ia, ib)[0]
    except ValueError:
        pw = np.nan
    try:
        sh = shin_devig(ia, ib)[0]
    except ValueError:
        sh = np.nan
    return prop, pw, sh


def check_manifest(fights: pd.DataFrame) -> dict:
    """Recompute PRED-001's DEV priced fingerprints from the export."""
    el = fights[fights.winner.isin(["a", "b"]) & fights.bfo_close_a.notna()
                & fights.bfo_close_b.notna() & (fights.is_active != 0)]
    ids = sorted(int(i) for i in el.fight_id)
    ya = dict(zip(el.fight_id.astype(int), (el.winner == "a").astype(int)))
    got = {
        "decided_priced": len(ids),
        "events_priced": int(el.event_id.nunique()),
        "priced_ids_sha256": hashlib.sha256(",".join(map(str, ids)).encode()).hexdigest(),
        "priced_outcomes_sha256": hashlib.sha256(
            ",".join(f"{i}:{ya[i]}" for i in ids).encode()).hexdigest(),
    }
    want = {k: MANIFEST_DEV[k] for k in got}
    return {"recomputed": got, "frozen": want, "match": got == want}


def load_dev(data_dir: pathlib.Path = DEV_DATA, *, require_manifest: bool = True) -> DevData:
    data_dir = pathlib.Path(data_dir)
    fpath, xpath = data_dir / "fights.csv", data_dir / "fighters.csv"
    fights = pd.read_csv(fpath, dtype={"winner": str, "method": str, "end_time": str,
                                       "weight_class": str}, keep_default_na=False,
                         na_values={c: [""] for c in ("end_round", "scheduled_rounds",
                                                      "bfo_open_a", "bfo_open_b",
                                                      "bfo_close_a", "bfo_close_b",
                                                      "is_title_fight", "is_main_event",
                                                      "bout_order", "is_active")
                                    + tuple(f"{s}_{k}" for k in STAT_STEMS for s in "ab")})
    # The PRED-001 guard. It raises on the first sealed row instead of
    # filtering, so an export that asked for 2025 cannot look fine.
    pp.dev_only(fights.to_dict("records"), date_key="event_date")
    fighters = pd.read_csv(xpath, dtype={"stance": str, "sex": str, "dob": str},
                           keep_default_na=False, na_values={"height_in": [""], "reach_in": [""]})
    check = check_manifest(fights) if require_manifest else {"match": None, "skipped": True}
    if require_manifest and not check["match"]:
        raise ValueError(f"DEV export does not match the frozen PRED-001 manifest: {check}")
    return DevData(fights=fights, fighters=fighters,
                   sha256={"fights.csv": file_sha256(fpath), "fighters.csv": file_sha256(xpath)},
                   manifest_check=check)


def prepare(dev: DevData) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (fights, stats, fighters) in cfl_engine's 3-CSV contract, plus
    the discovery columns (market, context) on `fights`."""
    f = dev.fights.copy()
    f["event_date"] = pd.to_datetime(f["event_date"])
    f["result"] = [result_of(w, m) for w, m in zip(f.winner, f.method)]
    f["n_rounds_sched"] = pd.to_numeric(f["scheduled_rounds"], errors="coerce")
    f["fight_seconds"] = [_seconds(r, t) for r, t in zip(f.end_round, f.end_time)]
    f["odds_a"], f["odds_b"] = f["bfo_close_a"], f["bfo_close_b"]
    dv = [devig_all(a, b) for a, b in zip(f.bfo_close_a, f.bfo_close_b)]
    f["q_close"] = [d[0] for d in dv]
    f["q_close_power"] = [d[1] for d in dv]
    f["q_close_shin"] = [d[2] for d in dv]
    f["q_open"] = [devig_all(a, b)[0] for a, b in zip(f.bfo_open_a, f.bfo_open_b)]
    f["overround_close"] = [implied(a) + implied(b) - 1.0 if pd.notna(a) and pd.notna(b) else np.nan
                            for a, b in zip(f.bfo_close_a, f.bfo_close_b)]
    f["overround_open"] = [implied(a) + implied(b) - 1.0 if pd.notna(a) and pd.notna(b) else np.nan
                           for a, b in zip(f.bfo_open_a, f.bfo_open_b)]
    f["wc_limit"] = f["weight_class"].map(WEIGHT_LIMIT).astype(float)
    f["is_scorable"] = (f.winner.isin(["a", "b"]) & f.q_close.notna()
                        & (f.is_active.fillna(1) != 0)).astype(bool)
    f["y"] = (f.winner == "a").astype(float)
    f = f.sort_values(["event_date", "fight_id"]).reset_index(drop=True)

    # One stats row per (fight, fighter). Fights with no recorded totals get
    # no row, so they add no zeros to anyone's rates (the engine fills a
    # missing row's numbers with 0, which would read as a fight with no
    # output at all).
    rows = []
    for r in f.itertuples(index=False):
        if pd.isna(getattr(r, "a_sig_landed")):
            continue
        for me, them, s, o in ((r.fighter_a_id, r.fighter_b_id, "a", "b"),
                               (r.fighter_b_id, r.fighter_a_id, "b", "a")):
            rows.append({
                "fight_id": r.fight_id, "fighter_id": me,
                "sig_landed": getattr(r, f"{s}_sig_landed"),
                "sig_attempted": getattr(r, f"{s}_sig_attempted"),
                "td_landed": getattr(r, f"{s}_td_landed"),
                "td_attempted": getattr(r, f"{s}_td_attempted"),
                "sub_attempts": getattr(r, f"{s}_sub_attempts"),
                "knockdowns": getattr(r, f"{s}_kd"),
                "control_seconds": getattr(r, f"{s}_ctrl_seconds"),
                "fight_seconds": r.fight_seconds,
            })
    stats = pd.DataFrame(rows)
    fighters = dev.fighters.rename(columns={}).copy()
    fighters["dob"] = pd.to_datetime(fighters["dob"].replace("", None), errors="coerce")
    return f, stats, fighters
