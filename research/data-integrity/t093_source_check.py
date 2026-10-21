#!/usr/bin/env python3
"""T-093 source check: does UFCStats publish round stats for the 21 early fights?

READ-ONLY. Fetches public UFCStats fight-details pages and reports what each one
contains. It writes nothing anywhere except a local JSON file and a folder of
the raw pages it fetched (both uploaded as a workflow artifact). It reads no
secret and never touches the CFL database.

The fight list below (CFL fight id -> UFCStats fight URL and the two names) was
read from production `fights` on 2026-10-21 with a SELECT. Two CONTROL fights
from the same era that DO have rounds in CFL are included, so that the parser
is shown to recognise round data when a page has it. If the controls come back
"no rounds", the parser is wrong and the whole result must be discarded.

Stdlib only. Polite: one request at a time, a pause between requests, a real
User-Agent, and a bounded retry.
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from html import unescape

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36 CannonFightLab-T093-source-check "
      "(+https://cannonfightlab.com)")
PAUSE_S = 3.0
RETRIES = 3

# (cfl_fight_id, role, ufcstats_url, fighter_a, fighter_b, event, date)
FIGHTS = [
    (8708, "target", "http://www.ufcstats.com/fight-details/b80e6a799c95d499", "Marcus Bossett", "Eldo Xavier Dias", "UFC 4: Revenge of the Warriors", "1994-12-16"),
    (8709, "target", "http://www.ufcstats.com/fight-details/a1db4c917777aa79", "Joe Charles", "Kevin Rosier", "UFC 4: Revenge of the Warriors", "1994-12-16"),
    (8688, "target", "http://www.ufcstats.com/fight-details/8e03db41687d9132", "Anthony Macias", "He-Man Gipson", "UFC 6: Clash of the Titans", "1995-07-14"),
    (8689, "target", "http://www.ufcstats.com/fight-details/b297c3e938e1005e", "Joel Sutton", "Jack McGlaughlin", "UFC 6: Clash of the Titans", "1995-07-14"),
    (8678, "target", "http://www.ufcstats.com/fight-details/e4fe950846b51bdf", "Onassis Parungao", "Francesco Maturi", "UFC 7: The Brawl in Buffalo", "1995-09-08"),
    (8679, "target", "http://www.ufcstats.com/fight-details/4b334c9727eee450", "Joel Sutton", "Geza Kalman", "UFC 7: The Brawl in Buffalo", "1995-09-08"),
    (8667, "target", "http://www.ufcstats.com/fight-details/7ffcc3a72e082ace", "Mark Hall", "Trent Jenkins", "UFC - Ultimate Ultimate '95", "1995-12-16"),
    (8668, "target", "http://www.ufcstats.com/fight-details/6449a1a9a69a830c", "Joe Charles", "Scott Bessac", "UFC - Ultimate Ultimate '95", "1995-12-16"),
    (8659, "target", "http://www.ufcstats.com/fight-details/5701dbbbfa4f8313", "Sam Adkins", "Keith Mielke", "UFC 8: David vs Goliath", "1996-02-16"),
    (8642, "target", "http://www.ufcstats.com/fight-details/f59b1215176636f6", "Sam Adkins", "Felix Lee Mitchell", "UFC 10: The Tournament", "1996-07-12"),
    (8633, "target", "http://www.ufcstats.com/fight-details/3badedeb2c5533f4", "Roberto Traven", "Dave Berry", "UFC 11: The Proving Ground", "1996-09-20"),
    (8634, "target", "http://www.ufcstats.com/fight-details/c413b0abc04358c3", "Scott Ferrozzo", "Sam Fulton", "UFC 11: The Proving Ground", "1996-09-20"),
    (8624, "target", "http://www.ufcstats.com/fight-details/2f449bd58b3d9a99", "Tai Bowden", "Jack Nilson", "UFC - Ultimate Ultimate '96", "1996-12-07"),
    (8625, "target", "http://www.ufcstats.com/fight-details/d93c8c77e1091a16", "Steve Nelmark", "Marcus Bossett", "UFC - Ultimate Ultimate '96", "1996-12-07"),
    (8626, "target", "http://www.ufcstats.com/fight-details/a5c90086fb65f58e", "Mark Hall", "Felix Lee Mitchell", "UFC - Ultimate Ultimate '96", "1996-12-07"),
    (8615, "target", "http://www.ufcstats.com/fight-details/77bf1e37929b0d59", "Justin Martin", "Eric Martin", "UFC 12: Judgement Day", "1997-02-07"),
    (8616, "target", "http://www.ufcstats.com/fight-details/565ecefd8a37ad7e", "Nick Sanzo", "Jackie Lee", "UFC 12: Judgement Day", "1997-02-07"),
    (8574, "target", "http://www.ufcstats.com/fight-details/4bce0ce561a65288", "Chris Brennan", "Courtney Turner", "UFC 16: Battle in the Bayou", "1998-03-13"),
    (8575, "target", "http://www.ufcstats.com/fight-details/b80872821bc4f6ba", "Laverne Clark", "Josh Stuart", "UFC 16: Battle in the Bayou", "1998-03-13"),
    (8566, "target", "http://www.ufcstats.com/fight-details/8b258bbb37f74a66", "Andre Roberts", "Harry Moskowitz", "UFC 17: Redemption", "1998-05-15"),
    (8558, "target", "http://www.ufcstats.com/fight-details/635fbf57001897c7", "Cesar Marscucci", "Paulo Santos", "UFC - Ultimate Brazil", "1998-10-16"),
    # Controls: same era, CFL HAS rounds for these (2 rows each).
    (8559, "control", "http://www.ufcstats.com/fight-details/1d3c1dedfba6eddc", "Frank Shamrock", "Jeremy Horn", "UFC 17: Redemption", "1998-05-15"),
    (8560, "control", "http://www.ufcstats.com/fight-details/a4d8e991ec42b048", "Pete Williams", "Mark Coleman", "UFC 17: Redemption", "1998-05-15"),
]


# One cookie jar for the whole run, like a browser session. The first run
# (2026-10-21, run 39620094556) got HTTP 200 with a ~3 KB page holding no fight
# markup for all 23 URLs, controls included, so the response is now described
# (final URL, server, cookies set, a text snippet) rather than guessed at.
JAR = CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(JAR))
META = {}


def fetch(url):
    """Return (status, body_text, error). Never raises."""
    last_err = None
    for attempt in range(1, RETRIES + 1):
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.8",
        })
        try:
            with OPENER.open(req, timeout=30) as r:
                body = r.read().decode("utf-8", "replace")
                META[url] = {"final_url": r.geturl(),
                             "server": r.headers.get("Server"),
                             "content_type": r.headers.get("Content-Type"),
                             "cookies_set": sorted({c.name for c in JAR})}
                return r.status, body, None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, "", "HTTP 404"
            last_err = f"HTTP {e.code}"
        except Exception as e:  # network, DNS, timeout
            last_err = f"{type(e).__name__}: {e}"
        time.sleep(PAUSE_S * attempt)
    return None, "", last_err


def text(s):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def analyse(html):
    out = {}
    names = [text(m) for m in re.findall(
        r'class="b-fight-details__person-name"[^>]*>(.*?)</h3>', html, re.S)]
    out["names_on_page"] = names
    out["has_fight_details_block"] = 'b-fight-details__fight' in html
    out["totals_heading"] = bool(re.search(r">\s*Totals\s*<", html))
    out["per_round_heading_count"] = len(re.findall(r">\s*Per round\s*<", html, re.I))
    rounds = sorted({int(n) for n in re.findall(r">\s*Round\s+(\d+)\s*<", html)})
    out["round_labels_found"] = rounds
    tables = re.findall(r"<table[^>]*b-fight-details__table[^>]*>.*?</table>", html, re.S)
    out["stat_table_count"] = len(tables)
    cells = []
    for t in tables:
        body = re.search(r"<tbody.*?</tbody>", t, re.S)
        if body:
            cells += [text(c) for c in re.findall(
                r'<p class="b-fight-details__table-text"[^>]*>(.*?)</p>', body.group(0), re.S)]
    numeric = [c for c in cells if re.search(r"\d", c)]
    out["table_cells"] = len(cells)
    out["table_cells_with_digits"] = len(numeric)
    out["table_cells_dashes"] = sum(1 for c in cells if c in ("--", "---"))
    notes = sorted({text(m) for m in re.findall(
        r">([^<>]*not currently available[^<>]*)<", html, re.I)})
    out["not_available_notes"] = notes
    # The first table on the page is the fight Totals table. Digits there, beyond
    # the fighter-name cells, mean UFCStats publishes fight-level totals.
    totals_has_data = False
    if tables:
        body = re.search(r"<tbody.*?</tbody>", tables[0], re.S)
        if body:
            tc = [text(c) for c in re.findall(
                r'<p class="b-fight-details__table-text"[^>]*>(.*?)</p>', body.group(0), re.S)]
            totals_has_data = any(re.search(r"\d", c) for c in tc)
    out["totals_have_data"] = totals_has_data
    out["per_round_have_data"] = bool(rounds) and out["per_round_heading_count"] > 0 \
        and len(tables) >= 2 and len(numeric) > 0
    return out


def verdict(status, a):
    if status is None:
        return "fetch_failed"
    if status == 404 or not a.get("names_on_page"):
        return "page_missing"
    return "yes" if a["per_round_have_data"] else "no"


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "t093-out"
    os.makedirs(os.path.join(outdir, "pages"), exist_ok=True)
    results = []
    for i, (fid, role, url, fa, fb, ev, date) in enumerate(FIGHTS):
        if i:
            time.sleep(PAUSE_S)
        status, html, err = fetch(url)
        rec = {"cfl_fight_id": fid, "role": role, "url": url,
               "fighter_a": fa, "fighter_b": fb, "event": ev, "event_date": date,
               "http_status": status, "error": err, "bytes": len(html)}
        if html:
            rec["sha256"] = hashlib.sha256(html.encode()).hexdigest()
            with open(os.path.join(outdir, "pages", f"{fid}.html"), "w") as fh:
                fh.write(html)
        rec.update(META.get(url, {}))
        a = analyse(html) if html else {}
        rec.update(a)
        if html and not a.get("names_on_page"):
            rec["title"] = text((re.search(r"<title[^>]*>(.*?)</title>", html, re.S) or [None, ""])[1])
            rec["body_snippet"] = text(html)[:400]
            if i < 2 or role == "control":
                print(f"--- {fid}: no fight markup. final_url={rec.get('final_url')} "
                      f"server={rec.get('server')} cookies={rec.get('cookies_set')} "
                      f"title={rec['title']!r}\n    raw head: {html[:1500]!r}", flush=True)
        if a.get("names_on_page"):
            on = " ".join(a["names_on_page"]).lower()
            rec["names_match"] = all(n.split()[-1].lower() in on for n in (fa, fb))
        rec["source_has_rounds"] = verdict(status, a)
        rec["source_has_totals"] = (a.get("totals_have_data") if html else None)
        results.append(rec)
        print(f"{fid:>5} {role:<7} status={status} rounds={rec['source_has_rounds']:<12} "
              f"totals={rec['source_has_totals']} round_labels={a.get('round_labels_found')} "
              f"tables={a.get('stat_table_count')} digit_cells={a.get('table_cells_with_digits')} "
              f"names={a.get('names_on_page')} notes={a.get('not_available_notes')} err={err}",
              flush=True)

    controls = [r for r in results if r["role"] == "control"]
    parser_ok = bool(controls) and all(r["source_has_rounds"] == "yes" for r in controls)
    summary = {
        "task": "T-093",
        "checked_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "parser_validated_by_controls": parser_ok,
        "targets": len([r for r in results if r["role"] == "target"]),
        "counts": {},
        "results": results,
    }
    for r in results:
        if r["role"] == "target":
            k = r["source_has_rounds"]
            summary["counts"][k] = summary["counts"].get(k, 0) + 1
    with open(os.path.join(outdir, "t093_source_check.json"), "w") as fh:
        json.dump(summary, fh, indent=2)
    print("JSON_BEGIN")
    print(json.dumps(summary, indent=1))
    print("JSON_END")
    print(f"parser_validated_by_controls={parser_ok} counts={summary['counts']}")
    # Exit non-zero only when the check itself could not be trusted.
    if not parser_ok:
        print("CONTROLS FAILED: parser or fetch not trustworthy; do not use this result.")
        sys.exit(2)


if __name__ == "__main__":
    main()
