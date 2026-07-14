from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..calibration import default_calibration_log_file
from ..confidence_config import get_confidence_config


def _read_calibration_events(log_path: Path | None = None) -> list[dict[str, Any]]:
    target = log_path or default_calibration_log_file()
    if not target.exists():
        return []

    events: list[dict[str, Any]] = []
    try:
        for line in target.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                events.append(parsed)
    except Exception:
        return []

    return events


def compute_calibration_metrics(
    log_path: Path | None = None,
    *,
    pass_threshold: float | None = None,
) -> dict[str, Any]:
    """Compute accuracy / precision / recall / F1 from calibration log events."""
    events = _read_calibration_events(log_path)
    threshold = (
        pass_threshold
        if pass_threshold is not None
        else get_confidence_config().thresholds.pass_min
    )

    if not events:
        return {
            "eventCount": 0,
            "passThreshold": threshold,
            "accuracy": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "truePositives": 0,
            "trueNegatives": 0,
            "falsePositives": 0,
            "falseNegatives": 0,
        }

    tp = tn = fp = fn = 0
    for event in events:
        predicted = float(event.get("confidence", 0.0)) >= threshold
        actual = bool(event.get("actualMatch", False))
        if predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
        elif not predicted and actual:
            fn += 1
        else:
            tn += 1

    total = tp + tn + fp + fn
    accuracy = (tp + tn) / total if total else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return {
        "eventCount": len(events),
        "passThreshold": threshold,
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "truePositives": tp,
        "trueNegatives": tn,
        "falsePositives": fp,
        "falseNegatives": fn,
    }
