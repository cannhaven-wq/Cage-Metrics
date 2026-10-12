"""Single source of truth for the published model version string.

Bump this when the feature set or training scheme changes in a way that makes
old backtest rows non-comparable. The site treats every engine_v* row as one
model family (it never filters by version) -- the string is provenance, shown
to users as-is.

History:
  engine_v1  2026-07-16  initial leak-audited walk-forward engine
  engine_v2  2026-07-18  + static physical attributes (height/reach/stance)
  engine_v3  2026-10-12  T-083: same features and training scheme, made
                         reproducible. Weight class is a fixed scale instead of
                         factorize order (engine.wc_code_of); dependencies are
                         pinned exactly; every publish saves its model,
                         calibrator, inputs and a hashed manifest. There is no
                         engine_v3 backtest in model_picks yet: the published
                         backtest rows are engine_v2.

ENGINE_BUILD identifies the exact dependency set. Change it whenever
requirements.txt changes; the publish manifest records both.
"""
ENGINE_VERSION = "engine_v3"
ENGINE_BUILD = "2026-10-12.1"
