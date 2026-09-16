# DUR-001 historical backfill — spec-gated

A tool that refuses to run a historical backfill until the preregistration says
it may.

## Why a gate

`PREREGISTRATION.md` §13 is three conditions in one sentence:

> A historical backfill, if ever attempted, must be walk-forward with
> `training_cutoff < fight_start`, carry a distinct `model_version`, and never
> be written to `prop_model_locks`.

A backfill is the easiest way to destroy DUR-001. Score the frozen model on
fights whose outcomes are already inside its training data and you get a number
that looks excellent and means nothing. If that number ever reaches
`prop_model_locks`, the ledger stops being a record of what was predicted in
advance — which is the only property it has.

So the conditions are code, not prose, and they run before any work happens.

## Current status: the timing rule is frozen; the gate still refuses loosely-specified runs

**Preregistration Amendment 1.2 (2026-09-16) froze the historical timing rule**
to `t10_earliest_observed_start` — T−10 before the earliest provider start ever
observed, with moved starts flagged and retained. Item (i) is decided.

The rejected candidate, `self_consistent_walkback`, is **not** retained as a
sensitivity. It excluded fights that had no self-consistent snapshot, which
conditions the cohort on events occurring after the sampling decision. It now
earns its own `TIMING_REJECTED` refusal, and asserting `timing_rule_approved`
cannot buy past it — otherwise "approval" would become the very re-decision the
amendment removed.

A backfill can now clear the gate, but only by naming the frozen rule
explicitly and satisfying every other §13 condition. Frozen does not mean
defaulted into: a spec that leaves `timing_rule` unset is still refused.

```
$ python research/dur001_backfill/run_backfill.py --check
GATE REFUSED — 3 violation(s):
  [MODEL_VERSION] model_version is empty. ...
  [NO_ROWS] the spec scores no fights. ...
  [TIMING_RULE] no historical timing rule set. Preregistration amendment 1.2 ...
```

`run_backfill.py` still contains **no scoring code**. Item (i) is settled, but
the walk-forward fold discrepancy is not, and Reed has held every amendment
clause that touches calibration or scoring until it is. The scorer goes in that
file, behind `assert_clear`, once that is closed.

## The checks

| code | what it stops |
|---|---|
| `LOCK_TABLE` | writing to `prop_model_locks` |
| `FORBIDDEN_TABLE` | writing to `prop_odds`, `fight_odds`, `pre_fight_snapshots` |
| `DB_WRITE` | any database write at all — a backfill's output is a file |
| `MODEL_VERSION` | an empty version, or reusing the live `PROP-0001@v1` |
| `LEAKY_ROW` | `training_cutoff >= fight_start` on any row, strictly compared |
| `TIMING_RULE` | an unset rule, or one that is not the rule Amendment 1.2 froze |
| `TIMING_REJECTED` | the candidate Amendment 1.2 rejected — refused even if marked approved |
| `TIMING_UNAPPROVED` | the frozen rule, but the spec does not assert it is running under 1.2 |
| `ODDS_API` | spending live Odds API credits on historical work |
| `NO_ROWS` | running an empty backfill that produces a result-shaped artifact |

`check()` returns **all** violations, not the first — someone fixing a spec
should see the whole list rather than peel them off one run at a time.

### The one that matters most

`LEAKY_ROW` compares **strictly** and **per row**. A cutoff equal to the fight's
start still lets that fight's own result into the training set on a
same-timestamp boundary, and a spec that holds on average but fails on nine
fights is not walk-forward.

## Layout

```
spec.py       BackfillSpec / BackfillRow, the constants, SpecViolation
gate.py       check() / assert_clear() / is_clear() / explain()
run_backfill.py   CLI; --check reports, and currently refuses
tests/        29 tests
```

```
python -m unittest discover -s research/dur001_backfill/tests
```

Defaults refuse. `BackfillSpec()` with no arguments fails the gate rather than
being permissive — there is a test for that.

## If the gate blocks something you believe is correct

Change the backfill, or get the preregistration amended. Do not edit the gate.
A gate that is edited to let a specific run through is not a gate.
