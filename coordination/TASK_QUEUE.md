# Task queue

What is queued, who owns it, and what level it sits at. One row per task.

**Levels** are defined in [`CRITICAL_GATES.md`](CRITICAL_GATES.md): `L0`
execute, `L1` AI-to-AI, `L2` proceed and notify, `L3` Reed only.
**Owners**: `Claude` (build), `ChatGPT` (spec / review), `Reed` (owner).
**Status**: `proposed`, `queued`, `in-progress`, `blocked`, `done`, `dropped`.

An `L3` task cannot be marked `done` until [`DECISIONS.md`](DECISIONS.md)
records the decision against its id. `tests/test_coordination.py` enforces it.

Ids are never reused. A task that dies is `dropped`, not deleted — the reason
it died is usually worth more than the task was.

---

## Open

| id | task | level | owner | status |
|---|---|---|---|---|
| T-001 | Record DUR-002's `armed → collecting` transition when the first `PROP-0001@v2` lock row lands | L3 | Reed | blocked |
| T-002 | Individual votes on the nine held amendment clauses — (a) (b) (c) (d) (e) (f) (g) (j) (k) | L3 | Reed | blocked |
| T-003 | Specify market / closing-price capture and CLV measurement | L1 | ChatGPT | queued |
| T-004 | Collapse the `picks.html` → `card-lab.html` → `/` redirect to a single hop | L1 | Claude | queued |

## Closed

| id | task | level | owner | status |
|---|---|---|---|---|
| T-005 | Build the `coordination/` layer and wire it into `CLAUDE.md` | L1 | Claude | done |

---

## Notes on the open rows

**T-001** is blocked on an event, not on a person: the first v2 row landing.
The steps are already prescribed in
[`CFL_RESEARCH_STATE.md`](../CFL_RESEARCH_STATE.md) — record the first-lock UTC
timestamp, the workflow run id and commit SHA, `lock_prop0002.py`'s sha256 and
the row count; set `lock_script.frozen = true`; move the script into DUR-002's
frozen files; rerun the guards. It is L3 anyway, because moving an experiment's
lifecycle state is an owner decision even when the procedure is mechanical.
Claude may prepare the diff; Reed lands it.

**T-002** is the live bottleneck on DUR-001's specification. The clauses are not
approved en bloc and are split by risk in the register. Six of them change data
eligibility, scoring, model behaviour or interpretation; three are governance
only. The three low-risk ones could move first if Reed wants to clear the
backlog without touching anything that affects a result.

**T-003** is the stated top priority in the research register: it is the
biggest statistical dependency for showing CFL has an economically meaningful
edge. It needs a written specification before any code — CLV is a public claim
surface, so how it is measured is decided once, in advance, not discovered.

**T-004** is small and self-contained, and is named in `CLAUDE.md` as worth
doing. Good filler when a larger line is blocked.
