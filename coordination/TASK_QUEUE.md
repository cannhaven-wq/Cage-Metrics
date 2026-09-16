# Task queue

What is queued, who owns it, and what level it sits at. One row per task.

**Levels** are defined in [`CRITICAL_GATES.md`](CRITICAL_GATES.md): `L0`
execute, `L1` AI-to-AI, `L2` proceed and notify, `L3` owner only.
**Owners**: `Claude` (build), `ChatGPT` (spec / review), `Owner` (Reed Cannon, per CLAUDE.md).
**Status**: `proposed`, `queued`, `in-progress`, `blocked`, `done`, `dropped`.

An `L3` task cannot be marked `done` until [`DECISIONS.md`](DECISIONS.md)
records the decision against its id. `tests/test_coordination.py` enforces it.

Ids are never reused. A task that dies is `dropped`, not deleted — the reason
it died is usually worth more than the task was.

---

## Open

| id | task | level | owner | status |
|---|---|---|---|---|
| T-001 | Automate DUR-002's `armed → collecting` transition, guard-gated, with provenance recorded | L1 | Claude | queued |
| T-002 | Individual votes on the nine held amendment clauses — (a) (b) (c) (d) (e) (f) (g) (j) (k) | L3 | Owner | blocked |
| T-003 | Review the CLV measurement protocol draft before freeze | L1 | ChatGPT | in-progress |
| T-004 | Collapse the `picks.html` → `card-lab.html` → `/` redirect to a single hop | L1 | Claude | queued |
| T-006 | Two-sided quote capture at the publish instant | L1 | Claude | queued |
| T-007 | Resolve the five L3 questions in the CLV protocol, then freeze it | L3 | Owner | blocked |

## Closed

| id | task | level | owner | status |
|---|---|---|---|---|
| T-005 | Build the `coordination/` layer and wire it into `CLAUDE.md` | L1 | Claude | done |
| T-008 | Draft the CLV measurement protocol | L1 | Claude | done |

---

## Notes on the open rows

**T-001** dropped from L3/Owner to L1/Claude under
[D-002](DECISIONS.md) — a transition that is fully prescribed and
machine-verifiable is execution, not a decision. The steps are prescribed in
[`CFL_RESEARCH_STATE.md`](../CFL_RESEARCH_STATE.md) and each precondition is
already enforced by a named test in `tests/test_research_state.py`; the mapping
is in [`CRITICAL_GATES.md`](CRITICAL_GATES.md).

The task is the automation, not the transition itself: detect the first
`PROP-0001@v2` row, record the first-lock UTC timestamp, workflow run id, commit
SHA, `lock_prop0002.py`'s sha256 and row count, set `lock_script.frozen = true`,
move the script into DUR-002's frozen files, rerun the guards. **If any guard
fails the transition does not happen and is not forced** — a failing guard is a
stop, and working around one is L3.

**T-002** is the live bottleneck on DUR-001's specification. The clauses are not
approved en bloc and are split by risk in the register. Six of them change data
eligibility, scoring, model behaviour or interpretation; three are governance
only. The three low-risk ones could move first if the owner wants to clear the
backlog without touching anything that affects a result.

**T-003** is with ChatGPT now. The draft is
[`research/clv/CLV_MEASUREMENT_PROTOCOL.md`](../research/clv/CLV_MEASUREMENT_PROTOCOL.md);
the review checklist is §7. Twelve decided rules, eleven open questions. It is a
**measurement protocol, not an experiment** — no hypothesis, no challenger, no
verdict, so it stays out of the DUR register.

**T-004** is small and self-contained, and is named in `CLAUDE.md` as worth
doing. Good filler when a larger line is blocked.

**T-006** is urgent in a way its size hides. Q-05's de-vigged variant needs both
sides of the market captured at the publish instant, and that can never be
backfilled — every card that goes by without it is permanently unavailable to
that definition. It does not wait on the protocol freeze, because capturing more
than you end up needing costs nothing and capturing less is irreversible.

**T-007** is the freeze. Five questions need the owner: Q-05 (vigged or de-vigged),
Q-06 (published probability or wager price), Q-07 (aggregation and weighting),
Q-08 (minimum sample), Q-11 (how it may be described). Each changes what a
published number means. It is blocked behind T-003 — ChatGPT reviews the
methodology first, so the questions reaching the owner have been through a
statistician.
