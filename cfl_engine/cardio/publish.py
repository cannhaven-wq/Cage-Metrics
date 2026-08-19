"""CFL cardio fade-slope model — Step 6: publish ratings to Supabase.

Upserts cfl_engine/cardio/fighter_cardio.csv into the fighter_cardio table.
Keyed on fighter_id, so re-running after a refit updates in place rather than
duplicating. computed_at is set explicitly on every write so a stale row is
always distinguishable from a fresh one.

Requires SUPABASE_URL + SUPABASE_SECRET_KEY (the legacy JWT service_role key —
the newer sb_secret_ format is not accepted by these scrapers).

Usage:
    python cfl_engine/cardio/publish.py            # dry run, prints what it would send
    python cfl_engine/cardio/publish.py --execute
"""
from __future__ import annotations

import argparse
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = os.path.join(HERE, "fighter_cardio.csv")
TABLE = "fighter_cardio"
BATCH = 500

COLUMNS = [
    "fighter_id", "fade_slope", "fade_slope_dev", "population_slope", "slope_se",
    "total_min_fought", "min_past_10", "n_fights", "n_fights_reaching_r3", "n_round_obs",
]
INT_COLUMNS = {"fighter_id", "n_fights", "n_fights_reaching_r3", "n_round_obs"}


def _env(name):
    v = os.environ.get(name)
    if not v:
        raise SystemExit(name + " not set in the environment.")
    return v


def clean(value, column):
    """NaN/inf -> None so PostgREST gets valid JSON, ints stay ints."""
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if column in INT_COLUMNS:
        return int(value)
    return float(value)


def valid_fighter_ids(base, headers):
    """fighter_cardio has a FK to fighters(id); a stale id would fail the batch."""
    ids, offset = set(), 0
    while True:
        p = {"select": "id", "limit": "1000", "offset": str(offset)}
        req = urllib.request.Request(base + "/rest/v1/fighters?" + urllib.parse.urlencode(p),
                                     headers=headers)
        with urllib.request.urlopen(req) as r:
            batch = json.loads(r.read())
        ids.update(f["id"] for f in batch)
        if len(batch) < 1000:
            return ids
        offset += 1000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    base = _env("SUPABASE_URL").rstrip("/")
    key = _env("SUPABASE_SECRET_KEY")
    headers = {"apikey": key, "Authorization": "Bearer " + key,
               "Content-Type": "application/json"}

    df = pd.read_csv(args.csv)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise SystemExit("CSV is missing columns: " + ", ".join(missing))

    known = valid_fighter_ids(base, headers)
    stamp = datetime.now(timezone.utc).isoformat()

    payload, skipped = [], 0
    for _, row in df.iterrows():
        fid = int(row["fighter_id"])
        if fid not in known:
            skipped += 1
            continue
        rec = {c: clean(row[c], c) for c in COLUMNS}
        rec["computed_at"] = stamp
        payload.append(rec)

    print("rows in csv        : %d" % len(df))
    print("skipped (unknown id): %d" % skipped)
    print("to upsert          : %d" % len(payload))
    if payload:
        print("\nsample record:")
        print(json.dumps(payload[0], indent=1))

    if not args.execute:
        print("\n(dry run — nothing written. Re-run with --execute to publish.)")
        return

    url = base + "/rest/v1/" + TABLE + "?on_conflict=fighter_id"
    up = dict(headers)
    up["Prefer"] = "resolution=merge-duplicates,return=minimal"
    sent = 0
    for i in range(0, len(payload), BATCH):
        chunk = payload[i:i + BATCH]
        req = urllib.request.Request(url, data=json.dumps(chunk).encode(),
                                     headers=up, method="POST")
        try:
            with urllib.request.urlopen(req) as r:
                r.read()
        except urllib.error.HTTPError as e:
            raise SystemExit("HTTP %s on batch at offset %d: %s"
                             % (e.code, i, e.read().decode()[:400]))
        sent += len(chunk)
        print("  upserted %d/%d" % (sent, len(payload)))
    print("\nEXECUTED: %d rows in %s (computed_at %s)." % (sent, TABLE, stamp))


if __name__ == "__main__":
    main()
