import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path

_logger = logging.getLogger(__name__)

from .config import (
    CACHE_TTL_BY_KIND,
    EVICT_BATCH_SIZE,
    MAX_CACHE_ENTRIES,
    NEGATIVE_CACHE_TTL_SEC,
)

_JSON_SUFFIX = ".json"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    url          TEXT PRIMARY KEY,
    ok           INTEGER NOT NULL DEFAULT 0,
    status       INTEGER NOT NULL DEFAULT 0,
    content_len  INTEGER NOT NULL DEFAULT 0,
    html         TEXT NOT NULL DEFAULT '',
    fetched_at   REAL NOT NULL DEFAULT 0,
    error_detail TEXT NOT NULL DEFAULT '',
    access_count INTEGER NOT NULL DEFAULT 1,
    last_access  REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_last_access ON cache(last_access);
"""


def default_cache_file() -> Path:
    env_path = os.getenv("RVTDOCS_MCP_CACHE_FILE")
    if env_path:
        path = Path(env_path).expanduser()
        if path.suffix == _JSON_SUFFIX:
            return path.with_suffix(".db")
        return path

    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "rvtdocs-mcp" / "cache.db"

    return Path.home() / ".rvtdocs-mcp" / "cache.db"


def _resolve_db_path(cache_file: Path) -> Path:
    if cache_file.suffix == _JSON_SUFFIX:
        return cache_file.with_suffix(".db")
    return cache_file


def _json_cache_path_for(db_path: Path, cache_file: Path | None = None) -> Path:
    if cache_file is not None and cache_file.suffix == _JSON_SUFFIX:
        return cache_file

    env_path = os.getenv("RVTDOCS_MCP_CACHE_FILE")
    if env_path:
        path = Path(env_path).expanduser()
        if path.suffix == _JSON_SUFFIX:
            return path

    return db_path.with_suffix(_JSON_SUFFIX)


def is_fresh(entry: dict, ttl_sec: int | None = None, *, kind: str | None = None) -> bool:
    if ttl_sec is None:
        if kind is not None:
            ttl_sec = CACHE_TTL_BY_KIND.get(kind, CACHE_TTL_BY_KIND["default"])
        else:
            ttl_sec = CACHE_TTL_BY_KIND["default"]

    fetched_at = float(entry.get("fetched_at", 0))
    if fetched_at <= 0:
        return False
    return (time.time() - fetched_at) <= ttl_sec


def is_negative_cached(entry: dict) -> bool:
    """Check if a failed fetch is still within the negative cache window."""
    if entry.get("ok", False) or int(entry.get("status", 0)) != 0:
        return False
    return is_fresh(entry, NEGATIVE_CACHE_TTL_SEC)


def _entry_from_row(row: sqlite3.Row) -> dict:
    return {
        "ok": bool(row["ok"]),
        "status": int(row["status"]),
        "content_length": int(row["content_len"]),
        "html": str(row["html"]),
        "fetched_at": float(row["fetched_at"]),
        "error_detail": str(row["error_detail"]),
    }


def _migrate_json_to_sqlite(conn: sqlite3.Connection, json_path: Path) -> None:
    if not json_path.exists():
        return

    row = conn.execute("SELECT COUNT(*) FROM cache").fetchone()
    if row is not None and int(row[0]) > 0:
        return

    try:
        raw = json_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return
    except Exception:
        return

    now = time.time()
    conn.execute("BEGIN")
    try:
        for url, entry in data.items():
            if not isinstance(entry, dict):
                continue

            fetched_at = float(entry.get("fetched_at", now))
            conn.execute(
                """
                INSERT OR IGNORE INTO cache (
                    url, ok, status, content_len, html, fetched_at, error_detail, access_count, last_access
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    str(url),
                    int(bool(entry.get("ok", False))),
                    int(entry.get("status", 0)),
                    int(entry.get("content_length", 0)),
                    str(entry.get("html", "")),
                    fetched_at,
                    str(entry.get("error_detail", "")),
                    fetched_at,
                ),
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        return

    migrated_path = json_path.with_name(json_path.name + ".migrated")
    try:
        json_path.rename(migrated_path)
    except OSError as exc:
        _logger.warning("Could not rename migrated cache file %s: %s", json_path, exc)


class SharedCache:
    def __init__(self, cache_file: Path) -> None:
        self._db_path = _resolve_db_path(cache_file)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        with self._db_lock:
            self._conn.executescript(_SCHEMA)
            self._conn.execute("PRAGMA journal_mode=WAL")
            _migrate_json_to_sqlite(self._conn, _json_cache_path_for(self._db_path, cache_file))

    def get(self, url: str) -> dict | None:
        with self._db_lock:
            row = self._conn.execute(
                """
                SELECT ok, status, content_len, html, fetched_at, error_detail
                FROM cache
                WHERE url = ?
                """,
                (url,),
            ).fetchone()
            if row is None:
                return None

            now = time.time()
            self._conn.execute(
                "UPDATE cache SET access_count = access_count + 1, last_access = ? WHERE url = ?",
                (now, url),
            )
            return _entry_from_row(row)

    def put(self, url: str, entry: dict) -> None:
        now = time.time()
        fetched_at = float(entry.get("fetched_at", now))
        with self._db_lock:
            self._conn.execute(
                """
                INSERT INTO cache (
                    url, ok, status, content_len, html, fetched_at, error_detail, access_count, last_access
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(url) DO UPDATE SET
                    ok = excluded.ok,
                    status = excluded.status,
                    content_len = excluded.content_len,
                    html = excluded.html,
                    fetched_at = excluded.fetched_at,
                    error_detail = excluded.error_detail,
                    access_count = cache.access_count + 1,
                    last_access = excluded.last_access
                """,
                (
                    url,
                    int(bool(entry.get("ok", False))),
                    int(entry.get("status", 0)),
                    int(entry.get("content_length", 0)),
                    str(entry.get("html", "")),
                    fetched_at,
                    str(entry.get("error_detail", "")),
                    now,
                ),
            )
            self._maybe_evict()

    def stats(self) -> dict:
        with self._db_lock:
            row = self._conn.execute(
                """
                SELECT
                    COUNT(*) AS entry_count,
                    COALESCE(SUM(content_len), 0) AS total_content_bytes,
                    COALESCE(MIN(fetched_at), 0) AS oldest_fetched_at,
                    COALESCE(MAX(fetched_at), 0) AS newest_fetched_at
                FROM cache
                """
            ).fetchone()
        assert row is not None
        return {
            "entry_count": int(row["entry_count"]),
            "total_content_bytes": int(row["total_content_bytes"]),
            "oldest_fetched_at": float(row["oldest_fetched_at"]),
            "newest_fetched_at": float(row["newest_fetched_at"]),
        }

    def _maybe_evict(self) -> None:
        row = self._conn.execute("SELECT COUNT(*) FROM cache").fetchone()
        count = int(row[0]) if row is not None else 0
        if count <= MAX_CACHE_ENTRIES:
            return

        self._conn.execute(
            """
            DELETE FROM cache
            WHERE url IN (
                SELECT url FROM cache ORDER BY last_access ASC LIMIT ?
            )
            """,
            (EVICT_BATCH_SIZE,),
        )


_shared_cache: SharedCache | None = None
_cache_lock = threading.Lock()


def get_shared_cache() -> SharedCache:
    global _shared_cache
    if _shared_cache is None:
        with _cache_lock:
            if _shared_cache is None:
                _shared_cache = SharedCache(default_cache_file())
    return _shared_cache
