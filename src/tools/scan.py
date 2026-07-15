"""rvtdocs_scan tool: browse namespace or class members.

Lists all classes in a namespace, or all methods/properties of a class.
Uses the in-memory tree index for instant results.
"""
from __future__ import annotations

from ..config import DEFAULT_YEAR, SUPPORTED_YEARS
from ..search.tree_index import get_tree_index


def rvtdocs_scan(
    target: str,
    year: str = "2025",
    types: str = "",
) -> dict:
    """Browse a Revit API namespace or class to list its members.

    Use to explore what's available in a namespace or class:
    - target="Autodesk.Revit.DB.Structure" -> lists all classes in that namespace
    - target="Wall" -> lists all members (methods, properties) of Wall class

    Args:
        target: Namespace FQN or class name to browse
        year: Revit API version year (2022-2027)
        types: Filter results by type (class, method, property, enum)
    """
    target = (target or "").strip()
    if not target:
        return {"results": [], "total": 0, "error": "Empty target"}

    year = year.strip() if year else DEFAULT_YEAR
    if year not in SUPPORTED_YEARS:
        year = DEFAULT_YEAR

    type_filter: set[str] | None = None
    if types:
        type_filter = {t.strip().lower() for t in types.split(",") if t.strip()}

    index = get_tree_index()
    results = index.scan(target, year, types=type_filter)

    return {
        "target": target,
        "year": year,
        "results": [
            {"fqn": r.fqn, "type": r.api_type}
            for r in results
        ],
        "total": len(results),
    }


def register(app):
    app.tool()(rvtdocs_scan)
