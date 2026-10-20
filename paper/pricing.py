"""Offer normalisation: every venue becomes "risk 1 unit, net payout if the side wins".

A sportsbook price and a Polymarket purchase are different instruments. This
module reduces both to the same two numbers, so the strategy evaluator never
has to know where an offer came from:

    stake_cost   units risked, fees included (the strategy risks exactly one)
    net_if_win   units received net of stake and fees if the side wins

Expected net return against a probability p is then  p * net_if_win - (1 - p) * stake_cost,
divided by stake_cost. For a sportsbook that is the familiar p * D - 1.

Polymarket purchases are priced by WALKING THE ASK LADDER: shares are bought
from the best ask upward until the budget is spent, each level paying the
taker fee the market reports. A displayed price, a midpoint or the Gamma
`outcomePrices` number is never used; an offer with no executable asks, no
fee rate, or not enough depth to place the whole stake is rejected with a
named reason rather than filled hypothetically.

Nothing here reads a clock, a database or the network.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


class OfferRejected(ValueError):
    """An offer that cannot be priced honestly. The reason is the message."""


# --------------------------------------------------------------------------- odds arithmetic

def american_to_decimal(american: float) -> float:
    a = float(american)
    if abs(a) < 100:
        raise OfferRejected(f"invalid American odds {american}")
    return 1.0 + a / 100.0 if a > 0 else 1.0 + 100.0 / -a


def american_to_implied(american: float) -> float:
    a = float(american)
    if abs(a) < 100:
        raise OfferRejected(f"invalid American odds {american}")
    return 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)


def devig_proportional(american_a: float, american_b: float) -> float:
    """Vig-free p(A) from one book's two-sided quote. Both sides required."""
    pa, pb = american_to_implied(american_a), american_to_implied(american_b)
    return pa / (pa + pb)


def net_odds_to_american(net_if_win: float, stake_cost: float) -> float:
    """The American price equivalent to 'risk stake_cost to net net_if_win'."""
    if stake_cost <= 0 or net_if_win <= 0:
        raise OfferRejected("non-positive stake or payout")
    r = net_if_win / stake_cost
    return 100.0 * r if r >= 1.0 else -100.0 / r


# --------------------------------------------------------------------------- the normalised offer

@dataclass
class Offer:
    venue_id: int
    venue_kind: str                 # 'sportsbook' | 'polymarket'
    fight_id: int
    side: str                       # 'a' | 'b'
    fighter_id: int
    stake_cost: float               # units risked, fees included
    net_if_win: float               # units net if the side wins
    retrieved_at: str               # ISO instant we observed it
    provider_ts: Optional[str]      # ISO instant the provider last updated it (None if not given)
    source: dict = field(default_factory=dict)   # the exact quote(s) used, verbatim

    @property
    def equivalent_american(self) -> float:
        return net_odds_to_american(self.net_if_win, self.stake_cost)

    def expected_return(self, p: float) -> float:
        """Expected net return per unit risked at probability p."""
        return (p * self.net_if_win - (1.0 - p) * self.stake_cost) / self.stake_cost

    def to_dict(self) -> dict:
        d = asdict(self)
        d["equivalent_american"] = round(self.equivalent_american, 1)
        return d


# --------------------------------------------------------------------------- sportsbook

def sportsbook_offer(*, venue_id: int, fight_id: int, side: str, fighter_id: int,
                     american: float, stake: float, retrieved_at: str,
                     provider_ts: Optional[str], quote: dict) -> Offer:
    d = american_to_decimal(american)
    return Offer(venue_id=venue_id, venue_kind="sportsbook", fight_id=fight_id, side=side,
                 fighter_id=fighter_id, stake_cost=stake, net_if_win=stake * (d - 1.0),
                 retrieved_at=retrieved_at, provider_ts=provider_ts, source=dict(quote))


# --------------------------------------------------------------------------- polymarket

#: Polymarket's published taker-fee form: fee = shares * rate * p * (1 - p), makers pay 0.
#: The RATE is never hard-coded: it comes from the market's own fee field at capture
#: time, in basis points. See paper/README.md "Fees" for what was and was not verified.
FEE_FORMULAS = {"p_times_1_minus_p": lambda rate, p: rate * p * (1.0 - p)}


def polymarket_fill(*, asks: list[dict], budget: float, fee_rate_bps: Optional[float],
                    fee_formula: str = "p_times_1_minus_p", min_fill_fraction: float = 1.0,
                    tick_size: Optional[float] = None, min_order_size: Optional[float] = None) -> dict:
    """Walk the executable asks and spend `budget` units (fees included) on YES shares.

    asks: [{"price": "0.57", "size": "120.5"}, ...] in any order; price is the
    cost per share in collateral, size is shares available at that price.
    Returns {shares, cost, fee, avg_price, levels_used, fill_fraction}.
    Raises OfferRejected when the fill would be hypothetical.
    """
    if fee_rate_bps is None:
        raise OfferRejected("polymarket: fee rate missing; fee rule cannot be applied")
    if fee_formula not in FEE_FORMULAS:
        raise OfferRejected(f"polymarket: unknown fee formula {fee_formula!r}")
    if not asks:
        raise OfferRejected("polymarket: no executable asks")
    rate = float(fee_rate_bps) / 10_000.0
    if rate < 0:
        raise OfferRejected("polymarket: negative fee rate")
    fee_of = FEE_FORMULAS[fee_formula]
    ladder = []
    for lvl in asks:
        try:
            p, s = float(lvl["price"]), float(lvl["size"])
        except (KeyError, TypeError, ValueError):
            raise OfferRejected("polymarket: malformed ask level")
        if not (0.0 < p < 1.0) or s <= 0:
            continue
        ladder.append((p, s))
    if not ladder:
        raise OfferRejected("polymarket: no executable asks")
    ladder.sort()                       # cheapest first; a BUY lifts the lowest ask
    remaining, shares, cost, fee, used = float(budget), 0.0, 0.0, 0.0, []
    for p, s in ladder:
        if remaining <= 1e-12:
            break
        per_share = p + fee_of(rate, p)             # collateral per share, fee included
        take = min(s, remaining / per_share)
        shares += take
        cost += take * p
        fee += take * fee_of(rate, p)
        remaining -= take * per_share
        used.append({"price": p, "size": s, "taken": take})
    spent = cost + fee
    fill_fraction = spent / float(budget) if budget else 0.0
    if fill_fraction + 1e-9 < min_fill_fraction:
        raise OfferRejected(f"polymarket: insufficient depth, {fill_fraction:.0%} of the stake fillable")
    if min_order_size is not None and shares < float(min_order_size):
        raise OfferRejected(f"polymarket: fill of {shares:.2f} shares is under the market minimum {min_order_size}")
    return {"shares": shares, "cost": cost, "fee": fee, "spent": spent,
            "avg_price": cost / shares if shares else None, "levels_used": used,
            "fill_fraction": fill_fraction, "fee_rate_bps": float(fee_rate_bps),
            "fee_formula": fee_formula, "tick_size": tick_size}


def polymarket_offer(*, venue_id: int, fight_id: int, side: str, fighter_id: int,
                     book: dict, stake: float, retrieved_at: str, provider_ts: Optional[str],
                     min_fill_fraction: float = 1.0, unit_notional: float = 100.0) -> Offer:
    """book: one captured order book for the fighter's YES token, with fee fields.

    Required keys: asks, fee_rate_bps, market_status, settlement_ok (bool set by
    the capture after reading the market's resolution text), mapping_confidence.
    Each share pays 1 collateral if the side wins, 0 otherwise; the stake is
    lost in full on a loss. The fee is charged on the purchase.

    Order books are in collateral and shares, so one paper unit is sized as
    `unit_notional` collateral for the fill (depth and the market's minimum
    order size are judged at that size) and converted back to units after.
    """
    if book.get("market_status") not in ("open", "active"):
        raise OfferRejected(f"polymarket: market status {book.get('market_status')!r} is not open")
    if book.get("settlement_ok") is not True:
        raise OfferRejected("polymarket: settlement rules not verified as a plain fight-winner market")
    if book.get("mapping_confidence") != "exact":
        raise OfferRejected(f"polymarket: fighter mapping is {book.get('mapping_confidence')!r}, not exact")
    if unit_notional <= 0:
        raise OfferRejected("polymarket: unit notional must be positive")
    fill = polymarket_fill(asks=book.get("asks") or [], budget=stake * unit_notional, fee_rate_bps=book.get("fee_rate_bps"),
                           fee_formula=book.get("fee_formula", "p_times_1_minus_p"),
                           min_fill_fraction=min_fill_fraction, tick_size=book.get("tick_size"),
                           min_order_size=book.get("min_order_size"))
    fill["unit_notional"] = unit_notional
    net_if_win = (fill["shares"] * 1.0 - fill["spent"]) / unit_notional
    if net_if_win <= 0:
        raise OfferRejected("polymarket: fees exceed any possible payout at this price")
    return Offer(venue_id=venue_id, venue_kind="polymarket", fight_id=fight_id, side=side,
                 fighter_id=fighter_id, stake_cost=fill["spent"] / unit_notional, net_if_win=net_if_win,
                 retrieved_at=retrieved_at, provider_ts=provider_ts,
                 source={"token_id": book.get("token_id"), "condition_id": book.get("condition_id"),
                         "asks": book.get("asks"), "fill": fill, "book_hash": book.get("hash")})
