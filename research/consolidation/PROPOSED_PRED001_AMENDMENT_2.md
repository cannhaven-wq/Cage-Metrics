# PROPOSED — PRED-001 Amendment 2: provenance-only contamination note

**Status: prepared, NOT applied.** PRED-001 is frozen; applying this is an L3
amendment (`coordination/CRITICAL_GATES.md` item 1) and waits for the owner's
separate approval (D-034, item 4). Nothing under `research/protocol/` is
changed by the pull request that carries this file, and
`tests/test_consolidation.py` fails if the frozen files move without an
amendment.

## What it records, plainly

Two files on `main` have held the results of sealed-period fights, beside
their betting prices, in this public repository since August 2026. Nobody
needs to have opened them for this to matter: PRED-001's holdout is a set of
conventions, and its manifest should say where those conventions were not
kept. The amendment **adds one sentence to the manifest's list of known
contamination and nothing else**. It changes no partition, threshold, budget,
benchmark or rule, and it is not motivated by any result.

## The facts it rests on

| file | first committed | rows | rows from 2025-01-01 | of which H1 (to 2026-07-11) | of which RESERVE | columns that matter |
|---|---|---|---|---|---|---|
| `out_real/oos_predictions.csv` | `574dbe88`, 2026-08-07 | 3,881 | 793 | 786 | 7 | `y` (result), `odds_a`, `odds_b`, `q_mkt`, `fight_id`, `event_date` |
| `out_real/edge_bets.csv` | `1b6b5fc3`, 2026-08-18 | 658 | 304 | 301 | 3 | the same, plus `won` |

`.gitignore` has listed `out_real/` since `f3ca4c07` (2026-07-16), so both
files were added past the ignore rule. They predate PRED-001's freeze
(2026-10-12). The repository is public. Nothing in this proposal removes them:
removal from history is a separate owner decision.

## Exact changes, if approved

1. **`research/protocol/holdout_manifest.json`** — append one string to
   `known_contamination`:

   > "Sealed-period results have been public in this repository since August 2026: out_real/oos_predictions.csv (committed 574dbe88, 2026-08-07) and out_real/edge_bets.csv (1b6b5fc3, 2026-08-18), both on main and outside research/experiments/ (so PRED-001's experiment lint does not see them), hold the result and BFO closing prices of 786 H1 and 7 RESERVE fights. Any session or person with the repository could have read them. This changes no rule: it is why no claim rests on H1 (section 9), recorded here so an auditor knows the exposure existed. Recorded by Amendment 2."

2. **`research/protocol/PREDICTION_RESEARCH_PROTOCOL.md`** — append under
   `## Amendments`:

   ```
   ### Amendment 2 — <date of approval>

   **Motivation:** provenance only. The research consolidation audit
   (D-034) found sealed-period results committed to `main` under `out_real/`
   since August 2026. `motivated_by_observed_results: false` — it concerns
   where data sits, not what any result showed; no look has been taken under
   this protocol. Change: one sentence added to `known_contamination` in
   `holdout_manifest.json`. Not changed: everything else, including the
   partitions, the manifest's fingerprints and counts, the thresholds, the
   budgets, the benchmark and the claim ladder.
   ```

3. **`research/protocol/FREEZE.json`** — append a history entry:

   ```json
   {
     "version": "1.2.0",
     "date": "<date of approval>",
     "amendment": 2,
     "motivated_by_observed_results": false,
     "looks_taken_before": 0,
     "motivation": "provenance only: records that out_real/ on main has exposed H1 and RESERVE results since 2026-08; no rule changes",
     "files": { "<every governed file>": "<sha256 after the change>" },
     "decision": "D-0xx"
   }
   ```

   Only `holdout_manifest.json` and the protocol text change; every other
   governed file keeps its 1.1.0 hash. `research/protocol/protocol.json`
   `version` moves to `1.2.0` only if the owner wants the version bump; the
   tests do not require it.

4. **`tests/test_consolidation.py`** — its check that FREEZE.json still ends
   at 1.1.0 is updated in the same pull request, so applying the amendment is
   a visible diff.

## What it does not do

It does not delete or rewrite `out_real/`, does not change any fingerprint
(the manifest's `partitions` block, which holds them, is untouched), and does
not make H1 any less usable than it already was: PRED-001 already treats an
H1 pass as licensing only a prospective test.
