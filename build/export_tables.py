#!/usr/bin/env python3
"""Export Supabase tables to newline-delimited JSON under data/exports/.

Why this exists
---------------
The research work (DUR-001, PROP-0001, the walk-forward harness) keeps needing
a local, versioned copy of what the database held at a point in time. Two of the
tables are also destructive by design: `prop_projections` is full-table replaced
on every refresh, and `v_fight_odds_consensus` is overwritten as the line moves.
A daily export is the only cheap way to keep a history of either.

It is also the bulk dump for `prop_model_locks`, which RLS makes unreadable with
the publishable key, so the provenance audit in research/provenance/ had to pull
it through an admin connection by hand.

Read-only
---------
This script issues GET requests only. It never writes to Supabase.

Paging
------
PostgREST caps a response at 1,000 rows regardless of what you ask for, so every
table is pulled with an explicit Range header and an incrementing offset until a
short page comes back. `fight_rounds` is the one that actually needs it — it is
several rows per fight across ~9k fights.

Environment
-----------
  SUPABASE_URL                e.g. https://<ref>.supabase.co
  SUPABASE_SERVICE_ROLE_KEY   service_role key; needed because several of these
                              tables have no anon SELECT policy and would
                              otherwise return 0 rows with HTTP 200 and no error

Both are required. The script exits non-zero if either is missing rather than
writing empty files — an empty export that looks like a successful run is worse
than a failed one.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PAGE = 1000
OUT_DIR = Path("data/exports")
MAX_RETRIES = 4
TIMEOUT = 120

# Tables and views to export, in dependency-ish order. fight_rounds is REQUIRED:
# it is the round-by-round source behind v_fighter_consistency and the cardio
# work, and it is the one table nothing else can reconstruct.
TABLES = [
    "events",
    "fighters",
    "fights",
    "fight_rounds",          # required — do not drop
    "fight_odds",
    "prop_odds",
    "prop_model_locks",
    "fight_start_estimates",
    "pre_fight_snapshots",
    "v_pre_fight_graded",
]


def env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        sys.exit(
            f"[export] {name} is not set. Refusing to run: a partial export that "
            f"looks successful is worse than no export."
        )
    return v


def fetch_page(base: str, key: str, table: str, offset: int) -> list[dict]:
    """One page of up to PAGE rows, ordered by a stable key where possible."""
    qs = urllib.parse.urlencode({"select": "*"})
    url = f"{base}/rest/v1/{urllib.parse.quote(table)}?{qs}"
    req = urllib.request.Request(url)
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    # Range is what actually bounds the page; PostgREST ignores a larger limit.
    req.add_header("Range-Unit", "items")
    req.add_header("Range", f"{offset}-{offset + PAGE - 1}")

    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:500]
            # 416 = offset past the end. That is a normal end-of-table signal.
            if e.code == 416:
                return []
            last_err = RuntimeError(f"HTTP {e.code} on {table}@{offset}: {body}")
            # 4xx other than 429 will not fix themselves on a retry.
            if 400 <= e.code < 500 and e.code != 429:
                raise last_err
        except Exception as e:  # noqa: BLE001 - network flakiness
            last_err = e
        sleep = 2 ** (attempt + 1)
        print(f"[export]   retry {attempt + 1}/{MAX_RETRIES} in {sleep}s ({last_err})")
        time.sleep(sleep)
    raise RuntimeError(f"[export] {table}@{offset} failed after {MAX_RETRIES} tries: {last_err}")


def export_table(base: str, key: str, table: str) -> tuple[int, Path]:
    rows: list[dict] = []
    offset = 0
    while True:
        page = fetch_page(base, key, table, offset)
        rows.extend(page)
        if len(page) < PAGE:
            break
        offset += PAGE

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{table}.jsonl"
    # sort_keys so the file is byte-stable run to run and git diffs stay small.
    body = "".join(json.dumps(r, sort_keys=True, default=str) + "\n" for r in rows)
    # Only rewrite when the content actually changed, same reasoning as
    # build/prerender.js writeIfChanged: unchanged tables should not churn git.
    if path.exists() and path.read_text() == body:
        print(f"[export] {table:<24} {len(rows):>7} rows (unchanged)")
        return len(rows), path
    path.write_text(body)
    print(f"[export] {table:<24} {len(rows):>7} rows -> {path}")
    return len(rows), path


def main() -> None:
    base = env("SUPABASE_URL").rstrip("/")
    key = env("SUPABASE_SERVICE_ROLE_KEY")

    print(f"[export] target {base}")
    counts: dict[str, int] = {}
    failures: list[str] = []

    for t in TABLES:
        try:
            n, _ = export_table(base, key, t)
            counts[t] = n
        except Exception as e:  # noqa: BLE001
            print(f"[export] FAILED {t}: {e}", file=sys.stderr)
            failures.append(t)

    # fight_rounds is required. Everything else failing is bad; this is fatal.
    if "fight_rounds" in failures or counts.get("fight_rounds", 0) == 0:
        sys.exit("[export] fight_rounds is required and came back empty or failed.")

    manifest = {
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "supabase_url": base,
        "row_counts": counts,
        "failed": failures,
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"[export] manifest written; {len(counts)} ok, {len(failures)} failed")

    if failures:
        sys.exit(f"[export] {len(failures)} table(s) failed: {', '.join(failures)}")


if __name__ == "__main__":
    main()
