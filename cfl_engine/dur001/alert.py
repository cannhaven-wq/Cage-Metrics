"""DUR-001 dead-man alert — read-only, posts to Discord.

    python cfl_engine/dur001/alert.py --dry-run     # print, do not post
    python cfl_engine/dur001/alert.py               # post to DISCORD_WEBHOOK_URL
    python cfl_engine/dur001/alert.py --event-id 4433 --dry-run

`health.py` answers "is the capture healthy right now?" when you ask it. This
answers "has something gone quiet that nobody is watching?" on a schedule, and
shouts when it has.

The distinction that matters is the dead man's switch. A capture pipeline that
stops returns no errors: the workflow goes green, the tables stop growing, and
the card runs off with no closing quote. Nothing fails. So the alert treats
SILENCE near a card as the failure condition, not an absent error.

Two separate silences
---------------------
Totals (`prop_odds`) and moneyline (`fight_odds`) are captured by different
paths in `build/fetch-odds.js` and can stall independently. Grading them
together — taking the newer of the two capture ages — hides exactly the failure
DUR-001 cares about: totals stop, moneyline keeps running, the combined age
looks fine, and the experiment silently loses its market benchmark.

So `grade_extra()` grades them as two independent dead-man switches and emits a
separate RED line for each. Totals stalling is a DUR-001 data failure even when
moneyline is perfectly healthy.

Never writes to the database. Never reads a fight result. Never computes model
performance.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from health import sql, target_event          # noqa: E402  (read-only helpers)

# Inside this many hours of a card, silence is an emergency rather than a shrug.
NEAR_CARD_HOURS = 24
# A capture stream older than this, inside the near-card window, is dead.
CAPTURE_MAX_AGE_H = 3
# Far from a card the streams are allowed to be much quieter.
CAPTURE_MAX_AGE_FAR_H = 36

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0"


# --------------------------------------------------------------------- grading
def grade_extra(hours_to_card, prop_age_h, ml_age_h, *,
                max_age_h: float = CAPTURE_MAX_AGE_H,
                max_age_far_h: float = CAPTURE_MAX_AGE_FAR_H,
                near_card_hours: float = NEAR_CARD_HOURS) -> list[tuple[str, str]]:
    """Dead-man grading for the two capture streams.

    Args:
      hours_to_card: hours until the next card's first fight. None if no card is
        scheduled. Negative means the card has started.
      prop_age_h: hours since the newest `prop_odds` row. None means the table
        has never been written, which is the worst case, not a missing value.
      ml_age_h: hours since the newest `fight_odds` row. Same convention.

    Returns a list of (level, message), level in {"RED", "YELLOW"}. Empty means
    nothing to say.

    The two streams are graded INDEPENDENTLY and on purpose. A totals stall is a
    DUR-001 data failure whether or not moneyline is still running, so it gets
    its own line and its own RED. Combining them — grading on the newer of the
    two ages — would let a healthy moneyline mask a dead totals feed.
    """
    out: list[tuple[str, str]] = []

    if hours_to_card is None:
        return out                      # no card scheduled: nothing to be late for

    near = hours_to_card <= near_card_hours
    limit = max_age_h if near else max_age_far_h
    window = (f"inside {near_card_hours:g}h of the card"
              if near else f"more than {near_card_hours:g}h out")

    for label, age, table in (("totals", prop_age_h, "prop_odds"),
                              ("moneyline", ml_age_h, "fight_odds")):
        if age is None:
            out.append((
                "RED",
                f"{label} capture has NEVER written a row ({table} is empty) — {window}",
            ))
        elif age > limit:
            out.append((
                "RED" if near else "YELLOW",
                f"{label} capture silent for {age:.1f}h (limit {limit:g}h) — "
                f"newest {table} row is stale, {window}",
            ))

    return out


def overall(lines: list[tuple[str, str]]) -> str:
    if any(lvl == "RED" for lvl, _ in lines):
        return "RED"
    if any(lvl == "YELLOW" for lvl, _ in lines):
        return "YELLOW"
    return "GREEN"


# ------------------------------------------------------------------ collection
def hours_since(ts: str | None, now: dt.datetime) -> float | None:
    """Hours between an ISO timestamp and now. None in, None out."""
    if not ts:
        return None
    t = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return (now - t).total_seconds() / 3600.0


def collect(event_id=None):
    """Read-only snapshot of what the alert grades."""
    now = dt.datetime.now(dt.timezone.utc)
    ev = target_event(event_id)
    if not ev:
        return {"now": now, "event": None, "hours_to_card": None,
                "prop_age_h": None, "ml_age_h": None, "locks": None}

    eid = ev["id"]
    row = sql(f"""
select
  (select max(captured_at) from prop_odds)  as last_prop,
  (select max(captured_at) from fight_odds) as last_ml,
  (select min(start_at) from v_fight_start_best s
     join fights f on f.id = s.fight_id where f.event_id = {eid}) as first_start,
  (select count(*) from fights f where f.event_id = {eid}
     and not coalesce(f.is_main_event,false) and not coalesce(f.is_title_fight,false)
     and coalesce(f.scheduled_rounds,3) = 3
     and f.winner_id is null and f.method is null) as eligible,
  (select count(distinct l.fight_id) from prop_model_locks l
     join fights f on f.id = l.fight_id where f.event_id = {eid}) as locked_fights
""")[0]

    return {
        "now": now,
        "event": ev,
        "hours_to_card": (-hours_since(row["first_start"], now)
                          if row["first_start"] else None),
        "prop_age_h": hours_since(row["last_prop"], now),
        "ml_age_h": hours_since(row["last_ml"], now),
        "locks": {"eligible": row["eligible"], "locked_fights": row["locked_fights"]},
    }


def grade_locks(locks, hours_to_card) -> list[tuple[str, str]]:
    """A card inside the near window with unlocked eligible fights is a RED:
    once the bell goes, that fight can never be locked."""
    if not locks or hours_to_card is None:
        return []
    missing = (locks["eligible"] or 0) - (locks["locked_fights"] or 0)
    if missing <= 0:
        return []
    lvl = "RED" if hours_to_card <= NEAR_CARD_HOURS else "YELLOW"
    return [(lvl, f"{missing} eligible fight(s) still unlocked with "
                  f"{hours_to_card:.1f}h to the card — a fight that starts unlocked "
                  f"can never enter DUR-001")]


# --------------------------------------------------------------------- output
def render(snap, lines) -> str:
    status = overall(lines)
    ev = snap["event"]
    head = (f"**DUR-001 capture alert — {status}**\n"
            f"{ev['name']} ({ev['event_date']})" if ev else
            f"**DUR-001 capture alert — {status}**\nno upcoming card")
    body = "\n".join(f"• [{lvl}] {msg}" for lvl, msg in lines) or "• all capture streams healthy"
    ages = (f"\n\ntotals age: {fmt_age(snap['prop_age_h'])}   "
            f"moneyline age: {fmt_age(snap['ml_age_h'])}   "
            f"to card: {fmt_age(snap['hours_to_card'], signed=True)}")
    return f"{head}\n{body}{ages}"


def fmt_age(h, signed=False) -> str:
    if h is None:
        return "never"
    return f"{h:+.1f}h" if signed else f"{h:.1f}h"


def post_discord(text: str) -> None:
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        sys.exit("DISCORD_WEBHOOK_URL not set (use --dry-run to print instead).")
    req = urllib.request.Request(
        url, data=json.dumps({"content": text}).encode(), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--event-id", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the message instead of posting it")
    ap.add_argument("--always", action="store_true",
                    help="post even when everything is GREEN")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    snap = collect(args.event_id)
    lines = grade_extra(snap["hours_to_card"], snap["prop_age_h"], snap["ml_age_h"])
    lines += grade_locks(snap["locks"], snap["hours_to_card"])
    text = render(snap, lines)
    status = overall(lines)

    if args.dry_run:
        print(text)
        print(f"\n[dry-run] status={status} lines={len(lines)} (nothing posted)")
        return
    if status == "GREEN" and not args.always:
        print(f"[alert] {status}: nothing to say, not posting.")
        return
    post_discord(text)
    print(f"[alert] {status}: posted {len(lines)} line(s).")


if __name__ == "__main__":
    main()
