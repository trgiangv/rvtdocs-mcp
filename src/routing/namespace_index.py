from __future__ import annotations

import json
import threading
from pathlib import Path

from ..config import DEFAULT_YEAR

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_SUPPORTED_YEARS = ("2022", "2023", "2024", "2025", "2026", "2027")
_EMPTY_INDEX: dict[str, str] = {}


class NamespaceIndex:
    """Lazy-loaded namespace → class mapping from pre-built index files."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or _DATA_DIR
        self._indices: dict[str, dict[str, str]] = {}
        self._missing_years: set[str] = set()
        self._available_years: list[str] | None = None
        self._lock = threading.Lock()

    def lookup(self, class_name: str, year: str = DEFAULT_YEAR) -> str | None:
        """Return namespace tail (e.g. 'DB', 'UI') for a class name, or None."""
        index = self._load_year(year)
        return index.get(class_name)

    def get_index_for_year(self, year: str) -> dict[str, str]:
        """Return the loaded class-name → namespace-tail index for a Revit year."""
        return self._load_year(year)

    def _available_index_years(self) -> list[str]:
        if self._available_years is None:
            years: list[str] = []
            for year in _SUPPORTED_YEARS:
                if self._index_path(year).is_file():
                    years.append(year)
            self._available_years = years
        return self._available_years

    def _index_path(self, year: str) -> Path:
        return self._data_dir / f"namespace_index_{year}.json"

    def _resolve_year(self, year: str) -> str | None:
        available = self._available_index_years()
        if not available:
            return None
        if year in available:
            return year
        target = int(year)
        return min(available, key=lambda candidate: abs(int(candidate) - target))

    def _load_year(self, year: str) -> dict[str, str]:
        resolved_year = self._resolve_year(year)
        if resolved_year is None:
            return _EMPTY_INDEX

        cached = self._indices.get(resolved_year)
        if cached is not None:
            return cached

        if resolved_year in self._missing_years:
            return _EMPTY_INDEX

        with self._lock:
            cached = self._indices.get(resolved_year)
            if cached is not None:
                return cached

            if resolved_year in self._missing_years:
                return _EMPTY_INDEX

            path = self._index_path(resolved_year)
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._missing_years.add(resolved_year)
                return _EMPTY_INDEX

            if not isinstance(raw, dict):
                self._missing_years.add(resolved_year)
                return _EMPTY_INDEX

            index = {
                str(class_name): str(namespace_tail)
                for class_name, namespace_tail in raw.items()
            }
            self._indices[resolved_year] = index
            return index


_namespace_index: NamespaceIndex | None = None
_namespace_index_lock = threading.Lock()


def get_namespace_index() -> NamespaceIndex:
    """Return the module-level namespace index singleton."""
    global _namespace_index
    if _namespace_index is not None:
        return _namespace_index

    with _namespace_index_lock:
        if _namespace_index is None:
            _namespace_index = NamespaceIndex()
        return _namespace_index
