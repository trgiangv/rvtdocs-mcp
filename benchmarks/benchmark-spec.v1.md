# RVTDocs Benchmark Spec v1

## Purpose

Establish a repeatable, production-oriented benchmark contract before implementing resolver and matcher redesign.

## Dataset Scope

- Year matrix: 2022, 2023, 2024, 2025, 2026, 2027.
- Namespace families:
  - Autodesk.Revit.DB
  - Autodesk.Revit.UI
  - Autodesk.Revit.ApplicationServices
  - Autodesk.Revit.Attributes
  - Autodesk.Revit.Creation
  - Autodesk.Revit.Exceptions
- Intent categories:
  - namespace
  - class
  - method
  - method_overload
  - chain_method
  - member_or_property
  - news
  - root

## Seed Contract

Each seed item must provide:

- id: stable unique identifier.
- query: raw input query.
- namespaceFamily: family for aggregate reporting.
- expectedKind: intended symbol kind.
- expectedPrimarySymbol: canonical symbol path if applicable.
- acceptedAlternates: optional list of acceptable alternatives.
- expectedOutcome: one of success, ambiguous, not_found_expected.
- years: list of years or "all".
- mustContainTokens: optional semantic evidence terms.
- forbiddenTokens: optional anti-evidence terms.
- notes: optional comments.

Method-overload seeds should also provide:

- expectedSignatureArity (optional in v1 while parser is being upgraded).
- expectedParamTypesNormalized (optional in v1 while parser is being upgraded).
- expectedReturnType (optional in v1 while parser is being upgraded).

## Scoring Rules

1. Resolver Accuracy
- Pass if resolved path maps to expectedPrimarySymbol or acceptedAlternates.

2. Final Success Rate
- Pass if resolver check passes and tool reports success=true.

3. Overload Accuracy
- Applied to expectedKind=method_overload.
- v1 proxy mode: same as final pass until overload parser lands.

4. Ambiguity Quality
- For expectedOutcome=ambiguous, the run should not hard-success.
- Temporary pass criteria in v1: success=false and reasonCode in content_mismatch/not_found_fail_fast.

5. Retry Discipline
- retriesUsed should remain 0 for default mode.

## KPI Gates

- Global final success rate >= 90%.
- Per-namespace-family >= 85%.
- DB and UI each >= 90%.
- Overload accuracy >= 90% (proxy in v1, strict in v2).
- network_error <= 1% (excluding external outage windows).

## Output Artifacts

Each run emits:

- JSON detail report with all case rows.
- CSV tabular report for spreadsheet analysis.
- Aggregate summary including:
  - total cases
  - success rate
  - resolver accuracy
  - by-year matrix
  - by-family matrix
  - top failure reason codes

## Execution Protocol

1. Run full matrix over all seed entries and all years.
2. Execute at least 3 runs:
- cold cache
- warm cache
- warm cache repeat
3. Compare variance and investigate unstable clusters.
4. Do not tune semantic thresholds before resolver accuracy reaches 95%.

## Non-Goals (v1)

- Not validating natural-language QA quality outside symbol retrieval.
- Not introducing multi-retry behavior.
- Not adding non-rvtdocs external data sources.
