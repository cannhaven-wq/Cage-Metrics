"""Retirement is confirmed by observation, and a bad read cannot cause one."""
from __future__ import annotations

import unittest

from cfl_engine.event_flow.retirement import (
    CONFIRMED,
    NOT_A_CANDIDATE,
    ON_CARD,
    PENDING,
    REQUIRED_CONFIRMATIONS,
    card_observations,
    verdict_for,
)

MAIN, SECOND, WITHDRAWN, REPLACEMENT, OTHER = 101, 102, 103, 104, 105


def observation(instant: str, fight_ids: list[int]) -> list[dict]:
    """One complete card appended in one statement: one observed_at for all."""
    return [{"fight_id": fid, "observed_at": instant, "bout_order": i + 1}
            for i, fid in enumerate(reversed(fight_ids))]


class TestWithdrawal(unittest.TestCase):
    """A fighter withdraws and the bout disappears — the UFC 331 shape."""

    def test_one_absence_is_not_enough(self):
        rows = (observation("2026-09-14T07:20:00Z", [MAIN, SECOND, WITHDRAWN])
                + observation("2026-09-15T07:20:00Z", [MAIN, SECOND]))
        v = verdict_for(rows, WITHDRAWN)
        self.assertEqual(v.state, PENDING)
        self.assertEqual(v.confirmations, 1)
        self.assertFalse(v.should_retire,
                         "a single absence retired a booking — a bad read would too")

    def test_two_consecutive_absences_confirm_it(self):
        rows = (observation("2026-09-14T07:20:00Z", [MAIN, SECOND, WITHDRAWN])
                + observation("2026-09-15T07:20:00Z", [MAIN, SECOND])
                + observation("2026-09-15T19:20:00Z", [MAIN, SECOND]))
        v = verdict_for(rows, WITHDRAWN)
        self.assertEqual(v.state, CONFIRMED)
        self.assertEqual(v.confirmations, 2)
        self.assertTrue(v.should_retire)

    def test_the_bouts_that_remain_are_never_candidates(self):
        rows = (observation("2026-09-14T07:20:00Z", [MAIN, SECOND, WITHDRAWN])
                + observation("2026-09-15T07:20:00Z", [MAIN, SECOND])
                + observation("2026-09-15T19:20:00Z", [MAIN, SECOND]))
        for still_on in (MAIN, SECOND):
            self.assertEqual(verdict_for(rows, still_on).state, ON_CARD)


class TestFalsePositiveProtection(unittest.TestCase):
    """The rule exists because one bad read must not retire a live booking."""

    def test_a_single_bad_read_does_not_retire(self):
        """One truncated card, then the fight is back. Nothing is retired."""
        rows = (observation("2026-09-14T07:20:00Z", [MAIN, SECOND, OTHER])
                + observation("2026-09-15T07:20:00Z", [MAIN, SECOND])       # bad read
                + observation("2026-09-15T19:20:00Z", [MAIN, SECOND, OTHER]))
        v = verdict_for(rows, OTHER)
        self.assertEqual(v.state, ON_CARD)
        self.assertFalse(v.should_retire)

    def test_reappearing_resets_the_streak(self):
        """Absent, back, absent. That is one absence, not two."""
        rows = (observation("2026-09-13T07:20:00Z", [MAIN, OTHER])
                + observation("2026-09-14T07:20:00Z", [MAIN])                # absent
                + observation("2026-09-15T07:20:00Z", [MAIN, OTHER])         # back
                + observation("2026-09-16T07:20:00Z", [MAIN]))               # absent
        v = verdict_for(rows, OTHER)
        self.assertEqual(v.confirmations, 1)
        self.assertEqual(v.state, PENDING)
        self.assertFalse(v.should_retire,
                         "a flapping read was counted as consecutive absence")

    def test_a_single_observation_can_never_retire_anything(self):
        rows = observation("2026-09-15T07:20:00Z", [MAIN, SECOND])
        v = verdict_for(rows, WITHDRAWN)
        self.assertFalse(v.should_retire)

    def test_a_fight_never_seen_on_the_card_is_not_a_candidate(self):
        """Cards are announced piecemeal. Not-yet-scraped is not withdrawn."""
        rows = (observation("2026-09-14T07:20:00Z", [MAIN, SECOND])
                + observation("2026-09-15T07:20:00Z", [MAIN, SECOND]))
        v = verdict_for(rows, 999)
        self.assertEqual(v.state, NOT_A_CANDIDATE)
        self.assertFalse(v.should_retire)

    def test_an_empty_ledger_retires_nothing(self):
        self.assertFalse(verdict_for([], MAIN).should_retire)

    def test_the_threshold_is_the_only_knob(self):
        """Raising it makes the rule stricter, never looser."""
        rows = (observation("2026-09-14T07:20:00Z", [MAIN, WITHDRAWN])
                + observation("2026-09-15T07:20:00Z", [MAIN])
                + observation("2026-09-16T07:20:00Z", [MAIN]))
        self.assertTrue(verdict_for(rows, WITHDRAWN, required=2).should_retire)
        self.assertFalse(verdict_for(rows, WITHDRAWN, required=3).should_retire)


class TestOpponentSwap(unittest.TestCase):
    """The other class: a booking replaced rather than simply removed.

    Event 4282's shape — Gastelum vs Belgaroui superseded by Belgaroui vs Santos.
    The superseded booking leaves the card; the replacement arrives. One rule
    covers both, because the rule is about presence on the card and nothing else.
    """

    def test_the_superseded_booking_retires_and_the_replacement_does_not(self):
        rows = (observation("2026-09-10T07:20:00Z", [MAIN, WITHDRAWN])
                + observation("2026-09-11T07:20:00Z", [MAIN, REPLACEMENT])
                + observation("2026-09-12T07:20:00Z", [MAIN, REPLACEMENT]))
        self.assertTrue(verdict_for(rows, WITHDRAWN).should_retire)
        self.assertEqual(verdict_for(rows, REPLACEMENT).state, ON_CARD)

    def test_no_fighter_identity_is_consulted(self):
        """The rule reads fight ids, never names or fighter ids.

        A swap and a withdrawal are the same shape to it, which is why one rule
        is enough and why a name-matching heuristic is not needed.
        """
        rows = (observation("2026-09-10T07:20:00Z", [MAIN, WITHDRAWN])
                + observation("2026-09-11T07:20:00Z", [MAIN])
                + observation("2026-09-12T07:20:00Z", [MAIN]))
        self.assertTrue(verdict_for(rows, WITHDRAWN).should_retire)


class TestHistoryIsNotRewritten(unittest.TestCase):
    """Retiring is a verdict about the CURRENT card. It unsays nothing."""

    def test_the_verdict_writes_nothing(self):
        rows = (observation("2026-09-14T07:20:00Z", [MAIN, WITHDRAWN])
                + observation("2026-09-15T07:20:00Z", [MAIN])
                + observation("2026-09-16T07:20:00Z", [MAIN]))
        before = [dict(r) for r in rows]
        verdict_for(rows, WITHDRAWN)
        self.assertEqual(rows, before, "computing a verdict mutated the ledger")

    def test_the_earlier_observation_still_stands(self):
        """'It was bout 2 on the 14th' stays answerable after retirement."""
        rows = (observation("2026-09-14T07:20:00Z", [MAIN, WITHDRAWN])
                + observation("2026-09-15T07:20:00Z", [MAIN])
                + observation("2026-09-16T07:20:00Z", [MAIN]))
        self.assertTrue(verdict_for(rows, WITHDRAWN).should_retire)

        observed = [o for o in card_observations(rows) if WITHDRAWN in o.fight_ids]
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0].observed_at, "2026-09-14T07:20:00Z")
        historical = [r for r in rows if r["fight_id"] == WITHDRAWN]
        self.assertEqual(len(historical), 1,
                         "the withdrawn booking's history was erased")
        self.assertEqual(historical[0]["bout_order"], 1)

    def test_a_whole_card_shares_one_instant(self):
        rows = observation("2026-09-14T07:20:00Z", [MAIN, SECOND, OTHER])
        obs = card_observations(rows)
        self.assertEqual(len(obs), 1, "one append must read back as ONE card")
        self.assertEqual(obs[0].fight_ids, frozenset({MAIN, SECOND, OTHER}))

    def test_observations_are_newest_first_regardless_of_row_order(self):
        rows = (observation("2026-09-16T07:20:00Z", [MAIN])
                + observation("2026-09-14T07:20:00Z", [MAIN, WITHDRAWN]))
        self.assertEqual([o.observed_at for o in card_observations(rows)],
                         ["2026-09-16T07:20:00Z", "2026-09-14T07:20:00Z"])
        self.assertEqual([o.observed_at for o in card_observations(rows[::-1])],
                         ["2026-09-16T07:20:00Z", "2026-09-14T07:20:00Z"])


if __name__ == "__main__":
    unittest.main()
