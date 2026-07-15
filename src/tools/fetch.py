"""rvtdocs_fetch tool: fetch detailed documentation for a specific API page.

Accepts a direct URL (from rvtdocs_search results) and returns parsed content.
"""
from __future__ import annotations

from ..config import BASE_URL, DEFAULT_MAX_CHARS
from ..extractor import extract_page_content
from ..fetcher import get_fetcher


async def rvtdocs_fetch(
    url: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    mode: str = "full",
) -> dict:
    """Fetch detailed Revit API documentation for a specific page.

    Use rvtdocs_search first to find relevant APIs, then use this tool
    with the URL from search results to get full documentation.

    Args:
        url: URL or path from rvtdocs_search results
             (e.g. "https://rvtdocs.com/2025/Autodesk.Revit.DB.Wall.Create(...)")
        max_chars: Maximum characters for snippet extraction
        mode: "full" (default) includes snippet, "lean" omits snippet
    """
    url = (url or "").strip()
    if not url:
        return {"success": False, "error": "Empty URL"}

    full_url = url if url.startswith("http") else f"{BASE_URL}{url}"

    fetcher = get_fetcher()
    try:
        result = await fetcher.fetch(full_url)
    except Exception as e:
        return {"success": False, "url": full_url, "error": str(e)}

    if not result.ok:
        return {
            "success": False,
            "url": full_url,
            "status": result.status,
            "error": result.error_detail or f"HTTP {result.status}",
        }

    extracted = extract_page_content(result.html, max_chars)

    payload: dict = {
        "success": True,
        "url": full_url,
        "http": {
            "status": result.status,
            "elapsedMs": result.elapsed_ms,
            "fromCache": result.from_cache,
        },
    }

    if mode != "lean":
        payload["snippet"] = extracted.snippet
    payload["sections"] = extracted.sections

    return payload


def register(app):
    app.tool()(rvtdocs_fetch)
