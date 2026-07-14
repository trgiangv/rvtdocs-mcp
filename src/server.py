import asyncio
import json
import time

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from .async_fetcher import AsyncPageFetcher
from .cache_store import get_shared_cache
from .calibration import log_calibration_event
from .confidence_config import get_confidence_config
from .config import (
    DEFAULT_MAX_CHARS,
    DEFAULT_YEAR,
    MAX_BATCH_OUTPUT_CHARS,
    MAX_OUTPUT_CHARS,
    SUPPORTED_YEARS,
)
from .extractor import extract_for_resolution
from .fetcher import PageFetcher
from .models import ErrorCode, FetchResult, QueryResolution
from .routing import canonicalize_query, normalize_year, resolve_query
from .routing.namespace_index import get_namespace_index
from .routing.suggestions import build_suggestions
from .schemas import FetchPayload, HttpMeta
from .session_store import SessionStore
from .telemetry import TelemetryLogger, build_tool_event

MAX_BATCH_SIZE = 10

app = FastMCP("rvtdocs-mcp-py")
fetcher = PageFetcher()
async_fetcher = AsyncPageFetcher()
telemetry = TelemetryLogger()
session = SessionStore()


def _payload_json_size(payload: dict) -> int:
    return len(json.dumps(payload, ensure_ascii=False))


def _keep_sections_within_budget(parts: list[str], content_budget: int) -> str | None:
    if len(parts) <= 1:
        return None

    kept = parts[0]
    for part in parts[1:]:
        candidate = f"{kept}\n## {part}" if kept else f"## {part}"
        if len(candidate) > content_budget:
            break
        kept = candidate
    return kept


def _truncate_snippet_at_sections(snippet: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(snippet) <= max_chars:
        return snippet

    marker = "\n\n...(truncated)"
    if max_chars <= len(marker):
        return snippet[:max_chars]

    content_budget = max_chars - len(marker)
    kept = _keep_sections_within_budget(snippet.split("\n## "), content_budget)
    if kept and len(kept) < len(snippet):
        return (kept[:content_budget].rstrip() + marker)[:max_chars]

    if content_budget < 20:
        return snippet[:max_chars]
    return (snippet[: content_budget - 3].rstrip() + "..." + marker)[:max_chars]


def _try_truncate_snippet(payload: dict, max_chars: int) -> tuple[dict, bool, bool]:
    extracted = payload.get("extracted")
    if not isinstance(extracted, dict):
        return payload, False, False

    snippet = str(extracted.get("snippet", ""))
    if not snippet:
        return payload, False, False

    base_payload = dict(payload)
    base_extracted = dict(extracted)
    base_extracted["snippet"] = ""
    base_payload["extracted"] = base_extracted
    base_payload["token_output_chars"] = 0
    base_size = _payload_json_size(base_payload)
    if base_size < max_chars:
        snippet_budget = max_chars - base_size - 32
        truncated_snippet = _truncate_snippet_at_sections(snippet, snippet_budget)
        updated_extracted = dict(extracted)
        updated_extracted["snippet"] = truncated_snippet
        payload["extracted"] = updated_extracted
        payload["token_output_chars"] = len(truncated_snippet)
        return payload, True, _payload_json_size(payload) <= max_chars

    updated_extracted = dict(extracted)
    updated_extracted["snippet"] = ""
    payload["extracted"] = updated_extracted
    payload["token_output_chars"] = 0
    return payload, True, False


def _try_truncate_diagnostics(payload: dict, max_chars: int) -> tuple[dict, bool, bool]:
    diagnostics = payload.get("diagnostics")
    if not isinstance(diagnostics, dict) or not diagnostics:
        return payload, False, False

    payload["diagnostics"] = {
        "mode": diagnostics.get("mode"),
        "result": diagnostics.get("result"),
    }
    return payload, True, _payload_json_size(payload) <= max_chars


def _try_truncate_suggestions(payload: dict, max_chars: int) -> tuple[dict, bool, bool]:
    suggestions = payload.get("suggestions")
    if not isinstance(suggestions, dict):
        return payload, False, False

    items = suggestions.get("suggestions")
    if not isinstance(items, list) or len(items) <= 2:
        return payload, False, False

    slim = dict(suggestions)
    slim["suggestions"] = items[:2]
    payload["suggestions"] = slim
    return payload, True, _payload_json_size(payload) <= max_chars


def _try_truncate_error(payload: dict) -> tuple[dict, bool]:
    error = payload.get("error")
    if not isinstance(error, str) or len(error) <= 500:
        return payload, False

    payload["error"] = error[:500]
    return payload, True


def _apply_truncation_step(
    payload: dict,
    max_chars: int,
    truncated: bool,
    step,
) -> tuple[dict, bool, bool | None]:
    payload, step_truncated, within_limit = step(payload, max_chars)
    if not step_truncated:
        return payload, truncated, None
    truncated = True
    if within_limit:
        payload["outputTruncated"] = True
        return payload, truncated, True
    return payload, truncated, False


def _enforce_output_limit(payload: dict, max_chars: int) -> dict:
    if _payload_json_size(payload) <= max_chars:
        return payload

    truncated = False
    for step in (
        _try_truncate_snippet,
        _try_truncate_diagnostics,
        _try_truncate_suggestions,
    ):
        payload, truncated, done = _apply_truncation_step(payload, max_chars, truncated, step)
        if done is True:
            return payload
        if done is False and _payload_json_size(payload) <= max_chars:
            payload["outputTruncated"] = True
            return payload

    payload, error_truncated = _try_truncate_error(payload)
    if error_truncated:
        truncated = True

    if truncated or _payload_json_size(payload) > max_chars:
        payload["outputTruncated"] = True

    return payload


def _year_warning_for(year: str) -> str | None:
    return normalize_year(year).warning


def _to_scan_payload(payload: dict) -> dict:
    result = {
        "success": payload.get("success", False),
        "resolved": payload.get("resolved", {}),
        "http": payload.get("http", {}),
        "trust": payload.get("trust", {}),
        "note": payload.get("note", ""),
    }
    if payload.get("error"):
        result["error"] = payload["error"]
    if payload.get("suggestions"):
        result["suggestions"] = payload["suggestions"]
    if payload.get("sectionsFound"):
        result["sectionsFound"] = payload["sectionsFound"]
    if payload.get("deprecation"):
        result["deprecation"] = payload["deprecation"]
    if payload.get("yearWarning"):
        result["yearWarning"] = payload["yearWarning"]
    if payload.get("outputTruncated"):
        result["outputTruncated"] = payload["outputTruncated"]
    return result


def _is_namespace_miss(resolution: QueryResolution, extracted: dict | None) -> bool:
    if not extracted:
        return False

    semantic_reason = str(extracted.get("reasonCode", ""))
    focus = str(extracted.get("focus", ""))
    if focus not in {"class", "method", "namespace"}:
        return False

    if semantic_reason.endswith("_low_confidence"):
        return True

    confidence = float(extracted.get("confidence", 0.0))
    matched = bool(extracted.get("matched", False))
    class_name = (resolution.class_name or "").lower()
    snippet = str(extracted.get("snippet", "")).lower()
    if class_name and class_name not in snippet and 0.2 <= confidence < 0.5:
        return True
    return not matched and 0.2 <= confidence < 0.5


def _resolve_reason_code(
    *,
    resolution: QueryResolution,
    fetch_ok: bool,
    status: int,
    semantic_match: bool,
    extracted: dict | None,
) -> ErrorCode:
    deprecation = (extracted or {}).get("deprecation") or {}
    snippet = str((extracted or {}).get("snippet", ""))

    if fetch_ok and semantic_match:
        if deprecation.get("obsolete"):
            return ErrorCode.API_DEPRECATED
        return ErrorCode.SINGLE_FETCH_SUCCESS

    if status == 0:
        return ErrorCode.NETWORK_ERROR

    if not fetch_ok:
        return ErrorCode.HTTP_ERROR

    if deprecation.get("obsolete"):
        return ErrorCode.API_DEPRECATED

    if resolution.kind == "ambiguous":
        return ErrorCode.ROUTING_AMBIGUOUS

    if not snippet.strip():
        return ErrorCode.EXTRACTION_EMPTY

    if _is_namespace_miss(resolution, extracted):
        return ErrorCode.ROUTING_NAMESPACE_MISS

    return ErrorCode.API_NOT_FOUND


def _build_http_payload(fetch_result: FetchResult, reason_code: ErrorCode) -> dict:
    meta = fetch_result.to_meta_dict()
    meta["reasonCode"] = reason_code
    meta.pop("errorDetail", None)
    return meta


def _build_note(fetch_ok: bool) -> str:
    return "single-fetch success" if fetch_ok else "single-fetch failed; caller may decide fallback policy"


def _build_trust(is_success: bool, reason_code: ErrorCode, extracted: dict | None) -> dict:
    confidence = float((extracted or {}).get("confidence", 0.0))
    pass_min = get_confidence_config().thresholds.pass_min
    if is_success and confidence >= pass_min:
        verdict = "pass"
    elif reason_code in {
        ErrorCode.NETWORK_ERROR,
        ErrorCode.HTTP_ERROR,
        ErrorCode.API_NOT_FOUND,
    }:
        verdict = "fail"
    else:
        verdict = "warn"

    return {
        "verdict": verdict,
        "confidence": confidence,
        "reasonCode": reason_code,
    }


def _shape_extracted(extracted: dict | None, include_snippet: bool, lean: bool = False) -> tuple[dict | None, int]:
    if not extracted:
        return None, 0

    shaped = dict(extracted)
    shaped.pop("deprecation", None)
    shaped.pop("sectionsFound", None)
    snippet = shaped.get("snippet", "")
    token_output_chars = len(snippet)
    if not include_snippet:
        shaped.pop("snippet", None)
        token_output_chars = 0
    if lean:
        shaped.pop("tokenStats", None)
        shaped.pop("evidence", None)
    return shaped, token_output_chars


def _build_diagnostics(
    *,
    query: str,
    mode: str,
    resolution,
    extracted: dict | None,
    is_success: bool,
    reason_code: ErrorCode,
    include_snippet: bool,
) -> dict:
    canonical = canonicalize_query(query)
    return {
        "mode": mode,
        "inputQuery": query,
        "canonicalQuery": canonical.canonical_query,
        "canonicalRewritten": canonical.rewritten,
        "resolution": {
            "kind": resolution.kind,
            "reason": resolution.reason,
            "path": resolution.path,
            "className": resolution.class_name,
            "methodName": resolution.method_name,
            "unverifiedNamespace": resolution.unverified_namespace,
        },
        "semantic": {
            "focus": (extracted or {}).get("focus", ""),
            "matched": bool((extracted or {}).get("matched", False)),
            "confidence": float((extracted or {}).get("confidence", 0.0)),
            "reasonCode": (extracted or {}).get("reasonCode", ""),
            "evidence": list((extracted or {}).get("evidence", [])),
        },
        "result": {
            "success": is_success,
            "reasonCode": reason_code,
            "snippetIncluded": include_snippet,
        },
    }


def _namespace_index_for_year(year: str) -> dict[str, str]:
    return get_namespace_index().get_index_for_year(year)


def _snippet_source_from_extracted(extracted: dict | None) -> str:
    if not extracted:
        return "none"
    token_stats = extracted.get("tokenStats") or {}
    return str(token_stats.get("snippetSource", "compact"))


def _log_tool_telemetry(
    *,
    tool: str,
    query: str,
    year: str,
    mode: str,
    payload: dict,
    extracted: dict | None = None,
) -> None:
    telemetry.log_async(
        build_tool_event(
            tool=tool,
            query=query,
            year=year,
            mode=mode,
            payload=payload,
            snippet_source=_snippet_source_from_extracted(extracted),
        )
    )


def _compute_suggestions(
    *,
    query: str,
    resolution: QueryResolution,
    is_success: bool,
    reason_code: ErrorCode,
    extracted: dict | None,
    namespace_index: dict[str, str],
) -> dict | None:
    deprecation = (extracted or {}).get("deprecation")
    has_deprecation = bool(deprecation and deprecation.get("obsolete"))
    if not is_success or has_deprecation:
        return build_suggestions(
            query=query,
            resolution=resolution,
            error_code=reason_code,
            extracted=extracted,
            namespace_index=namespace_index,
        )
    return None


def _emit_calibration_log(
    *,
    query: str,
    resolution: QueryResolution,
    extracted: dict | None,
) -> None:
    if not extracted:
        return

    token_stats = extracted.get("tokenStats") or {}
    log_calibration_event(
        query=query,
        kind=resolution.kind,
        confidence=float(extracted.get("confidence", 0.0)),
        evidence=list(extracted.get("evidence") or []),
        reason_code=str(extracted.get("reasonCode", "")),
        actual_match=bool(extracted.get("matched", False)),
        snippet_source=str(token_stats.get("snippetSource", "compact")),
    )


def _build_fetch_result(
    *,
    query: str,
    year: str,
    max_chars: int,
    include_snippet: bool,
    mode: str,
    resolution: QueryResolution,
    fetch_result: FetchResult,
    namespace_index: dict[str, str],
    year_warning: str | None = None,
    tool: str = "rvtdocs_fetch",
) -> dict:
    lean = mode in {"scan", "trust"}

    extracted = (
        extract_for_resolution(resolution, fetch_result.html, max_chars)
        if fetch_result.ok
        else None
    )
    semantic_match = bool(extracted and extracted.get("matched", False))
    is_success = fetch_result.ok and semantic_match
    reason_code = _resolve_reason_code(
        resolution=resolution,
        fetch_ok=fetch_result.ok,
        status=fetch_result.status,
        semantic_match=semantic_match,
        extracted=extracted,
    )

    deprecation = (extracted or {}).get("deprecation")
    sections_found = list((extracted or {}).get("sectionsFound") or [])
    suggestions = _compute_suggestions(
        query=query,
        resolution=resolution,
        is_success=is_success,
        reason_code=reason_code,
        extracted=extracted,
        namespace_index=namespace_index,
    )

    shaped_extracted, token_output_chars = _shape_extracted(extracted, include_snippet, lean=lean)
    trust = _build_trust(is_success, reason_code, extracted)
    diagnostics = _build_diagnostics(
        query=query,
        mode=mode,
        resolution=resolution,
        extracted=extracted,
        is_success=is_success,
        reason_code=reason_code,
        include_snippet=include_snippet,
    )

    http_payload = _build_http_payload(fetch_result, reason_code)
    if fetch_result.error_detail and not lean:
        http_payload["errorDetail"] = fetch_result.error_detail

    _emit_calibration_log(query=query, resolution=resolution, extracted=extracted)

    payload = FetchPayload(
        success=is_success,
        resolved=resolution.to_dict(),
        http=HttpMeta(**http_payload),
        extracted=shaped_extracted if not lean or shaped_extracted else None,
        token_hint_chars=len(extracted["snippet"]) if extracted else 0,
        token_output_chars=token_output_chars,
        note=_build_note(fetch_result.ok),
        trust=trust,
        diagnostics=diagnostics if mode == "diagnostics" else {},
        error=fetch_result.error_detail if fetch_result.error_detail and not fetch_result.ok else None,
        suggestions=suggestions,
        deprecation=deprecation,
        sectionsFound=sections_found or None,
        yearWarning=year_warning,
    ).model_dump()

    payload = _enforce_output_limit(payload, MAX_OUTPUT_CHARS)
    _log_tool_telemetry(
        tool=tool,
        query=query,
        year=year,
        mode=mode,
        payload=payload,
        extracted=extracted,
    )
    return payload


def _fetch_payload(
    query: str,
    year: str,
    max_chars: int,
    include_snippet: bool,
    mode: str,
    tool: str = "rvtdocs_fetch",
) -> dict:
    normalized_year = normalize_year(year)
    resolution = resolve_query(query=query, year=normalized_year.year)
    namespace_index = _namespace_index_for_year(normalized_year.year)

    try:
        fetch_result = fetcher.fetch(resolution.url)
    except Exception as error:  # pragma: no cover
        payload = _enforce_output_limit(
            FetchPayload(
                success=False,
                resolved=resolution.to_dict(),
                http=HttpMeta(attemptsUsed=1, retriesUsed=0, reasonCode=ErrorCode.NETWORK_ERROR),
                error=str(error),
                suggestions=build_suggestions(
                    query=query,
                    resolution=resolution,
                    error_code=ErrorCode.NETWORK_ERROR,
                    extracted=None,
                    namespace_index=namespace_index,
                ),
                yearWarning=normalized_year.warning,
            ).model_dump(),
            MAX_OUTPUT_CHARS,
        )
        _log_tool_telemetry(
            tool=tool,
            query=query,
            year=normalized_year.year,
            mode=mode,
            payload=payload,
        )
        return payload

    return _build_fetch_result(
        query=query,
        year=normalized_year.year,
        max_chars=max_chars,
        include_snippet=include_snippet,
        mode=mode,
        resolution=resolution,
        fetch_result=fetch_result,
        namespace_index=namespace_index,
        year_warning=normalized_year.warning,
        tool=tool,
    )


async def _fetch_payload_async(
    query: str,
    year: str,
    max_chars: int,
    include_snippet: bool,
    mode: str,
    tool: str = "rvtdocs_fetch",
) -> dict:
    normalized_year = normalize_year(year)
    resolution = resolve_query(query=query, year=normalized_year.year)
    namespace_index = _namespace_index_for_year(normalized_year.year)

    try:
        fetch_result = await async_fetcher.fetch(resolution.url)
    except Exception as error:  # pragma: no cover
        payload = _enforce_output_limit(
            FetchPayload(
                success=False,
                resolved=resolution.to_dict(),
                http=HttpMeta(attemptsUsed=1, retriesUsed=0, reasonCode=ErrorCode.NETWORK_ERROR),
                error=str(error),
                suggestions=build_suggestions(
                    query=query,
                    resolution=resolution,
                    error_code=ErrorCode.NETWORK_ERROR,
                    extracted=None,
                    namespace_index=namespace_index,
                ),
                yearWarning=normalized_year.warning,
            ).model_dump(),
            MAX_OUTPUT_CHARS,
        )
        _log_tool_telemetry(
            tool=tool,
            query=query,
            year=normalized_year.year,
            mode=mode,
            payload=payload,
        )
        return payload

    return await asyncio.to_thread(
        _build_fetch_result,
        query=query,
        year=normalized_year.year,
        max_chars=max_chars,
        include_snippet=include_snippet,
        mode=mode,
        resolution=resolution,
        fetch_result=fetch_result,
        namespace_index=namespace_index,
        year_warning=normalized_year.warning,
        tool=tool,
    )


def _failure_payload_for_query(
    query: str,
    year: str,
    error: Exception,
    *,
    mode: str = "trust",
    tool: str = "rvtdocs_batch",
) -> dict:
    normalized_year = normalize_year(year)
    resolution = resolve_query(query=query, year=normalized_year.year)
    namespace_index = _namespace_index_for_year(normalized_year.year)
    payload = _enforce_output_limit(
        FetchPayload(
            success=False,
            resolved=resolution.to_dict(),
            http=HttpMeta(attemptsUsed=1, retriesUsed=0, reasonCode=ErrorCode.NETWORK_ERROR),
            error=str(error),
            suggestions=build_suggestions(
                query=query,
                resolution=resolution,
                error_code=ErrorCode.NETWORK_ERROR,
                extracted=None,
                namespace_index=namespace_index,
            ),
            yearWarning=normalized_year.warning,
        ).model_dump(),
        MAX_OUTPUT_CHARS,
    )
    _log_tool_telemetry(
        tool=tool,
        query=query,
        year=normalized_year.year,
        mode=mode,
        payload=payload,
    )
    return payload


def _enforce_batch_output_budget(results: list[dict]) -> list[dict]:
    if not results:
        return results

    total_size = sum(_payload_json_size(result) for result in results)
    if total_size <= MAX_BATCH_OUTPUT_CHARS:
        return results

    per_item_limit = max(1000, MAX_BATCH_OUTPUT_CHARS // len(results))
    adjusted: list[dict] = []
    for result in results:
        adjusted.append(_enforce_output_limit(result, per_item_limit))
    return adjusted


@app.tool()
def rvtdocs_fetch(
    query: str,
    year: str = "2026",
    max_chars: int = DEFAULT_MAX_CHARS,
    mode: str = "trust",
) -> dict:
    """Fetch RVTDocs in single-fetch mode with trust-gate output shaping.

    mode:
    - trust (default): lean payload, snippet removed to minimize output tokens
    - full: include snippet for detailed inspection
    - diagnostics: include snippet and return resolver/semantic trace metadata
    """
    normalized_mode = mode.strip().lower()
    include_snippet = normalized_mode in {"full", "diagnostics"}
    return _fetch_payload(
        query=query,
        year=year,
        max_chars=max_chars,
        include_snippet=include_snippet,
        mode=normalized_mode,
        tool="rvtdocs_fetch",
    )


@app.tool()
def rvtdocs_scan(
    query: str,
    year: str = "2026",
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict:
    """Resolve and trust-check a query with minimal output for low token cost."""
    payload = _fetch_payload(
        query=query,
        year=year,
        max_chars=max_chars,
        include_snippet=False,
        mode="scan",
        tool="rvtdocs_scan",
    )
    return _to_scan_payload(payload)


@app.tool()
def rvtdocs_debug(
    query: str,
    year: str = "2026",
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict:
    """Run diagnostic fetch with snippet and resolver/semantic trace metadata."""
    return _fetch_payload(
        query=query,
        year=year,
        max_chars=max_chars,
        include_snippet=True,
        mode="diagnostics",
        tool="rvtdocs_debug",
    )


@app.tool()
async def rvtdocs_batch(
    queries: list[str],
    year: str = "2026",
    max_chars: int = DEFAULT_MAX_CHARS,
    mode: str = "trust",
) -> dict:
    """Batch-fetch multiple RVTDocs queries in a single tool call.

    Reduces tool-call overhead when looking up related APIs.
    Returns a list of results, one per query, plus aggregate stats.

    mode:
    - trust (default): lean payload per query
    - full: include snippet per query
    """
    normalized_mode = mode.strip().lower()
    include_snippet = normalized_mode in {"full", "diagnostics"}
    limited_queries = queries[:MAX_BATCH_SIZE]

    tasks = [
        _fetch_payload_async(
            query=query,
            year=year,
            max_chars=max_chars,
            include_snippet=include_snippet,
            mode=normalized_mode,
            tool="rvtdocs_batch",
        )
        for query in limited_queries
    ]
    gathered = await asyncio.gather(*tasks, return_exceptions=True)

    results = []
    total_chars = 0
    successes = 0

    for query, outcome in zip(limited_queries, gathered, strict=True):
        if isinstance(outcome, Exception):
            payload = _failure_payload_for_query(
                query=query,
                year=year,
                error=outcome,
                mode=normalized_mode,
                tool="rvtdocs_batch",
            )
        else:
            payload = outcome
        total_chars += int(payload.get("token_output_chars", 0))
        if payload.get("success"):
            successes += 1
        results.append(payload)

    results = _enforce_batch_output_budget(results)
    total_chars = sum(_payload_json_size(result) for result in results)
    year_warning = _year_warning_for(year)

    response = {
        "results": results,
        "stats": {
            "totalQueries": len(limited_queries),
            "successes": successes,
            "failures": len(limited_queries) - successes,
            "successRate": successes / max(len(limited_queries), 1),
            "totalOutputChars": total_chars,
            "outputTruncated": any(result.get("outputTruncated") for result in results),
        },
    }
    if year_warning:
        response["yearWarning"] = year_warning
    return response


@app.tool()
def rvtdocs_stats(hours: int = 24) -> dict:
    """Query usage statistics for the rvtdocs MCP server.

    Returns tool call counts, success rates, cache hit rates,
    and top queries/failures for the specified time period.
    """
    return telemetry.query_stats(hours)


@app.tool()
def rvtdocs_version_info() -> dict:
    """Returns supported Revit API documentation versions and recommendations."""
    return {
        "supportedYears": sorted(SUPPORTED_YEARS),
        "defaultYear": DEFAULT_YEAR,
        "recommendation": (
            "Pass year matching your running Revit version. "
            "Read revit://version resource from RevitDevTool daemon to detect automatically."
        ),
        "cacheStats": get_shared_cache().stats(),
    }


@app.tool()
def rvtdocs_schema() -> dict:
    """Return JSON schemas for all rvtdocs tools for external validation."""
    return {
        "tools": {
            "rvtdocs_fetch": {
                "parameters": {
                    "query": {
                        "type": "string",
                        "required": True,
                        "description": "Revit API query",
                    },
                    "year": {
                        "type": "string",
                        "required": False,
                        "default": DEFAULT_YEAR,
                    },
                    "max_chars": {
                        "type": "integer",
                        "required": False,
                        "default": DEFAULT_MAX_CHARS,
                    },
                    "mode": {
                        "type": "string",
                        "required": False,
                        "default": "trust",
                        "enum": ["trust", "full", "diagnostics"],
                    },
                },
            },
            "rvtdocs_scan": {
                "parameters": {
                    "query": {"type": "string", "required": True},
                    "year": {
                        "type": "string",
                        "required": False,
                        "default": DEFAULT_YEAR,
                    },
                    "max_chars": {
                        "type": "integer",
                        "required": False,
                        "default": DEFAULT_MAX_CHARS,
                    },
                },
            },
            "rvtdocs_debug": {
                "parameters": {
                    "query": {"type": "string", "required": True},
                    "year": {
                        "type": "string",
                        "required": False,
                        "default": DEFAULT_YEAR,
                    },
                    "max_chars": {
                        "type": "integer",
                        "required": False,
                        "default": DEFAULT_MAX_CHARS,
                    },
                },
            },
            "rvtdocs_batch": {
                "parameters": {
                    "queries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "required": True,
                    },
                    "year": {
                        "type": "string",
                        "required": False,
                        "default": DEFAULT_YEAR,
                    },
                    "max_chars": {
                        "type": "integer",
                        "required": False,
                        "default": DEFAULT_MAX_CHARS,
                    },
                    "mode": {
                        "type": "string",
                        "required": False,
                        "default": "trust",
                        "enum": ["trust", "full", "diagnostics"],
                    },
                },
            },
            "rvtdocs_stats": {
                "parameters": {
                    "hours": {
                        "type": "integer",
                        "required": False,
                        "default": 24,
                    },
                },
            },
            "rvtdocs_version_info": {
                "parameters": {},
            },
            "rvtdocs_schema": {
                "parameters": {},
            },
            "rvtdocs_session_set": {
                "parameters": {
                    "key": {"type": "string", "required": True},
                    "value": {"type": "string", "required": True},
                },
            },
            "rvtdocs_session_get": {
                "parameters": {
                    "key": {"type": "string", "required": True},
                },
            },
        },
        "version": "0.2.0",
    }


@app.tool()
def rvtdocs_session_set(key: str, value: str) -> dict:
    """Store a key-value pair in the session store.

    Useful for caching resolved API info between tool calls.
    Data is ephemeral (lost on server restart).
    """
    session.set(key, {"value": value, "set_at": time.time()})
    return {"stored": True, "key": key}


@app.tool()
def rvtdocs_session_get(key: str) -> dict:
    """Retrieve a value from the session store."""
    entry = session.get(key)
    if entry is None:
        return {"found": False, "key": key}
    return {
        "found": True,
        "key": key,
        "value": entry["value"],
        "setAt": entry["set_at"],
    }


def main() -> None:
    app.run()


if __name__ == "__main__":
    main()
