"""Run one card through the paper system: forecast, evaluate, record. Default is a dry run.

    python3 paper/run_card.py --snapshot path/to/snapshot.json [--now ISO] [--ledger path] [--write]
    python3 paper/run_card.py --live [--event-id N] ...            # read-only pull from Supabase
    python3 paper/run_card.py --settle --snapshot results.json      # settle open selections

Without --write nothing is appended to the ledger and nothing is sent anywhere:
the decisions, the would-be win_model_locks rows and the would-be ledger events
are printed. With --write the ledger file is appended (private, git-ignored).
Writing to win_model_locks is a separate, explicit --execute-locks flag that is
refused unless PAPER_ALLOW_LOCK_WRITE=1 is also set: starting prospective
collection is an owner decision (L3), not a command-line default.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import data as D  # noqa: E402
import settle as S  # noqa: E402
from ledger import Ledger, DuplicateRun  # noqa: E402
from reference import build_reference, parse_ts  # noqa: E402
from strategy import evaluate_card  # noqa: E402

DEFAULT_CFG = HERE / "config" / "strategy_draft.json"
DEFAULT_LEDGER = HERE / "private" / "ledger.jsonl"


def load_cfg(path) -> tuple[dict, str]:
    b = pathlib.Path(path).read_bytes()
    return json.loads(b), hashlib.sha256(b).hexdigest()


def forecast(snap: dict, cfg: dict, references: dict, artifact_path: str, tmpdir: pathlib.Path) -> dict:
    """Run MMA-001 for every fight on the card. Abstains (p_a None) where there is no reference."""
    if not snap.get("history"):
        return {"model_version": None, "artifact_sha256": None, "forecasts": [], "skipped": "no history in snapshot"}
    targets = []
    for f in snap["card"]["fights"]:
        fa = snap.get("fighters", {}).get(str(f["fighter_a_id"]), {}); fb = snap.get("fighters", {}).get(str(f["fighter_b_id"]), {})
        ref = references.get(int(f["id"]))
        targets.append({"fight_id": f["id"], "event_id": snap["card"]["event_id"], "event_date": snap["card"]["event_date"],
                        "a_id": f["fighter_a_id"], "b_id": f["fighter_b_id"], "a_dob": fa.get("dob"), "b_dob": fb.get("dob"),
                        "a_reach": fa.get("reach_in"), "b_reach": fb.get("reach_in"), "q": ref.p_a if ref else None})
    tmpdir.mkdir(parents=True, exist_ok=True)
    (tmpdir / "history.json").write_text(json.dumps(snap["history"]))
    (tmpdir / "targets.json").write_text(json.dumps({"targets": targets}))
    out = subprocess.run(["node", str(HERE / "mma001" / "forecast.js"), artifact_path, str(tmpdir / "history.json"), str(tmpdir / "targets.json")],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def lock_rows(snap: dict, cfg: dict, fc: dict, references: dict, lock_at: datetime, code_commit: str) -> list[dict]:
    """The win_model_locks rows this run would write (one per fight, p_a NULL = abstention)."""
    rows = []
    by_id = {f["fight_id"]: f for f in fc.get("forecasts", [])}
    for f in snap["card"]["fights"]:
        fid = int(f["id"]); r = by_id.get(fid, {}); ref = references.get(fid)
        rows.append({
            "fight_id": fid, "event_id": snap["card"]["event_id"], "fighter_a_id": f["fighter_a_id"], "fighter_b_id": f["fighter_b_id"],
            "p_a": r.get("p_a"), "experiment_id": cfg["model"]["experiment_id"], "model_name": cfg["model"]["name"],
            "model_version": fc.get("model_version"), "artifact_sha256": fc.get("artifact_sha256"), "code_commit": code_commit,
            "training_cutoff": "2024-12-31", "training_n_fights": 6335, "features": r.get("features"), "feature_hash": r.get("feature_hash"),
            "generated_at": lock_at.isoformat(),
            "market_p_a_vigfree": ref.p_a if ref else None, "market_book_count": len(ref.book_ids) if ref else 0,
            "market_quotes": [{"book_id": q["book_id"], "american_a": q["american_a"], "american_b": q["american_b"], "captured_at": q["captured_at"]} for q in (ref.quotes if ref else [])],
            "market_captured_at": max(q["captured_at"] for q in ref.quotes) if ref and ref.quotes else None,
            "market_source": "fight_odds via v_fight_odds_latest_by_book; proportional de-vig median", "notes": r.get("abstain_reason")})
    return rows


def run(args) -> dict:
    cfg, cfg_sha = load_cfg(args.config)
    snap = D.load_snapshot(args.snapshot) if args.snapshot else D.fetch_snapshot(args.event_id)
    now = parse_ts(args.now) if args.now else datetime.now(timezone.utc)
    lock_at, why = D.lock_instant(snap, cfg)
    report = {"card": {k: v for k, v in snap["card"].items() if k != "fights"}, "n_fights": len(snap["card"]["fights"]),
              "config_sha256": cfg_sha, "strategy_version": cfg["strategy_version"], "now": now.isoformat()}
    if lock_at is None:
        report.update(status="no_lock", reason=why); return report
    report["lock_at"] = lock_at.isoformat()
    if args.evaluate_at_capture:
        # A read-only look at the market as captured, BEFORE the lock. Never written, never a lock.
        now = parse_ts(args.now) if args.now else parse_ts(snap["captured_at"]); lock_at = now
        report.update(mode="dry_evaluation_at_capture", note=f"evaluated at {now.isoformat()}, not at the lock; nothing is recorded")
    elif now < lock_at:
        report.update(status="before_lock", reason=f"lock instant {lock_at.isoformat()} not reached"); return report
    if now - lock_at > __import__("datetime").timedelta(minutes=float(cfg["offer"]["max_quote_age_minutes"])):
        report.update(status="late", reason=f"now is {int((now - lock_at).total_seconds() // 60)} min after the lock instant; a late lock is refused, the card is recorded as missed"); return report
    fights = [f for f in snap["card"]["fights"] if f.get("is_active") is not False and f.get("winner_id") is None]
    card = {"event_id": snap["card"]["event_id"], "fights": fights}
    quotes = {}
    for q in snap["quotes"]:
        quotes.setdefault(int(q["fight_id"]), []).append(q)
    pm = {}
    for b in snap.get("polymarket_books", []):
        pm.setdefault(int(b["fight_id"]), []).append(b)
    references = {}
    for f in fights:
        ref, _ = build_reference(int(f["id"]), quotes.get(int(f["id"]), []), now=lock_at, cfg=cfg)
        if ref:
            references[int(f["id"])] = ref
    artifact = args.artifact or os.environ.get(cfg["model"]["artifact_env"], "")
    fc = forecast(snap, cfg, references, artifact, HERE / "private" / "tmp") if artifact and pathlib.Path(artifact).exists() else \
        {"model_version": None, "artifact_sha256": None, "forecasts": [], "skipped": "no model artifact available (PAPER_MODEL_ARTIFACT)"}
    p_model = {f["fight_id"]: f.get("p_a") for f in fc.get("forecasts", [])}
    ledger = Ledger(args.ledger)
    bankroll = {s: S.metrics(ledger, cfg)["strategies"][s]["bankroll_settled"] for s in cfg["strategies"]}
    decisions = evaluate_card(card={"event_id": card["event_id"], "fights": fights}, quotes_by_fight=quotes, pm_books_by_fight=pm,
                              p_model_by_fight=p_model, cfg=cfg, now=lock_at, bankroll=bankroll)
    code_commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=HERE.parent).stdout.strip() or "unknown"
    rows = lock_rows(snap, cfg, fc, references, lock_at, code_commit)
    report.update(status="evaluated", model=fc.get("model_version"), artifact_sha256=fc.get("artifact_sha256"), model_skipped=fc.get("skipped"),
                  bankroll=bankroll, decisions=[d.to_dict() for d in decisions], win_model_locks_rows=rows,
                  forecasts_abstained=sum(1 for r in rows if r["p_a"] is None))
    if args.write and args.evaluate_at_capture:
        report["ledger_appended"] = False; report["write_refused"] = "a pre-lock dry evaluation is never recorded"
    elif args.write:
        try:
            lock = ledger.record_lock(card_id=card["event_id"], strategy_version=cfg["strategy_version"], ts=now.isoformat(), lock_at=lock_at.isoformat(),
                                      config_sha256=cfg_sha, model_version=fc.get("model_version"), artifact_sha256=fc.get("artifact_sha256"),
                                      fight_ids=[int(f["id"]) for f in fights], corners={str(f["id"]): [f["fighter_a_id"], f["fighter_b_id"]] for f in fights},
                                      snapshot_captured_at=snap["captured_at"], code_commit=code_commit)
        except DuplicateRun as e:
            report.update(status="duplicate_run", reason=str(e)); return report
        for r in rows:
            ledger.append("forecast", card_id=card["event_id"], strategy_version=cfg["strategy_version"], ts=now.isoformat(), lock_event_id=lock["event_id"], **r)
        corners = {int(f["id"]): (f["fighter_a_id"], f["fighter_b_id"]) for f in fights}
        for d in decisions:
            kind = "selection" if d.decision == "bet" else d.decision
            payload = d.to_dict(); payload.pop("decision", None)
            if kind == "selection":
                payload.update(fighter_id=d.offer["fighter_id"], fighter_a_id=corners[d.fight_id][0], fighter_b_id=corners[d.fight_id][1], model_version=fc.get("model_version"))
            ledger.append(kind, card_id=card["event_id"], strategy_version=cfg["strategy_version"], ts=now.isoformat(), lock_event_id=lock["event_id"], **payload)
        report["ledger_appended"] = True
    if args.execute_locks:
        if os.environ.get("PAPER_ALLOW_LOCK_WRITE") != "1":
            report["win_model_locks"] = "refused: PAPER_ALLOW_LOCK_WRITE is not set; writing locks starts prospective collection (L3)"
        else:
            report["win_model_locks"] = write_locks(rows)
    return report


def write_locks(rows: list[dict]) -> str:
    """Insert into win_model_locks over PostgREST. The table's own triggers decide the lock time and refuse late or settled rows."""
    import urllib.request
    base = os.environ.get("SUPABASE_URL", "").rstrip("/"); key = D._env_key()
    if not base or not key:
        return "refused: no database credentials"
    body = json.dumps([{k: v for k, v in r.items() if k not in ("fighter_a_id", "fighter_b_id")} | {"fighter_a_id": r["fighter_a_id"], "fighter_b_id": r["fighter_b_id"]} for r in rows]).encode()
    req = urllib.request.Request(f"{base}/rest/v1/win_model_locks", data=body, method="POST", headers={
        "apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Prefer": "return=minimal,resolution=ignore-duplicates"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return f"inserted (HTTP {r.status})"


def settle(args) -> dict:
    cfg, _ = load_cfg(args.config)
    snap = D.load_snapshot(args.snapshot) if args.snapshot else D.fetch_snapshot(args.event_id, history=False)
    fights = {int(f["id"]): f for f in snap["card"]["fights"]}
    ledger = Ledger(args.ledger)
    now = parse_ts(args.now) if args.now else datetime.now(timezone.utc)
    applied = []
    for sel in ledger.open_selections():
        f = fights.get(int(sel["fight_id"]))
        if f is None:
            continue
        res = S.settle_one(sel, f)
        if res is None:
            continue
        applied.append({"selection_id": sel["event_id"], "strategy": sel["strategy"], "fight_id": sel["fight_id"], **res})
        if args.write:
            typ = res.pop("type")
            ledger.append(typ, card_id=sel["card_id"], strategy_version=sel["strategy_version"], ts=now.isoformat(), selection_id=sel["event_id"], strategy=sel["strategy"], fight_id=sel["fight_id"], **res)
    m = S.metrics(ledger, cfg)
    if args.write:
        ledger.append("look", card_id=snap["card"]["event_id"], strategy_version=cfg["strategy_version"], ts=now.isoformat(), metrics=m)
    return {"applied": applied, "metrics": m}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot"); ap.add_argument("--live", action="store_true"); ap.add_argument("--event-id", type=int)
    ap.add_argument("--config", default=str(DEFAULT_CFG)); ap.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    ap.add_argument("--artifact", help="MMA-001 artifact path (default: $PAPER_MODEL_ARTIFACT)")
    ap.add_argument("--now", help="ISO instant to evaluate at (tests and dry runs)")
    ap.add_argument("--evaluate-at-capture", action="store_true", help="read-only look at the captured market before the lock; never recorded")
    ap.add_argument("--write", action="store_true", help="append to the ledger (default: print only)")
    ap.add_argument("--execute-locks", action="store_true", help="also insert win_model_locks rows (needs PAPER_ALLOW_LOCK_WRITE=1)")
    ap.add_argument("--settle", action="store_true", help="settle open selections from the snapshot's fight rows")
    args = ap.parse_args(argv)
    if not args.snapshot and not args.live:
        ap.error("give --snapshot FILE or --live")
    out = settle(args) if args.settle else run(args)
    print(json.dumps(out, indent=1, default=str))
    return out


if __name__ == "__main__":
    main()
