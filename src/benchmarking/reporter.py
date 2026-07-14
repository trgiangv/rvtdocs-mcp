from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def rate(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    passed = sum(1 for row in rows if row.get(key))
    return passed / len(rows)


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_year: dict[str, list[dict[str, Any]]] = defaultdict(list)
    reasons = Counter()

    for row in rows:
        by_family[str(row["namespaceFamily"])].append(row)
        by_year[str(row["year"])].append(row)
        reasons[str(row["reasonCode"]) or "unknown"] += 1

    return {
        "totalCases": len(rows),
        "finalSuccessRate": rate(rows, "finalOk"),
        "resolverAccuracy": rate(rows, "resolverOk"),
        "semanticPassRate": rate(rows, "semanticOk"),
        "outcomePassRate": rate(rows, "outcomeOk"),
        "networkErrorRate": sum(1 for row in rows if row.get("reasonCode") == "network_error") / len(rows)
        if rows
        else 0.0,
        "retryNonZeroRate": sum(1 for row in rows if int(row.get("retriesUsed", 0)) > 0) / len(rows)
        if rows
        else 0.0,
        "byNamespaceFamily": {
            family: {
                "cases": len(items),
                "finalSuccessRate": rate(items, "finalOk"),
                "resolverAccuracy": rate(items, "resolverOk"),
            }
            for family, items in sorted(by_family.items())
        },
        "byYear": {
            year: {
                "cases": len(items),
                "finalSuccessRate": rate(items, "finalOk"),
                "resolverAccuracy": rate(items, "resolverOk"),
            }
            for year, items in sorted(by_year.items())
        },
        "topReasonCodes": reasons.most_common(10),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
