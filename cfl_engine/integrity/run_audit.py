#!/usr/bin/env python3
"""Run the integrity checks and report what moved since the last baseline.

    python cfl_engine/integrity/run_audit.py            # table, human readable
    python cfl_engine/integrity/run_audit.py --json     # machine readable
    python cfl_engine/integrity/run_audit.py --fail-on-regression

Read-only. It issues `SELECT count(*)` and nothing else — no writes, no DDL, no
fixes. Deciding what to do about a defect is a separate act from noticing it,
and this only ever notices.

What a regression means
-----------------------
Each check carries the count measured on 2026-09-16. Higher than that means new
damage; lower means somebody cleaned up. The run prints both and, with
`--fail-on-regression`, exits non-zero on the first kind only — a cleanup should
not turn a workflow red.

Checks marked "not a defect" are reported and never counted as regressions. The
bell-time check counts a thing we WANT to go up.

Environment
-----------
  SUPABASE_URL                 https://<ref>.supabase.co
  SUPABASE_SECRET_KEY          (or SUPABASE_SERVICE_ROLE_KEY / SUPABASE_SERVICE_KEY)

A service key is required. `fight_odds` has no anon SELECT policy, so the
publishable key returns zero rows with HTTP 200 — which would report a perfectly
clean database. An empty result here is a failure, not a pass.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cfl_engine.integrity.checks import CHECKS, NOTE  # noqa: E402

TIMEOUT = 120
# Created by cfl_engine/integrity/count_rpc.sql, which is NOT applied. Without
# it the script says so and stops rather than running 21 queries some other way.
RPC = "cfl_integrity_count"


def env_key() -> str:
    for name in ("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY"):
        v = os.environ.get(name, "").strip()
        if v:
            return v
    sys.exit(
        "No Supabase service key in env. Refusing to run: `fight_odds` has no "
        "anon SELECT policy, so a publishable key would report a spotlessly "
        "clean database with HTTP 200."
    )


def run_check(base_url: str, key: str, sql: str) -> int:
    """Ask Postgres for one number, through a read-only RPC."""
    body = json.dumps({"q": sql}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/rest/v1/rpc/{RPC}",
        data=body,
        method="POST",
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return int(json.loads(resp.read().decode("utf-8")))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fail-on-regression", action="store_true",
                    help="exit 1 if any defect count is above its baseline")
    args = ap.parse_args()

    base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not base_url:
        sys.exit("SUPABASE_URL not set.")
    key = env_key()

    results = []
    for c in CHECKS:
        try:
            n = run_check(base_url, key, c.sql.strip())
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:200]
            sys.exit(
                f"check `{c.key}` failed (HTTP {e.code}). If this says the "
                f"function does not exist, apply cfl_engine/integrity/count_rpc.sql "
                f"first — this script will not run the query any other way.\n  {detail}"
            )
        results.append({
            "key": c.key, "title": c.title, "n": n, "baseline": c.baseline,
            "delta": n - c.baseline, "unit": c.unit,
            "classification": c.classification, "why": c.why,
        })

    regressions = [r for r in results
                   if r["delta"] > 0 and r["classification"] != NOTE]
    improvements = [r for r in results if r["delta"] < 0]

    if args.json:
        print(json.dumps({"results": results,
                          "regressions": [r["key"] for r in regressions],
                          "improvements": [r["key"] for r in improvements]}, indent=2))
    else:
        width = max(len(r["key"]) for r in results)
        for r in results:
            mark = "  " if r["delta"] == 0 else ("UP" if r["delta"] > 0 else "DN")
            delta = "" if r["delta"] == 0 else f"  ({r['delta']:+d} vs baseline {r['baseline']})"
            print(f"{mark} {r['key']:<{width}}  {r['n']:>6} {r['unit']}{delta}")
            print(f"     {r['title']}  [{r['classification']}]")
        print()
        if regressions:
            print(f"{len(regressions)} check(s) worse than baseline: "
                  + ", ".join(r["key"] for r in regressions))
        if improvements:
            print(f"{len(improvements)} check(s) better than baseline: "
                  + ", ".join(r["key"] for r in improvements)
                  + " — update the baselines in checks.py if this was deliberate.")
        if not regressions and not improvements:
            print("Every check matches its 2026-09-16 baseline.")

    return 1 if (args.fail_on_regression and regressions) else 0


if __name__ == "__main__":
    raise SystemExit(main())
