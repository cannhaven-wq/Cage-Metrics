#!/usr/bin/env python3
"""Probe candidate running-order sources from a GitHub runner (T-030).

UFCStats answers GitHub's runners with an HTTP 200 anti-bot page, so the
ingester cannot read it from Actions. This asks the alternatives, once each,
and reports what actually came back — status, size, whether it is a challenge
page, and the fields a running order would need (bout order, card segment,
start time). It writes nothing anywhere except stdout and --out-dir.

Not probed: UFC.com. Its Terms of Use prohibit automated access
(research/event-card/EVENT_CARD_PLAN_2026-10-15.md), so it is not a source this
repo may use without UFC's written permission.

Every sample is also printed as gzip+base64 between markers, so it can be
recovered from the job log when the artifact store is out of reach.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "CannonFightLab-source-probe/1.0 (+https://cannonfightlab.com; research use)"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/mma/ufc"
WIKI = "https://en.wikipedia.org/w/api.php"


def fetch(url: str) -> tuple[int, str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.headers.get("content-type", ""), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("content-type", ""), e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 - a probe reports, it does not raise
        return 0, "", f"{type(e).__name__}: {e}"


def dump(name: str, body: str, out_dir: Path | None) -> None:
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / name).write_text(body, encoding="utf-8")
    blob = base64.b64encode(gzip.compress(body.encode("utf-8"), 9)).decode()
    print(f"-----BEGIN SAMPLE {name}-----")
    for i in range(0, len(blob), 76):
        print(blob[i:i + 76])
    print(f"-----END SAMPLE {name}-----")


def describe_espn_event(ev: dict) -> list[str]:
    lines = [f"  event {ev.get('id')} {ev.get('name')!r} date={ev.get('date')}"]
    comps = ev.get("competitions") or []
    lines.append(f"  competitions: {len(comps)}; keys of first: "
                 f"{sorted((comps[0] if comps else {}).keys())}")
    for i, c in enumerate(comps):
        names = [((x.get("athlete") or {}).get("displayName")) for x in c.get("competitors", [])]
        seg = c.get("cardSegment")
        seg = seg.get("name") if isinstance(seg, dict) else seg
        lines.append(f"   [{i}] date={c.get('date')} startDate={c.get('startDate')} "
                     f"segment={seg!r} matchNumber={c.get('matchNumber')} "
                     f"type={(c.get('type') or {}).get('abbreviation')} "
                     f"status={((c.get('status') or {}).get('type') or {}).get('name')} "
                     f"{' vs '.join(n or '?' for n in names)}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", nargs="*", default=["20261017"],
                    help="ESPN scoreboard dates (YYYYMMDD) besides the current one")
    ap.add_argument("--wiki-title", default="UFC Fight Night: Buckley vs. Malott")
    ap.add_argument("--out-dir", type=Path)
    args = ap.parse_args()
    report: list[str] = []

    # ESPN: the current scoreboard, then dated ones, then each event's summary.
    seen_events: dict[str, dict] = {}
    for label, url in [("espn_scoreboard_current.json", f"{ESPN}/scoreboard")] + [
            (f"espn_scoreboard_{d}.json", f"{ESPN}/scoreboard?dates={d}") for d in args.dates]:
        status, ctype, body = fetch(url)
        report.append(f"{url}\n  HTTP {status} {ctype} {len(body.encode())} bytes")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            report.append(f"  not JSON: {body[:200]!r}")
            continue
        dump(label, body, args.out_dir)
        for ev in data.get("events", []):
            seen_events[str(ev.get("id"))] = ev
            report.extend(describe_espn_event(ev))
    for eid in list(seen_events)[:3]:
        url = f"{ESPN}/summary?event={eid}"
        status, ctype, body = fetch(url)
        report.append(f"{url}\n  HTTP {status} {ctype} {len(body.encode())} bytes")
        try:
            data = json.loads(body)
            report.append(f"  top-level keys: {sorted(data.keys())}")
            dump(f"espn_summary_{eid}.json", body, args.out_dir)
        except json.JSONDecodeError:
            report.append(f"  not JSON: {body[:200]!r}")

    # Other ESPN hosts, once each: is the 403 host-wide or path-specific?
    for url in ("https://site.web.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard",
                "https://sports.core.api.espn.com/v2/sports/mma/leagues/ufc/events"):
        status, ctype, body = fetch(url)
        report.append(f"{url}\n  HTTP {status} {ctype} {len(body.encode())} bytes "
                      f"{body[:120]!r}")

    # Wikipedia (MediaWiki API — documented, permitted with an identifying UA).
    titles = [args.wiki_title]
    # The next scheduled event, from the list article's "Scheduled events" section.
    try:
        q = urllib.parse.urlencode({"action": "parse", "page": "List of UFC events",
                                    "prop": "sections", "format": "json", "formatversion": 2})
        status, _, body = fetch(f"{WIKI}?{q}")
        sections = json.loads(body)["parse"]["sections"]
        idx = next(x["index"] for x in sections if "cheduled" in x["line"])
        q = urllib.parse.urlencode({"action": "parse", "page": "List of UFC events",
                                    "prop": "wikitext", "section": idx, "format": "json",
                                    "formatversion": 2})
        status, _, body = fetch(f"{WIKI}?{q}")
        text = json.loads(body)["parse"]["wikitext"]
        links = re.findall(r"\[\[(UFC[^\]|]+)", text)
        report.append(f"List of UFC events / scheduled: HTTP {status}, {len(links)} UFC links; "
                      f"first three: {links[:3]}; last three: {links[-3:]}")
        titles += links[-1:] + links[:1]
    except Exception as e:  # noqa: BLE001
        report.append(f"List of UFC events: could not read the scheduled section: {e}")
    for title in dict.fromkeys(titles):
        q = urllib.parse.urlencode({"action": "parse", "page": title, "prop": "wikitext|revid",
                                    "format": "json", "formatversion": 2, "redirects": 1})
        url = f"{WIKI}?{q}"
        status, ctype, body = fetch(url)
        report.append(f"{url}\n  HTTP {status} {ctype} {len(body.encode())} bytes")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            report.append(f"  not JSON: {body[:200]!r}")
            continue
        parse = data.get("parse") or {}
        text = parse.get("wikitext", "")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        name = "wikipedia_" + re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_") + ".wikitext"
        report.append(f"  title={parse.get('title')!r} revid={parse.get('revid')} "
                      f"error={data.get('error', {}).get('code')} wikitext={len(text)} chars "
                      f"sha256={digest}; 'Main card': {'Main card' in text}; "
                      f"'Preliminary card': {'Preliminary card' in text}")
        if text:
            if args.out_dir:
                args.out_dir.mkdir(parents=True, exist_ok=True)
                (args.out_dir / name).write_text(text, encoding="utf-8")
            # Raw, so it can be recovered from the job log and checked by sha256.
            print(f"-----BEGIN RAW {name} sha256={digest}-----")
            print(text)
            print(f"-----END RAW {name}-----")

    print("\n=== SOURCE PROBE REPORT ===")
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
