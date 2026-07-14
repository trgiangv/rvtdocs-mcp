from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from ..config import BASE_URL, DEFAULT_TIMEOUT_SEC, USER_AGENT
from ..routing.constants import DB_SUBNAMESPACES, NAMESPACE_TAILS

_DEFAULT_YEARS = ("2022", "2023", "2024", "2025", "2026", "2027")
_LINK_PATTERN_TEMPLATE = r'href=["\']/{year}/(Autodesk\.Revit\.[A-Za-z0-9_.]+)["\']'
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def canonical_namespace_tails() -> list[str]:
    """Map NAMESPACE_TAILS entries to resolver-style namespace tails."""
    tails: list[str] = []
    seen: set[str] = set()
    for tail in NAMESPACE_TAILS:
        canonical = f"DB.{tail}" if tail in DB_SUBNAMESPACES else tail
        if canonical not in seen:
            seen.add(canonical)
            tails.append(canonical)
    return tails


def namespace_tail_to_fqcn(namespace_tail: str) -> str:
    return f"Autodesk.Revit.{namespace_tail}"


def _fetch_html(url: str, timeout_sec: int = DEFAULT_TIMEOUT_SEC) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Encoding": "identity",
            "Connection": "close",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_sec) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_classes_from_namespace_page(html: str, year: str, namespace_tail: str) -> dict[str, str]:
    """Extract direct child class links from a namespace listing page."""
    prefix = f"Autodesk.Revit.{namespace_tail}."
    pattern = re.compile(_LINK_PATTERN_TEMPLATE.format(year=year), flags=re.ASCII)
    mapping: dict[str, str] = {}

    for fqcn in pattern.findall(html):
        if not fqcn.startswith(prefix):
            continue
        remainder = fqcn[len(prefix) :]
        if not remainder or "." in remainder:
            continue
        mapping[remainder] = namespace_tail

    return mapping


def scrape_year(year: str, *, delay_sec: float = 0.0) -> dict[str, str]:
    """Build class-name → namespace-tail mapping for one Revit year."""
    merged: dict[str, str] = {}
    conflicts: list[tuple[str, str, str]] = []

    for namespace_tail in canonical_namespace_tails():
        url = f"{BASE_URL}/{year}/{namespace_tail_to_fqcn(namespace_tail)}"
        try:
            html = _fetch_html(url)
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            continue

        page_mapping = extract_classes_from_namespace_page(html, year, namespace_tail)
        for class_name, tail in page_mapping.items():
            existing = merged.get(class_name)
            if existing and existing != tail:
                conflicts.append((class_name, existing, tail))
                continue
            merged[class_name] = tail

        if delay_sec > 0:
            time.sleep(delay_sec)

    if conflicts:
        sample = ", ".join(f"{name}: {left} vs {right}" for name, left, right in conflicts[:5])
        print(f"warning: {len(conflicts)} class namespace conflicts for {year}; sample: {sample}")

    return dict(sorted(merged.items()))


def write_index(year: str, mapping: dict[str, str], data_dir: Path | None = None) -> Path:
    target_dir = data_dir or _DATA_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = target_dir / f"namespace_index_{year}.json"
    output_path.write_text(json.dumps(mapping, ensure_ascii=True, indent=2), encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape RVTDocs namespace pages into class index files")
    parser.add_argument("--year", help="Single Revit year to scrape (for example 2025)")
    parser.add_argument("--years", help="Comma-separated years (default: 2022-2027)")
    parser.add_argument("--out-dir", default=str(_DATA_DIR), help="Directory for namespace_index_*.json files")
    parser.add_argument("--delay-sec", type=float, default=0.0, help="Optional delay between namespace page fetches")
    args = parser.parse_args()

    if args.year:
        years = [args.year.strip()]
    elif args.years:
        years = [value.strip() for value in args.years.split(",") if value.strip()]
    else:
        years = list(_DEFAULT_YEARS)

    out_dir = Path(args.out_dir)
    summary: dict[str, dict[str, object]] = {}

    for year in years:
        mapping = scrape_year(year, delay_sec=args.delay_sec)
        output_path = write_index(year, mapping, out_dir)
        summary[year] = {
            "classes": len(mapping),
            "artifact": str(output_path),
        }
        print(json.dumps({"year": year, "classes": len(mapping), "artifact": str(output_path)}, ensure_ascii=True))

    print(json.dumps({"summary": summary}, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
