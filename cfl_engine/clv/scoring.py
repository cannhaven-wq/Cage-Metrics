"""CLV-001 row scoring: which quotes are eligible, and what a row scores.

Pure functions over plain dicts. No database, no network, no clock of its own —
`now` is always passed in. `settle_clv.py` fetches rows and hands them here; the
rules live here and are unit-tested here (`test_scoring.py`).

Governed by `research/clv/CLV_MEASUREMENT_PROTOCOL.md` (CLV-001, frozen
2026-09-16). Every constant below traces to a resolved question or a
decided rule, named in the comment beside it. Nothing here is tunable.

The order of operations is the part that is easy to get wrong, so it is fixed:

    immutable forecast lock  ->  linked publish quote  ->  eligible quotes
                             ->  per-book two-sided pairs  ->  de-vig EACH book
                             ->  median of the per-book fair probabilities
                             ->  CLV_return against the posted price

Eligibility is decided PER ROW, never per table (Amendment 6). A `fight_odds`
row is usable because that row carries the §4 provenance, not because the
columns exist on the table — the 110,032 rows captured before the columns
landed carry NULL in all of them and are permanently unscorable.

De-vig first, median second (Q-02). Taking the median of vigged prices and
de-vigging once afterwards blends the books' margins together and is a different
estimator — `test_devig.py` pins that they genuinely differ.

**Fail closed.** Every path that cannot establish a required input returns an
unscored reason from `UNSCORED_REASONS` rather than a number. There is no
fallback, no substitution and no imputation (R-04). A row that cannot be scored
is counted and reported (R-05), which is what stops a coverage problem hiding
inside a favourable average.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

try:                                  # imported as cfl_engine.clv.scoring
    from .devig import (
        DevigError, MAX_MARKET_PROB, MIN_MARKET_PROB, american_to_prob,
        clv_return, median, power_devig,
    )
except ImportError:                   # run directly, with this folder on sys.path
    from devig import (                # noqa: F401
        DevigError, MAX_MARKET_PROB, MIN_MARKET_PROB, american_to_prob,
        clv_return, median, power_devig,
    )

PROTOCOL_ID = "CLV-001"
PROTOCOL_VERSION = "1.0.10"
PROTOCOL_TAG = f"{PROTOCOL_ID}@{PROTOCOL_VERSION}"

# ---------------------------------------------------------------------------
# What the benchmark is called
# ---------------------------------------------------------------------------
# It is the **CFL closing-price proxy** — long form, the *late pre-fight
# closing-price proxy*. It is NOT the sportsbook closing line and may never be
# described as the exact closing line on any surface, in any artifact, or in any
# summary.
#
# The distinction is real and is stated rather than hidden: for bouts after the
# first, the cutoff is the previous bout's completion, so the proxy can sit
# several minutes before the actual bell. That is accepted for this protocol
# version because it is the most consistent, observable and reproducible cutoff
# implementable with the tools currently available — not because the gap is
# thought to be zero.
BENCHMARK_NAME = "CFL closing-price proxy"
BENCHMARK_NAME_LONG = "late pre-fight closing-price proxy"

# ---------------------------------------------------------------------------
# The close reference — Amendments 3 and 4.1, superseded in part by 5
# ---------------------------------------------------------------------------
# A UFC card is one scheduled start and then a queue. Only the FIRST bout begins
# at a time anybody published; every later bout begins when the one before it
# ends (Amendment 3). A single card-level "commence time" applied to all thirteen
# fights is therefore wrong for twelve of them.
#
# THE OPERATIONAL CUTOFF — Amendment 5, and it is a PROXY by construction
# ---------------------------------------------------------------------------
# Frozen for this protocol version:
#
#   bout 1      cutoff = the card's SCHEDULED START
#   bout 2..N   cutoff = the EXACT COMPLETION of the immediately previous bout
#
# and the scored price is the latest eligible sportsbook snapshot strictly
# before that cutoff. Those two, always — no third case, and nothing overrides
# them inside this version.
#
# WHAT THIS IS AND IS NOT. For bouts after the first the cutoff is the previous
# bout's completion, not the bell, so the proxy can sit several minutes before
# the fight actually started. That is accepted here, deliberately and on the
# record: it is the most consistent, observable and reproducible cutoff
# implementable with the tools currently available. It is a CFL closing-price
# proxy, never the exact sportsbook closing line, and the gap is reported per
# row rather than assumed away.
#
# The previous bout's completion therefore has TWO roles, and both are real:
#
#   1. it is this protocol version's scoring cutoff for the next fight;
#   2. it triggers aggressive card-night capture for that fight.
#
# It is NOT a claim about when the next fight began. The next fight began at its
# bell, some minutes later, and nothing here pretends otherwise: the cutoff is
# named a cutoff, quotes at or after it are excluded directly, and no
# "the fight had started" fact is asserted from it.
#
# An earlier draft (Amendment 4.2) treated role 2 as the only legitimate one and
# refused role 1, on the grounds that the cutoff precedes the bell. Amendment 5
# supersedes that: waiting for a confirmed bell means scoring nothing, and a
# consistently-early cutoff that every observation shares is a better measurement
# than no measurement — provided it is named as a proxy and its lead time is
# recorded, which it is.
#
# IF RELIABLE BELL TIMESTAMPS ARRIVE, that is a NEW PROTOCOL VERSION — not a
# per-row upgrade inside this one. Rows scored under this version are never
# retroactively reinterpreted or overwritten, which is why every scored row
# carries its own `clv_protocol_version`.
CLOSE_REFERENCE_BASES = frozenset({
    "scheduled_first_bout",      # bout 1 — the card's scheduled start.
    "previous_bout_completion",  # bouts 2..N — the exact completion before it.
})

# `bell_at` IS NOT HERE, and that is deliberate (Amendment 5.1).
#
# An earlier draft let a confirmed bell outrank the frozen cutoff "where one
# exists". That silently makes this version two protocols: fights with a bell
# scored one way, fights without scored another, inside the same version and the
# same summary statistic. A version whose rule depends on which optional field
# happens to be populated is not frozen.
#
# So the cutoff for this version is exactly the two above, always. `bell_at`
# remains an AUDIT field — carried on the row, never substituted for the cutoff —
# and scoring against real bells is a NEW PROTOCOL VERSION whenever reliable ones
# arrive.
AUDIT_ONLY_BASES = frozenset({"bell_at"})

# Bases whose cutoff is intended to BE the fight's start, so the recorded lead
# time is also, as far as this version can tell, the gap to the start.
EXACT_REFERENCE_BASES = frozenset({"scheduled_first_bout"})

# Bases whose cutoff PRECEDES the bell. The lead time to the cutoff is exact;
# the gap to the actual bell is larger by the walkout interval, so the recorded
# lead time is a LOWER BOUND on it. Reported, never hidden.
PRECEDES_BELL_BASES = frozenset({"previous_bout_completion"})

# Recognised, reported, and still never a cutoff: the card's scheduled start
# applied to a later bout sits hours early (Amendment 4.1). Amendment 5 restores
# `previous_bout_completion` to the scoring set and leaves this one out.
NON_SCORING_REFERENCE_BASES = frozenset({"card_scheduled_start"})

# Kept as the name the storage layer uses. Identical to PRECEDES_BELL_BASES: a
# cutoff that precedes the bell makes the recorded lead time a lower bound on the
# true gap to it.
LOWER_BOUND_REFERENCE_BASES = PRECEDES_BELL_BASES

# Bases that were admissible under an earlier amendment and are not now.
# `provider_commence` was narrowed to the first bout by Amendment 3 and renamed
# `scheduled_first_bout` there. `bell_at` was admitted by Amendment 5 as an
# override and withdrawn by 5.1 — it stays an audit field.
SUPERSEDED_START_BASES = frozenset({"provider_commence", "bell_at"})

# Still inadmissible, unchanged: the event date at 18:00 UTC is a placeholder,
# wrong by hours in both directions, and would decide staleness by a constant
# nobody chose for this purpose.
INADMISSIBLE_START_BASES = frozenset({"event_date_fallback"})

# R-13. Live capture begins 2026-05-22; everything stamped before it is a
# historical import whose capture instant was never recorded and defaulted to
# the Unix epoch. 30,724 of 110,032 fight_odds rows carry 1970-01-01.
LIVE_CAPTURE_ERA_START = dt.datetime(2026, 5, 22, tzinfo=dt.timezone.utc)

# Q-01b. One measured near-card capture interval (30 min) plus 15 min grace.
# NOT derived from the overall gap distribution, which is bimodal — the
# between-cards mode would have produced a useless ~24-hour limit.
STALENESS_LIMIT_MINUTES = 45

# WHICH INSTANT THE STALENESS LIMIT IS MEASURED FROM — Amendment 6 (h).
#
# `captured_at`. The 45 minutes was derived from CFL's own OBSERVATION cadence —
# one measured near-card capture interval plus grace — so it answers "how long
# ago did we look?" and nothing else. It is frozen against that meaning.
#
# `provider_last_update` is a different quantity: when the BOOK last moved the
# price. A price we retrieved five minutes before the cutoff that the book last
# moved four hours earlier is stale in a way this limit was never calibrated to
# detect. That is worth knowing, which is why §4 item 11 requires the field and
# `REQUIRED_QUOTE_PROVENANCE` below refuses a quote without it — but measuring
# the frozen 45 minutes from it instead would silently redefine the rule and
# change which rows score, under the same version number.
#
# So: recorded, required, reported — never the clock. Re-pointing the limit at
# provider_last_update is a METHODOLOGICAL AMENDMENT, not an implementation
# choice.
STALENESS_MEASURED_FROM = "captured_at"

# Q-02. Minimum eligible books with a valid TWO-SIDED close.
MIN_BOOKS = 3

# Q-03. Exchanges and prediction markets are excluded from the primary metric:
# they price on commission rather than vig, so de-vigging them is meaningless
# and mixing them into a vig-based consensus produces a number that is cleanly
# neither. Named here so the exclusion survives a book-id renumbering.
EXCHANGE_BOOK_NAMES = frozenset({"polymarket", "kalshi", "betfair", "smarkets",
                                 "matchbook", "prophetx", "novig", "sporttrade"})

# Not books at all — feed-side aggregates. A consensus row is already a blend of
# other books' margins, so de-vigging it is not the same operation as de-vigging
# a book, and counting it toward MIN_BOOKS would double-count its constituents.
AGGREGATE_BOOK_NAMES = frozenset({"bfo consensus", "cfl consensus (odds api)"})

# ---------------------------------------------------------------------------
# §4 provenance, enforced ROW BY ROW — Amendment 6 (a)
# ---------------------------------------------------------------------------
# The migration adding these columns makes them RECORDABLE. It does not make any
# particular row contain them, and every one of the 110,032 rows that predate it
# carries NULL in all of them, permanently and correctly ("this row predates the
# column").
#
# The defect this closes: eligibility was decided at the SCHEMA level — the
# settler checked that `model_edges` had the CLV-001 columns and then scored on
# whatever `fight_odds` happened to hold. So the day after the capture migration
# lands, a May or June quote with a perfectly credible `captured_at` and NULL in
# every new provenance column becomes scorable, and the measurement quietly
# includes rows that cannot support it. §4 is explicit that these "cannot be
# backfilled" and that anything captured without them "simply cannot be used for
# the definitions that need them" — that is a per-QUOTE rule, and it is now
# applied per quote.
#
# Each entry names the §4 item it satisfies:
#   source_event_id       item  9  provider market id — Q-10's stable key
#   feed_version          item  6  provider and feed version
#   opponent_fighter_id   item 10  opponent identity at quote time
#   provider_last_update  item 11  the provider's own timestamp …
#   retrieved_at          item 11  … kept separate from ours
#   market_status         item  8  suspension / takedown state
#   raw                   item 12  the immutable link to what the provider said
#
# Items 1 and 2 (book, fighter, price, credible UTC instant, both corners) are
# enforced separately and earlier, because a quote missing those is not a quote.
REQUIRED_QUOTE_PROVENANCE = (
    "source_event_id", "feed_version", "opponent_fighter_id",
    "provider_last_update", "retrieved_at", "market_status", "raw",
)

# The publish side carries the same burden (§4 item 12). A posted price with no
# link to the exact quote it came from is an assertion, not a record — the same
# defect the PROP-0001 provenance audit found in v1 locks that recorded
# `code_version` as `…-dirty` with no record of what dirty was.
REQUIRED_PUBLISH_PROVENANCE = REQUIRED_QUOTE_PROVENANCE


def _provenance_present(value) -> bool:
    """Present means populated, not merely non-NULL.

    An empty string and an empty jsonb object both survive a NULL check while
    recording nothing, which is the failure mode this whole section exists to
    stop.
    """
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return len(value) > 0
    return True


def missing_quote_provenance(quote: dict,
                             required: tuple = REQUIRED_QUOTE_PROVENANCE) -> tuple:
    """Which §4 provenance fields this quote does not carry. Empty means whole."""
    return tuple(f for f in required if not _provenance_present(quote.get(f)))


class Unscored(Exception):
    """Carries the closed-vocabulary reason a row could not be scored."""

    def __init__(self, reason: str, detail: str = ""):
        if reason not in UNSCORED_REASONS:
            raise ValueError(f"{reason!r} is not in the closed vocabulary")
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


# The closed vocabulary. An open text field becomes a free-form excuse column and
# the counts stop aggregating, so this list and the database CHECK constraint in
# research/clv/proposed_2026-09-16_clv001_columns.sql must stay identical.
UNSCORED_REASONS = (
    # --- global preconditions: these disqualify every row at once ---
    "schema_incomplete",             # the CLV-001 columns are not on the table
    "protocol_version_mismatch",     # row/protocol versions differ; not comparable
    "eligible_book_list_not_frozen",  # Q-02's named list is absent from protocol.json
    # --- per-row ---
    "no_publish_price",              # odds_at_publish missing
    "bet_fighter_not_in_fight",      # Q-10: opponent change / rematch / reschedule
    "no_scheduled_start",            # Q-01 has no reference instant to measure to
    "no_closing_quotes",             # nothing on file from an eligible book
    "implausible_timestamp",         # R-13: epoch-era or future capture instant
    "stale_close",                   # outside the 45-minute limit
    "one_sided_close",               # no eligible book quoted both corners
    "non_market_price",              # R-03 band violation on every pair
    "devig_failed",                  # no root in the frozen bracket
    "insufficient_books",            # fewer than MIN_BOOKS survived
    "forecast_not_before_close",     # R-07: no-lookahead violated
    "only_pre_card_price",           # Amendment 4.1: safely pre-fight, not late
    "no_previous_bout_completion",   # Amendment 5: bout 2..N with no cutoff on file
    # --- Amendment 6, provenance hardening ---
    "no_immutable_forecast_lock",    # R-07: the lock rests only on a mutable row
    "ambiguous_edge_identity",       # R-07: the snapshot cannot say WHICH edge
    "no_publish_quote_link",         # §4 item 12: posted price has no source quote
    "incomplete_quote_provenance",   # §4: the close quotes lack required fields
    "market_identity_changed",       # Q-10 / R-06: different market or opponent
)


def is_eligible_book(name: str) -> bool:
    """Q-02/Q-03 shape test: a real sportsbook, not an exchange or an aggregate.

    This is a *necessary* condition, not a sufficient one. Q-02 requires a fixed
    NAMED list frozen at protocol freeze; this function only rules out the two
    categories that are excluded by kind. `settle_clv.py` still refuses to score
    anything until the named list exists — see `eligible_book_list_not_frozen`.
    """
    key = (name or "").strip().lower()
    return bool(key) and key not in EXCHANGE_BOOK_NAMES and key not in AGGREGATE_BOOK_NAMES


def credible_capture_instant(captured_at: dt.datetime | None,
                             now: dt.datetime) -> bool:
    """R-13. A populated but fake timestamp is not a timestamp.

    Credible means at or after the live-capture era began and not in the future.
    An epoch stamp is the worst case for this protocol specifically: it is always
    "before the fight", so it passes every ordering rule and would be selected as
    the opener every time.
    """
    if captured_at is None:
        return False
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=dt.timezone.utc)
    return LIVE_CAPTURE_ERA_START <= captured_at <= now


def quote_prob(quote: dict) -> float | None:
    """Vigged single-side implied probability for a raw quote row."""
    p = quote.get("implied_prob")
    if p is None and quote.get("american_odds") is not None:
        p = american_to_prob(quote["american_odds"])
    return None if p is None else float(p)


def closing_pairs(quotes: list[dict], bet_fighter_id: int, opp_fighter_id: int,
                  reference_instant: dt.datetime, now: dt.datetime,
                  eligible_book_ids: set[int],
                  forecast_locked_at: dt.datetime | None,
                  publish_market_id: str | None = None,
                  ) -> tuple[list[dict], dict]:
    """The scheduled-close proxy (Q-01), per book, both corners.

    For each eligible book, take its latest quote per corner that is

      * strictly AFTER the immutable forecast lock (R-07),
      * strictly BEFORE `reference_instant` (Q-01, Amendment 5),
      * on a credible capture instant (R-13),
      * within the staleness limit measured from `captured_at` (Q-01b),
      * carrying every §4 provenance field (Amendment 6 (a)),
      * and referring to the same market and the same opponent as the forecast
        (Q-10, R-06).

    A book contributes a pair only if BOTH corners survive; a book quoting one
    side is not a two-way market and cannot be de-vigged.

    `forecast_locked_at` is REQUIRED and is deliberately not defaulted. R-07 is
    the rule an implementation is most likely to violate by accident, and a
    default of None would be a silent bypass of it — the same shape of hole
    Amendment 5.1 closed in `score_row`. Passing None here drops every quote:
    no lock, no eligible close.

    Returns `(pairs, diagnostics)`. `pairs` is one dict per contributing book,
    already ordered by book id so the artifact is deterministic. `diagnostics`
    counts why the others dropped out, which is what distinguishes
    `one_sided_close` from `stale_close` from `implausible_timestamp` when the
    row ends up unscored.

    This never raises: it reports. The caller decides what the counts mean.
    """
    diag = {"seen": 0, "ineligible_book": 0, "after_reference": 0,
            "implausible_timestamp": 0, "stale": 0, "one_sided_books": 0,
            "wrong_fighter": 0, "before_forecast_lock": 0,
            "missing_provenance": 0, "opponent_mismatch": 0,
            "market_id_mismatch": 0}
    # Q-01b, measured from the OBSERVATION instant. See STALENESS_MEASURED_FROM.
    cutoff = reference_instant - dt.timedelta(minutes=STALENESS_LIMIT_MINUTES)

    # book_id -> fighter_id -> the latest surviving quote
    latest: dict[int, dict[int, dict]] = {}
    for q in quotes:
        diag["seen"] += 1
        book_id = q.get("book_id")
        if book_id not in eligible_book_ids:
            diag["ineligible_book"] += 1
            continue
        fighter_id = q.get("fighter_id")
        if fighter_id not in (bet_fighter_id, opp_fighter_id):
            diag["wrong_fighter"] += 1
            continue
        at = q.get("captured_at")
        if not credible_capture_instant(at, now):
            diag["implausible_timestamp"] += 1
            continue
        # R-07, literally, per quote pair — not once per edge against the cutoff.
        # `published_at < cutoff` is a far weaker test: it lets a forecast locked
        # at 9:28 be scored against a book quote from 9:20 as long as the cutoff
        # is 9:30. That quote was on the screen BEFORE the forecast existed, so
        # "the forecast preceded the market quote" is false for it, and the
        # comparison is measuring a price the forecast could have been read off.
        if forecast_locked_at is None or at <= forecast_locked_at:
            diag["before_forecast_lock"] += 1
            continue
        if at >= reference_instant:
            diag["after_reference"] += 1      # Q-01: strictly before, and R-03
            continue
        if at < cutoff:
            diag["stale"] += 1
            continue
        # §4, per row. The columns existing on the table says nothing about this
        # row carrying them, and a pre-migration row never will.
        if missing_quote_provenance(q):
            diag["missing_provenance"] += 1
            continue
        # Q-10, mechanically. The quote names its own opponent; if that is not
        # the other corner of the fight we are scoring, the price referred to a
        # different matchup and cannot be compared with this forecast.
        expected_opponent = (opp_fighter_id if fighter_id == bet_fighter_id
                             else bet_fighter_id)
        if q.get("opponent_fighter_id") != expected_opponent:
            diag["opponent_mismatch"] += 1
            continue
        # R-06. A repost or a rematch gets a new provider market id, and is a
        # different market rather than a later quote on the same one. Enforced
        # only when the publish side identified its market — otherwise there is
        # nothing to compare against and the check would be inventing a match.
        if (publish_market_id is not None
                and q.get("source_event_id") != publish_market_id):
            diag["market_id_mismatch"] += 1
            continue
        keep = latest.setdefault(book_id, {})
        if fighter_id not in keep or at > keep[fighter_id]["captured_at"]:
            keep[fighter_id] = q

    pairs = []
    for book_id in sorted(latest):
        corners = latest[book_id]
        if bet_fighter_id not in corners or opp_fighter_id not in corners:
            diag["one_sided_books"] += 1
            continue
        bet_q, opp_q = corners[bet_fighter_id], corners[opp_fighter_id]
        q_bet, q_opp = quote_prob(bet_q), quote_prob(opp_q)
        if q_bet is None or q_opp is None:
            diag["one_sided_books"] += 1      # a corner with no price is no corner
            continue
        pairs.append({
            "book_id": book_id,
            "q_bet": q_bet,
            "q_opp": q_opp,
            "quote_ids": sorted(x for x in (bet_q.get("id"), opp_q.get("id"))
                                if x is not None),
            "quoted_at": max(bet_q["captured_at"], opp_q["captured_at"]),
        })
    return pairs, diag


def consensus(pairs: list[dict]) -> tuple[float, int, dict]:
    """De-vig each book, then median (Q-02, Q-04, Q-12 — power).

    Returns `(median_fair_bet, n_books, artifact)`. The artifact is the
    calculation as performed: every contributing book with its raw pair, its
    de-vigged fair probability and its solved exponent. Stored so a later reader
    can reconstruct the number without re-querying rows that may since have been
    added to the same fight.

    Raises `Unscored` with `non_market_price`, `devig_failed` or
    `insufficient_books` — in that order of specificity, so the reported reason
    names the actual obstacle rather than its downstream symptom.
    """
    books, band_failures, devig_failures = [], 0, 0
    for p in pairs:
        if not (MIN_MARKET_PROB <= p["q_bet"] <= MAX_MARKET_PROB
                and MIN_MARKET_PROB <= p["q_opp"] <= MAX_MARKET_PROB):
            band_failures += 1                # R-03
            continue
        try:
            fair_bet, _, k = power_devig(p["q_bet"], p["q_opp"])
        except DevigError:
            devig_failures += 1
            continue
        books.append({"book_id": p["book_id"],
                      "q_bet": p["q_bet"], "q_opp": p["q_opp"],
                      "fair_bet": fair_bet, "k": k,
                      "quote_ids": p["quote_ids"]})

    if not books:
        if band_failures and not devig_failures:
            raise Unscored("non_market_price",
                           f"all {band_failures} book pair(s) fell outside "
                           f"[{MIN_MARKET_PROB}, {MAX_MARKET_PROB}] (R-03)")
        if devig_failures:
            raise Unscored("devig_failed",
                           f"{devig_failures} book pair(s) had no root in the "
                           f"frozen bracket")
        raise Unscored("insufficient_books", "0 eligible two-sided books")

    if len(books) < MIN_BOOKS:
        raise Unscored(
            "insufficient_books",
            f"{len(books)} eligible book(s) survived de-vig; the frozen minimum "
            f"is {MIN_BOOKS} (Q-02)")

    fair = median([b["fair_bet"] for b in books])
    artifact = {
        "protocol": PROTOCOL_TAG,
        "devig": "power",
        "books": books,
        "median_fair_bet": fair,
        "n_books": len(books),
    }
    return fair, len(books), artifact


def canonical_sha256(artifact: dict) -> str:
    """sha256 of the canonical serialisation, so a stored artifact that is later
    edited is detectable. model_edges has no append-only trigger and adding one
    would not be an additive migration, so integrity is by hash instead."""
    blob = json.dumps(artifact, sort_keys=True, separators=(",", ":"),
                      default=str).encode()
    return hashlib.sha256(blob).hexdigest()


# The stable immutable edge id, if both sides carry one. `model_edges.id` is the
# edge's own identity; `pre_fight_snapshots.edge_model_edge_id` is the snapshot's
# record of WHICH edge it froze. When both are present the match is exact and
# nothing below is needed.
#
# Neither existed before Amendment 7. The column is added by
# research/clv/proposed_2026-09-16_snapshot_edge_identity.sql (UNAPPLIED) and
# written by cfl_engine/snapshot_predictions.py once it lands; every snapshot
# taken before then carries NULL, and those fall to the cohort rule below.
SNAPSHOT_EDGE_ID_FIELD = "edge_model_edge_id"

# When that edge was published, frozen at snapshot time. Added by the same
# migration and written by the same producer.
#
# Deliberately NOT `engine_published_at`. That column holds
# `model_picks.published_at` — the MODEL PICK's publication — and a pick and a
# value edge are different records published at different times. CLV-001 scores
# the EDGE, so R-07's "forecast" is the edge, and the pick's instant is not a
# stand-in for it in any branch.
SNAPSHOT_EDGE_PUBLISHED_FIELD = "edge_published_at"

# Never admissible as the edge's lock, under any circumstances. Named so the
# exclusion is a value in the module rather than an absence somebody has to
# notice.
NOT_AN_EDGE_LOCK_FIELDS = frozenset({"engine_published_at"})


def forecast_lock(edge: dict, snapshot: dict | None,
                  edge_cohort: list | None = None) -> tuple:
    """The IMMUTABLE instant the forecast was locked.

    Returns `(locked_at, provenance)`. Raises `Unscored` with
    `no_immutable_forecast_lock` or `ambiguous_edge_identity` when it cannot
    establish one — never returns a guess.

    IDENTIFYING THE EDGE, which is the hard half.

    `pre_fight_snapshots` is unique on `fight_id`, so a row always exists for a
    snapshotted fight and matching on the fight alone would accept a record of
    some other forecast as this one's lock. The cross-check on side + bet
    fighter + price is much stronger, but it is still not an identity: the same
    fight can be republished with the same side, the same fighter and — by
    coincidence or because the price had not moved — the same price.

    That is not hypothetical here. `snapshot_predictions.py` explicitly handles
    several live edges on one fight and keeps only the one with the latest
    `published_at`, so the architecture does NOT guarantee one live edge per
    fight, and the snapshot is a record of one particular publication.

    Two answers, in order:

      1. the shared immutable id, when both sides carry it. Exact, and the only
         one that is an identity rather than a coincidence test;
      2. the tuple, plus a UNIQUENESS requirement over the fight's live-edge
         cohort: exactly one edge on that fight may match the snapshot's tuple.
         Two matches is ambiguity, and ambiguity scores nothing.

    `edge_cohort` is every live edge on this fight, this one included. `None`
    means the caller did not establish the cohort, which is not the same as an
    empty one and is refused — the same fail-closed treatment
    `closing_pairs` gives a missing lock.

    R-07 does not merely say the forecast precedes the quote. It says: "A
    forecast whose timestamp cannot be established from an immutable record is
    not eligible." `model_edges` is a working table with no append-only trigger —
    `published_at` can be rewritten, and a row rewritten after the fact is not a
    record of what we published, it is a claim about it. Treating it as the lock
    is exactly the accident R-07 warns about, one step removed.

    `pre_fight_snapshots` is the immutable record, and it is trigger-enforced
    against UPDATE and DELETE for every role including `service_role`. Identity
    within it is `edge_model_edge_id` first and the tuple only as the legacy
    fallback, as above.

    WHICH INSTANT, and this is the part that is easy to get wrong:

      1. `edge_published_at` — the EDGE's own publication, when the snapshot
         carries it (and the edge id beside it; the two are required together).
      2. `snapshot_at` — the legacy fallback, for snapshots taken before that
         column existed. Later than publication, so fail-closed, and marked
         `immutable_is_conservative_fallback` on the row rather than passed off
         as the real instant.
      3. **Never `engine_published_at`.** That is `model_picks.published_at` —
         the MODEL PICK's publication — and a pick and a value edge are
         different records published at different times. It is carried for audit
         and is not a lock in any branch (`NOT_AN_EDGE_LOCK_FIELDS`).

    THE EFFECTIVE LOCK IS THE LATER of the immutable instant and the mutable
    `published_at`. Later is strictly harder to satisfy, so a `published_at`
    that has been edited — in either direction, for any reason — can only ever
    cost observations. It can never admit a quote the immutable record would
    have excluded. That asymmetry is the whole point, and it is why the two are
    combined this way rather than one being trusted over the other.
    """
    if not snapshot:
        raise Unscored("no_immutable_forecast_lock",
                       "no pre_fight_snapshots row identifies this edge, so the "
                       "forecast's lock instant rests only on model_edges."
                       "published_at, which is mutable (R-07)")

    snapshot_edge_id = snapshot.get(SNAPSHOT_EDGE_ID_FIELD)
    identity = None
    if snapshot_edge_id is not None and edge.get("id") is not None:
        if snapshot_edge_id != edge.get("id"):
            raise Unscored(
                "no_immutable_forecast_lock",
                f"the pre-fight snapshot froze edge {snapshot_edge_id!r} and "
                f"this is edge {edge.get('id')!r}; it is the record of a "
                f"different publication (R-07)")
        identity = "shared_edge_id"

    if identity is None:
        for field, mine, theirs in (
                ("side", edge.get("side"), snapshot.get("edge_side")),
                ("bet_fighter_id", edge.get("bet_fighter_id"),
                 snapshot.get("edge_bet_fighter_id")),
                ("odds_at_publish", edge.get("odds_at_publish"),
                 snapshot.get("edge_odds_at_publish"))):
            if theirs is None:
                raise Unscored(
                    "no_immutable_forecast_lock",
                    f"the pre-fight snapshot for this fight records no {field}, "
                    f"so it cannot be matched to this edge (R-07)")
            if mine != theirs:
                raise Unscored(
                    "no_immutable_forecast_lock",
                    f"the pre-fight snapshot records {field}={theirs!r} and this "
                    f"edge carries {mine!r}; they are records of different "
                    f"forecasts (R-07)")

        # The tuple matched. That is necessary and not sufficient — it is only an
        # identity if no OTHER live edge on this fight matches it too.
        if edge_cohort is None:
            raise Unscored(
                "ambiguous_edge_identity",
                "the snapshot carries no edge id, so this edge was matched by "
                f"(side, bet_fighter_id, odds_at_publish) — and the fight's live "
                f"edges were not supplied, so that match cannot be shown to be "
                f"unique. Not established is not the same as established "
                f"(R-07). Wiring {SNAPSHOT_EDGE_ID_FIELD} removes the question.")
        twins = [e for e in edge_cohort
                 if e.get("side") == snapshot.get("edge_side")
                 and e.get("bet_fighter_id") == snapshot.get("edge_bet_fighter_id")
                 and e.get("odds_at_publish") == snapshot.get("edge_odds_at_publish")]
        if len(twins) > 1:
            raise Unscored(
                "ambiguous_edge_identity",
                f"{len(twins)} live edges on this fight share the snapshot's "
                f"(side, bet_fighter_id, odds_at_publish), so the snapshot "
                f"cannot say which publication it froze. "
                f"`snapshot_predictions.py` keeps only the latest live edge per "
                f"fight, so several are possible and only one of them is the "
                f"one on record. Ambiguous scores nothing (R-07).")
        identity = "tuple_unique_in_cohort"

    # THE EDGE'S OWN PUBLICATION INSTANT, and nothing else.
    #
    # `engine_published_at` is NOT it. That column is `model_picks.published_at` —
    # the MODEL PICK's publication — and a pick and a value edge are different
    # records published at different times: the engine posts a pick, and the edge
    # derived from it appears later, when the price has moved far enough to flag
    # one. Using the pick's instant as the edge's places the lock early and admits
    # quotes from before the edge existed. That is a lookahead violation wearing
    # an immutable record's clothes, which is the worst kind, because everything
    # about it looks audited.
    #
    # So: `edge_published_at` when the snapshot carries it, and `snapshot_at`
    # otherwise. `snapshot_at` is not the publication instant either — it is
    # LATER than it — but that is the safe direction: it proves the edge existed
    # by then, and a later lock can only narrow the eligible window. It is
    # labelled a fallback on the row so nobody reads it as the real thing.
    #
    # `engine_published_at` never appears here in any branch. It stays on the
    # snapshot as provenance for the main model prediction, which is what it is.
    # Both fields together, never one alone: a publication instant with no edge
    # id beside it cannot be attached to a particular publication, and would be
    # indistinguishable from the pick timestamp it exists to displace.
    if (snapshot.get(SNAPSHOT_EDGE_PUBLISHED_FIELD) is not None
            and snapshot.get(SNAPSHOT_EDGE_ID_FIELD) is not None):
        source = SNAPSHOT_EDGE_PUBLISHED_FIELD
        locked_at = snapshot[SNAPSHOT_EDGE_PUBLISHED_FIELD]
    else:
        source, locked_at = "snapshot_at", snapshot.get("snapshot_at")
    if locked_at is None:
        raise Unscored(
            "no_immutable_forecast_lock",
            f"the pre-fight snapshot carries neither {SNAPSHOT_EDGE_PUBLISHED_FIELD} "
            f"nor snapshot_at, so nothing immutable says when the EDGE was "
            f"published. engine_published_at is the model pick's instant and is "
            f"not a substitute (R-07).")
    is_fallback = source == "snapshot_at"

    published_at = edge.get("published_at")
    effective = locked_at
    if published_at is not None and published_at > effective:
        effective = published_at
    return effective, {
        "locked_at": effective,
        "immutable_locked_at": locked_at,
        "immutable_source": f"pre_fight_snapshots.{source}",
        # TRUE when the immutable instant is `snapshot_at` rather than the edge's
        # own publication time — a conservative bound, not a record of when the
        # edge was published. Labelled rather than smoothed over: a reader
        # comparing two scored rows needs to know which one rests on the weaker
        # evidence, and the weaker one is systematically late.
        "immutable_is_conservative_fallback": is_fallback,
        # Carried for audit, never used as the lock. This is the MODEL PICK's
        # publication, which is a different event from the edge's.
        "engine_published_at": snapshot.get("engine_published_at"),
        "snapshot_id": snapshot.get("id"),
        # HOW the snapshot was tied to this edge. 'shared_edge_id' is an
        # identity; 'tuple_unique_in_cohort' is a match shown to be unique among
        # the fight's live edges, which is weaker and says so on the row.
        "edge_identity": identity,
        "model_edges_published_at": published_at,
        # TRUE when the mutable column is the later of the two and therefore the
        # binding one. Recorded rather than hidden: it is the case where the
        # working table tightened the immutable record, which is allowed, and
        # the case a reader would most want flagged.
        "published_at_is_binding": effective == published_at and published_at != locked_at,
        "agrees_with_immutable_record": published_at == locked_at,
    }


def verify_publish_quote(quote: dict | None, edge: dict, bet_fighter_id: int,
                         opp_fighter_id: int, now: dt.datetime,
                         published_at: dt.datetime) -> tuple:
    """§4 item 12. Returns `(provenance, None)` or `(None, detail)`.

    `odds_at_publish` is one side of `CLV_return`, and without a link to the
    exact source quote it is an assertion rather than a record — we would be
    comparing a de-vigged, fully-provenanced closing consensus against a number
    somebody typed. The link must PROVE, not merely reference:

      * the exact offered price — the quote's own `american_odds` equals
        `odds_at_publish`; a link to a row quoting something else is not a link
        to this price;
      * fighter and opponent identity (Q-10);
      * the provider's market id (R-06 — the stable key across a repost);
      * the quote instant, credible under R-13 **and at or before publication**;
      * provider and feed provenance, `raw` included.

    The temporal check is the one a price match hides. A row can carry the right
    price, the right corners, the right market and a perfectly credible
    `captured_at` and still have been captured AFTER the edge was published — in
    which case it is not the source of the posted price, it is a later quote that
    happens to agree with it. A book that does not move for an hour produces
    several such rows, so "the price matches" selects the wrong one routinely
    rather than rarely.

    `published_at` is the publication instant: the edge's own column when it has
    one, and the immutable snapshot instant otherwise. It is never later than the
    effective forecast lock, so a quote at or before it is also strictly before
    the cutoff — the publish side of `CLV_return` cannot come from inside the
    window the closing side is measured over.

    Historical edges have no such link and are not given one. Fabricating it —
    "find the row whose price matches" — invents the record R-07 and §4 item 12
    exist to require, and would be indistinguishable from the real thing
    afterwards. They stay unscored, which is a coverage fact reported under R-05.
    """
    if not quote:
        return None, ("no source quote is linked to odds_at_publish, so the "
                      "publish side of CLV_return is an assertion rather than a "
                      "record (§4 item 12)")
    if quote.get("fighter_id") != bet_fighter_id:
        return None, (f"the linked publish quote prices fighter "
                      f"{quote.get('fighter_id')!r}, not the bet fighter "
                      f"{bet_fighter_id!r}")
    if quote.get("opponent_fighter_id") != opp_fighter_id:
        return None, (f"the linked publish quote names opponent "
                      f"{quote.get('opponent_fighter_id')!r}; this fight's other "
                      f"corner is {opp_fighter_id!r} (Q-10)")
    if quote.get("american_odds") != edge.get("odds_at_publish"):
        return None, (f"the linked publish quote offers "
                      f"{quote.get('american_odds')!r} and the edge posted "
                      f"{edge.get('odds_at_publish')!r}; the link does not prove "
                      f"the price that was published")
    if not credible_capture_instant(quote.get("captured_at"), now):
        return None, ("the linked publish quote's capture instant is not credible "
                      "(R-13), so it cannot place the posted price in time")
    if published_at is None:
        return None, ("no publication instant can be established, so the linked "
                      "quote cannot be shown to have existed when the price was "
                      "posted")
    if quote["captured_at"] > published_at:
        return None, (f"the linked publish quote was captured at "
                      f"{quote['captured_at'].isoformat()}, AFTER the edge was "
                      f"published at {published_at.isoformat()}. It cannot be "
                      f"the source of a price posted before it existed — a "
                      f"matching price is not a source (§4 item 12)")
    missing = missing_quote_provenance(quote, REQUIRED_PUBLISH_PROVENANCE)
    if missing:
        return None, (f"the linked publish quote is missing required §4 "
                      f"provenance: {', '.join(missing)}")
    return {
        "quote_id": quote.get("id"),
        "american_odds": quote.get("american_odds"),
        "captured_at": quote.get("captured_at"),
        "provider_market_id": quote.get("source_event_id"),
        "opponent_fighter_id": quote.get("opponent_fighter_id"),
        "feed_version": quote.get("feed_version"),
        "provider_last_update": quote.get("provider_last_update"),
        "retrieved_at": quote.get("retrieved_at"),
    }, None


# ---------------------------------------------------------------------------
# Write-once settlement — Amendment 7
# ---------------------------------------------------------------------------
# The persisted result fields, paired with the key `score_row` returns them
# under. This list IS the contract: a field stored at first scoring is a field
# every later run must find unchanged, so adding a persisted column without
# adding it here would create a field nobody ever checks again.
#
# `clv_scored_at` is deliberately ABSENT. It records when the row was first
# scored, it is never rewritten, and comparing it to "now" on a re-run would
# fail every time.
VERIFIED_FIELDS = (
    ("clv_protocol_version", "protocol_version"),
    ("clv_return", "clv_return"),
    ("closing_fair_probability", "closing_fair_probability"),
    ("closing_book_count", "closing_book_count"),
    ("clv_source_quote_ids", "quote_ids"),
    ("clv_consensus_sha256", "consensus_sha256"),
    ("clv_close_basis", "close_basis"),
    ("clv_lead_time_minutes", "lead_time_minutes"),
    ("clv_lead_time_is_lower_bound", "lead_time_is_lower_bound"),
    ("clv_proxy_quoted_at", "proxy_quoted_at"),
    ("clv_cutoff_at", "cutoff_at"),
    ("clv_publish_quote_id", "publish_quote_id"),
)

# How close two numbers must be to count as the same stored value. The writer
# rounds clv_return and the fair probability to 10 places and the lead time to
# 4, and Postgres `numeric` round-trips as a decimal string, so an exact float
# comparison would report drift that is only formatting.
NUMERIC_TOLERANCE = 1e-9


def _as_number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _same_value(stored, recomputed) -> bool:
    if stored is None or recomputed is None:
        return stored is None and recomputed is None
    if isinstance(stored, dt.datetime) and isinstance(recomputed, dt.datetime):
        return abs((stored - recomputed).total_seconds()) < 1e-6
    if isinstance(stored, (list, tuple)) or isinstance(recomputed, (list, tuple)):
        return list(stored or []) == list(recomputed or [])
    if isinstance(stored, bool) or isinstance(recomputed, bool):
        return bool(stored) == bool(recomputed)
    a, b = _as_number(stored), _as_number(recomputed)
    if a is not None and b is not None:
        return abs(a - b) <= NUMERIC_TOLERANCE * max(1.0, abs(a), abs(b))
    return str(stored) == str(recomputed)


def has_clv001_score(stored: dict) -> bool:
    """Does this `model_edges` row already carry a CLV-001 result?

    `clv_scored_at` is the marker rather than `clv_return`, because it is set on
    exactly the rows the writer has written and on no others. Keying off
    `clv_return` would read a NULL return as "never scored" and re-score it.
    """
    return bool(stored) and stored.get("clv_scored_at") is not None


def verify_against_stored(result: dict, stored: dict) -> list:
    """Compare a fresh scoring against the row already on file.

    Returns a list of human-readable disagreements — empty means the stored row
    reproduces exactly. It NEVER returns a patch and never suggests one: the
    only two outcomes a caller may act on are "unchanged, write nothing" and
    "changed, stop and say so".

    Why this is not a refresh. The protocol says observations scored under a
    version are never retroactively reinterpreted or overwritten, and a settler
    that re-PATCHes on every run breaks that quietly: the second run sees later
    database state — a quote inserted since, a corrected completion, a
    reschedule — and rewrites a number that was supposed to be the record of
    what we measured at the time. Nothing in the row would show it had moved.

    So drift is an ALARM, not an update. Three things can cause it, and all
    three are worth stopping for:

      1. the evidence changed after the fact (which R-01's triggers now make
         very hard, and which is exactly what they exist to surface);
      2. the scorer changed without a version bump;
      3. the stored artifact was edited directly.

    A fourth is possible and is not misconduct: a float that does not survive
    the jsonb round-trip bit for bit. It would still stop the run, and that is
    the right default — the failure mode of this check is "a human looks", never
    "the row is quietly rewritten". If it ever fires for that reason, the fix is
    to make the artifact's serialisation exact, not to relax the comparison.
    """
    problems = []
    if not has_clv001_score(stored):
        return ["the row carries no CLV-001 score to verify"]

    stored_version = stored.get("clv_protocol_version")
    if stored_version != PROTOCOL_TAG:
        # Not drift — a row from another version, which this version may not
        # touch at all. Reported separately by the caller.
        return [f"stored under {stored_version!r}, and this is {PROTOCOL_TAG}. "
                f"A row scored under one version is never re-scored under "
                f"another; it is left exactly as it is."]

    if not result.get("scored"):
        return [f"the row is scored on file but no longer scores: "
                f"{result.get('reason')} — {result.get('detail')}"]

    live = dict(result)
    live["protocol_version"] = PROTOCOL_TAG
    live["publish_quote_id"] = (result.get("publish_quote") or {}).get("quote_id")

    for column, key in VERIFIED_FIELDS:
        if not _same_value(stored.get(column), live.get(key)):
            problems.append(f"{column}: stored {stored.get(column)!r}, "
                            f"recomputed {live.get(key)!r}")

    # The artifact is checked against its OWN hash as well as against the fresh
    # one. A stored artifact edited in place would otherwise reproduce the
    # comparison above — the recomputed hash matches the recomputed artifact,
    # and nothing would look at the jsonb actually on the row.
    artifact = stored.get("clv_closing_consensus")
    if artifact is not None:
        rehashed = canonical_sha256(artifact)
        if rehashed != stored.get("clv_consensus_sha256"):
            problems.append(
                f"clv_closing_consensus no longer hashes to its own "
                f"clv_consensus_sha256 (stored hash "
                f"{stored.get('clv_consensus_sha256')!r}, artifact hashes to "
                f"{rehashed!r}) — the stored artifact was edited after it was "
                f"written")
    return problems


def admissible_reference(start_at: dt.datetime | None,
                         start_basis: str | None,
                         is_first_bout: bool | None = None) -> dt.datetime | None:
    """The close reference for one fight, or None if what we hold is not one.

    Amendment 3. Returns the instant at which this fight began, by the best
    available account of it. Everything strictly before it and inside the
    staleness limit is eligible to be the close; everything at or after it is a
    quote taken once the fight was under way and is excluded.

    The guard this function exists for: a start-time view ALWAYS answers. DUR-001's
    `v_fight_start_best` falls back to the event date at 18:00 UTC, so a caller
    that reads the instant without reading the basis gets a plausible-looking
    schedule for every fight in the database, including fights from 1994. Same
    shape as R-13 — a populated placeholder sailing through a presence check.

    `scheduled_first_bout` additionally requires `is_first_bout` to be TRUE, not
    merely non-false. A card's scheduled start is the first fight's start and
    nobody else's; applying it to the twelfth bout would put the reference five
    hours early and mark every real quote in between as in-play. When the card's
    running order is unknown, `is_first_bout` is None, and that is not a yes.
    """
    if start_at is None or start_basis not in CLOSE_REFERENCE_BASES:
        return None
    if start_basis == "scheduled_first_bout" and is_first_bout is not True:
        return None
    return start_at


def lead_time_minutes(quoted_at: dt.datetime | None,
                      reference_at: dt.datetime | None) -> float | None:
    """Minutes from the proxy quote to the reference instant. None if either is
    missing. Negative is impossible by construction — the quote must be strictly
    before the reference to be eligible at all — but it is not clamped, because
    a negative here would mean an eligibility bug and should be visible."""
    if quoted_at is None or reference_at is None:
        return None
    return (reference_at - quoted_at).total_seconds() / 60.0


def reference_is_lower_bound(start_basis: str | None) -> bool | None:
    """Does this basis's cutoff PRECEDE the bell?

    The recorded lead time is always the exact gap from the selected quote to the
    CUTOFF. This says whether that is also the gap to the fight actually
    starting. Under `previous_bout_completion` it is not — the walkout interval
    sits between them — so the recorded lead time is a lower bound on the true
    distance from the bell, and the row says so rather than implying otherwise.

    None when the basis is unknown, never False: False asserts the cutoff is the
    start, which is a claim we would not have.
    """
    if start_basis in LOWER_BOUND_REFERENCE_BASES:
        return True
    if start_basis in EXACT_REFERENCE_BASES:
        return False
    return None


def score_row(edge: dict, quotes: list[dict], fight: dict,
              reference_instant: dt.datetime | None, now: dt.datetime,
              eligible_book_ids: set[int] | None,
              reference_basis: str | None = None,
              is_first_bout: bool | None = None,
              snapshot: dict | None = None,
              publish_quote: dict | None = None,
              edge_cohort: list | None = None) -> dict:
    """Score one `model_edges` row under CLV-001, or say why it cannot be.

    Returns a dict that is always shaped the same — `scored` is True or False and
    `reason` is None or a member of `UNSCORED_REASONS`. It never returns a
    partially-populated scored row: the database CHECK constraint refuses those,
    because partial provenance is worse than none. It looks reconstructible and
    is not.

    The check order is fixed so the reported reason is deterministic and the
    aggregate counts mean the same thing run to run. Earlier checks are the more
    fundamental obstacle: a row with no posted price cannot be scored no matter
    what the market did.
    """
    out = {"edge_id": edge.get("id"), "fight_id": edge.get("fight_id"),
           "event_date": edge.get("event_date"),
           # The publication floor counts DISTINCT EVENTS. event_date is not a
           # proxy for that: the UFC runs two cards on one date often enough that
           # counting dates would understate the event count and let the 20-event
           # gate open early. Carried from the fight, per event_id.
           "event_id": fight.get("event_id"),
           "scored": False,
           "reason": None, "detail": "", "clv_return": None,
           "closing_fair_probability": None, "closing_book_count": None,
           "quote_ids": None, "consensus": None, "consensus_sha256": None,
           # Which of this version's two bases supplied the pre-fight cutoff, how
           # late the proxy quote was, and whether that lead time is exact or a
           # lower bound. Carried even on an unscored row, so a refusal says what
           # it was asked to score against.
           "close_basis": reference_basis,
           # THE CUTOFF ITSELF, persisted. Amendment 6 (e).
           #
           # It was previously recoverable only for bouts 2..N, where it happens
           # to equal clv_window_opened_at. For bout 1 the cutoff is the card's
           # scheduled start and nothing on the row held it, so the one number
           # every scored observation is defined against was not stored for the
           # only bouts this version can currently score. A lead time plus a
           # basis is not a substitute: reconstructing the cutoff from them
           # re-reads a schedule that may since have moved.
           "cutoff_at": reference_instant,
           "lead_time_minutes": None,
           "lead_time_is_lower_bound": reference_is_lower_bound(reference_basis),
           "proxy_quoted_at": None,
           "forecast_lock": None,
           "publish_quote": None,
           "diagnostics": {}}

    def unscored(reason: str, detail: str = "") -> dict:
        out["reason"], out["detail"] = Unscored(reason, detail).reason, detail
        return out

    # A caller may not hand in a cutoff whose basis this version does not permit.
    # `admissible_reference` is the gate, but a direct `score_row(...,
    # reference_instant=X, reference_basis='bell_at')` would sail past it — so the
    # same rule is enforced here, at the only other way in. This version permits
    # exactly `scheduled_first_bout` and `previous_bout_completion`.
    if reference_instant is not None and reference_basis not in CLOSE_REFERENCE_BASES:
        return unscored(
            "no_scheduled_start",
            f"reference_basis {reference_basis!r} is not a cutoff in "
            f"{PROTOCOL_TAG}. This version permits exactly "
            f"{sorted(CLOSE_REFERENCE_BASES)}; `bell_at` is audit-only and "
            f"scoring against a confirmed bell requires a new protocol version "
            f"(Amendment 5.1).")
    if (reference_instant is not None
            and reference_basis == "scheduled_first_bout"
            and is_first_bout is not True):
        return unscored(
            "no_scheduled_start",
            "the card's scheduled start is the FIRST bout's cutoff only; this "
            "fight is not identified as bout 1 (Amendment 3)")

    if eligible_book_ids is None:
        return unscored("eligible_book_list_not_frozen",
                        "Q-02 requires a fixed named sportsbook list frozen at "
                        "protocol freeze; protocol.json carries none")
    if edge.get("odds_at_publish") is None:
        return unscored("no_publish_price", "odds_at_publish is null")

    # Q-10, the half of it the captured data supports. Provider market IDs are
    # not stored, so a reposted market cannot be matched mechanically; fighter
    # identity can be, and a bet fighter who is no longer in the fight means the
    # market now prices a different fight from the one the forecast was made on.
    bet_fighter_id = edge.get("bet_fighter_id")
    corners = {fight.get("fighter_a_id"), fight.get("fighter_b_id")}
    if bet_fighter_id not in corners:
        return unscored("bet_fighter_not_in_fight",
                        f"fighter {bet_fighter_id} is not a corner of fight "
                        f"{edge.get('fight_id')} today (Q-10)")
    opp_fighter_id = next(iter(corners - {bet_fighter_id}), None)
    if opp_fighter_id is None:
        return unscored("one_sided_close", "the fight has no recorded opponent")

    if reference_instant is None:
        if reference_basis in NON_SCORING_REFERENCE_BASES:
            # The card's scheduled start applied to a later bout: hours early, so
            # the proxy would mean something different on every fight of the card
            # (Amendment 4.1). The snapshots are kept regardless.
            return unscored(
                "only_pre_card_price",
                "the only instant on file for this fight is the card's scheduled "
                "start, which on a later bout is hours before it began. Not a "
                "consistent cutoff, so it is not scored (Amendment 4.1). The "
                "snapshots are kept.")
        if is_first_bout is False:
            # Amendment 5's cutoff for bouts 2..N is the previous bout's exact
            # completion, and it is simply not recorded for this fight yet.
            return unscored(
                "no_previous_bout_completion",
                "this is not the card's first bout, so the cutoff is the exact "
                "completion of the bout before it (Amendment 5) — and no such "
                "completion is on file. Recording one makes the snapshots "
                "already captured scorable.")
        return unscored("no_scheduled_start",
                        "no cutoff for this fight: this version's cutoff is the "
                        "card's scheduled start (bout 1) or the previous bout's "
                        "exact completion (bouts 2..N), and neither is on file. "
                        "A confirmed bell is audit-only and cannot supply one "
                        "(Amendments 3, 5, 5.1)")

    # R-07, no-lookahead — and it starts with establishing the lock from an
    # IMMUTABLE record, because a lock read off a rewritable row is not one.
    try:
        locked_at, lock_info = forecast_lock(edge, snapshot, edge_cohort)
    except Unscored as e:
        return unscored(e.reason, e.detail)
    out["forecast_lock"] = lock_info

    # The edge-level half of R-07: a forecast locked at or after the cutoff has
    # no pre-cutoff window at all. The per-quote half is enforced inside
    # closing_pairs, and it is the half that actually bites — this one only
    # catches the degenerate case.
    if locked_at >= reference_instant:
        return unscored("forecast_not_before_close",
                        f"the forecast was locked at {locked_at.isoformat()}, "
                        f"which is not before the cutoff "
                        f"{reference_instant.isoformat()}")

    # §4 item 12. The publish side of CLV_return must be a record.
    #
    # THE BOUND ON THE PUBLISH QUOTE: the immutable edge instant, and the
    # mutable `published_at` only when it is EARLIER.
    #
    # The immutable side is `edge_published_at` when the snapshot carries it, and
    # `snapshot_at` as the conservative fallback otherwise — the same instant the
    # lock uses, never `engine_published_at`.
    #
    # Why the mutable column may only tighten this. The lock takes the LATER of
    # the two, because a later lock can only shrink the closing window. Here the
    # comparison runs the other way — a quote must be at or before publication —
    # so the later instant is the permissive one, and a `published_at` edited
    # forwards would admit a quote captured after the real publication. Taking
    # the earlier makes an edit in either direction cost rows rather than admit
    # them, which is the same asymmetry read from the other end.
    published_at = min(t for t in (edge.get("published_at"),
                                   lock_info["immutable_locked_at"])
                       if t is not None)
    publish_info, publish_detail = verify_publish_quote(
        publish_quote, edge, bet_fighter_id, opp_fighter_id, now, published_at)
    if publish_info is None:
        return unscored("no_publish_quote_link", publish_detail)
    out["publish_quote"] = publish_info

    pairs, diag = closing_pairs(quotes, bet_fighter_id, opp_fighter_id,
                                reference_instant, now, eligible_book_ids,
                                forecast_locked_at=locked_at,
                                publish_market_id=publish_info["provider_market_id"])
    out["diagnostics"] = diag

    if not pairs:
        # Structural obstacles first, and deliberately ahead of one_sided_close.
        # Dropping one corner of a book for missing provenance leaves the book
        # one-sided, so reporting one_sided_close first would name the symptom
        # and hide the cause — and the cause here is permanent, while a genuine
        # one-sided close may be fixed by the next capture.
        if diag["missing_provenance"]:
            return unscored(
                "incomplete_quote_provenance",
                f"{diag['missing_provenance']} quote(s) in the window are missing "
                f"required §4 provenance ({', '.join(REQUIRED_QUOTE_PROVENANCE)}). "
                f"These fields cannot be backfilled, so rows captured before the "
                f"capture migration landed are permanently unscorable — a "
                f"coverage fact under R-05, not a gap to paper over.")
        if diag["opponent_mismatch"] or diag["market_id_mismatch"]:
            return unscored(
                "market_identity_changed",
                f"{diag['opponent_mismatch']} quote(s) name a different opponent "
                f"and {diag['market_id_mismatch']} quote(s) a different provider "
                f"market than the forecast was made on (Q-10, R-06)")
        if diag["before_forecast_lock"]:
            return unscored(
                "forecast_not_before_close",
                f"{diag['before_forecast_lock']} quote(s) in the window are at or "
                f"before the forecast lock {locked_at.isoformat()}. R-07 requires "
                f"forecast_locked_at < close_quoted_at strictly, per quote — a "
                f"price that was on the screen before the forecast existed cannot "
                f"measure the forecast against it.")
        if diag["one_sided_books"]:
            return unscored("one_sided_close",
                            f"{diag['one_sided_books']} eligible book(s) quoted "
                            f"only one corner in the window")
        if diag["stale"] and not diag["implausible_timestamp"]:
            return unscored("stale_close",
                            f"{diag['stale']} quote(s) fell outside the "
                            f"{STALENESS_LIMIT_MINUTES}-minute limit (Q-01b)")
        if diag["implausible_timestamp"]:
            return unscored("implausible_timestamp",
                            f"{diag['implausible_timestamp']} quote(s) carry a "
                            f"capture instant R-13 rejects")
        return unscored("no_closing_quotes",
                        "no quote from an eligible book before the reference "
                        "instant")

    try:
        fair, n_books, artifact = consensus(pairs)
    except Unscored as e:
        return unscored(e.reason, e.detail)

    # The proxy instant is the latest quote that entered the consensus — the
    # "late" in late pre-fight price proxy. Lead time is measured from it, so a
    # thin consensus assembled from older books reports the lead time it
    # actually has rather than the best one in the set.
    proxy_at = max(p["quoted_at"] for p in pairs
                   if p["book_id"] in {b["book_id"] for b in artifact["books"]})
    artifact["proxy_quoted_at"] = proxy_at
    artifact["close_basis"] = reference_basis
    # THE CUTOFF GOES INTO THE HASHED ARTIFACT — Amendment 6 (e).
    #
    # The consensus is a set of prices selected BY a cutoff. Hashing the prices
    # without it leaves the selection rule outside the integrity check: the same
    # books, the same quotes and the same median produce the same hash whether
    # they were selected against a 22:00 cutoff or a 23:00 one, and the artifact
    # cannot then be verified as the calculation that was actually performed.
    artifact["cutoff_at"] = reference_instant
    # The other two ends of the provenance chain, so the hash covers the whole of
    # it: what the forecast was locked against, and what the posted price was.
    artifact["forecast_locked_at"] = locked_at
    artifact["publish_quote_id"] = publish_info["quote_id"]
    artifact["benchmark"] = BENCHMARK_NAME

    out.update({
        "scored": True,
        "clv_return": clv_return(fair, edge["odds_at_publish"]),
        "closing_fair_probability": fair,
        "closing_book_count": n_books,
        "quote_ids": sorted(qid for b in artifact["books"] for qid in b["quote_ids"]),
        "consensus": artifact,
        "consensus_sha256": canonical_sha256(artifact),
        "proxy_quoted_at": proxy_at,
        "cutoff_at": reference_instant,
        "lead_time_minutes": lead_time_minutes(proxy_at, reference_instant),
    })
    return out
