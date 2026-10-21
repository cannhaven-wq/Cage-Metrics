"""BT-001: how many bets the pre-registered pass bar would need.

Deterministic, standard library only, reads no data and no outcomes. It
answers one question for RESULTS_2026-10-21.md: given the bar fixed in
BACKTEST_PLAN_2026-10-21.md §6 (Bonferroni over 15 tests, the event-bootstrap
lower bound of ROI above zero), how many flat 1-unit bets would a strategy need
before it could pass, and how wide is the interval on the sample we actually
have?

Model: a flat bet at decimal price d on a side that truly wins with
probability p returns d - 1 with probability p and -1 otherwise, so its mean is
p*d - 1 (the ROI) and its standard deviation is d*sqrt(p*(1-p)). Bets are
treated as independent; clustering by card can only make the real requirement
larger (PRED-001 floors the design effect at 1 for the same reason).

Run:  python research/backtest/power.py
"""

from statistics import NormalDist

K_TESTS = 15                 # plan §3: strategy x execution-time tests
ALPHA_FAMILY = 0.05
POWER = 0.80
OVERROUND = 1.042            # median single-book overround measured on 2026-10-17 (RESULTS §2)
ACTIONABLE_FIGHTS = 58       # W3 two-sided pre-bell fights on settled cards (RESULTS §1)

Z = NormalDist().inv_cdf
z_bonf = Z(1 - ALPHA_FAMILY / (2 * K_TESTS))   # two-sided Bonferroni interval
z_95 = Z(0.975)
z_pow = Z(POWER)


def sd_per_bet(decimal: float, roi: float) -> float:
    """SD of one flat bet's return when the true ROI is `roi` at price `decimal`."""
    p = (1 + roi) / decimal
    return decimal * (p * (1 - p)) ** 0.5


def bets_needed(decimal: float, roi: float) -> int:
    """Bets for an 80% chance that the Bonferroni lower bound clears zero."""
    s = sd_per_bet(decimal, roi)
    return int(-(-((z_bonf + z_pow) * s / roi) ** 2 // 1))


def main() -> None:
    prices = [("short favourite", 1.40), ("favourite", 1.65), ("near even", 1.95),
              ("underdog", 2.60), ("long underdog", 4.00)]
    rois = [0.02, 0.05, 0.10]

    print(f"Bonferroni z (K={K_TESTS}) = {z_bonf:.3f}; power z = {z_pow:.3f}\n")
    print("Bets needed for an 80% chance of passing the plan's bar")
    print(f"{'price':<18}{'decimal':>8}" + "".join(f"{'ROI +' + format(r, '.0%'):>12}" for r in rois))
    for name, d in prices:
        print(f"{name:<18}{d:>8.2f}" + "".join(f"{bets_needed(d, r):>12,}" for r in rois))

    print(f"\nInterval half-width on the {ACTIONABLE_FIGHTS} actionable fights "
          "(one bet per fight, true ROI 0)")
    print(f"{'price':<18}{'decimal':>8}{'95%':>10}{'Bonferroni':>12}")
    for name, d in prices:
        s = sd_per_bet(d, 0.0)
        se = s / ACTIONABLE_FIGHTS ** 0.5
        print(f"{name:<18}{d:>8.2f}{z_95 * se:>10.1%}{z_bonf * se:>12.1%}")

    hold = 1 - 1 / OVERROUND
    print(f"\nA fair-odds bettor paying a {OVERROUND - 1:.1%} overround starts at an "
          f"expected ROI of about {-hold:.1%} per bet.")


if __name__ == "__main__":
    main()
