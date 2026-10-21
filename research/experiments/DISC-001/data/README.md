# DISC-001 data — not committed

The two files `discover.py` reads are **not in the repository** (owner
decision D-034, 2026-10-21: no full historical data exports in a public
repository). They are pinned here by hash so any copy can be checked byte for
byte, and `tests/test_disc001.py` checks a local copy if one is present.

| file | rows | sha256 | md5 without the final newline (as in REPORT.md) | git blob |
|---|---|---|---|---|
| `dev_fights.csv` | 7,974 | `2904655f1cee82eb6fd9fb9c7dbb513b4f337e0343ed5576099d26eefe90df92` | `886dff134655d8cad62b055c82dfd3a1` | `0e6f3931bc25cb6135df721ada15b3ed8411f11c` |
| `dev_fighters.csv` | 2,550 | `0ae32b6bd0e7f37f913462e6b79d25e65b2f60d6772840c747875d43348a30db` | `bed424a2de1324bb0a9330ae49b1c8c1` | `3c5e8a26cdd538b58014c64db0f1247539c3a3da` |

## How to obtain them

1. **Re-export.** Run `research/factors/disc001_dev_export.sql` read-only
   against the database (every statement filters `event_date < 2025-01-01`),
   or `build/disc001-export.js`, which implements it and prints the md5 of each
   output. Save the outputs here under the names above, each ending with one
   newline.
2. **Or take the original bytes** from commit `772dbcc2` on
   `claude/brave-bohr-e8j482` while that branch exists (it has not been
   deleted; deleting it is an owner decision):
   `git show 772dbcc2:research/experiments/DISC-001/data/dev_fights.csv`.

Then `python3 research/experiments/DISC-001/discover.py` reproduces
`results.json` (the consolidation audit reproduced every verdict and gain
exactly), and the skipped tests in `tests/test_disc001.py` run.

The scored set is the 6,824 priced, decided DEV fights; their ids and outcomes
reproduce PRED-001's frozen DEV fingerprints in
`research/protocol/holdout_manifest.json`.
