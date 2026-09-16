"""Tests for the frozen CLV-001 arithmetic.

    python -m unittest cfl_engine/clv/test_devig.py -v

These check the numbers the published metric will eventually rest on. They are
pure — no database, no network — so they can run anywhere and cannot pass by
accident of environment.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from devig import (  # noqa: E402
    K_HI, K_LO, DevigError, american_to_decimal, american_to_prob,
    clv_return, closing_fair_probability, median, power_devig,
    proportional_devig, shin_devig,
)

PAIRS = [(0.55, 0.52), (0.70, 0.35), (0.48, 0.58), (0.90, 0.13), (0.34, 0.70)]


class TestConversions(unittest.TestCase):
    def test_american_to_prob_known_values(self):
        self.assertAlmostEqual(american_to_prob(150), 0.4000, places=4)
        self.assertAlmostEqual(american_to_prob(-200), 0.6667, places=4)

    def test_american_to_decimal_known_values(self):
        self.assertAlmostEqual(american_to_decimal(150), 2.5)
        self.assertAlmostEqual(american_to_decimal(-200), 1.5)

    def test_decimal_and_prob_are_consistent(self):
        """1/decimal is the vigged implied probability — the bar CLV_return clears."""
        for odds in (-500, -200, -110, 110, 150, 400):
            with self.subTest(odds=odds):
                self.assertAlmostEqual(1.0 / american_to_decimal(odds),
                                       american_to_prob(odds), places=12)


class TestPowerDevig(unittest.TestCase):
    def test_fair_probabilities_sum_to_one(self):
        for q_a, q_b in PAIRS:
            with self.subTest(pair=(q_a, q_b)):
                fa, fb, _ = power_devig(q_a, q_b)
                self.assertAlmostEqual(fa + fb, 1.0, places=12)

    def test_devig_shrinks_the_favourite_side_toward_fair(self):
        for q_a, q_b in PAIRS:
            with self.subTest(pair=(q_a, q_b)):
                fa, fb, _ = power_devig(q_a, q_b)
                self.assertLess(fa, q_a, "removing vig must lower each raw side")
                self.assertLess(fb, q_b)

    def test_k_lands_inside_the_protocol_bracket(self):
        for q_a, q_b in PAIRS:
            with self.subTest(pair=(q_a, q_b)):
                _, _, k = power_devig(q_a, q_b)
                self.assertGreater(k, K_LO)
                self.assertLess(k, K_HI)

    def test_ordering_is_preserved(self):
        """De-vig may not flip which side the market favours."""
        for q_a, q_b in PAIRS:
            with self.subTest(pair=(q_a, q_b)):
                fa, fb, _ = power_devig(q_a, q_b)
                self.assertEqual(q_a > q_b, fa > fb)

    def test_symmetric_pair_devigs_to_even(self):
        fa, fb, _ = power_devig(0.525, 0.525)
        self.assertAlmostEqual(fa, 0.5, places=10)
        self.assertAlmostEqual(fb, 0.5, places=10)

    def test_argument_order_does_not_change_the_answer(self):
        for q_a, q_b in PAIRS:
            with self.subTest(pair=(q_a, q_b)):
                fa, _, _ = power_devig(q_a, q_b)
                _, fa2, _ = power_devig(q_b, q_a)
                self.assertAlmostEqual(fa, fa2, places=12)

    def test_the_two_conventions_agree_exactly(self):
        """The frozen protocol says the sum is 'strictly decreasing in k'. For the
        formula it specifies, q^(1/k), the sum is INCREASING; it is decreasing
        only under q^k. The two are reparametrisations — the q^k root is the
        reciprocal — so the fair probabilities are identical and no number is
        affected. This test pins that equivalence, so the documentation defect
        stays documentation-only.
        """
        def devig_other_convention(q_a, q_b):
            lo, hi = K_LO, K_HI
            f = lambda k: q_a ** k + q_b ** k - 1.0
            flo = f(lo)
            for _ in range(300):
                mid = (lo + hi) / 2.0
                fm = f(mid)
                if (fm > 0) == (flo > 0):
                    lo, flo = mid, fm
                else:
                    hi = mid
            k = (lo + hi) / 2.0
            fa, fb = q_a ** k, q_b ** k
            t = fa + fb
            return fa / t, fb / t, k

        for q_a, q_b in PAIRS:
            with self.subTest(pair=(q_a, q_b)):
                fa1, _, k1 = power_devig(q_a, q_b)
                fa2, _, k2 = devig_other_convention(q_a, q_b)
                self.assertAlmostEqual(fa1, fa2, places=9,
                                       msg="the two conventions must agree on the "
                                           "fair probability")
                self.assertAlmostEqual(1.0 / k1, k2, places=6,
                                       msg="and their roots must be reciprocals")

    def test_the_stated_direction_is_the_wrong_one(self):
        """Guards the reason `_bisect` is direction-agnostic. If this ever starts
        failing, the protocol's claim became true and the note can go."""
        q_a, q_b = 0.55, 0.52
        f = lambda k: q_a ** (1.0 / k) + q_b ** (1.0 / k) - 1.0
        self.assertLess(f(K_LO), f(K_HI),
                        "for q^(1/k) the sum is increasing in k; the protocol says "
                        "decreasing, which is why the implementation must not rely "
                        "on the claim")


class TestPairRejection(unittest.TestCase):
    def test_sentinel_prices_are_refused(self):
        """R-03. The feed emits -199900 / +199900 when a book pulls a market."""
        for bad in (0.9995, 0.0005, 0.98, 0.02):
            with self.subTest(q=bad):
                with self.assertRaises(DevigError):
                    power_devig(bad, 0.5)

    def test_a_pair_with_no_overround_is_refused(self):
        with self.assertRaises(DevigError):
            power_devig(0.48, 0.48)

    def test_none_is_refused(self):
        with self.assertRaises(DevigError):
            power_devig(None, 0.5)

    def test_the_refusal_says_which_rule(self):
        with self.assertRaises(DevigError) as ctx:
            power_devig(0.99, 0.5)
        self.assertIn("R-03", str(ctx.exception))


class TestConsensus(unittest.TestCase):
    def test_three_books_are_enough(self):
        fair, n = closing_fair_probability([(0.55, 0.52), (0.56, 0.51), (0.54, 0.53)])
        self.assertEqual(n, 3)
        self.assertTrue(0.0 < fair < 1.0)

    def test_two_books_are_not(self):
        """Q-02: the primary requires at least three."""
        with self.assertRaises(DevigError) as ctx:
            closing_fair_probability([(0.55, 0.52), (0.56, 0.51)])
        self.assertIn("minimum is 3", str(ctx.exception))

    def test_ineligible_books_are_dropped_and_can_drop_below_the_floor(self):
        pairs = [(0.55, 0.52), (0.56, 0.51), (0.9995, 0.0005)]
        with self.assertRaises(DevigError):
            closing_fair_probability(pairs)

    def test_devig_per_book_then_median_is_not_median_then_devig(self):
        """Q-02 fixes the order, and the order changes the answer — but only when
        the median q_a and the median q_b come from DIFFERENT books.

        When one book is median on both sides, "median then de-vig" happens to
        de-vig that book's own real pair and the two orders coincide. That is a
        coincidence of the data, not an equivalence of the methods, and a test
        built on such a case would prove nothing. So this uses a set whose median
        pair is SYNTHETIC — (0.55, 0.51), which no book quoted — which is exactly
        the situation Q-02's ordering exists to rule out.
        """
        pairs = [(0.55, 0.52), (0.60, 0.50), (0.52, 0.51)]
        med_qa = median([a for a, _ in pairs])
        med_qb = median([b for _, b in pairs])
        self.assertNotIn((med_qa, med_qb), pairs,
                         "this case is only meaningful if the median pair is one "
                         "no book actually quoted")

        per_book, _ = closing_fair_probability(pairs)
        median_then, _, _ = power_devig(med_qa, med_qb)
        self.assertNotAlmostEqual(
            per_book, median_then, places=6,
            msg="de-vig-then-median and median-then-de-vig are different "
                "estimators; Q-02 picks the first",
        )

    def test_the_two_orders_can_coincide_and_that_is_not_equivalence(self):
        """The converse, pinned so nobody 'simplifies' the implementation after
        seeing the two orders agree on one example."""
        pairs = [(0.55, 0.52), (0.62, 0.45), (0.50, 0.58)]
        med = (median([a for a, _ in pairs]), median([b for _, b in pairs]))
        self.assertIn(med, pairs, "here the median pair IS a real book's quote")
        per_book, _ = closing_fair_probability(pairs)
        median_then, _, _ = power_devig(*med)
        self.assertAlmostEqual(per_book, median_then, places=10)

    def test_median_is_lower_of_two_on_an_even_count(self):
        self.assertEqual(median([0.1, 0.2, 0.3, 0.4]), 0.2)

    def test_median_of_nothing_is_refused(self):
        with self.assertRaises(DevigError):
            median([])


class TestClvReturn(unittest.TestCase):
    def test_exactly_fair_is_zero(self):
        """+150 is decimal 2.5; a fair closing probability of 1/2.5 is break-even."""
        self.assertAlmostEqual(clv_return(1.0 / 2.5, 150), 0.0, places=12)

    def test_beating_the_close_is_positive(self):
        self.assertGreater(clv_return(0.45, 150), 0.0)

    def test_losing_to_the_close_is_negative(self):
        self.assertLess(clv_return(0.35, 150), 0.0)

    def test_the_bar_is_the_vigged_publish_probability(self):
        """Conservative by construction: the threshold is 1/decimal, which is the
        VIGGED implied probability at publish, not a fair one."""
        for odds in (-250, -110, 120, 300):
            with self.subTest(odds=odds):
                bar = american_to_prob(odds)
                self.assertAlmostEqual(clv_return(bar, odds), 0.0, places=12)
                self.assertGreater(clv_return(bar + 0.01, odds), 0.0)
                self.assertLess(clv_return(bar - 0.01, odds), 0.0)

    def test_a_worked_dog_example(self):
        """Posted +150 (decimal 2.5), closing fair 0.44 -> 0.44*2.5 - 1 = +0.10."""
        self.assertAlmostEqual(clv_return(0.44, 150), 0.10, places=10)

    def test_missing_inputs_are_refused(self):
        for a, b in ((None, 150), (0.5, None)):
            with self.subTest(args=(a, b)):
                with self.assertRaises(DevigError):
                    clv_return(a, b)

    def test_a_non_probability_is_refused(self):
        for p in (0.0, 1.0, -0.2, 1.5):
            with self.subTest(p=p):
                with self.assertRaises(DevigError):
                    clv_return(p, 150)


class TestSensitivities(unittest.TestCase):
    """Proportional and Shin are frozen sensitivities — never the primary."""

    def test_proportional_sums_to_one(self):
        for q_a, q_b in PAIRS:
            with self.subTest(pair=(q_a, q_b)):
                fa, fb = proportional_devig(q_a, q_b)
                self.assertAlmostEqual(fa + fb, 1.0, places=12)

    def test_shin_sums_to_one(self):
        for q_a, q_b in PAIRS:
            with self.subTest(pair=(q_a, q_b)):
                fa, fb, _ = shin_devig(q_a, q_b)
                self.assertAlmostEqual(fa + fb, 1.0, places=9)

    def test_the_three_methods_disagree(self):
        """If they agreed there would be no point reporting sensitivities."""
        q_a, q_b = 0.70, 0.35
        power, _, _ = power_devig(q_a, q_b)
        prop, _ = proportional_devig(q_a, q_b)
        self.assertNotAlmostEqual(power, prop, places=4)

    def test_sensitivities_reject_the_same_bad_pairs(self):
        for fn in (proportional_devig, shin_devig):
            with self.subTest(fn=fn.__name__):
                with self.assertRaises(DevigError):
                    fn(0.9995, 0.0005)


if __name__ == "__main__":
    unittest.main(verbosity=2)
