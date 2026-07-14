from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models import ErrorCode
from .calibration_metrics import compute_calibration_metrics
from .models import BenchmarkCase

# Legacy reason codes from pre-ErrorCode responses mapped to current equivalents.
_LEGACY_REASON_ALIASES: dict[str, frozenset[str]] = {
    "not_found_fail_fast": frozenset(
        {
            "not_found_fail_fast",
            ErrorCode.API_NOT_FOUND,
            ErrorCode.HTTP_ERROR,
        }
    ),
    "content_mismatch": frozenset(
        {
            "content_mismatch",
            ErrorCode.API_NOT_FOUND,
            ErrorCode.ROUTING_NAMESPACE_MISS,
            ErrorCode.EXTRACTION_EMPTY,
            ErrorCode.ROUTING_AMBIGUOUS,
        }
    ),
    "single_fetch_success": frozenset(
        {
            "single_fetch_success",
            ErrorCode.SINGLE_FETCH_SUCCESS,
        }
    ),
}


def _reason_matches(reason: str, *legacy_codes: str) -> bool:
    normalized = reason.strip().lower()
    for legacy in legacy_codes:
        aliases = _LEGACY_REASON_ALIASES.get(legacy, frozenset({legacy}))
        if normalized in {str(alias) for alias in aliases}:
            return True
    return False


def normalize_symbol_path(symbol: str, year: str) -> str:
    if not symbol:
        return ""
    return f"/{year}/{symbol}"


def resolved_path(result: dict[str, Any]) -> str:
    return str((result.get("resolved") or {}).get("path") or "")


def resolver_match(case: BenchmarkCase, result: dict[str, Any]) -> bool:
    path = resolved_path(result).lower()
    if not path:
        return False

    if case.expected_outcome != "success":
        return True

    expected_kind = case.expected_kind.lower()
    if expected_kind in {"method", "method_overload", "chain_method", "member_or_property"}:
        if not case.expected_primary_symbol:
            return True

        symbol_parts = [part for part in case.expected_primary_symbol.split(".") if part]
        if len(symbol_parts) <= 1:
            return True

        class_symbol = ".".join(symbol_parts[:-1])
        expected_path = normalize_symbol_path(class_symbol, case.year).lower()
        if path == expected_path:
            return True

        alternate_paths = [
            normalize_symbol_path(".".join([part for part in alt.split(".") if part][:-1]), case.year).lower()
            for alt in case.accepted_alternates
            if len([part for part in alt.split(".") if part]) > 1
        ]
        return any(path == candidate for candidate in alternate_paths)

    candidates = []
    if case.expected_primary_symbol:
        candidates.append(normalize_symbol_path(case.expected_primary_symbol, case.year))
    candidates.extend(normalize_symbol_path(value, case.year) for value in case.accepted_alternates)

    if not candidates:
        return True
    return any(path == candidate.lower() for candidate in candidates)


def semantic_token_check(case: BenchmarkCase, result: dict[str, Any]) -> bool:
    extracted = result.get("extracted") or {}
    snippet = str(extracted.get("snippet") or "").lower()
    reason = str((result.get("http") or {}).get("reasonCode") or "")

    if not snippet:
        if case.expected_outcome == "success":
            return _reason_matches(reason, "single_fetch_success")
        return True

    for token in case.must_contain_tokens:
        if token.lower() not in snippet:
            return False

    for token in case.forbidden_tokens:
        if token.lower() in snippet:
            return False

    return True


def outcome_match(case: BenchmarkCase, result: dict[str, Any]) -> bool:
    success = bool(result.get("success"))
    reason = str((result.get("http") or {}).get("reasonCode") or "")

    if case.expected_outcome == "success":
        return success
    if case.expected_outcome == "not_found_expected":
        return (not success) and _reason_matches(reason, "not_found_fail_fast")
    if case.expected_outcome == "ambiguous":
        return (not success) and _reason_matches(reason, "content_mismatch", "not_found_fail_fast")
    return False


def evaluate_calibration(
    log_path: Path | None = None,
    *,
    pass_threshold: float | None = None,
) -> dict[str, Any]:
    """Evaluate confidence calibration from the append-only telemetry log."""
    return compute_calibration_metrics(log_path, pass_threshold=pass_threshold)


def evaluate_case(case: BenchmarkCase, result: dict[str, Any]) -> dict[str, Any]:
    resolver_ok = resolver_match(case, result)
    semantic_ok = semantic_token_check(case, result)
    outcome_ok = outcome_match(case, result)
    final_ok = resolver_ok and semantic_ok and outcome_ok if case.expected_outcome == "success" else outcome_ok

    http = result.get("http") or {}
    trust = result.get("trust") or {}

    return {
        "id": case.case_id,
        "year": case.year,
        "namespaceFamily": case.namespace_family,
        "query": case.query,
        "expectedKind": case.expected_kind,
        "expectedOutcome": case.expected_outcome,
        "resolvedPath": resolved_path(result),
        "reasonCode": str(http.get("reasonCode", "")),
        "status": int(http.get("status", 0) or 0),
        "success": bool(result.get("success", False)),
        "resolverOk": resolver_ok,
        "semanticOk": semantic_ok,
        "outcomeOk": outcome_ok,
        "finalOk": final_ok,
        "confidence": float(trust.get("confidence", 0.0) or 0.0),
        "trustVerdict": str(trust.get("verdict", "")),
        "elapsedMs": int(http.get("elapsedMs", 0) or 0),
        "retriesUsed": int(http.get("retriesUsed", 0) or 0),
    }
