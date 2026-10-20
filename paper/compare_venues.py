"""Side-by-side of every venue's executable offer per fight and side, at one instant.

    python3 paper/compare_venues.py --snapshot SNAP.json --polymarket-books BOOKS.jsonl --now ISO

Read-only. For each eligible fight and each corner it prints, for every venue
that produced a priceable offer at `now` under the draft config: the
equivalent American price after fees, the market-reference probability for
that side (median de-vig of >= 3 OTHER sportsbooks), the expected return at
the reference, and MMA-001's expected return when a forecast exists. Offers
the rules reject are listed with the reason. This is the comparison the paper
strategy sees; it decides nothing and records nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import data as D  # noqa: E402
import run_card as R  # noqa: E402
from reference import build_reference, parse_ts  # noqa: E402
from strategy import candidate_offers  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", required=True); ap.add_argument("--polymarket-books"); ap.add_argument("--now", required=True)
    ap.add_argument("--config", default=str(R.DEFAULT_CFG)); ap.add_argument("--artifact")
    args = ap.parse_args(argv)
    cfg, _ = R.load_cfg(args.config)
    snap = D.load_snapshot(args.snapshot)
    now = parse_ts(args.now)
    fights = R.eligible_fights(snap)
    names = {int(f["id"]): (f.get("fighter_a_name", "A"), f.get("fighter_b_name", "B")) for f in fights}
    quotes = {}
    for q in snap["quotes"]:
        quotes.setdefault(int(q["fight_id"]), []).append(q)
    pm_rows = list(snap.get("polymarket_books") or [])
    if args.polymarket_books:
        pm_rows += D.load_polymarket_jsonl(args.polymarket_books)
    pm = {}
    for b in D.latest_polymarket_books(pm_rows, now=now, fight_ids={int(f["id"]) for f in fights}):
        pm.setdefault(int(b["fight_id"]), []).append(b)
    references = {}
    for f in fights:
        ref, _ = build_reference(int(f["id"]), quotes.get(int(f["id"]), []), now=now, cfg=cfg)
        if ref:
            references[int(f["id"])] = ref
    artifact = args.artifact or os.environ.get(cfg["model"]["artifact_env"], "")
    fc = R.forecast(snap, fights, references, artifact, HERE / "private" / "tmp") if artifact and pathlib.Path(artifact).exists() else {"forecasts": []}
    p_model = {f["fight_id"]: f.get("p_a") for f in fc.get("forecasts", [])}
    stake = float(cfg["staking"]["unit"])
    book_names = cfg["venues"].get("sportsbook_names", {})
    rows_out = []
    print(f"{'fight':34s} side {'venue':12s} {'price':>7s} {'p_ref':>6s} {'ev_ref':>7s} {'p_mod':>6s} {'ev_mod':>7s}")
    for f in fights:
        fid = int(f["id"])
        offers, rejected = candidate_offers(f, quotes.get(fid, []), pm.get(fid, []), now=now, cfg=cfg, stake=stake)
        for side in ("a", "b"):
            for o in sorted([o for o in offers if o.side == side], key=lambda o: -o.equivalent_american):
                excl = o.venue_id if o.venue_kind == "sportsbook" else None
                ref, why = build_reference(fid, quotes.get(fid, []), now=now, cfg=cfg, exclude_book_id=excl)
                p_ref = (ref.p_a if side == "a" else 1 - ref.p_a) if ref else None
                pm_p = p_model.get(fid)
                p_mod = (pm_p if side == "a" else 1 - pm_p) if pm_p is not None else None
                label = "Polymarket" if o.venue_kind == "polymarket" else book_names.get(str(o.venue_id), f"book {o.venue_id}")
                row = {"fight_id": fid, "side": side, "venue": label, "equivalent_american": round(o.equivalent_american, 1),
                       "p_reference": p_ref, "ev_reference": o.expected_return(p_ref) if p_ref is not None else None,
                       "p_model": p_mod, "ev_model": o.expected_return(p_mod) if p_mod is not None else None,
                       "fill": o.source.get("fill") if o.venue_kind == "polymarket" else None}
                rows_out.append(row)
                nm = names[fid][0 if side == "a" else 1][:32]
                fmt = lambda v, n=3: "" if v is None else f"{v:.{n}f}"  # noqa: E731
                print(f"{nm:34s} {side:4s} {label:12s} {row['equivalent_american']:>+7.0f} {fmt(p_ref):>6s} {fmt(row['ev_reference'], 4):>7s} {fmt(p_mod):>6s} {fmt(row['ev_model'], 4):>7s}")
        for rj in rejected:
            if rj["venue_id"] == int(cfg["venues"]["polymarket"]["venue_id"]):
                print(f"{names[fid][0][:14] + ' v ' + names[fid][1][:14]:34s} {str(rj['side']):4s} Polymarket   rejected: {rj['reason']}")
    out = HERE / "private" / "venue_comparison.json"
    out.write_text(json.dumps({"now": now.isoformat(), "rows": rows_out}, indent=1, default=str))
    print(f"\n{len(rows_out)} offers written to {out}")


if __name__ == "__main__":
    main()
