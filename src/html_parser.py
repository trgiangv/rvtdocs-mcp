from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import DEFAULT_MAX_CHARS

_CARD_TOOLBAR_LABEL = ".card-toolbar-label"
_NONE_LABEL = "(none)"
_OBSOLETE_PATTERN = re.compile(r"\[Obsolete\]", flags=re.IGNORECASE)
_DEPRECATED_PATTERN = re.compile(r"\bDeprecated\b", flags=re.IGNORECASE)
def _strip_member_count(label: str) -> str:
    idx = label.rfind("(")
    if idx > 0 and label.rstrip().endswith(")"):
        return label[:idx].rstrip()
    return label
_WHITESPACE_PATTERN = re.compile(r"\s+")

_SECTION_LABELS = (
    "Syntax",
    "Parameters",
    "Return Value",
    "Remarks",
    "Exceptions",
    "See Also",
    "Properties",
    "Methods",
    "Constructors",
    "Inheritance Hierarchy",
    "Namespace",
    "Assembly",
    "Fields",
    "Events",
    "Classes",
    "Enumerations",
    "Interfaces",
    "Structures",
    "Examples",
)

@dataclass
class ApiMember:
    name: str
    return_type: str = ""
    description: str = ""
    is_obsolete: bool = False


@dataclass
class ApiParameter:
    name: str
    type: str = ""
    description: str = ""


@dataclass
class ApiPageStructure:
    title: str = ""
    synopsis: str = ""
    parameters: list[ApiParameter] = field(default_factory=list)
    returns: str = ""
    remarks: str = ""
    examples: list[str] = field(default_factory=list)
    see_also: list[str] = field(default_factory=list)
    sections_found: list[str] = field(default_factory=list)
    methods: list[ApiMember] = field(default_factory=list)
    properties: list[ApiMember] = field(default_factory=list)
    constructors: list[ApiMember] = field(default_factory=list)
    is_class_page: bool = False
    is_method_page: bool = False
    is_namespace_page: bool = False
    namespace_classes: list[str] = field(default_factory=list)


def _compact_text(text: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", text).strip()


def _node_text(node) -> str:
    if node is None:
        return ""
    try:
        text = node.text(separator=" ")
    except Exception:
        return ""
    return _compact_text(text)


def _strip_label_prefix(text: str, prefix: str) -> str:
    cleaned = text.strip()
    if cleaned.lower().startswith(prefix.lower()):
        cleaned = cleaned[len(prefix) :].lstrip(" :")
    return _compact_text(cleaned)


def _is_obsolete(*parts: str) -> bool:
    joined = " ".join(part for part in parts if part)
    return bool(_OBSOLETE_PATTERN.search(joined) or _DEPRECATED_PATTERN.search(joined))


def _normalize_section_label(label: str) -> str:
    cleaned = _strip_member_count(label).strip()
    for known in _SECTION_LABELS:
        if cleaned.lower() == known.lower():
            return known
    return cleaned


_REVIT_API_SUFFIX = " - Revit API"

def _strip_revit_api_suffix(title: str) -> str:
    idx = title.lower().rfind(_REVIT_API_SUFFIX.lower())
    if idx >= 0:
        return title[:idx].strip()
    return title.strip()


def _extract_title(tree) -> str:
    h1 = tree.css_first("h1")
    if h1 is not None:
        title = _node_text(h1)
        if title:
            return title

    title_tag = tree.css_first("title")
    if title_tag is not None:
        title = _node_text(title_tag)
        if title:
            return _strip_revit_api_suffix(title)

    breadcrumb = tree.css_first(".crumb-current")
    if breadcrumb is not None:
        return _node_text(breadcrumb)

    return ""


def _extract_labeled_block(tree, selector: str, label: str) -> str:
    node = tree.css_first(selector)
    if node is None:
        return ""
    return _strip_label_prefix(_node_text(node), label)


def _extract_syntax(tree) -> str:
    snippet = tree.css_first(".code-snippet:not(.hidden) pre code")
    if snippet is None:
        snippet = tree.css_first(".code-snippet pre code")
    if snippet is None:
        snippet = tree.css_first("pre code")
    return _node_text(snippet)


def _extract_param_rows(tree) -> list[ApiParameter]:
    parameters: list[ApiParameter] = []
    for row in tree.css(".params-card .param-row"):
        param_type = _node_text(row.css_first(".param-type"))
        param_name = _node_text(row.css_first(".param-name"))
        param_desc = _node_text(row.css_first(".param-desc"))
        if param_name or param_type:
            parameters.append(ApiParameter(name=param_name, type=param_type, description=param_desc))
    return parameters


def _parse_param_table_columns(headers: list[str]) -> tuple[int, int, int] | None:
    if not headers or "name" not in headers or "description" not in headers:
        return None
    name_idx = headers.index("name")
    type_idx = headers.index("type") if "type" in headers else -1
    desc_idx = headers.index("description")
    return name_idx, type_idx, desc_idx


def _parse_params_from_rows(rows, name_idx: int, type_idx: int, desc_idx: int) -> list[ApiParameter]:
    params: list[ApiParameter] = []
    min_cells = max(name_idx, desc_idx) + 1
    for row in rows:
        cells = row.css("td")
        if len(cells) < min_cells:
            continue
        param_name = _node_text(cells[name_idx])
        param_type = _node_text(cells[type_idx]) if 0 <= type_idx < len(cells) else ""
        param_desc = _node_text(cells[desc_idx])
        if param_name:
            params.append(ApiParameter(name=param_name, type=param_type, description=param_desc))
    return params


def _extract_params_from_tables(tree) -> list[ApiParameter]:
    for card in tree.css(".params-card"):
        for table in card.css("table"):
            headers = [_compact_text(_node_text(th)).lower() for th in table.css("th")]
            columns = _parse_param_table_columns(headers)
            if columns is None:
                continue
            params = _parse_params_from_rows(table.css("tbody tr"), *columns)
            if params:
                return params
    return []


def _extract_parameters(tree) -> list[ApiParameter]:
    parameters = _extract_param_rows(tree)
    if parameters:
        return parameters
    return _extract_params_from_tables(tree)


def _extract_returns(tree) -> str:
    return_row = tree.css_first(".return-row")
    if return_row is None:
        return ""

    return_type = _node_text(return_row.css_first(".return-type"))
    return_desc = _node_text(return_row.css_first(".return-desc"))
    if return_type and return_desc:
        return f"{return_type} - {return_desc}"
    return return_type or return_desc


def _extract_examples(tree) -> list[str]:
    examples: list[str] = []
    for card in tree.css(".card"):
        label = card.css_first(_CARD_TOOLBAR_LABEL)
        if label is None:
            continue
        section_name = _normalize_section_label(_node_text(label))
        if section_name.lower() != "examples":
            continue
        for block in card.css("pre code"):
            code = _node_text(block)
            if code:
                examples.append(code)
    return examples


def _extract_see_also(tree) -> list[str]:
    links: list[str] = []
    for card in tree.css(".card"):
        label = card.css_first(_CARD_TOOLBAR_LABEL)
        if label is None:
            continue
        section_name = _normalize_section_label(_node_text(label))
        if section_name.lower() != "see also":
            continue
        for anchor in card.css("a"):
            text = _node_text(anchor)
            if text:
                links.append(text)
    return links


def _member_name_from_row(row) -> str:
    anchor = row.css_first("a.member-name-link")
    if anchor is None:
        return _node_text(row.css_first(".td-name"))

    name = _node_text(anchor)
    params = row.css_first(".member-name-params")
    params_text = _node_text(params) if params is not None else ""
    if params_text and params_text not in name:
        name = f"{name}{params_text}"
    return name


def _member_return_type_from_row(row) -> str:
    ret_type = row.css_first(".member-ret-type")
    if ret_type is not None:
        return _node_text(ret_type)
    if row.css_first(".member-ret-none") is not None:
        return "None"
    return _node_text(row.css_first(".td-rt"))


def _parse_member_rows(rows) -> list[ApiMember]:
    members: list[ApiMember] = []
    for row in rows:
        name = _member_name_from_row(row)
        if not name:
            continue
        return_type = _member_return_type_from_row(row)
        description = _node_text(row.css_first(".td-desc"))
        members.append(
            ApiMember(
                name=name,
                return_type=return_type,
                description=description,
                is_obsolete=_is_obsolete(name, description),
            )
        )
    return members


def _extract_member_section(tree, section_label: str) -> list[ApiMember]:
    target = section_label.lower()
    for card in tree.css(".member-section-card, .card"):
        label = card.css_first(_CARD_TOOLBAR_LABEL)
        if label is None:
            continue
        section_name = _normalize_section_label(_node_text(label)).lower()
        if section_name != target:
            continue
        rows = card.css("table.member-section-table tbody tr")
        return _parse_member_rows(rows)
    return []


def _extract_namespace_classes(tree) -> list[str]:
    for card in tree.css(".member-section-card, .card"):
        label = card.css_first(_CARD_TOOLBAR_LABEL)
        if label is None:
            continue
        section_name = _normalize_section_label(_node_text(label)).lower()
        if section_name != "classes":
            continue
        classes: list[str] = []
        for row in card.css("table.member-section-table tbody tr"):
            anchor = row.css_first("a.member-name-link")
            if anchor is None:
                continue
            name = _node_text(anchor)
            if name:
                classes.append(name)
        return classes
    return []


def _detect_page_type(tree, structure: ApiPageStructure) -> None:
    page_type = ""
    page_type_node = tree.css_first(".crumb-pagetype")
    if page_type_node is not None:
        page_type = _node_text(page_type_node).lower()

    has_member_tables = bool(structure.methods or structure.properties or structure.constructors)
    has_parameters = bool(structure.parameters)
    has_namespace_classes = bool(structure.namespace_classes)

    structure.is_namespace_page = page_type == "namespace" or (
        has_namespace_classes and not has_member_tables and not has_parameters
    )
    structure.is_class_page = page_type == "class" or (
        has_member_tables and not structure.is_namespace_page
    )
    structure.is_method_page = page_type in {"method", "property"} or (
        not structure.is_class_page
        and not structure.is_namespace_page
        and (has_parameters or bool(structure.synopsis))
    )

    if structure.is_namespace_page:
        structure.is_method_page = False
        structure.is_class_page = False
    elif structure.is_class_page:
        structure.is_method_page = False


def _collect_sections(tree, structure: ApiPageStructure) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def add(label: str) -> None:
        normalized = _normalize_section_label(label)
        if not normalized or normalized.lower() in seen:
            return
        seen.add(normalized.lower())
        found.append(normalized)

    for label_node in tree.css(_CARD_TOOLBAR_LABEL):
        add(_node_text(label_node))

    if structure.remarks:
        add("Remarks")
    if structure.returns:
        add("Return Value")
    if structure.parameters:
        add("Parameters")
    if structure.synopsis and any(
        token in structure.synopsis.lower()
        for token in ("public ", "private ", "class ", "void ", "function ", "property ")
    ):
        add("Syntax")

    return found


def has_meaningful_structure(structure: ApiPageStructure) -> bool:
    """Return True when structured parsing found usable API content."""
    if structure.synopsis.strip():
        return True
    if structure.parameters:
        return True
    if structure.methods or structure.properties or structure.constructors:
        return True
    if structure.namespace_classes:
        return True
    return False


def _extract_synopsis(tree) -> str:
    description = _extract_labeled_block(tree, ".card-description", "Description:")
    syntax = _extract_syntax(tree)
    if description and syntax:
        return f"{description}\n{syntax}"
    return description or syntax


def _extract_remarks(tree) -> str:
    return _extract_labeled_block(tree, ".card-remarks", "Remarks:")


def _populate_member_sections(tree, structure: ApiPageStructure) -> None:
    structure.methods = _extract_member_section(tree, "Methods")
    structure.properties = _extract_member_section(tree, "Properties")
    structure.constructors = _extract_member_section(tree, "Constructors")
    structure.namespace_classes = _extract_namespace_classes(tree)


def _parse_fallback_title(html: str, structure: ApiPageStructure) -> ApiPageStructure:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if title_match:
        structure.title = _compact_text(re.sub(r"<[^>]+>", " ", title_match.group(1)))
    structure.sections_found = ["title_only"]
    return structure


def _populate_structure_from_tree(tree, structure: ApiPageStructure) -> None:
    structure.title = _extract_title(tree)
    structure.synopsis = _extract_synopsis(tree)
    structure.remarks = _extract_remarks(tree)
    structure.parameters = _extract_parameters(tree)
    structure.returns = _extract_returns(tree)
    structure.examples = _extract_examples(tree)
    structure.see_also = _extract_see_also(tree)
    _populate_member_sections(tree, structure)
    _detect_page_type(tree, structure)
    structure.sections_found = _collect_sections(tree, structure)


def parse_rvtdocs_page(html: str) -> ApiPageStructure:
    """Parse rvtdocs.com HTML into structured API documentation."""
    structure = ApiPageStructure()

    if not html or not html.strip():
        return structure

    try:
        from selectolax.lexbor import LexborHTMLParser  # type: ignore

        tree = LexborHTMLParser(html)
    except Exception:
        return _parse_fallback_title(html, structure)

    try:
        _populate_structure_from_tree(tree, structure)
    except Exception:
        if not structure.title:
            structure.title = _extract_title(tree)
        if not structure.sections_found:
            structure.sections_found = ["partial_parse"]

    return structure


def _first_paragraph(text: str) -> str:
    if not text:
        return ""
    parts = re.split(r"\n{2,}", text.strip())
    return parts[0].strip() if parts else text.strip()


def _format_parameters(parameters: list[ApiParameter]) -> str:
    if not parameters:
        return _NONE_LABEL
    lines = ["| Name | Type | Description |", "| --- | --- | --- |"]
    for param in parameters:
        lines.append(f"| {param.name} | {param.type} | {param.description} |")
    return "\n".join(lines)


def _format_members(members: list[ApiMember], *, include_return_type: bool = True) -> str:
    if not members:
        return _NONE_LABEL
    lines: list[str] = []
    for member in members:
        obsolete = " [Obsolete]" if member.is_obsolete else ""
        if include_return_type and member.return_type:
            line = f"- {member.name} -> {member.return_type}{obsolete}"
        else:
            line = f"- {member.name}{obsolete}"
        if member.description:
            line = f"{line}: {member.description}"
        lines.append(line)
    return "\n".join(lines)


def _trim_section_content(content: str, budget: int) -> str:
    if budget <= 0:
        return ""
    if len(content) <= budget:
        return content
    if budget < 20:
        return content[:budget]
    return content[: budget - 3].rstrip() + "..."


def _apply_char_budget(sections: list[tuple[str, str]], max_chars: int) -> str:
    non_empty = [(header, body) for header, body in sections if body]
    if not non_empty:
        return ""

    rendered = [f"## {header}\n{body}" for header, body in non_empty]
    full_text = "\n\n".join(rendered)
    if len(full_text) <= max_chars:
        return full_text

    overhead = sum(len(f"## {header}\n") + 2 for header, _ in non_empty)
    content_budget = max(0, max_chars - overhead)
    total_body = sum(len(body) for _, body in non_empty)
    if total_body <= 0:
        return full_text[:max_chars]

    trimmed_sections: list[str] = []
    remaining = content_budget
    for index, (header, body) in enumerate(non_empty):
        if index == len(non_empty) - 1:
            slice_budget = remaining
        else:
            slice_budget = max(1, int(content_budget * (len(body) / total_body)))
            remaining -= slice_budget
        trimmed_sections.append(f"## {header}\n{_trim_section_content(body, slice_budget)}")

    result = "\n\n".join(trimmed_sections)
    if len(result) > max_chars:
        return result[:max_chars]
    return result


def build_structured_snippet(
    structure: ApiPageStructure,
    query_kind: str,
    max_chars: int = 12000,
) -> str:
    """Build a token-efficient snippet from structured API data."""
    limit = max(500, int(max_chars or DEFAULT_MAX_CHARS))
    kind = (query_kind or "").strip().lower()

    if kind == "namespace" or structure.is_namespace_page:
        sections = [
            (structure.title or "Namespace", ""),
            (
                f"Classes ({len(structure.namespace_classes)})",
                _format_members(
                    [ApiMember(name=name) for name in structure.namespace_classes],
                    include_return_type=False,
                ),
            ),
        ]
        if sections[0][0]:
            sections[0] = (sections[0][0], structure.synopsis)
        return _apply_char_budget(sections, limit)

    if kind == "class" or structure.is_class_page:
        sections = [
            (structure.title or "Class", structure.synopsis),
            (f"Methods ({len(structure.methods)})", _format_members(structure.methods)),
            (f"Properties ({len(structure.properties)})", _format_members(structure.properties)),
        ]
        return _apply_char_budget(sections, limit)

    sections = [
        ("Synopsis", structure.synopsis),
        ("Parameters", _format_parameters(structure.parameters)),
        ("Returns", structure.returns or _NONE_LABEL),
        ("Remarks", _first_paragraph(structure.remarks)),
    ]
    return _apply_char_budget(sections, limit)
