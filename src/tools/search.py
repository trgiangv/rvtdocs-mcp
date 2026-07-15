"""rvtdocs_search tool: keyword search over Revit API documentation.

Accepts natural queries like "create wall from curve", "energy analysis",
"rebar placement" and returns ranked list of matching API entries from
the local sidebar tree index.
"""
from __future__ import annotations

from ..config import DEFAULT_YEAR, SUPPORTED_YEARS
from ..search.tree_index import SearchResult, get_tree_index

_TYPE_MAP: dict[str, str] = {
    "class": "class",
    "method": "method",
    "property": "property",
    "enum": "enum",
    "interface": "interface",
    "constructor": "constructor",
    "event": "event",
    "struct": "struct",
    "delegate": "delegate",
    "namespace": "namespace",
}


def _parse_types(types_str: str | None) -> set[str] | None:
    if not types_str:
        return None
    parsed: set[str] = set()
    for t in types_str.lower().replace(",", " ").split():
        mapped = _TYPE_MAP.get(t.strip())
        if mapped:
            parsed.add(mapped)
    return parsed or None


def _result_to_dict(r: SearchResult) -> dict:
    """Compact result dict — fqn is the primary identifier, url for fetch."""
    return {
        "fqn": r.fqn,
        "type": r.api_type,
        "url": r.url,
        "score": r.score,
    }


def rvtdocs_search(
    query: str,
    year: str = DEFAULT_YEAR,
    types: str = "",
    limit: int = 20,
) -> dict:
    """Search Revit API documentation locally using keyword matching.

    Accepts natural queries like "create wall from curve", "energy analysis",
    "Wall.Create", "Rebar", or any keywords related to Revit API.

    Returns a ranked list of matching API entries (classes, methods, properties,
    enums, etc.) with FQN, type, namespace, and direct URL.

    Use this tool FIRST to discover relevant APIs, then use rvtdocs_fetch
    with a specific URL to get detailed documentation.

    Args:
        query: Search keywords (e.g. "create wall curve", "EnergyAnalysis", "Rebar")
        year: Revit API version year (2022-2027)
        types: Filter by type (comma-separated): class, method, property, enum, interface
        limit: Maximum number of results (default 20)
    """
    query = (query or "").strip()
    if not query:
        return {"results": [], "total": 0, "error": "Empty query"}

    year = year.strip() if year else DEFAULT_YEAR
    if year not in SUPPORTED_YEARS:
        year = DEFAULT_YEAR

    type_filter = _parse_types(types)
    limit = max(1, min(limit, 50))

    index = get_tree_index()
    try:
        results = index.search(query, year, types=type_filter, limit=limit)
    except Exception as e:
        return {"results": [], "total": 0, "error": str(e)}

    return {
        "results": [_result_to_dict(r) for r in results],
        "total": len(results),
    }


def register(app):
    app.tool()(rvtdocs_search)
