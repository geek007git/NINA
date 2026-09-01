"""The persistent memory store."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nina.memory import MemoryStore, NullMemoryStore, normalize_key


@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "memory.json")


def test_remember_then_recall(store: MemoryStore) -> None:
    store.remember("gym schedule", "Monday, Wednesday, Friday")
    item = store.recall("gym schedule")
    assert item is not None
    assert item.value == "Monday, Wednesday, Friday"


def test_keys_are_normalized(store: MemoryStore) -> None:
    """Speech-to-text varies its casing and spacing between utterances."""
    store.remember("  My  Gym   Schedule ", "MWF")
    assert store.recall("my gym schedule") is not None
    assert len(store) == 1

    store.remember("MY GYM SCHEDULE", "Tue/Thu")
    assert len(store) == 1
    item = store.recall("my gym schedule")
    assert item is not None
    assert item.value == "Tue/Thu"


def test_recall_falls_back_to_substring_match(store: MemoryStore) -> None:
    store.remember("gym schedule", "MWF")
    item = store.recall("what is my gym schedule")
    assert item is not None
    assert item.value == "MWF"


def test_recall_misses_return_none(store: MemoryStore) -> None:
    store.remember("gym schedule", "MWF")
    assert store.recall("favourite album") is None


def test_recall_prefers_the_closest_key(store: MemoryStore) -> None:
    store.remember("coffee", "black")
    store.remember("coffee order at work", "flat white")
    item = store.recall("coffee")
    assert item is not None
    assert item.value == "black"


def test_forget(store: MemoryStore) -> None:
    store.remember("a", "1")
    assert store.forget("A") is True
    assert store.forget("a") is False
    assert len(store) == 0


def test_persistence_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "memory.json"
    first = MemoryStore(path)
    first.remember("album", "Kind of Blue")

    second = MemoryStore(path)
    second.load()
    item = second.recall("album")
    assert item is not None
    assert item.value == "Kind of Blue"


def test_eviction_drops_the_oldest(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.json", max_items=3)
    for i in range(5):
        store.remember(f"key{i}", f"value{i}")

    assert len(store) == 3
    keys = {item.key for item in store.all_items()}
    assert keys == {"key2", "key3", "key4"}


def test_long_values_are_truncated(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.json", max_value_chars=20)
    item = store.remember("essay", "x" * 100)
    assert len(item.value) == 20
    assert item.value.endswith("…")


def test_empty_key_or_value_is_rejected(store: MemoryStore) -> None:
    with pytest.raises(ValueError, match="key cannot be empty"):
        store.remember("   ", "value")
    with pytest.raises(ValueError, match="value cannot be empty"):
        store.remember("key", "   ")


def test_all_items_is_newest_first(store: MemoryStore) -> None:
    store.remember("first", "1")
    store.remember("second", "2")
    assert [i.key for i in store.all_items()] == ["second", "first"]


def test_clear(store: MemoryStore) -> None:
    store.remember("a", "1")
    store.clear()
    assert len(store) == 0


def test_corrupt_file_is_quarantined_not_fatal(tmp_path: Path) -> None:
    """A damaged store must never stop the agent from starting."""
    path = tmp_path / "memory.json"
    path.write_text("{ this is not json", encoding="utf-8")

    store = MemoryStore(path)
    store.load()

    assert len(store) == 0
    assert path.with_suffix(".json.corrupt").exists()
    # Still usable afterwards.
    store.remember("a", "1")
    assert store.recall("a") is not None


def test_missing_file_starts_empty(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "nope" / "memory.json")
    store.load()
    assert len(store) == 0


def test_saved_file_is_valid_readable_json(tmp_path: Path) -> None:
    path = tmp_path / "memory.json"
    store = MemoryStore(path)
    store.remember("album", "Kind of Blue")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["items"][0]["key"] == "album"
    assert payload["items"][0]["value"] == "Kind of Blue"


def test_no_temp_files_are_left_behind(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.json")
    store.remember("a", "1")
    store.remember("b", "2")
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".memory-")]
    assert leftovers == []


def test_null_store_accepts_writes_and_forgets_them() -> None:
    store = NullMemoryStore()
    store.remember("a", "1")
    # It stays in process memory but is never persisted, so callers need no
    # None-checks when memory is disabled.
    assert store.recall("a") is not None
    assert not store.path.exists()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("  A  B ", "a b"), ("Gym\tSchedule", "gym schedule"), ("", "")],
)
def test_normalize_key(raw: str, expected: str) -> None:
    assert normalize_key(raw) == expected
