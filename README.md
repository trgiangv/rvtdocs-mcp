# rvtdocs-mcp

Local-first MCP server for Revit API documentation. Downloads once, searches instantly.

## Tools

| Tool | Purpose | Latency |
|------|---------|---------|
| `rvtdocs_search` | Keyword search across 28K+ API entries | ~7ms |
| `rvtdocs_scan` | Browse namespace or class members | ~1ms |
| `rvtdocs_diff` | Compare APIs between Revit versions | ~1ms |
| `rvtdocs_fetch` | Fetch full page documentation | 50-500ms |

## How it works

1. On first query per year, downloads the API tree index from rvtdocs.com (~7MB)
2. Caches permanently in `%APPDATA%/rvtdocs-mcp/` (Windows) or `~/.cache/rvtdocs-mcp/` (Unix)
3. Builds in-memory searchable index (28K entries, ~350ms load)
4. All search/scan/diff are local with <10ms latency

## Workflow

```
# 1. Explore with vague query (zero prior knowledge needed)
rvtdocs_search(query="electrical circuit", year="2025")
-> namespaces, classes, methods ranked by relevance

# 2. Browse discovered namespace
rvtdocs_scan(target="Autodesk.Revit.DB.Electrical", types="class")
-> 78 classes in that namespace

# 3. Check version compatibility
rvtdocs_diff(from_year="2025", to_year="2027", scope="Autodesk.Revit.DB.Structure")
-> +181 added, -40 removed (classes + methods)

# 4. Fetch detail for specific API
rvtdocs_fetch(url="https://rvtdocs.com/2025/Autodesk.Revit.DB.Connector")
-> full documentation with description, methods table, remarks
```

## Install

### From git (production)

```json
{
  "mcpServers": {
    "rvtdocs-mcp": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/trgiangv/rvtdocs-mcp.git", "rvtdocs-mcp"]
    }
  }
}
```

### From local source (development)

```json
{
  "mcpServers": {
    "rvtdocs-mcp": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "/path/to/rvtdocs-mcp", "rvtdocs-mcp"]
    }
  }
}
```

## Requirements

- Python >= 3.12
- Dependencies: `mcp`, `httpx`, `trafilatura`

## Supported Revit versions

2022, 2023, 2024, 2025, 2026, 2027
