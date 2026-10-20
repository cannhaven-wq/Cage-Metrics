"""Strategy evaluator: turns one card's offers, references and model numbers into decisions.

Pure: no clock (the lock instant is an argument), no network, no database. The
rules are read from the DRAFT config; nothing is hard-coded here so a change is
a diff in one JSON file and never a quiet edit to code.

For every eligible fight and every strategy the result is exactly one of:

    bet        an Offer, its stake, ev_reference and ev_model
    pass       the fight was priced and considered; no offer qualified (reason)
    abstain    the fight could not be evaluated at all (reason): no reference,
               no fresh offers, or the model produced no number for S1

Model coverage is separate from betting: `p_model` is None when MMA-001
abstained, and that is recorded as a model abstention on the lock regardless
of what the betting rules decide.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from pricing import Offer, OfferRejected, sportsbook_offer, polymarket_offer
from reference import build_reference, quote_is_fresh


@dataclass
class Decision:
    strategy: str
    fight_id: int
    decision: str                       # bet | pass | abstain
    reason: str
    side: Optional[str] = None
    offer: Optional[dict] = None
    stake: float = 0.0
    ev_reference: Optional[float] = None
    ev_model: Optional[float] = None
    p_reference: Optional[float] = None
    p_model: Optional[float] = None
    reference: Optional[dict] = None
    rank: Optional[int] = None
    candidates_considered: int = 0
    rejected_offers: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _band_ok(offer: Offer, cfg: dict) -> tuple[bool, str]:
    am = offer.equivalent_american
    lo, hi = float(cfg["offer"]["min_american"]), float(cfg["offer"]["max_american"])
    if am < lo or am > hi:
        return False, f"equivalent price {am:+.0f} outside {lo:+.0f}..{hi:+.0f}"
    return True, "ok"


def candidate_offers(fight: dict, quotes: list[dict], pm_books: list[dict], *, now: datetime,
                     cfg: dict, stake: float) -> tuple[list[Offer], list[dict]]:
    """Every fresh, in-band, priceable offer on both sides, and why the rest were rejected."""
    offers, rejected = [], []
    sb_ids = set(int(b) for b in cfg["venues"]["sportsbooks"])
    max_age = float(cfg["offer"]["max_quote_age_minutes"])
    check_prov = bool(cfg["offer"].get("check_provider_timestamp", True))
    corners = {"a": int(fight["fighter_a_id"]), "b": int(fight["fighter_b_id"])}
    for q in quotes:
        bid = int(q["book_id"])
        if bid not in sb_ids:
            continue
        fresh, why = quote_is_fresh(q, now, max_age, check_prov)
        if not fresh:
            rejected.append({"venue_id": bid, "side": "both", "reason": why}); continue
        for side in ("a", "b"):
            am = q.get(f"american_{side}")
            if am is None:
                rejected.append({"venue_id": bid, "side": side, "reason": "no price on this side"}); continue
            try:
                o = sportsbook_offer(venue_id=bid, fight_id=int(fight["id"]), side=side, fighter_id=corners[side],
                                     american=am, stake=stake, retrieved_at=q["captured_at"],
                                     provider_ts=q.get("provider_last_update"), quote=q)
            except OfferRejected as e:
                rejected.append({"venue_id": bid, "side": side, "reason": str(e)}); continue
            ok, why = _band_ok(o, cfg)
            if not ok:
                rejected.append({"venue_id": bid, "side": side, "reason": why}); continue
            offers.append(o)
    pm = cfg["venues"].get("polymarket") or {}
    if pm.get("enabled"):
        vid = int(pm["venue_id"])
        for b in pm_books:
            side = b.get("side")
            if side not in ("a", "b"):
                rejected.append({"venue_id": vid, "side": side, "reason": "book not mapped to a corner"}); continue
            if int(b.get("fighter_id", -1)) != corners[side]:
                rejected.append({"venue_id": vid, "side": side, "reason": "book fighter does not match the corner on file"}); continue
            fresh, why = quote_is_fresh({"captured_at": b.get("retrieved_at"), "provider_last_update": b.get("book_timestamp")},
                                        now, max_age, check_prov)
            if not fresh:
                rejected.append({"venue_id": vid, "side": side, "reason": why}); continue
            if pm.get("fee_rule_must_be_verified", True) and b.get("fee_rule_verified") is not True:
                rejected.append({"venue_id": vid, "side": side, "reason": "fee rule not verified against official documentation"}); continue
            try:
                o = polymarket_offer(venue_id=vid, fight_id=int(fight["id"]), side=side, fighter_id=corners[side],
                                     book=b, stake=stake, retrieved_at=b["retrieved_at"], provider_ts=b.get("book_timestamp"),
                                     min_fill_fraction=float(cfg["offer"].get("polymarket_min_fill_fraction", 1.0)),
                                     unit_notional=float(cfg["staking"].get("unit_notional_usd", 100.0)))
            except OfferRejected as e:
                rejected.append({"venue_id": vid, "side": side, "reason": str(e)}); continue
            ok, why = _band_ok(o, cfg)
            if not ok:
                rejected.append({"venue_id": vid, "side": side, "reason": why}); continue
            offers.append(o)
    return offers, rejected


def evaluate_card(*, card: dict, quotes_by_fight: dict, pm_books_by_fight: dict, p_model_by_fight: dict,
                  cfg: dict, now: datetime, bankroll: dict) -> list[Decision]:
    """card: {event_id, fights:[{id, fighter_a_id, fighter_b_id, ...}]}
    quotes_by_fight: {fight_id: [sportsbook quotes]}; pm_books_by_fight: {fight_id: [books]}
    p_model_by_fight: {fight_id: p_a or None}; bankroll: {strategy: settled units}
    """
    st = cfg["staking"]; stake = float(st["unit"])
    stop_at = float(st["stop_new_selections_at_bankroll"])
    decisions: list[Decision] = []
    for strat, rule in cfg["strategies"].items():
        stopped = bankroll.get(strat, float(st["bankroll_start"])) <= stop_at
        qualifying = []
        for f in card["fights"]:
            fid = int(f["id"])
            pm_val = p_model_by_fight.get(fid)
            offers, rejected = candidate_offers(f, quotes_by_fight.get(fid, []), pm_books_by_fight.get(fid, []),
                                                now=now, cfg=cfg, stake=stake)
            if not offers:
                decisions.append(Decision(strat, fid, "abstain", "no fresh in-band offer on either side",
                                          p_model=pm_val, rejected_offers=rejected)); continue
            best = None; best_ref = None; no_ref_reasons = set()
            for o in offers:
                excl = o.venue_id if o.venue_kind == "sportsbook" else None
                ref, why = build_reference(fid, quotes_by_fight.get(fid, []), now=now, cfg=cfg, exclude_book_id=excl)
                if ref is None:
                    no_ref_reasons.add(why); continue
                p_ref = ref.p_a if o.side == "a" else 1.0 - ref.p_a
                ev_ref = o.expected_return(p_ref)
                if best is None or (ev_ref, -o.fight_id, -o.venue_id) > (best[1], -best[0].fight_id, -best[0].venue_id):
                    best, best_ref = (o, ev_ref, p_ref), ref
            if best is None:
                decisions.append(Decision(strat, fid, "abstain", "; ".join(sorted(no_ref_reasons)) or "no reference",
                                          p_model=pm_val, rejected_offers=rejected, candidates_considered=len(offers))); continue
            o, ev_ref, p_ref = best
            ev_model = None
            if pm_val is not None:
                p_m = pm_val if o.side == "a" else 1.0 - pm_val
                ev_model = o.expected_return(p_m)
            common = dict(side=o.side, offer=o.to_dict(), ev_reference=ev_ref, ev_model=ev_model, p_reference=p_ref,
                          p_model=pm_val, reference=best_ref.to_dict(), candidates_considered=len(offers), rejected_offers=rejected)
            if ev_ref < float(rule["min_ev_reference"]):
                decisions.append(Decision(strat, fid, "pass", f"best market-reference return {ev_ref:+.1%} below {rule['min_ev_reference']:.0%}", **common)); continue
            if rule.get("require_model"):
                if pm_val is None:
                    decisions.append(Decision(strat, fid, "abstain", "model produced no probability for this fight", **common)); continue
                if ev_model < float(rule["min_ev_model"]):
                    decisions.append(Decision(strat, fid, "pass", f"model return {ev_model:+.1%} below {rule['min_ev_model']:.0%}", **common)); continue
            if stopped:
                decisions.append(Decision(strat, fid, "pass", f"bankroll {bankroll.get(strat):.1f} at or below stop {stop_at:.0f}; no new selections", **common)); continue
            qualifying.append((o, ev_ref, common))
        # rank: ev_reference desc, fight_id asc, venue_id asc; cap units per card
        qualifying.sort(key=lambda t: (-t[1], t[0].fight_id, t[0].venue_id))
        used = 0.0; cap = float(st["max_units_per_card"])
        for rank, (o, ev_ref, common) in enumerate(qualifying, start=1):
            if used + stake > cap + 1e-9:
                decisions.append(Decision(strat, o.fight_id, "pass", f"card cap {cap:.0f} units reached (rank {rank})", rank=rank, **common)); continue
            used += stake
            decisions.append(Decision(strat, o.fight_id, "bet", "qualified", stake=stake, rank=rank, **common))
    return decisions
