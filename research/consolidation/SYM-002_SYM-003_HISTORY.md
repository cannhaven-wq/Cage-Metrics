# SYM-002 and SYM-003 — research history, recorded before closing PR #53

**2026-10-21. Internal research record.** Draft PR #53
(`claude/cool-sagan-osv7iq`, session `session_012786gCgS8ufJEFc311FVoK`) is
being closed as **superseded** by the consolidated research framework
(D-034). This file is the record that stays on `main`; the branch is not
deleted.

## Plain version

On 7 October 2026 a separate Claude session built a third search engine: it
looked for a short written formula, built from each fighter's record, that
picks winners better than a plain weighted average or the betting market. It
kept its data, models and results in a private folder that never reached
GitHub. Only the code and its rules were committed. **So the repository
holds no SYM result, and none may be cited.** It also tested its formulas on
2025–26 fights before those years were sealed, so it counts as having looked
at the sealed period.

## What was committed (code and rules only)

| commit (2026-10-07, UTC) | what |
|---|---|
| `f65e1a1d` 16:30 | SYM-002 preregistration and `config.json`, frozen before any feature or fit |
| `2c6a268e` 16:43 | point-in-time features (23 per fighter), bounded symbolic search (`symreg.py`), outer folds, audits, report code |
| `9bf99be2` 16:51 | SYM-003 preregistration (matchup features), frozen before any SYM-003 feature; marks v1's leakage status "unverified" |
| `7cd45514` 16:55 | SYM-003 features, audit, run and report code |

`research/symbolic/private/` is git-ignored in full: raw exports, fitted and
frozen models (`private/models/FROZEN.json`), candidate logs and the written
report never entered the repository. Data came through the Supabase connector
with read-only `SELECT`s.

## What the two experiments asked

- **SYM-002.** Does a symbolic formula over 23 point-in-time gaps (age, reach,
  height, stance, Elo, opponent Elo, experience, layoff, activity, striking
  and grappling rates, win rate, finish rate, last-three record) beat a
  regularised logistic regression on the same gaps, or the archived market?
  Outer test folds **2021–2026**, trained on earlier events. A final model was
  fitted on everything through **2026-10-03**, hashed, for scoring only on
  events after 2026-10-07.
- **SYM-003.** Do matchup features add to SYM-002's baseline? Three groups:
  wrestling matchup (W), striking matchup (S), and **opponent-adjusted
  performance (O)** — six residuals of what a fighter did against what each
  past opponent normally allowed, using the opponent's rates going into that
  bout. Same folds, 2021–2026.
- **"v1"**, an earlier, uncommitted session's three-term formula (reported
  61.5% accuracy on 226 eligible 2026 fights). Its code was never available;
  SYM-002 re-implemented only its structure. Its leakage status is
  **unverified**.

The commit message of `7cd45514` and SYM-003's preregistration both say that
SYM-002 found the weighted average "as good as any fancy formula". That is
the session's own description; the evidence behind it is not in the
repository and cannot be checked.

## Sealed-period contamination

- The outer folds 2021–2026 include **every H1 year (2025-01-01 → 2026-07-11)**
  and part of RESERVE. Outcomes from those years were read, scored and
  compared. This happened on 2026-10-07, five days **before** PRED-001 froze
  the holdout, so it broke no rule then; it is still a look at H1.
- The work used **archived BFO odds** (1970 placeholder timestamps,
  "unverified") and 34 timing-verified prices as a descriptive side table.
- **Consequences:**
  1. Any idea SYM-002 or SYM-003 tested — in particular the
     **opponent-adjusted (O) and matchup (W, S) features** — has been
     evaluated on H1 by a CFL session. A later experiment built on the same
     idea must declare it, and its H1 result is non-confirmatory
     (PRED-001 §2).
  2. The frozen SYM final models were fitted through 2026-10-03, so they are
     ineligible for H1 and RESERVE. They could only ever be scored
     prospectively, and they are not in the repository.
  3. Because the results are private and unrecorded, nobody can show what
     they were. **This matters for PRED-002**, whose central idea
     (opponent-adjusted grappling) is SYM-003's O group:
     see [`PRED-002_PRIOR_EXPLORATION.md`](PRED-002_PRIOR_EXPLORATION.md).

## Why superseded, not merged

It is a third discovery engine alongside the two now consolidated; its
results cannot be audited; its test folds overlap the sealed period; and the
consolidated engine already covers its feature families (Elo, opponent Elo,
rates, matchup cross terms) on DEV only. The PR is closed **unmerged**. The
code stays readable on the branch for as long as the branch exists; deleting
it is a separate owner decision.
