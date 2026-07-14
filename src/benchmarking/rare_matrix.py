from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ..server import rvtdocs_fetch
from ..routing import canonicalize_query

DEFAULT_YEARS = ["2022", "2023", "2024", "2025", "2026", "2027"]

QUERIES_BY_DOMAIN: dict[str, list[str]] = {
    "DirectContext3D": [
        "Autodesk.Revit.DB.DirectContext3D",
        "IDirectContext3DServer",
        "DrawContext",
    ],
    "Geometry": [
        "Solid",
        "CurveLoop",
        "TessellatedShapeBuilder",
        "BRepBuilder",
    ],
    "FamilyEditor": [
        "FamilyManager",
        "FamilyType",
        "Autodesk.Revit.Creation.Document",
        "Document.NewFamilyInstance",
    ],
    "ExtensibleStorage": [
        "Autodesk.Revit.DB.ExtensibleStorage",
        "SchemaBuilder.SetSchemaName",
        "Entity.Set",
    ],
    "SystemAnalysisBuildingEnergy": [
        "Autodesk.Revit.DB.Analysis",
        "EnergyAnalysisDetailModel",
        "Autodesk.Revit.DB.Analysis.AnalysisResultSchema",
    ],
    "ExternalServer": [
        "Autodesk.Revit.DB.ExternalService",
        "ExternalServiceRegistry",
        "ExternalServiceRegistry.GetService",
    ],
    "Fabrication": [
        "Autodesk.Revit.DB.Fabrication",
        "FabricationPart",
        "FabricationService",
    ],
    "IFC": [
        "Autodesk.Revit.DB.IFC",
        "IFCImportOptions",
        "IFCExportOptions",
    ],
    "Steel": [
        "Autodesk.Revit.DB.Steel",
        "SteelElementProperties",
        "StructuralConnectionHandler",
    ],
}

_RARE_EXACT_QUERY_REWRITES: dict[str, str] = {
    # Keep only safe disambiguations for intentionally ambiguous short queries.
    "Document.NewFamilyInstance": "Autodesk.Revit.Creation.Document.NewFamilyInstance",
    "StructuralConnectionHandler": "Autodesk.Revit.DB.Structure.StructuralConnectionHandler",
}


def _canonicalize_for_rare_matrix(query: str) -> tuple[str, bool]:
    # Start from minimal production canonicalization, then apply benchmark-only domain rewrites.
    base = canonicalize_query(query)
    rewritten = _RARE_EXACT_QUERY_REWRITES.get(base.canonical_query)
    if rewritten is not None:
        return rewritten, rewritten != query

    return base.canonical_query, base.rewritten


def _collect_rows(years: list[str], max_chars: int, mode: str) -> list[dict]:
    rows: list[dict] = []
    for domain, queries in QUERIES_BY_DOMAIN.items():
        for query in queries:
            canonical_query, rewritten = _canonicalize_for_rare_matrix(query)
            for year in years:
                result = rvtdocs_fetch(query=canonical_query, year=year, max_chars=max_chars, mode=mode)
                http = result.get("http") or {}
                trust = result.get("trust") or {}
                rows.append(
                    {
                        "domain": domain,
                        "query": query,
                        "canonicalQuery": canonical_query,
                        "rewritten": rewritten,
                        "year": year,
                        "success": bool(result.get("success")),
                        "reasonCode": str(http.get("reasonCode", "")),
                        "status": int(http.get("status", 0) or 0),
                        "confidence": float(trust.get("confidence", 0.0) or 0.0),
                        "elapsedMs": int(http.get("elapsedMs", 0) or 0),
                        "tokenHintChars": int(result.get("token_hint_chars", 0) or 0),
                        "tokenOutputChars": int(result.get("token_output_chars", 0) or 0),
                        "path": str((result.get("resolved") or {}).get("path", "")),
                    }
                )
    return rows


def _summarize_rows(rows: list[dict]) -> dict:
    summary = {}
    for domain in QUERIES_BY_DOMAIN:
        items = [row for row in rows if row["domain"] == domain]
        total = len(items)
        success = sum(1 for row in items if row["success"])
        by_reason = defaultdict(int)
        for row in items:
            by_reason[row["reasonCode"]] += 1

        summary[domain] = {
            "cases": total,
            "successRate": (success / total) if total else 0.0,
            "avgConfidence": (sum(row["confidence"] for row in items) / total) if total else 0.0,
            "avgElapsedMs": (sum(row["elapsedMs"] for row in items) / total) if total else 0.0,
            "avgTokenHintChars": (sum(row["tokenHintChars"] for row in items) / total) if total else 0.0,
            "reasonCodes": dict(sorted(by_reason.items(), key=lambda kv: (-kv[1], kv[0]))),
        }

    return {
        "totalCases": len(rows),
        "globalSuccessRate": sum(1 for row in rows if row["success"]) / len(rows) if rows else 0.0,
        "globalAvgTokenHintChars": sum(row["tokenHintChars"] for row in rows) / len(rows) if rows else 0.0,
        "domains": summary,
    }


def _write_artifacts(rows: list[dict], report: dict, out_dir: Path) -> tuple[Path, Path]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    details_path = out_dir / f"rare-api-matrix-{stamp}.details.json"
    summary_path = out_dir / f"rare-api-matrix-{stamp}.summary.json"

    details_path.write_text(json.dumps(rows, ensure_ascii=True, indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    return details_path, summary_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run rare-domain API exploration matrix")
    parser.add_argument("--out-dir", default="benchmarks/reports", help="Directory for report artifacts")
    parser.add_argument("--years", default=",".join(DEFAULT_YEARS), help="Comma-separated years")
    parser.add_argument("--max-chars", type=int, default=1200)
    parser.add_argument("--mode", default="trust", choices=["trust", "full"])
    args = parser.parse_args()

    years = [value.strip() for value in args.years.split(",") if value.strip()]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = _collect_rows(years=years, max_chars=args.max_chars, mode=args.mode)
    report = _summarize_rows(rows)
    details_path, summary_path = _write_artifacts(rows=rows, report=report, out_dir=out_dir)

    print(
        json.dumps(
            {
                "summary": report,
                "artifacts": {
                    "detailJson": str(details_path),
                    "summaryJson": str(summary_path),
                },
            },
            ensure_ascii=True,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
