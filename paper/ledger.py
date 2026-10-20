"""Append-only paper ledger: one JSON object per line, hash-chained, never rewritten.

Event types (all carry event_id, ts, type, card_id, strategy_version, prev_hash, hash):

    lock          the card's lock instant, the config hash, the model version,
                  the fights covered and their corners at lock
    forecast      the model's p_a (or null = abstention) per fight, what would be
                  written to win_model_locks
    selection     one bet: strategy, fight, side, the exact offer, stake, EVs
    pass          a priced fight considered and declined, with the reason
    abstain       a fight that could not be evaluated, with the reason
    card_commit   closes the card's batch: the ids and count of every event above
    card_abort    marks an earlier lock whose batch never reached card_commit
                  (a crash); its events are ignored, never removed
    cancel        a selection voided before settlement (corner change, card change)
    settlement    the outcome applied to one selection
    look          a metrics computation, recorded before it is discussed

How a card is recorded (record_card):
- an exclusive advisory lock on <ledger>.lock serialises writers on this host;
- the file is RE-READ under that lock, so two processes that both saw "no lock
  for this card" cannot both record it (DuplicateRun for the loser);
- an incomplete batch found on disk (lock without card_commit: a crash) is
  closed with a card_abort marker, then the card is recorded again in full;
- every event of the batch, lock through card_commit, is hash-chained in
  memory and written with ONE write() followed by fsync(), so a crash leaves
  either the whole batch or an incomplete one that the next run recovers.

Nothing is ever updated or deleted. A truncated final line (a crash mid-write)
is kept in place and skipped; it is tolerated only if the chain is intact
across it, so an edited or removed line still fails verify().

The default location is paper/private/ledger.jsonl, which is git-ignored.
A database table with a unique (card_id, strategy_version) constraint would
give the same guarantee across hosts; the file gives it on one host.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import pathlib
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional


class DuplicateRun(RuntimeError):
    pass


class LedgerCorrupt(RuntimeError):
    pass


def _canon(d: dict) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), default=str)


def _hash_of(event_without_hash: dict) -> str:
    return hashlib.sha256(_canon(event_without_hash).encode()).hexdigest()


class Ledger:
    def __init__(self, path: pathlib.Path):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._reload()

    # ------------------------------------------------------------------ parse + verify
    def _reload(self) -> None:
        self._all: list[dict] = []          # every parsed event, aborted batches included
        self.skipped_lines: list[int] = []  # 1-based line numbers that were not JSON
        self.file_ends_with_newline = True
        if self.path.exists():
            raw = self.path.read_bytes()
            self.file_ends_with_newline = (not raw) or raw.endswith(b"\n")
            for i, line in enumerate(raw.decode("utf-8", errors="replace").split("\n"), start=1):
                if not line.strip():
                    continue
                try:
                    self._all.append(json.loads(line))
                except ValueError:
                    self.skipped_lines.append(i)
        self.verify()
        # batches: a lock opens one, card_commit closes it, card_abort retires an open one
        self.aborted_lock_ids = {e["aborted_lock_event_id"] for e in self._all if e["type"] == "card_abort"}
        committed = {e["lock_event_id"] for e in self._all if e["type"] == "card_commit"}
        self._batch_of: dict[str, Optional[str]] = {}
        open_lock = None
        for e in self._all:
            if e["type"] == "lock":
                open_lock = e["event_id"]
            self._batch_of[e["event_id"]] = open_lock if e["type"] not in ("card_abort",) else None
            if e["type"] == "card_commit" and e.get("lock_event_id") == open_lock:
                open_lock = None
            if e["type"] == "card_abort" and e.get("aborted_lock_event_id") == open_lock:
                open_lock = None
        self.incomplete_lock_id = open_lock if (open_lock and open_lock not in committed) else None
        hidden = set(self.aborted_lock_ids) | ({self.incomplete_lock_id} if self.incomplete_lock_id else set())
        # an aborted batch is ignored for good; an incomplete one until recovery retires it
        self._events = [e for e in self._all if self._batch_of.get(e["event_id"]) not in hidden]

    def verify(self) -> None:
        prev = ""
        for i, e in enumerate(self._all):
            body = {k: v for k, v in e.items() if k != "hash"}
            if e.get("prev_hash") != prev:
                raise LedgerCorrupt(f"event {i + 1}: prev_hash does not match the event before it")
            if e.get("hash") != _hash_of(body):
                raise LedgerCorrupt(f"event {i + 1}: hash does not match its content")
            prev = e["hash"]

    @property
    def last_hash(self) -> str:
        return self._all[-1]["hash"] if self._all else ""

    def events(self, type: Optional[str] = None, **match) -> list[dict]:
        """Events outside aborted batches."""
        out = []
        for e in self._events:
            if type and e["type"] != type:
                continue
            if all(e.get(k) == v for k, v in match.items()):
                out.append(e)
        return out

    def lock_for(self, card_id, strategy_version: str) -> Optional[dict]:
        """The COMMITTED lock for a card, or None."""
        committed = {e["lock_event_id"] for e in self.events("card_commit")}
        hits = [e for e in self.events("lock", card_id=card_id, strategy_version=strategy_version) if e["event_id"] in committed]
        return hits[0] if hits else None

    # ------------------------------------------------------------------ writing
    @contextmanager
    def _exclusive(self):
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _build(self, prev_hash: str, type: str, *, card_id, strategy_version: str, ts: Optional[str], payload: dict) -> dict:
        e = {"event_id": str(uuid.uuid4()), "ts": ts or datetime.now(timezone.utc).isoformat(),
             "type": type, "card_id": card_id, "strategy_version": strategy_version, "prev_hash": prev_hash, **payload}
        e["hash"] = _hash_of(e)
        return e

    def _write_batch(self, events: list[dict]) -> None:
        data = "".join(_canon(e) + "\n" for e in events).encode()
        if not self.file_ends_with_newline:
            data = b"\n" + data            # a truncated tail stays on its own line
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        self._reload()

    def append(self, type: str, *, card_id, strategy_version: str, ts: Optional[str] = None, **payload) -> dict:
        """One event, written under the writer lock after a re-read."""
        with self._exclusive():
            self._reload()
            e = self._build(self.last_hash, type, card_id=card_id, strategy_version=strategy_version, ts=ts, payload=payload)
            self._write_batch([e])
            return e

    def record_card(self, *, card_id, strategy_version: str, ts: Optional[str] = None,
                    lock: dict, events: list[tuple[str, dict]]) -> dict:
        """Record a whole card atomically: lock, the given (type, payload) events, card_commit.

        Refuses with DuplicateRun if a committed lock for the card exists, judged
        after re-reading the file under the writer lock. An incomplete batch on
        disk is retired with card_abort first, in the same write.
        """
        with self._exclusive():
            self._reload()
            if self.lock_for(card_id, strategy_version):
                raise DuplicateRun(f"card {card_id} is already locked under {strategy_version}; a rerun adds nothing")
            batch: list[dict] = []
            prev = self.last_hash
            if self.incomplete_lock_id:
                bad = next(e for e in self._all if e["event_id"] == self.incomplete_lock_id)
                batch.append(self._build(prev, "card_abort", card_id=bad["card_id"], strategy_version=bad["strategy_version"], ts=ts,
                                         payload={"aborted_lock_event_id": bad["event_id"],
                                                  "reason": "batch never reached card_commit; retired on recovery, its events are ignored"}))
                prev = batch[-1]["hash"]
            lock_event = self._build(prev, "lock", card_id=card_id, strategy_version=strategy_version, ts=ts, payload=lock)
            batch.append(lock_event); prev = lock_event["hash"]
            for typ, payload in events:
                e = self._build(prev, typ, card_id=card_id, strategy_version=strategy_version, ts=ts,
                                payload={"lock_event_id": lock_event["event_id"], **payload})
                batch.append(e); prev = e["hash"]
            commit = self._build(prev, "card_commit", card_id=card_id, strategy_version=strategy_version, ts=ts,
                                 payload={"lock_event_id": lock_event["event_id"], "event_ids": [e["event_id"] for e in batch[1:]],
                                          "n_events": len(batch) - 1})
            batch.append(commit)
            self._write_batch(batch)
            return lock_event

    # ------------------------------------------------------------------ reads used by settlement
    def open_selections(self) -> list[dict]:
        settled = {e["selection_id"] for e in self.events("settlement")} | {e["selection_id"] for e in self.events("cancel")}
        return [e for e in self.events("selection") if e["event_id"] not in settled]

    def selection_by_id(self, selection_id: str) -> Optional[dict]:
        hits = [e for e in self.events("selection") if e["event_id"] == selection_id]
        return hits[0] if hits else None
