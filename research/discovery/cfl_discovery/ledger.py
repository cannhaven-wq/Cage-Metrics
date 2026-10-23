"""Append-only, hash-chained record of every discovery run.

Each line of research/discovery/ledger.jsonl is one run: what was tested (the
catalog hash), on what (data hashes), with what (config and code hashes), and
what came out (the results file's hash and the tier counts). Each entry hashes
the one before it. tests/test_discovery.py fails if the chain breaks, if a
results file a ledger entry points at is missing or edited, or if an entry
present on main disappears.

This is what "every tested hypothesis is preserved" means in practice: a run
whose shortlist confirmed nothing cannot be deleted to leave only the run that
did, without the deletion showing up as a failing test.

Some recorded files are deliberately not committed (raw data exports and
per-fight predictions, D-034). Those are listed with their sha256 in
WITHHELD.json beside the ledger; an absent file passes only if it is listed
there with the hash the ledger recorded, and a present one must still match.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re

GENESIS = "0" * 64
WITHHELD = "WITHHELD.json"
# Only these may be withheld (D-034): the raw exports and per-fight predictions.
# A run's results, catalog, config, shortlist or summary must stay committed,
# or "every tested hypothesis is preserved" would have a back door.
WITHHOLDABLE = re.compile(r"^(data/dev/[^/]+\.csv|runs/[^/]+/oos_predictions\.csv)$")


def read_withheld(root: pathlib.Path) -> dict:
    p = pathlib.Path(root) / WITHHELD
    return json.loads(p.read_text())["files"] if p.exists() else {}


def withhold(root: pathlib.Path, rel: str, sha: str, meta: dict) -> None:
    """Record a file that is kept out of the repository, by hash."""
    if not WITHHOLDABLE.match(rel):
        raise ValueError(f"{rel} may not be withheld: only data exports and per-fight predictions")
    p = pathlib.Path(root) / WITHHELD
    doc = json.loads(p.read_text())
    prior = doc["files"].get(rel)
    if prior and prior["sha256"] != sha:
        raise RuntimeError(f"{rel} is already withheld with a different sha256")
    doc["files"][rel] = dict(meta, sha256=sha)
    p.write_text(json.dumps(doc, indent=1) + "\n")


def _hash(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "entry_hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def read(path: pathlib.Path) -> list[dict]:
    path = pathlib.Path(path)
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def append(path: pathlib.Path, entry: dict) -> dict:
    path = pathlib.Path(path)
    prior = read(path)
    problems = verify(prior)
    if problems:
        raise RuntimeError(f"refusing to append to a broken ledger: {problems}")
    entry = dict(entry)
    entry["seq"] = len(prior) + 1
    entry["prev_hash"] = prior[-1]["entry_hash"] if prior else GENESIS
    entry["entry_hash"] = _hash(entry)
    with path.open("a") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def verify(entries: list[dict], root: pathlib.Path | None = None,
           withheld: dict | None = None) -> list[str]:
    """Chain and content problems; empty list means intact. With `root`,
    also checks every recorded results file exists and matches its hash, or
    is absent and listed in WITHHELD.json (or `withheld`) with that hash."""
    problems = []
    if root is not None and withheld is None:
        withheld = read_withheld(root)
    prev = GENESIS
    for i, e in enumerate(entries, start=1):
        if e.get("seq") != i:
            problems.append(f"entry {i}: seq is {e.get('seq')}")
        if e.get("prev_hash") != prev:
            problems.append(f"entry {i}: prev_hash does not match entry {i - 1}")
        if _hash(e) != e.get("entry_hash"):
            problems.append(f"entry {i}: entry_hash does not match its content (edited?)")
        prev = e.get("entry_hash")
        if root is not None:
            for rel, sha in (e.get("files") or {}).items():
                p = pathlib.Path(root) / rel
                if not p.exists():
                    held = (withheld or {}).get(rel)
                    if held is None:
                        problems.append(f"entry {i}: {rel} is missing")
                    elif not WITHHOLDABLE.match(rel):
                        problems.append(f"entry {i}: {rel} is missing and may not be withheld")
                    elif held.get("sha256") != sha:
                        problems.append(f"entry {i}: {rel} is withheld with a different sha256")
                elif hashlib.sha256(p.read_bytes()).hexdigest() != sha:
                    problems.append(f"entry {i}: {rel} changed after it was recorded")
    return problems
