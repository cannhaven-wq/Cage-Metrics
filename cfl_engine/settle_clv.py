"""Post-event CLV settlement: fill closing_odds / clv_pp / clv_beat on published
live edges once the line has closed.

For every model_edges row with source='live', settled_at IS NULL, and
event_date < today, compute the closing price of the BET SIDE and score our
closing-line value:

  closing price (bet side) = the closing capture in fight_odds: rows with
  is_closer=true for (fight_id, bet_fighter_id), keyed by fighter_id (never by
  the capture's A/B side convention). If no closer is on file yet, the row is
  left unsettled — we never substitute a stale or devigged price for a real
  close (both would silently corrupt clv on the product's headline metric).

CLV sign convention (READ THIS — it is easy to get backwards):
  odds_at_publish is a single-side American price, so it can't be devigged after
  the fact (you'd need the other side at the same instant). We therefore compare
  RAW single-side implied probabilities:

      implied_publish = american_to_prob(odds_at_publish)      # price we took
      implied_close   = closing implied prob of the bet side   # price at close
      clv_pp   = implied_close - implied_publish
      clv_beat = clv_pp > 0

  You BEAT the close when the line moved toward your side after you bet — i.e.
  the market's closing implied probability of your fighter is HIGHER than the
  implied probability at the price you locked (you got a longer/better price).

  Worked example (dog): bet +150 (implied 100/250 = 0.4000); closes +120
  (implied 100/220 = 0.4545). The line steamed toward us; we locked the longer
  price. clv_pp = 0.4545 - 0.4000 = +0.0545 > 0  ->  clv_beat = True.
  Worked example (fav): bet -200 (0.6667); closes -300 (0.7500).
  clv_pp = +0.0833 > 0  ->  beat the close (we took the shorter-vig price).
  Positive clv_pp always means we beat the close.

Credentials: env SUPABASE_URL + SUPABASE_SECRET_KEY (service key, read from env,
never printed). --dry-run (default) prints the plan; --execute PATCHes the rows.

Usage (from repo root, PYTHONPATH=cfl_engine):
  python cfl_engine/settle_clv.py            # dry-run
  python cfl_engine/settle_clv.py --execute  # write closing_odds/clv_pp/clv_beat
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request

from engine import american_to_prob
from export_data import fetch_all, prob_to_american


def _env_key() -> str:
    for name in ("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY"):
        if os.environ.get(name):
            return os.environ[name]
    sys.exit("No Supabase service key in env (SUPABASE_SECRET_KEY / "
             "SUPABASE_SERVICE_ROLE_KEY / SUPABASE_SERVICE_KEY).")


def fetch_maybe_missing(base_url: str, key: str, table: str, params: str) -> list[dict]:
    """fetch_all, but a not-yet-created table (404 / PGRST205) reads as empty so a
    first dry-run before the DDL is applied still runs clean."""
    try:
        return fetch_all(base_url, key, table, params)
    except urllib.error.HTTPError as e:
        if e.code in (404, 406):
            print(f"  note: {table} not found (create it via model_serving_tables.sql) "
                  f"— treating as empty.")
            return []
        raise


def closing_implied(base_url: str, key: str, fight_id: int, fighter_id: int) -> tuple:
    """Return (implied_close, american_close, source) for the bet fighter, or
    (None, None, None) if no closing price is on file yet.

    Both returned values come from the SAME median book: implied_close is that
    book's raw single-side implied prob (unit-consistent with the raw, vigged
    odds_at_publish — never devigged), and american_close is that book's real
    booked price (not a reconstructed prob_to_american, which could be a line no
    book offered). No stale-snapshot fallback: a missing close leaves the row
    unsettled, which the caller handles.
    """
    rows = fetch_maybe_missing(
        base_url, key, "fight_odds",
        "select=fighter_id,american_odds,implied_prob"
        f"&is_closer=eq.true&fight_id=eq.{fight_id}&fighter_id=eq.{fighter_id}")
    priced = []  # (implied_prob, american_odds) from real closing books
    for r in rows:
        am = r.get("american_odds")
        p = r.get("implied_prob")
        if p is None and am is not None:
            p = american_to_prob(am)
        if p is not None and 0.0 < float(p) < 1.0:
            priced.append((float(p), am))
    if not priced:
        return None, None, None
    priced.sort(key=lambda t: t[0])
    imp, am = priced[len(priced) // 2]  # median book: prob + its own booked price
    american_close = int(am) if am is not None else prob_to_american(imp)
    return imp, american_close, "bfo_closer"


def patch_row(base_url: str, key: str, row_id: int, payload: dict) -> None:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{base_url}/rest/v1/model_edges?id=eq.{row_id}",
        data=body, method="PATCH",
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Content-Type": "application/json", "Prefer": "return=minimal"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        resp.read()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute", action="store_true",
                    help="PATCH the rows (default: dry-run plan only)")
    ap.add_argument("--dry-run", action="store_true", help="explicit no-op (default)")
    args = ap.parse_args()
    execute = args.execute

    base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not base_url:
        sys.exit("SUPABASE_URL not set in env.")
    key = _env_key()
    today = dt.date.today().isoformat()

    rows = fetch_maybe_missing(
        base_url, key, "model_edges",
        "select=id,fight_id,event_date,side,bet_fighter_id,odds_at_publish"
        f"&source=eq.live&settled_at=is.null&event_date=lt.{today}&order=event_date")
    print(f"unsettled live edges with event_date < {today}: {len(rows)}")
    if not rows:
        print("nothing to settle — clean run.")
        return

    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    planned = []
    for r in rows:
        implied_pub = american_to_prob(r["odds_at_publish"]) if r["odds_at_publish"] is not None else None
        imp_close, am_close, src = closing_implied(base_url, key, r["fight_id"], r["bet_fighter_id"])
        if imp_close is None or implied_pub is None:
            print(f"  fight {r['fight_id']} side {r['side']}: no closing price yet "
                  f"(publish odds {r['odds_at_publish']}) — skipped.")
            continue
        clv_pp = round(imp_close - implied_pub, 6)
        clv_beat = clv_pp > 0
        payload = {"closing_odds": int(am_close), "clv_pp": clv_pp,
                   "clv_beat": clv_beat, "settled_at": now_iso}
        planned.append((r["id"], payload))
        print(f"  fight {r['fight_id']} side {r['side']} fighter {r['bet_fighter_id']}: "
              f"publish {r['odds_at_publish']} (imp {implied_pub:.4f}) -> "
              f"close {am_close} (imp {imp_close:.4f}, {src})  "
              f"clv_pp {clv_pp:+.4f}  {'BEAT' if clv_beat else 'lost'}")

    if not execute:
        print(f"\nDRY-RUN — {len(planned)} row(s) would be settled. "
              f"Re-run with --execute to write.")
        return
    for row_id, payload in planned:
        patch_row(base_url, key, row_id, payload)
    print(f"\nEXECUTED — settled {len(planned)} edge row(s).")


if __name__ == "__main__":
    main()
