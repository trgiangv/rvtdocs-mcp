import re

from .compact import extract_compact_text
from .confidence_config import get_confidence_config
from .config import DEFAULT_MAX_CHARS
from .html_parser import ApiPageStructure, build_structured_snippet, has_meaningful_structure, parse_rvtdocs_page
from .models import QueryResolution

_INHERITED_ENTRY_PATTERN = re.compile(
    r"\|[^|]+\|[^|]+\|[^|]*?\(Inherited from \w+\s*\)\s*\|[^|]+\|",
    flags=re.IGNORECASE,
)

_SECTION_MARKERS = (
    "Syntax",
    "Parameters",
    "Return Value",
    "Remarks",
    "Exceptions",
    "See Also",
    "Properties",
    "Methods",
    "Constructors",
    "Inheritance Hierarchy",
    "Namespace",
    "Assembly",
    "Fields",
    "Events",
)

_OBSOLETE_PATTERN = re.compile(r"\[Obsolete\]", flags=re.IGNORECASE)
_DEPRECATED_PATTERN = re.compile(r"\bDeprecated\b", flags=re.IGNORECASE)
_USE_INSTEAD_PATTERN = re.compile(
    r"Use\s+([\w.]+)\s+instead",
    flags=re.IGNORECASE,
)
_REMOVED_IN_PATTERN = re.compile(
    r"removed in\s+Revit\s+(\d{4})",
    flags=re.IGNORECASE,
)


def _detect_sections(text: str) -> list[str]:
    found: list[str] = []
    for marker in _SECTION_MARKERS:
        if re.search(rf"\b{re.escape(marker)}\b", text, flags=re.IGNORECASE):
            found.append(marker)
    return found


def _detect_deprecation(text: str) -> dict:
    obsolete = bool(_OBSOLETE_PATTERN.search(text) or _DEPRECATED_PATTERN.search(text))
    replacement = ""
    hint = ""

    use_match = _USE_INSTEAD_PATTERN.search(text)
    if use_match:
        replacement = use_match.group(1).strip()
        obsolete = True

    removed_match = _REMOVED_IN_PATTERN.search(text)
    if removed_match:
        obsolete = True
        hint = f"Removed in Revit {removed_match.group(1)}"

    if obsolete and not hint:
        if _OBSOLETE_PATTERN.search(text):
            hint = "Marked [Obsolete] in documentation"
        elif _DEPRECATED_PATTERN.search(text):
            hint = "Marked Deprecated in documentation"

    return {
        "obsolete": obsolete,
        "replacement": replacement,
        "hint": hint,
    }


def _enrich_payload(base: dict, plain: str, structure: ApiPageStructure | None = None) -> dict:
    enriched = dict(base)
    snippet = str(base.get("snippet", ""))
    deprecation = _detect_deprecation(snippet if snippet else plain)
    if deprecation["obsolete"] or deprecation["replacement"] or deprecation["hint"]:
        enriched["deprecation"] = deprecation
    sections = structure.sections_found if structure and structure.sections_found else _detect_sections(plain)
    if sections:
        enriched["sectionsFound"] = sections
    return enriched


def _resolved_symbol(resolution: QueryResolution) -> str:
    prefix = f"/{resolution.year}/"
    if resolution.path.startswith(prefix):
        return resolution.path[len(prefix) :]
    return ""


def _strip_inherited_entries(text: str) -> str:
    """Remove pipe-delimited table entries inherited from base classes.

    Operates on the flat text output from trafilatura/readability, where table
    rows may appear as inline pipe segments rather than separate lines.
    """
    return _INHERITED_ENTRY_PATTERN.sub("", text)


def pick_snippet(text: str, keyword: str, max_chars: int, strip_inherited: bool = False) -> str:
    limit = max(500, int(max_chars or DEFAULT_MAX_CHARS))

    working_text = _strip_inherited_entries(text) if strip_inherited else text

    if not keyword:
        return working_text[:limit]

    lowered_text = working_text.lower()
    keyword_lower = keyword.lower()
    idx = lowered_text.find(keyword_lower)
    if idx < 0:
        alt_keyword = keyword_lower.replace(".", " ")
        idx = lowered_text.find(alt_keyword)
    if idx < 0:
        return working_text[:limit]

    start = max(0, idx - int(limit * 0.2))
    end = min(len(working_text), start + limit)
    return working_text[start:end]


def _method_confidence(
    class_name: str,
    method_name: str,
    snippet: str,
    structure: ApiPageStructure | None = None,
) -> tuple[float, str, list[str]]:
    config = get_confidence_config()
    weights = config.method
    thresholds = config.thresholds
    score = 0.0
    evidence: list[str] = []
    lowered = snippet.lower()

    if method_name.lower() in lowered:
        score += weights.method_token
        evidence.append("method_token")

    if class_name.lower() in lowered:
        score += weights.class_token
        evidence.append("class_token")

    if any(token in lowered for token in config.method_signature_hints):
        score += weights.signature_hints
        evidence.append("signature_hints")

    if structure is not None:
        synopsis_lower = structure.synopsis.lower()
        if structure.is_method_page:
            score += weights.structured_method_page
            evidence.append("structured_method_page")
        if method_name.lower() in synopsis_lower:
            score += weights.structured_synopsis
            evidence.append("method_in_synopsis")
        if structure.parameters:
            score += weights.structured_parameters
            evidence.append("structured_parameters")
        if structure.returns:
            score += weights.structured_returns
            evidence.append("structured_returns")

    if score >= thresholds.method_exact_min:
        reason = "method_exact_match"
    elif score >= thresholds.method_partial_min:
        reason = "method_partial_match"
    else:
        reason = "method_low_confidence"
    return min(score, 1.0), reason, evidence


def _class_confidence(
    class_name: str,
    symbol_prefix: str,
    snippet: str,
    structure: ApiPageStructure | None = None,
) -> tuple[float, str, list[str]]:
    config = get_confidence_config()
    weights = config.class_weights
    thresholds = config.thresholds
    score = 0.0
    evidence: list[str] = []
    lowered = snippet.lower()
    symbol_prefix_lower = symbol_prefix.lower()

    if f"{symbol_prefix}.{class_name}".lower() in lowered:
        score += weights.fqcn
        evidence.append("fqcn")
    elif class_name.lower() in lowered and symbol_prefix_lower in lowered:
        score += weights.namespace_plus_class
        evidence.append("namespace_plus_class")

    if any(token in lowered for token in config.class_signature_hints):
        score += weights.class_context
        evidence.append("class_context")

    if structure is not None:
        if structure.is_class_page:
            score += weights.structured_class_page
            evidence.append("structured_class_page")
        if class_name.lower() in structure.title.lower():
            score += weights.class_in_title
            evidence.append("class_in_title")
        if structure.methods or structure.properties:
            score += weights.structured_members
            evidence.append("structured_member_tables")

    if score >= thresholds.class_exact_min:
        reason = "class_exact_match"
    elif score >= thresholds.class_partial_min:
        reason = "class_partial_match"
    else:
        reason = "class_low_confidence"
    return min(score, 1.0), reason, evidence


def _namespace_structured_confidence(
    namespace_symbol: str,
    structure: ApiPageStructure,
) -> tuple[float, list[str]]:
    score = 0.0
    evidence: list[str] = []
    namespace_lower = namespace_symbol.lower()

    if structure.is_namespace_page:
        score += 0.15
        evidence.append("structured_namespace_page")
    if structure.namespace_classes:
        score += 0.15
        evidence.append("structured_class_list")
    if namespace_lower in structure.title.lower():
        score += 0.2
        evidence.append("namespace_in_title")

    return score, evidence


def _namespace_confidence(
    namespace_symbol: str,
    snippet: str,
    structure: ApiPageStructure | None = None,
) -> tuple[float, str, list[str]]:
    score = 0.0
    evidence: list[str] = []
    lowered = snippet.lower()
    namespace_lower = namespace_symbol.lower()

    if namespace_lower in lowered:
        score += 0.7
        evidence.append("namespace_fqcn")

    tail_token = namespace_symbol.split(".")[-1].lower() if namespace_symbol else ""
    if tail_token and tail_token in lowered:
        score += 0.25
        evidence.append("namespace_tail")

    tail_tokens = [token for token in namespace_symbol.split(".") if token]
    overlap = sum(1 for token in tail_tokens if token.lower() in lowered)
    if overlap:
        score += min(0.45, overlap * 0.12)
        evidence.append("namespace_tokens")

    if "namespace" in lowered:
        score += 0.2
        evidence.append("namespace_label")

    if any(marker in lowered for marker in ("classes (", "enumerations (", "interfaces (", "structures (")):
        score += 0.15
        evidence.append("namespace_members_table")

    if structure is not None:
        structured_score, structured_evidence = _namespace_structured_confidence(
            namespace_symbol,
            structure,
        )
        score += structured_score
        evidence.extend(structured_evidence)

    if score >= 0.7:
        reason = "namespace_exact_match"
    elif score >= 0.3:
        reason = "namespace_partial_match"
    else:
        reason = "namespace_low_confidence"
    return min(score, 1.0), reason, evidence


def _news_confidence(snippet: str) -> tuple[float, str, list[str]]:
    lowered = snippet.lower()
    evidence: list[str] = []
    score = 0.0
    if "news" in lowered:
        score += 0.6
        evidence.append("news_token")
    if "what" in lowered and "new" in lowered:
        score += 0.4
        evidence.append("whats_new_phrase")
    if "new" in lowered and "removed" in lowered:
        score += 0.3
        evidence.append("new_removed_section")
    if "obsolete" in lowered:
        score += 0.2
        evidence.append("obsolete_token")

    if score >= 0.8:
        reason = "news_exact_match"
    elif score >= 0.4:
        reason = "news_partial_match"
    else:
        reason = "news_low_confidence"
    return min(score, 1.0), reason, evidence


def _structured_snippet_or_fallback(
    structure: ApiPageStructure | None,
    query_kind: str,
    plain: str,
    keyword: str,
    max_chars: int,
    *,
    strip_inherited: bool = False,
) -> tuple[str, bool]:
    if structure is not None and has_meaningful_structure(structure):
        return build_structured_snippet(structure, query_kind, max_chars), True
    return pick_snippet(plain, keyword, max_chars, strip_inherited=strip_inherited), False


def _extract_method_payload(
    resolution: QueryResolution,
    plain: str,
    token_meta: dict,
    max_chars: int,
    structure: ApiPageStructure | None = None,
) -> dict:
    keyword = f"{resolution.class_name}.{resolution.method_name}"
    snippet, used_structured = _structured_snippet_or_fallback(
        structure,
        "method",
        plain,
        keyword,
        max_chars,
        strip_inherited=True,
    )
    if not used_structured and resolution.method_name and resolution.method_name.lower() not in snippet.lower():
        snippet = pick_snippet(plain, resolution.method_name, max_chars, strip_inherited=True)
    confidence, reason_code, evidence = _method_confidence(
        str(resolution.class_name),
        str(resolution.method_name),
        snippet,
        structure,
    )
    if used_structured:
        evidence = [*evidence, "structured_snippet"]
    payload_meta = dict(token_meta)
    if used_structured:
        payload_meta["snippetSource"] = "structured"
    return _enrich_payload(
        {
            "focus": "method",
            "keyword": keyword,
            "matched": str(resolution.method_name).lower() in snippet.lower(),
            "confidence": confidence,
            "reasonCode": reason_code,
            "evidence": evidence,
            "tokenStats": payload_meta,
            "snippet": snippet,
        },
        plain,
        structure,
    )


def _extract_namespace_payload(
    resolution: QueryResolution,
    plain: str,
    token_meta: dict,
    max_chars: int,
    structure: ApiPageStructure | None = None,
) -> dict:
    symbol = _resolved_symbol(resolution)
    keyword = symbol or resolution.query
    tail_token = keyword.split(".")[-1] if keyword else ""
    snippet, used_structured = _structured_snippet_or_fallback(
        structure,
        "namespace",
        plain,
        keyword,
        max_chars,
    )
    if not used_structured and tail_token and tail_token.lower() not in snippet.lower():
        snippet = pick_snippet(plain, tail_token, max_chars)
    confidence, reason_code, evidence = _namespace_confidence(keyword, snippet, structure)
    if used_structured:
        evidence = [*evidence, "structured_snippet"]
    payload_meta = dict(token_meta)
    if used_structured:
        payload_meta["snippetSource"] = "structured"
    return _enrich_payload(
        {
            "focus": "namespace",
            "keyword": keyword,
            "matched": confidence >= 0.3,
            "confidence": confidence,
            "reasonCode": reason_code,
            "evidence": evidence,
            "tokenStats": payload_meta,
            "snippet": snippet,
        },
        plain,
        structure,
    )


def _extract_class_payload(
    resolution: QueryResolution,
    plain: str,
    token_meta: dict,
    max_chars: int,
    structure: ApiPageStructure | None = None,
) -> dict:
    symbol = _resolved_symbol(resolution)
    symbol_prefix = "Autodesk.Revit"
    symbol_parts = symbol.split(".") if symbol else []
    if len(symbol_parts) > 1:
        symbol_prefix = ".".join(symbol_parts[:-1])
    keyword = f"{symbol_prefix}.{resolution.class_name}"
    snippet, used_structured = _structured_snippet_or_fallback(
        structure,
        "class",
        plain,
        keyword,
        max_chars,
        strip_inherited=True,
    )
    confidence, reason_code, evidence = _class_confidence(
        str(resolution.class_name),
        symbol_prefix,
        snippet,
        structure,
    )
    if used_structured:
        evidence = [*evidence, "structured_snippet"]
    payload_meta = dict(token_meta)
    if used_structured:
        payload_meta["snippetSource"] = "structured"
    return _enrich_payload(
        {
            "focus": "class",
            "keyword": keyword,
            "matched": str(resolution.class_name).lower() in snippet.lower(),
            "confidence": confidence,
            "reasonCode": reason_code,
            "evidence": evidence,
            "tokenStats": payload_meta,
            "snippet": snippet,
        },
        plain,
        structure,
    )


def _extract_news_payload(plain: str, token_meta: dict, max_chars: int) -> dict:
    keyword = "new"
    snippet = pick_snippet(plain, keyword, max_chars)
    confidence, reason_code, evidence = _news_confidence(snippet)
    return _enrich_payload(
        {
            "focus": "news",
            "keyword": keyword,
            "matched": bool(re.search(r"new|news", snippet, flags=re.IGNORECASE)),
            "confidence": confidence,
            "reasonCode": reason_code,
            "evidence": evidence,
            "tokenStats": token_meta,
            "snippet": snippet,
        },
        plain,
    )


def _extract_ambiguous_payload(resolution: QueryResolution, plain: str, token_meta: dict, max_chars: int) -> dict:
    snippet = pick_snippet(plain, "", max_chars)
    return _enrich_payload(
        {
            "focus": "ambiguous",
            "keyword": resolution.query,
            "matched": False,
            "confidence": 0.2,
            "reasonCode": "ambiguous_query_requires_namespace",
            "evidence": ["ambiguous_short_query"],
            "tokenStats": token_meta,
            "snippet": snippet,
        },
        plain,
    )


def extract_for_resolution(resolution: QueryResolution, html: str, max_chars: int) -> dict:
    structure = parse_rvtdocs_page(html)
    plain, token_meta = extract_compact_text(html)

    if resolution.kind == "method" and resolution.class_name and resolution.method_name:
        return _extract_method_payload(resolution, plain, token_meta, max_chars, structure)

    if resolution.kind == "namespace":
        return _extract_namespace_payload(resolution, plain, token_meta, max_chars, structure)

    if resolution.kind == "class" and resolution.class_name:
        return _extract_class_payload(resolution, plain, token_meta, max_chars, structure)

    if resolution.kind == "news":
        return _extract_news_payload(plain, token_meta, max_chars)

    if resolution.kind == "ambiguous":
        return _extract_ambiguous_payload(resolution, plain, token_meta, max_chars)

    snippet = pick_snippet(plain, "", max_chars)
    return _enrich_payload(
        {
            "focus": "root",
            "keyword": "",
            "matched": True,
            "confidence": 0.4,
            "reasonCode": "root_fallback",
            "evidence": ["fallback"],
            "tokenStats": token_meta,
            "snippet": snippet,
        },
        plain,
        structure,
    )
