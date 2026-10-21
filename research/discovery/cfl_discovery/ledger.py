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
"""
from __future__ import annotations

import hashlib
import json
import pathlib

GENESIS = "0" * 64


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


def verify(entries: list[dict], root: pathlib.Path | None = None) -> list[str]:
    """Chain and content problems; empty list means intact. With `root`,
    also checks every recorded results file exists and matches its hash."""
    problems = []
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
                    problems.append(f"entry {i}: {rel} is missing")
                elif hashlib.sha256(p.read_bytes()).hexdigest() != sha:
                    problems.append(f"entry {i}: {rel} changed after it was recorded")
    return problems
