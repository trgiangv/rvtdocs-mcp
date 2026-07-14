from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ..server import rvtdocs_fetch
from .evaluator import evaluate_calibration, evaluate_case
from .reporter import aggregate, write_csv
from .seed_loader import expand_cases


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RVTDocs benchmark seed matrix")
    parser.add_argument("--seed-file", default="benchmarks/query-seeds.v1.json", help="Path to benchmark seed file")
    parser.add_argument("--out-dir", default="benchmarks/reports", help="Directory for report artifacts")
    parser.add_argument("--years", default="", help="Optional comma-separated year override, e.g. 2026,2027")
    parser.add_argument("--max-chars", type=int, default=1200)
    parser.add_argument("--mode", default="trust", choices=["trust", "full"])
    parser.add_argument(
        "--calibration-log",
        default="",
        help="Optional path to calibration_log.jsonl for confidence metrics in summary",
    )

    args = parser.parse_args()

    seed_path = Path(args.seed_file)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    seed_doc = json.loads(seed_path.read_text(encoding="utf-8"))
    years_override = [value.strip() for value in args.years.split(",") if value.strip()] or None
    cases = expand_cases(seed_doc, years_override)

    rows = []
    for case in cases:
        result = rvtdocs_fetch(query=case.query, year=case.year, max_chars=args.max_chars, mode=args.mode)
        rows.append(evaluate_case(case, result))

    summary = aggregate(rows)
    calibration_log = Path(args.calibration_log) if args.calibration_log else None
    calibration = evaluate_calibration(calibration_log)
    if calibration.get("eventCount"):
        summary["calibration"] = calibration

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    base_name = f"benchmark-{timestamp}"

    detail_path = out_dir / f"{base_name}.details.json"
    csv_path = out_dir / f"{base_name}.rows.csv"
    summary_path = out_dir / f"{base_name}.summary.json"

    detail_path.write_text(json.dumps(rows, ensure_ascii=True, indent=2), encoding="utf-8")
    write_csv(csv_path, rows)
    summary_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "seedFile": str(seed_path),
                "cases": len(rows),
                "summary": summary,
                "artifacts": {
                    "detailJson": str(detail_path),
                    "rowsCsv": str(csv_path),
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
