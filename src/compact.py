import os
import re


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _strip_html_basic(html: str) -> str:
    without_script = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    without_style = re.sub(r"<style[\s\S]*?</style>", " ", without_script, flags=re.IGNORECASE)
    without_tags = re.sub(r"<[^>]+>", " ", without_style)
    decoded = (
        without_tags.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
    )
    return _compact_text(decoded)


def _extract_with_trafilatura(html: str) -> str | None:
    try:
        import trafilatura  # type: ignore

        content = trafilatura.extract(html)
        if content and content.strip():
            return _compact_text(content)
    except Exception:
        return None
    return None


def _extract_with_readability(html: str) -> str | None:
    try:
        from readability import Document  # type: ignore

        summary_html = Document(html).summary()
        if summary_html and summary_html.strip():
            return _strip_html_basic(summary_html)
    except Exception:
        return None
    return None


def _extract_with_selectolax(html: str) -> str | None:
    try:
        from selectolax.lexbor import LexborHTMLParser  # type: ignore

        tree = LexborHTMLParser(html)
        text = tree.text(separator=" ")
        if text and text.strip():
            return _compact_text(text)
    except Exception:
        return None
    return None


def extract_compact_text(html: str) -> tuple[str, dict]:
    raw_text = _strip_html_basic(html)
    mode = os.getenv("RVTDOCS_MCP_PARSER_MODE", "auto").strip().lower()

    backend = "builtin"
    compact_text = raw_text

    if mode in {"auto", "trafilatura"}:
        content = _extract_with_trafilatura(html)
        if content:
            backend = "trafilatura"
            compact_text = content

    if backend == "builtin" and mode in {"auto", "readability"}:
        content = _extract_with_readability(html)
        if content:
            backend = "readability-lxml"
            compact_text = content

    if backend == "builtin" and mode in {"auto", "selectolax"}:
        content = _extract_with_selectolax(html)
        if content:
            backend = "selectolax"
            compact_text = content

    raw_chars = len(raw_text)
    clean_chars = len(compact_text)
    reduction_ratio = 0.0
    if raw_chars > 0:
        reduction_ratio = max(0.0, 1.0 - (clean_chars / raw_chars))

    meta = {
        "parserBackend": backend,
        "rawChars": raw_chars,
        "cleanChars": clean_chars,
        "reductionRatio": round(reduction_ratio, 4),
        "parserMode": mode,
    }
    return compact_text, meta
