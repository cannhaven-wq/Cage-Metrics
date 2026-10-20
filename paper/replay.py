"""Historical replay of the pinned paper strategy, point-in-time, from per-book capture rows.

    python3 paper/replay.py --data paper/private/replay --out paper/private/replay/out

Read-only on its inputs. Uses the existing evaluator (strategy.evaluate_card),
ledger (Ledger.record_card) and settlement (settle.settle_one) unchanged; this
module only reconstructs, for each card, what was knowable at its decision
instant.

Point-in-time rules (each one tested in tests/paper/test_replay.py):

- The decision instant is the pinned config's lock: earliest VERIFIED start
  minus the configured lead. A start counts only if it was OBSERVED at or
  before that instant (fight_start_estimates.observed_at); bell_at is recorded
  after the bell and is never available at a pre-fight lock. The instant is the
  first moment the clock reaches the lock implied by what was known then.
- A sportsbook quote is ONE capture of ONE book: both corners' rows must carry
  the same captured_at. Sides are matched to corners by fighter_id (never by
  the stored side label). A row whose opponent_fighter_id names someone other
  than the other corner is dropped. Live rows and non-open markets are dropped.
  Nothing captured after the instant is visible.
- For each book the latest such pair at or before the instant is the book's
  quote; both rows' provider timestamps are kept and the OLDER one is used for
  freshness, so a quote is fresh only if both sides are.
- Which bookings are on the card is taken from today's is_active flag; a
  booking retired after the lock would wrongly be missing. Disclosed, and
  checked against the quotes (a retired booking with fresh quotes at the lock
  is reported).

Evidence classes, never mixed in one ledger:

- SETTLED: cards whose outcomes are outside every sealed partition. One
  continuous bankroll across them, chronological, settled after each card.
- DECISION-ONLY: cards in a sealed partition. Decisions are reconstructed;
  no outcome is read, nothing is settled, so the bankroll stop cannot be
  evaluated and is assumed not to have triggered (stated in the report).
- MISSED: cards with no lock (no verified start observed in time), no
  eligible book, or no fresh quote at the instant. Recorded with the reason.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import settle as S  # noqa: E402
from ledger import Ledger  # noqa: E402
from reference import build_reference, parse_ts  # noqa: E402
from strategy import evaluate_card  # noqa: E402

DEV_END = "2025-01-01"
H1_END = "2026-07-11"
RESERVE_END_EXCL = "2026-10-12"


def partition_of(event_date: str) -> str:
    d = str(event_date)[:10]
    if d < DEV_END:
        return "DEV"
    if d <= H1_END:
        return "H1"
    if d < RESERVE_END_EXCL:
        return "RESERVE"
    return "PROSPECTIVE"


def canon_sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


# --------------------------------------------------------------------------- the decision instant

def lock_at_point_in_time(fights: list[dict], starts: list[dict], event_date: str, cfg: dict) -> tuple[Optional[datetime], str, dict]:
    """The instant a live runner would have locked this card, using only what it knew then.

    L(t) = (earliest start known at t) - lead, where a bout's start is the latest
    provider estimate OBSERVED at or before t, or, if none yet, the pinned
    date-only fallback (00:00 UTC of the event date). Before any provider start
    is known the card cannot lock (verified start required). The lock is the
    FIRST t at which t >= L(t): the moment the clock reaches the lock implied by
    the information available at that moment. L is piecewise constant between
    observations, so it is enough to check each observation interval.

    starts: [{fight_id, source, start_at, observed_at}]; only 'odds_api_commence'
    is a provider start. bell_at is recorded after the bell and is never used.
    """
    lead = timedelta(minutes=float(cfg["lock"]["lead_minutes_before_earliest_start"]))
    active = [int(f["id"]) for f in fights if f.get("is_active") is not False]
    obs = sorted((parse_ts(s["observed_at"]), int(s["fight_id"]), parse_ts(s["start_at"]))
                 for s in starts if s.get("source") == "odds_api_commence" and int(s["fight_id"]) in active)
    if not obs:
        return None, "no provider start time observed for any active bout (verified bases: provider_commence; bell_at is post-hoc)", {}
    event_midnight = datetime.fromisoformat(str(event_date)[:10]).replace(tzinfo=timezone.utc)
    known: dict[int, datetime] = {}
    times = sorted({o for o, _, _ in obs})
    for i, t in enumerate(times):
        for o, fid, st in obs:
            if o == t:
                known[fid] = st                              # latest estimate observed so far
        basis = {fid: (("provider_commence", known[fid]) if fid in known else ("event_date_fallback", event_midnight)) for fid in active}
        L = min(v for _, v in basis.values()) - lead
        fire = max(t, L)                                     # cannot lock before the info existed
        nxt = times[i + 1] if i + 1 < len(times) else None
        if nxt is None or fire < nxt:
            if fire > L:
                return None, f"first verified start became known at {t.isoformat()}, after the lock it implies ({L.isoformat()}): card missed", \
                    {k: (b, v.isoformat()) for k, (b, v) in basis.items()}
            return fire, "ok", {k: (b, v.isoformat()) for k, (b, v) in basis.items()}
    return None, "unreachable", {}


# --------------------------------------------------------------------------- quotes as of the instant

def quotes_as_of(rows: list[dict], fight: dict, at: datetime, cfg: dict) -> tuple[list[dict], list[dict]]:
    """Latest same-capture two-sided quote per eligible book, at or before `at`.

    Returns (quotes in the evaluator's shape, exclusions with reasons).
    """
    a, b = int(fight["fighter_a_id"]), int(fight["fighter_b_id"])
    books = set(int(x) for x in cfg["venues"]["sportsbooks"]) - set(int(x) for x in cfg["reference"]["excluded_book_ids"])
    groups = defaultdict(list)
    excl = []
    for r in rows:
        if int(r["fight_id"]) != int(fight["id"]) or int(r["book_id"]) not in books:
            continue
        cap = parse_ts(r["captured_at"])
        if cap > at:
            continue                                     # not yet observed
        fid = int(r["fighter_id"])
        if fid not in (a, b):
            excl.append({"row_id": r["id"], "reason": "fighter not in the corners on file"}); continue
        opp = r.get("opponent_fighter_id")
        if opp is not None and int(opp) != (b if fid == a else a):
            excl.append({"row_id": r["id"], "reason": "opponent on the row is not the other corner"}); continue
        if r.get("is_live") is True:
            excl.append({"row_id": r["id"], "reason": "live (in-fight) quote"}); continue
        if r.get("market_status") not in (None, "open"):
            excl.append({"row_id": r["id"], "reason": f"market status {r.get('market_status')!r}"}); continue
        groups[(int(r["book_id"]), cap)].append(r)
    best: dict[int, tuple] = {}
    for (book, cap), rs in groups.items():
        sides = defaultdict(list)
        for r in rs:
            sides["a" if int(r["fighter_id"]) == a else "b"].append(r)
        if len(sides["a"]) != 1 or len(sides["b"]) != 1:
            continue                                     # one-sided or duplicated capture: not a quote
        if book not in best or best[book][0] < cap:
            best[book] = (cap, sides["a"][0], sides["b"][0])
    out = []
    for book, (cap, ra, rb) in sorted(best.items()):
        provs = [p for p in (ra.get("provider_last_update"), rb.get("provider_last_update")) if p]
        if provs and any(parse_ts(p) > at for p in provs):
            excl.append({"row_id": [ra["id"], rb["id"]], "reason": "provider timestamp after the instant"}); continue
        older = min(provs, key=parse_ts) if len(provs) == 2 else None
        out.append({"fight_id": int(fight["id"]), "book_id": book, "american_a": int(ra["american_odds"]),
                    "american_b": int(rb["american_odds"]), "captured_at": cap.isoformat(),
                    "provider_last_update": older, "row_ids": [ra["id"], rb["id"]],
                    "provider_last_update_a": ra.get("provider_last_update"), "provider_last_update_b": rb.get("provider_last_update"),
                    "provider_ts_note": None if older else "provider timestamp missing on at least one side; freshness by capture time only"})
    return out, excl


# --------------------------------------------------------------------------- one card

def replay_card(*, card: dict, fights: list[dict], starts: list[dict], rows: list[dict], cfg: dict,
                ledger: Optional[Ledger], strategy_version: str, bankroll: dict, strategies: tuple = ("M1",)) -> dict:
    lock, why, basis = lock_at_point_in_time(fights, starts, card["event_date"], cfg)
    active = [f for f in fights if f.get("is_active") is not False]
    rep = {"event_id": card["event_id"], "name": card["name"], "event_date": card["event_date"],
           "partition": partition_of(card["event_date"]), "active_bouts": len(active)}
    if lock is None:
        rep.update(status="missed", reason=why)
        return rep
    rep["lock_at"] = lock.isoformat()
    rep["start_basis"] = basis
    quotes, exclusions = {}, []
    for f in active:
        q, ex = quotes_as_of(rows, f, lock, cfg)
        quotes[int(f["id"])] = q
        exclusions += [dict(e, fight_id=int(f["id"])) for e in ex]
    rep["exclusions"] = exclusions
    rep["quotes_at_lock"] = {fid: len(q) for fid, q in quotes.items()}
    retired_with_quotes = []
    for f in fights:
        if f.get("is_active") is False:
            q, _ = quotes_as_of(rows, f, lock, cfg)
            if any(parse_ts(x["captured_at"]) >= lock - timedelta(minutes=float(cfg["offer"]["max_quote_age_minutes"])) for x in q):
                retired_with_quotes.append(int(f["id"]))
    rep["retired_bookings_with_fresh_quotes_at_lock"] = retired_with_quotes
    decisions = evaluate_card(card={"event_id": card["event_id"], "fights": active}, quotes_by_fight=quotes,
                              pm_books_by_fight={}, p_model_by_fight={}, cfg=cfg, now=lock, bankroll=bankroll)
    decisions = [d for d in decisions if d.strategy in strategies]
    rep["decisions"] = [d.to_dict() for d in decisions]
    rep["status"] = "evaluated"
    if ledger is not None:
        corners = {int(f["id"]): (int(f["fighter_a_id"]), int(f["fighter_b_id"])) for f in active}
        events = []
        for d in decisions:
            kind = "selection" if d.decision == "bet" else d.decision
            payload = d.to_dict(); payload.pop("decision", None)
            if kind == "selection":
                payload.update(fighter_id=d.offer["fighter_id"], fighter_a_id=corners[d.fight_id][0], fighter_b_id=corners[d.fight_id][1])
            events.append((kind, payload))
        ledger.record_card(card_id=card["event_id"], strategy_version=strategy_version, ts=lock.isoformat(),
                           lock={"lock_at": lock.isoformat(), "fight_ids": sorted(corners), "corners": {str(k): list(v) for k, v in corners.items()},
                                 "replay": True, "start_basis": basis}, events=events)
    return rep


def settle_card(ledger: Ledger, card: dict, outcomes: dict, at: str) -> list[dict]:
    """Settle every open selection of this card from outcome rows {fight_id: row}."""
    applied = []
    for sel in ledger.open_selections():
        if sel["card_id"] != card["event_id"]:
            continue
        f = outcomes.get(int(sel["fight_id"]))
        if f is None:
            continue
        res = S.settle_one(sel, f)
        if res is None:
            continue
        typ = res.pop("type")
        ledger.append(typ, card_id=sel["card_id"], strategy_version=sel["strategy_version"], ts=at,
                      selection_id=sel["event_id"], strategy=sel["strategy"], fight_id=sel["fight_id"], **res)
        applied.append({"selection_id": sel["event_id"], "fight_id": sel["fight_id"], "type": typ, **res})
    return applied


# --------------------------------------------------------------------------- the whole replay

def run_replay(*, data_dir: pathlib.Path, out_dir: pathlib.Path, cfg_path: pathlib.Path, expected_cfg_sha: Optional[str] = None) -> dict:
    cfg_bytes = cfg_path.read_bytes()
    cfg_sha = hashlib.sha256(cfg_bytes).hexdigest()
    if expected_cfg_sha and cfg_sha != expected_cfg_sha:
        raise SystemExit(f"config sha256 {cfg_sha} is not the pinned {expected_cfg_sha}")
    cfg = json.loads(cfg_bytes)
    meta = json.loads((data_dir / "card_meta.json").read_text())
    rows = json.loads((data_dir / "quote_rows.json").read_text())
    outcomes_rows = json.loads((data_dir / "outcomes_unsealed.json").read_text())
    for o in outcomes_rows:
        ev = next(f["event_id"] for f in meta["fights"] if int(f["id"]) == int(o["id"]))
        card = next(e for e in meta["events"] if e["event_id"] == ev)
        if partition_of(card["event_date"]) != "PROSPECTIVE":
            raise SystemExit(f"outcome for fight {o['id']} is in a sealed partition; refusing to read it")
    outcomes = {int(o["id"]): o for o in outcomes_rows}
    fingerprints = {"config_sha256": cfg_sha, "quote_rows": canon_sha(rows), "card_meta": canon_sha(meta),
                    "outcomes_unsealed": canon_sha(outcomes_rows)}
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in ("ledger_settled.jsonl", "ledger_decision_only.jsonl"):
        (out_dir / f).unlink(missing_ok=True)
        (out_dir / (f + ".lock")).unlink(missing_ok=True)
    settled_ledger = Ledger(out_dir / "ledger_settled.jsonl")
    sealed_ledger = Ledger(out_dir / "ledger_decision_only.jsonl")
    sv = cfg["strategy_version"] + "+replay"
    fights_by_event = defaultdict(list)
    for f in meta["fights"]:
        fights_by_event[f["event_id"]].append(f)
    starts_by_event = defaultdict(list)
    fight_event = {int(f["id"]): f["event_id"] for f in meta["fights"]}
    for s in meta["starts"]:
        starts_by_event[fight_event[int(s["fight_id"])]].append(s)
    rows_by_event = defaultdict(list)
    for r in rows:
        rows_by_event[r["event_id"]].append(r)
    today = datetime.now(timezone.utc).date().isoformat()
    cards = []
    for card in sorted(meta["events"], key=lambda e: e["event_date"]):
        if card["event_date"] >= today:
            continue                                     # unsettled, upcoming: not part of a historical replay
        part = partition_of(card["event_date"])
        settled_class = part == "PROSPECTIVE" and all(int(f["id"]) in outcomes for f in fights_by_event[card["event_id"]])
        ledger = settled_ledger if settled_class else sealed_ledger
        bankroll = {s: S.metrics(settled_ledger, cfg)["strategies"][s]["bankroll_settled"] for s in cfg["strategies"]} if settled_class \
            else {s: float(cfg["staking"]["bankroll_start"]) for s in cfg["strategies"]}
        rep = replay_card(card=card, fights=fights_by_event[card["event_id"]], starts=starts_by_event[card["event_id"]],
                          rows=rows_by_event[card["event_id"]], cfg=cfg, ledger=ledger,
                          strategy_version=sv, bankroll=bankroll)
        rep["evidence_class"] = "SETTLED" if settled_class else ("DECISION_ONLY_SEALED" if part in ("H1", "RESERVE", "DEV") else "DECISION_ONLY")
        rep["bankroll_before"] = bankroll.get("M1")
        if rep["status"] == "missed":
            ledger.append("missed_card", card_id=card["event_id"], strategy_version=sv, ts=card["event_date"], reason=rep["reason"])
        if settled_class and rep["status"] == "evaluated":
            rep["settlements"] = settle_card(settled_ledger, card, outcomes, at=card["event_date"] + "T23:59:59+00:00")
        cards.append(rep)
    m_settled = S.metrics(settled_ledger, cfg)
    report = {"fingerprints": fingerprints, "strategy_version": sv, "cards": cards,
              "metrics_settled": {"cards": m_settled["cards"], "M1": m_settled["strategies"]["M1"], "clv": m_settled["clv"]}}
    (out_dir / "replay_report.json").write_text(json.dumps(report, indent=1, default=str))
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="directory with card_meta.json, quote_rows.json, outcomes_unsealed.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--config", default=str(HERE / "config" / "strategy_draft.json"))
    ap.add_argument("--expect-config-sha256", help="refuse to run unless the config matches this pinned hash")
    args = ap.parse_args(argv)
    rep = run_replay(data_dir=pathlib.Path(args.data), out_dir=pathlib.Path(args.out), cfg_path=pathlib.Path(args.config),
                     expected_cfg_sha=args.expect_config_sha256)
    print(json.dumps({"fingerprints": rep["fingerprints"], "cards": [{k: c.get(k) for k in ("event_date", "name", "partition", "evidence_class", "status", "reason", "lock_at")} for c in rep["cards"]],
                      "metrics_settled_M1": rep["metrics_settled"]["M1"]}, indent=1, default=str))


if __name__ == "__main__":
    main()
