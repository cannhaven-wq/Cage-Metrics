"""De-vigging: strip a book's overround out of a two-way market to recover the
book's implied probability for each side.

Three methods, all producing probabilities that sum to 1 across the two sides:

  multiplicative (a.k.a. proportional) -- scale each raw implied prob by
      1 / overround, so both sides keep the same ratio.  Because it strips an
      equal FRACTION from each side, it removes more absolute vig from the
      short (favourite) price, leaving the underdog relatively over-credited.
      On a skewed book this is the method that most favours the dog.

  additive               -- subtract an equal ABSOLUTE slice of the overround
      from each side.  Lands between the other two on a normal book, but on a
      very heavy favourite (e.g. -2000) the equal subtraction can drive the
      dog's probability negative, which is why it is only a comparison baseline
      here, never the pipeline default.

  power (DEFAULT)        -- find the exponent k (> 1 at any overround) such that
      r1**k + r2**k == 1, then the de-vigged prob for side i is r_i**k.  Raising
      to k > 1 shrinks a long price (near 1) far less in relative terms than a
      short one, so after renormalizing the FAVOURITE keeps the most probability
      and the DOG is discounted the most.  That is the correct direction for the
      empirical favourite-longshot bias -- underdog prices are inflated by
      recreational demand -- so power is the method the paper-trading pipeline
      uses for both entry and closing prices.

The three only meaningfully disagree when the market is skewed; on a near-pick
'em they land within a fraction of a point of each other.  On the -400 / +280
book in the self-test the favourite's fair prob runs 0.7525 (multiplicative) ->
0.7684 (additive) -> 0.7777 (power): a ~2.5 pp spread that flows straight into
the CLV numbers, which is why the method is pinned rather than left to chance.

Pure-stdlib on purpose (no numpy/pandas) so the grading pipeline can import it
without pulling the model's heavy deps.  American<->prob helpers mirror
cfl_engine/engine.py exactly so the two never drift.
"""

from __future__ import annotations

import math
from typing import Literal

Method = Literal["power", "multiplicative", "additive"]


# --------------------------------------------------------------------------- odds
def american_to_prob(odds: float) -> float:
    """Raw (vigged) implied probability of a single American price."""
    odds = float(odds)
    return 100.0 / (odds + 100.0) if odds > 0 else -odds / (-odds + 100.0)


def american_to_decimal(odds: float) -> float:
    odds = float(odds)
    return 1.0 + odds / 100.0 if odds > 0 else 1.0 - 100.0 / odds


def prob_to_american(p: float) -> int:
    """Fair American price for a (vig-free) probability. Inverse of the above."""
    if not 0.0 < p < 1.0:
        raise ValueError(f"probability out of range: {p}")
    return round(-100.0 * p / (1.0 - p)) if p >= 0.5 else round(100.0 * (1.0 - p) / p)


# --------------------------------------------------------------------------- devig
def _overround(r1: float, r2: float) -> float:
    return r1 + r2


def devig_multiplicative(r1: float, r2: float) -> tuple[float, float]:
    total = _overround(r1, r2)
    return r1 / total, r2 / total


def devig_additive(r1: float, r2: float) -> tuple[float, float]:
    excess = _overround(r1, r2) - 1.0
    return r1 - excess / 2.0, r2 - excess / 2.0


def _solve_power_k(r1: float, r2: float, tol: float = 1e-12, max_iter: int = 200) -> float:
    """Find k > 0 with r1**k + r2**k == 1 by bisection.

    f(k) = r1**k + r2**k is strictly decreasing in k for 0 < r_i < 1 (each term
    decays), so there is exactly one root.  At an overround (sum > 1) the root is
    k > 1; a fair book (sum == 1) gives k == 1.  Bracket [1, hi] by doubling hi
    until f(hi) < 1, then bisect.
    """
    if not (0.0 < r1 < 1.0 and 0.0 < r2 < 1.0):
        raise ValueError(f"raw probs must be strictly between 0 and 1: {r1}, {r2}")

    def f(k: float) -> float:
        return r1 ** k + r2 ** k

    lo, hi = 0.0, 1.0
    # If already <= 1 the book has no vig (or is inverted); root is at/below 1.
    if f(1.0) <= 1.0:
        lo, hi = 0.0, 1.0
    else:
        lo, hi = 1.0, 2.0
        while f(hi) > 1.0:
            hi *= 2.0
            if hi > 1e6:  # pathological; bail rather than loop forever
                break
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        val = f(mid)
        if abs(val - 1.0) < tol:
            return mid
        if val > 1.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def devig_power(r1: float, r2: float) -> tuple[float, float]:
    k = _solve_power_k(r1, r2)
    p1, p2 = r1 ** k, r2 ** k
    # Renormalize the last ulp of bisection error so the pair sums to exactly 1.
    s = p1 + p2
    return p1 / s, p2 / s


_DEVIG = {
    "power": devig_power,
    "multiplicative": devig_multiplicative,
    "additive": devig_additive,
}


def devig_pair(
    odds_a: float, odds_b: float, method: Method = "power"
) -> tuple[float, float]:
    """De-vig a two-way American market -> (fair_prob_a, fair_prob_b), sums to 1."""
    r1, r2 = american_to_prob(odds_a), american_to_prob(odds_b)
    return _DEVIG[method](r1, r2)


def devig_prob(odds_side: float, odds_other: float, method: Method = "power") -> float:
    """Fair probability of the FIRST side only. Convenience for CLV math, where
    we care about one side of a captured (over vs under) prop line."""
    return devig_pair(odds_side, odds_other, method)[0]


# --------------------------------------------------------------------------- tests
def _run_self_test() -> None:
    def approx(a, b, eps=1e-9):
        return abs(a - b) < eps

    # -- basic invariants ----------------------------------------------------
    # American<->prob round-trips.
    assert approx(american_to_prob(-200), 2.0 / 3.0)
    assert approx(american_to_prob(+150), 100.0 / 250.0)
    assert approx(american_to_decimal(+150), 2.5)
    assert approx(american_to_decimal(-200), 1.5)
    assert prob_to_american(2.0 / 3.0) == -200
    assert prob_to_american(0.4) == 150

    # Every method returns a normalized pair.
    for m in ("power", "multiplicative", "additive"):
        a, b = devig_pair(-110, -110, m)
        assert approx(a + b, 1.0), (m, a, b)
        # A perfectly symmetric market must de-vig to 50/50 under all methods.
        assert approx(a, 0.5) and approx(b, 0.5), (m, a, b)

    # Power method: k must actually solve r1**k + r2**k == 1.
    r1, r2 = american_to_prob(-400), american_to_prob(+280)
    k = _solve_power_k(r1, r2)
    assert approx(r1 ** k + r2 ** k, 1.0, 1e-9), (k, r1 ** k + r2 ** k)

    # -- the method gap on a skewed book: -400 / +280 -----------------------
    # Raw implied: fav 0.8000, dog 0.2632  (overround = +6.32%).
    fav_raw, dog_raw = american_to_prob(-400), american_to_prob(+280)
    over = fav_raw + dog_raw
    assert approx(fav_raw, 0.8) and 0.263 < dog_raw < 0.2633
    assert 1.06 < over < 1.064

    fav_mult, dog_mult = devig_multiplicative(fav_raw, dog_raw)
    fav_add, dog_add = devig_additive(fav_raw, dog_raw)
    fav_pow, dog_pow = devig_power(fav_raw, dog_raw)

    # All three normalize.
    for fv, dg in ((fav_mult, dog_mult), (fav_add, dog_add), (fav_pow, dog_pow)):
        assert approx(fv + dg, 1.0)

    # The ordering that motivates pinning power for CLV, verified numerically:
    #   power gives the favourite the MOST prob (dog discounted most),
    #   multiplicative the LEAST (dog credited most),
    #   additive sits between the two.
    assert fav_pow > fav_add > fav_mult, (fav_pow, fav_add, fav_mult)
    assert dog_mult > dog_add > dog_pow, (dog_mult, dog_add, dog_pow)

    # The favourite spread between the extreme methods is material -- ~2.5 pp on
    # this line -- which is the whole reason the method choice matters for CLV.
    gap_pp = (fav_pow - fav_mult) * 100.0
    assert gap_pp > 2.0, gap_pp

    print("devig.py self-test: PASS")
    print(f"\n  Skewed book -400 / +280  (raw fav {fav_raw:.4f}, dog {dog_raw:.4f}, "
          f"overround {(over - 1) * 100:+.2f}%)")
    print(f"  {'method':<16}{'fair fav':>10}{'fair dog':>10}{'fav Am':>9}{'dog Am':>9}")
    for name, (fv, dg) in (
        ("additive", (fav_add, dog_add)),
        ("multiplicative", (fav_mult, dog_mult)),
        ("power", (fav_pow, dog_pow)),
    ):
        print(f"  {name:<16}{fv:>10.4f}{dg:>10.4f}"
              f"{prob_to_american(fv):>+9d}{prob_to_american(dg):>+9d}")
    print(f"\n  favourite gap power - multiplicative = {gap_pp:.2f} pp "
          f"(power credits the favourite most, the dog least)")


if __name__ == "__main__":
    _run_self_test()
