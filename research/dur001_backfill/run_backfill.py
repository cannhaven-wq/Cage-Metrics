"""DUR-001 historical backfill runner — gated, and currently refusing.

    python research/dur001_backfill/run_backfill.py --check
    python research/dur001_backfill/run_backfill.py --check \
        --model-version PROP-0001-HIST@v1 --timing-rule t10_earliest_observed_start

Run `--check` to see what the gate says about a proposed backfill. The gate is
in `gate.py`; the rules it enforces come from PREREGISTRATION.md §13.

**As of 2026-09-16 no backfill can clear the gate**, and that is intended. The
historical timing rule is amendment item (i), which is still awaiting Reed's
choice between two candidates. Until one is picked and marked approved there is
no pre-registered definition of which historical quote is the benchmark, so
there is nothing legitimate to compute. Picking the rule after seeing which one
flatters the result is the selection the preregistration exists to prevent.

This runner deliberately contains no scoring code. Writing the scorer before the
rule is chosen invites running it "just to look", and the looking is the damage.
When item (i) is approved, the scorer goes here, behind `assert_clear`.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from research.dur001_backfill.gate import check, explain      # noqa: E402
from research.dur001_backfill.spec import BackfillSpec        # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="report what the gate says and exit")
    ap.add_argument("--model-version", default="")
    ap.add_argument("--target-table", default="research_backfill_results")
    ap.add_argument("--timing-rule", default=None)
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
