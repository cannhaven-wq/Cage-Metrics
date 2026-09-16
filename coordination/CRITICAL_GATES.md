# Critical gates

Who is allowed to decide what, and the short list of things that stop and wait
for Reed.

The default is **proceed**. This file exists to name the narrow set of
exceptions, not to add ceremony to ordinary work. If a change is revertible,
testable and already inside a written specification, no one needs to ask.

---

## Decision levels

| level | who decides | what it covers |
|---|---|---|
| **L0** | whoever is working | Formatting, tests, docs, debugging, refactors, read-only research. Execute; no announcement needed beyond the commit. |
| **L1** | AI-to-AI | New features, schemas, analytics, research tooling. Claude implements, ChatGPT reviews. Reed is not needed. |
| **L2** | AI, Reed notified | Meaningful but reversible product changes. Proceed, write it into `DECISIONS.md`, and flag it in the next handoff. Stop only if it trips a constraint below. |
| **L3** | **Reed only** | Stop and ask. The list is below and it is closed — see "Adding a gate". |

An AI may **never** record Reed's approval from inference, silence, or a
general prior "go ahead". An L3 entry in [`DECISIONS.md`](DECISIONS.md) quotes
what Reed actually said, or it is not an approval.

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

## The L3 list

Stop and ask Reed for:

1. **Changing a frozen specification or preregistration.** Mechanically blocked
   by `tests/test_research_state.py`; the two legal routes are a dated
   amendment or a new `model_version`. See
   [`CFL_RESEARCH_STATE.md`](../CFL_RESEARCH_STATE.md).
2. **Moving an experiment's lifecycle state** — `draft → frozen → armed →
   collecting` — or recording a verdict.
3. **Merging a major architectural change.**
4. **Applying a production DB migration** with real risk: anything touching
   RLS, triggers on append-only tables, or a column another surface reads.
5. **Spending money or enabling paid infrastructure**, including additional
   Odds API credits.
6. **Changing monetisation, pricing, or any public performance claim.**
7. **Legal or compliance choices**, including anything on `disclaimer.html`.
8. **A statistical decision with more than one defensible path.** Do not pick
   the one that looks better. Write both up and hand them over.
9. **Anything irreversible** by the four-part test above.

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

DUR-001 is collecting and DUR-002 is armed. Until each reaches its predefined
evaluation point, the duration model is not touched by anyone — no calibration
experiments, no threshold exploration, no tuning. Routine operation (locks
written, capture monitored, the alert running) is the experiment running, not
work on the model. Full terms at the top of
[`CFL_RESEARCH_STATE.md`](../CFL_RESEARCH_STATE.md).

---

## Adding a gate

The L3 list is closed to AI edits. Claude and ChatGPT may **propose** a gate by
opening a task in [`TASK_QUEUE.md`](TASK_QUEUE.md) at L3; only Reed adds or
removes one, and the change is logged in [`DECISIONS.md`](DECISIONS.md) like
any other L3 decision.

The failure mode this prevents is gate inflation: an AI that can widen its own
stop list can also narrow it.
