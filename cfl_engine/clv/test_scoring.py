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
    BENCHMARK_NAME, BENCHMARK_NAME_LONG, CLOSE_REFERENCE_BASES,
    EXACT_REFERENCE_BASES, INADMISSIBLE_START_BASES, LIVE_CAPTURE_ERA_START,
    LOWER_BOUND_REFERENCE_BASES, MIN_BOOKS, NON_SCORING_REFERENCE_BASES,
    PRECEDES_BELL_BASES, PROTOCOL_TAG, PROTOCOL_VERSION,
    STALENESS_LIMIT_MINUTES, SUPERSEDED_START_BASES, UNSCORED_REASONS, Unscored,
    admissible_reference, canonical_sha256, closing_pairs, consensus,
    credible_capture_instant, is_eligible_book, lead_time_minutes,
    reference_is_lower_bound, score_row,
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


def score(quotes=None, fight=None, ref=START, books=BOOKS, now=NOW,
          basis="bell_at", first_bout=None, **over):
    return score_row(edge=edge(**over),
                     quotes=three_books() if quotes is None else quotes,
                     fight=FIGHT if fight is None else fight,
                     reference_instant=ref, now=now, eligible_book_ids=books,
                     reference_basis=basis, is_first_bout=first_bout)


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
            "only_pre_card_price":
                lambda: score(ref=None, basis="card_scheduled_start"),
            "no_previous_bout_completion":
                lambda: score(ref=None, basis=None, first_bout=False),
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


class TestCloseReference(unittest.TestCase):
    """Amendment 3 — the event-flow rule.

    A card is one scheduled start and then a queue. Only the first bout begins
    when the schedule says; every later bout begins when the one before it ends.
    A start-time view ALWAYS answers, so reading an instant without reading its
    basis hands every fight since 1994 a plausible-looking schedule — the same
    defect shape as R-13, a populated placeholder passing a presence check."""

    def test_a_real_bell_is_admissible_for_any_bout(self):
        self.assertEqual(admissible_reference(START, "bell_at"), START)
        self.assertEqual(admissible_reference(START, "bell_at", is_first_bout=False),
                         START)

    def test_the_previous_bouts_completion_IS_the_cutoff_for_later_bouts(self):
        """Amendment 5. Bout 2..N's cutoff is the exact completion of the bout
        before it — accepted as a PROXY that precedes the bell by the walkout
        interval, because it is the most consistent, observable and reproducible
        cutoff available."""
        self.assertIn("previous_bout_completion", CLOSE_REFERENCE_BASES)
        self.assertEqual(
            admissible_reference(START, "previous_bout_completion",
                                 is_first_bout=False), START)
        self.assertEqual(
            admissible_reference(START, "previous_bout_completion"), START)

    def test_that_cutoff_is_marked_as_preceding_the_bell(self):
        self.assertIn("previous_bout_completion", PRECEDES_BELL_BASES)
        self.assertIs(reference_is_lower_bound("previous_bout_completion"), True)
        for basis in ("bell_at", "scheduled_first_bout"):
            with self.subTest(basis=basis):
                self.assertIs(reference_is_lower_bound(basis), False)

    def test_the_scheduled_start_is_admissible_for_the_first_bout_only(self):
        self.assertEqual(
            admissible_reference(START, "scheduled_first_bout", is_first_bout=True),
            START)
        self.assertIsNone(
            admissible_reference(START, "scheduled_first_bout", is_first_bout=False),
            "the card's scheduled start is the FIRST fight's start and nobody "
            "else's; on bout twelve it sits hours early")

    def test_an_unknown_running_order_is_not_a_yes(self):
        """`is_first_bout` is None when the card's order was never recorded, and
        that must not pass as first-bout. Defaulting it to True would apply the
        card's schedule to every fight — the exact failure Amendment 3 fixes."""
        self.assertIsNone(admissible_reference(START, "scheduled_first_bout"))
        self.assertIsNone(
            admissible_reference(START, "scheduled_first_bout", is_first_bout=None))

    def test_provider_commence_alone_no_longer_qualifies(self):
        """Amendment 2 (b) admitted it for every fight; Amendment 3 narrows it to
        the first bout, where it is named for what it is. Narrowing, never
        widening."""
        self.assertIsNone(admissible_reference(START, "provider_commence"))
        self.assertIsNone(
            admissible_reference(START, "provider_commence", is_first_bout=True))
        self.assertTrue(SUPERSEDED_START_BASES.isdisjoint(CLOSE_REFERENCE_BASES))

    def test_the_event_date_fallback_is_still_not_admissible(self):
        for basis in INADMISSIBLE_START_BASES:
            with self.subTest(basis=basis):
                self.assertIsNone(admissible_reference(START, basis, True),
                                  "18:00 UTC on the event date is a placeholder, "
                                  "wrong by hours in both directions")

    def test_an_unknown_basis_is_not(self):
        for basis in (None, "", "guess", "BELL_AT", "market_disappearance"):
            with self.subTest(basis=basis):
                self.assertIsNone(admissible_reference(START, basis, True))

    def test_a_missing_instant_is_not_rescued_by_a_good_basis(self):
        self.assertIsNone(admissible_reference(None, "bell_at"))
        self.assertIsNone(admissible_reference(None, "previous_bout_completion"))

    def test_a_fight_with_no_reference_is_unscored_not_scored_on_a_placeholder(self):
        got = score(ref=admissible_reference(START, "event_date_fallback", True))
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "no_scheduled_start")

    def test_the_admissible_set_is_the_frozen_three(self):
        self.assertEqual(CLOSE_REFERENCE_BASES,
                         {"bell_at", "scheduled_first_bout",
                          "previous_bout_completion"})

    def test_the_pre_card_price_is_still_never_a_cutoff(self):
        self.assertEqual(NON_SCORING_REFERENCE_BASES, {"card_scheduled_start"})
        self.assertTrue(
            CLOSE_REFERENCE_BASES.isdisjoint(NON_SCORING_REFERENCE_BASES))

    def test_every_basis_is_either_exact_or_precedes_the_bell(self):
        self.assertEqual(EXACT_REFERENCE_BASES | PRECEDES_BELL_BASES,
                         CLOSE_REFERENCE_BASES)
        self.assertTrue(EXACT_REFERENCE_BASES.isdisjoint(PRECEDES_BELL_BASES))

    def test_the_lower_bound_set_is_exactly_the_previous_bout_case(self):
        self.assertEqual(LOWER_BOUND_REFERENCE_BASES, PRECEDES_BELL_BASES)
        self.assertEqual(LOWER_BOUND_REFERENCE_BASES,
                         {"previous_bout_completion"},
                         "only the previous-bout cutoff precedes the bell; any "
                         "other entry here would be a silent widening")


class TestLatePreFightProxy(unittest.TestCase):
    """Amendment 4 — tier 4, the one that stops exact start detection blocking.

    A fight cannot begin before its own card begins, so a quote strictly before
    the card's scheduled start is verifiably pre-fight for EVERY fight on the
    card, running order or not. It bounds; it does not guess. What it gives up is
    lead time, not correctness."""

    def test_a_pre_card_price_is_recognised_and_NOT_scored(self):
        """Amendment 4.1. The quote is safely pre-fight — a fight cannot begin
        before its card does — and on a later bout it is hours early. Safely
        pre-fight is not the same as LATE, and calling both by one name would
        make the benchmark mean different things on different fights of the same
        card."""
        got = score(ref=None, basis="card_scheduled_start")
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "only_pre_card_price")

    def test_a_pre_card_price_is_distinguished_from_having_no_price(self):
        """Two different situations, two different reasons. One is 'we hold a
        verifiably pre-fight price that is not late enough'; the other is 'we
        hold nothing'. Collapsing them would hide which problem to fix."""
        self.assertEqual(score(ref=None, basis="card_scheduled_start")["reason"],
                         "only_pre_card_price")
        self.assertEqual(score(ref=None, basis=None)["reason"],
                         "no_scheduled_start")

    def test_the_withdrawn_basis_is_recognised_but_never_admissible(self):
        self.assertIn("card_scheduled_start", NON_SCORING_REFERENCE_BASES)
        self.assertNotIn("card_scheduled_start", CLOSE_REFERENCE_BASES)
        self.assertIsNone(admissible_reference(START, "card_scheduled_start"))
        self.assertIsNone(
            admissible_reference(START, "card_scheduled_start", is_first_bout=False))

    def test_a_later_bout_with_no_completion_on_file_says_exactly_that(self):
        got = score(ref=None, basis=None, first_bout=False)
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "no_previous_bout_completion",
                         "recording one completion makes the already-captured "
                         "snapshots scorable, so the report must name it")

    def test_the_three_unscorable_states_are_told_apart(self):
        self.assertEqual(
            score(ref=None, basis="card_scheduled_start")["reason"],
            "only_pre_card_price")
        self.assertEqual(
            score(ref=None, basis=None, first_bout=False)["reason"],
            "no_previous_bout_completion")
        self.assertEqual(
            score(ref=None, basis=None, first_bout=True)["reason"],
            "no_scheduled_start")

    def test_every_scored_row_records_its_lead_time_to_the_cutoff(self):
        for basis in sorted(CLOSE_REFERENCE_BASES):
            with self.subTest(basis=basis):
                got = score(basis=basis, first_bout=(basis != "previous_bout_completion"))
                self.assertTrue(got["scored"], got["reason"])
                self.assertAlmostEqual(got["lead_time_minutes"], 10.0, places=6)
                self.assertIs(got["lead_time_is_lower_bound"],
                              basis == "previous_bout_completion")

    def test_the_provenance_reed_asked_to_preserve_is_all_present(self):
        """Cutoff timestamp, cutoff basis, selected quote timestamp, lead time,
        source quote ids, protocol version — every scored observation."""
        got = score(basis="previous_bout_completion", first_bout=False)
        self.assertTrue(got["scored"], got["reason"])
        self.assertEqual(got["close_basis"], "previous_bout_completion")
        self.assertEqual(got["proxy_quoted_at"], FRESH)
        self.assertIsNotNone(got["lead_time_minutes"])
        self.assertIsNotNone(got["lead_time_is_lower_bound"])
        self.assertTrue(got["quote_ids"])
        self.assertEqual(got["consensus"]["protocol"], PROTOCOL_TAG)
        self.assertTrue(got["consensus_sha256"])

    def test_an_unknown_basis_is_neither_exact_nor_bounded(self):
        self.assertIsNone(reference_is_lower_bound(None),
                          "None, never False — False would assert the lead time "
                          "is exact")
        self.assertIsNone(reference_is_lower_bound("something_new"))

    def test_the_lead_time_is_measured_from_the_latest_contributing_quote(self):
        """The 'late' in late pre-fight price proxy. A consensus assembled partly
        from older books must report the lead time it actually has."""
        got = score(quotes=three_books(at=START - dt.timedelta(minutes=5)))
        self.assertTrue(got["scored"], got["reason"])
        self.assertAlmostEqual(got["lead_time_minutes"], 5.0, places=6)
        self.assertEqual(got["proxy_quoted_at"], START - dt.timedelta(minutes=5))

    def test_five_minute_capture_produces_a_five_minute_lead_time(self):
        """What Amendment 4's cadence buys: the proxy is minutes old, not half an
        hour, so 'late pre-fight price' is a fair description of it."""
        got = score(quotes=three_books(at=START - dt.timedelta(minutes=4)))
        self.assertLess(got["lead_time_minutes"], 5.0)

    def test_lead_time_needs_both_ends(self):
        self.assertIsNone(lead_time_minutes(None, START))
        self.assertIsNone(lead_time_minutes(START, None))

    def test_the_benchmark_is_never_called_the_closing_line(self):
        for name in (BENCHMARK_NAME, BENCHMARK_NAME_LONG):
            with self.subTest(name=name):
                self.assertIn("proxy", name.lower())
        self.assertNotEqual(BENCHMARK_NAME.lower(), "closing line")

    def test_the_stored_artifact_names_the_benchmark_and_the_basis(self):
        got = score(basis="previous_bout_completion")
        self.assertEqual(got["consensus"]["benchmark"], BENCHMARK_NAME)
        self.assertEqual(got["consensus"]["close_basis"], "previous_bout_completion")

    def test_an_unscored_row_carries_no_lead_time(self):
        got = score(books=None)
        self.assertFalse(got["scored"])
        self.assertIsNone(got["lead_time_minutes"])
        self.assertIsNone(got["proxy_quoted_at"])


class TestTriggerIsNotTheClose(unittest.TestCase):
    """The distinction Amendment 3 turns on, and the one easiest to collapse by
    accident. The previous bout ending starts the 30-minute CAPTURE window. The
    CLOSE is the last valid pre-live quote for the upcoming fight."""

    def test_a_quote_taken_after_the_fight_started_is_excluded(self):
        # Three books quote 10 minutes AFTER this bout began.
        after = START + dt.timedelta(minutes=10)
        got = score(quotes=three_books(at=after))
        self.assertFalse(got["scored"],
                         "a quote taken once the fight was under way can never "
                         "be its closing price")
        self.assertEqual(got["diagnostics"]["after_reference"], 6)

    def test_a_quote_exactly_at_the_start_is_excluded(self):
        got = score(quotes=three_books(at=START))
        self.assertFalse(got["scored"], "strictly before, so the boundary is out")

    def test_the_close_is_the_last_quote_before_the_start_not_the_trigger(self):
        """The trigger (previous bout's completion) is also this fight's
        reference here, but the SCORED close must still be the last quote before
        it — not a quote at the trigger, and not the trigger instant itself."""
        early = START - dt.timedelta(minutes=40)
        late = START - dt.timedelta(minutes=5)
        quotes = three_books(at=early) + three_books(at=late)
        for i, q in enumerate(quotes[6:], start=100):
            q["id"] = i                       # distinguish the late batch
        got = score(quotes=quotes)
        self.assertTrue(got["scored"], got["reason"])
        self.assertTrue(all(qid >= 100 for qid in got["quote_ids"]),
                        "the close must be the LAST eligible quote before the "
                        "start, not an earlier one still inside the window")

    def test_capture_after_the_trigger_still_scores_the_pre_start_quote(self):
        """The case the whole rule exists for: a late-card fight whose quotes
        only exist because the previous bout ending triggered capture. They are
        pre-live for THIS fight and must score."""
        got = score(quotes=three_books(at=START - dt.timedelta(minutes=12)))
        self.assertTrue(got["scored"], got["reason"])
        self.assertEqual(got["closing_book_count"], 3)


class TestFrozenBookList(unittest.TestCase):
    """Amendment 2 (a). Q-02 froze the rule at the freeze and the list was never
    written down; the dry run found it and this is what stops it recurring."""

    def test_the_protocol_now_carries_a_named_list(self):
        with open(PROTOCOL_JSON, encoding="utf-8") as fh:
            books = json.load(fh).get("eligible_books")
        self.assertTrue(books, "Q-02 requires a fixed NAMED list; it is missing")
        self.assertEqual(len(books), len(set(books)), "duplicate book name")

    def test_no_aggregate_or_prediction_market_is_on_the_list(self):
        with open(PROTOCOL_JSON, encoding="utf-8") as fh:
            books = json.load(fh)["eligible_books"]
        for name in books:
            with self.subTest(book=name):
                self.assertTrue(is_eligible_book(name),
                                f"{name} is excluded by kind and cannot be named "
                                f"eligible")

    def test_freezing_the_list_did_not_open_publication(self):
        """The whole point of the separation. Amendment 2 removes a blocker from
        the WRITE path; it must not touch the PUBLISH path."""
        with open(PROTOCOL_JSON, encoding="utf-8") as fh:
            gate = json.load(fh)["publication_gate"]
        self.assertFalse(gate["publication_allowed"])
        self.assertIn("sample_floor_met", gate["blocked_by"])
        self.assertIn("interval_excludes_zero", gate["blocked_by"])
        self.assertEqual(gate["sample_floor"]["scored_observations_current"], 0)

    def test_the_amendment_chain_is_intact(self):
        with open(PROTOCOL_JSON, encoding="utf-8") as fh:
            protocol = json.load(fh)
        chain = protocol["amendments"]
        self.assertEqual(chain[0]["sha256_before"], protocol["sha256_at_v1_0_0"])
        for a, b in zip(chain, chain[1:]):
            self.assertEqual(a["sha256_after"], b["sha256_before"],
                             "an amendment must chain from the one before it")
            self.assertEqual(a["version_after"], b["version_before"])
        self.assertEqual(chain[-1]["sha256_after"], protocol["protocol_sha256"])
        self.assertEqual(chain[-1]["version_after"], protocol["version"])
        for a in chain:
            self.assertFalse(a["motivated_by_observed_results"])


class TestProtocolPinning(unittest.TestCase):
    def test_the_module_version_matches_the_frozen_protocol(self):
        with open(PROTOCOL_JSON, encoding="utf-8") as fh:
            protocol = json.load(fh)
        self.assertEqual(protocol["version"], PROTOCOL_VERSION)
        self.assertEqual(protocol["status"], "frozen")

    def test_the_recorded_hash_matches_the_protocol_on_disk(self):
        import hashlib
        md = os.path.join(REPO_ROOT, "research", "clv",
                          "CLV_MEASUREMENT_PROTOCOL.md")
        with open(md, "rb") as fh:
            on_disk = hashlib.sha256(fh.read()).hexdigest()
        with open(PROTOCOL_JSON, encoding="utf-8") as fh:
            self.assertEqual(on_disk, json.load(fh)["protocol_sha256"],
                             "the protocol was edited without recording an "
                             "amendment, or the amendment forgot the hash")

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
