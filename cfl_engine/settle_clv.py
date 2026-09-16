"""Post-event CLV settlement. Two modes, chosen explicitly, that never mix.

    LEGACY   (default)   fills closing_odds / clv_pp / clv_beat, the pre-CLV-001
                         construction this script has always written. Unchanged.
    CLV-001  (--clv001)  computes the frozen primary measure, CLV_return, into
                         separate columns. Reports by default; writes only when
                         every precondition holds.

Usage (from repo root, PYTHONPATH=cfl_engine):

    python cfl_engine/settle_clv.py                    # legacy dry-run
    python cfl_engine/settle_clv.py --execute          # legacy write (the cron)
    python cfl_engine/settle_clv.py --clv001 --report  # CLV-001, writes nothing
    python cfl_engine/settle_clv.py --clv001 --write   # CLV-001, gated

`--clv001` requires exactly one of `--report` / `--write`. There is no default:
neither reporting nor writing should ever happen because someone forgot a flag.

WHY TWO MODES AND NOT A REPLACEMENT
-----------------------------------
`clv_pp` and `clv_beat` are the raw single-side implied-probability movement,
vigged at both ends. CLV-001 §1.2 retains them as a secondary descriptive
figure: they are what the stored rows already mean, and silently recomputing
them under the new definition would reinterpret history. So the legacy path
below is untouched, keeps running on its cron, and keeps writing its own
columns. CLV-001 lands in new columns beside it and never overwrites it.

THE CLV-001 MODE FAILS CLOSED, EVERYWHERE
-----------------------------------------
Writing requires, all of them, with no fallback for any:

  * the CLV-001 columns exist on `model_edges`
    (research/clv/proposed_2026-09-16_clv001_columns.sql — NOT yet applied);
  * `research/clv/protocol.json` says `frozen`, its version matches the version
    compiled into `clv/scoring.py` EXACTLY, and the protocol markdown still
    hashes to the sha256 the json records;
  * Q-02's fixed named sportsbook list is present in the frozen protocol;
  * every capture requirement the protocol names as unbackfillable is met.

Miss any one and no CLV result is written for any row. Per-row obstacles — a
one-sided close, fewer than three books, an R-13 sentinel timestamp, a stale
quote — leave that row unscored with a reason from the closed vocabulary, never
scored on a substitute. Unscored counts are reported beside every summary
(R-05), because a coverage problem that hides inside a favourable average is the
specific failure this protocol exists to prevent.

Publication is a separate gate and this script does not touch it. It computes
and stores a private number; `protocol.json` holds `publication_allowed`, which
is false and stays false until 100 scored observations across 20 distinct events
with a cluster interval excluding zero.

----------------------------------------------------------------------------
LEGACY MODE — the original docstring follows, unchanged.
----------------------------------------------------------------------------

Fill closing_odds / clv_pp / clv_beat on published live edges once the line has
closed.

For every model_edges row with source='live', settled_at IS NULL, and
event_date < today, compute the closing price of the BET SIDE and score our
closing-line value:

  closing price (bet side) = the closing capture in fight_odds: rows with
  is_closer=true for (fight_id, bet_fighter_id), keyed by fighter_id (never by
  the capture's A/B side convention). If no closer is on file yet, the row is
  left unsettled — we never substitute a stale or devigged price for a real
  close (both would silently corrupt clv on the product's headline metric).

  NON-MARKET PRICE GUARD (added 2026-08-19 after a live near-miss): a capture
  outside [MIN_MARKET_PROB, MAX_MARKET_PROB] is discarded as not-a-market and
  the row is left unsettled. The feed emits sentinel lines like -199900 /
  +199900 (implied 0.9995 / 0.0005) when a book pulls a fight off the board or
  the capture lands post-settlement. No book prices a real fight there. One
  such row (Makhachev vs Machado Garry, fight 27648) was single-handedly
  responsible for the entire positive mean CLV across the first 21 settleable
  edges: +0.99pp with it, -0.03pp without. Left ungated, this metric reports a
  house edge that does not exist.

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
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

from engine import american_to_prob
from export_data import fetch_all, prob_to_american

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "clv"))
from scoring import (  # noqa: E402
    CLOSE_REFERENCE_BASES, PROTOCOL_ID, PROTOCOL_TAG, PROTOCOL_VERSION,
    UNSCORED_REASONS, admissible_reference, is_eligible_book, score_row,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROTOCOL_JSON = os.path.join(REPO_ROOT, "research", "clv", "protocol.json")
PROTOCOL_MD = os.path.join(REPO_ROOT, "research", "clv",
                           "CLV_MEASUREMENT_PROTOCOL.md")

# The columns research/clv/proposed_2026-09-16_clv001_columns.sql adds. All of
# them, or none: a scored row carries its whole provenance or it is not written.
CLV001_COLUMNS = (
    "clv_return", "closing_fair_probability", "closing_book_count",
    "clv_protocol_version", "clv_scored_at", "clv_unscored_reason",
    "clv_source_quote_ids", "clv_closing_consensus", "clv_consensus_sha256",
    # Amendment 4 — how late the proxy was, and whether that is exact.
    "clv_close_basis", "clv_lead_time_minutes", "clv_lead_time_is_lower_bound",
    "clv_proxy_quoted_at", "clv_window_opened_at",
)

# Capture columns on fight_odds that the close depends on
# (research/clv/proposed_2026-09-16_fight_odds_capture.sql).
CAPTURE_COLUMNS = ("source_event_id", "bout_started_at", "proxy_cutoff_at",
                   "is_live", "provider_last_update", "retrieved_at",
                   "opponent_fighter_id")


# A real two-way market never prices a side outside this band. Anything beyond
# it is a pulled line, a settled line, or a feed artifact — not a price we could
# have bet, so it cannot be used to score closing-line value.
MIN_MARKET_PROB = 0.03
MAX_MARKET_PROB = 0.97


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
        if p is None:
            continue
        p = float(p)
        if not (MIN_MARKET_PROB <= p <= MAX_MARKET_PROB):
            # Sentinel / pulled / post-settlement capture — not a bettable price.
            continue
        priced.append((p, am))
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
                    help="LEGACY mode: PATCH the rows (default: dry-run plan only)")
    ap.add_argument("--dry-run", action="store_true", help="explicit no-op (default)")
    ap.add_argument("--clv001", action="store_true",
                    help="run the frozen CLV-001 measure instead of the legacy one")
    ap.add_argument("--report", action="store_true",
                    help="CLV-001 mode: compute and print, write nothing")
    ap.add_argument("--write", action="store_true",
                    help="CLV-001 mode: write, if and only if every precondition holds")
    args = ap.parse_args()

    if args.clv001:
        if args.report == args.write:
            sys.exit("--clv001 needs exactly one of --report / --write. There is "
                     "no default: neither reporting nor writing should happen "
                     "because a flag was forgotten.")
        if args.execute:
            sys.exit("--execute is the LEGACY write flag. CLV-001 writes with "
                     "--write, which is gated separately and deliberately.")
        return clv001_main(write=args.write)
    if args.report or args.write:
        sys.exit("--report / --write are CLV-001 flags; pass --clv001 too.")
    return legacy_main(execute=args.execute)


def legacy_main(execute: bool):
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
    skipped: list[int] = []
    for r in rows:
        implied_pub = american_to_prob(r["odds_at_publish"]) if r["odds_at_publish"] is not None else None
        imp_close, am_close, src = closing_implied(base_url, key, r["fight_id"], r["bet_fighter_id"])
        if imp_close is None or implied_pub is None:
            skipped.append(r["fight_id"])
            print(f"  fight {r['fight_id']} side {r['side']}: no usable closing price "
                  f"(publish odds {r['odds_at_publish']}) — skipped. Either no closer "
                  f"is on file yet, or every capture was outside the "
                  f"{MIN_MARKET_PROB}-{MAX_MARKET_PROB} market band.")
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

    if skipped:
        print(f"\n{len(skipped)} row(s) left unsettled for lack of a usable "
              f"close: {skipped}. They stay eligible — a later run picks them "
              f"up if a real closing price arrives.")

    _summarise(planned)

    if not execute:
        print(f"\nDRY-RUN — {len(planned)} row(s) would be settled. "
              f"Re-run with --execute to write.")
        return
    for row_id, payload in planned:
        patch_row(base_url, key, row_id, payload)
    print(f"\nEXECUTED — settled {len(planned)} edge row(s).")



# ===========================================================================
# CLV-001 — the frozen measure
# ===========================================================================

def _iso(ts: str | None) -> dt.datetime | None:
    """PostgREST timestamptz -> aware datetime. Never guesses a zone."""
    if not ts:
        return None
    s = ts.strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        out = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    return out if out.tzinfo else out.replace(tzinfo=dt.timezone.utc)


def _sha256_file(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def preflight(base_url: str, key: str) -> tuple[dict, list[str]]:
    """Every condition CLV-001 requires before a single value may be written.

    Returns `(conditions, blockers)`. A condition that cannot be evaluated counts
    as NOT met — unknown is treated as failed, which is what "fail closed" means
    here. `blockers` is the ordered list of condition names that are false, and
    an empty list is the only thing that opens write mode.

    Nothing in here is skippable with a flag. That is the point: a gate with an
    override is not a gate, and this one guards the number the whole protocol
    exists to make trustworthy.
    """
    cond: dict[str, bool] = {}
    detail: dict[str, str] = {}

    # --- the frozen protocol itself -----------------------------------------
    protocol: dict = {}
    try:
        with open(PROTOCOL_JSON, encoding="utf-8") as fh:
            protocol = json.load(fh)
    except (OSError, ValueError) as e:
        detail["protocol_readable"] = str(e)
    cond["protocol_readable"] = bool(protocol)
    cond["protocol_frozen"] = protocol.get("status") == "frozen"
    cond["protocol_version_matches"] = protocol.get("version") == PROTOCOL_VERSION
    detail["protocol_version_matches"] = (
        f"protocol.json {protocol.get('version')!r} vs scoring.py "
        f"{PROTOCOL_VERSION!r}")

    # The markdown is the protocol; the json is its mirror. If they have drifted
    # apart, neither can be trusted to say what the rules are.
    try:
        on_disk = _sha256_file(PROTOCOL_MD)
        cond["protocol_sha256_matches"] = on_disk == protocol.get("protocol_sha256")
        detail["protocol_sha256_matches"] = f"on disk {on_disk[:16]}…"
    except OSError as e:
        cond["protocol_sha256_matches"] = False
        detail["protocol_sha256_matches"] = str(e)

    # --- Q-02's fixed named sportsbook list ---------------------------------
    # Resolved as "a fixed NAMED list frozen at protocol freeze". The name of the
    # rule is the whole rule: a list assembled now, from books that happen to be
    # in the data, is book selection after the fact — exactly what DUR-001
    # forbids and what freezing the list was meant to make impossible. So this
    # script will not derive one. It reads it, or it refuses.
    named = protocol.get("eligible_books")
    cond["eligible_book_list_frozen"] = bool(named)
    detail["eligible_book_list_frozen"] = (
        f"{len(named)} book(s) named" if named else
        "protocol.json has no `eligible_books` key. Q-02 resolved to a fixed "
        "named list frozen AT FREEZE and the list was never written down. It "
        "cannot be chosen now without choosing it after seeing the data.")

    # --- the storage the results go into ------------------------------------
    missing = _missing_clv_columns(base_url, key)
    cond["schema_present"] = not missing
    detail["schema_present"] = (
        "all CLV-001 columns present" if not missing else
        f"missing: {', '.join(missing)} — apply "
        f"research/clv/proposed_2026-09-16_clv001_columns.sql")

    # --- capture requirements that cannot be backfilled ---------------------
    caps = _capture_capabilities(base_url, key)
    cond.update(caps["conditions"])
    detail.update(caps["detail"])

    blockers = [name for name, ok in cond.items() if not ok]
    return {"conditions": cond, "detail": detail, "protocol": protocol,
            "eligible_books": named or []}, blockers


def _missing_clv_columns(base_url: str, key: str) -> list[str]:
    """Which CLV-001 columns `model_edges` does not have.

    PostgREST fails the whole select on the first unknown column, so probe one
    at a time. Slow and boring, and it names the column rather than saying
    something went wrong.
    """
    missing = []
    for col in CLV001_COLUMNS:
        try:
            fetch_all(base_url, key, "model_edges", f"select={col}&limit=1")
        except urllib.error.HTTPError:
            missing.append(col)
        except Exception:                       # noqa: BLE001 - unknown is failed
            missing.append(col)
    return missing


def _capture_capabilities(base_url: str, key: str) -> dict:
    """What the capture path can and cannot currently supply.

    These are protocol §4 requirements that cannot be backfilled. A missing one
    is not a bug to work around — it is a fact about what the record supports,
    and the honest response is to refuse to write a number that pretends
    otherwise.
    """
    cond, detail = {}, {}

    cols = set()
    try:
        probe = fetch_all(base_url, key, "fight_odds", "select=*&limit=1")
        if probe:
            cols = set(probe[0])
    except Exception as e:                      # noqa: BLE001
        detail["quote_provenance_present"] = str(e)

    # Item 12: an immutable link from the stored consensus back to exact rows.
    cond["quote_provenance_present"] = "id" in cols
    detail.setdefault("quote_provenance_present",
                      "fight_odds.id present" if "id" in cols else
                      "fight_odds has no row id to reference")

    # Item 9: provider market IDs, the only stable key across a repost or a
    # rematch. Q-10 says matching is mechanical on fighter identity AND provider
    # market id; without the second half, only the first can be enforced.
    # `source_event_id` is the name prop_odds already uses for this, and
    # research/clv/proposed_2026-09-16_fight_odds_capture.sql adds it here.
    has_market_id = "source_event_id" in cols
    cond["provider_market_ids_captured"] = has_market_id
    detail["provider_market_ids_captured"] = (
        "fight_odds.source_event_id present" if has_market_id else
        "fight_odds carries no provider market id (§4 item 9) — apply "
        "research/clv/proposed_2026-09-16_fight_odds_capture.sql. Q-10's "
        "mechanical match is half-enforceable meanwhile: fighter identity yes, "
        "repost/rematch no.")

    # Item 11: the provider's own timestamp separately from ours. Collapsing them
    # hides feed lag, and feed lag is what the staleness limit measures.
    has_split_time = {"provider_last_update", "retrieved_at"} <= cols
    cond["provider_and_retrieval_times_split"] = has_split_time
    detail["provider_and_retrieval_times_split"] = (
        "present" if has_split_time else
        "fight_odds has captured_at only (§4 item 11) — a price we retrieved 5 "
        "minutes before the bell that the book last moved 4 hours earlier is a "
        "stale price wearing a fresh timestamp, and nothing on the row says so.")

    # Item 10: what the quote referred to. A late opponent change silently
    # redefines a price and is invisible afterwards.
    cond["opponent_at_quote_time_captured"] = "opponent_fighter_id" in cols
    detail["opponent_at_quote_time_captured"] = (
        "present" if "opponent_fighter_id" in cols else
        "fight_odds does not record the opposing corner at quote time (§4 item "
        "10), so Q-10's opponent-change exclusion rests on today's corners.")

    # Item 7, Amendment 3: a close reference per fight, not per card. The card's
    # published start belongs to bout 1; every later bout begins when the one
    # before it ends.
    bases = ",".join(sorted(CLOSE_REFERENCE_BASES))
    try:
        rows = fetch_all(base_url, key, "v_clv_close_reference",
                         f"select=fight_id&reference_basis=in.({bases})&limit=1")
        cond["close_reference_available"] = bool(rows)
    except Exception as e:                      # noqa: BLE001
        cond["close_reference_available"] = False
        detail["close_reference_available"] = (
            f"v_clv_close_reference unreadable ({e}) — apply "
            f"research/clv/proposed_2026-09-16_event_flow.sql")
    detail.setdefault(
        "close_reference_available",
        f"v_clv_close_reference resolves a basis in ({bases})"
        if cond["close_reference_available"] else
        "no fight resolves an admissible close reference")

    # The running order is the prerequisite for everything after bout 1: without
    # it there is no "previous bout" to reason from, and no fight can even be
    # identified as the card's first.
    try:
        rows = fetch_all(base_url, key, "fight_bout_order", "select=fight_id&limit=1")
        cond["running_order_captured"] = bool(rows)
    except Exception as e:                      # noqa: BLE001
        cond["running_order_captured"] = False
        detail["running_order_captured"] = f"fight_bout_order unreadable ({e})"
    detail.setdefault(
        "running_order_captured",
        "fight_bout_order populated" if cond["running_order_captured"] else
        "no running order on file. `fights` has no order column — only "
        "is_main_event, which names the last bout — and sorting by id would be "
        "an inference dressed as a record.")

    # Exact bout completions. Not is_exact=false rows: an upper bound from the
    # result scraper is completion PLUS unknown lag, and using it would place a
    # bout's start too late and admit in-play quotes as its close.
    try:
        rows = fetch_all(base_url, key, "fight_bout_completions",
                         "select=fight_id&is_exact=is.true&limit=1")
        cond["bout_completions_captured"] = bool(rows)
    except Exception as e:                      # noqa: BLE001
        cond["bout_completions_captured"] = False
        detail["bout_completions_captured"] = f"fight_bout_completions unreadable ({e})"
    detail.setdefault(
        "bout_completions_captured",
        "exact bout completions on file" if cond["bout_completions_captured"] else
        "no exact bout completions. Under Amendment 5 these ARE the scoring "
        "cutoff for bouts 2..N, so without them only bout 1 of a card scores — "
        "roughly one observation per event against a floor of 100 across 20. "
        "Acquiring them needs a live feed or manual entry, which is an L3 call "
        "and is now the highest-leverage open item.")
    return {"conditions": cond, "detail": detail}


def clv001_main(write: bool) -> None:
    base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not base_url:
        sys.exit("SUPABASE_URL not set in env.")
    key = _env_key()
    now = dt.datetime.now(dt.timezone.utc)

    print(f"=== {PROTOCOL_TAG} — {'WRITE' if write else 'REPORT'} mode ===")
    print(f"protocol : {PROTOCOL_ID} v{PROTOCOL_VERSION}")
    print(f"run at   : {now.isoformat()}")
    print(f"writes   : {'gated below' if write else 'NONE — report mode writes nothing'}\n")

    state, blockers = preflight(base_url, key)
    print("preflight")
    for name, ok in state["conditions"].items():
        mark = "ok  " if ok else "FAIL"
        note = state["detail"].get(name, "")
        print(f"  [{mark}] {name}" + (f"  — {note}" if note else ""))

    if write and blockers:
        print(f"\nWRITE REFUSED. {len(blockers)} precondition(s) not met: "
              f"{', '.join(blockers)}.")
        print("No CLV-001 value was written for any row, and nothing was "
              "partially written. Fix the preconditions, not the gate.")
        sys.exit(2)

    # The report runs regardless, because knowing WHY nothing scores is the
    # whole value of a dry run. Scoring below cannot write: `write_allowed` is
    # the only thing that unlocks the PATCH, and a blocker forces it false.
    write_allowed = write and not blockers
    eligible_book_ids = _resolve_eligible_books(base_url, key, state["eligible_books"])

    # Same population as legacy settlement: real published edges on cards that
    # have already happened. A fight that has not been fought has no close, and
    # scoring one against quotes taken before a future scheduled start would be
    # measuring a market that is still moving.
    today = dt.date.today().isoformat()
    rows = fetch_all(
        base_url, key, "model_edges",
        "select=id,fight_id,event_date,side,bet_fighter_id,odds_at_publish,"
        f"published_at,source&source=eq.live&event_date=lt.{today}"
        "&order=event_date")
    print(f"\nlive edges on cards before {today}: {len(rows)}")
    if not rows:
        print("nothing to score.")
        return

    fights = _fights_by_id(base_url, key, {r["fight_id"] for r in rows})
    quotes = _quotes_by_fight(base_url, key, {r["fight_id"] for r in rows})

    results = []
    for r in rows:
        r["published_at"] = _iso(r.get("published_at"))
        fight = fights.get(r["fight_id"], {})
        results.append(score_row(
            edge=r, quotes=quotes.get(r["fight_id"], []), fight=fight,
            reference_instant=fight.get("start_at"), now=now,
            eligible_book_ids=eligible_book_ids,
            reference_basis=fight.get("start_basis"),
            is_first_bout=fight.get("is_first_bout")))

    _report_clv001(results)

    if not write_allowed:
        print("\nREPORT ONLY — nothing was written, and the publication gate was "
              "not touched. It stays shut until 100 scored observations across "
              "20 distinct events with an interval excluding zero.")
        return

    scored = [x for x in results if x["scored"]]
    for x in scored:
        patch_row(base_url, key, x["edge_id"], {
            "clv_return": round(x["clv_return"], 10),
            "closing_fair_probability": round(x["closing_fair_probability"], 10),
            "closing_book_count": x["closing_book_count"],
            "clv_protocol_version": PROTOCOL_TAG,
            "clv_scored_at": now.isoformat(),
            "clv_unscored_reason": None,
            "clv_source_quote_ids": x["quote_ids"],
            "clv_closing_consensus": x["consensus"],
            "clv_consensus_sha256": x["consensus_sha256"],
            "clv_close_basis": x["close_basis"],
            "clv_lead_time_minutes": round(x["lead_time_minutes"], 4),
            "clv_lead_time_is_lower_bound": x["lead_time_is_lower_bound"],
            "clv_proxy_quoted_at": x["proxy_quoted_at"].isoformat(),
            "clv_window_opened_at": (
                fights.get(x["fight_id"], {}).get("window_opens_at").isoformat()
                if fights.get(x["fight_id"], {}).get("window_opens_at") else None),
        })
    print(f"\nWROTE {len(scored)} CLV-001 result(s). Legacy clv_pp / clv_beat "
          f"were not read and not modified.")
    print("The publication gate is unchanged. Storing a number is not showing "
          "one.")


def _resolve_eligible_books(base_url: str, key: str,
                            named: list) -> set[int] | None:
    """Map Q-02's frozen NAMES onto book ids. Returns None if there is no list.

    Names, not ids: ids are a database detail that can be renumbered, and the
    protocol froze names. A named book the feed has never produced is not an
    error — it is simply absent from the consensus for every fight.
    """
    if not named:
        return None
    try:
        books = fetch_all(base_url, key, "odds_books", "select=id,name")
    except Exception:                           # noqa: BLE001
        return None
    want = {str(n).strip().lower() for n in named}
    return {b["id"] for b in books
            if str(b.get("name", "")).strip().lower() in want
            and is_eligible_book(b.get("name"))}


def _fights_by_id(base_url: str, key: str, fight_ids: set) -> dict:
    """Corners plus the close reference, per fight.

    The reference comes from `v_clv_close_reference`, which under v1.0.8 resolves
    exactly two cutoffs and says which one answered: the card's scheduled start
    for bout 1, and the immediately previous bout's exact completion for bouts
    2..N. A confirmed bell is NOT one of them — it is carried as an audit field
    and never substituted for the cutoff (Amendment 5.1). Scoring against real
    bells is a new protocol version, not a per-row upgrade inside this one.

    NOT from DUR-001's `v_fight_start_best`. Two reasons, both load-bearing.
    That view always answers — it falls back to the event date at 18:00 UTC — so
    taking its instant at face value hands every fight in the database a
    plausible-looking schedule. And it is defined in a frozen file serving a
    running experiment, so CLV-001 reads its own view rather than reinterpreting
    DUR-001's.

    `admissible_reference` is applied even though the view already filters, so
    the rule holds at both ends. A view can be replaced; this function is the
    one the tests pin.
    """
    out = {}
    for chunk in _chunks(sorted(fight_ids), 100):
        ids = ",".join(str(i) for i in chunk)
        for f in fetch_all(base_url, key, "fights",
                           f"select=id,event_id,fighter_a_id,fighter_b_id,bell_at"
                           f"&id=in.({ids})"):
            f["bell_at"] = _iso(f.get("bell_at"))
            f["start_at"], f["start_basis"] = None, None
            f["bout_order"], f["is_first_bout"] = None, None
            out[f["id"]] = f

        try:
            refs = fetch_all(base_url, key, "v_clv_close_reference",
                             f"select=fight_id,reference_at,reference_basis,"
                             f"bout_order,is_first_bout,actual_bell_at,"
                             f"prev_bout_completed_at"
                             f"&fight_id=in.({ids})")
        except Exception as e:                  # noqa: BLE001 - unknown is failed
            print(f"  note: v_clv_close_reference unavailable ({e}) — every row "
                  f"will be unscored for want of a close reference. Apply "
                  f"research/clv/proposed_2026-09-16_event_flow.sql.")
            refs = []
        for s in refs:
            f = out.get(s["fight_id"])
            if f is None:
                continue
            f["start_basis"] = s.get("reference_basis")
            f["bout_order"] = s.get("bout_order")
            f["is_first_bout"] = s.get("is_first_bout")
            # Carried separately and never used as the reference: the audit
            # field records when the fight actually began, which stays
            # comparable even if a later version changes the cutoff basis.
            f["actual_bell_at"] = _iso(s.get("actual_bell_at"))
            # When the bout before this one ended. Under Amendment 5 this IS the
            # cutoff for bouts 2..N — carried separately for provenance, and
            # never read as a claim that this fight began then.
            f["window_opens_at"] = _iso(s.get("prev_bout_completed_at"))
            f["start_at"] = admissible_reference(_iso(s.get("reference_at")),
                                                 s.get("reference_basis"),
                                                 s.get("is_first_bout"))
    return out


def _quotes_by_fight(base_url: str, key: str, fight_ids: set) -> dict:
    out: dict[int, list[dict]] = {}
    for chunk in _chunks(sorted(fight_ids), 50):
        ids = ",".join(str(i) for i in chunk)
        for q in fetch_all(base_url, key, "fight_odds",
                           f"select=id,fight_id,fighter_id,book_id,american_odds,"
                           f"implied_prob,captured_at&fight_id=in.({ids})"):
            q["captured_at"] = _iso(q.get("captured_at"))
            out.setdefault(q["fight_id"], []).append(q)
    return out


def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _report_clv001(results: list) -> None:
    """Counts, reasons and provenance. Deliberately NOT a headline statistic.

    Under R-05 the unscored count travels with any summary, so the reasons get
    the same prominence as the scored total — not a footnote. This print is also
    the only thing a dry run produces, so it has to be enough to act on.
    """
    scored = [x for x in results if x["scored"]]
    reasons: dict[str, int] = {}
    for x in results:
        if not x["scored"]:
            reasons[x["reason"]] = reasons.get(x["reason"], 0) + 1

    # DISTINCT EVENTS, by event_id — never by event_date. The UFC runs two cards
    # on one date often enough that counting dates would understate the event
    # count and let the 20-event gate open early on 19 real events.
    events = {x["event_id"] for x in scored if x["event_id"] is not None}
    undated = sum(1 for x in scored if x["event_id"] is None)
    print(f"\nscored   : {len(scored)} observation(s) across {len(events)} "
          f"distinct event(s), counted by event_id")
    if undated:
        print(f"  warning: {undated} scored row(s) carry no event_id and cannot "
              f"count toward the 20-event floor")
    print(f"unscored : {len(results) - len(scored)}")
    for reason in UNSCORED_REASONS:             # fixed order, so runs compare
        if reasons.get(reason):
            print(f"    {reasons[reason]:>4}  {reason}")
    unknown = set(reasons) - set(UNSCORED_REASONS)
    if unknown:                                 # cannot happen; assert it anyway
        raise AssertionError(f"reason outside the closed vocabulary: {unknown}")

    example = next((x for x in results if not x["scored"] and x["detail"]), None)
    if example:
        print(f"\n  e.g. edge {example['edge_id']} (fight {example['fight_id']}): "
              f"{example['detail']}")

    print(f"\ngate: 100 scored observations AND 20 distinct events (by event_id) "
          f"AND an event-cluster interval excluding zero.")
    print(f"      currently {len(scored)} / 100 and {len(events)} / 20. Blocked.")

    if scored:
        print("\nprovenance of the scored rows (no summary statistic is printed "
              "— the gate is shut):")
        for x in scored[:10]:
            print(f"  edge {x['edge_id']}  books={x['closing_book_count']}  "
                  f"quotes={x['quote_ids']}  sha={x['consensus_sha256'][:16]}…")
        if len(scored) > 10:
            print(f"  … and {len(scored) - 10} more")


def _summarise(planned: list) -> None:
    """Print the headline number for THIS run's rows.

    Deliberately loud. The whole point of settling is the number, and a cron
    that writes silently is how this metric sat null for months. Both the beat
    RATE and the average move are reported because they can disagree: many
    small wins against a few large losses is a good rate and no real edge,
    which is exactly what the first backfill showed.
    """
    if not planned:
        print("\nno settleable rows — nothing to summarise.")
        return
    vals = [pl["clv_pp"] for _, pl in planned]
    beat = sum(1 for v in vals if v > 0)
    mean = sum(vals) / len(vals)
    print(f"\nTHIS RUN: {beat}/{len(vals)} bets got a better price than the "
          f"close ({100.0 * beat / len(vals):.0f}%). "
          f"Average move {mean * 100:+.2f} points.")


if __name__ == "__main__":
    main()
