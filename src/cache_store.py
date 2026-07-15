"""Simple in-memory LRU cache for fetched pages."""
from __future__ import annotations

from collections import OrderedDict

from .config import MAX_CACHE_ENTRIES


class SharedCache:
    """In-memory LRU cache for fetched HTML pages."""

    def __init__(self, max_entries: int = MAX_CACHE_ENTRIES) -> None:
        self._store: OrderedDict[str, dict] = OrderedDict()
        self._max = max_entries

    def get(self, url: str) -> dict | None:
        entry = self._store.get(url)
        if entry is not None:
            self._store.move_to_end(url)
        return entry

    def put(self, url: str, data: dict) -> None:
        self._store[url] = data
        self._store.move_to_end(url)
        while len(self._store) > self._max:
            self._store.popitem(last=False)


_global_cache: SharedCache | None = None


def get_shared_cache() -> SharedCache:
    global _global_cache
    if _global_cache is None:
        _global_cache = SharedCache()
    return _global_cache
