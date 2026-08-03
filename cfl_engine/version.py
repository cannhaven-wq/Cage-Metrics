"""Single source of truth for the published model version string.

Bump this when the feature set or training scheme changes in a way that makes
old backtest rows non-comparable. The site treats every engine_v* row as one
model family (it never filters by version) -- the string is provenance, shown
to users as-is.

History:
  engine_v1  2026-07-16  initial leak-audited walk-forward engine
  engine_v2  2026-07-18  + static physical attributes (height/reach/stance)
"""
ENGINE_VERSION = "engine_v2"
