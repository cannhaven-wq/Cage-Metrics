#!/usr/bin/env python3
"""T-093: an independent second source for the 21 early fights without rounds.

READ-ONLY. Uses the official MediaWiki API (en.wikipedia.org/w/api.php,
action=parse, prop=wikitext) with a descriptive User-Agent, one request at a
time with a pause. Reads no secret, touches no CFL database, writes only a
local JSON file.

WHAT THIS CAN AND CANNOT SHOW
  Wikipedia's results table gives, per bout: that it happened, the method, the
  round and the time, and often a note such as "alternate bout". That tells us
  whether a bout ran in rounds at all (1994-96 tournament bouts were mostly a
  single period) and whether CFL's result row agrees with a second source.
  It does NOT carry strike, takedown or control statistics, so it can never
  confirm or deny that per-round STATISTICS exist anywhere. That question stays
  "unverified" unless UFCStats itself can be read.

Why a second source: UFCStats answers a plain HTTP client from GitHub Actions
with HTTP 200 and a "Checking your browser..." JavaScript page (runs
39620094556 and 39620705070). See t093_source_check.py.
"""
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from difflib import SequenceMatcher

API = "https://en.wikipedia.org/w/api.php"
UA = ("CannonFightLab-T093-source-check/1.0 (https://cannonfightlab.com; "
      "read-only data-integrity check of 21 UFC bouts, 1994-1998) python-urllib")
PAUSE_S = 2.0

# Candidate article titles per CFL event; the API follows redirects. If none
# hold both fighters, a search is tried and its top hits are checked.
EVENTS = {
    "UFC 4: Revenge of the Warriors": ["UFC 4"],
    "UFC 6: Clash of the Titans": ["UFC 6"],
    "UFC 7: The Brawl in Buffalo": ["UFC 7"],
    "UFC - Ultimate Ultimate '95": ["Ultimate Ultimate 1995", "Ultimate Ultimate '95", "UFC 7.5"],
    "UFC 8: David vs Goliath": ["UFC 8"],
    "UFC 10: The Tournament": ["UFC 10"],
    "UFC 11: The Proving Ground": ["UFC 11"],
    "UFC - Ultimate Ultimate '96": ["Ultimate Ultimate 1996", "Ultimate Ultimate '96", "UFC 11.5"],
    "UFC 12: Judgement Day": ["UFC 12"],
    "UFC 16: Battle in the Bayou": ["UFC 16"],
    "UFC 17: Redemption": ["UFC 17"],
    "UFC - Ultimate Brazil": ["UFC Brazil", "Ultimate Brazil", "UFC 17.5"],
}

# (cfl_id, fighter_a, fighter_b, event, cfl_method, cfl_end_round, cfl_end_time)
# read from production `fights` with a SELECT on 2026-10-21.
FIGHTS = [
    (8708, "Marcus Bossett", "Eldo Xavier Dias", "UFC 4: Revenge of the Warriors", "KO/TKO", 1, "4:55"),
    (8709, "Joe Charles", "Kevin Rosier", "UFC 4: Revenge of the Warriors", "Submission", 1, "0:14"),
    (8688, "Anthony Macias", "He-Man Gipson", "UFC 6: Clash of the Titans", "KO/TKO", 1, "3:06"),
    (8689, "Joel Sutton", "Jack McGlaughlin", "UFC 6: Clash of the Titans", "KO/TKO", 1, "2:01"),
    (8678, "Onassis Parungao", "Francesco Maturi", "UFC 7: The Brawl in Buffalo", "KO/TKO", 1, "5:26"),
    (8679, "Joel Sutton", "Geza Kalman", "UFC 7: The Brawl in Buffalo", "TKO - Doctor's Stoppage", 1, "0:48"),
    (8667, "Mark Hall", "Trent Jenkins", "UFC - Ultimate Ultimate '95", "Submission", 1, "5:29"),
    (8668, "Joe Charles", "Scott Bessac", "UFC - Ultimate Ultimate '95", "Submission", 1, "4:38"),
    (8659, "Sam Adkins", "Keith Mielke", "UFC 8: David vs Goliath", "KO/TKO", 1, "0:50"),
    (8642, "Sam Adkins", "Felix Lee Mitchell", "UFC 10: The Tournament", "Decision - Unanimous", 2, "3:00"),
    (8633, "Roberto Traven", "Dave Berry", "UFC 11: The Proving Ground", "KO/TKO", 1, "1:33"),
    (8634, "Scott Ferrozzo", "Sam Fulton", "UFC 11: The Proving Ground", "Submission", 1, "1:45"),
    (8624, "Tai Bowden", "Jack Nilson", "UFC - Ultimate Ultimate '96", "KO/TKO", 1, "4:46"),
    (8625, "Steve Nelmark", "Marcus Bossett", "UFC - Ultimate Ultimate '96", "Submission", 1, "1:37"),
    (8626, "Mark Hall", "Felix Lee Mitchell", "UFC - Ultimate Ultimate '96", "KO/TKO", 1, "1:45"),
    (8615, "Justin Martin", "Eric Martin", "UFC 12: Judgement Day", "Submission", 1, "0:14"),
    (8616, "Nick Sanzo", "Jackie Lee", "UFC 12: Judgement Day", "KO/TKO", 1, "0:48"),
    (8574, "Chris Brennan", "Courtney Turner", "UFC 16: Battle in the Bayou", "Submission", 1, "1:20"),
    (8575, "Laverne Clark", "Josh Stuart", "UFC 16: Battle in the Bayou", "KO/TKO", 1, "1:15"),
    (8566, "Andre Roberts", "Harry Moskowitz", "UFC 17: Redemption", "Decision - Unanimous", 2, "3:00"),
    (8558, "Cesar Marscucci", "Paulo Santos", "UFC - Ultimate Brazil", "KO/TKO", 1, "10:27"),
]


def get(params):
    q = urllib.parse.urlencode(dict(params, format="json", formatversion="2"))
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8")), None
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            time.sleep(PAUSE_S * (attempt + 2))
    return None, err


def fold(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def tokens(s):
    return re.findall(r"[a-z][a-z'\-]+", fold(s))


def name_hit(name, row_tokens):
    """Best fuzzy match of the fighter's surname against the row's words."""
    last = tokens(name)[-1]
    best = max((SequenceMatcher(None, last, t).ratio() for t in row_tokens), default=0)
    return best


def strip_markup(s):
    s = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"\{\{flagicon\|[^}]*\}\}", "", s, flags=re.I)
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"'''?", "", s)
    s = re.sub(r"\{\{(?:sort|nowrap)\|(?:[^|}]*\|)?([^}]*)\}\}", r"\1", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


def rows_of(wikitext):
    """Table rows (split on |-) plus the nearest preceding section heading."""
    out = []
    heading = ""
    for part in re.split(r"\n\|-[^\n]*", wikitext):
        hs = re.findall(r"^=+\s*(.*?)\s*=+\s*$", part, re.M)
        cells = [strip_markup(c) for c in re.split(r"\|\||\n\s*[|!]", "\n" + part)]
        cells = [c for c in cells if c and not c.startswith("{|") and not c.startswith("class=")]
        out.append({"heading": heading, "cells": cells, "raw": part.strip()[:600]})
        if hs:
            heading = hs[-1]
    return out


def rules_sentences(wikitext):
    text = strip_markup(re.sub(r"\{\|.*?\|\}", " ", wikitext, flags=re.S))
    sents = re.split(r"(?<=[.!?])\s+", text)
    keep = [s for s in sents if re.search(r"\b(round|rounds|time limit|overtime|no time limit|alternate)\b", s, re.I)]
    return [s[:300] for s in keep[:6]]


def parse_page(title):
    data, err = get({"action": "parse", "page": title, "prop": "wikitext|revid", "redirects": "1"})
    if not data or "parse" not in data:
        return None, err or (data or {}).get("error", {}).get("info", "no parse")
    p = data["parse"]
    return {"title": p.get("title"), "pageid": p.get("pageid"), "revid": p.get("revid"),
            "wikitext": p.get("wikitext", "")}, None


def find_row(page, fa, fb):
    best = None
    for r in rows_of(page["wikitext"]):
        toks = [t for c in r["cells"] for t in tokens(c)]
        sa, sb = name_hit(fa, toks), name_hit(fb, toks)
        score = min(sa, sb)
        if best is None or score > best[0]:
            best = (score, r, sa, sb)
    return best


def round_time(cells):
    for i, c in enumerate(cells):
        if re.fullmatch(r"\d{1,2}:\d{2}", c):
            rnd = cells[i - 1] if i and re.fullmatch(r"\d|N/?A|—|-", cells[i - 1]) else None
            return rnd, c
    return None, None


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "t093_wikipedia_check.json"
    pages = {}
    page_log = {}
    for ev, cands in EVENTS.items():
        needed = [f for f in FIGHTS if f[3] == ev]
        tried = []
        chosen = None
        for title in cands:
            time.sleep(PAUSE_S)
            pg, err = parse_page(title)
            tried.append({"title": title, "resolved": pg and pg["title"], "error": err})
            if pg and all((find_row(pg, f[1], f[2]) or (0,))[0] >= 0.8 for f in needed):
                chosen = pg
                break
        if not chosen:
            time.sleep(PAUSE_S)
            data, err = get({"action": "query", "list": "search", "srsearch": f"{ev} 199", "srlimit": "3"})
            for hit in ((data or {}).get("query", {}).get("search", []) if data else []):
                time.sleep(PAUSE_S)
                pg, err = parse_page(hit["title"])
                tried.append({"title": hit["title"], "resolved": pg and pg["title"], "error": err, "via": "search"})
                if pg and all((find_row(pg, f[1], f[2]) or (0,))[0] >= 0.8 for f in needed):
                    chosen = pg
                    break
        pages[ev] = chosen
        page_log[ev] = {"tried": tried, "chosen": chosen and chosen["title"],
                        "revid": chosen and chosen["revid"],
                        "rules_text": rules_sentences(chosen["wikitext"]) if chosen else []}
        print(f"EVENT {ev!r}: page={page_log[ev]['chosen']!r} revid={page_log[ev]['revid']} tried={[t['title'] for t in tried]}", flush=True)
        for s in page_log[ev]["rules_text"]:
            print(f"    rules: {s}", flush=True)

    results = []
    for fid, fa, fb, ev, meth, rnd, tm in FIGHTS:
        pg = pages.get(ev)
        rec = {"cfl_fight_id": fid, "fighter_a": fa, "fighter_b": fb, "event": ev,
               "cfl_method": meth, "cfl_end_round": rnd, "cfl_end_time": tm,
               "wiki_page": pg and pg["title"], "wiki_revid": pg and pg["revid"]}
        if not pg:
            rec["wiki_status"] = "event_page_not_found"
        else:
            score, row, sa, sb = find_row(pg, fa, fb)
            if score < 0.8:
                rec["wiki_status"] = "bout_not_found_on_page"
                rec["best_partial_match"] = {"score": round(score, 2), "cells": row["cells"][:12]}
            else:
                w_rnd, w_time = round_time(row["cells"])
                rec.update({
                    "wiki_status": "bout_found",
                    "match_score": round(score, 2),
                    "wiki_row_cells": row["cells"][:14],
                    "wiki_section": row["heading"],
                    "wiki_round": w_rnd, "wiki_time": w_time,
                    "wiki_marks_alternate_or_prelim": bool(re.search(
                        r"alternate|reserve|prelim|non-televised|untelevised|superfight|dark",
                        " ".join(row["cells"]) + " " + row["heading"], re.I)),
                    "time_agrees_with_cfl": (w_time == tm) if w_time else None,
                    "round_agrees_with_cfl": (str(rnd) == w_rnd) if w_rnd and w_rnd.isdigit() else None,
                })
        # Wikipedia never carries strike/takedown statistics; this cannot move.
        rec["per_round_statistics_at_source"] = "unverified"
        results.append(rec)
        print(f"{fid} {fa} vs {fb}: {rec['wiki_status']} round={rec.get('wiki_round')} time={rec.get('wiki_time')} "
              f"(cfl {rnd}/{tm}) section={rec.get('wiki_section')!r} alt/prelim={rec.get('wiki_marks_alternate_or_prelim')} "
              f"row={rec.get('wiki_row_cells') or rec.get('best_partial_match')}", flush=True)

    summary = {
        "task": "T-093",
        "source": "Wikipedia via the MediaWiki API (action=parse, prop=wikitext)",
        "checked_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "what_this_cannot_show": "per-round strike/takedown/control statistics; stays unverified",
        "counts": {},
        "events": page_log,
        "results": results,
    }
    for r in results:
        summary["counts"][r["wiki_status"]] = summary["counts"].get(r["wiki_status"], 0) + 1
    with open(out_path, "w") as fh:
        json.dump(summary, fh, indent=1)
    print("WIKI_JSON_BEGIN")
    print(json.dumps(summary, indent=1))
    print("WIKI_JSON_END")
    print("counts:", summary["counts"])


if __name__ == "__main__":
    main()
