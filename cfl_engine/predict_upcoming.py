"""Live serving: publish calibrated picks (Face 1) + flagged edges (Face 2) for
UPCOMING fights, straight from the audited walk-forward engine.

One brain, two faces — exactly as the backtest, retrained on ALL completed
decisive fights and pointed at the next card(s):

  1. Rebuild point-in-time features by running engine.build_features on
     completed+upcoming concatenated, then selecting the upcoming rows. The
     history loops only look at strictly-prior COMPLETED fights, so the upcoming
     rows' placeholder results never leak into anyone's features. Completed rows
     are identical to a completed-only build (upcoming fights are future-dated,
     so they are never prior to a real fight, never update Elo — placeholder
     result 'nc' is skipped by compute_elo, belt-and-braces vs multi-card leaks).
  2. Train the final XGBClassifier on all completed decisive fights: params from
     train.tune on the base window (same folds as run_pipeline), early stopping
     on the last 10% of the training window (mirrors train.walk_forward). Predict
     with engine.predict_symmetric (MANDATORY — averages both corner orderings so
     P(A)+P(B)=1 exactly; upcoming rows are left in DB corner order, not
     randomized, and symmetric inference makes that safe).
  3. Calibrate with a single isotonic fit on the pooled walk-forward OOS
     (out_real/oos_predictions.csv, p_raw vs y; Platt if <1500 rows) — mirrors
     train.rolling_calibrate. Blend with a logistic stack of [logit(p_cal),
     logit(q_mkt)] fit on the OOS rows that have odds — mirrors train.rolling_blend.
  4. Emit model_picks for every upcoming fight, and model_edges only where the
     current vig-free consensus disagrees by >= the engine's edge_min AND the
     fight is not in a no-bet segment (Catch Weight / Light Heavyweight /
     Strawweight, or a debut). Guardrails (quarter-Kelly / 2% cap / 4% edge) come
     straight from faces.face2_edges — never redefined here.

Corner discipline: predictions and odds are handled in the DB fights-table corner
order throughout (fighter_a_id/fighter_b_id as stored). pick_side / edge side is
therefore the true DB corner, never a randomized label. Consensus odds are mapped
to DB corners by FIGHTER ID (the snapshot's own a/b naming is not trusted).

Credentials: env SUPABASE_URL + SUPABASE_SECRET_KEY (service key, legacy JWT,
read from env — never printed). --dry-run (default) prints + writes preview CSVs;
--execute inserts via REST with insert-only pick locking.

Usage (from repo root, PYTHONPATH=cfl_engine):
  python cfl_engine/predict_upcoming.py            # dry-run
  python cfl_engine/predict_upcoming.py --execute  # publish
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
import urllib.error
import urllib.request

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier

import faces
from engine import (american_to_prob, build_features, devig_a, load_data,
                    make_matchup_features, predict_symmetric, randomize_corners)
from export_data import fetch_all  # reuse the paginating PostgREST reader
from train import EPS, FIXED, _logit, chronological_folds, tune

HERE = os.path.dirname(__file__)
DATA_DIR = os.path.join(HERE, "data")
OOS_CSV = os.path.join(HERE, os.pardir, "out_real", "oos_predictions.csv")
PREVIEW_DIR = os.path.join(HERE, os.pardir, "out_real")

MODEL_VERSION = "engine_v1"
SOURCE = "live"
ISO_MIN_POOL = 1500  # mirrors train.ISO_MIN_POOL: below this, isotonic overfits

# No-bet segments (from audit.segment_brier: divisions where the market's Brier
# beats the model). Debut fighters (0 prior fights) are the 'debut_involved'
# segment. Edges are suppressed here; picks are still published.
NO_BET_WEIGHT_CLASSES = ("Catch Weight", "Light Heavyweight", "Strawweight")

# Guardrails live in faces.face2_edges — pull them from its signature so they are
# never redefined (single source of truth: quarter-Kelly / 2% cap / 4% edge_min).
_F2 = inspect.signature(faces.face2_edges).parameters
EDGE_MIN = _F2["edge_min"].default
KELLY_FRAC = _F2["kelly_frac"].default
CAP = _F2["cap"].default


# --------------------------------------------------------------------- env / REST
def _env_key() -> str:
    for name in ("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY"):
        if os.environ.get(name):
            return os.environ[name]
    sys.exit("No Supabase service key in env (SUPABASE_SECRET_KEY / "
             "SUPABASE_SERVICE_ROLE_KEY / SUPABASE_SERVICE_KEY).")


def rest_insert(base_url: str, key: str, table: str, rows: list[dict],
                on_conflict: str) -> int:
    """Insert-only publish: on_conflict=<cols> + resolution=ignore-duplicates so a
    row that already exists (same fight_id, source) is left untouched — published
    picks are never re-priced. Returns the number of rows the server accepted."""
    if not rows:
        return 0
    body = json.dumps(rows).encode()
    req = urllib.request.Request(
        f"{base_url}/rest/v1/{table}?on_conflict={on_conflict}",
        data=body, method="POST",
        headers={
            "apikey": key, "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=ignore-duplicates,return=representation",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return len(json.load(resp))


# --------------------------------------------------------------------- data pulls
def pull_upcoming(base_url: str, key: str) -> pd.DataFrame:
    """Upcoming fights = fights on an is_upcoming event, both corners present,
    winner_id still null. Returns DB corner order untouched."""
    events = fetch_all(base_url, key, "events",
                       "select=id,event_date,name&is_upcoming=eq.true&order=event_date")
    ev = {e["id"]: e for e in events}
    if not ev:
        return pd.DataFrame()
    idlist = ",".join(str(i) for i in ev)
    fights = fetch_all(base_url, key, "fights",
                       "select=id,event_id,fighter_a_id,fighter_b_id,winner_id,"
                       "weight_class,scheduled_rounds"
                       f"&event_id=in.({idlist})&winner_id=is.null&order=event_id,id")
    rows = []
    for f in fights:
        if f["fighter_a_id"] is None or f["fighter_b_id"] is None:
            continue
        e = ev.get(f["event_id"])
        if not e or not e["event_date"]:
            continue
        rows.append({
            "fight_id": f["id"], "event_id": f["event_id"],
            "event_name": e["name"], "event_date": e["event_date"],
            "fighter_a_id": f["fighter_a_id"], "fighter_b_id": f["fighter_b_id"],
            "weight_class": f["weight_class"], "n_rounds_sched": f["scheduled_rounds"],
        })
    return pd.DataFrame(rows)


def pull_consensus(base_url: str, key: str, fight_ids: list[int]) -> dict:
    """Current vig-free market per fight, mapped to DB corners BY FIGHTER ID.

    Reads v_fight_odds_consensus — the VIEW computed live from the raw
    fight_odds rows that the 2h Odds-API cron keeps fresh. (The similarly
    named fight_odds_consensus_snapshot TABLE goes stale — it stopped being
    refreshed in May 2026 and has zero upcoming coverage; do not read it.)
    The view carries its OWN fighter_a_id/fighter_b_id + american_odds_a/b; we
    never trust the positional a/b naming — we key each price to its
    fighter_id, then read off the price for the DB fighter_a / fighter_b.
    If more than one row per fight appears, the latest fetched_at wins.

    Returns {fight_id: {fighter_id: american_odds}}.
    """
    if not fight_ids:
        return {}
    out: dict[int, dict] = {}
    seen: dict[int, str] = {}
    for i in range(0, len(fight_ids), 200):
        chunk = ",".join(str(x) for x in fight_ids[i:i + 200])
        rows = fetch_all(base_url, key, "v_fight_odds_consensus",
                         "select=fight_id,fighter_a_id,fighter_b_id,"
                         "american_odds_a,american_odds_b,fetched_at"
                         f"&fight_id=in.({chunk})&order=fetched_at")
        for r in rows:  # ascending fetched_at -> later rows overwrite earlier
            fid = r["fight_id"]
            ts = r.get("fetched_at") or ""
            if fid in seen and ts < seen[fid]:
                continue
            seen[fid] = ts
            out[fid] = {r["fighter_a_id"]: r["american_odds_a"],
                        r["fighter_b_id"]: r["american_odds_b"]}
    return out


def load_fighters(base_url: str, key: str, need_ids: set) -> pd.DataFrame:
    """data/fighters.csv (dob for the trained population) + any upcoming
    fighters missing from it, fetched live so debutants still get an age."""
    base = pd.read_csv(os.path.join(DATA_DIR, "fighters.csv"))
    base["dob"] = pd.to_datetime(base["dob"], errors="coerce")
    missing = need_ids - set(base["fighter_id"])
    if missing:
        idlist = ",".join(str(i) for i in missing)
        live = fetch_all(base_url, key, "fighters", f"select=id,name,dob&id=in.({idlist})")
        if live:
            add = pd.DataFrame([{"fighter_id": x["id"], "name": x["name"], "dob": x["dob"]}
                               for x in live])
            add["dob"] = pd.to_datetime(add["dob"], errors="coerce")
            base = pd.concat([base, add], ignore_index=True)
    return base


# --------------------------------------------------------------------- modeling
def train_final_model(feat_completed: pd.DataFrame, log=print):
    """Mirror run_pipeline's feature build (randomize corners, decisive only),
    tune on the base window, then fit ONE final model on all completed decisive
    fights with early stopping on the last 10% of the (chronological) window."""
    feat = randomize_corners(feat_completed, seed=42)
    model_df = feat[feat["result"].isin(["a", "b"])].reset_index(drop=True)
    y = (model_df["result"] == "a").astype(int).to_numpy()
    X, diff_cols, _ = make_matchup_features(model_df)

    folds = chronological_folds(len(model_df))
    base_end = len(folds[0][0])
    params = tune(X, y, base_end, log=log)

    es = int(len(X) * 0.9)  # last 10% for early stopping (same as walk_forward)
    model = XGBClassifier(early_stopping_rounds=75, **{**FIXED, **params})
    model.fit(X.iloc[:es], y[:es], eval_set=[(X.iloc[es:], y[es:])], verbose=False)
    log(f"  final model: trained on {len(X)} decisive fights, "
        f"best_iter={model.best_iteration}")
    return model, diff_cols


def fit_calibrator_and_blend(log=print):
    """Single isotonic (or Platt) calibrator on the pooled walk-forward OOS, plus
    a logistic market blend on the OOS rows that have odds. Returns
    (calibrate(p_raw)->p_cal, blend(p_cal, q_mkt)->p_blend)."""
    oos = pd.read_csv(OOS_CSV)
    p_raw = oos["p_raw"].to_numpy()
    y = oos["y"].to_numpy()
    if len(oos) >= ISO_MIN_POOL:
        iso = IsotonicRegression(y_min=EPS, y_max=1 - EPS, out_of_bounds="clip")
        iso.fit(p_raw, y)
        calibrate = lambda p: iso.predict(np.asarray(p, dtype=float))
        log(f"  calibrator: isotonic on {len(oos)} pooled OOS rows")
    else:
        platt = LogisticRegression(C=1e6, max_iter=1000)
        platt.fit(_logit(p_raw).reshape(-1, 1), y)
        calibrate = lambda p: platt.predict_proba(_logit(np.asarray(p, dtype=float)).reshape(-1, 1))[:, 1]
        log(f"  calibrator: Platt on {len(oos)} pooled OOS rows")

    p_cal_oos = np.clip(calibrate(p_raw), EPS, 1 - EPS)
    has_q = oos["q_mkt"].notna().to_numpy()
    Z = np.column_stack([_logit(p_cal_oos[has_q]), _logit(oos["q_mkt"].to_numpy()[has_q])])
    lr = LogisticRegression(C=100.0, max_iter=1000)
    lr.fit(Z, y[has_q])
    log(f"  blend: logistic on {int(has_q.sum())} OOS rows with odds")

    def blend(p_cal, q_mkt):
        z = np.column_stack([_logit(np.asarray(p_cal, dtype=float)),
                             _logit(np.asarray(q_mkt, dtype=float))])
        return lr.predict_proba(z)[:, 1]

    return calibrate, blend


# --------------------------------------------------------------------- main
def build_predictions(base_url: str, key: str, log=print):
    log("[1/5] pulling upcoming fights + current consensus ...")
    up = pull_upcoming(base_url, key)
    if up.empty:
        log("      no upcoming fights found (no is_upcoming events).")
        return pd.DataFrame(), pd.DataFrame()
    fight_ids = up["fight_id"].tolist()
    consensus = pull_consensus(base_url, key, fight_ids)
    log(f"      {len(up)} upcoming fights across {up['event_id'].nunique()} events; "
        f"consensus odds for {len(consensus)} of them")

    log("[2/5] rebuilding point-in-time features (completed + upcoming) ...")
    fights_c, stats_c, fighters_c = load_data(
        os.path.join(DATA_DIR, "fights.csv"),
        os.path.join(DATA_DIR, "fight_stats.csv"),
        os.path.join(DATA_DIR, "fighters.csv"))
    need = set(up["fighter_a_id"]) | set(up["fighter_b_id"])
    fighters_all = load_fighters(base_url, key, need)

    up_rows = up.copy()
    up_rows["event_date"] = pd.to_datetime(up_rows["event_date"])
    up_rows["result"] = "nc"          # placeholder; compute_elo skips nc, never leaks
    up_rows["method"] = np.nan
    up_rows["odds_a"] = np.nan
    up_rows["odds_b"] = np.nan

    # Training features: completed fights only (mirrors run_pipeline exactly).
    feat_completed = build_features(fights_c, stats_c, fighters_all)

    # Serving features: rebuild PER UPCOMING EVENT so fights on OTHER upcoming
    # cards never leak into a fighter's history. A fighter booked on two future
    # cards would otherwise pick up a phantom 0-stat prior on the later card
    # (wiping their streak, corrupting days_since_last). Fights within one event
    # share an event_date, so the engine's strictly-before-date rule already
    # keeps same-card fights out of each other's history — and each per-event
    # build sees only completed fights as priors. ~1s per event.
    parts = []
    for _eid, grp in up_rows.groupby("event_id"):
        g = grp.reindex(columns=fights_c.columns)  # align to completed schema
        combined = pd.concat([fights_c, g], ignore_index=True)
        feat_e = build_features(combined, stats_c, fighters_all)
        parts.append(feat_e[feat_e["fight_id"].isin(set(grp["fight_id"]))])
    feat_up = pd.concat(parts, ignore_index=True)

    log("[3/5] training final model + calibrator/blend ...")
    model, diff_cols = train_final_model(feat_completed, log=log)
    calibrate, blend = fit_calibrator_and_blend(log=log)

    log("[4/5] symmetric inference on upcoming fights ...")
    X_up, diff_cols_up, _ = make_matchup_features(feat_up)
    assert diff_cols_up == diff_cols, "feature columns drifted between train and serve"
    p_raw_a, asym = predict_symmetric(model, X_up, diff_cols)  # P(DB fighter_a)
    # Clip to the publish bounds HERE, upstream of the blend: the isotonic tail
    # blocks rest on single-digit samples, and an artifact like 0.9999 must not
    # flow through logit() into the blend and flag a 20-point "edge".
    p_cal_a = np.clip(calibrate(p_raw_a), PUBLISH_P_MIN, PUBLISH_P_MAX)

    # devig current consensus to DB corners; blend where a market exists
    q_a = np.full(len(feat_up), np.nan)
    odds_a = np.full(len(feat_up), np.nan)
    odds_b = np.full(len(feat_up), np.nan)
    for i, r in feat_up.iterrows():
        c = consensus.get(int(r["fight_id"]))
        if not c:
            continue
        oa = c.get(int(r["fighter_a_id"]))
        ob = c.get(int(r["fighter_b_id"]))
        if oa is None or ob is None:
            continue
        odds_a[i], odds_b[i] = oa, ob
        q_a[i] = devig_a(oa, ob)  # vig-free P(DB fighter_a)
    has_q = ~np.isnan(q_a)
    p_blend_a = p_cal_a.copy()
    if has_q.any():
        p_blend_a[has_q] = np.clip(
            blend(p_cal_a[has_q], q_a[has_q]), EPS, 1 - EPS)

    meta = feat_up[["fight_id", "event_date", "fighter_a_id", "fighter_b_id",
                    "weight_class", "a_n_fights", "b_n_fights"]].copy()
    meta = meta.merge(up[["fight_id", "event_name", "event_date"]].rename(
        columns={"event_date": "event_date_str"}), on="fight_id", how="left")
    name_map = dict(zip(fighters_all["fighter_id"], fighters_all["name"]))
    meta["a_name"] = meta["fighter_a_id"].map(name_map)
    meta["b_name"] = meta["fighter_b_id"].map(name_map)
    meta["p_cal_a"] = p_cal_a
    meta["p_blend_a"] = p_blend_a
    meta["q_a"] = q_a
    meta["odds_a"] = odds_a
    meta["odds_b"] = odds_b
    meta["raw_asymmetry"] = asym

    log("[5/5] assembling picks + edges ...")
    picks = _make_picks(meta)
    edges = _make_edges(meta)
    return picks, edges


# Publish cap on calibrated confidence: the pooled isotonic's tail blocks rest
# on single-digit sample counts (7 fights in the top block), so extreme values
# like 0.9999 are calibration artifacts, not knowledge. Clipping the PUBLISHED
# probability is a variance floor, not a distortion of the model.
PUBLISH_P_MIN, PUBLISH_P_MAX = 0.05, 0.95


def _make_picks(meta: pd.DataFrame) -> pd.DataFrame:
    """One calibrated pick per upcoming fight (DB corner discipline)."""
    rows = []
    for r in meta.itertuples(index=False):
        pa = float(np.clip(r.p_cal_a, PUBLISH_P_MIN, PUBLISH_P_MAX))
        take_a = pa >= 0.5
        rows.append({
            "fight_id": int(r.fight_id),
            "event_date": str(r.event_date_str),
            "p_cal": round(pa if take_a else 1 - pa, 6),
            "pick_fighter_id": int(r.fighter_a_id if take_a else r.fighter_b_id),
            "pick_side": "a" if take_a else "b",
            "tier": faces.tier_of(pa),
            "source": SOURCE,
            "model_version": MODEL_VERSION,
            # preview-only context (dropped before insert):
            "_event": r.event_name, "_wc": r.weight_class,
            "_pick": r.a_name if take_a else r.b_name,
            "_opp": r.b_name if take_a else r.a_name,
            "_conf": round(max(pa, 1 - pa), 4),
        })
    return pd.DataFrame(rows)


def _make_edges(meta: pd.DataFrame) -> pd.DataFrame:
    """Flagged +EV bets vs the vig-free consensus, via faces.face2_edges (its
    quarter-Kelly / cap / edge_min guardrails, unmodified). No-bet segments and
    fights without a current market are dropped before the edge test."""
    nobet = (meta["weight_class"].isin(NO_BET_WEIGHT_CLASSES)
             | (meta["a_n_fights"] == 0) | (meta["b_n_fights"] == 0))
    cand = meta[~nobet].copy()
    # shape face2_edges expects (DB corner order; y is a throwaway — 'won' is
    # unknowable pre-event and is discarded):
    f2in = pd.DataFrame({
        "blended": (~cand["q_a"].isna()).to_numpy(),
        "q_mkt": cand["q_a"].to_numpy(),
        "p_blend": cand["p_blend_a"].to_numpy(),
        "odds_a": cand["odds_a"].to_numpy(),
        "odds_b": cand["odds_b"].to_numpy(),
        "y": 0,
        "fight_id": cand["fight_id"].to_numpy(),
        "event_date": cand["event_date_str"].to_numpy(),
        "fighter_a_id": cand["fighter_a_id"].to_numpy(),
        "fighter_b_id": cand["fighter_b_id"].to_numpy(),
        "_event": cand["event_name"].to_numpy(),
        "_wc": cand["weight_class"].to_numpy(),
        "_a_name": cand["a_name"].to_numpy(),
        "_b_name": cand["b_name"].to_numpy(),
    })
    bets, _ = faces.face2_edges(f2in)
    if bets.empty:
        return pd.DataFrame()
    rows = []
    for r in bets.to_dict("records"):  # dict keeps leading-underscore col names
        take_a = r["side"] == "a"
        rows.append({
            "fight_id": int(r["fight_id"]),
            "event_date": str(r["event_date"]),
            "side": r["side"],  # DB corner (features never randomized on serve)
            "bet_fighter_id": int(r["fighter_a_id"] if take_a else r["fighter_b_id"]),
            "p_blend": round(float(r["p_side"]), 6),
            "q_mkt": round(float(r["q_side"]), 6),
            "edge": round(float(r["edge"]), 6),
            "stake_frac": round(float(r["stake"]), 6),
            "odds_at_publish": int(r["odds_a"] if take_a else r["odds_b"]),
            "source": SOURCE,
            "model_version": MODEL_VERSION,
            "_event": r["_event"], "_wc": r["_wc"],  # preview-only context
            "_bet": r["_a_name"] if take_a else r["_b_name"],
        })
    return pd.DataFrame(rows)


_PICK_COLS = ["fight_id", "event_date", "p_cal", "pick_fighter_id", "pick_side",
              "tier", "source", "model_version"]
_EDGE_COLS = ["fight_id", "event_date", "side", "bet_fighter_id", "p_blend",
              "q_mkt", "edge", "stake_frac", "odds_at_publish", "source",
              "model_version"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute", action="store_true",
                    help="insert into Supabase (default: dry-run preview only)")
    ap.add_argument("--dry-run", action="store_true", help="explicit no-op (default)")
    args = ap.parse_args()
    execute = args.execute

    base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not base_url:
        sys.exit("SUPABASE_URL not set in env.")
    key = _env_key()

    picks, edges = build_predictions(base_url, key)
    os.makedirs(PREVIEW_DIR, exist_ok=True)

    if picks.empty:
        print("\nNo upcoming picks produced.")
        return
    picks_out = picks[_PICK_COLS]
    edges_out = edges[_EDGE_COLS] if not edges.empty else pd.DataFrame(columns=_EDGE_COLS)
    picks_out.to_csv(os.path.join(PREVIEW_DIR, "model_picks_preview.csv"), index=False)
    edges_out.to_csv(os.path.join(PREVIEW_DIR, "model_edges_preview.csv"), index=False)

    # ------- human-readable preview
    tier_counts = picks["tier"].value_counts().to_dict()
    print(f"\n=== PICKS ({len(picks)}) — by tier: {tier_counts} ===")
    show = picks[["_event", "fight_id", "pick_side", "_pick", "_opp", "p_cal",
                  "tier", "_wc"]].rename(
        columns={"_event": "event", "_pick": "pick", "_opp": "opp", "_wc": "wc"})
    with pd.option_context("display.max_rows", None, "display.width", 220,
                           "display.max_colwidth", 28):
        print(show.to_string(index=False))

    print(f"\n=== EDGES ({len(edges)}) ===")
    if edges.empty:
        print("  (none) — no upcoming fight cleared the edge threshold against a "
              "current vig-free consensus.")
    else:
        eshow = edges[["_event", "fight_id", "side", "_bet", "p_blend",
                       "q_mkt", "edge", "stake_frac", "odds_at_publish"]].rename(
            columns={"_event": "event", "_bet": "bet"})
        with pd.option_context("display.max_rows", None, "display.width", 220,
                               "display.max_colwidth", 28):
            print(eshow.to_string(index=False))

    print(f"\npreview CSVs -> {os.path.abspath(os.path.join(PREVIEW_DIR, 'model_picks_preview.csv'))}")
    print(f"             {os.path.abspath(os.path.join(PREVIEW_DIR, 'model_edges_preview.csv'))}")

    if not execute:
        print("\nDRY-RUN — nothing inserted. Re-run with --execute to publish.")
        return

    n_p = rest_insert(base_url, key, "model_picks",
                      picks_out.to_dict("records"), "fight_id,source")
    n_e = rest_insert(base_url, key, "model_edges",
                      edges_out.to_dict("records"), "fight_id,source") if not edges_out.empty else 0
    print(f"\nEXECUTED — model_picks: {n_p} inserted (duplicates ignored), "
          f"model_edges: {n_e} inserted.")


if __name__ == "__main__":
    main()
