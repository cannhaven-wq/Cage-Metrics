"""Data access for the paper system. Two sources, one shape.

A *snapshot* is a JSON document with everything one card run needs, captured at
or before the lock instant:

    {
      "captured_at": ISO,
      "card": {"event_id", "name", "event_date", "fights": [{"id","fighter_a_id","fighter_b_id",
               "fighter_a_name","fighter_b_name","is_active","winner_id","method","bout_order"}]},
      "starts": [{"fight_id","start_at","start_basis"}],              # v_fight_start_best
      "quotes": [{"fight_id","book_id","american_a","american_b","captured_at","provider_last_update"}],
      "polymarket_books": [{...capture_book rows...}],                 # table rows and/or a JSONL file
      "history": {"fights": [25-column rows]},                        # for MMA-001 (private)
      "fighters": {"<id>": {"dob","reach_in"}}
    }

`load_snapshot(path)` reads one from disk (fixtures, dry runs). `fetch_snapshot()`
builds one from Supabase over PostgREST with the service key from the
environment; it is the only function here that touches the network and it is
read-only. It also reads `polymarket_books` when that table exists, so a
captured order book reaches the evaluator by the same path as a sportsbook
quote. `load_polymarket_jsonl` adds books captured to a file by
capture_book.py --out. Both are validated by `check_snapshot`.
"""
from __future__ import annotations

import json
import os
import pathlib
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional

PAGE = 1000


def _env_key() -> Optional[str]:
    for n in ("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY"):
        if os.environ.get(n):
            return os.environ[n]
    return None


def _get(base: str, key: str, table: str, params: str) -> list[dict]:
    rows, start = [], 0
    while True:
        req = urllib.request.Request(f"{base}/rest/v1/{table}?{params}", headers={
            "apikey": key, "Authorization": f"Bearer {key}", "Range-Unit": "items", "Range": f"{start}-{start + PAGE - 1}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            page = json.load(r)
        rows.extend(page)
        if len(page) < PAGE:
            return rows
        start += PAGE


def load_snapshot(path) -> dict:
    snap = json.loads(pathlib.Path(path).read_text())
    check_snapshot(snap)
    return snap


def check_snapshot(snap: dict) -> None:
    for k in ("captured_at", "card", "starts", "quotes"):
        if k not in snap:
            raise ValueError(f"snapshot lacks {k}")
    for f in snap["card"]["fights"]:
        for k in ("id", "fighter_a_id", "fighter_b_id"):
            if f.get(k) is None:
                raise ValueError(f"fight row lacks {k}: {f}")
    snap.setdefault("polymarket_books", [])


# --------------------------------------------------------------------------- polymarket books

def load_polymarket_jsonl(path) -> list[dict]:
    """Rows written by capture_book.py --out (one JSON object per line)."""
    rows = []
    for line in pathlib.Path(path).read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _ts(v) -> datetime:
    t = datetime.fromisoformat(str(v).replace("Z", "+00:00").replace(" ", "T"))
    if t.tzinfo is None:
        raise ValueError(f"timestamp without a time zone: {v!r}")
    return t.astimezone(timezone.utc)


def latest_polymarket_books(rows: list[dict], *, now: datetime, fight_ids: set[int]) -> list[dict]:
    """The newest capture per (fight, token) retrieved at or before `now`, for the card's fights.

    The evaluator applies freshness, fee, status, settlement and mapping rules
    itself; this only picks which capture represents each token at the lock.
    """
    best: dict[tuple, dict] = {}
    for r in rows:
        try:
            fid = int(r["fight_id"]); tok = str(r["token_id"]); t = _ts(r["retrieved_at"])
        except (KeyError, TypeError, ValueError):
            continue
        if fid not in fight_ids or t > now:
            continue
        k = (fid, tok)
        if k not in best or _ts(best[k]["retrieved_at"]) < t:
            best[k] = r
    return [dict(r) for r in best.values()]


# --------------------------------------------------------------------------- the lock instant

def _active(snap: dict) -> set[int]:
    return {int(f["id"]) for f in snap["card"]["fights"] if f.get("is_active") is not False}


def earliest_verified_start(snap: dict, cfg: dict) -> tuple[Optional[datetime], str]:
    """The card's earliest start among bases the config calls verified, or None with the reason.

    Retired bookings (is_active = false) do not set the lock.
    """
    bases = set(cfg["lock"]["verified_start_bases"])
    fights = _active(snap)
    verified, unverified = [], []
    for s in snap["starts"]:
        if int(s["fight_id"]) not in fights:
            continue
        (verified if s.get("start_basis") in bases else unverified).append(s)
    if not verified:
        return None, f"no fight on the card has a verified start (bases on file: {sorted({s.get('start_basis') for s in unverified})})"
    t = min(datetime.fromisoformat(str(s["start_at"]).replace("Z", "+00:00")) for s in verified)
    return t.astimezone(timezone.utc), "ok"


def lock_instant(snap: dict, cfg: dict) -> tuple[Optional[datetime], str]:
    """One predetermined lock per card: earliest verified start minus the configured lead.

    win_model_locks' own deadline is the earliest start over the whole card
    with a date-only start counting from 00:00 UTC; if any active fight on the
    card only has an event_date_fallback start, that 00:00 UTC bound is the
    earlier one and wins.
    """
    start, why = earliest_verified_start(snap, cfg)
    if start is None:
        if cfg["lock"].get("require_verified_start", True):
            return None, why
    lead = timedelta(minutes=float(cfg["lock"]["lead_minutes_before_earliest_start"]))
    candidates = []
    if start is not None:
        candidates.append(start - lead)
    fights = _active(snap)
    for s in snap["starts"]:
        if int(s["fight_id"]) in fights and s.get("start_basis") == "event_date_fallback":
            d = datetime.fromisoformat(str(s["start_at"]).replace("Z", "+00:00")).astimezone(timezone.utc)
            candidates.append(d.replace(hour=0, minute=0, second=0, microsecond=0) - lead)
    if not candidates:
        return None, "no start of any kind on file"
    return min(candidates), "ok"


# --------------------------------------------------------------------------- live, read-only

def fetch_snapshot(event_id: Optional[int] = None, *, history: bool = True) -> dict:
    """Read-only pull of the next (or given) card from Supabase. Needs SUPABASE_URL and a service key."""
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = _env_key()
    if not base or not key:
        raise RuntimeError("SUPABASE_URL and a service key are required for a live snapshot; use --snapshot for a file")
    now = datetime.now(timezone.utc)
    if event_id is None:
        evs = _get(base, key, "events", f"select=id,name,event_date&event_date=gte.{now.date().isoformat()}&order=event_date.asc&limit=1")
        if not evs:
            raise RuntimeError("no upcoming card")
        ev = evs[0]
    else:
        ev = _get(base, key, "events", f"select=id,name,event_date&id=eq.{event_id}")[0]
    fights = _get(base, key, "fights", f"select=id,fighter_a_id,fighter_b_id,fighter_a_name,fighter_b_name,is_active,winner_id,method,bout_order,bell_at&event_id=eq.{ev['id']}&order=id")
    ids = ",".join(str(f["id"]) for f in fights)
    starts = _get(base, key, "v_fight_start_best", f"select=fight_id,start_at,start_basis&fight_id=in.({ids})")
    quotes = _get(base, key, "v_fight_odds_latest_by_book", f"select=fight_id,book_id,american_odds_a,american_odds_b,captured_at&fight_id=in.({ids})")
    # the view carries no provider timestamp; take it from the underlying rows so freshness checks both
    prov = _get(base, key, "fight_odds", f"select=fight_id,book_id,fighter_id,provider_last_update,captured_at&fight_id=in.({ids})&order=captured_at.desc")
    latest_prov = {}
    for r in prov:
        latest_prov.setdefault((r["fight_id"], r["book_id"]), r.get("provider_last_update"))
    q_rows = [{"fight_id": q["fight_id"], "book_id": q["book_id"], "american_a": q["american_odds_a"], "american_b": q["american_odds_b"],
               "captured_at": q["captured_at"], "provider_last_update": latest_prov.get((q["fight_id"], q["book_id"]))} for q in quotes]
    fighter_ids = sorted({f["fighter_a_id"] for f in fights} | {f["fighter_b_id"] for f in fights})
    fr = _get(base, key, "fighters", f"select=id,dob,reach_in&id=in.({','.join(map(str, fighter_ids))})")
    snap = {"captured_at": now.isoformat(), "card": {"event_id": ev["id"], "name": ev["name"], "event_date": ev["event_date"], "fights": fights},
            "starts": starts, "quotes": q_rows, "polymarket_books": [],
            "fighters": {str(f["id"]): {"dob": f["dob"], "reach_in": f["reach_in"]} for f in fr}}
    try:
        snap["polymarket_books"] = _get(base, key, "polymarket_books", f"select=*&fight_id=in.({ids})&order=retrieved_at.desc")
        snap["polymarket_books_source"] = "table polymarket_books"
    except urllib.error.HTTPError as e:
        snap["polymarket_books_source"] = f"table polymarket_books not readable (HTTP {e.code}); no books from the database"
    if history:
        snap["history"] = {"fights": fetch_history_rows(base, key)}
    check_snapshot(snap)
    return snap


def fetch_history_rows(base: str, key: str) -> list[list]:
    """All settled bouts as MMA-001 25-column rows (same recipe as the Doc's export_mma_dev.sql, no date cut)."""
    cols = ("id,event_id,fighter_a_id,fighter_b_id,winner_id,method,end_round,end_time,scheduled_rounds,weight_class,is_active,"
            "a_sig_str_landed,b_sig_str_landed,a_td_landed,b_td_landed,a_td_attempted,b_td_attempted,a_ctrl_seconds,b_ctrl_seconds,"
            "a_kd,b_kd,a_sub_attempts,b_sub_attempts")
    fights = _get(base, key, "fights", f"select={cols}&order=id")
    events = {e["id"]: e for e in _get(base, key, "events", "select=id,event_date,is_upcoming&order=id")}
    fighters = {f["id"]: f for f in _get(base, key, "fighters", "select=id,dob,reach_in&order=id")}
    return history_rows_from_tables(fights, events, fighters)


def history_rows_from_tables(fights: list[dict], events: dict, fighters: dict) -> list[list]:
    """Pure: the Doc's export recipe applied to table rows. Shared by the live pull and the tests."""
    nc = ("overturned", "could not continue", "no contest", "other")
    out = []
    for f in fights:
        e = events.get(f["event_id"])
        if not e or e.get("is_upcoming") or not e.get("event_date"):
            continue
        if f.get("is_active") is False or f["id"] in (43, 46, 8780):
            continue
        a, b = f.get("fighter_a_id"), f.get("fighter_b_id")
        if a is None or b is None or a == b:
            continue
        m = str(f.get("method") or "").lower()
        if any(m.startswith(x) for x in nc):
            continue
        w = f.get("winner_id")
        if w == a:
            y = 1
        elif w == b:
            y = 0
        elif m.startswith("decision"):
            y = 0.5
        else:
            continue
        secs = None
        try:
            er, et = int(f.get("end_round")), str(f.get("end_time"))
            if 1 <= er <= 10 and ":" in et:
                mm, ss = et.split(":"); secs = (er - 1) * 300 + int(mm) * 60 + int(ss)
        except (TypeError, ValueError):
            pass
        if secs is None and m.startswith("decision") and f.get("scheduled_rounds") and 1 <= int(f["scheduled_rounds"]) <= 5:
            secs = int(f["scheduled_rounds"]) * 300
        fa, fb = fighters.get(a, {}), fighters.get(b, {})
        num = lambda v: None if v is None else float(v)  # noqa: E731
        out.append([f["id"], f["event_id"], str(e["event_date"])[:10], a, b, y, secs,
                    num(f.get("a_sig_str_landed")), num(f.get("b_sig_str_landed")), num(f.get("a_td_landed")), num(f.get("b_td_landed")),
                    num(f.get("a_td_attempted")), num(f.get("b_td_attempted")), num(f.get("a_ctrl_seconds")), num(f.get("b_ctrl_seconds")),
                    num(f.get("a_kd")), num(f.get("b_kd")), num(f.get("a_sub_attempts")), num(f.get("b_sub_attempts")),
                    fa.get("dob"), fb.get("dob"), num(fa.get("reach_in")), num(fb.get("reach_in")), f.get("weight_class"), f.get("method")])
    return out
