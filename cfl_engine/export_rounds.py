"""Export the fight_rounds table to data/fight_rounds.csv in the schema the
props count-feature builder (features/build_count_features.py) expects.

The live `fight_rounds` table uses verbose column names (a_sig_str_landed,
a_ctrl_seconds, ...); build_count_features reads the compact stems
(a_sig_landed, a_ctrl, ...). This script fetches the table and renames, so the
round-level CSV can be regenerated from Supabase in CI (export_data.py only
aggregates rounds to fight level and never writes this file).

Credentials: env SUPABASE_URL + a service key. Read-only.

Usage:  python cfl_engine/export_rounds.py [--outdir cfl_engine/data]
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from export_data import fetch_all  # reuse the paginating PostgREST reader

# compact CSV stem -> live fight_rounds column stem (per corner a_/b_)
STEM_MAP = {
    "sig_landed": "sig_str_landed",
    "sig_att":    "sig_str_attempted",
    "td_landed":  "td_landed",
    "td_att":     "td_attempted",
    "kd":         "kd",
    "ctrl":       "ctrl_seconds",
    "sub_att":    "sub_attempts",
}
OUT_COLS = (["fight_id", "round_number", "fighter_a_id", "fighter_b_id"]
            + [f"{s}_{stem}" for stem in STEM_MAP for s in ("a", "b")])


def _env_key() -> str:
    for name in ("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY"):
        if os.environ.get(name):
            return os.environ[name]
    sys.exit("No Supabase service key in env.")


def build_df(base_url: str, key: str) -> pd.DataFrame:
    sel = ",".join(["fight_id", "round_number", "fighter_a_id", "fighter_b_id"]
                   + [f"{s}_{live}" for live in STEM_MAP.values() for s in ("a", "b")])
    rows = fetch_all(base_url, key, "fight_rounds", f"select={sel}&order=fight_id,round_number")
    out = []
    for r in rows:
        rec = {"fight_id": r["fight_id"], "round_number": r["round_number"],
               "fighter_a_id": r["fighter_a_id"], "fighter_b_id": r["fighter_b_id"]}
        for csv_stem, live_stem in STEM_MAP.items():
            for s in ("a", "b"):
                rec[f"{s}_{csv_stem}"] = r.get(f"{s}_{live_stem}")
        out.append(rec)
    return pd.DataFrame(out, columns=OUT_COLS)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", default=os.path.join(HERE, "data"))
    args = ap.parse_args()
    base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not base_url:
        sys.exit("SUPABASE_URL not set.")
    key = _env_key()
    df = build_df(base_url, key)
    os.makedirs(args.outdir, exist_ok=True)
    path = os.path.join(args.outdir, "fight_rounds.csv")
    df.to_csv(path, index=False)
    print(f"wrote {len(df)} rows -> {path}")


if __name__ == "__main__":
    main()
