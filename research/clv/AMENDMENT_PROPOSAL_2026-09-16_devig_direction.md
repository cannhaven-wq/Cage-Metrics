# CLV-001 amendment proposal — de-vig bisection direction

**Status: PROPOSED — not in force. Needs Reed's approval.**
**Raised:** 2026-09-16, hours after the freeze, while implementing §1.1.
**Severity:** documentation only. **No number changes.**
**Protocol version affected:** `1.0.0`, frozen 2026-09-16T10:30:00Z.

---

## The defect

§6 / Amendment 1.1 specifies the power de-vig as:

> solve for the single exponent `k > 0` satisfying
> `q_over^(1/k) + q_under^(1/k) = 1`
> … Solved by bisection on `k` over `[0.5, 5.0]` to a tolerance of 1e-10;
> **the sum is strictly decreasing in `k`**, so the root is unique.

**For the formula as written, the sum is strictly *increasing* in `k`.**

For `0 < q < 1`, raising `k` lowers the exponent `1/k` toward zero, which pushes
`q^(1/k)` *up* toward 1. Measured on a typical pair (`q_a = 0.55`, `q_b = 0.52`,
overround 1.07):

| `k` | `q_a^(1/k) + q_b^(1/k) − 1` |
|---|---|
| 0.5 | −0.4271 |
| 0.75 | −0.1312 |
| 1.0 | +0.0700 |
| 2.0 | +0.4627 |
| 5.0 | +0.7647 |

Monotone increasing. The claim is true only of the *other* common convention,
`q^k`, where raising `k` shrinks each side and the sum falls.

## Why no number changes

The two conventions are **exact reparametrisations of each other**: the `q^k`
root is the reciprocal of the `q^(1/k)` root, so they produce bit-identical fair
probabilities. Verified on three pairs:

| pair | `q^(1/k)` root | `q^k` root | `1/k` | fair_a, both ways |
|---|---|---|---|---|
| (0.55, 0.52) | 0.902328 | 1.108245 | 1.108245 | 0.5155352112 |
| (0.70, 0.35) | 0.922810 | 1.083647 | 1.083647 | 0.6794241586 |
| (0.48, 0.58) | 0.915341 | 1.092489 | 1.092489 | 0.4484971366 |

Both roots also fall inside the protocol's `[0.5, 5.0]` bracket, so the bracket
is correct as written for either convention. **Nothing about the measured CLV is
affected, now or retrospectively.**

## Why it still matters

An implementer who trusted the stated direction would write the bisection's sign
test the wrong way round and either converge on a bracket edge or fail to
converge. The claim is exactly the kind a reader takes on trust, because it reads
like a justification for uniqueness rather than a fact to re-derive.

It is also a false mathematical statement inside a document whose entire value is
that its statements can be relied on without re-checking.

## Proposed amendment

Replace, in §6 / Amendment 1.1:

> the sum is strictly decreasing in `k`, so the root is unique

with:

> the sum is strictly **increasing** in `k` — raising `k` lowers the exponent
> `1/k` and pushes each `q^(1/k)` toward 1 — so the root is unique. (Under the
> equivalent `q^k` parameterisation the sum decreases and the root is the
> reciprocal; the fair probabilities are identical either way.)

Nothing else changes: same formula, same bracket, same tolerance, same numbers.

## What the implementation does meanwhile

`cfl_engine/clv/devig.py` **does not rely on the claim at all.** `_bisect` reads
the sign at both bracket ends and keeps the half that brackets the root, which is
correct under either convention and would survive the claim being corrected in
either direction.

Two tests pin this:

- `test_the_two_conventions_agree_exactly` — the reparametrisation, so the
  defect stays numerically inert;
- `test_the_stated_direction_is_the_wrong_one` — asserts the sum *increases*,
  and is written to start failing if the protocol's claim ever becomes true, at
  which point this proposal and the module's note can both be deleted.

## Why this is a proposal and not a fix

The protocol was frozen a few hours before this was found. Its own change routes
are a dated amendment recorded with both hashes and a reason, or a new version.
Quietly correcting a frozen document — even to fix something that changes no
number — is the precise habit the freeze exists to prevent, and it would be
indistinguishable afterwards from quietly correcting something that *did*.

`motivated_by_observed_results`: **false.** This was found by implementing the
formula, not by looking at any CLV figure. No CLV figure exists.

## If approved

1. Amend §6 / Amendment 1.1 as above.
2. Record the amendment with `sha256_before` / `sha256_after` in
   `protocol.json`, chaining from `ef912fcea18b560476755e797d2e5001832a4ba2230fe8daf368544bb61aba1a`.
3. Bump the protocol to `1.0.1`.
4. Delete the note in `devig.py` and the second test above.
