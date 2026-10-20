"""Regression tests for the review findings on commit 8549c9c.

1. Polymarket books reach the evaluator (table rows and a capture_book JSONL file).
2. A BUY's fee is collected in shares, as Polymarket documents it.
3. --evaluate-at-capture can never reach a database write.
4. Recording a card is atomic, serialised across processes, and crash-recoverable.
5. Forecast and lock rows cover only the bookings the evaluator covers.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
from datetime import timedelta

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
PAPER = REPO / "paper"
sys.path.insert(0, str(PAPER))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import data as D  # noqa: E402
import run_card as R  # noqa: E402
from ledger import Ledger, DuplicateRun, LedgerCorrupt  # noqa: E402
from pricing import polymarket_fill, polymarket_offer  # noqa: E402
from test_paper_system import CFG, EVEN, T0, fight, full_snapshot, iso, pm_book, quotes_for, snapshot  # noqa: E402


# ----------------------------------------------------------------------------- 2. fee in shares

def test_buy_fee_is_collected_in_shares_not_added_to_cash():
    fill = polymarket_fill(asks=[{"price": "0.50", "size": "1000"}], budget=100.0, fee_rate_bps=1000)
    assert fill["spent"] == pytest.approx(100.0), "the cash risked is the cash spent at the ask"
    assert fill["shares_gross"] == pytest.approx(200.0)
    assert fill["fee_shares"] == pytest.approx(200 * 0.10 * 0.5 * 0.5) and fill["fee_denomination"] == "shares"
    assert fill["shares"] == pytest.approx(195.0), "net shares = gross minus the fee taken in shares"
    book = pm_book(1, "a", 100, [{"price": "0.50", "size": "1000"}], fee_bps=1000)
    o = polymarket_offer(venue_id=7, fight_id=1, side="a", fighter_id=100, book=book, stake=1.0, retrieved_at=iso(T0), provider_ts=None, unit_notional=100.0)
    assert o.stake_cost == pytest.approx(1.0) and o.net_if_win == pytest.approx(0.95)
    # zero fee: a 0.50 ask is exactly even money
    book0 = pm_book(1, "a", 100, [{"price": "0.50", "size": "1000"}], fee_bps=0)
    o0 = polymarket_offer(venue_id=7, fight_id=1, side="a", fighter_id=100, book=book0, stake=1.0, retrieved_at=iso(T0), provider_ts=None, unit_notional=100.0)
    assert o0.net_if_win == pytest.approx(1.0) and o0.equivalent_american == pytest.approx(100)


# ----------------------------------------------------------------------------- 3. flags

def test_dry_evaluation_can_never_reach_a_write(tmp_path):
    p = tmp_path / "s.json"; p.write_text(json.dumps(full_snapshot()))
    for flags in (["--write"], ["--execute-locks"], ["--write", "--execute-locks"]):
        with pytest.raises(SystemExit):
            R.parse_args(["--snapshot", str(p), "--evaluate-at-capture", *flags])
    with pytest.raises(SystemExit):
        R.parse_args(["--snapshot", str(p), "--execute-locks"])      # a database lock without a ledger record
    assert R.parse_args(["--snapshot", str(p), "--evaluate-at-capture"]).evaluate_at_capture


# ----------------------------------------------------------------------------- 4. atomic, serialised, recoverable

RACER = r"""
import sys, json, time
sys.path.insert(0, sys.argv[1])
from ledger import Ledger, DuplicateRun
led = Ledger(sys.argv[2])
seen = led.lock_for(9, "v")                 # both racers look first and see nothing
time.sleep(0.2)
try:
    led.record_card(card_id=9, strategy_version="v", lock={"who": sys.argv[3]}, events=[("selection", {"strategy": "M1", "fight_id": 1, "stake": 1.0})])
    print(json.dumps({"who": sys.argv[3], "saw_lock": bool(seen), "result": "recorded"}))
except DuplicateRun:
    print(json.dumps({"who": sys.argv[3], "saw_lock": bool(seen), "result": "duplicate"}))
"""


def test_two_processes_cannot_both_record_the_same_card(tmp_path):
    led = tmp_path / "l.jsonl"
    racer = tmp_path / "racer.py"; racer.write_text(RACER)
    procs = [subprocess.Popen([sys.executable, str(racer), str(PAPER), str(led), who], stdout=subprocess.PIPE, text=True) for who in ("A", "B")]
    outs = [json.loads(p.communicate()[0]) for p in procs]
    assert all(not o["saw_lock"] for o in outs), "both saw no lock before writing"
    assert sorted(o["result"] for o in outs) == ["duplicate", "recorded"]
    l = Ledger(led)
    assert len(l.events("selection")) == 1 and len(l.events("lock")) == 1 and l.lock_for(9, "v")


def test_crash_after_lock_is_recovered_without_losing_the_record(tmp_path):
    path = tmp_path / "l.jsonl"
    led = Ledger(path)
    led.record_card(card_id=9, strategy_version="v", lock={"n": 1}, events=[("selection", {"strategy": "M1", "fight_id": 1, "stake": 1.0}),
                                                                         ("pass", {"strategy": "M1", "fight_id": 2})])
    full = path.read_text().splitlines()
    # simulate a crash: the commit line was never written, and the last decision line is cut in half
    path.write_text("\n".join(full[:-2]) + "\n" + full[-2][: len(full[-2]) // 2])
    crashed = Ledger(path)
    assert crashed.incomplete_lock_id and crashed.skipped_lines == [3]
    assert crashed.lock_for(9, "v") is None, "an uncommitted lock is not a lock"
    assert crashed.events("selection") == [], "events of an incomplete batch are not visible"
    # the rerun completes the card: the old batch is retired in place, nothing is removed
    lock2 = crashed.record_card(card_id=9, strategy_version="v", lock={"n": 2}, events=[("selection", {"strategy": "M1", "fight_id": 1, "stake": 1.0})])
    again = Ledger(path)
    assert again.lock_for(9, "v")["event_id"] == lock2["event_id"]
    assert len(again.events("selection")) == 1 and len(again.events("card_abort")) == 1
    assert again.skipped_lines == [3], "the truncated line stays in the file, skipped"
    text = path.read_text()
    assert full[0] in text and full[1] in text, "the original lines were not rewritten"
    with pytest.raises(DuplicateRun):
        again.record_card(card_id=9, strategy_version="v", lock={"n": 3}, events=[])


def test_a_damaged_middle_line_is_still_corruption(tmp_path):
    path = tmp_path / "l.jsonl"
    led = Ledger(path)
    led.record_card(card_id=9, strategy_version="v", lock={}, events=[("pass", {"strategy": "M1", "fight_id": 1})])
    lines = path.read_text().splitlines()
    lines[1] = lines[1][:20]          # a committed line made unparseable
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(LedgerCorrupt):
        Ledger(path)


# ----------------------------------------------------------------------------- 5. retired and settled bookings

def test_forecast_and_lock_rows_cover_only_eligible_bookings(tmp_path):
    snap = full_snapshot()
    snap["card"]["fights"].append({**fight(4, 104, 204), "is_active": False})
    snap["card"]["fights"].append({**fight(5, 105, 205), "winner_id": 105, "method": "KO/TKO"})
    snap["starts"] += [{"fight_id": 4, "start_at": "2026-10-23T18:00:00+00:00", "start_basis": "event_date_fallback"},
                       {"fight_id": 5, "start_at": "2026-10-24T22:00:00+00:00", "start_basis": "provider_commence"}]
    p = tmp_path / "s.json"; p.write_text(json.dumps(snap))
    out = R.main(["--snapshot", str(p), "--now", iso(T0 + timedelta(minutes=5)), "--ledger", str(tmp_path / "l.jsonl")])
    assert out["status"] == "evaluated", out
    assert out["lock_at"] == iso(T0), "a retired booking's date-only start does not move the lock"
    assert sorted(r["fight_id"] for r in out["win_model_locks_rows"]) == [1, 2, 3]
    assert {d["fight_id"] for d in out["decisions"]} == {1, 2, 3}


# ----------------------------------------------------------------------------- 1. polymarket reaches the evaluator

def test_polymarket_books_from_a_capture_file_reach_a_decision(tmp_path):
    snap = snapshot([fight(1, 101, 201)], [{"fight_id": 1, "start_at": "2026-10-24T22:00:00+00:00", "start_basis": "provider_commence"}], quotes_for(1, EVEN))
    p = tmp_path / "s.json"; p.write_text(json.dumps(snap))
    now = T0 + timedelta(minutes=5)
    good = pm_book(1, "a", 101, [{"price": "0.44", "size": "5000"}], fee_bps=0, retrieved_at=iso(T0 - timedelta(minutes=2)), book_timestamp=iso(T0 - timedelta(minutes=2)))
    stale_newer = {**good, "asks": [{"price": "0.30", "size": "5000"}], "retrieved_at": iso(T0 + timedelta(minutes=30)), "book_timestamp": iso(T0 + timedelta(minutes=30))}
    older = {**good, "asks": [{"price": "0.60", "size": "5000"}], "retrieved_at": iso(T0 - timedelta(minutes=20)), "book_timestamp": iso(T0 - timedelta(minutes=20))}
    books = tmp_path / "books.jsonl"; books.write_text("\n".join(json.dumps(b) for b in (older, good, stale_newer)) + "\n")
    out = R.main(["--snapshot", str(p), "--now", iso(now), "--ledger", str(tmp_path / "l.jsonl"), "--polymarket-books", str(books)])
    assert out["polymarket_books_considered"] == 1, "the newest capture at or before the lock represents the token"
    m1 = next(d for d in out["decisions"] if d["strategy"] == "M1")
    assert m1["decision"] == "bet" and m1["offer"]["venue_kind"] == "polymarket" and m1["offer"]["source"]["asks"][0]["price"] == "0.44"
    assert "file" in out["polymarket_books_source"]
    # the same rows arriving as table rows inside the snapshot are used the same way
    snap["polymarket_books"] = [older, good, stale_newer]; p.write_text(json.dumps(snap))
    out2 = R.main(["--snapshot", str(p), "--now", iso(now), "--ledger", str(tmp_path / "l2.jsonl")])
    assert next(d for d in out2["decisions"] if d["strategy"] == "M1")["offer"]["venue_kind"] == "polymarket"


def test_latest_polymarket_books_picks_per_token_and_ignores_future_captures():
    rows = [{"fight_id": 1, "token_id": "t", "retrieved_at": iso(T0 - timedelta(minutes=9)), "v": 1},
            {"fight_id": 1, "token_id": "t", "retrieved_at": iso(T0 - timedelta(minutes=1)), "v": 2},
            {"fight_id": 1, "token_id": "t", "retrieved_at": iso(T0 + timedelta(minutes=1)), "v": 3},
            {"fight_id": 2, "token_id": "u", "retrieved_at": iso(T0 - timedelta(minutes=1)), "v": 4},
            {"fight_id": 1, "token_id": "t", "retrieved_at": "2026-10-24 15:00:00", "v": 5}]
    got = D.latest_polymarket_books(rows, now=T0, fight_ids={1})
    assert [r["v"] for r in got] == [2], "newest at-or-before the lock, this card only, naive timestamps ignored"


# ----------------------------------------------------------------------------- forecast path consistency (same-author check)

def test_forecast_path_matches_the_docs_feature_path_on_dev_history():
    hist = PAPER / "private" / "history_all.json"
    if not hist.exists():
        pytest.skip("private history export not present")
    out = subprocess.run(["node", str(PAPER / "mma001" / "audit_forecast_path.js"), str(hist), "60"], capture_output=True, text=True)
    res = json.loads(out.stdout)
    assert out.returncode == 0 and res["pass"] and res["checked"] == 60 and res["max_abs_feature_difference"] <= 1e-12, res
