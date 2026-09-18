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
    AUDIT_ONLY_BASES, PRECEDES_BELL_BASES, PROTOCOL_TAG, PROTOCOL_VERSION,
    REQUIRED_PUBLISH_PROVENANCE, REQUIRED_QUOTE_PROVENANCE,
    NOT_AN_EDGE_LOCK_FIELDS, SNAPSHOT_EDGE_ID_FIELD,
    SNAPSHOT_EDGE_PUBLISHED_FIELD, VERIFIED_FIELDS,
    STALENESS_LIMIT_MINUTES, STALENESS_MEASURED_FROM, SUPERSEDED_START_BASES,
    UNSCORED_REASONS, Unscored,
    admissible_reference, canonical_sha256, closing_pairs, consensus,
    credible_capture_instant, forecast_lock, has_clv001_score,
    is_eligible_book, lead_time_minutes, missing_quote_provenance,
    reference_is_lower_bound, score_row, verify_against_stored,
    verify_publish_quote,
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

# The forecast lock: when the VALUE EDGE was published. Days before the card.
LOCK = START - dt.timedelta(days=5)
# When the MODEL PICK was published — earlier, and a different record. The engine
# posts a pick, and the edge derived from it appears later, once the price has
# moved far enough to flag one. Never the edge's lock.
PICK_PUBLISHED = LOCK - dt.timedelta(days=2)
MARKET = "odds-api-evt-7f3"                      # the provider's market id
PUBLISH_QUOTE_ID = 9001


def provenance(**over):
    """The §4 fields every usable quote must carry (Amendment 6 (a)).

    Spelled out rather than defaulted in `quote()` so a test can knock exactly
    one field out and see the row become unscorable for that reason alone.
    """
    row = {"source_event_id": MARKET, "feed_version": "odds-api-v4",
           "opponent_fighter_id": None, "provider_last_update": FRESH,
           "retrieved_at": FRESH, "market_status": "open",
           "raw": {"bookmaker": "draftkings"}}
    row.update(over)
    return row


def quote(qid, fighter_id, book_id, prob, at=FRESH, **over):
    row = {"id": qid, "fight_id": 1, "fighter_id": fighter_id,
           "book_id": book_id, "implied_prob": prob, "american_odds": None,
           "captured_at": at}
    row.update(provenance(
        opponent_fighter_id=OPP if fighter_id == BET else BET,
        provider_last_update=at, retrieved_at=at))
    row.update(over)
    return row


def publish_quote(**over):
    """The exact fight_odds row the edge posted its price from (§4 item 12)."""
    row = quote(PUBLISH_QUOTE_ID, BET, 1, 0.40, at=LOCK)
    row["american_odds"] = 150
    row.update(over)
    return row


def snapshot(**over):
    """The immutable pre-fight record that establishes the lock (R-07).

    The MODERN shape, carrying the edge's own identity and publication instant.
    `engine_published_at` is deliberately set to a DIFFERENT, earlier instant
    than `edge_published_at`: it is the model PICK's publication, and every test
    that would pass with the two equal proves nothing about which one is read.
    """
    row = {"id": 55, "fight_id": 1, "snapshot_at": LOCK + dt.timedelta(hours=1),
           "engine_published_at": PICK_PUBLISHED, "edge_side": "a",
           "edge_bet_fighter_id": BET, "edge_odds_at_publish": 150,
           "edge_model_edge_id": 7, "edge_published_at": LOCK}
    row.update(over)
    return row


def legacy_snapshot(**over):
    """A snapshot taken before the edge-identity columns existed.

    No edge id, no edge publication instant — and `engine_published_at` sitting
    there looking like one. Every historical row has this shape.
    """
    row = snapshot(**over)
    row.pop("edge_model_edge_id", None)
    row.pop("edge_published_at", None)
    row.update(over)
    return row


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
           "published_at": LOCK, "clv_publish_quote_id": PUBLISH_QUOTE_ID}
    row.update(over)
    return row


def score(quotes=None, fight=None, ref=START, books=BOOKS, now=NOW,
          basis="previous_bout_completion", first_bout=False,
          snap=True, pub=True, cohort=True, **over):
    """`snap`/`pub`/`cohort` accept True (the good default), None (absent, and
    therefore refused) or an explicit value."""
    this_edge = edge(**over)
    return score_row(edge=this_edge,
                     quotes=three_books() if quotes is None else quotes,
                     fight=FIGHT if fight is None else fight,
                     reference_instant=ref, now=now, eligible_book_ids=books,
                     reference_basis=basis, is_first_bout=first_bout,
                     snapshot=snapshot() if snap is True else snap,
                     publish_quote=publish_quote() if pub is True else pub,
                     edge_cohort=[this_edge] if cohort is True else cohort)


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

    def test_no_cutoff_means_no_row_can_score(self):
        """Bout 1 with no card start on file, and a later bout with no previous
        completion on file, are both unscored — with the reason naming which
        input is missing."""
        self.assertEqual(
            score(ref=None, basis=None, first_bout=True)["reason"],
            "no_scheduled_start")
        self.assertEqual(
            score(ref=None, basis=None, first_bout=False)["reason"],
            "no_previous_bout_completion")

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
            "no_scheduled_start":
                lambda: score(ref=None, basis=None, first_bout=True),
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
                lambda: score(snap=snapshot(
                    edge_published_at=START + dt.timedelta(hours=1),
                    snapshot_at=START + dt.timedelta(hours=1))),
            "no_immutable_forecast_lock": lambda: score(snap=None),
            "ambiguous_edge_identity":
                lambda: score(snap=legacy_snapshot(), cohort=None),
            "no_publish_quote_link": lambda: score(pub=None),
            "incomplete_quote_provenance": lambda: score(quotes=[
                dict(q, feed_version=None) for q in three_books()]),
            "market_identity_changed": lambda: score(quotes=[
                dict(q, source_event_id="a-different-market")
                for q in three_books()]),
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

    def test_a_real_bell_does_NOT_override_the_frozen_cutoff(self):
        """Amendment 5.1. A bell override would silently make one version behave
        as two — fights with a bell scored one way, fights without scored another,
        inside the same summary statistic. A rule that depends on which optional
        field happens to be populated is not frozen."""
        self.assertNotIn("bell_at", CLOSE_REFERENCE_BASES)
        self.assertIn("bell_at", AUDIT_ONLY_BASES)
        self.assertIsNone(admissible_reference(START, "bell_at"))
        self.assertIsNone(admissible_reference(START, "bell_at", is_first_bout=True))
        self.assertIsNone(admissible_reference(START, "bell_at", is_first_bout=False))

    def test_a_direct_call_cannot_score_against_a_bell_either(self):
        """admissible_reference is the gate, but score_row takes the instant and
        the basis as SEPARATE arguments — so a caller that resolved the reference
        itself, or a future one that forgets the gate, would hand in a real
        instant labelled 'bell_at' and get a perfectly valid-looking score back.
        The refusal has to live inside score_row, not only in front of it."""
        got = score(ref=START, basis="bell_at", first_bout=False)
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "no_scheduled_start")
        self.assertIn("bell", got["detail"])
        self.assertIsNone(got["clv_return"])
        self.assertEqual(score(ref=START, basis="bell_at", first_bout=True)["scored"],
                         False, "a bell is not a cutoff on bout 1 either")

    def test_an_unknown_basis_is_refused_rather_than_trusted(self):
        """The permitted set is a closed vocabulary. Anything outside it — a
        typo, a basis from a future version, a string from a caller that grew a
        new tier — is refused, never scored on the strength of the instant
        looking reasonable."""
        for basis in ("card_scheduled_start", "provider_commence",
                      "event_date_fallback", "closing_line", ""):
            with self.subTest(basis=basis):
                got = score(ref=START, basis=basis, first_bout=False)
                self.assertFalse(got["scored"],
                                 f"{basis!r} scored, and it is not a cutoff")
                self.assertEqual(got["reason"], "no_scheduled_start")

    def test_the_refusal_names_the_two_bases_this_version_allows(self):
        detail = score(ref=START, basis="bell_at")["detail"]
        self.assertIn("previous_bout_completion", detail)
        self.assertIn("scheduled_first_bout", detail)
        self.assertIn(PROTOCOL_TAG, detail,
                      "the message has to say WHICH version is refusing, because "
                      "a later version may well admit a bell")

    def test_the_card_schedule_cannot_be_smuggled_onto_a_later_bout(self):
        """scheduled_first_bout is bout 1's cutoff and nothing else's. On bout 7
        it is hours early, which is the whole reason Amendment 4.1 withdrew it."""
        got = score(ref=START, basis="scheduled_first_bout", first_bout=False)
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "no_scheduled_start")
        self.assertTrue(score(ref=START, basis="scheduled_first_bout",
                              first_bout=True)["scored"])

    def test_scoring_against_real_bells_would_be_a_new_version(self):
        """Stated as a test so the boundary is checkable: the audit field exists,
        and admitting it is a version bump rather than a code change here."""
        self.assertTrue(AUDIT_ONLY_BASES.isdisjoint(CLOSE_REFERENCE_BASES))
        self.assertIn("bell_at", SUPERSEDED_START_BASES)

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
        self.assertIs(reference_is_lower_bound("scheduled_first_bout"), False)
        self.assertIsNone(reference_is_lower_bound("bell_at"),
                          "bell_at is not a cutoff in this version, so it has no "
                          "lead-time character here — null, not False")

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
        got = score(ref=admissible_reference(START, "event_date_fallback", True),
                    basis=None, first_bout=True)
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "no_scheduled_start")

    def test_the_admissible_set_is_the_frozen_two(self):
        self.assertEqual(CLOSE_REFERENCE_BASES,
                         {"scheduled_first_bout", "previous_bout_completion"},
                         "exactly two cases, always — no third, and nothing "
                         "overrides them inside this version")

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
        self.assertEqual(score(ref=None, basis=None, first_bout=True)["reason"],
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
                got = score(basis=basis,
                            first_bout=(basis == "scheduled_first_bout"))
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


# ---------------------------------------------------------------------------
# Amendment 6 (a) — eligibility is a property of the ROW, not of the schema
# ---------------------------------------------------------------------------

class TestRowLevelProvenance(unittest.TestCase):
    """The columns existing on `fight_odds` says nothing about a given row.

    The trap this closes is specific and dated: the capture migration lands, and
    the very next run scores May and June quotes. Their `captured_at` is
    credible — live capture began 2026-05-22, so R-13 passes them — they are
    inside the staleness window of some cutoff, and they carry NULL in every
    provenance column, correctly, because those columns did not exist when the
    rows were written. A schema-level check sees "the table has the columns" and
    lets them through.
    """

    # After the migration is installed and a cutoff exists: a perfectly ordinary
    # early-June capture, credible instant and all.
    JUNE_CUTOFF = dt.datetime(2026, 6, 14, 22, 0, tzinfo=dt.timezone.utc)
    JUNE_QUOTE = JUNE_CUTOFF - dt.timedelta(minutes=10)
    JUNE_LOCK = JUNE_CUTOFF - dt.timedelta(days=4)

    def june_books(self, **strip):
        """Three two-sided books from June, with the new columns NULL."""
        out = []
        for q in three_books(at=self.JUNE_QUOTE):
            row = dict(q)
            for field in (strip or {f: None for f in REQUIRED_QUOTE_PROVENANCE}):
                row[field] = None
            out.append(row)
        return out

    def score_june(self, quotes):
        this_edge = edge(published_at=self.JUNE_LOCK)
        return score_row(
            edge=this_edge, edge_cohort=[this_edge],
            quotes=quotes, fight=FIGHT, reference_instant=self.JUNE_CUTOFF,
            now=NOW, eligible_book_ids=BOOKS,
            reference_basis="previous_bout_completion", is_first_bout=False,
            snapshot=snapshot(edge_published_at=self.JUNE_LOCK,
                              snapshot_at=self.JUNE_LOCK),
            publish_quote=publish_quote(captured_at=self.JUNE_LOCK,
                                        provider_last_update=self.JUNE_LOCK,
                                        retrieved_at=self.JUNE_LOCK))

    def test_a_credible_june_quote_with_null_provenance_cannot_score(self):
        """THE regression. Everything else about these rows is fine."""
        quotes = self.june_books()
        for q in quotes:                       # the premise, asserted not assumed
            self.assertTrue(credible_capture_instant(q["captured_at"], NOW),
                            "the test is only meaningful if R-13 passes them")
        got = self.score_june(quotes)
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "incomplete_quote_provenance")
        self.assertIsNone(got["clv_return"])

    def test_the_same_quotes_score_once_they_carry_the_provenance(self):
        """The control. Without it the test above would pass for the wrong
        reason — a fixture that cannot score under any conditions."""
        got = self.score_june(three_books(at=self.JUNE_QUOTE))
        self.assertTrue(got["scored"], got["detail"])

    def test_every_required_field_is_load_bearing_on_its_own(self):
        for field in REQUIRED_QUOTE_PROVENANCE:
            with self.subTest(field=field):
                got = self.score_june(self.june_books(**{field: None}))
                self.assertEqual(got["reason"], "incomplete_quote_provenance",
                                 f"dropping {field} alone left the row scorable")

    def test_empty_is_not_present(self):
        """An empty string and an empty jsonb survive a NULL check and record
        nothing, which is the same defect as R-13's populated epoch stamp."""
        self.assertFalse(missing_quote_provenance(quote(1, BET, 1, 0.5)))
        for field, empty in (("feed_version", ""), ("feed_version", "   "),
                             ("source_event_id", ""), ("raw", {}),
                             ("market_status", "")):
            with self.subTest(field=field, value=empty):
                q = quote(1, BET, 1, 0.5)
                q[field] = empty
                self.assertIn(field, missing_quote_provenance(q))

    def test_one_missing_corner_reports_the_cause_not_the_symptom(self):
        """Stripping provenance from one side leaves the book one-sided. The
        reported reason must be the provenance, not `one_sided_close` — one is
        permanent and one might be fixed by the next capture."""
        quotes = []
        for q in three_books(at=self.JUNE_QUOTE):
            row = dict(q)
            if row["fighter_id"] == OPP:
                row["raw"] = None
            quotes.append(row)
        got = self.score_june(quotes)
        self.assertEqual(got["reason"], "incomplete_quote_provenance")

    def test_the_diagnostic_counts_the_dropped_rows(self):
        got = self.score_june(self.june_books())
        self.assertEqual(got["diagnostics"]["missing_provenance"], 6)
        self.assertEqual(got["diagnostics"]["seen"], 6)

    def test_the_settler_reads_every_field_it_checks(self):
        """The same mistake one layer down: checking a field the query never
        selected would make every row read as provenance-less."""
        sys.path.insert(0, os.path.dirname(REPO_ROOT and
                                           os.path.join(REPO_ROOT, "cfl_engine")))
        engine_dir = os.path.join(REPO_ROOT, "cfl_engine")
        if engine_dir not in sys.path:
            sys.path.insert(0, engine_dir)
        import settle_clv                                            # noqa: E402
        for field in REQUIRED_QUOTE_PROVENANCE:
            self.assertIn(field, settle_clv.QUOTE_SELECT_COLUMNS,
                          f"{field} is required but never fetched")


# ---------------------------------------------------------------------------
# Amendment 6 (b) — R-07 per quote, literally
# ---------------------------------------------------------------------------

class TestNoLookaheadPerQuote(unittest.TestCase):
    """`forecast_locked_at < close_quoted_at`, strictly, for EVERY quote."""

    # Reed's exact case, on the clock he gave: the previous bout ended at 9:30,
    # the forecast was locked at 9:28, and the book last moved at 9:20.
    CUTOFF = dt.datetime(2026, 9, 12, 21, 30, tzinfo=dt.timezone.utc)
    LOCKED = dt.datetime(2026, 9, 12, 21, 28, tzinfo=dt.timezone.utc)
    QUOTED = dt.datetime(2026, 9, 12, 21, 20, tzinfo=dt.timezone.utc)

    def score_at(self, quoted_at, locked_at=None):
        locked_at = self.LOCKED if locked_at is None else locked_at
        this_edge = edge(published_at=locked_at)
        return score_row(
            edge=this_edge, edge_cohort=[this_edge],
            quotes=three_books(at=quoted_at), fight=FIGHT,
            reference_instant=self.CUTOFF, now=NOW, eligible_book_ids=BOOKS,
            reference_basis="previous_bout_completion", is_first_bout=False,
            snapshot=snapshot(edge_published_at=locked_at,
                              snapshot_at=locked_at),
            publish_quote=publish_quote(
                captured_at=locked_at - dt.timedelta(minutes=1),
                provider_last_update=locked_at - dt.timedelta(minutes=1),
                retrieved_at=locked_at - dt.timedelta(minutes=1)))

    def test_a_forecast_locked_at_928_cannot_score_a_920_quote(self):
        """The regression Reed named. The cutoff is 9:30, so the quote is
        comfortably pre-cutoff — and it was on the screen before the forecast
        existed, which is what R-07 forbids."""
        got = self.score_at(self.QUOTED)
        self.assertLess(self.QUOTED, self.CUTOFF,
                        "the quote must be pre-cutoff or the test proves nothing")
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "forecast_not_before_close")
        self.assertIn("9", got["detail"])
        self.assertEqual(got["diagnostics"]["before_forecast_lock"], 6)

    def test_a_quote_after_the_lock_and_before_the_cutoff_scores(self):
        got = self.score_at(self.LOCKED + dt.timedelta(minutes=1))
        self.assertTrue(got["scored"], got["detail"])

    def test_a_quote_exactly_at_the_lock_does_not_score(self):
        """Strictly, as written. Simultaneous is not after."""
        got = self.score_at(self.LOCKED)
        self.assertEqual(got["reason"], "forecast_not_before_close")

    def test_the_old_edge_level_check_alone_would_have_passed_this(self):
        """Pins WHY the per-quote rule is needed: the check it replaced —
        published_at < cutoff — is satisfied by exactly this arrangement."""
        self.assertLess(self.LOCKED, self.CUTOFF)
        self.assertLess(self.QUOTED, self.CUTOFF)
        self.assertLess(self.QUOTED, self.LOCKED)
        self.assertEqual(self.score_at(self.QUOTED)["reason"],
                         "forecast_not_before_close")

    def test_closing_pairs_requires_the_lock_and_does_not_default_it(self):
        """A default of None would be a silent bypass of R-07."""
        import inspect
        sig = inspect.signature(closing_pairs)
        self.assertIs(sig.parameters["forecast_locked_at"].default,
                      inspect.Parameter.empty,
                      "forecast_locked_at must have no default")
        pairs, diag = closing_pairs(three_books(), BET, OPP, START, NOW, BOOKS,
                                    forecast_locked_at=None)
        self.assertEqual(pairs, [], "no lock must mean no eligible close")
        self.assertEqual(diag["before_forecast_lock"], 6)


# ---------------------------------------------------------------------------
# Amendment 6 (c) — the lock comes from an immutable record
# ---------------------------------------------------------------------------

class TestImmutableForecastLock(unittest.TestCase):
    def test_no_snapshot_means_no_score(self):
        got = score(snap=None)
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "no_immutable_forecast_lock")
        self.assertIn("mutable", got["detail"])

    def test_the_snapshot_must_identify_THIS_edge_not_just_the_fight(self):
        """pre_fight_snapshots is unique on fight_id, so a row always exists for
        a snapshotted fight. Matching on the fight alone would accept a record of
        a different forecast as this one's lock."""
        for field, wrong in (("edge_side", "b"),
                             ("edge_bet_fighter_id", 999),
                             ("edge_odds_at_publish", -140)):
            with self.subTest(field=field):
                # A LEGACY snapshot: with an edge id present the tuple is not
                # consulted at all, which is the whole point of wiring the id.
                got = score(snap=legacy_snapshot(**{field: wrong}))
                self.assertEqual(got["reason"], "no_immutable_forecast_lock")
                self.assertIn(field.replace("edge_", ""), got["detail"])

    def test_a_snapshot_missing_the_edge_fields_cannot_match(self):
        got = score(snap=legacy_snapshot(edge_odds_at_publish=None))
        self.assertEqual(got["reason"], "no_immutable_forecast_lock")

    def test_snapshot_at_is_the_only_fallback_and_is_labelled_as_one(self):
        """A historical snapshot carries no edge publication instant. It falls
        back to `snapshot_at` — later than publication, therefore conservative —
        and NEVER to `engine_published_at`, which belongs to the model pick."""
        got = score(snap=legacy_snapshot())
        self.assertTrue(got["scored"], got["detail"])
        lock = got["forecast_lock"]
        self.assertEqual(lock["immutable_source"],
                         "pre_fight_snapshots.snapshot_at")
        self.assertTrue(lock["immutable_is_conservative_fallback"],
                        "a fallback must say it is one; a reader comparing two "
                        "scored rows needs to know which rests on weaker "
                        "evidence, and this one is systematically late")
        self.assertEqual(lock["immutable_locked_at"], LOCK + dt.timedelta(hours=1))
        self.assertNotEqual(lock["immutable_locked_at"], PICK_PUBLISHED)

    def test_the_modern_snapshot_locks_on_the_edges_own_instant(self):
        got = score()
        self.assertTrue(got["scored"], got["detail"])
        lock = got["forecast_lock"]
        self.assertEqual(lock["immutable_source"],
                         "pre_fight_snapshots.edge_published_at")
        self.assertEqual(lock["immutable_locked_at"], LOCK)
        self.assertFalse(lock["immutable_is_conservative_fallback"])

    def test_an_edge_instant_without_an_edge_id_is_not_used(self):
        """A publication instant with no edge id beside it cannot be attached to
        a particular publication, and would be indistinguishable from the pick
        timestamp it exists to displace. The database enforces the same pairing."""
        snap = snapshot()
        del snap["edge_model_edge_id"]
        got = score(snap=snap, cohort=[edge()])
        self.assertTrue(got["scored"], got["detail"])
        self.assertEqual(got["forecast_lock"]["immutable_source"],
                         "pre_fight_snapshots.snapshot_at")

    def test_a_snapshot_with_neither_instant_cannot_lock(self):
        got = score(snap=legacy_snapshot(snapshot_at=None))
        self.assertEqual(got["reason"], "no_immutable_forecast_lock")
        self.assertIn("engine_published_at is the model pick", got["detail"])

    def test_the_effective_lock_is_the_later_of_the_two(self):
        """A mutated published_at can only ever COST observations. It cannot
        admit a quote the immutable record would have excluded — which is the
        whole reason the two are combined rather than one being trusted."""
        later = FRESH + dt.timedelta(minutes=1)     # after every closing quote
        got = score(published_at=later)
        self.assertEqual(got["reason"], "forecast_not_before_close",
                         "a later published_at must bind")

        earlier = LOCK - dt.timedelta(days=30)
        # The linked publish quote moves with the stated publication instant: a
        # quote captured a month AFTER publication is not its source, and that
        # is a different refusal (Amendment 7 (c)) from the one under test.
        got = score(published_at=earlier,
                    pub=publish_quote(captured_at=earlier,
                                      provider_last_update=earlier,
                                      retrieved_at=earlier))
        self.assertTrue(got["scored"], got["detail"])
        self.assertEqual(got["forecast_lock"]["locked_at"], LOCK,
                         "an earlier published_at must NOT loosen the immutable "
                         "lock — that is the direction an attacker would want")

    def test_the_row_records_which_record_locked_it(self):
        info = score()["forecast_lock"]
        self.assertEqual(info["snapshot_id"], 55)
        self.assertEqual(info["immutable_source"],
                         "pre_fight_snapshots.edge_published_at")
        self.assertTrue(info["agrees_with_immutable_record"])
        self.assertFalse(info["published_at_is_binding"])
        self.assertEqual(info["engine_published_at"], PICK_PUBLISHED,
                         "the pick's instant is carried for audit and is not "
                         "the lock")

    def test_a_disagreement_is_recorded_rather_than_hidden(self):
        info = score(published_at=LOCK + dt.timedelta(minutes=2))["forecast_lock"]
        self.assertFalse(info["agrees_with_immutable_record"])
        self.assertTrue(info["published_at_is_binding"])


# ---------------------------------------------------------------------------
# Amendment 7 (c) — the snapshot must identify ONE publication
# ---------------------------------------------------------------------------

class TestEdgeIdentity(unittest.TestCase):
    """The tuple is a cross-check. Only an id is an identity.

    `pre_fight_snapshots` is unique on `fight_id` and `snapshot_predictions.py`
    keeps only the latest live edge per fight — so several live edges on one
    fight are possible, the snapshot records one of them, and a tuple two of
    them can share cannot say which.
    """

    def other_edge(self, **over):
        """A second live edge on the same fight."""
        return edge(id=8, **over)

    def test_a_shared_edge_id_is_an_exact_match(self):
        got = score(snap=snapshot(edge_model_edge_id=7))
        self.assertTrue(got["scored"], got["detail"])
        self.assertEqual(got["forecast_lock"]["edge_identity"], "shared_edge_id")

    def test_a_shared_edge_id_naming_another_edge_is_refused(self):
        got = score(snap=snapshot(edge_model_edge_id=8))
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "no_immutable_forecast_lock")
        self.assertIn("different publication", got["detail"])

    def test_the_edge_id_wins_over_a_tuple_that_would_be_ambiguous(self):
        """The whole point of wiring it: ambiguity stops mattering."""
        twins = [edge(), self.other_edge()]          # identical tuples
        got = score(snap=snapshot(edge_model_edge_id=7), cohort=twins)
        self.assertTrue(got["scored"], got["detail"])
        self.assertEqual(got["forecast_lock"]["edge_identity"], "shared_edge_id")

    def test_two_live_edges_sharing_the_tuple_score_nothing(self):
        """Same side, same fighter, same price — which one did the snapshot
        freeze? Nothing on the snapshot can say, so neither scores."""
        twins = [edge(), self.other_edge()]
        got = score(snap=legacy_snapshot(), cohort=twins)
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "ambiguous_edge_identity")
        self.assertIn("2 live edges", got["detail"])

    def test_a_second_edge_with_a_different_price_is_not_a_twin(self):
        """Ambiguity is about the tuple, not about the count. A fight with two
        live edges at different prices is still unambiguous."""
        got = score(snap=legacy_snapshot(),
                    cohort=[edge(), self.other_edge(odds_at_publish=-140)])
        self.assertTrue(got["scored"], got["detail"])
        self.assertEqual(got["forecast_lock"]["edge_identity"],
                         "tuple_unique_in_cohort")

    def test_a_second_edge_on_the_other_side_is_not_a_twin(self):
        got = score(snap=legacy_snapshot(),
                    cohort=[edge(), self.other_edge(side="b")])
        self.assertTrue(got["scored"], got["detail"])

    def test_an_unestablished_cohort_is_refused_not_assumed_unique(self):
        """Not established is not the same as established. `None` means the
        caller never looked, and that is exactly when a silent default would
        assume the convenient answer."""
        got = score(snap=legacy_snapshot(), cohort=None)
        self.assertEqual(got["reason"], "ambiguous_edge_identity")
        self.assertIn("not supplied", got["detail"])

    def test_the_row_records_how_the_edge_was_identified(self):
        """A reader must be able to tell an identity from a unique-looking
        tuple, because they are not the same evidence."""
        self.assertEqual(
            score(snap=legacy_snapshot())["forecast_lock"]["edge_identity"],
            "tuple_unique_in_cohort")
        self.assertEqual(score()["forecast_lock"]["edge_identity"],
                         "shared_edge_id")

    def test_the_snapshotter_selects_and_writes_the_edge_id(self):
        """The fix is only real if the producer records it. Pinned here because
        the column is useless if nothing fills it — and the field name must
        match what `forecast_lock` reads."""
        src = (REPO_ROOT and open(os.path.join(REPO_ROOT, "cfl_engine",
                                               "snapshot_predictions.py"),
                                  encoding="utf-8").read())
        self.assertIn('"select=id,fight_id,side,bet_fighter_id', src,
                      "the snapshotter must select the edge id to record it")
        self.assertIn(f'"{SNAPSHOT_EDGE_ID_FIELD}": ed and ed["id"]', src)
        self.assertIn("OPTIONAL_COLUMNS", src,
                      "writing a column the table may not have must degrade, "
                      "not take the snapshot cron down")


# ---------------------------------------------------------------------------
# Amendment 7 (e) — the edge's lock is the EDGE's publication, not the pick's
# ---------------------------------------------------------------------------

class TestEdgePublicationInstant(unittest.TestCase):
    """`engine_published_at` is `model_picks.published_at`.

    A model pick and a value edge are different records published at different
    times: the engine posts a pick, and the edge derived from it appears later,
    once the price has moved far enough to flag one. R-07 locks the forecast
    being scored, and CLV-001 scores the EDGE — so reading the pick's instant as
    the edge's places the lock early and admits quotes from before the edge
    existed. A lookahead violation wearing an immutable record's clothes, which
    is the worst kind, because everything about it looks audited.

    ChatGPT's scenario, on the calendar it specified.
    """

    # Monday the pick, Tuesday the edge, Wednesday the snapshot.
    MONDAY = dt.datetime(2026, 9, 7, 12, 0, tzinfo=dt.timezone.utc)
    MONDAY_EVENING = dt.datetime(2026, 9, 7, 20, 0, tzinfo=dt.timezone.utc)
    TUESDAY = dt.datetime(2026, 9, 8, 12, 0, tzinfo=dt.timezone.utc)
    WEDNESDAY = dt.datetime(2026, 9, 9, 12, 0, tzinfo=dt.timezone.utc)
    # …and `model_edges.published_at`, later edited backwards to Sunday.
    SUNDAY = dt.datetime(2026, 9, 6, 12, 0, tzinfo=dt.timezone.utc)

    def modern(self, **over):
        row = snapshot(engine_published_at=self.MONDAY,
                       edge_published_at=self.TUESDAY,
                       snapshot_at=self.WEDNESDAY)
        row.update(over)
        return row

    def legacy(self, **over):
        row = legacy_snapshot(engine_published_at=self.MONDAY,
                              snapshot_at=self.WEDNESDAY)
        row.update(over)
        return row

    def score_with(self, snap, quotes_at, published_at=None, cohort=True):
        published_at = self.SUNDAY if published_at is None else published_at
        this_edge = edge(published_at=published_at)
        return score_row(
            edge=this_edge,
            edge_cohort=[this_edge] if cohort is True else cohort,
            quotes=three_books(at=quotes_at), fight=FIGHT,
            reference_instant=START, now=NOW, eligible_book_ids=BOOKS,
            reference_basis="previous_bout_completion", is_first_bout=False,
            snapshot=snap,
            # Captured at or before the EARLIEST publication instant on record —
            # here the backdated Sunday, which tightens the bound. The publish
            # side is not what these tests are about; the closing side is.
            publish_quote=publish_quote(captured_at=published_at,
                                        provider_last_update=published_at,
                                        retrieved_at=published_at))

    def test_a_monday_quote_is_not_eligible_after_published_at_is_backdated(self):
        """THE regression. The pick went out Monday, the edge Tuesday, the
        snapshot Wednesday — and `model_edges.published_at` has since been edited
        back to Sunday. A Monday-evening quote must still be refused: it existed
        before the edge did, whatever the mutable column now says."""
        got = self.score_with(self.modern(), self.MONDAY_EVENING)
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "forecast_not_before_close")
        self.assertEqual(got["diagnostics"]["before_forecast_lock"], 6)

    def test_the_immutable_lock_stays_tuesday_for_a_modern_snapshot(self):
        got = self.score_with(self.modern(), FRESH)
        self.assertTrue(got["scored"], got["detail"])
        lock = got["forecast_lock"]
        self.assertEqual(lock["immutable_locked_at"], self.TUESDAY)
        self.assertEqual(lock["locked_at"], self.TUESDAY,
                         "a published_at edited backwards must not move the "
                         "lock earlier — the later of the two binds")
        self.assertFalse(lock["immutable_is_conservative_fallback"])

    def test_the_legacy_fallback_is_wednesday_not_monday(self):
        """With no `edge_published_at` on file the lock is `snapshot_at` —
        Wednesday, which is late and therefore safe. NEVER Monday: that is the
        pick's instant, and using it would be exactly the defect."""
        got = self.score_with(self.legacy(), FRESH)
        self.assertTrue(got["scored"], got["detail"])
        lock = got["forecast_lock"]
        self.assertEqual(lock["immutable_locked_at"], self.WEDNESDAY)
        self.assertNotEqual(lock["immutable_locked_at"], self.MONDAY)
        self.assertTrue(lock["immutable_is_conservative_fallback"])

    def test_the_monday_quote_is_refused_under_the_legacy_fallback_too(self):
        got = self.score_with(self.legacy(), self.MONDAY_EVENING)
        self.assertEqual(got["reason"], "forecast_not_before_close")

    def test_engine_published_at_can_never_satisfy_the_edge_lock(self):
        """Stated as its own property: there is no combination of inputs under
        which the pick's instant becomes the edge's lock."""
        self.assertIn("engine_published_at", NOT_AN_EDGE_LOCK_FIELDS)
        for snap in (self.modern(), self.legacy(),
                     self.legacy(snapshot_at=None)):
            with self.subTest(snapshot=snap.get("edge_published_at")):
                try:
                    locked_at, info = forecast_lock(
                        edge(published_at=self.SUNDAY), snap, [edge()])
                except Unscored:
                    continue                     # refused outright is also fine
                self.assertNotEqual(info["immutable_locked_at"], self.MONDAY)
                self.assertNotIn("engine_published_at",
                                 info["immutable_source"])

    def test_the_pick_instant_is_still_carried_for_audit(self):
        info = self.score_with(self.modern(), FRESH)["forecast_lock"]
        self.assertEqual(info["engine_published_at"], self.MONDAY,
                         "it is provenance for the main model prediction — "
                         "retained, never promoted")

    def test_the_publish_quote_is_bounded_by_the_edge_instant(self):
        """A quote captured Wednesday carries the right price and a credible
        instant, and still postdates the Tuesday publication."""
        got = self.score_with(self.modern(), FRESH)
        self.assertTrue(got["scored"], got["detail"])   # Monday quote: fine

        wednesday_quote = publish_quote(captured_at=self.WEDNESDAY,
                                        provider_last_update=self.WEDNESDAY,
                                        retrieved_at=self.WEDNESDAY)
        this_edge = edge(published_at=self.SUNDAY)
        late = score_row(
            edge=this_edge, edge_cohort=[this_edge], quotes=three_books(),
            fight=FIGHT, reference_instant=START, now=NOW,
            eligible_book_ids=BOOKS,
            reference_basis="previous_bout_completion", is_first_bout=False,
            snapshot=self.modern(), publish_quote=wednesday_quote)
        self.assertFalse(late["scored"])
        self.assertEqual(late["reason"], "no_publish_quote_link")
        self.assertIn("AFTER the edge was published", late["detail"])

    def test_a_backdated_published_at_cannot_widen_the_publish_quote_bound(self):
        """Sunday is earlier than Tuesday, so it TIGHTENS the bound — a Monday
        quote is refused on the publish side as well as the closing side. A
        mutable column may narrow this window; it may never widen it."""
        this_edge = edge(published_at=self.SUNDAY)
        got = score_row(
            edge=this_edge, edge_cohort=[this_edge], quotes=three_books(),
            fight=FIGHT, reference_instant=START, now=NOW,
            eligible_book_ids=BOOKS,
            reference_basis="previous_bout_completion", is_first_bout=False,
            snapshot=self.modern(),
            publish_quote=publish_quote(
                captured_at=self.MONDAY_EVENING,
                provider_last_update=self.MONDAY_EVENING,
                retrieved_at=self.MONDAY_EVENING))
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "no_publish_quote_link")

    def test_the_producer_writes_the_edge_publication_instant(self):
        """The column is useless if nothing fills it, and it must come from the
        EDGE row rather than the pick."""
        src = open(os.path.join(REPO_ROOT, "cfl_engine",
                                "snapshot_predictions.py"), encoding="utf-8").read()
        self.assertIn(f'"{SNAPSHOT_EDGE_PUBLISHED_FIELD}": ed and ed["published_at"]',
                      src, "the edge instant must come from the edge row `ed`")
        self.assertIn('"engine_published_at": pk and pk["published_at"]', src,
                      "and the pick instant must keep coming from the pick row")
        self.assertIn(SNAPSHOT_EDGE_PUBLISHED_FIELD,
                      src[src.index("OPTIONAL_COLUMNS"):
                          src.index("OPTIONAL_COLUMNS") + 200],
                      "it must degrade when the column is absent, like the id")

    def test_the_producer_drops_both_halves_when_either_is_missing(self):
        """The pair is required in both directions and the database enforces it,
        so a producer that writes an id with no instant would fail the whole
        INSERT batch. `model_edges.published_at` can be NULL, so that is
        reachable. Degrading that fight to the legacy path costs precision and
        is the right trade against losing the snapshot."""
        engine_dir = os.path.join(REPO_ROOT, "cfl_engine")
        if engine_dir not in sys.path:
            sys.path.insert(0, engine_dir)
        import snapshot_predictions as snap                           # noqa: E402

        rows = [{"fight_id": 1, "edge_model_edge_id": 7,
                 "edge_published_at": None},          # edge with no publish time
                {"fight_id": 2, "edge_model_edge_id": None,
                 "edge_published_at": None},          # no edge at all
                {"fight_id": 3, "edge_model_edge_id": 9,
                 "edge_published_at": LOCK}]          # complete
        snap._pair_edge_identity(rows, log=lambda *_: None)
        self.assertNotIn("edge_model_edge_id", rows[0])
        self.assertNotIn("edge_published_at", rows[0])
        self.assertEqual(rows[2]["edge_model_edge_id"], 9)
        self.assertEqual(rows[2]["edge_published_at"], LOCK)

    def test_the_migration_adds_the_column_and_pairs_it_with_the_id(self):
        sql = open(os.path.join(REPO_ROOT, "research", "clv",
                                "proposed_2026-09-16_snapshot_edge_identity.sql"),
                   encoding="utf-8").read()
        self.assertIn(f"add column if not exists {SNAPSHOT_EDGE_PUBLISHED_FIELD} "
                      f"timestamptz", sql)
        self.assertIn("pre_fight_snapshots_edge_published_needs_an_id", sql)
        self.assertIn("pre_fight_snapshots_edge_id_needs_published_at", sql,
                      "the pairing is required in BOTH directions; an id with "
                      "no instant is a half-written row")
        self.assertIn("pre_fight_snapshots_edge_published_before_snapshot", sql)


# ---------------------------------------------------------------------------
# Amendment 7 (a) — settlement is write-once, re-runs verify
# ---------------------------------------------------------------------------

class TestWriteOnce(unittest.TestCase):
    """A CLV-001 observation is written once and then only ever checked.

    The defect: every scored row was re-PATCHed on every run, so a second
    settlement reinterpreted an earlier observation against later database
    state — a quote inserted since, a corrected completion, a reschedule — and
    refreshed `clv_scored_at` so nothing on the row showed it had moved. The
    protocol says observations are never retroactively reinterpreted or
    overwritten; the writer did the opposite, on a cron.
    """

    SCORED_AT = dt.datetime(2026, 9, 13, 6, 0, tzinfo=dt.timezone.utc)

    def stored_from(self, result, **over):
        """The row as the writer would have left it at first scoring."""
        row = {
            "clv_scored_at": self.SCORED_AT,
            "clv_protocol_version": PROTOCOL_TAG,
            "clv_return": round(result["clv_return"], 10),
            "closing_fair_probability": round(
                result["closing_fair_probability"], 10),
            "closing_book_count": result["closing_book_count"],
            "clv_source_quote_ids": result["quote_ids"],
            "clv_consensus_sha256": result["consensus_sha256"],
            "clv_closing_consensus": result["consensus"],
            "clv_close_basis": result["close_basis"],
            "clv_lead_time_minutes": round(result["lead_time_minutes"], 4),
            "clv_lead_time_is_lower_bound": result["lead_time_is_lower_bound"],
            "clv_proxy_quoted_at": result["proxy_quoted_at"],
            "clv_cutoff_at": result["cutoff_at"],
            "clv_publish_quote_id": result["publish_quote"]["quote_id"],
        }
        row.update(over)
        return row

    def test_an_identical_rerun_reports_no_disagreement(self):
        first = score()
        self.assertTrue(first["scored"], first["detail"])
        second = score()
        self.assertEqual(verify_against_stored(second, self.stored_from(first)),
                         [])

    def test_an_unscored_row_is_not_treated_as_written(self):
        """R-04: a row with no usable close stays eligible for a later run."""
        self.assertFalse(has_clv001_score({}))
        self.assertFalse(has_clv001_score({"clv_scored_at": None}))
        self.assertTrue(has_clv001_score({"clv_scored_at": self.SCORED_AT}))

    def test_scored_at_is_never_compared_and_so_never_refreshed(self):
        """It records when the row was FIRST scored. Comparing it to a later run
        would fail every time, which is how a verifier turns back into a writer."""
        self.assertNotIn("clv_scored_at", [c for c, _ in VERIFIED_FIELDS])

    def test_every_persisted_field_is_verified(self):
        """A field stored at first scoring and never checked again is a field
        that can drift silently."""
        engine_dir = os.path.join(REPO_ROOT, "cfl_engine")
        if engine_dir not in sys.path:
            sys.path.insert(0, engine_dir)
        import settle_clv                                            # noqa: E402
        verified = {c for c, _ in VERIFIED_FIELDS}
        never_checked = set(settle_clv.CLV001_COLUMNS) - verified - {
            # Written once and legitimately not re-derived here:
            "clv_scored_at",              # when, not what
            "clv_unscored_reason",        # NULL on every scored row
            "clv_closing_consensus",      # checked against its own hash instead
            "clv_window_opened_at",       # comes from the fight, not the scoring
        }
        self.assertEqual(never_checked, set(),
                         f"persisted but never verified: {never_checked}")

    def test_a_changed_consensus_is_drift(self):
        first = score()
        moved = score(quotes=three_books(
            pairs=((0.58, 0.50), (0.61, 0.49), (0.54, 0.50))))
        problems = verify_against_stored(moved, self.stored_from(first))
        self.assertTrue(problems)
        self.assertTrue(any("closing_fair_probability" in p for p in problems))
        self.assertTrue(any("clv_consensus_sha256" in p for p in problems))

    def test_a_changed_cutoff_is_drift(self):
        """The case the stored cutoff exists for: the schedule moved after the
        row was scored, and the number would silently be re-based on it."""
        first = score()
        later = score(ref=START + dt.timedelta(minutes=20))
        problems = verify_against_stored(later, self.stored_from(first))
        self.assertTrue(any("clv_cutoff_at" in p for p in problems))

    def test_a_row_that_no_longer_scores_is_drift_not_a_deletion(self):
        first = score()
        gone = score(quotes=[])
        problems = verify_against_stored(gone, self.stored_from(first))
        self.assertTrue(problems)
        self.assertIn("no longer scores", problems[0])

    def test_an_edited_stored_artifact_is_caught_by_its_own_hash(self):
        """Editing the jsonb in place would otherwise reproduce every other
        comparison — the recomputed hash matches the recomputed artifact, and
        nothing would look at what is actually on the row."""
        first = score()
        stored = self.stored_from(first)
        tampered = json.loads(json.dumps(stored["clv_closing_consensus"],
                                         default=str))
        tampered["median_fair_bet"] = 0.99
        stored["clv_closing_consensus"] = tampered
        problems = verify_against_stored(first, stored)
        self.assertTrue(any("edited after it was written" in p
                            for p in problems))

    def test_a_row_from_another_protocol_version_is_left_alone(self):
        first = score()
        stored = self.stored_from(first, clv_protocol_version="CLV-001@1.0.7")
        problems = verify_against_stored(first, stored)
        self.assertEqual(len(problems), 1)
        self.assertIn("never re-scored under another", problems[0])

    def test_numeric_round_tripping_is_not_reported_as_drift(self):
        """Postgres `numeric` comes back as a decimal string. Reporting that as
        drift would fire on every run and train everyone to ignore it."""
        first = score()
        stored = self.stored_from(first)
        for column in ("clv_return", "closing_fair_probability",
                       "clv_lead_time_minutes"):
            stored[column] = str(stored[column])
        stored["closing_book_count"] = str(stored["closing_book_count"])
        self.assertEqual(verify_against_stored(first, stored), [])

    def test_the_settler_writes_only_rows_that_were_never_scored(self):
        engine_dir = os.path.join(REPO_ROOT, "cfl_engine")
        if engine_dir not in sys.path:
            sys.path.insert(0, engine_dir)
        import settle_clv                                            # noqa: E402
        first = score()
        rows = [{"id": 7, "fight_id": 1},                       # never scored
                {"id": 8, "fight_id": 2, **self.stored_from(first)},   # scored
                {"id": 9, "fight_id": 3, **self.stored_from(first)}]   # drifted
        drifted_result = dict(score(ref=START + dt.timedelta(minutes=20)),
                              edge_id=9)
        results = [dict(first, edge_id=7), dict(first, edge_id=8),
                   drifted_result]
        fresh, drifted, verified, foreign = settle_clv._partition_for_write(
            results, rows)
        self.assertEqual([x["edge_id"] for x in fresh], [7],
                         "only the never-scored row may be written")
        self.assertEqual(verified, [8])
        self.assertEqual([e for e, _ in drifted], [9])
        self.assertEqual(foreign, [])

    def test_a_second_identical_settlement_would_write_nothing(self):
        """The regression Reed asked for, at the level the writer decides it."""
        engine_dir = os.path.join(REPO_ROOT, "cfl_engine")
        if engine_dir not in sys.path:
            sys.path.insert(0, engine_dir)
        import settle_clv                                            # noqa: E402
        first = score()
        rows = [{"id": 7, "fight_id": 1, **self.stored_from(first)}]
        fresh, drifted, verified, foreign = settle_clv._partition_for_write(
            [dict(first, edge_id=7)], rows)
        self.assertEqual(fresh, [], "a re-run must PATCH nothing")
        self.assertEqual(drifted, [])
        self.assertEqual(verified, [7])

    def test_the_settler_aborts_on_drift_rather_than_rewriting(self):
        """Source-level, because the alternative is discovering it in
        production: the drift branch must exit, and must do so before the
        patch loop rather than after it."""
        src = open(os.path.join(REPO_ROOT, "cfl_engine", "settle_clv.py"),
                   encoding="utf-8").read()
        body = src[src.index("fresh, drifted, verified, foreign ="):]
        abort = body.index("sys.exit(")
        patch = body.index("claim_and_write_clv001(")
        self.assertLess(abort, patch,
                        "the drift abort must come before any PATCH")
        self.assertIn("POST-SCORE DRIFT", body)
        # And the only write loop iterates the never-scored rows.
        self.assertIn("for x in fresh:", body)
        self.assertNotIn("for x in scored:", body)


# ---------------------------------------------------------------------------
# Amendment 6 (d) — the posted price names its source quote
# ---------------------------------------------------------------------------

class TestPublishQuoteLink(unittest.TestCase):
    def test_no_link_means_no_score(self):
        got = score(pub=None)
        self.assertEqual(got["reason"], "no_publish_quote_link")
        self.assertIn("assertion", got["detail"])

    def test_the_link_must_prove_the_price(self):
        got = score(pub=publish_quote(american_odds=-135))
        self.assertEqual(got["reason"], "no_publish_quote_link")
        self.assertIn("does not prove", got["detail"])

    def test_the_link_must_prove_the_corners(self):
        self.assertEqual(score(pub=publish_quote(fighter_id=OPP))["reason"],
                         "no_publish_quote_link")
        self.assertEqual(
            score(pub=publish_quote(opponent_fighter_id=999))["reason"],
            "no_publish_quote_link")

    def test_the_link_must_carry_full_provenance(self):
        for field in REQUIRED_PUBLISH_PROVENANCE:
            with self.subTest(field=field):
                got = score(pub=publish_quote(**{field: None}))
                self.assertEqual(got["reason"], "no_publish_quote_link")
                # opponent_fighter_id is refused one check earlier, as an
                # identity mismatch rather than a missing field — a more
                # specific answer to the same question, so the detail names the
                # corner rather than the column.
                self.assertIn("opponent" if field == "opponent_fighter_id"
                              else field, got["detail"])

    def test_a_quote_captured_after_publication_is_not_the_source(self):
        """Amendment 7 (c). The price matches, the corners match, the market
        matches, the instant is credible — and the quote did not exist when the
        edge was published, so it is a later quote that agrees with the posted
        price rather than the row it came from.

        This is the routine case, not the exotic one: a book that has not moved
        for an hour leaves several rows at the same price, and only one of them
        precedes publication.
        """
        after = LOCK + dt.timedelta(minutes=30)
        self.assertLess(after, FRESH, "the quote must still be pre-cutoff, or "
                                      "the test proves something else")
        got = score(pub=publish_quote(captured_at=after,
                                      provider_last_update=after,
                                      retrieved_at=after))
        self.assertFalse(got["scored"])
        self.assertEqual(got["reason"], "no_publish_quote_link")
        self.assertIn("AFTER the edge was published", got["detail"])
        self.assertIn("a matching price is not a source", got["detail"])

    def test_a_quote_captured_at_the_publication_instant_is_accepted(self):
        """At or before, not strictly before: the quote we published from can
        legitimately carry the same instant the publication is stamped with."""
        got = score(pub=publish_quote(captured_at=LOCK,
                                      provider_last_update=LOCK,
                                      retrieved_at=LOCK))
        self.assertTrue(got["scored"], got["detail"])

    def test_the_publication_instant_is_not_the_effective_lock(self):
        """The effective lock is the LATER of published_at and the immutable
        instant. Anchoring the temporal check to it would let a late
        `published_at` admit a quote captured after the real publication —
        exactly backwards, since taking the later instant is supposed to be the
        conservative direction."""
        late = LOCK + dt.timedelta(hours=2)
        got = score(published_at=late,
                    pub=publish_quote(captured_at=LOCK + dt.timedelta(hours=1),
                                      provider_last_update=LOCK,
                                      retrieved_at=LOCK))
        self.assertFalse(got["scored"],
                         "the immutable instant, not the effective lock, bounds "
                         "the publish quote")
        self.assertEqual(got["reason"], "no_publish_quote_link")

    def test_a_pre_publication_quote_is_also_pre_cutoff(self):
        """The consequence worth stating: the publish side can never be drawn
        from inside the window the closing side is measured over."""
        got = score()
        self.assertTrue(got["scored"], got["detail"])
        self.assertLessEqual(got["publish_quote"]["captured_at"],
                             got["forecast_lock"]["locked_at"])
        self.assertLess(got["publish_quote"]["captured_at"], got["cutoff_at"])

    def test_the_link_must_carry_a_credible_instant(self):
        got = score(pub=publish_quote(captured_at=EPOCH))
        self.assertEqual(got["reason"], "no_publish_quote_link")
        self.assertIn("R-13", got["detail"])

    def test_a_scored_row_records_the_whole_publish_side(self):
        info = score()["publish_quote"]
        self.assertEqual(info["quote_id"], PUBLISH_QUOTE_ID)
        self.assertEqual(info["american_odds"], 150)
        self.assertEqual(info["provider_market_id"], MARKET)
        self.assertEqual(info["opponent_fighter_id"], OPP)
        for field in ("captured_at", "feed_version", "provider_last_update",
                      "retrieved_at"):
            self.assertIsNotNone(info[field])

    def test_closing_quotes_must_name_the_same_provider_market(self):
        """R-06. A repost or a rematch gets a new market id and is a different
        market, not a later quote on the same one."""
        quotes = [dict(q, source_event_id="odds-api-evt-REPOST")
                  for q in three_books()]
        got = score(quotes=quotes)
        self.assertEqual(got["reason"], "market_identity_changed")
        self.assertEqual(got["diagnostics"]["market_id_mismatch"], 6)

    def test_closing_quotes_must_name_the_same_opponent(self):
        quotes = [dict(q, opponent_fighter_id=999) for q in three_books()]
        got = score(quotes=quotes)
        self.assertEqual(got["reason"], "market_identity_changed")
        self.assertEqual(got["diagnostics"]["opponent_mismatch"], 6)

    def test_the_opponent_check_is_per_corner_not_a_constant(self):
        """Each quote names the OTHER fighter, so a check that compared every
        row against one id would reject half of a perfectly good market."""
        got = score()
        self.assertTrue(got["scored"], got["detail"])
        self.assertEqual(got["diagnostics"]["opponent_mismatch"], 0)


# ---------------------------------------------------------------------------
# Amendment 6 (e) — the cutoff is stored, and hashed
# ---------------------------------------------------------------------------

class TestCutoffIsPersisted(unittest.TestCase):
    def test_a_scored_row_carries_the_cutoff_it_was_scored_against(self):
        got = score()
        self.assertTrue(got["scored"], got["detail"])
        self.assertEqual(got["cutoff_at"], START)

    def test_bout_one_carries_it_too_though_nothing_else_on_the_row_holds_it(self):
        """The case that motivated this. For bouts 2..N the cutoff coincides
        with clv_window_opened_at; for bout 1 it is the card's scheduled start
        and no other column held it — and bout 1 is the only bout this version
        can currently score."""
        got = score(basis="scheduled_first_bout", first_bout=True)
        self.assertTrue(got["scored"], got["detail"])
        self.assertEqual(got["cutoff_at"], START)
        self.assertEqual(got["close_basis"], "scheduled_first_bout")

    def test_the_cutoff_is_inside_the_hash_not_merely_beside_it(self):
        """Same books, same quotes, same median — a different cutoff must not
        produce the same hash, or the selection rule is outside the integrity
        check and the artifact cannot be verified as the calculation performed."""
        a = score()
        later = START + dt.timedelta(minutes=20)
        b = score(ref=later)
        self.assertTrue(a["scored"] and b["scored"])
        self.assertEqual(a["closing_fair_probability"],
                         b["closing_fair_probability"],
                         "the test is only meaningful when the number is equal")
        self.assertEqual(a["quote_ids"], b["quote_ids"])
        self.assertNotEqual(a["consensus_sha256"], b["consensus_sha256"])
        self.assertEqual(a["consensus"]["cutoff_at"], START)
        self.assertEqual(b["consensus"]["cutoff_at"], later)

    def test_the_lock_and_the_publish_quote_are_hashed_too(self):
        a = score()
        # Later, not earlier: an earlier immutable instant is overridden by the
        # mutable published_at under the take-the-later rule, so it would leave
        # the effective lock — and therefore the artifact — unchanged.
        later = LOCK + dt.timedelta(days=1)
        b = score(snap=snapshot(edge_published_at=later, snapshot_at=later))
        self.assertEqual(a["closing_fair_probability"],
                         b["closing_fair_probability"])
        self.assertNotEqual(a["consensus_sha256"], b["consensus_sha256"])
        self.assertEqual(a["consensus"]["publish_quote_id"], PUBLISH_QUOTE_ID)

    def test_the_lead_time_agrees_with_the_stored_cutoff(self):
        got = score()
        self.assertAlmostEqual(
            got["lead_time_minutes"],
            (got["cutoff_at"] - got["proxy_quoted_at"]).total_seconds() / 60.0,
            places=9)

    def test_the_migration_stores_the_cutoff_and_requires_it(self):
        with open(MIGRATION, encoding="utf-8") as fh:
            sql = fh.read()
        self.assertIn("clv_cutoff_at timestamptz", sql)
        self.assertIn("clv_publish_quote_id bigint", sql)
        complete = re.search(r"model_edges_clv_scored_is_complete(.*?)not valid",
                             sql, re.S).group(1)
        for col in ("clv_cutoff_at", "clv_publish_quote_id", "clv_close_basis",
                    "clv_proxy_quoted_at", "clv_lead_time_minutes",
                    "clv_protocol_version"):
            self.assertIn(f"{col} is not null", complete,
                          f"a scored row may still omit {col}")


# ---------------------------------------------------------------------------
# Amendment 6 (h) — the staleness clock is named, and left alone
# ---------------------------------------------------------------------------

class TestStalenessClock(unittest.TestCase):
    def test_the_limit_is_still_45_minutes_from_the_capture_instant(self):
        self.assertEqual(STALENESS_LIMIT_MINUTES, 45)
        self.assertEqual(STALENESS_MEASURED_FROM, "captured_at")

    def test_an_old_provider_last_update_does_not_make_a_fresh_quote_stale(self):
        """The rule was frozen against CFL's observation cadence. Silently
        re-pointing it at the book's own last move would change which rows score
        under the same version number — that is an amendment, not a fix."""
        quotes = [dict(q, provider_last_update=FRESH - dt.timedelta(hours=9))
                  for q in three_books()]
        got = score(quotes=quotes)
        self.assertTrue(got["scored"], got["detail"])
        self.assertEqual(got["diagnostics"]["stale"], 0)

    def test_a_stale_capture_instant_still_fails_however_recent_the_book_move(self):
        quotes = [dict(q, provider_last_update=START - dt.timedelta(minutes=1))
                  for q in three_books(at=START - dt.timedelta(hours=3))]
        got = score(quotes=quotes)
        self.assertEqual(got["reason"], "stale_close")

    def test_provider_last_update_is_still_required_provenance(self):
        self.assertIn("provider_last_update", REQUIRED_QUOTE_PROVENANCE)
        self.assertEqual(score(quotes=[dict(q, provider_last_update=None)
                                       for q in three_books()])["reason"],
                         "incomplete_quote_provenance")


# ---------------------------------------------------------------------------
# The 20-event floor counts EVENTS, by event_id
# ---------------------------------------------------------------------------

class TestEventCounting(unittest.TestCase):
    """The publication gate needs 20 DISTINCT EVENTS, and an event is an
    event_id.

    Counting event_date instead is the tempting shortcut, because every edge row
    already carries one. It is wrong in exactly the way that matters: the UFC
    runs two cards on one date regularly (an early prelim card and a numbered
    card, or a Fight Night in one time zone and an overseas card in another). A
    date count of 20 can be 19 real events or fewer, and the gate would open on
    a sample narrower than the floor was written to require.
    """

    def test_the_scored_row_carries_the_fight_s_event_id(self):
        got = score(fight={**FIGHT, "event_id": 4242})
        self.assertTrue(got["scored"], got["reason"])
        self.assertEqual(got["event_id"], 4242)
        self.assertEqual(got["event_date"], "2026-09-12",
                         "the date is still carried — it is just not the count")

    def test_a_fight_with_no_event_id_scores_but_carries_none(self):
        """A missing event_id must not fabricate one or block the score; it has
        to be visibly absent so the report can refuse to count it."""
        got = score(fight=dict(FIGHT))          # no event_id key at all
        self.assertTrue(got["scored"], got["reason"])
        self.assertIsNone(got["event_id"])

    def test_two_event_ids_on_one_date_count_as_two_events(self):
        """The regression this class exists for."""
        rows = [
            {"scored": True, "event_id": 11, "event_date": "2026-09-12",
             "edge_id": 1, "fight_id": 1, "reason": None, "detail": None,
             "closing_book_count": 3, "quote_ids": [1, 2, 3],
             "consensus_sha256": "a" * 64},
            {"scored": True, "event_id": 12, "event_date": "2026-09-12",
             "edge_id": 2, "fight_id": 2, "reason": None, "detail": None,
             "closing_book_count": 3, "quote_ids": [4, 5, 6],
             "consensus_sha256": "b" * 64},
        ]
        out = self._report(rows)
        self.assertIn("2 observation(s) across 2 distinct event(s)", out)
        self.assertIn("2 / 20", out)
        self.assertNotIn("1 distinct event", out,
                         "counting by event_date would have collapsed these two "
                         "cards into one")

    def test_one_event_id_on_two_dates_counts_as_one_event(self):
        """The mirror. A card that starts 22:00 local and finishes after
        midnight UTC is one event, however many dates its rows carry."""
        rows = [
            {"scored": True, "event_id": 11, "event_date": "2026-09-12",
             "edge_id": 1, "fight_id": 1, "reason": None, "detail": None,
             "closing_book_count": 3, "quote_ids": [1], "consensus_sha256": "a" * 64},
            {"scored": True, "event_id": 11, "event_date": "2026-09-13",
             "edge_id": 2, "fight_id": 2, "reason": None, "detail": None,
             "closing_book_count": 3, "quote_ids": [2], "consensus_sha256": "b" * 64},
        ]
        out = self._report(rows)
        self.assertIn("2 observation(s) across 1 distinct event(s)", out)
        self.assertIn("1 / 20", out)

    def test_a_row_without_an_event_id_is_warned_about_not_counted(self):
        rows = [
            {"scored": True, "event_id": 11, "event_date": "2026-09-12",
             "edge_id": 1, "fight_id": 1, "reason": None, "detail": None,
             "closing_book_count": 3, "quote_ids": [1], "consensus_sha256": "a" * 64},
            {"scored": True, "event_id": None, "event_date": "2026-09-12",
             "edge_id": 2, "fight_id": 2, "reason": None, "detail": None,
             "closing_book_count": 3, "quote_ids": [2], "consensus_sha256": "b" * 64},
        ]
        out = self._report(rows)
        self.assertIn("across 1 distinct event(s)", out)
        self.assertIn("1 scored row(s) carry no event_id", out,
                      "an uncountable row has to be visible, not silently "
                      "dropped or silently counted as its own event")

    def test_the_gate_line_says_it_counts_by_event_id(self):
        out = self._report([])
        self.assertIn("20 distinct events (by event_id)", out)
        self.assertIn("Blocked.", out)

    @staticmethod
    def _report(rows):
        """Run the real reporting function and capture what it printed.

        Importing settle_clv is safe here: the module reads env at call time,
        not at import, and _report_clv001 touches nothing but its argument.
        """
        import contextlib
        import io
        engine_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if engine_dir not in sys.path:
            sys.path.insert(0, engine_dir)
        import settle_clv                                            # noqa: E402
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            settle_clv._report_clv001(rows)
        return buf.getvalue()


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
            BET, OPP, START, NOW, BOOKS, forecast_locked_at=LOCK)
        self.assertEqual(pairs, [])
        self.assertEqual(diag["implausible_timestamp"], 1)
        self.assertEqual(diag["wrong_fighter"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
