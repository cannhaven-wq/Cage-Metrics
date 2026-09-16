"""CLV-001 row scoring: which quotes are eligible, and what a row scores.

Pure functions over plain dicts. No database, no network, no clock of its own —
`now` is always passed in. `settle_clv.py` fetches rows and hands them here; the
rules live here and are unit-tested here (`test_scoring.py`).

Governed by `research/clv/CLV_MEASUREMENT_PROTOCOL.md` (CLV-001, frozen
2026-09-16). Every constant below traces to a resolved question or a
decided rule, named in the comment beside it. Nothing here is tunable.

The order of operations is the part that is easy to get wrong, so it is fixed:

    eligible quotes  ->  per-book two-sided pairs  ->  de-vig EACH book
                     ->  median of the per-book fair probabilities
                     ->  CLV_return against the posted price

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
PROTOCOL_VERSION = "1.0.8"
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
                  eligible_book_ids: set[int]) -> tuple[list[dict], dict]:
    """The scheduled-close proxy (Q-01), per book, both corners.

    For each eligible book, take its latest quote per corner that is strictly
    before `reference_instant`, has a credible capture instant (R-13) and is
    within the staleness limit (Q-01b). A book contributes a pair only if BOTH
    corners survive; a book quoting one side is not a two-way market and cannot
    be de-vigged.

    Returns `(pairs, diagnostics)`. `pairs` is one dict per contributing book,
    already ordered by book id so the artifact is deterministic. `diagnostics`
    counts why the others dropped out, which is what distinguishes
    `one_sided_close` from `stale_close` from `implausible_timestamp` when the
    row ends up unscored.

    This never raises: it reports. The caller decides what the counts mean.
    """
    diag = {"seen": 0, "ineligible_book": 0, "after_reference": 0,
            "implausible_timestamp": 0, "stale": 0, "one_sided_books": 0,
            "wrong_fighter": 0}
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
        if at >= reference_instant:
            diag["after_reference"] += 1      # Q-01: strictly before, and R-03
            continue
        if at < cutoff:
            diag["stale"] += 1
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
              is_first_bout: bool | None = None) -> dict:
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
           "event_date": edge.get("event_date"), "scored": False,
           "reason": None, "detail": "", "clv_return": None,
           "closing_fair_probability": None, "closing_book_count": None,
           "quote_ids": None, "consensus": None, "consensus_sha256": None,
           # Amendment 4: which tier supplied the pre-fight cutoff, how late the
           # proxy quote was, and whether that lead time is exact or a bound.
           "close_basis": reference_basis,
           "lead_time_minutes": None,
           "lead_time_is_lower_bound": reference_is_lower_bound(reference_basis),
           "proxy_quoted_at": None,
           "diagnostics": {}}

    def unscored(reason: str, detail: str = "") -> dict:
        out["reason"], out["detail"] = Unscored(reason, detail).reason, detail
        return out

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
                        "no cutoff for this fight: needs the card's scheduled "
                        "start (bout 1), the previous bout's exact completion "
                        "(bouts 2..N), or a confirmed bell (Amendments 3, 5)")

    # R-07, no-lookahead. Strict, in UTC.
    published_at = edge.get("published_at")
    if published_at is not None and published_at >= reference_instant:
        return unscored("forecast_not_before_close",
                        f"published_at {published_at.isoformat()} is not before "
                        f"the close reference {reference_instant.isoformat()}")

    pairs, diag = closing_pairs(quotes, bet_fighter_id, opp_fighter_id,
                                reference_instant, now, eligible_book_ids)
    out["diagnostics"] = diag

    if not pairs:
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
        "lead_time_minutes": lead_time_minutes(proxy_at, reference_instant),
    })
    return out
