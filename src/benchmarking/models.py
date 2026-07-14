from dataclasses import dataclass


@dataclass
class BenchmarkCase:
    case_id: str
    year: str
    query: str
    namespace_family: str
    expected_kind: str
    expected_primary_symbol: str
    accepted_alternates: list[str]
    expected_outcome: str
    must_contain_tokens: list[str]
    forbidden_tokens: list[str]
