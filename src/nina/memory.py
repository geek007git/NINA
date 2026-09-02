"""Persistent key/value memory that survives across sessions.

A voice assistant that forgets everything the moment the room closes is a demo,
not an assistant. This is deliberately a small, dependency-free JSON store
rather than a vector database: the data is a few hundred short facts a person
explicitly asked to be remembered, and a file that a human can open and edit is
worth more here than embedding search.

Durability notes:

* Writes go to a temp file in the same directory and are then atomically
  replaced, so a crash mid-write cannot truncate an existing store.
* The store is capped; the oldest entries are evicted first.
* Corrupt files are quarantined rather than deleted, then the store starts
  empty, because losing the process is worse than losing the file.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import MemoryError_
from .logging_setup import get_logger

logger = get_logger("memory")

_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class MemoryItem:
    """One remembered fact."""

    key: str
    value: str
    updated_at: float

    def as_dict(self) -> dict[str, Any]:
        return {"key": self.key, "value": self.value, "updated_at": self.updated_at}


def normalize_key(key: str) -> str:
    """Normalize a key so 'My Gym Days' and 'my gym days' are the same memory.

    Speech-to-text output varies in casing and spacing between utterances, so
    without this the same spoken key would create duplicate entries.
    """
    return " ".join(key.strip().lower().split())


class MemoryStore:
    """A small, thread-safe, atomically-persisted key/value store."""

    def __init__(
        self,
        path: Path | str,
        *,
        max_items: int = 200,
        max_value_chars: int = 500,
    ) -> None:
        self.path = Path(path)
        self.max_items = max_items
        self.max_value_chars = max_value_chars
        self._lock = threading.RLock()
        self._items: dict[str, MemoryItem] = {}
        self._loaded = False

    # -- persistence -----------------------------------------------------

    def load(self) -> None:
        """Read the store from disk. Safe to call repeatedly."""
        with self._lock:
            self._loaded = True
            if not self.path.exists():
                self._items = {}
                return
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                items = raw["items"] if isinstance(raw, dict) else raw
                parsed: dict[str, MemoryItem] = {}
                for entry in items:
                    key = normalize_key(str(entry["key"]))
                    if not key:
                        continue
                    parsed[key] = MemoryItem(
                        key=key,
                        value=str(entry["value"]),
                        updated_at=float(entry.get("updated_at", 0.0)),
                    )
                self._items = parsed
            except (OSError, ValueError, KeyError, TypeError) as exc:
                # A damaged store must not stop the agent from starting.
                quarantine = self.path.with_suffix(self.path.suffix + ".corrupt")
                logger.warning(
                    "memory store unreadable, quarantining and starting empty",
                    extra={
                        "path": str(self.path),
                        "quarantine": str(quarantine),
                        "error": str(exc),
                    },
                )
                with contextlib.suppress(OSError):
                    self.path.replace(quarantine)
                self._items = {}

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def save(self) -> None:
        """Persist the store atomically."""
        with self._lock:
            payload = {
                "version": _SCHEMA_VERSION,
                "items": [item.as_dict() for item in self._sorted_items()],
            }
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                # Same directory as the target, so os.replace stays atomic
                # (a cross-filesystem rename is not).
                fd, tmp_name = tempfile.mkstemp(
                    dir=str(self.path.parent), prefix=".memory-", suffix=".tmp"
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        json.dump(payload, handle, ensure_ascii=False, indent=2)
                        handle.flush()
                        os.fsync(handle.fileno())
                    Path(tmp_name).replace(self.path)
                except BaseException:
                    Path(tmp_name).unlink(missing_ok=True)
                    raise
            except OSError as exc:
                raise MemoryError_(f"could not write memory store at {self.path}: {exc}") from exc

    # -- operations ------------------------------------------------------

    def remember(self, key: str, value: str) -> MemoryItem:
        """Store or overwrite a fact, returning the stored item.

        Raises:
            ValueError: if the key or value is empty.
        """
        norm = normalize_key(key)
        value = value.strip()
        if not norm:
            raise ValueError("memory key cannot be empty")
        if not value:
            raise ValueError("memory value cannot be empty")
        if len(value) > self.max_value_chars:
            value = value[: self.max_value_chars - 1].rstrip() + "…"

        with self._lock:
            self._ensure_loaded()
            item = MemoryItem(key=norm, value=value, updated_at=time.time())
            self._items[norm] = item
            self._evict()
            self.save()
            return item

    def recall(self, key: str) -> MemoryItem | None:
        """Look up a fact by key, falling back to a substring match.

        The fallback matters because a spoken key is rarely repeated word for
        word: "my gym schedule" should still find "gym schedule".
        """
        norm = normalize_key(key)
        with self._lock:
            self._ensure_loaded()
            if norm in self._items:
                return self._items[norm]
            candidates = [
                item
                for stored, item in self._items.items()
                if norm and (norm in stored or stored in norm)
            ]
            if not candidates:
                return None
            # Prefer the closest length match, then the most recently updated.
            candidates.sort(key=lambda i: (abs(len(i.key) - len(norm)), -i.updated_at))
            return candidates[0]

    def forget(self, key: str) -> bool:
        """Delete a fact. Returns ``True`` if something was removed."""
        norm = normalize_key(key)
        with self._lock:
            self._ensure_loaded()
            if norm not in self._items:
                return False
            del self._items[norm]
            self.save()
            return True

    def all_items(self) -> list[MemoryItem]:
        """Every stored fact, most recently updated first."""
        with self._lock:
            self._ensure_loaded()
            return self._sorted_items()

    def clear(self) -> None:
        with self._lock:
            self._ensure_loaded()
            self._items = {}
            self.save()

    def __len__(self) -> int:
        with self._lock:
            self._ensure_loaded()
            return len(self._items)

    # -- internals -------------------------------------------------------

    def _sorted_items(self) -> list[MemoryItem]:
        return sorted(self._items.values(), key=lambda i: i.updated_at, reverse=True)

    def _evict(self) -> None:
        """Drop the oldest entries once the cap is exceeded."""
        if len(self._items) <= self.max_items:
            return
        for item in self._sorted_items()[self.max_items :]:
            self._items.pop(item.key, None)


class NullMemoryStore(MemoryStore):
    """A store that accepts writes and drops them.

    Used when memory is disabled, so calling code never needs a ``None`` check.
    """

    def __init__(self) -> None:
        super().__init__(Path("memory-disabled.json"))
        self._loaded = True

    def load(self) -> None:
        self._loaded = True
        self._items = {}

    def save(self) -> None:
        return None
