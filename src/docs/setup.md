# Setup Guide

## Prerequisites

- **Python 3.14+** — required by `pyproject.toml` (`requires-python = ">=3.14"`)
- **uv** — Python package manager and runner ([install guide](https://docs.astral.sh/uv/getting-started/installation/))

## Installation Methods

### Method 1: Local Development (from source)

Clone the repo and run directly:

```bash
# Clone (or use existing checkout)
git clone https://github.com/trgiangv/rvtdocs-mcp.git
cd rvtdocs-mcp

# Run via uv (installs deps automatically in isolated env)
uv run --python 3.14 rvtdocs-mcp

# Or run the module directly while editing source
uv run --python 3.14 python -m src.server
```

### Method 2: Run via `uvx` from local path

```bash
uvx --from /path/to/rvtdocs-mcp --python 3.14 rvtdocs-mcp
```

### Method 3: Run via `uvx` from GitHub (future)

From the GitHub repository:

```bash
uvx --from "git+https://github.com/trgiangv/rvtdocs-mcp.git" --python 3.14 rvtdocs-mcp
```

## Cursor MCP Configuration

Add to your Cursor MCP settings (`~/.cursor/mcp.json` or workspace `.cursor/mcp.json`):

### From Local Path

```json
{
  "mcpServers": {
    "rvtdocs-py": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "/absolute/path/to/rvtdocs-mcp",
        "--python",
        "3.14",
        "rvtdocs-mcp"
      ]
    }
  }
}
```

### From GitHub

```json
{
  "mcpServers": {
    "rvtdocs-py": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/trgiangv/rvtdocs-mcp.git",
        "--python",
        "3.14",
        "rvtdocs-mcp"
      ]
    }
  }
}
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RVTDOCS_MCP_TELEMETRY` | `"1"` | Set to `"0"` to disable telemetry logging |
| `RVTDOCS_MCP_TELEMETRY_DIR` | `None` | Custom directory for telemetry JSONL files |

## Dependencies

From `pyproject.toml`:

| Package | Min Version | Purpose |
|---------|-------------|---------|
| `mcp` | 1.28.1 | MCP protocol server framework (FastMCP) |
| `httpx` | 0.28 | Async HTTP client for batch concurrent fetching |
| `trafilatura` | 2.0.0 | Fallback text extraction from HTML |
| `readability-lxml` | 0.8.4.1 | Fallback content extraction |
| `selectolax` | 0.4.10 | Fast structured HTML parsing (primary extractor) |
| `pydantic` | 2.13.4 | Data validation and serialization |

## Cache Location

SQLite cache is stored at:

```
`%LOCALAPPDATA%/rvtdocs-mcp/cache.db` on Windows, or the platform-specific fallback returned by `src.cache_store.default_cache_file()`.
```

Or platform-specific default cache directory. The cache auto-migrates from legacy `cache.json` format on first access.

## Verify Installation

After configuring Cursor, reload the MCP server and test:

1. Open Cursor chat
2. Ask: "Use rvtdocs_scan to check if Wall exists in Revit 2025"
3. Expected: Tool call returns `{ "success": true, "trust": { "verdict": "pass" } }`

If tools are not visible after MCP reload, the `uvx` command may have failed. Check Cursor MCP logs for errors.

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| Tools not visible after reload | Local path or GitHub source changed | Reload MCP so `uv` or `uvx --from` resolves the latest source |
| `Python 3.14 not found` | Python 3.14 not installed | Install via `uv python install 3.14` |
| Slow first queries | Cold cache | First fetch per URL takes 1-2s. Subsequent hits are <100ms |
| `network_error` on fetch | rvtdocs.com unreachable | Check internet; server retries 2x with 1s/3s backoff |
