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

## Current status: refusing, by design

No backfill can clear the gate today. The blocker is `TIMING_RULE`: amendment
item (i) puts two candidate historical timing rules to Reed and neither has been
picked. Until one is chosen and marked approved there is no pre-registered
definition of which historical quote is the benchmark, so there is nothing
legitimate to compute.

That is the point. Choosing the rule after seeing which one flatters the result
is exactly the selection the preregistration exists to prevent.

```
$ python research/dur001_backfill/run_backfill.py --check
GATE REFUSED — 3 violation(s):
  [MODEL_VERSION] model_version is empty. ...
  [NO_ROWS] the spec scores no fights. ...
  [TIMING_RULE] no historical timing rule set. Amendment item (i) ...
```

`run_backfill.py` deliberately contains **no scoring code**. Writing the scorer
before the rule is chosen invites running it "just to look", and the looking is
the damage. When item (i) is approved, the scorer goes in that file, behind
`assert_clear`.

## The checks

| code | what it stops |
|---|---|
| `LOCK_TABLE` | writing to `prop_model_locks` |
| `FORBIDDEN_TABLE` | writing to `prop_odds`, `fight_odds`, `pre_fight_snapshots` |
| `DB_WRITE` | any database write at all — a backfill's output is a file |
| `MODEL_VERSION` | an empty version, or reusing the live `PROP-0001@v1` |
| `LEAKY_ROW` | `training_cutoff >= fight_start` on any row, strictly compared |
| `TIMING_RULE` | an unset or non-pre-registrable historical timing rule |
| `TIMING_UNAPPROVED` | a valid rule that nobody has approved yet |
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
