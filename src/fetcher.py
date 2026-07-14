import http.client
import time
import urllib.error
import urllib.request
from pathlib import Path

from .cache_store import SharedCache, get_shared_cache, is_fresh, is_negative_cached
from .config import DEFAULT_CACHE_TTL_SEC, DEFAULT_TIMEOUT_SEC, MAX_RETRIES, RETRY_BACKOFF_SECS, USER_AGENT
from .models import FetchResult


class PageFetcher:
    def __init__(self, cache_ttl_sec: int = DEFAULT_CACHE_TTL_SEC, cache_file: Path | None = None) -> None:
        self._cache_ttl_sec = max(0, cache_ttl_sec)
        self._cache = SharedCache(cache_file) if cache_file else get_shared_cache()

    def _try_cache(self, url: str) -> FetchResult | None:
        cached = self._cache.get(url)
        if cached is None:
            return None

        if int(cached.get("status", 0)) != 0 and is_fresh(cached, self._cache_ttl_sec):
            return FetchResult(
                ok=bool(cached.get("ok", False)),
                status=int(cached.get("status", 0)),
                elapsed_ms=0,
                content_length=int(cached.get("content_length", 0)),
                html=str(cached.get("html", "")),
                from_cache=True,
            )

        if is_negative_cached(cached):
            return FetchResult(
                ok=False,
                status=0,
                elapsed_ms=0,
                content_length=0,
                html="",
                from_cache=True,
                error_detail=str(cached.get("error_detail", "negative cache hit")),
            )

        return None

    def _do_fetch(self, url: str, timeout_sec: int) -> FetchResult:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Encoding": "identity",
                "Connection": "close",
            },
        )

        start = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=timeout_sec) as response:
                try:
                    raw_html = response.read()
                except http.client.IncompleteRead as error:
                    raw_html = error.partial or b""

                html = raw_html.decode("utf-8", errors="replace")
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                return FetchResult(
                    ok=200 <= response.status < 300 and len(html) > 0,
                    status=response.status,
                    elapsed_ms=elapsed_ms,
                    content_length=len(html),
                    html=html,
                    from_cache=False,
                )
        except urllib.error.HTTPError as error:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return FetchResult(
                ok=False,
                status=error.code,
                elapsed_ms=elapsed_ms,
                content_length=0,
                html="",
                from_cache=False,
                error_detail=str(error.reason),
            )
        except urllib.error.URLError as error:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return FetchResult(
                ok=False,
                status=0,
                elapsed_ms=elapsed_ms,
                content_length=0,
                html="",
                from_cache=False,
                error_detail=str(error.reason),
            )

    def fetch(self, url: str, timeout_sec: int = DEFAULT_TIMEOUT_SEC) -> FetchResult:
        cached = self._try_cache(url)
        if cached is not None:
            return cached

        last_result: FetchResult | None = None
        total_elapsed = 0

        for attempt in range(1 + MAX_RETRIES):
            result = self._do_fetch(url, timeout_sec)
            total_elapsed += result.elapsed_ms
            last_result = result

            if result.ok or result.status == 404:
                break

            if attempt < MAX_RETRIES and result.status == 0:
                backoff = RETRY_BACKOFF_SECS[min(attempt, len(RETRY_BACKOFF_SECS) - 1)]
                time.sleep(backoff)

        assert last_result is not None
        final = FetchResult(
            ok=last_result.ok,
            status=last_result.status,
            elapsed_ms=total_elapsed,
            content_length=last_result.content_length,
            html=last_result.html,
            from_cache=False,
            attempts_used=attempt + 1,
            retries_used=attempt,
            error_detail=last_result.error_detail,
        )

        cache_entry: dict = {
            "ok": final.ok,
            "status": final.status,
            "content_length": final.content_length,
            "html": final.html,
            "fetched_at": time.time(),
            "error_detail": final.error_detail,
        }
        self._cache.put(url, cache_entry)
        return final
