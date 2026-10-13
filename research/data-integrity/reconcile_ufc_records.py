"""
reconcile_ufc_records.py — T-083. Read-only.

Compares each sampled fighter's UFC bouts on UFCStats (the source both of our
tables were scraped from, and the reference the sport's own record keepers
use) against:

  * `fights`   — bout by bout, matched on fights.ufc_fight_id = the UFCStats
                 fight-details id, so a renamed fighter cannot mismatch;
  * `fighters` — the stored ufc_wins / ufc_losses / ufc_draws totals.

It writes nothing anywhere except its own report. Run by
.github/workflows/reconcile-ufc-records.yml, because the agent sessions that
maintain this repo cannot reach ufcstats.com.

Which fighters: FIGHTER_IDS (comma-separated) if set. Otherwise every fighter
on the next card's active bookings, plus a fixed set of champions with
well-known records, plus SAMPLE_SIZE (default 40) fighters drawn with a fixed
seed from everyone with a completed UFC fight in `fights`.

UFCStats sits behind a light proof-of-work page. This solves it the same way
cage-metrics-scrapper/challenge.py does — by doing the work, with an honest
User-Agent — and waits DELAY seconds between pages.

"Could not look" is reported as such, never as agreement.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sys
import time
from collections import Counter

import requests
from bs4 import BeautifulSoup

SUPA = "https://uftancejftcryfvbggll.supabase.co"
# The public, publishable key the website ships in _shared.js. Read access only,
# enforced by RLS.
KEY = "sb_publishable_boJGOA1CFN-SF14HHFGUAw_YEEm0DU8"
UA = "CannonFightLab/1.0 (record reconciliation; +https://cannonfightlab.com)"
DELAY = float(os.environ.get("DELAY", "1.5"))
SAMPLE_SIZE = int(os.environ.get("SAMPLE_SIZE") or "40")
WELL_KNOWN = ["Jon Jones", "Islam Makhachev", "Alexander Volkanovski", "Israel Adesanya",
              "Kamaru Usman", "Leon Edwards", "Max Holloway", "Charles Oliveira"]

FIGHT_ID_RE = re.compile(r"/fight-details/([0-9a-f]{16})")
# UFCStats fighter pages also list bouts from other promotions a fighter had
# before or beside the UFC: Dana White's Contender Series, Road to UFC, WEC,
# PRIDE, Strikeforce, DREAM, Cage Warriors... Those are not UFC fights and are
# correctly absent from `fights`. Measured 2026-10-13: every one of the 54
# bouts UFCStats listed that `fights` lacked was one of these.
UFC_EVENT_RE = re.compile(r"^(UFC\b|The Ultimate Fighter\b)", re.I)


# ---------------------------------------------------------------- Supabase
def rest(path: str, params: dict) -> list:
    out, start = [], 0
    while True:
        r = requests.get(f"{SUPA}/rest/v1/{path}", params=params,
                         headers={"apikey": KEY, "Authorization": f"Bearer {KEY}",
                                  "Range": f"{start}-{start + 999}"}, timeout=60)
        r.raise_for_status()
        page = r.json()
        out += page
        if len(page) < 1000:
            return out
        start += 1000


def pick_fighters() -> list[int]:
    if os.environ.get("FIGHTER_IDS", "").strip():
        return [int(x) for x in os.environ["FIGHTER_IDS"].split(",") if x.strip()]
    ids: list[int] = []
    today = time.strftime("%Y-%m-%d", time.gmtime())
    ev = rest("events", {"select": "id", "event_date": f"gte.{today}", "order": "event_date.asc", "limit": "1"})
    if ev:
        card = rest("fights", {"select": "fighter_a_id,fighter_b_id,is_active", "event_id": f"eq.{ev[0]['id']}"})
        for f in card:
            if f.get("is_active") is not False:
                ids += [f["fighter_a_id"], f["fighter_b_id"]]
    names = ",".join('"' + n + '"' for n in WELL_KNOWN)
    ids += [f["id"] for f in rest("fighters", {"select": "id", "name": f"in.({names})"})]
    pool = sorted({f["fighter_a_id"] for f in rest("fights", {"select": "fighter_a_id", "method": "not.is.null"})})
    rng = random.Random(20261013)
    ids += rng.sample(pool, min(SAMPLE_SIZE, len(pool)))
    seen, out = set(), []
    for i in ids:
        if i and i not in seen:
            seen.add(i); out.append(i)
    return out


# ---------------------------------------------------------------- UFCStats
def is_challenge(text: str) -> bool:
    return "Checking your browser" in text or ("/__c" in text and "var nonce=" in text)


def solve(session: requests.Session, html: str, origin: str) -> bool:
    nonce = re.search(r'nonce\s*=\s*"([0-9a-fA-F]+)"', html)
    diff = re.search(r"target\s*=\s*new Array\(\s*(\d+)\s*\+\s*1\s*\)\.join\(", html)
    if not nonce or not diff:
        return False
    prefix, n = "0" * int(diff.group(1)), 0
    while not hashlib.sha256(f"{nonce.group(1)}:{n}".encode()).hexdigest().startswith(prefix):
        n += 1
    r = session.post(origin + "/__c", data={"nonce": nonce.group(1), "n": n}, timeout=30)
    return 200 <= r.status_code < 300


def fetch(session: requests.Session, url: str) -> str | None:
    origin = re.match(r"(https?://[^/]+)", url).group(1)
    r = session.get(url, timeout=30)
    for _ in range(2):
        if not is_challenge(r.text):
            break
        if not solve(session, r.text, origin):
            return None
        r = session.get(url, timeout=30)
    if r.status_code != 200 or is_challenge(r.text):
        return None
    return r.text


def parse_fighter_page(html: str) -> list[dict]:
    """Every bout row on a UFCStats fighter page: fight id and result flag."""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.select("tr.b-fight-details__table-row"):
        link = tr.get("data-link") or ""
        m = FIGHT_ID_RE.search(link)
        if not m:
            continue
        flag = tr.select_one(".b-flag__text")
        tds = tr.find_all("td")
        ev_ps = tds[6].find_all("p") if len(tds) > 6 else []
        names = [a.get_text(strip=True) for a in (tds[1].find_all("a") if len(tds) > 1 else [])]
        rows.append({"ufc_fight_id": m.group(1),
                     "result": (flag.get_text(strip=True).lower() if flag else ""),
                     "event": ev_ps[0].get_text(" ", strip=True) if ev_ps else "",
                     "date": ev_ps[1].get_text(" ", strip=True) if len(ev_ps) > 1 else "",
                     "opponent": names[1] if len(names) > 1 else ""})
    return rows


# ---------------------------------------------------------------- compare
def ours_result(f: dict, fid: int) -> str:
    if f.get("winner_id") is None:
        return "draw" if re.match(r"(?i)decision", f.get("method") or "") else "nc"
    return "win" if f["winner_id"] == fid else "loss"


def tally(results) -> dict:
    c = Counter(results)
    return {"w": c["win"], "l": c["loss"], "d": c["draw"], "nc": c["nc"]}


def main() -> int:
    ids = pick_fighters()
    fighters = {f["id"]: f for f in rest("fighters", {
        "select": "id,name,ufc_url,ufc_wins,ufc_losses,ufc_draws,updated_at",
        "id": f"in.({','.join(map(str, ids))})"})}
    s = requests.Session()
    s.headers["User-Agent"] = UA
    report, could_not_look = [], []
    for i, fid in enumerate(ids):
        f = fighters.get(fid)
        if not f or not f.get("ufc_url"):
            could_not_look.append({"id": fid, "why": "no ufc_url"})
            continue
        if i:
            time.sleep(DELAY)
        html = fetch(s, f["ufc_url"])
        if html is None:
            could_not_look.append({"id": fid, "name": f["name"], "why": "UFCStats page not fetched"})
            continue
        rows = [r for r in parse_fighter_page(html) if r["result"] in ("win", "loss", "draw", "nc")]
        src = [r for r in rows if UFC_EVENT_RE.match(r["event"])]
        non_ufc = [r for r in rows if not UFC_EVENT_RE.match(r["event"])]
        ours = rest("fights", {"select": "id,ufc_fight_id,winner_id,method,is_active,event_id",
                               "or": f"(fighter_a_id.eq.{fid},fighter_b_id.eq.{fid})"})
        by_ufc = {o["ufc_fight_id"]: o for o in ours if o.get("ufc_fight_id")}
        src_ids = {r["ufc_fight_id"] for r in src}
        completed_ours = [o for o in ours if o.get("method") and o.get("is_active") is not False]
        missing = [{k: r[k] for k in ("ufc_fight_id", "result", "opponent", "event", "date")}
                   for r in src if r["ufc_fight_id"] not in by_ufc]
        extra = [o["id"] for o in completed_ours if o.get("ufc_fight_id") not in src_ids]
        wrong = []
        for r in src:
            o = by_ufc.get(r["ufc_fight_id"])
            if o and o.get("method"):
                mine = ours_result(o, fid)
                if mine != r["result"]:
                    wrong.append({"fight_id": o["id"], "ufc_fight_id": r["ufc_fight_id"],
                                  "ufcstats": r["result"], "ours": mine})
            elif o and not o.get("method"):
                wrong.append({"fight_id": o["id"], "ufc_fight_id": r["ufc_fight_id"],
                              "ufcstats": r["result"], "ours": "no result recorded"})
        report.append({
            "id": fid, "name": f["name"],
            "ufcstats": tally(r["result"] for r in src),
            "fights_table": tally(ours_result(o, fid) for o in completed_ours),
            "fighters_table": {"w": f["ufc_wins"], "l": f["ufc_losses"], "d": f["ufc_draws"]},
            "fighters_updated_at": f["updated_at"],
            "missing_from_fights": missing, "extra_in_fights": extra, "result_mismatches": wrong,
            "non_ufc_bouts_ignored": len(non_ufc),
        })

    def rec(t): return f"{t['w']}-{t['l']}" + (f"-{t['d']}" if t.get("d") else "") + (f" ({t['nc']} NC)" if t.get("nc") else "")
    def same(a, b): return a["w"] == b["w"] and a["l"] == b["l"] and (a.get("d") or 0) == (b.get("d") or 0)

    n = len(report)
    fights_ok = sum(1 for r in report if same(r["fights_table"], r["ufcstats"]) and not r["result_mismatches"])
    fighters_ok = sum(1 for r in report if same(r["fighters_table"], r["ufcstats"]))
    lines = [f"# UFC record reconciliation against UFCStats ({time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())})", "",
             f"Fighters checked: **{n}**. Could not look: **{len(could_not_look)}**.", "",
             f"* `fights` agrees with UFCStats bout-for-bout on UFC events: **{fights_ok} / {n}**",
             f"* Non-UFC bouts on those UFCStats pages, ignored (DWCS, WEC, PRIDE...): "
             f"**{sum(r['non_ufc_bouts_ignored'] for r in report)}**",
             f"* `fighters.ufc_wins/losses/draws` agrees with UFCStats: **{fighters_ok} / {n}**", "",
             "| fighter | UFCStats | fights table | fighters table | missing | extra | wrong result |",
             "|---|---|---|---|---|---|---|"]
    for r in report:
        lines.append(f"| {r['name']} ({r['id']}) | {rec(r['ufcstats'])} | {rec(r['fights_table'])} | "
                     f"{rec(r['fighters_table'])} | {len(r['missing_from_fights'])} | {len(r['extra_in_fights'])} | "
                     f"{len(r['result_mismatches'])} |")
    gaps = [(r["name"], m) for r in report for m in r["missing_from_fights"]]
    if gaps:
        lines += ["", "## UFC-event bouts on UFCStats that `fights` does not hold", "",
                  "| fighter | result | opponent | event | date | ufcstats id |", "|---|---|---|---|---|---|"]
        lines += [f"| {n} | {m['result']} | {m['opponent']} | {m['event']} | {m['date']} | {m['ufc_fight_id']} |"
                  for n, m in gaps]
    if could_not_look:
        lines += ["", "## Could not look", ""] + [f"* {c}" for c in could_not_look]
    md = "\n".join(lines)
    print(md)
    with open("reconcile-report.json", "w") as fh:
        json.dump({"report": report, "could_not_look": could_not_look}, fh, indent=1)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(md + "\n")
    # Looking at nothing is a failure, not a clean bill of health.
    return 1 if n == 0 or len(could_not_look) > n else 0


if __name__ == "__main__":
    sys.exit(main())
