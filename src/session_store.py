from __future__ import annotations

import threading


class SessionStore:
    """In-memory key-value store for cross-tool session data.

    Allows tools and agents to share state within a server session.
    Data is lost on server restart (by design — ephemeral session data).
    """

    def __init__(self, max_entries: int = 100) -> None:
        self._data: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries

    def get(self, key: str) -> dict | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            return dict(entry)

    def set(self, key: str, value: dict) -> None:
        with self._lock:
            self._data[key] = dict(value)
            if len(self._data) > self._max_entries:
                self._evict_oldest()

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False

    def list_keys(self) -> list[str]:
        with self._lock:
            return list(self._data.keys())

    def clear(self) -> int:
        with self._lock:
            count = len(self._data)
            self._data.clear()
            return count

    def _evict_oldest(self) -> None:
        if not self._data:
            return
        oldest_key = min(
            self._data,
            key=lambda item: float(self._data[item].get("set_at", 0)),
        )
        del self._data[oldest_key]
