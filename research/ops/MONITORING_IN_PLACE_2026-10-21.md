# Monitoring already in place — evaluation for decision C4 (2026-10-21)

**Verdict: the existing monitoring is working. No new watcher is added**
(owner decision C4: deferred).

| monitor | what it watches | schedule | evidence |
|---|---|---|---|
| Dead man (`dead-man.yml`) | a pre-fight record exists for every fight on every card inside 10 days; opens an issue and fails the run when one is missing | asks for 3 runs a day | 12 scheduled runs, 2026-10-17 → 10-21, all succeeded. GitHub delivered 2–3 a day; the longest gap was about 14 h |
| Pipeline health (`pipeline-health.yml`) | GitHub, Railway and Supabase jobs: a failed scheduled run, no recent success, a disabled workflow, stale data, a one-sided odds capture | 2 a day | ran green 2026-10-21 12:24 UTC |
| Tests (`tests.yml`) | every push and PR: Python, Node and the signup browser test | on push | green on main today |
| Live-site check (`verify-live.yml`) | the real cannonfightlab.com in Chromium, desktop and mobile | manual | fixed today (#110); green on main 15:42 UTC |

**The known gap still stands.** All of these run on GitHub's scheduler. If
GitHub stopped delivering schedules, the pipeline-health check, which also
reports disabled workflows, would go quiet at the same time as everything
else. That was T-076's point.

It remains acceptable for now:
- GitHub has kept delivering 2–3 dead-man runs a day.
- A missed pre-fight record still produces an issue on the next run that
  lands.
- Reopen T-076 only if a run gap longer than a day appears.

The built outside-observer design is kept, inert, in
`research/ops/T076_DEAD_MAN_OBSERVER_RUNBOOK.md`.
