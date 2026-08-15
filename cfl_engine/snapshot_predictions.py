"""Freeze the pre-fight record: one immutable row per fight, before the bell.

THE RULE (see pre_fight_snapshots_migration.sql): every fight on every card gets
exactly one snapshot, taken before that card starts, capturing everything CFL was
publicly showing at that moment:

  * the engine's pick, calibrated probability, tier, and WHICH engine version
    produced it (this drifts within a single card — insert-only pick locking
    means a fight locked in July keeps engine_v1 while a late addition gets v2)
  * the vig-free market price we could see at snapshot time
  * the flagged value edge and stake, if we posted one
  * the Prop Board projections for both corners — the ONLY durable copy, since
    prop_projections is full-table replaced on every refresh
  * the legacy v1..v6 model cards the site still renders

Nothing here is computed. This is pure evidence collection: it reads what we
already published and pins it to a timestamp that provably precedes the fight.
That is deliberate — a snapshot that re-runs the model could disagree with what
the site actually showed, which would defeat the point.

Append-only, enforced in the database. Re-running is always safe: fights that
already have a snapshot are skipped, never overwritten. So the schedule can run
twice (day-before + day-of) and the earliest row always wins, while a fight
booked late still gets captured by the second pass.

Credentials: env SUPABASE_URL + SUPABASE_SECRET_KEY (service key, legacy JWT,
read from env — never printed).

Usage (from repo root):
  python cfl_engine/snapshot_predictions.py                    # dry-run, next card
  python cfl_engine/snapshot_predictions.py --execute          # write it
  python cfl_engine/snapshot_predictions.py --event-id 118 --execute
  python cfl_engine/snapshot_predictions.py --within-days 1 --execute   # cron form
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SNAP_TABLE = "pre_fight_snapshots"
PAGE = 1000

# Legacy model cards still rendered on the homepage / event pages. Mirrors
# cfl.PUBLIC_MODELS in _shared.js — keep in sync if that list changes.
LEGACY_MODELS = ["v6", "v3", "v5", "v4", "v2", "v1"]


# ------------------------------------------------------------------ transport
def _rest(base_url, key, method, path, body=None, prefer=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": prefer or "return=representation",
    }
    req = urllib.request.Request(
        f"{base_url}/rest/v1/{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            txt = resp.read().decode()
            return json.loads(txt) if txt else []
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:500]
        # The table is created by a manual SQL Editor step (direct DB is
        # IPv6-only from the office PC), so the schedule can legitimately go
        # live before the migration is applied. Say exactly that instead of
        # dumping a PostgREST 404 into a red CI run.
        if e.code == 404 and "PGRST205" in detail and SNAP_TABLE in path:
            raise SystemExit(
                f"ERROR: the {SNAP_TABLE} table does not exist yet.\n"
                f"       Apply pre_fight_snapshots_migration.sql in the Supabase\n"
                f"       SQL Editor, then re-run. No snapshot was taken.") from None
        raise SystemExit(f"ERROR {method} {path} -> HTTP {e.code}: {detail}") from None


def fetch_all(base_url, key, table, query):
    """Paged GET — PostgREST caps a single response, and a big card plus six
    legacy models can exceed it."""
    out, offset = [], 0
    while True:
        page = _rest(base_url, key, "GET",
                     f"{table}?{query}&limit={PAGE}&offset={offset}")
        out.extend(page)
        if len(page) < PAGE:
            return out
        offset += PAGE


# ------------------------------------------------------------------- targeting
def find_target_events(base_url, key, within_days, log=print):
    """Every event dated today .. today+within_days that still has a pending
    fight. Returns a list, not one event: two cards can land in the same window
    (a Fight Night on Saturday and an early international card), and missing one
    means that card has no pre-fight record at all.

    Pending = winner_id is null. A card that already finished is skipped, so a
    late run can never backfill a snapshot after the bell.
    """
    today = dt.date.today()
    horizon = (today + dt.timedelta(days=within_days)).isoformat()
    events = fetch_all(base_url, key, "events",
                       "select=id,event_date,name"
                       f"&event_date=gte.{today.isoformat()}&event_date=lte.{horizon}"
                       "&order=event_date")
    targets = []
    for e in events:
        pend = fetch_all(base_url, key, "fights",
                         f"select=id&event_id=eq.{e['id']}&winner_id=is.null&limit=1")
        if pend:
            log(f"  target card: {e['name']} ({e['event_date']}, id {e['id']})")
            targets.append(e)
    if not targets:
        log(f"  no card with pending fights in the next {within_days} day(s) — nothing to snapshot.")
    return targets


# ------------------------------------------------------------------- gathering
def _in_list(ids):
    return "(" + ",".join(str(int(i)) for i in ids) + ")"


def drop_stale_bookings(fights, log=print):
    """Exclude dead bookings — a fighter listed in more than one pending fight.

    This is NOT the same-pair id reassignment that export_data.py already merges
    (that groups on the fighter PAIR). This is an opponent swap: the matchup
    changes, the scraper inserts the new bout, and the superseded row survives
    with both fighters still attached. On 2026-08-15 that put two fights on UFC
    330 that were never going to happen, and the engine had published a pick for
    each.

    A fighter competes once per card, so when one appears twice the later
    booking is the live one. Dropping the older is not optional here: a
    permanent 'pre-fight prediction' for a bout that never took place is a false
    record, and it can never settle, so it would sit in the graded view as an
    ungradeable null forever.

    Loud on purpose. A silent drop would hide a scraper bug that keeps recurring.
    """
    by_fighter = {}
    for f in fights:
        for fid in (f.get("fighter_a_id"), f.get("fighter_b_id")):
            if fid is not None:
                by_fighter.setdefault(fid, []).append(f)

    stale, reasons = set(), []
    for fid, booked in by_fighter.items():
        if len(booked) < 2:
            continue
        # Highest fight id = most recently scraped booking (house convention,
        # matches the canonical pick in export_data.py's dedupe).
        live = max(booked, key=lambda f: f["id"])
        for f in booked:
            if f["id"] != live["id"] and f["id"] not in stale:
                stale.add(f["id"])
                reasons.append(
                    f"    fight {f['id']} ({f['fighter_a_name']} vs {f['fighter_b_name']}) "
                    f"— superseded by {live['id']} "
                    f"({live['fighter_a_name']} vs {live['fighter_b_name']})")

    if stale:
        log(f"  DEAD BOOKINGS — {len(stale)} fight(s) excluded from the record "
            f"(a fighter cannot be on the card twice):")
        log("\n".join(reasons))
        log("    These still carry live engine picks and are almost certainly "
            "showing on the site. Worth a dead_booking_cleanup pass.")
    return [f for f in fights if f["id"] not in stale]


def collect(base_url, key, event, log=print):
    """Assemble one snapshot row per pending fight on this card."""
    event_id = event["id"]
    fights = fetch_all(
        base_url, key, "fights",
        "select=id,event_id,fighter_a_id,fighter_a_name,fighter_b_id,fighter_b_name,"
        "weight_class,is_title_fight,is_main_event,scheduled_rounds,winner_id"
        f"&event_id=eq.{event_id}&winner_id=is.null&order=id")
    if not fights:
        return []
    fights = drop_stale_bookings(fights, log=log)
    if not fights:
        return []
    idl = _in_list([f["id"] for f in fights])

    # Skip fights already on record — append-only, earliest snapshot wins.
    existing = {r["fight_id"] for r in fetch_all(
        base_url, key, SNAP_TABLE, f"select=fight_id&fight_id=in.{idl}")}
    if existing:
        log(f"  {len(existing)} fight(s) already snapshotted — leaving those untouched.")
    fights = [f for f in fights if f["id"] not in existing]
    if not fights:
        return []
    idl = _in_list([f["id"] for f in fights])

    # --- engine picks (live only; backtest rows must never enter the record) ---
    picks = {}
    for p in fetch_all(base_url, key, "model_picks",
                       "select=fight_id,pick_fighter_id,pick_side,p_cal,tier,"
                       f"model_version,published_at&fight_id=in.{idl}&source=eq.live"):
        # Several engine versions can cover one fight; keep the newest publish.
        cur = picks.get(p["fight_id"])
        if cur is None or (p["published_at"] or "") > (cur["published_at"] or ""):
            picks[p["fight_id"]] = p

    # --- market consensus at snapshot time ---
    odds = {o["fight_id"]: o for o in fetch_all(
        base_url, key, "v_fight_odds_consensus",
        "select=fight_id,american_odds_a,american_odds_b,implied_prob_a,"
        f"implied_prob_b,bookmaker_count,fetched_at&fight_id=in.{idl}")}

    # --- flagged value edges (live only) ---
    edges = {}
    for e in fetch_all(base_url, key, "model_edges",
                       "select=fight_id,side,bet_fighter_id,edge,stake_frac,"
                       f"odds_at_publish,published_at&fight_id=in.{idl}&source=eq.live"):
        cur = edges.get(e["fight_id"])
        if cur is None or (e["published_at"] or "") > (cur["published_at"] or ""):
            edges[e["fight_id"]] = e

    # --- Prop Board, both corners (only durable copy) ---
    props = {}
    for pr in fetch_all(base_url, key, "prop_projections",
                        f"select=*&fight_id=in.{idl}&order=side"):
        props.setdefault(pr["fight_id"], []).append(
            {k: v for k, v in pr.items() if k not in ("id", "event_name", "event_date")})

    # --- legacy model cards still shown on the site ---
    legacy = {}
    ml = ",".join(LEGACY_MODELS)
    for m in fetch_all(base_url, key, "model_predictions",
                       "select=fight_id,model_version,fighter_id,model_p"
                       f"&fight_id=in.{idl}&model_version=in.({ml})"):
        slot = legacy.setdefault(m["fight_id"], {})
        prev = slot.get(m["model_version"])
        # Two rows per fight (one per corner) — keep the model's favoured side.
        if prev is None or float(m["model_p"]) > float(prev["model_p"]):
            slot[m["model_version"]] = {
                "fighter_id": m["fighter_id"], "model_p": float(m["model_p"])}

    rows = []
    for f in fights:
        fid = f["id"]
        pk, od, ed = picks.get(fid), odds.get(fid), edges.get(fid)
        rows.append({
            "snapshot_label": None,          # filled by caller
            "event_id": event_id,
            "event_name": event.get("name"),
            "event_date": event["event_date"],
            "fight_id": fid,
            "weight_class": f.get("weight_class"),
            "main_event": bool(f.get("is_main_event")),
            "title_fight": bool(f.get("is_title_fight")),
            "scheduled_rounds": f.get("scheduled_rounds"),
            "fighter_a_id": f.get("fighter_a_id"),
            "fighter_a_name": f.get("fighter_a_name"),
            "fighter_b_id": f.get("fighter_b_id"),
            "fighter_b_name": f.get("fighter_b_name"),

            "engine_pick_fighter_id": pk and pk["pick_fighter_id"],
            "engine_pick_side": pk and pk["pick_side"],
            "engine_p_cal": pk and pk["p_cal"],
            "engine_tier": pk and pk["tier"],
            "engine_model_version": pk and pk["model_version"],
            "engine_published_at": pk and pk["published_at"],

            "odds_american_a": od and od["american_odds_a"],
            "odds_american_b": od and od["american_odds_b"],
            "implied_prob_a": od and od["implied_prob_a"],
            "implied_prob_b": od and od["implied_prob_b"],
            "bookmaker_count": od and od["bookmaker_count"],
            "odds_fetched_at": od and od["fetched_at"],

            "edge_side": ed and ed["side"],
            "edge_bet_fighter_id": ed and ed["bet_fighter_id"],
            "edge_value": ed and ed["edge"],
            "edge_stake_frac": ed and ed["stake_frac"],
            "edge_odds_at_publish": ed and ed["odds_at_publish"],

            "props": props.get(fid),
            "legacy_models": legacy.get(fid),
        })
    return rows


# -------------------------------------------------------------------- reporting
def report(rows, log=print):
    """Print the card exactly as it will be frozen, and call out what is missing.
    Gaps are printed loudly rather than failing the run: a fight with no prop
    projection still deserves its pick on record."""
    no_pick = [r for r in rows if not r["engine_pick_fighter_id"]]
    no_odds = [r for r in rows if r["odds_american_a"] is None]
    no_prop = [r for r in rows if not r["props"]]
    versions = sorted({r["engine_model_version"] for r in rows if r["engine_model_version"]})

    for r in rows:
        pick = "—"
        if r["engine_pick_fighter_id"]:
            side = r["engine_pick_side"]
            name = r["fighter_a_name"] if side == "a" else r["fighter_b_name"]
            pick = f"{name} {float(r['engine_p_cal']):.1%} ({r['engine_tier']}, {r['engine_model_version']})"
        price = "no price"
        if r["odds_american_a"] is not None:
            price = f"{r['odds_american_a']:+d}/{r['odds_american_b']:+d}"
        tags = []
        if r["main_event"]:
            tags.append("MAIN")
        if r["edge_value"] is not None:
            tags.append(f"EDGE {float(r['edge_value']):.1%}")
        if not r["props"]:
            tags.append("no props")
        log(f"    {r['fighter_a_name']} vs {r['fighter_b_name']}"
            f"  |  {pick}  |  {price}"
            + (f"  |  {' · '.join(tags)}" if tags else ""))

    log(f"\n  {len(rows)} fight(s) to freeze.")
    if versions:
        log(f"  engine versions on this card: {', '.join(versions)}"
            + ("   <-- MIXED: picks were locked at different times"
               if len(versions) > 1 else ""))
    if no_pick:
        log(f"  WARNING: {len(no_pick)} fight(s) have NO live engine pick — "
            f"snapshotting them anyway so the gap itself is on record.")
    if no_odds:
        log(f"  WARNING: {len(no_odds)} fight(s) have no market price at snapshot time.")
    if no_prop:
        log(f"  NOTE: {len(no_prop)} fight(s) have no prop projection "
            f"(thin tape or not published).")


# -------------------------------------------------------------------- publishing
def publish(base_url, key, rows, label, log=print):
    """Insert, ignoring any fight already on record. Never updates: the table's
    triggers reject UPDATE outright, so a duplicate must be dropped, not merged."""
    for r in rows:
        r["snapshot_label"] = label
    inserted = _rest(base_url, key, "POST", SNAP_TABLE, rows,
                     prefer="return=representation,resolution=ignore-duplicates")
    log(f"  froze {len(inserted)} of {len(rows)} row(s) into {SNAP_TABLE} "
        f"(label '{label}').")
    if len(inserted) < len(rows):
        log(f"  {len(rows) - len(inserted)} already had a snapshot — left as-is.")
    return len(inserted)


# ------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--event-id", type=int,
                    help="snapshot one specific event instead of auto-targeting")
    ap.add_argument("--within-days", type=int, default=2,
                    help="auto-target cards dated today .. today+N (default 2)")
    ap.add_argument("--label", default=None,
                    help="snapshot_label to record (default: cron_pre_event)")
    ap.add_argument("--execute", action="store_true",
                    help="actually write; omit for a dry run")
    args = ap.parse_args(argv)

    base_url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not base_url or not key:
        raise SystemExit("ERROR: SUPABASE_URL and SUPABASE_SECRET_KEY must be set.")
    base_url = base_url.rstrip("/")
    label = args.label or ("manual" if args.event_id else "cron_pre_event")

    print(f"Pre-fight snapshot — {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M UTC}\n")

    if args.event_id:
        found = fetch_all(base_url, key, "events",
                          f"select=id,event_date,name&id=eq.{args.event_id}")
        if not found:
            raise SystemExit(f"ERROR: no event with id {args.event_id}.")
        events = found
        print(f"  target card: {found[0]['name']} ({found[0]['event_date']})")
    else:
        events = find_target_events(base_url, key, args.within_days)

    total = 0
    for event in events:
        rows = collect(base_url, key, event)
        if not rows:
            print(f"  {event['name']}: every pending fight is already on record — nothing to do.\n")
            continue
        print(f"\n  {event['name']} ({event['event_date']}):")
        report(rows)
        if args.execute:
            total += publish(base_url, key, rows, label)
        else:
            print(f"  DRY RUN — nothing written. Re-run with --execute to freeze.")
        print()

    if args.execute:
        print(f"Done. {total} fight(s) added to the permanent pre-fight record.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
