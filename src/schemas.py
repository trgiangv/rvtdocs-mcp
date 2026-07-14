from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HttpMeta(BaseModel):
    ok: bool = False
    status: int = 0
    elapsedMs: int = 0
    contentLength: int = 0
    fromCache: bool = False
    attemptsUsed: int = 1
    retriesUsed: int = 0
    reasonCode: str = ""


class TokenStats(BaseModel):
    parserBackend: str = "builtin"
    rawChars: int = 0
    cleanChars: int = 0
    reductionRatio: float = 0.0
    parserMode: str = "auto"


class ExtractedPayload(BaseModel):
    focus: str
    keyword: str
    matched: bool = False
    confidence: float = 0.0
    reasonCode: str
    evidence: list[str] = Field(default_factory=list)
    tokenStats: TokenStats | None = None
    snippet: str = ""


class FetchPayload(BaseModel):
    success: bool = False
    resolved: dict[str, Any]
    http: HttpMeta
    extracted: ExtractedPayload | dict[str, Any] | None = None
    token_hint_chars: int = 0
    token_output_chars: int = 0
    note: str = ""
    trust: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    suggestions: dict[str, Any] | None = None
    deprecation: dict[str, Any] | None = None
    sectionsFound: list[str] | None = None
    outputTruncated: bool = False
    yearWarning: str | None = None
