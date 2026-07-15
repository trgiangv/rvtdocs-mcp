"""HTTP page fetcher with caching for rvtdocs.com pages."""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from .cache_store import SharedCache, get_shared_cache
from .config import DEFAULT_TIMEOUT_SEC, USER_AGENT

_HTTP_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Encoding": "identity",
}


@dataclass
class FetchResult:
    ok: bool
    status: int
    elapsed_ms: int
    html: str
    from_cache: bool
    error_detail: str = ""


class PageFetcher:
    def __init__(self) -> None:
        self._cache: SharedCache = get_shared_cache()

    async def fetch(self, url: str, timeout_sec: int = DEFAULT_TIMEOUT_SEC) -> FetchResult:
        cached = self._try_cache(url)
        if cached is not None:
            return cached
        return await self._do_fetch(url, timeout_sec)

    def _try_cache(self, url: str) -> FetchResult | None:
        entry = self._cache.get(url)
        if entry is None:
            return None
        return FetchResult(
            ok=entry["ok"],
            status=entry["status"],
            elapsed_ms=0,
            html=entry.get("html", ""),
            from_cache=True,
        )

    async def _do_fetch(self, url: str, timeout_sec: int) -> FetchResult:
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                headers=_HTTP_HEADERS,
                timeout=httpx.Timeout(timeout_sec),
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
            html = response.text
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            status = response.status_code
            ok = 200 <= status < 300 and len(html) > 0

            self._cache.put(url, {"ok": ok, "status": status, "html": html})

            return FetchResult(
                ok=ok,
                status=status,
                elapsed_ms=elapsed_ms,
                html=html,
                from_cache=False,
                error_detail="" if ok else response.reason_phrase,
            )
        except httpx.HTTPError as error:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return FetchResult(
                ok=False,
                status=0,
                elapsed_ms=elapsed_ms,
                html="",
                from_cache=False,
                error_detail=str(error),
            )


_global_fetcher: PageFetcher | None = None


def get_fetcher() -> PageFetcher:
    global _global_fetcher
    if _global_fetcher is None:
        _global_fetcher = PageFetcher()
    return _global_fetcher
