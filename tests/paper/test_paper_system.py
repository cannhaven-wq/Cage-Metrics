"""Paper-trading system: failure cases first, then the whole pipeline on synthetic fixtures.

Run:  python3 -m pytest -q tests/paper
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
PAPER = REPO / "paper"
sys.path.insert(0, str(PAPER))
import data as D  # noqa: E402
import settle as S  # noqa: E402
from ledger import Ledger, DuplicateRun, LedgerCorrupt  # noqa: E402
from pricing import OfferRejected, polymarket_fill, polymarket_offer, sportsbook_offer, american_to_decimal  # noqa: E402
from reference import build_reference, quote_is_fresh  # noqa: E402
from strategy import evaluate_card  # noqa: E402

CFG = json.loads((PAPER / "config" / "strategy_draft.json").read_text())
T0 = datetime(2026, 10, 24, 16, 0, tzinfo=timezone.utc)      # the lock instant used throughout
iso = lambda t: t.isoformat()  # noqa: E731


# ----------------------------------------------------------------------------- fixtures

def quote(book_id, a, b, age_min=5, prov_age_min=None):
    return {"fight_id": 1, "book_id": book_id, "american_a": a, "american_b": b,
            "captured_at": iso(T0 - timedelta(minutes=age_min)),
            "provider_last_update": iso(T0 - timedelta(minutes=prov_age_min if prov_age_min is not None else age_min))}


def quotes_for(fight_id, prices, **kw):
    out = []
    for book_id, (a, b) in prices.items():
        q = quote(book_id, a, b, **kw); q["fight_id"] = fight_id; out.append(q)
    return out


def fight(fid, a=100 + 0, b=200):
    return {"id": fid, "fighter_a_id": a, "fighter_b_id": b, "is_active": True, "winner_id": None, "method": None}


def pm_book(fight_id, side, fighter_id, asks, fee_bps=300, **over):
    b = {"fight_id": fight_id, "side": side, "fighter_id": fighter_id, "token_id": "t1", "condition_id": "c1",
         "asks": asks, "bids": [], "fee_rate_bps": fee_bps, "fee_rule_verified": True, "market_status": "open",
         "settlement_ok": True, "mapping_confidence": "exact", "retrieved_at": iso(T0 - timedelta(minutes=3)),
         "book_timestamp": iso(T0 - timedelta(minutes=3)), "tick_size": 0.01, "min_order_size": 5}
    b.update(over); return b


EVEN = {1: (-110, -110), 3: (-108, -112), 9: (-110, -110), 11: (-105, -115)}     # four books, near-even


# ----------------------------------------------------------------------------- pricing

def test_sportsbook_offer_is_plain_payout():
    o = sportsbook_offer(venue_id=1, fight_id=1, side="a", fighter_id=100, american=150, stake=1.0, retrieved_at=iso(T0), provider_ts=None, quote={})
    assert o.net_if_win == pytest.approx(1.5) and o.stake_cost == 1.0
    assert o.expected_return(0.5) == pytest.approx(0.5 * 1.5 - 0.5)
    assert o.equivalent_american == pytest.approx(150)


def test_polymarket_fill_walks_depth_and_charges_fee():
    fill = polymarket_fill(asks=[{"price": "0.60", "size": "1.0"}, {"price": "0.55", "size": "1.0"}, {"price": "0.70", "size": "100"}], budget=2.0, fee_rate_bps=1000)
    # cheapest first: 0.55 then 0.60 then 0.70; fee = rate * p * (1-p) per share
    assert [round(l["price"], 2) for l in fill["levels_used"]] == [0.55, 0.60, 0.70]
    assert fill["spent"] == pytest.approx(2.0)
    assert fill["fee"] == pytest.approx(0.1 * (0.55 * 0.45 + 0.60 * 0.40) + 0.1 * 0.70 * 0.30 * fill["levels_used"][2]["taken"])
    assert fill["fee"] > 0 and fill["fill_fraction"] == pytest.approx(1.0)


def test_polymarket_rejects_missing_fee_insufficient_depth_and_bad_status():
    with pytest.raises(OfferRejected, match="fee rate missing"):
        polymarket_fill(asks=[{"price": "0.5", "size": "100"}], budget=1.0, fee_rate_bps=None)
    with pytest.raises(OfferRejected, match="insufficient depth"):
        polymarket_fill(asks=[{"price": "0.5", "size": "0.5"}], budget=1.0, fee_rate_bps=0)
    with pytest.raises(OfferRejected, match="no executable asks"):
        polymarket_fill(asks=[], budget=1.0, fee_rate_bps=0)
    good = pm_book(1, "a", 100, [{"price": "0.50", "size": "1000"}])
    for bad, msg in (({"market_status": "closed"}, "not open"), ({"settlement_ok": False}, "settlement rules"), ({"mapping_confidence": "fuzzy(90)"}, "mapping")):
        with pytest.raises(OfferRejected, match=msg):
            polymarket_offer(venue_id=7, fight_id=1, side="a", fighter_id=100, book={**good, **bad}, stake=1.0, retrieved_at=iso(T0), provider_ts=None)


def test_polymarket_offer_payout_uses_shares_not_displayed_price():
    book = pm_book(1, "a", 100, [{"price": "0.40", "size": "1000"}], fee_bps=0)
    o = polymarket_offer(venue_id=7, fight_id=1, side="a", fighter_id=100, book=book, stake=1.0, retrieved_at=iso(T0), provider_ts=None, unit_notional=100.0)
    assert o.source["fill"]["shares"] == pytest.approx(250) and o.net_if_win == pytest.approx(1.5) and o.stake_cost == pytest.approx(1.0)
    assert o.equivalent_american == pytest.approx(150)
    thin = pm_book(1, "a", 100, [{"price": "0.40", "size": "100"}], fee_bps=0)      # only 40 collateral of depth for a 100 fill
    with pytest.raises(OfferRejected, match="insufficient depth"):
        polymarket_offer(venue_id=7, fight_id=1, side="a", fighter_id=100, book=thin, stake=1.0, retrieved_at=iso(T0), provider_ts=None, unit_notional=100.0)


# ----------------------------------------------------------------------------- freshness and reference

def test_stale_quotes_are_refused_on_either_timestamp():
    assert quote_is_fresh(quote(1, -110, -110, age_min=59), T0, 60)[0]
    assert not quote_is_fresh(quote(1, -110, -110, age_min=61), T0, 60)[0]
    fresh, why = quote_is_fresh(quote(1, -110, -110, age_min=5, prov_age_min=90), T0, 60)
    assert not fresh and "provider" in why
    assert not quote_is_fresh(quote(1, -110, -110, age_min=-5), T0, 60)[0], "a quote captured after the lock is not usable"
    assert not quote_is_fresh({"fight_id": 1, "captured_at": "2026-10-24 15:00:00"}, T0, 60)[0], "naive timestamps are refused"


def test_reference_needs_three_other_books_and_excludes_the_quoting_book():
    qs = quotes_for(1, EVEN)
    ref, why = build_reference(1, qs, now=T0, cfg=CFG, exclude_book_id=1)
    assert ref and ref.book_ids == [3, 9, 11] and 0.49 < ref.p_a < 0.51
    ref, why = build_reference(1, quotes_for(1, {1: (-110, -110), 3: (-110, -110), 9: (-110, -110)}), now=T0, cfg=CFG, exclude_book_id=1)
    assert ref is None and "found 2" in why
    # synthetic consensus, BFO placeholder and prediction markets never count
    extra = quotes_for(1, {14: (-110, -110), 6: (-110, -110), 7: (-110, -110), 8: (-110, -110)})
    ref, why = build_reference(1, extra + quotes_for(1, {1: (-110, -110), 3: (-110, -110)}), now=T0, cfg=CFG)
    assert ref is None


# ----------------------------------------------------------------------------- strategy

def run_eval(fights, quotes, pm=None, p_model=None, bankroll=None, cfg=CFG):
    qbf = {}
    for q in quotes:
        qbf.setdefault(q["fight_id"], []).append(q)
    pbf = {}
    for b in pm or []:
        pbf.setdefault(b["fight_id"], []).append(b)
    return evaluate_card(card={"event_id": 9, "fights": fights}, quotes_by_fight=qbf, pm_books_by_fight=pbf,
                         p_model_by_fight=p_model or {}, cfg=cfg, now=T0, bankroll=bankroll or {})


def by(decisions, strat, fid):
    return next(d for d in decisions if d.strategy == strat and d.fight_id == fid)


def test_m1_bets_the_dispersed_price_and_s1_needs_the_model():
    # book 9 offers +125 on A while the other three sit at -110/-110 -> p_ref(A)=0.5, EV at +125 = 0.5*2.25-1 = +12.5%
    qs = quotes_for(1, {1: (-110, -110), 3: (-110, -110), 11: (-110, -110), 9: (125, -150)})
    d = run_eval([fight(1)], qs, p_model={1: 0.50})
    m1 = by(d, "M1", 1); s1 = by(d, "S1", 1)
    assert m1.decision == "bet" and m1.side == "a" and m1.offer["venue_id"] == 9 and m1.ev_reference == pytest.approx(0.125)
    assert s1.decision == "bet" and s1.ev_model == pytest.approx(0.125)
    # model disagrees enough -> S1 passes, M1 unchanged
    d = run_eval([fight(1)], qs, p_model={1: 0.40})
    assert by(d, "M1", 1).decision == "bet" and by(d, "S1", 1).decision == "pass"
    # model abstained -> S1 abstains while M1 still bets
    d = run_eval([fight(1)], qs, p_model={1: None})
    assert by(d, "S1", 1).decision == "abstain" and by(d, "M1", 1).decision == "bet"


def test_underdog_side_is_considered_and_band_is_enforced():
    # A heavy favourite: three books at -450/+350; book 9 offers +420 on B (outside +400) and -380 on A
    qs = quotes_for(1, {1: (-450, 350), 3: (-450, 350), 11: (-450, 350), 9: (-380, 420)})
    d = run_eval([fight(1)], qs)
    m1 = by(d, "M1", 1)
    assert all(r["reason"].startswith("equivalent price") for r in m1.rejected_offers if r["venue_id"] in (1, 3, 11) and r["side"] == "a")
    assert any(r["venue_id"] == 9 and r["side"] == "b" for r in m1.rejected_offers), "+420 is outside the band"
    assert m1.decision in ("bet", "pass") and (m1.side == "a" if m1.decision == "bet" else True)


def test_card_cap_and_ranking():
    fights = [fight(i, a=100 + i, b=200 + i) for i in range(1, 7)]
    qs = []
    for i in range(1, 7):
        edge = 100 + 5 * i          # bigger dispersed price on later fights
        qs += quotes_for(i, {1: (-110, -110), 3: (-110, -110), 11: (-110, -110), 9: (edge, -150)})
    d = run_eval(fights, qs)
    bets = [x for x in d if x.strategy == "M1" and x.decision == "bet"]
    assert len(bets) == 4 and [b.fight_id for b in sorted(bets, key=lambda b: b.rank)] == [6, 5, 4, 3]
    capped = [x for x in d if x.strategy == "M1" and x.decision == "pass" and "card cap" in x.reason]
    assert {x.fight_id for x in capped} == {1, 2}


def test_bankroll_stop_blocks_new_selections():
    qs = quotes_for(1, {1: (-110, -110), 3: (-110, -110), 11: (-110, -110), 9: (125, -150)})
    d = run_eval([fight(1)], qs, bankroll={"M1": 70.0, "S1": 100.0}, p_model={1: 0.5})
    assert by(d, "M1", 1).decision == "pass" and "stop" in by(d, "M1", 1).reason
    assert by(d, "S1", 1).decision == "bet"


def test_stale_offers_and_missing_reference_abstain():
    qs = quotes_for(1, {1: (-110, -110), 3: (-110, -110), 11: (-110, -110), 9: (125, -150)}, age_min=90)
    d = run_eval([fight(1)], qs)
    assert by(d, "M1", 1).decision == "abstain"
    qs = quotes_for(1, {9: (125, -150), 1: (-110, -110)})
    d = run_eval([fight(1)], qs)
    assert by(d, "M1", 1).decision == "abstain" and "reference needs 3" in by(d, "M1", 1).reason


def test_polymarket_offer_competes_and_swapped_corner_is_rejected():
    qs = quotes_for(1, EVEN)
    good = pm_book(1, "a", 100, [{"price": "0.44", "size": "5000"}], fee_bps=0)    # 227 shares for 100 -> +127% net, EV +13.6%
    d = run_eval([fight(1)], qs, pm=[good])
    assert by(d, "M1", 1).decision == "bet" and by(d, "M1", 1).offer["venue_kind"] == "polymarket"
    swapped = pm_book(1, "a", 200, [{"price": "0.44", "size": "5000"}], fee_bps=0)  # says side a but names fighter 200 (corner B)
    d = run_eval([fight(1)], qs, pm=[swapped])
    m1 = by(d, "M1", 1)
    assert m1.decision == "pass" and any("does not match the corner" in r["reason"] for r in m1.rejected_offers)
    unverified = pm_book(1, "a", 100, [{"price": "0.44", "size": "5000"}], fee_bps=0, fee_rule_verified=False)
    d = run_eval([fight(1)], qs, pm=[unverified])
    assert any("fee rule not verified" in r["reason"] for r in by(d, "M1", 1).rejected_offers)


# ----------------------------------------------------------------------------- lock timing

def snapshot(fights, starts, quotes, now_capture=T0):
    return {"captured_at": iso(now_capture), "card": {"event_id": 9, "name": "Test card", "event_date": "2026-10-24", "fights": fights},
            "starts": starts, "quotes": quotes, "polymarket_books": []}


def test_lock_instant_is_earliest_verified_start_minus_lead_and_honours_the_date_fallback():
    starts = [{"fight_id": 1, "start_at": "2026-10-25T02:00:00+00:00", "start_basis": "provider_commence"},
              {"fight_id": 2, "start_at": "2026-10-24T22:00:00+00:00", "start_basis": "bell_at"}]
    t, why = D.lock_instant(snapshot([fight(1), fight(2)], starts, []), CFG)
    assert t == datetime(2026, 10, 24, 16, 0, tzinfo=timezone.utc)
    starts.append({"fight_id": 3, "start_at": "2026-10-24T18:00:00+00:00", "start_basis": "event_date_fallback"})
    t, why = D.lock_instant(snapshot([fight(1), fight(2), fight(3)], starts, []), CFG)
    assert t == datetime(2026, 10, 23, 18, 0, tzinfo=timezone.utc), "a date-only start counts from 00:00 UTC in win_model_locks; that bound wins"
    t, why = D.lock_instant(snapshot([fight(3)], starts[2:], []), CFG)
    assert t is None and "verified" in why


# ----------------------------------------------------------------------------- ledger, duplicates, settlement

def test_ledger_refuses_duplicate_run_and_detects_tampering(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    led.record_lock(card_id=9, strategy_version="v", lock_at=iso(T0))
    with pytest.raises(DuplicateRun):
        led.record_lock(card_id=9, strategy_version="v", lock_at=iso(T0))
    led.append("selection", card_id=9, strategy_version="v", strategy="M1", fight_id=1, stake=1.0)
    lines = (tmp_path / "l.jsonl").read_text().splitlines()
    lines[1] = lines[1].replace('"stake":1.0', '"stake":2.0')
    (tmp_path / "l.jsonl").write_text("\n".join(lines) + "\n")
    with pytest.raises(LedgerCorrupt):
        Ledger(tmp_path / "l.jsonl")


def test_settlement_outcomes_including_corner_change_and_push():
    sel = {"fighter_a_id": 100, "fighter_b_id": 200, "fighter_id": 100, "offer": {"venue_kind": "sportsbook", "net_if_win": 1.5, "stake_cost": 1.0}}
    f = {"fighter_a_id": 100, "fighter_b_id": 200, "winner_id": 100, "method": "KO/TKO", "is_active": True}
    assert S.settle_one(sel, f)["pnl"] == 1.5
    assert S.settle_one(sel, {**f, "winner_id": 200})["pnl"] == -1.0
    assert S.settle_one(sel, {**f, "winner_id": None, "method": None}) is None, "unsettled stays open"
    assert S.settle_one(sel, {**f, "winner_id": None, "method": "No Contest"})["result"] == "push"
    assert S.settle_one(sel, {**f, "fighter_b_id": 300})["type"] == "cancel", "opponent changed after the lock"
    pm_sel = {**sel, "offer": {**sel["offer"], "venue_kind": "polymarket"}}
    assert S.settle_one(pm_sel, {**f, "winner_id": None, "method": "No Contest"}) is None, "polymarket NC resolution is not assumed"


def test_metrics_compare_strategies_over_the_same_cards_and_clv_unavailable(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    led.record_lock(card_id=1, strategy_version="v", fight_ids=[1, 2]); led.record_lock(card_id=2, strategy_version="v", fight_ids=[3])
    s = led.append("selection", card_id=1, strategy_version="v", strategy="M1", fight_id=1, stake=1.0)
    led.append("pass", card_id=1, strategy_version="v", strategy="M1", fight_id=2)
    led.append("pass", card_id=1, strategy_version="v", strategy="S1", fight_id=1); led.append("pass", card_id=1, strategy_version="v", strategy="S1", fight_id=2)
    led.append("abstain", card_id=2, strategy_version="v", strategy="M1", fight_id=3); led.append("abstain", card_id=2, strategy_version="v", strategy="S1", fight_id=3)
    led.append("settlement", card_id=1, strategy_version="v", selection_id=s["event_id"], strategy="M1", result="win", pnl=1.5)
    m = S.metrics(led, CFG)
    assert m["n_cards"] == 2 and m["strategies"]["M1"]["bets"] == 1 and m["strategies"]["M1"]["roi"] == pytest.approx(1.5)
    assert m["strategies"]["S1"]["bets"] == 0 and m["strategies"]["S1"]["cards_with_no_bets"] == 2 and m["strategies"]["S1"]["coverage"] == 1.0
    assert m["strategies"]["M1"]["bankroll_settled"] == pytest.approx(101.5)
    assert m["clv"]["status"] == "unavailable"
    assert S.metrics(led, CFG, clv_reference={"protocol": "other"})["clv"]["status"] == "unavailable"


# ----------------------------------------------------------------------------- the model bridge

def test_forecast_js_abstains_without_market_and_is_symmetric(tmp_path):
    artifact = PAPER / "private" / "mma001_artifact.json"
    if not artifact.exists():
        pytest.skip("private MMA-001 artifact not present")
    row = lambda i, d, a, b, y: [i, i, d, a, b, y, 900, 45, 30, 2, 1, 4, 3, 180, 60, 1, 0, 1, 0, "1990-01-01", "1991-01-01", 72, 70, "LW", "Decision - Unanimous"]  # noqa: E731
    hist = {"fights": [row(1, "2025-03-01", 1, 2, 1), row(2, "2025-06-01", 1, 3, 1), row(3, "2026-01-10", 2, 4, 0)]}
    targets = {"targets": [{"fight_id": 10, "event_id": 5, "event_date": "2026-10-24", "a_id": 1, "b_id": 2, "a_dob": "1990-01-01", "b_dob": "1991-01-01", "a_reach": 72, "b_reach": 70, "q": 0.55},
                           {"fight_id": 11, "event_id": 5, "event_date": "2026-10-24", "a_id": 2, "b_id": 1, "a_dob": "1991-01-01", "b_dob": "1990-01-01", "a_reach": 70, "b_reach": 72, "q": 0.45},
                           {"fight_id": 12, "event_id": 5, "event_date": "2026-10-24", "a_id": 3, "b_id": 4, "a_dob": None, "b_dob": None, "a_reach": None, "b_reach": None, "q": None}]}
    (tmp_path / "h.json").write_text(json.dumps(hist)); (tmp_path / "t.json").write_text(json.dumps(targets))
    out = subprocess.run(["node", str(PAPER / "mma001" / "forecast.js"), str(artifact), str(tmp_path / "h.json"), str(tmp_path / "t.json")], capture_output=True, text=True, check=True)
    fc = {f["fight_id"]: f for f in json.loads(out.stdout)["forecasts"]}
    assert fc[10]["p_a"] + fc[11]["p_a"] == pytest.approx(1.0, abs=1e-9), "swapping corners gives the complement"
    assert fc[10]["p_a"] != pytest.approx(0.55) and 0 < fc[10]["p_a"] < 1, "history moved the number off the market"
    assert fc[10]["history_fights_a"] == 2 and fc[10]["history_fights_b"] == 2, "post-2024 history was replayed"
    assert fc[12]["p_a"] is None and "no market" in fc[12]["abstain_reason"]


def test_history_rows_follow_the_doc_recipe():
    events = {1: {"event_date": "2026-01-10", "is_upcoming": False}, 2: {"event_date": "2026-12-01", "is_upcoming": True}}
    fighters = {1: {"dob": "1990-01-01", "reach_in": 72}, 2: {"dob": None, "reach_in": None}}
    fights = [{"id": 1, "event_id": 1, "fighter_a_id": 1, "fighter_b_id": 2, "winner_id": 1, "method": "KO/TKO", "end_round": 2, "end_time": "1:30", "scheduled_rounds": 3, "is_active": True},
              {"id": 2, "event_id": 1, "fighter_a_id": 1, "fighter_b_id": 2, "winner_id": 1, "method": "Overturned", "end_round": 2, "end_time": "1:30", "scheduled_rounds": 3},
              {"id": 3, "event_id": 2, "fighter_a_id": 1, "fighter_b_id": 2, "winner_id": None, "method": None},
              {"id": 4, "event_id": 1, "fighter_a_id": 1, "fighter_b_id": 2, "winner_id": None, "method": "Decision - Majority", "scheduled_rounds": 3, "end_round": None, "end_time": None}]
    rows = D.history_rows_from_tables(fights, events, fighters)
    assert [r[0] for r in rows] == [1, 4] and rows[0][5] == 1 and rows[0][6] == 390 and rows[1][5] == 0.5 and rows[1][6] == 900


# ----------------------------------------------------------------------------- end to end, dry run then write, rerun refused, late lock refused

def full_snapshot():
    fights = [fight(1, 101, 201), fight(2, 102, 202), fight(3, 103, 203)]
    starts = [{"fight_id": i, "start_at": "2026-10-24T22:00:00+00:00", "start_basis": "provider_commence"} for i in (1, 2, 3)]
    qs = quotes_for(1, {1: (-110, -110), 3: (-110, -110), 11: (-110, -110), 9: (125, -150)})
    qs += quotes_for(2, {1: (-200, 170), 3: (-200, 170), 11: (-200, 170), 9: (-200, 170)})
    qs += quotes_for(3, {1: (-110, -110)})
    return snapshot(fights, starts, qs)


def test_pipeline_dry_run_write_rerun_and_late_lock(tmp_path):
    import run_card as R
    snap = full_snapshot(); p = tmp_path / "snap.json"; p.write_text(json.dumps(snap)); led = tmp_path / "ledger.jsonl"
    dry = R.main(["--snapshot", str(p), "--now", iso(T0 + timedelta(minutes=5)), "--ledger", str(led)])
    assert dry["status"] == "evaluated" and not led.exists(), "a dry run writes nothing"
    assert dry["lock_at"] == iso(T0) and len(dry["win_model_locks_rows"]) == 3 and dry["forecasts_abstained"] == 3
    m1 = {d["fight_id"]: d for d in dry["decisions"] if d["strategy"] == "M1"}
    assert m1[1]["decision"] == "bet" and m1[2]["decision"] == "pass" and m1[3]["decision"] == "abstain"
    wet = R.main(["--snapshot", str(p), "--now", iso(T0 + timedelta(minutes=5)), "--ledger", str(led), "--write"])
    assert wet["ledger_appended"] and Ledger(led).events("selection")
    again = R.main(["--snapshot", str(p), "--now", iso(T0 + timedelta(minutes=10)), "--ledger", str(led), "--write"])
    assert again["status"] == "duplicate_run" and len(Ledger(led).events("selection")) == 1, "a rerun never adds exposure"
    late = R.main(["--snapshot", str(p), "--now", iso(T0 + timedelta(hours=3)), "--ledger", str(tmp_path / "x.jsonl")])
    assert late["status"] == "late"
    early = R.main(["--snapshot", str(p), "--now", iso(T0 - timedelta(hours=1)), "--ledger", str(tmp_path / "x.jsonl")])
    assert early["status"] == "before_lock"
    # settle: fight 1 won by corner A (fighter 101); fight 2 corners changed
    res = snapshot([{**fight(1, 101, 201), "winner_id": 101, "method": "KO/TKO"}, fight(2, 102, 999), fight(3, 103, 203)], [], [])
    rp = tmp_path / "res.json"; rp.write_text(json.dumps(res))
    out = R.main(["--settle", "--snapshot", str(rp), "--ledger", str(led), "--write", "--now", iso(T0 + timedelta(days=1))])
    assert out["metrics"]["strategies"]["M1"]["bets"] == 1 and out["metrics"]["strategies"]["M1"]["profit"] == pytest.approx(1.25)
    assert out["metrics"]["clv"]["status"] == "unavailable"
    assert not Ledger(led).open_selections()
