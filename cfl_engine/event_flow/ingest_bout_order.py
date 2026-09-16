#!/usr/bin/env python3
"""Record what order a card runs in, from the UFCStats event page.

Plain English
-------------
The database knows which fights are on a card. It does not know which one walks
out first. That matters because only the first bout starts when the schedule
says — every later one starts when the fight before it ends — so without a
running order there is no way to say whether a price was taken before a fight or
during it.

UFCStats publishes the order for free, on the page the event scraper already
reads. This writes it down: one row per bout, first walkout is 1.

  python cfl_engine/event_flow/ingest_bout_order.py                 # dry run, upcoming cards
  python cfl_engine/event_flow/ingest_bout_order.py --execute
  python cfl_engine/event_flow/ingest_bout_order.py --event-id 4433 --execute
  python cfl_engine/event_flow/ingest_bout_order.py --event-id 4433 --from-file page.html

Costs nothing. UFCStats is public HTML on the same host the scraper already
polls; no API key, no credits, no paid tier.

What it will not do
-------------------
* It never infers order from database ids. If the page cannot be read, there is
  no order, and the run reports that instead of producing one.
* It writes a card completely or not at all. One unlinkable bout renumbers every
  bout below it, so a partial card is worse than none.
* It never creates or alters a table. If `fight_bout_order` is not there, the run
  stops and says which migration creates it.
* It never rewrites history. Inserts only, duplicates ignored at the unique
  index; a reshuffled card appends a fresh observation and the latest wins.
* It is a dry run unless `--execute` is passed.

Environment
-----------
  SUPABASE_URL                 https://<ref>.supabase.co
  SUPABASE_SECRET_KEY          (or SUPABASE_SERVICE_ROLE_KEY / SUPABASE_SERVICE_KEY)

The ledger is revoked from anon and authenticated, so a publishable key reads
zero rows with HTTP 200 and writes nothing — which would look like a clean run.
Hence a service key is required and its absence is a hard exit.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cfl_engine.event_flow.bout_order import (  # noqa: E402
    SOURCE,
    BoutOrderRefused,
    FightRow,
    build_rows,
    describe,
)
from cfl_engine.event_flow.ufcstats_card import (  # noqa: E402
    CardParseError,
    parse_event_page,
)

LEDGER = "fight_bout_order"
MIGRATION = "research/clv/proposed_2026-09-16_event_flow.sql"
UFCSTATS_EVENT = "http://www.ufcstats.com/event-details/{ufc_event_id}"
TIMEOUT = 60
DEFAULT_WITHIN_DAYS = 45

# Exit codes, so a workflow can tell "nothing to do" from "the ledger is missing"
# from "a card would not link".
EXIT_OK = 0
EXIT_CONFIG = 2          # env/table missing — fix the setup
EXIT_REFUSED = 3         # a card would not link completely — fix the data
EXIT_FETCH = 4           # the page could not be fetched or read


def die(code: int, message: str) -> "NoReturn":  # noqa: F821
    """Exit with a named code AND say why.

    `sys.exit("message")` prints the message but always exits 1, so a workflow
    that branches on the code cannot tell a missing table from a card that would
    not link. These are the codes above and they are the contract.
    """
    print(message, file=sys.stderr)
    raise SystemExit(code)


# ---------------------------------------------------------------------------
# Supabase REST — reads are plain GETs, the one write is an insert
# ---------------------------------------------------------------------------
def env_key() -> str:
    for name in ("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY"):
        v = os.environ.get(name, "").strip()
        if v:
            return v
    die(
        EXIT_CONFIG,
        "No Supabase service key in env (SUPABASE_SECRET_KEY / "
        "SUPABASE_SERVICE_ROLE_KEY / SUPABASE_SERVICE_KEY). Refusing to run: the "
        f"{LEDGER} ledger is revoked from anon, so a publishable key would read "
        "zero rows with HTTP 200 and look like a clean run."
    )


def rest_get(base_url: str, key: str, path: str, params: dict) -> list:
    url = f"{base_url}/rest/v1/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url, headers={"apikey": key, "Authorization": f"Bearer {key}"}
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def rest_insert(base_url: str, key: str, path: str, rows: list[dict]) -> int:
    """Insert, ignoring rows the unique index already holds.

    `resolution=ignore-duplicates` is what makes a re-run a no-op: the ledger's
    unique index is (fight_id, source, bout_order), so re-observing the same
    order inserts nothing and a moved bout inserts a new row. There is no
    upsert here — an upsert would rewrite an observation, which the table's
    triggers reject anyway.
    """
    body = json.dumps(rows).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/rest/v1/{path}",
        data=body,
        method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=ignore-duplicates,return=representation",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return len(json.loads(resp.read().decode("utf-8")))


def require_ledger(base_url: str, key: str) -> None:
    """Stop unless the ledger exists. Never create it."""
    try:
        rest_get(base_url, key, LEDGER, {"select": "id", "limit": 1})
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        die(
            EXIT_CONFIG,
            f"`{LEDGER}` is not readable (HTTP {e.code}). This script does not "
            f"create tables. Apply {MIGRATION} first.\n  {detail}"
        )


# ---------------------------------------------------------------------------
# Fetching the page
# ---------------------------------------------------------------------------
def fetch_page(ufc_event_id: str) -> str:
    url = UFCSTATS_EVENT.format(ufc_event_id=ufc_event_id)
    req = urllib.request.Request(
        url,
        headers={
            # UFCStats serves plain HTML; a browser-shaped UA is what the
            # existing scraper sends and what the site expects.
            "User-Agent": "Mozilla/5.0 (compatible; CannonFightLab/1.0; +https://cannonfightlab.com)",
            "Accept": "text/html",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read().decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# One event
# ---------------------------------------------------------------------------
def ingest_event(
    event: dict,
    base_url: str,
    key: str,
    execute: bool,
    page_html: str | None = None,
    log=print,
) -> str:
    """Returns one of: 'written', 'dry-run', 'refused', 'fetch-failed'."""
    eid = event["id"]
    label = f"{event['name']} ({event['event_date']}) [event_id={eid}]"
    log(f"\n== {label}")

    if page_html is None:
        try:
            page_html = fetch_page(event["ufc_event_id"])
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            log(f"   FETCH FAILED: {e}")
            return "fetch-failed"

    try:
        card = parse_event_page(page_html)
    except CardParseError as e:
        log(f"   PAGE UNREADABLE: {e}")
        return "fetch-failed"

    if card.ufc_event_id and card.ufc_event_id != event["ufc_event_id"]:
        # A redirect or a stale url would otherwise write one card's order onto
        # another card's fights.
        log(
            f"   REFUSED: page is event {card.ufc_event_id}, expected "
            f"{event['ufc_event_id']}"
        )
        return "refused"

    fights = [
        FightRow(id=f["id"], ufc_fight_id=f["ufc_fight_id"], event_id=f["event_id"])
        for f in rest_get(
            base_url, key, "fights",
            {"select": "id,ufc_fight_id,event_id", "event_id": f"eq.{eid}", "limit": 200},
        )
    ]

    try:
        rows = build_rows(card, fights, eid)
    except BoutOrderRefused as e:
        log(f"   REFUSED: {e}")
        return "refused"

    log(f"   {len(rows)} bouts, first walkout first:")
    log(describe(rows, card))

    unlisted = len(fights) - len(rows)
    if unlisted > 0:
        # Expected and not an error: bookings that fell off the card stay in
        # `fights` forever. They get no order row, which is the point.
        log(f"   note: {unlisted} fight row(s) on this event are not on the page "
            f"(dead bookings) — no order written for them")

    if not execute:
        log("   DRY RUN — nothing written. Pass --execute to insert.")
        return "dry-run"

    inserted = rest_insert(base_url, key, LEDGER, [r.to_payload() for r in rows])
    log(f"   inserted {inserted} new observation(s); "
        f"{len(rows) - inserted} already on record (unchanged order)")
    return "written"


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--event-id", type=int, help="CFL events.id; default is every upcoming card")
    ap.add_argument("--within-days", type=int, default=DEFAULT_WITHIN_DAYS,
                    help=f"upcoming window when --event-id is absent (default {DEFAULT_WITHIN_DAYS})")
    ap.add_argument("--from-file", type=Path,
                    help="read the page from disk instead of fetching; requires --event-id")
    ap.add_argument("--execute", action="store_true", help="write rows (default is a dry run)")
    args = ap.parse_args()

    if args.from_file and args.event_id is None:
        die(EXIT_CONFIG, "--from-file needs --event-id: a page on disk does not "
                         "say which CFL event it belongs to.")

    base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not base_url:
        die(EXIT_CONFIG, "SUPABASE_URL not set.")
    key = env_key()
    require_ledger(base_url, key)

    if args.event_id is not None:
        events = rest_get(base_url, key, "events",
                          {"select": "id,name,event_date,ufc_event_id,is_upcoming",
                           "id": f"eq.{args.event_id}"})
        if not events:
            die(EXIT_CONFIG, f"no event with id {args.event_id}")
    else:
        today = dt.date.today()
        horizon = today + dt.timedelta(days=args.within_days)
        events = rest_get(base_url, key, "events",
                          {"select": "id,name,event_date,ufc_event_id,is_upcoming",
                           "is_upcoming": "is.true",
                           "event_date": f"lte.{horizon.isoformat()}",
                           "order": "event_date.asc", "limit": 50})
        events = [e for e in events if e["event_date"] >= today.isoformat()]

    if not events:
        print("No events in scope. Nothing to do.")
        return EXIT_OK

    page_html = args.from_file.read_text(encoding="utf-8") if args.from_file else None

    print(f"{len(events)} event(s) in scope; source='{SOURCE}'; "
          f"{'EXECUTE' if args.execute else 'DRY RUN'}")
    outcomes = [
        ingest_event(e, base_url, key, args.execute, page_html=page_html)
        for e in events
    ]

    print("\n-- summary --")
    for state in ("written", "dry-run", "refused", "fetch-failed"):
        n = outcomes.count(state)
        if n:
            print(f"  {state}: {n}")

    if "refused" in outcomes:
        return EXIT_REFUSED
    if "fetch-failed" in outcomes:
        return EXIT_FETCH
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
