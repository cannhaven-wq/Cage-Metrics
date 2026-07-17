"""Export Supabase data to the three CSVs of the cfl_engine data contract.

Produces (in --outdir, default cfl_engine/data/):
  fights.csv       one row per completed fight: fight_id, event_date,
                   fighter_a_id, fighter_b_id, result, weight_class,
                   n_rounds_sched, method, odds_a, odds_b
  fight_stats.csv  one row per (fight, fighter): sig/td/sub/kd/control totals
  fighters.csv     fighter_id, name, dob

Sources (live schema, verified 2026-07-16):
  fights           per-fight totals in wide a_/b_ columns + winner_id/method
  fight_rounds     per-round wide a_/b_ columns -- cross-checks the fight-level
                   totals and backfills corners whose totals are null
  events           event_date, is_upcoming
  fight_odds       BestFightOdds capture; closing = is_closer rows, keyed by
                   fighter_id (never by the capture's side convention),
                   consensus = median implied prob across books per fighter
  fighters         id, name, dob

Result mapping, in precedence order:
  method Overturned / Could Not Continue / No Contest / Other -> nc, even if a
  stale winner_id survives in the row (vacated results must not train as wins);
  winner_id -> a/b; winnerless 'Decision - *' -> draw; winnerless finish or
  missing method or missing event_date or event is_upcoming -> excluded, counted.

Credentials come from env vars SUPABASE_URL and SUPABASE_SECRET_KEY (falls back
to SUPABASE_SERVICE_ROLE_KEY / SUPABASE_SERVICE_KEY). The service key is
required: fight_odds is anon-blocked and returns zero rows silently otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from statistics import median

import pandas as pd

PAGE = 1000

STAT_KEYS = {  # contract column -> fights/fight_rounds wide-column stem
    "sig_landed": "sig_str_landed",
    "sig_attempted": "sig_str_attempted",
    "td_landed": "td_landed",
    "td_attempted": "td_attempted",
    "sub_attempts": "sub_attempts",
    "knockdowns": "kd",
    "control_seconds": "ctrl_seconds",
}

NC_OVERRIDE = ("overturned", "could not continue", "no contest", "other")


def _env_key() -> str:
    for name in ("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY"):
        if os.environ.get(name):
            return os.environ[name]
    sys.exit("No Supabase service key found in env (SUPABASE_SECRET_KEY / "
             "SUPABASE_SERVICE_ROLE_KEY / SUPABASE_SERVICE_KEY).")


def fetch_all(base_url: str, key: str, table: str, params: str) -> list[dict]:
    """Page through PostgREST with Range headers until a short page."""
    rows: list[dict] = []
    start = 0
    while True:
        req = urllib.request.Request(
            f"{base_url}/rest/v1/{table}?{params}",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Range-Unit": "items",
                "Range": f"{start}-{start + PAGE - 1}",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            page = json.load(resp)
        rows.extend(page)
        if len(page) < PAGE:
            return rows
        start += PAGE


def prob_to_american(p: float) -> int:
    """Invert implied probability back to American odds (with vig intact)."""
    if p >= 0.5:
        return round(-100.0 * p / (1.0 - p))
    return round(100.0 * (1.0 - p) / p)


def american_to_prob(odds: float) -> float:
    odds = float(odds)
    return 100.0 / (odds + 100.0) if odds > 0 else -odds / (-odds + 100.0)


def map_result(winner_id, fighter_a_id, fighter_b_id, method):
    """Returns 'a'/'b'/'draw'/'nc', or (None, reason) to exclude the row."""
    m = (method or "").strip().lower()
    if any(m.startswith(x) for x in NC_OVERRIDE):
        return "nc"  # vacated/aborted results override any stale winner_id
    if winner_id is not None:
        if winner_id == fighter_a_id:
            return "a"
        if winner_id == fighter_b_id:
            return "b"
        return (None, "winner_not_in_corners")
    if not m:
        return (None, "no_result")
    if m.startswith("decision") or "draw" in m:
        return "draw"
    return (None, "winnerless_finish")  # KO/Sub with no winner = data anomaly


def fight_seconds(end_round, end_time, sched, method) -> float:
    """Total elapsed seconds. Falls back to scheduled length for decisions."""
    try:
        mm, ss = str(end_time).split(":")
        return (int(end_round) - 1) * 300 + int(mm) * 60 + int(ss)
    except (ValueError, TypeError, AttributeError):
        m = (method or "").lower()
        if m.startswith("decision") and sched:
            return int(sched) * 300
        return float("nan")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=os.path.join(os.path.dirname(__file__), "data"))
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    base_url = os.environ["SUPABASE_URL"].rstrip("/")
    key = _env_key()

    print("pulling events, fighters, fights, fight_rounds, closing odds ...")
    events = fetch_all(base_url, key, "events",
                       "select=id,event_date,is_upcoming&order=id")
    fighters = fetch_all(base_url, key, "fighters",
                         "select=id,name,dob&order=id")
    fight_cols = ",".join(
        ["id", "event_id", "fighter_a_id", "fighter_b_id", "winner_id", "method",
         "weight_class", "scheduled_rounds", "end_round", "end_time"]
        + [f"{s}_{stem}" for stem in STAT_KEYS.values() for s in ("a", "b")]
    )
    fights = fetch_all(base_url, key, "fights", f"select={fight_cols}&order=id")
    round_cols = ",".join(
        ["fight_id", "fighter_a_id", "fighter_b_id"]
        + [f"{s}_{stem}" for stem in STAT_KEYS.values() for s in ("a", "b")]
    )
    rounds = fetch_all(base_url, key, "fight_rounds", f"select={round_cols}&order=id")
    odds = fetch_all(base_url, key, "fight_odds",
                     "select=fight_id,fighter_id,american_odds,implied_prob"
                     "&is_closer=eq.true&order=id")
    if not odds:
        sys.exit("fight_odds returned 0 rows -- wrong key (anon blocks this table)?")
    print(f"  events={len(events)} fighters={len(fighters)} fights={len(fights)} "
          f"round_rows={len(rounds)} closer_odds_rows={len(odds)}")

    ev = {e["id"]: e for e in events}
    corners = {f["id"]: (f["fighter_a_id"], f["fighter_b_id"]) for f in fights}

    # ------------------------------------------- fight_rounds per-fighter totals
    agg: dict[tuple, dict] = {}
    for r in rounds:
        for side, fid_col in (("a", "fighter_a_id"), ("b", "fighter_b_id")):
            key_ = (r["fight_id"], r[fid_col])
            acc = agg.setdefault(key_, {k: 0 for k in STAT_KEYS})
            for k, stem in STAT_KEYS.items():
                acc[k] += r.get(f"{side}_{stem}") or 0

    # ------------------------------------------------------- dead-booking dedupe
    # ufcstats occasionally reassigns a bout's fight id; the scraper then inserts
    # a fresh row and the stale booking survives (stats land on the new row, the
    # odds capture may hang off the old one). A dead booking is a stats-empty
    # ghost of the same fight -- merge those. Same-pair rows that BOTH carry
    # stats evidence are genuine same-night rematches (e.g. Sakuraba-Silveira,
    # UFC Ultimate Japan 1997) and must be kept.
    def has_evidence(f: dict) -> bool:
        wide = any(f.get(f"{s}_{stem}") is not None
                   for stem in STAT_KEYS.values() for s in ("a", "b"))
        return wide or (f["id"], f["fighter_a_id"]) in agg or \
            (f["id"], f["fighter_b_id"]) in agg

    groups: dict[tuple, list[dict]] = {}
    for f in fights:
        pair = tuple(sorted((f["fighter_a_id"], f["fighter_b_id"])))
        groups.setdefault((f["event_id"], pair), []).append(f)
    skip_ids: set = set()
    siblings: dict[int, list[int]] = {}
    dup_report = []
    for group in groups.values():
        if len(group) < 2:
            continue
        with_evidence = [f for f in group if has_evidence(f)]
        if len(with_evidence) >= 2:
            continue  # genuine same-night rematch: keep every row
        canonical = with_evidence[0] if with_evidence else \
            max(group, key=lambda f: f["id"])
        siblings[canonical["id"]] = [canonical["id"]] + [
            f["id"] for f in group if f["id"] != canonical["id"]]
        for f in group:
            if f["id"] != canonical["id"]:
                skip_ids.add(f["id"])
        dup_report.append(f"    kept {canonical['id']}, dropped "
                          f"{[f['id'] for f in group if f['id'] != canonical['id']]}")
    if dup_report:
        print(f"  duplicate bookings merged ({len(dup_report)} fights):")
        print("\n".join(dup_report))

    # ------------------------------------------------------------------- odds
    # Keyed by (fight_id, fighter_id): immune to any side-labeling convention
    # in the odds capture. Rows for fighters not in the fight's corners are
    # dropped and counted (would indicate an odds-matching bug upstream).
    by_fighter: dict[tuple, list[float]] = {}
    n_odds_unmatched = n_odds_unusable = 0
    for r in odds:
        p = r["implied_prob"]
        if p is None and r["american_odds"] is not None:
            p = american_to_prob(r["american_odds"])
        if p is None or not (0.0 < float(p) < 1.0):
            n_odds_unusable += 1
            continue
        c = corners.get(r["fight_id"])
        if c is None or r["fighter_id"] not in c:
            n_odds_unmatched += 1
            continue
        by_fighter.setdefault((r["fight_id"], r["fighter_id"]), []).append(float(p))
    closing = {k: prob_to_american(median(v)) for k, v in by_fighter.items()}
    print(f"  closer rows dropped: {n_odds_unmatched} fighter-not-in-corners, "
          f"{n_odds_unusable} unusable prob")

    # ------------------------------------------------------- fights + stats rows
    fight_rows, stat_rows = [], []
    excluded = {"upcoming_event": 0, "no_event_date": 0, "no_result": 0,
                "winner_not_in_corners": 0, "winnerless_finish": 0,
                "duplicate_booking": 0}
    n_backfilled = n_zero_corner = checked = mismatched = 0
    for f in fights:
        if f["id"] in skip_ids:
            excluded["duplicate_booking"] += 1
            continue
        e = ev.get(f["event_id"])
        if e is None or e["is_upcoming"]:
            excluded["upcoming_event"] += 1
            continue
        if not e["event_date"]:
            excluded["no_event_date"] += 1  # event_date anchors point-in-time
            continue
        res = map_result(f["winner_id"], f["fighter_a_id"], f["fighter_b_id"], f["method"])
        if isinstance(res, tuple):
            excluded[res[1]] += 1
            continue
        fight_rows.append({
            "fight_id": f["id"], "event_date": e["event_date"],
            "fighter_a_id": f["fighter_a_id"], "fighter_b_id": f["fighter_b_id"],
            "result": res, "weight_class": f["weight_class"],
            "n_rounds_sched": f["scheduled_rounds"], "method": f["method"],
            "odds_a": next((closing[(s, f["fighter_a_id"])] for s in
                            siblings.get(f["id"], [f["id"]])
                            if (s, f["fighter_a_id"]) in closing), None),
            "odds_b": next((closing[(s, f["fighter_b_id"])] for s in
                            siblings.get(f["id"], [f["id"]])
                            if (s, f["fighter_b_id"]) in closing), None),
        })

        secs = fight_seconds(f["end_round"], f["end_time"], f["scheduled_rounds"], f["method"])
        corner_stats = {}
        for side, fid_col in (("a", "fighter_a_id"), ("b", "fighter_b_id")):
            fid = f[fid_col]
            vals = {k: f.get(f"{side}_{stem}") for k, stem in STAT_KEYS.items()}
            fallback = agg.get((f["id"], fid))
            if all(v is None for v in vals.values()):
                if fallback is not None:
                    vals = dict(fallback)  # documented fight_rounds backfill
                    n_backfilled += 1
                else:
                    corner_stats[fid] = None
                    continue
            else:
                vals = {k: (v if v is not None else 0) for k, v in vals.items()}
                if fallback is not None:
                    checked += 1
                    if any(int(vals[k]) != int(fallback[k]) for k in STAT_KEYS):
                        mismatched += 1
            corner_stats[fid] = vals
        have = [fid for fid, v in corner_stats.items() if v is not None]
        if not have:
            continue  # no stats for either corner; engine treats fight as statless
        for fid, vals in corner_stats.items():
            if vals is None:
                # Emit zeros: dropping one corner would make the engine's
                # opponent self-join discard the OTHER corner's real stats too.
                vals = {k: 0 for k in STAT_KEYS}
                n_zero_corner += 1
            stat_rows.append({"fight_id": f["id"], "fighter_id": fid,
                              **vals, "fight_seconds": secs})

    if not fight_rows:
        sys.exit("No fights survived filtering -- check exclusion counters/filters.")
    fights_df = pd.DataFrame(fight_rows).sort_values(["event_date", "fight_id"])
    stats_df = pd.DataFrame(stat_rows)
    fighters_df = pd.DataFrame(
        [{"fighter_id": x["id"], "name": x["name"], "dob": x["dob"]} for x in fighters]
    )

    fights_df.to_csv(os.path.join(args.outdir, "fights.csv"), index=False)
    stats_df.to_csv(os.path.join(args.outdir, "fight_stats.csv"), index=False)
    fighters_df.to_csv(os.path.join(args.outdir, "fighters.csv"), index=False)

    both_odds = (fights_df["odds_a"].notna() & fights_df["odds_b"].notna()).mean()
    print(f"\nwrote {len(fights_df)} fights, {len(stats_df)} stat rows, "
          f"{len(fighters_df)} fighters -> {args.outdir}")
    print(f"  results: {fights_df['result'].value_counts().to_dict()}")
    print(f"  excluded: {excluded}")
    print(f"  odds coverage (both sides): {both_odds:.1%} of exported fights")
    print(f"  stats: {n_backfilled} corners backfilled from fight_rounds, "
          f"{n_zero_corner} corners zero-filled (partner had data)")
    print(f"  fight_seconds missing: {int(stats_df['fight_seconds'].isna().sum())} stat rows")
    print(f"  cross-check totals vs fight_rounds: {checked} corners compared, "
          f"{mismatched} mismatched")
    if excluded["winner_not_in_corners"] or excluded["winnerless_finish"]:
        print("  WARNING: winner/method anomalies excluded -- inspect upstream data.")


if __name__ == "__main__":
    main()
