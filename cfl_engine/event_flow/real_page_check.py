#!/usr/bin/env python3
"""Check the running-order parser against REAL UFCStats pages (T-030).

Plain English
-------------
The ingester's parser was only ever tested against a page written by hand. The
one assumption that matters most — UFCStats lists the MAIN EVENT FIRST, so the
page has to be read bottom-up — has never been checked against the real site,
because this container cannot reach it.

This script does that check from somewhere that can (a GitHub Actions runner),
and writes down exactly what it saw. It does not touch the database, needs no
secret, and writes nothing but a JSON report.

How it checks the direction without a person
--------------------------------------------
Every UFC event is named after its main event: "UFC Fight Night: Buckley vs.
Malott". The page prints that title. So for each page:

  * the bout the parser puts LAST in walkout order (the highest bout_order,
    page row 0) must be the two fighters the title names, and
  * the bout it puts FIRST (bout_order 1) must NOT be.

If the title names the bottom row instead, the flip is backwards and the check
fails loudly. A title with no "A vs. B" (e.g. a numbered card sold on its
number) cannot confirm the direction and is reported as `unconfirmable`, never
as a pass.

What it refuses
---------------
It does not get past any bot wall. If UFCStats answers with an interstitial or
an error instead of the card, the report says so (`status: "page_unreadable"`)
and the run fails. A check that quietly passed on a challenge page would be the
exact silent failure this file exists to prevent.

  python cfl_engine/event_flow/real_page_check.py --out REAL_PAGE_CHECK.json
  python cfl_engine/event_flow/real_page_check.py --event <ufc_event_id> --event <...>
  python cfl_engine/event_flow/real_page_check.py --from-file page.html --event <id>
"""
from __future__ import annotations

import argparse
import datetime as dt
import html as htmlmod
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cfl_engine.event_flow.bout_order import walkout_order  # noqa: E402
from cfl_engine.event_flow.ufcstats_card import (  # noqa: E402
    CardParseError,
    parse_event_page,
)

BASE = "http://www.ufcstats.com"
EVENT_URL = BASE + "/event-details/{ufc_event_id}"
COMPLETED_URL = BASE + "/statistics/events/completed"
UPCOMING_URL = BASE + "/statistics/events/upcoming"
USER_AGENT = "Mozilla/5.0 (compatible; CannonFightLab/1.0; +https://cannonfightlab.com)"
TIMEOUT = 60

# Direction verdicts.
CONFIRMED = "confirmed"           # title names page row 0, not the bottom row
CONTRADICTED = "contradicted"     # title names the bottom row: the flip is backwards
UNCONFIRMABLE = "unconfirmable"   # title names no matchup we can find on the card

TITLE_RE = re.compile(
    r'<span[^>]*class="[^"]*b-content__title-highlight[^"]*"[^>]*>(.*?)</span>',
    re.S | re.I,
)
LISTING_ROW_RE = re.compile(
    r'href="(?:https?://(?:www\.)?ufcstats\.com)?/event-details/([0-9a-f]{16})"[^>]*>'
    r'\s*(.*?)\s*</a>.*?<span class="b-statistics__date">\s*(.*?)\s*</span>',
    re.S | re.I,
)
CHALLENGE_MARKERS = ("checking your browser", "challenge", "captcha", "cf-chl",
                     "just a moment")


def fetch(url: str) -> tuple[int, str]:
    """Plain GET with an honest User-Agent. Returns (status, body)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "text/html"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# Pure functions — everything below this line is tested without a network
# ---------------------------------------------------------------------------
def fold(text: str) -> str:
    """Lowercase, strip accents and punctuation: 'Jr.' and 'Ñ' must not decide a check."""
    nfkd = unicodedata.normalize("NFKD", text)
    plain = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", plain.lower()).split())


def page_title(page_html: str) -> str | None:
    m = TITLE_RE.search(page_html)
    if not m:
        return None
    text = re.sub(r"<[^>]+>", " ", m.group(1))
    return " ".join(htmlmod.unescape(text).split()) or None


def title_matchup(title: str | None) -> tuple[str, str] | None:
    """'UFC Fight Night: Buckley vs. Malott' -> ('buckley', 'malott')."""
    if not title:
        return None
    tail = title.split(":", 1)[1] if ":" in title else title
    parts = re.split(r"\s+vs\.?\s+", tail, flags=re.I)
    if len(parts) != 2:
        return None
    a, b = (fold(p) for p in parts)
    return (a, b) if a and b else None


def _names_match(title_side: str, fighter_name: str) -> bool:
    """A title side ('de ridder', 'buckley') is the tail of the full name."""
    full = fold(fighter_name)
    return bool(title_side) and (full == title_side or full.endswith(" " + title_side))


def bout_matches_title(fighter_names: tuple[str, ...], matchup: tuple[str, str]) -> bool:
    a, b = matchup
    n1, n2 = fighter_names
    return ((_names_match(a, n1) and _names_match(b, n2))
            or (_names_match(a, n2) and _names_match(b, n1)))


def looks_like_challenge(page_html: str) -> bool:
    low = page_html[:20000].lower()
    return "fight-details" not in low and any(m in low for m in CHALLENGE_MARKERS)


def check_page(ufc_event_id: str, page_html: str, http_status: int | None = None) -> dict:
    """One page -> one report entry. Never raises; an unreadable page is a verdict."""
    entry: dict = {
        "ufc_event_id": ufc_event_id,
        "url": EVENT_URL.format(ufc_event_id=ufc_event_id),
        "http_status": http_status,
        "bytes": len(page_html.encode("utf-8")),
    }
    if http_status is not None and http_status != 200:
        entry.update(status="page_unreadable",
                     reason=f"HTTP {http_status}"
                            + (" (bot-wall interstitial)" if looks_like_challenge(page_html) else ""))
        return entry
    if looks_like_challenge(page_html):
        entry.update(status="page_unreadable",
                     reason="UFCStats served a bot-wall interstitial, not the card. "
                            "Not bypassed; no order read.")
        return entry
    try:
        card = parse_event_page(page_html)
    except CardParseError as e:
        entry.update(status="parse_error", reason=str(e))
        return entry

    title = page_title(page_html)
    n = len(card.bouts)
    bouts = sorted(
        ({"bout_order": walkout_order(b.page_index, n),
          "page_row": b.page_index,
          "ufc_fight_id": b.ufc_fight_id,
          "matchup": b.matchup}
         for b in card.bouts),
        key=lambda r: r["bout_order"],
    )
    top, bottom = card.bouts[0], card.bouts[-1]
    matchup = title_matchup(title)
    if matchup is None:
        direction, why = UNCONFIRMABLE, "the page title names no 'A vs. B' matchup"
    elif bout_matches_title(top.fighter_names, matchup) and not (
            n > 1 and bout_matches_title(bottom.fighter_names, matchup)):
        direction, why = CONFIRMED, (
            f"title names {top.matchup!r}, which the parser puts at bout {n} of {n} "
            f"(last to walk out = main event)")
    elif n > 1 and bout_matches_title(bottom.fighter_names, matchup):
        direction, why = CONTRADICTED, (
            f"title names {bottom.matchup!r}, which the parser puts at bout 1 — "
            f"the flip is backwards")
    else:
        direction, why = UNCONFIRMABLE, (
            "the title's matchup is not the top or bottom row (main event changed "
            "after the event was named?)")

    page_event_id_ok = card.ufc_event_id in (None, ufc_event_id)
    entry.update(
        status="parsed" if page_event_id_ok else "wrong_event",
        page_event_id=card.ufc_event_id,
        title=title,
        n_bouts=n,
        main_event_bout_order=n,
        main_event_matchup=top.matchup,
        first_walkout_matchup=bottom.matchup,
        direction=direction,
        direction_reason=why,
        bouts=bouts,
    )
    return entry


def parse_listing(page_html: str) -> list[dict]:
    """An events listing page -> [{ufc_event_id, name, date}] in page order."""
    out, seen = [], set()
    for eid, name, date in LISTING_ROW_RE.findall(page_html):
        if eid in seen:
            continue
        seen.add(eid)
        out.append({"ufc_event_id": eid,
                    "name": " ".join(htmlmod.unescape(re.sub(r"<[^>]+>", " ", name)).split()),
                    "date": " ".join(date.split())})
    return out


def _listing_date(row: dict) -> dt.date | None:
    try:
        return dt.datetime.strptime(row["date"], "%B %d, %Y").date()
    except (KeyError, ValueError):
        return None


def pick_events(completed: list[dict], upcoming: list[dict], today: dt.date) -> list[dict]:
    """The most recent completed event and the next upcoming one.

    The completed listing's top row is often the NEXT event (UFCStats pins it),
    so 'completed' means dated before today, not 'first row of that page'.
    """
    picked = []
    done = [r for r in completed if (_listing_date(r) or today) < today]
    if done:
        picked.append({**max(done, key=_listing_date), "kind": "completed"})
    ahead = [r for r in upcoming if (_listing_date(r) or dt.date.min) >= today]
    if ahead:
        picked.append({**min(ahead, key=_listing_date), "kind": "upcoming"})
    return picked


def build_report(entries: list[dict], run: dict) -> dict:
    """The record `ingest_bout_order.require_real_page_verified` reads.

    The five top-level fields it demands describe the COMPLETED event, because
    a settled card is the one whose order can no longer move under the check.
    The per-page detail for every event read is under `events`.
    """
    ok = [e for e in entries if e.get("status") == "parsed"]
    anchor = next((e for e in ok if e.get("kind") == "completed"), ok[0] if ok else None)
    verdicts = {e.get("direction") for e in ok}
    passed = bool(ok) and len(ok) == len(entries) and CONTRADICTED not in verdicts \
        and CONFIRMED in verdicts
    report = {
        "check": "T-030 real-page check: UFCStats running-order parser against live pages",
        "result": "pass" if passed else "fail",
        "checked_by": run.get("checked_by"),
        "checked_at": run.get("checked_at"),
        "ufc_event_id": anchor["ufc_event_id"] if anchor else None,
        "cfl_event_id": None,
        "main_event_bout_order": anchor["main_event_bout_order"] if anchor else None,
        "first_walkout_matchup": anchor["first_walkout_matchup"] if anchor else None,
        "main_event_matchup": anchor["main_event_matchup"] if anchor else None,
        "direction_check": (
            "automated: each page's title names its main event; the parser must put "
            "that bout last in walkout order (highest bout_order) and not first"),
        "run": run,
        "events": entries,
    }
    if not passed:
        # A failed check must not satisfy the ingester's gate.
        for k in ("checked_by", "ufc_event_id", "main_event_bout_order",
                  "first_walkout_matchup"):
            report[k] = None
    return report


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--event", action="append", default=[],
                    help="UFCStats event id; default = latest completed + next upcoming")
    ap.add_argument("--from-file", type=Path, help="read one page from disk (needs one --event)")
    ap.add_argument("--out", type=Path, default=Path("REAL_PAGE_CHECK.json"))
    ap.add_argument("--checked-by", default="automated (real_page_check.py)")
    args = ap.parse_args()

    now = dt.datetime.now(dt.timezone.utc)
    run = {"checked_by": args.checked_by,
           "checked_at": now.date().isoformat(),
           "checked_at_utc": now.isoformat(timespec="seconds"),
           "user_agent": USER_AGENT}
    entries: list[dict] = []

    if args.from_file:
        if len(args.event) != 1:
            print("--from-file needs exactly one --event", file=sys.stderr)
            return 2
        entries.append({**check_page(args.event[0], args.from_file.read_text("utf-8")),
                        "kind": "file"})
    else:
        if args.event:
            targets = [{"ufc_event_id": e, "kind": "given"} for e in args.event]
        else:
            listings = {}
            for kind, url in (("completed", COMPLETED_URL), ("upcoming", UPCOMING_URL)):
                status, body = fetch(url)
                rows = parse_listing(body) if status == 200 else []
                listings[kind] = rows
                run[f"{kind}_listing"] = {"url": url, "http_status": status,
                                          "events_found": len(rows),
                                          "challenge": looks_like_challenge(body)}
            targets = pick_events(listings["completed"], listings["upcoming"], now.date())
            if not targets:
                entries.append({"status": "page_unreadable",
                                "reason": "no events found on the UFCStats listings"})
        for t in targets:
            status, body = fetch(EVENT_URL.format(ufc_event_id=t["ufc_event_id"]))
            entry = check_page(t["ufc_event_id"], body, status)
            entries.append({**entry, "kind": t["kind"],
                            **({"listing_name": t["name"], "listing_date": t["date"]}
                               if "name" in t else {})})

    report = build_report(entries, run)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    for e in entries:
        print(f"\n[{e.get('kind')}] {e.get('title') or e.get('ufc_event_id')}: "
              f"{e.get('status')} — {e.get('direction', '')} {e.get('direction_reason') or e.get('reason', '')}",
              file=sys.stderr)
        for b in e.get("bouts", []):
            print(f"   {b['bout_order']:>2}  {b['matchup']}", file=sys.stderr)
    return 0 if report["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
