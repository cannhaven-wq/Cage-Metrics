"""Reproducibility bundle for every live engine publish (T-083).

T-082 found that the engine's locked live forecasts could not be re-derived:
re-running the same code for the same days moved a fight by 4.5 points on
average and flipped 1 in 10. A forecast that cannot be re-derived cannot be
audited. So every publish now writes, before anything is inserted:

  model.ubj               the exact trained XGBoost model
  calibrator.json         the isotonic (or Platt) map, as numbers
  blend.json              the market-blend coefficients
  serving_features.csv    the feature rows the model scored, with fight ids
  predictions.csv         p_raw_a, p_cal_a, p_blend_a, q_a per fight
  inputs/                 the history export and OOS file the run trained on
  manifest.json           engine version and build, git commit, library
                          versions, and the sha256 of every file above

`verify(dir)` re-derives every published probability from the bundle alone and
checks it is IDENTICAL, not close. `python cfl_engine/publish_bundle.py DIR`
runs it.

Where bundles live: engine-serve.yml uploads each one as a workflow artifact
(90-day retention, the maximum Actions allows). That keeps them only for 90
days. Durable storage is a separate decision (a storage bucket or a table is a
production change) and is queued, not assumed.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
OOS_CSV = os.path.join(HERE, os.pardir, "out_real", "oos_predictions.csv")
INPUT_FILES = {
    "fights.csv": os.path.join(DATA_DIR, "fights.csv"),
    "fight_stats.csv": os.path.join(DATA_DIR, "fight_stats.csv"),
    "fighters.csv": os.path.join(DATA_DIR, "fighters.csv"),
    "oos_predictions.csv": OOS_CSV,
}
PIN_LIBS = ("xgboost", "scikit-learn", "pandas", "numpy", "scipy")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _versions() -> dict:
    from importlib.metadata import PackageNotFoundError, version
    out = {"python": sys.version.split()[0]}
    for lib in PIN_LIBS:
        try:
            out[lib] = version(lib)
        except PackageNotFoundError:
            out[lib] = None
    return out


def _git_commit() -> str | None:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True,
                              text=True, timeout=10).stdout.strip() or None
    except Exception:  # noqa: BLE001 - provenance is best effort; the hashes are not
        return None


def write(bundle: dict, root: str, inputs: dict | None = None, now=None) -> dict:
    """Write one publish bundle under root/<UTC timestamp>/ and return its manifest."""
    from version import ENGINE_BUILD, ENGINE_VERSION
    now = now or dt.datetime.now(dt.timezone.utc)
    d = os.path.join(root, now.strftime("%Y%m%dT%H%M%SZ"))
    os.makedirs(os.path.join(d, "inputs"), exist_ok=True)

    bundle["model"].save_model(os.path.join(d, "model.ubj"))
    with open(os.path.join(d, "calibrator.json"), "w") as f:
        json.dump(bundle["calibrator"], f)
    with open(os.path.join(d, "blend.json"), "w") as f:
        json.dump(bundle["blend"], f)
    feats = bundle["X_up"].copy()
    feats.insert(0, "fight_id", bundle["predictions"]["fight_id"].to_numpy())
    # repr-exact floats: a CSV that rounds a feature changes the prediction
    feats.to_csv(os.path.join(d, "serving_features.csv"), index=False, float_format="%.17g")
    bundle["predictions"].to_csv(os.path.join(d, "predictions.csv"), index=False,
                                 float_format="%.17g")
    for name, src in (inputs or INPUT_FILES).items():
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(d, "inputs", name))

    files = {}
    for base, _dirs, names in os.walk(d):
        for n in sorted(names):
            full = os.path.join(base, n)
            files[os.path.relpath(full, d)] = sha256_file(full)
    manifest = {
        "engine_version": ENGINE_VERSION, "engine_build": ENGINE_BUILD,
        "git_commit": _git_commit(), "written_at": now.isoformat(timespec="seconds"),
        "versions": _versions(),
        "diff_cols": bundle["diff_cols"], "feature_cols": bundle["feature_cols"],
        "model_params": {k: v for k, v in bundle["model"].get_params().items()
                         if isinstance(v, (int, float, str, bool, type(None)))},
        "n_fights": int(len(bundle["predictions"])),
        "files": dict(sorted(files.items())),
    }
    body = json.dumps(manifest, indent=1, sort_keys=True)
    with open(os.path.join(d, "manifest.json"), "w") as f:
        f.write(body)
    manifest["dir"] = d
    manifest["manifest_sha256"] = hashlib.sha256(body.encode()).hexdigest()
    return manifest


def _calibrate(cal: dict, p: np.ndarray) -> np.ndarray:
    """Apply a stored calibrator. For isotonic this is exactly what
    IsotonicRegression.predict(out_of_bounds="clip") does — clip to the knot
    range, then linear interpolation between knots — and
    tests/test_engine_reproducible.py checks it is bit-identical to sklearn."""
    p = np.asarray(p, dtype=float)
    if cal["kind"] == "isotonic":
        x = np.asarray(cal["x"], dtype=float)
        y = np.asarray(cal["y"], dtype=float)
        return np.interp(np.clip(p, x[0], x[-1]), x, y)
    from train import _logit
    z = _logit(p) * cal["coef"][0][0] + cal["intercept"][0]
    return 1.0 / (1.0 + np.exp(-z))


def verify(d: str) -> dict:
    """Re-derive every published probability from the bundle; identical or fail."""
    from xgboost import XGBClassifier
    from engine import predict_symmetric
    import predict_upcoming as pu

    with open(os.path.join(d, "manifest.json")) as f:
        manifest = json.load(f)
    problems = []
    for rel, want in manifest["files"].items():
        got = sha256_file(os.path.join(d, rel)) if os.path.exists(os.path.join(d, rel)) else None
        if got != want:
            problems.append(f"{rel}: sha256 {got} != manifest {want}")
    model = XGBClassifier()
    model.load_model(os.path.join(d, "model.ubj"))
    with open(os.path.join(d, "calibrator.json")) as f:
        cal = json.load(f)
    # round_trip: pandas' default float parser is not exact for 17-digit
    # values, and "re-derive exactly" means exactly
    feats = pd.read_csv(os.path.join(d, "serving_features.csv"), float_precision="round_trip")
    pred = pd.read_csv(os.path.join(d, "predictions.csv"), float_precision="round_trip")
    X = feats[manifest["feature_cols"]]
    p_raw, _ = predict_symmetric(model, X, manifest["diff_cols"])
    p_cal = np.clip(_calibrate(cal, p_raw), pu.PUBLISH_P_MIN, pu.PUBLISH_P_MAX)
    raw_diff = float(np.max(np.abs(p_raw - pred["p_raw_a"].to_numpy()))) if len(pred) else 0.0
    cal_diff = float(np.max(np.abs(p_cal - pred["p_cal_a"].to_numpy()))) if len(pred) else 0.0
    if raw_diff != 0.0:
        problems.append(f"p_raw_a differs by up to {raw_diff}")
    if cal_diff != 0.0:
        problems.append(f"p_cal_a differs by up to {cal_diff}")
    return {"dir": d, "n": int(len(pred)), "max_abs_diff_raw": raw_diff,
            "max_abs_diff_cal": cal_diff, "problems": problems, "ok": not problems}


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    res = verify(sys.argv[1])
    print(json.dumps(res, indent=1))
    sys.exit(0 if res["ok"] else 1)
