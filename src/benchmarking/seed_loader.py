from __future__ import annotations

from typing import Any

from .models import BenchmarkCase
from ..routing import canonicalize_query


def expand_cases(seed_doc: dict[str, Any], years_override: list[str] | None = None) -> list[BenchmarkCase]:
    default_years = [str(y) for y in seed_doc.get("defaultYears", [])]
    cases: list[BenchmarkCase] = []

    for seed in seed_doc.get("seeds", []):
        seed_years = seed.get("years", "all")
        if years_override:
            years = years_override
        elif seed_years == "all":
            years = default_years
        else:
            years = [str(y) for y in seed_years]

        raw_query = str(seed.get("query", ""))
        expected_outcome = str(seed.get("expectedOutcome", "success"))
        canonical = (
            canonicalize_query(raw_query).canonical_query
            if expected_outcome == "success"
            else raw_query
        )

        for year in years:
            cases.append(
                BenchmarkCase(
                    case_id=str(seed["id"]),
                    year=str(year),
                    query=canonical,
                    namespace_family=str(seed.get("namespaceFamily", "Unknown")),
                    expected_kind=str(seed.get("expectedKind", "unknown")),
                    expected_primary_symbol=str(seed.get("expectedPrimarySymbol", "")),
                    accepted_alternates=[str(v) for v in seed.get("acceptedAlternates", [])],
                    expected_outcome=expected_outcome,
                    must_contain_tokens=[str(v) for v in seed.get("mustContainTokens", [])],
                    forbidden_tokens=[str(v) for v in seed.get("forbiddenTokens", [])],
                )
            )

    return cases
