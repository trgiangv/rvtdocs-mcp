"""rvtdocs_diff tool: compare API entries between Revit versions.

Enables cross-version compatibility checking, migration planning,
and new API discovery without web search.
"""
from __future__ import annotations

from ..config import DEFAULT_YEAR, SUPPORTED_YEARS
from ..search.tree_index import get_tree_index


def rvtdocs_diff(
    from_year: str = "2025",
    to_year: str = "2027",
    scope: str = "",
    types: str = "class",
) -> dict:
    """Compare Revit API between two versions to find new, removed, or changed APIs.

    Use this to check version compatibility, find new APIs, or plan migrations.
    Returns added and removed entries between from_year and to_year.

    Args:
        from_year: Base version year (e.g. "2025")
        to_year: Target version year (e.g. "2027")
        scope: Namespace prefix to limit comparison (e.g. "Autodesk.Revit.DB.Electrical")
               Empty = compare all APIs
        types: Filter by type (comma-separated): class, method, property, enum, namespace
               Default: "class" (most useful for migration)
    """
    from_year = from_year.strip() if from_year else DEFAULT_YEAR
    to_year = to_year.strip() if to_year else "2027"
    if from_year not in SUPPORTED_YEARS:
        from_year = DEFAULT_YEAR
    if to_year not in SUPPORTED_YEARS:
        to_year = "2027"

    type_filter: set[str] | None = None
    if types:
        type_filter = {t.strip().lower() for t in types.split(",") if t.strip()}

    idx = get_tree_index()
    idx.ensure_loaded(from_year)
    idx.ensure_loaded(to_year)

    scope_lower = scope.lower().strip() if scope else ""

    from_entries = idx._entries_by_year.get(from_year, [])
    to_entries = idx._entries_by_year.get(to_year, [])

    from_fqns = {
        e.fqn for e in from_entries
        if (not type_filter or e.api_type in type_filter)
        and (not scope_lower or e.fqn_lower.startswith(scope_lower))
    }
    to_fqns = {
        e.fqn for e in to_entries
        if (not type_filter or e.api_type in type_filter)
        and (not scope_lower or e.fqn_lower.startswith(scope_lower))
    }

    added = sorted(to_fqns - from_fqns)
    removed = sorted(from_fqns - to_fqns)

    return {
        "from": from_year,
        "to": to_year,
        "scope": scope or "(all)",
        "types": types or "(all)",
        "added": added[:100],
        "removed": removed[:100],
        "summary": {
            "addedCount": len(added),
            "removedCount": len(removed),
            "unchangedCount": len(from_fqns & to_fqns),
        },
    }


def register(app):
    app.tool()(rvtdocs_diff)
