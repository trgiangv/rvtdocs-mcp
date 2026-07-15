"""Extract structured content from rvtdocs.com HTML pages."""
from __future__ import annotations

from dataclasses import dataclass, field

import trafilatura

from .config import DEFAULT_MAX_CHARS


@dataclass
class ExtractionResult:
    snippet: str = ""
    sections: list[str] = field(default_factory=list)


def extract_page_content(html: str, max_chars: int = DEFAULT_MAX_CHARS) -> ExtractionResult:
    """Extract readable text content from an rvtdocs.com HTML page."""
    if not html:
        return ExtractionResult()

    text = trafilatura.extract(
        html,
        include_tables=True,
        include_links=False,
        include_images=False,
        favor_precision=True,
    )

    if not text:
        return ExtractionResult()

    snippet = text[:max_chars] if len(text) > max_chars else text

    sections: list[str] = []
    for marker in ("Synopsis", "Parameters", "Return Value", "Remarks",
                   "Properties", "Methods", "Constructors", "Exceptions",
                   "Inheritance", "Namespace", "Events", "Fields"):
        if marker in text:
            sections.append(marker)

    return ExtractionResult(snippet=snippet, sections=sections)
