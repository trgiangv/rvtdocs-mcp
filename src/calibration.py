from __future__ import annotations

import json
import os
import time
from pathlib import Path

_MAX_LOG_BYTES = 10 * 1024 * 1024


def default_calibration_log_file() -> Path:
    env_path = os.getenv("RVTDOCS_MCP_CALIBRATION_LOG")
    if env_path:
        return Path(env_path).expanduser()

    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "rvtdocs-mcp" / "calibration_log.jsonl"

    return Path.home() / ".rvtdocs-mcp" / "calibration_log.jsonl"


def _rotate_if_needed(log_file: Path) -> None:
    try:
        if log_file.exists() and log_file.stat().st_size >= _MAX_LOG_BYTES:
            rotated = log_file.with_name(
                f"calibration_log.{int(time.time())}.jsonl"
            )
            log_file.rename(rotated)
    except Exception:
        pass


def log_calibration_event(
    query: str,
    kind: str,
    confidence: float,
    evidence: list[str],
    reason_code: str,
    actual_match: bool,
    snippet_source: str = "compact",
    *,
    log_file: Path | None = None,
) -> None:
    """Append calibration data to JSONL file for offline analysis."""
    try:
        target = log_file or default_calibration_log_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        _rotate_if_needed(target)

        record = {
            "ts": int(time.time()),
            "query": query,
            "kind": kind,
            "confidence": round(confidence, 4),
            "evidence": list(evidence),
            "reasonCode": reason_code,
            "actualMatch": actual_match,
            "snippetSource": snippet_source,
        }
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
    except Exception:
        pass
