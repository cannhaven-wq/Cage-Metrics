"""DUR-001 tests. Two layers:

  * pure-Python (no network): market maths, settlement rules, the PROP-0001
    threshold mapping, the walk-forward residual test, and — the important one —
    that the point-in-time world used for a lock cannot see anything dated on or
    after the training cutoff.
  * database (needs SUPABASE_ACCESS_TOKEN; skipped otherwise): every ledger
    rejects UPDATE / DELETE, the lock guard rejects post-hoc locks, and the whole
    probe is rolled back so nothing is ever stored.

Run:  python -m pytest cfl_engine/dur001/test_dur001.py -q
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.request

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "features"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "models"))

import dur001_analysis as an          # noqa: E402
import lock_prop0001 as lk            # noqa: E402
import build_features as bf           # noqa: E402


# ------------------------------------------------------------ market maths
def test_american_to_probability_both_signs():
    assert abs(an.american_to_q(-150) - 0.6) < 1e-9
    assert abs(an.american_to_q(+150) - 0.4) < 1e-9
    assert abs(an.american_to_q(-100) - 0.5) < 1e-9


def test_two_way_devig_sums_to_one_and_matches_view_formula():
    po, pu = an.devig_two_way(-135, 105)
    assert abs(po + pu - 1) < 1e-12
    qo, qu = an.american_to_q(-135), an.american_to_q(105)
    assert abs(po - qo / (qo + qu)) < 1e-12


# ------------------------------------------------------------- settlement
@pytest.mark.parametrize("secs,line,expect", [
    (751, 2.5, 1),      # past 2:30 of R3 -> over
    (750, 2.5, 0),      # exactly 2:30 of R3 -> under (must go PAST)
    (749, 2.5, 0),
    (900, 2.5, 1),      # decision
    (451, 1.5, 1), (450, 1.5, 0),
    (151, 0.5, 1), (150, 0.5, 0),
    (600, 2.0, None),   # whole-number line ends on the bell -> push
    (601, 2.0, 1), (599, 2.0, 0),
    (None, 2.5, None),  # ungraded / void
])
def test_settle_over(secs, line, expect):
    assert an.settle_over(secs, line) == expect


# --------------------------------------------------- PROP-0001 threshold map
def test_threshold_probabilities_follow_survival_identity():
    h1, h2, h3 = 0.22, 0.20, 0.16
    phi = {1: 0.47, 2: 0.43, 3: 0.46}
    tp = lk.threshold_probs(h1, h2, h3, phi)
    assert abs(tp[0.5] - (1 - phi[1] * h1)) < 1e-12
    assert abs(tp[1.5] - (1 - h1) * (1 - phi[2] * h2)) < 1e-12
    assert abs(tp[2.5] - (1 - h1) * (1 - h2) * (1 - phi[3] * h3)) < 1e-12
    assert abs(tp["distance"] - (1 - h1) * (1 - h2) * (1 - h3)) < 1e-12
    # monotone in the threshold, and distance <= over 2.5
    assert tp[0.5] > tp[1.5] > tp[2.5] >= tp["distance"]
    assert abs(sum(tp["p_ends"].values()) + tp["distance"] - 1) < 1e-12


def test_lock_row_reproduces_probability_from_stored_hazards():
    """A stored lock carries haz_r*, phi_r*: recompute P(over 2.5) from them."""
    row = {"haz_r1": 0.217822, "haz_r2": 0.198911, "haz_r3": 0.158263,
           "phi_r1": 0.467232, "phi_r2": 0.432532, "phi_r3": 0.462963,
           "predicted_probability": 0.580684}          # real lock id 27, fight 47331
    tp = lk.threshold_probs(row["haz_r1"], row["haz_r2"], row["haz_r3"],
                            {1: row["phi_r1"], 2: row["phi_r2"], 3: row["phi_r3"]})
    assert abs(tp[2.5] - row["predicted_probability"]) < 1e-5


# ------------------------------------------------ point-in-time guarantee
def _mini_world(cutoff: dt.date, extra_future=False):
    """Two fighters with history; optionally a FUTURE fight (on/after cutoff)
    between them that a leaky implementation would fold into the features."""
    events = [{"id": 1, "event_date": "2025-01-01", "is_upcoming": False},
              {"id": 2, "event_date": "2025-06-01", "is_upcoming": False},
              {"id": 3, "event_date": cutoff.isoformat(), "is_upcoming": False},
              {"id": 9, "event_date": (cutoff + dt.timedelta(days=5)).isoformat(), "is_upcoming": True}]
    fighters = [{"id": 10, "name": "A", "dob": "1995-01-01", "height_in": 70, "reach_in": 72, "stance": "Orthodox"},
                {"id": 20, "name": "B", "dob": "1994-01-01", "height_in": 71, "reach_in": 74, "stance": "Southpaw"},
                {"id": 30, "name": "C", "dob": "1996-01-01", "height_in": 69, "reach_in": 70, "stance": "Orthodox"}]
    fights = [
        {"id": 100, "event_id": 1, "fighter_a_id": 10, "fighter_b_id": 30, "winner_id": 10,
         "method": "KO/TKO", "scheduled_rounds": 3, "end_round": 1, "end_time": "1:10"},
        {"id": 101, "event_id": 2, "fighter_a_id": 20, "fighter_b_id": 30, "winner_id": 20,
         "method": "Decision - Unanimous", "scheduled_rounds": 3, "end_round": 3, "end_time": "5:00"},
        {"id": 999, "event_id": 9, "fighter_a_id": 10, "fighter_b_id": 20, "winner_id": None,
         "method": None, "scheduled_rounds": 3, "end_round": None, "end_time": None},
    ]
    if extra_future:   # a result dated ON the cutoff day (a leak if it counted)
        fights.append({"id": 102, "event_id": 3, "fighter_a_id": 10, "fighter_b_id": 20, "winner_id": 20,
                       "method": "Submission", "scheduled_rounds": 3, "end_round": 2, "end_time": "3:00"})
    def rr(fid, a, b, n):
        return [{"fight_id": fid, "fighter_a_id": a, "fighter_b_id": b, "round_number": r,
                 "a_sig_str_landed": 20, "b_sig_str_landed": 10, "a_sig_str_attempted": 40,
                 "b_sig_str_attempted": 30, "a_td_landed": 1, "b_td_landed": 0, "a_ctrl_seconds": 60,
                 "b_ctrl_seconds": 0, "a_kd": 0, "b_kd": 0, "a_sub_attempts": 0, "b_sub_attempts": 1}
                for r in range(1, n + 1)]
    rounds = rr(100, 10, 30, 1) + rr(101, 20, 30, 3)
    if extra_future:
        rounds += rr(102, 10, 20, 2)
    return events, fighters, fights, rounds


def test_pit_world_ignores_fights_on_or_after_cutoff():
    cutoff = dt.date(2026, 9, 15)
    w0 = lk.PITWorld(*_mini_world(cutoff), cutoff=cutoff, log=lambda *_: None)
    w1 = lk.PITWorld(*_mini_world(cutoff, extra_future=True), cutoff=cutoff, log=lambda *_: None)
    assert 102 not in w0.fight_date and 102 not in w1.fight_date       # cutoff-day fight excluded
    assert 999 not in w1.fight_date                                    # upcoming fight excluded
    when = pd.Timestamp(cutoff + dt.timedelta(days=5))
    for fid in (10, 20):
        f0 = w0.feats_asof(fid, 999, when); f1 = w1.feats_asof(fid, 999, when)
        for k, v in f0.items():
            if isinstance(v, float) and np.isnan(v):
                assert np.isnan(f1[k])
            else:
                assert f1[k] == v, f"feature {k} leaked post-cutoff data"
    # and the matchup row the model sees is identical
    a0, b0 = w0.feats_asof(10, 999, when), w0.feats_asof(20, 999, when)
    a1, b1 = w1.feats_asof(10, 999, when), w1.feats_asof(20, 999, when)
    assert bf.matchup_features(a0, b0) == bf.matchup_features(a1, b1)


def test_training_panel_is_strictly_before_cutoff_and_covariates_frozen():
    cutoff = dt.date(2026, 9, 15)
    w = lk.PITWorld(*_mini_world(cutoff, extra_future=True), cutoff=cutoff, log=lambda *_: None)
    pp, fdf, cov, med, phi = w.training_panel()
    assert (pd.to_datetime(fdf.event_date) < pd.Timestamp(cutoff)).all()
    assert cov == bf.covariate_columns() and len(cov) == 49
    assert set(phi) == {1, 2, 3}


def test_upcoming_card_excludes_five_round_and_settled_fights():
    today = dt.date(2026, 9, 15)
    events = [{"id": 5, "name": "UFC X", "event_date": "2026-09-19", "is_upcoming": True}]
    fights = [
        {"id": 1, "event_id": 5, "fighter_a_id": 1, "fighter_b_id": 2, "winner_id": None, "method": None,
         "scheduled_rounds": 3, "is_main_event": True, "is_title_fight": True},       # 5-rounder in disguise
        {"id": 2, "event_id": 5, "fighter_a_id": 3, "fighter_b_id": 4, "winner_id": 3, "method": "KO/TKO",
         "scheduled_rounds": 3, "is_main_event": False, "is_title_fight": False},     # settled
        {"id": 3, "event_id": 5, "fighter_a_id": 5, "fighter_b_id": 6, "winner_id": None, "method": None,
         "scheduled_rounds": 3, "is_main_event": False, "is_title_fight": False},     # eligible
        {"id": 4, "event_id": 5, "fighter_a_id": 5, "fighter_b_id": 7, "winner_id": None, "method": None,
         "scheduled_rounds": 3, "is_main_event": False, "is_title_fight": False},     # dup booking of 5 -> keep newest (4)
    ]
    card = lk.upcoming_card(events, fights, today, 8, log=lambda *_: None)
    assert [f["id"] for f in card] == [4]


# ------------------------------------------------ walk-forward residual test
def test_walk_forward_only_uses_prior_events_and_detects_planted_signal():
    df = an.prepare(an.make_synthetic(30, seed=3, cfl_signal=1.0, cfl_noise=0.1))
    p_base, p_chal, coefs = an.walk_forward(df)
    scored = ~np.isnan(p_base)
    first = df[scored].event_date.min()
    # nothing before the first scored event is scored; every fit used only prior rows
    assert (df[~scored].event_date <= first).all()
    dates = sorted(set(df.event_date))
    for c in coefs:
        d = dt.date.fromisoformat(c["event_date"])
        assert c["n_prior"] == int((df.event_date < d).sum())
        assert dates.index(d) >= an.MIN_PRIOR_EVENTS
    p6, sc = an.phase6_residual(df)
    assert p6["G_LL"] > 0.01                     # planted signal found
    # true null (CFL = market + noise): no gain, and clearly below the planted case
    p6n, _ = an.phase6_residual(an.prepare(an.make_synthetic(30, seed=3, cfl_signal=0.0, cfl_noise=0.1)))
    assert p6n["G_LL"] < 0.005 and p6n["G_LL"] < p6["G_LL"]


def test_bootstrap_resamples_events_not_fights():
    df = an.prepare(an.make_synthetic(12, seed=1))
    _, sc = an.phase6_residual(df)
    p7 = an.phase7_bootstrap(sc, draws=200)
    assert p7["n_events"] == sc.event_id.nunique()
    assert p7["G_LL"]["lo95"] <= p7["G_LL"]["mean"] <= p7["G_LL"]["hi95"]
    assert p7["mean_CLV"] is None and p7["ROI"] is None


def test_decision_rules_are_frozen_and_reject_when_ceiling_is_low():
    p6 = {"G_LL": -0.001, "delta_Brier": 0.0, "cal_challenger": {"slope": 1.0, "intercept": 0.0}}
    p7 = {"G_LL": {"mean": -0.001, "lo95": -0.004, "hi95": 0.002}}
    d = an.phase9_decision(p6, p7)
    assert d["verdict"] == "REJECT" and d["ceiling_below_practical_gain"]
    p6 = {"G_LL": 0.006, "delta_Brier": -0.001, "cal_challenger": {"slope": 1.05, "intercept": 0.02}}
    p7 = {"G_LL": {"mean": 0.006, "lo95": 0.001, "hi95": 0.011}}
    assert an.phase9_decision(p6, p7)["verdict"] == "PROMOTE"
    assert an.PRACTICAL_GAIN == 0.003 and an.SLOPE_BAND == (0.8, 1.2)


# ----------------------------------------------------------- database layer
PROJECT_REF = "uftancejftcryfvbggll"
ROLLBACK_PROBE = r"""
do $$
declare r text := ''; qid bigint; lid bigint; sid bigint; fid bigint; eid bigint; bid bigint;
begin
  select f.id, f.event_id into fid, eid from fights f join events e on e.id=f.event_id
   where e.event_date > current_date + 3 and f.winner_id is null and f.method is null order by e.event_date, f.id limit 1;
  select id into bid from odds_books order by id limit 1;
  insert into prop_odds (fight_id, event_id, market_type, line, over_odds, under_odds, book_id, source, captured_at, source_commence_at, is_live)
  values (fid, eid, 'total_rounds', 2.5, -120, 100, bid, 'odds_api', now(), now()+interval '5 days', false) returning id into qid;
  begin update prop_odds set over_odds=-130 where id=qid; r := r||'quote_update_ALLOWED;';
  exception when others then r := r||'quote_update_blocked;'; end;
  begin delete from prop_odds where id=qid; r := r||'quote_delete_ALLOWED;';
  exception when others then r := r||'quote_delete_blocked;'; end;
  insert into fight_start_estimates (fight_id, source, start_at) values (fid,'odds_api_commence', now()+interval '5 days') returning id into sid;
  begin update fight_start_estimates set start_at=now() where id=sid; r := r||'start_update_ALLOWED;';
  exception when others then r := r||'start_update_blocked;'; end;
  insert into prop_model_locks (fight_id, event_id, market_type, threshold, side, model_name, model_version, generated_at, training_cutoff, predicted_probability)
  values (fid, eid, 'total_rounds', 2.5, 'over', 'PROP-0001', 'TEST-ONLY', now(), now()-interval '1 hour', 0.55) returning id into lid;
  begin update prop_model_locks set predicted_probability=0.6 where id=lid; r := r||'lock_update_ALLOWED;';
  exception when others then r := r||'lock_update_blocked;'; end;
  begin delete from prop_model_locks where id=lid; r := r||'lock_delete_ALLOWED;';
  exception when others then r := r||'lock_delete_blocked;'; end;
  begin
    insert into prop_model_locks (fight_id, event_id, market_type, threshold, side, model_name, model_version, generated_at, training_cutoff, predicted_probability)
    values (fid, eid, 'total_rounds', 1.5, 'over', 'PROP-0001', 'TEST-ONLY', now(), now()+interval '1 day', 0.55);
    r := r||'future_cutoff_ALLOWED;';
  exception when others then r := r||'future_cutoff_blocked;'; end;
  begin
    insert into prop_model_locks (fight_id, event_id, market_type, threshold, side, model_name, model_version, generated_at, training_cutoff, predicted_probability)
    select id, event_id, 'total_rounds', 2.5, 'over', 'PROP-0001', 'TEST-ONLY', now(), now()-interval '1 hour', 0.55
      from fights where winner_id is not null order by id desc limit 1;
    r := r||'settled_lock_ALLOWED;';
  exception when others then r := r||'settled_lock_blocked;'; end;
  raise exception 'PROBE:%', r;
end $$;
"""


def _mgmt_sql(sql):
    token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query",
        data=json.dumps({"query": sql}).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


@pytest.mark.skipif(not os.environ.get("SUPABASE_ACCESS_TOKEN"), reason="needs SUPABASE_ACCESS_TOKEN")
def test_db_ledgers_are_append_only_and_lock_guard_holds():
    """Runs a DO block that inserts probe rows, tries to rewrite them, then raises
    so the WHOLE transaction rolls back. The error text carries the results."""
    status, body = _mgmt_sql(ROLLBACK_PROBE)
    assert "PROBE:" in body, body
    res = body.split("PROBE:", 1)[1]
    for expected in ("quote_update_blocked", "quote_delete_blocked", "start_update_blocked",
                     "lock_update_blocked", "lock_delete_blocked", "future_cutoff_blocked",
                     "settled_lock_blocked"):
        assert expected in res, res
    assert "ALLOWED" not in res, res
    # and nothing leaked: no TEST-ONLY lock survives the rollback
    status, body = _mgmt_sql("select count(*) as n from prop_model_locks where model_version='TEST-ONLY'")
    assert '"n":0' in body.replace(" ", ""), body
