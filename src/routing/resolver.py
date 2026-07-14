from __future__ import annotations

from dataclasses import dataclass

from .canonicalization import canonicalize_query
from .constants import (
    AMBIGUOUS_SHORT_CLASS_NAMES,
    CAMEL_TOKEN_PATTERN,
    CLASS_FQCN_PATTERN,
    DB_SUBNAMESPACES,
    EXACT_CLASS_NAMESPACE_HINTS,
    GENERIC_METHOD_TOKENS,
    KNOWN_NAMESPACE_TAILS,
    METHOD_PATTERN,
    METHOD_CONTEXT_NAMESPACE_HINTS,
    METHOD_VERB_PREFIXES,
    NAMESPACE_AFFINITY_KEYWORDS,
    NAMESPACE_PREFIX_ALIASES,
    NAMESPACE_TAILS,
    POLICY_SINGLE_FETCH,
    ROOT_DB_CLASS_PREFIXES,
    SHORT_CLASS_PATTERN,
)
from ..config import (
    BASE_URL,
    DEFAULT_YEAR,
    MAX_ACCEPTED_YEAR,
    MIN_ACCEPTED_YEAR,
    SUPPORTED_YEARS,
)
from ..models import QueryResolution
from .namespace_index import get_namespace_index


@dataclass(frozen=True)
class _ClassTailResolution:
    tail: str
    unverified_namespace: bool


def _camel_tokens(value: str) -> set[str]:
    return {token.lower() for token in CAMEL_TOKEN_PATTERN.findall(value or "") if token}


def _namespace_bonus(class_name: str, class_tokens: set[str], suffix: str) -> int:
    is_ui_suffix = suffix.startswith("UI")
    has_command_or_dialog = "command" in class_tokens or "dialog" in class_tokens

    bonus = 2 * int(class_name.startswith("UI") and is_ui_suffix)
    bonus += 3 * int("command" in class_tokens and is_ui_suffix)
    bonus += 1 * int("data" in class_tokens and is_ui_suffix)
    bonus += 2 * int(class_name.endswith("Attribute") and suffix == "Attributes")
    bonus += 2 * int(class_name.endswith("Exception") and suffix == "Exceptions")
    bonus += 2 * int(is_ui_suffix and has_command_or_dialog)
    bonus -= 1 * int(suffix == "ExternalData" and has_command_or_dialog)
    return bonus


def _best_namespace_suffix(class_name: str, method_name: str | None = None) -> str | None:
    class_tokens = _camel_tokens(class_name)
    method_tokens = _camel_tokens(method_name) if method_name else set()
    method_tokens = {token for token in method_tokens if token not in GENERIC_METHOD_TOKENS}
    if not class_tokens and not method_tokens:
        return None

    best_suffix = None
    best_score = 0
    for suffix in NAMESPACE_TAILS:
        suffix_tokens = _camel_tokens(suffix)
        affinity_tokens = NAMESPACE_AFFINITY_KEYWORDS.get(suffix, set())

        score = 2 * len(class_tokens & suffix_tokens)
        score += 2 * len(class_tokens & affinity_tokens)
        score += len(method_tokens & suffix_tokens)
        score += len(method_tokens & affinity_tokens)
        score += _namespace_bonus(class_name, class_tokens, suffix)

        if score > best_score:
            best_score = score
            best_suffix = suffix
    return best_suffix if best_score > 0 else None


def _is_namespace_prefix(token: str) -> bool:
    return token in NAMESPACE_PREFIX_ALIASES


def _normalize_namespace_tail(tail: str) -> str:
    if tail in DB_SUBNAMESPACES:
        return f"DB.{tail}"
    return tail


def _looks_like_method_name(token: str) -> bool:
    return any(token.startswith(prefix) for prefix in METHOD_VERB_PREFIXES)


def _build_symbol_path(tail: str) -> str:
    return f"Autodesk.Revit.{tail}"


def _make_resolution(
    *,
    year: str,
    query: str,
    kind: str,
    tail: str,
    reason: str,
    class_name: str | None = None,
    method_name: str | None = None,
    unverified_namespace: bool = False,
) -> QueryResolution:
    path = f"/{year}/{_build_symbol_path(tail)}"
    return QueryResolution(
        host=BASE_URL,
        year=year,
        query=query,
        kind=kind,
        path=path,
        url=f"{BASE_URL}{path}",
        reason=reason,
        policy=POLICY_SINGLE_FETCH,
        class_name=class_name,
        method_name=method_name,
        unverified_namespace=unverified_namespace,
    )


def _resolve_fqcn(raw_query: str, query_year: str, class_tail: str) -> QueryResolution:
    parts = class_tail.split(".")

    if class_tail in KNOWN_NAMESPACE_TAILS:
        return _make_resolution(
            year=query_year,
            query=raw_query,
            kind="namespace",
            tail=class_tail,
            reason="Fully-qualified namespace detected",
        )

    if len(parts) >= 3 and _looks_like_method_name(parts[-1]):
        return _make_resolution(
            year=query_year,
            query=raw_query,
            kind="method",
            tail=".".join(parts[:-1]),
            reason="Fully-qualified chain method detected",
            class_name=parts[-2],
            method_name=parts[-1],
        )

    return _make_resolution(
        year=query_year,
        query=raw_query,
        kind="class",
        tail=class_tail,
        reason="Fully-qualified class detected",
        class_name=parts[-1],
    )


def _class_tail_from_short_name(
    class_name: str,
    method_name: str | None = None,
    *,
    year: str = DEFAULT_YEAR,
) -> _ClassTailResolution:
    if not class_name:
        return _ClassTailResolution("DB.", unverified_namespace=True)

    exact_hint = EXACT_CLASS_NAMESPACE_HINTS.get(class_name)
    if exact_hint:
        return _ClassTailResolution(f"{exact_hint}.{class_name}", unverified_namespace=False)

    index_tail = get_namespace_index().lookup(class_name, year)
    if index_tail:
        return _ClassTailResolution(f"{index_tail}.{class_name}", unverified_namespace=False)

    for hint_class, method_prefix, hint_namespace in METHOD_CONTEXT_NAMESPACE_HINTS:
        if class_name == hint_class and method_name and method_name.startswith(method_prefix):
            return _ClassTailResolution(f"{hint_namespace}.{class_name}", unverified_namespace=False)

    if any(class_name.startswith(prefix) for prefix in ROOT_DB_CLASS_PREFIXES):
        return _ClassTailResolution(f"DB.{class_name}", unverified_namespace=False)

    suffix = _best_namespace_suffix(class_name, method_name)
    if not suffix:
        return _ClassTailResolution(f"DB.{class_name}", unverified_namespace=True)
    return _ClassTailResolution(
        f"{_normalize_namespace_tail(suffix)}.{class_name}",
        unverified_namespace=True,
    )


def _resolve_dotted(raw_query: str, query_year: str, left: str, right: str) -> QueryResolution:
    if _is_namespace_prefix(left):
        if _looks_like_method_name(right):
            namespace_tail = NAMESPACE_PREFIX_ALIASES[left]
            class_name = left
            class_tail = f"{namespace_tail}.{class_name}"
            return _make_resolution(
                year=query_year,
                query=raw_query,
                kind="method",
                tail=class_tail,
                reason="Namespace-qualified method query detected",
                class_name=class_name,
                method_name=right,
            )

        class_tail = f"{NAMESPACE_PREFIX_ALIASES[left]}.{right}"
        return _make_resolution(
            year=query_year,
            query=raw_query,
            kind="class",
            tail=class_tail,
            reason="Namespace-qualified class query detected",
            class_name=right,
        )

    class_resolution = _class_tail_from_short_name(left, right, year=query_year)
    return _make_resolution(
        year=query_year,
        query=raw_query,
        kind="method",
        tail=class_resolution.tail,
        reason="Method query detected; class-first strategy",
        class_name=left,
        method_name=right,
        unverified_namespace=class_resolution.unverified_namespace,
    )


@dataclass(frozen=True)
class NormalizedYear:
    year: str
    warning: str | None = None


def normalize_year(year: str | None) -> NormalizedYear:
    raw = (year or DEFAULT_YEAR).strip()
    if not (raw.isdigit() and len(raw) == 4):
        return NormalizedYear(
            year=DEFAULT_YEAR,
            warning=f"Invalid year '{year}'; using default {DEFAULT_YEAR}",
        )

    numeric = int(raw)
    if numeric < MIN_ACCEPTED_YEAR or numeric > MAX_ACCEPTED_YEAR:
        return NormalizedYear(
            year=DEFAULT_YEAR,
            warning=(
                f"Year {raw} outside accepted range "
                f"{MIN_ACCEPTED_YEAR}-{MAX_ACCEPTED_YEAR}; using default {DEFAULT_YEAR}"
            ),
        )

    if raw not in SUPPORTED_YEARS:
        return NormalizedYear(
            year=raw,
            warning=(
                f"Year {raw} is outside the documented Revit API range "
                f"(2022-2027); docs may be incomplete or unavailable"
            ),
        )

    return NormalizedYear(year=raw)


def resolve_query(query: str, year: str | None = None) -> QueryResolution:
    canonical = canonicalize_query(query)
    raw_query = canonical.canonical_query
    query_year = normalize_year(year).year
    lower_query = raw_query.lower()

    if not raw_query:
        path = f"/{query_year}/"
        return QueryResolution(
            host=BASE_URL,
            year=query_year,
            query=raw_query,
            kind="root",
            path=path,
            url=f"{BASE_URL}{path}",
            reason="Empty query fallback",
            policy=POLICY_SINGLE_FETCH,
        )

    if "what's new" in lower_query or "whats new" in lower_query or "news" in lower_query:
        path = f"/{query_year}/"
        return QueryResolution(
            host=BASE_URL,
            year=query_year,
            query=raw_query,
            kind="news",
            path=path,
            url=f"{BASE_URL}{path}",
            reason="News intent detected; routed to year root",
            policy=POLICY_SINGLE_FETCH,
        )

    class_match = CLASS_FQCN_PATTERN.search(raw_query)
    if class_match:
        return _resolve_fqcn(raw_query, query_year, class_match.group(1))

    method_match = METHOD_PATTERN.fullmatch(raw_query)
    if method_match:
        return _resolve_dotted(raw_query, query_year, method_match.group(1), method_match.group(2))

    if SHORT_CLASS_PATTERN.fullmatch(raw_query):
        if raw_query in AMBIGUOUS_SHORT_CLASS_NAMES:
            path = f"/{query_year}/"
            return QueryResolution(
                host=BASE_URL,
                year=query_year,
                query=raw_query,
                kind="ambiguous",
                path=path,
                url=f"{BASE_URL}{path}",
                reason="Ambiguous short class query; namespace required",
                policy=POLICY_SINGLE_FETCH,
            )

        if raw_query in NAMESPACE_PREFIX_ALIASES:
            return _make_resolution(
                year=query_year,
                query=raw_query,
                kind="namespace",
                tail=NAMESPACE_PREFIX_ALIASES[raw_query],
                reason="Short namespace query detected",
            )

        class_resolution = _class_tail_from_short_name(raw_query, year=query_year)
        return _make_resolution(
            year=query_year,
            query=raw_query,
            kind="class",
            tail=class_resolution.tail,
            reason="Short class query detected",
            class_name=class_resolution.tail.split(".")[-1],
            unverified_namespace=class_resolution.unverified_namespace,
        )

    path = f"/{query_year}/"
    return QueryResolution(
        host=BASE_URL,
        year=query_year,
        query=raw_query,
        kind="root",
        path=path,
        url=f"{BASE_URL}{path}",
        reason="Generic fallback",
        policy=POLICY_SINGLE_FETCH,
    )
