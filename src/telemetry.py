from __future__ import annotations

import json
import os
import threading
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import TELEMETRY_ENABLED, TELEMETRY_LOG_DIR

_MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
_MAX_LOG_FILES = 3
_LOG_FILENAME = "telemetry.jsonl"


def _default_log_dir() -> Path:
    if TELEMETRY_LOG_DIR:
        return Path(TELEMETRY_LOG_DIR).expanduser()

    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "rvtdocs-mcp"

    return Path.home() / ".rvtdocs-mcp"


@dataclass
class ToolEvent:
    timestamp: str
    tool: str
    query: str
    year: str
    mode: str
    success: bool
    confidence: float
    reason_code: str
    elapsed_ms: int
    from_cache: bool
    output_chars: int
    snippet_source: str


class TelemetryLogger:
    """Append-only JSONL logger with rotation."""

    def __init__(self, log_dir: Path | None = None) -> None:
        self._dir = log_dir or _default_log_dir()
        self._lock = threading.Lock()

    def _log_file(self) -> Path:
        return self._dir / _LOG_FILENAME

    def _rotate_files(self, log_file: Path) -> None:
        oldest = log_file.parent / f"{log_file.name}.{_MAX_LOG_FILES}"
        if oldest.exists():
            oldest.unlink()

        for index in range(_MAX_LOG_FILES - 1, 0, -1):
            source = log_file.parent / f"{log_file.name}.{index}"
            if not source.exists():
                continue
            target = log_file.parent / f"{log_file.name}.{index + 1}"
            source.rename(target)

        log_file.rename(log_file.parent / f"{log_file.name}.1")

    def _rotate_if_needed(self, log_file: Path) -> None:
        if log_file.exists() and log_file.stat().st_size >= _MAX_LOG_SIZE:
            self._rotate_files(log_file)

    def log(self, event: ToolEvent) -> None:
        """Log event. Never raises."""
        if not TELEMETRY_ENABLED:
            return

        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            log_file = self._log_file()

            with self._lock:
                self._rotate_if_needed(log_file)
                with log_file.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(asdict(event), ensure_ascii=True) + "\n")
        except Exception:
            pass

    def log_async(self, event: ToolEvent) -> None:
        """Fire-and-forget logging on a background thread. Never raises."""
        if not TELEMETRY_ENABLED:
            return

        try:
            threading.Thread(target=self.log, args=(event,), daemon=True).start()
        except Exception:
            pass

    def _iter_log_files(self) -> list[Path]:
        log_file = self._log_file()
        files = [log_file]
        for index in range(1, _MAX_LOG_FILES + 1):
            rotated = log_file.parent / f"{log_file.name}.{index}"
            if rotated.exists():
                files.append(rotated)
        return files

    def _parse_timestamp(self, value: str) -> float | None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.timestamp()
        except Exception:
            return None

    def _read_events(self, hours: int) -> list[dict]:
        cutoff = time.time() - (hours * 3600)
        events: list[dict] = []

        for log_file in self._iter_log_files():
            try:
                with log_file.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        timestamp = self._parse_timestamp(str(record.get("timestamp", "")))
                        if timestamp is None or timestamp < cutoff:
                            continue
                        events.append(record)
            except Exception:
                continue

        return events

    def query_stats(self, hours: int = 24) -> dict:
        """Compute usage stats from recent events."""
        hours = max(1, int(hours))
        events = self._read_events(hours)

        if not events:
            return {
                "period": f"{hours}h",
                "totalCalls": 0,
                "byTool": {},
                "successRate": 0.0,
                "avgConfidence": 0.0,
                "avgLatencyMs": 0.0,
                "cacheHitRate": 0.0,
                "topQueries": [],
                "topFailures": [],
            }

        total_calls = len(events)
        successes = sum(1 for event in events if event.get("success"))
        confidences = [float(event.get("confidence", 0.0)) for event in events]
        latencies = [int(event.get("elapsed_ms", 0) or 0) for event in events]
        cache_hits = sum(1 for event in events if event.get("from_cache"))

        by_tool: Counter[str] = Counter()
        for event in events:
            tool = str(event.get("tool", "unknown"))
            short_name = tool.removeprefix("rvtdocs_")
            by_tool[short_name] += 1

        query_counts: Counter[str] = Counter()
        for event in events:
            query = str(event.get("query", "")).strip()
            if query:
                query_counts[query] += 1

        failure_counts: Counter[str] = Counter()
        for event in events:
            if event.get("success"):
                continue
            reason = str(event.get("reason_code", "unknown"))
            failure_counts[reason] += 1

        return {
            "period": f"{hours}h",
            "totalCalls": total_calls,
            "byTool": dict(by_tool),
            "successRate": round(successes / total_calls, 4),
            "avgConfidence": round(sum(confidences) / total_calls, 4),
            "avgLatencyMs": round(sum(latencies) / total_calls, 1),
            "cacheHitRate": round(cache_hits / total_calls, 4),
            "topQueries": [
                {"query": query, "count": count}
                for query, count in query_counts.most_common(10)
            ],
            "topFailures": [
                {"reasonCode": reason, "count": count}
                for reason, count in failure_counts.most_common(5)
            ],
        }


def build_tool_event(
    *,
    tool: str,
    query: str,
    year: str,
    mode: str,
    payload: dict,
    snippet_source: str = "none",
) -> ToolEvent:
    trust = payload.get("trust") or {}
    http = payload.get("http") or {}
    return ToolEvent(
        timestamp=datetime.now(UTC).isoformat(),
        tool=tool,
        query=query,
        year=year,
        mode=mode,
        success=bool(payload.get("success")),
        confidence=float(trust.get("confidence", 0.0)),
        reason_code=str(trust.get("reasonCode", "")),
        elapsed_ms=int(http.get("elapsedMs", 0) or 0),
        from_cache=bool(http.get("fromCache", False)),
        output_chars=int(payload.get("token_output_chars", 0) or 0),
        snippet_source=snippet_source,
    )
