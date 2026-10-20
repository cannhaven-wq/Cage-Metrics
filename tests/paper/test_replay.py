"""Historical replay, arbitrage scan and Polymarket fee arithmetic.

Run:  python3 -m pytest -q tests/paper/test_replay.py
"""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
PAPER = REPO / "paper"
sys.path.insert(0, str(PAPER))
import arbitrage as A  # noqa: E402
import replay as RP  # noqa: E402
import settle as S  # noqa: E402
from ledger import Ledger, DuplicateRun  # noqa: E402
from pricing import OfferRejected, polymarket_fill, polymarket_offer, round_fee  # noqa: E402

CFG = json.loads((PAPER / "config" / "strategy_draft.json").read_text())
START = datetime(2026, 11, 7, 22, 0, tzinfo=timezone.utc)          # earliest bout start
LOCK = START - timedelta(minutes=360)
iso = lambda t: t.isoformat()  # noqa: E731


def fight(fid, a, b, active=True):
    return {"id": fid, "event_id": 1, "fighter_a_id": a, "fighter_b_id": b, "fighter_a_name": f"A{a}", "fighter_b_name": f"B{b}", "is_active": active}


def start_row(fid, at, observed):
    return {"fight_id": fid, "source": "odds_api_commence", "start_at": iso(at), "observed_at": iso(observed)}


_id = [0]


def row(fid, fighter, opp, book, odds, cap, prov=None, live=None, status="open"):
    _id[0] += 1
    return {"id": _id[0], "fight_id": fid, "fighter_id": fighter, "opponent_fighter_id": opp, "book_id": book, "american_odds": odds,
            "captured_at": iso(cap), "provider_last_update": iso(prov or cap), "is_live": live, "market_status": status, "event_id": 1}


def pair(fid, a, b, book, oa, ob, cap, prov=None):
    return [row(fid, a, b, book, oa, cap, prov), row(fid, b, a, book, ob, cap, prov)]


# ----------------------------------------------------------------------------- decision instant: no future starts, no bell

def test_lock_uses_only_starts_observed_by_the_lock():
    fights = [fight(1, 10, 20), fight(2, 30, 40)]
    early_obs = START - timedelta(days=5)
    starts = [start_row(1, START, early_obs), start_row(2, START + timedelta(hours=1), early_obs),
              # a later, EARLIER start learned after the lock must not move it
              start_row(1, START - timedelta(hours=3), LOCK + timedelta(minutes=30))]
    lock, why, basis = RP.lock_at_point_in_time(fights, starts, "2026-11-07", CFG)
    assert lock == LOCK and basis[1][1] == iso(START)


def test_lock_falls_back_to_event_midnight_when_a_bout_has_no_start_yet_and_never_uses_bell():
    fights = [fight(1, 10, 20), fight(2, 30, 40)]
    starts = [start_row(1, START, START - timedelta(days=5))]       # bout 2 has no provider start at all
    lock, _, basis = RP.lock_at_point_in_time(fights, starts, "2026-11-07", CFG)
    assert lock == datetime(2026, 11, 6, 18, 0, tzinfo=timezone.utc) and basis[2][0] == "event_date_fallback"
    lock, why, _ = RP.lock_at_point_in_time(fights, [], "2026-11-07", CFG)
    assert lock is None and "bell_at" in why


def test_lock_fires_at_the_first_instant_the_clock_reaches_it():
    fights = [fight(1, 10, 20), fight(2, 30, 40)]
    # bout 2's start is only observed AFTER the fallback instant (event-day 00:00 - 6h): a live runner had already locked
    starts = [start_row(1, START, START - timedelta(days=5)), start_row(2, START, datetime(2026, 11, 7, 2, 0, tzinfo=timezone.utc))]
    lock, _, basis = RP.lock_at_point_in_time(fights, starts, "2026-11-07", CFG)
    assert lock == datetime(2026, 11, 6, 18, 0, tzinfo=timezone.utc) and basis[2][0] == "event_date_fallback"
    # bout 2's start observed BEFORE the fallback instant: the true lock applies
    starts = [start_row(1, START, START - timedelta(days=5)), start_row(2, START, START - timedelta(days=2))]
    lock, _, _ = RP.lock_at_point_in_time(fights, starts, "2026-11-07", CFG)
    assert lock == LOCK
    # the first provider start is only learned after the lock it implies: the card is missed, never locked late
    late = [start_row(1, START, LOCK + timedelta(minutes=10)), start_row(2, START, LOCK + timedelta(minutes=10))]
    lock, why, _ = RP.lock_at_point_in_time(fights, late, "2026-11-07", CFG)
    assert lock is None and "missed" in why


# ----------------------------------------------------------------------------- quotes as of the instant

def test_future_quotes_and_future_provider_stamps_are_invisible():
    f = fight(1, 10, 20)
    rows = pair(1, 10, 20, 1, -150, 130, LOCK - timedelta(minutes=10)) + pair(1, 10, 20, 1, -500, 400, LOCK + timedelta(minutes=1))
    q, _ = RP.quotes_as_of(rows, f, LOCK, CFG)
    assert [(x["american_a"], x["american_b"]) for x in q] == [(-150, 130)]
    rows = pair(1, 10, 20, 3, -150, 130, LOCK - timedelta(minutes=10), prov=LOCK + timedelta(minutes=5))
    q, ex = RP.quotes_as_of(rows, f, LOCK, CFG)
    assert q == [] and any("after the instant" in e["reason"] for e in ex)


def test_sides_are_matched_by_fighter_id_not_row_order():
    f = fight(1, 10, 20)
    cap = LOCK - timedelta(minutes=5)
    rows = [row(1, 20, 10, 1, 130, cap), row(1, 10, 20, 1, -150, cap)]       # corner B's row first
    q, _ = RP.quotes_as_of(rows, f, LOCK, CFG)
    assert q[0]["american_a"] == -150 and q[0]["american_b"] == 130


def test_two_captures_are_never_combined_into_one_quote():
    f = fight(1, 10, 20)
    rows = [row(1, 10, 20, 1, -150, LOCK - timedelta(minutes=50)), row(1, 20, 10, 1, 130, LOCK - timedelta(minutes=5))]
    q, _ = RP.quotes_as_of(rows, f, LOCK, CFG)
    assert q == [], "side A from one capture and side B from another is not a quote"
    rows += [row(1, 10, 20, 1, -160, LOCK - timedelta(minutes=5))]
    q, _ = RP.quotes_as_of(rows, f, LOCK, CFG)
    assert [(x["american_a"], x["american_b"]) for x in q] == [(-160, 130)]


def test_changed_opponent_rows_and_strangers_are_dropped():
    f = fight(1, 10, 20)
    cap = LOCK - timedelta(minutes=5)
    rows = [row(1, 10, 99, 1, -150, cap), row(1, 20, 10, 1, 130, cap),       # A's row names opponent 99
            row(1, 77, 20, 3, -150, cap), row(1, 20, 77, 3, 130, cap)]       # a fighter not on the card
    q, ex = RP.quotes_as_of(rows, f, LOCK, CFG)
    assert q == [] and {e["reason"] for e in ex} >= {"opponent on the row is not the other corner", "fighter not in the corners on file"}


def test_live_rows_excluded_books_and_closed_markets_are_dropped():
    f = fight(1, 10, 20)
    cap = LOCK - timedelta(minutes=5)
    rows = [row(1, 10, 20, 1, -150, cap, live=True), row(1, 20, 10, 1, 130, cap, live=True)]
    rows += pair(1, 10, 20, 14, -150, 130, cap) + pair(1, 10, 20, 6, -150, 130, cap) + pair(1, 10, 20, 7, -150, 130, cap)
    rows += [row(1, 10, 20, 3, -150, cap, status="closed"), row(1, 20, 10, 3, 130, cap, status="closed")]
    q, _ = RP.quotes_as_of(rows, f, LOCK, CFG)
    assert q == []


# ----------------------------------------------------------------------------- the whole card, ledger, bankroll

def card_rows(fid, a, b, oa_best, cap):
    rows = []
    for book in (1, 3, 11):
        rows += pair(fid, a, b, book, -110, -110, cap)
    rows += pair(fid, a, b, 9, oa_best, -150, cap)
    return rows


def test_replay_card_end_to_end_with_stale_and_fresh_cards(tmp_path):
    fights = [fight(i, 100 + i, 200 + i) for i in range(1, 7)]
    starts = [start_row(i, START, START - timedelta(days=3)) for i in range(1, 7)]
    rows = []
    for i in range(1, 7):
        rows += card_rows(i, 100 + i, 200 + i, 100 + 5 * i, LOCK - timedelta(minutes=20))
    led = Ledger(tmp_path / "l.jsonl")
    rep = RP.replay_card(card={"event_id": 1, "name": "t", "event_date": "2026-11-07"}, fights=fights, starts=starts, rows=rows,
                         cfg=CFG, ledger=led, strategy_version="v", bankroll={"M1": 100.0, "S1": 100.0})
    m1 = [d for d in rep["decisions"] if d["strategy"] == "M1"]
    assert {d["strategy"] for d in rep["decisions"]} == {"M1"}, "only M1 is replayed"
    bets = [d for d in m1 if d["decision"] == "bet"]
    assert len(bets) == 4 and sorted(b["fight_id"] for b in bets) == [3, 4, 5, 6], "card cap 4, ranked by reference return"
    assert all(b["offer"]["venue_id"] == 9 for b in bets)
    with pytest.raises(DuplicateRun):
        RP.replay_card(card={"event_id": 1, "name": "t", "event_date": "2026-11-07"}, fights=fights, starts=starts, rows=rows,
                       cfg=CFG, ledger=led, strategy_version="v", bankroll={"M1": 100.0})
    # the same prices two hours stale: every fight abstains, no bet
    stale = []
    for i in range(1, 7):
        stale += card_rows(i, 100 + i, 200 + i, 100 + 5 * i, LOCK - timedelta(minutes=120))
    rep2 = RP.replay_card(card={"event_id": 2, "name": "t2", "event_date": "2026-11-07"}, fights=fights, starts=starts, rows=stale,
                          cfg=CFG, ledger=None, strategy_version="v", bankroll={"M1": 100.0})
    assert all(d["decision"] == "abstain" for d in rep2["decisions"])


def test_bankroll_is_continuous_and_the_stop_binds_on_later_cards(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    fights = [fight(i, 100 + i, 200 + i) for i in range(1, 5)]
    starts = [start_row(i, START, START - timedelta(days=3)) for i in range(1, 5)]
    rows = []
    for i in range(1, 5):
        rows += card_rows(i, 100 + i, 200 + i, 125, LOCK - timedelta(minutes=20))
    # pre-load 29 units of settled losses so the bankroll stands at 71
    for k in range(29):
        s = led.append("selection", card_id=1000 + k, strategy_version="v", strategy="M1", fight_id=k, stake=1.0, ts=f"2026-01-{k % 28 + 1:02d}T00:00:00+00:00")
        led.append("settlement", card_id=1000 + k, strategy_version="v", selection_id=s["event_id"], strategy="M1", result="loss", pnl=-1.0)
    br = S.metrics(led, CFG)["strategies"]["M1"]["bankroll_settled"]
    assert br == pytest.approx(71.0)
    rep = RP.replay_card(card={"event_id": 5, "name": "c", "event_date": "2026-11-07"}, fights=fights, starts=starts, rows=rows,
                         cfg=CFG, ledger=led, strategy_version="v", bankroll={"M1": br})
    assert sum(d["decision"] == "bet" for d in rep["decisions"]) == 4
    for s in led.open_selections():
        led.append("settlement", card_id=s["card_id"], strategy_version="v", selection_id=s["event_id"], strategy="M1", result="loss", pnl=-1.0)
    br2 = S.metrics(led, CFG)["strategies"]["M1"]["bankroll_settled"]
    assert br2 == pytest.approx(67.0)
    rep2 = RP.replay_card(card={"event_id": 6, "name": "d", "event_date": "2026-11-14"}, fights=fights, starts=starts, rows=rows,
                          cfg=CFG, ledger=None, strategy_version="v", bankroll={"M1": br2})
    assert all(d["decision"] != "bet" for d in rep2["decisions"]) and any("stop" in d["reason"] for d in rep2["decisions"])


def test_replay_refuses_a_sealed_outcome_and_a_different_config(tmp_path):
    d = tmp_path / "data"; d.mkdir()
    meta = {"events": [{"event_id": 9, "name": "sealed", "event_date": "2026-09-19"}], "fights": [fight(1, 10, 20) | {"event_id": 9}], "starts": []}
    (d / "card_meta.json").write_text(json.dumps(meta)); (d / "quote_rows.json").write_text("[]")
    (d / "outcomes_unsealed.json").write_text(json.dumps([{"id": 1, "fighter_a_id": 10, "fighter_b_id": 20, "winner_id": 10, "method": "KO", "is_active": True}]))
    with pytest.raises(SystemExit, match="sealed partition"):
        RP.run_replay(data_dir=d, out_dir=tmp_path / "o", cfg_path=PAPER / "config" / "strategy_draft.json")
    with pytest.raises(SystemExit, match="not the pinned"):
        RP.run_replay(data_dir=d, out_dir=tmp_path / "o", cfg_path=PAPER / "config" / "strategy_draft.json", expected_cfg_sha="0" * 64)


def test_partitions():
    assert RP.partition_of("2024-12-31") == "DEV" and RP.partition_of("2026-07-11") == "H1"
    assert RP.partition_of("2026-10-11") == "RESERVE" and RP.partition_of("2026-10-17") == "PROSPECTIVE"


# ----------------------------------------------------------------------------- Polymarket fees: units and documented values

@pytest.mark.parametrize("p,fee_usd,fee_sh", [(0.25, 0.9375, 3.75), (0.50, 1.25, 2.5), (0.75, 0.9375, 1.25)])
def test_fee_for_100_shares_matches_the_documented_sports_table(p, fee_usd, fee_sh):
    # docs.polymarket.com/trading/fees, Sports column, 100 shares: $0.94 at 0.25, $1.25 at 0.50, $0.94 at 0.75 (cents)
    fill = polymarket_fill(asks=[{"price": str(p), "size": "1000"}], budget=100 * p, fee_rate_bps=500, fee_exponent=1)
    assert fill["shares_gross"] == pytest.approx(100)
    assert fill["fee_usdc"] == pytest.approx(fee_usd) and round(fill["fee_usdc"], 2) == pytest.approx(round(fee_usd + 1e-9, 2))
    assert fill["fee_shares"] == pytest.approx(fee_sh), "fee_shares = fee_collateral / execution price"
    assert fill["shares"] == pytest.approx(100 - fee_sh)


def test_fee_rounds_to_five_decimals_and_ceiling_formula_is_never_a_decision_basis():
    assert round_fee(0.000004) == 0.0 and round_fee(0.000005) == 0.00001 and round_fee(1.2345649) == 1.23456
    tiny = polymarket_fill(asks=[{"price": "0.99", "size": "10"}], budget=0.001, fee_rate_bps=500)
    assert tiny["fee_usdc"] == 0.0, "anything below 0.00001 rounds to zero"
    book = {"asks": [{"price": "0.5", "size": "1000"}], "fee_rate_bps": 1000, "fee_formula": "v1_signed_ceiling_min", "market_status": "open",
            "settlement_ok": True, "settlement_rule": "fifty_fifty_on_void", "mapping_confidence": "exact"}
    with pytest.raises(OfferRejected, match="sensitivity"):
        polymarket_offer(venue_id=7, fight_id=1, side="a", fighter_id=1, book=book, stake=1.0, retrieved_at=iso(LOCK), provider_ts=None)
    ceil = polymarket_fill(asks=[{"price": "0.5", "size": "1000"}], budget=50, fee_rate_bps=1000, fee_formula="v1_signed_ceiling_min")
    assert ceil["fee_usdc"] == pytest.approx(5.0) and ceil["fee_shares"] == pytest.approx(10.0), "legacy signed ceiling: 0.10 x 0.5 x 100"


# ----------------------------------------------------------------------------- arbitrage arithmetic

def test_sportsbook_pair_split_and_states():
    p = A.sportsbook_pair(2.10, 2.10)                     # +110 / +110
    assert p["margin"] < 1 and p["stake_a"] == 50.0 and p["stake_b"] == 50.0
    assert p["pnl_a_wins"] == pytest.approx(5.0) and p["pnl_b_wins"] == pytest.approx(5.0)
    q = A.sportsbook_pair(1.909, 1.909)                   # -110 / -110: not favourable
    assert q["margin"] > 1 and q["pnl_a_wins"] < 0


def test_scan_finds_a_favourable_pair_only_when_both_quotes_are_fresh():
    f = fight(1, 10, 20)
    cap = LOCK - timedelta(minutes=5)
    rows = pair(1, 10, 20, 1, 115, -140, cap) + pair(1, 10, 20, 3, -140, 115, cap)
    eps = A.scan_sportsbooks(rows, [f], CFG, [LOCK], {1: START})
    assert len(eps) == 1 and eps[0]["class"] == "quoted_pair" and eps[0]["book_a"] == 1 and eps[0]["book_b"] == 3
    stale = pair(1, 10, 20, 1, 115, -140, LOCK - timedelta(minutes=90)) + pair(1, 10, 20, 3, -140, 115, cap)
    assert A.scan_sportsbooks(stale, [f], CFG, [LOCK], {1: START}) == []


def test_scan_ignores_instants_after_the_bout_could_have_started_and_flags_unknown_starts():
    f = fight(1, 10, 20)
    live_t = START + timedelta(minutes=10)
    rows = pair(1, 10, 20, 1, 600, -900, live_t - timedelta(minutes=2)) + pair(1, 10, 20, 3, -900, 600, live_t - timedelta(minutes=2))
    cut = A.bout_cutoffs([start_row(1, START, START - timedelta(days=2)), start_row(1, START + timedelta(hours=2), START - timedelta(days=1))])
    assert cut[1] == START, "earliest start ever recorded"
    assert A.scan_sportsbooks(rows, [f], CFG, [live_t], cut) == [], "in-fight prices are not a pre-fight position"
    eps = A.scan_sportsbooks(rows, [f], CFG, [live_t], {})
    assert eps and all(e["class"] == "start_unknown" for e in eps)


def test_polymarket_plus_sportsbook_states_depth_and_void_payoff():
    # favourite on Polymarket (0.70 ask) against the underdog at a sportsbook (+260): winner states positive,
    # but a void pays 0.50 a share on ~$71 of shares bought at 0.70 while the sportsbook only refunds
    book = {"side": "a", "asks": [{"price": "0.70", "size": "1000"}], "fee_rate_bps": 500, "fee_exponent": 1, "min_order_size": 5}
    sb = {"american_a": -300, "american_b": 260}
    r = A.pm_plus_sportsbook(book, sb, "b")
    assert r["class"] == "quoted_pair" and min(r["pnl_pm_side_wins"], r["pnl_sb_side_wins"]) > 0
    assert r["pnl_void"] == pytest.approx(round(0.5 * r["pm_net_shares"] + r["sb_stake"] - 100, 2))
    assert r["pnl_void"] < 0 and r["all_states_nonnegative"] is False, "50-50 on a void loses money against a refunding sportsbook leg"
    assert "void state loses money" in r["why_not_execution"]
    thin = dict(book, asks=[{"price": "0.40", "size": "2"}])
    assert A.pm_plus_sportsbook(thin, sb, "b")["class"] == "second_leg_unfilled"
