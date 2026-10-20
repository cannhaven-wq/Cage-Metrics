"""Opposite-side scan: can one fighter at venue X plus the other at venue Y lock in a profit?

    python3 paper/arbitrage.py --data paper/private/replay --out paper/private/replay/out

Read-only. Outcome-free by construction: an arbitrage is judged on prices and
settlement rules, never on who won, so this scan may read sealed-period PRICES
without reading any sealed OUTCOME.

For a pair (side a at X, side b at Y), with a fixed $100 combined stake split
to equalise the two winner payoffs, every state is priced:

    a wins / b wins                 from the two prices (and fills)
    draw / no contest / cancelled   sportsbook leg: refund ASSUMED (2-way MMA
    / opponent changed              moneylines are commonly voided on a draw,
                                    but no book's rule is in our data);
                                    Polymarket leg: 0.50 per net share
                                    (its UFC resolution text, captured)

Three classes, never merged:

  quoted_pair         both quotes fresh (60 min, both timestamps) at the same
                      instant and 1/dA + 1/dB < 1: a mathematically favourable
                      pair of QUOTED prices. Not a trade.
  simulated_execution both legs' size is known to be available at the instant
                      (order-book depth, minimum order, rounding) and every
                      settlement state is non-negative under KNOWN rules.
                      Sportsbook limits are unknown, so a pair with a
                      sportsbook leg can never reach this class.
  second_leg_unfilled the first leg is executable but the second is not at the
                      required size or price (depth, minimum order, staleness).

A pair whose void-state payoff is negative, or rests on an assumed rule, is
reported with that fact and is not an arbitrage.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import defaultdict
from datetime import datetime, timedelta

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pricing import OfferRejected, american_to_decimal, polymarket_fill  # noqa: E402
from reference import parse_ts, quote_is_fresh  # noqa: E402
from replay import quotes_as_of, partition_of  # noqa: E402

STAKE = 100.0


def cents(x: float) -> float:
    return float(int(round(x * 100.0))) / 100.0


def sportsbook_pair(da: float, db: float, total: float = STAKE) -> dict:
    """Split `total` across two sportsbook legs to equalise the winner payoffs; stakes in whole cents."""
    ia, ib = 1.0 / da, 1.0 / db
    sa = cents(total * ia / (ia + ib))
    sb = cents(total - sa)
    return {"margin": ia + ib, "stake_a": sa, "stake_b": sb,
            "pnl_a_wins": round(sa * da - total, 2), "pnl_b_wins": round(sb * db - total, 2),
            "pnl_void_if_both_refund": 0.0}


def bout_cutoffs(starts: list[dict]) -> dict:
    """fight_id -> the EARLIEST start time ever recorded for the bout (any observation).

    A pre-fight position must be taken before the bout starts. bell_at is never
    filled and is_live is therefore unknown on most rows, so an instant counts
    as pre-fight only if it is before every start estimate the provider ever
    gave for that bout. Using later-observed estimates here only EXCLUDES
    instants, so it cannot manufacture an opportunity.
    """
    out = {}
    for s in starts:
        if s.get("source") != "odds_api_commence":
            continue
        t = parse_ts(s["start_at"]); fid = int(s["fight_id"])
        out[fid] = min(out.get(fid, t), t)
    return out


def scan_sportsbooks(rows: list[dict], fights: list[dict], cfg: dict, instants: list[datetime],
                     cutoffs: dict | None = None) -> list[dict]:
    """Every favourable sportsbook pair at every pre-fight capture instant, deduplicated into episodes.

    cutoffs: fight_id -> earliest recorded start. A bout with no recorded start
    cannot be shown to be pre-fight; its pairs are returned with class
    'start_unknown' and are not counted as quoted pairs.
    """
    max_age = float(cfg["offer"]["max_quote_age_minutes"])
    cutoffs = cutoffs if cutoffs is not None else {}
    hits = []
    for f in fights:
        if f.get("is_active") is False:
            continue
        fr = [r for r in rows if int(r["fight_id"]) == int(f["id"])]
        if not fr:
            continue
        cut = cutoffs.get(int(f["id"]))
        for t in instants:
            if cut is not None and t >= cut:
                continue                                 # at or after the bout could have started: live market
            q, _ = quotes_as_of(fr, f, t, cfg)
            fresh = [x for x in q if quote_is_fresh(x, t, max_age, True)[0]]
            for qa in fresh:
                for qb in fresh:
                    if qa["book_id"] == qb["book_id"]:
                        continue
                    da, db = american_to_decimal(qa["american_a"]), american_to_decimal(qb["american_b"])
                    if 1.0 / da + 1.0 / db < 1.0:
                        p = sportsbook_pair(da, db)
                        provider_known = bool(qa.get("provider_last_update")) and bool(qb.get("provider_last_update"))
                        klass = "start_unknown" if cut is None else ("quoted_pair" if provider_known else "provider_time_unknown")
                        hits.append({"fight_id": int(f["id"]), "at": t.isoformat(), "book_a": qa["book_id"], "american_a": qa["american_a"],
                                     "book_b": qb["book_id"], "american_b": qb["american_b"], "captured_a": qa["captured_at"], "captured_b": qb["captured_at"],
                                     "minutes_before_start": round((cut - t).total_seconds() / 60, 1) if cut else None,
                                     "row_ids": qa["row_ids"] + qb["row_ids"], **p, "class": klass,
                                     "why_not_execution": "sportsbook limits unknown; draw/no-contest refund rule assumed, not in data"})
    episodes = {}
    for h in hits:
        k = (h["fight_id"], h["book_a"], h["book_b"], h["american_a"], h["american_b"], h["class"])
        episodes.setdefault(k, {**h, "first_seen": h["at"], "last_seen": h["at"], "instants": 0})
        episodes[k]["last_seen"] = h["at"]; episodes[k]["instants"] += 1
    return list(episodes.values())


def pm_plus_sportsbook(book: dict, sb_quote: dict, sb_side: str, *, total: float = STAKE, steps: int = 2000) -> dict:
    """Polymarket leg on book['side'] plus a sportsbook leg on the other side, $100 combined.

    Searches the Polymarket cash amount (in cents) that maximises the worst of
    the two winner payoffs, filling the PM leg against its real ask ladder with
    the market's fee (collected in shares) and the market's minimum order.
    """
    d_sb = american_to_decimal(sb_quote[f"american_{sb_side}"])
    best = None
    for k in range(1, steps):
        c = cents(total * k / steps)
        s = cents(total - c)
        if c <= 0 or s <= 0:
            continue
        try:
            fill = polymarket_fill(asks=book["asks"], budget=c, fee_rate_bps=book["fee_rate_bps"], fee_exponent=book.get("fee_exponent", 1),
                                   min_order_size=book.get("min_order_size"), tick_size=book.get("tick_size"))
        except OfferRejected as e:
            continue
        shares = fill["shares"]
        pnl_pm = shares - total
        pnl_sb = s * d_sb - total
        worst = min(pnl_pm, pnl_sb)
        if best is None or worst > best["worst_winner_pnl"]:
            best = {"pm_cash": c, "sb_stake": s, "pm_net_shares": shares, "pm_fee_shares": fill["fee_shares"], "pm_fee_usdc": fill["fee_usdc"],
                    "pm_avg_price": fill["avg_price"], "pnl_pm_side_wins": round(pnl_pm, 2), "pnl_sb_side_wins": round(pnl_sb, 2),
                    "pnl_void": round(0.5 * shares + s - total, 2), "worst_winner_pnl": worst}
    if best is None:
        return {"class": "second_leg_unfilled", "reason": "no Polymarket fill at any split (depth or minimum order)"}
    states = [best["pnl_pm_side_wins"], best["pnl_sb_side_wins"], best["pnl_void"]]
    best["margin_check"] = None
    if min(best["pnl_pm_side_wins"], best["pnl_sb_side_wins"]) > 0:
        best["class"] = "quoted_pair"
        best["why_not_execution"] = "sportsbook leg limit unknown" + ("" if best["pnl_void"] >= 0 else "; void state loses money (Polymarket pays 0.50, sportsbook refunds)")
    else:
        best["class"] = "not_favourable"
    best["all_states_nonnegative"] = min(states) >= 0
    return best


def run(data_dir: pathlib.Path, out_dir: pathlib.Path, cfg_path: pathlib.Path) -> dict:
    cfg = json.loads(cfg_path.read_text())
    meta = json.loads((data_dir / "card_meta.json").read_text())
    rows = json.loads((data_dir / "quote_rows.json").read_text())
    extra = data_dir / "quote_rows_ufc333_pm_window.json"
    if extra.exists():
        rows = rows + json.loads(extra.read_text())
    fe = {int(f["id"]): f["event_id"] for f in meta["fights"]}
    starts_by_event = defaultdict(list)
    for st in meta["starts"]:
        starts_by_event[fe[int(st["fight_id"])]].append(st)
    fights_by_event = defaultdict(list)
    for f in meta["fights"]:
        fights_by_event[f["event_id"]].append(f)
    rows_by_event = defaultdict(list)
    for r in rows:
        rows_by_event[r["event_id"]].append(r)
    books_cfg = set(cfg["venues"]["sportsbooks"])
    per_card, all_eps = [], []
    for ev in sorted(meta["events"], key=lambda e: e["event_date"]):
        rs = [r for r in rows_by_event.get(ev["event_id"], []) if int(r["book_id"]) in books_cfg]
        instants = sorted({parse_ts(r["captured_at"]) for r in rs})
        eps = scan_sportsbooks(rs, fights_by_event[ev["event_id"]], cfg, instants, bout_cutoffs(starts_by_event[ev["event_id"]])) if rs else []
        n_books = len({int(r["book_id"]) for r in rs})
        per_card.append({"event_id": ev["event_id"], "event_date": ev["event_date"], "name": ev["name"], "partition": partition_of(ev["event_date"]),
                         "configured_books_with_rows": n_books, "capture_instants": len(instants),
                         "quoted_pair_episodes": sum(e["class"] == "quoted_pair" for e in eps),
                         "start_unknown_episodes": sum(e["class"] == "start_unknown" for e in eps),
                         "provider_time_unknown_episodes": sum(e["class"] == "provider_time_unknown" for e in eps)})
        all_eps += [dict(e, event_id=ev["event_id"]) for e in eps]
    # Polymarket executable books: only the 2026-10-20 capture exists
    pm_results = []
    pm_path = data_dir / "pm_books_ufc333_2026-10-20T1914.jsonl"
    if pm_path.exists():
        books = [json.loads(l) for l in pm_path.read_text().splitlines() if l.strip()]
        ev_id = 4542
        fights = {int(f["id"]): f for f in fights_by_event[ev_id]}
        rs = [r for r in rows_by_event.get(ev_id, []) if int(r["book_id"]) in books_cfg]
        for b in books:
            f = fights.get(int(b["fight_id"]))
            if f is None or f.get("is_active") is False:
                continue
            t = parse_ts(b["retrieved_at"])
            if b.get("mapping_confidence") != "exact" or not b.get("fee_rule_verified") or not b.get("settlement_ok"):
                pm_results.append({"fight_id": f["id"], "pm_side": b["side"], "class": "excluded",
                                   "reason": f"mapping {b.get('mapping_confidence')}, fee verified {b.get('fee_rule_verified')}, settlement ok {b.get('settlement_ok')}"})
                continue
            q, _ = quotes_as_of(rs, f, t, cfg)
            other = "b" if b["side"] == "a" else "a"
            for sq in q:
                fresh, why = quote_is_fresh(sq, t, float(cfg["offer"]["max_quote_age_minutes"]), True)
                if not fresh:
                    pm_results.append({"fight_id": f["id"], "pm_side": b["side"], "sb_book": sq["book_id"], "class": "second_leg_unfilled", "reason": f"sportsbook quote not fresh: {why}"})
                    continue
                r = pm_plus_sportsbook(b, sq, other)
                pm_results.append({"fight_id": f["id"], "pm_side": b["side"], "pm_best_ask": b.get("best_ask"), "sb_book": sq["book_id"],
                                   "sb_side": other, "sb_american": sq[f"american_{other}"], "at": t.isoformat(), "sb_captured_at": sq["captured_at"], **r})
    # nearest-miss context: the best (lowest) two-book margin per fight at the replay decision instants is in the replay report
    out = {"per_card": per_card, "sportsbook_quoted_pair_episodes": all_eps, "polymarket_plus_sportsbook": pm_results,
           "counts": {"sb_quoted_pair_episodes": sum(e["class"] == "quoted_pair" for e in all_eps),
                      "sb_start_unknown_episodes": sum(e["class"] == "start_unknown" for e in all_eps),
                      "sb_provider_time_unknown_episodes": sum(e["class"] == "provider_time_unknown" for e in all_eps),
                      "sb_simulated_execution": 0, "sb_simulated_execution_note": "not reachable: sportsbook limits are unknown",
                      "pm_sb_pairs_checked": sum(1 for r in pm_results if r.get("class") in ("quoted_pair", "not_favourable")),
                      "pm_sb_quoted_pair": sum(1 for r in pm_results if r.get("class") == "quoted_pair"),
                      "pm_sb_all_states_nonnegative": sum(1 for r in pm_results if r.get("class") == "quoted_pair" and r.get("all_states_nonnegative")),
                      "pm_sb_second_leg_unfilled": sum(1 for r in pm_results if r.get("class") == "second_leg_unfilled")}}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "arbitrage_report.json").write_text(json.dumps(out, indent=1, default=str))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--config", default=str(HERE / "config" / "strategy_draft.json"))
    args = ap.parse_args(argv)
    out = run(pathlib.Path(args.data), pathlib.Path(args.out), pathlib.Path(args.config))
    print(json.dumps({"per_card": out["per_card"], "counts": out["counts"]}, indent=1))


if __name__ == "__main__":
    main()
