# T-086 — research corrections, recorded before the bell (2026-10-13)

The owner approved these in [D-026](../../coordination/DECISIONS.md). They are
written **before** the 2026-10-17 card, so no result can have shaped them. This
file adds to the record and **edits nothing that is sealed**.

## 1. PRED-001 RESERVE: 169 as frozen, 164 under the corrected definition

- **What stays.** `research/protocol/holdout_manifest.json` records RESERVE
  (event dates 2026-07-18 → 2026-10-10) as `"decided": 169`. That file is
  hash-pinned by PRED-001, and it is **not modified**. The 169 is the
  original frozen cohort and stays the record of what was sealed.
- **What changed.**
  - The frozen eligibility treated every row in `fights` as a UFC bout. Five
    of the 169 are Dana White's Contender Series bouts on "DWCS 10.3"
    (2026-08-25): fights **49307, 49308, 49309, 49310, 49311**. They are not
    UFC bouts.
  - Re-derived from production on 2026-10-13, before any move: 169 decided
    fights, 5 of them on event 4259.
  - Once T-086 is applied, the same recipe returns **164**.
- **The corrected definition.** The frozen eligibility, restricted to bouts on
  UFC cards. A UFC card is one that passes `events_ufc_name_only`, the rule in
  `build/promotion.js` and `t086_dwcs_non_ufc.sql`.
- **The rule.**
  - The 164-fight cohort is a **corrected cohort**, not the frozen one. It may
    not be cited, scored or compared as though it were the original sealed
    RESERVE.
  - Any future use of RESERVE states which of the two it means, and cites this
    file.
  - RESERVE has never been scored. It has no hash and no benchmark
    (`decided_priced: 0`).
- **H1 is unaffected.** It was re-derived on 2026-10-13 with the frozen recipe
  (`holdout_manifest.sql`): 710 fights, 63 events, and all four hashes match the
  manifest. No DWCS bout is in H1.

## 2. PROP-0001 locks on fight 53618 (Leblanc vs Galanti, 2026-10-17)

**The locks.** Eight rows in `prop_model_locks`, written 2026-10-09:

| ids | version | locked at (UTC) |
|---|---|---|
| 457, 458, 459, 460 | PROP-0001@v1 | 2026-10-09 17:21:17 |
| 505, 506, 507, 508 | PROP-0001@v2 | 2026-10-09 17:21:29 |

All eight carry feature_hash `d1af8f98f9e6973d`.

**The contamination, known before the fight.**
- At lock time, Galanti's only completed bout in `fights` was 49311, on the
  Contender Series card. Leblanc's was 88, a UFC bout.
- The locked feature `m_fh_n_fights` (the mean prior-fight count over both
  corners) therefore reads **1.0**. Counting UFC bouts only, it would read
  **0.5**.
- The other fight-history and round-pace features for Galanti also come from
  that one non-UFC bout.
- PROP-0001's training set (`training_n_fights` 6,881) included the 5 DWCS
  bouts.

**How it is graded (owner-approved).**
- All eight locks are preserved, append-only, and graded under their
  **original rules**. No outcome-based exclusion.
- Every report that includes this card also gives a **sensitivity check**: the
  same metrics with fight 53618's eight locks left out, labelled as a
  sensitivity check, reported beside the primary result and never in place of
  it.
- This decision is fixed now, before the result.

## 3. Road to UFC 4.6: untouched

Event 146 "UFC - Road to UFC 4.6" (2025-08-22) and its two bouts (417, 418)
stay where they are, and no rule changes for them.

- Being in the sealed H1 set does not prove they belong in the UFC category.
- Being named "UFC - …" does not prove it either.
- Classifying them waits for independent verification against an official
  source. Any change would also need a PRED-001 amendment, because both bouts
  are in H1.
