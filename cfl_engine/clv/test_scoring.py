"""Implementation tripwires for CLV-001 row scoring.

    python -m unittest cfl_engine/clv/test_scoring.py -v

`test_devig.py` checks the arithmetic. This file checks the things Reed named as
the ones that must not be able to go wrong quietly:

  1. each book is de-vigged separately BEFORE any median is taken;
  2. at least three eligible two-sided books are required;
  3. the consensus is the median of the per-book fair probabilities;
  4. CLV_return is computed from that median and the posted price, in that order;
  5. an epoch / import-era row can never score, under any combination of inputs;
  6. nothing here changes publication state.

Every one of these is written to FAIL if the property stops holding, not merely
to exercise the happy path. Several deliberately construct the case where a
sloppier implementation would still pass.

Pure: no database, no network, no clock — `now` is always injected.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from devig import median, power_devig                                # noqa: E402
from scoring import (                                                # noqa: E402
    LIVE_CAPTURE_ERA_START, MIN_BOOKS, PROTOCOL_TAG, PROTOCOL_VERSION,
    STALENESS_LIMIT_MINUTES, UNSCORED_REASONS, Unscored, canonical_sha256,
    closing_pairs, consensus, credible_capture_instant, is_eligible_book,
    score_row,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MIGRATION = os.path.join(REPO_ROOT, "research", "clv",
                         "proposed_2026-09-16_clv001_columns.sql")
PROTOCOL_JSON = os.path.join(REPO_ROOT, "research", "clv", "protocol.json")

NOW = dt.datetime(2026, 9, 16, 12, 0, tzinfo=dt.timezone.utc)
START = dt.datetime(2026, 9, 12, 22, 0, tzinfo=dt.timezone.utc)   # scheduled bell
FRESH = START - dt.timedelta(minutes=10)                          # inside the limit
EPOCH = dt.datetime(1970, 1, 1, 0, 0, 1, tzinfo=dt.timezone.utc)

BET, OPP = 101, 202
FIGHT = {"id": 1, "fighter_a_id": BET, "fighter_b_id": OPP}
BOOKS = {1, 3, 9, 10, 11}


def quote(qid, fighter_id, book_id, prob, at=FRESH):
    return {"id": qid, "fight_id": 1, "fighter_id": fighter_id,
            "book_id": book_id, "implied_prob": prob, "american_odds": None,
            "captured_at": at}


def three_books(pairs=((0.55, 0.52), (0.60, 0.50), (0.52, 0.51)), at=FRESH):
    """One two-sided quote per book. Default pairs are chosen so the median
    q_bet and the median q_opp come from DIFFERENT books — see
    test_devig_happens_per_book_before_any_median."""
    out, qid = [], 1
    for book_id, (q_bet, q_opp) in zip(sorted(BOOKS), pairs):
        out.append(quote(qid, BET, book_id, q_bet, at))
        out.append(quote(qid + 1, OPP, book_id, q_opp, at))
        qid += 2
    return out


def edge(**over):
    row = {"id": 7, "fight_id": 1, "event_date": "2026-09-12", "side": "a",
           "bet_fighter_id": BET, "odds_at_publish": 150,
           "published_at": START - dt.timedelta(days=5)}
    row.update(over)
    return row


def score(quotes=None, fight=None, ref=START, books=BOOKS, now=NOW, **over):
    return score_row(edge=edge(**over),
                     quotes=three_books() if quotes is None else quotes,
                     fight=FIGHT if fight is None else fight,
                     reference_instant=ref, now=now, eligible_book_ids=books)


# ---------------------------------------------------------------------------
# 1 + 3. De-vig per book first, then median
# ---------------------------------------------------------------------------

class TestOrderOfOperations(unittest.TestCase):
    def test_devig_happens_per_book_before_any_median(self):
        """The ONE property a shortcut would break.

        The default pairs are built so the median q_bet (0.55, book 1) and the
        median q_opp (0.51, book 9) come from different books. A "median the
        vigged prices, then de-vig once" implementation therefore de-vigs the
        synthetic pair (0.55, 0.51) — a pair no book quoted — and lands on a
        different number. If the two ever agree, the implementation reordered.
        """
        pairs = [(0.55, 0.52), (0.60, 0.50), (0.52, 0.51)]
        med_q_bet = median([p[0] for p in pairs])
        med_q_opp = median([p[1] for p in pairs])
        self.assertNotIn((med_q_bet, med_q_opp), pairs,
                         "the test is only meaningful when the median pair is "
                         "synthetic")

        got = score()
        self.assertTrue(got["scored"], got["reason"])
        wrong_order, _, _ = power_devig(med_q_bet, med_q_opp)
        self.assertNotAlmostEqual(
            got["closing_fair_probability"], wrong_order, places=6,
            msg="the consensus equals median-then-de-vig, so the implementation "
                "is taking the median of vigged prices — Q-02 fixes the "
                "opposite order")

    def test_the_consensus_is_the_median_of_the_per_book_fair_probabilities(self):
        got = score()
        per_book = [power_devig(a, b)[0]
                    for a, b in ((0.55, 0.52), (0.60, 0.50), (0.52, 0.51))]
        self.assertAlmostEqual(got["closing_fair_probability"],
                               median(per_book), places=12)

    def test_every_contributing_book_is_in_the_artifact_with_its_own_k(self):
        books = score()["consensus"]["books"]
        self.assertEqual(len(books), 3)
        self.assertEqual(len({b["k"] for b in books}), 3,
                         "three different pairs must solve to three different "
                         "exponents; one shared k means one shared de-vig")
        for b in books:
            fair, _, k = power_devig(b["q_bet"], b["q_opp"])
            self.assertAlmostEqual(b["fair_bet"], fair, places=12)
            self.assertAlmostEqual(b["k"], k, places=12)


# ---------------------------------------------------------------------------
# 2. The three-book floor
# ---------------------------------------------------------------------------

class TestBookFloor(unittest.TestCase):
    def test_three_books_score(self):
        self.assertTrue(score()["scored"])

    def test_two_books_do_not(self):
        got = score(quotes=three_books()[:4])
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "insufficient_books")

    def test_the_floor_counts_books_that_SURVIVED_devig_not_books_present(self):
        """Three books quote, one is a pulled-line sentinel. Two survive, so the
        row is unscored — the floor is not satisfied by showing up."""
        quotes = three_books()
        quotes[4] = quote(5, BET, 9, 0.9995)      # R-03 sentinel
        quotes[5] = quote(6, OPP, 9, 0.0005)
        got = score(quotes=quotes)
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "insufficient_books")

    def test_a_one_sided_book_does_not_count_toward_the_floor(self):
        quotes = three_books()
        quotes.pop()                              # book 9 loses its opponent side
        got = score(quotes=quotes)
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "insufficient_books")

    def test_the_floor_is_the_frozen_three(self):
        self.assertEqual(MIN_BOOKS, 3, "Q-02 froze three; changing it needs an "
                                       "amendment, not an edit")


# ---------------------------------------------------------------------------
# 4. CLV_return, and the order it is computed in
# ---------------------------------------------------------------------------

class TestClvReturn(unittest.TestCase):
    def test_return_is_the_consensus_times_decimal_publish_minus_one(self):
        got = score()
        self.assertAlmostEqual(
            got["clv_return"],
            got["closing_fair_probability"] * 2.5 - 1.0, places=12)

    def test_the_publish_price_is_never_devigged(self):
        """+150 is decimal 2.5. If the publish side were de-vigged the bar would
        move, so pin the exact break-even: a consensus of 1/2.5 returns zero."""
        quotes = [quote(1, BET, 1, 0.4008), quote(2, OPP, 1, 0.6008),
                  quote(3, BET, 3, 0.4008), quote(4, OPP, 3, 0.6008),
                  quote(5, BET, 9, 0.4008), quote(6, OPP, 9, 0.6008)]
        got = score(quotes=quotes)
        self.assertTrue(got["scored"], got["reason"])
        fair = got["closing_fair_probability"]
        self.assertAlmostEqual(got["clv_return"], fair * 2.5 - 1.0, places=12)

    def test_a_row_with_no_posted_price_cannot_score(self):
        got = score(odds_at_publish=None)
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "no_publish_price")


# ---------------------------------------------------------------------------
# 5. R-13 — an epoch row can never score
# ---------------------------------------------------------------------------

class TestEpochRowsCanNeverScore(unittest.TestCase):
    def test_the_epoch_is_not_a_credible_capture_instant(self):
        self.assertFalse(credible_capture_instant(EPOCH, NOW))

    def test_nothing_before_the_live_capture_era_is_credible(self):
        just_before = LIVE_CAPTURE_ERA_START - dt.timedelta(seconds=1)
        self.assertFalse(credible_capture_instant(just_before, NOW))
        self.assertTrue(credible_capture_instant(LIVE_CAPTURE_ERA_START, NOW))

    def test_a_future_timestamp_is_not_credible_either(self):
        self.assertFalse(credible_capture_instant(NOW + dt.timedelta(hours=1), NOW))

    def test_a_missing_timestamp_is_not_credible(self):
        self.assertFalse(credible_capture_instant(None, NOW))

    def test_an_all_epoch_fight_is_unscored_whatever_the_prices_are(self):
        got = score(quotes=three_books(at=EPOCH))
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "implausible_timestamp")

    def test_epoch_rows_cannot_pad_a_real_consensus_to_the_floor(self):
        """The dangerous case, and the reason R-13 exists at all: an epoch stamp
        is always 'before the fight', so it passes every ordering rule. Two real
        books plus one epoch book must NOT reach three."""
        quotes = three_books()[:4]                       # two real books
        quotes += [quote(9, BET, 10, 0.55, EPOCH), quote(10, OPP, 10, 0.52, EPOCH)]
        got = score(quotes=quotes)
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "insufficient_books")
        self.assertEqual(got["diagnostics"]["implausible_timestamp"], 2)

    def test_an_epoch_quote_id_never_reaches_the_provenance_array(self):
        quotes = three_books()
        quotes += [quote(99, BET, 10, 0.55, EPOCH), quote(100, OPP, 10, 0.52, EPOCH)]
        got = score(quotes=quotes)
        self.assertTrue(got["scored"], got["reason"])
        self.assertNotIn(99, got["quote_ids"])
        self.assertNotIn(100, got["quote_ids"])


# ---------------------------------------------------------------------------
# Staleness, eligibility, and the no-lookahead rule
# ---------------------------------------------------------------------------

class TestWindowAndEligibility(unittest.TestCase):
    def test_a_quote_older_than_the_limit_is_stale(self):
        old = START - dt.timedelta(minutes=STALENESS_LIMIT_MINUTES + 1)
        got = score(quotes=three_books(at=old))
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "stale_close")

    def test_a_quote_exactly_at_the_limit_still_counts(self):
        edge_of = START - dt.timedelta(minutes=STALENESS_LIMIT_MINUTES)
        self.assertTrue(score(quotes=three_books(at=edge_of))["scored"])

    def test_the_limit_is_the_frozen_forty_five_minutes(self):
        self.assertEqual(STALENESS_LIMIT_MINUTES, 45)

    def test_a_quote_at_or_after_the_reference_instant_is_excluded(self):
        got = score(quotes=three_books(at=START))
        self.assertFalse(got["scored"], "Q-01 says STRICTLY before")
        self.assertEqual(got["diagnostics"]["after_reference"], 6)

    def test_an_ineligible_book_contributes_nothing(self):
        got = score(books={1, 3})                  # book 9 no longer named
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "insufficient_books")

    def test_exchanges_and_aggregates_are_not_eligible_books(self):
        for name in ("Polymarket", "Kalshi", "Betfair", "BFO Consensus",
                     "CFL Consensus (Odds API)", "  polymarket  "):
            with self.subTest(name=name):
                self.assertFalse(is_eligible_book(name))
        for name in ("FanDuel", "DraftKings", "BetMGM"):
            with self.subTest(name=name):
                self.assertTrue(is_eligible_book(name))

    def test_no_frozen_book_list_means_no_row_can_score(self):
        got = score(books=None)
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "eligible_book_list_not_frozen")

    def test_no_scheduled_start_means_no_row_can_score(self):
        got = score(ref=None)
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "no_scheduled_start")

    def test_a_forecast_published_after_the_close_is_refused(self):
        got = score(published_at=START + dt.timedelta(hours=1))
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "forecast_not_before_close")

    def test_a_bet_fighter_no_longer_in_the_fight_is_refused(self):
        got = score(fight={"id": 1, "fighter_a_id": 999, "fighter_b_id": OPP})
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "bet_fighter_not_in_fight")

    def test_only_the_latest_surviving_quote_per_book_and_corner_is_used(self):
        quotes = three_books()
        earlier = FRESH - dt.timedelta(minutes=20)
        quotes += [quote(50, BET, 1, 0.70, earlier), quote(51, OPP, 1, 0.40, earlier)]
        got = score(quotes=quotes)
        self.assertTrue(got["scored"], got["reason"])
        self.assertNotIn(50, got["quote_ids"])
        self.assertIn(1, got["quote_ids"])


# ---------------------------------------------------------------------------
# 6. No publication state changes, and provenance integrity
# ---------------------------------------------------------------------------

class TestNoPublicationSideEffects(unittest.TestCase):
    def test_scoring_does_not_touch_the_publication_gate(self):
        """Scoring is a pure function of its inputs. Read the frozen gate, score
        a hundred rows, read it again — byte-identical."""
        with open(PROTOCOL_JSON, "rb") as fh:
            before = fh.read()
        for _ in range(100):
            score()
        with open(PROTOCOL_JSON, "rb") as fh:
            self.assertEqual(before, fh.read(),
                             "scoring wrote to the protocol; the gate is not "
                             "something computation may open")

    def test_the_gate_is_still_shut(self):
        with open(PROTOCOL_JSON, encoding="utf-8") as fh:
            gate = json.load(fh)["publication_gate"]
        self.assertFalse(gate["publication_allowed"])
        self.assertEqual(gate["sample_floor"]["scored_observations_required"], 100)
        self.assertEqual(gate["sample_floor"]["distinct_events_required"], 20)

    def test_the_scored_row_names_the_protocol_version_it_used(self):
        self.assertEqual(score()["consensus"]["protocol"], PROTOCOL_TAG)

    def test_the_artifact_hash_is_stable_and_detects_an_edit(self):
        got = score()
        self.assertEqual(canonical_sha256(got["consensus"]),
                         got["consensus_sha256"])
        tampered = json.loads(json.dumps(got["consensus"], default=str))
        tampered["median_fair_bet"] += 1e-9
        self.assertNotEqual(canonical_sha256(tampered), got["consensus_sha256"])

    def test_a_scored_row_carries_its_whole_provenance(self):
        """The database CHECK refuses partial provenance. Nothing should ever
        reach it that way."""
        got = score()
        for field in ("clv_return", "closing_fair_probability",
                      "closing_book_count", "quote_ids", "consensus",
                      "consensus_sha256"):
            with self.subTest(field=field):
                self.assertIsNotNone(got[field])
        self.assertEqual(len(got["quote_ids"]), 2 * got["closing_book_count"])

    def test_an_unscored_row_carries_no_partial_result(self):
        got = score(books=None)
        for field in ("clv_return", "closing_fair_probability",
                      "closing_book_count", "quote_ids", "consensus",
                      "consensus_sha256"):
            with self.subTest(field=field):
                self.assertIsNone(got[field])


# ---------------------------------------------------------------------------
# The closed vocabulary, and the script/database agreeing on it
# ---------------------------------------------------------------------------

class TestClosedVocabulary(unittest.TestCase):
    def test_an_unknown_reason_cannot_be_constructed(self):
        with self.assertRaises(ValueError):
            Unscored("it_was_probably_fine")

    def test_the_migration_and_the_module_list_the_same_reasons(self):
        """A reason added on one side only fails here, not at INSERT time."""
        with open(MIGRATION, encoding="utf-8") as fh:
            sql = fh.read()
        block = re.search(
            r"model_edges_clv_unscored_reason_known.*?\)\)\s*not valid;",
            sql, re.S)
        self.assertIsNotNone(block, "the unscored-reason constraint is gone")
        in_sql = set(re.findall(r"'([a-z_]+)'", block.group(0)))
        self.assertEqual(in_sql, set(UNSCORED_REASONS))

    def test_every_reason_is_reachable_or_named_as_a_global_precondition(self):
        """Guards against a vocabulary that accretes reasons nothing emits."""
        # These two are decided before any row is looked at, by `preflight` in
        # settle_clv.py — they disqualify the whole run, not a row.
        global_only = {"schema_incomplete", "protocol_version_mismatch"}
        reachable = {
            "eligible_book_list_not_frozen": lambda: score(books=None),
            "no_publish_price": lambda: score(odds_at_publish=None),
            "bet_fighter_not_in_fight":
                lambda: score(fight={"id": 1, "fighter_a_id": 999,
                                     "fighter_b_id": OPP}),
            "no_scheduled_start": lambda: score(ref=None),
            "no_closing_quotes": lambda: score(quotes=[]),
            "implausible_timestamp": lambda: score(quotes=three_books(at=EPOCH)),
            "stale_close": lambda: score(quotes=three_books(
                at=START - dt.timedelta(hours=3))),
            "one_sided_close": lambda: score(quotes=[
                q for q in three_books() if q["fighter_id"] == BET]),
            "non_market_price": lambda: score(quotes=[
                quote(1, BET, 1, 0.9995), quote(2, OPP, 1, 0.0005),
                quote(3, BET, 3, 0.9995), quote(4, OPP, 3, 0.0005),
                quote(5, BET, 9, 0.9995), quote(6, OPP, 9, 0.0005)]),
            "insufficient_books": lambda: score(quotes=three_books()[:4]),
            "forecast_not_before_close":
                lambda: score(published_at=START + dt.timedelta(hours=1)),
            # In band on both sides, but summing BELOW one: there is no vig to
            # remove, no root in the bracket, and it is not a coherent two-way
            # market. The band guard does not catch this, which is why the
            # bracket is a separate frozen rule.
            "devig_failed": lambda: score(quotes=[
                quote(1, BET, 1, 0.45), quote(2, OPP, 1, 0.45),
                quote(3, BET, 3, 0.45), quote(4, OPP, 3, 0.45),
                quote(5, BET, 9, 0.45), quote(6, OPP, 9, 0.45)]),
        }
        self.assertEqual(set(reachable) | global_only, set(UNSCORED_REASONS),
                         "a reason exists that no path produces and that is not "
                         "declared a global precondition")
        for reason, make in reachable.items():
            with self.subTest(reason=reason):
                self.assertEqual(make()["reason"], reason)

    def test_the_band_and_the_bracket_are_reported_as_different_failures(self):
        """R-03 and the bisection bracket are separate frozen rules, and the
        reason must name the one that actually bit. A sentinel pair is
        `non_market_price`; an in-band pair with no overround is `devig_failed`.
        Collapsing them would make the dry-run counts unactionable."""
        def pairs(q_bet, q_opp):
            return [{"book_id": b, "q_bet": q_bet, "q_opp": q_opp,
                     "quote_ids": [b], "quoted_at": FRESH} for b in (1, 3, 9)]

        with self.assertRaises(Unscored) as ctx:
            consensus(pairs(0.9995, 0.0005))
        self.assertEqual(ctx.exception.reason, "non_market_price")

        with self.assertRaises(Unscored) as ctx:
            consensus(pairs(0.45, 0.45))
        self.assertEqual(ctx.exception.reason, "devig_failed")

        with self.assertRaises(Unscored) as ctx:
            consensus([])
        self.assertEqual(ctx.exception.reason, "insufficient_books")


class TestProtocolPinning(unittest.TestCase):
    def test_the_module_version_matches_the_frozen_protocol(self):
        with open(PROTOCOL_JSON, encoding="utf-8") as fh:
            protocol = json.load(fh)
        self.assertEqual(protocol["version"], PROTOCOL_VERSION)
        self.assertEqual(protocol["status"], "frozen")

    def test_closing_pairs_reports_rather_than_raises(self):
        """The diagnostics are what tell a dry run WHY nothing scored, so this
        path must never throw on bad input."""
        pairs, diag = closing_pairs(
            [quote(1, BET, 1, None, None), quote(2, 999, 1, 0.5)],
            BET, OPP, START, NOW, BOOKS)
        self.assertEqual(pairs, [])
        self.assertEqual(diag["implausible_timestamp"], 1)
        self.assertEqual(diag["wrong_fighter"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
