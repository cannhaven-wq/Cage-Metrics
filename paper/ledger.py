"""Append-only paper ledger: one JSON object per line, hash-chained, never rewritten.

Event types (all carry event_id, ts, type, card_id, strategy_version, prev_hash, hash):

    lock          the card's lock instant, the config hash, the model version,
                  the fights covered and their corners at lock
    selection     one bet: strategy, fight, side, the exact offer, stake, EVs
    pass          a priced fight considered and declined, with the reason
    abstain       a fight that could not be evaluated, with the reason
    forecast      the model's p_a (or null = abstention) per fight, what would be
                  written to win_model_locks
    cancel        a selection voided before settlement (corner change, card change)
    settlement    the outcome applied to one selection
    look          a metrics computation, recorded before it is discussed

Rules the store enforces:
- A card+strategy_version is locked once. A second lock for the same key is
  refused, so a rerun can never add exposure (DuplicateRun).
- Nothing is updated or deleted; corrections are new events that reference
  the original by event_id.
- Each line's hash covers the previous hash, so an edited or dropped line
  breaks the chain (verify()).

The default location is paper/private/ledger.jsonl, which is git-ignored:
row-level selections never enter the public repository. A database table
with the same shape is prepared in paper/sql/paper_ledger_migration.sql and
is NOT applied; see README.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import uuid
from datetime import datetime, timezone
from typing import Iterable, Optional


class DuplicateRun(RuntimeError):
    pass


class LedgerCorrupt(RuntimeError):
    pass


def _canon(d: dict) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), default=str)


class Ledger:
    def __init__(self, path: pathlib.Path):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._events: list[dict] = []
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    self._events.append(json.loads(line))
        self.verify()

    # ------------------------------------------------------------------ chain
    def verify(self) -> None:
        prev = ""
        for i, e in enumerate(self._events):
            body = {k: v for k, v in e.items() if k != "hash"}
            if e.get("prev_hash") != prev:
                raise LedgerCorrupt(f"line {i + 1}: prev_hash does not match the line before it")
            h = hashlib.sha256(_canon(body).encode()).hexdigest()
            if e.get("hash") != h:
                raise LedgerCorrupt(f"line {i + 1}: hash does not match its content")
            prev = h

    @property
    def last_hash(self) -> str:
        return self._events[-1]["hash"] if self._events else ""

    def events(self, type: Optional[str] = None, **match) -> list[dict]:
        out = []
        for e in self._events:
            if type and e["type"] != type:
                continue
            if all(e.get(k) == v for k, v in match.items()):
                out.append(e)
        return out

    # ------------------------------------------------------------------ write
    def append(self, type: str, *, card_id, strategy_version: str, ts: Optional[str] = None, **payload) -> dict:
        e = {"event_id": str(uuid.uuid4()), "ts": ts or datetime.now(timezone.utc).isoformat(),
             "type": type, "card_id": card_id, "strategy_version": strategy_version,
             "prev_hash": self.last_hash, **payload}
        e["hash"] = hashlib.sha256(_canon(e).encode()).hexdigest()
        with self.path.open("a") as fh:
            fh.write(_canon(e) + "\n")
        self._events.append(e)
        return e

    def lock_for(self, card_id, strategy_version: str) -> Optional[dict]:
        hits = self.events("lock", card_id=card_id, strategy_version=strategy_version)
        return hits[0] if hits else None

    def record_lock(self, *, card_id, strategy_version: str, **payload) -> dict:
        if self.lock_for(card_id, strategy_version):
            raise DuplicateRun(f"card {card_id} is already locked under {strategy_version}; a rerun adds nothing")
        return self.append("lock", card_id=card_id, strategy_version=strategy_version, **payload)

    # ------------------------------------------------------------------ reads used by settlement
    def open_selections(self) -> list[dict]:
        settled = {e["selection_id"] for e in self.events("settlement")} | {e["selection_id"] for e in self.events("cancel")}
        return [e for e in self.events("selection") if e["event_id"] not in settled]

    def selection_by_id(self, selection_id: str) -> Optional[dict]:
        hits = [e for e in self.events("selection") if e["event_id"] == selection_id]
        return hits[0] if hits else None
