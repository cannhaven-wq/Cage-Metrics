# Critical gates

Who is allowed to decide what, and the short list of things that stop and wait
for the owner.

The default is **proceed**. This file exists to name the narrow set of
exceptions, not to add ceremony to ordinary work. If a change is revertible,
testable and already inside a written specification, no one needs to ask.

---

## Decision levels

| level | who decides | what it covers |
|---|---|---|
| **L0** | whoever is working | Formatting, tests, docs, debugging, refactors, read-only research. Execute; no announcement needed beyond the commit. |
| **L1** | AI-to-AI | New features, schemas, analytics, research tooling. Claude implements, ChatGPT reviews. the owner is not needed. |
| **L2** | AI, owner notified | Meaningful but reversible product changes. Proceed, write it into `DECISIONS.md`, and flag it in the next handoff. Stop only if it trips a constraint below. |
| **L3** | **Owner only** | Stop and ask. The list is below and it is closed — see "Adding a gate". |

An AI may **never** record the owner's approval from inference, silence, or a
general prior "go ahead". An L3 entry in [`DECISIONS.md`](DECISIONS.md) quotes
what the owner actually said, or it is not an approval.

---

## What "reversible" means here

The default rule — *if reversible, testable and within spec, proceed* — only
works if "reversible" is defined, and in this repo the obvious reading is
wrong. `git revert` does not undo everything.

A change is reversible **only if all four hold**:

1. it is revertible in git;
2. it writes **no row** to an append-only table — `prop_model_locks`,
   `pre_fight_snapshots`, `model_picks`. Those reject UPDATE and DELETE by
   trigger for every role including `service_role`. A row written in error
   stays written;
3. it publishes **no public claim** — site copy, a post, an email, a number on
   a live surface. A retraction is not a reversal;
4. it changes **no frozen file**, and starts **no observation** under a frozen
   preregistration.

Fail any one of those and it is at least L2, and probably L3.

---

## The test: discretion, not consequence

L3 is for decisions that require **judgement**. A step can be consequential and
still not be L3, if what to do is already written down and a machine can check
that it was done right.

> A transition that is fully prescribed and machine-verifiable is not a
> decision. It is execution, and it executes.

Stopping on those does not add safety — it adds a queue. The thing that makes
them safe is the specification and the test, both of which exist whether or not
a person is watching.

## The L3 list

Stop and ask the owner for:

1. **Changing a frozen specification or preregistration.** Mechanically blocked
   by `tests/test_research_state.py`; the two legal routes are a dated
   amendment or a new `model_version`. See
   [`CFL_RESEARCH_STATE.md`](../CFL_RESEARCH_STATE.md).
2. **An amendment motivated by new evidence.** The amendment procedure is
   the owner's to invoke, and `motivated_by_observed_results` must be recorded
   `false` *and be true*.
3. **Recording a verdict** on an experiment. A verdict is a judgement about
   what the evidence means, which is the definition of discretion.
4. **Merging a major architectural change.**
5. **Applying a production or destructive DB migration**: anything touching
   RLS, triggers on append-only tables, a column another surface reads, or any
   `DROP` / `DELETE` / destructive `UPDATE`.
6. **Spending money or enabling paid infrastructure**, including additional
   Odds API credits.
7. **Changing monetisation, pricing, or payments.**
8. **Any public performance claim** — a new number on a surface, or a change to
   how an existing one is described.
9. **Legal or compliance choices**, including anything on `disclaimer.html`.
10. **A statistical decision with more than one defensible path.** Do not pick
    the one that looks better. Write the options up and hand them over.
11. **Anything materially irreversible** by the four-part test above.

## What is *not* L3

**Routine lifecycle transitions.** `draft → frozen → armed → collecting`
executes automatically when every frozen prerequisite passes. Record the
transition and its provenance; do not stop for the owner.

The worked case is DUR-002's `armed → collecting`. Every step is already
prescribed in [`CFL_RESEARCH_STATE.md`](../CFL_RESEARCH_STATE.md) — record the
first-lock UTC timestamp, the workflow run id and commit SHA,
`lock_prop0002.py`'s sha256 and the row count; set `lock_script.frozen = true`;
move the script into DUR-002's frozen files; rerun the guards. And every step is
already checked by `tests/test_research_state.py`:

| prerequisite | enforced by |
|---|---|
| `armed` implies zero observations | `test_armed_means_zero_observations` |
| `collecting` implies observations recorded | `test_collecting_means_observations_are_recorded` |
| the lock script is frozen at first collection | `test_an_unfrozen_lock_script_means_not_yet_collecting` |
| frozen files still match their bytes on disk | `test_registry_hashes_match_disk` |
| the two registries agree | `test_every_registry_frozen_file_is_in_the_markdown_table` |

There is no judgement left in it. A human approval step there approves nothing;
it just delays the record of an event that already happened.

**The limit.** This covers transitions whose preconditions are written down
*and* checkable. A transition that needs someone to decide whether a condition
is met is not prescribed, and is L3 under item 10. If a guard fails, the
transition does not happen and does not get forced — a failing guard is a stop,
and working around one is itself an L3 change.

### The standing prohibition

> Neither AI may modify a frozen statistical specification because a new result
> looks better.

This is a rule about motive, and motive is not checkable, so the repo does not
rely on it alone. Every amendment records
`motivated_by_observed_results: false` in `research/registry.json`, the hashes
must chain from the freeze to what is on disk, and the preregistration's own
`## Amendments` section must carry the same date. The test fails if the
paperwork and the bytes disagree. The rule above is the reason those checks
exist; the checks are what actually holds.

### The duration model is read-only

DUR-001 and DUR-002 are both collecting. Until each reaches its predefined
evaluation point, the duration model is not touched by anyone — no calibration
experiments, no threshold exploration, no tuning. Routine operation (locks
written, capture monitored, the alert running) is the experiment running, not
work on the model. Full terms at the top of
[`CFL_RESEARCH_STATE.md`](../CFL_RESEARCH_STATE.md).

---

## Adding a gate

The L3 list is closed to AI edits. Claude and ChatGPT may **propose** a gate by
opening a task in [`TASK_QUEUE.md`](TASK_QUEUE.md) at L3; only the owner adds or
removes one, and the change is logged in [`DECISIONS.md`](DECISIONS.md) like
any other L3 decision.

The failure mode this prevents is gate inflation: an AI that can widen its own
stop list can also narrow it.
