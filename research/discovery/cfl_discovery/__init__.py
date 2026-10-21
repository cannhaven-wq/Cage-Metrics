"""CFL Discovery Engine, Phase 1 - offline hypothesis discovery on PRED-001 DEV data.

Plain version: generate many candidate fight factors, test each one against the
betting market on fights it was not fitted on, and keep a permanent record of
every one tried, including the ones that failed.

Nothing here reads a database, a network, or any fight on or after
2025-01-01. Nothing here registers, promotes or publishes a model. A result
from this package is an exploratory DEV result under PRED-001 section 9: it
licenses no statement outside the research folder.
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
DISCOVERY_DIR = HERE.parent
REPO = DISCOVERY_DIR.parent.parent

# Reuse, do not rebuild: the frozen PRED-001 rules and the engine's
# point-in-time feature builder are imported, never copied or edited.
for p in (REPO / "research" / "protocol", REPO / "cfl_engine"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

__version__ = "1.0.0"
