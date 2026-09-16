"""The frozen CLV-001 arithmetic: de-vig, and `CLV_return`.

Pure functions, no database, no I/O. `settle_clv.py` wires them to rows; the
correctness of the numbers lives here and is unit-tested here.

Governed by `research/clv/CLV_MEASUREMENT_PROTOCOL.md`, frozen 2026-09-16.

    CLV_return = closing_fair_probability × decimal_odds_at_publish − 1

Publish side: the **actual posted price**, vigged, exactly as a bettor takes it.
Closing side: **power de-vigged** fair probability (Q-12), median across eligible
books, de-vigged **per book first** and only then median-ed (Q-02 — the order is
not interchangeable; taking the median of vigged prices and de-vigging once
afterwards blends the books' margins together and is a different estimator).

A note on the bisection direction
-----------------------------------------------------------------------------
The formula is `q_over^(1/k) + q_under^(1/k) = 1`, and for it the sum is
strictly **increasing** in `k`: raising `k` lowers the exponent `1/k` and pushes
each `q^(1/k)` toward 1. It is *decreasing* under the other common convention,
`q^k`. The two are exact reparametrisations — the `q^k` root is the reciprocal
of the `q^(1/k)` root — so they yield bit-identical fair probabilities, and both
roots fall inside the `[0.5, 5.0]` bracket.

DUR-001 Amendment 1.1 originally stated the direction the wrong way round. It
was found here, while implementing the formula, and corrected upstream by
**DUR-001 Amendment 2**, which CLV-001 inherits as its **Amendment 1** (v1.0.0 →
v1.0.1). Both amendments record `motivated_by_observed_results: false` and no
de-vigged probability changed; the proposal Reed approved is kept at
`research/clv/AMENDMENT_PROPOSAL_2026-09-16_devig_direction.md`.

`_bisect` stays **direction-agnostic** regardless: it reads the sign at both
bracket ends rather than assuming which way `f` runs. That was written when the
document was wrong, and it is kept now that the document is right — an
implementation that would break if a docstring changed is an implementation
resting on a docstring.
"""
from __future__ import annotations

# The protocol's bracket and tolerance, used verbatim.
K_LO, K_HI = 0.5, 5.0
K_TOL = 1e-10
MAX_ITER = 200

# A real two-way market never prices a side outside this band (R-03).
MIN_MARKET_PROB = 0.03
MAX_MARKET_PROB = 0.97


class DevigError(ValueError):
    """The pair cannot be de-vigged under the frozen rules."""


def american_to_prob(odds: float) -> float:
    """Single-side implied probability, vig intact."""
    odds = float(odds)
    return 100.0 / (odds + 100.0) if odds > 0 else -odds / (-odds + 100.0)


def american_to_decimal(odds: float) -> float:
    """Decimal odds, i.e. total return per unit staked including the stake."""
    odds = float(odds)
    return 1.0 + (odds / 100.0 if odds > 0 else 100.0 / -odds)


def _bisect(f, lo: float, hi: float, tol: float = K_TOL) -> float:
    """Root of `f` in [lo, hi], without assuming which way `f` runs.

    Deliberately direction-agnostic — see the module docstring. `f` is
    continuous and monotone here, so reading the sign at `lo` is enough to know
    which half to keep.
    """
    flo, fhi = f(lo), f(hi)
    if flo == 0.0:
        return lo
    if fhi == 0.0:
        return hi
    if (flo > 0) == (fhi > 0):
        raise DevigError(
            f"no root in [{lo}, {hi}]: f({lo})={flo:+.6f}, f({hi})={fhi:+.6f}. "
            f"The bracket is the protocol's; a pair that escapes it is not a "
            f"two-way market this protocol can score.")
    for _ in range(MAX_ITER):
        mid = (lo + hi) / 2.0
        fm = f(mid)
        if abs(fm) < tol or (hi - lo) < tol:
            return mid
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return (lo + hi) / 2.0


def power_devig(q_a: float, q_b: float) -> tuple[float, float, float]:
    """Frozen primary de-vig (Q-12). Returns (fair_a, fair_b, k).

    Solves `q_a**(1/k) + q_b**(1/k) = 1` on the protocol's [0.5, 5.0] bracket.
    """
    _check_pair(q_a, q_b)
    k = _bisect(lambda k: q_a ** (1.0 / k) + q_b ** (1.0 / k) - 1.0, K_LO, K_HI)
    fair_a, fair_b = q_a ** (1.0 / k), q_b ** (1.0 / k)
    # Renormalise away the last ulps of bisection error so the pair sums to
    # exactly 1. Without this a downstream "fair probabilities sum to one"
    # assertion fails on floating-point dust.
    total = fair_a + fair_b
    return fair_a / total, fair_b / total, k


def proportional_devig(q_a: float, q_b: float) -> tuple[float, float]:
    """Frozen SENSITIVITY only — never the primary (Q-05, Q-12)."""
    _check_pair(q_a, q_b)
    total = q_a + q_b
    return q_a / total, q_b / total


def shin_devig(q_a: float, q_b: float, z_tol: float = 1e-12) -> tuple[float, float, float]:
    """Frozen SENSITIVITY only — never the primary. Returns (fair_a, fair_b, z).

    Shin's model with an insider share `z`. For the two-way case the fair
    probability has a closed form given z, and z solves the normalisation.
    """
    _check_pair(q_a, q_b)
    s = q_a + q_b

    def fair(q: float, z: float) -> float:
        # standard two-outcome Shin inversion
        root = ((z * z + 4.0 * (1.0 - z) * q * q / s) ** 0.5 - z) / (2.0 * (1.0 - z))
        return root

    lo, hi = 0.0, 0.9999
    for _ in range(MAX_ITER):
        z = (lo + hi) / 2.0
        tot = fair(q_a, z) + fair(q_b, z)
        if abs(tot - 1.0) < z_tol:
            break
        if tot > 1.0:
            lo = z
        else:
            hi = z
    fa, fb = fair(q_a, z), fair(q_b, z)
    total = fa + fb
    return fa / total, fb / total, z


def _check_pair(q_a: float, q_b: float) -> None:
    for name, q in (("q_a", q_a), ("q_b", q_b)):
        if q is None:
            raise DevigError(f"{name} is None")
        if not (MIN_MARKET_PROB <= q <= MAX_MARKET_PROB):
            raise DevigError(
                f"{name}={q:.4f} is outside the market band "
                f"[{MIN_MARKET_PROB}, {MAX_MARKET_PROB}] — a pulled, settled or "
                f"sentinel line, not a price anyone could have bet (R-03)")
    if q_a + q_b <= 1.0:
        raise DevigError(
            f"overround is {q_a + q_b:.6f} <= 1. A two-way book quote sums above "
            f"1; at or below it there is no vig to remove and the pair is not a "
            f"coherent market.")


def median(values: list[float]) -> float:
    """Median, lower-of-two on an even count.

    Lower-of-two rather than the mean of the middle pair: the protocol's
    consensus is 'the median book', and averaging two books invents a fair
    probability no book quoted. Deterministic, which matters for a frozen rule.
    """
    if not values:
        raise DevigError("median of an empty set")
    s = sorted(values)
    return s[(len(s) - 1) // 2]


def closing_fair_probability(book_pairs: list[tuple[float, float]],
                             min_books: int = 3) -> tuple[float, int]:
    """Consensus closing fair probability for side A. Returns (fair_a, n_books).

    `book_pairs` is one `(q_a, q_b)` vigged pair per eligible book, both sides
    from the SAME book at the close. De-vig each book separately, then take the
    median of the per-book fair probabilities (Q-02).

    Books that fail the band or overround checks are dropped; if fewer than
    `min_books` survive, the observation is unscored rather than scored on thin
    evidence (Q-02, R-05).
    """
    fair = []
    for q_a, q_b in book_pairs:
        try:
            fa, _, _ = power_devig(q_a, q_b)
        except DevigError:
            continue                      # dropped, and counted by the caller
        fair.append(fa)
    if len(fair) < min_books:
        raise DevigError(
            f"only {len(fair)} eligible book(s) survived de-vig; the frozen "
            f"minimum is {min_books} (Q-02). Unscored, and counted as such.")
    return median(fair), len(fair)


def clv_return(closing_fair_prob: float, odds_at_publish: float) -> float:
    """The frozen primary measure.

        CLV_return = closing_fair_probability × decimal_odds_at_publish − 1

    Expected return per unit staked at the price CFL actually posted, evaluated
    against the market's de-vigged closing fair probability.

    **Conservative by construction.** The publish side keeps the book's margin,
    so the bar is fair-close > *vigged* implied at publish. Zero means exactly
    fair closing value after paying the posted price — not "no edge either way".
    Never describe it as a fair-versus-fair comparison.
    """
    if closing_fair_prob is None or odds_at_publish is None:
        raise DevigError("clv_return needs both a closing fair probability and a "
                         "published price")
    if not (0.0 < closing_fair_prob < 1.0):
        raise DevigError(f"closing_fair_prob={closing_fair_prob} is not a probability")
    return closing_fair_prob * american_to_decimal(odds_at_publish) - 1.0
