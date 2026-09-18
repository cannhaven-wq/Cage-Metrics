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
import re
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
    Observation,
    build_rows,
    describe,
    plan_append,
)
from cfl_engine.event_flow.ufcstats_card import (  # noqa: E402
    CardParseError,
    parse_event_page,
)
from cfl_engine.event_flow.retirement import (  # noqa: E402
    REQUIRED_CONFIRMATIONS,
    plan_retirements,
)

LEDGER = "fight_bout_order"
MIGRATION = "research/clv/proposed_2026-09-16_event_flow.sql"
MIGRATION_FIX = "cfl_engine/event_flow/MIGRATION_ADJUSTMENT.md"
# A record that a human read one REAL UFCStats page and confirmed the printed
# running order against the card. Writing is refused until it exists — see
# `require_real_page_verified`.
VERIFICATION = Path(__file__).parent / "REAL_PAGE_CHECK.json"
# A card is at most 18 bouts; an event with this many ledger rows is either a
# runaway loop or a read that needs paging. Either way, stop rather than compute
# "the latest observation" from a set that might be truncated.
MAX_LEDGER_ROWS = 1000
UFCSTATS_EVENT = "http://www.ufcstats.com/event-details/{ufc_event_id}"
TIMEOUT = 60
DEFAULT_WITHIN_DAYS = 45

# Exit codes, so a workflow can tell "nothing to do" from "the ledger is missing"
# from "a card would not link".
EXIT_OK = 0
EXIT_CONFIG = 2          # env/table missing — fix the setup
EXIT_REFUSED = 3         # a card would not link completely — fix the data
EXIT_FETCH = 4           # the page could not be fetched or read
EXIT_LEDGER_SHAPE = 5    # the ledger still carries the unique index — see MIGRATION_FIX


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


def rest_append(base_url: str, key: str, path: str, rows: list[dict]) -> int:
    """Append an observation. Plain insert — no conflict resolution of any kind.

    There is deliberately no `resolution=ignore-duplicates` here. That header is
    what broke 5 -> 6 -> 5: it told the database to silently drop an observation
    because an identical-looking one existed in the past, which is exactly the
    observation we most needed to keep. Whether anything changed is decided
    before this is called, by reading the ledger.

    And no `merge-duplicates` either — that is an UPDATE, which an append-only
    table rejects by trigger and which would be wrong even if it did not.

    All the rows go in one POST, so they share one transaction and therefore one
    `now()`: a card observation has a single `observed_at` and reads back as one
    coherent snapshot.
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
            "Prefer": "return=representation",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return len(json.loads(resp.read().decode("utf-8")))


def read_ledger(base_url: str, key: str, event_id: int) -> list[Observation]:
    """Every observation on record for this event, newest first.

    Newest first matters: it means a truncated read still contains the latest
    row for each fight. The truncation guard below is belt and braces on top of
    that, because "probably contains" is not the standard for a ledger.
    """
    rows = rest_get(
        base_url, key, LEDGER,
        {"select": "id,fight_id,bout_order,observed_at,source",
         "event_id": f"eq.{event_id}",
         "source": f"eq.{SOURCE}",
         "order": "observed_at.desc,id.desc",
         "limit": MAX_LEDGER_ROWS},
    )
    if len(rows) >= MAX_LEDGER_ROWS:
        die(EXIT_CONFIG,
            f"event {event_id} has {MAX_LEDGER_ROWS}+ rows in `{LEDGER}`. A card "
            f"is at most 18 bouts, so this is a runaway. Refusing to decide what "
            f"changed from a possibly truncated read.")
    return [
        Observation(
            id=r["id"], fight_id=r["fight_id"], bout_order=r["bout_order"],
            observed_at=parse_ts(r["observed_at"]), source=r["source"],
        )
        for r in rows
    ]


FRACTION = re.compile(r"\.(\d+)")


def parse_ts(value: str) -> dt.datetime:
    """Postgres timestamptz as PostgREST renders it.

    Postgres emits fractional seconds of whatever width it needs — `.5`,
    `.512482` — and older Pythons reject both a trailing `Z` and any width that
    is not exactly 3 or 6 digits. Both are normalised here rather than trusting
    `fromisoformat` with whatever happens to arrive, because a parse failure in
    the middle of deciding "has this card changed?" would be a bad place to
    discover a format difference.

    A naive timestamp is read as UTC: the column is `timestamptz` and PostgREST
    always renders an offset, so naive means something already went wrong, and
    assuming UTC keeps the comparison total rather than raising on a subtraction.
    """
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    text = FRACTION.sub(lambda m: "." + m.group(1)[:6].ljust(6, "0"), text, count=1)
    parsed = dt.datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def unique_index_still_present(error_body: str) -> bool:
    """Does this failure mean the ledger still forbids a returning bout?

    Postgres raises 23505 on a unique violation; PostgREST passes the index name
    through. If that name is the one the CLV migration creates, this is not a
    bug in the card we just read — it is the ledger shape, and it is fixable
    only in the migration.
    """
    return "23505" in error_body or "fight_bout_order_unique_idx" in error_body


def require_real_page_verified() -> None:
    """Refuse to write until somebody has read a real UFCStats page.

    The parser is tested against a fixture that was written by hand to the
    markup contract, because this container cannot reach ufcstats.com. A fixture
    built from an assumption cannot test the assumption. The specific assumption
    is the one that matters most and is invisible when wrong: that the page
    lists the main event FIRST, which is why bout_order counts up from the
    bottom of the page.

    If that is backwards, every card in the ledger is inverted, every close
    reference derived from it is attached to the wrong fight, and nothing fails.

    So writing is gated on a file recording that a human read one real page and
    confirmed the direction. A dry run — which is how you produce that
    confirmation — is never gated.
    """
    if VERIFICATION.is_file():
        try:
            record = json.loads(VERIFICATION.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            die(EXIT_CONFIG, f"{VERIFICATION.name} is not valid JSON: {e}")
        missing = [k for k in ("ufc_event_id", "checked_by", "checked_at",
                               "main_event_bout_order", "first_walkout_matchup")
                   if not record.get(k)]
        if missing:
            die(EXIT_CONFIG,
                f"{VERIFICATION.name} is missing {missing}. The record has to say "
                f"which page was read, by whom, when, and what the direction "
                f"came out as — otherwise it asserts nothing.")
        return

    die(EXIT_CONFIG,
        "Refusing to write: no real UFCStats page has been checked yet.\n"
        "  The parser is only tested against a hand-built fixture, so the one "
        "assumption that matters — that the page lists the main event first — "
        "is still unverified, and getting it backwards inverts every card "
        "silently.\n"
        "  Do this once, somewhere with UFCStats access:\n"
        "    curl -s http://www.ufcstats.com/event-details/<ufc_event_id> > page.html\n"
        "    python cfl_engine/event_flow/ingest_bout_order.py \\\n"
        "        --event-id <cfl_event_id> --from-file page.html\n"
        "  Read the printed order against the real card. If bout 1 is the first "
        "prelim and the last line is the main event, record it in\n"
        f"    {VERIFICATION}\n"
        "  as {\"ufc_event_id\", \"cfl_event_id\", \"checked_by\", \"checked_at\", "
        "\"main_event_bout_order\", \"first_walkout_matchup\", \"notes\"}.\n"
        "  See cfl_engine/event_flow/README.md. The dry run itself is not gated.")


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
# ---------------------------------------------------------------------------
# Stale bookings: reading, reporting, applying
# ---------------------------------------------------------------------------
def _ledger_rows(observations: list[Observation]) -> list[dict]:
    """Observations -> the plain rows `retirement` reads.

    `observed_at` is normalised to a string because the retirement rule groups
    a card by that value, and two spellings of one instant would split a single
    append into two observations — which would hand a pending retirement a
    second confirmation it never earned.
    """
    return [{"fight_id": o.fight_id,
             "observed_at": o.observed_at.isoformat()
                            if hasattr(o.observed_at, "isoformat") else str(o.observed_at),
             "bout_order": o.bout_order}
            for o in observations]


def _read_fights(base_url: str, key: str, event_id: int) -> tuple[list[dict], bool]:
    """This event's fights, with `is_active` when the column exists.

    Returns (rows, column_present). The column is proposed in
    add_bout_order_migration.sql and unapplied, so its absence is the normal
    case today and must not be an error.
    """
    params = {"event_id": f"eq.{event_id}", "limit": 200}
    try:
        rows = rest_get(base_url, key, "fights",
                        {**params, "select": "id,ufc_fight_id,event_id,is_active"})
        return rows, True
    except urllib.error.HTTPError:
        rows = rest_get(base_url, key, "fights",
                        {**params, "select": "id,ufc_fight_id,event_id"})
        return rows, False


def _report_retirements(retire, active_column: bool, log=print) -> None:
    """Say what the card implies, whether or not anything can be written."""
    if retire.is_empty:
        return
    for fight_id, seen in retire.pending:
        log(f"   stale PENDING: fight {fight_id} absent from the latest {seen} "
            f"observation(s); {REQUIRED_CONFIRMATIONS} needed. One bad parse "
            f"looks exactly like this, so nothing is retired yet")
    if retire.deactivate:
        log(f"   stale CONFIRMED: {list(retire.deactivate)} — absent from the "
            f"latest {REQUIRED_CONFIRMATIONS} complete card observations")
    if retire.reactivate:
        log(f"   back on the card: {list(retire.reactivate)} — is_active would "
            f"return to true")
    if not active_column and (retire.deactivate or retire.reactivate):
        log(f"   note: `fights.is_active` does not exist, so nothing can be "
            f"flagged. Apply add_bout_order_migration.sql. The fight rows and "
            f"every prediction, quote and snapshot against them are untouched "
            f"either way.")


def _apply_retirements(base_url: str, key: str, retire, active_column: bool,
                       log=print) -> None:
    """Flip `is_active`, and nothing else, ever.

    This is the only write in this module that touches `fights`, and it writes
    exactly one boolean. The fight row is never deleted, its history in
    `fight_bout_order` is never rewritten, and no prediction, quote, snapshot or
    result is touched — a booking that was published was published.
    """
    if not (retire.deactivate or retire.reactivate):
        return
    if not active_column:
        log("   is_active not applied: the column does not exist yet")
        return
    for fight_id in retire.deactivate:
        _patch_fight(base_url, key, fight_id, False)
        log(f"   set is_active=false on fight {fight_id}")
    for fight_id in retire.reactivate:
        _patch_fight(base_url, key, fight_id, True)
        log(f"   set is_active=true on fight {fight_id}")


def _patch_fight(base_url: str, key: str, fight_id: int, is_active: bool) -> None:
    url = f"{base_url}/rest/v1/fights?id=eq.{fight_id}"
    body = json.dumps({"is_active": is_active}).encode()
    req = urllib.request.Request(url, data=body, method="PATCH", headers={
        "apikey": key, "Authorization": f"Bearer {key}",
        "Content-Type": "application/json", "Prefer": "return=minimal",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT):
        pass


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

    # `is_active` may not be on the table yet (add_bout_order_migration.sql is
    # unapplied). Ask for it, fall back without it, and carry "unknown" rather
    # than guessing — the plan then reports what it WOULD do instead of going
    # quiet, which is the useful behaviour before the column lands.
    raw, active_column = _read_fights(base_url, key, eid)
    fights = [
        FightRow(id=f["id"], ufc_fight_id=f["ufc_fight_id"], event_id=f["event_id"])
        for f in raw
    ]
    active_by_fight = {f["id"]: f.get("is_active") for f in raw} if active_column else {}

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

    # What does the ledger currently say, and does the page disagree with it?
    # This is the whole change-detection rule, and it compares against the
    # LATEST observation only. A position the card held at some point in the
    # past never blocks a later observation of the same position.
    ledger = read_ledger(base_url, key, eid)
    plan = plan_append(rows, ledger)
    log(f"   {plan.reason}")
    for line in plan.changes:
        log(f"     {line}")
    if plan.stale_fights:
        # The ledger has no way to say "this bout left the card", and inventing
        # one would record something we did not observe. Said out loud instead.
        log(f"   note: {len(plan.stale_fights)} fight(s) were ordered before and "
            f"are not on the page now — their last observation stands: "
            f"{list(plan.stale_fights)}")

    # --- stale bookings -----------------------------------------------------
    retire = plan_retirements(
        _ledger_rows(ledger),
        {r.fight_id for r in rows},
        active_by_fight,
    )
    _report_retirements(retire, active_column, log)

    # A pending retirement is a reason to append even when nothing moved. See
    # RetirementPlan's docstring: a stale fight contributes no change entry, so
    # without this the absence would sit at one confirmation for ever.
    should_append = plan.append or retire.awaiting_confirmation
    if not plan.append and retire.awaiting_confirmation:
        log("   appending anyway: a retirement is awaiting its second "
            "observation, and an unchanged card would never supply one")

    if not should_append:
        log("   nothing to append.")
        return "unchanged"

    if not execute:
        log(f"   DRY RUN — would append {len(rows)} row(s) as one observation. "
            f"Pass --execute to write.")
        if retire.deactivate:
            log(f"   DRY RUN — would set is_active=false on {list(retire.deactivate)}")
        if retire.reactivate:
            log(f"   DRY RUN — would set is_active=true on {list(retire.reactivate)}")
        return "dry-run"

    try:
        appended = rest_append(base_url, key, LEDGER, [r.to_payload() for r in rows])
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        if unique_index_still_present(detail):
            die(EXIT_LEDGER_SHAPE,
                f"`{LEDGER}` rejected this observation as a duplicate (HTTP "
                f"{e.code}). That is the ledger shape, not this card: "
                f"`fight_bout_order_unique_idx` on (fight_id, source, bout_order) "
                f"forbids a bout from ever returning to a position it held "
                f"before, so a 5 -> 6 -> 5 reshuffle cannot be recorded and the "
                f"ledger is left saying 6.\n"
                f"  Fix it in the migration: see {MIGRATION_FIX}.\n"
                f"  Nothing was written.\n  {detail}")
        raise
    log(f"   appended {appended} row(s) as one observation")

    # Re-plan against the ledger INCLUDING the observation just persisted.
    # "Absent from two persisted observations" has to be counted after the
    # second one exists, not before it — planning only beforehand would leave
    # every retirement a run late, and on a card that then stops changing it
    # would never arrive at all.
    retire = plan_retirements(
        _ledger_rows(read_ledger(base_url, key, eid)),
        {r.fight_id for r in rows},
        active_by_fight,
    )
    _apply_retirements(base_url, key, retire, active_column, log)
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
    if args.execute:
        require_real_page_verified()
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
    for state in ("written", "unchanged", "dry-run", "refused", "fetch-failed"):
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
