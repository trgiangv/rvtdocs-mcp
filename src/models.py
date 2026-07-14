from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    """Machine-readable failure and success codes for fetch outcomes."""

    ROUTING_AMBIGUOUS = "routing_ambiguous"
    API_NOT_FOUND = "api_not_found"
    API_DEPRECATED = "api_deprecated"
    EXTRACTION_EMPTY = "extraction_empty"
    NETWORK_ERROR = "network_error"
    HTTP_ERROR = "http_error"
    ROUTING_NAMESPACE_MISS = "routing_namespace_miss"
    SINGLE_FETCH_SUCCESS = "single_fetch_success"


@dataclass(frozen=True)
class QueryResolution:
    host: str
    year: str
    query: str
    kind: str
    path: str
    url: str
    reason: str
    policy: str
    class_name: str | None = None
    method_name: str | None = None
    unverified_namespace: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FetchResult:
    ok: bool
    status: int
    elapsed_ms: int
    content_length: int
    html: str
    from_cache: bool
    attempts_used: int = 1
    retries_used: int = 0
    error_detail: str = ""

    def to_meta_dict(self) -> dict:
        return {
            "ok": self.ok,
            "status": self.status,
            "elapsedMs": self.elapsed_ms,
            "contentLength": self.content_length,
            "fromCache": self.from_cache,
            "attemptsUsed": self.attempts_used,
            "retriesUsed": self.retries_used,
            "errorDetail": self.error_detail,
        }
