# AGENTS

## Overview

rvtdocs-mcp is a local-first MCP server for Revit API documentation exploration.
Downloads the full API tree index from rvtdocs.com once per version, caches in AppData,
then provides instant keyword search, namespace browsing, version comparison, and page
fetching — all offline after initial download.

## Architecture

```
rvtdocs.com/static/json_trees/sidebar_{year}.json (7MB per year)
    ↓ (download once)
%APPDATA%/rvtdocs-mcp/revit_{year}.json (cached permanently)
    ↓ (load ~350ms)
In-memory index (28K entries per year)
    ↓
Tools: search (7ms) | scan (1ms) | diff (1ms) | fetch (network)
```

## Tools (4 total)

| Tool | Purpose | Mode | Latency |
|------|---------|------|---------|
| `rvtdocs_search` | Keyword search across 28K API entries | Local index | ~7ms |
| `rvtdocs_scan` | Browse namespace or class members | Local index | ~1ms |
| `rvtdocs_diff` | Compare API between two Revit versions | Local index | ~1ms |
| `rvtdocs_fetch` | Fetch detailed page content by URL | Network + cache | 50-500ms |

## Project Structure

```
src/
  server.py           # FastMCP entry point (wiring only)
  config.py           # Constants (BASE_URL, years, limits)
  cache_store.py      # In-memory LRU page cache
  fetcher.py          # HTTP client with cache
  extractor.py        # HTML -> text (trafilatura)
  search/
    __init__.py
    tree_index.py     # Core: download, index, search, scan, scoring
  tools/
    __init__.py       # Tool registration
    search.py         # rvtdocs_search (sync, local)
    scan.py           # rvtdocs_scan (sync, local)
    diff.py           # rvtdocs_diff (sync, local)
    fetch.py          # rvtdocs_fetch (async, network)
```

## Commands

```bash
uvx --from . rvtdocs-mcp       # Run server (MCP stdio)
uv run python -c "..."          # Quick test
```

## Data

- Source: `https://rvtdocs.com/static/json_trees/sidebar_{year}.json`
- Local cache: `%APPDATA%/rvtdocs-mcp/revit_{year}.json` (Win) or `~/.cache/rvtdocs-mcp/` (Unix)
- Supported years: 2022, 2023, 2024, 2025, 2026, 2027
- Entries per year: ~28,000 (namespaces, classes, methods, properties, enums, etc.)
- Download: lazy (first query per year triggers download)

## Design Decisions

- **In-memory over DB**: 28K entries fit in ~2MB RAM. DuckDB/SQLite add complexity without benefit.
- **Download once**: Tree data is static per Revit version. No periodic refresh needed.
- **Search-first**: LLMs need discovery, not exact lookup. Vague queries surface namespaces/classes.
- **Namespace boosting**: Namespaces score 1.5x — always appear at top for broad queries.
- **Depth scoring**: Shallow FQN (+3) ranked above deep nested members (-2) for exploration.
- **Sync tools**: search/scan/diff are sync (no await). Only fetch is async (network I/O).
- **Compact output**: 4 fields per result (fqn, type, url, score) — minimal token cost.
- **trafilatura**: Reliable HTML→text without custom parsing per page type.

## MCP Config

```json
{
  "rvtdocs-mcp": {
    "type": "stdio",
    "command": "uvx",
    "args": ["--from", "c:\\Users\\truon\\source\\repos\\rvtdocs-mcp", "rvtdocs-mcp"]
  }
}
```

## Change Rules

- Adding a tool: create `src/tools/{name}.py`, register in `src/tools/__init__.py`
- Tree index changes: clear AppData cache files to force re-download
- Config changes: edit `src/config.py` (single source of truth)
- All search/scan/diff tools must remain sync (no network I/O)
- `rvtdocs_fetch` is the only async tool (network required)
