from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CanonicalizedQuery:
    raw_query: str
    canonical_query: str
    domain: str
    rewritten: bool


def canonicalize_query(query: str) -> CanonicalizedQuery:
    """Apply only low-risk query normalization for production routing.

    Keep this function intentionally conservative to avoid hardcoded namespace bias.
    Domain-specific rewrites for experiments belong to benchmarking modules.
    """
    raw = (query or "").strip()
    if not raw:
        return CanonicalizedQuery(raw_query=raw, canonical_query=raw, domain="generic", rewritten=False)

    if raw.startswith("Autodesk.Revit."):
        return CanonicalizedQuery(raw_query=raw, canonical_query=raw, domain="fqcn", rewritten=False)

    return CanonicalizedQuery(raw_query=raw, canonical_query=raw, domain="generic", rewritten=False)
