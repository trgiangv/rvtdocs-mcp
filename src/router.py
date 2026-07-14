"""Compatibility wrapper for legacy router imports."""

from .routing import CanonicalizedQuery, NormalizedYear, canonicalize_query, normalize_year, resolve_query

__all__ = [
    "CanonicalizedQuery",
    "NormalizedYear",
    "canonicalize_query",
    "normalize_year",
    "resolve_query",
]
