"""Settlement and metrics for the paper ledger. Pure functions over ledger events.

Settlement of one selection, given the fight's current row:
- corners changed since the lock          -> cancel (void), never scored
- no result yet                           -> left open
- no-contest / overturned / could-not-continue / draw
                                          -> sportsbook: push (stake returned);
                                             polymarket: 'unresolved' (its rules are
                                             not assumed; left open until a person records them)
- winner is the selected fighter          -> win: +net_if_win
- winner is the other corner              -> loss: -stake_cost

Metrics per strategy, over the same set of cards for every strategy so a card
with no bets still counts in coverage and turnover:
  bets, turnover, profit, roi, max_drawdown (on the settled running total),
  open_exposure, coverage (eligible fights with a bet/pass/abstain decision /
  eligible fights), cards, cards_with_no_bets, wins, losses, pushes.

CLV is reported as 'unavailable' unless the caller supplies a CLV-001 closing
reference whose provenance says the frozen definition's prerequisites were met
(`clv_reference.protocol == 'CLV-001' and clv_reference.prerequisites_met`).
No other closing-price definition is substituted.
"""
from __future__ import annotations

from typing import Optional

NC_PREFIXES = ("overturned", "could not continue", "no contest", "other")


def settle_one(sel: dict, fight: dict) -> Optional[dict]:
    """Returns the settlement/cancel payload for one selection, or None if still open."""
    if int(fight["fighter_a_id"]) != int(sel["fighter_a_id"]) or int(fight["fighter_b_id"]) != int(sel["fighter_b_id"]):
        return {"type": "cancel", "reason": "corners changed since lock",
                "corners_at_lock": [sel["fighter_a_id"], sel["fighter_b_id"]],
                "corners_now": [fight["fighter_a_id"], fight["fighter_b_id"]], "pnl": 0.0}
    if fight.get("is_active") is False:
        return {"type": "cancel", "reason": "booking retired", "pnl": 0.0}
    method = str(fight.get("method") or "").strip().lower()
    winner = fight.get("winner_id")
    off = sel["offer"]
    if any(method.startswith(p) for p in NC_PREFIXES) or (winner is None and method.startswith("decision")) or "draw" in method:
        if off["venue_kind"] == "sportsbook":
            return {"type": "settlement", "result": "push", "pnl": 0.0, "method": fight.get("method")}
        return None  # polymarket: resolution of a draw/NC is market-specific; left open for a person
    if winner is None:
        return None
    if int(winner) == int(sel["fighter_id"]):
        return {"type": "settlement", "result": "win", "pnl": float(off["net_if_win"]), "method": fight.get("method")}
    if int(winner) in (int(sel["fighter_a_id"]), int(sel["fighter_b_id"])):
        return {"type": "settlement", "result": "loss", "pnl": -float(off["stake_cost"]), "method": fight.get("method")}
    return {"type": "cancel", "reason": "winner is neither corner on the lock", "pnl": 0.0}


def metrics(ledger, cfg: dict, clv_reference: Optional[dict] = None) -> dict:
    start = float(cfg["staking"]["bankroll_start"])
    cards = sorted({e["card_id"] for e in ledger.events("lock")})
    out = {"cards": cards, "n_cards": len(cards), "strategies": {}, "clv": _clv_status(clv_reference)}
    settled_by_sel = {e["selection_id"]: e for e in ledger.events("settlement")}
    cancelled = {e["selection_id"] for e in ledger.events("cancel")}
    for strat in cfg["strategies"]:
        sels = [e for e in ledger.events("selection", strategy=strat)]
        decided = ledger.events("pass", strategy=strat) + ledger.events("abstain", strategy=strat) + sels
        eligible = sum(len(e.get("fight_ids", [])) for e in ledger.events("lock"))
        running, peak, dd, profit, turnover, wins, losses, pushes, open_exp = start, start, 0.0, 0.0, 0.0, 0, 0, 0, 0.0
        for s in sorted(sels, key=lambda e: e["ts"]):
            if s["event_id"] in cancelled:
                continue
            st = settled_by_sel.get(s["event_id"])
            if st is None:
                open_exp += float(s["stake"]); continue
            turnover += float(s["stake"]); profit += float(st["pnl"])
            running += float(st["pnl"]); peak = max(peak, running); dd = max(dd, peak - running)
            wins += st["result"] == "win"; losses += st["result"] == "loss"; pushes += st["result"] == "push"
        cards_with_bets = {s["card_id"] for s in sels if s["event_id"] not in cancelled}
        out["strategies"][strat] = {
            "bets": wins + losses + pushes, "open": len([s for s in sels if s["event_id"] not in settled_by_sel and s["event_id"] not in cancelled]),
            "cancelled": len([s for s in sels if s["event_id"] in cancelled]),
            "wins": wins, "losses": losses, "pushes": pushes,
            "turnover": turnover, "profit": profit, "roi": (profit / turnover) if turnover else None,
            "bankroll_settled": running, "max_drawdown": dd, "open_exposure": open_exp,
            "coverage": (len(decided) / eligible) if eligible else None,
            "cards_with_no_bets": len(set(cards) - cards_with_bets),
        }
    return out


def _clv_status(ref: Optional[dict]) -> dict:
    if not ref:
        return {"status": "unavailable", "reason": "CLV-001 closing reference not supplied: its prerequisites (clv001_columns and event_flow migrations, v_clv_close_reference) are not applied"}
    if ref.get("protocol") != "CLV-001" or not ref.get("prerequisites_met"):
        return {"status": "unavailable", "reason": "only the frozen CLV-001 definition may be used; another closing-price definition is not substituted"}
    return {"status": "available", "source": ref.get("source")}
