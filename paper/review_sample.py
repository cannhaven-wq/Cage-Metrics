"""Build the pre-replay validation sample: raw rows -> paired quote -> margin-free probability.

    python3 paper/review_sample.py --data paper/private/replay --out paper/private/replay/out

Read-only. For each lockable card it solves the decision instant, then takes up
to three fights and, for each, every book's point-in-time quote with the two raw
rows it was built from. Each pair is checked against the invariants the replay
relies on; any failure is printed and the exit code is 1. No outcome is read.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pricing import devig_proportional  # noqa: E402
from reference import parse_ts  # noqa: E402
from replay import lock_at_point_in_time, partition_of, quotes_as_of  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--config", default=str(HERE / "config" / "strategy_draft.json"))
    args = ap.parse_args(argv)
    cfg = json.loads(pathlib.Path(args.config).read_text())
    d = pathlib.Path(args.data)
    meta = json.loads((d / "card_meta.json").read_text()); rows = json.loads((d / "quote_rows.json").read_text())
    by_id = {r["id"]: r for r in rows}
    fights_by_event, starts_by_event, rows_by_event = defaultdict(list), defaultdict(list), defaultdict(list)
    fe = {}
    for f in meta["fights"]:
        fights_by_event[f["event_id"]].append(f); fe[int(f["id"])] = f["event_id"]
    for s in meta["starts"]:
        starts_by_event[fe[int(s["fight_id"])]].append(s)
    for r in rows:
        rows_by_event[r["event_id"]].append(r)
    sample, failures = [], []
    for ev in sorted(meta["events"], key=lambda e: e["event_date"]):
        fights = [f for f in fights_by_event[ev["event_id"]] if f.get("is_active") is not False]
        lock, why, _ = lock_at_point_in_time(fights_by_event[ev["event_id"]], starts_by_event[ev["event_id"]], ev["event_date"], cfg)
        if lock is None or not rows_by_event.get(ev["event_id"]):
            continue
        taken = 0
        for f in sorted(fights, key=lambda f: f["id"]):
            q, ex = quotes_as_of(rows_by_event[ev["event_id"]], f, lock, cfg)
            if not q:
                continue
            for x in q:
                ra, rb = by_id[x["row_ids"][0]], by_id[x["row_ids"][1]]
                checks = {
                    "same_capture_instant": ra["captured_at"] == rb["captured_at"] == x["captured_at"].replace("+00:00", "") or parse_ts(ra["captured_at"]) == parse_ts(rb["captured_at"]) == parse_ts(x["captured_at"]),
                    "same_book": ra["book_id"] == rb["book_id"] == x["book_id"],
                    "side_a_is_corner_a": int(ra["fighter_id"]) == int(f["fighter_a_id"]),
                    "side_b_is_corner_b": int(rb["fighter_id"]) == int(f["fighter_b_id"]),
                    "opponents_consistent": (ra["opponent_fighter_id"] in (None, f["fighter_b_id"])) and (rb["opponent_fighter_id"] in (None, f["fighter_a_id"])),
                    "price_a_from_row_a": int(ra["american_odds"]) == x["american_a"], "price_b_from_row_b": int(rb["american_odds"]) == x["american_b"],
                    "captured_not_after_lock": parse_ts(x["captured_at"]) <= lock,
                    "provider_not_after_lock": all(parse_ts(p) <= lock for p in (ra["provider_last_update"], rb["provider_last_update"]) if p),
                    "not_live": ra["is_live"] is not True and rb["is_live"] is not True,
                }
                bad = [k for k, v in checks.items() if not v]
                if bad:
                    failures.append({"fight_id": f["id"], "book_id": x["book_id"], "failed": bad})
                sample.append({"event_date": ev["event_date"], "card": ev["name"], "partition": partition_of(ev["event_date"]), "lock_at": lock.isoformat(),
                               "fight_id": f["id"], "fighter_a": f"{f['fighter_a_name']} ({f['fighter_a_id']})", "fighter_b": f"{f['fighter_b_name']} ({f['fighter_b_id']})",
                               "book_id": x["book_id"], "row_a": ra, "row_b": rb, "paired": {k: x[k] for k in ("american_a", "american_b", "captured_at", "provider_last_update")},
                               "quote_age_min": round((lock - parse_ts(x["captured_at"])).total_seconds() / 60, 1),
                               "p_a_margin_free": round(devig_proportional(x["american_a"], x["american_b"]), 4),
                               "overround": round(1 / (1 + x["american_a"] / 100 if x["american_a"] > 0 else 1 + 100 / -x["american_a"]) + 1 / (1 + x["american_b"] / 100 if x["american_b"] > 0 else 1 + 100 / -x["american_b"]), 4),
                               "checks": checks})
            taken += 1
            if taken >= 3:
                break
    out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out / "review_sample.json").write_text(json.dumps({"n_pairs": len(sample), "cards": sorted({s["event_date"] for s in sample}),
                                                        "fights": sorted({s["fight_id"] for s in sample}), "failures": failures, "sample": sample}, indent=1, default=str))
    print(json.dumps({"n_pairs": len(sample), "cards": sorted({s["event_date"] for s in sample}), "fights": len({s["fight_id"] for s in sample}), "failures": failures}, indent=1))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
