#!/usr/bin/env python3
"""Probe candidate running-order sources from a GitHub runner (T-030).

UFCStats answers GitHub's runners with an HTTP 200 anti-bot page, so the
ingester cannot read it from Actions. This asks the alternatives and reports
what actually came back. It writes nothing anywhere except stdout and --out-dir.

Findings so far (2026-10-21), each from a run of this probe:
  * site.api.espn.com            -> HTTP 403 Access Denied (run 39621346144)
  * site.web.api.espn.com        -> HTTP 200, scoreboard JSON with every bout
                                    in walkout order and section start times
                                    (run 39622101981); /summary -> 404
  * sports.core.api.espn.com     -> HTTP 200 (index only)
  * en.wikipedia.org/w/api.php   -> HTTP 200, the event article's wikitext
Not probed: UFC.com — its Terms of Use prohibit automated access.

For each source it prints a FIXTURE: the raw response cut down by the same
helpers the adapters use (`sources.espn_fixture`,
`sources.wikipedia_results_section`), no value changed, with the sha256 of both
the raw response and the fixture. That is how the real samples in
`fixtures/` were recovered from the job log (the artifact store is out of the
agent sandbox's reach) and checked byte for byte.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cfl_engine.event_flow.sources import (  # noqa: E402
    SourceError,
    espn_fixture,
    espn_fixture_text,
    fixture_canonical_sha,
    parse_espn_scoreboard,
    wikipedia_results_section,
)

UA = "CannonFightLab-source-probe/1.0 (+https://cannonfightlab.com; research use)"
# site.api.espn.com answered runners 403 (run 39621346144); site.web.api answered 200.
ESPN = "https://site.web.api.espn.com/apis/site/v2/sports/mma/ufc"
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


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def emit(name: str, raw: str, fixture: str, out_dir: Path | None) -> None:
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / name).write_text(fixture, encoding="utf-8")
        (out_dir / ("raw_" + name)).write_text(raw, encoding="utf-8")
    canon = fixture_canonical_sha(name, fixture)
    print(f"-----BEGIN FIXTURE {name} raw_sha256={sha(raw)} raw_bytes={len(raw.encode())} "
          f"fixture_sha256={sha(fixture)} canonical_sha256={canon} "
          f"fixture_bytes={len(fixture.encode())}-----")
    print(fixture)
    print(f"-----END FIXTURE {name}-----")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", nargs="*", default=["20261017"],
                    help="ESPN scoreboard dates (YYYYMMDD) besides the current one")
    ap.add_argument("--wiki-titles", nargs="*",
                    default=["UFC Fight Night: Buckley vs. Malott", "UFC 333"])
    ap.add_argument("--out-dir", type=Path)
    args = ap.parse_args()
    report: list[str] = []

    for label, url in [("espn_scoreboard_current.json", f"{ESPN}/scoreboard")] + [
            (f"espn_scoreboard_{d}.json", f"{ESPN}/scoreboard?dates={d}") for d in args.dates]:
        status, ctype, body = fetch(url)
        report.append(f"{url}\n  HTTP {status} {ctype} {len(body.encode())} bytes")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            report.append(f"  not JSON: {body[:200]!r}")
            continue
        fixture = espn_fixture_text(espn_fixture(data))
        emit(label, body, fixture, args.out_dir)
        try:
            for card in parse_espn_scoreboard(data):
                report.append(f"  {card.event_name!r} {card.event_date}: {len(card.bouts)} bouts; "
                              f"first {card.first_walkout.matchup!r}, last "
                              f"{card.main_event.matchup!r}")
        except SourceError as e:
            report.append(f"  REFUSED: {e}")

    for title in args.wiki_titles:
        q = urllib.parse.urlencode({"action": "parse", "page": title, "prop": "wikitext|revid",
                                    "format": "json", "formatversion": 2, "redirects": 1})
        url = f"{WIKI}?{q}"
        status, ctype, body = fetch(url)
        report.append(f"{url}\n  HTTP {status} {ctype} {len(body.encode())} bytes")
        try:
            parse = json.loads(body).get("parse") or {}
        except json.JSONDecodeError:
            report.append(f"  not JSON: {body[:200]!r}")
            continue
        text = parse.get("wikitext", "")
        report.append(f"  title={parse.get('title')!r} revid={parse.get('revid')} "
                      f"wikitext={len(text)} chars sha256={sha(text)}")
        try:
            section = wikipedia_results_section(text)
        except SourceError as e:
            report.append(f"  {e}")
            continue
        name = "wikipedia_" + "".join(c if c.isalnum() else "_" for c in title).strip("_")
        emit(name + f"_rev{parse.get('revid')}.wikitext", text, section, args.out_dir)

    print("\n=== SOURCE PROBE REPORT ===")
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
