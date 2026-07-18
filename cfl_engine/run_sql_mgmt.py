"""Run a SQL file against the CFL Supabase project via the Management API.

Usage:  python cfl_engine/run_sql_mgmt.py <file.sql>
Needs SUPABASE_ACCESS_TOKEN in env (personal access token; never printed).
This is how DDL ships from this machine: the direct Postgres port is
IPv6-only/unreachable, but api.supabase.com is not.
"""
import json
import os
import sys
import urllib.error
import urllib.request

PROJECT_REF = "uftancejftcryfvbggll"


def main() -> None:
    token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    if not token:
        sys.exit("SUPABASE_ACCESS_TOKEN not set.")
    if len(sys.argv) != 2:
        sys.exit("usage: python cfl_engine/run_sql_mgmt.py <file.sql>")
    with open(sys.argv[1], encoding="utf-8") as f:
        sql = f.read()

    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query",
        data=json.dumps({"query": sql}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # api.supabase.com is behind Cloudflare bot management, which 403s
            # (error 1010) on the default Python-urllib User-Agent. A normal
            # browser UA clears the signature check.
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/126.0.0.0 Safari/537.36"),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            print(f"OK ({r.status}): {r.read().decode()[:500]}")
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:800]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
