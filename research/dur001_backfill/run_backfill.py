"""DUR-001 historical backfill runner — gated, and currently refusing.

    python research/dur001_backfill/run_backfill.py --check
    python research/dur001_backfill/run_backfill.py --check \
        --model-version PROP-0001-HIST@v1 --timing-rule t10_earliest_observed_start

Run `--check` to see what the gate says about a proposed backfill. The gate is
in `gate.py`; the rules it enforces come from PREREGISTRATION.md §13.

Preregistration Amendment 1.2 (2026-09-16) froze the historical timing rule to
`t10_earliest_observed_start`, so item (i) is settled and a well-specified
backfill can now clear the gate. The rejected candidate earns a dedicated
`TIMING_REJECTED` refusal that asserting approval cannot buy past.

This runner still contains no scoring code, deliberately. Reed has held every
amendment clause touching calibration or scoring until the walk-forward fold
discrepancy is closed, and writing the scorer before then invites running it
"just to look" — the looking is the damage. The scorer goes here, behind
`assert_clear`, once that is resolved.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from research.dur001_backfill.gate import check, explain      # noqa: E402
from research.dur001_backfill.spec import (                   # noqa: E402
    FROZEN_TIMING_RULE,
    BackfillSpec,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="report what the gate says and exit")
    ap.add_argument("--model-version", default="")
    ap.add_argument("--target-table", default="research_backfill_results")
    ap.add_argument("--timing-rule", default=None,
                    help=f"must be {FROZEN_TIMING_RULE!r} (Amendment 1.2)")
    ap.add_argument("--timing-rule-approved", action="store_true")
    args = ap.parse_args()

    spec = BackfillSpec(
        model_version=args.model_version,
        target_table=args.target_table,
        timing_rule=args.timing_rule,
        timing_rule_approved=args.timing_rule_approved,
        rows=(),        # no fights are assembled until the gate clears
    )

    print(explain(spec))
    if not args.check:
        print("\nNo scoring code exists yet — see this module's docstring. "
              "Use --check.")
    return 1 if check(spec) else 0


if __name__ == "__main__":
    raise SystemExit(main())
