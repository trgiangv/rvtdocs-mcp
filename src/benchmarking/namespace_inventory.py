from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE_URL = "https://rvtdocs.com"
DEFAULT_YEARS = ["2022", "2023", "2024", "2025", "2026", "2027"]
LINK_PATTERN_TEMPLATE = r"href=[\"']/{year}/(Autodesk\.Revit\.[A-Za-z0-9_.]+)[\"']"


def _fetch_year_root(client: httpx.Client, year: str) -> str:
    response = client.get(f"{BASE_URL}/{year}/")
    response.raise_for_status()
    return response.text


def _extract_namespaces(html: str, year: str) -> dict[str, int]:
    pattern = re.compile(LINK_PATTERN_TEMPLATE.format(year=year), flags=re.ASCII)
    symbols = set(pattern.findall(html))

    # Year root pages list namespaces directly; keep only namespace-like links.
    namespaces = {symbol for symbol in symbols if symbol.count(".") <= 3}
    return dict.fromkeys(sorted(namespaces), 0)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture RVTDocs namespace inventory across years")
    parser.add_argument("--years", default=",".join(DEFAULT_YEARS), help="Comma-separated years")
    parser.add_argument("--out-dir", default="benchmarks/reports", help="Directory for report artifacts")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS certificate validation")
    args = parser.parse_args()

    years = [value.strip() for value in args.years.split(",") if value.strip()]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    per_year: dict[str, dict[str, int]] = {}
    errors: dict[str, str] = {}

    with httpx.Client(follow_redirects=True, verify=not args.insecure, timeout=20.0) as client:
        for year in years:
            try:
                html = _fetch_year_root(client, year)
                per_year[year] = _extract_namespaces(html, year)
            except Exception as error:  # pragma: no cover - network dependent
                errors[year] = str(error)
                per_year[year] = {}

    baseline_year = years[-1] if years else ""
    baseline_set = set(per_year.get(baseline_year, {}).keys())

    summary = {
        "years": years,
        "baselineYear": baseline_year,
        "countsByYear": {year: len(per_year.get(year, {})) for year in years},
        "missingVsBaseline": {
            year: sorted(baseline_set - set(per_year.get(year, {}).keys())) for year in years
        },
        "newVsBaseline": {
            year: sorted(set(per_year.get(year, {}).keys()) - baseline_set) for year in years
        },
        "errors": errors,
    }

    report = {
        "summary": summary,
        "namespacesByYear": {
            year: [
                {"namespace": namespace, "members": members}
                for namespace, members in sorted(per_year.get(year, {}).items())
            ]
            for year in years
        },
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    report_path = out_dir / f"namespace-inventory-{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "summary": summary,
                "artifact": str(report_path),
            },
            ensure_ascii=True,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
