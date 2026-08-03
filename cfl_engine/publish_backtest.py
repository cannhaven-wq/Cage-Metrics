"""Publish the CFL engine backtest to the model_picks / model_edges tables.

Loads the walk-forward replay (out_real/oos_predictions.csv, edge_bets.csv),
maps the engine's RANDOMIZED inference corners back to the DB fights-table
corner, and writes source='backtest' rows via the Supabase REST API.

Corner mapping (the load-bearing detail):
  oos_predictions.csv / edge_bets.csv carry POST-randomization corners in
  fighter_a_id / fighter_b_id, and p_cal / p_blend are the probability of the
  CSV's 'a'. The DB's true corner order lives in cfl_engine/data/fights.csv.
  To publish we pick the fighter the probability points at, then label the side
  'a'/'b' by comparing that fighter to the DB fights row's fighter_a_id.
  The randomized side label is NEVER published.

Guardrails (edge_min / cap) and the tier cutoffs are read from cfl_engine/
faces.py, never redefined here. Only calibrated rows are published, which
excludes fold 0 by construction (asserted). 'live' rows are never touched —
a backtest re-publish only DELETE+reinserts its own source='backtest' rows.

Modes:
  --dry-run  (default) validate, print samples + counts, write preview CSVs.
  --execute  DELETE existing source='backtest' rows, then batch-insert.

Credentials (only needed for --execute) come from env vars SUPABASE_URL and
SUPABASE_SECRET_KEY (falls back to SUPABASE_SERVICE_ROLE_KEY /
SUPABASE_SERVICE_KEY). The service key is required — it bypasses RLS.
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import faces  # tier cutoffs + guardrail defaults; PYTHONPATH=cfl_engine
from version import ENGINE_VERSION

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OOS_CSV = os.path.join(REPO, "out_real", "oos_predictions.csv")
EDGES_CSV = os.path.join(REPO, "out_real", "edge_bets.csv")
DB_FIGHTS_CSV = os.path.join(HERE, "data", "fights.csv")
PREVIEW_PICKS = os.path.join(REPO, "out_real", "publish_preview_picks.csv")
PREVIEW_EDGES = os.path.join(REPO, "out_real", "publish_preview_edges.csv")

SOURCE = "backtest"
MODEL_VERSION = ENGINE_VERSION
BATCH = 500
PAGE = 1000

# Guardrails come from faces.face2_edges' signature — the single source of
# truth that produced edge_bets.csv. Read, never redefined.
_SIG = inspect.signature(faces.face2_edges).parameters
EDGE_MIN = _SIG["edge_min"].default
KELLY_CAP = _SIG["cap"].default

PICK_COLS = ["fight_id", "event_date", "p_cal", "pick_fighter_id",
             "pick_side", "tier", "source", "model_version", "published_at"]
EDGE_COLS = ["fight_id", "event_date", "side", "bet_fighter_id", "p_blend",
             "q_mkt", "edge", "stake_frac", "odds_at_publish", "closing_odds",
             "clv_pp", "clv_beat", "source", "model_version", "published_at",
             "settled_at"]
PICK_NOT_NULL = [c for c in PICK_COLS if c != "published_at"]
EDGE_NOT_NULL = ["fight_id", "event_date", "side", "bet_fighter_id", "p_blend",
                 "q_mkt", "edge", "stake_frac", "source", "model_version"]


# ----------------------------------------------------------------- corner map
def _db_corner_maps() -> tuple[dict, dict]:
    """fight_id -> DB fighter_a_id / fighter_b_id from the DB fights export."""
    db = pd.read_csv(DB_FIGHTS_CSV, usecols=["fight_id", "fighter_a_id", "fighter_b_id"])
    if db["fight_id"].duplicated().any():
        sys.exit("data/fights.csv has duplicate fight_id -- corner map is ambiguous.")
    a = {int(r.fight_id): r.fighter_a_id for r in db.itertuples(index=False)}
    b = {int(r.fight_id): r.fighter_b_id for r in db.itertuples(index=False)}
    return a, b


def _require_cols(df: pd.DataFrame, cols: list[str], name: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        sys.exit(f"{name} missing expected columns {missing}; header drifted.")


def _map_db_side(fight_ids, chosen_fighter_ids, db_a, db_b, frame_name):
    """Return the DB corner ('a'/'b') for each chosen fighter, verifying the
    fighter genuinely sits in that fight's DB corner pair."""
    sides, bad = [], []
    for fid, who in zip(fight_ids, chosen_fighter_ids):
        fid = int(fid)
        da, dbb = db_a.get(fid), db_b.get(fid)
        if da is None or pd.isna(da) or dbb is None or pd.isna(dbb):
            bad.append((fid, "fight_id not in DB fights.csv corner map"))
            sides.append(None)
            continue
        da, dbb = int(da), int(dbb)
        if who == da:
            sides.append("a")
        elif who == dbb:
            sides.append("b")
        else:
            bad.append((fid, f"chosen fighter {who} in neither DB corner ({da},{dbb})"))
            sides.append(None)
    if bad:
        for fid, why in bad[:10]:
            print(f"  CORNER-MAP ERROR fight {fid}: {why}")
        sys.exit(f"{frame_name}: {len(bad)} rows failed DB corner mapping -- aborting.")
    return sides


# --------------------------------------------------------------- build frames
def build_picks(now_iso: str, db_a: dict, db_b: dict) -> pd.DataFrame:
    oos = pd.read_csv(OOS_CSV)
    _require_cols(oos, ["fold", "calibrated", "fight_id", "event_date",
                        "fighter_a_id", "fighter_b_id", "p_cal"], "oos_predictions.csv")

    d = oos[oos["calibrated"] == True].copy()  # noqa: E712 — pandas mask, not identity
    if d.empty:
        sys.exit("No calibrated OOS rows -- nothing to publish.")
    # Calibrated ONLY, which excludes fold 0 by construction. Assert it.
    assert (d["fold"] != 0).all(), "fold 0 leaked into the calibrated set"
    if d["fight_id"].duplicated().any():
        sys.exit("Duplicate fight_id in calibrated OOS -- would violate unique(fight_id,source).")

    take_a = d["p_cal"].to_numpy() >= 0.5
    pick_fighter = np.where(take_a, d["fighter_a_id"], d["fighter_b_id"]).astype("int64")
    p_pub = np.where(take_a, d["p_cal"], 1.0 - d["p_cal"])
    # Same publish cap as predict_upcoming.py: isotonic tail blocks rest on
    # single-digit samples, so extremes like 0.9999 are calibration artifacts.
    # report.md metrics stay unclipped; this caps only what users see.
    p_pub = np.clip(p_pub, 0.5, 0.95)
    side = _map_db_side(d["fight_id"], pick_fighter, db_a, db_b, "model_picks")

    out = pd.DataFrame({
        "fight_id": d["fight_id"].astype("int64").to_numpy(),
        "event_date": d["event_date"].astype(str).str.slice(0, 10).to_numpy(),
        "p_cal": p_pub,
        "pick_fighter_id": pick_fighter,
        "pick_side": side,
        "tier": d["p_cal"].map(faces.tier_of).to_numpy(),  # tier_of does max(p,1-p) internally
        "source": SOURCE,
        "model_version": MODEL_VERSION,
        "published_at": now_iso,
    })
    return out[PICK_COLS]


def build_edges(now_iso: str, db_a: dict, db_b: dict) -> pd.DataFrame:
    e = pd.read_csv(EDGES_CSV)
    _require_cols(e, ["fold", "calibrated", "blended", "fight_id", "event_date",
                      "fighter_a_id", "fighter_b_id", "odds_a", "odds_b",
                      "side", "p_side", "q_side", "edge", "stake"], "edge_bets.csv")

    # edge_bets are blend rows by construction (blended requires calibrated);
    # assert the guardrail rather than trust it.
    assert (e["calibrated"] == True).all(), "uncalibrated row in edge_bets.csv"  # noqa: E712
    assert (e["fold"] != 0).all(), "fold 0 row in edge_bets.csv"
    if e["fight_id"].duplicated().any():
        sys.exit("Duplicate fight_id in edge_bets -- would violate unique(fight_id,source).")

    csv_side_a = e["side"].to_numpy() == "a"
    bet_fighter = np.where(csv_side_a, e["fighter_a_id"], e["fighter_b_id"]).astype("int64")
    side = _map_db_side(e["fight_id"], bet_fighter, db_a, db_b, "model_edges")
    odds_bet = np.where(csv_side_a, e["odds_a"], e["odds_b"]).astype(float)
    odds_int = [None if pd.isna(o) else int(round(o)) for o in odds_bet]

    out = pd.DataFrame({
        "fight_id": e["fight_id"].astype("int64").to_numpy(),
        "event_date": e["event_date"].astype(str).str.slice(0, 10).to_numpy(),
        "side": side,
        "bet_fighter_id": bet_fighter,
        "p_blend": e["p_side"].to_numpy(),          # blend prob of the bet side
        "q_mkt": e["q_side"].to_numpy(),            # vig-free market prob of the bet side
        "edge": e["edge"].to_numpy(),
        "stake_frac": e["stake"].to_numpy(),
        "odds_at_publish": odds_int,                # American, bet side
        "closing_odds": odds_int,                   # backtest rows ARE at close
        "clv_pp": None,                             # no bet-time line in a backtest
        "clv_beat": None,
        "source": SOURCE,
        "model_version": MODEL_VERSION,
        "published_at": now_iso,
        "settled_at": now_iso,                      # graded outcome time == publish for replay
    })
    return out[EDGE_COLS]


# ------------------------------------------------------------------- validate
def validate(picks: pd.DataFrame, edges: pd.DataFrame) -> list[str]:
    anomalies = []

    for c in PICK_NOT_NULL:
        n = picks[c].isna().sum()
        if n:
            anomalies.append(f"model_picks.{c} has {n} nulls")
    for c in EDGE_NOT_NULL:
        n = edges[c].isna().sum()
        if n:
            anomalies.append(f"model_edges.{c} has {n} nulls")

    if not picks["p_cal"].between(0.5, 1.0).all():
        lo, hi = picks["p_cal"].min(), picks["p_cal"].max()
        anomalies.append(f"model_picks.p_cal out of [0.5,1]: min={lo:.4f} max={hi:.4f}")

    pv = picks["pick_side"].value_counts(normalize=True)
    if pv.max() >= 1.0:
        anomalies.append(f"model_picks.pick_side is 100% '{pv.idxmax()}' -- corner map suspect")
    ev = edges["side"].value_counts(normalize=True)
    if len(ev) and ev.max() >= 1.0:
        anomalies.append(f"model_edges.side is 100% '{ev.idxmax()}' -- corner map suspect")

    if not (edges["edge"] >= EDGE_MIN).all():
        anomalies.append(f"model_edges.edge below edge_min={EDGE_MIN}: min={edges['edge'].min():.4f}")
    if not (edges["stake_frac"] <= KELLY_CAP + 1e-12).all():
        anomalies.append(f"model_edges.stake_frac above cap={KELLY_CAP}: max={edges['stake_frac'].max():.4f}")

    for name, df, key in (("model_picks", picks, "fight_id"), ("model_edges", edges, "fight_id")):
        if df[key].duplicated().any():
            anomalies.append(f"{name} has duplicate {key} (violates unique(fight_id,source))")
    return anomalies


def _rows_json(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> list of dicts with native Python / JSON-safe scalars,
    every dict carrying IDENTICAL keys (missing keys would defeat DB defaults)."""
    rows = []
    for rec in df.to_dict("records"):
        clean = {}
        for k, v in rec.items():
            if v is None or (np.isscalar(v) and pd.isna(v)):
                clean[k] = None
            elif isinstance(v, (np.integer,)):
                clean[k] = int(v)
            elif isinstance(v, (np.floating,)):
                clean[k] = float(v)
            elif isinstance(v, (np.bool_,)):
                clean[k] = bool(v)
            else:
                clean[k] = v
        rows.append(clean)
    return rows


# ----------------------------------------------------------------------- REST
def _key() -> str:
    for n in ("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY"):
        if os.environ.get(n):
            return os.environ[n]
    sys.exit("No Supabase service key in env (SUPABASE_SECRET_KEY / "
             "SUPABASE_SERVICE_ROLE_KEY / SUPABASE_SERVICE_KEY) -- required for --execute.")


def _headers(key: str, extra: dict | None = None) -> dict:
    h = {"apikey": key, "Authorization": f"Bearer {key}"}
    if extra:
        h.update(extra)
    return h


def rest_delete_backtest(base: str, key: str, table: str) -> None:
    # Filter is required by PostgREST; fight_id=gte.0 matches every row, scoped
    # to source='backtest' so 'live' rows are never touched.
    url = f"{base}/rest/v1/{table}?fight_id=gte.0&source=eq.{SOURCE}"
    req = urllib.request.Request(url, method="DELETE",
                                 headers=_headers(key, {"Prefer": "return=minimal"}))
    with urllib.request.urlopen(req, timeout=120):
        pass
    print(f"  deleted existing source='{SOURCE}' rows from {table}")


def rest_insert(base: str, key: str, table: str, rows: list[dict]) -> int:
    n = 0
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i + BATCH]
        body = json.dumps(batch).encode("utf-8")
        req = urllib.request.Request(
            f"{base}/rest/v1/{table}", data=body, method="POST",
            headers=_headers(key, {"Content-Type": "application/json",
                                   "Prefer": "return=minimal"}),
        )
        with urllib.request.urlopen(req, timeout=120):
            pass
        n += len(batch)
        print(f"  inserted {n}/{len(rows)} into {table}")
    return n


def execute(picks: pd.DataFrame, edges: pd.DataFrame) -> None:
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not base:
        sys.exit("SUPABASE_URL not set -- required for --execute.")
    key = _key()
    pick_rows, edge_rows = _rows_json(picks), _rows_json(edges)
    try:
        print("model_picks:")
        rest_delete_backtest(base, key, "model_picks")
        rest_insert(base, key, "model_picks", pick_rows)
        print("model_edges:")
        rest_delete_backtest(base, key, "model_edges")
        rest_insert(base, key, "model_edges", edge_rows)
    except urllib.error.HTTPError as ex:
        detail = ex.read().decode("utf-8", "replace")
        sys.exit(f"REST error {ex.code}: {detail}")
    print(f"\nEXECUTED: {len(pick_rows)} model_picks + {len(edge_rows)} model_edges "
          f"published as source='{SOURCE}'.")


# ------------------------------------------------------------------ dry-run IO
def dry_run(picks: pd.DataFrame, edges: pd.DataFrame, anomalies: list[str]) -> None:
    picks.to_csv(PREVIEW_PICKS, index=False)
    edges.to_csv(PREVIEW_EDGES, index=False)

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)

    print("=" * 78)
    print(f"DRY RUN — source='{SOURCE}', model_version='{MODEL_VERSION}' "
          f"(edge_min={EDGE_MIN}, kelly_cap={KELLY_CAP})")
    print("=" * 78)

    print(f"\nmodel_picks: {len(picks)} rows")
    print("  sample (5):")
    print(picks.head(5).to_string(index=False))
    print("  pick_side distribution (DB corner):",
          picks["pick_side"].value_counts().to_dict())
    print("  tier distribution:", picks["tier"].value_counts().to_dict())
    print(f"  p_cal range: [{picks['p_cal'].min():.4f}, {picks['p_cal'].max():.4f}]")

    print(f"\nmodel_edges: {len(edges)} rows")
    print("  sample (5):")
    print(edges.head(5).to_string(index=False))
    print("  side distribution (DB corner):", edges["side"].value_counts().to_dict())
    print(f"  edge range: [{edges['edge'].min():.4f}, {edges['edge'].max():.4f}]")
    print(f"  stake_frac range: [{edges['stake_frac'].min():.4f}, {edges['stake_frac'].max():.4f}]")
    print(f"  odds_at_publish nulls: {edges['odds_at_publish'].isna().sum()}")

    print(f"\npreview CSVs written:\n  {PREVIEW_PICKS}\n  {PREVIEW_EDGES}")
    print("\nvalidation:", "OK — no anomalies" if not anomalies else "ANOMALIES FOUND:")
    for a in anomalies:
        print(f"  - {a}")
    print("\n(dry-run: nothing written to Supabase. Re-run with --execute to publish.)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute", action="store_true",
                    help="Publish to Supabase (default is a dry run).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Explicit dry run (the default).")
    args = ap.parse_args()

    now_iso = datetime.now(timezone.utc).isoformat()
    db_a, db_b = _db_corner_maps()
    picks = build_picks(now_iso, db_a, db_b)
    edges = build_edges(now_iso, db_a, db_b)
    anomalies = validate(picks, edges)

    if args.execute:
        if anomalies:
            print("Refusing to --execute with validation anomalies:")
            for a in anomalies:
                print(f"  - {a}")
            sys.exit(1)
        execute(picks, edges)
    else:
        dry_run(picks, edges, anomalies)


if __name__ == "__main__":
    main()
