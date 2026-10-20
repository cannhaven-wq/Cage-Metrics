"""The market reference: a margin-free consensus of at least three OTHER eligible sportsbooks.

Rules, all configurable in strategy_draft.json and all applied here:

- Only books in `venues.sportsbooks` count. Ids in `reference.excluded_book_ids`
  (the BFO placeholder consensus, the synthetic CFL consensus, Polymarket,
  Kalshi) never do, whatever list they appear in.
- A quote is fresh only if BOTH its retrieval time and, when the provider
  gives one, its provider update time are within `max_quote_age_minutes` of
  the lock instant. A quote without a provider timestamp is accepted on
  retrieval time alone, and that fact is recorded on the reference.
- Both sides of a book's quote are required; a one-sided quote is skipped.
- When the offer being judged comes from book X, X is removed from the
  reference so a price is never compared with itself.
- Below `min_other_books` there is no reference: the function returns None
  with the reason, and the caller passes the fight.

The consensus is the median of per-book proportional de-vig p(A).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from pricing import devig_proportional, OfferRejected


def parse_ts(v) -> datetime:
    """An aware instant. Naive timestamps are refused rather than assumed UTC."""
    t = datetime.fromisoformat(str(v).replace("Z", "+00:00").replace(" ", "T"))
    if t.tzinfo is None:
        raise ValueError(f"timestamp without a time zone: {v!r}")
    return t.astimezone(timezone.utc)


def quote_is_fresh(quote: dict, now: datetime, max_age_min: float, check_provider: bool = True) -> tuple[bool, str]:
    """(fresh, reason). Checks captured_at and, if present, provider_last_update."""
    limit = timedelta(minutes=max_age_min)
    try:
        cap = parse_ts(quote["captured_at"])
    except (KeyError, ValueError) as e:
        return False, f"no usable captured_at ({e})"
    if cap > now:
        return False, "captured after the lock instant"
    if now - cap > limit:
        return False, f"retrieved {int((now - cap).total_seconds() // 60)} min before lock, limit {int(max_age_min)}"
    if check_provider and quote.get("provider_last_update"):
        try:
            prov = parse_ts(quote["provider_last_update"])
        except ValueError as e:
            return False, f"bad provider timestamp ({e})"
        if now - prov > limit:
            return False, f"provider last updated {int((now - prov).total_seconds() // 60)} min before lock, limit {int(max_age_min)}"
    return True, "fresh"


@dataclass
class Reference:
    fight_id: int
    p_a: float
    book_ids: list[int]
    quotes: list[dict] = field(default_factory=list)   # the exact quotes used
    excluded_book_id: Optional[int] = None
    provider_ts_missing: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"fight_id": self.fight_id, "p_a": self.p_a, "book_ids": self.book_ids,
                "quotes": self.quotes, "excluded_book_id": self.excluded_book_id,
                "provider_ts_missing": self.provider_ts_missing}


def build_reference(fight_id: int, quotes: list[dict], *, now: datetime, cfg: dict,
                    exclude_book_id: Optional[int] = None) -> tuple[Optional[Reference], str]:
    """quotes: [{book_id, american_a, american_b, captured_at, provider_last_update?}] for one fight.

    Returns (Reference, 'ok') or (None, reason).
    """
    allowed = set(int(b) for b in cfg["venues"]["sportsbooks"]) - set(int(b) for b in cfg["reference"]["excluded_book_ids"])
    max_age = float(cfg["reference"]["max_quote_age_minutes"])
    check_prov = bool(cfg["offer"].get("check_provider_timestamp", True))
    used, ps, missing_prov, rejected = [], [], [], []
    seen = set()
    for q in quotes:
        bid = int(q["book_id"])
        if bid not in allowed or bid == exclude_book_id or bid in seen:
            continue
        if q.get("american_a") is None or q.get("american_b") is None:
            rejected.append((bid, "one-sided")); continue
        fresh, why = quote_is_fresh(q, now, max_age, check_prov)
        if not fresh:
            rejected.append((bid, why)); continue
        try:
            p = devig_proportional(q["american_a"], q["american_b"])
        except OfferRejected as e:
            rejected.append((bid, str(e))); continue
        seen.add(bid); used.append(dict(q)); ps.append(p)
        if not q.get("provider_last_update"):
            missing_prov.append(bid)
    need = int(cfg["reference"]["min_other_books"])
    if len(ps) < need:
        return None, (f"reference needs {need} fresh two-sided sportsbooks, found {len(ps)}"
                      + (f" (rejected: {rejected})" if rejected else ""))
    return Reference(fight_id=fight_id, p_a=float(statistics.median(ps)),
                     book_ids=sorted(seen), quotes=used, excluded_book_id=exclude_book_id,
                     provider_ts_missing=missing_prov), "ok"
