"""Fit the chosen WIN-001 variant on every eligible DEV fight and write artifact.json.

    cd research/experiments/WIN-001 && python3 freeze_artifact.py

Deterministic: same data, same code, same bytes. The artifact records the
sha256 of the three DEV data files it was fitted from, so a refit on different
data cannot pass as the frozen one. Re-running after the freeze must reproduce
the registered sha256 exactly, or the registered artifact is not this code's.
"""
from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import model as M  # noqa: E402
from dev_walkforward import load  # noqa: E402

CHOSEN = "full_c1"   # best DEV walk-forward gain; see DEV_RESULTS.md


def main():
    rows, elig = load()
    feats, C = M.VARIANTS[CHOSEN]
    art = M.fit(elig, elig.p_market.to_numpy(), elig.y.to_numpy(), feats, C)
    art.update({
        "experiment_id": "WIN-001",
        "variant": CHOSEN,
        "model_class": "incremental",
        "dev_window": [str(elig.event_date.min().date()), str(elig.event_date.max().date())],
        "dev_data_sha256": {p.name: M.sha256_file(p) for p in sorted((HERE / "data").glob("*.csv"))},
        "benchmark": "BFO closing consensus, proportional de-vig",
    })
    sha = M.save_artifact(art)
    print(f"fitted on {art['n_fit']} fights; artifact.json sha256 {sha}")
    for k, v in art["coef"].items():
        print(f"  {k:16s} {v:+.4f}")


if __name__ == "__main__":
    main()
