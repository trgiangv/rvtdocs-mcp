from __future__ import annotations

import difflib

from ..models import ErrorCode, QueryResolution
from .constants import (
    AMBIGUOUS_SHORT_CLASS_NAMES,
    EXACT_CLASS_NAMESPACE_HINTS,
    METHOD_VERB_PREFIXES,
    NAMESPACE_TAILS,
)

_AMBIGUOUS_CLASS_NAMESPACES: dict[str, list[str]] = {
    "Application": [
        "Autodesk.Revit.ApplicationServices",
        "Autodesk.Revit.UI",
    ],
    "Document": [
        "Autodesk.Revit.DB",
        "Autodesk.Revit.Creation",
    ],
}

_METHOD_SIGNATURE_HINTS = (
    "Syntax",
    "Parameters",
    "Return Value",
    "Remarks",
    "Exceptions",
    "See Also",
)


def _string_similarity(left: str, right: str) -> float:
    return difflib.SequenceMatcher(None, left.lower(), right.lower()).ratio()


def _closest_class_matches(
    query: str,
    *,
    namespace_index: dict[str, str] | None = None,
    limit: int = 5,
) -> list[str]:
    if namespace_index:
        candidates = sorted(namespace_index.keys())
        scored = [(name, _string_similarity(query, name)) for name in candidates]
        scored.sort(key=lambda item: item[1], reverse=True)
        matches = [name for name, score in scored if score >= 0.55][:limit]
        if matches:
            return matches

    candidates = sorted(EXACT_CLASS_NAMESPACE_HINTS.keys())
    scored = [(name, _string_similarity(query, name)) for name in candidates]
    scored.sort(key=lambda item: item[1], reverse=True)
    return [name for name, score in scored if score >= 0.55][:limit]


def _namespace_candidates_for_class(
    class_name: str,
    namespace_index: dict[str, str] | None = None,
) -> list[str]:
    if namespace_index:
        index_tail = namespace_index.get(class_name)
        if index_tail:
            return [f"Autodesk.Revit.{index_tail}"]

    if class_name in _AMBIGUOUS_CLASS_NAMESPACES:
        return list(_AMBIGUOUS_CLASS_NAMESPACES[class_name])

    hint = EXACT_CLASS_NAMESPACE_HINTS.get(class_name)
    if hint:
        return [f"Autodesk.Revit.{hint}"]

    return [f"Autodesk.Revit.{tail}" for tail in NAMESPACE_TAILS[:8]]


def _namespace_qualified_alternates(class_name: str, namespaces: list[str]) -> list[str]:
    return [f"{namespace}.{class_name}" for namespace in namespaces]


def _method_qualified_alternates(
    resolution: QueryResolution,
    namespaces: list[str],
) -> list[str]:
    if resolution.kind != "method" or not resolution.class_name or not resolution.method_name:
        return []

    alternates = [f"{resolution.class_name}.{resolution.method_name}"]
    for namespace in namespaces[:3]:
        alternates.append(f"{namespace}.{resolution.class_name}.{resolution.method_name}")
    return alternates


def _closest_class_alternates(
    query: str,
    resolution: QueryResolution,
    *,
    namespace_index: dict[str, str] | None = None,
) -> list[str]:
    closest = _closest_class_matches(
        query if resolution.kind != "method" else str(resolution.class_name),
        namespace_index=namespace_index,
    )
    alternates: list[str] = []
    for match in closest:
        if namespace_index and match in namespace_index:
            alternates.append(f"Autodesk.Revit.{namespace_index[match]}.{match}")
            continue

        hint = EXACT_CLASS_NAMESPACE_HINTS.get(match)
        if hint:
            alternates.append(f"Autodesk.Revit.{hint}.{match}")
        else:
            alternates.append(match)
    return alternates


def _dedupe_alternate_queries(alternates: list[str], query: str) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for alternate in alternates:
        key = alternate.lower()
        if key in seen or alternate == query:
            continue
        seen.add(key)
        deduped.append(alternate)
    return deduped[:8]


def _suggest_alternate_queries(
    query: str,
    resolution: QueryResolution,
    namespaces: list[str],
    *,
    namespace_index: dict[str, str] | None = None,
) -> list[str]:
    class_name = resolution.class_name or query
    alternates = _namespace_qualified_alternates(class_name, namespaces)
    alternates.extend(_method_qualified_alternates(resolution, namespaces))
    alternates.extend(
        _closest_class_alternates(query, resolution, namespace_index=namespace_index)
    )
    return _dedupe_alternate_queries(alternates, query)


def _suggest_for_ambiguous(
    query: str,
    resolution: QueryResolution,
    class_name: str,
    namespace_index: dict[str, str] | None,
) -> tuple[list[str], list[str]]:
    namespaces = _namespace_candidates_for_class(class_name, namespace_index)
    if class_name in AMBIGUOUS_SHORT_CLASS_NAMES:
        suggestions = [
            f"'{class_name}' is ambiguous; qualify with a namespace such as "
            + ", ".join(namespaces[:4])
        ]
    else:
        suggestions = ["Short query resolved ambiguously; add a namespace prefix."]
    for namespace in namespaces:
        suggestions.append(f"Try fully-qualified class: {namespace}.{class_name}")
    alternate_queries = _suggest_alternate_queries(
        query,
        resolution,
        namespaces,
        namespace_index=namespace_index,
    )
    return suggestions, alternate_queries


def _suggest_for_not_found_method(
    query: str,
    resolution: QueryResolution,
    namespace_index: dict[str, str] | None,
) -> tuple[list[str], list[str]]:
    method_name = resolution.method_name or ""
    class_name = resolution.class_name or ""
    suggestions = [
        (
            f"Method '{method_name}' may not exist on the resolved class page; "
            "verify spelling and check the class page for available overloads."
        ),
        "Method pages list sections such as: " + ", ".join(_METHOD_SIGNATURE_HINTS),
    ]
    if any(method_name.startswith(prefix) for prefix in METHOD_VERB_PREFIXES):
        suggestions.append(
            f"'{method_name}' follows a common Revit verb pattern "
            f"({', '.join(METHOD_VERB_PREFIXES[:6])}, ...); confirm class namespace."
        )
    namespaces = _namespace_candidates_for_class(class_name, namespace_index)
    alternate_queries = _suggest_alternate_queries(
        query,
        resolution,
        namespaces,
        namespace_index=namespace_index,
    )
    if class_name:
        hint = EXACT_CLASS_NAMESPACE_HINTS.get(class_name)
        if hint:
            alternate_queries.insert(0, f"Autodesk.Revit.{hint}.{class_name}.{method_name}")
        elif namespace_index and class_name in namespace_index:
            alternate_queries.insert(
                0,
                f"Autodesk.Revit.{namespace_index[class_name]}.{class_name}.{method_name}",
            )
    return suggestions, alternate_queries


def _suggest_for_not_found_generic(
    query: str,
    resolution: QueryResolution,
    class_name: str,
    namespace_index: dict[str, str] | None,
) -> tuple[list[str], list[str]]:
    suggestions = [
        "Page fetched but content did not match the query focus.",
        "Retry with mode=full to include the snippet for inspection.",
        "Increase max_chars if the target symbol appears late on the page.",
    ]
    if resolution.kind == "namespace":
        suggestions.append("Try the parent namespace or a shorter namespace tail token.")
    alternate_queries = _suggest_alternate_queries(
        query,
        resolution,
        _namespace_candidates_for_class(class_name, namespace_index),
        namespace_index=namespace_index,
    )
    return suggestions, alternate_queries


def _suggest_for_deprecated(extracted: dict | None) -> tuple[list[str], list[str]]:
    deprecation = (extracted or {}).get("deprecation") or {}
    replacement = deprecation.get("replacement") or ""
    hint = deprecation.get("hint") or ""
    suggestions: list[str] = []
    if replacement:
        suggestions.append(f"API is obsolete; replacement candidate: {replacement}")
    if hint:
        suggestions.append(hint)
    suggestions.append("Check What's New for the removal version and migration path.")
    alternate_queries = [replacement] if replacement else []
    return suggestions, alternate_queries


def _suggest_for_network_error() -> tuple[list[str], list[str]]:
    return ["Network connection failed; retry after connectivity is restored."], []


def _suggest_for_http_error(
    query: str,
    resolution: QueryResolution,
    class_name: str,
    namespace_index: dict[str, str] | None,
) -> tuple[list[str], list[str]]:
    suggestions = [
        "HTTP request failed; verify the resolved URL path and Revit year.",
        "Try a fully-qualified symbol path if the short query misrouted.",
    ]
    alternate_queries = _suggest_alternate_queries(
        query,
        resolution,
        _namespace_candidates_for_class(class_name, namespace_index),
        namespace_index=namespace_index,
    )
    return suggestions, alternate_queries


def _append_closest_class_hints(
    suggestions: list[str],
    query: str,
    resolution: QueryResolution,
    error_code: ErrorCode | str,
    namespace_index: dict[str, str] | None,
) -> None:
    closest = _closest_class_matches(
        query if resolution.kind != "method" else str(resolution.class_name),
        namespace_index=namespace_index,
    )
    if closest and error_code != ErrorCode.ROUTING_AMBIGUOUS:
        suggestions.append(f"Closest known class hints: {', '.join(closest[:3])}")


def _append_namespace_index_matches(
    suggestions: list[str],
    alternate_queries: list[str],
    class_name: str,
    error_code: ErrorCode | str,
    namespace_index: dict[str, str] | None,
) -> None:
    if not namespace_index or error_code != ErrorCode.API_NOT_FOUND:
        return

    indexed = sorted(namespace_index.keys())
    partial = [name for name in indexed if class_name.lower() in name.lower()][:5]
    if not partial:
        return

    suggestions.append(f"Namespace index partial matches: {', '.join(partial)}")
    for match in partial[:3]:
        tail = namespace_index.get(match)
        if tail:
            alternate_queries.append(f"Autodesk.Revit.{tail}.{match}")
        else:
            alternate_queries.append(match)


def _dedupe_alternates(alternate_queries: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped_alternates: list[str] = []
    for alternate in alternate_queries:
        key = alternate.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped_alternates.append(alternate)
    return deduped_alternates[:8]


def build_suggestions(
    query: str,
    resolution: QueryResolution,
    error_code: ErrorCode | str,
    extracted: dict | None,
    namespace_index: dict | None = None,
) -> dict:
    """Build suggestions for failed queries."""
    suggestions: list[str] = []
    alternate_queries: list[str] = []
    class_name = resolution.class_name or query

    if error_code == ErrorCode.ROUTING_AMBIGUOUS:
        suggestions, alternate_queries = _suggest_for_ambiguous(
            query,
            resolution,
            class_name,
            namespace_index,
        )

    elif error_code == ErrorCode.API_NOT_FOUND and resolution.kind == "method":
        suggestions, alternate_queries = _suggest_for_not_found_method(
            query,
            resolution,
            namespace_index,
        )

    elif error_code in {
        ErrorCode.API_NOT_FOUND,
        ErrorCode.ROUTING_NAMESPACE_MISS,
        ErrorCode.EXTRACTION_EMPTY,
    }:
        suggestions, alternate_queries = _suggest_for_not_found_generic(
            query,
            resolution,
            class_name,
            namespace_index,
        )

    elif error_code == ErrorCode.API_DEPRECATED:
        suggestions, alternate_queries = _suggest_for_deprecated(extracted)

    elif error_code == ErrorCode.HTTP_ERROR:
        suggestions, alternate_queries = _suggest_for_http_error(
            query,
            resolution,
            class_name,
            namespace_index,
        )

    elif error_code == ErrorCode.NETWORK_ERROR:
        suggestions, alternate_queries = _suggest_for_network_error()

    _append_closest_class_hints(
        suggestions,
        query,
        resolution,
        error_code,
        namespace_index,
    )
    _append_namespace_index_matches(
        suggestions,
        alternate_queries,
        class_name,
        error_code,
        namespace_index,
    )

    return {
        "suggestions": suggestions,
        "alternateQueries": _dedupe_alternates(alternate_queries),
    }
