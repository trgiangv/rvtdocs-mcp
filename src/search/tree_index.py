"""Local search index built from rvtdocs tree data.

Downloads revit_{year}.json once per year into %APPDATA%/rvtdocs-mcp/,
flattens into a searchable in-memory index. Supports keyword search with
scoring/ranking, ~200ms load, ~7ms/query.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from ..config import BASE_URL, SUPPORTED_YEARS

_TREE_URL_TEMPLATE = BASE_URL + "/static/json_trees/sidebar_{year}.json"
_LOCAL_FILENAME = "revit_{year}.json"


def _get_cache_dir() -> Path:
    """Get platform-appropriate cache directory for downloaded tree data."""
    import os
    import platform
    if platform.system() == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    cache_dir = base / "rvtdocs-mcp"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


_INDEX_DIR = _get_cache_dir()

_TYPE_PATTERNS: dict[str, str] = {
    "Class": "class",
    "Properties": "member_list",
    "Methods": "member_list",
    "Constructors": "member_list",
    "Events": "member_list",
    "Fields": "member_list",
    "Property": "property",
    "Method": "method",
    "Constructor": "constructor",
    "Event": "event",
    "Field": "field",
    "Enumeration": "enum",
    "Interface": "interface",
    "Namespace": "namespace",
    "Structure": "struct",
    "Delegate": "delegate",
    "Operator": "operator",
}

_CAMEL_SPLIT = re.compile(r"[A-Z][a-z]+|[A-Z]+(?=[A-Z])|[a-z]+|\d+")


def _extract_type(title: str, fqn: str) -> str:
    for pattern, api_type in _TYPE_PATTERNS.items():
        if title.endswith(f" {pattern}"):
            return api_type
    if title == fqn and " " not in title and "(" not in title:
        return "namespace"
    return "other"


def _extract_short_name(fqn: str) -> str:
    return fqn.rsplit(".", 1)[-1] if fqn else ""


def _extract_class_name(fqn: str, api_type: str) -> str:
    parts = fqn.split(".")
    if api_type in ("method", "property", "constructor", "event", "field", "member_list"):
        return parts[-2] if len(parts) >= 2 else ""
    if api_type == "class":
        return parts[-1] if parts else ""
    return ""


def _extract_namespace(fqn: str, api_type: str) -> str:
    parts = fqn.split(".")
    if api_type in ("method", "property", "constructor", "event", "field", "member_list"):
        return ".".join(parts[:-2]) if len(parts) >= 3 else ""
    if api_type in ("class", "enum", "interface", "struct", "delegate"):
        return ".".join(parts[:-1]) if len(parts) >= 2 else ""
    return fqn


def _tokenize(text: str) -> set[str]:
    """Split into searchable tokens (camelCase aware + lowercase)."""
    tokens: set[str] = set()
    for part in text.replace(".", " ").replace("(", " ").replace(")", " ").replace(",", " ").split():
        tokens.add(part.lower())
        for camel_token in _CAMEL_SPLIT.findall(part):
            tokens.add(camel_token.lower())
    return tokens


@dataclass(frozen=True, slots=True)
class SearchResult:
    """A single search result from the local tree index."""
    title: str
    fqn: str
    api_type: str
    namespace: str
    class_name: str
    short_name: str
    page_id: str
    url: str
    score: float = 0.0


@dataclass
class _IndexEntry:
    """Internal indexed entry with pre-computed tokens."""
    title: str
    fqn: str
    fqn_lower: str
    api_type: str
    namespace: str
    class_name: str
    class_name_lower: str
    short_name: str
    short_name_lower: str
    page_id: str
    tokens: set[str] = field(default_factory=set)


_TYPE_MULTIPLIERS = {
    "member_list": 0.3,
    "namespace": 1.5,
    "class": 1.2,
    "enum": 1.15,
    "interface": 1.15,
    "method": 1.1,
    "struct": 1.1,
}


def _type_multiplier(api_type: str) -> float:
    return _TYPE_MULTIPLIERS.get(api_type, 1.0)


class TreeIndex:
    """Searchable index built from sidebar tree JSON."""

    def __init__(self) -> None:
        self._entries_by_year: dict[str, list[_IndexEntry]] = {}
        self._load_times: dict[str, float] = {}

    def ensure_loaded(self, year: str) -> None:
        if year in self._entries_by_year:
            return
        tree_path = _INDEX_DIR / _LOCAL_FILENAME.format(year=year)
        if not tree_path.exists():
            self._download_tree(year, tree_path)
        self._load_from_file(year, tree_path)

    def _download_tree(self, year: str, target: Path) -> None:
        url = _TREE_URL_TEMPLATE.format(year=year)
        target.parent.mkdir(parents=True, exist_ok=True)
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        target.write_bytes(resp.content)

    def _load_from_file(self, year: str, path: Path) -> None:
        start = time.perf_counter()
        raw = json.loads(path.read_bytes())
        entries: list[_IndexEntry] = []
        self._flatten(raw, entries)
        self._entries_by_year[year] = entries
        self._load_times[year] = time.perf_counter() - start

    def _flatten(self, nodes: list[dict], entries: list[_IndexEntry]) -> None:
        for node in nodes:
            title = node.get("title", "")
            fqn = node.get("fqn", "")
            page_id = node.get("url", "")

            if fqn:
                api_type = _extract_type(title, fqn)
                class_name = _extract_class_name(fqn, api_type)
                namespace = _extract_namespace(fqn, api_type)
                short_name = _extract_short_name(fqn)
                tokens = _tokenize(fqn) | _tokenize(title)
                entries.append(_IndexEntry(
                    title=title,
                    fqn=fqn,
                    fqn_lower=fqn.lower(),
                    api_type=api_type,
                    namespace=namespace,
                    class_name=class_name,
                    class_name_lower=class_name.lower(),
                    short_name=short_name,
                    short_name_lower=short_name.lower(),
                    page_id=page_id,
                    tokens=tokens,
                ))

            children = node.get("children")
            if children:
                self._flatten(children, entries)

    def search(
        self,
        query: str,
        year: str,
        *,
        types: set[str] | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Search the index with keyword matching and BM25-like scoring.

        Supports:
        - Multi-word queries: "create wall curve"
        - Dotted queries: "Wall.Create"
        - Single keywords: "Rebar"
        - Type filtering: types={"class", "method"}
        """
        self.ensure_loaded(year)
        entries = self._entries_by_year.get(year, [])
        if not entries:
            return []

        query_tokens = _tokenize(query)
        query_lower = query.strip().lower()
        query_parts = query_lower.replace(".", " ").split()

        if not query_tokens:
            return []

        scored: list[tuple[float, _IndexEntry]] = []

        for entry in entries:
            if types and entry.api_type not in types:
                continue

            score = self._score_entry(entry, query_tokens, query_lower, query_parts)
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: -x[0])
        base_url_year = f"{BASE_URL}/{year}"

        return [
            SearchResult(
                title=entry.title,
                fqn=entry.fqn,
                api_type=entry.api_type,
                namespace=entry.namespace,
                class_name=entry.class_name,
                short_name=entry.short_name,
                page_id=entry.page_id,
                url=f"{base_url_year}/{entry.fqn}",
                score=round(score, 3),
            )
            for score, entry in scored[:limit]
        ]

    def _score_entry(
        self,
        entry: _IndexEntry,
        query_tokens: set[str],
        query_lower: str,
        query_parts: list[str],
    ) -> float:
        """Score an entry against query. Higher = better match."""
        if query_lower == entry.fqn_lower:
            return 100.0

        matched_tokens = query_tokens & entry.tokens
        if not matched_tokens:
            return 0.0

        score = self._base_score(entry, query_lower, query_parts, matched_tokens, query_tokens)
        return score * _type_multiplier(entry.api_type)

    def _base_score(
        self,
        entry: _IndexEntry,
        query_lower: str,
        query_parts: list[str],
        matched_tokens: set[str],
        query_tokens: set[str],
    ) -> float:
        score = 0.0
        score += 50.0 * (query_lower == entry.short_name_lower)
        score += 45.0 * (query_lower == entry.class_name_lower)
        score += 40.0 * ("." in query_lower and query_lower in entry.fqn_lower)

        token_ratio = len(matched_tokens) / len(query_tokens)
        score += token_ratio * 20.0

        if all(part in entry.fqn_lower for part in query_parts):
            score += 15.0

        if any(entry.short_name_lower.startswith(t) for t in query_tokens):
            score += 8.0
        if any(entry.class_name_lower.startswith(t) for t in query_tokens):
            score += 5.0

        depth = entry.fqn.count(".")
        if depth <= 3:
            score += 3.0
        elif depth >= 5:
            score -= 2.0

        return score

    def scan(
        self,
        target: str,
        year: str,
        *,
        types: set[str] | None = None,
    ) -> list[SearchResult]:
        """List direct children of a namespace or class members."""
        self.ensure_loaded(year)
        entries = self._entries_by_year.get(year, [])
        target_lower = target.lower()
        base_url = f"{BASE_URL}/{year}"

        results: list[SearchResult] = []
        for entry in entries:
            if not self._is_child_of(entry, target, target_lower):
                continue
            if types and entry.api_type not in types:
                continue
            results.append(SearchResult(
                title=entry.title,
                fqn=entry.fqn,
                api_type=entry.api_type,
                namespace=entry.namespace,
                class_name=entry.class_name,
                short_name=entry.short_name,
                page_id=entry.page_id,
                url=f"{base_url}/{entry.fqn}",
            ))

        return results

    @staticmethod
    def _is_child_of(entry: _IndexEntry, target: str, target_lower: str) -> bool:
        if entry.namespace.lower() == target_lower:
            return True
        if entry.fqn_lower.startswith(target_lower + "."):
            remaining = entry.fqn[len(target) + 1:]
            if "." not in remaining:
                return True
        return entry.class_name_lower == target_lower

    def get_stats(self, year: str) -> dict:
        self.ensure_loaded(year)
        entries = self._entries_by_year.get(year, [])
        type_counts: dict[str, int] = {}
        for e in entries:
            type_counts[e.api_type] = type_counts.get(e.api_type, 0) + 1
        return {
            "year": year,
            "totalEntries": len(entries),
            "loadTimeMs": round(self._load_times.get(year, 0) * 1000, 1),
            "typeBreakdown": type_counts,
        }


_global_index: TreeIndex | None = None


def get_tree_index() -> TreeIndex:
    """Get or create the global tree index singleton."""
    global _global_index
    if _global_index is None:
        _global_index = TreeIndex()
    return _global_index
